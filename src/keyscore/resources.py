"""应用内置资源路径。"""

from __future__ import annotations

from pathlib import Path


def app_icon_path() -> Path:
    """
    返回 KeyScore 应用图标路径。

    Returns:
        Path: 内置 `KS.png` 的绝对路径。
    """

    return Path(__file__).resolve().parent / "assets" / "KS.png"
