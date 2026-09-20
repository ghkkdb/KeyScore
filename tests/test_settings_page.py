"""主窗口设置分类布局测试。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QIcon, QKeySequence, QPixmap
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from keyscore.app_settings import ThemeId, load_app_settings
from keyscore.main_window import MainWindow
from keyscore.piano_roll import PianoRollEditor
from keyscore.resources import app_icon_path
from keyscore.theme import ThemeManager
from keyscore.window_chrome import ProfileSelector, SmoothComboBox, SmoothSpinBox


class SettingsPageTests(unittest.TestCase):
    """验证设置页分类和项目版本信息。"""

    application: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        """为主窗口测试创建共享 QApplication。"""

        cls.application = QApplication.instance() or QApplication([])

    def test_about_is_main_page_and_settings_contains_two_categories(self) -> None:
        """关于应位于主导航，设置页只保留外观和快捷键分类。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"KEYSCORE_DATA_DIR": directory},
        ):
            manager = ThemeManager(self.application, ThemeId.FLUENT)
            window = MainWindow(manager, Path(directory) / "app_settings.json")
            try:
                self.assertEqual(window.pages.count(), 4)
                self.assertEqual(
                    [button.text() for button in window.navigation_buttons],
                    ["曲谱", "按键映射", "设置", "关于"],
                )
                self.assertEqual(
                    [button.accessibleName() for button in window.navigation_buttons],
                    ["曲谱", "按键映射", "设置", "关于"],
                )
                self.assertTrue(
                    all(not button.toolTip() for button in window.navigation_buttons)
                )
                self.assertTrue(
                    bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
                )
                self.assertEqual(window.navigation_buttons[0].width(), 58)
                self.assertIsInstance(window.profile_combo, ProfileSelector)
                self.assertIsInstance(window.theme_combo, SmoothComboBox)
                self.assertIsInstance(window.countdown_seconds_spin, SmoothSpinBox)
                self.assertIsInstance(window.roll_preview, PianoRollEditor)
                self.assertEqual(window.preview_tabs.count(), 2)
                self.assertFalse(hasattr(window, "progress"))
                self.assertFalse(hasattr(window, "play_button"))
                self.assertFalse(hasattr(window, "more_button"))
                self.assertEqual(window.minimumWidth(), 890)
                self.assertEqual(window.delete_button.parent(), window.pages.widget(0))
                self.assertEqual(window.settings_stack.count(), 2)
                self.assertEqual(
                    [
                        window.settings_categories.item(index).text()
                        for index in range(window.settings_categories.count())
                    ],
                    ["外观", "快捷键"],
                )
                window._switch_page(3)
                self.assertEqual(window.pages.currentIndex(), 3)
                labels = [label.text() for label in window.findChildren(QLabel)]
                self.assertIn("版本 0.1.0", labels)
                self.assertTrue(window.playback_overlay_check.isChecked())
                self.assertEqual(window.countdown_seconds_spin.value(), 3)
                self.assertTrue(window.countdown_overlay_check.isChecked())
                self.assertGreaterEqual(window.record_hotkey_edit.minimumWidth(), 200)
                labels = [label.text() for label in window.findChildren(QLabel)]
                self.assertNotIn("游戏演奏按键", labels)
            finally:
                window.close()

    def test_app_icon_resource_can_be_loaded(self) -> None:
        """应用图标应随包发布并能被 Qt 正常读取。"""

        path = app_icon_path()
        pixmap = QPixmap(str(path))
        icon = QIcon(str(path))

        self.assertTrue(path.is_file())
        self.assertFalse(pixmap.isNull())
        self.assertFalse(icon.isNull())
        self.assertEqual(pixmap.width(), pixmap.height())

    def test_custom_hotkeys_are_saved_and_labels_refresh(self) -> None:
        """保存有效快捷键后应立即持久化并刷新界面提示。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"KEYSCORE_DATA_DIR": directory},
        ):
            settings_path = Path(directory) / "app_settings.json"
            manager = ThemeManager(self.application, ThemeId.FLUENT)
            window = MainWindow(manager, settings_path)
            try:
                window.record_hotkey_edit.setKeySequence(QKeySequence("Ctrl+F8"))
                window.play_hotkey_edit.setKeySequence(QKeySequence("Alt+P"))
                window.stop_hotkey_edit.setKeySequence(QKeySequence("Shift+F10"))
                with patch.object(window.hotkeys, "configure", return_value=True):
                    window._save_hotkey_settings()

                settings = load_app_settings(settings_path)
                self.assertEqual(settings.record_hotkey, "Ctrl+F8")
                self.assertEqual(settings.play_hotkey, "Alt+P")
                self.assertEqual(settings.stop_hotkey, "Shift+F10")
                self.assertIn("Ctrl+F8 录制", window.shortcut_hint.text())
                self.assertIn("Alt+P 播放", window.shortcut_hint.text())
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
