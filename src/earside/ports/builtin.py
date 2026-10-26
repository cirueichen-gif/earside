"""內建端口：Windows SAPI TTS。零安裝的保底。

可調參數見 config.toml [tuning]（sapi_rate）；這裡的 175 只是預設值。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


class SapiTTS:
    def __init__(self, rate: int = 175, voice: str | None = None) -> None:
        self.rate = rate
        self.voice = voice
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            import pyttsx3

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.rate)
            if self.voice:
                self._engine.setProperty("voice", self.voice)
        return self._engine

    def warm(self) -> None:
        """在 TTS worker 的執行緒裡先把 engine 建好，避免跟串流執行緒同時初始化 COM。"""
        self._get_engine()

    def synthesize(self, text: str, voice: str | None = None) -> bytes:
        engine = self._get_engine()
        if voice:
            engine.setProperty("voice", voice)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        try:
            engine.save_to_file(text, tmp.name)
            engine.runAndWait()
            data = Path(tmp.name).read_bytes()
            if not data:
                raise RuntimeError("SAPI 沒有產出音檔")
            return data
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
