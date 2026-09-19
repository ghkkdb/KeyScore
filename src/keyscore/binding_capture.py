"""键盘扫描码和鼠标按键录入对话框。"""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QMouseEvent
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from .models import Binding, BindingKind


class BindingCaptureDialog(QDialog):
    """等待用户按下一个键盘键或鼠标按键。"""

    _MOUSE_BINDINGS = {
        Qt.MouseButton.LeftButton: (1, "鼠标左键"),
        Qt.MouseButton.RightButton: (2, "鼠标右键"),
        Qt.MouseButton.MiddleButton: (3, "鼠标中键"),
        Qt.MouseButton.BackButton: (4, "鼠标侧键 1"),
        Qt.MouseButton.ForwardButton: (5, "鼠标侧键 2"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        初始化按键录入对话框。

        Args:
            parent (QWidget | None): 父窗口。
        """

        super().__init__(parent)
        self.setWindowTitle("录入按键")
        self.setModal(True)
        self.setFixedSize(360, 190)
        self.binding: Binding | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 22)
        layout.setSpacing(12)
        title = QLabel("按下一个按键")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("dialogTitle")
        hint = QLabel("支持键盘、鼠标左/中/右键和侧键\nEsc 取消")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setObjectName("muted")
        cancel = QPushButton("取消")
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel.clicked.connect(self.reject)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addStretch()
        layout.addWidget(cancel, alignment=Qt.AlignmentFlag.AlignCenter)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        将键盘事件转换为物理扫描码绑定。

        Args:
            event (QKeyEvent): Qt 键盘按下事件。
        """

        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        native_scan = int(event.nativeScanCode())
        if native_scan == 0 and sys.platform == "win32":
            native_scan = int(ctypes.windll.user32.MapVirtualKeyW(int(event.nativeVirtualKey()), 0))
        if native_scan == 0:
            return
        extended = bool(native_scan & 0xE000)
        scan_code = native_scan & 0xFF if extended else native_scan
        label = QKeySequence(event.key()).toString() or event.text().upper() or f"Scan {scan_code}"
        self.binding = Binding(BindingKind.KEYBOARD, scan_code, label, extended)
        self.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        将鼠标按下事件转换为鼠标绑定。

        Args:
            event (QMouseEvent): Qt 鼠标按下事件。
        """

        value = self._MOUSE_BINDINGS.get(event.button())
        if value is None:
            super().mousePressEvent(event)
            return
        code, label = value
        self.binding = Binding(BindingKind.MOUSE, code, label)
        self.accept()


def capture_binding(parent: QWidget | None = None) -> Binding | None:
    """
    打开按键录入对话框并返回结果。

    Args:
        parent (QWidget | None): 父窗口。

    Returns:
        Binding | None: 用户完成录入时的绑定，取消时返回 `None`。
    """

    dialog = BindingCaptureDialog(parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.binding
    return None
