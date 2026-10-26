"""PlaybackBridge：PortAudio callback 只做複製轉發，不碰 asyncio。

可調參數見 config.toml [tuning]（playback_samplerate）；這裡的 48000 只是預設值。
打斷用 abort flag ＋清空緩衝，不重建 stream（重建會慢、會爆音）。
"""

from __future__ import annotations

import asyncio
import io
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf


class PlaybackBridge:
    def __init__(self, samplerate: int = 48000, channels: int = 1) -> None:
        self.samplerate = samplerate
        self.channels = channels
        self._lock = threading.Lock()
        self._buf = np.zeros(0, dtype=np.float32)
        self._pos = 0
        self._done = threading.Event()
        self._abort = threading.Event()
        self._closed = False
        self._stream = sd.OutputStream(
            samplerate=samplerate,
            channels=channels,
            dtype="float32",
            callback=self._callback,
            blocksize=0,
        )
        self._stream.start()

    # --- callback：只做記憶體複製，不准 await、不准呼叫 asyncio ---
    def _callback(self, outdata, frames, time_info, status) -> None:  # noqa: ANN001
        outdata.fill(0)
        with self._lock:
            if self._abort.is_set() or self._pos >= len(self._buf):
                if self._pos >= len(self._buf) and not self._done.is_set():
                    self._done.set()
                return
            chunk = self._buf[self._pos : self._pos + frames]
            outdata[: len(chunk), 0] = chunk
            self._pos += len(chunk)
            if self._pos >= len(self._buf):
                self._done.set()

    def play(self, wav: bytes, wait: bool = True) -> float:
        """播一段 wav，回傳時長（秒）。wait=False 時不阻塞。"""
        data, sr = sf.read(io.BytesIO(wav), dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sr != self.samplerate and len(data) > 0:
            n = int(len(data) * self.samplerate / sr)
            data = np.interp(
                np.linspace(0, len(data) - 1, n), np.arange(len(data)), data
            ).astype(np.float32)
        with self._lock:
            self._abort.clear()
            self._done.clear()
            self._buf = np.ascontiguousarray(data, dtype=np.float32)
            self._pos = 0
        if wait:
            self._done.wait()
        return len(data) / self.samplerate

    def stop(self) -> None:
        with self._lock:
            self._abort.set()
            self._buf = np.zeros(0, dtype=np.float32)
            self._pos = 0
            self._done.set()

    async def play_async(self, wav: bytes) -> float:
        """asyncio 唯一入口：等待放到 thread，不凍結事件迴圈。

        callback 仍然只碰記憶體（見 _callback）；這裡只負責「等它播完」。
        """
        return await asyncio.to_thread(self.play, wav, True)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.stop()
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self) -> "PlaybackBridge":
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        self.close()
