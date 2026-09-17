"""键谱的极简歌单与播放主窗口。"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
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
from .models import (
    ActionType,
    Binding,
    MappingMode,
    NoteEvent,
    NoteOutputMode,
    Octave,
    PlaybackPlan,
    TimedInputEvent,
    note_binding_key,
)
from .overlay import CountdownOverlay, PlaybackOverlay
from .parser import ScoreParseError, parse_score
from .playback import PlaybackState, TimelinePlayer
from .profile_store import (
    import_profile,
    list_profile_paths,
    load_active_profile,
    load_profile,
    profile_path_for_name,
    save_active_profile,
    save_profile,
    save_profile_with_name,
)


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
QComboBox, QLineEdit, QSpinBox {
    background: #171819; color: #ECEDEE; border: 1px solid #303236;
    border-radius: 5px; padding: 7px 9px;
}
QComboBox QLineEdit {
    background: transparent; color: #ECEDEE; border: none; padding: 0;
}
QComboBox QAbstractItemView {
    background: #171819; color: #ECEDEE; border: 1px solid #303236;
    selection-background-color: #292C2F;
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
        self.profiles_directory = self.data_directory / "profiles"
        self.profile_state_path = self.data_directory / "profile_state.json"
        self.profile_path = self._initialize_profiles()
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
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(170)
        self.profile_combo.setEditable(True)
        profile_line_edit = self.profile_combo.lineEdit()
        if profile_line_edit is not None:
            profile_line_edit.setReadOnly(True)
            profile_line_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.profile_combo.setPlaceholderText("选择配置方案")
        self._refresh_profile_combo()
        self.profile_combo.currentIndexChanged.connect(self._select_profile)
        settings_button = QPushButton("设置")
        settings_button.clicked.connect(self._show_settings)
        header.addWidget(brand)
        header.addStretch()
        header.addWidget(shortcut_hint)
        header.addSpacing(12)
        header.addWidget(self.profile_combo)
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
        delete_button = QPushButton("删除")
        delete_button.clicked.connect(self._delete_current_score)
        actions.addWidget(new_button)
        actions.addWidget(import_button)
        actions.addWidget(delete_button)
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
        delete_action = QAction("删除当前曲谱", self)
        delete_action.triggered.connect(self._delete_current_score)
        new_profile_action = QAction("新建配置方案…", self)
        new_profile_action.triggered.connect(self._new_profile)
        import_profile_action = QAction("导入配置方案…", self)
        import_profile_action.triggered.connect(self._import_profile)
        menu.addActions((new_action, import_action, edit_action, delete_action))
        menu.addSeparator()
        menu.addActions((new_profile_action, import_profile_action))

    def _initialize_profiles(self) -> Path:
        """初始化 Profile 目录，并兼容迁移早期单文件配置。"""

        paths = list_profile_paths(self.profiles_directory)
        if paths:
            active_path = load_active_profile(self.profiles_directory, self.profile_state_path)
            return active_path or paths[0]
        legacy_path = self.data_directory / "profile.json"
        profile = load_profile(legacy_path)
        path = profile_path_for_name(self.profiles_directory, profile.name)
        save_profile(profile, path)
        save_active_profile(path, self.profile_state_path)
        return path

    def _refresh_profile_combo(self) -> None:
        """扫描 Profile 文件并刷新顶部方案选择器。"""

        current_path = getattr(self, "profile_path", None)
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        selected_index = 0
        for index, path in enumerate(list_profile_paths(self.profiles_directory)):
            profile = load_profile(path)
            self.profile_combo.addItem(profile.name, str(path))
            if current_path is not None and path.resolve() == current_path.resolve():
                selected_index = index
        self.profile_combo.setCurrentIndex(selected_index)
        if self.profile_combo.count():
            self.profile_combo.setEditText(self.profile_combo.itemText(selected_index))
        self.profile_combo.blockSignals(False)
        if self.profile_combo.count():
            self._select_profile(self.profile_combo.currentIndex(), show_status=False)

    def _select_profile(self, index: int, show_status: bool = True) -> None:
        """切换当前用于编译和播放的独立配置方案。"""

        if index < 0:
            return
        path_text = self.profile_combo.itemData(index)
        if not isinstance(path_text, str):
            return
        if show_status:
            self._discard_playback_plan()
        self.profile_path = Path(path_text)
        self.profile = load_profile(self.profile_path)
        try:
            save_active_profile(self.profile_path, self.profile_state_path)
        except OSError:
            if show_status:
                self.statusBar().showMessage("配置已切换，但无法保存当前方案状态")
        self.profile_combo.setToolTip(
            f"当前配置：{self.profile.name}\n映射模式：{self.profile.mapping_mode.value}"
        )
        if show_status:
            self.statusBar().showMessage(f"已切换配置方案：{self.profile.name}")

    def _discard_playback_plan(self) -> None:
        """停止当前播放并清除使用旧 Profile 编译的时间轴。"""

        self._waiting_for_foreground = False
        self.countdown_overlay.cancel()
        self.player.stop(wait=True)
        self.playback_overlay.hide()
        self.plan = None
        self.target_hwnd = 0
        self.progress.setValue(0)
        self.now_playing.setText("尚未播放")

    def _new_profile(self) -> None:
        """从当前 Profile 复制创建一份独立的个人配置方案。"""

        from PySide6.QtWidgets import QInputDialog

        name, accepted = QInputDialog.getText(self, "新建配置方案", "方案名称：")
        if not accepted or not name.strip():
            return
        path = profile_path_for_name(self.profiles_directory, name)
        if path.exists():
            QMessageBox.warning(self, "无法新建", "同名配置方案已存在")
            return
        self._discard_playback_plan()
        self.profile.name = name.strip()
        try:
            save_profile(self.profile, path)
        except OSError as exc:
            QMessageBox.warning(self, "新建失败", str(exc))
            return
        self.profile_path = path
        self._refresh_profile_combo()
        self.statusBar().showMessage(f"已新建并切换配置方案：{self.profile.name}")

    def _import_profile(self) -> None:
        """导入外部 Profile，并立即显示和切换到该配置方案。"""

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "导入配置方案",
            "",
            "KeyScore 配置方案 (*.ksprofile.json)",
        )
        if not filename:
            return
        self._discard_playback_plan()
        try:
            path = import_profile(Path(filename), self.profiles_directory)
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.warning(self, "导入配置失败", str(exc))
            return
        self.profile_path = path
        self._refresh_profile_combo()
        self.statusBar().showMessage(f"已导入并切换配置方案：{self.profile.name}")

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

    def _delete_current_score(self) -> None:
        """在用户确认后删除当前选中的本地曲谱。"""

        if self.current_entry is None:
            self.statusBar().showMessage("请先选择要删除的曲谱")
            return
        result = QMessageBox.question(
            self,
            "删除曲谱？",
            f"确定删除《{self.current_entry.title}》吗？此操作无法撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        entry = self.current_entry
        self.emergency_stop()
        try:
            self.library.delete_score(entry)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "删除失败", str(exc))
            return
        self.current_entry = None
        self.score_title.setText("未选择曲谱")
        self.score_meta.setText("")
        self.preview.clear()
        self.edit_button.setEnabled(False)
        self._refresh_library()
        self.statusBar().showMessage(f"已删除：{entry.title}")

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
        """按当前映射模式显示并保存该 Profile 的键位配置。"""

        dialog = QDialog(self)
        dialog.setWindowTitle(f"配置方案 · {self.profile.name}")
        dialog.resize(560, 650)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(26, 24, 26, 20)
        heading = QLabel("按键映射")
        heading.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(heading)
        name_edit = QLineEdit(self.profile.name)
        name_edit.setPlaceholderText("输入配置方案名称")
        name_form = QFormLayout()
        name_form.addRow("方案名称", name_edit)
        layout.addLayout(name_form)
        mode_combo = QComboBox()
        mode_names = {
            MappingMode.DEGREE_MODIFIER: "音级 + 按住修饰键",
            MappingMode.DIRECT_NOTE: "每个音符直接映射",
            MappingMode.ROW_OCTAVE: "三行音区直接映射",
        }
        for mode, label in mode_names.items():
            mode_combo.addItem(label, mode.value)
        mode_combo.setCurrentIndex(list(mode_names).index(self.profile.mapping_mode))
        layout.addWidget(mode_combo)
        hint = QLabel()
        hint.setObjectName("muted")
        layout.addWidget(hint)

        note_bindings = dict(self.profile.note_bindings)
        zone_bindings = dict(self.profile.zone_bindings)
        semitone_binding = self.profile.semitone_binding
        direct_bindings = dict(self.profile.direct_note_bindings)
        mapping_box = QWidget()
        mapping_layout = QVBoxLayout(mapping_box)
        mapping_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(mapping_box, 1)

        def request_binding() -> Binding | None:
            """打开按键捕获窗口并返回用户录入的绑定。"""

            return capture_binding(dialog)

        def create_binding_button(
            binding: Binding | None,
            save: object,
            prefix: str = "",
        ) -> QPushButton:
            """创建一个可捕获并保存键位的按钮。"""

            def button_text(value: Binding | None) -> str:
                """生成包含可选音级前缀的按钮文字。"""

                label = value.label if value else "未设置"
                return f"{prefix}\n{label}" if prefix else label

            button = QPushButton(button_text(binding), objectName="binding")

            def record() -> None:
                """录入当前按钮对应的键位。"""

                captured = request_binding()
                if captured is not None:
                    save(captured)
                    button.setText(button_text(captured))

            button.clicked.connect(record)
            return button

        def add_binding_row(grid: QGridLayout, row: int, label_text: str, binding: Binding | None, save: object) -> None:
            """为映射网格加入一个可重新录入的按键按钮。"""

            grid.addWidget(QLabel(label_text), row, 0)
            grid.addWidget(create_binding_button(binding, save), row, 1)

        def clear_mapping_layout(target: QLayout) -> None:
            """递归移除切换映射模式后遗留的控件和子布局。"""

            while target.count():
                item = target.takeAt(0)
                widget = item.widget()
                child_layout = item.layout()
                if widget is not None:
                    widget.deleteLater()
                elif child_layout is not None:
                    clear_mapping_layout(child_layout)
                    child_layout.deleteLater()

        def rebuild_mapping() -> None:
            """根据所选模式重建映射编辑区。"""

            clear_mapping_layout(mapping_layout)
            mode_value = mode_combo.currentData()
            try:
                mode = MappingMode(str(mode_value))
            except ValueError:
                return
            if mode is MappingMode.DEGREE_MODIFIER:
                hint.setText("适合三角洲等布局：中音无修饰，低/高音和半音按住修饰键。")
                grid = QGridLayout()
                names = ("Do", "Re", "Mi", "Fa", "Sol", "La", "Si")
                for row, name in enumerate(names):
                    degree = row + 1
                    add_binding_row(
                        grid, row, f"{degree}  {name}", note_bindings.get(degree),
                        lambda value, item=degree: note_bindings.__setitem__(item, value),
                    )
                row = len(names)
                for octave, label_text in ((Octave.LOW, "低音修饰"), (Octave.HIGH, "高音修饰")):
                    add_binding_row(
                        grid, row, label_text, zone_bindings.get(octave),
                        lambda value, item=octave: zone_bindings.__setitem__(item, value),
                    )
                    row += 1
                add_binding_row(
                    grid, row, "半音修饰", semitone_binding,
                    lambda value: setattr_holder(value),
                )
                grid.setColumnStretch(1, 1)
                mapping_layout.addLayout(grid)
                return

            if mode is MappingMode.ROW_OCTAVE:
                hint.setText("低、中、高三个音区各一行，每行按 1～7 直接映射，不使用半音行。")
                grid = QGridLayout()
                grid.setHorizontalSpacing(6)
                for row, (octave, octave_label) in enumerate(
                    ((Octave.LOW, "低音"), (Octave.MIDDLE, "中音"), (Octave.HIGH, "高音"))
                ):
                    grid.addWidget(QLabel(octave_label), row, 0)
                    for degree in range(1, 8):
                        note = NoteEvent(Fraction(0), Fraction(1), degree, octave, False)
                        key = note_binding_key(note)
                        button = create_binding_button(
                            direct_bindings.get(key),
                            lambda value, item=key: direct_bindings.__setitem__(item, value),
                            str(degree),
                        )
                        grid.addWidget(button, row, degree)
                mapping_layout.addLayout(grid)
                mapping_layout.addStretch()
                return

            hint.setText("低、中、高音的自然音与半音分别成行，每个音符可独立绑定。")
            grid = QGridLayout()
            grid.setHorizontalSpacing(6)
            row = 0
            for octave, octave_label in ((Octave.LOW, "低"), (Octave.MIDDLE, "中"), (Octave.HIGH, "高")):
                for is_semitone, prefix in ((False, ""), (True, "#")):
                    grid.addWidget(QLabel(f"{prefix}{octave_label}音"), row, 0)
                    for degree in range(1, 8):
                        note = NoteEvent(Fraction(0), Fraction(1), degree, octave, is_semitone)
                        key = note_binding_key(note)
                        button = create_binding_button(
                            direct_bindings.get(key),
                            lambda value, item=key: direct_bindings.__setitem__(item, value),
                            str(degree),
                        )
                        grid.addWidget(button, row, degree)
                    row += 1
            mapping_layout.addLayout(grid)

        def setattr_holder(value: Binding) -> None:
            """保存半音修饰键的闭包赋值。"""

            nonlocal semitone_binding
            semitone_binding = value

        mode_combo.currentIndexChanged.connect(rebuild_mapping)
        rebuild_mapping()

        options = QFormLayout()
        output_mode_combo = QComboBox()
        output_mode_combo.addItem("短按触发（推荐）", NoteOutputMode.TAP.value)
        output_mode_combo.addItem("持续按住", NoteOutputMode.HOLD.value)
        output_mode_index = output_mode_combo.findData(self.profile.note_output_mode.value)
        output_mode_combo.setCurrentIndex(max(0, output_mode_index))
        hold_spin = QSpinBox()
        hold_spin.setRange(10, 500)
        hold_spin.setSuffix(" ms")
        hold_spin.setValue(self.profile.key_hold_ms)
        gap_spin = QSpinBox()
        gap_spin.setRange(0, 200)
        gap_spin.setSuffix(" ms")
        gap_spin.setValue(self.profile.key_gap_ms)
        options.addRow("音符输出方式", output_mode_combo)
        options.addRow("按键时长", hold_spin)
        options.addRow("最小释放间隔", gap_spin)
        layout.addLayout(options)

        def update_hold_control() -> None:
            """根据输出方式启用或禁用固定按键时长。"""

            is_tap = output_mode_combo.currentData() == NoteOutputMode.TAP.value
            hold_spin.setEnabled(is_tap)
            hold_spin.setToolTip(
                "短按触发时使用固定按键时长"
                if is_tap
                else "持续按住模式由曲谱音符时值决定按键时长"
            )

        output_mode_combo.currentIndexChanged.connect(update_hold_control)
        update_hold_control()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")

        def update_save_button(text: str) -> None:
            """根据方案名称是否变化提示保存或另存为。"""

            save_button.setText("保存" if text.strip() == self.profile.name else "另存为新方案")

        name_edit.textChanged.connect(update_save_button)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        self.hotkeys.stop()
        result = dialog.exec()
        self.hotkeys.start()
        if result != QDialog.DialogCode.Accepted:
            return
        self._discard_playback_plan()
        self.profile.note_bindings = note_bindings
        self.profile.zone_bindings = zone_bindings
        self.profile.semitone_binding = semitone_binding
        try:
            self.profile.mapping_mode = MappingMode(str(mode_combo.currentData()))
            self.profile.note_output_mode = NoteOutputMode(
                str(output_mode_combo.currentData())
            )
        except ValueError:
            QMessageBox.warning(self, "设置保存失败", "未知的映射或音符输出模式")
            return
        self.profile.direct_note_bindings = direct_bindings
        self.profile.key_hold_ms = hold_spin.value()
        self.profile.key_gap_ms = gap_spin.value()
        try:
            self.profile_path = save_profile_with_name(
                self.profile,
                self.profile_path,
                self.profiles_directory,
                name_edit.text(),
            )
            self._refresh_profile_combo()
            self.statusBar().showMessage(f"当前配置已保存并生效：{self.profile.name}")
        except (OSError, ValueError) as exc:
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
