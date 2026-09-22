"""钢琴卷帘控件和双视图编辑器测试。"""

from __future__ import annotations

import os
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsView

from keyscore.editor_window import ScoreEditorWindow
from keyscore.piano_roll import PianoRollEditor
from keyscore.score_document import RollPitch, add_note, document_from_text, pitch_index
from keyscore.models import Octave


class PianoRollTests(unittest.TestCase):
    """验证卷帘加载、编辑同步和文本错误回退。"""

    application: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        """为 Qt 控件测试创建共享应用。"""

        cls.application = QApplication.instance() or QApplication([])

    def test_preview_accepts_document_and_moves_playhead(self) -> None:
        """只读卷帘应能显示文档并更新播放指针。"""

        view = PianoRollEditor(editable=False)
        document = document_from_text("@title 预览\n1 2 3")
        view.set_score_document(document)
        view.set_playhead_beat(1.5)

        self.assertIs(view.score_document(), document)
        self.assertFalse(view.editable)

    def test_grid_does_not_create_scene_items_and_notes_are_not_movable(self) -> None:
        """细网格应直接绘制，场景中只保留不可拖动的音符和播放指针。"""

        view = PianoRollEditor(editable=True)
        document = document_from_text(" ".join("#1:0.25" for _index in range(64)))
        view.set_grid(Fraction(1, 16))
        view.set_score_document(document)

        self.assertEqual(len(view.scene().items()), len(document.groups) + 1)
        for item in view.scene().items():
            self.assertFalse(
                bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
            )
            self.assertFalse(item.acceptHoverEvents())

    def test_every_note_uses_a_compact_visible_label(self) -> None:
        """所有时值的音符都应使用一致的简短音高标签。"""

        view = PianoRollEditor(editable=True)
        document = document_from_text("1:0.25 #2:0.25 H3:2")
        view.set_score_document(document)
        note_items = [item for item in view.scene().items() if item.toolTip()]

        self.assertEqual(
            {item.display_label for item in note_items},
            {"1", "#2", "3"},
        )

    def test_edit_view_forces_complete_repaint_after_selection(self) -> None:
        """编辑器选择音符时应完整重绘，避免圆角块只剩文字或局部残影。"""

        view = PianoRollEditor(editable=True)
        preview = PianoRollEditor(editable=False)

        self.assertEqual(
            view.viewportUpdateMode(),
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate,
        )
        self.assertEqual(view.viewport().cursor().shape(), Qt.CursorShape.CrossCursor)
        self.assertGreater(view._pixels_per_beat, preview._pixels_per_beat)
        self.assertGreater(view._row_height, preview._row_height)

    def test_overview_frame_tracks_horizontal_and_vertical_scroll(self) -> None:
        """全局预览中的定位框应随卷帘时间和音阶位置移动。"""

        view = PianoRollEditor(editable=False)
        view.resize(500, 360)
        view.set_score_document(document_from_text(" ".join("1" for _index in range(64))))
        view.show()
        self.application.processEvents()
        start_frame = view._overview._frame_rect()

        view.horizontalScrollBar().setValue(view.horizontalScrollBar().maximum())
        view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
        self.application.processEvents()
        end_frame = view._overview._frame_rect()

        self.assertGreater(end_frame.left(), start_frame.left())
        self.assertGreater(end_frame.top(), start_frame.top())
        self.assertLess(end_frame.height(), view._overview._content_rect().height())
        self.assertGreaterEqual(view._overview.height(), 80)
        view.close()

    def test_click_quantization_uses_the_clicked_grid_cell(self) -> None:
        """点击网格右半部分时仍应落在当前格而不是跳到下一格。"""

        view = PianoRollEditor(editable=True)
        view.set_grid(Fraction(1, 4))

        self.assertEqual(view._snap(0.24), Fraction(0))
        self.assertEqual(view._snap(0.26), Fraction(1, 4))
        self.assertEqual(view._snap(0.49), Fraction(1, 4))

    def test_draw_mode_drag_creates_grid_snapped_note_and_can_undo(self) -> None:
        """绘制模式横向拖动应生成吸附网格的音符并支持一次撤销。"""

        view = PianoRollEditor(editable=True)
        view.resize(720, 460)
        view.set_grid(Fraction(1, 4))
        view.set_score_document(document_from_text("@title 拖拽绘制\n1"))
        view.set_draw_mode(True)
        view.show()
        self.application.processEvents()
        pitch = RollPitch(Octave.MIDDLE, 4)
        row = 59 - pitch_index(pitch)
        start = view.mapFromScene(
            QPointF(
                view._keyboard_width + 4 * view._pixels_per_beat,
                view._ruler_height + (row + 0.5) * view._row_height,
            )
        )
        end = view.mapFromScene(
            QPointF(
                view._keyboard_width + 5.5 * view._pixels_per_beat,
                view._ruler_height + (row + 0.5) * view._row_height,
            )
        )

        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), end)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.application.processEvents()

        document = view.score_document()
        assert document is not None
        drawn = next(group for group in document.groups if group.start_beat == 4)
        self.assertEqual(drawn.duration_beats, Fraction(3, 2))
        self.assertIn(pitch, drawn.pitches)

        view.undo_stack.undo()
        self.assertFalse(
            any(group.start_beat == 4 for group in view.score_document().groups)
        )
        view.close()

    def test_select_mode_keeps_marquee_and_alt_temporarily_draws(self) -> None:
        """选择模式普通拖动不得加音符，按住 Alt 时应临时切换为绘制。"""

        view = PianoRollEditor(editable=True)
        view.resize(720, 460)
        view.set_grid(Fraction(1, 4))
        view.set_score_document(document_from_text("@title 模式分流\n1"))
        view.show()
        self.application.processEvents()
        pitch = RollPitch(Octave.MIDDLE, 5)
        row = 59 - pitch_index(pitch)
        start = view.mapFromScene(
            QPointF(
                view._keyboard_width + 4 * view._pixels_per_beat,
                view._ruler_height + (row + 0.5) * view._row_height,
            )
        )
        end = view.mapFromScene(
            QPointF(
                view._keyboard_width + 5 * view._pixels_per_beat,
                view._ruler_height + (row + 0.5) * view._row_height,
            )
        )
        original_count = len(view.score_document().groups)

        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), end)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertEqual(len(view.score_document().groups), original_count)

        QTest.mousePress(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.AltModifier,
            start,
        )
        QTest.mouseMove(view.viewport(), end)
        QTest.mouseRelease(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.AltModifier,
            end,
        )
        self.application.processEvents()

        self.assertTrue(
            any(group.start_beat == 4 for group in view.score_document().groups)
        )
        view.close()

    def test_draw_mode_alt_temporarily_restores_marquee(self) -> None:
        """绘制模式按住 Alt 拖动时应保留框选行为而不创建音符。"""

        view = PianoRollEditor(editable=True)
        view.resize(720, 460)
        view.set_score_document(document_from_text("@title 临时框选\n1"))
        view.set_draw_mode(True)
        view.show()
        self.application.processEvents()
        note_item = next(item for item in view.scene().items() if item.toolTip())
        note_rect = note_item.sceneBoundingRect()
        start = view.mapFromScene(
            QPointF(note_rect.left() + 1.0, note_rect.top() - 6.0)
        )
        end = view.mapFromScene(
            QPointF(note_rect.right() + 6.0, note_rect.bottom() + 6.0)
        )
        original = view.score_document()

        QTest.mousePress(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.AltModifier,
            start,
        )
        QTest.mouseMove(view.viewport(), end)
        QTest.mouseRelease(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.AltModifier,
            end,
        )

        self.assertEqual(view.score_document(), original)
        self.assertTrue(note_item.isSelected())
        view.close()

    def test_filled_editing_canvas_appends_three_cells_and_scrolls_right(self) -> None:
        """占满尾格后应追加三个当前网格，并自动移动到新尾部。"""

        view = PianoRollEditor(editable=True)
        view.resize(420, 280)
        view.set_grid(Fraction(1, 4))
        view.set_score_document(document_from_text(" ".join("1" for _ in range(16))))
        view.show()
        self.application.processEvents()

        view._extend_editing_canvas_if_needed(Fraction(16))
        self.application.processEvents()

        self.assertEqual(view._editing_extent_beats, Fraction(67, 4))
        self.assertEqual(
            view.horizontalScrollBar().value(),
            view.horizontalScrollBar().maximum(),
        )
        view.close()

    def test_pitch_hit_testing_uses_the_full_visual_row(self) -> None:
        """同一音高行的上半部和下半部都必须命中同一个音符。"""

        view = PianoRollEditor(editable=True)
        row = 20
        row_top = view._ruler_height + row * view._row_height

        upper_pitch = view._scene_pitch(row_top + 1.0)
        lower_pitch = view._scene_pitch(row_top + view._row_height - 1.0)
        next_pitch = view._scene_pitch(row_top + view._row_height + 1.0)

        self.assertEqual(upper_pitch, lower_pitch)
        self.assertNotEqual(lower_pitch, next_pitch)

    def test_hovered_grid_row_tracks_the_pitch_label_to_highlight(self) -> None:
        """十字光标移动到音高行时应记录对应的左侧音节标签。"""

        view = PianoRollEditor(editable=True)
        view.resize(520, 360)
        view.set_score_document(document_from_text("1 2 3 4"))
        view.show()
        self.application.processEvents()
        expected = RollPitch(Octave.MIDDLE, 4)
        row = 59 - pitch_index(expected)
        scene_position = QPointF(
            view._keyboard_width + view._pixels_per_beat,
            view._ruler_height + (row + 0.5) * view._row_height,
        )

        QTest.mouseMove(view.viewport(), view.mapFromScene(scene_position))
        self.application.processEvents()

        self.assertEqual(view._hover_pitch, expected)
        view.close()

    def test_preview_follows_playhead_and_defaults_to_middle_octave(self) -> None:
        """长曲谱播放时应横向跟随，初始垂直位置应位于中音区。"""

        view = PianoRollEditor(editable=False)
        view.resize(420, 280)
        view.set_score_document(document_from_text(" ".join("1" for _index in range(48))))
        view.show()
        self.application.processEvents()

        self.assertGreater(view.verticalScrollBar().value(), 0)
        view.set_playhead_beat(36)
        self.application.processEvents()
        self.assertGreater(view.horizontalScrollBar().value(), 0)
        view.close()

    def test_paused_playhead_update_does_not_override_manual_scroll(self) -> None:
        """暂停后的指针刷新不应把用户拖动的横向滚动条拉回播放位置。"""

        view = PianoRollEditor(editable=False)
        view.resize(420, 280)
        view.set_score_document(document_from_text(" ".join("1" for _index in range(48))))
        view.show()
        self.application.processEvents()

        view.horizontalScrollBar().setValue(view.horizontalScrollBar().maximum())
        manual_position = view.horizontalScrollBar().value()
        view.set_playhead_beat(0, follow_view=False)
        self.application.processEvents()

        self.assertEqual(view.horizontalScrollBar().value(), manual_position)
        view.close()

    def test_preview_follows_current_pitch_vertically(self) -> None:
        """播放音高跨越音区时，预览应同步上下滚动到当前音符。"""

        view = PianoRollEditor(editable=False)
        view.resize(420, 280)
        view.set_score_document(document_from_text("1"))
        view.show()
        self.application.processEvents()

        view.follow_playhead_pitch(RollPitch(Octave.HIGHEST, 7))
        QTest.qWait(250)
        high_position = view.verticalScrollBar().value()
        view.follow_playhead_pitch(RollPitch(Octave.LOWEST, 1))
        QTest.qWait(250)
        low_position = view.verticalScrollBar().value()

        self.assertGreater(low_position, high_position)
        view.close()

    def test_roll_change_synchronizes_text_when_opened(self) -> None:
        """卷帘修改应延迟到打开文本页时统一序列化。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.txt"
            path.write_text("@title 同步\n1 2", encoding="utf-8")
            window = ScoreEditorWindow(path)
            try:
                document = window.roll_editor.score_document()
                assert document is not None
                changed = add_note(
                    document,
                    document.total_beats,
                    document.groups[0].duration_beats,
                    document.groups[0].pitches[0],
                )
                window.roll_editor._apply_document(changed)

                self.assertTrue(window.editor.document().isModified())
                self.assertEqual(len(document.groups) + 1, len(changed.groups))
                self.assertTrue(window._roll_dirty)
                window.editor_tabs.setCurrentIndex(1)
                self.assertIn("@title 同步", window.editor.toPlainText())
                self.assertFalse(window._roll_dirty)
            finally:
                window.editor.document().setModified(False)
                window.close()

    def test_invalid_text_cannot_switch_to_roll(self) -> None:
        """文本语法错误时应留在文本页并显示错误。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.txt"
            path.write_text("@title 错误测试\n1 2", encoding="utf-8")
            window = ScoreEditorWindow(path)
            try:
                window.editor_tabs.setCurrentIndex(1)
                window.editor.setPlainText("1 X9")
                window.editor_tabs.setCurrentIndex(0)

                self.assertEqual(window.editor_tabs.currentIndex(), 1)
                self.assertIn("第 1 行", window.validation_label.text())
            finally:
                window.editor.document().setModified(False)
                window.close()

    def test_undo_enables_redo_after_deleting_note(self) -> None:
        """只有执行撤销后重做按钮才应启用并恢复删除操作。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.txt"
            path.write_text("@title 撤销测试\n1 2", encoding="utf-8")
            window = ScoreEditorWindow(path)
            try:
                note_item = next(
                    item for item in window.roll_editor.scene().items() if item.toolTip()
                )
                note_item.setSelected(True)
                window.roll_editor.delete_selected_notes()
                self.application.processEvents()
                self.assertTrue(window.undo_button.isEnabled())
                self.assertFalse(window.redo_button.isEnabled())

                window.undo_button.click()
                self.application.processEvents()
                self.assertTrue(window.redo_button.isEnabled())
                self.assertEqual(len(window.roll_editor.score_document().groups), 2)

                window.redo_button.click()
                self.application.processEvents()
                self.assertEqual(len(window.roll_editor.score_document().groups), 1)
            finally:
                window.editor.document().setModified(False)
                window.close()

    def test_custom_duration_presets_cycle_in_user_order(self) -> None:
        """编辑器应加载用户拍数，并按用户顺序循环切换。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.txt"
            path.write_text("@title 拍数测试\n1", encoding="utf-8")
            window = ScoreEditorWindow(
                path,
                duration_presets=("1/8", "3/4", "3"),
                default_note_duration="3/4",
                duration_cycle_hotkey="D",
            )
            try:
                self.assertEqual(window.duration_combo.currentData(), "3/4")
                window._cycle_note_duration()
                self.assertEqual(window.duration_combo.currentData(), "3")
                window._cycle_note_duration()
                self.assertEqual(window.duration_combo.currentData(), "1/8")
                window._cycle_note_duration_reverse()
                self.assertEqual(window.duration_combo.currentData(), "3")
            finally:
                window.editor.document().setModified(False)
                window.close()

    def test_editor_default_new_note_duration_is_quarter_beat(self) -> None:
        """未传入自定义设置时，新音符应默认使用四分之一拍。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.txt"
            path.write_text("@title 默认拍数\n1", encoding="utf-8")
            window = ScoreEditorWindow(path)
            try:
                self.assertEqual(window.duration_combo.currentData(), "1/4")
                self.assertEqual(window.roll_editor._default_duration, Fraction(1, 4))
            finally:
                window.editor.document().setModified(False)
                window.close()

    def test_editor_mode_buttons_switch_canvas_operation(self) -> None:
        """编辑器的选择和绘制按钮应互斥并同步卷帘光标模式。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.txt"
            path.write_text("@title 模式按钮\n1", encoding="utf-8")
            window = ScoreEditorWindow(path)
            try:
                window.resize(window.minimumSize())
                window.show()
                self.application.processEvents()
                self.assertTrue(window.select_mode_button.isChecked())
                self.assertFalse(window.roll_editor._draw_mode)
                self.assertGreaterEqual(
                    window.select_mode_button.width(),
                    window.select_mode_button.minimumSizeHint().width(),
                )
                self.assertGreaterEqual(
                    window.draw_mode_button.width(),
                    window.draw_mode_button.minimumSizeHint().width(),
                )

                window.draw_mode_button.click()
                self.assertTrue(window.draw_mode_button.isChecked())
                self.assertFalse(window.select_mode_button.isChecked())
                self.assertTrue(window.roll_editor._draw_mode)
                self.assertGreaterEqual(window.draw_mode_button.width(), 116)
                self.assertGreaterEqual(window.draw_mode_button.height(), 40)
                self.assertEqual(
                    window.roll_editor.viewport().cursor().shape(),
                    Qt.CursorShape.SizeHorCursor,
                )

                window.select_mode_button.click()
                self.assertFalse(window.roll_editor._draw_mode)
            finally:
                window.editor.document().setModified(False)
                window.close()

    def test_window_undo_still_works_after_duration_switch(self) -> None:
        """切换新音符拍数后，窗口级 Ctrl+Z 仍应撤销卷帘编辑。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.txt"
            path.write_text("@title 快捷撤销\n1 2", encoding="utf-8")
            window = ScoreEditorWindow(path)
            try:
                note_item = next(
                    item for item in window.roll_editor.scene().items() if item.toolTip()
                )
                note_item.setSelected(True)
                window.roll_editor.delete_selected_notes()
                window._cycle_note_duration()
                window.show()
                window.duration_combo.setFocus()
                self.application.processEvents()
                QTest.keyClick(
                    window.duration_combo,
                    Qt.Key.Key_Z,
                    Qt.KeyboardModifier.ControlModifier,
                )
                self.application.processEvents()

                document = window.roll_editor.score_document()
                assert document is not None
                self.assertEqual(len(document.groups), 2)
            finally:
                window.editor.document().setModified(False)
                window.close()


if __name__ == "__main__":
    unittest.main()
