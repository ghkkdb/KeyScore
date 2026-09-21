"""播放器急停与释放保障测试。"""

from __future__ import annotations

import time
import threading
import unittest

from keyscore.compiler import compile_score
from keyscore.input_backend import RecordingBackend, WindowsSendInputBackend
from keyscore.models import (
    ActionType,
    Binding,
    BindingKind,
    TimedInputEvent,
    default_profile,
)
from keyscore.parser import parse_score
from keyscore.playback import PlaybackState, TimelinePlayer


class PlaybackTests(unittest.TestCase):
    """验证正常结束和紧急停止都会释放所有按键。"""

    def test_completed_plan_releases_all(self) -> None:
        """播放完成后必须至少执行一次全部释放。"""

        backend = RecordingBackend()
        plan = compile_score(parse_score("@bpm 400\n1:0.05"), default_profile())
        player = TimelinePlayer(backend)
        player.load(plan)
        player.play()
        deadline = time.perf_counter() + 1.0
        while player.state is not PlaybackState.STOPPED and time.perf_counter() < deadline:
            time.sleep(0.005)
        self.assertEqual(player.state, PlaybackState.STOPPED)
        self.assertGreaterEqual(backend.release_count, 1)
        self.assertAlmostEqual(player.position_ms, plan.duration_ms)

    def test_stop_releases_all(self) -> None:
        """紧急停止应立即执行全部释放。"""

        backend = RecordingBackend()
        plan = compile_score(parse_score("@bpm 60\n1:4"), default_profile())
        player = TimelinePlayer(backend)
        player.load(plan)
        player.play()
        time.sleep(0.01)
        player.stop(wait=True)
        self.assertEqual(player.state, PlaybackState.STOPPED)
        self.assertGreaterEqual(backend.release_count, 1)
        self.assertEqual(player.position_ms, 0.0)

    def test_shared_combination_modifier_uses_reference_count(self) -> None:
        """重叠组合共享修饰键时不应被第一个释放事件提前松开。"""

        shift = Binding(BindingKind.KEYBOARD, 0x2A, "Shift")
        first = Binding(BindingKind.KEYBOARD, 0x1E, "A", modifiers=(shift,))
        second = Binding(BindingKind.KEYBOARD, 0x30, "B", modifiers=(shift,))
        backend = WindowsSendInputBackend.__new__(WindowsSendInputBackend)
        backend._pressed = {}
        backend._lock = threading.RLock()
        sent: list[tuple[str, bool]] = []
        backend._send_binding = lambda binding, pressed: sent.append(
            (binding.label, pressed)
        )

        for action, binding in (
            (ActionType.PRESS, first),
            (ActionType.PRESS, second),
            (ActionType.RELEASE, first),
            (ActionType.RELEASE, second),
        ):
            backend.emit(TimedInputEvent(0.0, action, binding))

        self.assertEqual(
            sent,
            [
                ("Shift", True),
                ("A", True),
                ("B", True),
                ("A", False),
                ("B", False),
                ("Shift", False),
            ],
        )


if __name__ == "__main__":
    unittest.main()
