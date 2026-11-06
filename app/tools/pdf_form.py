from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QDragEnterEvent, QDropEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.common.styles import COLOR_BORDER, COLOR_PRIMARY, MODERN_QSS
from app.services import app_settings
from app.shell.theme import THEMES, build_shell_qss, theme_tokens, tool_table_qss
from app.common.pdf_form.field_models import (
    FIELD_TYPE_LABELS,
    FormError,
    ImportAnalysis,
)
from app.common.pdf_form.form_canvas import PdfFormViewerPane
from app.common.pdf_form.form_creator import FormCreatorPanel
from app.common.pdf_form.form_data_io import (
    analyze_import_data,
    apply_import_analysis,
    build_extraction_rows,
    collect_fields_from_multiple_pdfs,
    export_collected_rows_to_csv,
    export_fields_to_csv,
    export_fields_to_json,
    export_template_csv,
    load_external_data_file,
)
from app.common.pdf_form.form_filler import FormFillerPanel
from app.common.pdf_file_open import open_pdf_dialog, try_open_pdf, show_open_error
from app.common.pdf_form.form_service import (
    FormDocumentSession,
    ensure_sample_form_pdf,
)


STATUS_LABELS_KO = {
    "matched": ("정상 매칭", "#15803D"),
    "unmatched_data": ("매칭되지 않음", "#B45309"),
    "read_only": ("읽기 전용", "#6B7280"),
    "unsupported_type": ("지원 안 함", "#6B7280"),
    "invalid_format": ("값 형식 오류", "#B91C1C"),
    "invalid_choice": ("선택지 없음", "#B91C1C"),
}


class PdfFormWidget(QWidget):
    """사이드바 「PDF 입력폼 관리」 통합 도구 — 양식 만들기 | 양식 작성하기 | 데이터 추출·입력."""

    def __init__(self, parent=None, comparison_settings=None):
        super().__init__(parent)
        self.comparison_settings = comparison_settings
        self.setStyleSheet(MODERN_QSS + build_shell_qss(app_settings.get('ui/theme')))
        self.setAcceptDrops(True)

        self.session: FormDocumentSession | None = None
        self.selected_xref: int = 0
        self._imported_data: dict[str, object] = {}
        self._manual_mapping: dict[str, str | None] = {}
        self._current_analysis: ImportAnalysis | None = None
        self._step_cards: list[tuple[QFrame, QLabel, str, QLabel]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(8)

        # 1. 상단 제목 & 파일 정보 바
        self.top_header_bar = self._build_top_header()
        root.addWidget(self.top_header_bar)

        # 2. 제한/경고 배너 (XFA, 서명, 권한 제한 시 표시)
        self.banner_restriction = QLabel("")
        self.banner_restriction.setWordWrap(True)
        self.banner_restriction.setStyleSheet(
            "QLabel { background-color: #FEF3C7; color: #92400E; border: 1px solid #F59E0B; "
            "border-radius: 6px; padding: 6px 10px; font-weight: 600; }"
        )
        self.banner_restriction.setVisible(False)
        root.addWidget(self.banner_restriction)

        # 3. 시작 화면(Welcome) vs 메인 작업 화면(Workspace) 스택
        self.main_stack = QStackedWidget()
        self.welcome_view = self._build_welcome_view()
        self.workspace_view = self._build_workspace_view()
        self.main_stack.addWidget(self.welcome_view)
        self.main_stack.addWidget(self.workspace_view)
        root.addWidget(self.main_stack, 1)

        # 단축키: Ctrl+Z / Ctrl+Y
        sc_undo = QShortcut(QKeySequence.StandardKey.Undo, self)
        sc_undo.activated.connect(self.undo_action)
        sc_redo = QShortcut(QKeySequence.StandardKey.Redo, self)
        sc_redo.activated.connect(self.redo_action)

        # 메인 윈도우 집중모드 호환용 컨트롤
        self.btn_focus_mode = QPushButton(self)
        self.btn_focus_mode.setObjectName("secondaryBtn")
        self.btn_focus_mode.setFixedSize(40, 40)
        self.btn_focus_mode.setCheckable(True)
        self.btn_focus_mode.hide()

        self._style_file_table()
        self._update_top_info()

    def _style_file_table(self):
        theme_id = app_settings.get("ui/theme")
        self.setStyleSheet(MODERN_QSS + build_shell_qss(theme_id))
        table_qss = tool_table_qss(theme_id, selectable=True)
        for tbl in (
            getattr(self.creator_panel, "field_table", None) if hasattr(self, "creator_panel") else None,
            getattr(self, "extract_table", None),
            getattr(self, "import_table", None),
        ):
            if tbl is not None:
                tbl.setStyleSheet(table_qss)

        if theme_id not in THEMES or theme_id == "default":
            if hasattr(self, "top_header_bar"):
                self.top_header_bar.setStyleSheet(
                    "QFrame#formTopHeader { background-color: #FCFAF7; border: 1px solid #E5E0DA; border-radius: 10px; }"
                )
            if hasattr(self, "welcome_view"):
                self.welcome_view.setStyleSheet(
                    "QFrame#formWelcomeView { background-color: #FFFFFF; border: 1px solid #E5E0DA; border-radius: 12px; }"
                )
            if hasattr(self, "welcome_headline"):
                self.welcome_headline.setStyleSheet("font-size: 22px; font-weight: 700; color: #2C2A29; border: none;")
            if hasattr(self, "welcome_sub"):
                self.welcome_sub.setStyleSheet("font-size: 13px; color: #5C5652; border: none;")
            for card, t_lbl, step_title, d_lbl in self._step_cards:
                card.setStyleSheet(
                    "QFrame { background-color: #FAF8F5; border: 1px solid #E4DED7; border-radius: 10px; padding: 14px; }"
                )
                t_lbl.setText(f"<b style='font-size:14px; color:#A63F2B;'>{step_title}</b>")
                d_lbl.setStyleSheet("color: #4A4542; font-size: 12px; border: none;")
        else:
            tokens = theme_tokens(theme_id)
            if hasattr(self, "top_header_bar"):
                self.top_header_bar.setStyleSheet(
                    f"QFrame#formTopHeader {{ background-color: {tokens['panel_bg']}; border: 1px solid {tokens['border']}; border-radius: 10px; }}"
                )
            if hasattr(self, "welcome_view"):
                self.welcome_view.setStyleSheet(
                    f"QFrame#formWelcomeView {{ background-color: {tokens['panel_bg']}; border: 1px solid {tokens['border']}; border-radius: 12px; }}"
                )
            if hasattr(self, "welcome_headline"):
                self.welcome_headline.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {tokens['text']}; border: none;")
            if hasattr(self, "welcome_sub"):
                self.welcome_sub.setStyleSheet(f"font-size: 13px; color: {tokens['text_muted']}; border: none;")
            for card, t_lbl, step_title, d_lbl in self._step_cards:
                card.setStyleSheet(
                    f"QFrame {{ background-color: {tokens['app_bg']}; border: 1px solid {tokens['border']}; border-radius: 10px; padding: 14px; }}"
                )
                t_lbl.setText(f"<b style='font-size:14px; color:{tokens['accent']};'>{step_title}</b>")
                d_lbl.setStyleSheet(f"color: {tokens['text']}; font-size: 12px; border: none;")

        if hasattr(self, "filler_panel"):
            self.filler_panel.apply_theme(theme_id)

    _style_table = _style_file_table

    def _build_top_header(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("formTopHeader")
        bar.setStyleSheet(
            "QFrame#formTopHeader { background-color: #FCFAF7; border: 1px solid #E5E0DA; border-radius: 10px; }"
        )
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)

        title_row = QHBoxLayout()
        lbl_title = QLabel(
            "<span style='font-size:15px; font-weight:700;'>PDF 입력폼 관리</span>  "
            "<span style='font-size:12px;'>"
            "일반 PDF에 입력란을 만들거나, 만들어진 양식을 작성하고 데이터를 관리할 수 있습니다.</span>"
        )
        lbl_title.setStyleSheet("border: none;")
        title_row.addWidget(lbl_title, 1)
        lay.addLayout(title_row)

        info_row = QHBoxLayout()
        info_row.setSpacing(8)
        self.btn_open_pdf = QPushButton("PDF 열기")
        self.btn_open_pdf.setObjectName("actionBtn")
        self.btn_open_pdf.clicked.connect(self.open_pdf_dialog)

        self.btn_open_sample = QPushButton("예제 양식 열기")
        self.btn_open_sample.setObjectName("secondaryBtn")
        self.btn_open_sample.clicked.connect(self.open_sample_form)

        self.lbl_file_name = QLabel("열린 파일 없음")
        self.lbl_file_name.setStyleSheet("font-weight: 600;")

        self.lbl_doc_stats = QLabel("페이지 - · 입력란 -")

        self.lbl_dirty_badge = QLabel("저장됨")
        self.lbl_dirty_badge.setStyleSheet(
            "color: #15803D; background: #DCFCE7; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 600;"
        )

        self.btn_top_undo = QPushButton("실행 취소")
        self.btn_top_undo.clicked.connect(self.undo_action)
        self.btn_top_redo = QPushButton("다시 실행")
        self.btn_top_redo.clicked.connect(self.redo_action)

        info_row.addWidget(self.btn_open_pdf)
        info_row.addWidget(self.btn_open_sample)
        info_row.addSpacing(6)
        info_row.addWidget(self.lbl_file_name)
        info_row.addWidget(self.lbl_doc_stats)
        info_row.addWidget(self.lbl_dirty_badge)
        info_row.addStretch(1)
        info_row.addWidget(self.btn_top_undo)
        info_row.addWidget(self.btn_top_redo)
        lay.addLayout(info_row)
        return bar

    def _build_welcome_view(self) -> QWidget:
        w = QFrame()
        w.setObjectName("formWelcomeView")
        w.setStyleSheet(
            "QFrame#formWelcomeView { background-color: #FFFFFF; border: 1px solid #E5E0DA; border-radius: 12px; }"
        )
        outer = QVBoxLayout(w)
        outer.setContentsMargins(36, 32, 36, 32)
        outer.setSpacing(18)
        outer.addStretch(1)

        headline = QLabel("PDF 입력폼 관리로 문서 작업을 더 간편하게")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        headline.setStyleSheet("font-size: 22px; font-weight: 700; color: #2C2A29; border: none;")
        self.welcome_headline = headline
        outer.addWidget(headline)

        sub = QLabel(
            "PDF에 이름, 날짜, 체크박스처럼 직접 입력할 수 있는 공간을 만들고,\n"
            "작성된 정보를 엑셀(CSV)이나 JSON 데이터로 손쉽게 주고받을 수 있습니다."
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("font-size: 13px; color: #5C5652; border: none;")
        self.welcome_sub = sub
        outer.addWidget(sub)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        steps = [
            ("① 양식 만들기", "일반 PDF 문서 위에서 마우스로 영역을 드래그해 한 줄 입력란, 날짜, 체크박스, 라디오 버튼, 드롭다운 목록을 추가합니다."),
            ("② 양식 작성하기", "준비된 PDF 입력폼의 입력란을 클릭하거나 오른쪽 입력 패널에서 편리하게 내용을 채우고 저장합니다."),
            ("③ 데이터 추출·입력", "입력된 내용을 엑셀(CSV)·JSON으로 내보내거나, 외부 데이터를 불러와 자동으로 채웁니다."),
        ]
        for step_title, step_desc in steps:
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background-color: #FAF8F5; border: 1px solid #E4DED7; border-radius: 10px; padding: 14px; }"
            )
            clay = QVBoxLayout(card)
            clay.setSpacing(6)
            t_lbl = QLabel(f"<b style='font-size:14px; color:#A63F2B;'>{step_title}</b>")
            t_lbl.setStyleSheet("border: none;")
            d_lbl = QLabel(step_desc)
            d_lbl.setWordWrap(True)
            d_lbl.setStyleSheet("color: #4A4542; font-size: 12px; border: none;")
            clay.addWidget(t_lbl)
            clay.addWidget(d_lbl)
            cards_row.addWidget(card, 1)
            self._step_cards.append((card, t_lbl, step_title, d_lbl))
        outer.addLayout(cards_row)

        btns_row = QHBoxLayout()
        btns_row.setSpacing(12)
        btns_row.addStretch(1)
        self.btn_welcome_open = QPushButton("PDF 파일 열기")
        self.btn_welcome_open.setObjectName("actionBtn")
        self.btn_welcome_open.setMinimumSize(170, 42)
        self.btn_welcome_open.clicked.connect(self.open_pdf_dialog)

        self.btn_welcome_sample = QPushButton("예제 양식으로 체험하기")
        self.btn_welcome_sample.setObjectName("secondaryBtn")
        self.btn_welcome_sample.setMinimumSize(190, 42)
        self.btn_welcome_sample.clicked.connect(self.open_sample_form)

        btns_row.addWidget(self.btn_welcome_open)
        btns_row.addWidget(self.btn_welcome_sample)
        btns_row.addStretch(1)
        outer.addLayout(btns_row)
        outer.addStretch(1)
        return w

    def _build_workspace_view(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.tabs = QTabWidget()

        # 탭 1 + 탭 2는 왼쪽 60% PDF 미리보기 + 오른쪽 40% 기능 패널 QSplitter 구조
        self.pdf_split_page = QWidget()
        split_lay = QHBoxLayout(self.pdf_split_page)
        split_lay.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        self.viewer_pane = PdfFormViewerPane()
        self.viewer_pane.canvas.widget_selected.connect(self._on_canvas_widget_selected)
        self.viewer_pane.canvas.rect_drawn.connect(self._on_canvas_rect_drawn)
        self.viewer_pane.canvas.widget_moved.connect(self._on_canvas_widget_moved)
        self.viewer_pane.canvas.widget_resized.connect(self._on_canvas_widget_resized)
        self.viewer_pane.canvas.delete_requested.connect(self._on_canvas_delete_requested)
        self.viewer_pane.canvas.escape_pressed.connect(self._on_canvas_escape)

        self.right_stack = QStackedWidget()
        self.creator_panel = FormCreatorPanel()
        self.creator_panel.tool_mode_changed.connect(self.viewer_pane.canvas.set_Creation_tool)
        self.creator_panel.widget_focus_requested.connect(self._focus_widget_by_xref)
        self.creator_panel.document_mutated.connect(self._on_document_mutated)
        self.creator_panel.save_form_requested.connect(lambda: self.save_current_pdf(bake=False))
        self.creator_panel.help_requested.connect(lambda: self.show_tab_help(0))

        self.filler_panel = FormFillerPanel()
        self.filler_panel.field_selected.connect(self._on_filler_field_selected)
        self.filler_panel.value_committed.connect(self._on_filler_value_committed)
        self.filler_panel.switch_to_creator_requested.connect(lambda: self.tabs.setCurrentIndex(0))
        self.filler_panel.save_filled_requested.connect(self.save_current_pdf)
        self.filler_panel.help_requested.connect(lambda: self.show_tab_help(1))

        self.right_stack.addWidget(self.creator_panel)
        self.right_stack.addWidget(self.filler_panel)

        self.splitter.addWidget(self.viewer_pane)
        self.splitter.addWidget(self.right_stack)
        self.splitter.setStretchFactor(0, 6)
        self.splitter.setStretchFactor(1, 4)
        self.splitter.setSizes([720, 480])
        split_lay.addWidget(self.splitter)

        self.data_tab_widget = self._build_data_io_tab()
        self.body_stack = QStackedWidget()
        self.body_stack.addWidget(self.pdf_split_page)
        self.body_stack.addWidget(self.data_tab_widget)

        self.tab_placeholder_0 = QWidget()
        self.tab_placeholder_1 = QWidget()
        self.tab_placeholder_2 = QWidget()
        self.tabs.addTab(self.tab_placeholder_0, "양식 만들기")
        self.tabs.addTab(self.tab_placeholder_1, "양식 작성하기")
        self.tabs.addTab(self.tab_placeholder_2, "데이터 추출·입력")
        self.tabs.tabBar().setExpanding(False)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # QTabWidget의 탭 바만 상단에 쓰고 아래에 body_stack 배치
        self.tabs.setMaximumHeight(36)
        lay.addWidget(self.tabs)
        lay.addWidget(self.body_stack, 1)
        return host

    def _build_data_io_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(10)

        top_row = QHBoxLayout()
        lbl_guide = QLabel(
            "<b>PDF 입력폼의 입력값을 엑셀(CSV)·JSON으로 추출하거나, 외부 데이터 파일을 가져와 자동으로 입력합니다.</b>"
        )
        btn_help = QPushButton("이 기능은 무엇인가요?")
        btn_help.setObjectName("secondaryBtn")
        btn_help.clicked.connect(lambda: self.show_tab_help(2))
        top_row.addWidget(lbl_guide, 1)
        top_row.addWidget(btn_help)
        lay.addLayout(top_row)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # 상단: 데이터 추출 섹션
        extract_group = QGroupBox("1. 데이터 추출 (현재 PDF 입력폼 값 확인 및 내보내기)")
        ex_lay = QVBoxLayout(extract_group)
        ex_lay.setSpacing(6)

        ex_btn_row = QHBoxLayout()
        self.lbl_extract_count = QLabel("추출 가능한 필드: 0개")
        self.chk_include_restricted = QCheckBox("읽기 전용·내보내기 제한 항목 포함")
        self.chk_include_restricted.toggled.connect(self.refresh_data_tab)
        self.btn_export_csv = QPushButton("CSV로 내보내기 (엑셀 호환)")
        self.btn_export_csv.setObjectName("actionBtn")
        self.btn_export_csv.clicked.connect(self.export_csv_dialog)
        self.btn_export_json = QPushButton("JSON으로 내보내기")
        self.btn_export_json.clicked.connect(self.export_json_dialog)
        self.btn_export_template = QPushButton("입력용 CSV 템플릿 저장")
        self.btn_export_template.setObjectName("secondaryBtn")
        self.btn_export_template.clicked.connect(self.export_template_dialog)
        self.btn_collect_multi = QPushButton("여러 PDF에서 데이터 모으기")
        self.btn_collect_multi.setObjectName("secondaryBtn")
        self.btn_collect_multi.setToolTip("동일한 양식으로 작성된 여러 PDF의 입력값을 하나의 표로 모읍니다.")
        self.btn_collect_multi.clicked.connect(self.collect_from_multiple_pdfs_dialog)

        ex_btn_row.addWidget(self.lbl_extract_count)
        ex_btn_row.addSpacing(12)
        ex_btn_row.addWidget(self.chk_include_restricted)
        ex_btn_row.addStretch(1)
        ex_btn_row.addWidget(self.btn_export_template)
        ex_btn_row.addWidget(self.btn_collect_multi)
        ex_btn_row.addWidget(self.btn_export_csv)
        ex_btn_row.addWidget(self.btn_export_json)
        ex_lay.addLayout(ex_btn_row)

        self.extract_table = QTableWidget(0, 7)
        self.extract_table.setHorizontalHeaderLabels(
            ["페이지", "표시 이름", "필드명", "유형", "현재 값", "필수", "읽기 전용"]
        )
        self.extract_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.extract_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.extract_table.verticalHeader().setVisible(False)
        self.extract_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.extract_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        ex_lay.addWidget(self.extract_table, 1)
        splitter.addWidget(extract_group)

        # 하단: 데이터 가져와 입력 섹션
        import_group = QGroupBox("2. 데이터 가져와 입력 (외부 CSV / JSON → PDF 자동 입력)")
        im_lay = QVBoxLayout(import_group)
        im_lay.setSpacing(6)

        im_top_row = QHBoxLayout()
        self.btn_load_data = QPushButton("CSV / JSON 데이터 가져오기")
        self.btn_load_data.setObjectName("actionBtn")
        self.btn_load_data.clicked.connect(self.import_data_dialog)

        self.lbl_import_summary = QLabel("가져온 데이터 파일이 없습니다. 먼저 [입력용 CSV 템플릿 저장]으로 양식을 받아 작성해보세요.")
        self.lbl_import_summary.setStyleSheet("color: #4A4542; font-weight: 600;")

        self.btn_apply_import = QPushButton("정상 매칭 항목 PDF에 적용")
        self.btn_apply_import.setObjectName("actionBtn")
        self.btn_apply_import.setEnabled(False)
        self.btn_apply_import.clicked.connect(self.apply_imported_data)

        self.btn_save_after_import = QPushButton("PDF 저장")
        self.btn_save_after_import.setObjectName("secondaryBtn")
        self.btn_save_after_import.clicked.connect(lambda: self.save_current_pdf(bake=False))

        im_top_row.addWidget(self.btn_load_data)
        im_top_row.addWidget(self.lbl_import_summary, 1)
        im_top_row.addWidget(self.btn_apply_import)
        im_top_row.addWidget(self.btn_save_after_import)
        im_lay.addLayout(im_top_row)

        self.import_table = QTableWidget(0, 5)
        self.import_table.setHorizontalHeaderLabels(
            ["외부 데이터 키", "가져온 값", "연결할 PDF 필드 (수동 변경 가능)", "검증 상태", "상세 설명"]
        )
        self.import_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.import_table.verticalHeader().setVisible(False)
        self.import_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.import_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.import_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        im_lay.addWidget(self.import_table, 1)
        splitter.addWidget(import_group)

        lay.addWidget(splitter, 1)
        return w

    def _on_tab_changed(self, index: int):
        if index in (0, 1):
            self.body_stack.setCurrentWidget(self.pdf_split_page)
            self.right_stack.setCurrentIndex(index)
            self.viewer_pane.canvas.mode = "create" if index == 0 else "fill"
            self.viewer_pane.refresh_view()
            if index == 0:
                self.creator_panel.refresh_panel(self.selected_xref)
            else:
                self.filler_panel.rebuild_fields()
        else:
            self.body_stack.setCurrentWidget(self.data_tab_widget)
            self.refresh_data_tab()

    def _update_top_info(self):
        has_doc = self.session is not None
        self.main_stack.setCurrentIndex(1 if has_doc else 0)
        self.btn_top_undo.setEnabled(bool(self.session and self.session.can_undo))
        self.btn_top_redo.setEnabled(bool(self.session and self.session.can_redo))

        if not self.session:
            self.lbl_file_name.setText("열린 파일 없음")
            self.lbl_doc_stats.setText("페이지 - · 입력란 -")
            self.lbl_dirty_badge.setText("대기 중")
            self.banner_restriction.setVisible(False)
            return

        widgets = self.session.list_widgets()
        logical = self.session.list_logical_fields()
        self.lbl_file_name.setText(self.session.source_path.name)
        self.lbl_doc_stats.setText(
            f"페이지 {self.session.page_count}p · 입력 항목 {len(logical)}개 (입력란 {len(widgets)}개)"
        )
        if self.session.dirty:
            self.lbl_dirty_badge.setText("저장되지 않은 변경사항 있음")
            self.lbl_dirty_badge.setStyleSheet(
                "color: #B45309; background: #FEF3C7; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 600;"
            )
        else:
            self.lbl_dirty_badge.setText("저장됨")
            self.lbl_dirty_badge.setStyleSheet(
                "color: #15803D; background: #DCFCE7; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 600;"
            )

        msg = self.session.restriction_message()
        self.banner_restriction.setText(msg)
        self.banner_restriction.setVisible(bool(msg))

    def confirm_discard_changes(self) -> bool:
        if not self.session or not self.session.dirty:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("저장되지 않은 변경사항")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(
            f"'{self.session.source_path.name}'에 저장하지 않은 양식/입력 변경사항이 있습니다.\n"
            "저장하지 않고 계속하시겠습니까?"
        )
        btn_save = box.addButton("저장 후 진행", QMessageBox.ButtonRole.AcceptRole)
        btn_discard = box.addButton("저장하지 않음", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_save)
        box.exec()
        clicked = box.clickedButton()
        if clicked == btn_cancel:
            return False
        if clicked == btn_save:
            return self.save_current_pdf(bake=False)
        return clicked == btn_discard

    def open_pdf_dialog(self):
        if not self.confirm_discard_changes():
            return
        paths = open_pdf_dialog(self, "PDF 파일 열기", multi=False)
        path = paths[0] if paths else ""
        if path:
            self.load_pdf(path)

    def open_sample_form(self):
        if not self.confirm_discard_changes():
            return
        try:
            sample_path = ensure_sample_form_pdf()
            self.load_pdf(str(sample_path), prefer_tab=1)
        except Exception as exc:
            QMessageBox.warning(self, "예제 양식 열기", f"예제 양식을 준비할 수 없습니다:\n{exc}")

    def load_pdf(self, path: str | Path, prefer_tab: int | None = None) -> bool:
        password = ""
        for _attempt in range(3):
            try:
                new_session = FormDocumentSession(path, password=password)
                break
            except FormError as exc:
                if "암호" in str(exc):
                    pw, ok = QInputDialog.getText(
                        self, "암호화 PDF 열기", "이 PDF는 암호로 보호되어 있습니다. 암호를 입력하세요:",
                        QLineEdit.EchoMode.Password,
                    )
                    if ok and pw:
                        password = pw
                        continue
                    return False
                QMessageBox.warning(self, "PDF 열기", str(exc))
                return False
        else:
            return False

        if self.session is not None:
            self.session.close()
        self.session = new_session
        self.selected_xref = 0
        self._imported_data.clear()
        self._manual_mapping.clear()
        self._current_analysis = None

        self.viewer_pane.bind_session(self.session, 0)
        self.creator_panel.bind_session(self.session, 0)
        self.filler_panel.bind_session(self.session)
        self.refresh_data_tab()
        self._update_top_info()

        if prefer_tab is not None:
            self.tabs.setCurrentIndex(prefer_tab)
        else:
            has_fields = len(self.session.list_logical_fields()) > 0
            self.tabs.setCurrentIndex(1 if has_fields else 0)
        self._on_tab_changed(self.tabs.currentIndex())
        return True

    def _on_canvas_widget_selected(self, xref: int):
        self.selected_xref = xref
        if not self.session:
            return
        w = self.session.get_widget_by_xref(xref) if xref else None
        self.viewer_pane.canvas.highlighted_field_name = w.field_name if w else ""
        self.viewer_pane.canvas.update()
        if self.tabs.currentIndex() == 0:
            self.creator_panel.refresh_panel(xref)
        elif self.tabs.currentIndex() == 1 and w is not None:
            self.filler_panel.select_field_from_canvas(w.field_name)

    def _on_canvas_rect_drawn(self, page_index: int, pdf_rect: tuple[float, float, float, float]):
        if not self.session:
            return
        tool_type = self.viewer_pane.canvas.creation_tool or "text"
        try:
            default_label = FIELD_TYPE_LABELS.get(tool_type, "입력란")
            created = self.session.add_field(
                page_index,
                pdf_rect,
                field_type=tool_type,
                field_label=default_label,
            )
            self.selected_xref = created.xref
            self.creator_panel.reset_to_select_mode()
            self._sync_all_views(selected_xref=created.xref)
        except FormError as exc:
            QMessageBox.warning(self, "입력란 추가", str(exc))

    def _on_canvas_widget_moved(self, xref: int, pdf_rect: tuple[float, float, float, float]):
        if not self.session:
            return
        try:
            updated = self.session.update_widget_properties(xref, rect=pdf_rect)
            self._sync_all_views(selected_xref=updated.xref)
        except FormError as exc:
            QMessageBox.warning(self, "입력란 이동", str(exc))

    def _on_canvas_widget_resized(self, xref: int, pdf_rect: tuple[float, float, float, float]):
        if not self.session:
            return
        try:
            updated = self.session.update_widget_properties(xref, rect=pdf_rect)
            self._sync_all_views(selected_xref=updated.xref)
        except FormError as exc:
            QMessageBox.warning(self, "입력란 크기 변경", str(exc))

    def _on_canvas_delete_requested(self, xref: int):
        self.selected_xref = xref
        self.creator_panel.current_xref = xref
        self.creator_panel.delete_selected_widget()

    def _on_canvas_escape(self):
        self.selected_xref = 0
        self.viewer_pane.canvas.selected_xref = 0
        self.viewer_pane.canvas.highlighted_field_name = ""
        self.creator_panel.reset_to_select_mode()
        self.creator_panel.refresh_panel(0)

    def _focus_widget_by_xref(self, xref: int):
        if not self.session:
            return
        w = self.session.get_widget_by_xref(xref)
        if w is None:
            return
        self.selected_xref = xref
        self.viewer_pane.canvas.selected_xref = xref
        self.viewer_pane.canvas.highlighted_field_name = w.field_name
        self.viewer_pane.ensure_widget_visible(w)
        self.viewer_pane.canvas.update()

    def _on_filler_field_selected(self, field_name: str, primary_xref: int):
        if not self.session:
            return
        self.selected_xref = primary_xref
        self.viewer_pane.canvas.selected_xref = primary_xref
        self.viewer_pane.canvas.highlighted_field_name = field_name
        w = self.session.get_widget_by_xref(primary_xref) if primary_xref else None
        if w is not None:
            self.viewer_pane.ensure_widget_visible(w)
        self.viewer_pane.canvas.update()

    def _on_filler_value_committed(self, field_name: str):
        self.viewer_pane.refresh_view()
        self.viewer_pane.canvas.highlighted_field_name = field_name
        self.creator_panel.refresh_panel(self.selected_xref)
        self.refresh_data_tab()
        self._update_top_info()

    def _on_document_mutated(self, selected_xref: int):
        self._sync_all_views(selected_xref=selected_xref)

    def _sync_all_views(self, selected_xref: int = 0):
        self.selected_xref = selected_xref
        self.viewer_pane.canvas.selected_xref = selected_xref
        self.viewer_pane.refresh_view()
        self.creator_panel.refresh_panel(selected_xref)
        self.filler_panel.rebuild_fields()
        self.refresh_data_tab()
        self._update_top_info()

    def undo_action(self):
        if self.session and self.session.undo():
            self._sync_all_views(0)

    def redo_action(self):
        if self.session and self.session.redo():
            self._sync_all_views(0)

    def save_current_pdf(self, bake: bool = False) -> bool:
        if not self.session:
            return False
        if bake:
            box = QMessageBox(self)
            box.setWindowTitle("입력 내용 고정 저장 안내")
            box.setIcon(QMessageBox.Icon.Warning)
            box.setText(
                "입력 내용이 문서에 고정되며, 저장 후에는 양식 입력란으로 다시 수정하거나 추출할 수 없습니다.\n"
                "(현재 열려 있는 작업 화면의 양식은 그대로 유지됩니다.)\n\n"
                "고정된 PDF를 별도 파일로 저장하시겠습니까?"
            )
            btn_ok = box.addButton("고정본 저장", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(btn_ok)
            box.exec()
            if box.clickedButton() != btn_ok:
                return False

        suffix = "_고정본.pdf" if bake else "_양식저장.pdf"
        default_path = self.session.source_path.with_name(self.session.source_path.stem + suffix)
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "입력 내용 고정 PDF 저장" if bake else "PDF 입력폼 저장",
            str(default_path),
            "PDF 파일 (*.pdf)",
        )
        if not save_path:
            return False

        try:
            if bake:
                saved = self.session.save_baked_pdf(save_path)
            else:
                saved = self.session.save_form_pdf(save_path)
            self._update_top_info()
            QMessageBox.information(self, "저장 완료", f"PDF 파일이 저장되었습니다:\n{saved}")
            return True
        except FormError as exc:
            QMessageBox.warning(self, "저장 실패", str(exc))
            return False

    # ── 탭 3: 데이터 추출·입력 ─────────────────────────────────────────
    def refresh_data_tab(self):
        self.extract_table.setRowCount(0)
        if not self.session:
            self.lbl_extract_count.setText("추출 가능한 필드: 0개")
            self.btn_export_csv.setEnabled(False)
            self.btn_export_json.setEnabled(False)
            self.btn_export_template.setEnabled(False)
            self.btn_load_data.setEnabled(False)
            return

        rows = build_extraction_rows(
            self.session, include_restricted=self.chk_include_restricted.isChecked()
        )
        self.lbl_extract_count.setText(f"추출 가능한 논리 필드: {len(rows)}개")
        has_rows = len(rows) > 0
        self.btn_export_csv.setEnabled(has_rows)
        self.btn_export_json.setEnabled(has_rows)
        self.btn_export_template.setEnabled(has_rows)
        self.btn_load_data.setEnabled(has_rows)

        for r_idx, row in enumerate(rows):
            self.extract_table.insertRow(r_idx)
            loc_suffix = f" ({row['widget_count']}곳)" if int(row["widget_count"]) > 1 else ""
            cells = [
                f"{row['page']}p{loc_suffix}",
                str(row["field_label"]),
                str(row["field_name"]),
                str(row["type_label"]),
                str(row["value"]),
                "필수" if row["required"] else "-",
                "읽기 전용" if row["read_only"] else "입력 가능",
            ]
            for c_idx, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c_idx in (0, 5, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.extract_table.setItem(r_idx, c_idx, item)

        if self._imported_data:
            self._rebuild_import_preview()

    def export_csv_dialog(self):
        if not self.session:
            return
        default = self.session.source_path.with_name(self.session.source_path.stem + "_데이터.csv")
        path, _ = QFileDialog.getSaveFileName(self, "CSV로 데이터 내보내기", str(default), "CSV 파일 (*.csv)")
        if not path:
            return
        try:
            saved = export_fields_to_csv(
                self.session, path, include_restricted=self.chk_include_restricted.isChecked()
            )
            QMessageBox.information(self, "CSV 내보내기 완료", f"CSV 파일로 저장했습니다:\n{saved}")
        except FormError as exc:
            QMessageBox.warning(self, "CSV 내보내기 오류", str(exc))

    def export_json_dialog(self):
        if not self.session:
            return
        default = self.session.source_path.with_name(self.session.source_path.stem + "_데이터.json")
        path, _ = QFileDialog.getSaveFileName(self, "JSON으로 데이터 내보내기", str(default), "JSON 파일 (*.json)")
        if not path:
            return
        try:
            saved = export_fields_to_json(
                self.session, path, include_restricted=self.chk_include_restricted.isChecked()
            )
            QMessageBox.information(self, "JSON 내보내기 완료", f"JSON 파일로 저장했습니다:\n{saved}")
        except FormError as exc:
            QMessageBox.warning(self, "JSON 내보내기 오류", str(exc))

    def export_template_dialog(self):
        if not self.session:
            return
        default = self.session.source_path.with_name(self.session.source_path.stem + "_입력템플릿.csv")
        path, _ = QFileDialog.getSaveFileName(self, "입력용 CSV 템플릿 저장", str(default), "CSV 파일 (*.csv)")
        if not path:
            return
        try:
            saved = export_template_csv(self.session, path)
            QMessageBox.information(
                self,
                "템플릿 저장 완료",
                f"입력용 CSV 템플릿을 저장했습니다:\n{saved}\n\n"
                "엑셀에서 value 열에 값을 입력한 뒤 [CSV / JSON 데이터 가져오기]로 불러오면 자동 매칭됩니다.",
            )
        except FormError as exc:
            QMessageBox.warning(self, "템플릿 저장 오류", str(exc))

    def import_data_dialog(self):
        if not self.session:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "외부 데이터 파일 불러오기", "", "데이터 파일 (*.csv *.json);;CSV 파일 (*.csv);;JSON 파일 (*.json)"
        )
        if not path:
            return
        self.load_import_file(path)

    def load_import_file(self, path: str | Path) -> bool:
        if not self.session:
            return False
        try:
            self._imported_data = load_external_data_file(path)
            self._manual_mapping.clear()
            self._rebuild_import_preview()
            return True
        except FormError as exc:
            QMessageBox.warning(self, "데이터 가져오기 오류", str(exc))
            return False

    def _rebuild_import_preview(self):
        if not self.session or not self._imported_data:
            self.import_table.setRowCount(0)
            self.btn_apply_import.setEnabled(False)
            return

        analysis = analyze_import_data(self.session, self._imported_data, self._manual_mapping)
        self._current_analysis = analysis
        pdf_fields = self.session.list_logical_fields()

        total = len(analysis.items)
        n_ok = analysis.count_by_status("matched")
        n_unmatched = analysis.count_by_status("unmatched_data")
        n_ro = analysis.count_by_status("read_only") + analysis.count_by_status("unsupported_type")
        n_err = analysis.count_by_status("invalid_format") + analysis.count_by_status("invalid_choice")
        n_missing = len(analysis.missing_pdf_fields)

        self.lbl_import_summary.setText(
            f"총 {total}개 항목 — 정상 매칭: {n_ok}개 · 매칭 실패: {n_unmatched}개 · "
            f"읽기 전용/제외: {n_ro}개 · 값 오류: {n_err}개 (PDF 미포함 필드: {n_missing}개)"
        )
        self.btn_apply_import.setEnabled(n_ok > 0)

        self.import_table.setRowCount(0)
        for row_idx, item in enumerate(analysis.items):
            self.import_table.insertRow(row_idx)
            self.import_table.setItem(row_idx, 0, QTableWidgetItem(str(item.source_key)))
            self.import_table.setItem(row_idx, 1, QTableWidgetItem(str(item.raw_value)))

            combo = QComboBox()
            combo.addItem("(연결 안 함)", None)
            for lf in pdf_fields:
                combo.addItem(f"{lf.display_name} ({lf.field_name})", lf.field_name)
            if item.target_field_name:
                idx = combo.findData(item.target_field_name)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.currentIndexChanged.connect(
                lambda _i, sk=item.source_key, cb=combo: self._on_manual_mapping_changed(sk, cb.currentData())
            )
            self.import_table.setCellWidget(row_idx, 2, combo)

            status_label, color_hex = STATUS_LABELS_KO.get(item.status, (item.status, "#333333"))
            st_item = QTableWidgetItem(status_label)
            st_item.setForeground(QColor(color_hex))
            st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.import_table.setItem(row_idx, 3, st_item)
            self.import_table.setItem(row_idx, 4, QTableWidgetItem(item.reason))

    def _on_manual_mapping_changed(self, source_key: str, target_field_name: str | None):
        self._manual_mapping[source_key] = target_field_name
        self._rebuild_import_preview()

    def apply_imported_data(self):
        if not self.session or not self._current_analysis:
            return
        try:
            applied_count, skipped = apply_import_analysis(self.session, self._current_analysis)
            self._sync_all_views(self.selected_xref)
            self._rebuild_import_preview()
            msg_lines = [f"정상 매칭된 {applied_count}개 항목을 PDF 입력폼에 반영했습니다."]
            if skipped:
                msg_lines.append(f"\n제외/실패 항목 ({len(skipped)}개):")
                for s in skipped[:8]:
                    msg_lines.append(f" - {s.source_key}: {s.reason}")
            msg_lines.append("\n[양식 작성하기] 탭에서 반영된 화면을 확인하고 저장할 수 있습니다.")
            QMessageBox.information(self, "데이터 자동 입력 결과", "\n".join(msg_lines))
        except FormError as exc:
            QMessageBox.warning(self, "데이터 적용 오류", str(exc))

    def show_tab_help(self, tab_index: int):
        helps = {
            0: (
                "양식 만들기 안내",
                "<b>① 양식 만들기란?</b><br>"
                "일반 PDF 문서 위에 사용자가 직접 글자를 입력하거나 체크할 수 있는 <b>입력란</b>을 만드는 기능입니다.<br><br>"
                "<b>사용 순서</b><br>"
                "1. 오른쪽에서 추가할 입력란 종류(한 줄 입력란, 체크박스, 드롭다운 등)를 선택합니다.<br>"
                "2. 왼쪽 PDF 화면에서 마우스로 원하는 위치를 드래그하면 입력란이 만들어집니다.<br>"
                "3. 오른쪽 속성 창에서 표시 이름, 필수 여부, 선택 항목을 수정하고 <b>[입력 가능한 PDF 입력폼 저장]</b>을 누릅니다.",
            ),
            1: (
                "양식 작성하기 안내",
                "<b>② 양식 작성하기란?</b><br>"
                "이미 입력란이 만들어진 PDF 입력폼에 내용을 채워 넣는 기능입니다.<br><br>"
                "<b>사용 팁</b><br>"
                "• 왼쪽 PDF의 파란색 입력란을 클릭하면 오른쪽 입력 칸으로 바로 이동합니다.<br>"
                "• 반대로 오른쪽 입력 칸을 클릭하면 PDF에서 해당 위치를 찾아 강조해 줍니다.<br>"
                "• <b>양식 유지 저장</b>: 나중에 다시 열어 내용을 고칠 수 있습니다.<br>"
                "• <b>입력 내용 고정 저장</b>: 도장처럼 내용을 페이지에 고정해 더 이상 수정할 수 없게 만듭니다.",
            ),
            2: (
                "데이터 추출·입력 안내",
                "<b>③ 데이터 추출·입력이란?</b><br>"
                "PDF 입력폼에 적힌 내용을 엑셀(CSV)이나 JSON 파일로 뽑아내거나, 반대로 파일에 정리된 값을 PDF에 자동으로 채워 넣는 기능입니다.<br><br>"
                "<b>사용 팁</b><br>"
                "• 처음 사용할 때는 <b>[입력용 CSV 템플릿 저장]</b>을 눌러 빈 엑셀 양식을 만든 뒤, 값을 채워 다시 가져오면 필드명이 자동으로 연결됩니다.",
            ),
        }
        title, body = helps.get(tab_index, helps[0])
        QMessageBox.information(self, title, body)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local.lower().endswith(".pdf"):
                if self.confirm_discard_changes():
                    self.load_pdf(local)
                break
            if local.lower().endswith((".csv", ".json")) and self.session:
                self.tabs.setCurrentIndex(2)
                self.load_import_file(local)
                break

    def closeEvent(self, event):
        if self.session is not None:
            self.session.close()
        super().closeEvent(event)

    def collect_from_multiple_pdfs_dialog(self):
        """동일한 양식의 여러 PDF에서 데이터를 모아 CSV로 저장한다."""
        files, _ = QFileDialog.getOpenFileNames(
            self, "데이터를 모을 PDF 선택", "", "PDF Files (*.pdf)"
        )
        if not files:
            return
        include = self.chk_include_restricted.isChecked()
        try:
            rows, warnings = collect_fields_from_multiple_pdfs(files, include_restricted=include)
            if not rows:
                QMessageBox.information(self, "결과 없음", "추출할 데이터가 없습니다.")
                return
            dest, _ = QFileDialog.getSaveFileName(
                self, "모은 데이터 저장", "collected_form_data.csv", "CSV Files (*.csv)"
            )
            if not dest:
                return
            export_collected_rows_to_csv(rows, dest)
            msg = f"{len(files)}개 파일에서 {len(rows)}개 항목을 모아 저장했습니다.\n{dest}"
            if warnings:
                msg += "\n\n주의:\n" + "\n".join(warnings[:5])
            QMessageBox.information(self, "완료", msg)
        except Exception as exc:
            QMessageBox.critical(self, "오류", str(exc))

