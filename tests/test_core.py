from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.core.bus import EventBus  # noqa: E402
from earside.core.config import _deep_merge, load_config  # noqa: E402


class ConfigTest(unittest.TestCase):
    def test_deep_merge_keeps_defaults(self) -> None:
        merged = _deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}})
        self.assertEqual(merged, {"a": {"b": 1, "c": 3}})

    def test_load_returns_dict(self) -> None:
        self.assertIn("ports", load_config())


class BusTest(unittest.TestCase):
    def test_emit_reaches_handler(self) -> None:
        bus = EventBus()
        seen: list[str] = []
        bus.on("x", lambda event: seen.append(event.type))
        asyncio.run(bus.emit("x", {"n": 1}))
        self.assertEqual(seen, ["x"])
        self.assertEqual(len(bus.recent()), 1)


if __name__ == "__main__":
    unittest.main()
