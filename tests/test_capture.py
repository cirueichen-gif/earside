from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.eyes.capture import (  # noqa: E402
    CaptureSession,
    find_window,
    get_client_rect,
    get_window_rect,
)

# 這個測試真的會開記事本、抓視窗；預設跳過，免得每次跑測試都閃一個視窗。
RUN_CAPTURE = os.environ.get("EARSIDE_CAPTURE_TEST") == "1"


@unittest.skipUnless(
    sys.platform == "win32" and RUN_CAPTURE,
    "set EARSIDE_CAPTURE_TEST=1 才跑（會開記事本視窗）",
)
class CaptureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.proc = subprocess.Popen(["notepad.exe"])
        time.sleep(1.2)
        cls.hwnd = find_window("記事本|Notepad")
        cls.session = CaptureSession(hwnd=cls.hwnd)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.session.close()
        user32 = ctypes.windll.user32
        if cls.hwnd and user32.IsWindow(cls.hwnd):
            user32.PostMessageW(cls.hwnd, 0x0010, 0, 0)  # WM_CLOSE
        time.sleep(0.5)
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=2)
            except Exception:  # noqa: BLE001
                cls.proc.kill()

    def test_rect(self) -> None:
        left, top, width, height = get_window_rect(self.hwnd)
        self.assertGreater(width, 100)
        self.assertGreater(height, 100)
        c_left, c_top, c_w, c_h = get_client_rect(self.hwnd)
        self.assertGreater(c_w, 100)
        self.assertGreater(c_h, 100)

    def test_grab(self) -> None:
        self.assertEqual(self.session.backend_name, "mss")
        frame = self.session.grab()
        self.assertEqual(frame.ndim, 3)
        self.assertEqual(frame.shape[2], 3)
        self.assertEqual(frame.dtype, np.uint8)
        self.assertGreater(float(frame.std()), 0.0, "擷取到全黑畫面")

    def test_roi_and_clamp(self) -> None:
        roi = self.session.grab_region((0.1, 0.1, 0.3, 0.2))
        self.assertEqual(roi.shape[2], 3)
        clamped = self.session.grab_region((-0.5, -0.5, 1.5, 1.5))
        self.assertGreater(clamped.shape[0], 0)
        self.assertGreater(clamped.shape[1], 0)

    def test_benchmark(self) -> None:
        started = time.perf_counter()
        for _ in range(5):
            self.session.grab()
        avg_ms = (time.perf_counter() - started) * 1000 / 5
        print(f"\n[capture] 5 grabs avg {avg_ms:.2f} ms")
        self.assertLess(avg_ms, 100.0)


if __name__ == "__main__":
    unittest.main()
