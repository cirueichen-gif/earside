"""專案路徑。從 src/earside/core/paths.py 往上找三層就是專案根。"""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def src_root() -> Path:
    return project_root() / "src"


def local_dir() -> Path:
    return project_root() / "local"


def cache_dir() -> Path:
    d = project_root() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d
