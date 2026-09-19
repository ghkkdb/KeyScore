"""不抢占游戏焦点的倒计时和播放信息悬浮层。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget


class _BaseOverlay(QWidget):
    """提供透明、置顶、不激活的悬浮窗口基类。"""

    def __init__(self) -> None:
        """初始化通用悬浮窗口标志和样式。"""

        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def _move_top_center(self, top: int) -> None:
        """
        将悬浮窗口移动到主显示器顶部居中位置。

        Args:
            top (int): 距显示器可用区域顶部的像素距离。
        """

        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        self.move(geometry.x() + (geometry.width() - self.width()) // 2, geometry.y() + top)


class CountdownOverlay(_BaseOverlay):
    """在屏幕中央显示等待提示和可配置的准备倒计时。"""

    def __init__(self) -> None:
        """初始化倒计时悬浮层。"""

        super().__init__()
        self.setFixedSize(360, 220)
        outer = QVBoxLayout(self)
        card = QFrame(objectName="overlayCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(8)
        self.number_label = QLabel("3")
        self.number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.number_label.setStyleSheet("font-size: 72px; font-weight: 400;")
        self.message_label = QLabel("即将开始演奏")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setStyleSheet("font-size: 17px; font-weight: 400;")
        self.title_label = QLabel("")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setObjectName("muted")
        self.hint_label = QLabel("F10 随时停止")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setObjectName("muted")
        layout.addWidget(self.number_label)
        layout.addWidget(self.message_label)
        layout.addWidget(self.title_label)
        layout.addStretch()
        layout.addWidget(self.hint_label)
        outer.addWidget(card)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._remaining = 0
        self._finished: Callable[[], None] | None = None

    def set_shortcuts(self, record_hotkey: str, stop_hotkey: str) -> None:
        """
        更新倒计时悬浮层中的快捷键提示。

        Args:
            record_hotkey (str): 录制快捷键显示文本。
            stop_hotkey (str): 停止快捷键显示文本。
        """

        self._record_hotkey = record_hotkey
        self._stop_hotkey = stop_hotkey

    def show_waiting(self, title: str, visible: bool = True) -> None:
        """
        显示等待用户切换到游戏的提示。

        Args:
            title (str): 待播放曲名。
            visible (bool): 是否显示悬浮提示。
        """

        self._timer.stop()
        self.number_label.setText("…")
        self.message_label.setText("等待切换到游戏")
        self.title_label.setText(f"《{title}》\n检测到游戏后将开始倒计时")
        self.hint_label.setText(f"{getattr(self, '_stop_hotkey', 'F10')} 随时停止")
        self._set_visible(visible)

    def show_recording_waiting(self, seconds: int = 3, visible: bool = True) -> None:
        """
        显示等待用户切换到游戏以开始录制的提示。

        Args:
            seconds (int): 切换到游戏后的倒计时秒数。
            visible (bool): 是否显示悬浮提示。
        """

        self._timer.stop()
        self.number_label.setText("●")
        self.message_label.setText("等待切换到游戏")
        self.title_label.setText(f"检测到游戏窗口后将开始 {seconds} 秒倒计时")
        self.hint_label.setText(f"{getattr(self, '_stop_hotkey', 'F10')} 随时停止")
        self._set_visible(visible)

    def start_countdown(
        self,
        title: str,
        finished: Callable[[], None],
        seconds: int = 3,
        visible: bool = True,
    ) -> None:
        """
        开始可配置时长的倒计时。

        Args:
            title (str): 待播放曲名。
            finished (Callable[[], None]): 倒计时完成回调。
            seconds (int): 倒计时秒数。
            visible (bool): 是否显示悬浮提示。
        """

        self._remaining = max(1, seconds)
        self._finished = finished
        self.number_label.setText(str(self._remaining))
        self.message_label.setText("即将开始演奏")
        self.title_label.setText(f"《{title}》")
        self.hint_label.setText(f"{getattr(self, '_stop_hotkey', 'F10')} 随时停止")
        self._set_visible(visible)
        self._timer.start(1000)

    def start_recording_countdown(
        self,
        finished: Callable[[], None],
        seconds: int = 3,
        visible: bool = True,
    ) -> None:
        """
        开始录制前的可配置准备倒计时。

        Args:
            finished (Callable[[], None]): 倒计时完成回调。
            seconds (int): 倒计时秒数。
            visible (bool): 是否显示悬浮提示。
        """

        self._remaining = max(1, seconds)
        self._finished = finished
        self.number_label.setText(str(self._remaining))
        self.message_label.setText("即将开始录制")
        self.title_label.setText("请准备演奏")
        record = getattr(self, "_record_hotkey", "F8")
        stop = getattr(self, "_stop_hotkey", "F10")
        self.hint_label.setText(f"{record} 完成    {stop} 紧急停止")
        self._set_visible(visible)
        self._timer.start(1000)

    def _set_visible(self, visible: bool) -> None:
        """
        根据设置显示或隐藏提示，但不影响倒计时计时器。

        Args:
            visible (bool): 是否显示悬浮层。
        """

        if visible:
            self.show()
            self._move_center()
        else:
            self.hide()

    def cancel(self) -> None:
        """取消倒计时并隐藏悬浮层。"""

        self._timer.stop()
        self._finished = None
        self.hide()

    def _move_center(self) -> None:
        """将窗口移动到主显示器中心。"""

        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        self.move(
            geometry.x() + (geometry.width() - self.width()) // 2,
            geometry.y() + (geometry.height() - self.height()) // 2,
        )

    def _tick(self) -> None:
        """更新倒计时文字并在结束时调用回调。"""

        self._remaining -= 1
        if self._remaining > 0:
            self.number_label.setText(str(self._remaining))
            return
        self._timer.stop()
        self.number_label.setText("▶")
        self.message_label.setText("开始")
        callback = self._finished
        self._finished = None
        QTimer.singleShot(250, self.hide)
        if callback is not None:
            callback()


class PlaybackOverlay(_BaseOverlay):
    """显示曲名、进度、当前音符和播放状态。"""

    def __init__(self) -> None:
        """初始化小型播放悬浮条。"""

        super().__init__()
        self.setFixedSize(500, 108)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame(objectName="overlayCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        self.title_label = QLabel("未命名曲谱")
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 500;")
        self.bpm_label = QLabel("100 BPM")
        self.bpm_label.setObjectName("muted")
        self.bpm_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self.title_label, 1)
        title_row.addWidget(self.bpm_label)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1000)

        info_row = QHBoxLayout()
        info_row.setSpacing(14)
        self.status_label = QLabel("准备中")
        self.note_label = QLabel("等待音符")
        self.note_label.setObjectName("muted")
        self.shortcut_label = QLabel("F9 暂停/继续    F10 停止")
        self.shortcut_label.setObjectName("muted")
        self.shortcut_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        info_row.addWidget(self.status_label)
        info_row.addWidget(self.note_label)
        info_row.addStretch()
        info_row.addWidget(self.shortcut_label)

        layout.addLayout(title_row)
        layout.addWidget(self.progress)
        layout.addLayout(info_row)
        outer.addWidget(card)

    def begin(self, title: str, bpm: int) -> None:
        """
        显示新的播放信息。

        Args:
            title (str): 曲名。
            bpm (int): 播放 BPM。
        """

        self.title_label.setText(title)
        self.bpm_label.setText(f"{bpm} BPM")
        self.progress.setValue(0)
        self.status_label.setText("准备中")
        self.note_label.setText("等待音符")
        self.show()
        self._move_top_center(32)

    def set_shortcuts(self, play_hotkey: str, stop_hotkey: str) -> None:
        """
        更新播放悬浮层中的快捷键提示。

        Args:
            play_hotkey (str): 播放控制快捷键显示文本。
            stop_hotkey (str): 停止快捷键显示文本。
        """

        self.shortcut_label.setText(f"{play_hotkey} 暂停/继续    {stop_hotkey} 停止")

    def update_playback(self, ratio: float, note_text: str, paused: bool) -> None:
        """
        更新播放进度和当前音符。

        Args:
            ratio (float): 0～1 的播放进度。
            note_text (str): 当前音符文本。
            paused (bool): 当前是否暂停。
        """

        self.progress.setValue(max(0, min(1000, int(ratio * 1000))))
        self.status_label.setText("已暂停" if paused else "演奏中")
        self.note_label.setText(note_text)


class RecordingOverlay(_BaseOverlay):
    """显示录制状态、时长、音符数量和当前音符。"""

    def __init__(self) -> None:
        """初始化录制悬浮条。"""

        super().__init__()
        self.setFixedSize(500, 104)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame(objectName="overlayCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(9)
        top = QHBoxLayout()
        self.status_label = QLabel("● 等待第一个音符")
        self.status_label.setStyleSheet("color: #D13438; font-weight: 700;")
        self.time_label = QLabel("00:00.0")
        self.time_label.setObjectName("muted")
        top.addWidget(self.status_label)
        top.addStretch()
        top.addWidget(self.time_label)
        bottom = QHBoxLayout()
        self.note_label = QLabel("当前：等待音符")
        self.note_label.setObjectName("muted")
        self.count_label = QLabel("已记录 0 个音符")
        self.count_label.setObjectName("muted")
        self.hint_label = QLabel("F8 完成    F10 紧急停止")
        self.hint_label.setObjectName("muted")
        bottom.addWidget(self.note_label)
        bottom.addWidget(self.count_label)
        bottom.addStretch()
        bottom.addWidget(self.hint_label)
        layout.addLayout(top)
        layout.addLayout(bottom)
        outer.addWidget(card)

    def set_shortcuts(self, record_hotkey: str, stop_hotkey: str) -> None:
        """
        更新录制悬浮层中的快捷键提示。

        Args:
            record_hotkey (str): 完成录制快捷键显示文本。
            stop_hotkey (str): 紧急停止快捷键显示文本。
        """

        self.hint_label.setText(f"{record_hotkey} 完成    {stop_hotkey} 紧急停止")

    def begin(self) -> None:
        """显示等待首个有效音符的初始状态。"""

        self.status_label.setText("● 等待第一个音符")
        self.time_label.setText("00:00.0")
        self.note_label.setText("当前：等待音符")
        self.count_label.setText("已记录 0 个音符")
        self.show()
        self._move_top_center(32)

    def update_recording(
        self,
        elapsed_ms: float,
        note_count: int,
        note_text: str,
        paused: bool,
    ) -> None:
        """
        更新录制悬浮条信息。

        Args:
            elapsed_ms (float): 已录制时间，不包含暂停区间。
            note_count (int): 已识别音符数量。
            note_text (str): 最近识别的音符文本。
            paused (bool): 是否因为目标窗口失焦而暂停。
        """

        total_seconds = max(0.0, elapsed_ms / 1000.0)
        minutes = int(total_seconds // 60)
        seconds = total_seconds - minutes * 60
        self.time_label.setText(f"{minutes:02d}:{seconds:04.1f}")
        self.status_label.setText("已暂停：请切回游戏" if paused else "● 正在录制")
        self.note_label.setText(f"当前：{note_text}")
        self.count_label.setText(f"已记录 {note_count} 个音符")
