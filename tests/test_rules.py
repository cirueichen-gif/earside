"""Tests for eyes rules and preset loading/validation."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.eyes.preset import Preset, Region, load_preset
from earside.eyes.rules import RuleEngine


class TestPresetValidation(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _write_preset(self, data: dict) -> Path:
        p = Path(self.test_dir) / "test_preset.json"
        with p.open("w", encoding="utf-8") as f:
            json.dump(data, f)
        return p

    def test_valid_preset(self):
        data = {
            "id": "test_game",
            "name": "Test Game",
            "match": {"window_title_regex": "Test"},
            "reference_aspect": 1.777,
            "regions": [
                {
                    "name": "r1",
                    "rect": [0.1, 0.2, 0.3, 0.4],
                    "interval_ms": 200,
                    "rule": {"type": "change", "diff_ratio": 0.1},
                }
            ],
            "triggers": [],
            "vision": {},
        }
        p = self._write_preset(data)
        loaded = load_preset(p)
        self.assertEqual(loaded.id, "test_game")
        self.assertEqual(len(loaded.regions), 1)
        self.assertEqual(loaded.regions[0].rect, (0.1, 0.2, 0.3, 0.4))

    def test_missing_rect(self):
        data = {
            "id": "test_game",
            "name": "Test Game",
            "match": {},
            "reference_aspect": 1.6,
            "regions": [
                {
                    "name": "r1",
                    "interval_ms": 200,
                    "rule": {"type": "change"},
                }
            ],
        }
        p = self._write_preset(data)
        with self.assertRaises(ValueError) as ctx:
            load_preset(p)
        self.assertIn("rect", str(ctx.exception))

    def test_rect_out_of_bounds(self):
        data = {
            "id": "test_game",
            "name": "Test Game",
            "match": {},
            "reference_aspect": 1.6,
            "regions": [
                {
                    "name": "r1",
                    "rect": [0.1, 1.2, 0.3, 0.4],  # 1.2 > 1.0
                    "interval_ms": 200,
                    "rule": {"type": "change"},
                }
            ],
        }
        p = self._write_preset(data)
        with self.assertRaises(ValueError) as ctx:
            load_preset(p)
        self.assertIn("out of bounds", str(ctx.exception))

    def test_duplicate_region_name(self):
        data = {
            "id": "test_game",
            "name": "Test Game",
            "match": {},
            "reference_aspect": 1.6,
            "regions": [
                {
                    "name": "duplicate_name",
                    "rect": [0.1, 0.1, 0.1, 0.1],
                    "interval_ms": 100,
                    "rule": {"type": "change"},
                },
                {
                    "name": "duplicate_name",
                    "rect": [0.2, 0.2, 0.1, 0.1],
                    "interval_ms": 100,
                    "rule": {"type": "change"},
                },
            ],
        }
        p = self._write_preset(data)
        with self.assertRaises(ValueError) as ctx:
            load_preset(p)
        self.assertIn("Duplicate region name", str(ctx.exception))


class TestRulesExecution(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_luma_sat_drop_name_area(self):
        """1. 名字區：背景亮、名字亮 -> off；把名字塗黑（target 變暗、bg 不變）-> 連續幾幀後 on."""
        preset = Preset(
            id="test_death",
            name="Test Death",
            match={},
            reference_aspect=1.6,
            regions=[
                Region(
                    name="self_name",
                    rect=(0.4, 0.9, 0.2, 0.05),
                    interval_ms=200,
                    rule={
                        "type": "luma_sat_drop",
                        "luma_ratio": 0.6,
                        "sat_ratio": 0.5,
                        "consecutive": 3,
                        "bg_ring": 0.1,  # 10% outer border is ring
                    },
                )
            ],
        )
        engine = RuleEngine(preset)

        # Create bright frame: 100x40.
        # Ring (outer border) and center (name) both bright and saturated
        # HSV: S=200, V=220 -> in BGR
        bright_hsv = np.full((40, 100, 3), (25, 200, 220), dtype=np.uint8)
        bright_bgr = cv2.cvtColor(bright_hsv, cv2.COLOR_HSV2BGR)

        # Dark name frame: ring stays same bright, center (target) painted black/gray (low sat, low luma)
        dark_hsv = bright_hsv.copy()
        # ring_px_x = 10, ring_px_y = 4
        # inner area: [4:36, 10:90]
        dark_hsv[4:36, 10:90] = (0, 10, 20)  # low saturation, low value
        dark_bgr = cv2.cvtColor(dark_hsv, cv2.COLOR_HSV2BGR)

        # Feed 16 bright frames (interval 200ms -> >3000ms, excluding 2000ms gives >=5 baseline samples)
        for i in range(16):
            res = engine.evaluate("self_name", bright_bgr)
            self.assertFalse(res["on"])

        # Baseline should now be established
        self.assertIn("r0", res["metrics"])
        self.assertGreater(res["metrics"]["r0"], 0.5)

        # Now paint name dark, evaluate consecutive frames
        # With temporal 5-frame smoothing + consecutive 3:
        # After 5 dark frames, both smoothed R and raw R drop below threshold and trigger consecutively.
        on_history = []
        for _ in range(6):
            res = engine.evaluate("self_name", dark_bgr)
            on_history.append(res["on"])

        # Early frames are False, later frames become True
        self.assertFalse(on_history[0])
        self.assertTrue(on_history[-1])
        self.assertTrue(res["on"])
        self.assertGreater(res["score"], 0.5)

    def test_blob_count_red_dots(self):
        """2. 紅色 blob：黑底畫 3 顆紅點 -> blob_count=3，on；全黑 -> off."""
        preset = Preset(
            id="test_blob",
            name="Test Blob",
            match={},
            reference_aspect=1.6,
            regions=[
                Region(
                    name="minimap",
                    rect=(0.0, 0.0, 0.2, 0.2),
                    interval_ms=500,
                    rule={
                        "type": "blob_count",
                        # Red wraps around 0 and 180 in OpenCV HSV (H: 0-10 or 170-180)
                        # We test standard red range [170, 10, 100, 255, 100, 255]
                        "hsv": [170, 10, 100, 255, 100, 255],
                        "min_area_px": 4,
                        "max_area_px": 100,
                        "min_count": 3,
                    },
                )
            ],
        )
        engine = RuleEngine(preset)

        # Pure black frame
        black_bgr = np.zeros((100, 100, 3), dtype=np.uint8)
        res_black = engine.evaluate("minimap", black_bgr)
        self.assertFalse(res_black["on"])
        self.assertEqual(res_black["metrics"]["blob_count"], 0)

        # Draw 3 separated red blobs (red in BGR is (0, 0, 255))
        dots_bgr = black_bgr.copy()
        cv2.circle(dots_bgr, (25, 25), 3, (0, 0, 255), -1)
        cv2.circle(dots_bgr, (50, 50), 3, (0, 0, 255), -1)
        cv2.circle(dots_bgr, (75, 75), 3, (0, 0, 255), -1)

        res_dots = engine.evaluate("minimap", dots_bgr)
        self.assertEqual(res_dots["metrics"]["blob_count"], 3)
        self.assertTrue(res_dots["on"])

    def test_change_detector(self):
        """3. change：同圖 -> off；整張變白 -> on."""
        preset = Preset(
            id="test_change",
            name="Test Change",
            match={},
            reference_aspect=1.6,
            regions=[
                Region(
                    name="kill_feed",
                    rect=(0.7, 0.0, 0.3, 0.2),
                    interval_ms=500,
                    rule={"type": "change", "diff_ratio": 0.2, "consecutive": 1},
                )
            ],
        )
        engine = RuleEngine(preset)

        img1 = np.full((100, 100, 3), 50, dtype=np.uint8)
        # Frame 1 (first frame) -> off
        r1 = engine.evaluate("kill_feed", img1)
        self.assertFalse(r1["on"])

        # Frame 2 (same image) -> off
        r2 = engine.evaluate("kill_feed", img1)
        self.assertFalse(r2["on"])
        self.assertEqual(r2["metrics"]["diff_ratio"], 0.0)

        # Frame 3 (change entire image to bright white 255) -> on
        img_white = np.full((100, 100, 3), 255, dtype=np.uint8)
        r3 = engine.evaluate("kill_feed", img_white)
        self.assertTrue(r3["on"])
        self.assertGreaterEqual(r3["metrics"]["diff_ratio"], 0.9)

    def test_template_match(self):
        """4. template：用一張小圖當模板貼回大圖 -> on."""
        # Create a small template image
        tpl_img = np.zeros((20, 20, 3), dtype=np.uint8)
        cv2.circle(tpl_img, (10, 10), 8, (0, 255, 255), -1)  # Yellow circle
        tpl_path = Path(self.test_dir) / "skull.png"
        cv2.imwrite(str(tpl_path), tpl_img)

        preset = Preset(
            id="test_tpl",
            name="Test Template",
            match={},
            reference_aspect=1.6,
            regions=[
                Region(
                    name="icon",
                    rect=(0.5, 0.5, 0.1, 0.1),
                    interval_ms=500,
                    rule={"type": "template", "template": "skull.png", "threshold": 0.85},
                )
            ],
            base_dir=Path(self.test_dir),
        )
        engine = RuleEngine(preset)

        # Large frame without template -> off
        large_bg = np.full((100, 100, 3), 30, dtype=np.uint8)
        r_off = engine.evaluate("icon", large_bg)
        self.assertFalse(r_off["on"])

        # Large frame with template pasted at (40, 40) -> on
        large_with_tpl = large_bg.copy()
        large_with_tpl[40:60, 40:60] = tpl_img
        r_on = engine.evaluate("icon", large_with_tpl)
        self.assertTrue(r_on["on"])
        self.assertGreaterEqual(r_on["metrics"]["max_val"], 0.95)

    def test_color_ratio(self):
        """5. color_ratio：半張紅 -> on."""
        preset = Preset(
            id="test_color",
            name="Test Color Ratio",
            match={},
            reference_aspect=1.6,
            regions=[
                Region(
                    name="health_bar",
                    rect=(0.1, 0.8, 0.2, 0.05),
                    interval_ms=200,
                    rule={
                        "type": "color_ratio",
                        "hsv": [0, 10, 100, 255, 100, 255],  # Red
                        "min_ratio": 0.4,
                    },
                )
            ],
        )
        engine = RuleEngine(preset)

        # Half red, half black
        img = np.zeros((50, 100, 3), dtype=np.uint8)
        # Left half red (0, 0, 255)
        img[:, :50] = (0, 0, 255)

        res = engine.evaluate("health_bar", img)
        self.assertTrue(res["on"])
        self.assertAlmostEqual(res["metrics"]["matched_ratio"], 0.5, places=2)

    def test_ocr_contains_placeholder(self):
        """6. ocr_contains 佔位驗證."""
        preset = Preset(
            id="test_ocr",
            name="Test OCR",
            match={},
            reference_aspect=1.6,
            regions=[
                Region(
                    name="text_box",
                    rect=(0.1, 0.8, 0.2, 0.05),
                    interval_ms=200,
                    rule={"type": "ocr_contains", "text": "DEAD"},
                )
            ],
        )
        engine = RuleEngine(preset)
        frame = np.zeros((50, 50, 3), dtype=np.uint8)
        res = engine.evaluate("text_box", frame)
        self.assertFalse(res["on"])
        self.assertEqual(res["metrics"].get("reason"), "ocr not implemented")


if __name__ == "__main__":
    unittest.main()
