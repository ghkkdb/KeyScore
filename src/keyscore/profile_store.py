"""游戏按键映射的 JSON 持久化。"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Binding, BindingKind, GameProfile, Octave, ZoneMode, default_profile


def save_profile(profile: GameProfile, path: Path) -> None:
    """
    将当前游戏配置保存为 JSON。

    Args:
        profile (GameProfile): 待保存配置。
        path (Path): JSON 文件路径。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": profile.name,
        "zone_mode": profile.zone_mode.value,
        "initial_zone": profile.initial_zone.value,
        "key_hold_ms": profile.key_hold_ms,
        "key_gap_ms": profile.key_gap_ms,
        "zone_delay_ms": profile.zone_delay_ms,
        "zone_click_ms": profile.zone_click_ms,
        "notes": {str(key): _binding_to_dict(value) for key, value in profile.note_bindings.items()},
        "zones": {
            key.value: _binding_to_dict(value)
            for key, value in profile.zone_bindings.items()
            if key in (Octave.LOW, Octave.HIGH)
        },
        "semitone": _binding_to_dict(profile.semitone_binding),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_profile(path: Path) -> GameProfile:
    """
    读取游戏配置，文件缺失或损坏时返回默认值。

    Args:
        path (Path): JSON 文件路径。

    Returns:
        GameProfile: 已恢复或默认配置。
    """

    if not path.exists():
        return default_profile()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fallback = default_profile()
        zone_payload = payload["zones"]
        if not isinstance(zone_payload, dict):
            raise ValueError("音区配置格式无效")
        legacy_middle = zone_payload.get(Octave.MIDDLE.value)
        semitone_payload = payload.get("semitone", legacy_middle)
        profile = GameProfile(
            name=str(payload.get("name", "默认配置")),
            note_bindings={
                int(key): _binding_from_dict(value) for key, value in payload["notes"].items()
            },
            zone_bindings={
                Octave(key): _binding_from_dict(value)
                for key, value in zone_payload.items()
                if key in (Octave.LOW.value, Octave.HIGH.value)
            },
            semitone_binding=(
                _binding_from_dict(semitone_payload)
                if semitone_payload is not None
                else fallback.semitone_binding
            ),
            zone_mode=ZoneMode.COMBINATION,
            initial_zone=Octave(payload.get("initial_zone", Octave.MIDDLE.value)),
            key_hold_ms=int(payload.get("key_hold_ms", 50)),
            key_gap_ms=int(payload.get("key_gap_ms", 10)),
            zone_delay_ms=int(payload.get("zone_delay_ms", 35)),
            zone_click_ms=int(payload.get("zone_click_ms", 20)),
        )
        for degree, binding in fallback.note_bindings.items():
            profile.note_bindings.setdefault(degree, binding)
        for octave, binding in fallback.zone_bindings.items():
            profile.zone_bindings.setdefault(octave, binding)
        return profile
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return default_profile()


def _binding_to_dict(binding: Binding) -> dict[str, object]:
    """
    将绑定转换为 JSON 兼容字典。

    Args:
        binding (Binding): 待转换绑定。

    Returns:
        dict[str, object]: 可序列化字典。
    """

    return {
        "kind": binding.kind.value,
        "code": binding.code,
        "label": binding.label,
        "extended": binding.extended,
    }


def _binding_from_dict(value: object) -> Binding:
    """
    将 JSON 字典转换为绑定。

    Args:
        value (object): 已解析 JSON 值。

    Returns:
        Binding: 恢复的绑定。

    Raises:
        ValueError: 值不是有效绑定字典时抛出。
    """

    if not isinstance(value, dict):
        raise ValueError("绑定格式无效")
    return Binding(
        BindingKind(str(value["kind"])),
        int(value["code"]),
        str(value["label"]),
        bool(value.get("extended", False)),
    )
