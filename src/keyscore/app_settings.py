"""应用级设置的读取与持久化。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from fractions import Fraction
from pathlib import Path

from .hotkeys import HotkeyValidationError, normalize_hotkey


class ThemeId(str, Enum):
    """KeyScore 支持的界面主题。"""

    FLUENT = "fluent"
    ESPORTS = "esports"


@dataclass(frozen=True, slots=True)
class AppSettings:
    """与按键配置方案无关的全局应用设置。"""

    theme: ThemeId = ThemeId.FLUENT
    record_hotkey: str = "F8"
    play_hotkey: str = "F9"
    stop_hotkey: str = "F10"
    duration_cycle_hotkey: str = "D"
    duration_reverse_hotkey: str = "A"
    duration_presets: tuple[str, ...] = ("1/4", "1/2", "3/4", "1", "2", "4")
    default_note_duration: str = "1/4"
    score_sort_mode: str = "modified"
    show_playback_overlay: bool = True
    countdown_seconds: int = 3
    show_countdown_overlay: bool = True


def _read_hotkey(payload: dict[str, object], key: str, default: str) -> str:
    """
    从设置对象中读取并校验一个全局快捷键。

    Args:
        payload (dict[str, object]): 设置文件解析结果。
        key (str): 字段名称。
        default (str): 校验失败时采用的默认快捷键。

    Returns:
        str: 规范化后的快捷键文本。
    """

    value = payload.get(key, default)
    if not isinstance(value, str):
        return default
    try:
        return normalize_hotkey(value)
    except HotkeyValidationError:
        return default


def _read_bool(payload: dict[str, object], key: str, default: bool) -> bool:
    """
    读取严格布尔设置，避免将字符串误判为开启状态。

    Args:
        payload (dict[str, object]): 设置文件解析结果。
        key (str): 字段名称。
        default (bool): 字段无效时采用的默认值。

    Returns:
        bool: 校验后的布尔值。
    """

    value = payload.get(key, default)
    return value if isinstance(value, bool) else default


def normalize_duration(value: str) -> str:
    """
    校验并规范化一个编辑器音符拍数。

    Args:
        value (str): 分数、小数或整数拍数。

    Returns:
        str: 约分后的稳定拍数字符串。

    Raises:
        ValueError: 拍数不是 1/64～64 范围内的正数时抛出。
    """

    try:
        duration = Fraction(value.strip())
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("拍数必须是整数、小数或分数") from exc
    if not Fraction(1, 64) <= duration <= 64:
        raise ValueError("拍数必须在 1/64～64 之间")
    if duration.denominator == 1:
        return str(duration.numerator)
    return f"{duration.numerator}/{duration.denominator}"


def _read_duration_presets(
    payload: dict[str, object], defaults: AppSettings
) -> tuple[tuple[str, ...], str]:
    """
    读取、校验并去重用户的常用拍数和默认拍数。

    Args:
        payload (dict[str, object]): 设置文件解析结果。
        defaults (AppSettings): 安全默认设置。

    Returns:
        tuple[tuple[str, ...], str]: 规范拍数列表和默认拍数。
    """

    raw_presets = payload.get("duration_presets", defaults.duration_presets)
    if not isinstance(raw_presets, (list, tuple)):
        return defaults.duration_presets, defaults.default_note_duration
    presets: list[str] = []
    try:
        for raw in raw_presets:
            if not isinstance(raw, str):
                raise ValueError
            normalized = normalize_duration(raw)
            if normalized not in presets:
                presets.append(normalized)
    except ValueError:
        return defaults.duration_presets, defaults.default_note_duration
    if not presets:
        return defaults.duration_presets, defaults.default_note_duration
    raw_default = payload.get("default_note_duration", defaults.default_note_duration)
    try:
        default_duration = normalize_duration(str(raw_default))
    except ValueError:
        default_duration = defaults.default_note_duration
    if default_duration not in presets:
        default_duration = presets[0]
    return tuple(presets), default_duration


def load_app_settings(path: Path) -> AppSettings:
    """
    读取应用设置；文件缺失、损坏或字段未知时使用安全默认值。

    Args:
        path (Path): 应用设置 JSON 文件路径。

    Returns:
        AppSettings: 校验后的应用设置。
    """

    defaults = AppSettings()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return defaults
        try:
            theme = ThemeId(str(payload.get("theme", defaults.theme.value)))
        except ValueError:
            theme = defaults.theme
        record_hotkey = _read_hotkey(payload, "record_hotkey", defaults.record_hotkey)
        play_hotkey = _read_hotkey(payload, "play_hotkey", defaults.play_hotkey)
        stop_hotkey = _read_hotkey(payload, "stop_hotkey", defaults.stop_hotkey)
        duration_cycle_hotkey = _read_hotkey(
            payload, "duration_cycle_hotkey", defaults.duration_cycle_hotkey
        )
        duration_reverse_hotkey = _read_hotkey(
            payload, "duration_reverse_hotkey", defaults.duration_reverse_hotkey
        )
        if len(
            {
                record_hotkey,
                play_hotkey,
                stop_hotkey,
                duration_cycle_hotkey,
                duration_reverse_hotkey,
            }
        ) != 5:
            record_hotkey = defaults.record_hotkey
            play_hotkey = defaults.play_hotkey
            stop_hotkey = defaults.stop_hotkey
            duration_cycle_hotkey = defaults.duration_cycle_hotkey
            duration_reverse_hotkey = defaults.duration_reverse_hotkey
        duration_presets, default_note_duration = _read_duration_presets(
            payload, defaults
        )
        score_sort_value = payload.get("score_sort_mode", defaults.score_sort_mode)
        score_sort_mode = (
            score_sort_value
            if score_sort_value in {"modified", "title"}
            else defaults.score_sort_mode
        )
        countdown_value = payload.get("countdown_seconds", defaults.countdown_seconds)
        countdown_seconds = (
            countdown_value
            if isinstance(countdown_value, int)
            and not isinstance(countdown_value, bool)
            and 1 <= countdown_value <= 10
            else defaults.countdown_seconds
        )
        return AppSettings(
            theme=theme,
            record_hotkey=record_hotkey,
            play_hotkey=play_hotkey,
            stop_hotkey=stop_hotkey,
            duration_cycle_hotkey=duration_cycle_hotkey,
            duration_reverse_hotkey=duration_reverse_hotkey,
            duration_presets=duration_presets,
            default_note_duration=default_note_duration,
            score_sort_mode=score_sort_mode,
            show_playback_overlay=_read_bool(
                payload,
                "show_playback_overlay",
                defaults.show_playback_overlay,
            ),
            countdown_seconds=countdown_seconds,
            show_countdown_overlay=_read_bool(
                payload,
                "show_countdown_overlay",
                defaults.show_countdown_overlay,
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        return defaults


def save_app_settings(settings: AppSettings, path: Path) -> None:
    """
    原子写入应用设置，避免异常中断留下半份 JSON。

    Args:
        settings (AppSettings): 待保存的应用设置。
        path (Path): 应用设置 JSON 文件路径。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    payload = asdict(settings)
    payload["theme"] = settings.theme.value
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
