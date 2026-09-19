"""录制会话状态与暂停时间处理。"""

from __future__ import annotations

from ..models import GameProfile
from .decoder import DecodedNoteStart, ProfileInputDecoder
from .models import PhysicalInputEvent, RecordedNote, RecordingTake


class RecordingSession:
    """把物理事件收集为可供转谱的归一化演奏。"""

    def __init__(self, profile: GameProfile) -> None:
        """
        初始化录制会话。

        Args:
            profile (GameProfile): 录制期间固定使用的按键配置。
        """

        self._decoder = ProfileInputDecoder(profile)
        self._notes: list[RecordedNote] = []
        self._paused_at_ms: float | None = None
        self._paused_total_ms = 0.0
        self._last_timestamp_ms = 0.0
        self._first_note_timestamp_ms: float | None = None

    @property
    def note_count(self) -> int:
        """返回已经按下过的音符数量。"""

        return len(self._notes) + self._decoder.active_count

    def feed(self, event: PhysicalInputEvent) -> DecodedNoteStart | None:
        """
        消费一次输入；注入事件和暂停期间事件会被忽略。

        Args:
            event (PhysicalInputEvent): 系统输入事件。

        Returns:
            DecodedNoteStart | None: 新识别音符，其他事件返回空。
        """

        if event.injected or self._paused_at_ms is not None:
            return None
        timestamp_ms = event.timestamp_ms - self._paused_total_ms
        self._last_timestamp_ms = max(self._last_timestamp_ms, timestamp_ms)
        result = self._decoder.feed(event.binding, event.pressed, timestamp_ms)
        if isinstance(result, RecordedNote):
            self._notes.append(result)
            return None
        if isinstance(result, DecodedNoteStart) and self._first_note_timestamp_ms is None:
            self._first_note_timestamp_ms = timestamp_ms
        return result

    def elapsed_ms(self, timestamp_ms: float) -> float:
        """
        返回从首个音符开始且排除暂停区间的录制时长。

        Args:
            timestamp_ms (float): 当前系统单调时钟毫秒位置。

        Returns:
            float: 当前有效录制时长；尚无音符时为零。
        """

        if self._first_note_timestamp_ms is None:
            return 0.0
        current = self._paused_at_ms if self._paused_at_ms is not None else timestamp_ms
        adjusted = current - self._paused_total_ms
        return max(0.0, adjusted - self._first_note_timestamp_ms)

    def pause(self, timestamp_ms: float) -> None:
        """
        暂停时间轴并关闭仍按住的音符。

        Args:
            timestamp_ms (float): 系统单调时钟毫秒位置。
        """

        if self._paused_at_ms is not None:
            return
        adjusted = timestamp_ms - self._paused_total_ms
        self._notes.extend(self._decoder.finish(adjusted))
        self._last_timestamp_ms = max(self._last_timestamp_ms, adjusted)
        self._paused_at_ms = timestamp_ms

    def resume(self, timestamp_ms: float) -> None:
        """
        恢复录制并从时间轴中排除暂停区间。

        Args:
            timestamp_ms (float): 系统单调时钟毫秒位置。
        """

        if self._paused_at_ms is None:
            return
        self._paused_total_ms += max(0.0, timestamp_ms - self._paused_at_ms)
        self._paused_at_ms = None

    def finish(self, timestamp_ms: float) -> RecordingTake:
        """
        关闭活动音符并返回从第一个音符零点开始的演奏。

        Args:
            timestamp_ms (float): 系统单调时钟毫秒位置。

        Returns:
            RecordingTake: 时间轴已经归一化的录制结果。
        """

        if self._paused_at_ms is None:
            adjusted = timestamp_ms - self._paused_total_ms
            self._notes.extend(self._decoder.finish(adjusted))
        if not self._notes:
            return RecordingTake(())
        origin = min(note.start_ms for note in self._notes)
        notes = tuple(
            RecordedNote(
                note.start_ms - origin,
                note.end_ms - origin,
                note.degree,
                note.octave,
                note.is_semitone,
            )
            for note in sorted(self._notes, key=lambda item: (item.start_ms, item.degree))
        )
        return RecordingTake(notes)
