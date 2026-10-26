"""專案路徑。從 src/earside/core/paths.py 往上找三層就是專案根。"""

from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        # onedir exe：PyInstaller 6 把 datas 放在 _internal/；優先找有 config 的那層。
        exe_dir = Path(sys.executable).resolve().parent
        for candidate in (exe_dir, exe_dir / "_internal"):
            if (candidate / "config.example.toml").is_file():
                return candidate
        return exe_dir
    return Path(__file__).resolve().parents[3]


def src_root() -> Path:
    return project_root() / "src"


def local_dir() -> Path:
    return project_root() / "local"


def cache_dir() -> Path:
    d = project_root() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d
