"""Windows 全局键盘和鼠标低级监听器。"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from typing import Callable

from ..models import Binding, BindingKind
from .models import PhysicalInputEvent


if sys.platform == "win32":
    ULONG_PTR = ctypes.c_size_t
    LRESULT = ctypes.c_ssize_t

    class _KBDLLHOOKSTRUCT(ctypes.Structure):
        """对应 Win32 KBDLLHOOKSTRUCT。"""

        _fields_ = (
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        )

    class _MSLLHOOKSTRUCT(ctypes.Structure):
        """对应 Win32 MSLLHOOKSTRUCT。"""

        _fields_ = (
            ("pt", wintypes.POINT),
            ("mouseData", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        )


class GlobalInputCapture:
    """在专用消息线程中旁路监听全局键盘和鼠标事件。"""

    _WH_KEYBOARD_LL = 13
    _WH_MOUSE_LL = 14
    _WM_QUIT = 0x0012
    _WM_KEYDOWN = 0x0100
    _WM_KEYUP = 0x0101
    _WM_SYSKEYDOWN = 0x0104
    _WM_SYSKEYUP = 0x0105
    _LLKHF_EXTENDED = 0x01
    _LLKHF_INJECTED = 0x10
    _LLMHF_INJECTED = 0x01
    _MOUSE_MESSAGES = {
        0x0201: (1, True),
        0x0202: (1, False),
        0x0204: (2, True),
        0x0205: (2, False),
        0x0207: (3, True),
        0x0208: (3, False),
    }

    def __init__(
        self,
        on_event: Callable[[PhysicalInputEvent], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """
        初始化监听回调。

        Args:
            on_event (Callable[[PhysicalInputEvent], None]): 每次输入事件的回调。
            on_error (Callable[[str], None] | None): 后台监听错误回调。
        """

        self._on_event = on_event
        self._on_error = on_error
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._started_ok = False

    def start(self) -> bool:
        """
        启动全局监听线程。

        Returns:
            bool: 两个系统 Hook 均安装成功时返回 `True`。
        """

        if sys.platform != "win32":
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._ready.clear()
        self._started_ok = False
        self._thread = threading.Thread(
            target=self._run,
            name="KeyScoreInputCapture",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self._started_ok

    def stop(self) -> None:
        """停止监听线程并等待系统 Hook 被卸载。"""

        thread = self._thread
        if thread is None:
            return
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(
                self._thread_id, self._WM_QUIT, 0, 0
            )
        if thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        self._thread_id = 0

    def _emit(self, binding: Binding, pressed: bool, injected: bool) -> None:
        """
        保护用户回调，避免异常逃逸到 Win32 Hook。

        Args:
            binding (Binding): 捕获的物理绑定。
            pressed (bool): 是否为按下事件。
            injected (bool): 是否由软件注入。
        """

        try:
            self._on_event(
                PhysicalInputEvent(
                    time.perf_counter_ns() / 1_000_000.0,
                    binding,
                    pressed,
                    injected,
                )
            )
        except Exception as exc:  # Win32 回调边界必须兜底
            if self._on_error is not None:
                self._on_error(str(exc))

    def _run(self) -> None:
        """安装低级 Hook 并运行当前线程的 Windows 消息循环。"""

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        hook_proc = ctypes.WINFUNCTYPE(
            LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.SetWindowsHookExW.argtypes = (
            ctypes.c_int,
            hook_proc,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        )
        user32.CallNextHookEx.restype = LRESULT
        user32.CallNextHookEx.argtypes = (
            wintypes.HHOOK,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
        self._thread_id = int(kernel32.GetCurrentThreadId())

        @hook_proc
        def keyboard_callback(code: int, wparam: int, lparam: int) -> int:
            """
            转换键盘低级 Hook 数据并继续系统 Hook 链。

            Args:
                code (int): Hook 处理代码。
                wparam (int): 键盘消息类型。
                lparam (int): KBDLLHOOKSTRUCT 指针。

            Returns:
                int: 后续 Hook 的处理结果。
            """

            if code >= 0 and wparam in {
                self._WM_KEYDOWN,
                self._WM_KEYUP,
                self._WM_SYSKEYDOWN,
                self._WM_SYSKEYUP,
            }:
                data = ctypes.cast(lparam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                pressed = wparam in {self._WM_KEYDOWN, self._WM_SYSKEYDOWN}
                extended = bool(data.flags & self._LLKHF_EXTENDED)
                injected = bool(data.flags & self._LLKHF_INJECTED)
                binding = Binding(
                    BindingKind.KEYBOARD,
                    int(data.scanCode),
                    f"Scan {int(data.scanCode)}",
                    extended,
                )
                self._emit(binding, pressed, injected)
            return int(user32.CallNextHookEx(None, code, wparam, lparam))

        @hook_proc
        def mouse_callback(code: int, wparam: int, lparam: int) -> int:
            """
            转换鼠标低级 Hook 数据并继续系统 Hook 链。

            Args:
                code (int): Hook 处理代码。
                wparam (int): 鼠标消息类型。
                lparam (int): MSLLHOOKSTRUCT 指针。

            Returns:
                int: 后续 Hook 的处理结果。
            """

            if code >= 0:
                data = ctypes.cast(lparam, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                mapping = self._MOUSE_MESSAGES.get(wparam)
                if mapping is None and wparam in {0x020B, 0x020C}:
                    xbutton = (int(data.mouseData) >> 16) & 0xFFFF
                    mapping = (3 + xbutton, wparam == 0x020B)
                if mapping is not None:
                    mouse_code, pressed = mapping
                    self._emit(
                        Binding(BindingKind.MOUSE, mouse_code, f"鼠标键 {mouse_code}"),
                        pressed,
                        bool(data.flags & self._LLMHF_INJECTED),
                    )
            return int(user32.CallNextHookEx(None, code, wparam, lparam))

        module = kernel32.GetModuleHandleW(None)
        keyboard_hook = user32.SetWindowsHookExW(
            self._WH_KEYBOARD_LL, keyboard_callback, module, 0
        )
        mouse_hook = user32.SetWindowsHookExW(
            self._WH_MOUSE_LL, mouse_callback, module, 0
        )
        self._started_ok = bool(keyboard_hook and mouse_hook)
        self._ready.set()
        if not self._started_ok:
            if keyboard_hook:
                user32.UnhookWindowsHookEx(keyboard_hook)
            if mouse_hook:
                user32.UnhookWindowsHookEx(mouse_hook)
            if self._on_error is not None:
                error = ctypes.get_last_error()
                message = str(ctypes.WinError(error)) if error else "无法安装全局输入监听器"
                self._on_error(message)
            return

        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            user32.UnhookWindowsHookEx(keyboard_hook)
            user32.UnhookWindowsHookEx(mouse_hook)
