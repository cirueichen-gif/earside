"""TTS 專用執行緒：COM 物件（SAPI）綁在建立它的執行緒上，不能跨執行緒共用。"""

from __future__ import annotations

import asyncio
import concurrent.futures
import queue
import threading


class TtsWorker:
    def __init__(self, tts) -> None:
        self._tts = tts
        self._queue: queue.Queue = queue.Queue()
        self._closed = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        # Windows COM：SAPI 的訊息幫浦要 STA；worker 執行緒預設是 MTA，
        # 不顯式 CoInitializeEx 會卡在 runAndWait 的 startLoop 裡。
        pythoncom = None
        try:
            import pythoncom as _pythoncom

            _pythoncom.CoInitializeEx(_pythoncom.COINIT_APARTMENTTHREADED)
            pythoncom = _pythoncom
        except Exception:  # noqa: BLE001 - 非 Windows／沒有 pywin32 就用原樣
            pythoncom = None
        try:
            warm = getattr(self._tts, "warm", None)
            if callable(warm):
                warm()
            while True:
                item = self._queue.get()
                if item is None:
                    return
                text, future = item
                try:
                    future.set_result(self._tts.synthesize(text))
                except BaseException as exc:  # noqa: BLE001 - 原樣交回呼叫端
                    future.set_exception(exc)
        finally:
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:  # noqa: BLE001
                    pass

    async def synthesize(self, text: str) -> bytes:
        if self._closed:
            raise RuntimeError("TTS worker 已關閉")
        future: concurrent.futures.Future = concurrent.futures.Future()
        self._queue.put((text, future))
        return await asyncio.wrap_future(future)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._thread.join(timeout=2.0)
