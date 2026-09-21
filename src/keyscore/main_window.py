"""键谱的主导航、曲谱与播放主窗口。"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import time

from PySide6.QtCore import (
    QCollator,
    QEvent,
    QLocale,
    QObject,
    QPoint,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QCloseEvent, QColor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QKeySequenceEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .app_settings import (
    AppSettings,
    ThemeId,
    load_app_settings,
    normalize_duration,
    save_app_settings,
)
from . import __version__
from .compiler import PlanCompileError, compile_score
from .editor_window import ScoreEditorWindow
from .foreground import foreground_window, is_foreground
from .hotkeys import (
    GlobalHotkeyListener,
    HotkeyValidationError,
    hotkey_scan_code,
    normalize_hotkey,
)
from .input_backend import WindowsSendInputBackend
from .library import ScoreEntry, ScoreLibrary, default_data_directory
from .midi_import import import_midi
from .models import (
    ActionType,
    BindingKind,
    GameProfile,
    Octave,
    PlaybackPlan,
    TimedInputEvent,
)
from .overlay import CountdownOverlay, PlaybackOverlay, RecordingOverlay
from .parser import ScoreParseError, parse_score
from .piano_roll import PianoRollEditor
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
from .recording.decoder import (
    DecodedNoteStart,
    RecordingDecodeError,
    recording_profile_conflicts,
    recording_reserved_shortcuts,
)
from .recording.dialogs import RecordingReviewDialog, RecordingSetupDialog
from .recording.input_capture import GlobalInputCapture
from .recording.models import PhysicalInputEvent, RecordingSettings
from .recording.session import RecordingSession
from .recording.transcriber import transcribe_take
from .score_document import document_from_score, pitch_from_note, serialize_document
from .theme import THEME_LABELS, ThemeManager
from .window_chrome import (
    FramelessMainWindow,
    ProfileSelector,
    RoundedShell,
    SmoothComboBox,
    SmoothSpinBox,
    WindowTitleBar,
    painted_icon,
)


class _UiSignals(QObject):
    """将快捷键和播放工作线程回调转发到 Qt 主线程。"""

    toggle_requested = Signal()
    stop_requested = Signal()
    state_changed = Signal(str)
    event_emitted = Signal(object)
    playback_error = Signal(str)
    record_requested = Signal()
    recording_input = Signal(object)
    recording_error = Signal(str)


class MainWindow(FramelessMainWindow):
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
        self.resize(1180, 870)
        self.setMinimumSize(890, 620)
        self.theme_manager = theme_manager
        self.app_settings_path = app_settings_path
        self.app_settings = load_app_settings(app_settings_path)
        self.score_title_collator = QCollator(
            QLocale(QLocale.Language.Chinese, QLocale.Country.China)
        )
        self.score_title_collator.setCaseSensitivity(
            Qt.CaseSensitivity.CaseInsensitive
        )
        self.score_title_collator.setNumericMode(True)

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
        self._record_waiting_for_foreground = False
        self._record_ready = False
        self._record_paused = False
        self.recording_session: RecordingSession | None = None
        self.recording_settings: RecordingSettings | None = None
        self._editors: list[ScoreEditorWindow] = []

        self.signals = _UiSignals(self)
        self.signals.toggle_requested.connect(self.toggle_playback)
        self.signals.stop_requested.connect(self.emergency_stop)
        self.signals.state_changed.connect(self._on_state_changed)
        self.signals.event_emitted.connect(self._on_event)
        self.signals.playback_error.connect(self._on_playback_error)
        self.signals.record_requested.connect(self.toggle_recording)
        self.signals.recording_input.connect(self._on_recording_input)
        self.signals.recording_error.connect(self._on_recording_error)

        self.backend = WindowsSendInputBackend()
        self.player = TimelinePlayer(
            self.backend,
            on_state_change=lambda state: self.signals.state_changed.emit(state.value),
            on_event=lambda event, _position: self.signals.event_emitted.emit(event),
            on_error=lambda error: self.signals.playback_error.emit(str(error)),
        )
        self.countdown_overlay = CountdownOverlay()
        self.playback_overlay = PlaybackOverlay()
        self.recording_overlay = RecordingOverlay()
        self.input_capture = GlobalInputCapture(
            on_event=self.signals.recording_input.emit,
            on_error=self.signals.recording_error.emit,
        )
        self.hotkeys = GlobalHotkeyListener(
            on_toggle=self.signals.toggle_requested.emit,
            on_stop=self.signals.stop_requested.emit,
            on_record=self.signals.record_requested.emit,
            play_hotkey=self.app_settings.play_hotkey,
            stop_hotkey=self.app_settings.stop_hotkey,
            record_hotkey=self.app_settings.record_hotkey,
        )

        self._build_ui()
        self.maximized_changed.connect(self._sync_window_shell)
        self._refresh_library()

        self.focus_timer = QTimer(self)
        self.focus_timer.setInterval(120)
        self.focus_timer.timeout.connect(self._check_foreground)
        self.focus_timer.start()
        self.ui_timer = QTimer(self)
        self.ui_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.ui_timer.setInterval(33)
        self.ui_timer.timeout.connect(self._refresh_progress)
        self.ui_timer.start()
        QTimer.singleShot(0, self._start_hotkeys)

    def _build_ui(self) -> None:
        """创建固定顶部栏、左侧导航和四页工作区。"""

        window_root = QWidget(objectName="windowRoot")
        self.window_root_layout = QVBoxLayout(window_root)
        self.window_root_layout.setContentsMargins(12, 12, 12, 12)
        self.window_root_layout.setSpacing(0)

        self.app_shell = RoundedShell()
        self.app_shell.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.window_shadow = QGraphicsDropShadowEffect(self)
        self.window_shadow.setBlurRadius(34)
        self.window_shadow.setOffset(0, 5)
        self.window_shadow.setColor(QColor(42, 91, 145, 76))
        self.app_shell.setGraphicsEffect(self.window_shadow)
        root = QVBoxLayout(self.app_shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.title_bar = WindowTitleBar("KeyScore", "用键盘，奏响你的音乐")
        root.addWidget(self.title_bar)
        root.addWidget(self._build_header())

        body_widget = QWidget(objectName="centralPanel")
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body_widget.setLayout(body)
        self.body_widget = body_widget
        sidebar = QWidget(objectName="sidebar")
        sidebar.setFixedWidth(86)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 18, 14, 14)
        sidebar_layout.setSpacing(10)
        self.navigation_buttons: list[QToolButton] = []
        navigation_items = (
            ("music", "曲谱"),
            ("keyboard", "按键映射"),
            ("settings", "设置"),
            ("info", "关于"),
        )
        for index, (icon, label) in enumerate(navigation_items):
            button = QToolButton(objectName="navigation")
            button.setText(label)
            button.setIcon(painted_icon(icon))
            button.setIconSize(QSize(28, 28))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setAccessibleName(label)
            button.setFixedSize(58, 58)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setProperty("active", index == 0)
            button.clicked.connect(lambda _checked=False, page=index: self._switch_page(page))
            button.installEventFilter(self)
            sidebar_layout.addWidget(button)
            self.navigation_buttons.append(button)
        sidebar_layout.addStretch()
        version = QLabel(
            f"v{__version__}",
            objectName="sidebarVersion",
        )
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(version)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_score_page())
        self.profile_page = ProfileMappingPage()
        self.profile_page.save_requested.connect(self._save_profile_changes)
        self.profile_page.new_requested.connect(self._new_profile)
        self.profile_page.delete_requested.connect(self._delete_profile)
        self.profile_page.import_requested.connect(self._import_profile)
        self.pages.addWidget(self.profile_page)
        self.pages.addWidget(self._build_settings_page())
        self.pages.addWidget(self._build_about_page())
        body.addWidget(sidebar)
        body.addWidget(self.pages, 1)
        self.navigation_hint = QLabel(body_widget, objectName="navigationHint")
        self.navigation_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.navigation_hint.hide()
        root.addWidget(body_widget, 1)
        self.app_status_bar = QStatusBar(objectName="appStatusBar")
        self.app_status_bar.setSizeGripEnabled(False)
        root.addWidget(self.app_status_bar)
        self.window_root_layout.addWidget(self.app_shell)
        self.setCentralWidget(window_root)
        self._refresh_hotkey_labels()
        self.statusBar().showMessage(
            f"就绪：{self.app_settings.record_hotkey} 录制游戏演奏，"
            f"{self.app_settings.play_hotkey} 播放当前曲谱"
        )
        self._refresh_profile_combo()

    def statusBar(self) -> QStatusBar:
        """
        返回嵌入圆角窗口外壳的状态栏。

        Returns:
            QStatusBar: 主窗口底部状态栏。
        """

        if hasattr(self, "app_status_bar"):
            return self.app_status_bar
        return super().statusBar()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """
        为导航图标和排序按钮显示应用内圆角文字提示。

        Args:
            watched (QObject): 当前接收事件的对象。
            event (QEvent): Qt 事件。

        Returns:
            bool: 事件是否已经被处理。
        """

        is_navigation_button = (
            hasattr(self, "navigation_buttons")
            and watched in self.navigation_buttons
        )
        is_sort_button = (
            hasattr(self, "score_sort_button")
            and watched is self.score_sort_button
        )
        if (is_navigation_button or is_sort_button) and hasattr(
            self, "navigation_hint"
        ):
            if event.type() is QEvent.Type.Enter:
                button = watched
                if isinstance(button, QToolButton):
                    hint_text = (
                        button.text()
                        if is_navigation_button
                        else str(button.property("hoverHint") or "")
                    )
                    self.navigation_hint.setText(hint_text)
                    self.navigation_hint.adjustSize()
                    if is_navigation_button:
                        position = button.mapTo(
                            self.body_widget,
                            QPoint(
                                button.width() + 10,
                                (button.height() - self.navigation_hint.height()) // 2,
                            ),
                        )
                    else:
                        position = button.mapTo(
                            self.body_widget,
                            QPoint(
                                button.width() - self.navigation_hint.width(),
                                button.height() + 8,
                            ),
                        )
                        position.setX(
                            max(
                                8,
                                min(
                                    position.x(),
                                    self.body_widget.width()
                                    - self.navigation_hint.width()
                                    - 8,
                                ),
                            )
                        )
                    self.navigation_hint.move(position)
                    self.navigation_hint.raise_()
                    self.navigation_hint.show()
            elif event.type() is QEvent.Type.Leave:
                self.navigation_hint.hide()
        return super().eventFilter(watched, event)

    def _sync_window_shell(self, maximized: bool) -> None:
        """
        根据最大化状态调整外边距、阴影和标题栏按钮。

        Args:
            maximized (bool): 窗口当前是否已最大化。
        """

        margin = 0 if maximized else 12
        self.window_root_layout.setContentsMargins(margin, margin, margin, margin)
        self.window_shadow.setEnabled(not maximized)
        self.app_shell.set_corner_radius(0.0 if maximized else 24.0)
        self.app_shell.setProperty("maximized", maximized)
        style = self.app_shell.style()
        style.unpolish(self.app_shell)
        style.polish(self.app_shell)
        self.title_bar.update_maximize_state(maximized)

    def _build_header(self) -> QWidget:
        """
        创建应用级播放控制和 Profile 选择栏。

        Returns:
            QWidget: 顶部控制栏。
        """

        header_widget = QWidget(objectName="commandBar")
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(104, 8, 22, 12)
        header.setSpacing(10)
        previous_button = QPushButton("上一首")
        previous_button.setIcon(painted_icon("previous", 24))
        previous_button.clicked.connect(self._previous_score)
        self.header_play_button = QPushButton("播放", objectName="primary")
        self.header_play_button.setIcon(painted_icon("play", 24))
        self.header_play_button.clicked.connect(self.toggle_playback)
        self.header_stop_button = QPushButton("停止")
        self.header_stop_button.setIcon(painted_icon("stop", 24))
        self.header_stop_button.clicked.connect(self.emergency_stop)
        next_button = QPushButton("下一首")
        next_button.setIcon(painted_icon("next", 24))
        next_button.clicked.connect(self._next_score)
        self.header_record_button = QPushButton("录制")
        self.header_record_button.setIcon(painted_icon("record", 24))
        self.header_record_button.setObjectName("record")
        self.header_record_button.clicked.connect(self.toggle_recording)
        self.shortcut_hint = QLabel()
        self.shortcut_hint.setObjectName("muted")
        self.shortcut_hint.hide()
        self.profile_combo = ProfileSelector()
        self.profile_combo.setPlaceholderText("选择配置方案")
        self.profile_combo.currentIndexChanged.connect(self._select_profile)
        header.addStretch()
        header.addWidget(previous_button)
        header.addWidget(self.header_play_button)
        header.addWidget(self.header_stop_button)
        header.addWidget(next_button)
        header.addWidget(self.header_record_button)
        divider = QLabel("│", objectName="commandDivider")
        header.addWidget(divider)
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
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(18)
        heading_row = QHBoxLayout()
        heading_box = QVBoxLayout()
        heading_box.addWidget(QLabel("曲谱", objectName="displayTitle"))
        heading_box.addWidget(QLabel("管理、预览、编辑和播放本地曲谱", objectName="muted"))
        import_button = QPushButton("导入")
        import_button.setToolTip("导入 KeyScore 文本，或从 MIDI 提取主旋律")
        import_button.clicked.connect(self._import_score)
        self.delete_button = QPushButton("删除")
        self.delete_button.clicked.connect(self._delete_current_score)
        self.page_record_button = QPushButton("录制演奏")
        self.page_record_button.clicked.connect(self.toggle_recording)
        new_button = QPushButton("新建曲谱", objectName="primary")
        new_button.clicked.connect(self._new_score)
        heading_row.addLayout(heading_box)
        heading_row.addStretch()
        heading_row.addWidget(import_button)
        heading_row.addWidget(self.delete_button)
        heading_row.addWidget(self.page_record_button)
        heading_row.addWidget(new_button)
        self.record_buttons = [self.header_record_button, self.page_record_button]
        layout.addLayout(heading_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_playlist())
        splitter.addWidget(self._build_preview())
        splitter.setSizes([250, 650])
        splitter.setHandleWidth(16)
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
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(350)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 12)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索曲谱…")
        self.search_edit.textChanged.connect(self._filter_playlist)
        self.score_sort_button = QToolButton(objectName="sortToggle")
        self.score_sort_button.setFixedSize(38, 38)
        self.score_sort_button.setIconSize(QSize(22, 22))
        self.score_sort_button.clicked.connect(self._toggle_score_sort)
        self.score_sort_button.installEventFilter(self)
        self._update_score_sort_button()
        self.playlist = QListWidget()
        self.playlist.currentItemChanged.connect(self._on_playlist_selection)
        self.playlist.itemDoubleClicked.connect(lambda _item: self._edit_current())
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.score_sort_button)
        layout.addLayout(search_row)
        layout.addWidget(self.playlist, 1)
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
        self.roll_preview = PianoRollEditor(editable=False)
        self.preview_tabs = QTabWidget()
        self.preview_tabs.setObjectName("previewTabs")
        self.preview_tabs.addTab(self.roll_preview, "卷帘")
        self.preview_tabs.addTab(self.preview, "文本")
        layout.addLayout(title_row)
        layout.addWidget(self.score_meta)
        layout.addWidget(self.preview_tabs, 1)
        return panel

    def _build_settings_page(self) -> QWidget:
        """
        创建带外观和快捷键二级分类的应用设置页面。

        Returns:
            QWidget: 全局设置页面。
        """

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)
        layout.addWidget(QLabel("设置", objectName="displayTitle"))
        layout.addWidget(
            QLabel("管理 KeyScore 的全局选项", objectName="muted")
        )

        settings_card = QWidget(objectName="pageCard")
        settings_layout = QHBoxLayout(settings_card)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(0)
        self.settings_categories = QListWidget()
        self.settings_categories.setObjectName("settingsCategories")
        self.settings_categories.setFixedWidth(170)
        self.settings_categories.setSpacing(3)
        self.settings_categories.addItems(("外观", "快捷键"))
        self.settings_categories.setCurrentRow(0)
        settings_layout.addWidget(self.settings_categories)

        self.settings_stack = QStackedWidget()
        self.settings_stack.addWidget(self._build_appearance_settings())
        self.settings_stack.addWidget(self._build_shortcut_settings())
        self.settings_categories.currentRowChanged.connect(
            self.settings_stack.setCurrentIndex
        )
        settings_layout.addWidget(self.settings_stack, 1)
        layout.addWidget(settings_card, 1)
        return page

    def _build_appearance_settings(self) -> QWidget:
        """
        创建外观分类内容。

        Returns:
            QWidget: 外观设置页面。
        """

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(24, 22, 24, 22)
        page_layout.setSpacing(14)
        page_layout.addWidget(QLabel("外观", objectName="dialogTitle"))
        page_layout.addWidget(
            QLabel("调整 KeyScore 的界面显示方式", objectName="muted")
        )
        card = QWidget(objectName="settingsSection")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(12)
        card_layout.addWidget(QLabel("界面风格", objectName="sectionLabel"))
        theme_row = QHBoxLayout()
        theme_description = QVBoxLayout()
        theme_description.addWidget(QLabel("主题"))
        theme_description.addWidget(
            QLabel("应用到主窗口、编辑器、对话框和播放悬浮层", objectName="muted")
        )
        self.theme_combo = SmoothComboBox()
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
        page_layout.addWidget(card)

        overlay_card = QWidget(objectName="settingsSection")
        overlay_layout = QGridLayout(overlay_card)
        overlay_layout.setContentsMargins(18, 16, 18, 16)
        overlay_layout.setHorizontalSpacing(24)
        overlay_layout.setVerticalSpacing(12)
        overlay_layout.addWidget(QLabel("悬浮层", objectName="sectionLabel"), 0, 0, 1, 2)
        overlay_layout.addWidget(QLabel("播放时显示曲名、进度和当前音符"), 1, 0)
        self.playback_overlay_check = QCheckBox("显示播放悬浮层")
        self.playback_overlay_check.setChecked(self.app_settings.show_playback_overlay)
        overlay_layout.addWidget(self.playback_overlay_check, 1, 1)
        overlay_layout.addWidget(QLabel("开始播放或录制前的准备时间"), 2, 0)
        self.countdown_seconds_spin = SmoothSpinBox()
        self.countdown_seconds_spin.setRange(1, 10)
        self.countdown_seconds_spin.setSuffix(" 秒")
        self.countdown_seconds_spin.setValue(self.app_settings.countdown_seconds)
        overlay_layout.addWidget(self.countdown_seconds_spin, 2, 1)
        overlay_layout.addWidget(QLabel("等待切换窗口及倒计时期间显示提示"), 3, 0)
        self.countdown_overlay_check = QCheckBox("显示倒计时悬浮提示")
        self.countdown_overlay_check.setChecked(self.app_settings.show_countdown_overlay)
        overlay_layout.addWidget(self.countdown_overlay_check, 3, 1)
        overlay_layout.setColumnStretch(0, 1)
        self.playback_overlay_check.toggled.connect(self._save_overlay_settings)
        self.countdown_seconds_spin.valueChanged.connect(self._save_overlay_settings)
        self.countdown_overlay_check.toggled.connect(self._save_overlay_settings)
        page_layout.addWidget(overlay_card)
        page_layout.addStretch()
        return page

    def _build_shortcut_settings(self) -> QWidget:
        """
        创建可编辑的全局快捷键分类。

        Returns:
            QWidget: 快捷键设置页面。
        """

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        layout.addWidget(QLabel("快捷键", objectName="dialogTitle"))
        layout.addWidget(
            QLabel("自定义全局控制快捷键和曲谱编辑器拍数", objectName="muted")
        )
        shortcuts = QWidget(objectName="settingsSection")
        shortcuts_layout = QGridLayout(shortcuts)
        shortcuts_layout.setContentsMargins(18, 16, 18, 16)
        shortcuts_layout.setHorizontalSpacing(16)
        shortcuts_layout.setVerticalSpacing(12)
        shortcuts_layout.addWidget(QLabel("全局控制快捷键", objectName="sectionLabel"), 0, 0, 1, 2)
        shortcuts_layout.addWidget(QLabel("功能", objectName="muted"), 1, 0)
        shortcuts_layout.addWidget(QLabel("快捷键", objectName="muted"), 1, 1)
        editors: list[QKeySequenceEdit] = []
        for row, (action, shortcut) in enumerate(
            (
                ("开始 / 完成录制", self.app_settings.record_hotkey),
                ("播放 / 暂停 / 继续", self.app_settings.play_hotkey),
                ("紧急停止", self.app_settings.stop_hotkey),
            ),
            start=2,
        ):
            shortcuts_layout.addWidget(QLabel(action), row, 0)
            editor = QKeySequenceEdit(QKeySequence(shortcut.replace("Win+", "Meta+")))
            editor.setObjectName("shortcutEditor")
            editor.setMaximumSequenceLength(1)
            editor.setMinimumSize(200, 38)
            editor.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            editors.append(editor)
            shortcuts_layout.addWidget(editor, row, 1)
        self.record_hotkey_edit, self.play_hotkey_edit, self.stop_hotkey_edit = editors
        shortcuts_layout.addWidget(
            QLabel("编辑器快捷键", objectName="sectionLabel"), 5, 0, 1, 2
        )
        shortcuts_layout.addWidget(QLabel("切换新音符拍数"), 6, 0)
        self.duration_hotkey_edit = QKeySequenceEdit(
            QKeySequence(self.app_settings.duration_cycle_hotkey.replace("Win+", "Meta+"))
        )
        self.duration_hotkey_edit.setObjectName("shortcutEditor")
        self.duration_hotkey_edit.setMaximumSequenceLength(1)
        self.duration_hotkey_edit.setMinimumSize(200, 38)
        shortcuts_layout.addWidget(self.duration_hotkey_edit, 6, 1)
        shortcuts_layout.addWidget(QLabel("反向切换新音符拍数"), 7, 0)
        self.duration_reverse_hotkey_edit = QKeySequenceEdit(
            QKeySequence(
                self.app_settings.duration_reverse_hotkey.replace("Win+", "Meta+")
            )
        )
        self.duration_reverse_hotkey_edit.setObjectName("shortcutEditor")
        self.duration_reverse_hotkey_edit.setMaximumSequenceLength(1)
        self.duration_reverse_hotkey_edit.setMinimumSize(200, 38)
        shortcuts_layout.addWidget(self.duration_reverse_hotkey_edit, 7, 1)
        shortcuts_layout.addWidget(QLabel("常用拍数"), 8, 0)
        self.duration_presets_edit = QLineEdit(
            ", ".join(self.app_settings.duration_presets)
        )
        self.duration_presets_edit.setPlaceholderText("例如：1/4, 1/2, 3/4, 1, 2, 4")
        self.duration_presets_edit.setToolTip("使用逗号分隔；列表顺序也是快捷键循环顺序")
        shortcuts_layout.addWidget(self.duration_presets_edit, 8, 1)
        shortcuts_layout.addWidget(QLabel("默认新音符拍数"), 9, 0)
        self.default_duration_edit = QLineEdit(self.app_settings.default_note_duration)
        self.default_duration_edit.setPlaceholderText("例如：1 或 3/4")
        shortcuts_layout.addWidget(self.default_duration_edit, 9, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        restore_button = QPushButton("恢复默认")
        restore_button.clicked.connect(self._restore_default_hotkeys)
        save_button = QPushButton("保存快捷键", objectName="primary")
        save_button.clicked.connect(self._save_hotkey_settings)
        buttons.addWidget(restore_button)
        buttons.addWidget(save_button)
        shortcuts_layout.addLayout(buttons, 10, 0, 1, 2)
        shortcut_hint = QLabel(
            "快捷键支持单键或 Ctrl / Alt / Shift / Win 组合；五项不能重复。"
            "拍数支持整数、小数和分数，使用逗号分隔。",
            objectName="muted",
        )
        shortcut_hint.setWordWrap(True)
        shortcuts_layout.addWidget(shortcut_hint, 11, 0, 1, 2)
        shortcuts_layout.setColumnStretch(0, 1)
        shortcuts_layout.setColumnStretch(1, 1)
        shortcuts_layout.setColumnMinimumWidth(1, 200)
        layout.addWidget(shortcuts)
        layout.addStretch()
        return page

    def _build_about_page(self) -> QWidget:
        """
        创建与设置同级的版本、相关网站和本地数据目录页面。

        Returns:
            QWidget: 关于页面。
        """

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)
        layout.addWidget(QLabel("关于", objectName="displayTitle"))
        layout.addWidget(QLabel("KeyScore 的版本、相关网站和数据目录", objectName="muted"))

        product = QWidget(objectName="settingsSection")
        product_layout = QVBoxLayout(product)
        product_layout.setContentsMargins(18, 16, 18, 16)
        product_layout.setSpacing(7)
        product_layout.addWidget(QLabel("KeyScore 键谱", objectName="dialogTitle"))
        product_layout.addWidget(QLabel(f"版本 {__version__}", objectName="muted"))
        product_layout.addWidget(
            QLabel(
                "面向 Windows 游戏乐器的曲谱编辑、自动演奏和游戏演奏录制工具。",
                objectName="muted",
            )
        )
        layout.addWidget(product)

        websites = QWidget(objectName="settingsSection")
        websites_layout = QVBoxLayout(websites)
        websites_layout.setContentsMargins(18, 16, 18, 16)
        websites_layout.setSpacing(10)
        websites_layout.addWidget(QLabel("相关网站", objectName="sectionLabel"))

        github_url = "https://github.com/ghkkdb/KeyScore"
        github_row = QHBoxLayout()
        github_label = QLabel(github_url, objectName="muted")
        github_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        github_label.setWordWrap(True)
        github_row.addWidget(github_label, 1)
        self.github_website_button = QPushButton("GitHub 项目主页 ↗")
        self.github_website_button.clicked.connect(
            lambda _checked=False: self._open_website(github_url)
        )
        github_row.addWidget(self.github_website_button)
        websites_layout.addLayout(github_row)

        bilibili_url = (
            "https://space.bilibili.com/417156717?spm_id_from=333.1007.0.0"
        )
        bilibili_row = QHBoxLayout()
        bilibili_label = QLabel(bilibili_url, objectName="muted")
        bilibili_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        bilibili_label.setWordWrap(True)
        bilibili_row.addWidget(bilibili_label, 1)
        self.bilibili_website_button = QPushButton("哔哩哔哩个人空间 ↗")
        self.bilibili_website_button.clicked.connect(
            lambda _checked=False: self._open_website(bilibili_url)
        )
        bilibili_row.addWidget(self.bilibili_website_button)
        websites_layout.addLayout(bilibili_row)
        layout.addWidget(websites)

        data = QWidget(objectName="settingsSection")
        data_layout = QVBoxLayout(data)
        data_layout.setContentsMargins(18, 16, 18, 16)
        data_layout.setSpacing(10)
        data_layout.addWidget(QLabel("应用数据目录", objectName="sectionLabel"))
        data_label = QLabel(str(self.data_directory), objectName="muted")
        data_label.setWordWrap(True)
        data_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        data_layout.addWidget(data_label)
        data_button_row = QHBoxLayout()
        data_button_row.addStretch()
        open_data_button = QPushButton("打开数据目录")
        open_data_button.clicked.connect(self._open_data_directory)
        data_button_row.addWidget(open_data_button)
        data_layout.addLayout(data_button_row)
        layout.addWidget(data)
        layout.addStretch()
        return page

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
        self.profile_page.delete_profile_button.setEnabled(
            self.profile_combo.count() > 1
        )
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

        if self.recording_session is not None:
            self._cancel_recording()
        self._waiting_for_foreground = False
        self.countdown_overlay.cancel()
        self.player.stop(wait=True)
        self.playback_overlay.hide()
        self.plan = None
        self.target_hwnd = 0

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

    def _delete_profile(self) -> None:
        """确认后删除当前配置方案，并切换到剩余方案。"""

        paths = list_profile_paths(self.profiles_directory)
        if len(paths) <= 1:
            QMessageBox.warning(self, "无法删除", "至少需要保留一个配置方案")
            return
        if not self._confirm_discard_profile_changes():
            return
        result = QMessageBox.question(
            self,
            "删除配置方案？",
            f"确定删除配置方案“{self.profile.name}”吗？此操作无法撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        target = self.profile_path.resolve()
        directory = self.profiles_directory.resolve()
        if target.parent != directory or target not in {path.resolve() for path in paths}:
            QMessageBox.warning(self, "删除失败", "当前配置方案不属于本地方案目录")
            return
        self._discard_playback_plan()
        try:
            self.profile_path.unlink()
        except OSError as exc:
            QMessageBox.warning(self, "删除失败", str(exc))
            return
        remaining = list_profile_paths(self.profiles_directory)
        self.profile_path = remaining[0]
        self.profile = load_profile(self.profile_path)
        try:
            save_active_profile(self.profile_path, self.profile_state_path)
        except OSError:
            pass
        self._refresh_profile_combo()
        self.statusBar().showMessage(
            f"配置方案已删除，已切换到：{self.profile.name}"
        )

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
            index (int): 页面索引，依次为曲谱、按键映射、设置和关于。
        """

        if not 0 <= index < self.pages.count():
            return
        self.pages.setCurrentIndex(index)
        for button_index, button in enumerate(self.navigation_buttons):
            active = button_index == index
            button.setChecked(active)
            button.setProperty("active", active)
            style = button.style()
            style.unpolish(button)
            style.polish(button)
            button.update()

    def _open_data_directory(self) -> None:
        """使用系统文件管理器打开 KeyScore 应用数据目录。"""

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.data_directory))):
            QMessageBox.warning(self, "无法打开目录", str(self.data_directory))

    def _open_website(self, url: str) -> None:
        """
        使用系统默认浏览器打开关于页中的网站。

        Args:
            url (str): 需要打开的 HTTPS 网址。
        """

        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(self, "无法打开网站", url)

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
        updated = replace(self.app_settings, theme=theme)
        try:
            save_app_settings(updated, self.app_settings_path)
        except OSError as exc:
            QMessageBox.warning(self, "主题保存失败", f"主题已临时生效，但无法保存：{exc}")
            return
        self.app_settings = updated
        self.statusBar().showMessage(f"界面风格已切换为：{THEME_LABELS[theme]}")

    def _save_overlay_settings(self, _value: object = None) -> None:
        """
        即时保存悬浮层显示选项和倒计时时长。

        Args:
            _value (object): Qt 控件信号携带但无需使用的值。
        """

        updated = replace(
            self.app_settings,
            show_playback_overlay=self.playback_overlay_check.isChecked(),
            countdown_seconds=self.countdown_seconds_spin.value(),
            show_countdown_overlay=self.countdown_overlay_check.isChecked(),
        )
        try:
            save_app_settings(updated, self.app_settings_path)
        except OSError as exc:
            QMessageBox.warning(self, "悬浮层设置保存失败", str(exc))
            return
        self.app_settings = updated
        if not updated.show_playback_overlay:
            self.playback_overlay.hide()
        elif self.plan is not None and self.player.state is not PlaybackState.STOPPED:
            self.playback_overlay.begin(self.plan.title, self.plan.bpm)
            ratio = (
                min(1.0, self.player.position_ms / self.plan.duration_ms)
                if self.plan.duration_ms > 0
                else 0.0
            )
            self.playback_overlay.update_playback(
                ratio,
                self.current_note_text,
                self.player.state is PlaybackState.PAUSED,
            )
        if not updated.show_countdown_overlay:
            self.countdown_overlay.hide()
        self.statusBar().showMessage("悬浮层设置已保存")

    def _hotkey_text(self, editor: QKeySequenceEdit) -> str:
        """
        读取并规范化快捷键编辑器中的单段组合键。

        Args:
            editor (QKeySequenceEdit): 待读取的快捷键编辑器。

        Returns:
            str: 规范化后的快捷键文本。

        Raises:
            HotkeyValidationError: 快捷键为空或包含不支持的按键时抛出。
        """

        text = editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        return normalize_hotkey(text)

    def _set_hotkey_editors(self, settings: AppSettings) -> None:
        """
        将应用设置中的快捷键和拍数预设回填到编辑器。

        Args:
            settings (AppSettings): 快捷键来源设置。
        """

        self.record_hotkey_edit.setKeySequence(
            QKeySequence(settings.record_hotkey.replace("Win+", "Meta+"))
        )
        self.play_hotkey_edit.setKeySequence(
            QKeySequence(settings.play_hotkey.replace("Win+", "Meta+"))
        )
        self.stop_hotkey_edit.setKeySequence(
            QKeySequence(settings.stop_hotkey.replace("Win+", "Meta+"))
        )
        self.duration_hotkey_edit.setKeySequence(
            QKeySequence(settings.duration_cycle_hotkey.replace("Win+", "Meta+"))
        )
        self.duration_reverse_hotkey_edit.setKeySequence(
            QKeySequence(settings.duration_reverse_hotkey.replace("Win+", "Meta+"))
        )
        self.duration_presets_edit.setText(", ".join(settings.duration_presets))
        self.default_duration_edit.setText(settings.default_note_duration)

    def _restore_default_hotkeys(self) -> None:
        """恢复并立即保存全部默认快捷键和编辑器拍数。"""

        defaults = AppSettings()
        self._set_hotkey_editors(defaults)
        self._save_hotkey_settings()

    def _save_hotkey_settings(self) -> None:
        """校验、注册并持久化全局快捷键和编辑器设置。"""

        previous = self.app_settings
        try:
            record_hotkey = self._hotkey_text(self.record_hotkey_edit)
            play_hotkey = self._hotkey_text(self.play_hotkey_edit)
            stop_hotkey = self._hotkey_text(self.stop_hotkey_edit)
            duration_hotkey = self._hotkey_text(self.duration_hotkey_edit)
            duration_reverse_hotkey = self._hotkey_text(
                self.duration_reverse_hotkey_edit
            )
            if len(
                {
                    record_hotkey,
                    play_hotkey,
                    stop_hotkey,
                    duration_hotkey,
                    duration_reverse_hotkey,
                }
            ) != 5:
                raise HotkeyValidationError("全局快捷键和编辑器快捷键不能重复")
            raw_presets = self.duration_presets_edit.text().replace("，", ",").split(",")
            duration_presets: list[str] = []
            for raw in raw_presets:
                if not raw.strip():
                    continue
                value = normalize_duration(raw)
                if value not in duration_presets:
                    duration_presets.append(value)
            if not duration_presets:
                raise ValueError("至少需要设置一个常用拍数")
            default_duration = normalize_duration(self.default_duration_edit.text())
            if default_duration not in duration_presets:
                raise ValueError("默认新音符拍数必须包含在常用拍数中")
        except (HotkeyValidationError, ValueError) as exc:
            QMessageBox.warning(self, "快捷键无效", str(exc))
            return

        if not self.hotkeys.configure(record_hotkey, play_hotkey, stop_hotkey):
            self.hotkeys.configure(
                previous.record_hotkey,
                previous.play_hotkey,
                previous.stop_hotkey,
            )
            self._set_hotkey_editors(previous)
            QMessageBox.warning(
                self,
                "快捷键注册失败",
                "至少一个快捷键已被其他程序占用，原快捷键已恢复。",
            )
            return

        updated = replace(
            previous,
            record_hotkey=record_hotkey,
            play_hotkey=play_hotkey,
            stop_hotkey=stop_hotkey,
            duration_cycle_hotkey=duration_hotkey,
            duration_reverse_hotkey=duration_reverse_hotkey,
            duration_presets=tuple(duration_presets),
            default_note_duration=default_duration,
        )
        try:
            save_app_settings(updated, self.app_settings_path)
        except OSError as exc:
            self.hotkeys.configure(
                previous.record_hotkey,
                previous.play_hotkey,
                previous.stop_hotkey,
            )
            self._set_hotkey_editors(previous)
            QMessageBox.warning(self, "快捷键保存失败", str(exc))
            return
        self.app_settings = updated
        self._set_hotkey_editors(updated)
        self._refresh_hotkey_labels()
        for editor in self._editors:
            editor.set_duration_settings(
                updated.duration_presets,
                updated.default_note_duration,
                updated.duration_cycle_hotkey,
                updated.duration_reverse_hotkey,
            )
        self.statusBar().showMessage("快捷键和编辑器拍数已保存并立即生效")

    def _refresh_hotkey_labels(self) -> None:
        """刷新主窗口和各悬浮层中的快捷键说明。"""

        settings = self.app_settings
        self.shortcut_hint.setText(
            f"{settings.record_hotkey} 录制    {settings.play_hotkey} 播放 / 暂停    "
            f"{settings.stop_hotkey} 停止"
        )
        self.header_play_button.setToolTip(f"播放 / 暂停（{settings.play_hotkey}）")
        self.header_record_button.setToolTip(f"开始 / 完成录制（{settings.record_hotkey}）")
        self.header_stop_button.setToolTip(f"紧急停止（{settings.stop_hotkey}）")
        self.countdown_overlay.set_shortcuts(
            settings.record_hotkey,
            settings.stop_hotkey,
        )
        self.playback_overlay.set_shortcuts(
            settings.play_hotkey,
            settings.stop_hotkey,
        )
        self.recording_overlay.set_shortcuts(
            settings.record_hotkey,
            settings.stop_hotkey,
        )

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
        """启动当前配置的三个全局快捷键监听器。"""

        if not self.hotkeys.start():
            self.statusBar().showMessage("全局快捷键注册失败，可能已被其他程序占用")

    def _reserved_hotkey_inputs(self) -> tuple[tuple[int, str], ...]:
        """
        返回录制时必须排除的全局快捷键主键扫描码。

        Returns:
            tuple[tuple[int, str], ...]: 非零扫描码与快捷键显示文本。
        """

        values = (
            self.app_settings.record_hotkey,
            self.app_settings.play_hotkey,
            self.app_settings.stop_hotkey,
        )
        return tuple(
            (scan_code, value)
            for value in values
            if (scan_code := hotkey_scan_code(value)) != 0
        )

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
        entries = list(self.library.entries())
        if self.app_settings.score_sort_mode == "modified":
            entries.sort(
                key=lambda entry: (
                    -entry.path.stat().st_mtime,
                    entry.title.casefold(),
                )
            )
        else:
            entries.sort(
                key=lambda entry: self.score_title_collator.sortKey(entry.title)
            )
        for row, entry in enumerate(entries):
            item = QListWidgetItem(entry.title)
            item.setData(Qt.ItemDataRole.UserRole, str(entry.path))
            self.playlist.addItem(item)
            if previous_path is not None and entry.path.resolve() == previous_path.resolve():
                selected_row = row
        self.playlist.blockSignals(False)
        self._filter_playlist(self.search_edit.text())
        if self.playlist.count():
            self.playlist.setCurrentRow(selected_row)

    def _toggle_score_sort(self) -> None:
        """切换、保存并立即应用曲谱列表排序方式。"""

        previous = self.app_settings
        mode = "title" if previous.score_sort_mode == "modified" else "modified"
        updated = replace(previous, score_sort_mode=mode)
        self.app_settings = updated
        try:
            save_app_settings(updated, self.app_settings_path)
        except OSError as exc:
            self.statusBar().showMessage(f"排序已应用，但无法保存设置：{exc}")
        self._update_score_sort_button()
        self._refresh_library()

    def _update_score_sort_button(self) -> None:
        """根据当前排序模式刷新图标、提示和无障碍名称。"""

        by_time = self.app_settings.score_sort_mode == "modified"
        current = (
            "按时间（最新优先）"
            if by_time
            else "按名称（英文/拼音 A-Z）"
        )
        target = "按名称（英文/拼音）" if by_time else "按时间"
        self.score_sort_button.setIcon(
            painted_icon("sort_time" if by_time else "sort_title", 24)
        )
        self.score_sort_button.setToolTip("")
        self.score_sort_button.setProperty(
            "hoverHint", f"当前：{current}\n点击切换为{target}"
        )
        self.score_sort_button.setAccessibleName(f"曲谱排序：{current}")

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
            self.roll_preview.set_score_document(None)
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
            self.roll_preview.set_score_document(None)
            self.preview_tabs.setCurrentWidget(self.preview)
            self.edit_button.setEnabled(True)
            return
        self.current_entry = ScoreEntry(score.title, path)
        self.score_title.setText(score.title)
        self.score_meta.setText(
            f"{score.bpm} BPM   ·   {float(score.total_beats):g} 拍   ·   "
            f"{len(score.notes)} 个音符"
        )
        self.preview.setPlainText(text)
        self.roll_preview.set_score_document(document_from_score(score))
        self.edit_button.setEnabled(True)

    @Slot()
    def toggle_recording(self) -> None:
        """开始新的游戏演奏录制，或完成当前录制并进入整理。"""

        if self.recording_session is not None:
            self._finish_recording()
            return
        conflicts = recording_profile_conflicts(self.profile)
        if conflicts:
            QMessageBox.warning(
                self,
                "无法开始录制",
                "当前配置存在无法反向判断的重复按键：\n" + "\n".join(conflicts),
            )
            return
        reserved = recording_reserved_shortcuts(
            self.profile,
            self._reserved_hotkey_inputs(),
        )
        if reserved:
            QMessageBox.warning(
                self,
                "无法开始录制",
                "当前配置占用了录制控制快捷键："
                + "、".join(reserved)
                + "。请先更换这些映射。",
            )
            return

        default_bpm = 100
        default_beat = "4/4"
        if self.current_entry is not None:
            try:
                current_score = parse_score(
                    self.current_entry.path.read_text(encoding="utf-8")
                )
                default_bpm = current_score.bpm
                default_beat = current_score.beat
            except (OSError, UnicodeError, ScoreParseError):
                pass
        dialog = RecordingSetupDialog(default_bpm, default_beat, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.emergency_stop()
        try:
            session = RecordingSession(self.profile)
        except RecordingDecodeError as exc:
            QMessageBox.warning(self, "无法开始录制", str(exc))
            return
        if not self.input_capture.start():
            QMessageBox.warning(
                self,
                "无法开始录制",
                "系统全局键鼠监听器启动失败，请检查运行权限后重试。",
            )
            return
        self.recording_session = session
        self.recording_settings = dialog.settings()
        self._record_waiting_for_foreground = True
        self._record_ready = False
        self._record_paused = False
        self.target_hwnd = 0
        self.profile_combo.setEnabled(False)
        for button in self.record_buttons:
            button.setText("完成录制")
        self.countdown_overlay.show_recording_waiting(
            self.app_settings.countdown_seconds,
            self.app_settings.show_countdown_overlay,
        )
        self.statusBar().showMessage("录制已准备，请切换到游戏窗口")

    def _begin_recording_after_countdown(self) -> None:
        """倒计时完成后验证游戏仍在前台，并进入事件录制状态。"""

        if self.recording_session is None:
            return
        if not is_foreground(self.target_hwnd):
            self._record_waiting_for_foreground = True
            self.countdown_overlay.show_recording_waiting(
                self.app_settings.countdown_seconds,
                self.app_settings.show_countdown_overlay,
            )
            return
        self._record_ready = True
        self._record_paused = False
        self.recording_overlay.begin()
        self.statusBar().showMessage(
            f"正在录制：{self.app_settings.record_hotkey} 完成，"
            f"{self.app_settings.stop_hotkey} 紧急停止"
        )

    @Slot(object)
    def _on_recording_input(self, value: object) -> None:
        """
        在 Qt 主线程中把全局物理事件交给录制会话。

        Args:
            value (object): 输入监听线程发来的事件。
        """

        if not isinstance(value, PhysicalInputEvent):
            return
        if (
            self.recording_session is None
            or not self._record_ready
            or self._record_paused
            or not is_foreground(self.target_hwnd)
        ):
            return
        reserved_codes = {code for code, _label in self._reserved_hotkey_inputs()}
        if (
            value.binding.kind is BindingKind.KEYBOARD
            and value.binding.code in reserved_codes
        ):
            return
        try:
            started = self.recording_session.feed(value)
        except RecordingDecodeError as exc:
            self._on_recording_error(str(exc))
            return
        if isinstance(started, DecodedNoteStart):
            prefix = {
                Octave.LOWEST: "倍低音 ",
                Octave.LOW: "低音 ",
                Octave.MIDDLE: "",
                Octave.HIGH: "高音 ",
                Octave.HIGHEST: "倍高音 ",
            }[started.octave]
            sharp = "#" if started.is_semitone else ""
            self.current_note_text = f"{sharp}{prefix}{started.degree}"

    @Slot(str)
    def _on_recording_error(self, message: str) -> None:
        """
        停止发生异常的录制并显示错误。

        Args:
            message (str): 输入监听或反向解码异常。
        """

        if self.recording_session is None:
            self.statusBar().showMessage(f"录制监听异常：{message}")
            return
        self._cancel_recording()
        QMessageBox.warning(self, "录制已停止", message)

    def _finish_recording(self) -> None:
        """停止捕获、生成曲谱，并打开录制整理对话框。"""

        session = self.recording_session
        settings = self.recording_settings
        if session is None or settings is None:
            return
        self._record_ready = False
        self.input_capture.stop()
        take = session.finish(time.perf_counter_ns() / 1_000_000.0)
        self._reset_recording_ui()
        if not take.notes:
            QMessageBox.information(self, "没有录制内容", "没有检测到当前配置中的有效音符。")
            return
        try:
            score_text = transcribe_take(take, settings, self.profile.note_output_mode)
        except ValueError as exc:
            QMessageBox.warning(self, "转谱失败", str(exc))
            return

        while True:
            review = RecordingReviewDialog(score_text, len(take.notes), self)
            if review.exec() != QDialog.DialogCode.Accepted:
                self.statusBar().showMessage("已放弃本次录制")
                return
            score_text = review.score_text()
            try:
                entry = self.library.save_score_text(score_text)
            except (OSError, UnicodeError, ValueError) as exc:
                QMessageBox.warning(self, "无法保存录制", str(exc))
                continue
            self._refresh_library(entry.path)
            self._switch_page(0)
            self._open_editor(entry.path)
            self.statusBar().showMessage(f"录制已保存：{entry.title}")
            return

    def _cancel_recording(self) -> None:
        """丢弃活动录制并恢复所有界面和监听状态。"""

        self._record_ready = False
        self.input_capture.stop()
        self._reset_recording_ui()

    def _reset_recording_ui(self) -> None:
        """清空录制状态并恢复控件、倒计时和悬浮条。"""

        self.recording_session = None
        self.recording_settings = None
        self._record_waiting_for_foreground = False
        self._record_ready = False
        self._record_paused = False
        self.countdown_overlay.cancel()
        self.recording_overlay.hide()
        self.profile_combo.setEnabled(True)
        self.header_record_button.setText("录制")
        self.page_record_button.setText("录制演奏")

    @Slot()
    def toggle_playback(self) -> None:
        """根据当前状态开始、暂停或继续当前曲谱。"""

        if self.recording_session is not None:
            self.statusBar().showMessage(
                f"请先按 {self.app_settings.record_hotkey} 完成当前录制"
            )
            return

        if self.player.state is PlaybackState.PLAYING:
            self.player.pause()
            return
        if self.player.state is PlaybackState.PAUSED:
            if self.target_hwnd and is_foreground(self.target_hwnd):
                self.player.play()
            else:
                self.statusBar().showMessage(
                    f"请切回开始播放时的窗口，再按 {self.app_settings.play_hotkey} 继续"
                )
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
            self.countdown_overlay.show_waiting(
                self.plan.title,
                self.app_settings.show_countdown_overlay,
            )
            self.statusBar().showMessage("请切换到游戏窗口")

    @Slot()
    def emergency_stop(self) -> None:
        """取消等待或倒计时，停止播放并释放全部按键。"""

        if self.recording_session is not None:
            self._finish_recording()
            return

        self._waiting_for_foreground = False
        self.countdown_overlay.cancel()
        self.player.stop()
        self.playback_overlay.hide()
        self.roll_preview.set_playhead_beat(0, follow_view=False)
        self.statusBar().showMessage("已停止并释放所有按键")

    def _remember_foreground_and_countdown(self, hwnd: int) -> None:
        """
        记住触发播放快捷键时的前台窗口并开始倒计时。

        Args:
            hwnd (int): 当时的前台窗口句柄。
        """

        if self.plan is None:
            return
        self._waiting_for_foreground = False
        self.target_hwnd = hwnd
        self.statusBar().showMessage("前台保护已启用，正在准备播放")
        self.countdown_overlay.start_countdown(
            self.plan.title,
            self._begin_after_countdown,
            self.app_settings.countdown_seconds,
            self.app_settings.show_countdown_overlay,
        )

    def _begin_after_countdown(self) -> None:
        """倒计时结束后再次验证前台窗口并开始播放。"""

        if self.plan is None:
            return
        if not is_foreground(self.target_hwnd):
            self._waiting_for_foreground = True
            self.countdown_overlay.show_waiting(
                self.plan.title,
                self.app_settings.show_countdown_overlay,
            )
            return
        self.current_note_text = "等待第一个音符"
        if self.app_settings.show_playback_overlay:
            self.playback_overlay.begin(self.plan.title, self.plan.bpm)
        else:
            self.playback_overlay.hide()
        self.player.play()

    def _check_foreground(self) -> None:
        """检测等待中的前台窗口或播放时的焦点变化。"""

        if self.recording_session is not None:
            current = foreground_window()
            if self._record_waiting_for_foreground:
                if current and current != int(self.winId()):
                    self._record_waiting_for_foreground = False
                    self.target_hwnd = current
                    self.statusBar().showMessage("已识别游戏窗口，正在准备录制")
                    self.countdown_overlay.start_recording_countdown(
                        self._begin_recording_after_countdown,
                        self.app_settings.countdown_seconds,
                        self.app_settings.show_countdown_overlay,
                    )
                return
            if self._record_ready and self.target_hwnd:
                now_ms = time.perf_counter_ns() / 1_000_000.0
                if not is_foreground(self.target_hwnd) and not self._record_paused:
                    self.recording_session.pause(now_ms)
                    self._record_paused = True
                    self.statusBar().showMessage("游戏失去焦点，录制已暂停")
                elif is_foreground(self.target_hwnd) and self._record_paused:
                    self.recording_session.resume(now_ms)
                    self._record_paused = False
                    self.statusBar().showMessage("已返回游戏，录制继续")
            return

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

        if self.recording_session is not None and self._record_ready:
            elapsed_ms = self.recording_session.elapsed_ms(
                time.perf_counter_ns() / 1_000_000.0
            )
            self.recording_overlay.update_recording(
                elapsed_ms,
                self.recording_session.note_count,
                self.current_note_text,
                self._record_paused,
            )
            return

        if self.plan is None or self.plan.duration_ms <= 0:
            return
        ratio = min(1.0, self.player.position_ms / self.plan.duration_ms)
        state = self.player.state
        self.roll_preview.set_playhead_beat(
            self.player.position_ms * self.plan.bpm / 60_000.0,
            follow_view=state is PlaybackState.PLAYING,
        )
        paused = state is PlaybackState.PAUSED
        if self.playback_overlay.isVisible():
            self.playback_overlay.update_playback(ratio, self.current_note_text, paused)

    def _new_score(self) -> None:
        """以内存草稿打开新曲谱，只有用户保存后才写入曲谱库。"""

        self._open_editor(
            None,
            initial_text=self.library.new_score_text(),
            save_new=lambda text: self.library.save_score_text(text).path,
        )

    def _import_score(self) -> None:
        """导入外部文本曲谱，或从 MIDI 提取单声部主旋律。"""

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "导入曲谱",
            "",
            "支持的曲谱 (*.txt *.mid *.midi);;MIDI 文件 (*.mid *.midi);;文本简谱 (*.txt)",
        )
        if not filename:
            return
        source = Path(filename)
        try:
            if source.suffix.lower() in {".mid", ".midi"}:
                result = import_midi(source)
                entry = self.library.save_score_text(serialize_document(result.document))
            else:
                result = None
                entry = self.library.import_score(source)
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        self._refresh_library(entry.path)
        self.statusBar().showMessage(f"已导入：{entry.title}")
        if result is not None:
            QMessageBox.information(
                self,
                "MIDI 主旋律已导入",
                f"已转换并保存为 KeyScore 曲谱。\n\n{result.report.summary()}",
            )

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
        self.roll_preview.set_score_document(None)
        self.edit_button.setEnabled(False)
        self._refresh_library()
        self.statusBar().showMessage(f"已删除：{entry.title}")

    def _edit_current(self) -> None:
        """在独立窗口中打开当前曲谱。"""

        if self.current_entry is None:
            return
        self._open_editor(self.current_entry.path)

    def _open_editor(
        self,
        path: Path | None,
        initial_text: str | None = None,
        save_new: Callable[[str], Path] | None = None,
    ) -> None:
        """
        创建独立曲谱编辑窗口。

        Args:
            path (Path | None): 待编辑曲谱路径；新建草稿时为空。
            initial_text (str | None): 新建草稿的初始文本。
            save_new (Callable[[str], Path] | None): 新建草稿保存回调。
        """

        try:
            editor = ScoreEditorWindow(
                path,
                self,
                self.app_settings.duration_presets,
                self.app_settings.default_note_duration,
                self.app_settings.duration_cycle_hotkey,
                self.app_settings.duration_reverse_hotkey,
                initial_text,
                save_new,
            )
        except (OSError, UnicodeError, ValueError) as exc:
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
            self.header_play_button.setText("暂停")
        elif state is PlaybackState.PAUSED:
            self.header_play_button.setText("继续")
        elif state is PlaybackState.STOPPED:
            self.header_play_button.setText("播放")
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
        self.roll_preview.follow_playhead_pitch(pitch_from_note(event.note))
        octave_text = {
            Octave.LOWEST: "倍低音",
            Octave.LOW: "低音",
            Octave.MIDDLE: "中音",
            Octave.HIGH: "高音",
            Octave.HIGHEST: "倍高音",
        }
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
        self.input_capture.stop()
        self.countdown_overlay.cancel()
        self.playback_overlay.hide()
        self.recording_overlay.hide()
        self.player.stop(wait=True)
        event.accept()
