from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.common.pdf_form.field_models import (
    ALIGN_LABELS,
    CREATABLE_FIELD_TYPES,
    FormError,
    WidgetInstance,
)
from app.common.pdf_form.form_service import FormDocumentSession


def _rgb_tuple_to_hex(rgb: tuple[float, float, float] | None, fallback: str = "#1A1A1A") -> str:
    if not rgb or len(rgb) != 3:
        return fallback
    r, g, b = (max(0, min(255, round(c * 255))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def _hex_to_rgb_tuple(text: str, fallback: tuple[float, float, float] = (0.1, 0.1, 0.1)) -> tuple[float, float, float]:
    col = QColor((text or "").strip())
    if not col.isValid():
        return fallback
    return (col.redF(), col.greenF(), col.blueF())


class FormCreatorPanel(QWidget):
    """탭 1 — 양식 만들기 오른쪽 패널 (도구 선택, 생성된 필드 목록, 필드 속성 편집)."""

    tool_mode_changed = pyqtSignal(object)     # None (select mode) or field_type str
    widget_focus_requested = pyqtSignal(int)   # xref
    document_mutated = pyqtSignal(int)         # selected xref after mutation
    save_form_requested = pyqtSignal()
    help_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session: FormDocumentSession | None = None
        self.current_xref: int = 0
        self._loading_props = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(8)

        # 상단 안내 + 도움말 링크
        top_bar = QHBoxLayout()
        guide_lbl = QLabel("<b>PDF에서 입력받을 위치를 마우스로 지정하세요.</b>")
        guide_lbl.setStyleSheet("color: #2C2A29; font-size: 13px;")
        self.btn_help = QPushButton("이 기능은 무엇인가요?")
        self.btn_help.setObjectName("secondaryBtn")
        self.btn_help.clicked.connect(self.help_requested.emit)
        top_bar.addWidget(guide_lbl, 1)
        top_bar.addWidget(self.btn_help)
        outer.addLayout(top_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(2, 2, 4, 2)
        layout.setSpacing(10)

        # 1. 입력란 추가 도구 그룹
        tools_group = QGroupBox("1. 입력란 추가 도구")
        tools_grid = QGridLayout(tools_group)
        tools_grid.setSpacing(6)
        self.tool_btn_group = QButtonGroup(self)
        self.tool_btn_group.setExclusive(True)
        self.tool_buttons: dict[str | None, QPushButton] = {}

        btn_select = QPushButton("선택 / 위치 이동")
        btn_select.setCheckable(True)
        btn_select.setChecked(True)
        btn_select.setToolTip("이미 만든 입력란을 클릭해 선택하거나 이동·크기 조정합니다.")
        btn_select.clicked.connect(lambda: self._select_tool(None))
        self.tool_btn_group.addButton(btn_select)
        self.tool_buttons[None] = btn_select
        tools_grid.addWidget(btn_select, 0, 0, 1, 2)

        for idx, (ftype, title, desc) in enumerate(CREATABLE_FIELD_TYPES):
            btn = QPushButton(f"+ {title}")
            btn.setCheckable(True)
            btn.setToolTip(f"{title}: {desc}")
            btn.clicked.connect(lambda _checked=False, t=ftype: self._select_tool(t))
            self.tool_btn_group.addButton(btn)
            self.tool_buttons[ftype] = btn
            row = (idx // 2) + 1
            col = idx % 2
            tools_grid.addWidget(btn, row, col)

        self.lbl_tool_hint = QLabel("현재 모드: <b>선택 / 위치 이동</b> — 입력란을 클릭해 속성을 편집합니다.")
        self.lbl_tool_hint.setWordWrap(True)
        self.lbl_tool_hint.setStyleSheet("color: #55504D; font-size: 12px; padding: 2px;")
        tools_grid.addWidget(self.lbl_tool_hint, 5, 0, 1, 2)
        layout.addWidget(tools_group)

        # 2. 생성된 입력란 목록
        list_group = QGroupBox("2. 생성된 입력란 목록")
        list_layout = QVBoxLayout(list_group)
        list_layout.setSpacing(6)

        self.field_table = QTableWidget(0, 4)
        self.field_table.setHorizontalHeaderLabels(["표시 이름", "유형", "페이지", "필수"])
        self.field_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.field_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.field_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.field_table.verticalHeader().setVisible(False)
        self.field_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            self.field_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.field_table.setMinimumHeight(130)
        self.field_table.setMaximumHeight(180)
        self.field_table.cellClicked.connect(self._on_table_row_clicked)
        list_layout.addWidget(self.field_table)

        list_btns = QHBoxLayout()
        self.btn_undo = QPushButton("실행 취소")
        self.btn_undo.clicked.connect(self._on_undo)
        self.btn_redo = QPushButton("다시 실행")
        self.btn_redo.clicked.connect(self._on_redo)
        self.btn_delete = QPushButton("선택 입력란 삭제")
        self.btn_delete.setStyleSheet("QPushButton { color: #B91C1C; font-weight: 600; }")
        self.btn_delete.clicked.connect(self.delete_selected_widget)
        list_btns.addWidget(self.btn_undo)
        list_btns.addWidget(self.btn_redo)
        list_btns.addStretch(1)
        list_btns.addWidget(self.btn_delete)
        list_layout.addLayout(list_btns)
        layout.addWidget(list_group)

        # 3. 선택된 입력란 속성 편집
        self.props_group = QGroupBox("3. 선택한 입력란 속성 편집")
        props_layout = QVBoxLayout(self.props_group)
        props_form = QFormLayout()
        props_form.setSpacing(6)

        self.edit_label = QLineEdit()
        self.edit_label.setPlaceholderText("예: 신청자 이름")
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("예: applicant_name")
        self.chk_allow_dup = QCheckBox("같은 필드명 공유 허용 (라디오 그룹 / 동일 값 반복 표시)")
        self.btn_link_alias = QPushButton("선택한 입력란을 동일 값으로 연결")
        self.btn_link_alias.setObjectName("secondaryBtn")
        self.btn_link_alias.setToolTip("현재 선택한 입력란을 다른 필드와 동일한 값을 공유하도록 연결합니다.")
        self.btn_link_alias.clicked.connect(self._link_selected_as_alias)
        self.btn_normalize_radio = QPushButton("라디오 그룹 상태 정리")
        self.btn_normalize_radio.setObjectName("secondaryBtn")
        self.btn_normalize_radio.setToolTip("같은 그룹의 라디오 버튼이 하나만 선택되도록 On/Off 상태를 정리합니다.")
        self.btn_normalize_radio.clicked.connect(self._normalize_selected_radio)

        self.lbl_type_info = QLabel("-")
        self.lbl_page_info = QLabel("-")

        self.chk_required = QCheckBox("필수 입력 항목")
        self.chk_readonly = QCheckBox("읽기 전용 (수정 잠금)")

        self.edit_default = QLineEdit()
        self.edit_default.setPlaceholderText("기본값 (선택사항)")
        self.chk_default_bool = QCheckBox("기본으로 체크됨")
        self.chk_default_bool.setVisible(False)

        self.spin_maxlen = QSpinBox()
        self.spin_maxlen.setRange(0, 5000)
        self.spin_maxlen.setSpecialValueText("제한 없음")

        self.edit_radio_option = QLineEdit()
        self.edit_radio_option.setPlaceholderText("이 라디오 버튼의 선택값 (예: 남성)")

        # 선택 목록 편집기 (드롭다운 / 목록 상자)
        self.choices_box = QWidget()
        choices_lay = QVBoxLayout(self.choices_box)
        choices_lay.setContentsMargins(0, 0, 0, 0)
        choices_lay.setSpacing(4)
        self.choices_list = QListWidget()
        self.choices_list.setMaximumHeight(95)
        choice_add_row = QHBoxLayout()
        self.edit_new_choice = QLineEdit()
        self.edit_new_choice.setPlaceholderText("새 선택 항목 입력")
        btn_add_choice = QPushButton("추가")
        btn_add_choice.clicked.connect(self._add_choice_item)
        btn_del_choice = QPushButton("삭제")
        btn_del_choice.clicked.connect(self._remove_choice_item)
        btn_up_choice = QPushButton("▲")
        btn_up_choice.setFixedWidth(32)
        btn_up_choice.clicked.connect(lambda: self._move_choice_item(-1))
        btn_dn_choice = QPushButton("▼")
        btn_dn_choice.setFixedWidth(32)
        btn_dn_choice.clicked.connect(lambda: self._move_choice_item(1))
        for w in (self.edit_new_choice, btn_add_choice, btn_del_choice, btn_up_choice, btn_dn_choice):
            choice_add_row.addWidget(w)
        choices_lay.addWidget(self.choices_list)
        choices_lay.addLayout(choice_add_row)
        self.choices_box.setVisible(False)

        # 표시 속성
        self.spin_fontsize = QDoubleSpinBox()
        self.spin_fontsize.setRange(6.0, 36.0)
        self.spin_fontsize.setValue(11.0)
        self.spin_fontsize.setSingleStep(1.0)

        self.combo_align = QComboBox()
        for code, text in ALIGN_LABELS.items():
            self.combo_align.addItem(text, code)

        self.edit_text_color = QLineEdit("#1A1A1A")
        btn_pick_text_color = QPushButton("색상")
        btn_pick_text_color.clicked.connect(lambda: self._pick_color(self.edit_text_color))
        tcol_row = QHBoxLayout()
        tcol_row.addWidget(self.edit_text_color, 1)
        tcol_row.addWidget(btn_pick_text_color)

        self.edit_fill_color = QLineEdit("#FAFCFF")
        self.chk_transparent_fill = QCheckBox("배경 투명")
        self.chk_transparent_fill.setChecked(True)
        btn_pick_fill_color = QPushButton("색상")
        btn_pick_fill_color.clicked.connect(lambda: self._pick_color(self.edit_fill_color))
        fcol_row = QHBoxLayout()
        fcol_row.addWidget(self.edit_fill_color, 1)
        fcol_row.addWidget(btn_pick_fill_color)
        fcol_row.addWidget(self.chk_transparent_fill)

        self.edit_border_color = QLineEdit("#407AD9")
        btn_pick_border_color = QPushButton("색상")
        btn_pick_border_color.clicked.connect(lambda: self._pick_color(self.edit_border_color))
        bcol_row = QHBoxLayout()
        bcol_row.addWidget(self.edit_border_color, 1)
        bcol_row.addWidget(btn_pick_border_color)

        self.spin_border_width = QDoubleSpinBox()
        self.spin_border_width.setRange(0.0, 6.0)
        self.spin_border_width.setValue(0.0)
        self.spin_border_width.setSingleStep(0.5)

        props_form.addRow("표시 이름:", self.edit_label)
        props_form.addRow("내부 필드명:", self.edit_name)
        props_form.addRow("", self.chk_allow_dup)
        props_form.addRow(self.btn_link_alias)
        props_form.addRow(self.btn_normalize_radio)
        props_form.addRow("입력란 유형:", self.lbl_type_info)
        props_form.addRow("페이지 번호:", self.lbl_page_info)
        props_form.addRow("입력 조건:", self.chk_required)
        props_form.addRow("", self.chk_readonly)
        props_form.addRow("기본값:", self.edit_default)
        props_form.addRow("체크 기본값:", self.chk_default_bool)
        props_form.addRow("최대 글자 수:", self.spin_maxlen)
        props_form.addRow("라디오 선택값:", self.edit_radio_option)
        props_form.addRow("선택 항목 목록:", self.choices_box)
        props_form.addRow("글자 크기(pt):", self.spin_fontsize)
        props_form.addRow("텍스트 정렬:", self.combo_align)
        props_form.addRow("글자색:", tcol_row)
        props_form.addRow("배경색:", fcol_row)
        props_form.addRow("테두리색:", bcol_row)
        props_form.addRow("테두리 두께:", self.spin_border_width)
        props_layout.addLayout(props_form)

        self.btn_apply_props = QPushButton("속성 변경 적용")
        self.btn_apply_props.setObjectName("actionBtn")
        self.btn_apply_props.clicked.connect(self.apply_properties)
        props_layout.addWidget(self.btn_apply_props)
        layout.addWidget(self.props_group)
        layout.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # 하단 저장 버튼
        self.btn_save_form = QPushButton("입력 가능한 PDF 입력폼 저장")
        self.btn_save_form.setObjectName("actionBtn")
        self.btn_save_form.setMinimumHeight(38)
        self.btn_save_form.clicked.connect(self.save_form_requested.emit)
        outer.addWidget(self.btn_save_form)

        self.props_group.setEnabled(False)

    def _select_tool(self, field_type: str | None):
        btn = self.tool_buttons.get(field_type)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
        if field_type is None:
            self.lbl_tool_hint.setText("현재 모드: <b>선택 / 위치 이동</b> — 입력란을 클릭해 속성을 편집합니다.")
        else:
            title = next((t for k, t, _ in CREATABLE_FIELD_TYPES if k == field_type), field_type)
            self.lbl_tool_hint.setText(
                f"현재 모드: <b>{title} 추가</b> — 왼쪽 PDF 화면에서 마우스로 영역을 드래그하세요. (Esc: 선택 모드로 복귀)"
            )
        self.tool_mode_changed.emit(field_type)

    def reset_to_select_mode(self):
        self._select_tool(None)

    def bind_session(self, session: FormDocumentSession | None, selected_xref: int = 0):
        self.session = session
        self.refresh_panel(selected_xref)

    def refresh_panel(self, selected_xref: int = 0):
        self.current_xref = selected_xref
        has_doc = self.session is not None
        self.btn_save_form.setEnabled(has_doc)
        self.btn_undo.setEnabled(bool(self.session and self.session.can_undo))
        self.btn_redo.setEnabled(bool(self.session and self.session.can_redo))

        self.field_table.blockSignals(True)
        self.field_table.setRowCount(0)
        selected_row = -1
        if self.session:
            for row, w in enumerate(self.session.list_widgets()):
                self.field_table.insertRow(row)
                name_item = QTableWidgetItem(w.display_name)
                name_item.setData(Qt.ItemDataRole.UserRole, w.xref)
                type_item = QTableWidgetItem(w.type_label)
                page_item = QTableWidgetItem(f"{w.page_index + 1}p")
                req_item = QTableWidgetItem("필수" if w.required else "-")
                for col, item in enumerate((name_item, type_item, page_item, req_item)):
                    if col >= 2:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.field_table.setItem(row, col, item)
                if w.xref == selected_xref:
                    selected_row = row
        if selected_row >= 0:
            self.field_table.selectRow(selected_row)
        self.field_table.blockSignals(False)

        self.btn_delete.setEnabled(bool(selected_xref and self.session))
        self._load_widget_into_form(self.session.get_widget_by_xref(selected_xref) if (self.session and selected_xref) else None)

    def _on_table_row_clicked(self, row: int, _col: int):
        item = self.field_table.item(row, 0)
        if item is None:
            return
        xref = int(item.data(Qt.ItemDataRole.UserRole) or 0)
        if xref:
            self.current_xref = xref
            self.btn_delete.setEnabled(True)
            if self.session:
                self._load_widget_into_form(self.session.get_widget_by_xref(xref))
            self.widget_focus_requested.emit(xref)

    def _load_widget_into_form(self, w: WidgetInstance | None):
        self._loading_props = True
        try:
            if w is None:
                self.props_group.setEnabled(False)
                self.edit_label.clear()
                self.edit_name.clear()
                self.lbl_type_info.setText("-")
                self.lbl_page_info.setText("-")
                return

            self.props_group.setEnabled(True)
            self.edit_label.setText(w.field_label)
            self.edit_name.setText(w.field_name)
            self.lbl_type_info.setText(w.type_label)
            self.lbl_page_info.setText(f"{w.page_index + 1} 페이지")
            self.chk_required.setChecked(w.required)
            self.chk_readonly.setChecked(w.read_only)

            is_text_like = w.field_type in ("text", "multiline", "date")
            is_check = w.field_type == "checkbox"
            is_radio = w.field_type == "radio"
            is_choice = w.field_type in ("combobox", "listbox")

            self.edit_default.setVisible(not is_check)
            self.chk_default_bool.setVisible(is_check)
            if is_check:
                self.chk_default_bool.setChecked(bool(w.value))
            elif is_radio:
                self.edit_default.setText(str(w.value or ""))
            else:
                self.edit_default.setText(str(w.default_value or w.value or ""))

            self.spin_maxlen.setEnabled(is_text_like)
            self.spin_maxlen.setValue(w.max_len if is_text_like else 0)

            self.edit_radio_option.setEnabled(is_radio)
            self.edit_radio_option.setText(w.on_state if is_radio else "")

            self.choices_box.setVisible(is_choice)
            self.choices_list.clear()
            if is_choice:
                for ch in w.choices:
                    self.choices_list.addItem(ch)

            self.spin_fontsize.setValue(w.font_size)
            idx = self.combo_align.findData(w.align)
            self.combo_align.setCurrentIndex(max(0, idx))
            self.edit_text_color.setText(_rgb_tuple_to_hex(w.text_color, "#1A1A1A"))
            self.chk_transparent_fill.setChecked(w.fill_color is None)
            self.edit_fill_color.setText(_rgb_tuple_to_hex(w.fill_color, "#FAFCFF"))
            self.edit_border_color.setText(_rgb_tuple_to_hex(w.border_color, "#407AD9"))
            self.spin_border_width.setValue(w.border_width)
        finally:
            self._loading_props = False

    def _pick_color(self, line_edit: QLineEdit):
        initial = QColor(line_edit.text().strip() or "#1A1A1A")
        col = QColorDialog.getColor(initial, self, "색상 선택")
        if col.isValid():
            line_edit.setText(col.name().upper())

    def _add_choice_item(self):
        text = self.edit_new_choice.text().strip()
        if not text:
            return
        existing = [self.choices_list.item(i).text() for i in range(self.choices_list.count())]
        if text not in existing:
            self.choices_list.addItem(text)
        self.edit_new_choice.clear()

    def _remove_choice_item(self):
        row = self.choices_list.currentRow()
        if row >= 0:
            self.choices_list.takeItem(row)

    def _move_choice_item(self, delta: int):
        row = self.choices_list.currentRow()
        target = row + delta
        if 0 <= row < self.choices_list.count() and 0 <= target < self.choices_list.count():
            item = self.choices_list.takeItem(row)
            self.choices_list.insertItem(target, item)
            self.choices_list.setCurrentRow(target)

    def apply_properties(self):
        if self._loading_props or not self.session or not self.current_xref:
            return
        w = self.session.get_widget_by_xref(self.current_xref)
        if w is None:
            return
        try:
            choices = None
            if w.field_type in ("combobox", "listbox"):
                choices = [self.choices_list.item(i).text() for i in range(self.choices_list.count())]
            default_val: object
            if w.field_type == "checkbox":
                default_val = self.chk_default_bool.isChecked()
            else:
                default_val = self.edit_default.text().strip()

            radio_opt = self.edit_radio_option.text().strip() if w.field_type == "radio" else None
            radio_sel = (default_val == radio_opt and bool(radio_opt)) if w.field_type == "radio" else None

            updated = self.session.update_widget_properties(
                self.current_xref,
                field_name=self.edit_name.text().strip(),
                field_label=self.edit_label.text().strip(),
                default_value=default_val,
                required=self.chk_required.isChecked(),
                read_only=self.chk_readonly.isChecked(),
                max_len=self.spin_maxlen.value(),
                choices=choices,
                radio_option=radio_opt,
                radio_default_selected=radio_sel,
                font_size=self.spin_fontsize.value(),
                text_color=_hex_to_rgb_tuple(self.edit_text_color.text(), (0.1, 0.1, 0.1)),
                fill_color=None if self.chk_transparent_fill.isChecked() else _hex_to_rgb_tuple(self.edit_fill_color.text(), (0.98, 0.99, 1.0)),
                clear_fill_color=self.chk_transparent_fill.isChecked(),
                border_color=_hex_to_rgb_tuple(self.edit_border_color.text(), (0.25, 0.48, 0.85)),
                border_width=self.spin_border_width.value(),
                align=int(self.combo_align.currentData() or 0),
                allow_duplicate_name=self.chk_allow_dup.isChecked(),
            )
            self.document_mutated.emit(updated.xref)
        except FormError as exc:
            QMessageBox.warning(self, "속성 편집", str(exc))

    def delete_selected_widget(self):
        if not self.session or not self.current_xref:
            return
        w = self.session.get_widget_by_xref(self.current_xref)
        if w is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle("입력란 삭제")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"'{w.display_name}' ({w.type_label}) 입력란을 삭제하시겠습니까?\n삭제 후에도 [실행 취소]로 되돌릴 수 있습니다.")
        btn_del = box.addButton("삭제", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() != btn_del:
            return
        try:
            self.session.delete_widget(self.current_xref)
            self.current_xref = 0
            self.document_mutated.emit(0)
        except FormError as exc:
            QMessageBox.warning(self, "입력란 삭제", str(exc))

    def _on_undo(self):
        if self.session and self.session.undo():
            self.document_mutated.emit(0)

    def _on_redo(self):
        if self.session and self.session.redo():
            self.document_mutated.emit(0)

    def _link_selected_as_alias(self):
        if not self.session or not self.current_xref:
            QMessageBox.information(self, "안내", "먼저 연결할 입력란을 선택하세요.")
            return
        target, ok = QInputDialog.getText(
            self, "동일 값 공유", "연결할 대상 필드명을 입력하세요\n(같은 유형의 기존 필드명):"
        )
        if not ok or not target.strip():
            return
        try:
            updated = self.session.link_as_alias(self.current_xref, target.strip())
            self.document_mutated.emit(updated.xref)
            QMessageBox.information(self, "완료", f"'{target.strip()}'와 동일한 값을 공유하도록 연결했습니다.")
        except FormError as exc:
            QMessageBox.warning(self, "연결 실패", str(exc))

    def _normalize_selected_radio(self):
        if not self.session or not self.current_xref:
            QMessageBox.information(self, "안내", "라디오 그룹에 속한 입력란을 선택하세요.")
            return
        w = self.session.get_widget_by_xref(self.current_xref)
        if not w or w.field_type != "radio":
            QMessageBox.information(self, "안내", "라디오 버튼 입력란을 선택하세요.")
            return
        try:
            count = self.session.normalize_radio_group(w.field_name)
            self.document_mutated.emit(self.current_xref)
            QMessageBox.information(self, "완료", f"라디오 그룹 '{w.field_name}'의 {count}개 항목 상태를 정리했습니다.")
        except FormError as exc:
            QMessageBox.warning(self, "정리 실패", str(exc))

