from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.brain.sentences import speakable, split_sentences  # noqa: E402


class SplitTest(unittest.TestCase):
    def test_two_sentences(self) -> None:
        ready, rest = split_sentences("你好。今天天氣很好！")
        self.assertEqual(len(ready), 2)
        self.assertEqual(rest, "")

    def test_force_flushes_tail(self) -> None:
        ready, rest = split_sentences("這是一句沒有句號的話", force=True)
        self.assertEqual(ready, ["這是一句沒有句號的話"])
        self.assertEqual(rest, "")

    def test_partial_stays_in_buffer(self) -> None:
        ready, rest = split_sentences("我正在想")
        self.assertEqual(ready, [])
        self.assertEqual(rest, "我正在想")

    def test_long_comma_splits(self) -> None:
        text = "這是一段很長很長的話" * 4 + "，後面還有"
        ready, _ = split_sentences(text)
        self.assertGreaterEqual(len(ready), 1)


class SpeakableTest(unittest.TestCase):
    def test_strips_markers_and_markdown(self) -> None:
        out = speakable("[表情: 開心] 哈囉 https://x.com **粗體**")
        self.assertIn("哈囉", out)
        self.assertNotIn("表情", out)
        self.assertNotIn("https", out)
        self.assertNotIn("*", out)

    def test_code_block_removed(self) -> None:
        self.assertEqual(speakable("前```code```後"), "前後")


if __name__ == "__main__":
    unittest.main()
