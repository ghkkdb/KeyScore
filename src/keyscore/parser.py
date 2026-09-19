"""文本简谱解析器。"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from fractions import Fraction

from .models import NoteEvent, Octave, Score


_TOKEN_PATTERN = re.compile(
    r"\[[^\]]+\](?::\d+(?:\.\d+)?)?|\(|\)|[^\s|()]+|\|"
)
_NOTE_PATTERN = re.compile(
    r"^(?P<sharp>#?)(?P<octave>LL|HH|L|H)?(?P<degree>[0-7])(?::(?P<duration>\d+(?:\.\d+)?))?$"
)
_CHORD_PATTERN = re.compile(r"^\[(?P<body>[^\]]+)\](?::(?P<duration>\d+(?:\.\d+)?))?$")


class ScoreParseError(ValueError):
    """表示曲谱文本不符合简谱语法。"""

    def __init__(self, message: str, line: int, token: str) -> None:
        """
        初始化带位置信息的解析异常。

        Args:
            message (str): 错误说明。
            line (int): 出错的一基行号。
            token (str): 触发错误的词元。
        """

        super().__init__(f"第 {line} 行，`{token}`：{message}")
        self.line = line
        self.token = token


@dataclass(frozen=True)
class _ParsedToken:
    """表示一个可能包含多个同时音符的解析结果。"""

    notes: tuple[tuple[int, Octave, bool], ...]
    duration: Fraction


def _parse_duration(value: str | None, line: int, token: str) -> Fraction:
    """
    将时值文本转换为精确分数。

    Args:
        value (str | None): 冒号后的时值，缺省为一拍。
        line (int): 词元所在行号。
        token (str): 原始词元。

    Returns:
        Fraction: 以拍为单位的时值。

    Raises:
        ScoreParseError: 时值不大于零或无法解析时抛出。
    """

    try:
        duration = Fraction(value or "1")
    except (ValueError, ZeroDivisionError) as exc:
        raise ScoreParseError("时值格式无效", line, token) from exc
    if duration <= 0:
        raise ScoreParseError("时值必须大于 0", line, token)
    return duration


def _octave_from_prefix(prefix: str) -> Octave:
    """
    将音区前缀转换为枚举。

    Args:
        prefix (str): `LL`、`L`、`H`、`HH` 或空字符串。

    Returns:
        Octave: 对应音区。
    """

    return {
        "LL": Octave.LOWEST,
        "L": Octave.LOW,
        "H": Octave.HIGH,
        "HH": Octave.HIGHEST,
    }.get(prefix, Octave.MIDDLE)


def _parse_single(token: str, line: int, allow_rest: bool = True) -> _ParsedToken:
    """
    解析一个单音或休止符词元。

    Args:
        token (str): 待解析词元。
        line (int): 词元所在行号。
        allow_rest (bool): 是否允许休止符 0。

    Returns:
        _ParsedToken: 解析结果。

    Raises:
        ScoreParseError: 词元不符合简谱语法时抛出。
    """

    match = _NOTE_PATTERN.fullmatch(token)
    if match is None:
        raise ScoreParseError("音符格式无效", line, token)
    degree = int(match.group("degree"))
    if degree == 0 and not allow_rest:
        raise ScoreParseError("和弦内不能包含休止符", line, token)
    duration = _parse_duration(match.group("duration"), line, token)
    if degree == 0 and match.group("sharp"):
        raise ScoreParseError("休止符不能使用半音修饰", line, token)
    notes = (
        ()
        if degree == 0
        else ((degree, _octave_from_prefix(match.group("octave")), bool(match.group("sharp"))),)
    )
    return _ParsedToken(notes=notes, duration=duration)


def _parse_token(token: str, line: int) -> _ParsedToken:
    """
    解析单音、休止符或和弦词元。

    Args:
        token (str): 待解析词元。
        line (int): 词元所在行号。

    Returns:
        _ParsedToken: 解析结果。

    Raises:
        ScoreParseError: 和弦时值冲突或语法无效时抛出。
    """

    chord_match = _CHORD_PATTERN.fullmatch(token)
    if chord_match is None:
        return _parse_single(token, line)

    body_tokens = chord_match.group("body").split()
    if not body_tokens:
        raise ScoreParseError("和弦不能为空", line, token)
    chord_duration = _parse_duration(chord_match.group("duration"), line, token)
    notes: list[tuple[int, Octave, bool]] = []
    for body_token in body_tokens:
        parsed = _parse_single(body_token, line, allow_rest=False)
        if parsed.duration != 1:
            raise ScoreParseError("和弦内部不能单独指定时值", line, token)
        notes.extend(parsed.notes)
    return _ParsedToken(notes=tuple(notes), duration=chord_duration)


def parse_score(text: str) -> Score:
    """
    将文本简谱解析为内部曲谱模型。

    Args:
        text (str): 包含元数据和简谱的完整文本。

    Returns:
        Score: 已解析的曲谱。

    Raises:
        ScoreParseError: 元数据或音符格式错误时抛出。
    """

    metadata: dict[str, str] = {}
    metadata_lines: dict[str, int] = {}
    score_lines: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("@"):
            parts = line[1:].split(maxsplit=1)
            if len(parts) != 2:
                raise ScoreParseError("元数据需要名称和值", line_number, line)
            metadata_key = parts[0].lower()
            metadata[metadata_key] = parts[1].strip()
            metadata_lines[metadata_key] = line_number
        else:
            score_lines.append((line_number, line))

    try:
        bpm = int(metadata.get("bpm", "100"))
    except ValueError as exc:
        raise ScoreParseError("BPM 必须是整数", 1, metadata.get("bpm", "")) from exc
    if not 20 <= bpm <= 400:
        raise ScoreParseError("BPM 必须在 20～400 之间", 1, str(bpm))

    section_gap_value = metadata.get("section_gap", "1")
    section_gap = _parse_duration(
        section_gap_value,
        metadata_lines.get("section_gap", 1),
        f"@section_gap {section_gap_value}",
    )

    position = Fraction(0)
    notes: list[NoteEvent] = []
    extendable_note_indices: list[int] | None = None
    in_legato = False
    legato_open_line = 0
    legato_unit_count = 0
    legato_previous_indices: list[int] | None = None
    for line_number, line in score_lines:
        if line == "---":
            if in_legato:
                raise ScoreParseError("连音组内不能包含段落停顿", line_number, line)
            position += section_gap
            extendable_note_indices = None
            continue
        for token in _TOKEN_PATTERN.findall(line):
            if token == "(":
                if in_legato:
                    raise ScoreParseError("连音组不能嵌套", line_number, token)
                in_legato = True
                legato_open_line = line_number
                legato_unit_count = 0
                legato_previous_indices = None
                extendable_note_indices = None
                continue
            if token == ")":
                if not in_legato:
                    raise ScoreParseError("缺少连音组开始符号 `(`", line_number, token)
                if legato_unit_count < 2:
                    raise ScoreParseError("连音组至少需要两个音符或和弦", line_number, token)
                in_legato = False
                legato_previous_indices = None
                continue
            if token == "|":
                continue
            if token == "-":
                if extendable_note_indices is None:
                    raise ScoreParseError("增时线前必须有音符、和弦或休止符", line_number, token)
                for note_index in extendable_note_indices:
                    notes[note_index] = replace(
                        notes[note_index],
                        duration_beats=notes[note_index].duration_beats + 1,
                    )
                position += 1
                continue
            parsed = _parse_token(token, line_number)
            if in_legato and not parsed.notes:
                raise ScoreParseError("连音组内不能包含休止符", line_number, token)
            if in_legato and legato_previous_indices is not None:
                for note_index in legato_previous_indices:
                    notes[note_index] = replace(notes[note_index], legato_to_next=True)
            first_note_index = len(notes)
            for degree, octave, is_semitone in parsed.notes:
                notes.append(
                    NoteEvent(
                        start_beat=position,
                        duration_beats=parsed.duration,
                        degree=degree,
                        octave=octave,
                        is_semitone=is_semitone,
                    )
                )
            extendable_note_indices = list(range(first_note_index, len(notes)))
            if in_legato:
                legato_previous_indices = extendable_note_indices
                legato_unit_count += 1
            position += parsed.duration

    if in_legato:
        raise ScoreParseError("连音组缺少结束符号 `)`", legato_open_line, "(")

    if position == 0:
        raise ScoreParseError("曲谱中没有可播放的内容", 1, "")
    return Score(
        title=metadata.get("title", "未命名曲谱"),
        bpm=bpm,
        beat=metadata.get("beat", "4/4"),
        notes=tuple(notes),
        total_beats=position,
    )
