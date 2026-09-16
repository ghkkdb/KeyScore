"""全局播放和紧急停止快捷键监听。"""

from __future__ import annotations

from typing import Callable, Any


class GlobalHotkeyListener:
    """使用 pynput 监听 F9 和 F10，且屏蔽自动重复按键。"""

    def __init__(self, on_toggle: Callable[[], None], on_stop: Callable[[], None]) -> None:
        """
        初始化全局快捷键监听器。

        Args:
            on_toggle (Callable[[], None]): F9 首次按下回调。
            on_stop (Callable[[], None]): F10 首次按下回调。
        """

        self._on_toggle = on_toggle
        self._on_stop = on_stop
        self._listener: Any | None = None
        self._pressed: set[Any] = set()

    def start(self) -> bool:
        """
        启动监听器。

        Returns:
            bool: pynput 可用且启动成功时返回 `True`。
        """

        try:
            from pynput import keyboard
        except ImportError:
            return False

        def on_press(key: Any) -> None:
            if key in self._pressed:
                return
            self._pressed.add(key)
            if key == keyboard.Key.f9:
                self._on_toggle()
            elif key == keyboard.Key.f10:
                self._on_stop()

        def on_release(key: Any) -> None:
            self._pressed.discard(key)

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()
        return True

    def stop(self) -> None:
        """停止全局快捷键监听。"""

        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._pressed.clear()
