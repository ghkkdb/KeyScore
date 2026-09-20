"""钢琴卷帘使用的可编辑曲谱文档与文本序列化。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction

from .models import NoteEvent, Octave, Score
from .parser import parse_score


@dataclass(frozen=True, order=True)
class RollPitch:
    """表示卷帘中的一个 KeyScore 语义音高。"""

    octave: Octave
    degree: int
    is_semitone: bool = False


@dataclass(frozen=True)
class NoteGroup:
    """表示共享起点和时值的单音或和弦。"""

    start_beat: Fraction
    duration_beats: Fraction
    pitches: tuple[RollPitch, ...]
    legato_to_next: bool = False


@dataclass(frozen=True)
class ScoreDocument:
    """表示可由钢琴卷帘安全编辑和序列化的曲谱。"""

    title: str
    bpm: int
    beat: str
    groups: tuple[NoteGroup, ...]
    total_beats: Fraction


def pitch_from_note(note: NoteEvent) -> RollPitch:
    """
    将解析后的音符转换为卷帘音高。

    Args:
        note (NoteEvent): 已解析音符。

    Returns:
        RollPitch: 不包含时间信息的语义音高。
    """

    return RollPitch(note.octave, note.degree, note.is_semitone)


def document_from_score(score: Score) -> ScoreDocument:
    """
    将只读曲谱模型转换为可编辑文档。

    Args:
        score (Score): 解析器生成的曲谱。

    Returns:
        ScoreDocument: 按开始拍排序的可编辑文档。
    """

    grouped: dict[Fraction, list[NoteEvent]] = {}
    for note in score.notes:
        grouped.setdefault(note.start_beat, []).append(note)
    groups: list[NoteGroup] = []
    for start_beat in sorted(grouped):
        notes = grouped[start_beat]
        duration = min(note.duration_beats for note in notes)
        pitches = tuple(
            sorted(
                {pitch_from_note(note) for note in notes},
                key=pitch_index,
            )
        )
        groups.append(
            NoteGroup(
                start_beat=start_beat,
                duration_beats=duration,
                pitches=pitches,
                legato_to_next=all(note.legato_to_next for note in notes),
            )
        )
    return ScoreDocument(
        title=score.title,
        bpm=score.bpm,
        beat=score.beat,
        groups=tuple(groups),
        total_beats=score.total_beats,
    )


def document_from_text(text: str) -> ScoreDocument:
    """
    解析 KeyScore 文本并创建卷帘文档。

    Args:
        text (str): 完整曲谱文本。

    Returns:
        ScoreDocument: 可编辑曲谱文档。

    Raises:
        ScoreParseError: 文本不符合曲谱语法时由解析器抛出。
    """

    return document_from_score(parse_score(text))


def pitch_index(pitch: RollPitch) -> int:
    """
    返回音高在五音区十二平均律纵轴上的索引。

    Args:
        pitch (RollPitch): KeyScore 语义音高。

    Returns:
        int: 从倍低音 1 开始计算的半音索引。
    """

    octave_index = {
        Octave.LOWEST: 0,
        Octave.LOW: 1,
        Octave.MIDDLE: 2,
        Octave.HIGH: 3,
        Octave.HIGHEST: 4,
    }[pitch.octave]
    natural_offset = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}[pitch.degree]
    return octave_index * 12 + natural_offset + int(pitch.is_semitone)


def pitch_from_index(index: int) -> RollPitch:
    """
    将卷帘纵轴索引转换为规范 KeyScore 音高。

    Args:
        index (int): 0～59 范围内的半音索引。

    Returns:
        RollPitch: 对应的自然音或升音写法。

    Raises:
        ValueError: 索引超出五音区范围时抛出。
    """

    if not 0 <= index < 60:
        raise ValueError("音高超出 KeyScore 五音区范围")
    octave = (
        Octave.LOWEST,
        Octave.LOW,
        Octave.MIDDLE,
        Octave.HIGH,
        Octave.HIGHEST,
    )[index // 12]
    degree, is_semitone = {
        0: (1, False),
        1: (1, True),
        2: (2, False),
        3: (2, True),
        4: (3, False),
        5: (4, False),
        6: (4, True),
        7: (5, False),
        8: (5, True),
        9: (6, False),
        10: (6, True),
        11: (7, False),
    }[index % 12]
    return RollPitch(octave, degree, is_semitone)


def pitch_text(pitch: RollPitch) -> str:
    """
    返回音高对应的 KeyScore 词元正文。

    Args:
        pitch (RollPitch): 待格式化音高。

    Returns:
        str: 例如 `L1`、`#4` 或 `HH7`。
    """

    prefix = {
        Octave.LOWEST: "LL",
        Octave.LOW: "L",
        Octave.MIDDLE: "",
        Octave.HIGH: "H",
        Octave.HIGHEST: "HH",
    }[pitch.octave]
    return f"{'#' if pitch.is_semitone else ''}{prefix}{pitch.degree}"


def _duration_text(duration: Fraction) -> str:
    """
    将拍数转换为解析器支持的紧凑十进制。

    Args:
        duration (Fraction): 正拍数。

    Returns:
        str: 无多余末尾零的十进制文本。
    """

    if duration.denominator == 1:
        return str(duration.numerator)
    return f"{float(duration):.6f}".rstrip("0").rstrip(".")


def _unit_text(token: str, duration: Fraction) -> str:
    """
    为非一拍单位追加时值。

    Args:
        token (str): 音符、和弦或休止符正文。
        duration (Fraction): 单位时值。

    Returns:
        str: 可被当前解析器读取的完整词元。
    """

    return token if duration == 1 else f"{token}:{_duration_text(duration)}"


def validate_document(document: ScoreDocument) -> None:
    """
    校验可编辑文档能否由当前顺序曲谱格式表达。

    Args:
        document (ScoreDocument): 待校验文档。

    Raises:
        ValueError: 元数据、音符或时间轴无效时抛出。
    """

    if not document.title.strip():
        raise ValueError("曲名不能为空")
    if not 20 <= document.bpm <= 400:
        raise ValueError("BPM 必须在 20～400 之间")
    previous_end = Fraction(0)
    for index, group in enumerate(sorted(document.groups, key=lambda item: item.start_beat)):
        if group.start_beat < 0:
            raise ValueError("音符开始拍不能小于 0")
        if group.duration_beats <= 0:
            raise ValueError("音符时值必须大于 0")
        if not group.pitches:
            raise ValueError("和弦不能为空")
        if group.start_beat < previous_end:
            raise ValueError("当前曲谱格式不支持相互重叠的独立声部")
        if group.legato_to_next:
            if index + 1 >= len(document.groups):
                raise ValueError("最后一个音符不能连接到不存在的下一音符")
            next_group = sorted(document.groups, key=lambda item: item.start_beat)[index + 1]
            if group.start_beat + group.duration_beats != next_group.start_beat:
                raise ValueError("连音之间不能包含休止间隔")
        previous_end = group.start_beat + group.duration_beats


def serialize_document(document: ScoreDocument) -> str:
    """
    将可编辑文档序列化为规范 KeyScore 文本。

    Args:
        document (ScoreDocument): 待保存文档。

    Returns:
        str: 经过解析器复验的完整曲谱文本。

    Raises:
        ValueError: 文档包含当前格式无法表达的结构时抛出。
    """

    validate_document(document)
    tokens: list[str] = []
    cursor = Fraction(0)
    in_legato = False
    groups = sorted(document.groups, key=lambda item: item.start_beat)
    for group in groups:
        if group.start_beat > cursor:
            if in_legato:
                tokens.append(")")
                in_legato = False
            tokens.append(_unit_text("0", group.start_beat - cursor))
            cursor = group.start_beat
        if group.legato_to_next and not in_legato:
            tokens.append("(")
            in_legato = True
        pitches = [pitch_text(pitch) for pitch in sorted(group.pitches, key=pitch_index)]
        token = pitches[0] if len(pitches) == 1 else f"[{' '.join(pitches)}]"
        tokens.append(_unit_text(token, group.duration_beats))
        cursor = group.start_beat + group.duration_beats
        if in_legato and not group.legato_to_next:
            tokens.append(")")
            in_legato = False
    if in_legato:
        tokens.append(")")
    if document.total_beats > cursor:
        tokens.append(_unit_text("0", document.total_beats - cursor))
    if not tokens:
        tokens.append("0")

    lines = [" ".join(tokens[index : index + 12]) for index in range(0, len(tokens), 12)]
    text = (
        f"@title {document.title.strip()}\n"
        f"@bpm {document.bpm}\n"
        f"@beat {document.beat}\n"
        "@section_gap 1\n\n"
        + "\n".join(lines)
        + "\n"
    )
    parse_score(text)
    return text


def _groups_without_pitch(
    document: ScoreDocument,
    group_index: int,
    pitch: RollPitch,
) -> tuple[NoteGroup, ...]:
    """
    从指定音符组移除一个音高并清理空组。

    Args:
        document (ScoreDocument): 原始文档。
        group_index (int): 音符组索引。
        pitch (RollPitch): 待移除音高。

    Returns:
        tuple[NoteGroup, ...]: 移除后的音符组。

    Raises:
        ValueError: 索引或音高不存在时抛出。
    """

    if not 0 <= group_index < len(document.groups):
        raise ValueError("音符组不存在")
    group = document.groups[group_index]
    if pitch not in group.pitches:
        raise ValueError("音符不存在")
    remaining = tuple(item for item in group.pitches if item != pitch)
    groups = list(document.groups)
    if remaining:
        groups[group_index] = replace(group, pitches=remaining)
    else:
        groups.pop(group_index)
        if group_index > 0 and groups[group_index - 1].legato_to_next:
            groups[group_index - 1] = replace(
                groups[group_index - 1],
                legato_to_next=False,
            )
    return tuple(groups)


def add_note(
    document: ScoreDocument,
    start_beat: Fraction,
    duration_beats: Fraction,
    pitch: RollPitch,
) -> ScoreDocument:
    """
    在时间轴添加音符，或合并到同起点和弦。

    Args:
        document (ScoreDocument): 原始文档。
        start_beat (Fraction): 量化后的开始拍。
        duration_beats (Fraction): 新音符时值。
        pitch (RollPitch): 新音符音高。

    Returns:
        ScoreDocument: 添加后的新文档。

    Raises:
        ValueError: 新音符与独立声部重叠或参数无效时抛出。
    """

    if start_beat < 0 or duration_beats <= 0:
        raise ValueError("音符位置或时值无效")
    groups = list(document.groups)
    for index, group in enumerate(groups):
        if group.start_beat == start_beat:
            if pitch in group.pitches:
                return document
            groups[index] = replace(
                group,
                pitches=tuple(sorted((*group.pitches, pitch), key=pitch_index)),
            )
            result = replace(document, groups=tuple(groups))
            validate_document(result)
            return result
    new_group = NoteGroup(start_beat, duration_beats, (pitch,))
    groups.append(new_group)
    groups.sort(key=lambda item: item.start_beat)
    total = max(document.total_beats, start_beat + duration_beats)
    result = replace(document, groups=tuple(groups), total_beats=total)
    validate_document(result)
    return result


def remove_note(
    document: ScoreDocument,
    group_index: int,
    pitch: RollPitch,
) -> ScoreDocument:
    """
    从文档移除一个音符。

    Args:
        document (ScoreDocument): 原始文档。
        group_index (int): 音符组索引。
        pitch (RollPitch): 待删除音高。

    Returns:
        ScoreDocument: 删除后的新文档。
    """

    return replace(document, groups=_groups_without_pitch(document, group_index, pitch))
