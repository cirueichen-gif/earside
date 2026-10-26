"""端口工廠：設定說要哪一種，這裡長出來。"""

from __future__ import annotations

from typing import Any

from .base import PortError


def make_tts(cfg: dict[str, Any], rate: int = 175):
    kind = cfg.get("kind", "builtin")
    if kind == "builtin":
        impl = cfg.get("impl", "sapi")
        if impl == "sapi":
            from .builtin import SapiTTS

            return SapiTTS(rate=int(cfg.get("rate", rate)))
        raise PortError(f"未知的內建 TTS：{impl}")
    if kind == "http":
        from .http import HttpTTS

        return HttpTTS(cfg["url"])
    raise PortError(f"未知的 TTS 接法：{kind}")


def make_asr(cfg: dict[str, Any], timeout: float = 30.0):
    kind = cfg.get("kind", "http")
    if kind == "http":
        from .http import HttpSTT

        # 冷啟動載模型可能 13 秒；30 秒給它。
        return HttpSTT(cfg["url"], timeout=float(cfg.get("timeout", timeout)))
    raise PortError(f"這一版只支援 http ASR（{kind} 之後再做）")


def make_voice(cfg: dict[str, Any]):
    if not cfg.get("enabled", False):
        return None
    from .http import HttpVoice

    return HttpVoice(cfg["url"])


def make_llm(cfg: dict[str, Any]):
    kind = cfg.get("kind", "http")
    if kind != "http":
        raise PortError(f"這一版只支援 http LLM（{kind} 之後再做）")
    from .http import OpenAIClient

    return OpenAIClient(
        cfg["base_url"], api_key=cfg.get("api_key", ""), model=cfg.get("model", "")
    )


def make_vision(cfg: dict[str, Any]):
    # TODO(P3)：第三部分才接；現在 config 預設 enabled=false，沒有呼叫端。
    if not cfg.get("enabled", False):
        return None
    from .http import OpenAIClient

    return OpenAIClient(
        cfg["base_url"], api_key=cfg.get("api_key", ""), model=cfg.get("model", "")
    )
