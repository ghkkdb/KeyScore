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
    """在屏幕中央显示等待提示和 3秒准备倒计时。"""

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

    def show_waiting(self, title: str) -> None:
        """
        显示等待用户切换到游戏的提示。

        Args:
            title (str): 待播放曲名。
        """

        self._timer.stop()
        self.number_label.setText("…")
        self.message_label.setText("等待切换到游戏")
        self.title_label.setText(f"《{title}》\n检测到游戏后将开始倒计时")
        self.show()
        self._move_center()

    def start_countdown(self, title: str, finished: Callable[[], None]) -> None:
        """
        开始 3 秒倒计时。

        Args:
            title (str): 待播放曲名。
            finished (Callable[[], None]): 倒计时完成回调。
        """

        self._remaining = 3
        self._finished = finished
        self.number_label.setText("3")
        self.message_label.setText("即将开始演奏")
        self.title_label.setText(f"《{title}》")
        self.show()
        self._move_center()
        self._timer.start(1000)

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
