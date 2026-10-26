"""核心這一側的字幕客戶端：開進程、丟訊息、收屍。"""

from __future__ import annotations

import multiprocessing as mp
from typing import Any

from .overlay import run_overlay


class OverlayClient:
    def __init__(self, options: dict[str, Any] | None = None) -> None:
        ctx = mp.get_context("spawn")
        self._queue = ctx.Queue()
        self._proc = ctx.Process(
            target=run_overlay, args=(self._queue, options or {}), daemon=True
        )
        self._proc.start()

    def show(self, text: str) -> None:
        self._queue.put(("show", text))

    def hide(self) -> None:
        self._queue.put(("hide",))

    def close(self) -> None:
        self._queue.put(("quit",))
        self._proc.join(timeout=2.0)
        if self._proc.is_alive():
            self._proc.terminate()
