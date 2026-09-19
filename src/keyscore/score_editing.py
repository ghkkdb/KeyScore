"""曲谱编辑器使用的纯文本变换工具。"""

from __future__ import annotations

import re
from dataclasses import dataclass


_TOKEN_PATTERN = re.compile(
    r"\[[^\]]+\](?::\d+(?:\.\d+)?)?|\(|\)|[^\s|()]+|\|"
)
_NOTE_PATTERN = re.compile(r"#?[LH]?[0-7](?::\d+(?:\.\d+)?)?")
_CHORD_PATTERN = re.compile(r"\[(?P<body>[^\]]+)\](?::\d+(?:\.\d+)?)?")
_CHORD_NOTE_PATTERN = re.compile(r"#?[LH]?[1-7]")
_DURATION_PATTERN = re.compile(r"\d+(?:\.\d+)?")
_DURATION_SUFFIX_PATTERN = re.compile(r":\d+(?:\.\d+)?$")


@dataclass(frozen=True)
class ScoreEditResult:
    """描述一次曲谱文本变换的结果。"""

    text: str
    cursor_position: int
    changed_count: int


@dataclass(frozen=True)
class _ScoreToken:
    """记录一个曲谱正文词元及其文本位置。"""

    text: str
    start: int
    end: int
    kind: str


def _is_editable_token(token: str) -> bool:
    """
    判断词元是否为可设置时值的音符、休止符或和弦。

    Args:
        token (str): 待判断的曲谱词元。

    Returns:
        bool: 词元可以设置时值时返回 True。
    """

    if _NOTE_PATTERN.fullmatch(token) is not None:
        return True
    match = _CHORD_PATTERN.fullmatch(token)
    if match is None:
        return False
    notes = match.group("body").split()
    return bool(notes) and all(_CHORD_NOTE_PATTERN.fullmatch(note) for note in notes)


def _score_tokens(source: str) -> list[_ScoreToken]:
    """
    扫描曲谱正文并保留词元的绝对文本位置。

    Args:
        source (str): 完整曲谱文本。

    Returns:
        list[_ScoreToken]: 曲谱正文词元列表。
    """

    tokens: list[_ScoreToken] = []
    offset = 0
    for raw_line in source.splitlines(keepends=True):
        content = raw_line.rstrip("\r\n")
        stripped = content.strip()
        if stripped.startswith("@"):
            offset += len(raw_line)
            continue
        if stripped == "---":
            start = offset + content.index("---")
            tokens.append(_ScoreToken("---", start, start + 3, "barrier"))
            offset += len(raw_line)
            continue
        for match in _TOKEN_PATTERN.finditer(content):
            value = match.group(0)
            if _is_editable_token(value):
                kind = "editable"
            elif value == "-":
                kind = "sustain"
            elif value == "|":
                kind = "bar"
            else:
                kind = "barrier"
            tokens.append(
                _ScoreToken(
                    value,
                    offset + match.start(),
                    offset + match.end(),
                    kind,
                )
            )
        offset += len(raw_line)
    return tokens


def _canonical_duration(value: str) -> str:
    """
    校验并规范化编辑器使用的十进制拍数。

    Args:
        value (str): 用户指定的拍数文本。

    Returns:
        str: 去除无意义前导零和末尾零后的拍数。

    Raises:
        ValueError: 拍数格式无效或不大于零时抛出。
    """

    if _DURATION_PATTERN.fullmatch(value) is None:
        raise ValueError("时值必须是大于 0 的整数或小数")
    integer, separator, decimal = value.partition(".")
    integer = integer.lstrip("0") or "0"
    decimal = decimal.rstrip("0")
    normalized = f"{integer}.{decimal}" if separator and decimal else integer
    if normalized == "0":
        raise ValueError("时值必须大于 0")
    return normalized


def _without_duration(token: str) -> str:
    """
    删除音符、休止符或和弦末尾已有的时值。

    Args:
        token (str): 可编辑曲谱词元。

    Returns:
        str: 不含时值后缀的词元。
    """

    return _DURATION_SUFFIX_PATTERN.sub("", token)


def _expanded_sustain_span(source: str, token: _ScoreToken) -> tuple[int, int]:
    """
    扩展增时线删除范围，并一并清理一侧的水平空白。

    Args:
        source (str): 完整曲谱文本。
        token (_ScoreToken): 要删除的增时线词元。

    Returns:
        tuple[int, int]: 半开区间形式的删除范围。
    """

    end = token.end
    while end < len(source) and source[end] in " \t":
        end += 1
    if end > token.end:
        return token.start, end
    start = token.start
    while start > 0 and source[start - 1] in " \t":
        start -= 1
    return start, token.end


def _transform_position(
    position: int, replacements: list[tuple[int, int, str]]
) -> int:
    """
    将原文本位置换算为所有替换完成后的文本位置。

    Args:
        position (int): 原文本中的位置。
        replacements (list[tuple[int, int, str]]): 原文本坐标下的替换列表。

    Returns:
        int: 新文本中的对应位置。
    """

    transformed = position
    for start, end, replacement in sorted(replacements):
        if end <= position:
            transformed += len(replacement) - (end - start)
        elif start < position < end:
            transformed = start + len(replacement)
            position = end
    return transformed


def set_total_duration(
    source: str, selection_start: int, selection_end: int, duration: str
) -> ScoreEditResult:
    """
    为光标所在或选中的曲谱词元设置精确总时值。

    与目标词元关联、位于下一个可播放词元之前的增时线会被删除，确保
    最终总时值与指定值一致。元数据、段落标记和小节线不会被修改。

    Args:
        source (str): 完整曲谱文本。
        selection_start (int): 选择区域起点，未选择时等于终点。
        selection_end (int): 选择区域终点。
        duration (str): 大于零的整数或小数拍数。

    Returns:
        ScoreEditResult: 修改后的文本、光标位置和修改数量。

    Raises:
        ValueError: 时值格式无效时抛出。
    """

    normalized_duration = _canonical_duration(duration)
    start = min(selection_start, selection_end)
    end = max(selection_start, selection_end)
    tokens = _score_tokens(source)
    editable_indices: list[int] = []
    if start == end:
        candidates = [
            index
            for index, token in enumerate(tokens)
            if token.kind == "editable" and token.start <= start <= token.end
        ]
        if candidates:
            editable_indices.append(candidates[-1])
    else:
        editable_indices.extend(
            index
            for index, token in enumerate(tokens)
            if token.kind == "editable" and token.start >= start and token.end <= end
        )

    if not editable_indices:
        return ScoreEditResult(source, end, 0)

    replacements: list[tuple[int, int, str]] = []
    sustain_indices: set[int] = set()
    for index in editable_indices:
        token = tokens[index]
        base = _without_duration(token.text)
        replacement = base if normalized_duration == "1" else f"{base}:{normalized_duration}"
        replacements.append((token.start, token.end, replacement))
        for following_index in range(index + 1, len(tokens)):
            following = tokens[following_index]
            if following.kind == "bar":
                continue
            if following.kind == "sustain":
                sustain_indices.add(following_index)
                continue
            break

    sustain_spans = sorted(
        _expanded_sustain_span(source, tokens[index]) for index in sustain_indices
    )
    merged_sustain_spans: list[tuple[int, int]] = []
    for sustain_start, sustain_end in sustain_spans:
        if merged_sustain_spans and sustain_start <= merged_sustain_spans[-1][1]:
            previous_start, previous_end = merged_sustain_spans[-1]
            merged_sustain_spans[-1] = (
                previous_start,
                max(previous_end, sustain_end),
            )
        else:
            merged_sustain_spans.append((sustain_start, sustain_end))
    replacements.extend(
        (sustain_start, sustain_end, "")
        for sustain_start, sustain_end in merged_sustain_spans
    )

    result = source
    for replace_start, replace_end, replacement in sorted(replacements, reverse=True):
        result = result[:replace_start] + replacement + result[replace_end:]
    cursor_position = _transform_position(tokens[editable_indices[-1]].end, replacements)
    return ScoreEditResult(result, cursor_position, len(editable_indices))
