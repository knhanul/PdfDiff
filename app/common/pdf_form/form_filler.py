from PyQt6.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.common.pdf_form.field_models import FormError, LogicalField, validate_date_string
from app.common.pdf_form.form_service import FormDocumentSession


class _FocusFilter(QObject):
    focused = pyqtSignal()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.FocusIn, QEvent.Type.MouseButtonPress):
            self.focused.emit()
        return super().eventFilter(obj, event)


class FormFillerPanel(QWidget):
    """탭 2 — 양식 작성하기 오른쪽 패널 (PDF ↔ 입력 컨트롤 양방향 연동, 상태 요약, 양식 유지/고정 저장)."""

    field_selected = pyqtSignal(str, int)    # field_name, primary_xref
    value_committed = pyqtSignal(str)        # field_name
    switch_to_creator_requested = pyqtSignal()
    save_filled_requested = pyqtSignal(bool) # bake (True=입력 내용 고정, False=양식 유지)
    help_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session: FormDocumentSession | None = None
        self._field_cards: dict[str, QFrame] = {}
        self._field_editors: dict[str, QWidget] = {}
        self._focus_filters: list[_FocusFilter] = []
        self._syncing_ui = False
        self._active_field_name: str = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(8)

        # 상단 안내 + 도움말
        top_bar = QHBoxLayout()
        self.lbl_found_summary = QLabel("<b>이 문서에서 입력 가능한 항목 0개를 찾았습니다.</b>")
        self.lbl_found_summary.setStyleSheet("color: #2C2A29; font-size: 13px;")
        self.btn_help = QPushButton("이 기능은 무엇인가요?")
        self.btn_help.setObjectName("secondaryBtn")
        self.btn_help.clicked.connect(self.help_requested.emit)
        top_bar.addWidget(self.lbl_found_summary, 1)
        top_bar.addWidget(self.btn_help)
        outer.addLayout(top_bar)

        # 작성 상태 요약 카드
        self.status_card = QFrame()
        self.status_card.setStyleSheet(
            "QFrame { background-color: #F7F5F2; border: 1px solid #DFDAD4; border-radius: 8px; padding: 6px; }"
        )
        status_lay = QVBoxLayout(self.status_card)
        status_lay.setContentsMargins(8, 6, 8, 6)
        status_lay.setSpacing(4)
        self.lbl_progress_detail = QLabel("필수 항목 0개 중 0개 작성")
        self.lbl_progress_detail.setStyleSheet("color: #3D3835; font-size: 12px; font-weight: 600;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(14)
        self.lbl_badges = QLabel("작성 완료 0 · 미작성 0 · 필수 미작성 0 · 읽기 전용 0")
        self.lbl_badges.setStyleSheet("color: #6B6560; font-size: 11px;")
        status_lay.addWidget(self.lbl_progress_detail)
        status_lay.addWidget(self.progress_bar)
        status_lay.addWidget(self.lbl_badges)
        outer.addWidget(self.status_card)

        # 빈 양식 안내 카드 (일반 PDF일 때 표시)
        self.empty_box = QFrame()
        self.empty_box.setStyleSheet(
            "QFrame { background-color: #FFFBF7; border: 1px dashed #D4A373; border-radius: 10px; padding: 18px; }"
        )
        empty_lay = QVBoxLayout(self.empty_box)
        empty_lay.setSpacing(10)
        lbl_empty = QLabel(
            "<b>이 PDF에는 아직 입력 가능한 양식이 없습니다.</b><br>"
            "<span style='color:#666;'>양식 만들기 탭에서 이름, 날짜, 체크박스 등의 입력란을 먼저 추가해보세요.</span>"
        )
        lbl_empty.setWordWrap(True)
        btn_go_create = QPushButton("양식 만들기로 이동")
        btn_go_create.setObjectName("actionBtn")
        btn_go_create.clicked.connect(self.switch_to_creator_requested.emit)
        empty_lay.addWidget(lbl_empty)
        empty_lay.addWidget(btn_go_create, alignment=Qt.AlignmentFlag.AlignLeft)
        self.empty_box.setVisible(False)
        outer.addWidget(self.empty_box)

        # 입력 항목 스크롤 영역
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.form_host = QWidget()
        self.form_layout = QVBoxLayout(self.form_host)
        self.form_layout.setContentsMargins(2, 2, 4, 2)
        self.form_layout.setSpacing(8)
        self.scroll.setWidget(self.form_host)
        outer.addWidget(self.scroll, 1)

        # 하단 저장 옵션 및 저장 버튼
        save_group = QGroupBox("작성 결과 저장 옵션")
        save_lay = QVBoxLayout(save_group)
        save_lay.setSpacing(6)
        self.radio_keep_form = QRadioButton("양식 유지 (기본값 — 나중에 다시 열어 내용을 수정할 수 있음)")
        self.radio_bake_form = QRadioButton("입력 내용 고정 (문서 페이지에 글자 고정 — 이후 양식 수정·추출 불가)")
        self.radio_keep_form.setChecked(True)
        save_lay.addWidget(self.radio_keep_form)
        save_lay.addWidget(self.radio_bake_form)

        self.btn_save_filled = QPushButton("작성한 PDF 저장")
        self.btn_save_filled.setObjectName("actionBtn")
        self.btn_save_filled.setMinimumHeight(38)
        self.btn_save_filled.clicked.connect(
            lambda: self.save_filled_requested.emit(self.radio_bake_form.isChecked())
        )
        save_lay.addWidget(self.btn_save_filled)
        outer.addWidget(save_group)
        self.apply_theme()

    def apply_theme(self, theme_id=None):
        from app.services import app_settings
        from app.shell.theme import THEMES, theme_tokens

        if theme_id is None:
            theme_id = app_settings.get("ui/theme")
        if theme_id not in THEMES or theme_id == "default":
            self.status_card.setStyleSheet(
                "QFrame { background-color: #F7F5F2; border: 1px solid #DFDAD4; border-radius: 8px; padding: 6px; }"
            )
            self.lbl_progress_detail.setStyleSheet("color: #3D3835; font-size: 12px; font-weight: 600;")
            self.lbl_badges.setStyleSheet("color: #6B6560; font-size: 11px;")
            self.empty_box.setStyleSheet(
                "QFrame { background-color: #FFFBF7; border: 1px dashed #D4A373; border-radius: 10px; padding: 18px; }"
            )
            self.lbl_found_summary.setStyleSheet("color: #2C2A29; font-size: 13px;")
        else:
            tokens = theme_tokens(theme_id)
            self.status_card.setStyleSheet(
                f"QFrame {{ background-color: {tokens['panel_bg']}; border: 1px solid {tokens['border']}; border-radius: 8px; padding: 6px; }}"
            )
            self.lbl_progress_detail.setStyleSheet(f"color: {tokens['text']}; font-size: 12px; font-weight: 600;")
            self.lbl_badges.setStyleSheet(f"color: {tokens['text_muted']}; font-size: 11px;")
            self.empty_box.setStyleSheet(
                f"QFrame {{ background-color: {tokens['panel_bg']}; border: 1px dashed {tokens['accent']}; border-radius: 10px; padding: 18px; }}"
            )
            self.lbl_found_summary.setStyleSheet(f"color: {tokens['text']}; font-size: 13px;")
        if self.session:
            self._highlight_card(self._active_field_name)

    def bind_session(self, session: FormDocumentSession | None):
        self.session = session
        self.rebuild_fields()

    def rebuild_fields(self):
        self._syncing_ui = True
        try:
            while self.form_layout.count():
                item = self.form_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._field_cards.clear()
            self._field_editors.clear()
            self._focus_filters.clear()

            if not self.session:
                self.lbl_found_summary.setText("<b>PDF 문서를 먼저 열어주세요.</b>")
                self.empty_box.setVisible(False)
                self.status_card.setVisible(False)
                self.btn_save_filled.setEnabled(False)
                return

            fields = self.session.list_logical_fields()
            editable_fields = [lf for lf in fields if lf.editable]
            readonly_fields = [lf for lf in fields if not lf.editable]

            self.lbl_found_summary.setText(
                f"<b>이 문서에서 입력 가능한 항목 {len(editable_fields)}개를 찾았습니다.</b>"
            )
            has_any = len(fields) > 0
            self.empty_box.setVisible(not has_any)
            self.status_card.setVisible(has_any)
            self.scroll.setVisible(has_any)
            self.btn_save_filled.setEnabled(has_any)

            if not has_any:
                return

            # 계층형 필드 그룹화 (점 구분 필드명 기준)
            from collections import defaultdict
            groups: dict[str, list] = defaultdict(list)
            ungrouped = []
            for lf in editable_fields:
                parent = lf.parent_group
                if parent:
                    groups[parent].append(lf)
                else:
                    ungrouped.append(lf)

            def _add_card(lf):
                card = self._create_field_card(lf, read_only_mode=False)
                self._field_cards[lf.field_name] = card
                self.form_layout.addWidget(card)

            for group_name in sorted(groups.keys()):
                header = QLabel(f"<b style='color:#1F4E79;'>▸ {group_name} 정보</b>")
                header.setStyleSheet("margin-top: 10px; margin-bottom: 4px;")
                self.form_layout.addWidget(header)
                for lf in groups[group_name]:
                    _add_card(lf)

            for lf in ungrouped:
                _add_card(lf)

            if readonly_fields:
                ro_header = QLabel("<b>읽기 전용 / 서명 항목</b>")
                ro_header.setStyleSheet("color: #6B6560; margin-top: 8px;")
                self.form_layout.addWidget(ro_header)
                for lf in readonly_fields:
                    card = self._create_field_card(lf, read_only_mode=True)
                    self._field_cards[lf.field_name] = card
                    self.form_layout.addWidget(card)

            self.form_layout.addStretch(1)
            self.update_completion_status()
            if self._active_field_name:
                self._highlight_card(self._active_field_name)
        finally:
            self._syncing_ui = False

    def _install_focus_tracker(self, widget: QWidget, lf: LogicalField):
        flt = _FocusFilter(widget)
        primary_xref = lf.primary_widget.xref if lf.primary_widget else 0
        flt.focused.connect(lambda fn=lf.field_name, xr=primary_xref: self._on_editor_focused(fn, xr))
        widget.installEventFilter(flt)
        self._focus_filters.append(flt)

    def _create_field_card(self, lf: LogicalField, read_only_mode: bool = False) -> QFrame:
        card = QFrame()
        card.setProperty("fieldName", lf.field_name)
        self._apply_card_style(card, selected=False, required_missing=(lf.required and not lf.is_filled()))
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(5)

        head = QHBoxLayout()
        req_mark = " <span style='color:#C2410C; font-weight:700;'>*필수</span>" if lf.required else ""
        if lf.is_shared_value:
            locs = ", ".join(f"{w.page_index+1}p" for w in lf.widgets)
            multi_loc = f" · 동일한 값 사용 ({len(lf.widgets)}곳: {locs})"
        elif len(lf.widgets) > 1 and lf.field_type == "radio":
            multi_loc = f" · 라디오 그룹 ({len(lf.widgets)}개 선택지)"
        else:
            multi_loc = ""
        title_lbl = QLabel(
            f"<b>{lf.display_name}</b>{req_mark} "
            f"<span style='color:#777; font-size:11px;'>({lf.type_label} · {lf.primary_page}p{multi_loc})</span>"
        )
        head.addWidget(title_lbl, 1)
        lay.addLayout(head)

        if read_only_mode:
            ro_text = "전자서명 완료" if lf.is_signed else (str(lf.value or "(비어 있음)"))
            lbl_ro = QLabel(f"값: {ro_text}")
            lbl_ro.setStyleSheet("color: #555; background: #EFECE8; padding: 4px 6px; border-radius: 4px;")
            self._install_focus_tracker(card, lf)
            lay.addWidget(lbl_ro)
            return card

        if lf.field_type in ("text", "date"):
            ed = QLineEdit(str(lf.value or ""))
            if lf.max_len > 0:
                ed.setMaxLength(lf.max_len)
            if lf.field_type == "date":
                ed.setPlaceholderText("YYYY-MM-DD (예: 2026-05-01)")
            else:
                ed.setPlaceholderText(f"{lf.display_name} 입력")
            ed.editingFinished.connect(lambda fn=lf.field_name, w=ed: self._commit_line_edit(fn, w))
            self._install_focus_tracker(ed, lf)
            self._field_editors[lf.field_name] = ed
            lay.addWidget(ed)

        elif lf.field_type == "multiline":
            te = QTextEdit()
            te.setPlainText(str(lf.value or ""))
            te.setFixedHeight(72)
            te.setPlaceholderText(f"{lf.display_name} 입력 (여러 줄 가능)")
            timer = QTimer(te)
            timer.setSingleShot(True)
            timer.setInterval(400)
            timer.timeout.connect(lambda fn=lf.field_name, w=te: self._commit_text_edit(fn, w))
            te.textChanged.connect(lambda t=timer: None if self._syncing_ui else t.start())
            self._install_focus_tracker(te, lf)
            self._field_editors[lf.field_name] = te
            lay.addWidget(te)

        elif lf.field_type == "checkbox":
            cb = QCheckBox(f"{lf.display_name} 선택")
            cb.setChecked(bool(lf.value))
            cb.toggled.connect(lambda checked, fn=lf.field_name: self._commit_value(fn, checked))
            self._install_focus_tracker(cb, lf)
            self._field_editors[lf.field_name] = cb
            lay.addWidget(cb)

        elif lf.field_type == "radio":
            host = QWidget()
            rlay = QHBoxLayout(host)
            rlay.setContentsMargins(0, 0, 0, 0)
            rlay.setSpacing(12)
            bgroup = QButtonGroup(host)
            for opt in lf.radio_options:
                rb = QRadioButton(opt)
                rb.setChecked(str(lf.value or "") == opt)
                rb.toggled.connect(
                    lambda checked, fn=lf.field_name, val=opt: self._commit_value(fn, val) if checked else None
                )
                self._install_focus_tracker(rb, lf)
                bgroup.addButton(rb)
                rlay.addWidget(rb)
            rlay.addStretch(1)
            self._field_editors[lf.field_name] = host
            lay.addWidget(host)

        elif lf.field_type == "combobox":
            combo = QComboBox()
            for ch in lf.choices:
                combo.addItem(ch)
            if str(lf.value or "") in lf.choices:
                combo.setCurrentText(str(lf.value))
            combo.currentTextChanged.connect(lambda val, fn=lf.field_name: self._commit_value(fn, val))
            self._install_focus_tracker(combo, lf)
            self._field_editors[lf.field_name] = combo
            lay.addWidget(combo)

        elif lf.field_type == "listbox":
            lw = QListWidget()
            lw.setMaximumHeight(80)
            for i, ch in enumerate(lf.choices):
                lw.addItem(ch)
                if ch == str(lf.value or ""):
                    lw.setCurrentRow(i)
            lw.currentTextChanged.connect(lambda val, fn=lf.field_name: self._commit_value(fn, val))
            self._install_focus_tracker(lw, lf)
            self._field_editors[lf.field_name] = lw
            lay.addWidget(lw)

        self._install_focus_tracker(card, lf)
        return card

    @staticmethod
    def _apply_card_style(card: QFrame, selected: bool, required_missing: bool):
        from app.services import app_settings
        from app.shell.theme import THEMES, theme_tokens

        theme_id = app_settings.get("ui/theme")
        if theme_id not in THEMES or theme_id == "default":
            if selected:
                border = "2px solid #A63F2B"
                bg = "#FFF8F4"
            elif required_missing:
                border = "1px solid #E07A5F"
                bg = "#FFFDFB"
            else:
                border = "1px solid #DFDAD4"
                bg = "#FFFFFF"
        else:
            tokens = theme_tokens(theme_id)
            if selected:
                border = f"2px solid {tokens['accent']}"
                bg = tokens["selected"]
            elif required_missing:
                border = f"1px solid {tokens['accent']}"
                bg = tokens["warning_bg"]
            else:
                border = f"1px solid {tokens['border']}"
                bg = tokens["panel_bg"]
        card.setStyleSheet(f"QFrame {{ background-color: {bg}; border: {border}; border-radius: 8px; }}")

    def _on_editor_focused(self, field_name: str, primary_xref: int):
        if self._syncing_ui:
            return
        self._active_field_name = field_name
        self._highlight_card(field_name)
        self.field_selected.emit(field_name, primary_xref)

    def select_field_from_canvas(self, field_name: str):
        self._active_field_name = field_name
        self._highlight_card(field_name)
        card = self._field_cards.get(field_name)
        if card is not None:
            self.scroll.ensureWidgetVisible(card, 20, 40)
        editor = self._field_editors.get(field_name)
        if editor is not None and not editor.hasFocus():
            self._syncing_ui = True
            try:
                editor.setFocus()
            finally:
                self._syncing_ui = False

    def _highlight_card(self, active_name: str):
        if not self.session:
            return
        fields_map = {lf.field_name: lf for lf in self.session.list_logical_fields()}
        for fname, card in self._field_cards.items():
            lf = fields_map.get(fname)
            req_missing = bool(lf and lf.required and not lf.is_filled())
            self._apply_card_style(card, selected=(fname == active_name), required_missing=req_missing)

    def _commit_line_edit(self, field_name: str, line_edit: QLineEdit):
        if self._syncing_ui or not self.session:
            return
        lf = self.session.get_logical_field(field_name)
        if lf is None:
            return
        new_text = line_edit.text().strip()
        if str(lf.value or "") == new_text:
            return
        if lf.field_type == "date" and new_text:
            ok, normalized = validate_date_string(new_text)
            if not ok:
                QMessageBox.warning(self, "날짜 형식 확인", normalized)
                self._syncing_ui = True
                line_edit.setText(str(lf.value or ""))
                self._syncing_ui = False
                return
            new_text = normalized
            self._syncing_ui = True
            line_edit.setText(new_text)
            self._syncing_ui = False
        self._commit_value(field_name, new_text)

    def _commit_text_edit(self, field_name: str, text_edit: QTextEdit):
        if self._syncing_ui or not self.session:
            return
        lf = self.session.get_logical_field(field_name)
        if lf is None:
            return
        new_text = text_edit.toPlainText()
        if str(lf.value or "") == new_text:
            return
        self._commit_value(field_name, new_text)

    def _commit_value(self, field_name: str, value: object):
        if self._syncing_ui or not self.session:
            return
        try:
            self.session.set_field_value(field_name, value)
            self.update_completion_status()
            self._highlight_card(self._active_field_name)
            self.value_committed.emit(field_name)
        except FormError as exc:
            QMessageBox.warning(self, "양식 입력", str(exc))
            self.rebuild_fields()

    def update_completion_status(self):
        if not self.session:
            return
        fields = self.session.list_logical_fields()
        editable = [lf for lf in fields if lf.editable]
        readonly_count = len(fields) - len(editable)
        required_fields = [lf for lf in editable if lf.required]
        req_done = sum(1 for lf in required_fields if lf.is_filled())
        total_done = sum(1 for lf in editable if lf.is_filled())
        total_unfilled = len(editable) - total_done
        req_missing = len(required_fields) - req_done

        if required_fields:
            self.lbl_progress_detail.setText(
                f"필수 항목 {len(required_fields)}개 중 {req_done}개 작성 "
                f"(전체 입력 항목 {len(editable)}개 중 {total_done}개 완료)"
            )
            pct = round((req_done / len(required_fields)) * 100)
        else:
            self.lbl_progress_detail.setText(
                f"전체 입력 항목 {len(editable)}개 중 {total_done}개 작성 (필수 지정 항목 없음)"
            )
            pct = round((total_done / max(1, len(editable))) * 100)
        self.progress_bar.setValue(pct)
        self.lbl_badges.setText(
            f"작성 완료 {total_done} · 미작성 {total_unfilled} · 필수 미작성 {req_missing} · 읽기 전용 {readonly_count}"
        )
