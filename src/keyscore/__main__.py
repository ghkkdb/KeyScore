"""支持通过 ``python -m keyscore`` 启动应用。"""

from .app import main


if __name__ == "__main__":
    raise SystemExit(main())
