"""對話迴路：文字進 → LLM 串流 → 逐句 TTS → 播放＋字幕。"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Callable

from .sentences import speakable, split_sentences
from ..mouth.tts_worker import TtsWorker

SYSTEM_DEFAULT = """你是「耳邊」，坐在玩家耳機裡的陪玩。
- 一句話、最多兩句；講話要短，會被念出來。
- 不要 markdown、表情符號、網址、程式碼。
- 只講你看得到或聽得到的事；看不到就不要編。
- 語氣像朋友，不是客服。"""


def _stream_in_thread(stream_fn, messages: list[dict], loop: asyncio.AbstractEventLoop):
    """同步 generator 丟到執行緒跑，token 用 call_soon_threadsafe 送回事件迴圈。"""
    q: asyncio.Queue = asyncio.Queue()

    def worker() -> None:
        try:
            for token in stream_fn(messages):
                loop.call_soon_threadsafe(q.put_nowait, ("tok", token))
        except Exception as exc:  # noqa: BLE001 - 交給 consumer 決定降級
            loop.call_soon_threadsafe(q.put_nowait, ("err", exc))
        finally:
            loop.call_soon_threadsafe(q.put_nowait, ("end", None))

    threading.Thread(target=worker, daemon=True).start()
    return q


class Conversation:
    def __init__(
        self,
        llm,
        tts,
        player,
        voice=None,
        overlay=None,
        persona: str | None = None,
        max_turns: int = 10,
        on_speak: Callable[[str], None] | None = None,
        sentence_max_len: int = 42,
        sentence_soft_len: int = 24,
    ) -> None:
        self.llm = llm
        self.tts = tts
        self.tts_worker = None  # 真正要念時才開執行緒（SAPI 不能在串流期間先初始化 COM）
        self.player = player
        self.voice = voice
        self.overlay = overlay
        self.on_speak = on_speak
        self.system = persona or SYSTEM_DEFAULT
        self.max_turns = max_turns
        self.sentence_max_len = sentence_max_len
        self.sentence_soft_len = sentence_soft_len
        self.history: list[dict] = []
        self._cancelled = False
        self.last_play_end = 0.0
        self.stats = {
            "sentences": 0,
            "first_token_ms": None,
            "speak_ms": [],
        }

    def _messages(self, text: str) -> list[dict]:
        messages = [{"role": "system", "content": self.system}]
        messages.extend(self.history[-(self.max_turns * 2) :])
        messages.append({"role": "user", "content": text})
        return messages

    def cancel(self) -> None:
        """打斷：停止播放、丟掉這一輪剩下的句子。"""
        self._cancelled = True
        try:
            self.player.stop()
        except Exception:  # noqa: BLE001
            pass
        if self.overlay is not None:
            try:
                self.overlay.hide()
            except Exception:  # noqa: BLE001
                pass

    async def _speak(self, text: str) -> None:
        if self._cancelled:
            return
        clean = speakable(text)
        if not clean:
            return
        if self.on_speak is not None:
            self.on_speak(clean)
        t0 = time.perf_counter()
        if self.tts_worker is None:
            self.tts_worker = TtsWorker(self.tts)
        wav = await self.tts_worker.synthesize(clean)  # 專用執行緒，COM 綁在那條上
        if self._cancelled:
            return
        if self.voice is not None:
            wav = await asyncio.to_thread(self.voice.convert, wav, 0)
        if self._cancelled:
            return
        if self.overlay is not None:
            self.overlay.show(clean)
        await self.player.play_async(wav)
        self.last_play_end = time.monotonic()
        if self._cancelled:
            return
        self.stats["sentences"] += 1
        self.stats["speak_ms"].append(1000 * (time.perf_counter() - t0))
        if self.overlay is not None:
            await asyncio.sleep(1.0)
            if not self._cancelled:
                self.overlay.hide()

    async def reply(self, text: str) -> None:
        self._cancelled = False
        self.stats["first_token_ms"] = None
        loop = asyncio.get_running_loop()
        queue = _stream_in_thread(self.llm.stream, self._messages(text), loop)
        started = time.perf_counter()
        buffer = ""
        spoken: list[str] = []

        while not self._cancelled:
            kind, value = await queue.get()
            if kind == "end":
                break
            if kind == "err":
                raise value
            if self.stats["first_token_ms"] is None:
                self.stats["first_token_ms"] = 1000 * (time.perf_counter() - started)
            buffer += value
            ready, buffer = split_sentences(
                buffer, max_len=self.sentence_max_len, soft_len=self.sentence_soft_len
            )
            for sentence in ready:
                if self._cancelled:
                    break
                spoken.append(sentence)
                await self._speak(sentence)

        if buffer.strip() and not self._cancelled:
            spoken.append(buffer.strip())
            await self._speak(buffer)

        if spoken and not self._cancelled:
            self.history.append({"role": "user", "content": text})
            self.history.append(
                {"role": "assistant", "content": "".join(spoken).strip()}
            )

    def close(self) -> None:
        if self.tts_worker is not None:
            self.tts_worker.close()
