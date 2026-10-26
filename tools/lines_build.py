"""短句庫建置：preset 的 lines/*.txt → 預錄 wav＋manifest。

用法：
    python tools/lines_build.py --preset presets/demo-color --dry-run
    python tools/lines_build.py --preset presets/demo-color
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from earside.brain.linebank import iter_lines, line_key  # noqa: E402
from earside.core.config import load_config  # noqa: E402
from earside.core.paths import cache_dir  # noqa: E402
from earside.ports.factory import make_tts  # noqa: E402


def build_lines(
    preset_dir: str | Path,
    tts,
    out_dir: str | Path,
    voice: str | None = None,
    dry_run: bool = False,
    engine: str = "tts",
) -> dict:
    preset = Path(preset_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lines_dir = preset / "lines"
    voice_name = voice or "default"

    entries: list[dict] = []
    failed: list[dict] = []
    ok = 0
    skipped = 0

    for txt in sorted(lines_dir.glob("*.txt")) if lines_dir.is_dir() else []:
        bank = txt.stem
        for text in iter_lines(txt):
            key = line_key(text, voice_name, engine)
            wav = out / f"{key}.wav"
            entries.append(
                {
                    "bank": bank,
                    "text": text,
                    "key": key,
                    "file": wav.name,
                    "voice": voice_name,
                    "engine": engine,
                }
            )
            if wav.is_file():
                skipped += 1
                continue
            if dry_run:
                continue
            try:
                data = tts.synthesize(text)
                if not data:
                    raise RuntimeError("空音檔")
                wav.write_bytes(data)
                ok += 1
            except Exception as exc:  # noqa: BLE001 - partial success
                failed.append({"line": text, "error": str(exc)})

    manifest_path = out / "manifest.json"
    if not dry_run:
        manifest_path.write_text(
            json.dumps(
                {
                    "voice": voice_name,
                    "engine": engine,
                    "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "entries": entries,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return {
        "ok": ok,
        "failed": failed,
        "skipped": skipped,
        "manifest": str(manifest_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="建置短句庫")
    parser.add_argument("--preset", required=True, help="preset 資料夾（裡面有 lines/）")
    parser.add_argument("--config", default=None)
    parser.add_argument("--voice", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    out = Path(args.out) if args.out else cache_dir() / "lines"
    tts = None
    if not args.dry_run:
        tts = make_tts(
            cfg["ports"]["tts"], rate=int(cfg["tuning"].get("sapi_rate", 175))
        )
    result = build_lines(args.preset, tts, out, voice=args.voice, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
