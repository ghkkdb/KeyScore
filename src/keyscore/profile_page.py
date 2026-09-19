"""按键配置方案的主窗口页面。"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from fractions import Fraction

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .binding_capture import capture_binding
from .models import (
    Binding,
    GameProfile,
    MappingMode,
    NoteEvent,
    NoteOutputMode,
    Octave,
    note_binding_key,
)


class ProfileMappingPage(QWidget):
    """在主窗口内编辑当前 Profile 的键位和演奏参数。"""

    save_requested = Signal(object, str)
    new_requested = Signal()
    import_requested = Signal()
    dirty_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        创建按键映射页面。

        Args:
            parent (QWidget | None): 父控件。
        """

        super().__init__(parent)
        self._profile: GameProfile | None = None
        self._draft: GameProfile | None = None
        self._dirty = False
        self._build_ui()

    @property
    def has_unsaved_changes(self) -> bool:
        """
        返回页面是否存在未保存修改。

        Returns:
            bool: 存在未保存修改时为 `True`。
        """

        return self._dirty

    def _build_ui(self) -> None:
        """构建方案管理、映射网格和演奏参数区域。"""

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(24, 20, 24, 18)
        page_layout.setSpacing(14)

        heading_row = QHBoxLayout()
        heading_box = QVBoxLayout()
        heading = QLabel("按键映射", objectName="displayTitle")
        description = QLabel("管理当前配置方案的音符键位与演奏参数", objectName="muted")
        heading_box.addWidget(heading)
        heading_box.addWidget(description)
        self.save_button = QPushButton("保存方案", objectName="primary")
        self.save_button.clicked.connect(self._request_save)
        heading_row.addLayout(heading_box)
        heading_row.addStretch()
        heading_row.addWidget(self.save_button)
        page_layout.addLayout(heading_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget(objectName="pageCard")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 18, 20, 18)
        content_layout.setSpacing(14)

        profile_heading = QLabel("配置方案", objectName="sectionLabel")
        content_layout.addWidget(profile_heading)
        profile_row = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入配置方案名称")
        self.name_edit.textChanged.connect(lambda _text: self._mark_dirty())
        new_button = QPushButton("新建")
        new_button.clicked.connect(self.new_requested.emit)
        import_button = QPushButton("导入")
        import_button.clicked.connect(self.import_requested.emit)
        profile_row.addWidget(QLabel("方案名称"))
        profile_row.addWidget(self.name_edit, 1)
        profile_row.addWidget(new_button)
        profile_row.addWidget(import_button)
        content_layout.addLayout(profile_row)

        mode_form = QFormLayout()
        self.mode_combo = QComboBox()
        for mode, label in (
            (MappingMode.DEGREE_MODIFIER, "音级 + 按住修饰键"),
            (MappingMode.DIRECT_NOTE, "每个音符直接映射"),
            (MappingMode.ROW_OCTAVE, "三行音区直接映射"),
        ):
            self.mode_combo.addItem(label, mode.value)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_form.addRow("映射模式", self.mode_combo)
        content_layout.addLayout(mode_form)
        self.mapping_hint = QLabel(objectName="muted")
        self.mapping_hint.setWordWrap(True)
        content_layout.addWidget(self.mapping_hint)

        self.mapping_box = QWidget()
        self.mapping_layout = QVBoxLayout(self.mapping_box)
        self.mapping_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self.mapping_box)

        parameters_heading = QLabel("演奏参数", objectName="sectionLabel")
        content_layout.addWidget(parameters_heading)
        parameters = QGridLayout()
        self.output_mode_combo = QComboBox()
        self.output_mode_combo.addItem("短按触发（推荐）", NoteOutputMode.TAP.value)
        self.output_mode_combo.addItem("持续按住", NoteOutputMode.HOLD.value)
        self.output_mode_combo.currentIndexChanged.connect(self._on_output_mode_changed)
        self.hold_spin = QSpinBox()
        self.hold_spin.setRange(10, 500)
        self.hold_spin.setSuffix(" ms")
        self.hold_spin.valueChanged.connect(lambda _value: self._mark_dirty())
        self.gap_spin = QSpinBox()
        self.gap_spin.setRange(0, 200)
        self.gap_spin.setSuffix(" ms")
        self.gap_spin.valueChanged.connect(lambda _value: self._mark_dirty())
        parameters.addWidget(QLabel("音符输出方式"), 0, 0)
        parameters.addWidget(QLabel("按键时长"), 0, 1)
        parameters.addWidget(QLabel("最小释放间隔"), 0, 2)
        parameters.addWidget(self.output_mode_combo, 1, 0)
        parameters.addWidget(self.hold_spin, 1, 1)
        parameters.addWidget(self.gap_spin, 1, 2)
        parameters.setColumnStretch(0, 1)
        parameters.setColumnStretch(1, 1)
        parameters.setColumnStretch(2, 1)
        content_layout.addLayout(parameters)
        content_layout.addStretch()
        scroll.setWidget(content)
        page_layout.addWidget(scroll, 1)

        self.state_label = QLabel("所有修改已保存", objectName="muted")
        page_layout.addWidget(self.state_label)

    def load_profile(self, profile: GameProfile) -> None:
        """
        将 Profile 复制为可编辑草稿并刷新全部控件。

        Args:
            profile (GameProfile): 当前生效的配置方案。
        """

        self._profile = profile
        self._draft = deepcopy(profile)
        controls = (
            self.name_edit,
            self.mode_combo,
            self.output_mode_combo,
            self.hold_spin,
            self.gap_spin,
        )
        for control in controls:
            control.blockSignals(True)
        self.name_edit.setText(profile.name)
        self.mode_combo.setCurrentIndex(
            max(0, self.mode_combo.findData(profile.mapping_mode.value))
        )
        self.output_mode_combo.setCurrentIndex(
            max(0, self.output_mode_combo.findData(profile.note_output_mode.value))
        )
        self.hold_spin.setValue(profile.key_hold_ms)
        self.gap_spin.setValue(profile.key_gap_ms)
        for control in controls:
            control.blockSignals(False)
        self._update_hold_control()
        self._rebuild_mapping()
        self._set_dirty(False)

    def _create_binding_button(
        self,
        binding: Binding | None,
        save: Callable[[Binding], None],
        prefix: str = "",
    ) -> QPushButton:
        """
        创建可录入键盘或鼠标绑定的按钮。

        Args:
            binding (Binding | None): 当前绑定。
            save (Callable[[Binding], None]): 保存新绑定的回调。
            prefix (str): 显示在按键名称前的音级文字。

        Returns:
            QPushButton: 可点击录入的绑定按钮。
        """

        def button_text(value: Binding | None) -> str:
            """
            生成绑定按钮文字。

            Args:
                value (Binding | None): 要显示的绑定。

            Returns:
                str: 按钮显示文字。
            """

            label = value.label if value is not None else "未设置"
            return f"{prefix}\n{label}" if prefix else label

        button = QPushButton(button_text(binding), objectName="binding")

        def record() -> None:
            """捕获一个输入绑定并更新草稿。"""

            captured = capture_binding(self)
            if captured is None:
                return
            save(captured)
            button.setText(button_text(captured))
            self._mark_dirty()

        button.clicked.connect(record)
        return button

    def _add_binding_row(
        self,
        grid: QGridLayout,
        row: int,
        label_text: str,
        binding: Binding | None,
        save: Callable[[Binding], None],
    ) -> None:
        """
        向映射网格添加说明和录入按钮。

        Args:
            grid (QGridLayout): 目标网格。
            row (int): 网格行号。
            label_text (str): 行说明。
            binding (Binding | None): 当前绑定。
            save (Callable[[Binding], None]): 保存新绑定的回调。
        """

        grid.addWidget(QLabel(label_text), row, 0)
        grid.addWidget(self._create_binding_button(binding, save), row, 1)

    def _clear_layout(self, target: QLayout) -> None:
        """
        递归清空动态映射布局。

        Args:
            target (QLayout): 需要清空的布局。
        """

        while target.count():
            item = target.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)
                child_layout.deleteLater()

    def _rebuild_mapping(self) -> None:
        """根据草稿的映射模式重建按键区域。"""

        self._clear_layout(self.mapping_layout)
        draft = self._draft
        if draft is None:
            return
        if draft.mapping_mode is MappingMode.DEGREE_MODIFIER:
            self.mapping_hint.setText(
                "中音直接使用音级键；低音、高音和半音通过按住修饰键演奏。"
            )
            grid = QGridLayout()
            for row, name in enumerate(("Do", "Re", "Mi", "Fa", "Sol", "La", "Si")):
                degree = row + 1
                self._add_binding_row(
                    grid,
                    row,
                    f"{degree}  {name}",
                    draft.note_bindings.get(degree),
                    lambda value, item=degree: draft.note_bindings.__setitem__(item, value),
                )
            row = 7
            for octave, label_text in (
                (Octave.LOW, "低音修饰"),
                (Octave.HIGH, "高音修饰"),
            ):
                self._add_binding_row(
                    grid,
                    row,
                    label_text,
                    draft.zone_bindings.get(octave),
                    lambda value, item=octave: draft.zone_bindings.__setitem__(item, value),
                )
                row += 1
            self._add_binding_row(
                grid,
                row,
                "半音修饰",
                draft.semitone_binding,
                self._set_semitone_binding,
            )
            grid.setColumnStretch(1, 1)
            self.mapping_layout.addLayout(grid)
            return

        grid = QGridLayout()
        grid.setHorizontalSpacing(7)
        for degree in range(1, 8):
            header = QLabel(str(degree), objectName="muted")
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(header, 0, degree)
        if draft.mapping_mode is MappingMode.ROW_OCTAVE:
            self.mapping_hint.setText(
                "低、中、高三个音区各一行，每行按 1～7 直接映射，不使用半音行。"
            )
            rows = tuple(
                (octave, octave_label, False, "")
                for octave, octave_label in (
                    (Octave.LOW, "低音"),
                    (Octave.MIDDLE, "中音"),
                    (Octave.HIGH, "高音"),
                )
            )
        else:
            self.mapping_hint.setText(
                "低、中、高音的自然音与半音分别成行，每个音符可独立绑定。"
            )
            rows = tuple(
                (octave, f"{prefix}{octave_label}音", is_semitone, prefix)
                for octave, octave_label in (
                    (Octave.LOW, "低"),
                    (Octave.MIDDLE, "中"),
                    (Octave.HIGH, "高"),
                )
                for is_semitone, prefix in ((False, ""), (True, "#"))
            )
        for row, (octave, label_text, is_semitone, _prefix) in enumerate(rows, start=1):
            grid.addWidget(QLabel(label_text), row, 0)
            for degree in range(1, 8):
                note = NoteEvent(Fraction(0), Fraction(1), degree, octave, is_semitone)
                key = note_binding_key(note)
                button = self._create_binding_button(
                    draft.direct_note_bindings.get(key),
                    lambda value, item=key: draft.direct_note_bindings.__setitem__(item, value),
                )
                grid.addWidget(button, row, degree)
        self.mapping_layout.addLayout(grid)

    def _set_semitone_binding(self, value: Binding) -> None:
        """
        更新草稿中的半音修饰键。

        Args:
            value (Binding): 新半音修饰键。
        """

        if self._draft is not None:
            self._draft.semitone_binding = value

    def _on_mode_changed(self, _index: int) -> None:
        """
        响应映射模式变化并重建网格。

        Args:
            _index (int): 当前下拉框索引。
        """

        if self._draft is None:
            return
        try:
            self._draft.mapping_mode = MappingMode(str(self.mode_combo.currentData()))
        except ValueError:
            return
        self._rebuild_mapping()
        self._mark_dirty()

    def _on_output_mode_changed(self, _index: int) -> None:
        """
        响应音符输出方式变化。

        Args:
            _index (int): 当前下拉框索引。
        """

        self._update_hold_control()
        self._mark_dirty()

    def _update_hold_control(self) -> None:
        """根据输出方式启用或禁用固定按键时长。"""

        is_tap = self.output_mode_combo.currentData() == NoteOutputMode.TAP.value
        self.hold_spin.setEnabled(is_tap)
        self.hold_spin.setToolTip(
            "短按触发时使用固定按键时长"
            if is_tap
            else "持续按住模式由曲谱音符时值决定按键时长"
        )

    def _mark_dirty(self) -> None:
        """将页面标记为存在未保存修改。"""

        if self._draft is None:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        """
        更新修改状态与页面提示。

        Args:
            dirty (bool): 是否存在未保存修改。
        """

        self._dirty = dirty
        self.state_label.setText("方案存在未保存修改" if dirty else "所有修改已保存")
        self.save_button.setEnabled(dirty)
        self.dirty_changed.emit(dirty)

    def _request_save(self) -> None:
        """整理页面值并请求主窗口持久化当前方案。"""

        draft = self._draft
        if draft is None:
            return
        try:
            draft.mapping_mode = MappingMode(str(self.mode_combo.currentData()))
            draft.note_output_mode = NoteOutputMode(
                str(self.output_mode_combo.currentData())
            )
        except ValueError:
            return
        draft.key_hold_ms = self.hold_spin.value()
        draft.key_gap_ms = self.gap_spin.value()
        self.save_requested.emit(deepcopy(draft), self.name_edit.text())

    def mark_saved(self, profile: GameProfile) -> None:
        """
        在保存成功后用持久化结果重置页面草稿。

        Args:
            profile (GameProfile): 已保存并生效的 Profile。
        """

        self.load_profile(profile)
