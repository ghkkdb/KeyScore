"""钢琴卷帘可编辑文档测试。"""

from __future__ import annotations

import unittest
from fractions import Fraction

from keyscore.models import Octave
from keyscore.parser import parse_score
from keyscore.score_document import (
    RollPitch,
    add_note,
    document_from_text,
    pitch_from_index,
    pitch_index,
    pitch_text,
    remove_note,
    serialize_document,
)


class ScoreDocumentTests(unittest.TestCase):
    """验证文本曲谱与受约束卷帘时间轴能够安全往返。"""

    def test_round_trip_preserves_timing_chords_and_legato(self) -> None:
        """序列化后应保留休止、和弦、时值和连音语义。"""

        source = "@title 往返\n@bpm 120\n@beat 4/4\n\n0:0.5 (1:0.5 2) [3 5]:2"
        document = document_from_text(source)
        result = parse_score(serialize_document(document))

        self.assertEqual(result.title, "往返")
        self.assertEqual(result.notes[0].start_beat, Fraction(1, 2))
        self.assertTrue(result.notes[0].legato_to_next)
        self.assertEqual(result.notes[-1].duration_beats, Fraction(2))
        self.assertEqual(result.total_beats, Fraction(4))

    def test_add_same_start_creates_chord(self) -> None:
        """相同开始拍的新音符应合并进现有和弦。"""

        document = document_from_text("1 2")
        result = add_note(
            document,
            Fraction(0),
            Fraction(1),
            RollPitch(Octave.MIDDLE, 3),
        )

        self.assertEqual(len(result.groups), 2)
        self.assertEqual(len(result.groups[0].pitches), 2)
        self.assertIn("[1 3]", serialize_document(result))

    def test_overlapping_independent_voice_is_rejected(self) -> None:
        """当前文本格式无法表达的独立重叠声部应被拒绝。"""

        document = document_from_text("1:2 2")
        with self.assertRaisesRegex(ValueError, "重叠"):
            add_note(
                document,
                Fraction(1),
                Fraction(1),
                RollPitch(Octave.MIDDLE, 3),
            )

    def test_remove_note_returns_new_document(self) -> None:
        """删除音符应生成新的不可变文档。"""

        document = document_from_text("1 2 3")
        removed = remove_note(document, 1, RollPitch(Octave.MIDDLE, 2))

        self.assertEqual(len(document.groups), 3)
        self.assertEqual(len(removed.groups), 2)

    def test_all_visual_pitch_indices_round_trip(self) -> None:
        """五音区内六十个半音行都应能稳定映射。"""

        for index in range(60):
            with self.subTest(index=index):
                self.assertEqual(pitch_index(pitch_from_index(index)), index)

    def test_semitone_text_keeps_sharp_marker(self) -> None:
        """半音在音高轴和音符块上应保留井号标记。"""

        self.assertEqual(pitch_text(RollPitch(Octave.MIDDLE, 1, True)), "#1")

    def test_removing_legato_target_clears_previous_connection(self) -> None:
        """删除连音目标后不应留下无法序列化的悬空连接。"""

        document = document_from_text("(1 2) 3")
        result = remove_note(
            document,
            1,
            RollPitch(Octave.MIDDLE, 2),
        )

        self.assertFalse(result.groups[0].legato_to_next)
        parse_score(serialize_document(result))


if __name__ == "__main__":
    unittest.main()
