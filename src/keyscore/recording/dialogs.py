"""录制参数和录制结果整理对话框。"""

from __future__ import annotations

from datetime import datetime
from fractions import Fraction

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .models import RecordingSettings
from ..window_chrome import SmoothComboBox, SmoothSpinBox


class RecordingSetupDialog(QDialog):
    """收集录制所需的曲名、节拍和识别参数。"""

    def __init__(
        self,
        default_bpm: int = 100,
        default_beat: str = "4/4",
        parent: QWidget | None = None,
    ) -> None:
        """
        初始化参数表单。

        Args:
            default_bpm (int): 默认 BPM。
            default_beat (str): 默认拍号。
            parent (QWidget | None): 父窗口。
        """

        super().__init__(parent)
        self.setWindowTitle("录制游戏演奏")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(QLabel("录制游戏演奏", objectName="dialogTitle"))
        layout.addWidget(
            QLabel(
                "开始后请切换到游戏。KeyScore 只记录当前配置中已映射的键鼠输入。",
                objectName="muted",
            )
        )
        form = QFormLayout()
        form.setSpacing(10)
        self.title_edit = QLineEdit(f"游戏录制 {datetime.now():%Y-%m-%d %H-%M}")
        self.bpm_spin = SmoothSpinBox()
        self.bpm_spin.setRange(20, 400)
        self.bpm_spin.setValue(default_bpm)
        self.beat_combo = SmoothComboBox()
        self.beat_combo.addItems(("4/4", "3/4", "2/4", "6/8"))
        self.beat_combo.setCurrentText(default_beat)
        self.grid_combo = SmoothComboBox()
        for label, value in (
            ("1 拍", "1"),
            ("1/2 拍", "1/2"),
            ("1/4 拍（推荐）", "1/4"),
            ("1/8 拍", "1/8"),
        ):
            self.grid_combo.addItem(label, value)
        self.grid_combo.setCurrentIndex(2)
        self.chord_spin = SmoothSpinBox()
        self.chord_spin.setRange(10, 120)
        self.chord_spin.setSuffix(" ms")
        self.chord_spin.setValue(35)
        self.legato_check = QCheckBox("持续按住模式下识别圆括号连音")
        self.legato_check.setChecked(True)
        form.addRow("曲名", self.title_edit)
        form.addRow("BPM", self.bpm_spin)
        form.addRow("拍号", self.beat_combo)
        form.addRow("量化精度", self.grid_combo)
        form.addRow("和弦容差", self.chord_spin)
        form.addRow("连音", self.legato_check)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("开始录制")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def settings(self) -> RecordingSettings:
        """
        返回表单当前值。

        Returns:
            RecordingSettings: 经过类型转换的录制设置。
        """

        return RecordingSettings(
            title=self.title_edit.text().strip(),
            bpm=self.bpm_spin.value(),
            beat=self.beat_combo.currentText(),
            grid=Fraction(str(self.grid_combo.currentData())),
            chord_tolerance_ms=self.chord_spin.value(),
            detect_legato=self.legato_check.isChecked(),
        )

    def _accept_if_valid(self) -> None:
        """只有参数通过模型校验时才接受对话框。"""

        try:
            self.settings().validate()
        except ValueError as exc:
            self.title_edit.setToolTip(str(exc))
            self.title_edit.setFocus()
            return
        self.accept()


class RecordingReviewDialog(QDialog):
    """允许用户检查和微调自动生成的文本曲谱。"""

    def __init__(self, score_text: str, note_count: int, parent: QWidget | None = None) -> None:
        """
        初始化生成结果预览。

        Args:
            score_text (str): 自动生成的完整曲谱。
            note_count (int): 原始录制音符数量。
            parent (QWidget | None): 父窗口。
        """

        super().__init__(parent)
        self.setWindowTitle("录制整理")
        self.resize(760, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        layout.addWidget(QLabel("录制整理", objectName="dialogTitle"))
        layout.addWidget(
            QLabel(
                f"已记录 {note_count} 个音符。以下内容已量化，可在保存前直接修改。",
                objectName="muted",
            )
        )
        self.editor = QPlainTextEdit(score_text)
        layout.addWidget(self.editor, 1)
        actions = QHBoxLayout()
        cancel = QPushButton("放弃本次录制")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存并打开编辑器", objectName="primary")
        save.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addStretch()
        actions.addWidget(save)
        layout.addLayout(actions)

    def score_text(self) -> str:
        """
        返回用户确认时的曲谱文本。

        Returns:
            str: 对话框编辑器内容。
        """

        return self.editor.toPlainText()
