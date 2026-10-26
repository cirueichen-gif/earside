"""短句庫 runtime：讀 manifest／cache，挑一句預錄台詞。

建置工具在 `tools/lines_build.py`；這裡只負責挑，不合成。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def line_key(text: str, voice: str = "default", engine: str = "tts") -> str:
    raw = f"{engine}|{voice}|{text}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def iter_lines(path: str | Path) -> list[str]:
    lines: list[str] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


class LineBank:
    def __init__(self, preset_dir: str | Path, cache_dir: str | Path) -> None:
        self.banks: dict[str, list[tuple[str, Path]]] = {}
        self._index: dict[str, int] = {}
        cache = Path(cache_dir)
        manifest = cache / "manifest.json"

        if manifest.is_file():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for entry in data.get("entries", []):
                wav = cache / entry["file"]
                if wav.is_file():
                    self.banks.setdefault(entry["bank"], []).append(
                        (entry["text"], wav)
                    )
            return

        # 沒有 manifest 就自己掃 preset 的 lines/ 與 cache 的 hash 檔
        lines_dir = Path(preset_dir) / "lines"
        if not lines_dir.is_dir():
            return
        for txt in sorted(lines_dir.glob("*.txt")):
            for text in iter_lines(txt):
                wav = cache / f"{line_key(text)}.wav"
                if wav.is_file():
                    self.banks.setdefault(txt.stem, []).append((text, wav))

    def pick(self, bank: str | None) -> tuple[str, bytes] | None:
        entries = self.banks.get(bank or "")
        if not entries:
            return None
        index = self._index.get(bank or "", 0) % len(entries)
        self._index[bank or ""] = index + 1
        text, path = entries[index]
        try:
            return text, path.read_bytes()
        except OSError:
            return None
