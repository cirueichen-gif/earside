"""PyInstaller 入口：用絕對 import，避免相對 import 在凍結後失效。"""

from __future__ import annotations

import multiprocessing

from earside.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
