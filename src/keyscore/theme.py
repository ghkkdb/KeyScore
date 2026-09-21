"""Windows 11 Fluent 与游戏电竞双主题。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QWidget

from .app_settings import ThemeId


THEME_LABELS: dict[ThemeId, str] = {
    ThemeId.FLUENT: "Windows 11 Fluent（默认）",
    ThemeId.ESPORTS: "游戏电竞风",
}


_FLUENT_STYLE = r"""
QWidget { color: #17233C; font-family: "Microsoft YaHei UI"; }
QPushButton, QToolButton, QComboBox, QLineEdit, QSpinBox, QKeySequenceEdit, QListWidget, QPlainTextEdit { outline: none; }
QMainWindow { background: transparent; }
QDialog { background: #F3F7FC; }
QWidget#windowRoot { background: transparent; }
QWidget#editorWindow { background: #F3F7FC; }
QWidget#appShell {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #F8FCFF, stop:0.45 #F2F8FE, stop:1 #EAF5FF);
    border: 1px solid rgba(255, 255, 255, 220); border-radius: 24px;
}
QWidget#appShell[maximized="true"] { border-radius: 0; border: none; }
QWidget#windowTitleBar { background: transparent; }
QWidget#commandBar {
    background: rgba(246, 251, 255, 178);
    border: none; border-bottom: 1px solid rgba(190, 211, 232, 145);
}
QWidget#centralPanel {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #F8FBFE, stop:1 #EEF7FF);
}
QMenu { background: #FFFFFF; color: #17233C; border: 1px solid #D7E4F0; padding: 7px; border-radius: 10px; }
QMenu::item { padding: 8px 30px 8px 12px; border-radius: 7px; }
QMenu::item:selected { background: #E6F2FF; color: #0875DC; }
QMenu::separator { height: 1px; background: #E2EAF2; margin: 5px 8px; }
QLabel { background: transparent; }
QWidget#appLogo {
    background: transparent; border: none;
}
QLabel#brand { color: #102142; font-size: 22px; font-weight: 700; }
QLabel#brandSeparator { color: #8BA5C5; font-size: 19px; }
QLabel#brandSubtitle { color: #5F79A0; font-size: 13px; }
QLabel#dialogTitle { color: #12213A; font-size: 18px; font-weight: 700; }
QLabel#displayTitle { color: #102142; font-size: 25px; font-weight: 700; }
QLabel#sectionLabel { color: #607086; font-size: 13px; font-weight: 600; }
QLabel#muted, QLabel[state="normal"] { color: #66758A; }
QLabel#sidebarVersion { color: #7990AD; font-size: 11px; }
QLabel#navigationHint {
    background: #203959; color: #FFFFFF; border: none; border-radius: 7px;
    padding: 6px 10px; font-size: 13px; font-weight: 600;
}
QLabel#commandDivider { color: #B5C8DC; font-size: 20px; }
QLabel[state="warning"] { color: #986A00; }
QLabel[state="error"] { color: #C42B1C; }
QListWidget, QPlainTextEdit {
    background: rgba(255, 255, 255, 205); color: #26354D; border: 1px solid #D4E3F1;
    border-radius: 14px; outline: none; selection-background-color: #CFE5FF;
    selection-color: #102A4C;
}
QListWidget { padding: 6px; font-size: 14px; }
QListWidget::item { padding: 10px 11px; border-radius: 9px; }
QListWidget::item:selected { background: #D8EBFF; color: #0875DC; font-weight: 600; }
QListWidget::item:hover { background: #EAF4FE; }
QPlainTextEdit { padding: 16px; font-family: "Cascadia Mono", "Consolas"; font-size: 15px; }
QComboBox, QLineEdit, QSpinBox {
    background: rgba(255, 255, 255, 218); color: #17233C; border: 1px solid #C8DAEA;
    border-radius: 11px; padding: 8px 11px;
}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover { border-color: #8EBDEB; background: #FFFFFF; }
QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border: 2px solid #1684EA; padding: 7px 10px; }
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled { background: #EDEFF2; color: #8993A0; }
QComboBox QLineEdit { background: transparent; border: none; padding: 0; }
QComboBox QAbstractItemView { background: #FFFFFF; color: #17233C; border: 1px solid #C8DAEA; selection-background-color: #DCEBFC; border-radius: 9px; padding: 5px; }
QComboBox#smoothComboBox { padding-right: 34px; }
QComboBox#smoothComboBox::drop-down { width: 0; border: none; }
QComboBox#smoothComboBox::down-arrow { image: none; width: 0; height: 0; }
QSpinBox#smoothSpinBox { padding-right: 35px; }
QSpinBox#smoothSpinBox:focus { padding: 7px 35px 7px 10px; }
QSpinBox#smoothSpinBox QLineEdit { background: transparent; border: none; padding: 0; }
QKeySequenceEdit#shortcutEditor { background: transparent; border: none; padding: 0; }
QKeySequenceEdit#shortcutEditor QLineEdit {
    background: rgba(255, 255, 255, 218); color: #17233C; border: 1px solid #C8DAEA;
    border-radius: 11px; padding: 8px 11px;
}
QKeySequenceEdit#shortcutEditor QLineEdit:hover { border-color: #8EBDEB; background: #FFFFFF; }
QKeySequenceEdit#shortcutEditor QLineEdit:focus { border: 2px solid #1684EA; padding: 7px 10px; }
QPushButton {
    background: #F7FAFD; color: #263D61; border: 1px solid #C8DAEA;
    border-radius: 9px; padding: 9px 15px; min-height: 18px;
}
QPushButton:hover { background: #FFFFFF; border-color: #8EBDEB; }
QPushButton:pressed { background: #E3EFFA; }
QPushButton:disabled { background: #EEF1F4; color: #99A3AF; border-color: #E2E6EB; }
QPushButton#primary {
    background: #1687EF;
    color: #FFFFFF; border: 1px solid #1A8EED; font-weight: 700;
}
QPushButton#primary:hover { background: #118AF5; border-color: #0875DE; }
QPushButton#record { color: #263D61; }
QPushButton#record:hover { color: #D9364E; border-color: #F0A3AE; }
QPushButton#binding { background: rgba(255, 255, 255, 220); border: 1px solid #D2DFEC; text-align: left; }
QProgressBar { background: #D9E4F0; border: none; border-radius: 3px; min-height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #1687EF; border-radius: 3px; }
QStatusBar#appStatusBar {
    color: #6A7E99; border: none; border-top: 1px solid rgba(201, 217, 232, 150);
    border-bottom-left-radius: 23px; border-bottom-right-radius: 23px;
    background: rgba(247, 251, 255, 170); padding-left: 12px;
}
QWidget#appShell[maximized="true"] QStatusBar#appStatusBar { border-radius: 0; }
QSplitter::handle { background: transparent; width: 14px; }
QWidget#sidebar { background: rgba(248, 252, 255, 185); border-right: 1px solid rgba(203, 220, 236, 175); }
QWidget#pageCard { background: rgba(255, 255, 255, 205); border: 1px solid #D7E6F3; border-radius: 18px; }
QWidget#settingsSection { background: rgba(255, 255, 255, 190); border: 1px solid #D7E6F3; border-radius: 15px; }
QGraphicsView#pianoRoll { background: #F8FBFF; border: 1px solid #D4E3F1; border-radius: 14px; }
QTabWidget#previewTabs::pane, QTabWidget#editorTabs::pane { border: none; background: transparent; top: -1px; }
QTabWidget#previewTabs QTabBar::tab, QTabWidget#editorTabs QTabBar::tab {
    background: transparent; color: #66758A; border: none; border-radius: 8px;
    padding: 7px 14px; margin-right: 4px;
}
QTabWidget#previewTabs QTabBar::tab:selected, QTabWidget#editorTabs QTabBar::tab:selected {
    background: #DCEBFC; color: #0875DC; font-weight: 600;
}
QTabWidget#previewTabs QTabBar::tab:hover, QTabWidget#editorTabs QTabBar::tab:hover { background: #EAF4FE; }
QListWidget#settingsCategories {
    background: rgba(242, 248, 254, 190); border: none; border-right: 1px solid #DCE7F1;
    border-radius: 17px 0 0 17px; padding: 10px;
}
QListWidget#settingsCategories::item { padding: 10px 12px; border-radius: 9px; }
QListWidget#settingsCategories::item:selected { background: #DCEBFC; color: #0B5FC7; font-weight: 600; }
QLabel#shortcutKey {
    background: #FFFFFF; border: 1px solid #C9D3DF; border-radius: 9px;
    padding: 5px 12px; color: #26354D; font-family: "Cascadia Mono", "Consolas";
}
QToolButton#navigation { background: transparent; color: #35547E; border: none; border-radius: 12px; font-size: 25px; }
QToolButton#navigation:hover { background: #E6F2FF; color: #087BEB; }
QToolButton#navigation[active="true"] { background: #D8EAFF; color: #087AF0; font-weight: 700; }
QToolButton#sortToggle { background: rgba(255,255,255,218); border: 1px solid #C8DAEA; border-radius: 11px; }
QToolButton#sortToggle:hover { background: #EAF4FE; border-color: #8EBDEB; }
QToolButton#windowMinimize, QToolButton#windowMaximize, QToolButton#windowClose {
    background: transparent; color: #28456D; border: none; border-radius: 7px; font-size: 20px;
}
QToolButton#windowMinimize:hover, QToolButton#windowMaximize:hover { background: rgba(213, 230, 247, 180); }
QToolButton#windowClose:hover { background: #E94B57; color: #FFFFFF; }
QPushButton#profileSelector {
    background: #F7FAFD; color: #203959;
    border: 1px solid #C8DAEA; border-radius: 9px;
    padding: 8px 34px 8px 14px; text-align: left;
}
QPushButton#profileSelector:hover { background: #FFFFFF; border-color: #8EBDEB; }
QPushButton#profileSelector:pressed { background: #EAF3FC; border-color: #1684EA; }
QPushButton#profileSelector:disabled { background: #EDEFF2; color: #8993A0; border-color: #DDE4EB; }
QFrame#smoothPopup { background: transparent; border: none; }
QScrollArea#smoothPopupScroll, QWidget#smoothPopupContent { background: transparent; border: none; }
QPushButton#smoothOption {
    background: transparent; color: #203959; border: none; border-radius: 7px;
    padding: 7px 12px; text-align: left;
}
QPushButton#smoothOption:hover { background: #E5F2FF; color: #0875DC; }
QPushButton#smoothOption[selected="true"] { background: #DCEEFF; color: #0875DC; font-weight: 600; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 3px 2px; }
QScrollBar::handle:vertical { background: #B4C5D7; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #8EA9C3; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 9px; margin: 2px 3px; }
QScrollBar::handle:horizontal { background: #B4C5D7; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QToolTip { background: #FFFFFF; color: #213B60; border: 1px solid #D4E2EF; border-radius: 9px; padding: 7px 10px; }
QFrame#overlayCard { background: rgba(248, 251, 255, 244); border: 1px solid rgba(185, 199, 214, 220); border-radius: 16px; }
QFrame#overlayCard QLabel { color: #17233C; }
QFrame#overlayCard QLabel#muted { color: #66758A; }
QFrame#overlayCard QProgressBar::chunk { background: #1677D2; }
"""


_ESPORTS_STYLE = r"""
QWidget { color: #EAF4FF; font-family: "Microsoft YaHei UI"; }
QPushButton, QToolButton, QComboBox, QLineEdit, QSpinBox, QKeySequenceEdit, QListWidget, QPlainTextEdit { outline: none; }
QMainWindow { background: transparent; }
QDialog { background: #070B18; }
QWidget#windowRoot { background: transparent; }
QWidget#editorWindow { background: #070B18; }
QWidget#appShell {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #0B1530, stop:0.55 #080F23, stop:1 #071326);
    border: 1px solid #1D4778; border-radius: 24px;
}
QWidget#appShell[maximized="true"] { border-radius: 0; border: none; }
QWidget#windowTitleBar { background: transparent; }
QWidget#commandBar { background: rgba(7, 17, 38, 185); border: none; border-bottom: 1px solid #17315E; }
QWidget#centralPanel { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #080F20, stop:1 #09162B); }
QMenuBar { background: #070B18; color: #8295B7; border-bottom: 1px solid #18284D; padding: 3px; }
QMenuBar::item { padding: 6px 10px; border-radius: 4px; }
QMenuBar::item:selected, QMenu::item:selected { background: #132A51; color: #00D9FF; }
QMenu { background: #0B1327; color: #EAF4FF; border: 1px solid #1D4380; padding: 5px; }
QMenu::item { padding: 7px 26px 7px 10px; border-radius: 3px; }
QLabel { background: transparent; }
QWidget#appLogo { background: transparent; border: none; }
QLabel#brand { color: #EAFBFF; font-size: 22px; font-weight: 700; }
QLabel#brandSeparator { color: #38658D; font-size: 19px; }
QLabel#brandSubtitle { color: #82A1C7; font-size: 13px; }
QLabel#dialogTitle { color: #73EAFF; font-size: 18px; font-weight: 700; }
QLabel#displayTitle { color: #72ECFF; font-size: 24px; font-weight: 600; }
QLabel#sectionLabel { color: #8295B7; font-size: 13px; font-weight: 600; }
QLabel#muted, QLabel[state="normal"] { color: #8093B5; }
QLabel#sidebarVersion { color: #597294; font-size: 11px; }
QLabel#navigationHint {
    background: #162746; color: #EAFBFF; border: 1px solid #315478; border-radius: 7px;
    padding: 6px 10px; font-size: 13px; font-weight: 600;
}
QLabel#commandDivider { color: #315478; font-size: 20px; }
QLabel[state="warning"] { color: #FFB52E; }
QLabel[state="error"] { color: #FF3B82; }
QListWidget, QPlainTextEdit {
    background: #0A1224; color: #CFE4FF; border: 1px solid #183B72;
    border-radius: 14px; outline: none; selection-background-color: #173E71;
    selection-color: #FFFFFF;
}
QListWidget { padding: 5px; font-size: 14px; }
QListWidget::item { padding: 9px 10px; border-radius: 9px; }
QListWidget::item:selected { background: #44207B; color: #FFFFFF; border-left: 2px solid #00D9FF; }
QListWidget::item:hover { background: #101F3D; }
QPlainTextEdit { padding: 14px; font-family: "Cascadia Mono", "Consolas"; font-size: 15px; }
QComboBox, QLineEdit, QSpinBox {
    background: #0B1429; color: #EAF4FF; border: 1px solid #25477C;
    border-radius: 11px; padding: 8px 10px;
}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover { border-color: #00BDEB; }
QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border: 1px solid #00D9FF; }
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled { background: #101626; color: #50607C; }
QComboBox QLineEdit { background: transparent; border: none; padding: 0; }
QComboBox QAbstractItemView { background: #0B1429; color: #EAF4FF; border: 1px solid #00AEDA; selection-background-color: #3A1A72; }
QComboBox#smoothComboBox { padding-right: 34px; }
QComboBox#smoothComboBox::drop-down { width: 0; border: none; }
QComboBox#smoothComboBox::down-arrow { image: none; width: 0; height: 0; }
QSpinBox#smoothSpinBox { padding-right: 35px; }
QSpinBox#smoothSpinBox:focus { padding-right: 35px; }
QSpinBox#smoothSpinBox QLineEdit { background: transparent; border: none; padding: 0; }
QKeySequenceEdit#shortcutEditor { background: transparent; border: none; padding: 0; }
QKeySequenceEdit#shortcutEditor QLineEdit {
    background: #0B1429; color: #EAF4FF; border: 1px solid #25477C;
    border-radius: 11px; padding: 8px 10px;
}
QKeySequenceEdit#shortcutEditor QLineEdit:hover { border-color: #00BDEB; }
QKeySequenceEdit#shortcutEditor QLineEdit:focus { border-color: #00D9FF; }
QPushButton {
    background: #0D1830; color: #BFD6F2; border: 1px solid #233F70;
    border-radius: 9px; padding: 9px 14px;
}
QPushButton:hover { background: #122849; color: #73EAFF; border-color: #00BDEB; }
QPushButton:pressed { background: #18355B; }
QPushButton:disabled { background: #0B1020; color: #4E5C75; border-color: #17233A; }
QPushButton#primary { background: #123B5E; color: #A8F6FF; border: 1px solid #00D9FF; font-weight: 700; }
QPushButton#primary:hover { background: #0A3D5D; border-color: #74EEFF; }
QPushButton#binding { background: #0B1429; border: 1px solid #263F70; text-align: left; }
QProgressBar { background: #172443; border: none; border-radius: 3px; min-height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #00D9FF; border-radius: 3px; }
QStatusBar#appStatusBar {
    color: #7488AC; border: none; border-top: 1px solid #162746;
    border-bottom-left-radius: 23px; border-bottom-right-radius: 23px;
    background: rgba(8, 14, 29, 180); padding-left: 12px;
}
QWidget#appShell[maximized="true"] QStatusBar#appStatusBar { border-radius: 0; }
QSplitter::handle { background: transparent; width: 14px; }
QWidget#sidebar { background: rgba(9, 17, 38, 190); border-right: 1px solid #17315E; }
QWidget#pageCard { background: rgba(10, 18, 36, 220); border: 1px solid #183B72; border-radius: 18px; }
QWidget#settingsSection { background: rgba(12, 22, 43, 220); border: 1px solid #183B72; border-radius: 15px; }
QGraphicsView#pianoRoll { background: #081328; border: 1px solid #183B72; border-radius: 14px; }
QTabWidget#previewTabs::pane, QTabWidget#editorTabs::pane { border: none; background: transparent; top: -1px; }
QTabWidget#previewTabs QTabBar::tab, QTabWidget#editorTabs QTabBar::tab {
    background: transparent; color: #8093B5; border: none; border-radius: 8px;
    padding: 7px 14px; margin-right: 4px;
}
QTabWidget#previewTabs QTabBar::tab:selected, QTabWidget#editorTabs QTabBar::tab:selected {
    background: #32205E; color: #73EAFF; font-weight: 600;
}
QTabWidget#previewTabs QTabBar::tab:hover, QTabWidget#editorTabs QTabBar::tab:hover { background: #101F3D; }
QListWidget#settingsCategories {
    background: #091126; border: none; border-right: 1px solid #17315E;
    border-radius: 17px 0 0 17px; padding: 10px;
}
QListWidget#settingsCategories::item { padding: 10px 12px; border-radius: 4px; }
QListWidget#settingsCategories::item:selected {
    background: #44207B; color: #FFFFFF; border-left: 2px solid #00D9FF; font-weight: 600;
}
QLabel#shortcutKey {
    background: #0B1429; border: 1px solid #25477C; border-radius: 4px;
    padding: 5px 12px; color: #8EF2FF; font-family: "Cascadia Mono", "Consolas";
}
QToolButton#navigation { background: transparent; color: #82A1C7; border: none; border-radius: 12px; font-size: 25px; }
QToolButton#navigation:hover { background: #101F3D; color: #73EAFF; }
QToolButton#navigation[active="true"] { background: #32205E; color: #73EAFF; border: 1px solid #00BDEB; font-weight: 700; }
QToolButton#sortToggle { background: #0B1429; border: 1px solid #25477C; border-radius: 11px; }
QToolButton#sortToggle:hover { background: #101F3D; border-color: #00BDEB; }
QToolButton#windowMinimize, QToolButton#windowMaximize, QToolButton#windowClose { background: transparent; color: #91ACCC; border: none; border-radius: 7px; font-size: 20px; }
QToolButton#windowMinimize:hover, QToolButton#windowMaximize:hover { background: #132846; color: #CFF8FF; }
QToolButton#windowClose:hover { background: #D93854; color: #FFFFFF; }
QPushButton#profileSelector {
    background: #0B1429; color: #EAF4FF; border: 1px solid #25477C;
    border-radius: 9px; padding: 8px 34px 8px 14px; text-align: left;
}
QPushButton#profileSelector:hover { background: #10213C; border-color: #00BDEB; }
QPushButton#profileSelector:pressed { background: #132A49; border-color: #00D9FF; }
QPushButton#profileSelector:disabled { background: #101626; color: #50607C; border-color: #17233A; }
QFrame#smoothPopup { background: transparent; border: none; }
QScrollArea#smoothPopupScroll, QWidget#smoothPopupContent { background: transparent; border: none; }
QPushButton#smoothOption {
    background: transparent; color: #EAF4FF; border: none; border-radius: 7px;
    padding: 7px 12px; text-align: left;
}
QPushButton#smoothOption:hover { background: #352064; color: #FFFFFF; }
QPushButton#smoothOption[selected="true"] { background: #44207B; color: #FFFFFF; font-weight: 600; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #244B7E; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 9px; margin: 2px 3px; }
QScrollBar::handle:horizontal { background: #244B7E; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #34649D; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QToolTip { background: #101C35; color: #CFF8FF; border: 1px solid #00AEDA; border-radius: 9px; padding: 7px 10px; }
QFrame#overlayCard { background: rgba(7, 13, 29, 244); border: 1px solid #00BDEB; border-radius: 16px; }
QFrame#overlayCard QLabel { color: #EAF4FF; }
QFrame#overlayCard QLabel#muted { color: #8093B5; }
QFrame#overlayCard QProgressBar::chunk { background: #00D9FF; }
"""


def theme_stylesheet(theme: ThemeId) -> str:
    """
    返回指定主题的完整 Qt 样式表。

    Args:
        theme (ThemeId): 主题标识。

    Returns:
        str: 可交给 QApplication 的 QSS 文本。
    """

    return _ESPORTS_STYLE if theme is ThemeId.ESPORTS else _FLUENT_STYLE


def set_widget_state(widget: QWidget, state: str) -> None:
    """
    设置控件的动态视觉状态并立即刷新样式。

    Args:
        widget (QWidget): 需要更新的控件。
        state (str): QSS 使用的状态名称。
    """

    widget.setProperty("state", state)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class ThemeManager(QObject):
    """在运行时为整个 QApplication 切换主题。"""

    theme_changed = Signal(str)

    def __init__(self, application: QApplication, theme: ThemeId) -> None:
        """
        初始化主题管理器并应用初始主题。

        Args:
            application (QApplication): 当前 Qt 应用实例。
            theme (ThemeId): 初始主题。
        """

        super().__init__(application)
        self._application = application
        self._current = theme
        self.apply(theme)

    @property
    def current(self) -> ThemeId:
        """
        返回当前主题。

        Returns:
            ThemeId: 当前生效的主题标识。
        """

        return self._current

    def apply(self, theme: ThemeId) -> None:
        """
        将主题立即应用到所有现有和后续创建的 Qt 控件。

        Args:
            theme (ThemeId): 需要应用的主题。
        """

        self._current = theme
        self._application.setProperty("theme", theme.value)
        self._application.setStyleSheet(theme_stylesheet(theme))
        self.theme_changed.emit(theme.value)
