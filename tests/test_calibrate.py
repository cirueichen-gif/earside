"""Tests for eyes.calibrate pure functions and preset loading round-trip."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.eyes.calibrate import build_preset, normalize_rect, save_preset  # noqa: E402
from earside.eyes.preset import load_preset  # noqa: E402


class TestCalibratePureFunctions(unittest.TestCase):
    def test_normalize_rect_standard(self):
        # 100x100 image, dragging from (10, 20) to (50, 60)
        nx, ny, nw, nh = normalize_rect(10, 20, 50, 60, 100, 100)
        self.assertAlmostEqual(nx, 0.1, places=3)
        self.assertAlmostEqual(ny, 0.2, places=3)
        self.assertAlmostEqual(nw, 0.4, places=3)
        self.assertAlmostEqual(nh, 0.4, places=3)

    def test_normalize_rect_reverse_drag(self):
        # Dragging backwards from (50, 60) to (10, 20)
        nx, ny, nw, nh = normalize_rect(50, 60, 10, 20, 100, 100)
        self.assertAlmostEqual(nx, 0.1, places=3)
        self.assertAlmostEqual(ny, 0.2, places=3)
        self.assertAlmostEqual(nw, 0.4, places=3)
        self.assertAlmostEqual(nh, 0.4, places=3)

    def test_normalize_rect_out_of_bounds_clamped(self):
        # Dragging outside the image boundaries
        nx, ny, nw, nh = normalize_rect(-20, -10, 150, 120, 100, 100)
        self.assertGreaterEqual(nx, 0.0)
        self.assertGreaterEqual(ny, 0.0)
        self.assertLessEqual(nx + nw, 1.0)
        self.assertLessEqual(ny + nh, 1.0)

    def test_normalize_rect_min_one_pixel(self):
        # Zero-width drag (click without moving)
        nx, ny, nw, nh = normalize_rect(50, 50, 50, 50, 100, 100)
        self.assertGreater(nw, 0.0)
        self.assertGreater(nh, 0.0)
        self.assertLessEqual(nx + nw, 1.0)
        self.assertLessEqual(ny + nh, 1.0)

    def test_build_preset_defaults(self):
        p_dict = build_preset(
            preset_id="demo-test",
            name="Demo Test",
            window_title_regex="Notepad",
        )
        self.assertEqual(p_dict["id"], "demo-test")
        self.assertEqual(p_dict["name"], "Demo Test")
        self.assertEqual(p_dict["game_type"], "generic")
        self.assertTrue(p_dict["enabled"])
        self.assertEqual(p_dict["sensitivity"], 1.0)
        self.assertEqual(p_dict["match"]["window_title_regex"], "Notepad")
        self.assertEqual(p_dict["regions"], [])

    def test_build_preset_with_regions_and_rules(self):
        regions_input = [
            {
                "name": "hp_bar",
                "rect": [0.1, 0.2, 0.3, 0.4],
                "interval_ms": 250,
                "rule": {"type": "color_ratio", "hsv": [0, 10, 100, 255, 100, 255]},
            },
            {
                "name": "minimap",
                "rect": [0.8, 0.0, 0.2, 0.2],
                "interval_ms": 500,
                "rule": {"type": "change", "diff_ratio": 0.05, "sensitivity": 0.8},
            },
        ]
        p_dict = build_preset(
            preset_id="rts-game",
            name="RTS Game",
            window_title_regex="(?i)RTS",
            reference_aspect=1.6,
            game_type="rts",
            enabled=False,
            sensitivity=0.8,
            regions=regions_input,
        )
        self.assertEqual(p_dict["id"], "rts-game")
        self.assertEqual(p_dict["game_type"], "rts")
        self.assertFalse(p_dict["enabled"])
        self.assertEqual(p_dict["sensitivity"], 0.8)
        self.assertEqual(len(p_dict["regions"]), 2)
        self.assertEqual(p_dict["regions"][0]["name"], "hp_bar")
        self.assertEqual(p_dict["regions"][1]["rule"]["type"], "change")

    def test_save_and_load_round_trip(self):
        regions = [
            {
                "name": "r1",
                "rect": [0.05, 0.1, 0.25, 0.3],
                "interval_ms": 100,
                "rule": {"type": "luma_sat_drop", "luma_ratio": 0.5},
            }
        ]
        data = build_preset(
            preset_id="rt-preset",
            name="Round Trip Preset",
            window_title_regex="GameTitle",
            reference_aspect=1.7778,
            game_type="moba",
            enabled=True,
            sensitivity=1.2,
            regions=regions,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test_preset.json"
            save_preset(data, file_path)

            self.assertTrue(file_path.exists())

            # Verify UTF-8 formatting and valid json
            with file_path.open("r", encoding="utf-8") as f:
                raw_json = json.load(f)
            self.assertEqual(raw_json["id"], "rt-preset")

            # Load with earside's preset parser
            loaded = load_preset(file_path)
            self.assertEqual(loaded.id, "rt-preset")
            self.assertEqual(loaded.name, "Round Trip Preset")
            self.assertEqual(loaded.game_type, "moba")
            self.assertTrue(loaded.enabled)
            self.assertEqual(loaded.sensitivity, 1.2)
            self.assertEqual(len(loaded.regions), 1)
            self.assertEqual(loaded.regions[0].name, "r1")
            self.assertEqual(loaded.regions[0].rect, (0.05, 0.1, 0.25, 0.3))
            self.assertEqual(loaded.regions[0].interval_ms, 100)
            self.assertEqual(loaded.regions[0].rule["type"], "luma_sat_drop")


if __name__ == "__main__":
    unittest.main()
