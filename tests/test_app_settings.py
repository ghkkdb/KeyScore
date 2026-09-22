"""应用级设置持久化测试。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from keyscore.app_settings import AppSettings, ThemeId, load_app_settings, save_app_settings


class AppSettingsTests(TestCase):
    """验证应用设置可以完整持久化并在异常输入下安全启动。"""

    def test_missing_file_uses_fluent_theme(self) -> None:
        """设置文件不存在时默认使用 Fluent 主题。"""

        with TemporaryDirectory() as directory:
            settings = load_app_settings(Path(directory) / "app_settings.json")

        self.assertEqual(settings.theme, ThemeId.FLUENT)
        self.assertEqual(settings.record_hotkey, "F8")
        self.assertEqual(settings.play_hotkey, "F9")
        self.assertEqual(settings.stop_hotkey, "F10")
        self.assertEqual(settings.duration_cycle_hotkey, "D")
        self.assertEqual(settings.duration_reverse_hotkey, "A")
        self.assertIn("3/4", settings.duration_presets)
        self.assertEqual(settings.default_note_duration, "1/4")
        self.assertTrue(settings.show_playback_overlay)
        self.assertEqual(settings.countdown_seconds, 3)
        self.assertTrue(settings.show_countdown_overlay)

    def test_theme_round_trip(self) -> None:
        """保存后可以恢复游戏电竞主题。"""

        with TemporaryDirectory() as directory:
            path = Path(directory) / "app_settings.json"
            save_app_settings(AppSettings(theme=ThemeId.ESPORTS), path)
            settings = load_app_settings(path)

        self.assertEqual(settings.theme, ThemeId.ESPORTS)

    def test_all_settings_round_trip(self) -> None:
        """快捷键和悬浮层选项保存后应完整恢复。"""

        with TemporaryDirectory() as directory:
            path = Path(directory) / "app_settings.json"
            expected = AppSettings(
                theme=ThemeId.ESPORTS,
                record_hotkey="Ctrl+F8",
                play_hotkey="Alt+P",
                stop_hotkey="Shift+F10",
                duration_cycle_hotkey="Ctrl+D",
                duration_reverse_hotkey="Ctrl+A",
                duration_presets=("1/8", "1/3", "3/4", "2"),
                default_note_duration="3/4",
                score_sort_mode="title",
                show_playback_overlay=False,
                countdown_seconds=6,
                show_countdown_overlay=False,
            )
            save_app_settings(expected, path)
            actual = load_app_settings(path)

        self.assertEqual(actual, expected)

    def test_invalid_theme_falls_back_to_fluent(self) -> None:
        """未知主题标识不会阻止应用启动。"""

        with TemporaryDirectory() as directory:
            path = Path(directory) / "app_settings.json"
            path.write_text('{"theme": "unknown"}', encoding="utf-8")
            settings = load_app_settings(path)

        self.assertEqual(settings.theme, ThemeId.FLUENT)

    def test_invalid_shortcuts_and_overlay_values_use_defaults(self) -> None:
        """无效快捷键、重复键和越界倒计时应回退到默认值。"""

        with TemporaryDirectory() as directory:
            path = Path(directory) / "app_settings.json"
            path.write_text(
                '{"record_hotkey":"F7","play_hotkey":"F7",'
                '"stop_hotkey":"unknown","countdown_seconds":0,'
                '"show_playback_overlay":"false","show_countdown_overlay":1}',
                encoding="utf-8",
            )
            settings = load_app_settings(path)

        self.assertEqual(
            (settings.record_hotkey, settings.play_hotkey, settings.stop_hotkey),
            ("F8", "F9", "F10"),
        )
        self.assertEqual(settings.countdown_seconds, 3)
        self.assertTrue(settings.show_playback_overlay)
        self.assertTrue(settings.show_countdown_overlay)
