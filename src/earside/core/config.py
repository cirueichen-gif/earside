"""TOML 設定：預設值 + 檔案覆蓋。"""

from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any

from .paths import project_root

DEFAULTS: dict[str, Any] = {
    "app": {
        "language": "zh-TW",
        "persona": "personas/companion_zh.md",
        "preset": "presets/general.json",
    },
    "capture": {"backend": "auto"},
    "tuning": {
        # 耳朵
        "vad_threshold": 0.5,
        "vad_pre_roll_s": 0.30,
        "vad_onset_frames": 8,
        "vad_hangover_s": 1.00,
        "vad_min_speech_s": 0.25,
        "vad_max_utter_s": 15.0,
        "asr_timeout_s": 30.0,
        # 嘴巴
        "merge_window_s": 0.45,
        "fillers": "嗯恩啊喔哦欸呃唉齁嘿ㄟ",
        "sentence_max_len": 42,
        "sentence_soft_len": 24,
        "sapi_rate": 175,
        "playback_samplerate": 48000,
        "max_turns": 10,
        # 字幕
        "overlay_chars_per_line": 30,
    },
    "audio": {"input_device": ""},
    "ports": {
        "asr": {"kind": "http", "url": "http://127.0.0.1:8802/stt"},
        "tts": {
            "kind": "builtin",
            "impl": "sapi",
            "url": "http://127.0.0.1:8803/tts",
        },
        "voice": {"enabled": False, "url": "http://127.0.0.1:8804/voice"},
        "llm": {
            "kind": "http",
            "protocol": "openai",
            "base_url": "http://127.0.0.1:8801/v1",
            "api_key": "",
            "model": "companion",
        },
        "vision": {"enabled": False, "protocol": "openai", "base_url": "", "model": ""},
    },
    "behavior": {
        "silence_s": 240,
        "max_proactive_per_hour": 3,
        "barge_in": True,
        "echo_guard_s": 0.4,
        "combat_exit_s": 45,
    },
    "subtitle": {
        "font": "Microsoft JhengHei",
        "size": 30,
        "alpha": 0.82,
        "position": "bottom-center",
        "max_lines": 2,
    },
}


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def find_config(explicit: str | None = None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_file() else None
    for name in ("config.toml", "config.example.toml"):
        path = project_root() / name
        if path.is_file():
            return path
    return None


def load_config(explicit: str | None = None) -> dict[str, Any]:
    path = find_config(explicit)
    data: dict[str, Any] = {}
    if path is not None:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    return _deep_merge(DEFAULTS, data)
