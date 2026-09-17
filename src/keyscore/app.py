"""键谱 Qt 应用启动器。"""

from __future__ import annotations

import sys


def main() -> int:
    """
    创建 QApplication 并启动键谱主窗口。

    Returns:
        int: Qt 事件循环退出码。
    """

    try:
        from PySide6.QtGui import QFont, QFontDatabase
        from PySide6.QtWidgets import QApplication
    except ImportError as error:
        print(
            f"无法加载 PySide6：{error}\n请先执行：pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    from .main_window import MainWindow

    application = QApplication(sys.argv)
    application.setApplicationName("KeyScore")
    application.setOrganizationName("KeyScore")
    font_id = QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    font_families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
    application.setFont(QFont(font_families[0] if font_families else "Microsoft YaHei UI", 10))
    window = MainWindow()
    window.show()
    return application.exec()
