"""键谱的核心数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction


class Octave(str, Enum):
    """表示简谱音区。"""

    LOW = "low"
    MIDDLE = "middle"
    HIGH = "high"


class ZoneMode(str, Enum):
    """表示音区按键的工作模式。"""

    SWITCH = "switch"
    COMBINATION = "combination"


class BindingKind(str, Enum):
    """表示绑定的输入设备类型。"""

    KEYBOARD = "keyboard"
    MOUSE = "mouse"


class ActionType(str, Enum):
    """表示定时输入事件类型。"""

    PRESS = "press"
    RELEASE = "release"


@dataclass(frozen=True)
class Binding:
    """描述一个键盘扫描码或鼠标按键绑定。"""

    kind: BindingKind
    code: int
    label: str
    extended: bool = False


@dataclass(frozen=True)
class NoteEvent:
    """表示已解析的一个音符。"""

    start_beat: Fraction
    duration_beats: Fraction
    degree: int
    octave: Octave
    is_semitone: bool = False


@dataclass(frozen=True)
class Score:
    """表示一份完整的内部曲谱。"""

    title: str
    bpm: int
    beat: str
    notes: tuple[NoteEvent, ...]
    total_beats: Fraction


@dataclass(frozen=True)
class TimedInputEvent:
    """表示从播放起点计算的绝对时间输入事件。"""

    timestamp_ms: float
    action: ActionType
    binding: Binding
    note: NoteEvent | None = None


@dataclass(frozen=True)
class PlaybackPlan:
    """表示可交给播放器执行的完整时间轴。"""

    title: str
    bpm: int
    events: tuple[TimedInputEvent, ...]
    duration_ms: float


@dataclass
class GameProfile:
    """描述游戏的音符、音区和播放参数。"""

    name: str
    note_bindings: dict[int, Binding]
    zone_bindings: dict[Octave, Binding]
    semitone_binding: Binding
    zone_mode: ZoneMode = ZoneMode.COMBINATION
    initial_zone: Octave = Octave.MIDDLE
    key_hold_ms: int = 50
    key_gap_ms: int = 10
    zone_delay_ms: int = 35
    zone_click_ms: int = 20
    metadata: dict[str, str] = field(default_factory=dict)


def default_profile() -> GameProfile:
    """
    创建使用 A、S、D、F、G、H、J、K 扫描码的默认配置。

    Returns:
        GameProfile: 适合进行首次调试的默认游戏配置。
    """

    scan_codes = {
        1: 0x1E,
        2: 0x1F,
        3: 0x20,
        4: 0x21,
        5: 0x22,
        6: 0x23,
        7: 0x24,
        8: 0x25,
    }
    labels = {1: "A", 2: "S", 3: "D", 4: "F", 5: "G", 6: "H", 7: "J", 8: "K"}
    return GameProfile(
        name="默认配置",
        note_bindings={
            degree: Binding(BindingKind.KEYBOARD, code, labels[degree])
            for degree, code in scan_codes.items()
        },
        zone_bindings={
            Octave.LOW: Binding(BindingKind.MOUSE, 1, "鼠标左键"),
            Octave.HIGH: Binding(BindingKind.MOUSE, 2, "鼠标右键"),
        },
        semitone_binding=Binding(BindingKind.MOUSE, 3, "鼠标中键"),
    )
