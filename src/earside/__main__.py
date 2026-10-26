"""Windows spawn 保護：子進程會用 __mp_main__ 重新 import，別讓它再跑一次 main。"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
