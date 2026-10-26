"""事件匯流排。核心各模組只透過事件講話，不互相 import。"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass(slots=True)
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


Handler = Callable[[Event], Awaitable[None] | None]


class EventBus:
    def __init__(self, keep: int = 200) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._recent: deque[Event] = deque(maxlen=keep)
        self._lock = asyncio.Lock()

    def on(self, event_type: str, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def off(self, event_type: str, handler: Handler) -> None:
        if handler in self._handlers.get(event_type, []):
            self._handlers[event_type].remove(handler)

    async def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        event = Event(event_type, data or {})
        self._recent.append(event)
        for handler in list(self._handlers.get(event_type, [])) + list(
            self._handlers.get("*", [])
        ):
            result = handler(event)
            if inspect.isawaitable(result):
                await result

    def recent(self, limit: int = 20) -> list[Event]:
        return list(self._recent)[-limit:]
