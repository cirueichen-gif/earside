from __future__ import annotations

import asyncio
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.brain.conversation import Conversation  # noqa: E402
from earside.ports.http import OpenAIClient  # noqa: E402


class _FakeLLM:
    def __init__(self) -> None:
        self.cancelled = False

    def stream(self, messages):  # noqa: ANN001
        yield "你"

    def cancel(self) -> None:
        self.cancelled = True


class _FakePlayer:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _FakeTTS:
    def synthesize(self, text: str, voice=None) -> bytes:  # noqa: ANN001
        return b""


class _SlowLLM:
    """送一個 token 後沉默；模擬「打斷時 worker 卡在 HTTP 讀取」。"""

    def __init__(self) -> None:
        self.cancelled = False

    def stream(self, messages):  # noqa: ANN001
        yield "你"
        time.sleep(5)

    def cancel(self) -> None:
        self.cancelled = True


class _AsyncPlayer:
    def stop(self) -> None:
        pass

    async def play_async(self, wav: bytes) -> float:  # noqa: ANN001
        return 0.0


class ReplyCancelTest(unittest.TestCase):
    def test_reply_returns_quickly_after_cancel(self) -> None:
        conv = Conversation(_SlowLLM(), _FakeTTS(), _AsyncPlayer())

        async def run() -> float:
            task = asyncio.create_task(conv.reply("hi"))
            await asyncio.sleep(0.05)
            started = time.perf_counter()
            conv.cancel()
            await asyncio.wait_for(task, 1.0)
            return time.perf_counter() - started

        elapsed = asyncio.run(run())
        self.assertLess(elapsed, 0.5, f"cancel 後 reply 花了 {elapsed:.2f}s 才返回")


class CancelTest(unittest.TestCase):
    def test_conversation_cancel_stops_llm_and_player(self) -> None:
        llm = _FakeLLM()
        player = _FakePlayer()
        conv = Conversation(llm, _FakeTTS(), player)
        conv.cancel()
        self.assertTrue(conv._cancelled)  # noqa: SLF001
        self.assertTrue(llm.cancelled)
        self.assertTrue(player.stopped)

    def test_openai_client_cancel_closes_active_response(self) -> None:
        client = OpenAIClient("http://127.0.0.1:1/v1")

        class Response:
            closed = False

            def close(self) -> None:
                self.closed = True

        resp = Response()
        client._active = resp  # noqa: SLF001
        client.cancel()
        self.assertTrue(resp.closed)
        self.assertIsNone(client._active)  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()
