"""键谱的极简歌单与播放主窗口。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .binding_capture import capture_binding
from .compiler import PlanCompileError, compile_score
from .editor_window import ScoreEditorWindow
from .foreground import foreground_window, is_foreground
from .hotkeys import GlobalHotkeyListener
from .input_backend import WindowsSendInputBackend
from .library import ScoreEntry, ScoreLibrary, default_data_directory
from .models import ActionType, Binding, Octave, PlaybackPlan, TimedInputEvent
from .overlay import CountdownOverlay, PlaybackOverlay
from .parser import ScoreParseError, parse_score
from .playback import PlaybackState, TimelinePlayer
from .profile_store import load_profile, save_profile


_STYLE = """
QMainWindow, QWidget { background: #101112; color: #ECEDEE; }
QMenuBar { background: #101112; color: #8E9298; border: none; }
QMenuBar::item:selected, QMenu::item:selected { background: #202224; color: #FFFFFF; }
QMenu { background: #171819; color: #ECEDEE; border: 1px solid #292B2E; }
QLabel#muted { color: #777B81; }
QListWidget {
    background: #101112; color: #AEB1B6; border: none; outline: none;
    padding: 4px 0; font-size: 14px;
}
QListWidget::item { padding: 9px 10px; border-radius: 4px; }
QListWidget::item:selected { background: #202224; color: #FFFFFF; }
QListWidget::item:hover { background: #181A1C; }
QPlainTextEdit {
    background: #101112; color: #C7C9CD; border: none;
    padding: 16px 0; selection-background-color: #3B3E43;
    font-family: "Cascadia Mono", "Consolas"; font-size: 15px;
}
QComboBox, QSpinBox {
    background: #171819; color: #ECEDEE; border: 1px solid #303236;
    border-radius: 5px; padding: 7px 9px;
}
QPushButton {
    background: transparent; color: #B8BBC0; border: none;
    border-radius: 5px; padding: 8px 12px;
}
QPushButton:hover { background: #1B1D1F; color: #FFFFFF; }
QPushButton#primary { background: #ECEDEE; color: #101112; font-weight: 600; }
QPushButton#primary:hover { background: #FFFFFF; }
QPushButton#binding { background: #171819; border: 1px solid #292B2E; text-align: left; }
QProgressBar { background: #242628; border: none; border-radius: 1px; height: 2px; }
QProgressBar::chunk { background: #ECEDEE; border-radius: 1px; }
QStatusBar { color: #666A70; border-top: 1px solid #202224; }
QSplitter::handle { background: #202224; width: 1px; }
QDialog { background: #101112; }
"""


class _UiSignals(QObject):
    """将快捷键和播放工作线程回调转发到 Qt 主线程。"""

    toggle_requested = Signal()
    stop_requested = Signal()
    state_changed = Signal(str)
    event_emitted = Signal(object)
    playback_error = Signal(str)


class MainWindow(QMainWindow):
    """提供曲谱歌单、播放预览、按键映射和前台安全保护。"""

    def __init__(self) -> None:
        """初始化曲谱库、持久化配置、播放器和界面。"""

        super().__init__()
        self.setWindowTitle("KeyScore 键谱")
        self.resize(980, 680)
        self.setMinimumSize(760, 520)
        self.setStyleSheet(_STYLE)

        self.data_directory = default_data_directory()
        self.library = ScoreLibrary(self.data_directory)
        self.profile_path = self.data_directory / "profile.json"
        self.profile = load_profile(self.profile_path)
        self.current_entry: ScoreEntry | None = None
        self.plan: PlaybackPlan | None = None
        self.target_hwnd = 0
        self.current_note_text = "等待音符"
        self._waiting_for_foreground = False
        self._editors: list[ScoreEditorWindow] = []

        self.signals = _UiSignals(self)
        self.signals.toggle_requested.connect(self.toggle_playback)
        self.signals.stop_requested.connect(self.emergency_stop)
        self.signals.state_changed.connect(self._on_state_changed)
        self.signals.event_emitted.connect(self._on_event)
        self.signals.playback_error.connect(self._on_playback_error)

        self.backend = WindowsSendInputBackend()
        self.player = TimelinePlayer(
            self.backend,
            on_state_change=lambda state: self.signals.state_changed.emit(state.value),
            on_event=lambda event, _position: self.signals.event_emitted.emit(event),
            on_error=lambda error: self.signals.playback_error.emit(str(error)),
        )
        self.countdown_overlay = CountdownOverlay()
        self.playback_overlay = PlaybackOverlay()
        self.hotkeys = GlobalHotkeyListener(
            on_toggle=self.signals.toggle_requested.emit,
            on_stop=self.signals.stop_requested.emit,
        )

        self._build_ui()
        self._build_menu()
        self._refresh_library()

        self.focus_timer = QTimer(self)
        self.focus_timer.setInterval(120)
        self.focus_timer.timeout.connect(self._check_foreground)
        self.focus_timer.start()
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(50)
        self.ui_timer.timeout.connect(self._refresh_progress)
        self.ui_timer.start()
        QTimer.singleShot(0, self._start_hotkeys)

    def _build_ui(self) -> None:
        """创建左侧歌单和右侧播放预览的极简布局。"""

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 22, 28, 16)
        root.setSpacing(0)

        header = QHBoxLayout()
        brand = QLabel("KeyScore")
        brand.setStyleSheet("font-size: 19px; font-weight: 600;")
        shortcut_hint = QLabel("F9  播放 / 暂停    F10  停止")
        shortcut_hint.setObjectName("muted")
        settings_button = QPushButton("设置")
        settings_button.clicked.connect(self._show_settings)
        header.addWidget(brand)
        header.addStretch()
        header.addWidget(shortcut_hint)
        header.addSpacing(12)
        header.addWidget(settings_button)
        root.addLayout(header)
        root.addSpacing(26)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_playlist())
        splitter.addWidget(self._build_preview())
        splitter.setSizes([230, 690])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)
        root.addWidget(self._build_controls())
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪：选择曲谱后在游戏前台按 F9")

    def _build_playlist(self) -> QWidget:
        """
        创建歌单、新建和导入控制。

        Returns:
            QWidget: 歌单面板。
        """

        panel = QWidget()
        panel.setMinimumWidth(190)
        panel.setMaximumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 20, 0)
        heading = QLabel("曲谱")
        heading.setStyleSheet("font-size: 13px; color: #8E9298;")
        self.playlist = QListWidget()
        self.playlist.currentItemChanged.connect(self._on_playlist_selection)
        self.playlist.itemDoubleClicked.connect(lambda _item: self._edit_current())
        actions = QHBoxLayout()
        new_button = QPushButton("新建")
        new_button.clicked.connect(self._new_score)
        import_button = QPushButton("导入")
        import_button.clicked.connect(self._import_score)
        actions.addWidget(new_button)
        actions.addWidget(import_button)
        actions.addStretch()
        layout.addWidget(heading)
        layout.addSpacing(8)
        layout.addWidget(self.playlist, 1)
        layout.addLayout(actions)
        return panel

    def _build_preview(self) -> QWidget:
        """
        创建当前曲谱的只读预览和编辑入口。

        Returns:
            QWidget: 曲谱预览面板。
        """

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(30, 0, 0, 0)
        title_row = QHBoxLayout()
        self.score_title = QLabel("未选择曲谱")
        self.score_title.setStyleSheet("font-size: 24px; font-weight: 500;")
        self.edit_button = QPushButton("编辑")
        self.edit_button.clicked.connect(self._edit_current)
        self.edit_button.setEnabled(False)
        title_row.addWidget(self.score_title)
        title_row.addStretch()
        title_row.addWidget(self.edit_button)
        self.score_meta = QLabel("")
        self.score_meta.setObjectName("muted")
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("从左侧选择曲谱")
        layout.addLayout(title_row)
        layout.addWidget(self.score_meta)
        layout.addWidget(self.preview, 1)
        return panel

    def _build_controls(self) -> QWidget:
        """
        创建进度、播放和停止控制。

        Returns:
            QWidget: 底部控制面板。
        """

        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(250, 12, 0, 0)
        info = QVBoxLayout()
        self.now_playing = QLabel("尚未播放")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        info.addWidget(self.now_playing)
        info.addWidget(self.progress)
        self.play_button = QPushButton("播放", objectName="primary")
        self.play_button.clicked.connect(self.toggle_playback)
        self.stop_button = QPushButton("停止")
        self.stop_button.clicked.connect(self.emergency_stop)
        layout.addLayout(info, 1)
        layout.addSpacing(18)
        layout.addWidget(self.play_button)
        layout.addWidget(self.stop_button)
        return panel

    def _build_menu(self) -> None:
        """创建新建、导入、编辑和设置菜单。"""

        menu = self.menuBar().addMenu("文件")
        new_action = QAction("新建曲谱", self)
        new_action.triggered.connect(self._new_score)
        import_action = QAction("导入曲谱…", self)
        import_action.triggered.connect(self._import_score)
        edit_action = QAction("编辑当前曲谱", self)
        edit_action.triggered.connect(self._edit_current)
        menu.addActions((new_action, import_action, edit_action))

    def _start_hotkeys(self) -> None:
        """启动全局 F9/F10 监听器。"""

        if not self.hotkeys.start():
            self.statusBar().showMessage("未安装 pynput：全局 F9/F10 暂不可用")

    def _refresh_library(self, select_path: Path | None = None) -> None:
        """
        重新扫描歌单并可选中指定文件。

        Args:
            select_path (Path | None): 刷新后应选中的文件。
        """

        previous_path = select_path or (self.current_entry.path if self.current_entry else None)
        self.playlist.blockSignals(True)
        self.playlist.clear()
        selected_row = 0
        for row, entry in enumerate(self.library.entries()):
            item = QListWidgetItem(entry.title)
            item.setData(Qt.ItemDataRole.UserRole, str(entry.path))
            self.playlist.addItem(item)
            if previous_path is not None and entry.path.resolve() == previous_path.resolve():
                selected_row = row
        self.playlist.blockSignals(False)
        if self.playlist.count():
            self.playlist.setCurrentRow(selected_row)

    def _on_playlist_selection(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        """
        加载用户在歌单中选中的曲谱。

        Args:
            current (QListWidgetItem | None): 当前条目。
            _previous (QListWidgetItem | None): 上一条目。
        """

        if current is None:
            self.current_entry = None
            self.preview.clear()
            self.edit_button.setEnabled(False)
            return
        path = Path(str(current.data(Qt.ItemDataRole.UserRole)))
        try:
            text = path.read_text(encoding="utf-8")
            score = parse_score(text)
        except (OSError, UnicodeError, ScoreParseError) as exc:
            self.current_entry = ScoreEntry(current.text(), path)
            self.score_title.setText(current.text())
            self.score_meta.setText(str(exc))
            self.preview.setPlainText(text if "text" in locals() else "")
            self.edit_button.setEnabled(True)
            return
        self.current_entry = ScoreEntry(score.title, path)
        self.score_title.setText(score.title)
        self.score_meta.setText(f"{score.bpm} BPM   ·   {float(score.total_beats):g} 拍   ·   {len(score.notes)} 个音符")
        self.preview.setPlainText(text)
        self.edit_button.setEnabled(True)

    @Slot()
    def toggle_playback(self) -> None:
        """根据当前状态开始、暂停或继续当前曲谱。"""

        if self.player.state is PlaybackState.PLAYING:
            self.player.pause()
            return
        if self.player.state is PlaybackState.PAUSED:
            if self.target_hwnd and is_foreground(self.target_hwnd):
                self.player.play()
            else:
                self.statusBar().showMessage("请切回开始播放时的窗口，再按 F9 继续")
            return
        if self._waiting_for_foreground:
            return
        if self.current_entry is None:
            self.statusBar().showMessage("请先在歌单中选择曲谱")
            return
        try:
            score = parse_score(self.current_entry.path.read_text(encoding="utf-8"))
            self.plan = compile_score(score, self.profile)
            self.player.load(self.plan)
        except (OSError, UnicodeError, ScoreParseError, PlanCompileError, RuntimeError) as exc:
            QMessageBox.warning(self, "无法播放", str(exc))
            return

        current = foreground_window()
        if current and current != int(self.winId()):
            self._remember_foreground_and_countdown(current)
        else:
            self._waiting_for_foreground = True
            self.countdown_overlay.show_waiting(self.plan.title)
            self.statusBar().showMessage("请切换到游戏窗口")

    @Slot()
    def emergency_stop(self) -> None:
        """取消等待或倒计时，停止播放并释放全部按键。"""

        self._waiting_for_foreground = False
        self.countdown_overlay.cancel()
        self.player.stop()
        self.playback_overlay.hide()
        self.progress.setValue(0)
        self.now_playing.setText("已停止")
        self.statusBar().showMessage("已停止并释放所有按键")

    def _remember_foreground_and_countdown(self, hwnd: int) -> None:
        """
        记住按下 F9 时的前台窗口并开始倒计时。

        Args:
            hwnd (int): 当时的前台窗口句柄。
        """

        if self.plan is None:
            return
        self._waiting_for_foreground = False
        self.target_hwnd = hwnd
        self.statusBar().showMessage("前台保护已启用，正在准备播放")
        self.countdown_overlay.start_countdown(self.plan.title, self._begin_after_countdown)

    def _begin_after_countdown(self) -> None:
        """倒计时结束后再次验证前台窗口并开始播放。"""

        if self.plan is None:
            return
        if not is_foreground(self.target_hwnd):
            self._waiting_for_foreground = True
            self.countdown_overlay.show_waiting(self.plan.title)
            return
        self.current_note_text = "等待第一个音符"
        self.playback_overlay.begin(self.plan.title, self.plan.bpm)
        self.now_playing.setText(self.plan.title)
        self.player.play()

    def _check_foreground(self) -> None:
        """检测等待中的前台窗口或播放时的焦点变化。"""

        if self._waiting_for_foreground and self.plan is not None:
            current = foreground_window()
            if current and current != int(self.winId()):
                self._remember_foreground_and_countdown(current)
            return
        if self.player.state is PlaybackState.PLAYING and not is_foreground(self.target_hwnd):
            self.player.pause()
            self.statusBar().showMessage("前台窗口已切换，播放已暂停并释放按键")

    def _refresh_progress(self) -> None:
        """刷新主窗口和悬浮条中的播放进度。"""

        if self.plan is None or self.plan.duration_ms <= 0:
            return
        ratio = min(1.0, self.player.position_ms / self.plan.duration_ms)
        self.progress.setValue(int(ratio * 1000))
        paused = self.player.state is PlaybackState.PAUSED
        if self.playback_overlay.isVisible():
            self.playback_overlay.update_playback(ratio, self.current_note_text, paused)

    def _new_score(self) -> None:
        """在曲谱库中创建新曲谱并打开独立编辑窗口。"""

        try:
            entry = self.library.create_score()
        except OSError as exc:
            QMessageBox.warning(self, "新建失败", str(exc))
            return
        self._refresh_library(entry.path)
        self._open_editor(entry.path)

    def _import_score(self) -> None:
        """将外部文本曲谱复制到歌单中。"""

        filename, _ = QFileDialog.getOpenFileName(self, "导入曲谱", "", "文本简谱 (*.txt)")
        if not filename:
            return
        try:
            entry = self.library.import_score(Path(filename))
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        self._refresh_library(entry.path)
        self.statusBar().showMessage(f"已导入：{entry.title}")

    def _edit_current(self) -> None:
        """在独立窗口中打开当前曲谱。"""

        if self.current_entry is None:
            return
        self._open_editor(self.current_entry.path)

    def _open_editor(self, path: Path) -> None:
        """
        创建独立曲谱编辑窗口。

        Args:
            path (Path): 待编辑曲谱路径。
        """

        try:
            editor = ScoreEditorWindow(path, self)
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(self, "打开失败", str(exc))
            return
        self._editors.append(editor)
        editor.saved.connect(lambda saved_path: self._refresh_library(Path(saved_path)))
        editor.destroyed.connect(lambda _object=None, value=editor: self._forget_editor(value))
        editor.show()

    def _forget_editor(self, editor: ScoreEditorWindow) -> None:
        """
        从活动编辑窗口列表中移除已关闭窗口。

        Args:
            editor (ScoreEditorWindow): 已关闭编辑窗口。
        """

        if editor in self._editors:
            self._editors.remove(editor)

    def _show_settings(self) -> None:
        """显示可录入全部音符与音区按键的设置对话框。"""

        dialog = QDialog(self)
        dialog.setWindowTitle("设置")
        dialog.resize(520, 560)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(16)
        heading = QLabel("按键映射")
        heading.setStyleSheet("font-size: 18px; font-weight: 600;")
        hint = QLabel("中音不按修饰键。点击按钮可重新录入键盘或鼠标按键。")
        hint.setObjectName("muted")
        layout.addWidget(heading)
        layout.addWidget(hint)

        note_bindings: dict[int, Binding] = dict(self.profile.note_bindings)
        zone_bindings: dict[Octave, Binding] = dict(self.profile.zone_bindings)
        semitone_binding = self.profile.semitone_binding
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)

        def request_binding() -> Binding | None:
            """
            录入新的键盘或鼠标绑定。

            Returns:
                Binding | None: 用户录入的绑定，取消时返回 `None`。
            """

            return capture_binding(dialog)

        def record_note(degree: int, button: QPushButton) -> None:
            """
            录入并替换指定音符的绑定。

            Args:
                degree (int): 1～8 音符度数。
                button (QPushButton): 需要刷新文字的按钮。
            """

            binding = request_binding()
            if binding is not None:
                note_bindings[degree] = binding
                button.setText(binding.label)

        for index, (degree, name) in enumerate(
            enumerate(("Do", "Re", "Mi", "Fa", "Sol", "La", "Si", "高音 Do"), start=1)
        ):
            label = QLabel(f"{degree}  {name}")
            button = QPushButton(note_bindings[degree].label, objectName="binding")
            button.clicked.connect(
                lambda _checked=False, value=degree, target=button: record_note(value, target)
            )
            grid.addWidget(label, index, 0)
            grid.addWidget(button, index, 1)

        def record_zone(octave: Octave, button: QPushButton) -> None:
            """
            录入并替换指定音区的绑定。

            Args:
                octave (Octave): 待设置音区。
                button (QPushButton): 需要刷新文字的按钮。
            """

            binding = request_binding()
            if binding is not None:
                zone_bindings[octave] = binding
                button.setText(binding.label)

        row = 8
        for octave, label_text in (
            (Octave.LOW, "低音"),
            (Octave.HIGH, "高音"),
        ):
            label = QLabel(label_text)
            button = QPushButton(zone_bindings[octave].label, objectName="binding")
            button.clicked.connect(
                lambda _checked=False, value=octave, target=button: record_zone(value, target)
            )
            grid.addWidget(label, row, 0)
            grid.addWidget(button, row, 1)
            row += 1

        semitone_button = QPushButton(semitone_binding.label, objectName="binding")

        def record_semitone() -> None:
            """录入并刷新半音修饰键。"""

            nonlocal semitone_binding
            binding = request_binding()
            if binding is not None:
                semitone_binding = binding
                semitone_button.setText(binding.label)

        semitone_button.clicked.connect(record_semitone)
        grid.addWidget(QLabel("半音"), row, 0)
        grid.addWidget(semitone_button, row, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        options = QFormLayout()
        hold_spin = QSpinBox()
        hold_spin.setRange(10, 500)
        hold_spin.setSuffix(" ms")
        hold_spin.setValue(self.profile.key_hold_ms)
        gap_spin = QSpinBox()
        gap_spin.setRange(0, 200)
        gap_spin.setSuffix(" ms")
        gap_spin.setValue(self.profile.key_gap_ms)
        options.addRow("按键时长", hold_spin)
        options.addRow("最小释放间隔", gap_spin)
        layout.addLayout(options)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        self.hotkeys.stop()
        result = dialog.exec()
        self.hotkeys.start()
        if result != QDialog.DialogCode.Accepted:
            return
        self.profile.note_bindings = note_bindings
        self.profile.zone_bindings = zone_bindings
        self.profile.semitone_binding = semitone_binding
        self.profile.key_hold_ms = hold_spin.value()
        self.profile.key_gap_ms = gap_spin.value()
        try:
            save_profile(self.profile, self.profile_path)
        except OSError as exc:
            QMessageBox.warning(self, "设置保存失败", str(exc))

    def _on_state_changed(self, value: str) -> None:
        """
        根据播放器状态更新播放按钮。

        Args:
            value (str): PlaybackState 字符串值。
        """

        state = PlaybackState(value)
        if state is PlaybackState.PLAYING:
            self.play_button.setText("暂停")
        elif state is PlaybackState.PAUSED:
            self.play_button.setText("继续")
        elif state is PlaybackState.STOPPED:
            self.play_button.setText("播放")
            self.playback_overlay.hide()

    def _on_event(self, event: object) -> None:
        """
        在音符按下时更新悬浮层当前音符。

        Args:
            event (object): 播放线程传入的输入事件。
        """

        if not isinstance(event, TimedInputEvent):
            return
        if event.note is None or event.action is not ActionType.PRESS:
            return
        octave_text = {Octave.LOW: "低音", Octave.MIDDLE: "中音", Octave.HIGH: "高音"}
        self.current_note_text = f"{octave_text[event.note.octave]} {event.note.degree}"

    def _on_playback_error(self, message: str) -> None:
        """
        显示播放线程中的输入异常。

        Args:
            message (str): 异常文本。
        """

        QMessageBox.critical(self, "播放失败", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        关闭应用前停止播放、快捷键和悬浮层。

        Args:
            event (QCloseEvent): Qt 关闭事件。
        """

        self.hotkeys.stop()
        self.countdown_overlay.cancel()
        self.playback_overlay.hide()
        self.player.stop(wait=True)
        event.accept()
