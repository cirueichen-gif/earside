from __future__ import annotations

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.eyes.vision import compose_frame  # noqa: E402


class ComposeLayoutTest(unittest.TestCase):
    def test_many_tall_rois_stay_in_bounds(self) -> None:
        # 瘦高 ROI 夠多時會走「貼下方」版面；以前的 combined_w 少算 8px 間距會越界。
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        regions = [(f"r{i}", (i * 0.14, 0.1, 0.05, 0.5)) for i in range(6)]
        data = compose_frame(frame, regions)
        img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(img)
        self.assertGreater(img.shape[1], 320)

    def test_ten_tall_rois_stay_under_byte_limit(self) -> None:
        frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
        regions = [(f"r{i}", (i * 0.09, 0.1, 0.05, 0.5)) for i in range(10)]
        data = compose_frame(frame, regions, max_bytes=1_000_000)
        self.assertLessEqual(len(data), 1_000_000)


if __name__ == "__main__":
    unittest.main()
