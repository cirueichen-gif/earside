"""端口合約。全部用 bytes（wav／jpeg），不綁 numpy。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class PortError(RuntimeError):
    """端口呼叫失敗。呼叫端要能降級。"""


@runtime_checkable
class TTSPort(Protocol):
    def synthesize(self, text: str, voice: str | None = None) -> bytes: ...


@runtime_checkable
class STTPort(Protocol):
    def transcribe(self, wav: bytes, lang: str = "zh") -> str: ...


@runtime_checkable
class VoicePort(Protocol):
    def convert(self, wav: bytes, pitch: int = 0) -> bytes: ...


@runtime_checkable
class LLMPort(Protocol):
    def stream(self, messages: list[dict]) -> object: ...


@runtime_checkable
class VisionPort(Protocol):
    # TODO(P3)：第三部分才接。目前只有介面，沒有任何呼叫端。
    def describe(self, image: bytes, prompt: str) -> str: ...
