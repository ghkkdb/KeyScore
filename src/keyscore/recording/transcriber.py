"""将录制音符量化并生成 KeyScore 文本曲谱。"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from ..models import NoteOutputMode, Octave
from ..parser import parse_score
from .models import RecordedNote, RecordingSettings, RecordingTake


@dataclass
class _NoteGroup:
    """表示和弦容差内的一组同时音符。"""

    notes: list[RecordedNote]
    start_beat: Fraction = Fraction(0)


@dataclass(frozen=True)
class _OutputUnit:
    """表示待序列化的音符、和弦或休止单位。"""

    token: str
    duration: Fraction
    legato_to_next: bool = False


def _quantize(milliseconds: float, bpm: int, grid: Fraction) -> Fraction:
    """
    将毫秒位置四舍五入到最近的节拍网格。

    Args:
        milliseconds (float): 从录制起点计算的毫秒位置。
        bpm (int): 每分钟拍数。
        grid (Fraction): 最小节拍网格。

    Returns:
        Fraction: 量化后的拍数。
    """

    beats = Fraction(str(max(0.0, milliseconds))) * bpm / 60_000
    ratio = beats / grid
    rounded = (ratio.numerator * 2 + ratio.denominator) // (2 * ratio.denominator)
    return max(Fraction(0), rounded * grid)


def _pitch_text(note: RecordedNote) -> str:
    """
    把录制音高转换为 KeyScore 音符文本。

    Args:
        note (RecordedNote): 录制音符。

    Returns:
        str: 例如 `1`、`L1` 或 `#H1`。
    """

    octave = {
        Octave.LOWEST: "LL",
        Octave.LOW: "L",
        Octave.MIDDLE: "",
        Octave.HIGH: "H",
        Octave.HIGHEST: "HH",
    }[note.octave]
    return f"{'#' if note.is_semitone else ''}{octave}{note.degree}"


def _duration_text(duration: Fraction) -> str:
    """
    把精确拍数转换为解析器支持的简洁十进制。

    Args:
        duration (Fraction): 正拍数。

    Returns:
        str: 省略无意义末尾零的十进制文本。
    """

    if duration.denominator == 1:
        return str(duration.numerator)
    value = f"{float(duration):.6f}".rstrip("0").rstrip(".")
    return value


def _token_with_duration(token: str, duration: Fraction) -> str:
    """
    为曲谱单位追加非默认时值。

    Args:
        token (str): 音符、和弦或休止文本。
        duration (Fraction): 单位总时值。

    Returns:
        str: 可由现有解析器读取的词元。
    """

    return token if duration == 1 else f"{token}:{_duration_text(duration)}"


def _group_notes(take: RecordingTake, tolerance_ms: int) -> list[_NoteGroup]:
    """
    按起点容差聚合和弦并去除同组重复音高。

    Args:
        take (RecordingTake): 原始录制结果。
        tolerance_ms (int): 和弦起点容差。

    Returns:
        list[_NoteGroup]: 按起点排列的音符组。
    """

    groups: list[_NoteGroup] = []
    for note in take.notes:
        if not groups or note.start_ms - groups[-1].notes[0].start_ms > tolerance_ms:
            groups.append(_NoteGroup([note]))
            continue
        pitches = {
            (item.degree, item.octave, item.is_semitone) for item in groups[-1].notes
        }
        if (note.degree, note.octave, note.is_semitone) not in pitches:
            groups[-1].notes.append(note)
    return groups


def _merge_quantized_groups(
    groups: list[_NoteGroup], settings: RecordingSettings
) -> list[_NoteGroup]:
    """
    量化起点，并合并量化到同一拍点的相邻音符组。

    Args:
        groups (list[_NoteGroup]): 原始和弦分组。
        settings (RecordingSettings): 转谱设置。

    Returns:
        list[_NoteGroup]: 起点严格递增的量化分组。
    """

    merged: list[_NoteGroup] = []
    for group in groups:
        group.start_beat = _quantize(group.notes[0].start_ms, settings.bpm, settings.grid)
        if merged and merged[-1].start_beat == group.start_beat:
            existing = {
                (item.degree, item.octave, item.is_semitone) for item in merged[-1].notes
            }
            merged[-1].notes.extend(
                note
                for note in group.notes
                if (note.degree, note.octave, note.is_semitone) not in existing
            )
        else:
            merged.append(group)
    return merged


def _group_token(group: _NoteGroup) -> str:
    """
    生成单音或和弦正文。

    Args:
        group (_NoteGroup): 量化后的音符组。

    Returns:
        str: 不含时值的音符或和弦文本。
    """

    pitches = [_pitch_text(note) for note in group.notes]
    return pitches[0] if len(pitches) == 1 else f"[{' '.join(pitches)}]"


def _build_units(
    groups: list[_NoteGroup], settings: RecordingSettings, output_mode: NoteOutputMode
) -> list[_OutputUnit]:
    """
    根据短按或持续按住语义生成顺序曲谱单位。

    Args:
        groups (list[_NoteGroup]): 量化后的音符组。
        settings (RecordingSettings): 转谱设置。
        output_mode (NoteOutputMode): 当前 Profile 的音符输出方式。

    Returns:
        list[_OutputUnit]: 包含必要休止和连音标记的曲谱单位。
    """

    units: list[_OutputUnit] = []
    cursor = Fraction(0)
    for index, group in enumerate(groups):
        if group.start_beat > cursor:
            units.append(_OutputUnit("0", group.start_beat - cursor))
            cursor = group.start_beat
        next_group = groups[index + 1] if index + 1 < len(groups) else None
        if next_group is not None:
            available = next_group.start_beat - group.start_beat
        else:
            available = Fraction(0)

        raw_end_ms = max(note.end_ms for note in group.notes)
        sounding_end = _quantize(raw_end_ms, settings.bpm, settings.grid)
        legato = bool(
            settings.detect_legato
            and output_mode is NoteOutputMode.HOLD
            and next_group is not None
            and len(group.notes) == 1
            and len(next_group.notes) == 1
            and raw_end_ms + settings.legato_tolerance_ms
            >= next_group.notes[0].start_ms
        )
        if next_group is None:
            duration = (
                max(settings.grid, sounding_end - group.start_beat)
                if output_mode is NoteOutputMode.HOLD
                else Fraction(1)
            )
        elif output_mode is NoteOutputMode.TAP or legato:
            duration = available
        else:
            duration = min(available, max(settings.grid, sounding_end - group.start_beat))
        duration = max(settings.grid, duration)
        units.append(_OutputUnit(_group_token(group), duration, legato))
        cursor = group.start_beat + duration
    return units


def _measure_beats(beat: str) -> Fraction:
    """
    将拍号换算为四分音符拍数表示的小节长度。

    Args:
        beat (str): 例如 `4/4` 或 `6/8`。

    Returns:
        Fraction: 一个小节占用的四分音符拍数。
    """

    numerator, denominator = (int(part) for part in beat.split("/", maxsplit=1))
    return Fraction(numerator * 4, denominator)


def _serialize_units(units: list[_OutputUnit], beat: str) -> str:
    """
    序列化正文并在小节边界插入竖线。

    Args:
        units (list[_OutputUnit]): 顺序曲谱单位。
        beat (str): 曲谱拍号。

    Returns:
        str: 已格式化的曲谱正文。
    """

    tokens: list[str] = []
    cursor = Fraction(0)
    measure = _measure_beats(beat)
    next_bar = measure
    in_legato = False
    for unit in units:
        if unit.legato_to_next and not in_legato:
            tokens.append("(")
            in_legato = True
        tokens.append(_token_with_duration(unit.token, unit.duration))
        cursor += unit.duration
        if in_legato and not unit.legato_to_next:
            tokens.append(")")
            in_legato = False
        while cursor >= next_bar:
            tokens.append("|")
            next_bar += measure
    if in_legato:
        tokens.append(")")
    lines: list[str] = []
    current: list[str] = []
    bars = 0
    for token in tokens:
        current.append(token)
        if token == "|":
            bars += 1
            if bars % 4 == 0:
                lines.append(" ".join(current))
                current = []
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def transcribe_take(
    take: RecordingTake, settings: RecordingSettings, output_mode: NoteOutputMode
) -> str:
    """
    将录制结果转换为完整且经过解析器复验的 KeyScore 曲谱。

    Args:
        take (RecordingTake): 待转谱的录制结果。
        settings (RecordingSettings): 节拍、量化和识别设置。
        output_mode (NoteOutputMode): 录制配置的音符输出方式。

    Returns:
        str: 可直接保存和编辑的 UTF-8 曲谱文本。

    Raises:
        ValueError: 没有音符或设置无效时抛出。
    """

    settings.validate()
    if not take.notes:
        raise ValueError("没有录制到有效音符")
    groups = _merge_quantized_groups(
        _group_notes(take, settings.chord_tolerance_ms), settings
    )
    units = _build_units(groups, settings, output_mode)
    body = _serialize_units(units, settings.beat)
    text = (
        f"@title {settings.title.strip()}\n"
        f"@bpm {settings.bpm}\n"
        f"@beat {settings.beat}\n"
        "@section_gap 1\n\n"
        f"{body}\n"
    )
    parse_score(text)
    return text
