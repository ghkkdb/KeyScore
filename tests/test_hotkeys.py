"""可配置全局快捷键解析测试。"""

from unittest import TestCase

from keyscore.hotkeys import HotkeyValidationError, normalize_hotkey, parse_hotkey


class HotkeyParsingTests(TestCase):
    """验证用户输入的快捷键可以稳定转换为 Win32 注册参数。"""

    def test_function_key_is_supported(self) -> None:
        """单独功能键应保持规范名称。"""

        modifiers, virtual_key, label = parse_hotkey("f8")

        self.assertEqual(modifiers, 0)
        self.assertEqual(virtual_key, 0x77)
        self.assertEqual(label, "F8")

    def test_modifier_combination_is_normalized(self) -> None:
        """组合键应规范化修饰键和字母大小写。"""

        self.assertEqual(normalize_hotkey("ctrl+shift+r"), "Ctrl+Shift+R")

    def test_unsupported_or_multi_step_sequence_is_rejected(self) -> None:
        """不支持的主键和多段快捷键应被拒绝。"""

        with self.assertRaises(HotkeyValidationError):
            normalize_hotkey("Ctrl+F8, F9")
        with self.assertRaises(HotkeyValidationError):
            normalize_hotkey("Ctrl++")
