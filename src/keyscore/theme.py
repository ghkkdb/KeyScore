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
QMainWindow, QDialog { background: #F3F6FA; }
QWidget#centralPanel { background: #F3F6FA; }
QMenuBar { background: #F3F6FA; color: #526176; border: none; padding: 3px; }
QMenuBar::item { padding: 6px 10px; border-radius: 5px; }
QMenuBar::item:selected, QMenu::item:selected { background: #E1ECFA; color: #0B5FC7; }
QMenu { background: #FFFFFF; color: #17233C; border: 1px solid #D7E0EB; padding: 5px; }
QMenu::item { padding: 7px 26px 7px 10px; border-radius: 4px; }
QLabel { background: transparent; }
QLabel#brand { color: #12213A; font-size: 19px; font-weight: 700; }
QLabel#dialogTitle { color: #12213A; font-size: 18px; font-weight: 700; }
QLabel#displayTitle { color: #12213A; font-size: 24px; font-weight: 600; }
QLabel#sectionLabel { color: #607086; font-size: 13px; font-weight: 600; }
QLabel#muted, QLabel[state="normal"] { color: #66758A; }
QLabel[state="warning"] { color: #986A00; }
QLabel[state="error"] { color: #C42B1C; }
QListWidget, QPlainTextEdit {
    background: #FFFFFF; color: #26354D; border: 1px solid #DCE4EE;
    border-radius: 9px; outline: none; selection-background-color: #CFE5FF;
    selection-color: #102A4C;
}
QListWidget { padding: 5px; font-size: 14px; }
QListWidget::item { padding: 9px 10px; border-radius: 6px; }
QListWidget::item:selected { background: #DCEBFC; color: #0B5FC7; }
QListWidget::item:hover { background: #EDF4FC; }
QPlainTextEdit { padding: 14px; font-family: "Cascadia Mono", "Consolas"; font-size: 15px; }
QComboBox, QLineEdit, QSpinBox {
    background: #FFFFFF; color: #17233C; border: 1px solid #C9D3DF;
    border-bottom: 2px solid #7A8797; border-radius: 5px; padding: 7px 9px;
}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover { border-color: #93A2B5; border-bottom-color: #1677D2; }
QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border-bottom-color: #0067C0; }
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled { background: #EDEFF2; color: #8993A0; }
QComboBox QLineEdit { background: transparent; border: none; padding: 0; }
QComboBox QAbstractItemView { background: #FFFFFF; color: #17233C; border: 1px solid #C9D3DF; selection-background-color: #DCEBFC; }
QPushButton {
    background: #FFFFFF; color: #26354D; border: 1px solid #CCD6E2;
    border-radius: 6px; padding: 8px 13px;
}
QPushButton:hover { background: #F7FAFD; border-color: #AEBCCC; }
QPushButton:pressed { background: #E8EEF5; }
QPushButton:disabled { background: #EEF1F4; color: #99A3AF; border-color: #E2E6EB; }
QPushButton#primary { background: #1677D2; color: #FFFFFF; border-color: #1677D2; font-weight: 600; }
QPushButton#primary:hover { background: #0E6ABD; }
QPushButton#binding { background: #FFFFFF; border: 1px solid #D2DBE5; text-align: left; }
QProgressBar { background: #DCE3EB; border: none; border-radius: 2px; min-height: 4px; max-height: 4px; }
QProgressBar::chunk { background: #1677D2; border-radius: 2px; }
QStatusBar { color: #66758A; border-top: 1px solid #DDE4EC; background: #F7F9FC; }
QSplitter::handle { background: #D9E1EA; width: 1px; }
QWidget#topBar { background: #FFFFFF; border-bottom: 1px solid #DDE4EC; }
QWidget#sidebar { background: #FFFFFF; border-right: 1px solid #DDE4EC; }
QWidget#pageCard { background: #FFFFFF; border: 1px solid #DCE4EE; border-radius: 9px; }
QWidget#settingsSection { background: #F8FAFD; border: 1px solid #DCE4EE; border-radius: 8px; }
QListWidget#settingsCategories {
    background: #F7F9FC; border: none; border-right: 1px solid #DCE4EE;
    border-radius: 8px 0 0 8px; padding: 10px;
}
QListWidget#settingsCategories::item { padding: 10px 12px; border-radius: 6px; }
QListWidget#settingsCategories::item:selected { background: #DCEBFC; color: #0B5FC7; font-weight: 600; }
QLabel#shortcutKey {
    background: #FFFFFF; border: 1px solid #C9D3DF; border-radius: 5px;
    padding: 5px 12px; color: #26354D; font-family: "Cascadia Mono", "Consolas";
}
QPushButton#navigation { background: transparent; border: none; text-align: left; padding: 10px 12px; }
QPushButton#navigation:hover { background: #EDF4FC; }
QPushButton#navigation[active="true"] { background: #DCEBFC; color: #0B5FC7; font-weight: 600; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #B8C3CF; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #202A38; color: #FFFFFF; border: none; padding: 5px; }
QFrame#overlayCard { background: rgba(248, 251, 255, 244); border: 1px solid rgba(185, 199, 214, 220); border-radius: 12px; }
QFrame#overlayCard QLabel { color: #17233C; }
QFrame#overlayCard QLabel#muted { color: #66758A; }
QFrame#overlayCard QProgressBar::chunk { background: #1677D2; }
"""


_ESPORTS_STYLE = r"""
QWidget { color: #EAF4FF; font-family: "Microsoft YaHei UI"; }
QMainWindow, QDialog { background: #070B18; }
QWidget#centralPanel { background: #070B18; }
QMenuBar { background: #070B18; color: #8295B7; border-bottom: 1px solid #18284D; padding: 3px; }
QMenuBar::item { padding: 6px 10px; border-radius: 4px; }
QMenuBar::item:selected, QMenu::item:selected { background: #132A51; color: #00D9FF; }
QMenu { background: #0B1327; color: #EAF4FF; border: 1px solid #1D4380; padding: 5px; }
QMenu::item { padding: 7px 26px 7px 10px; border-radius: 3px; }
QLabel { background: transparent; }
QLabel#brand { color: #73EAFF; font-size: 19px; font-weight: 700; }
QLabel#dialogTitle { color: #73EAFF; font-size: 18px; font-weight: 700; }
QLabel#displayTitle { color: #72ECFF; font-size: 24px; font-weight: 600; }
QLabel#sectionLabel { color: #8295B7; font-size: 13px; font-weight: 600; }
QLabel#muted, QLabel[state="normal"] { color: #8093B5; }
QLabel[state="warning"] { color: #FFB52E; }
QLabel[state="error"] { color: #FF3B82; }
QListWidget, QPlainTextEdit {
    background: #0A1224; color: #CFE4FF; border: 1px solid #183B72;
    border-radius: 5px; outline: none; selection-background-color: #173E71;
    selection-color: #FFFFFF;
}
QListWidget { padding: 5px; font-size: 14px; }
QListWidget::item { padding: 9px 10px; border-radius: 4px; }
QListWidget::item:selected { background: #44207B; color: #FFFFFF; border-left: 2px solid #00D9FF; }
QListWidget::item:hover { background: #101F3D; }
QPlainTextEdit { padding: 14px; font-family: "Cascadia Mono", "Consolas"; font-size: 15px; }
QComboBox, QLineEdit, QSpinBox {
    background: #0B1429; color: #EAF4FF; border: 1px solid #25477C;
    border-radius: 4px; padding: 7px 9px;
}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover { border-color: #00BDEB; }
QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border: 1px solid #00D9FF; }
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled { background: #101626; color: #50607C; }
QComboBox QLineEdit { background: transparent; border: none; padding: 0; }
QComboBox QAbstractItemView { background: #0B1429; color: #EAF4FF; border: 1px solid #00AEDA; selection-background-color: #3A1A72; }
QPushButton {
    background: #0D1830; color: #BFD6F2; border: 1px solid #233F70;
    border-radius: 4px; padding: 8px 13px;
}
QPushButton:hover { background: #122849; color: #73EAFF; border-color: #00BDEB; }
QPushButton:pressed { background: #18355B; }
QPushButton:disabled { background: #0B1020; color: #4E5C75; border-color: #17233A; }
QPushButton#primary { background: #082B45; color: #8EF2FF; border: 1px solid #00D9FF; font-weight: 700; }
QPushButton#primary:hover { background: #0A3D5D; border-color: #74EEFF; }
QPushButton#binding { background: #0B1429; border: 1px solid #263F70; text-align: left; }
QProgressBar { background: #172443; border: none; border-radius: 2px; min-height: 4px; max-height: 4px; }
QProgressBar::chunk { background: #00D9FF; border-radius: 2px; }
QStatusBar { color: #7488AC; border-top: 1px solid #162746; background: #080E1D; }
QSplitter::handle { background: #17315E; width: 1px; }
QWidget#topBar { background: #091126; border-bottom: 1px solid #17315E; }
QWidget#sidebar { background: #091126; border-right: 1px solid #17315E; }
QWidget#pageCard { background: #0A1224; border: 1px solid #183B72; border-radius: 5px; }
QWidget#settingsSection { background: #0C162B; border: 1px solid #183B72; border-radius: 5px; }
QListWidget#settingsCategories {
    background: #091126; border: none; border-right: 1px solid #17315E;
    border-radius: 4px 0 0 4px; padding: 10px;
}
QListWidget#settingsCategories::item { padding: 10px 12px; border-radius: 4px; }
QListWidget#settingsCategories::item:selected {
    background: #44207B; color: #FFFFFF; border-left: 2px solid #00D9FF; font-weight: 600;
}
QLabel#shortcutKey {
    background: #0B1429; border: 1px solid #25477C; border-radius: 4px;
    padding: 5px 12px; color: #8EF2FF; font-family: "Cascadia Mono", "Consolas";
}
QPushButton#navigation { background: transparent; border: none; text-align: left; padding: 10px 12px; }
QPushButton#navigation:hover { background: #101F3D; }
QPushButton#navigation[active="true"] { background: #44207B; color: #FFFFFF; border-left: 2px solid #00D9FF; font-weight: 600; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #244B7E; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #101C35; color: #CFF8FF; border: 1px solid #00AEDA; padding: 5px; }
QFrame#overlayCard { background: rgba(7, 13, 29, 244); border: 1px solid #00BDEB; border-radius: 8px; }
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
