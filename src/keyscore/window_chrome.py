"""无边框窗口外壳与自定义标题栏。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
from collections.abc import Callable

from PySide6.QtCore import QByteArray, QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygon,
    QRegion,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .resources import app_icon_path


def painted_icon(name: str, size: int = 32) -> QIcon:
    """
    绘制不依赖系统字体的单色界面图标。

    Args:
        name (str): 图标名称。
        size (int): 图标画布边长。

    Returns:
        QIcon: 包含默认、悬浮和选中状态的图标。
    """

    icon = QIcon()
    states = (
        (QIcon.Mode.Normal, QIcon.State.Off, QColor("#456487")),
        (QIcon.Mode.Active, QIcon.State.Off, QColor("#1687EF")),
        (QIcon.Mode.Normal, QIcon.State.On, QColor("#087AF0")),
        (QIcon.Mode.Active, QIcon.State.On, QColor("#087AF0")),
        (QIcon.Mode.Disabled, QIcon.State.Off, QColor("#9AA9B9")),
    )
    for mode, state, color in states:
        pixmap = QPixmap(QSize(size, size))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(
            QPen(
                color,
                max(2.0, size / 14.0),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        unit = size / 32.0
        if name == "music":
            painter.drawLine(int(12 * unit), int(9 * unit), int(12 * unit), int(23 * unit))
            painter.drawLine(int(23 * unit), int(6 * unit), int(23 * unit), int(20 * unit))
            painter.drawLine(int(12 * unit), int(9 * unit), int(23 * unit), int(6 * unit))
            painter.drawLine(int(12 * unit), int(13 * unit), int(23 * unit), int(10 * unit))
            painter.setBrush(color)
            painter.drawEllipse(
                int(5 * unit), int(20 * unit), int(8 * unit), int(6 * unit)
            )
            painter.drawEllipse(
                int(16 * unit), int(17 * unit), int(8 * unit), int(6 * unit)
            )
        elif name == "keyboard":
            painter.drawRoundedRect(
                int(5 * unit),
                int(9 * unit),
                int(22 * unit),
                int(15 * unit),
                int(3 * unit),
                int(3 * unit),
            )
            for column in range(4):
                x = int((9 + column * 5) * unit)
                painter.drawPoint(x, int(14 * unit))
            painter.drawLine(int(10 * unit), int(19 * unit), int(22 * unit), int(19 * unit))
        elif name == "settings":
            painter.drawEllipse(int(10 * unit), int(10 * unit), int(12 * unit), int(12 * unit))
            painter.drawEllipse(int(14 * unit), int(14 * unit), int(4 * unit), int(4 * unit))
            for start_x, start_y, end_x, end_y in (
                (16, 5, 16, 9),
                (16, 23, 16, 27),
                (5, 16, 9, 16),
                (23, 16, 27, 16),
                (8, 8, 11, 11),
                (21, 21, 24, 24),
                (24, 8, 21, 11),
                (11, 21, 8, 24),
            ):
                painter.drawLine(
                    int(start_x * unit),
                    int(start_y * unit),
                    int(end_x * unit),
                    int(end_y * unit),
                )
        elif name == "info":
            painter.drawEllipse(int(6 * unit), int(6 * unit), int(20 * unit), int(20 * unit))
            painter.drawLine(int(16 * unit), int(14 * unit), int(16 * unit), int(21 * unit))
            painter.drawPoint(int(16 * unit), int(10 * unit))
        elif name in {"play", "previous", "next"}:
            if name in {"previous", "next"}:
                line_x = 8 if name == "previous" else 24
                painter.drawLine(int(line_x * unit), int(8 * unit), int(line_x * unit), int(24 * unit))
            painter.setBrush(color)
            if name == "previous":
                points = [(23, 8), (10, 16), (23, 24)]
            else:
                points = [(10, 8), (23, 16), (10, 24)]
            painter.drawPolygon(
                QPolygon(
                    [QPoint(int(x * unit), int(y * unit)) for x, y in points]
                )
            )
        elif name == "stop":
            painter.setBrush(color)
            painter.drawRoundedRect(
                int(9 * unit),
                int(9 * unit),
                int(14 * unit),
                int(14 * unit),
                int(2 * unit),
                int(2 * unit),
            )
        elif name == "record":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#F04452"))
            painter.drawEllipse(int(9 * unit), int(9 * unit), int(14 * unit), int(14 * unit))
        painter.end()
        icon.addPixmap(pixmap, mode, state)
    return icon


class AppLogo(QWidget):
    """显示 KeyScore 内置应用图标。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        初始化应用标识。

        Args:
            parent (QWidget | None): 父级容器。
        """

        super().__init__(parent, objectName="appLogo")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedSize(52, 52)
        self._pixmap = QPixmap(str(app_icon_path()))
        self._scaled_pixmap = QPixmap()
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self) -> None:
        """按当前屏幕缩放比预生成高分辨率图标缓存。"""

        if self._pixmap.isNull():
            self._scaled_pixmap = QPixmap()
            return
        ratio = max(1.0, self.devicePixelRatioF())
        physical_size = QSize(
            max(1, round(self.width() * ratio)),
            max(1, round(self.height() * ratio)),
        )
        self._scaled_pixmap = self._pixmap.scaled(
            physical_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._scaled_pixmap.setDevicePixelRatio(ratio)

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        按控件尺寸平滑缩放并绘制应用图标。

        Args:
            event (QPaintEvent): Qt 重绘事件。
        """

        super().paintEvent(event)
        if self._scaled_pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        x = (self.width() - self._scaled_pixmap.width() / self._scaled_pixmap.devicePixelRatio()) / 2
        y = (self.height() - self._scaled_pixmap.height() / self._scaled_pixmap.devicePixelRatio()) / 2
        painter.drawPixmap(QPoint(round(x), round(y)), self._scaled_pixmap)
        painter.end()


def _draw_combo_chevron(widget: QWidget, painter: QPainter) -> None:
    """
    在选择控件右侧绘制清晰的下拉箭头。

    Args:
        widget (QWidget): 箭头所属的选择控件。
        painter (QPainter): 当前控件的绘图器。
    """

    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#6A82A3" if widget.isEnabled() else "#AAB4C0")
    painter.setPen(
        QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    )
    center_x = widget.width() - 18
    center_y = widget.height() // 2
    painter.drawLine(center_x - 4, center_y - 2, center_x, center_y + 2)
    painter.drawLine(center_x, center_y + 2, center_x + 4, center_y - 2)


class _RoundedOptionsPopup(QFrame):
    """用透明顶层窗口实现的真圆角选项弹层。"""

    def __init__(
        self,
        anchor: QWidget,
        options: list[str],
        current_index: int,
        on_selected: Callable[[int], None],
    ) -> None:
        """
        创建一个可自动关闭的选项弹层。

        Args:
            anchor (QWidget): 弹层对齐的选择控件。
            options (list[str]): 需要显示的选项文字。
            current_index (int): 当前选中项索引。
            on_selected (Callable[[int], None]): 点击选项后的回调。
        """

        flags = (
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        super().__init__(anchor, flags)
        self.setObjectName("smoothPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._anchor = anchor
        self._on_selected = on_selected

        popup_layout = QVBoxLayout(self)
        popup_layout.setContentsMargins(7, 7, 7, 7)
        popup_layout.setSpacing(0)
        scroll = QScrollArea(objectName="smoothPopupScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget(objectName="smoothPopupContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)
        for index, text in enumerate(options):
            button = QPushButton(text, objectName="smoothOption")
            button.setProperty("selected", index == current_index)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setFixedHeight(36)
            button.clicked.connect(
                lambda _checked=False, item_index=index: self._select(item_index)
            )
            content_layout.addWidget(button)
        content_layout.addStretch()
        scroll.setWidget(content)
        popup_layout.addWidget(scroll)

        visible_items = min(max(1, len(options)), 8)
        self.resize(max(180, anchor.width()), visible_items * 38 + 14)

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        绘制真透明圆角背景，避免顶层弹层出现直角底色。

        Args:
            event (QPaintEvent): Qt 重绘事件。
        """

        _ = event
        esports = QApplication.instance().property("theme") == "esports"
        background = QColor("#0B1429" if esports else "#FFFFFF")
        border = QColor("#245487" if esports else "#D3E2F0")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(background)
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 13, 13)
        painter.end()

    def show_aligned(self) -> None:
        """在锹点控件下方显示弹层，超出屏幕时自动翻到上方。"""

        position = self._anchor.mapToGlobal(QPoint(0, self._anchor.height() + 5))
        screen = QApplication.screenAt(position) or self._anchor.screen()
        if screen is not None:
            available = screen.availableGeometry()
            if position.y() + self.height() > available.bottom():
                position.setY(
                    self._anchor.mapToGlobal(QPoint(0, 0)).y()
                    - self.height()
                    - 5
                )
            if position.x() + self.width() > available.right():
                position.setX(available.right() - self.width())
            position.setX(max(position.x(), available.left()))
        self.move(position)
        self.show()
        self.raise_()

    def _select(self, index: int) -> None:
        """
        提交选中项并关闭弹层。

        Args:
            index (int): 被点击的选项索引。
        """

        self._on_selected(index)
        self.close()


class RoundedShell(QWidget):
    """通过几何遮罩防止子控件覆盖窗口外壳圆角。"""

    def __init__(self, radius: float = 24.0, parent: QWidget | None = None) -> None:
        """
        初始化可动态更新圆角的窗口外壳。

        Args:
            radius (float): 默认圆角半径。
            parent (QWidget | None): 父级容器。
        """

        super().__init__(parent, objectName="appShell")
        self._corner_radius = radius

    def set_corner_radius(self, radius: float) -> None:
        """
        更新外壳圆角半径和遮罩。

        Args:
            radius (float): 新的圆角半径，为零时移除遮罩。
        """

        self._corner_radius = max(0.0, radius)
        self._update_mask()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        尺寸变化时同步更新圆角遮罩。

        Args:
            event (QResizeEvent): Qt 尺寸变化事件。
        """

        super().resizeEvent(event)
        self._update_mask()

    def _update_mask(self) -> None:
        """按当前尺寸与半径生成外壳裁剪遮罩。"""

        if self._corner_radius <= 0 or self.width() <= 0 or self.height() <= 0:
            self.clearMask()
            return
        path = QPainterPath()
        path.addRoundedRect(
            0.0,
            0.0,
            float(self.width()),
            float(self.height()),
            self._corner_radius,
            self._corner_radius,
        )
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))


class SmoothComboBox(QComboBox):
    """使用自绘箭头和真圆角弹层的通用组合框。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        初始化通用圆角组合框。

        Args:
            parent (QWidget | None): 父级容器。
        """

        super().__init__(parent, objectName="smoothComboBox")
        self._smooth_popup: _RoundedOptionsPopup | None = None

    def showPopup(self) -> None:
        """显示自定义圆角选项弹层。"""

        if self.count() <= 0:
            return
        self.hidePopup()
        self._smooth_popup = _RoundedOptionsPopup(
            self,
            [self.itemText(index) for index in range(self.count())],
            self.currentIndex(),
            self.setCurrentIndex,
        )
        self._smooth_popup.show_aligned()

    def hidePopup(self) -> None:
        """关闭活动的自定义选项弹层。"""

        if self._smooth_popup is not None:
            self._smooth_popup.close()
            self._smooth_popup.deleteLater()
            self._smooth_popup = None

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        绘制组合框内容和自定义下拉箭头。

        Args:
            event (QPaintEvent): Qt 重绘事件。
        """

        super().paintEvent(event)
        painter = QPainter(self)
        _draw_combo_chevron(self, painter)
        painter.end()


class SmoothSpinBox(QSpinBox):
    """隐藏系统原生按钮并使用自绘步进按钮的数字框。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        初始化统一风格的数字框。

        Args:
            parent (QWidget | None): 父级容器。
        """

        super().__init__(parent, objectName="smoothSpinBox")
        self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.setMouseTracking(True)
        self._hover_step = 0

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        根据指针位置更新上下步进区域的悬浮状态。

        Args:
            event (QMouseEvent): 鼠标移动事件。
        """

        previous = self._hover_step
        if event.position().x() >= self.width() - 30:
            self._hover_step = 1 if event.position().y() < self.height() / 2 else -1
        else:
            self._hover_step = 0
        if previous != self._hover_step:
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """
        鼠标离开数字框时清除步进按钮悬浮状态。

        Args:
            event (QEvent): Qt 离开事件。
        """

        self._hover_step = 0
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        点击右侧上下区域时执行数值步进。

        Args:
            event (QMouseEvent): 鼠标按下事件。
        """

        if (
            event.button() is Qt.MouseButton.LeftButton
            and event.position().x() >= self.width() - 30
        ):
            if event.position().y() < self.height() / 2:
                self.stepUp()
            else:
                self.stepDown()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        绘制数值框和统一的上下步进箭头。

        Args:
            event (QPaintEvent): Qt 重绘事件。
        """

        super().paintEvent(event)
        application = QApplication.instance()
        esports = application is not None and application.property("theme") == "esports"
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        step_rect_x = self.width() - 30
        if self._hover_step != 0 and self.isEnabled():
            hover = QColor("#153150" if esports else "#E6F2FF")
            top = 1 if self._hover_step > 0 else self.height() // 2
            height = self.height() // 2 - 1
            painter.fillRect(step_rect_x, top, 29, height, hover)
        divider = QColor("#25477C" if esports else "#D4E2EF")
        arrow = QColor("#8EB9D8" if esports else "#5F7899")
        painter.setPen(QPen(divider, 1.0))
        painter.drawLine(step_rect_x, 5, step_rect_x, self.height() - 5)
        painter.setPen(
            QPen(arrow, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        center_x = self.width() - 15
        upper_y = self.height() // 4 + 1
        lower_y = self.height() * 3 // 4 - 1
        painter.drawLine(center_x - 4, upper_y + 2, center_x, upper_y - 2)
        painter.drawLine(center_x, upper_y - 2, center_x + 4, upper_y + 2)
        painter.drawLine(center_x - 4, lower_y - 2, center_x, lower_y + 2)
        painter.drawLine(center_x, lower_y + 2, center_x + 4, lower_y - 2)
        painter.end()


class ProfileSelector(QPushButton):
    """使用自绘箭头和圆角菜单的配置方案选择器。"""

    currentIndexChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        初始化方案选择器。

        Args:
            parent (QWidget | None): 父级容器。
        """

        super().__init__(parent, objectName="profileSelector")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(210)
        self.setFixedHeight(42)
        self.setAccessibleName("当前配置方案")
        self._items: list[tuple[str, object]] = []
        self._current_index = -1
        self._placeholder = ""
        self._smooth_popup: _RoundedOptionsPopup | None = None
        self.clicked.connect(lambda _checked=False: self._show_menu())

    def clear(self) -> None:
        """清空所有方案并重置当前选项。"""

        changed = self._current_index != -1
        self._items.clear()
        if self._smooth_popup is not None:
            self._smooth_popup.close()
            self._smooth_popup.deleteLater()
            self._smooth_popup = None
        self._current_index = -1
        self.setText(self._placeholder)
        if changed:
            self.currentIndexChanged.emit(-1)

    def addItem(self, text: str, user_data: object = None) -> None:
        """
        添加一个可选方案。

        Args:
            text (str): 方案显示名称。
            user_data (object): 与方案关联的数据。
        """

        self._items.append((text, user_data))
        if self._current_index < 0:
            self.setCurrentIndex(0)

    def count(self) -> int:
        """
        返回方案数量。

        Returns:
            int: 当前可选方案数量。
        """

        return len(self._items)

    def currentIndex(self) -> int:
        """
        返回当前方案索引。

        Returns:
            int: 当前索引，无选项时为 -1。
        """

        return self._current_index

    def setCurrentIndex(self, index: int) -> None:
        """
        选中指定索引的方案。

        Args:
            index (int): 目标方案索引。
        """

        if not 0 <= index < len(self._items) or index == self._current_index:
            return
        self._current_index = index
        self.setText(self._items[index][0])
        self.currentIndexChanged.emit(index)

    def itemData(self, index: int) -> object:
        """
        返回指定方案的关联数据。

        Args:
            index (int): 方案索引。

        Returns:
            object: 关联数据，索引无效时为 `None`。
        """

        return self._items[index][1] if 0 <= index < len(self._items) else None

    def itemText(self, index: int) -> str:
        """
        返回指定方案的显示名称。

        Args:
            index (int): 方案索引。

        Returns:
            str: 显示名称，索引无效时为空字符串。
        """

        return self._items[index][0] if 0 <= index < len(self._items) else ""

    def findData(self, data: object) -> int:
        """
        查找关联数据对应的方案索引。

        Args:
            data (object): 需要匹配的关联数据。

        Returns:
            int: 匹配的索引，未找到时为 -1。
        """

        for index, (_text, value) in enumerate(self._items):
            if value == data:
                return index
        return -1

    def setEditText(self, text: str) -> None:
        """
        更新选择器显示文字，兼容原有组合框调用。

        Args:
            text (str): 需要显示的文字。
        """

        self.setText(text)

    def setPlaceholderText(self, text: str) -> None:
        """
        设置没有方案时的占位文字。

        Args:
            text (str): 占位文字。
        """

        self._placeholder = text
        if self._current_index < 0:
            self.setText(text)

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        绘制选择器内容和高分辨率下清晰的下拉箭头。

        Args:
            event (QPaintEvent): Qt 重绘事件。
        """

        super().paintEvent(event)
        painter = QPainter(self)
        _draw_combo_chevron(self, painter)
        painter.end()

    def _show_menu(self) -> None:
        """重建并在选择器下方显示圆角方案菜单。"""

        if not self._items:
            return
        if self._smooth_popup is not None:
            self._smooth_popup.close()
            self._smooth_popup.deleteLater()
        self._smooth_popup = _RoundedOptionsPopup(
            self,
            [text for text, _data in self._items],
            self._current_index,
            self.setCurrentIndex,
        )
        self._smooth_popup.show_aligned()


class FramelessMainWindow(QMainWindow):
    """提供 Windows 无边框窗口常用行为。"""

    maximized_changed = Signal(bool)

    _RESIZE_BORDER = 8

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        初始化可透明、可缩放的无边框主窗口。

        Args:
            parent (QWidget | None): 父级窗口。
        """

        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def changeEvent(self, event: QEvent) -> None:
        """
        在最大化状态变化时通知窗口外壳更新圆角。

        Args:
            event (QEvent): Qt 状态变化事件。
        """

        super().changeEvent(event)
        if event.type() is QEvent.Type.WindowStateChange:
            self.maximized_changed.emit(self.isMaximized())

    def nativeEvent(self, event_type: QByteArray, message: int) -> tuple[bool, int]:
        """
        在 Windows 上为无边框窗口恢复四边和四角缩放。

        Args:
            event_type (QByteArray): 原生事件类型。
            message (int): Windows 消息指针。

        Returns:
            tuple[bool, int]: 是否处理事件及命中测试结果。
        """

        if sys.platform != "win32" or self.isMaximized() or self.isFullScreen():
            return super().nativeEvent(event_type, message)

        msg = ctypes.wintypes.MSG.from_address(int(message))
        wm_nchittest = 0x0084
        if msg.message != wm_nchittest:
            return super().nativeEvent(event_type, message)

        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        frame = self.frameGeometry()
        border = self._RESIZE_BORDER
        left = x < frame.left() + border
        right = x >= frame.right() - border
        top = y < frame.top() + border
        bottom = y >= frame.bottom() - border

        if top and left:
            return True, 13  # HTTOPLEFT
        if top and right:
            return True, 14  # HTTOPRIGHT
        if bottom and left:
            return True, 16  # HTBOTTOMLEFT
        if bottom and right:
            return True, 17  # HTBOTTOMRIGHT
        if left:
            return True, 10  # HTLEFT
        if right:
            return True, 11  # HTRIGHT
        if top:
            return True, 12  # HTTOP
        if bottom:
            return True, 15  # HTBOTTOM
        return super().nativeEvent(event_type, message)


class WindowTitleBar(QWidget):
    """集成品牌信息和系统窗口按钮的自定义标题栏。"""

    def __init__(
        self,
        title: str,
        subtitle: str,
        parent: QWidget | None = None,
    ) -> None:
        """
        创建标题栏。

        Args:
            title (str): 应用名称。
            subtitle (str): 应用标语。
            parent (QWidget | None): 所属窗口内容容器。
        """

        super().__init__(parent, objectName="windowTitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(70)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 10, 0, 8)
        layout.setSpacing(12)

        logo = AppLogo()
        brand = QLabel(title, objectName="brand")
        separator = QLabel("│", objectName="brandSeparator")
        tagline = QLabel(subtitle, objectName="brandSubtitle")

        self.minimize_button = QToolButton(objectName="windowMinimize")
        self.minimize_button.setText("−")
        self.minimize_button.setToolTip("最小化")
        self.maximize_button = QToolButton(objectName="windowMaximize")
        self.maximize_button.setText("□")
        self.maximize_button.setToolTip("最大化")
        self.close_button = QToolButton(objectName="windowClose")
        self.close_button.setText("×")
        self.close_button.setToolTip("关闭")
        for button in (
            self.minimize_button,
            self.maximize_button,
            self.close_button,
        ):
            button.setFixedSize(56, 42)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.minimize_button.clicked.connect(lambda: self.window().showMinimized())
        self.maximize_button.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(lambda: self.window().close())

        layout.addWidget(logo)
        layout.addWidget(brand)
        layout.addWidget(separator)
        layout.addWidget(tagline)
        layout.addStretch()
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

    def toggle_maximized(self) -> None:
        """在最大化和普通窗口状态之间切换。"""

        window = self.window()
        if window.isMaximized():
            window.showNormal()
        else:
            window.showMaximized()
        self.update_maximize_state(window.isMaximized())

    def update_maximize_state(self, maximized: bool) -> None:
        """
        更新最大化按钮的图标和提示。

        Args:
            maximized (bool): 窗口当前是否已最大化。
        """

        self.maximize_button.setText("❐" if maximized else "□")
        self.maximize_button.setToolTip("还原" if maximized else "最大化")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        在标题栏空白区域按下左键时启动系统窗口拖动。

        Args:
            event (QMouseEvent): 鼠标按下事件。
        """

        if event.button() is Qt.MouseButton.LeftButton:
            window = self.window()
            if window.isMaximized():
                horizontal_ratio = event.position().x() / max(1, self.width())
                global_position = event.globalPosition().toPoint()
                window.showNormal()
                window.move(
                    int(global_position.x() - window.width() * horizontal_ratio),
                    global_position.y() - 24,
                )
            handle = window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """
        双击标题栏时切换最大化状态。

        Args:
            event (QMouseEvent): 鼠标双击事件。
        """

        if event.button() is Qt.MouseButton.LeftButton:
            self.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
