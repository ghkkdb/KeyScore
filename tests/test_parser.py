"""文本简谱解析器测试。"""

from __future__ import annotations

import unittest
from fractions import Fraction

from keyscore.models import Octave
from keyscore.parser import ScoreParseError, parse_score


class ScoreParserTests(unittest.TestCase):
    """验证基础音符、休止符、时值和和弦解析。"""

    def test_parse_basic_score(self) -> None:
        """基础曲谱应保留标题、BPM、音区和总拍数。"""

        score = parse_score("@title 测试\n@bpm 120\nL1 2 H3:2 | 0:0.5 4")
        self.assertEqual(score.title, "测试")
        self.assertEqual(score.bpm, 120)
        self.assertEqual(score.total_beats, Fraction(11, 2))
        self.assertEqual(len(score.notes), 4)
        self.assertEqual(score.notes[0].octave, Octave.LOW)
        self.assertEqual(score.notes[2].octave, Octave.HIGH)

    def test_chord_shares_start_time(self) -> None:
        """和弦中的所有音符应共享开始时间和时值。"""

        score = parse_score("[1 3 5]:2 6")
        self.assertEqual(len(score.notes), 4)
        self.assertTrue(all(note.start_beat == 0 for note in score.notes[:3]))
        self.assertTrue(all(note.duration_beats == 2 for note in score.notes[:3]))
        self.assertEqual(score.notes[3].start_beat, 2)

    def test_invalid_token_has_line_number(self) -> None:
        """非法音符应返回可用于编辑器定位的行号。"""

        with self.assertRaises(ScoreParseError) as context:
            parse_score("@bpm 100\n\n1 X9")
        self.assertEqual(context.exception.line, 3)

    def test_eight_is_not_a_valid_note(self) -> None:
        """独立高音 Do 已废弃，`8` 必须被拒绝。"""

        with self.assertRaises(ScoreParseError):
            parse_score("7 8:2")

    def test_sharp_marks_semitone_modifier(self) -> None:
        """`#` 前缀应记录为半音修饰而不改变基础音符。"""

        score = parse_score("#1 #H7:0.5")
        self.assertTrue(score.notes[0].is_semitone)
        self.assertEqual(score.notes[0].degree, 1)
        self.assertTrue(score.notes[1].is_semitone)
        self.assertEqual(score.notes[1].octave, Octave.HIGH)

    def test_section_break_uses_configured_gap(self) -> None:
        """独立段落标记应按配置的拍数推进后续音符。"""

        score = parse_score("@section_gap 1.5\n1\n---\n2")
        self.assertEqual(score.notes[0].start_beat, 0)
        self.assertEqual(score.notes[1].start_beat, Fraction(5, 2))
        self.assertEqual(score.total_beats, Fraction(7, 2))

    def test_section_break_defaults_to_one_beat(self) -> None:
        """未配置段落间隔时，段落标记应默认停顿一拍。"""

        score = parse_score("1\n---\n2")
        self.assertEqual(score.notes[1].start_beat, 2)

    def test_section_break_must_be_on_its_own_line(self) -> None:
        """段落标记混在音符行中时应报告语法错误。"""

        with self.assertRaises(ScoreParseError):
            parse_score("1 --- 2")

    def test_section_gap_must_be_positive(self) -> None:
        """段落间隔必须使用大于零的整数或小数拍数。"""

        with self.assertRaises(ScoreParseError) as context:
            parse_score("@section_gap 0\n1\n---\n2")
        self.assertEqual(context.exception.line, 1)

    def test_sustain_dashes_extend_previous_note(self) -> None:
        """每个增时线应给前一个音符增加一拍且不重复触发。"""

        score = parse_score("1 - - - | 2")
        self.assertEqual(len(score.notes), 2)
        self.assertEqual(score.notes[0].duration_beats, 4)
        self.assertEqual(score.notes[1].start_beat, 4)
        self.assertEqual(score.total_beats, 5)

    def test_sustain_dash_extends_chord_and_rest(self) -> None:
        """增时线应同时延长和弦内音符，也应能延长休止时间。"""

        score = parse_score("[1 3 5] - | 0 - 2")
        self.assertTrue(all(note.duration_beats == 2 for note in score.notes[:3]))
        self.assertEqual(score.notes[3].start_beat, 4)
        self.assertEqual(score.total_beats, 5)

    def test_sustain_dash_requires_previous_value(self) -> None:
        """曲谱开头或段落停顿后的增时线应给出明确错误。"""

        with self.assertRaisesRegex(ScoreParseError, "增时线前"):
            parse_score("- 1")
        with self.assertRaisesRegex(ScoreParseError, "增时线前"):
            parse_score("1\n---\n- 2")


if __name__ == "__main__":
    unittest.main()
