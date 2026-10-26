from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earside.brain.linebank import LineBank, iter_lines, line_key  # noqa: E402
from tools.lines_build import build_lines  # noqa: E402


class _FakeTTS:
    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.calls = 0

    def synthesize(self, text: str, voice=None) -> bytes:  # noqa: ANN001
        self.calls += 1
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("boom")
        return b"RIFF" + text.encode("utf-8")


class LineBankTest(unittest.TestCase):
    def test_key_stable_and_distinct(self) -> None:
        self.assertEqual(line_key("你好"), line_key("你好"))
        self.assertNotEqual(line_key("你好"), line_key("你好", voice="other"))

    def test_iter_lines_skips_comments_and_blanks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "death.txt"
            path.write_text("# 註解\n\n左邊\n  小心  \n", encoding="utf-8")
            self.assertEqual(iter_lines(path), ["左邊", "小心"])

    def test_build_partial_and_second_run_skips(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            preset = Path(td) / "preset"
            (preset / "lines").mkdir(parents=True)
            (preset / "lines" / "death.txt").write_text(
                "倒了\n再來\n", encoding="utf-8"
            )
            out = Path(td) / "cache"
            tts = _FakeTTS(fail_on="再來")
            first = build_lines(preset, tts, out)
            self.assertEqual(first["ok"], 1)
            self.assertEqual(len(first["failed"]), 1)
            self.assertTrue((out / "manifest.json").is_file())

            second = build_lines(preset, _FakeTTS(), out)
            self.assertEqual(second["ok"], 1)  # 上次失敗的這句會重試
            self.assertEqual(second["skipped"], 1)

    def test_runtime_reads_manifest_and_rotates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            preset = Path(td) / "preset"
            (preset / "lines").mkdir(parents=True)
            (preset / "lines" / "minimap.txt").write_text(
                "左邊\n右邊\n", encoding="utf-8"
            )
            out = Path(td) / "cache"
            build_lines(preset, _FakeTTS(), out)
            bank = LineBank(preset, out)
            first = bank.pick("minimap")
            second = bank.pick("minimap")
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertNotEqual(first[0], second[0])


if __name__ == "__main__":
    unittest.main()
