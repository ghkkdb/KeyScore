"""可配置的 Windows 全局快捷键解析与监听。"""

from __future__ import annotations

import ctypes
import sys
import threading
from collections.abc import Callable
from ctypes import wintypes


class HotkeyValidationError(ValueError):
    """表示快捷键文本无法转换为受支持的全局快捷键。"""


_MODIFIERS = {
    "ctrl": 0x0002,
    "control": 0x0002,
    "alt": 0x0001,
    "shift": 0x0004,
    "meta": 0x0008,
    "win": 0x0008,
}
_MODIFIER_LABELS = {
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "meta": "Win",
    "win": "Win",
}
_SPECIAL_KEYS = {
    "space": (0x20, "Space"),
    "tab": (0x09, "Tab"),
    "enter": (0x0D, "Enter"),
    "return": (0x0D, "Enter"),
    "esc": (0x1B, "Esc"),
    "escape": (0x1B, "Esc"),
    "backspace": (0x08, "Backspace"),
    "insert": (0x2D, "Insert"),
    "delete": (0x2E, "Delete"),
    "del": (0x2E, "Delete"),
    "home": (0x24, "Home"),
    "end": (0x23, "End"),
    "pageup": (0x21, "PageUp"),
    "pgup": (0x21, "PageUp"),
    "pagedown": (0x22, "PageDown"),
    "pgdown": (0x22, "PageDown"),
    "left": (0x25, "Left"),
    "up": (0x26, "Up"),
    "right": (0x27, "Right"),
    "down": (0x28, "Down"),
}


def parse_hotkey(value: str) -> tuple[int, int, str]:
    """
    解析单段全局快捷键并生成 Win32 修饰符、虚拟键和规范文本。

    Args:
        value (str): 例如 `F8` 或 `Ctrl+Shift+R` 的快捷键文本。

    Returns:
        tuple[int, int, str]: 修饰符掩码、虚拟键代码和规范显示文本。

    Raises:
        HotkeyValidationError: 快捷键为空、包含多段序列或主键不受支持时抛出。
    """

    raw = value.strip()
    if not raw:
        raise HotkeyValidationError("快捷键不能为空")
    if "," in raw:
        raise HotkeyValidationError("全局快捷键只能包含一段组合")
    parts = [part.strip() for part in raw.split("+") if part.strip()]
    if not parts:
        raise HotkeyValidationError("快捷键不能为空")
    modifier_mask = 0
    modifier_labels: list[str] = []
    key_parts: list[str] = []
    for part in parts:
        normalized = part.casefold()
        if normalized in _MODIFIERS:
            flag = _MODIFIERS[normalized]
            if modifier_mask & flag == 0:
                modifier_mask |= flag
                modifier_labels.append(_MODIFIER_LABELS[normalized])
        else:
            key_parts.append(part)
    if len(key_parts) != 1:
        raise HotkeyValidationError("快捷键必须包含且只能包含一个主键")

    key = key_parts[0]
    normalized_key = key.casefold().replace(" ", "")
    if len(key) == 1 and key.isascii() and key.isalnum():
        virtual_key = ord(key.upper())
        key_label = key.upper()
    elif normalized_key.startswith("f") and normalized_key[1:].isdigit():
        function_number = int(normalized_key[1:])
        if not 1 <= function_number <= 24:
            raise HotkeyValidationError("功能键必须在 F1～F24 之间")
        virtual_key = 0x6F + function_number
        key_label = f"F{function_number}"
    elif normalized_key in _SPECIAL_KEYS:
        virtual_key, key_label = _SPECIAL_KEYS[normalized_key]
    else:
        raise HotkeyValidationError("仅支持字母、数字、功能键和常用控制键")
    canonical = "+".join((*modifier_labels, key_label))
    return modifier_mask, virtual_key, canonical


def normalize_hotkey(value: str) -> str:
    """
    校验并规范化快捷键显示文本。

    Args:
        value (str): 用户或设置文件中的快捷键。

    Returns:
        str: 规范化后的快捷键。

    Raises:
        HotkeyValidationError: 快捷键格式不受支持时抛出。
    """

    return parse_hotkey(value)[2]


def hotkey_scan_code(value: str) -> int:
    """
    返回快捷键主键对应的 Windows 扫描码。

    Args:
        value (str): 已支持的快捷键文本。

    Returns:
        int: 物理主键扫描码；非 Windows 系统返回零。
    """

    if sys.platform != "win32":
        return 0
    _modifiers, virtual_key, _canonical = parse_hotkey(value)
    return int(ctypes.windll.user32.MapVirtualKeyW(virtual_key, 0))


class GlobalHotkeyListener:
    """在专用消息线程中注册三个可配置的 Windows 全局快捷键。"""

    _WM_HOTKEY = 0x0312
    _WM_QUIT = 0x0012
    _MOD_NOREPEAT = 0x4000

    def __init__(
        self,
        on_toggle: Callable[[], None],
        on_stop: Callable[[], None],
        on_record: Callable[[], None],
        play_hotkey: str = "F9",
        stop_hotkey: str = "F10",
        record_hotkey: str = "F8",
    ) -> None:
        """
        初始化回调和快捷键配置。

        Args:
            on_toggle (Callable[[], None]): 播放、暂停或继续回调。
            on_stop (Callable[[], None]): 紧急停止回调。
            on_record (Callable[[], None]): 开始或完成录制回调。
            play_hotkey (str): 播放控制快捷键。
            stop_hotkey (str): 紧急停止快捷键。
            record_hotkey (str): 录制控制快捷键。
        """

        self._callbacks = {1: on_record, 2: on_toggle, 3: on_stop}
        self._hotkeys = {
            1: normalize_hotkey(record_hotkey),
            2: normalize_hotkey(play_hotkey),
            3: normalize_hotkey(stop_hotkey),
        }
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._started_ok = False

    def configure(self, record_hotkey: str, play_hotkey: str, stop_hotkey: str) -> bool:
        """
        重新注册全部快捷键并立即应用。

        Args:
            record_hotkey (str): 录制控制快捷键。
            play_hotkey (str): 播放控制快捷键。
            stop_hotkey (str): 紧急停止快捷键。

        Returns:
            bool: 新快捷键全部注册成功时为 `True`。

        Raises:
            HotkeyValidationError: 快捷键格式无效或相互重复时抛出。
        """

        normalized = {
            1: normalize_hotkey(record_hotkey),
            2: normalize_hotkey(play_hotkey),
            3: normalize_hotkey(stop_hotkey),
        }
        if len(set(normalized.values())) != len(normalized):
            raise HotkeyValidationError("三个全局快捷键不能重复")
        self.stop()
        self._hotkeys = normalized
        return self.start()

    def start(self) -> bool:
        """
        启动 Windows 快捷键消息线程。

        Returns:
            bool: 三个快捷键全部注册成功时返回 `True`。
        """

        if sys.platform != "win32":
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._ready.clear()
        self._started_ok = False
        self._thread = threading.Thread(
            target=self._run,
            name="KeyScoreHotkeys",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self._started_ok

    def stop(self) -> None:
        """停止快捷键线程并解除全部系统注册。"""

        thread = self._thread
        if thread is None:
            return
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(
                self._thread_id,
                self._WM_QUIT,
                0,
                0,
            )
        if thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        self._thread_id = 0

    def _run(self) -> None:
        """注册快捷键、分发 WM_HOTKEY，并在退出时全部解除注册。"""

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._thread_id = int(kernel32.GetCurrentThreadId())
        registered: list[int] = []
        try:
            for hotkey_id, value in self._hotkeys.items():
                modifiers, virtual_key, _canonical = parse_hotkey(value)
                if not user32.RegisterHotKey(
                    None,
                    hotkey_id,
                    modifiers | self._MOD_NOREPEAT,
                    virtual_key,
                ):
                    self._started_ok = False
                    self._ready.set()
                    return
                registered.append(hotkey_id)
            self._started_ok = True
            self._ready.set()
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == self._WM_HOTKEY:
                    callback = self._callbacks.get(int(message.wParam))
                    if callback is not None:
                        callback()
        finally:
            for hotkey_id in registered:
                user32.UnregisterHotKey(None, hotkey_id)
            if not self._ready.is_set():
                self._ready.set()
