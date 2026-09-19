"""曲谱库与按键配置持久化测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from keyscore.library import ScoreLibrary, rename_score_file
from keyscore.models import (
    Binding,
    BindingKind,
    MappingMode,
    NoteOutputMode,
    default_profile,
)
from keyscore.profile_store import (
    import_profile,
    list_profile_paths,
    load_active_profile,
    load_profile,
    profile_path_for_name,
    save_active_profile,
    save_profile,
    save_profile_with_name,
)


class LibraryTests(unittest.TestCase):
    """验证本地曲谱扫描、导入和按键配置保存。"""

    def test_create_and_import_score(self) -> None:
        """新建和导入曲谱都应出现在歌单扫描结果中。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = ScoreLibrary(root)
            created = library.create_score("测试曲")
            source = root / "source.txt"
            source.write_text("@title 导入曲\n@bpm 120\n\n1 2 3\n", encoding="utf-8")
            imported = library.import_score(source)
            paths = {entry.path for entry in library.entries()}
            self.assertIn(created.path, paths)
            self.assertIn(imported.path, paths)
            self.assertEqual(imported.path.stem, "导入曲")

    def test_rename_score_file_uses_title_and_preserves_duplicates(self) -> None:
        """保存曲谱时应按标题改名，重名时不得覆盖已有文件。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "未命名曲谱.txt"
            second = root / "另一个文件.txt"
            first.write_text("1", encoding="utf-8")
            second.write_text("2", encoding="utf-8")
            first_result = rename_score_file(first, "测试/曲谱")
            second_result = rename_score_file(second, "测试曲谱")
            self.assertEqual(first_result.name, "测试曲谱.txt")
            self.assertEqual(second_result.name, "测试曲谱 2.txt")
            self.assertEqual(first_result.read_text(encoding="utf-8"), "1")
            self.assertEqual(second_result.read_text(encoding="utf-8"), "2")

    def test_delete_score_removes_only_library_entry(self) -> None:
        """删除曲谱应移除库内文件，且拒绝库外目标。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = ScoreLibrary(root)
            created = library.create_score("待删除")
            library.delete_score(created)
            self.assertFalse(created.path.exists())
            external = ScoreLibrary(root).create_score("保留")
            with self.assertRaises(ValueError):
                library.delete_score(type(created)("外部", root / "外部.txt"))
            self.assertTrue(external.path.exists())

    def test_profile_round_trip_keeps_binding(self) -> None:
        """自定义扫描码和扩展键标志应完整保存。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            profile = default_profile()
            profile.note_bindings[1] = Binding(BindingKind.KEYBOARD, 0x48, "Up", True)
            save_profile(profile, path)
            restored = load_profile(path)
            self.assertEqual(restored.note_bindings[1], profile.note_bindings[1])

    def test_profile_round_trip_keeps_mapping_mode_and_direct_notes(self) -> None:
        """新版 Profile 应保留映射模式和直接音符映射。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = default_profile()
            profile.mapping_mode = MappingMode.DIRECT_NOTE
            profile.note_output_mode = NoteOutputMode.HOLD
            profile.direct_note_bindings["middle:0:1"] = Binding(
                BindingKind.KEYBOARD, 0x10, "Q"
            )
            path = profile_path_for_name(root, "我的方案")
            save_profile(profile, path)
            restored = load_profile(path)
            self.assertEqual(restored.mapping_mode, MappingMode.DIRECT_NOTE)
            self.assertEqual(restored.note_output_mode, NoteOutputMode.HOLD)
            self.assertEqual(restored.direct_note_bindings, profile.direct_note_bindings)
            self.assertEqual(list_profile_paths(root), [path])

    def test_five_row_profile_round_trip_keeps_outer_octaves(self) -> None:
        """五行模式及倍低、倍高音绑定应完整持久化。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "五行.ksprofile.json"
            profile = default_profile()
            profile.mapping_mode = MappingMode.FIVE_ROW_OCTAVE
            profile.direct_note_bindings["lowest:0:1"] = Binding(
                BindingKind.KEYBOARD, 0x10, "Q"
            )
            profile.direct_note_bindings["highest:0:7"] = Binding(
                BindingKind.KEYBOARD, 0x11, "W"
            )
            save_profile(profile, path)
            restored = load_profile(path)
            self.assertEqual(restored.mapping_mode, MappingMode.FIVE_ROW_OCTAVE)
            self.assertEqual(
                restored.direct_note_bindings,
                profile.direct_note_bindings,
            )
            self.assertIn('"version": 4', path.read_text(encoding="utf-8"))

    def test_legacy_profile_defaults_to_tap_output(self) -> None:
        """缺少输出方式字段的旧 Profile 应保持原有短按行为。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "旧配置.ksprofile.json"
            profile = default_profile()
            save_profile(profile, path)
            text = path.read_text(encoding="utf-8")
            text = text.replace('  "note_output_mode": "tap",\n', "")
            path.write_text(text, encoding="utf-8")
            self.assertEqual(load_profile(path).note_output_mode, NoteOutputMode.TAP)

    def test_virtual_piano_profile_migrates_to_direct_note(self) -> None:
        """已移除的虚拟钢琴模式应兼容迁移为直接音符映射。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "旧钢琴.ksprofile.json"
            profile = default_profile()
            profile.mapping_mode = MappingMode.DIRECT_NOTE
            save_profile(profile, path)
            text = path.read_text(encoding="utf-8").replace(
                '"mapping_mode": "direct_note"',
                '"mapping_mode": "virtual_piano"',
            )
            path.write_text(text, encoding="utf-8")
            self.assertEqual(load_profile(path).mapping_mode, MappingMode.DIRECT_NOTE)

    def test_profile_discards_legacy_eighth_note_binding(self) -> None:
        """读取旧 Profile 时应移除已废弃的独立高音 Do 绑定。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(
                '{"name":"旧配置","notes":{"8":{"kind":"keyboard","code":37,"label":"K"}},'
                '"zones":{},"semitone":{"kind":"mouse","code":3,"label":"鼠标中键"}}',
                encoding="utf-8",
            )
            restored = load_profile(path)
            self.assertNotIn(8, restored.note_bindings)

    def test_import_profile_creates_local_copy_and_keeps_existing(self) -> None:
        """导入 Profile 应创建不覆盖已有方案的本地持久化副本。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "外部.ksprofile.json"
            target_directory = root / "profiles"
            profile = default_profile()
            profile.name = "游戏配置"
            save_profile(profile, source)
            first = import_profile(source, target_directory)
            second = import_profile(source, target_directory)
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertNotEqual(first, second)
            self.assertEqual(load_profile(first).name, "游戏配置")

    def test_import_profile_rejects_invalid_file(self) -> None:
        """导入时应拒绝无法解析的 Profile，而不是回退到默认配置。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "损坏.ksprofile.json"
            source.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                import_profile(source, root / "profiles")

    def test_active_profile_round_trip(self) -> None:
        """应用重启时应能恢复上次选中的配置方案。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profiles = root / "profiles"
            path = profile_path_for_name(profiles, "当前方案")
            save_profile(default_profile(), path)
            state_path = root / "profile_state.json"
            save_active_profile(path, state_path)
            self.assertEqual(load_active_profile(profiles, state_path), path)

    def test_save_profile_with_name_creates_new_named_profile(self) -> None:
        """保存时修改方案名称应保留旧方案并创建新的命名方案。"""

        with tempfile.TemporaryDirectory() as directory:
            profiles = Path(directory) / "profiles"
            profile = default_profile()
            old_path = profile_path_for_name(profiles, profile.name)
            save_profile(profile, old_path)
            new_path = save_profile_with_name(profile, old_path, profiles, "三角洲方案")
            self.assertTrue(old_path.exists())
            self.assertTrue(new_path.exists())
            self.assertEqual(len(list_profile_paths(profiles)), 2)
            self.assertEqual(load_profile(old_path).name, "默认配置")
            self.assertEqual(load_profile(new_path).name, "三角洲方案")

    def test_save_profile_with_name_rejects_duplicate(self) -> None:
        """重命名方案时不得覆盖已有的同名 Profile。"""

        with tempfile.TemporaryDirectory() as directory:
            profiles = Path(directory) / "profiles"
            profile = default_profile()
            first = profile_path_for_name(profiles, "方案一")
            second = profile_path_for_name(profiles, "方案二")
            save_profile(profile, first)
            save_profile(profile, second)
            with self.assertRaises(ValueError):
                save_profile_with_name(profile, first, profiles, "方案二")


if __name__ == "__main__":
    unittest.main()
