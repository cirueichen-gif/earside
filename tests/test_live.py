from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.brain.conversation import Conversation  # noqa: E402
from earside.brain.live import _is_filler  # noqa: E402


class FillerTest(unittest.TestCase):
    def test_fillers(self) -> None:
        for text in ("嗯", "嗯嗯", "啊。", "喔喔", "欸"):
            self.assertTrue(_is_filler(text), text)

    def test_meaningful_short_replies_survive(self) -> None:
        for text in ("好", "對", "是喔", "真的", "然後"):
            self.assertFalse(_is_filler(text), text)


class _NoTTS:
    def __init__(self) -> None:
        self.called = False

    def synthesize(self, text: str, voice=None) -> bytes:  # noqa: ANN001
        self.called = True
        return b""


class _Player:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class CancelTest(unittest.TestCase):
    def test_cancel_stops_playback_and_skips_speech(self) -> None:
        tts = _NoTTS()
        player = _Player()
        conv = Conversation(None, tts, player)
        conv.cancel()
        asyncio.run(conv._speak("你好"))  # noqa: SLF001 - 就是要驗取消後的 _speak
        self.assertTrue(player.stopped)
        self.assertFalse(tts.called)


if __name__ == "__main__":
    unittest.main()
