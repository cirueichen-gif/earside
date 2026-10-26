"""開發用：假的 OpenAI SSE 伺服器，讓 talk 在沒有 DSH 時也能跑。"""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKENS = ["你好。", "我是耳邊，", "現在在", "測試回話。"]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for token in TOKENS:
            payload = json.dumps(
                {"choices": [{"delta": {"content": token}}]}, ensure_ascii=False
            )
            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
            self.wfile.flush()
            time.sleep(0.15)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args) -> None:  # noqa: ANN002
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8899), Handler).serve_forever()
