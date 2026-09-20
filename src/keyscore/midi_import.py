"""将标准 MIDI 文件提取为 KeyScore 单声部曲谱。"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from .score_document import NoteGroup, ScoreDocument, pitch_from_index


class MidiImportError(ValueError):
    """表示 MIDI 文件无法转换为可用的 KeyScore 曲谱。"""


@dataclass(frozen=True)
class MidiImportReport:
    """记录 MIDI 简化转换时作出的选择和舍弃。"""

    track_name: str
    source_notes: int
    imported_notes: int
    ignored_drum_notes: int
    ignored_out_of_range_notes: int
    collapsed_notes: int
    shortened_notes: int
    quantization: Fraction

    def summary(self) -> str:
        """
        生成人类可读的导入摘要。

        Returns:
            str: 可直接显示在导入完成对话框中的多行摘要。
        """

        return (
            f"主旋律轨道：{self.track_name}\n"
            f"导入音符：{self.imported_notes}/{self.source_notes}\n"
            f"同起点合并：{self.collapsed_notes} 个（保留最高音）\n"
            f"重叠截短：{self.shortened_notes} 个\n"
            f"忽略鼓点：{self.ignored_drum_notes} 个\n"
            f"超出五音区：{self.ignored_out_of_range_notes} 个\n"
            f"量化精度：{_fraction_text(self.quantization)} 拍"
        )


@dataclass(frozen=True)
class MidiImportResult:
    """包含 MIDI 转换后的文档与转换报告。"""

    document: ScoreDocument
    report: MidiImportReport


@dataclass(frozen=True)
class _MidiNote:
    """表示解析后的单个 MIDI 音符事件。"""

    start_tick: int
    end_tick: int
    pitch: int


def import_midi(
    path: Path,
    quantization: Fraction = Fraction(1, 4),
) -> MidiImportResult:
    """
    从 MIDI 中选择音符最多的非鼓轨，并提取最高音旋律。

    Args:
        path (Path): 待导入的 `.mid` 或 `.midi` 文件。
        quantization (Fraction): 开始时间和时值使用的拍位网格。

    Returns:
        MidiImportResult: 可序列化的 KeyScore 文档及简化报告。

    Raises:
        MidiImportError: 依赖缺失、文件损坏或没有可导入音符时抛出。
    """

    if quantization <= 0:
        raise MidiImportError("MIDI 量化精度必须大于 0")
    try:
        import mido
    except ImportError as exc:
        raise MidiImportError("缺少 MIDI 解析组件 mido，请重新安装 KeyScore") from exc
    try:
        midi = mido.MidiFile(path)
    except (OSError, EOFError, ValueError) as exc:
        raise MidiImportError(f"无法读取 MIDI 文件：{exc}") from exc
    if midi.type == 2:
        raise MidiImportError("暂不支持异步多序列的 MIDI Format 2")
    ticks_per_beat = int(midi.ticks_per_beat)
    if ticks_per_beat <= 0:
        raise MidiImportError("MIDI 的 PPQ 时间基准无效")

    tracks: list[tuple[str, list[_MidiNote]]] = []
    ignored_drum_notes = 0
    for track_index, track in enumerate(midi.tracks):
        name, notes, drum_count = _read_track(track, track_index)
        ignored_drum_notes += drum_count
        if notes:
            tracks.append((name, notes))
    if not tracks:
        raise MidiImportError("MIDI 中没有可导入的非打击乐音符")

    track_name, source_notes = max(tracks, key=lambda item: len(item[1]))
    bpm, beat = _read_metadata(midi)
    document, report = _build_document(
        title=path.stem,
        bpm=bpm,
        beat=beat,
        track_name=track_name,
        notes=source_notes,
        ticks_per_beat=ticks_per_beat,
        quantization=quantization,
        ignored_drum_notes=ignored_drum_notes,
    )
    return MidiImportResult(document, report)


def _read_track(track: Any, track_index: int) -> tuple[str, list[_MidiNote], int]:
    """
    配对一条 MIDI 轨道中的 Note On 与 Note Off 事件。

    Args:
        track (Any): mido 提供的 MidiTrack 对象。
        track_index (int): 轨道序号，用于生成回退名称。

    Returns:
        tuple[str, list[_MidiNote], int]: 轨道名称、非鼓音符和鼓点数量。
    """

    absolute_tick = 0
    track_name = f"轨道 {track_index + 1}"
    active: dict[tuple[int, int], deque[int]] = defaultdict(deque)
    notes: list[_MidiNote] = []
    drum_count = 0
    for message in track:
        absolute_tick += int(message.time)
        if message.type == "track_name" and str(message.name).strip():
            track_name = str(message.name).strip()
            continue
        if message.type == "note_on" and int(message.velocity) > 0:
            key = (int(message.channel), int(message.note))
            active[key].append(absolute_tick)
            continue
        if message.type not in {"note_off", "note_on"}:
            continue
        if message.type == "note_on" and int(message.velocity) > 0:
            continue
        key = (int(message.channel), int(message.note))
        if not active[key]:
            continue
        start_tick = active[key].popleft()
        if int(message.channel) == 9:
            drum_count += 1
        elif absolute_tick > start_tick:
            notes.append(_MidiNote(start_tick, absolute_tick, int(message.note)))
    return track_name, notes, drum_count


def _read_metadata(midi: Any) -> tuple[int, str]:
    """
    读取 MIDI 中首次出现的速度和拍号。

    Args:
        midi (Any): mido 提供的 MidiFile 对象。

    Returns:
        tuple[int, str]: 限制在 KeyScore 范围内的 BPM 与拍号文本。
    """

    tempo = 500_000
    numerator = 4
    denominator = 4
    tempo_found = False
    signature_found = False
    for track in midi.tracks:
        for message in track:
            if message.type == "set_tempo" and not tempo_found:
                tempo = int(message.tempo)
                tempo_found = True
            elif message.type == "time_signature" and not signature_found:
                numerator = int(message.numerator)
                denominator = int(message.denominator)
                signature_found = True
    bpm = max(20, min(400, round(60_000_000 / max(1, tempo))))
    return bpm, f"{numerator}/{denominator}"


def _build_document(
    title: str,
    bpm: int,
    beat: str,
    track_name: str,
    notes: list[_MidiNote],
    ticks_per_beat: int,
    quantization: Fraction,
    ignored_drum_notes: int,
) -> tuple[ScoreDocument, MidiImportReport]:
    """
    量化音符、折叠同起点复音并生成顺序曲谱。

    Args:
        title (str): 目标曲名。
        bpm (int): 曲谱速度。
        beat (str): 曲谱拍号。
        track_name (str): 被选中的 MIDI 轨道名称。
        notes (list[_MidiNote]): 被选中轨道的源音符。
        ticks_per_beat (int): MIDI 每拍 tick 数。
        quantization (Fraction): 目标量化网格。
        ignored_drum_notes (int): 全文件已忽略的鼓点数量。

    Returns:
        tuple[ScoreDocument, MidiImportReport]: 转换文档和报告。

    Raises:
        MidiImportError: 所有音符均超出 KeyScore 音域时抛出。
    """

    grouped: dict[Fraction, list[tuple[int, Fraction]]] = defaultdict(list)
    out_of_range = 0
    for note in notes:
        pitch_index = note.pitch - 36
        if not 0 <= pitch_index < 60:
            out_of_range += 1
            continue
        start = _quantize_ticks(note.start_tick, ticks_per_beat, quantization, False)
        duration = _quantize_ticks(
            note.end_tick - note.start_tick,
            ticks_per_beat,
            quantization,
            True,
        )
        grouped[start].append((pitch_index, duration))
    if not grouped:
        raise MidiImportError("所选主旋律轨道的音符全部超出 KeyScore 五音区")

    selected: list[tuple[Fraction, int, Fraction]] = []
    collapsed = 0
    for start in sorted(grouped):
        candidates = grouped[start]
        highest = max(candidates, key=lambda item: item[0])
        selected.append((start, highest[0], highest[1]))
        collapsed += len(candidates) - 1

    groups: list[NoteGroup] = []
    shortened = 0
    for index, (start, pitch, duration) in enumerate(selected):
        if index + 1 < len(selected):
            available = selected[index + 1][0] - start
            if duration > available:
                duration = available
                shortened += 1
        if duration <= 0:
            continue
        groups.append(NoteGroup(start, duration, (pitch_from_index(pitch),)))
    if not groups:
        raise MidiImportError("量化后没有剩余的可用旋律音符")
    total_beats = max(group.start_beat + group.duration_beats for group in groups)
    document = ScoreDocument(
        title=title.strip() or "MIDI 导入曲谱",
        bpm=bpm,
        beat=beat,
        groups=tuple(groups),
        total_beats=total_beats,
    )
    report = MidiImportReport(
        track_name=track_name,
        source_notes=len(notes),
        imported_notes=len(groups),
        ignored_drum_notes=ignored_drum_notes,
        ignored_out_of_range_notes=out_of_range,
        collapsed_notes=collapsed,
        shortened_notes=shortened,
        quantization=quantization,
    )
    return document, report


def _quantize_ticks(
    ticks: int,
    ticks_per_beat: int,
    grid: Fraction,
    require_positive: bool,
) -> Fraction:
    """
    将 tick 数量吸附到最接近的拍位网格。

    Args:
        ticks (int): 待转换的非负 tick 数。
        ticks_per_beat (int): MIDI 每拍 tick 数。
        grid (Fraction): 量化网格。
        require_positive (bool): 是否至少返回一个网格单位。

    Returns:
        Fraction: 量化后的精确拍数。
    """

    beats = Fraction(max(0, ticks), ticks_per_beat)
    ratio = beats / grid
    steps = (ratio.numerator * 2 + ratio.denominator) // (2 * ratio.denominator)
    if require_positive:
        steps = max(1, steps)
    return steps * grid


def _fraction_text(value: Fraction) -> str:
    """
    将拍数转换为紧凑分数文本。

    Args:
        value (Fraction): 待显示的拍数。

    Returns:
        str: 整数或分数字符串。
    """

    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"
