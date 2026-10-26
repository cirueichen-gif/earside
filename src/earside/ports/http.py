"""HTTP 端口：本機服務，一紙 JSON 合約。"""

from __future__ import annotations

import io
import json
import urllib.request
import uuid
from typing import Any, Iterator

from .base import PortError


def _post_json(url: str, payload: dict[str, Any], timeout: float = 30.0) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json; charset=utf-8"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001 - 端口錯要能被降級處理
        raise PortError(f"{url}: {exc}") from exc


def _post_multipart(
    url: str,
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes]],
    timeout: float = 30.0,
) -> bytes:
    boundary = "----earside" + uuid.uuid4().hex
    out = io.BytesIO()
    for name, value in fields.items():
        out.write(f"--{boundary}\r\n".encode())
        out.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        out.write(str(value).encode("utf-8"))
        out.write(b"\r\n")
    for name, (filename, data) in files.items():
        out.write(f"--{boundary}\r\n".encode())
        out.write(
            (
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\n'
            ).encode()
        )
        out.write(b"Content-Type: application/octet-stream\r\n\r\n")
        out.write(data)
        out.write(b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        url,
        data=out.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001
        raise PortError(f"{url}: {exc}") from exc


class HttpTTS:
    def __init__(self, url: str, timeout: float = 30.0) -> None:
        self.url = url
        self.timeout = timeout

    def synthesize(self, text: str, voice: str | None = None) -> bytes:
        payload: dict[str, Any] = {"text": text, "format": "wav"}
        if voice:
            payload["voice"] = voice
        data = _post_json(self.url, payload, self.timeout)
        if not data:
            raise PortError(f"{self.url}: 空音檔")
        return data


class HttpSTT:
    def __init__(self, url: str, timeout: float = 10.0) -> None:
        self.url = url
        self.timeout = timeout

    def transcribe(self, wav: bytes, lang: str = "zh") -> str:
        data = _post_multipart(
            self.url,
            {"lang": lang},
            {"audio": ("utterance.wav", wav)},
            self.timeout,
        )
        try:
            payload = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise PortError(f"{self.url}: 回傳不是 JSON") from exc
        text = payload.get("text")
        if not isinstance(text, str):
            raise PortError(f"{self.url}: 缺少 text")
        return text


class HttpVoice:
    def __init__(self, url: str, timeout: float = 30.0) -> None:
        self.url = url
        self.timeout = timeout

    def convert(self, wav: bytes, pitch: int = 0) -> bytes:
        data = _post_multipart(
            self.url,
            {"pitch": str(pitch)},
            {"audio": ("tts.wav", wav)},
            self.timeout,
        )
        if not data:
            raise PortError(f"{self.url}: 空音檔")
        return data


class OpenAIClient:
    """OpenAI 相容的 chat/completions，串流與看圖共用一支。"""

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        model: str = "companion",
        timeout: float = 60.0,
    ) -> None:
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _request(self, messages: list[dict], stream: bool) -> urllib.request.Request:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return urllib.request.Request(self.url, data=body, headers=headers)

    def stream(self, messages: list[dict]) -> Iterator[str]:
        try:
            with urllib.request.urlopen(
                self._request(messages, stream=True), timeout=self.timeout
            ) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        obj = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    for choice in obj.get("choices", []):
                        delta = choice.get("delta") or {}
                        content = delta.get("content")
                        if content:
                            yield content
        except Exception as exc:  # noqa: BLE001
            raise PortError(f"{self.url}: {exc}") from exc

    def describe(self, image: bytes, prompt: str) -> str:
        # TODO(P3)：第三部分才接；現在沒有呼叫端。
        import base64

        b64 = base64.b64encode(image).decode("ascii")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }
        ]
        try:
            with urllib.request.urlopen(
                self._request(messages, stream=False), timeout=self.timeout
            ) as resp:
                obj = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise PortError(f"{self.url}: {exc}") from exc
        try:
            return obj["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise PortError(f"{self.url}: 回傳格式不對") from exc
