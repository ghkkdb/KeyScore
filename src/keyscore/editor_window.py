"""独立的曲谱编辑窗口。"""

from __future__ import annotations

from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QFont, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .library import rename_score_file
from .parser import ScoreParseError, parse_score
from .piano_roll import PianoRollEditor
from .score_document import ScoreDocument, document_from_text, serialize_document
from .score_editing import set_total_duration
from .theme import set_widget_state
from .window_chrome import SmoothComboBox


class ScoreEditorWindow(QMainWindow):
    """在独立窗口中编辑并保存一份文本简谱。"""

    saved = Signal(object)

    def __init__(
        self,
        path: Path | None,
        parent: QWidget | None = None,
        duration_presets: tuple[str, ...] = ("1/4", "1/2", "3/4", "1", "2", "4"),
        default_note_duration: str = "1",
        duration_cycle_hotkey: str = "D",
        duration_reverse_hotkey: str = "A",
        initial_text: str | None = None,
        save_new: Callable[[str], Path] | None = None,
    ) -> None:
        """
        初始化曲谱编辑窗口。

        Args:
            path (Path | None): 待编辑文件路径；新建草稿时为空。
            parent (QWidget | None): 父窗口。
            duration_presets (tuple[str, ...]): 新音符常用拍数。
            default_note_duration (str): 打开编辑器时默认选中的拍数。
            duration_cycle_hotkey (str): 循环切换拍数的窗口快捷键。
            duration_reverse_hotkey (str): 反向循环切换拍数的窗口快捷键。
            initial_text (str | None): 新建草稿使用的初始曲谱文本。
            save_new (Callable[[str], Path] | None): 保存新建草稿的回调。
        """

        super().__init__(parent)
        self.path = path
        self._save_new = save_new
        self._syncing_views = False
        self._roll_dirty = False
        self._text_dirty = False
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f"编辑 · {path.stem}" if path is not None else "新建曲谱")
        self.resize(980, 700)
        self.setMinimumSize(760, 540)

        central = QWidget(objectName="editorWindow")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(30, 24, 30, 22)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("曲谱编辑")
        title.setObjectName("dialogTitle")
        syntax = QLabel("双击添加音符，单击选择后可删除；音符不支持拖动")
        syntax.setObjectName("muted")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(syntax)

        self.editor = QPlainTextEdit()
        if path is None:
            if initial_text is None or save_new is None:
                raise ValueError("新建曲谱缺少初始内容或保存回调")
            source_text = initial_text
        else:
            source_text = path.read_text(encoding="utf-8")
        self.editor.setPlainText(source_text)
        font = QFont("Cascadia Mono")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(font)
        self.editor.textChanged.connect(self._on_text_changed)

        roll_page = QWidget()
        roll_layout = QVBoxLayout(roll_page)
        roll_layout.setContentsMargins(0, 8, 0, 0)
        roll_layout.setSpacing(10)
        roll_tools = QHBoxLayout()
        roll_tools.setSpacing(8)
        self.undo_button = QPushButton("撤销")
        self.redo_button = QPushButton("重做")
        self.undo_button.setToolTip("撤销最近一次添加或删除")
        self.redo_button.setToolTip("仅在执行撤销后恢复被撤销的操作")
        self.undo_button.setEnabled(False)
        self.redo_button.setEnabled(False)
        delete_button = QPushButton("删除音符")
        zoom_out_button = QPushButton("缩小")
        zoom_in_button = QPushButton("放大")
        self.grid_combo = SmoothComboBox()
        self.duration_combo = SmoothComboBox()
        for label, value in (
            ("1 拍", "1"),
            ("1/2 拍", "1/2"),
            ("1/4 拍", "1/4"),
            ("1/8 拍", "1/8"),
            ("1/16 拍", "1/16"),
        ):
            self.grid_combo.addItem(f"网格 {label}", value)
        self.grid_combo.setCurrentIndex(2)
        for value in duration_presets:
            self.duration_combo.addItem(f"新音符 {value} 拍", value)
        self.duration_combo.setCurrentIndex(
            max(0, self.duration_combo.findData(default_note_duration))
        )
        self.roll_editor = PianoRollEditor(editable=True)
        self.roll_editor.setMinimumHeight(360)
        self.roll_editor.document_changed.connect(self._on_roll_document_changed)
        self.roll_editor.edit_error.connect(self._show_roll_error)
        self.undo_button.clicked.connect(self.roll_editor.undo_stack.undo)
        self.redo_button.clicked.connect(self.roll_editor.undo_stack.redo)
        self.roll_editor.undo_stack.canUndoChanged.connect(self.undo_button.setEnabled)
        self.roll_editor.undo_stack.canRedoChanged.connect(self.redo_button.setEnabled)
        delete_button.clicked.connect(self.roll_editor.delete_selected_notes)
        zoom_out_button.clicked.connect(self.roll_editor.zoom_out)
        zoom_in_button.clicked.connect(self.roll_editor.zoom_in)
        self.grid_combo.currentIndexChanged.connect(self._apply_roll_grid)
        self.duration_combo.currentIndexChanged.connect(self._apply_roll_duration)
        roll_tools.addWidget(self.undo_button)
        roll_tools.addWidget(self.redo_button)
        roll_tools.addWidget(delete_button)
        roll_tools.addSpacing(10)
        roll_tools.addWidget(self.grid_combo)
        roll_tools.addWidget(self.duration_combo)
        roll_tools.addStretch()
        roll_tools.addWidget(zoom_out_button)
        roll_tools.addWidget(zoom_in_button)
        roll_layout.addLayout(roll_tools)
        roll_layout.addWidget(self.roll_editor, 1)

        text_page = QWidget()
        text_layout = QVBoxLayout(text_page)
        text_layout.setContentsMargins(0, 8, 0, 0)
        text_layout.setSpacing(10)

        duration_bar = QHBoxLayout()
        duration_hint = QLabel("总时值")
        duration_hint.setObjectName("muted")
        duration_bar.addWidget(duration_hint)
        for label, duration in (
            ("¼ 拍", "0.25"),
            ("½ 拍", "0.5"),
            ("¾ 拍", "0.75"),
            ("1 拍", "1"),
            ("1½ 拍", "1.5"),
            ("2 拍", "2"),
        ):
            button = QPushButton(label)
            button.setToolTip("设置光标所在或选中音符的总时值")
            button.clicked.connect(
                lambda _checked=False, value=duration: self._set_total_duration(value)
            )
            duration_bar.addWidget(button)
        custom_duration_button = QPushButton("自定义…")
        custom_duration_button.clicked.connect(self._set_custom_duration)
        duration_bar.addWidget(custom_duration_button)
        duration_bar.addStretch()

        insert_bar = QHBoxLayout()
        insert_hint = QLabel("插入")
        insert_hint.setObjectName("muted")
        insert_bar.addWidget(insert_hint)
        for label, token in (
            ("小节 |", "|"),
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
        self.editor_tabs = QTabWidget()
        self.editor_tabs.setObjectName("editorTabs")
        self.editor_tabs.addTab(roll_page, "钢琴卷帘")
        self.editor_tabs.addTab(text_page, "曲谱文本")
        self.editor_tabs.currentChanged.connect(self._on_editor_tab_changed)
        text_layout.addLayout(duration_bar)
        text_layout.addLayout(insert_bar)
        text_layout.addWidget(self.editor, 1)
        layout.addLayout(header)
        layout.addWidget(self.editor_tabs, 1)
        layout.addLayout(footer)
        self.setCentralWidget(central)
        self.duration_shortcut = QShortcut(
            QKeySequence(duration_cycle_hotkey.replace("Win+", "Meta+")), self
        )
        self.duration_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.duration_shortcut.activated.connect(self._cycle_note_duration)
        self.duration_reverse_shortcut = QShortcut(
            QKeySequence(duration_reverse_hotkey.replace("Win+", "Meta+")), self
        )
        self.duration_reverse_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.duration_reverse_shortcut.activated.connect(
            self._cycle_note_duration_reverse
        )
        self.undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self.undo_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.undo_shortcut.activated.connect(self.roll_editor.undo_stack.undo)
        self.redo_shortcut = QShortcut(QKeySequence.StandardKey.Redo, self)
        self.redo_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.redo_shortcut.activated.connect(self.roll_editor.undo_stack.redo)
        try:
            self.roll_editor.set_score_document(document_from_text(source_text))
        except ScoreParseError:
            self.editor_tabs.setCurrentWidget(text_page)
        self._apply_roll_grid()
        self._apply_roll_duration()
        self._validate()
        self.editor.document().setModified(path is None)

    def set_duration_settings(
        self,
        presets: tuple[str, ...],
        default_duration: str,
        hotkey: str,
        reverse_hotkey: str,
    ) -> None:
        """
        刷新拍数预设和编辑器快捷键，并尽量保留当前选择。

        Args:
            presets (tuple[str, ...]): 规范化后的常用拍数。
            default_duration (str): 当前选择失效时采用的默认拍数。
            hotkey (str): 循环切换拍数的快捷键。
            reverse_hotkey (str): 反向循环切换拍数的快捷键。
        """

        current = str(self.duration_combo.currentData() or default_duration)
        self.duration_combo.blockSignals(True)
        self.duration_combo.clear()
        for value in presets:
            self.duration_combo.addItem(f"新音符 {value} 拍", value)
        selected = current if current in presets else default_duration
        self.duration_combo.setCurrentIndex(max(0, self.duration_combo.findData(selected)))
        self.duration_combo.blockSignals(False)
        self.duration_shortcut.setKey(QKeySequence(hotkey.replace("Win+", "Meta+")))
        self.duration_reverse_shortcut.setKey(
            QKeySequence(reverse_hotkey.replace("Win+", "Meta+"))
        )
        self._apply_roll_duration()

    def _cycle_note_duration(self) -> None:
        """循环切换到用户拍数列表中的下一项。"""

        self._cycle_note_duration_by(1)

    def _cycle_note_duration_reverse(self) -> None:
        """反向循环切换到用户拍数列表中的上一项。"""

        self._cycle_note_duration_by(-1)

    def _cycle_note_duration_by(self, step: int) -> None:
        """
        按指定方向循环切换新音符拍数。

        Args:
            step (int): 循环方向；正数向后，负数向前。
        """

        if self.editor_tabs.currentIndex() != 0 or self.duration_combo.count() == 0:
            return
        next_index = (self.duration_combo.currentIndex() + step) % self.duration_combo.count()
        self.duration_combo.setCurrentIndex(next_index)
        self.validation_label.setText(
            f"新音符拍数：{self.duration_combo.currentData()} 拍"
        )
        set_widget_state(self.validation_label, "normal")

    def _apply_roll_grid(self, _index: int = -1) -> None:
        """
        将工具栏选择的吸附网格应用到卷帘。

        Args:
            _index (int): 组合框发送的当前索引。
        """

        value = self.grid_combo.currentData()
        if value is not None:
            self.roll_editor.set_grid(Fraction(str(value)))

    def _apply_roll_duration(self, _index: int = -1) -> None:
        """
        将工具栏选择的默认时值应用到新建音符。

        Args:
            _index (int): 组合框发送的当前索引。
        """

        value = self.duration_combo.currentData()
        if value is not None:
            self.roll_editor.set_default_duration(Fraction(str(value)))

    def _on_roll_document_changed(self, value: object) -> None:
        """
        标记卷帘修改，文本只在切换页面或保存时同步。

        Args:
            value (object): 卷帘发送的新文档。
        """

        if self._syncing_views or not isinstance(value, ScoreDocument):
            return
        self._roll_dirty = True
        self._text_dirty = False
        self.editor.document().setModified(True)
        note_count = sum(len(group.pitches) for group in value.groups)
        self.validation_label.setText(
            f"卷帘已修改 · {note_count} 个音符 · {float(value.total_beats):g} 拍"
        )
        set_widget_state(self.validation_label, "warning")

    def _sync_roll_to_text(self) -> bool:
        """
        在需要查看或保存文本时执行一次卷帘序列化。

        Returns:
            bool: 同步成功或无需同步时为 `True`。
        """

        if not self._roll_dirty:
            return True
        document = self.roll_editor.score_document()
        if document is None:
            return False
        try:
            text = serialize_document(document)
        except ValueError as exc:
            self._show_roll_error(str(exc))
            return False
        self._syncing_views = True
        self.editor.setPlainText(text)
        self.editor.document().setModified(True)
        self._syncing_views = False
        self._roll_dirty = False
        self._text_dirty = False
        self._validate()
        return True

    def _on_text_changed(self) -> None:
        """标记文本已修改并执行实时语法检查。"""

        if self._syncing_views:
            return
        self._text_dirty = True
        self._roll_dirty = False
        self._validate()

    def _on_editor_tab_changed(self, index: int) -> None:
        """
        切回卷帘时解析文本并阻止无效内容进入图形编辑器。

        Args:
            index (int): 当前标签页索引。
        """

        self.duration_shortcut.setEnabled(index == 0)
        self.duration_reverse_shortcut.setEnabled(index == 0)
        self.undo_shortcut.setEnabled(index == 0)
        self.redo_shortcut.setEnabled(index == 0)
        if self._syncing_views:
            return
        if index == 1:
            self._sync_roll_to_text()
            return
        if not self._text_dirty:
            return
        try:
            document = document_from_text(self.editor.toPlainText())
        except ScoreParseError as exc:
            self.validation_label.setText(str(exc))
            set_widget_state(self.validation_label, "error")
            self.editor_tabs.blockSignals(True)
            self.editor_tabs.setCurrentIndex(1)
            self.editor_tabs.blockSignals(False)
            self.duration_shortcut.setEnabled(False)
            self.duration_reverse_shortcut.setEnabled(False)
            self.undo_shortcut.setEnabled(False)
            self.redo_shortcut.setEnabled(False)
            self.editor.setFocus()
            return
        self.roll_editor.set_score_document(document)
        self._text_dirty = False

    def _show_roll_error(self, message: str) -> None:
        """
        在编辑器状态栏显示卷帘约束错误。

        Args:
            message (str): 用户可理解的错误内容。
        """

        self.validation_label.setText(message)
        set_widget_state(self.validation_label, "warning")

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

    def _set_total_duration(self, duration: str) -> None:
        """
        设置光标所在或选择区域内音符的精确总时值。

        Args:
            duration (str): 大于零的整数或小数拍数。
        """

        cursor = self.editor.textCursor()
        source = self.editor.toPlainText()
        try:
            result = set_total_duration(
                source,
                cursor.selectionStart(),
                cursor.selectionEnd(),
                duration,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "时值无效", str(exc))
            return
        if result.changed_count == 0:
            self.validation_label.setText("请将光标放在音符、休止符或和弦上")
            set_widget_state(self.validation_label, "warning")
            self.editor.setFocus()
            return

        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(result.text)
        cursor.endEditBlock()
        cursor.setPosition(result.cursor_position)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def _set_custom_duration(self) -> None:
        """询问自定义拍数并应用到光标所在或选中的音符。"""

        duration, accepted = QInputDialog.getDouble(
            self,
            "自定义总时值",
            "总拍数：",
            1.0,
            0.001,
            9999.0,
            3,
        )
        if not accepted:
            return
        duration_text = f"{duration:.3f}".rstrip("0").rstrip(".")
        self._set_total_duration(duration_text)

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

        if not self._sync_roll_to_text():
            QMessageBox.warning(self, "无法保存", "卷帘内容无法转换为有效曲谱文本")
            return

        try:
            score = parse_score(self.editor.toPlainText())
        except ScoreParseError as exc:
            QMessageBox.warning(self, "无法保存", str(exc))
            return
        try:
            if self.path is None:
                if self._save_new is None:
                    raise ValueError("新建曲谱没有可用的保存位置")
                self.path = self._save_new(self.editor.toPlainText())
            else:
                self.path.write_text(self.editor.toPlainText(), encoding="utf-8")
                self.path = rename_score_file(self.path, score.title)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.editor.document().setModified(False)
        self._roll_dirty = False
        self._text_dirty = False
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
            set_widget_state(self.validation_label, "normal")
        except ScoreParseError as exc:
            self.validation_label.setText(str(exc))
            set_widget_state(self.validation_label, "error")

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
