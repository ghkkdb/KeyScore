"""录制功能使用的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from ..models import Binding, Octave


@dataclass(frozen=True)
class PhysicalInputEvent:
    """表示从系统输入监听器收到的一次物理键鼠事件。"""

    timestamp_ms: float
    binding: Binding
    pressed: bool
    injected: bool = False


@dataclass(frozen=True)
class RecordedNote:
    """表示一次已经配对按下和释放时间的语义音符。"""

    start_ms: float
    end_ms: float
    degree: int
    octave: Octave
    is_semitone: bool = False


@dataclass(frozen=True)
class RecordingTake:
    """表示一次完成录制并已经归一化时间轴的演奏。"""

    notes: tuple[RecordedNote, ...]


@dataclass(frozen=True)
class RecordingSettings:
    """描述录制后转谱使用的节拍和识别参数。"""

    title: str
    bpm: int
    beat: str
    grid: Fraction = Fraction(1, 4)
    chord_tolerance_ms: int = 35
    legato_tolerance_ms: int = 20
    detect_legato: bool = True

    def validate(self) -> None:
        """
        校验转谱参数。

        Raises:
            ValueError: 参数超出支持范围或拍号格式无效时抛出。
        """

        if not self.title.strip():
            raise ValueError("曲名不能为空")
        if not 20 <= self.bpm <= 400:
            raise ValueError("BPM 必须在 20～400 之间")
        if self.grid <= 0:
            raise ValueError("量化精度必须大于 0")
        if not 10 <= self.chord_tolerance_ms <= 120:
            raise ValueError("和弦容差必须在 10～120ms 之间")
        if not 0 <= self.legato_tolerance_ms <= 100:
            raise ValueError("连音容差必须在 0～100ms 之间")
        parts = self.beat.split("/", maxsplit=1)
        if len(parts) != 2:
            raise ValueError("拍号格式必须类似 4/4")
        try:
            numerator, denominator = (int(part) for part in parts)
        except ValueError as exc:
            raise ValueError("拍号必须由整数构成") from exc
        if numerator <= 0 or denominator not in {2, 4, 8, 16}:
            raise ValueError("暂不支持该拍号")
