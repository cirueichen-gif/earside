from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.ears.listener import transcribe_file  # noqa: E402


def _speech_wav() -> str:
    from earside.ports.builtin import SapiTTS

    data = SapiTTS().synthesize("今天天氣很好，這是一段測試語音。")
    path = Path(tempfile.gettempdir()) / "earside_test_speech.wav"
    path.write_bytes(data)
    return str(path)


def _silence_wav(seconds: float = 3.0) -> str:
    path = Path(tempfile.gettempdir()) / "earside_test_silence.wav"
    sf.write(path, np.zeros(int(16000 * seconds), dtype=np.float32), 16000)
    return str(path)


@unittest.skipUnless(sys.platform == "win32", "SAPI 只在 Windows")
class VadTest(unittest.TestCase):
    def test_speech_is_detected(self) -> None:
        rows = transcribe_file(_speech_wav(), asr=None)
        self.assertGreaterEqual(len(rows), 1, "VAD 沒有切出任何句子")
        self.assertGreater(sum(r["seconds"] for r in rows), 0.8)

    def test_silence_is_ignored(self) -> None:
        self.assertEqual(transcribe_file(_silence_wav(), asr=None), [])


if __name__ == "__main__":
    unittest.main()
