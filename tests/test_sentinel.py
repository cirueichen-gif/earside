from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.eyes.preset import Preset, Region  # noqa: E402
from earside.eyes.rules import RuleEngine  # noqa: E402


def make_preset(sensitivity: float = 1.0, rule_sensitivity: float | None = None) -> Preset:
    rule = {"type": "change", "diff_ratio": 0.10, "diff_threshold": 25, "consecutive": 1}
    if rule_sensitivity is not None:
        rule["sensitivity"] = rule_sensitivity
    return Preset(
        id="t",
        name="t",
        match={},
        reference_aspect=1.6,
        regions=[Region(name="r", rect=(0.0, 0.0, 1.0, 1.0), interval_ms=200, rule=rule)],
        sensitivity=sensitivity,
    )


def frames(change_ratio: float = 0.06) -> tuple[np.ndarray, np.ndarray]:
    before = np.zeros((100, 100, 3), dtype=np.uint8)
    after = before.copy()
    after[: int(100 * change_ratio), :, :] = 255
    return before, after


class SensitivityTest(unittest.TestCase):
    def test_default_blocks_small_change(self) -> None:
        engine = RuleEngine(make_preset(1.0))
        before, after = frames()
        engine.evaluate("r", before)
        self.assertFalse(engine.evaluate("r", after)["on"])

    def test_high_sensitivity_triggers(self) -> None:
        engine = RuleEngine(make_preset(2.0))
        before, after = frames()
        engine.evaluate("r", before)
        self.assertTrue(engine.evaluate("r", after)["on"])

    def test_low_sensitivity_blocks(self) -> None:
        engine = RuleEngine(make_preset(0.5))
        before, after = frames()
        engine.evaluate("r", before)
        self.assertFalse(engine.evaluate("r", after)["on"])

    def test_region_override(self) -> None:
        engine = RuleEngine(make_preset(1.0, rule_sensitivity=2.0))
        before, after = frames()
        engine.evaluate("r", before)
        self.assertTrue(engine.evaluate("r", after)["on"])

    def test_preset_sensitivity_used_as_default(self) -> None:
        engine = RuleEngine(make_preset(2.0))
        before, after = frames()
        engine.evaluate("r", before)
        self.assertTrue(engine.evaluate("r", after)["on"])


if __name__ == "__main__":
    unittest.main()
