"""钢琴卷帘控件和双视图编辑器测试。"""

from __future__ import annotations

import os
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsView

from keyscore.editor_window import ScoreEditorWindow
from keyscore.piano_roll import PianoRollEditor
from keyscore.score_document import add_note, document_from_text


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

        self.assertEqual(
            view.viewportUpdateMode(),
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate,
        )

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


if __name__ == "__main__":
    unittest.main()
