"""把当前游戏配置的物理键鼠输入反向解码为音符。"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Binding, BindingKind, GameProfile, MappingMode, Octave
from .models import RecordedNote


BindingIdentity = tuple[BindingKind, int, bool]


class RecordingDecodeError(ValueError):
    """表示当前映射无法无歧义地反向解码。"""


@dataclass(frozen=True)
class DecodedNoteStart:
    """表示刚刚识别出的音符按下事件。"""

    degree: int
    octave: Octave
    is_semitone: bool


@dataclass(frozen=True)
class _ActiveNote:
    """保存等待释放的音符。"""

    start_ms: float
    degree: int
    octave: Octave
    is_semitone: bool


def binding_identity(binding: Binding) -> BindingIdentity:
    """
    返回不受显示名称影响的物理绑定标识。

    Args:
        binding (Binding): 键盘或鼠标绑定。

    Returns:
        BindingIdentity: 设备类型、代码和扩展键标记。
    """

    return binding.kind, binding.code, binding.extended


def recording_profile_conflicts(profile: GameProfile) -> tuple[str, ...]:
    """
    查找会导致录制反向映射歧义的重复绑定。

    Args:
        profile (GameProfile): 待检查的游戏配置。

    Returns:
        tuple[str, ...]: 可直接展示给用户的冲突说明。
    """

    usage: dict[BindingIdentity, list[str]] = {}

    def add(binding: Binding | None, description: str) -> None:
        """
        将一个可选绑定登记到用途索引。

        Args:
            binding (Binding | None): 待登记绑定，空值会被忽略。
            description (str): 绑定在配置中的语义用途。
        """

        if binding is None:
            return
        usage.setdefault(binding_identity(binding), []).append(description)

    if profile.mapping_mode is MappingMode.DEGREE_MODIFIER:
        for degree, binding in profile.note_bindings.items():
            add(binding, f"音级 {degree}")
        add(profile.zone_bindings.get(Octave.LOW), "低音修饰")
        add(profile.zone_bindings.get(Octave.HIGH), "高音修饰")
        add(profile.semitone_binding, "半音修饰")
    else:
        for key, binding in _active_direct_note_items(profile):
            add(binding, key)

    conflicts = []
    for descriptions in usage.values():
        if len(descriptions) > 1:
            conflicts.append("、".join(descriptions))
    return tuple(conflicts)


def recording_reserved_shortcuts(
    profile: GameProfile,
    shortcuts: tuple[tuple[int, str], ...] = (
        (0x42, "F8"),
        (0x43, "F9"),
        (0x44, "F10"),
    ),
) -> tuple[str, ...]:
    """
    查找占用了任一全局控制快捷键主键的演奏映射。

    Args:
        profile (GameProfile): 待检查的游戏配置。
        shortcuts (tuple[tuple[int, str], ...]): 扫描码与快捷键名称列表。

    Returns:
        tuple[str, ...]: 被占用的快捷键名称。
    """

    reserved = dict(shortcuts)
    bindings = list(profile.note_bindings.values())
    bindings.extend(profile.zone_bindings.values())
    bindings.append(profile.semitone_binding)
    bindings.extend(binding for _key, binding in _active_direct_note_items(profile))
    return tuple(
        sorted(
            {
                reserved[binding.code]
                for binding in bindings
                if binding.kind is BindingKind.KEYBOARD and binding.code in reserved
            }
        )
    )


def _pitch_from_key(key: str) -> tuple[int, Octave, bool]:
    """
    解析直接映射使用的稳定音符键名。

    Args:
        key (str): `octave:semitone:degree` 格式键名。

    Returns:
        tuple[int, Octave, bool]: 音级、音区和半音状态。

    Raises:
        RecordingDecodeError: 键名无效时抛出。
    """

    try:
        octave_text, semitone_text, degree_text = key.split(":")
        return int(degree_text), Octave(octave_text), bool(int(semitone_text))
    except (TypeError, ValueError) as exc:
        raise RecordingDecodeError(f"无法识别直接音符映射：{key}") from exc


def _active_direct_note_items(profile: GameProfile) -> tuple[tuple[str, Binding], ...]:
    """
    返回当前映射模式实际可见并可录制的直接音符绑定。

    Args:
        profile (GameProfile): 当前游戏配置。

    Returns:
        tuple[tuple[str, Binding], ...]: 当前模式使用的键名和绑定。
    """

    items: list[tuple[str, Binding]] = []
    for key, binding in profile.direct_note_bindings.items():
        _degree, octave, is_semitone = _pitch_from_key(key)
        if profile.mapping_mode is MappingMode.ROW_OCTAVE:
            if octave not in {Octave.LOW, Octave.MIDDLE, Octave.HIGH} or is_semitone:
                continue
        elif profile.mapping_mode is MappingMode.FIVE_ROW_OCTAVE and is_semitone:
            continue
        items.append((key, binding))
    return tuple(items)


class ProfileInputDecoder:
    """维护修饰键和活动音符状态，并输出完整录制音符。"""

    def __init__(self, profile: GameProfile) -> None:
        """
        创建当前配置的反向映射。

        Args:
            profile (GameProfile): 录制使用的游戏配置。

        Raises:
            RecordingDecodeError: 配置包含重复物理绑定时抛出。
        """

        conflicts = recording_profile_conflicts(profile)
        if conflicts:
            raise RecordingDecodeError(f"按键映射存在录制歧义：{'; '.join(conflicts)}")
        self._profile = profile
        self._pressed: set[BindingIdentity] = set()
        self._active: dict[BindingIdentity, _ActiveNote] = {}
        self._degree_by_binding = {
            binding_identity(binding): degree
            for degree, binding in profile.note_bindings.items()
        }
        self._pitch_by_binding = {
            binding_identity(binding): _pitch_from_key(key)
            for key, binding in _active_direct_note_items(profile)
        }

    @property
    def active_count(self) -> int:
        """返回当前尚未释放的语义音符数量。"""

        return len(self._active)

    def feed(
        self, binding: Binding, pressed: bool, timestamp_ms: float
    ) -> DecodedNoteStart | RecordedNote | None:
        """
        消费一次物理事件并返回新音符或已经释放的完整音符。

        Args:
            binding (Binding): 事件对应的物理绑定。
            pressed (bool): 是否为按下事件。
            timestamp_ms (float): 当前录制时间轴毫秒位置。

        Returns:
            DecodedNoteStart | RecordedNote | None: 状态变化产生的语义事件。

        Raises:
            RecordingDecodeError: 同时按下互斥音区修饰键时抛出。
        """

        identity = binding_identity(binding)
        if pressed:
            if identity in self._pressed:
                return None
            self._pressed.add(identity)
            pitch = self._decode_press(identity)
            if pitch is None:
                return None
            degree, octave, is_semitone = pitch
            self._active[identity] = _ActiveNote(
                timestamp_ms, degree, octave, is_semitone
            )
            return DecodedNoteStart(degree, octave, is_semitone)

        self._pressed.discard(identity)
        active = self._active.pop(identity, None)
        if active is None:
            return None
        return RecordedNote(
            active.start_ms,
            max(active.start_ms + 1.0, timestamp_ms),
            active.degree,
            active.octave,
            active.is_semitone,
        )

    def finish(self, timestamp_ms: float) -> tuple[RecordedNote, ...]:
        """
        在暂停或停止时强制关闭所有尚未释放的音符。

        Args:
            timestamp_ms (float): 关闭音符的录制时间轴位置。

        Returns:
            tuple[RecordedNote, ...]: 被强制关闭的音符。
        """

        notes = tuple(
            RecordedNote(
                active.start_ms,
                max(active.start_ms + 1.0, timestamp_ms),
                active.degree,
                active.octave,
                active.is_semitone,
            )
            for active in self._active.values()
        )
        self._active.clear()
        self._pressed.clear()
        return notes

    def _decode_press(
        self, identity: BindingIdentity
    ) -> tuple[int, Octave, bool] | None:
        """
        根据当前修饰键状态解释一次按下。

        Args:
            identity (BindingIdentity): 被按下的物理键标识。

        Returns:
            tuple[int, Octave, bool] | None: 语义音符，修饰键或无关键返回空。

        Raises:
            RecordingDecodeError: 高低音修饰键同时处于按下状态时抛出。
        """

        if self._profile.mapping_mode is not MappingMode.DEGREE_MODIFIER:
            return self._pitch_by_binding.get(identity)

        degree = self._degree_by_binding.get(identity)
        if degree is None:
            return None
        low = self._profile.zone_bindings.get(Octave.LOW)
        high = self._profile.zone_bindings.get(Octave.HIGH)
        low_pressed = low is not None and binding_identity(low) in self._pressed
        high_pressed = high is not None and binding_identity(high) in self._pressed
        if low_pressed and high_pressed:
            raise RecordingDecodeError("低音和高音修饰键不能同时按下")
        octave = Octave.LOW if low_pressed else Octave.HIGH if high_pressed else Octave.MIDDLE
        semitone = binding_identity(self._profile.semitone_binding) in self._pressed
        return degree, octave, semitone
