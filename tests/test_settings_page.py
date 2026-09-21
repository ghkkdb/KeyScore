"""主窗口设置分类布局测试。"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QIcon, QKeySequence, QPixmap
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from keyscore.app_settings import ThemeId, load_app_settings
from keyscore.main_window import MainWindow
from keyscore.models import default_profile
from keyscore.parser import parse_score
from keyscore.piano_roll import PianoRollEditor
from keyscore.resources import app_icon_path
from keyscore.theme import ThemeManager
from keyscore.profile_store import save_profile
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
                self.assertNotIn("应用信息", labels)
                self.assertNotIn("运行平台", labels)
                self.assertIn("https://github.com/ghkkdb/KeyScore", labels)
                self.assertIn(
                    "https://space.bilibili.com/417156717?spm_id_from=333.1007.0.0",
                    labels,
                )
                self.assertTrue(window.playback_overlay_check.isChecked())
                self.assertEqual(window.countdown_seconds_spin.value(), 3)
                self.assertTrue(window.countdown_overlay_check.isChecked())
                self.assertGreaterEqual(window.record_hotkey_edit.minimumWidth(), 200)
                self.assertFalse(window.score_sort_button.icon().isNull())
                self.assertFalse(window.score_sort_button.toolTip())
                self.assertIn(
                    "按时间", str(window.score_sort_button.property("hoverHint"))
                )
                QApplication.sendEvent(
                    window.score_sort_button,
                    QEvent(QEvent.Type.Enter),
                )
                self.assertIn("当前：按时间", window.navigation_hint.text())
                with patch(
                    "keyscore.main_window.QDesktopServices.openUrl",
                    return_value=True,
                ) as open_url:
                    window.github_website_button.click()
                self.assertEqual(
                    open_url.call_args.args[0].toString(),
                    "https://github.com/ghkkdb/KeyScore",
                )
                labels = [label.text() for label in window.findChildren(QLabel)]
                self.assertNotIn("游戏演奏按键", labels)
            finally:
                window.close()

    def test_new_score_stays_in_memory_until_saved(self) -> None:
        """点击新建只应打开含一个中音的草稿，不立即写入曲谱库。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"KEYSCORE_DATA_DIR": directory},
        ):
            manager = ThemeManager(self.application, ThemeId.FLUENT)
            window = MainWindow(manager, Path(directory) / "app_settings.json")
            try:
                before = set(window.library.scores_directory.glob("*.txt"))
                with patch.object(window, "_open_editor") as open_editor:
                    window._new_score()
                after = set(window.library.scores_directory.glob("*.txt"))
                self.assertEqual(before, after)
                self.assertIsNone(open_editor.call_args.args[0])
                draft = parse_score(open_editor.call_args.kwargs["initial_text"])
                self.assertEqual(len(draft.notes), 1)
                self.assertEqual(draft.notes[0].degree, 1)
            finally:
                window.close()

    def test_score_list_can_sort_by_time_and_title(self) -> None:
        """曲谱列表应能在最近修改和首字母顺序之间切换。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"KEYSCORE_DATA_DIR": directory},
        ):
            manager = ThemeManager(self.application, ThemeId.FLUENT)
            window = MainWindow(manager, Path(directory) / "app_settings.json")
            try:
                first = window.library.save_score_text("@title A曲\n1")
                second = window.library.save_score_text("@title B曲\n1")
                chinese_a = window.library.save_score_text("@title 安河桥\n1")
                chinese_y = window.library.save_score_text("@title 云宫迅音\n1")
                now = time.time()
                os.utime(first.path, (now + 10, now + 10))
                os.utime(second.path, (now + 20, now + 20))
                window._refresh_library()
                self.assertEqual(window.playlist.item(0).text(), "B曲")

                window.score_sort_button.click()
                self.assertEqual(window.playlist.item(0).text(), "A曲")
                titles = [
                    window.playlist.item(index).text()
                    for index in range(window.playlist.count())
                ]
                self.assertLess(titles.index(chinese_a.title), titles.index(chinese_y.title))
                self.assertIn(
                    "英文/拼音",
                    str(window.score_sort_button.property("hoverHint")),
                )
            finally:
                window.close()

    def test_delete_profile_keeps_one_profile_and_switches(self) -> None:
        """删除当前方案后应切换到剩余方案，最后一个方案不可删除。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"KEYSCORE_DATA_DIR": directory},
        ):
            manager = ThemeManager(self.application, ThemeId.FLUENT)
            window = MainWindow(manager, Path(directory) / "app_settings.json")
            try:
                second = default_profile()
                second.name = "第二方案"
                save_profile(
                    second,
                    window.profiles_directory / "第二方案.ksprofile.json",
                )
                window._refresh_profile_combo()
                target = window.profile_path
                with patch.object(
                    QMessageBox,
                    "question",
                    return_value=QMessageBox.StandardButton.Yes,
                ):
                    window._delete_profile()
                self.assertFalse(target.exists())
                self.assertEqual(window.profile_combo.count(), 1)
                self.assertFalse(window.profile_page.delete_profile_button.isEnabled())
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
                window.duration_hotkey_edit.setKeySequence(QKeySequence("Ctrl+D"))
                window.duration_presets_edit.setText("1/8, 1/2, 3/4, 1, 3")
                window.default_duration_edit.setText("3/4")
                with patch.object(window.hotkeys, "configure", return_value=True):
                    window._save_hotkey_settings()

                settings = load_app_settings(settings_path)
                self.assertEqual(settings.record_hotkey, "Ctrl+F8")
                self.assertEqual(settings.play_hotkey, "Alt+P")
                self.assertEqual(settings.stop_hotkey, "Shift+F10")
                self.assertEqual(settings.duration_cycle_hotkey, "Ctrl+D")
                self.assertEqual(settings.default_note_duration, "3/4")
                self.assertEqual(settings.duration_presets[-1], "3")
                self.assertIn("Ctrl+F8 录制", window.shortcut_hint.text())
                self.assertIn("Alt+P 播放", window.shortcut_hint.text())
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
