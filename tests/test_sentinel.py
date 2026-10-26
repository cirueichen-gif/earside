from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.brain.triggers import TriggerEngine  # noqa: E402
from earside.eyes.preset import Preset, Region  # noqa: E402
from earside.eyes.rules import RuleEngine  # noqa: E402
from earside.eyes.sentinel import SentinelRunner  # noqa: E402


class _FakeCapture:
    def __init__(self, frames: list[np.ndarray]) -> None:
        self.frames = frames
        self.i = 0

    def grab(self) -> np.ndarray:
        frame = self.frames[min(self.i, len(self.frames) - 1)]
        self.i += 1
        return frame


def _preset() -> Preset:
    return Preset(
        id="t",
        name="t",
        match={},
        reference_aspect=1.6,
        regions=[
            Region(
                name="r",
                rect=(0.0, 0.0, 1.0, 1.0),
                interval_ms=100,
                rule={"type": "change", "diff_ratio": 0.1, "consecutive": 1},
            )
        ],
    )


class SentinelRunnerTest(unittest.TestCase):
    def test_emits_only_on_state_change(self) -> None:
        before = np.zeros((50, 50, 3), dtype=np.uint8)
        after = before.copy()
        after[:20, :] = 255
        capture = _FakeCapture([before, after, after])
        runner = SentinelRunner(_preset(), capture, RuleEngine(_preset()))

        first = runner.poll(now=0.0)
        self.assertEqual(first, [])  # change 第一幀不算
        second = runner.poll(now=0.2)
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]["type"], "r.on")
        third = runner.poll(now=0.4)
        self.assertEqual(len(third), 1)
        self.assertEqual(third[0]["type"], "r.off")  # 畫面不再變→恢復 off


class TriggerEngineTest(unittest.TestCase):
    def test_cooldown_and_skip_if_speaking(self) -> None:
        engine = TriggerEngine(
            [
                {
                    "on": "r.on",
                    "do": "say",
                    "source": "linebank",
                    "bank": "death",
                    "cooldown_s": 30,
                },
                {"on": "m.on", "do": "say", "skip_if_speaking": True},
            ]
        )
        first = engine.actions_for({"type": "r.on"}, now=0.0)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["bank"], "death")
        self.assertEqual(engine.actions_for({"type": "r.on"}, now=10.0), [])
        self.assertEqual(len(engine.actions_for({"type": "r.on"}, now=31.0)), 1)

        self.assertEqual(
            engine.actions_for({"type": "m.on"}, speaking=True, now=40.0), []
        )
        self.assertEqual(
            len(engine.actions_for({"type": "m.on"}, speaking=False, now=41.0)), 1
        )

    def test_max_per_minute(self) -> None:
        engine = TriggerEngine(
            [{"on": "x", "do": "say", "max_per_min": 2}]
        )
        self.assertEqual(len(engine.actions_for({"type": "x"}, now=0.0)), 1)
        self.assertEqual(len(engine.actions_for({"type": "x"}, now=1.0)), 1)
        self.assertEqual(engine.actions_for({"type": "x"}, now=2.0), [])

    def test_max_per_hour(self) -> None:
        engine = TriggerEngine([{"on": "x", "do": "say", "max_per_hour": 2}])
        self.assertEqual(len(engine.actions_for({"type": "x"}, now=0.0)), 1)
        self.assertEqual(len(engine.actions_for({"type": "x"}, now=120.0)), 1)
        self.assertEqual(engine.actions_for({"type": "x"}, now=240.0), [])
        self.assertEqual(len(engine.actions_for({"type": "x"}, now=3700.0)), 1)


def _sensitivity_preset(
    sensitivity: float = 1.0, rule_sensitivity: float | None = None
) -> Preset:
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


def _sensitivity_frames(change_ratio: float = 0.06):
    before = np.zeros((100, 100, 3), dtype=np.uint8)
    after = before.copy()
    after[: int(100 * change_ratio), :, :] = 255
    return before, after


class SensitivityTest(unittest.TestCase):
    def test_default_blocks_small_change(self) -> None:
        engine = RuleEngine(_sensitivity_preset(1.0))
        before, after = _sensitivity_frames()
        engine.evaluate("r", before)
        self.assertFalse(engine.evaluate("r", after)["on"])

    def test_high_sensitivity_triggers(self) -> None:
        engine = RuleEngine(_sensitivity_preset(2.0))
        before, after = _sensitivity_frames()
        engine.evaluate("r", before)
        self.assertTrue(engine.evaluate("r", after)["on"])

    def test_low_sensitivity_blocks(self) -> None:
        engine = RuleEngine(_sensitivity_preset(0.5))
        before, after = _sensitivity_frames()
        engine.evaluate("r", before)
        self.assertFalse(engine.evaluate("r", after)["on"])

    def test_region_override(self) -> None:
        engine = RuleEngine(_sensitivity_preset(1.0, rule_sensitivity=2.0))
        before, after = _sensitivity_frames()
        engine.evaluate("r", before)
        self.assertTrue(engine.evaluate("r", after)["on"])

    def test_preset_sensitivity_used_as_default(self) -> None:
        engine = RuleEngine(_sensitivity_preset(2.0))
        before, after = _sensitivity_frames()
        engine.evaluate("r", before)
        self.assertTrue(engine.evaluate("r", after)["on"])


if __name__ == "__main__":
    unittest.main()
