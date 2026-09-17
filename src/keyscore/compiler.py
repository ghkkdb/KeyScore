"""将内部曲谱编译为绝对时间输入事件。"""

from __future__ import annotations

from collections import defaultdict
from fractions import Fraction

from .models import (
    ActionType,
    GameProfile,
    MappingMode,
    NoteEvent,
    Octave,
    PlaybackPlan,
    Score,
    TimedInputEvent,
    note_binding_key,
)


class PlanCompileError(ValueError):
    """表示曲谱无法使用当前游戏配置编译。"""


def _milliseconds(beats: Fraction, bpm: int) -> float:
    """
    将拍数转换为毫秒。

    Args:
        beats (Fraction): 拍数。
        bpm (int): 每分钟拍数。

    Returns:
        float: 对应毫秒数。
    """

    return float(beats) * 60_000.0 / bpm


def _append_note_events(
    output: list[TimedInputEvent],
    note: NoteEvent,
    note_start_ms: float,
    note_duration_ms: float,
    profile: GameProfile,
) -> float:
    """
    为单个音符添加按下和释放事件。

    Args:
        output (list[TimedInputEvent]): 目标事件列表。
        note (NoteEvent): 待编译音符。
        note_start_ms (float): 音符的实际按键起点。
        note_duration_ms (float): 从实际按下到下一拍点的可用时间。
        profile (GameProfile): 游戏配置。

    Returns:
        float: 音符释放事件的绝对毫秒时间戳。

    Raises:
        PlanCompileError: 音符未配置按键时抛出。
    """

    if profile.mapping_mode is MappingMode.DEGREE_MODIFIER:
        binding = profile.note_bindings.get(note.degree)
    else:
        if profile.mapping_mode is MappingMode.ROW_OCTAVE and note.is_semitone:
            raise PlanCompileError("三行音区直接映射不支持半音；请改用直接音符映射")
        binding = profile.direct_note_bindings.get(note_binding_key(note))
    if binding is None:
        raise PlanCompileError(f"音符 {note.octave.value} {note.degree} 没有配置按键")
    hold_ms = min(
        float(profile.key_hold_ms),
        max(1.0, note_duration_ms - float(profile.key_gap_ms)),
    )
    output.append(TimedInputEvent(note_start_ms, ActionType.PRESS, binding, note))
    release_ms = note_start_ms + hold_ms
    output.append(TimedInputEvent(release_ms, ActionType.RELEASE, binding, note))
    return release_ms


def compile_score(score: Score, profile: GameProfile) -> PlaybackPlan:
    """
    将曲谱编译为可由播放器执行的绝对时间轴。

    Args:
        score (Score): 已解析的曲谱。
        profile (GameProfile): 键鼠映射、音区修饰键和半音修饰键。

    Returns:
        PlaybackPlan: 排序后的播放计划。

    Raises:
        PlanCompileError: 映射缺失或同时音符需要冲突修饰键时抛出。
    """

    groups: dict[Fraction, list[NoteEvent]] = defaultdict(list)
    for note in score.notes:
        groups[note.start_beat].append(note)

    output: list[TimedInputEvent] = []
    for start_beat in sorted(groups):
        notes = groups[start_beat]
        start_ms = _milliseconds(start_beat, score.bpm)
        shortest_duration_ms = min(_milliseconds(note.duration_beats, score.bpm) for note in notes)
        transition_ms = min(float(profile.zone_delay_ms), shortest_duration_ms * 0.25)
        modifiers = []
        if profile.mapping_mode is MappingMode.DEGREE_MODIFIER:
            octaves = {note.octave for note in notes}
            semitone_states = {note.is_semitone for note in notes}
            if len(octaves) > 1:
                raise PlanCompileError("当前方案的全局音区修饰键不能表达跨音区和弦")
            if len(semitone_states) > 1:
                raise PlanCompileError("当前方案的全局半音修饰键不能表达自然音和半音混合和弦")

            octave = next(iter(octaves))
            if octave is not Octave.MIDDLE:
                zone_binding = profile.zone_bindings.get(octave)
                if zone_binding is None:
                    raise PlanCompileError(f"音区 {octave.value} 没有配置修饰键")
                modifiers.append(zone_binding)
            if next(iter(semitone_states)):
                modifiers.append(profile.semitone_binding)

        for modifier in modifiers:
            output.append(TimedInputEvent(start_ms, ActionType.PRESS, modifier))
        note_start_ms = start_ms + transition_ms if modifiers else start_ms
        modifier_release_ms = note_start_ms
        for note in notes:
            duration_ms = _milliseconds(note.duration_beats, score.bpm)
            available_ms = duration_ms - (note_start_ms - start_ms)
            release_ms = _append_note_events(
                output,
                note,
                note_start_ms,
                available_ms,
                profile,
            )
            modifier_release_ms = max(modifier_release_ms, release_ms)
        for modifier in modifiers:
            output.append(TimedInputEvent(modifier_release_ms, ActionType.RELEASE, modifier))

    action_order = {ActionType.RELEASE: 0, ActionType.PRESS: 1}
    output.sort(key=lambda event: (event.timestamp_ms, action_order[event.action]))
    return PlaybackPlan(
        title=score.title,
        bpm=score.bpm,
        events=tuple(output),
        duration_ms=_milliseconds(score.total_beats, score.bpm),
    )
