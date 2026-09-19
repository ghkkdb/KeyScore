"""主窗口按键映射页面测试。"""

import os
from unittest import TestCase

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from keyscore.models import GameProfile, MappingMode, default_profile
from keyscore.profile_page import ProfileMappingPage


class ProfileMappingPageTests(TestCase):
    """验证 Profile 页面在三种映射模式下保持可编辑。"""

    application: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        """为全部页面测试创建一个共享 QApplication。"""

        cls.application = QApplication.instance() or QApplication([])

    def test_load_profile_and_switch_all_mapping_modes(self) -> None:
        """加载 Profile 后三种映射布局均可重建。"""

        page = ProfileMappingPage()
        page.load_profile(default_profile())

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
