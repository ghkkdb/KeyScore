"""主窗口按键映射页面测试。"""

import os
from unittest import TestCase

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from keyscore.models import GameProfile, MappingMode, default_profile
from keyscore.profile_page import ProfileMappingPage
from keyscore.window_chrome import SmoothComboBox, SmoothSpinBox


class ProfileMappingPageTests(TestCase):
    """验证 Profile 页面在全部映射模式下保持可编辑。"""

    application: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        """为全部页面测试创建一个共享 QApplication。"""

        cls.application = QApplication.instance() or QApplication([])

    def test_load_profile_and_switch_all_mapping_modes(self) -> None:
        """加载 Profile 后全部映射布局均可重建。"""

        page = ProfileMappingPage()
        page.load_profile(default_profile())

        self.assertIsInstance(page.mode_combo, SmoothComboBox)
        self.assertIsInstance(page.output_mode_combo, SmoothComboBox)
        self.assertIsInstance(page.hold_spin, SmoothSpinBox)
        self.assertIsInstance(page.gap_spin, SmoothSpinBox)

        self.assertFalse(page.has_unsaved_changes)
        for mode in MappingMode:
            page.mode_combo.setCurrentIndex(page.mode_combo.findData(mode.value))
            self.application.processEvents()
            self.assertGreater(page.mapping_layout.count(), 0)

    def test_name_change_emits_save_request(self) -> None:
        """方案名称变化后保存按钮启用并提交草稿。"""

        page = ProfileMappingPage()
        page.load_profile(default_profile())
        captured: list[tuple[GameProfile, str]] = []
        page.save_requested.connect(
            lambda profile, name: captured.append((profile, name))
        )

        page.name_edit.setText("新的方案")
        page.save_button.click()

        self.assertTrue(page.has_unsaved_changes)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][1], "新的方案")

    def test_five_row_mode_builds_exactly_five_note_rows(self) -> None:
        """五行音区模式应显示五个行标题和三十五个绑定按钮。"""

        page = ProfileMappingPage()
        page.load_profile(default_profile())
        page.mode_combo.setCurrentIndex(
            page.mode_combo.findData(MappingMode.FIVE_ROW_OCTAVE.value)
        )
        grid = page.mapping_layout.itemAt(0).layout()
        self.assertIsNotNone(grid)
        assert grid is not None
        self.assertEqual(grid.count(), 47)
        self.assertIn("倍低", page.mapping_hint.text())
