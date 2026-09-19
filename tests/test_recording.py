"""游戏演奏录制、反向映射和量化转谱测试。"""

from __future__ import annotations

import unittest
from fractions import Fraction

from keyscore.models import (
    Binding,
    BindingKind,
    MappingMode,
    NoteOutputMode,
    Octave,
    default_profile,
)
from keyscore.parser import parse_score
from keyscore.recording.decoder import (
    DecodedNoteStart,
    ProfileInputDecoder,
    RecordingDecodeError,
)
from keyscore.recording.models import (
    PhysicalInputEvent,
    RecordedNote,
    RecordingSettings,
    RecordingTake,
)
from keyscore.recording.session import RecordingSession
from keyscore.recording.transcriber import transcribe_take


class RecordingDecoderTests(unittest.TestCase):
    """验证三类输入映射的反向解码基础行为。"""

    def test_modifier_mapping_decodes_octave_and_semitone(self) -> None:
        """音区和半音修饰键应在音符按下时参与反向解码。"""

        profile = default_profile()
        decoder = ProfileInputDecoder(profile)
        low = profile.zone_bindings[Octave.LOW]
        semitone = profile.semitone_binding
        note = profile.note_bindings[1]
        decoder.feed(low, True, 0.0)
        decoder.feed(semitone, True, 1.0)
        started = decoder.feed(note, True, 2.0)
        self.assertEqual(started, DecodedNoteStart(1, Octave.LOW, True))
        completed = decoder.feed(note, False, 102.0)
        self.assertIsInstance(completed, RecordedNote)
        assert isinstance(completed, RecordedNote)
        self.assertEqual(completed.end_ms - completed.start_ms, 100.0)

    def test_direct_mapping_rejects_duplicate_binding(self) -> None:
        """同一物理键对应多个音符时必须阻止录制。"""

        profile = default_profile()
        profile.mapping_mode = MappingMode.DIRECT_NOTE
        binding = Binding(BindingKind.KEYBOARD, 30, "A")
        profile.direct_note_bindings = {
            "middle:0:1": binding,
            "middle:0:2": binding,
        }
        with self.assertRaises(RecordingDecodeError):
            ProfileInputDecoder(profile)

    def test_five_row_decoder_ignores_hidden_semitone_bindings(self) -> None:
        """五行模式应保留但不读取独立映射模式下的半音绑定。"""

        profile = default_profile()
        profile.mapping_mode = MappingMode.FIVE_ROW_OCTAVE
        binding = Binding(BindingKind.KEYBOARD, 30, "A")
        profile.direct_note_bindings = {
            "lowest:0:1": binding,
            "lowest:1:1": binding,
        }
        decoder = ProfileInputDecoder(profile)
        started = decoder.feed(binding, True, 0.0)
        self.assertEqual(started, DecodedNoteStart(1, Octave.LOWEST, False))

    def test_session_ignores_injected_input_and_closes_missing_release(self) -> None:
        """注入事件不应入谱，停止时应补齐缺失的释放事件。"""

        profile = default_profile()
        session = RecordingSession(profile)
        binding = profile.note_bindings[1]
        session.feed(PhysicalInputEvent(100.0, binding, True, injected=True))
        session.feed(PhysicalInputEvent(200.0, binding, True))
        take = session.finish(700.0)
        self.assertEqual(len(take.notes), 1)
        self.assertEqual(take.notes[0].start_ms, 0.0)
        self.assertEqual(take.notes[0].end_ms, 500.0)

    def test_session_excludes_focus_pause_from_timeline(self) -> None:
        """失焦暂停的实际时间不应变成曲谱中的长休止。"""

        profile = default_profile()
        session = RecordingSession(profile)
        first = profile.note_bindings[1]
        second = profile.note_bindings[2]
        session.feed(PhysicalInputEvent(100.0, first, True))
        session.feed(PhysicalInputEvent(200.0, first, False))
        session.pause(300.0)
        session.resume(1300.0)
        session.feed(PhysicalInputEvent(1400.0, second, True))
        session.feed(PhysicalInputEvent(1500.0, second, False))
        take = session.finish(1600.0)
        self.assertEqual(take.notes[1].start_ms, 300.0)


class RecordingTranscriberTests(unittest.TestCase):
    """验证录制时间轴到 KeyScore 文本的转换。"""

    def test_tap_mode_groups_chord_and_uses_inter_onset_duration(self) -> None:
        """短按模式应合并近同时音符，并以音符起点间隔作为时值。"""

        take = RecordingTake(
            (
                RecordedNote(0.0, 40.0, 1, Octave.MIDDLE),
                RecordedNote(20.0, 60.0, 3, Octave.MIDDLE),
                RecordedNote(500.0, 540.0, 5, Octave.MIDDLE),
            )
        )
        settings = RecordingSettings("和弦录制", 120, "4/4", Fraction(1, 4))
        text = transcribe_take(take, settings, NoteOutputMode.TAP)
        score = parse_score(text)
        self.assertIn("[1 3]", text)
        self.assertEqual(score.notes[0].duration_beats, Fraction(1))
        self.assertEqual(score.notes[2].start_beat, Fraction(1))

    def test_hold_mode_creates_rest_from_release_gap(self) -> None:
        """持续按住模式应把释放到下一次按下之间转换成休止符。"""

        take = RecordingTake(
            (
                RecordedNote(0.0, 250.0, 1, Octave.MIDDLE),
                RecordedNote(500.0, 750.0, 2, Octave.MIDDLE),
            )
        )
        settings = RecordingSettings("休止测试", 120, "4/4", Fraction(1, 4))
        text = transcribe_take(take, settings, NoteOutputMode.HOLD)
        self.assertIn("1:0.5 0:0.5 2:0.5", text)
        parse_score(text)

    def test_hold_mode_writes_parenthesized_legato(self) -> None:
        """相邻单音几乎无释放空隙时应生成圆括号连音。"""

        take = RecordingTake(
            (
                RecordedNote(0.0, 505.0, 1, Octave.MIDDLE),
                RecordedNote(500.0, 1000.0, 2, Octave.MIDDLE),
            )
        )
        settings = RecordingSettings("连音测试", 120, "4/4", Fraction(1, 4))
        text = transcribe_take(take, settings, NoteOutputMode.HOLD)
        self.assertIn("( 1 2 )", text)
        score = parse_score(text)
        self.assertTrue(score.notes[0].legato_to_next)

    def test_transcriber_writes_outer_octave_prefixes(self) -> None:
        """录制转谱应使用 LL 和 HH 保存最外侧两个音区。"""

        take = RecordingTake(
            (
                RecordedNote(0.0, 40.0, 1, Octave.LOWEST),
                RecordedNote(500.0, 540.0, 7, Octave.HIGHEST),
            )
        )
        settings = RecordingSettings("五音区录制", 120, "4/4", Fraction(1, 4))
        text = transcribe_take(take, settings, NoteOutputMode.TAP)
        self.assertIn("LL1 HH7", text)
        score = parse_score(text)
        self.assertEqual(score.notes[0].octave, Octave.LOWEST)
        self.assertEqual(score.notes[1].octave, Octave.HIGHEST)


if __name__ == "__main__":
    unittest.main()
