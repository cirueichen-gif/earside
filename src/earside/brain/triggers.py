"""觸發器：哨兵事件 → 動作（冷卻、上限、說話中跳過）。

只決定「該不該做、做哪一種」，不碰音訊；由呼叫端執行。
"""

from __future__ import annotations

import time
from collections import deque


class TriggerEngine:
    def __init__(self, triggers: list[dict]) -> None:
        self.triggers = list(triggers or [])
        self._last_fired: dict[int, float] = {}
        self._calls: deque[tuple[int, float]] = deque()
        self._hour_calls: deque[tuple[int, float]] = deque()

    def _prune(self, now: float) -> None:
        while self._calls and self._calls[0][1] < now - 60.0:
            self._calls.popleft()
        while self._hour_calls and self._hour_calls[0][1] < now - 3600.0:
            self._hour_calls.popleft()

    def _recent(self, index: int, now: float) -> int:
        return sum(1 for i, _ in self._calls if i == index)

    def _recent_hour(self, index: int, now: float) -> int:
        return sum(1 for i, _ in self._hour_calls if i == index)

    def actions_for(
        self, event: dict, speaking: bool = False, now: float | None = None
    ) -> list[dict]:
        now = time.monotonic() if now is None else now
        self._prune(now)
        wanted = event.get("type")
        actions: list[dict] = []

        for index, trigger in enumerate(self.triggers):
            if trigger.get("on") != wanted:
                continue
            if speaking and trigger.get("skip_if_speaking"):
                continue

            cooldown = float(trigger.get("cooldown_s", 0))
            if index in self._last_fired and now - self._last_fired[index] < cooldown:
                continue

            max_per_min = trigger.get("max_per_min")
            if max_per_min is not None and self._recent(index, now) >= int(max_per_min):
                continue

            max_per_hour = trigger.get("max_per_hour")
            if max_per_hour is not None and self._recent_hour(
                index, now
            ) >= int(max_per_hour):
                continue

            self._last_fired[index] = now
            self._calls.append((index, now))
            self._hour_calls.append((index, now))
            actions.append(
                {
                    "type": trigger.get("do", "say"),
                    "source": trigger.get("source", "linebank"),
                    "bank": trigger.get("bank"),
                    "event": event,
                    "trigger": trigger,
                }
            )
        return actions
