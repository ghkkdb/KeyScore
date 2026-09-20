"""基于单调时钟的绝对时间轴播放器。"""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Callable

from .input_backend import InputBackend
from .models import PlaybackPlan, TimedInputEvent


class PlaybackState(str, Enum):
    """表示播放器的当前状态。"""

    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPING = "stopping"


class TimelinePlayer:
    """在独立线程中按绝对时间戳执行输入事件。"""

    def __init__(
        self,
        backend: InputBackend,
        on_state_change: Callable[[PlaybackState], None] | None = None,
        on_event: Callable[[TimedInputEvent, float], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """
        初始化播放器。

        Args:
            backend (InputBackend): 真实或测试输入后端。
            on_state_change (Callable[[PlaybackState], None] | None): 状态变化回调。
            on_event (Callable[[TimedInputEvent, float], None] | None): 事件发送后回调。
            on_error (Callable[[Exception], None] | None): 播放异常回调。
        """

        self._backend = backend
        self._on_state_change = on_state_change
        self._on_event = on_event
        self._on_error = on_error
        self._plan: PlaybackPlan | None = None
        self._state = PlaybackState.STOPPED
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None
        self._stop_requested = False
        self._started_at = 0.0
        self._paused_at = 0.0
        self._paused_position_ms = 0.0

    @property
    def state(self) -> PlaybackState:
        """
        返回当前播放状态。

        Returns:
            PlaybackState: 当前状态。
        """

        with self._condition:
            return self._state

    @property
    def position_ms(self) -> float:
        """
        返回当前播放位置。

        Returns:
            float: 从时间轴起点计算的毫秒数。
        """

        with self._condition:
            if self._state is PlaybackState.PAUSED:
                return self._paused_position_ms
            if self._state is PlaybackState.PLAYING:
                return max(0.0, (time.perf_counter() - self._started_at) * 1000.0)
            return self._paused_position_ms

    def load(self, plan: PlaybackPlan) -> None:
        """
        装载一份播放计划。

        Args:
            plan (PlaybackPlan): 待播放计划。

        Raises:
            RuntimeError: 播放器未停止时抛出。
        """

        with self._condition:
            if self._state is not PlaybackState.STOPPED:
                raise RuntimeError("只能在停止状态装载新曲谱")
            self._plan = plan
            self._paused_position_ms = 0.0

    def play(self) -> None:
        """
        开始播放或从暂停位置继续。

        Raises:
            RuntimeError: 尚未装载播放计划时抛出。
        """

        with self._condition:
            if self._plan is None:
                raise RuntimeError("尚未装载播放计划")
            if self._state is PlaybackState.PLAYING:
                return
            if self._state is PlaybackState.PAUSED:
                paused_duration = time.perf_counter() - self._paused_at
                self._started_at += paused_duration
                self._set_state_locked(PlaybackState.PLAYING)
                self._condition.notify_all()
                return
            self._stop_requested = False
            self._paused_position_ms = 0.0
            self._started_at = time.perf_counter()
            self._set_state_locked(PlaybackState.PLAYING)
            self._thread = threading.Thread(target=self._run, name="KeyScorePlayer", daemon=True)
            self._thread.start()

    def pause(self) -> None:
        """暂停播放并立即释放所有已按下的按键。"""

        with self._condition:
            if self._state is not PlaybackState.PLAYING:
                return
            self._paused_at = time.perf_counter()
            self._paused_position_ms = (self._paused_at - self._started_at) * 1000.0
            self._set_state_locked(PlaybackState.PAUSED)
        self._backend.release_all()

    def stop(self, wait: bool = False) -> None:
        """
        请求停止播放并释放所有按键。

        Args:
            wait (bool): 是否等待播放线程结束。
        """

        with self._condition:
            if self._state is PlaybackState.STOPPED:
                self._backend.release_all()
                return
            self._stop_requested = True
            self._set_state_locked(PlaybackState.STOPPING)
            self._condition.notify_all()
            thread = self._thread
        self._backend.release_all()
        if wait and thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def _set_state_locked(self, state: PlaybackState) -> None:
        """
        在已持有条件锁时更新状态并调用回调。

        Args:
            state (PlaybackState): 新状态。
        """

        self._state = state
        if self._on_state_change is not None:
            self._on_state_change(state)

    def _run(self) -> None:
        """执行已装载计划的工作线程主循环。"""

        plan = self._plan
        if plan is None:
            return
        index = 0
        completed = False
        try:
            while index < len(plan.events):
                with self._condition:
                    while self._state is PlaybackState.PAUSED and not self._stop_requested:
                        self._condition.wait()
                    if self._stop_requested:
                        break
                    event = plan.events[index]
                    remaining = event.timestamp_ms / 1000.0 - (time.perf_counter() - self._started_at)
                    if remaining > 0:
                        self._condition.wait(timeout=min(remaining, 0.02))
                        continue
                self._backend.emit(event)
                if self._on_event is not None:
                    self._on_event(event, event.timestamp_ms)
                index += 1

            if not self._stop_requested:
                while True:
                    remaining = plan.duration_ms / 1000.0 - (time.perf_counter() - self._started_at)
                    if remaining <= 0:
                        break
                    with self._condition:
                        if self._stop_requested:
                            break
                        self._condition.wait(timeout=min(remaining, 0.02))
            completed = not self._stop_requested
        except Exception as exc:  # noqa: BLE001 - 工作线程必须保证最终释放按键
            if self._on_error is not None:
                self._on_error(exc)
        finally:
            self._backend.release_all()
            with self._condition:
                self._paused_position_ms = plan.duration_ms if completed else 0.0
                self._stop_requested = False
                self._set_state_locked(PlaybackState.STOPPED)
                self._thread = None
