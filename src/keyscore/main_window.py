"""键谱的三页导航、曲谱与播放主窗口。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .app_settings import AppSettings, ThemeId, save_app_settings
from .compiler import PlanCompileError, compile_score
from .editor_window import ScoreEditorWindow
from .foreground import foreground_window, is_foreground
from .hotkeys import GlobalHotkeyListener
from .input_backend import WindowsSendInputBackend
from .library import ScoreEntry, ScoreLibrary, default_data_directory
from .models import (
    ActionType,
    GameProfile,
    Octave,
    PlaybackPlan,
    TimedInputEvent,
)
from .overlay import CountdownOverlay, PlaybackOverlay
from .parser import ScoreParseError, parse_score
from .playback import PlaybackState, TimelinePlayer
from .profile_page import ProfileMappingPage
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
from .theme import THEME_LABELS, ThemeManager


class _UiSignals(QObject):
    """将快捷键和播放工作线程回调转发到 Qt 主线程。"""

    toggle_requested = Signal()
    stop_requested = Signal()
    state_changed = Signal(str)
    event_emitted = Signal(object)
    playback_error = Signal(str)


class MainWindow(QMainWindow):
    """提供曲谱歌单、播放预览、按键映射和前台安全保护。"""

    def __init__(self, theme_manager: ThemeManager, app_settings_path: Path) -> None:
        """
        初始化曲谱库、持久化配置、播放器和界面。

        Args:
            theme_manager (ThemeManager): 全局主题管理器。
            app_settings_path (Path): 应用级设置文件路径。
        """

        super().__init__()
        self.setWindowTitle("KeyScore 键谱")
        self.resize(1120, 720)
        self.setMinimumSize(860, 580)
        self.theme_manager = theme_manager
        self.app_settings_path = app_settings_path

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
        """创建固定顶部栏、左侧导航和三页工作区。"""

        central = QWidget(objectName="centralPanel")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        sidebar = QWidget(objectName="sidebar")
        sidebar.setFixedWidth(168)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 18, 12, 14)
        sidebar_layout.setSpacing(8)
        self.navigation_buttons: list[QPushButton] = []
        for index, text in enumerate(("曲谱", "按键映射", "设置")):
            button = QPushButton(text, objectName="navigation")
            button.setProperty("active", index == 0)
            button.clicked.connect(lambda _checked=False, page=index: self._switch_page(page))
            sidebar_layout.addWidget(button)
            self.navigation_buttons.append(button)
        sidebar_layout.addStretch()
        version = QLabel("KeyScore v1.0\n用键盘，奏响你的音乐", objectName="muted")
        sidebar_layout.addWidget(version)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_score_page())
        self.profile_page = ProfileMappingPage()
        self.profile_page.save_requested.connect(self._save_profile_changes)
        self.profile_page.new_requested.connect(self._new_profile)
        self.profile_page.import_requested.connect(self._import_profile)
        self.pages.addWidget(self.profile_page)
        self.pages.addWidget(self._build_settings_page())
        body.addWidget(sidebar)
        body.addWidget(self.pages, 1)
        root.addLayout(body, 1)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪：选择曲谱后在游戏前台按 F9")
        self._refresh_profile_combo()

    def _build_header(self) -> QWidget:
        """
        创建应用级播放控制和 Profile 选择栏。

        Returns:
            QWidget: 顶部控制栏。
        """

        header_widget = QWidget(objectName="topBar")
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(20, 12, 20, 12)
        header.setSpacing(8)
        brand = QLabel("KeyScore")
        brand.setObjectName("brand")
        previous_button = QPushButton("上一首")
        previous_button.clicked.connect(self._previous_score)
        self.header_play_button = QPushButton("播放", objectName="primary")
        self.header_play_button.clicked.connect(self.toggle_playback)
        header_stop_button = QPushButton("停止")
        header_stop_button.clicked.connect(self.emergency_stop)
        next_button = QPushButton("下一首")
        next_button.clicked.connect(self._next_score)
        shortcut_hint = QLabel("F9  播放 / 暂停    F10  停止")
        shortcut_hint.setObjectName("muted")
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(190)
        self.profile_combo.setEditable(True)
        profile_line_edit = self.profile_combo.lineEdit()
        if profile_line_edit is not None:
            profile_line_edit.setReadOnly(True)
            profile_line_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.profile_combo.setPlaceholderText("选择配置方案")
        self.profile_combo.currentIndexChanged.connect(self._select_profile)
        header.addWidget(brand)
        header.addStretch()
        header.addWidget(previous_button)
        header.addWidget(self.header_play_button)
        header.addWidget(header_stop_button)
        header.addWidget(next_button)
        header.addSpacing(10)
        header.addWidget(shortcut_hint)
        header.addSpacing(12)
        header.addWidget(self.profile_combo)
        return header_widget

    def _build_score_page(self) -> QWidget:
        """
        创建曲谱管理、预览和播放状态合并页面。

        Returns:
            QWidget: 曲谱页面。
        """

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)
        heading_row = QHBoxLayout()
        heading_box = QVBoxLayout()
        heading_box.addWidget(QLabel("曲谱", objectName="displayTitle"))
        heading_box.addWidget(QLabel("管理、预览、编辑和播放本地曲谱", objectName="muted"))
        import_button = QPushButton("导入")
        import_button.clicked.connect(self._import_score)
        new_button = QPushButton("新建曲谱", objectName="primary")
        new_button.clicked.connect(self._new_score)
        heading_row.addLayout(heading_box)
        heading_row.addStretch()
        heading_row.addWidget(import_button)
        heading_row.addWidget(new_button)
        layout.addLayout(heading_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_playlist())
        splitter.addWidget(self._build_preview())
        splitter.setSizes([250, 650])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        return page

    def _build_playlist(self) -> QWidget:
        """
        创建歌单、新建和导入控制。

        Returns:
            QWidget: 歌单面板。
        """

        panel = QWidget(objectName="pageCard")
        panel.setMinimumWidth(190)
        panel.setMaximumWidth(330)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 12)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索曲谱…")
        self.search_edit.textChanged.connect(self._filter_playlist)
        self.playlist = QListWidget()
        self.playlist.currentItemChanged.connect(self._on_playlist_selection)
        self.playlist.itemDoubleClicked.connect(lambda _item: self._edit_current())
        actions = QHBoxLayout()
        delete_button = QPushButton("删除")
        delete_button.clicked.connect(self._delete_current_score)
        actions.addWidget(delete_button)
        actions.addStretch()
        layout.addWidget(self.search_edit)
        layout.addWidget(self.playlist, 1)
        layout.addLayout(actions)
        return panel

    def _build_preview(self) -> QWidget:
        """
        创建当前曲谱的只读预览和编辑入口。

        Returns:
            QWidget: 曲谱预览面板。
        """

        panel = QWidget(objectName="pageCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 14)
        title_row = QHBoxLayout()
        self.score_title = QLabel("未选择曲谱")
        self.score_title.setObjectName("displayTitle")
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
        layout.addWidget(self._build_controls())
        return panel

    def _build_controls(self) -> QWidget:
        """
        创建进度、播放和停止控制。

        Returns:
            QWidget: 底部控制面板。
        """

        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 10, 0, 0)
        info = QVBoxLayout()
        self.now_playing = QLabel("尚未播放")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        info.addWidget(self.now_playing)
        info.addWidget(self.progress)
        self.play_button = QPushButton("播放", objectName="primary")
        self.play_button.clicked.connect(self.toggle_playback)
        self.play_buttons = [self.header_play_button, self.play_button]
        self.stop_button = QPushButton("停止")
        self.stop_button.clicked.connect(self.emergency_stop)
        layout.addLayout(info, 1)
        layout.addSpacing(18)
        layout.addWidget(self.play_button)
        layout.addWidget(self.stop_button)
        return panel

    def _build_settings_page(self) -> QWidget:
        """
        创建只包含应用级选项的设置页面。

        Returns:
            QWidget: 全局设置页面。
        """

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)
        layout.addWidget(QLabel("设置", objectName="displayTitle"))
        layout.addWidget(QLabel("管理不随按键配置方案变化的全局选项", objectName="muted"))
        card = QWidget(objectName="pageCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)
        card_layout.addWidget(QLabel("外观", objectName="sectionLabel"))
        theme_row = QHBoxLayout()
        theme_description = QVBoxLayout()
        theme_description.addWidget(QLabel("界面风格"))
        theme_description.addWidget(
            QLabel("应用到主窗口、编辑器、对话框和播放悬浮层", objectName="muted")
        )
        self.theme_combo = QComboBox()
        self.theme_combo.setMinimumWidth(230)
        for theme, label in THEME_LABELS.items():
            self.theme_combo.addItem(label, theme.value)
        self.theme_combo.setCurrentIndex(
            max(0, self.theme_combo.findData(self.theme_manager.current.value))
        )
        self.theme_combo.currentIndexChanged.connect(self._apply_selected_theme)
        theme_row.addLayout(theme_description, 1)
        theme_row.addWidget(self.theme_combo)
        card_layout.addLayout(theme_row)
        card_layout.addSpacing(12)
        card_layout.addWidget(QLabel("数据", objectName="sectionLabel"))
        data_label = QLabel(f"应用数据目录\n{self.data_directory}", objectName="muted")
        data_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(data_label)
        card_layout.addStretch()
        layout.addWidget(card, 1)
        return page

    def _build_menu(self) -> None:
        """创建曲谱与配置方案的文件菜单。"""

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
        """
        切换当前用于编译和播放的独立配置方案。

        Args:
            index (int): 顶部 Profile 下拉框索引。
            show_status (bool): 是否显示切换状态并处理未保存提示。
        """

        if index < 0:
            return
        path_text = self.profile_combo.itemData(index)
        if not isinstance(path_text, str):
            return
        selected_path = Path(path_text)
        current_path = getattr(self, "profile_path", None)
        if (
            show_status
            and current_path is not None
            and selected_path.resolve() != current_path.resolve()
            and self.profile_page.has_unsaved_changes
        ):
            result = QMessageBox.question(
                self,
                "放弃方案修改？",
                "当前按键映射存在未保存修改，是否放弃并切换配置方案？",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if result != QMessageBox.StandardButton.Discard:
                previous_index = self.profile_combo.findData(str(current_path))
                self.profile_combo.blockSignals(True)
                self.profile_combo.setCurrentIndex(previous_index)
                self.profile_combo.blockSignals(False)
                return
        if show_status:
            self._discard_playback_plan()
        self.profile_path = selected_path
        self.profile = load_profile(self.profile_path)
        try:
            save_active_profile(self.profile_path, self.profile_state_path)
        except OSError:
            if show_status:
                self.statusBar().showMessage("配置已切换，但无法保存当前方案状态")
        self.profile_combo.setToolTip(
            f"当前配置：{self.profile.name}\n映射模式：{self.profile.mapping_mode.value}"
        )
        self.profile_page.load_profile(self.profile)
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

        if not self._confirm_discard_profile_changes():
            return
        name, accepted = QInputDialog.getText(self, "新建配置方案", "方案名称：")
        if not accepted or not name.strip():
            return
        path = profile_path_for_name(self.profiles_directory, name)
        if path.exists():
            QMessageBox.warning(self, "无法新建", "同名配置方案已存在")
            return
        self._discard_playback_plan()
        new_profile = deepcopy(self.profile)
        new_profile.name = name.strip()
        try:
            save_profile(new_profile, path)
        except OSError as exc:
            QMessageBox.warning(self, "新建失败", str(exc))
            return
        self.profile_path = path
        self.profile = new_profile
        self._refresh_profile_combo()
        self.statusBar().showMessage(f"已新建并切换配置方案：{self.profile.name}")

    def _import_profile(self) -> None:
        """导入外部 Profile，并立即显示和切换到该配置方案。"""

        if not self._confirm_discard_profile_changes():
            return
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

    def _confirm_discard_profile_changes(self) -> bool:
        """
        在离开当前 Profile 草稿前确认是否放弃修改。

        Returns:
            bool: 没有未保存修改或用户确认放弃时为 `True`。
        """

        if not self.profile_page.has_unsaved_changes:
            return True
        result = QMessageBox.question(
            self,
            "放弃方案修改？",
            "当前按键映射存在未保存修改，是否放弃这些修改？",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return result == QMessageBox.StandardButton.Discard

    def _switch_page(self, index: int) -> None:
        """
        切换主工作区页面并更新侧栏选中态。

        Args:
            index (int): 页面索引，依次为曲谱、按键映射和设置。
        """

        if not 0 <= index < self.pages.count():
            return
        self.pages.setCurrentIndex(index)
        for button_index, button in enumerate(self.navigation_buttons):
            button.setProperty("active", button_index == index)
            style = button.style()
            style.unpolish(button)
            style.polish(button)
            button.update()

    def _previous_score(self) -> None:
        """选择歌单中的上一首曲谱。"""

        count = self.playlist.count()
        if count == 0:
            return
        current = self.playlist.currentRow()
        self.playlist.setCurrentRow(max(0, current - 1))
        self._switch_page(0)

    def _next_score(self) -> None:
        """选择歌单中的下一首曲谱。"""

        count = self.playlist.count()
        if count == 0:
            return
        current = self.playlist.currentRow()
        self.playlist.setCurrentRow(min(count - 1, current + 1))
        self._switch_page(0)

    def _filter_playlist(self, query: str) -> None:
        """
        按曲名过滤歌单条目。

        Args:
            query (str): 搜索框内容。
        """

        normalized_query = query.strip().casefold()
        for row in range(self.playlist.count()):
            item = self.playlist.item(row)
            item.setHidden(normalized_query not in item.text().casefold())

    def _apply_selected_theme(self, _index: int) -> None:
        """
        即时应用并持久化设置页选择的全局主题。

        Args:
            _index (int): 主题下拉框索引。
        """

        try:
            theme = ThemeId(str(self.theme_combo.currentData()))
        except ValueError:
            theme = ThemeId.FLUENT
        self.theme_manager.apply(theme)
        try:
            save_app_settings(AppSettings(theme=theme), self.app_settings_path)
        except OSError as exc:
            QMessageBox.warning(self, "主题保存失败", f"主题已临时生效，但无法保存：{exc}")
            return
        self.statusBar().showMessage(f"界面风格已切换为：{THEME_LABELS[theme]}")

    def _save_profile_changes(self, profile: object, name: str) -> None:
        """
        保存按键映射页面提交的 Profile 草稿。

        Args:
            profile (object): 页面提交的 Profile 草稿。
            name (str): 用户输入的方案名称。
        """

        if not isinstance(profile, GameProfile):
            QMessageBox.warning(self, "保存失败", "配置方案数据无效")
            return
        self._discard_playback_plan()
        try:
            saved_path = save_profile_with_name(
                profile,
                self.profile_path,
                self.profiles_directory,
                name,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.profile = profile
        self.profile.name = name.strip()
        self.profile_path = saved_path
        self._refresh_profile_combo()
        self.profile_page.mark_saved(self.profile)
        self.statusBar().showMessage(f"当前配置已保存并生效：{self.profile.name}")

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
        self._filter_playlist(self.search_edit.text())
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
        if (
            self.current_entry is not None
            and path.resolve() != self.current_entry.path.resolve()
            and (self.player.state is not PlaybackState.STOPPED or self._waiting_for_foreground)
        ):
            self.emergency_stop()
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

    def _on_state_changed(self, value: str) -> None:
        """
        根据播放器状态更新播放按钮。

        Args:
            value (str): PlaybackState 字符串值。
        """

        state = PlaybackState(value)
        if state is PlaybackState.PLAYING:
            for button in self.play_buttons:
                button.setText("暂停")
        elif state is PlaybackState.PAUSED:
            for button in self.play_buttons:
                button.setText("继续")
        elif state is PlaybackState.STOPPED:
            for button in self.play_buttons:
                button.setText("播放")
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

        if not self._confirm_discard_profile_changes():
            event.ignore()
            return
        self.hotkeys.stop()
        self.countdown_overlay.cancel()
        self.playback_overlay.hide()
        self.player.stop(wait=True)
        event.accept()
