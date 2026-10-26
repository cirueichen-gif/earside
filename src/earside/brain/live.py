"""一直聽：耳朵收到一句 → 大腦想 → 嘴巴說。

可調參數見 config.toml [tuning]（merge_window_s／fillers）與 [behavior]（barge_in／echo_guard_s）。
- 她講話時你開口：VAD 一偵測到人聲就取消（不等 ASR 出字）。
- 她講完後的 echo guard：把 hangover 收到自己的尾音丟掉（喇叭模式尤其重要）。
- 打斷速度：VAD onset ≈ 0.3 秒，不是等 1 秒 hangover＋ASR。
"""

from __future__ import annotations

import asyncio
import queue
import re
import time

FILLERS = set("嗯恩啊喔哦欸呃唉齁嘿ㄟ")
MERGE_WINDOW = 0.45


def _is_filler(text: str, fillers: set[str] | None = None) -> bool:
    pool = fillers if fillers is not None else FILLERS
    clean = re.sub(r"[\s，。！？、,.!?~～…]+", "", text or "")
    return 0 < len(clean) <= 3 and all(ch in pool for ch in clean)


class LiveLoop:
    def __init__(
        self,
        conversation,
        listener,
        barge_in: bool = True,
        echo_guard_s: float = 0.4,
        merge_window_s: float = MERGE_WINDOW,
        fillers: set[str] | None = None,
    ) -> None:
        self.conversation = conversation
        self.listener = listener
        self.barge_in = barge_in
        self.echo_guard_s = echo_guard_s
        self.merge_window = merge_window_s
        self.fillers = fillers if fillers is not None else FILLERS
        self.speaking = False
        self.queue: queue.Queue[str] = queue.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._barged = False
        self._reply_started = 0.0
        self._echo_window: tuple[float, float] | None = None
        listener.on_text = self._on_text
        listener.on_speech_start = self._on_speech_start

    # --- 從 listener 執行緒進來的回呼 -------------------------------------
    def _on_speech_start(self) -> None:
        if not (self.speaking and self.barge_in) or self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._barge_now)

    def _on_text(self, text: str, utt: dict) -> None:
        print(f"[heard {utt.get('rms', 0):.3f}] {text}", flush=True)
        if _is_filler(text, self.fillers):
            return
        wall = utt.get("wall_start")
        # 回音判斷用「這句話開始講的 wall-clock」，不是「文字到達時間」。
        if not self._barged and self._echo_window and wall is not None:
            low, high = self._echo_window
            if low - 0.2 <= wall <= high:
                print(f"[echo] {text}", flush=True)
                return
            if wall > high:
                self._echo_window = None
        if self.speaking:
            if self.barge_in and self._loop is not None:
                self._loop.call_soon_threadsafe(self._barge_in, text)
            return
        self.queue.put(text)

    # --- 事件迴圈這一側 ---------------------------------------------------
    def _barge_now(self) -> None:
        if not self.speaking:
            return
        self._barged = True
        print("[barge: onset]", flush=True)
        self.conversation.cancel()

    def _barge_in(self, text: str) -> None:
        if not self.speaking:
            self.queue.put(text)
            return
        self._barged = True
        print(f"[barge] {text}", flush=True)
        self.conversation.cancel()
        self.queue.put(text)

    def _drain(self) -> list[str]:
        parts: list[str] = []
        while True:
            try:
                parts.append(self.queue.get_nowait())
            except queue.Empty:
                return parts

    async def run(self, seconds: float | None = None) -> None:
        self._loop = asyncio.get_running_loop()
        self.listener.start()
        ready = await asyncio.to_thread(self.listener.ready.wait, 20.0)
        if not ready or self.listener.error:
            raise RuntimeError(self.listener.error or "麥克風 20 秒沒有回應")

        deadline = time.monotonic() + seconds if seconds else None
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                return
            try:
                first = await asyncio.to_thread(self.queue.get, True, 0.2)
            except queue.Empty:
                continue
            await asyncio.sleep(self.merge_window)
            text = "".join([first, *self._drain()])
            if self.speaking:
                continue
            self.speaking = True
            self._barged = False
            self._reply_started = time.monotonic()
            try:
                await self.conversation.reply(text)
            except Exception as exc:  # noqa: BLE001 - 一輪失敗不能結束陪伴
                print(f"[error] {exc}", flush=True)
            finally:
                self.speaking = False
                if not self._barged and self.conversation.last_play_end:
                    self._echo_window = (
                        self._reply_started,
                        self.conversation.last_play_end + self.echo_guard_s,
                    )
