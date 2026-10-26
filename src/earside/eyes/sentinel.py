"""哨兵 runner：擷取→區域→規則→邊緣事件（on/off）。

`watch` 與之後的 `chat` 共用同一套；不要每個地方各寫一次迴圈。
"""

from __future__ import annotations

import time
from typing import Callable

from .capture import crop_norm
from .preset import Preset
from .rules import RuleEngine


class SentinelRunner:
    def __init__(self, preset: Preset, capture, engine: RuleEngine) -> None:
        self.preset = preset
        self.capture = capture
        self.engine = engine
        self.state = {region.name: False for region in preset.regions}
        self.due = {region.name: 0.0 for region in preset.regions}
        self.last_frame = None

    def poll(self, now: float | None = None) -> list[dict]:
        """跑一輪；回傳這一輪的邊緣事件（狀態真的變了才回）。"""
        now = time.monotonic() if now is None else now
        due = [r for r in self.preset.regions if now >= self.due[r.name]]
        if not due:
            return []

        frame = self.capture.grab()  # 多區共用一次抓圖
        self.last_frame = frame
        events: list[dict] = []
        for region in due:
            self.due[region.name] = now + region.interval_ms / 1000.0
            roi = crop_norm(frame, region.rect)
            result = self.engine.evaluate(region.name, roi)
            if result["on"] == self.state[region.name]:
                continue
            self.state[region.name] = result["on"]
            events.append(
                {
                    "type": f"{region.name}.{'on' if result['on'] else 'off'}",
                    "region": region.name,
                    "on": bool(result["on"]),
                    "score": float(result["score"]),
                    "metrics": result["metrics"],
                    "ts": now,
                }
            )
        return events

    def run(
        self,
        on_event: Callable[[dict], None],
        seconds: float | None = None,
        stop_event=None,
    ) -> None:
        deadline = time.monotonic() + seconds if seconds else None
        while not (stop_event and stop_event.is_set()):
            if deadline is not None and time.monotonic() >= deadline:
                return
            for event in self.poll():
                on_event(event)
            time.sleep(0.02)
