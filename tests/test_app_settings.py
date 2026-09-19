"""应用级设置持久化测试。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from keyscore.app_settings import AppSettings, ThemeId, load_app_settings, save_app_settings


class AppSettingsTests(TestCase):
    """验证主题设置在异常输入下仍可安全启动。"""

    def test_missing_file_uses_fluent_theme(self) -> None:
        """设置文件不存在时默认使用 Fluent 主题。"""

        with TemporaryDirectory() as directory:
            settings = load_app_settings(Path(directory) / "app_settings.json")

        self.assertEqual(settings.theme, ThemeId.FLUENT)

    def test_theme_round_trip(self) -> None:
        """保存后可以恢复游戏电竞主题。"""

        with TemporaryDirectory() as directory:
            path = Path(directory) / "app_settings.json"
            save_app_settings(AppSettings(theme=ThemeId.ESPORTS), path)
            settings = load_app_settings(path)

        self.assertEqual(settings.theme, ThemeId.ESPORTS)

    def test_invalid_theme_falls_back_to_fluent(self) -> None:
        """未知主题标识不会阻止应用启动。"""

        with TemporaryDirectory() as directory:
            path = Path(directory) / "app_settings.json"
            path.write_text('{"theme": "unknown"}', encoding="utf-8")
            settings = load_app_settings(path)

        self.assertEqual(settings.theme, ThemeId.FLUENT)
