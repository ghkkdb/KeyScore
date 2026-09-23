"""Windows 权限比较和提权启动参数测试。"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from keyscore.app import parse_startup_arguments
from keyscore.windows_privileges import IntegrityComparison, compare_window_integrity


class WindowsPrivilegesTests(unittest.TestCase):
    """验证权限关系判断和管理员重启状态恢复参数。"""

    def test_target_higher_integrity_requires_elevation(self) -> None:
        """目标完整性级别更高时应要求提升权限。"""

        with (
            patch(
                "keyscore.windows_privileges.current_process_integrity_level",
                return_value=0x2000,
            ),
            patch(
                "keyscore.windows_privileges.window_process_integrity_level",
                return_value=0x3000,
            ),
        ):
            result = compare_window_integrity(123)

        self.assertIs(result, IntegrityComparison.TARGET_HIGHER)

    def test_equal_or_lower_integrity_is_compatible(self) -> None:
        """目标权限不高于 KeyScore 时应允许继续播放。"""

        with (
            patch(
                "keyscore.windows_privileges.current_process_integrity_level",
                return_value=0x3000,
            ),
            patch(
                "keyscore.windows_privileges.window_process_integrity_level",
                return_value=0x2000,
            ),
        ):
            result = compare_window_integrity(123)

        self.assertIs(result, IntegrityComparison.COMPATIBLE)

    def test_unreadable_integrity_is_unknown(self) -> None:
        """任一进程权限无法读取时不应误判为普通权限。"""

        with (
            patch(
                "keyscore.windows_privileges.current_process_integrity_level",
                return_value=0x2000,
            ),
            patch(
                "keyscore.windows_privileges.window_process_integrity_level",
                return_value=None,
            ),
        ):
            result = compare_window_integrity(123)

        self.assertIs(result, IntegrityComparison.UNKNOWN)

    def test_startup_arguments_restore_elevated_score(self) -> None:
        """提权后的新实例应解析恢复曲谱路径并保留 Qt 参数。"""

        restarted, score_path, remaining = parse_startup_arguments(
            [
                "--restarted-elevated",
                "--resume-score",
                "D:/Scores/测试曲谱.txt",
                "-platform",
                "windows",
            ]
        )

        self.assertTrue(restarted)
        self.assertEqual(score_path, Path("D:/Scores/测试曲谱.txt"))
        self.assertEqual(remaining, ["-platform", "windows"])


if __name__ == "__main__":
    unittest.main()
