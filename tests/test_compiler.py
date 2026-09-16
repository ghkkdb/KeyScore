"""绝对时间轴编译器测试。"""

from __future__ import annotations

import unittest

from keyscore.compiler import PlanCompileError, compile_score
from keyscore.models import ActionType, default_profile
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
        plan = compile_score(parse_score("@bpm 120\n8:0.1 8:0.1"), profile)
        note_events = [event for event in plan.events if event.note is not None]
        self.assertEqual(note_events[1].timestamp_ms, 40.0)
        self.assertEqual(note_events[2].timestamp_ms, 50.0)


if __name__ == "__main__":
    unittest.main()
