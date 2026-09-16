"""Windows 前台窗口检测封装。"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


def foreground_window() -> int:
    """
    获取当前前台窗口句柄。

    Returns:
        int: Windows HWND；非 Windows 系统返回 0。
    """

    if sys.platform != "win32":
        return 0
    return int(ctypes.windll.user32.GetForegroundWindow())


def window_title(hwnd: int) -> str:
    """
    获取指定窗口的标题。

    Args:
        hwnd (int): Windows 窗口句柄。

    Returns:
        str: 窗口标题，获取失败时返回空字符串。
    """

    if sys.platform != "win32" or not hwnd:
        return ""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    length = user32.GetWindowTextLengthW(wintypes.HWND(hwnd))
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(wintypes.HWND(hwnd), buffer, length + 1)
    return buffer.value


def is_foreground(hwnd: int) -> bool:
    """
    判断指定窗口是否位于前台。

    Args:
        hwnd (int): 目标窗口句柄。

    Returns:
        bool: 目标窗口当前位于前台时返回 `True`。
    """

    return bool(hwnd) and foreground_window() == hwnd

