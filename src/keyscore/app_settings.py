"""应用级设置的读取与持久化。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ThemeId(str, Enum):
    """KeyScore 支持的界面主题。"""

    FLUENT = "fluent"
    ESPORTS = "esports"


@dataclass(frozen=True, slots=True)
class AppSettings:
    """与按键配置方案无关的全局应用设置。"""

    theme: ThemeId = ThemeId.FLUENT


def load_app_settings(path: Path) -> AppSettings:
    """
    读取应用设置；文件缺失、损坏或字段未知时使用安全默认值。

    Args:
        path (Path): 应用设置 JSON 文件路径。

    Returns:
        AppSettings: 校验后的应用设置。
    """

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return AppSettings()
        return AppSettings(theme=ThemeId(str(payload.get("theme", ThemeId.FLUENT.value))))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return AppSettings()


def save_app_settings(settings: AppSettings, path: Path) -> None:
    """
    原子写入应用设置，避免异常中断留下半份 JSON。

    Args:
        settings (AppSettings): 待保存的应用设置。
        path (Path): 应用设置 JSON 文件路径。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps({"theme": settings.theme.value}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
