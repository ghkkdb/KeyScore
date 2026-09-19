"""绝对时间轴编译器测试。"""

from __future__ import annotations

import unittest

from keyscore.compiler import PlanCompileError, compile_score
from keyscore.models import (
    ActionType,
    Binding,
    BindingKind,
    MappingMode,
    NoteOutputMode,
    default_profile,
    note_binding_key,
)
from keyscore.parser import parse_score


class CompilerTests(unittest.TestCase):
    """验证音区操作、音符按压和时间轴排序。"""

    def test_middle_note_has_no_modifier(self) -> None:
        """中音是默认状态，不应发送鼠标修饰键。"""

        profile = default_profile()
        plan = compile_score(parse_score("@bpm 120\n1"), profile)
        self.assertEqual(len(plan.events), 2)
        self.assertEqual(plan.events[0].binding.label, "A")
        self.assertEqual(plan.events[0].action, ActionType.PRESS)

    def test_high_note_holds_high_modifier(self) -> None:
        """高音应先按下高音修饰键，再发送音符。"""

        plan = compile_score(parse_score("@bpm 120\nH1"), default_profile())
        self.assertEqual(plan.events[0].binding.label, "鼠标右键")
        note_press = next(
            event for event in plan.events if event.note is not None and event.action is ActionType.PRESS
        )
        self.assertGreater(note_press.timestamp_ms, 0)

    def test_semitone_holds_middle_mouse(self) -> None:
        """`#` 音符应使用半音修饰键。"""

        plan = compile_score(parse_score("@bpm 120\n#1"), default_profile())
        self.assertEqual(plan.events[0].binding.label, "鼠标中键")

    def test_timeline_uses_absolute_beat_positions(self) -> None:
        """后续音符时间应由拍位直接计算，而非累加按键时长。"""

        plan = compile_score(parse_score("@bpm 120\n1 2:2 3"), default_profile())
        note_presses = [
            event for event in plan.events if event.note is not None and event.action is ActionType.PRESS
        ]
        self.assertEqual([event.timestamp_ms for event in note_presses], [0.0, 500.0, 1500.0])
        self.assertEqual(plan.duration_ms, 2000.0)

    def test_cross_octave_chord_is_rejected(self) -> None:
        """全局音区修饰键无法表达跨音区和弦，应拒绝编译。"""

        profile = default_profile()
        with self.assertRaises(PlanCompileError):
            compile_score(parse_score("[L1 H1]"), profile)

    def test_hold_duration_preserves_release_gap(self) -> None:
        """按键时长过大时应截断，为下一个音符保留最小释放间隔。"""

        profile = default_profile()
        profile.key_hold_ms = 100
        profile.key_gap_ms = 10
        plan = compile_score(parse_score("@bpm 120\n7:0.1 7:0.1"), profile)
        note_events = [event for event in plan.events if event.note is not None]
        self.assertEqual(note_events[1].timestamp_ms, 40.0)
        self.assertEqual(note_events[2].timestamp_ms, 50.0)

    def test_tap_mode_uses_fixed_key_hold_duration(self) -> None:
        """短按触发模式不应因为音符时值较长而延长实际按键。"""

        profile = default_profile()
        plan = compile_score(parse_score("@bpm 120\n1:2"), profile)
        note_events = [event for event in plan.events if event.note is not None]
        self.assertEqual(note_events[1].timestamp_ms, 50.0)

    def test_hold_mode_uses_note_duration(self) -> None:
        """持续按住模式应保持到音符结束前的最小释放间隔。"""

        profile = default_profile()
        profile.note_output_mode = NoteOutputMode.HOLD
        profile.key_gap_ms = 10
        plan = compile_score(parse_score("@bpm 120\n1:2 2"), profile)
        note_events = [event for event in plan.events if event.note is not None]
        self.assertEqual(note_events[1].timestamp_ms, 990.0)
        self.assertEqual(note_events[2].timestamp_ms, 1000.0)

    def test_hold_mode_uses_sustain_dash_duration(self) -> None:
        """持续按住模式应使用增时线扩展后的完整音符时值。"""

        profile = default_profile()
        profile.note_output_mode = NoteOutputMode.HOLD
        profile.key_gap_ms = 10
        plan = compile_score(parse_score("@bpm 120\n1 - - - 2"), profile)
        note_events = [event for event in plan.events if event.note is not None]
        self.assertEqual(note_events[1].timestamp_ms, 1990.0)
        self.assertEqual(note_events[2].timestamp_ms, 2000.0)

    def test_hold_mode_connects_different_legato_notes_without_gap(self) -> None:
        """持续按住模式下，异键连音应在下一音起点才释放旧音。"""

        profile = default_profile()
        profile.note_output_mode = NoteOutputMode.HOLD
        profile.key_gap_ms = 10
        plan = compile_score(parse_score("@bpm 120\n(1 2)"), profile)
        note_events = [event for event in plan.events if event.note is not None]
        self.assertEqual(note_events[1].timestamp_ms, 500.0)
        self.assertEqual(note_events[2].timestamp_ms, 500.0)
        self.assertEqual(note_events[1].action, ActionType.RELEASE)
        self.assertEqual(note_events[2].action, ActionType.PRESS)

    def test_tap_mode_does_not_extend_legato_notes(self) -> None:
        """短按触发模式不应因连音标记改变固定按键时长。"""

        profile = default_profile()
        profile.note_output_mode = NoteOutputMode.TAP
        plan = compile_score(parse_score("@bpm 120\n(1 2)"), profile)
        note_events = [event for event in plan.events if event.note is not None]
        self.assertEqual(note_events[1].timestamp_ms, 50.0)

    def test_legato_same_binding_preserves_release_gap(self) -> None:
        """连续使用同一物理键时应保留释放间隔以避免吞键。"""

        profile = default_profile()
        profile.note_output_mode = NoteOutputMode.HOLD
        profile.key_gap_ms = 10
        plan = compile_score(parse_score("@bpm 120\n(1 1)"), profile)
        note_events = [event for event in plan.events if event.note is not None]
        self.assertEqual(note_events[1].timestamp_ms, 490.0)
        self.assertEqual(note_events[2].timestamp_ms, 500.0)

    def test_legato_waits_for_next_modifier_transition(self) -> None:
        """跨音区连音应保持旧音至新音完成修饰键切换。"""

        profile = default_profile()
        profile.note_output_mode = NoteOutputMode.HOLD
        plan = compile_score(parse_score("@bpm 120\n(1 H2)"), profile)
        note_events = [event for event in plan.events if event.note is not None]
        first_release = next(
            event
            for event in note_events
            if event.note.degree == 1 and event.action is ActionType.RELEASE
        )
        second_press = next(
            event
            for event in note_events
            if event.note.degree == 2 and event.action is ActionType.PRESS
        )
        self.assertEqual(first_release.timestamp_ms, second_press.timestamp_ms)
        self.assertEqual(second_press.timestamp_ms, 535.0)

    def test_direct_note_mapping_allows_cross_octave_chord(self) -> None:
        """直接映射方案应能表达不同音区构成的同一和弦。"""

        score = parse_score("[L1 H1]")
        profile = default_profile()
        profile.mapping_mode = MappingMode.DIRECT_NOTE
        for note in score.notes:
            profile.direct_note_bindings[note_binding_key(note)] = profile.note_bindings[note.degree]
        plan = compile_score(score, profile)
        presses = [event for event in plan.events if event.action is ActionType.PRESS]
        self.assertEqual(len(presses), 2)
        self.assertTrue(all(event.timestamp_ms == 0 for event in presses))

    def test_row_octave_mapping_rejects_semitone(self) -> None:
        """三行音区模式只有三行自然音，不应读取隐藏的半音绑定。"""

        score = parse_score("#1")
        profile = default_profile()
        profile.mapping_mode = MappingMode.ROW_OCTAVE
        profile.direct_note_bindings[note_binding_key(score.notes[0])] = profile.note_bindings[1]
        with self.assertRaisesRegex(PlanCompileError, "不支持半音"):
            compile_score(score, profile)

    def test_five_row_octave_mapping_uses_outer_octaves(self) -> None:
        """五行音区模式应通过直接绑定播放倍低音和倍高音。"""

        score = parse_score("LL1 HH7")
        profile = default_profile()
        profile.mapping_mode = MappingMode.FIVE_ROW_OCTAVE
        profile.direct_note_bindings[note_binding_key(score.notes[0])] = Binding(
            BindingKind.KEYBOARD, 0x10, "Q"
        )
        profile.direct_note_bindings[note_binding_key(score.notes[1])] = Binding(
            BindingKind.KEYBOARD, 0x11, "W"
        )
        plan = compile_score(score, profile)
        presses = [event for event in plan.events if event.action is ActionType.PRESS]
        self.assertEqual([event.binding.code for event in presses], [0x10, 0x11])

    def test_five_row_octave_mapping_rejects_semitone(self) -> None:
        """五行音区模式与三行模式一致，不应读取半音绑定。"""

        score = parse_score("#HH1")
        profile = default_profile()
        profile.mapping_mode = MappingMode.FIVE_ROW_OCTAVE
        profile.direct_note_bindings[note_binding_key(score.notes[0])] = Binding(
            BindingKind.KEYBOARD, 0x10, "Q"
        )
        with self.assertRaisesRegex(PlanCompileError, "不支持半音"):
            compile_score(score, profile)

if __name__ == "__main__":
    unittest.main()
