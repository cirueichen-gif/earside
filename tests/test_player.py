from __future__ import annotations

import io
import sys
import threading
import time
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.mouth.player import PlaybackBridge  # noqa: E402


def _has_output_device() -> bool:
    try:
        import sounddevice as sd

        sd.query_devices(kind="output")
        return True
    except Exception:  # noqa: BLE001 - CI 沒有音訊裝置就跳過
        return False


HAS_OUTPUT = _has_output_device()


def silent_wav(seconds: float, sr: int = 48000) -> bytes:
    data = np.zeros(int(seconds * sr), dtype=np.float32)
    buf = io.BytesIO()
    sf.write(buf, data, sr, format="WAV")
    return buf.getvalue()


class PlayerTest(unittest.TestCase):
    @unittest.skipUnless(HAS_OUTPUT, "沒有音訊輸出裝置")
    def test_play_returns_duration(self) -> None:
        player = PlaybackBridge()
        try:
            duration = player.play(silent_wav(0.3))
            self.assertAlmostEqual(duration, 0.3, places=2)
        finally:
            player.close()

    @unittest.skipUnless(HAS_OUTPUT, "沒有音訊輸出裝置")
    def test_stop_returns_quickly_and_keeps_stream(self) -> None:
        player = PlaybackBridge()
        stream_before = player._stream  # noqa: SLF001 - 就是要驗 stream 沒被換掉
        try:
            thread = threading.Thread(target=player.play, args=(silent_wav(2.0),))
            thread.start()
            time.sleep(0.2)
            started = time.perf_counter()
            player.stop()
            thread.join(timeout=1.0)
            elapsed = time.perf_counter() - started
            self.assertLess(elapsed, 0.3)
            self.assertIs(player._stream, stream_before)  # noqa: SLF001
        finally:
            player.close()


if __name__ == "__main__":
    unittest.main()
