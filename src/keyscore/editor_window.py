"""独立的曲谱编辑窗口。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QFont, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .library import rename_score_file
from .parser import ScoreParseError, parse_score


class ScoreEditorWindow(QMainWindow):
    """在独立窗口中编辑并保存一份文本简谱。"""

    saved = Signal(object)

    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        """
        初始化曲谱编辑窗口。

        Args:
            path (Path): 待编辑文件路径。
            parent (QWidget | None): 父窗口。
        """

        super().__init__(parent)
        self.path = path
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f"编辑 · {path.stem}")
        self.resize(780, 620)
        self.setMinimumSize(600, 460)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(30, 24, 30, 22)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("曲谱编辑")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        syntax = QLabel("# 半音   L 低音   H 高音   - 延一拍   --- 段落")
        syntax.setObjectName("muted")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(syntax)

        self.editor = QPlainTextEdit()
        self.editor.setPlainText(path.read_text(encoding="utf-8"))
        font = QFont("Cascadia Mono")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(font)
        self.editor.textChanged.connect(self._validate)

        insert_bar = QHBoxLayout()
        insert_hint = QLabel("插入")
        insert_hint.setObjectName("muted")
        insert_bar.addWidget(insert_hint)
        for label, token in (
            ("延长 1 拍", "-"),
            ("休止 ½ 拍", "0:0.5"),
            ("休止 1 拍", "0"),
            ("休止 2 拍", "0:2"),
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, value=token: self._insert_score_token(value)
            )
            insert_bar.addWidget(button)
        section_button = QPushButton("段落停顿")
        section_button.clicked.connect(self._insert_section_break)
        insert_bar.addWidget(section_button)
        insert_bar.addStretch()

        footer = QHBoxLayout()
        self.validation_label = QLabel("语法正确")
        self.validation_label.setObjectName("muted")
        save_button = QPushButton("保存", objectName="primary")
        save_button.clicked.connect(self.save)
        footer.addWidget(self.validation_label)
        footer.addStretch()
        footer.addWidget(save_button)
        layout.addLayout(header)
        layout.addLayout(insert_bar)
        layout.addWidget(self.editor, 1)
        layout.addLayout(footer)
        self.setCentralWidget(central)
        self._validate()
        self.editor.document().setModified(False)

    def _insert_score_token(self, token: str) -> None:
        """
        在光标位置插入一个带安全空格的曲谱词元。

        Args:
            token (str): 要插入的休止符或音符文本。
        """

        cursor = self.editor.textCursor()
        source = self.editor.toPlainText()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        prefix = "" if start == 0 or source[start - 1].isspace() else " "
        suffix = "" if end == len(source) or source[end].isspace() else " "
        cursor.insertText(f"{prefix}{token}{suffix}")
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def _insert_section_break(self) -> None:
        """在当前行之后插入一个独立的段落停顿标记。"""

        cursor = self.editor.textCursor()
        cursor.clearSelection()
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cursor.insertText("\n---\n")
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def save(self) -> None:
        """经用户确认后校验并保存曲谱，成功后关闭编辑窗口。"""

        result = QMessageBox.question(
            self,
            "保存并关闭？",
            "确定保存当前曲谱并关闭编辑窗口吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        try:
            score = parse_score(self.editor.toPlainText())
        except ScoreParseError as exc:
            QMessageBox.warning(self, "无法保存", str(exc))
            return
        try:
            self.path.write_text(self.editor.toPlainText(), encoding="utf-8")
            self.path = rename_score_file(self.path, score.title)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.editor.document().setModified(False)
        self.setWindowTitle(f"编辑 · {score.title}")
        self.saved.emit(self.path)
        self.close()

    def _validate(self) -> None:
        """实时显示曲谱语法检查结果。"""

        try:
            score = parse_score(self.editor.toPlainText())
            self.validation_label.setText(
                f"语法正确 · {len(score.notes)} 个音符 · {float(score.total_beats):g} 拍"
            )
            self.validation_label.setStyleSheet("color: #777B81;")
        except ScoreParseError as exc:
            self.validation_label.setText(str(exc))
            self.validation_label.setStyleSheet("color: #D86A6A;")

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        在关闭有未保存修改的编辑窗口前请求确认。

        Args:
            event (QCloseEvent): Qt 关闭事件。
        """

        if not self.editor.document().isModified():
            event.accept()
            return
        result = QMessageBox.question(
            self,
            "放弃修改？",
            "当前曲谱尚未保存，是否放弃修改？",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if result == QMessageBox.StandardButton.Discard:
            event.accept()
        else:
            event.ignore()
