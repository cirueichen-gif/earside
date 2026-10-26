from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earside.ports.http import HttpSTT, PortError  # noqa: E402

SEEN: dict[str, bytes] = {}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        SEEN["body"] = self.rfile.read(length)
        if self.path.startswith("/broken"):
            self.send_response(500)
            self.end_headers()
            return
        payload = json.dumps(
            {"text": "測試成功", "lang": "zh", "confidence": 0.9}, ensure_ascii=False
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args) -> None:  # noqa: ANN002
        pass


class HttpPortTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def test_stt_posts_multipart_and_reads_text(self) -> None:
        stt = HttpSTT(f"http://127.0.0.1:{self.port}/stt")
        text = stt.transcribe(b"RIFFfake-wav", "zh")
        self.assertEqual(text, "測試成功")
        self.assertIn(b'name="audio"', SEEN["body"])
        self.assertIn(b'name="lang"', SEEN["body"])

    def test_stt_raises_port_error_on_500(self) -> None:
        stt = HttpSTT(f"http://127.0.0.1:{self.port}/broken", timeout=5)
        with self.assertRaises(PortError):
            stt.transcribe(b"RIFFfake-wav", "zh")


if __name__ == "__main__":
    unittest.main()
