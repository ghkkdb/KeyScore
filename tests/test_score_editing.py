"""曲谱编辑器纯文本变换测试。"""

from __future__ import annotations

import unittest

from keyscore.score_editing import set_total_duration


class ScoreEditingTests(unittest.TestCase):
    """验证总时值快捷编辑不会破坏曲谱结构。"""

    def test_sets_and_replaces_single_note_duration(self) -> None:
        """应添加或替换光标所在音符的总时值。"""

        source = "1 H3:0.25 4"
        result = set_total_duration(source, source.index("H3") + 1, source.index("H3") + 1, "0.5")
        self.assertEqual(result.text, "1 H3:0.5 4")
        self.assertEqual(result.changed_count, 1)

    def test_one_beat_uses_implicit_notation(self) -> None:
        """一拍应删除冗余的时值后缀。"""

        result = set_total_duration("H3:2", 2, 2, "1")
        self.assertEqual(result.text, "H3")

    def test_sets_chord_and_rest_duration(self) -> None:
        """和弦与休止符也应支持总时值快捷编辑。"""

        source = "[1 3 5]:2 0:2"
        chord = set_total_duration(source, 1, 1, "0.5")
        rest_start = chord.text.index("0:2")
        rest = set_total_duration(chord.text, rest_start, rest_start, "0.75")
        self.assertEqual(rest.text, "[1 3 5]:0.5 0:0.75")

    def test_sets_duration_inside_legato_group(self) -> None:
        """总时值快捷编辑应能识别连音组内的音符。"""

        source = "(1 H2:2 3)"
        position = source.index("H2")
        result = set_total_duration(source, position, position, "0.5")
        self.assertEqual(result.text, "(1 H2:0.5 3)")

    def test_sets_duration_on_outer_octave_notes(self) -> None:
        """倍低音和倍高音词元应支持总时值快捷编辑。"""

        source = "LL1 HH7:2"
        low = set_total_duration(source, 1, 1, "0.5")
        high_position = low.text.index("HH7")
        high = set_total_duration(low.text, high_position, high_position, "1")
        self.assertEqual(high.text, "LL1:0.5 HH7")

    def test_selection_updates_complete_tokens(self) -> None:
        """选择区域内的完整可编辑词元应批量更新。"""

        source = "1 H2:2 | [1 3 5] 4"
        result = set_total_duration(source, 0, source.index(" 4"), "1.5")
        self.assertEqual(result.text, "1:1.5 H2:1.5 | [1 3 5]:1.5 4")
        self.assertEqual(result.changed_count, 3)

    def test_setting_total_duration_removes_sustain_dashes(self) -> None:
        """设置精确总时值时应删除跨小节的关联增时线。"""

        source = "1 - | - 2"
        result = set_total_duration(source, 0, 0, "0.5")
        self.assertEqual(result.text, "1:0.5 | 2")

    def test_setting_duration_removes_consecutive_sustain_dashes(self) -> None:
        """连续增时线及其相邻空格应一次清理干净。"""

        result = set_total_duration("1 - - - 2", 0, 0, "0.75")
        self.assertEqual(result.text, "1:0.75 2")

    def test_section_break_stops_sustain_cleanup(self) -> None:
        """段落标记应阻止清理继续影响后续内容。"""

        source = "1 -\n---\n- 2"
        result = set_total_duration(source, 0, 0, "2")
        self.assertEqual(result.text, "1:2\n---\n- 2")

    def test_metadata_and_bar_are_not_editable(self) -> None:
        """元数据和小节线上的光标不应触发修改。"""

        source = "@bpm 100\n1 | 2"
        metadata = set_total_duration(source, 2, 2, "0.5")
        bar_position = source.index("|")
        bar = set_total_duration(source, bar_position, bar_position, "0.5")
        self.assertEqual(metadata.changed_count, 0)
        self.assertEqual(bar.changed_count, 0)
        self.assertEqual(bar.text, source)

    def test_invalid_duration_is_rejected(self) -> None:
        """零、负数和非十进制格式不应进入曲谱。"""

        for duration in ("0", "-1", "1/2", "abc"):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                set_total_duration("1", 0, 0, duration)


if __name__ == "__main__":
    unittest.main()
