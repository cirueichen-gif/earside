from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.ears.frames import file_frames  # noqa: E402


def _write_sine(freq: float, seconds: float = 1.0, sr: int = 44100) -> str:
    t = np.arange(int(sr * seconds)) / sr
    data = np.sin(2 * np.pi * freq * t).astype(np.float32) * 0.707
    path = Path(tempfile.gettempdir()) / f"earside_sine_{freq:.0f}.wav"
    sf.write(path, data, sr)
    return str(path)


def _collect(path: str) -> np.ndarray:
    return np.concatenate(list(file_frames(path)))


class ResampleTest(unittest.TestCase):
    def test_high_frequency_is_filtered(self) -> None:
        # 12 kHz 在 16k 取樣率是混疊頻段；線性內插會折回 4 kHz 且不衰減。
        x = _collect(_write_sine(12000))
        rms = float(np.sqrt(np.mean(x**2)))
        self.assertLess(rms, 0.05, f"12k 沒有被濾掉（rms={rms:.3f}）")

    def test_passband_survives(self) -> None:
        x = _collect(_write_sine(1000))
        rms = float(np.sqrt(np.mean(x**2)))
        self.assertGreater(rms, 0.4)

    def test_frame_count_matches_duration(self) -> None:
        frames = len(list(file_frames(_write_sine(1000))))
        self.assertAlmostEqual(frames, 31, delta=1)  # 16000/512 ≈ 31.25


if __name__ == "__main__":
    unittest.main()
