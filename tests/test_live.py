from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.brain.conversation import Conversation  # noqa: E402
from earside.brain.live import LiveLoop, _is_filler  # noqa: E402
from earside.eyes.preset import Preset, Region  # noqa: E402


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


class _RecordingConv:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.lines: list[str] = []
        self.last_play_end = 0.0

    async def reply(self, text: str) -> None:
        self.prompts.append(text)

    async def play_wav(self, text: str, wav: bytes) -> None:
        self.lines.append(text)


class _DummyListener:
    def __init__(self) -> None:
        self.on_text = None
        self.on_speech_start = None


class ProactiveTest(unittest.TestCase):
    def test_silence_then_rate_limit(self) -> None:
        conv = _RecordingConv()
        live = LiveLoop(conv, _DummyListener(), silence_s=240, max_proactive_per_hour=2)
        live._last_activity = 0.0  # noqa: SLF001

        asyncio.run(live._maybe_proactive(now=241))  # noqa: SLF001
        self.assertEqual(len(conv.prompts), 1)
        asyncio.run(live._maybe_proactive(now=242))  # noqa: SLF001
        self.assertEqual(len(conv.prompts), 1)

        asyncio.run(live._maybe_proactive(now=5000))  # noqa: SLF001
        self.assertEqual(len(conv.prompts), 2)
        asyncio.run(live._maybe_proactive(now=5001))  # noqa: SLF001
        self.assertEqual(len(conv.prompts), 2)

    def test_combat_suppresses_proactive(self) -> None:
        conv = _RecordingConv()
        live = LiveLoop(conv, _DummyListener(), silence_s=10, combat_exit_s=45)
        live._last_activity = 0.0  # noqa: SLF001
        live._note_event(  # noqa: SLF001
            {"type": "x.on", "on": True, "metrics": {"diff_ratio": 0.5}}, now=100
        )
        asyncio.run(live._maybe_proactive(now=120))  # noqa: SLF001
        self.assertEqual(conv.prompts, [])


class _FakeEye:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def describe(self, frame, regions):  # noqa: ANN001
        self.calls += 1
        return self.text


class _FakeSentinel:
    def __init__(self) -> None:
        self.last_frame = np.zeros((20, 20, 3), dtype=np.uint8)
        self.preset = Preset(
            id="t",
            name="t",
            match={},
            reference_aspect=1.6,
            regions=[Region("r", (0, 0, 1, 1), 200, {"type": "change"})],
            vision={"regions": ["r"]},
        )


class VisionActionTest(unittest.TestCase):
    def test_llm_action_includes_vision_text(self) -> None:
        conv = _RecordingConv()
        eye = _FakeEye("你在倉庫補彈")
        live = LiveLoop(
            conv,
            _DummyListener(),
            sentinel=_FakeSentinel(),
            triggers=None,
            eye=eye,
        )
        asyncio.run(
            live._handle_actions(  # noqa: SLF001
                {"type": "r.on"},
                [{"type": "say", "source": "llm", "trigger": {"vision": True}}],
            )
        )
        self.assertEqual(eye.calls, 1)
        self.assertIn("你在倉庫補彈", conv.prompts[0])


class _FakeBank:
    def pick(self, bank):  # noqa: ANN001
        return ("倒了", b"RIFF")


class LineBankActionTest(unittest.TestCase):
    def test_linebank_action_plays_pregenerated(self) -> None:
        conv = _RecordingConv()
        live = LiveLoop(conv, _DummyListener(), linebank=_FakeBank())
        asyncio.run(
            live._handle_actions(  # noqa: SLF001
                {"type": "r.on"},
                [{"type": "say", "source": "linebank", "bank": "death"}],
            )
        )
        self.assertEqual(conv.lines, ["倒了"])


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
