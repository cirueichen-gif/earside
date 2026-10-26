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
import threading
import time
from collections import deque

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
        sentinel=None,
        triggers=None,
        silence_s: float = 240.0,
        max_proactive_per_hour: int = 3,
        combat_exit_s: float = 45.0,
        eye=None,
        linebank=None,
    ) -> None:
        self.conversation = conversation
        self.listener = listener
        self.sentinel = sentinel
        self.triggers = triggers
        self.eye = eye
        self.linebank = linebank
        self.silence_s = silence_s
        self.max_proactive_per_hour = max_proactive_per_hour
        self.combat_exit_s = combat_exit_s
        self._last_activity = time.monotonic()
        self._proactive: deque[float] = deque()
        self._combat_until = 0.0
        self._sentinel_stop: threading.Event | None = None
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
        self._last_activity = time.monotonic()
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
    def _note_event(self, event: dict, now: float | None = None) -> None:
        """畫面變化大→進戰鬥模式；戰鬥中不主動找話。"""
        now = time.monotonic() if now is None else now
        metrics = event.get("metrics") or {}
        try:
            diff = float(metrics.get("diff_ratio", 0.0))
        except (TypeError, ValueError):
            diff = 0.0
        if event.get("on") and diff >= 0.25:
            self._combat_until = now + self.combat_exit_s

    async def _maybe_proactive(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if self.speaking or now < self._combat_until:
            return
        if now - self._last_activity < self.silence_s:
            return
        while self._proactive and self._proactive[0] < now - 3600.0:
            self._proactive.popleft()
        if len(self._proactive) >= self.max_proactive_per_hour:
            return
        self._proactive.append(now)
        self._last_activity = now
        self.speaking = True
        try:
            await self.conversation.reply(
                "（你已經沉默一段時間了。主動跟玩家說一句，短，不要編畫面外的東西。）"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[error] {exc}", flush=True)
        finally:
            self.speaking = False

    def _on_sentinel_event(self, event: dict) -> None:
        self._note_event(event)
        if self._loop is None:
            return
        actions = (
            self.triggers.actions_for(event, speaking=self.speaking)
            if self.triggers is not None
            else []
        )
        if not actions:
            return
        self._loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self._handle_actions(event, actions))
        )

    async def _handle_actions(self, event: dict, actions: list[dict]) -> None:
        if self.speaking or time.monotonic() < self._combat_until:
            return
        self.speaking = True
        try:
            for action in actions:
                if action.get("type") != "say":
                    continue
                if action.get("source") == "linebank":
                    entry = (
                        self.linebank.pick(action.get("bank"))
                        if self.linebank is not None
                        else None
                    )
                    if entry is not None:
                        await self.conversation.play_wav(entry[0], entry[1])
                    else:
                        print(
                            f"[sentinel] 短句庫沒有：{action.get('bank')}",
                            flush=True,
                        )
                    continue
                if action.get("source") == "llm":
                    vision_text = ""
                    trigger = action.get("trigger") or {}
                    if trigger.get("vision") and self.eye is not None:
                        vision_text = await self._look()
                    prompt = (
                        f"（哨兵事件：{event.get('type')}。"
                        f"{vision_text}"
                        "用一句話主動提醒或吐槽，短，不要編畫面外的東西。）"
                    )
                    await self.conversation.reply(prompt)
        finally:
            self.speaking = False

    async def _look(self) -> str:
        """叫眼睛看一眼；沒畫面／沒預算就回空字串。"""
        frame = getattr(self.sentinel, "last_frame", None)
        preset = getattr(self.sentinel, "preset", None)
        if frame is None or preset is None:
            return ""
        wanted = (getattr(preset, "vision", {}) or {}).get("regions") or []
        regions = [(r.name, r.rect) for r in preset.regions if r.name in wanted]
        try:
            text = await asyncio.to_thread(self.eye.describe, frame, regions)
        except Exception as exc:  # noqa: BLE001
            print(f"[eye] {exc}", flush=True)
            return ""
        return f"畫面：{text}。" if text else ""

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

        if self.sentinel is not None:
            self._sentinel_stop = threading.Event()
            threading.Thread(
                target=self.sentinel.run,
                args=(self._on_sentinel_event, None, self._sentinel_stop),
                daemon=True,
            ).start()

        deadline = time.monotonic() + seconds if seconds else None
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                return
            try:
                first = await asyncio.to_thread(self.queue.get, True, 0.2)
            except queue.Empty:
                await self._maybe_proactive()
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

    def stop_sentinel(self) -> None:
        if self._sentinel_stop is not None:
            self._sentinel_stop.set()
