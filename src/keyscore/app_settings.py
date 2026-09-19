"""应用级设置的读取与持久化。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
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
        if len({record_hotkey, play_hotkey, stop_hotkey}) != 3:
            record_hotkey = defaults.record_hotkey
            play_hotkey = defaults.play_hotkey
            stop_hotkey = defaults.stop_hotkey
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
