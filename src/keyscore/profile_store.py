"""游戏按键映射的 JSON 持久化。"""

from __future__ import annotations

import json
from pathlib import Path

from .models import (
    Binding,
    BindingKind,
    GameProfile,
    MappingMode,
    NoteOutputMode,
    Octave,
    ZoneMode,
    default_profile,
)


def save_profile(profile: GameProfile, path: Path) -> None:
    """
    将当前游戏配置保存为 JSON。

    Args:
        profile (GameProfile): 待保存配置。
        path (Path): JSON 文件路径。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 5,
        "name": profile.name,
        "mapping_mode": profile.mapping_mode.value,
        "note_output_mode": profile.note_output_mode.value,
        "zone_mode": profile.zone_mode.value,
        "initial_zone": profile.initial_zone.value,
        "key_hold_ms": profile.key_hold_ms,
        "key_gap_ms": profile.key_gap_ms,
        "zone_delay_ms": profile.zone_delay_ms,
        "zone_click_ms": profile.zone_click_ms,
        "notes": {
            str(key): _binding_to_dict(value)
            for key, value in profile.note_bindings.items()
            if 1 <= key <= 7
        },
        "zones": {
            key.value: _binding_to_dict(value)
            for key, value in profile.zone_bindings.items()
            if key in (Octave.LOW, Octave.HIGH)
        },
        "semitone": _binding_to_dict(profile.semitone_binding),
        "direct_notes": {
            key: _binding_to_dict(value) for key, value in profile.direct_note_bindings.items()
        },
        "metadata": profile.metadata,
    }
    temporary_path = path.with_name(f"{path.name}.tmp")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(path)


def load_profile(path: Path) -> GameProfile:
    """
    读取游戏配置，文件缺失或损坏时返回默认值。

    Args:
        path (Path): JSON 文件路径。

    Returns:
        GameProfile: 已恢复或默认配置。
    """

    try:
        return load_profile_strict(path)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return default_profile()


def load_profile_strict(path: Path) -> GameProfile:
    """
    严格读取一个 Profile，格式错误时直接报告异常。

    Args:
        path (Path): 待读取的 Profile 文件。

    Returns:
        GameProfile: 校验并恢复的配置方案。

    Raises:
        OSError: 文件读取失败时抛出。
        ValueError: Profile 结构或字段无效时抛出。
        json.JSONDecodeError: JSON 语法错误时抛出。
    """

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Profile 根节点必须是 JSON 对象")
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Profile 缺少方案名称")
    note_payload = payload.get("notes")
    zone_payload = payload.get("zones")
    direct_payload = payload.get("direct_notes", {})
    metadata_payload = payload.get("metadata", {})
    if not isinstance(note_payload, dict):
        raise ValueError("音级配置格式无效")
    if not isinstance(zone_payload, dict):
        raise ValueError("音区配置格式无效")
    if not isinstance(direct_payload, dict):
        raise ValueError("直接音符配置格式无效")
    if not isinstance(metadata_payload, dict):
        raise ValueError("Profile 元数据格式无效")

    fallback = default_profile()
    legacy_middle = zone_payload.get(Octave.MIDDLE.value)
    semitone_payload = payload.get("semitone", legacy_middle)
    mapping_mode_value = payload.get("mapping_mode", MappingMode.DEGREE_MODIFIER.value)
    if mapping_mode_value == "virtual_piano":
        mapping_mode_value = MappingMode.DIRECT_NOTE.value
    profile = GameProfile(
        name=name,
        note_bindings={
            degree: _binding_from_dict(value)
            for key, value in note_payload.items()
            if 1 <= (degree := int(key)) <= 7
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
        zone_mode=ZoneMode(payload.get("zone_mode", ZoneMode.COMBINATION.value)),
        initial_zone=Octave(payload.get("initial_zone", Octave.MIDDLE.value)),
        note_output_mode=NoteOutputMode(
            payload.get("note_output_mode", NoteOutputMode.TAP.value)
        ),
        key_hold_ms=int(payload.get("key_hold_ms", 50)),
        key_gap_ms=int(payload.get("key_gap_ms", 10)),
        zone_delay_ms=int(payload.get("zone_delay_ms", 35)),
        zone_click_ms=int(payload.get("zone_click_ms", 20)),
        mapping_mode=MappingMode(mapping_mode_value),
        direct_note_bindings={
            str(key): _binding_from_dict(value) for key, value in direct_payload.items()
        },
        metadata={str(key): str(value) for key, value in metadata_payload.items()},
    )
    for degree, binding in fallback.note_bindings.items():
        profile.note_bindings.setdefault(degree, binding)
    for octave, binding in fallback.zone_bindings.items():
        profile.zone_bindings.setdefault(octave, binding)
    return profile


def list_profile_paths(directory: Path) -> list[Path]:
    """
    返回配置目录中的全部方案文件。

    Args:
        directory (Path): Profile 保存目录。

    Returns:
        list[Path]: 按文件名排序的方案文件路径。
    """

    if not directory.exists():
        return []
    return sorted(directory.glob("*.ksprofile.json"), key=lambda item: item.name.casefold())


def profile_path_for_name(directory: Path, name: str) -> Path:
    """
    根据方案名称生成安全且稳定的保存路径。

    Args:
        directory (Path): Profile 保存目录。
        name (str): 用户可见的方案名称。

    Returns:
        Path: 对应的 JSON 保存路径。
    """

    safe_name = "".join(character for character in name.strip() if character not in '\\/:*?\"<>|')
    return directory / f"{safe_name or '未命名配置'}.ksprofile.json"


def save_profile_with_name(
    profile: GameProfile,
    current_path: Path,
    directory: Path,
    name: str,
) -> Path:
    """
    以用户指定名称保存 Profile；名称变化时保留原方案并另存新方案。

    Args:
        profile (GameProfile): 待保存配置。
        current_path (Path): 当前 Profile 文件路径。
        directory (Path): 本地 Profile 目录。
        name (str): 用户输入的方案名称。

    Returns:
        Path: 保存后的当前 Profile 文件路径。

    Raises:
        OSError: 文件保存失败时抛出。
        ValueError: 名称为空、发生重名或当前文件不属于 Profile 目录时抛出。
    """

    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("方案名称不能为空")
    destination = profile_path_for_name(directory, normalized_name)
    current_resolved = current_path.resolve()
    directory_resolved = directory.resolve()
    if current_resolved.parent != directory_resolved:
        raise ValueError("当前配置不属于本地 Profile 目录")
    if destination.exists() and destination.resolve() != current_resolved:
        raise ValueError("同名配置方案已存在")

    original_name = profile.name
    profile.name = normalized_name
    try:
        save_profile(profile, destination)
    except (OSError, ValueError):
        profile.name = original_name
        raise
    return destination


def import_profile(source: Path, directory: Path) -> Path:
    """
    校验并将外部 Profile 持久化到本地配置目录。

    Args:
        source (Path): 外部 `.ksprofile.json` 文件。
        directory (Path): 本地 Profile 目录。

    Returns:
        Path: 导入后的本地 Profile 路径。

    Raises:
        OSError: 文件读取或保存失败时抛出。
        ValueError: 文件扩展名或 Profile 内容无效时抛出。
    """

    if not source.name.lower().endswith(".ksprofile.json"):
        raise ValueError("请选择 .ksprofile.json 配置文件")
    profile = load_profile_strict(source)
    destination = profile_path_for_name(directory, profile.name)
    suffix = 2
    while destination.exists():
        destination = profile_path_for_name(directory, f"{profile.name} {suffix}")
        suffix += 1
    save_profile(profile, destination)
    return destination


def save_active_profile(path: Path, state_path: Path) -> None:
    """
    持久化当前选中的 Profile 文件名。

    Args:
        path (Path): 当前 Profile 路径。
        state_path (Path): 当前方案状态文件。
    """

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"active_profile": path.name}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_active_profile(directory: Path, state_path: Path) -> Path | None:
    """
    恢复上次选中的本地 Profile。

    Args:
        directory (Path): 本地 Profile 目录。
        state_path (Path): 当前方案状态文件。

    Returns:
        Path | None: 有效的上次方案路径；无法恢复时返回 `None`。
    """

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        filename = str(payload["active_profile"])
        candidate = directory / Path(filename).name
        if candidate in list_profile_paths(directory):
            return candidate
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return None


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
        "modifiers": [_binding_to_dict(value) for value in binding.modifiers],
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
    modifiers_payload = value.get("modifiers", [])
    if not isinstance(modifiers_payload, list):
        raise ValueError("绑定修饰键格式无效")
    return Binding(
        BindingKind(str(value["kind"])),
        int(value["code"]),
        str(value["label"]),
        bool(value.get("extended", False)),
        tuple(_binding_from_dict(item) for item in modifiers_payload),
    )
