"""键谱 Qt 应用启动器。"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QTranslator
    from PySide6.QtWidgets import QApplication


def install_chinese_translations(application: QApplication) -> QTranslator | None:
    """
    安装 Qt 简体中文翻译，使所有标准控件按钮显示为中文。

    Args:
        application (QApplication): 当前 Qt 应用实例。

    Returns:
        QTranslator | None: 已安装的翻译器；翻译文件不可用时返回 None。
    """

    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    QLocale.setDefault(QLocale("zh_CN"))
    translator = QTranslator(application)
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if not translator.load("qtbase_zh_CN", translations_path):
        return None
    application.installTranslator(translator)
    return translator


def main() -> int:
    """
    创建 QApplication 并启动键谱主窗口。

    Returns:
        int: Qt 事件循环退出码。
    """

    try:
        from PySide6.QtGui import QFont, QFontDatabase, QIcon
        from PySide6.QtWidgets import QApplication
    except ImportError as error:
        print(
            f"无法加载 PySide6：{error}\n请先执行：pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    from .app_settings import load_app_settings
    from .library import default_data_directory
    from .main_window import MainWindow
    from .resources import app_icon_path
    from .theme import ThemeManager

    application = QApplication(sys.argv)
    application.setApplicationName("KeyScore")
    application.setOrganizationName("KeyScore")
    application.setWindowIcon(QIcon(str(app_icon_path())))
    chinese_translator = install_chinese_translations(application)
    font_id = QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    font_families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
    application.setFont(QFont(font_families[0] if font_families else "Microsoft YaHei UI", 10))
    app_settings_path = default_data_directory() / "app_settings.json"
    app_settings = load_app_settings(app_settings_path)
    theme_manager = ThemeManager(application, app_settings.theme)
    window = MainWindow(theme_manager, app_settings_path)
    window.show()
    exit_code = application.exec()
    _ = chinese_translator  # 保持翻译器存活到事件循环结束。
    return exit_code
