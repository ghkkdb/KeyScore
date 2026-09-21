"""键盘扫描码和鼠标按键录入对话框。"""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QMouseEvent
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from .models import Binding, BindingKind


class BindingCaptureDialog(QDialog):
    """等待用户录入单键、单独修饰键或标准组合键。"""

    _MOUSE_BINDINGS = {
        Qt.MouseButton.LeftButton: (1, "鼠标左键"),
        Qt.MouseButton.RightButton: (2, "鼠标右键"),
        Qt.MouseButton.MiddleButton: (3, "鼠标中键"),
        Qt.MouseButton.BackButton: (4, "鼠标侧键 1"),
        Qt.MouseButton.ForwardButton: (5, "鼠标侧键 2"),
    }
    _MODIFIER_LABELS = {
        Qt.Key.Key_Control: "Ctrl",
        Qt.Key.Key_Alt: "Alt",
        Qt.Key.Key_Shift: "Shift",
        Qt.Key.Key_Meta: "Win",
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
        self._held_modifiers: dict[int, Binding] = {}
        self._used_primary = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 22)
        layout.setSpacing(12)
        title = QLabel("按下单键或组合键")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("dialogTitle")
        self.hint = QLabel(
            "支持单键、单独 Ctrl / Alt / Shift / Win，或修饰键组合\nEsc 取消"
        )
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setObjectName("muted")
        cancel = QPushButton("取消")
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel.clicked.connect(self.reject)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(self.hint)
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

        if event.key() == Qt.Key.Key_Escape and not self._held_modifiers:
            self.reject()
            return
        if event.isAutoRepeat():
            return
        binding = self._binding_from_key_event(event)
        if binding is None:
            return
        if event.key() in self._MODIFIER_LABELS:
            self._held_modifiers[event.key()] = binding
            self.hint.setText(
                f"正在录入：{'+'.join(item.label for item in self._held_modifiers.values())}\n"
                "直接松开可绑定单独修饰键，或继续按下主键"
            )
            return
        self._used_primary = True
        self.binding = Binding(
            binding.kind,
            binding.code,
            binding.label,
            binding.extended,
            tuple(self._held_modifiers.values()),
        )
        self.accept()

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        """
        在修饰键没有配合主键使用时将其保存为单独绑定。

        Args:
            event (QKeyEvent): Qt 键盘释放事件。
        """

        if event.isAutoRepeat() or event.key() not in self._held_modifiers:
            return
        binding = self._held_modifiers.pop(event.key())
        if not self._used_primary and not self._held_modifiers:
            self.binding = binding
            self.accept()

    def _binding_from_key_event(self, event: QKeyEvent) -> Binding | None:
        """
        将 Qt 键盘事件转换为不含组合修饰的物理绑定。

        Args:
            event (QKeyEvent): Qt 键盘事件。

        Returns:
            Binding | None: 可识别的物理绑定，无法取得扫描码时返回空。
        """

        native_scan = int(event.nativeScanCode())
        if native_scan == 0 and sys.platform == "win32":
            native_scan = int(ctypes.windll.user32.MapVirtualKeyW(int(event.nativeVirtualKey()), 0))
        if native_scan == 0:
            return None
        extended = bool(native_scan & 0xE000)
        scan_code = native_scan & 0xFF if extended else native_scan
        label = self._MODIFIER_LABELS.get(event.key())
        if label is None:
            label = QKeySequence(event.key()).toString() or event.text().upper()
        return Binding(
            BindingKind.KEYBOARD,
            scan_code,
            label or f"Scan {scan_code}",
            extended,
        )

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
        self.binding = Binding(
            BindingKind.MOUSE,
            code,
            label,
            modifiers=tuple(self._held_modifiers.values()),
        )
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
