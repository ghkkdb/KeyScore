"""可复用的 KeyScore 钢琴卷帘预览与编辑控件。"""

from __future__ import annotations

from fractions import Fraction
from math import ceil, floor

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QResizeEvent,
    QUndoCommand,
    QUndoStack,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QStyleOptionGraphicsItem,
    QWidget,
)

from .score_document import (
    RollPitch,
    ScoreDocument,
    add_note,
    pitch_from_index,
    pitch_index,
    pitch_text,
    remove_note,
)


_MAX_PITCH_INDEX = 59


class _OverviewBar(QWidget):
    """显示整首曲谱并控制卷帘时间与音阶位置的导航缩略图。"""

    def __init__(self, owner: PianoRollEditor) -> None:
        """
        创建与卷帘绑定的全局预览条。

        Args:
            owner (PianoRollEditor): 被导航的卷帘控件。
        """

        super().__init__(owner)
        self._owner = owner
        self._dragging = False
        self._drag_offset = QPointF()
        self._last_frame = QRectF()
        self._horizontal_animation = QPropertyAnimation(
            owner.horizontalScrollBar(),
            b"value",
            self,
        )
        self._vertical_animation = QPropertyAnimation(
            owner.verticalScrollBar(),
            b"value",
            self,
        )
        for animation in (self._horizontal_animation, self._vertical_animation):
            animation.setDuration(180)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("上下左右拖动定位框，可快速查看整首曲谱和不同音阶")
        owner.horizontalScrollBar().valueChanged.connect(self.update)
        owner.verticalScrollBar().valueChanged.connect(self.update)

    def _content_rect(self) -> QRectF:
        """
        返回缩略音符和定位框使用的内部区域。

        Returns:
            QRectF: 去除标题与边距后的绘制区域。
        """

        return QRectF(self.rect()).adjusted(12.0, 20.0, -12.0, -8.0)

    def _frame_rect(self) -> QRectF:
        """
        计算当前卷帘可视范围在缩略图中的定位框。

        Returns:
            QRectF: 当前定位框矩形。
        """

        document = self._owner.score_document()
        content = self._content_rect()
        if document is None or document.total_beats <= 0 or content.width() <= 0:
            return QRectF(content.left(), content.top(), content.width(), content.height())
        visible = self._owner.mapToScene(self._owner.viewport().rect()).boundingRect()
        start_beat = max(
            0.0,
            (visible.left() - self._owner._keyboard_width)
            / self._owner._pixels_per_beat,
        )
        end_beat = max(
            start_beat,
            (visible.right() - self._owner._keyboard_width)
            / self._owner._pixels_per_beat,
        )
        total = max(float(document.total_beats), end_beat, 1.0)
        left = content.left() + min(1.0, start_beat / total) * content.width()
        right = content.left() + min(1.0, end_beat / total) * content.width()
        width = min(content.width(), max(14.0, right - left))
        left = min(content.right() - width, left)
        pitch_area_top = self._owner._ruler_height
        pitch_area_height = 60.0 * self._owner._row_height
        visible_top = max(0.0, visible.top() - pitch_area_top)
        visible_bottom = max(visible_top, visible.bottom() - pitch_area_top)
        top_ratio = min(1.0, visible_top / pitch_area_height)
        bottom_ratio = min(1.0, visible_bottom / pitch_area_height)
        top = content.top() + top_ratio * content.height()
        bottom = content.top() + bottom_ratio * content.height()
        height = min(content.height(), max(10.0, bottom - top))
        top = min(content.bottom() - height, top)
        return QRectF(left, top, width, height)

    def _target_scroll_values(
        self,
        overview_position: QPointF,
        offset: QPointF | None = None,
    ) -> tuple[int, int]:
        """
        将缩略图坐标换算为水平及垂直滚动条目标值。

        Args:
            overview_position (QPointF): 鼠标在缩略图中的坐标。
            offset (QPointF | None): 拖动点相对定位框中心的偏移。

        Returns:
            tuple[int, int]: 限制在滚动条范围内的水平和垂直目标值。
        """

        document = self._owner.score_document()
        content = self._content_rect()
        if document is None or content.width() <= 0 or content.height() <= 0:
            return 0, 0
        drag_offset = offset or QPointF()
        center_x = min(
            content.right(),
            max(content.left(), overview_position.x() - drag_offset.x()),
        )
        center_y = min(
            content.bottom(),
            max(content.top(), overview_position.y() - drag_offset.y()),
        )
        horizontal_ratio = (center_x - content.left()) / content.width()
        vertical_ratio = (center_y - content.top()) / content.height()
        scene_x = (
            self._owner._keyboard_width
            + horizontal_ratio
            * float(document.total_beats)
            * self._owner._pixels_per_beat
        )
        scene_y = (
            self._owner._ruler_height
            + vertical_ratio * 60.0 * self._owner._row_height
        )
        visible = self._owner.mapToScene(
            self._owner.viewport().rect()
        ).boundingRect()
        horizontal_target = round(scene_x - visible.width() / 2.0)
        vertical_target = round(scene_y - visible.height() / 2.0)
        horizontal_bar = self._owner.horizontalScrollBar()
        vertical_bar = self._owner.verticalScrollBar()
        return (
            max(
                horizontal_bar.minimum(),
                min(horizontal_bar.maximum(), horizontal_target),
            ),
            max(
                vertical_bar.minimum(),
                min(vertical_bar.maximum(), vertical_target),
            ),
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        绘制全曲音符缩略图和当前可视范围框。

        Args:
            event (QPaintEvent): Qt 绘制事件。
        """

        del event
        application = QApplication.instance()
        dark = application is not None and application.property("theme") == "esports"
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        panel = QRectF(self.rect()).adjusted(4.0, 4.0, -4.0, -4.0)
        painter.setPen(QPen(QColor("#274A76" if dark else "#C7D9EB"), 1.0))
        painter.setBrush(QColor("#0A1730" if dark else "#F2F7FC"))
        painter.drawRoundedRect(panel, 10.0, 10.0)
        painter.setPen(QColor("#92B6DB" if dark else "#58708C"))
        painter.drawText(
            QRectF(panel.left() + 10.0, panel.top(), 100.0, 18.0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "全局预览",
        )
        document = self._owner.score_document()
        content = self._content_rect()
        if document is not None and document.groups and document.total_beats > 0:
            total = float(document.total_beats)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#FF9F43" if dark else "#F08A3C"))
            for group in document.groups:
                x = content.left() + float(group.start_beat) / total * content.width()
                width = max(
                    2.0,
                    float(group.duration_beats) / total * content.width(),
                )
                for pitch in group.pitches:
                    row = _MAX_PITCH_INDEX - pitch_index(pitch)
                    y = content.top() + (row + 0.5) / 60.0 * content.height()
                    painter.drawRoundedRect(QRectF(x, y - 1.4, width, 2.8), 1.4, 1.4)
        self._last_frame = self._frame_rect()
        painter.setPen(QPen(QColor("#18A0FB" if dark else "#1677D2"), 1.8))
        frame_fill = QColor("#18A0FB" if dark else "#1677D2")
        frame_fill.setAlpha(38)
        painter.setBrush(frame_fill)
        painter.drawRoundedRect(self._last_frame, 5.0, 5.0)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        开始拖动定位框，或平滑跳转到点击位置。

        Args:
            event (QMouseEvent): 鼠标按下事件。
        """

        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._horizontal_animation.stop()
        self._vertical_animation.stop()
        if self._last_frame.contains(event.position()):
            self._dragging = True
            self._drag_offset = event.position() - self._last_frame.center()
        else:
            horizontal, vertical = self._target_scroll_values(event.position())
            self._horizontal_animation.setStartValue(
                self._owner.horizontalScrollBar().value()
            )
            self._horizontal_animation.setEndValue(horizontal)
            self._vertical_animation.setStartValue(
                self._owner.verticalScrollBar().value()
            )
            self._vertical_animation.setEndValue(vertical)
            self._horizontal_animation.start()
            self._vertical_animation.start()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        拖动定位框时同步卷帘位置。

        Args:
            event (QMouseEvent): 鼠标移动事件。
        """

        if self._dragging:
            horizontal, vertical = self._target_scroll_values(
                event.position(),
                self._drag_offset,
            )
            self._owner.horizontalScrollBar().setValue(horizontal)
            self._owner.verticalScrollBar().setValue(vertical)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        结束定位框拖动。

        Args:
            event (QMouseEvent): 鼠标释放事件。
        """

        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _NoteItem(QGraphicsRectItem):
    """保存文档定位信息并自绘状态的音符块。"""

    def __init__(
        self,
        rect: QRectF,
        group_index: int,
        pitch: RollPitch,
        label: str,
        editable: bool,
    ) -> None:
        """
        创建音符图形项。

        Args:
            rect (QRectF): 音符在场景中的矩形。
            group_index (int): 文档音符组索引。
            pitch (RollPitch): 该图形项对应的语义音高。
            label (str): 音符块内显示文本。
            editable (bool): 是否允许选择和删除。
        """

        super().__init__(rect)
        self.group_index = group_index
        self.pitch = pitch
        self.label = label
        self.display_label = f"{'#' if pitch.is_semitone else ''}{pitch.degree}"
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, editable)
        self.setToolTip(label)
        self.setZValue(5)

    def boundingRect(self) -> QRectF:
        """
        为抗锯齿圆角和选中描边预留完整重绘范围。

        Returns:
            QRectF: 比音符主体略大的重绘边界。
        """

        return super().boundingRect().adjusted(-2.0, -2.0, 2.0, 2.0)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """
        绘制圆角音符块、选中边框和音符标签。

        Args:
            painter (QPainter): 场景绘制器。
            option (QStyleOptionGraphicsItem): 当前图形项状态。
            widget (QWidget | None): 可选目标控件。
        """

        del option, widget
        application = QApplication.instance()
        dark = application is not None and application.property("theme") == "esports"
        selected = self.isSelected()
        fill = QColor("#00BDEB" if dark else "#1687EF")
        if selected:
            fill = QColor("#FF9F1C" if dark else "#F28C18")
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        border = QColor("#FFF1C2") if selected else QColor(
            "#A8F6FF" if dark else "#FFFFFF"
        )
        painter.setPen(QPen(border, 1.5 if selected else 1.2))
        painter.setBrush(fill)
        painter.drawRoundedRect(self.rect(), 5, 5)
        font = painter.font()
        available_width = max(5, int(self.rect().width() - 3))
        for pixel_size in range(10, 4, -1):
            font.setPixelSize(pixel_size)
            if QFontMetrics(font).horizontalAdvance(self.display_label) <= available_width:
                break
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(
            self.rect().adjusted(1, 0, -1, 0),
            Qt.AlignmentFlag.AlignCenter,
            self.display_label,
        )


class _DocumentCommand(QUndoCommand):
    """使用前后文档快照实现卷帘撤销与重做。"""

    def __init__(
        self,
        editor: PianoRollEditor,
        before: ScoreDocument,
        after: ScoreDocument,
        text: str,
    ) -> None:
        """
        创建一次文档变更命令。

        Args:
            editor (PianoRollEditor): 接收快照的卷帘编辑器。
            before (ScoreDocument): 操作前文档。
            after (ScoreDocument): 操作后文档。
            text (str): 撤销栈中显示的操作名称。
        """

        super().__init__(text)
        self._editor = editor
        self._before = before
        self._after = after

    def undo(self) -> None:
        """恢复操作前文档。"""

        self._editor._apply_document(self._before)

    def redo(self) -> None:
        """应用操作后文档。"""

        self._editor._apply_document(self._after)


class PianoRollEditor(QGraphicsView):
    """显示并按当前顺序曲谱约束编辑音符时间轴。"""

    document_changed = Signal(object)
    edit_error = Signal(str)
    selection_changed = Signal(int)

    def __init__(self, editable: bool = False, parent: QWidget | None = None) -> None:
        """
        初始化钢琴卷帘。

        Args:
            editable (bool): 是否启用添加、选择和删除。
            parent (QWidget | None): 父级控件。
        """

        super().__init__(parent)
        self.setObjectName("pianoRoll")
        self._editable = editable
        self._document: ScoreDocument | None = None
        self._grid = Fraction(1, 4)
        self._default_duration = Fraction(1)
        self._follow_playhead = not editable
        self._pixels_per_beat = 68.0
        self._row_height = 22.0
        self._keyboard_width = 64.0
        self._ruler_height = 28.0
        self._playhead_beat = Fraction(0)
        self._playhead_item: QGraphicsLineItem | None = None
        self._undo_stack = QUndoStack(self)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate
            if editable
            else QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate
        )
        self._overview_height = 92
        self.setViewportMargins(0, self._overview_height, 0, 0)
        self._overview = _OverviewBar(self)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
        )
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setDragMode(
            QGraphicsView.DragMode.RubberBandDrag
            if editable
            else QGraphicsView.DragMode.ScrollHandDrag
        )
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._scene.selectionChanged.connect(self._emit_selection_count)
        self._rebuild_scene()
        self._layout_overview()

    @property
    def editable(self) -> bool:
        """
        返回控件是否允许编辑。

        Returns:
            bool: 编辑功能启用时为 `True`。
        """

        return self._editable

    @property
    def undo_stack(self) -> QUndoStack:
        """
        返回卷帘专用撤销栈。

        Returns:
            QUndoStack: 当前控件的撤销与重做栈。
        """

        return self._undo_stack

    def score_document(self) -> ScoreDocument | None:
        """
        返回当前文档。

        Returns:
            ScoreDocument | None: 当前文档或空值。
        """

        return self._document

    def set_score_document(
        self,
        document: ScoreDocument | None,
        reset_history: bool = True,
    ) -> None:
        """
        替换当前文档并重建场景。

        Args:
            document (ScoreDocument | None): 新文档，空值表示清空。
            reset_history (bool): 是否清空撤销历史。
        """

        self._document = document
        if reset_history:
            self._undo_stack.clear()
        self._rebuild_scene()
        self._overview.update()
        self._center_middle_octave()
        QTimer.singleShot(0, self._center_middle_octave)

    def set_grid(self, grid: Fraction) -> None:
        """
        设置双击添加音符时使用的量化网格。

        Args:
            grid (Fraction): 正拍数网格。

        Raises:
            ValueError: 网格不大于零时抛出。
        """

        if grid <= 0:
            raise ValueError("量化网格必须大于 0")
        self._grid = grid
        self._rebuild_scene()

    def set_default_duration(self, duration: Fraction) -> None:
        """
        设置新建音符的默认时值。

        Args:
            duration (Fraction): 正拍数时值。

        Raises:
            ValueError: 时值不大于零时抛出。
        """

        if duration <= 0:
            raise ValueError("默认时值必须大于 0")
        self._default_duration = duration

    def set_playhead_beat(self, beat: Fraction | float) -> None:
        """
        移动播放指针。

        Args:
            beat (Fraction | float): 从曲谱起点计算的拍数。
        """

        self._playhead_beat = max(Fraction(0), Fraction(str(beat)))
        if self._playhead_item is None:
            return
        x = self._keyboard_width + float(self._playhead_beat) * self._pixels_per_beat
        self._playhead_item.setLine(
            x,
            self._ruler_height,
            x,
            self._ruler_height + 60 * self._row_height,
        )
        if self._follow_playhead and self.isVisible():
            scroll_bar = self.horizontalScrollBar()
            visible_width = max(1.0, self.viewport().width() - self._keyboard_width)
            target = max(
                0.0,
                min(
                    float(scroll_bar.maximum()),
                    x - self._keyboard_width - visible_width * 0.34,
                ),
            )
            current = float(scroll_bar.value())
            distance = target - current
            easing = 0.55 if abs(distance) > visible_width else 0.34
            next_value = target if abs(distance) < 1.0 else current + distance * easing
            scroll_bar.setValue(round(next_value))

    def _center_middle_octave(self) -> None:
        """将初始垂直视野定位到中音音区并回到曲谱开头。"""

        middle_index = 29.5
        center_y = (
            self._ruler_height
            + (_MAX_PITCH_INDEX - middle_index + 0.5) * self._row_height
        )
        self.verticalScrollBar().setValue(
            max(0, int(center_y - self.viewport().height() / 2))
        )
        self.horizontalScrollBar().setValue(0)

    def zoom_in(self) -> None:
        """放大横向拍位比例。"""

        self._set_horizontal_zoom(self._pixels_per_beat * 1.2)

    def zoom_out(self) -> None:
        """缩小横向拍位比例。"""

        self._set_horizontal_zoom(self._pixels_per_beat / 1.2)

    def delete_selected_notes(self) -> None:
        """删除当前选择的全部音符并合并为一次撤销操作。"""

        if not self._editable or self._document is None:
            return
        selected = [item for item in self._scene.selectedItems() if isinstance(item, _NoteItem)]
        if not selected:
            return
        before = self._document
        after = before
        ordered = sorted(selected, key=lambda item: item.group_index, reverse=True)
        for item in ordered:
            group_index = next(
                (
                    index
                    for index, group in enumerate(after.groups)
                    if group.start_beat == before.groups[item.group_index].start_beat
                    and item.pitch in group.pitches
                ),
                -1,
            )
            if group_index >= 0:
                after = remove_note(after, group_index, item.pitch)
        if after != before:
            self._undo_stack.push(_DocumentCommand(self, before, after, "删除音符"))

    def _set_horizontal_zoom(self, pixels_per_beat: float) -> None:
        """
        更新横向缩放并保持当前中心拍位。

        Args:
            pixels_per_beat (float): 每拍对应像素数。
        """

        center = self.mapToScene(self.viewport().rect().center())
        old = self._pixels_per_beat
        center_beat = max(0.0, (center.x() - self._keyboard_width) / old)
        self._pixels_per_beat = min(220.0, max(28.0, pixels_per_beat))
        self._rebuild_scene()
        self.centerOn(
            self._keyboard_width + center_beat * self._pixels_per_beat,
            center.y(),
        )

    def _apply_document(self, document: ScoreDocument) -> None:
        """
        应用撤销命令提供的文档快照。

        Args:
            document (ScoreDocument): 新文档快照。
        """

        self._document = document
        self._rebuild_scene()
        self.document_changed.emit(document)

    def _push_change(self, after: ScoreDocument, text: str) -> None:
        """
        将文档变更加入撤销栈。

        Args:
            after (ScoreDocument): 操作后的文档。
            text (str): 操作名称。
        """

        if self._document is None or after == self._document:
            return
        self._undo_stack.push(_DocumentCommand(self, self._document, after, text))

    def _snap(self, value: float) -> Fraction:
        """
        将非负拍位吸附到当前网格。

        Args:
            value (float): 原始拍位。

        Returns:
            Fraction: 量化后的拍位。
        """

        raw = Fraction(str(max(0.0, value)))
        ratio = raw / self._grid
        step = ratio.numerator // ratio.denominator
        return step * self._grid

    def _scene_pitch(self, y: float) -> RollPitch:
        """
        将场景纵坐标换算为规范音高。

        Args:
            y (float): 场景纵坐标。

        Returns:
            RollPitch: 五音区范围内的音高。
        """

        row = round((y - self._ruler_height) / self._row_height)
        index = max(0, min(_MAX_PITCH_INDEX, _MAX_PITCH_INDEX - row))
        return pitch_from_index(index)

    def _note_rect(self, group_index: int, pitch: RollPitch) -> QRectF:
        """
        计算一个音符块的场景矩形。

        Args:
            group_index (int): 音符组索引。
            pitch (RollPitch): 音符音高。

        Returns:
            QRectF: 留有网格间隙的圆角块区域。
        """

        assert self._document is not None
        group = self._document.groups[group_index]
        x = self._keyboard_width + float(group.start_beat) * self._pixels_per_beat
        y = self._ruler_height + (_MAX_PITCH_INDEX - pitch_index(pitch)) * self._row_height
        width = max(8.0, float(group.duration_beats) * self._pixels_per_beat - 2.0)
        return QRectF(x + 1.0, y + 2.0, width, self._row_height - 4.0)

    def _rebuild_scene(self) -> None:
        """重建可交互音符项，背景网格由视图按需直接绘制。"""

        self._scene.clear()
        application = QApplication.instance()
        dark = application is not None and application.property("theme") == "esports"
        max_beat = max(
            16.0,
            float(self._document.total_beats) if self._document is not None else 16.0,
        )
        scene_width = self._keyboard_width + max_beat * self._pixels_per_beat + 80.0
        scene_height = self._ruler_height + 60 * self._row_height
        self._scene.setSceneRect(0, 0, scene_width, scene_height)
        if self._document is not None:
            for group_index, group in enumerate(self._document.groups):
                for pitch in group.pitches:
                    item = _NoteItem(
                        self._note_rect(group_index, pitch),
                        group_index,
                        pitch,
                        pitch_text(pitch),
                        self._editable,
                    )
                    self._scene.addItem(item)

        self._playhead_item = self._scene.addLine(
            0,
            self._ruler_height,
            0,
            scene_height,
            QPen(QColor("#FF3B82" if dark else "#E33B55"), 2.6),
        )
        self._playhead_item.setZValue(10)
        self.set_playhead_beat(self._playhead_beat)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """
        只绘制当前可见区域内的音高行和量化网格。

        Args:
            painter (QPainter): 背景绘制器。
            rect (QRectF): 当前可见场景区域。
        """

        application = QApplication.instance()
        dark = application is not None and application.property("theme") == "esports"
        background = QColor("#081328" if dark else "#F8FBFF")
        natural = QColor("#0D1A32" if dark else "#FFFFFF")
        sharp = QColor("#09162B" if dark else "#E8F0F8")
        grid_color = QColor("#1D365F" if dark else "#DCE7F1")
        strong_grid = QColor("#315A8E" if dark else "#B8CEE2")
        painter.fillRect(rect, background)

        first_row = max(
            0,
            floor((rect.top() - self._ruler_height) / self._row_height),
        )
        last_row = min(
            59,
            ceil((rect.bottom() - self._ruler_height) / self._row_height),
        )
        for row in range(first_row, last_row + 1):
            index = _MAX_PITCH_INDEX - row
            y = self._ruler_height + row * self._row_height
            pitch = pitch_from_index(index)
            painter.fillRect(
                QRectF(rect.left(), y, rect.width(), self._row_height),
                sharp if pitch.is_semitone else natural,
            )
            painter.setPen(QPen(grid_color, 0.7))
            painter.drawLine(
                QPointF(rect.left(), y + self._row_height),
                QPointF(rect.right(), y + self._row_height),
            )

        first_step = max(
            0,
            floor(
                (rect.left() - self._keyboard_width)
                / (self._pixels_per_beat * float(self._grid))
            ),
        )
        last_step = ceil(
            (rect.right() - self._keyboard_width)
            / (self._pixels_per_beat * float(self._grid))
        )
        for step in range(first_step, last_step + 1):
            beat = float(self._grid) * step
            x = self._keyboard_width + beat * self._pixels_per_beat
            whole_beat = abs(beat - round(beat)) < 1e-8
            painter.setPen(
                QPen(
                    strong_grid if whole_beat else grid_color,
                    1.0 if whole_beat else 0.55,
                )
            )
            painter.drawLine(
                QPointF(x, rect.top()),
                QPointF(x, rect.bottom()),
            )

    def _emit_selection_count(self) -> None:
        """发送当前已选音符数量。"""

        count = sum(isinstance(item, _NoteItem) for item in self._scene.selectedItems())
        self.selection_changed.emit(count)
        self.viewport().update()

    def _layout_overview(self) -> None:
        """让全局预览条始终铺满卷帘顶部预留区域。"""

        viewport_geometry = self.viewport().geometry()
        self._overview.setGeometry(
            viewport_geometry.left(),
            0,
            viewport_geometry.width(),
            self._overview_height,
        )

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """
        在滚动内容上方绘制始终可见的拍位标尺。

        Args:
            painter (QPainter): 前景绘制器。
            rect (QRectF): 当前可见场景区域。
        """

        super().drawForeground(painter, rect)
        application = QApplication.instance()
        dark = application is not None and application.property("theme") == "esports"
        background = QColor("#0B1830" if dark else "#F3F8FD")
        border = QColor("#315A8E" if dark else "#B8CEE2")
        text_color = QColor("#A7C8EA" if dark else "#536A86")
        key_natural = QColor("#10203A" if dark else "#F8FBFF")
        key_sharp = QColor("#091326" if dark else "#DCE8F3")
        keyboard_left = rect.left()
        first_row = max(
            0,
            floor((rect.top() - self._ruler_height) / self._row_height),
        )
        last_row = min(
            59,
            ceil((rect.bottom() - self._ruler_height) / self._row_height),
        )
        for row in range(first_row, last_row + 1):
            index = _MAX_PITCH_INDEX - row
            pitch = pitch_from_index(index)
            y = self._ruler_height + row * self._row_height
            key_rect = QRectF(
                keyboard_left,
                y,
                self._keyboard_width,
                self._row_height,
            )
            painter.fillRect(key_rect, key_sharp if pitch.is_semitone else key_natural)
            painter.setPen(QPen(border, 0.7))
            painter.drawLine(key_rect.bottomLeft(), key_rect.bottomRight())
            painter.setPen(text_color)
            painter.drawText(
                key_rect.adjusted(9, 0, -4, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                pitch_text(pitch),
            )
        ruler = QRectF(rect.left(), rect.top(), rect.width(), self._ruler_height)
        painter.fillRect(ruler, background)
        painter.setPen(QPen(border, 1.0))
        painter.drawLine(ruler.bottomLeft(), ruler.bottomRight())
        first_beat = max(
            0,
            floor((rect.left() - self._keyboard_width) / self._pixels_per_beat),
        )
        last_beat = ceil((rect.right() - self._keyboard_width) / self._pixels_per_beat)
        painter.setPen(text_color)
        for beat in range(first_beat, last_beat + 1):
            x = self._keyboard_width + beat * self._pixels_per_beat
            painter.drawLine(QPointF(x, ruler.bottom() - 5), QPointF(x, ruler.bottom()))
            painter.drawText(
                QRectF(x + 4, ruler.top(), 42, ruler.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                str(beat + 1),
            )
        corner = QRectF(
            keyboard_left,
            rect.top(),
            self._keyboard_width,
            self._ruler_height,
        )
        painter.fillRect(corner, background)
        painter.setPen(QPen(border, 1.0))
        painter.drawLine(corner.bottomLeft(), corner.bottomRight())
        painter.drawLine(corner.topRight(), corner.bottomRight())

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """
        双击空白网格时添加默认时值音符。

        Args:
            event (QMouseEvent): 鼠标双击事件。
        """

        if not self._editable or self._document is None:
            super().mouseDoubleClickEvent(event)
            return
        scene_position = self.mapToScene(event.position().toPoint())
        item = self._scene.itemAt(scene_position, self.transform())
        if isinstance(item, _NoteItem) or event.position().x() < self._keyboard_width:
            super().mouseDoubleClickEvent(event)
            return
        start = self._snap(
            (scene_position.x() - self._keyboard_width) / self._pixels_per_beat
        )
        try:
            after = add_note(
                self._document,
                start,
                self._default_duration,
                self._scene_pitch(scene_position.y()),
            )
        except ValueError as exc:
            self.edit_error.emit(str(exc))
            return
        self._push_change(after, "添加音符")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        处理删除、撤销和重做快捷键。

        Args:
            event (QKeyEvent): 键盘事件。
        """

        if self._editable and event.key() in {
            Qt.Key.Key_Delete,
            Qt.Key.Key_Backspace,
        }:
            self.delete_selected_notes()
            event.accept()
            return
        if self._editable and event.matches(QKeySequence.StandardKey.Undo):
            self._undo_stack.undo()
            event.accept()
            return
        if self._editable and event.matches(QKeySequence.StandardKey.Redo):
            self._undo_stack.redo()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """
        Ctrl+滚轮调整横向缩放，普通滚轮保持滚动行为。

        Args:
            event (QWheelEvent): 滚轮事件。
        """

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        调整卷帘尺寸时同步全局预览条宽度。

        Args:
            event (QResizeEvent): Qt 尺寸变化事件。
        """

        super().resizeEvent(event)
        if hasattr(self, "_overview"):
            self._layout_overview()
            self._overview.update()

    def changeEvent(self, event: QEvent) -> None:
        """
        主题或样式切换后使用新配色重建场景。

        Args:
            event (QEvent): Qt 状态变化事件。
        """

        super().changeEvent(event)
        if hasattr(self, "_scene") and event.type() in {
            QEvent.Type.PaletteChange,
            QEvent.Type.StyleChange,
        }:
            application = QApplication.instance()
            dark = application is not None and application.property("theme") == "esports"
            if self._playhead_item is not None:
                self._playhead_item.setPen(
                    QPen(QColor("#FF3B82" if dark else "#E33B55"), 2.6)
                )
            if hasattr(self, "_overview"):
                self._overview.update()
            self.viewport().update()
