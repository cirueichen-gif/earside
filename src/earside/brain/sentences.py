"""把 LLM 的串流切成一句一句，順便清掉不該念的東西。

可調參數見 config.toml [tuning]（sentence_max_len／sentence_soft_len）。
"""

from __future__ import annotations

import re

TERMINATORS = "。！？!?…～~\n"
SOFT = "，,、；;：:"
MARKER_RE = re.compile(r"\[(?:表情|SEND_FILE)[^\]]*\]")
CODE_RE = re.compile(r"```.*?```", re.S)
URL_RE = re.compile(r"https?://\S+")
MD_RE = re.compile(r"[*_`#>]+")

MAX_LEN = 42
SOFT_LEN = 24


def speakable(text: str) -> str:
    """TTS 要念的字：去標記、去 code、去網址、去 markdown。"""
    text = CODE_RE.sub("", text)
    text = MARKER_RE.sub("", text)
    text = URL_RE.sub("", text)
    text = MD_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_sentences(
    buffer: str, force: bool = False, max_len: int = MAX_LEN, soft_len: int = SOFT_LEN
) -> tuple[list[str], str]:
    """回傳（可以念的句子, 還沒講完的尾巴）。

    先切句末標點；太長的再用逗號切，避免一句拖 10 秒。
    """
    sentences: list[str] = []
    start = 0
    i = 0
    while i < len(buffer):
        ch = buffer[i]
        if ch in TERMINATORS:
            piece = buffer[start : i + 1].strip()
            if piece:
                sentences.append(piece)
            start = i + 1
        elif ch in SOFT and (i - start) >= soft_len:
            piece = buffer[start : i + 1].strip()
            if piece:
                sentences.append(piece)
            start = i + 1
        elif (i - start) >= max_len:
            piece = buffer[start : i + 1].strip()
            if piece:
                sentences.append(piece)
            start = i + 1
        i += 1

    rest = buffer[start:]
    if force and rest.strip():
        sentences.append(rest.strip())
        rest = ""
    return sentences, rest
