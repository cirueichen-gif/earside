from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.ports.http import OpenAIClient  # noqa: E402


class _SSEHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        assert body["stream"] is True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for token in ("你好", "，世界", "。"):
            chunk = json.dumps(
                {"choices": [{"delta": {"content": token}}]}, ensure_ascii=False
            )
            self.wfile.write(f"data: {chunk}\n\n".encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, *args) -> None:  # noqa: ANN002
        pass


class LLMStreamTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _SSEHandler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def test_stream_yields_deltas(self) -> None:
        client = OpenAIClient(
            f"http://127.0.0.1:{self.port}/v1", model="test", timeout=5
        )
        tokens = list(client.stream([{"role": "user", "content": "hi"}]))
        self.assertEqual(tokens, ["你好", "，世界", "。"])


if __name__ == "__main__":
    unittest.main()
