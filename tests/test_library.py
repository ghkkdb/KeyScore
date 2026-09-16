"""曲谱库与按键配置持久化测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from keyscore.library import ScoreLibrary
from keyscore.models import Binding, BindingKind, default_profile
from keyscore.profile_store import load_profile, save_profile


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

    def test_profile_round_trip_keeps_binding(self) -> None:
        """自定义扫描码和扩展键标志应完整保存。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            profile = default_profile()
            profile.note_bindings[1] = Binding(BindingKind.KEYBOARD, 0x48, "Up", True)
            save_profile(profile, path)
            restored = load_profile(path)
            self.assertEqual(restored.note_bindings[1], profile.note_bindings[1])


if __name__ == "__main__":
    unittest.main()
