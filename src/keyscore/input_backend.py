"""Windows SendInput 输出后端与测试记录后端。"""

from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from typing import Protocol

from .models import ActionType, Binding, BindingKind, TimedInputEvent, binding_components


class InputBackend(Protocol):
    """定义播放器所需的输入输出能力。"""

    def emit(self, event: TimedInputEvent) -> None:
        """发送一个定时输入事件。"""

    def release_all(self) -> None:
        """释放后端记录的所有已按下按键。"""


class RecordingBackend:
    """仅记录事件而不真正发送键鼠输入的测试后端。"""

    def __init__(self) -> None:
        """初始化空的事件记录。"""

        self.events: list[TimedInputEvent] = []
        self.release_count = 0

    def emit(self, event: TimedInputEvent) -> None:
        """
        记录一个输入事件。

        Args:
            event (TimedInputEvent): 待记录事件。
        """

        self.events.append(event)

    def release_all(self) -> None:
        """记录一次全部释放操作。"""

        self.release_count += 1


if sys.platform == "win32":
    ULONG_PTR = wintypes.WPARAM

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = (
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        )

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = (
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        )

    class _INPUTUNION(ctypes.Union):
        _fields_ = (("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT))

    class _INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = (("type", wintypes.DWORD), ("union", _INPUTUNION))


class WindowsSendInputBackend:
    """通过 Windows SendInput 和键盘扫描码发送前台输入。"""

    _INPUT_MOUSE = 0
    _INPUT_KEYBOARD = 1
    _KEYEVENTF_KEYUP = 0x0002
    _KEYEVENTF_EXTENDEDKEY = 0x0001
    _KEYEVENTF_SCANCODE = 0x0008
    _MOUSE_FLAGS = {
        1: (0x0002, 0x0004, 0),
        2: (0x0008, 0x0010, 0),
        3: (0x0020, 0x0040, 0),
        4: (0x0080, 0x0100, 0x0001),
        5: (0x0080, 0x0100, 0x0002),
    }

    def __init__(self) -> None:
        """
        初始化 SendInput 后端。

        Raises:
            OSError: 当前系统不是 Windows 时抛出。
        """

        if sys.platform != "win32":
            raise OSError("WindowsSendInputBackend 仅支持 Windows")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._pressed: dict[Binding, int] = {}
        self._lock = threading.RLock()

    def _send(self, input_value: "_INPUT") -> None:
        """
        发送单个 Win32 INPUT 结构。

        Args:
            input_value (_INPUT): 待发送的 Windows 输入结构。

        Raises:
            OSError: SendInput 返回失败时抛出。
        """

        sent = self._user32.SendInput(1, ctypes.byref(input_value), ctypes.sizeof(_INPUT))
        if sent != 1:
            error_code = ctypes.get_last_error()
            if error_code:
                raise ctypes.WinError(error_code)
            raise OSError("SendInput 未发送任何事件，请检查游戏和 KeyScore 的运行权限")

    def _send_binding(self, binding: Binding, pressed: bool) -> None:
        """
        发送指定绑定的按下或释放事件。

        Args:
            binding (Binding): 键盘或鼠标绑定。
            pressed (bool): `True` 表示按下，`False` 表示释放。

        Raises:
            ValueError: 鼠标按键代码不受支持时抛出。
        """

        if binding.kind is BindingKind.KEYBOARD:
            flags = self._KEYEVENTF_SCANCODE | (0 if pressed else self._KEYEVENTF_KEYUP)
            if binding.extended:
                flags |= self._KEYEVENTF_EXTENDEDKEY
            value = _INPUT(
                type=self._INPUT_KEYBOARD,
                ki=_KEYBDINPUT(wVk=0, wScan=binding.code, dwFlags=flags, time=0, dwExtraInfo=0),
            )
        else:
            if binding.code not in self._MOUSE_FLAGS:
                raise ValueError(f"不支持的鼠标按键代码：{binding.code}")
            down_flag, up_flag, mouse_data = self._MOUSE_FLAGS[binding.code]
            value = _INPUT(
                type=self._INPUT_MOUSE,
                mi=_MOUSEINPUT(
                    dx=0,
                    dy=0,
                    mouseData=mouse_data,
                    dwFlags=down_flag if pressed else up_flag,
                    time=0,
                    dwExtraInfo=0,
                ),
            )
        self._send(value)

    def emit(self, event: TimedInputEvent) -> None:
        """
        发送一个定时输入事件并跟踪按下状态。

        Args:
            event (TimedInputEvent): 待发送事件。
        """

        with self._lock:
            components = binding_components(event.binding)
            if event.action is ActionType.PRESS:
                for binding in components:
                    count = self._pressed.get(binding, 0)
                    if count == 0:
                        self._send_binding(binding, True)
                    self._pressed[binding] = count + 1
                return
            for binding in reversed(components):
                count = self._pressed.get(binding, 0)
                if count <= 1:
                    if count:
                        self._send_binding(binding, False)
                    self._pressed.pop(binding, None)
                else:
                    self._pressed[binding] = count - 1

    def release_all(self) -> None:
        """释放所有由本后端记录为已按下的键鼠按键。"""

        with self._lock:
            bindings = tuple(reversed(self._pressed))
            for binding in bindings:
                try:
                    self._send_binding(binding, False)
                finally:
                    self._pressed.pop(binding, None)
