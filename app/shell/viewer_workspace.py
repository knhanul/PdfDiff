"""Tabbed viewer: tab bar + viewer toolbar + (nav | canvas) + form banner + search."""
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QStackedWidget,
                             QTabBar, QVBoxLayout, QWidget)

from app.shell.global_search import GlobalSearchPanel
from app.shell.work_panel import WorkPanel
from app.viewer.nav_panel import NavPanel
from app.viewer.pdf_canvas import PdfCanvas


class FormBanner(QFrame):
    fill_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('formBanner')
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 8, 6)
        self.label = QLabel()
        btn = QPushButton('바로 작성하기')
        btn.setObjectName('primaryBtn')
        btn.clicked.connect(self.fill_requested.emit)
        close = QPushButton('✕')
        close.setObjectName('viewerToolBtn')
        close.setFixedWidth(28)
        close.clicked.connect(self.hide)
        lay.addWidget(self.label, 1)
        lay.addWidget(btn)
        lay.addWidget(close)
        self.hide()

    def show_count(self, n):
        self.label.setText(f'이 문서에는 입력 가능한 항목이 {n}개 있습니다.')
        self.show()


class DocView(QWidget):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self.doc = doc
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.banner = FormBanner()
        lay.addWidget(self.banner)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.nav = NavPanel()
        self.canvas = PdfCanvas()
        body.addWidget(self.nav)
        body.addWidget(self.canvas, 1)
        lay.addLayout(body, 1)
        self.nav.set_document(doc)
        self.canvas.set_document(doc)
        self.nav.page_selected.connect(self.canvas.go_to_page)
        self.canvas.page_changed.connect(self.nav.set_current)
        self.search_hits = []
        self.search_index = -1


class ViewerWorkspace(QWidget):
    form_fill_requested = pyqtSignal(str)   # path
    split_requested = pyqtSignal()
    open_requested = pyqtSignal()           # same as Ctrl+O / welcome open
    tab_count_changed = pyqtSignal(int)
    current_changed = pyqtSignal(object)    # doc or None
    close_doc = pyqtSignal(str)
    tool_requested = pyqtSignal(str, str)   # tool key, current path

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        tab_row = QWidget()
        tab_row.setObjectName('docTabRow')
        trl = QHBoxLayout(tab_row)
        trl.setContentsMargins(0, 0, 4, 0)
        trl.setSpacing(0)
        self.tabs = QTabBar()
        self.tabs.setObjectName('docTabs')
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setExpanding(False)
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideMiddle)
        trl.addWidget(self.tabs)
        self.btn_open_tab = QPushButton('＋ PDF 열기')
        self.btn_open_tab.setObjectName('openPdfTabBtn')
        self.btn_open_tab.setToolTip('PDF 열기 (Ctrl+O)')
        self.btn_open_tab.setMinimumSize(112, 32)
        self.btn_open_tab.clicked.connect(self.open_requested.emit)
        trl.addWidget(self.btn_open_tab, 0, Qt.AlignmentFlag.AlignVCenter)
        trl.addStretch(1)
        lay.addWidget(tab_row)

        lay.addWidget(self._build_toolbar())

        self.search_bar = self._build_search()
        lay.addWidget(self.search_bar)

        self.mode_bar = self._build_mode_bar()
        lay.addWidget(self.mode_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.global_search = GlobalSearchPanel(lambda: [v.doc for v in self._views])
        self.global_search.result_activated.connect(self.jump_to)
        self.global_search.closed.connect(self.hide_global_search)
        self.global_search.hide()
        body.addWidget(self.global_search)
        self.work_panel = WorkPanel()
        self.work_panel.closed.connect(self.close_work_mode)
        self.work_panel.tool_requested.connect(self._request_tool)
        self.work_panel.field_selected.connect(lambda pg: self._cv() and self._cv().canvas.go_to_page(pg))
        body.addWidget(self.work_panel)
        lay.addLayout(body, 1)
        self.default_fit = 'width'
        self.nav_default_visible = True

        self.tabs.currentChanged.connect(self._on_tab)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.tabMoved.connect(self._on_moved)
        self._views = []

        QShortcut(QKeySequence('Ctrl+F'), self, activated=self.show_search)
        QShortcut(QKeySequence('Ctrl+Shift+F'), self, activated=self.show_global_search)
        QShortcut(QKeySequence('Ctrl+='), self, activated=lambda: self._cv() and self._cv().canvas.zoom_in())
        QShortcut(QKeySequence('Ctrl+-'), self, activated=lambda: self._cv() and self._cv().canvas.zoom_out())
        QShortcut(QKeySequence('Ctrl+W'), self, activated=lambda: self._close_tab(self.tabs.currentIndex()))

    # ---- toolbar ---------------------------------------------------------
    def _btn(self, text, tip, slot, w=None):
        b = QPushButton(text)
        b.setObjectName('viewerToolBtn')
        b.setToolTip(tip)
        if w:
            b.setFixedWidth(w)
        b.clicked.connect(slot)
        return b

    def _build_toolbar(self):
        bar = QFrame()
        bar.setObjectName('viewerToolbar')
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 3, 8, 3)
        bl.setSpacing(4)
        self.btn_nav = self._btn('☰', '페이지 탐색 패널 접기/펼치기', self.toggle_nav, 32)
        bl.addWidget(self.btn_nav)
        bl.addSpacing(8)
        bl.addWidget(self._btn('‹', '이전 페이지', lambda: self._step(-1), 30))
        self.page_edit = QLineEdit()
        self.page_edit.setObjectName('pageEdit')
        self.page_edit.setFixedWidth(46)
        self.page_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_edit.returnPressed.connect(self._goto_typed)
        bl.addWidget(self.page_edit)
        self.page_total = QLabel('/ 0')
        self.page_total.setObjectName('mutedLabel')
        bl.addWidget(self.page_total)
        bl.addWidget(self._btn('›', '다음 페이지', lambda: self._step(1), 30))
        bl.addSpacing(12)
        bl.addWidget(self._btn('−', '축소 (Ctrl+-)', lambda: self._cv() and self._cv().canvas.zoom_out(), 30))
        self.zoom_label = QLabel('100%')
        self.zoom_label.setObjectName('zoomLabel')
        self.zoom_label.setFixedWidth(48)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(self.zoom_label)
        bl.addWidget(self._btn('+', '확대 (Ctrl+=)', lambda: self._cv() and self._cv().canvas.zoom_in(), 30))
        bl.addWidget(self._btn('폭 맞춤', '페이지 폭에 맞춤', lambda: self._cv() and self._cv().canvas.set_fit('width')))
        bl.addWidget(self._btn('쪽 맞춤', '한 페이지 전체 보기', lambda: self._cv() and self._cv().canvas.set_fit('page')))
        bl.addStretch()
        bl.addWidget(self._btn('찾기', '문서에서 찾기 (Ctrl+F)', self.show_search))
        bl.addWidget(self._btn('전체 찾기', '열린 PDF 전체에서 찾기 (Ctrl+Shift+F)', self.show_global_search))
        self.mode_buttons = {}
        for key, text, tip in (('info', '정보', '문서 정보 패널'), ('edit', '편집', '편집 작업 패널'),
                               ('form', '입력 항목', '이 문서의 입력 항목 패널')):
            b = self._btn(text, tip, lambda _=False, k=key: self.toggle_work_mode(k))
            b.setCheckable(True)
            self.mode_buttons[key] = b
            bl.addWidget(b)
        self.mode_buttons['form'].hide()  # shown only for PDFs that contain form fields
        bl.addWidget(self._btn('두 PDF 동시 보기', '현재 문서와 다른 문서를 나란히 보기', self.split_requested.emit))
        return bar

    def _build_mode_bar(self):
        """Situational toolbar: content depends on the active work mode."""
        bar = QFrame()
        bar.setObjectName('contextToolbar')
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 3, 8, 3)
        bl.setSpacing(4)
        self.mode_label = QLabel()
        self.mode_label.setObjectName('mutedLabel')
        bl.addWidget(self.mode_label)
        bl.addSpacing(8)
        self.mode_actions = {}
        specs = {
            'info': [('경로 복사', self._copy_path)],
            'edit': [('PDF 편집', lambda: self._request_tool('pdf_editor')),
                     ('PDF 생성', lambda: self._request_tool('pdf_create')),
                     ('영역지정비교', lambda: self._request_tool('pdf_compare')),
                     ('전체비교', lambda: self._request_tool('pdf_hf_compare'))],
            'form': [('PDF 입력폼 관리', lambda: self._request_tool('pdf_form'))],
        }
        for mode, items in specs.items():
            btns = []
            for text, slot in items:
                b = self._btn(text, text, slot)
                bl.addWidget(b)
                btns.append(b)
            self.mode_actions[mode] = btns
        bl.addStretch()
        bl.addWidget(self._btn('작업 끝내기', '작업 패널 닫기', self.close_work_mode))
        bar.hide()
        return bar

    # ---- work modes --------------------------------------------------------
    MODE_LABELS = {'info': '문서 정보', 'edit': '편집 모드', 'form': '입력 항목 모드'}

    def toggle_work_mode(self, mode):
        if self.work_panel.mode == mode:
            self.close_work_mode()
        else:
            self.open_work_mode(mode)

    def open_work_mode(self, mode):
        if not self._cv():
            return
        self.work_panel.open_mode(mode, self.current_doc())
        self.mode_label.setText(self.MODE_LABELS[mode])
        for m, btns in self.mode_actions.items():
            for b in btns:
                b.setVisible(m == mode)
        for m, b in self.mode_buttons.items():
            b.setChecked(m == mode)
        self.mode_bar.show()

    def close_work_mode(self):
        self.work_panel.close_panel()
        self.mode_bar.hide()
        for b in self.mode_buttons.values():
            b.setChecked(False)

    def work_mode(self):
        return self.work_panel.mode

    def _request_tool(self, key):
        d = self.current_doc()
        self.tool_requested.emit(key, d.path if d else '')

    def _copy_path(self):
        from PyQt6.QtWidgets import QApplication
        d = self.current_doc()
        if d:
            QApplication.clipboard().setText(d.path)

    # ---- global search -----------------------------------------------------
    def show_global_search(self):
        self.global_search.show()
        if self.search_edit.text().strip() and not self.global_search.edit.text():
            self.global_search.edit.setText(self.search_edit.text().strip())
        self.global_search.focus_input()

    def hide_global_search(self):
        self.global_search.hide()
        for v in self._views:
            v.canvas.highlights = {}
            v.canvas.viewport().update()

    def jump_to(self, path, page, rect=None):
        i = self.index_of(path)
        if i < 0:
            return False
        self.tabs.setCurrentIndex(i)
        v = self._views[i]
        v.canvas.highlights = {page: [tuple(rect)]} if rect else {}
        v.canvas.go_to_page(page, rect[1] if rect else None)
        v.canvas.viewport().update()
        return True

    def replace_current(self, doc, page=0):
        """Open doc in place of the current tab (기본 열기 방식 = 현재 탭 바꾸기)."""
        i = self.tabs.currentIndex()
        if self.index_of(doc.path) >= 0 or i < 0:
            return self.add_document(doc, page)
        self.add_document(doc, page)
        self._close_tab(i)

    def _build_search(self):
        bar = QFrame()
        bar.setObjectName('contextToolbar')
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 3, 8, 3)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText('문서에서 찾기…')
        self.search_edit.returnPressed.connect(self._search_next)
        self.search_info = QLabel('')
        self.search_info.setObjectName('mutedLabel')
        bl.addWidget(self.search_edit, 1)
        bl.addWidget(self.search_info)
        bl.addWidget(self._btn('이전', '이전 결과', lambda: self._search_next(-1)))
        bl.addWidget(self._btn('다음', '다음 결과', lambda: self._search_next(1)))
        bl.addWidget(self._btn('✕', '찾기 닫기', self.hide_search, 28))
        bar.hide()
        return bar

    # ---- docs ------------------------------------------------------------
    def _cv(self):
        w = self.stack.currentWidget()
        return w if isinstance(w, DocView) else None

    def current_doc(self):
        v = self._cv()
        return v.doc if v else None

    def index_of(self, path):
        for i, v in enumerate(self._views):
            if v.doc.path == path:
                return i
        return -1

    def add_document(self, doc, page=0):
        i = self.index_of(doc.path)
        if i >= 0:
            self.tabs.setCurrentIndex(i)
            return
        view = DocView(doc)
        view.canvas.fit_mode = None if self.default_fit == '100' else self.default_fit
        view.nav.setVisible(self.nav_default_visible)
        view.banner.fill_requested.connect(lambda p=doc.path: self.form_fill_requested.emit(p))
        view.canvas.page_changed.connect(self._sync_status)
        view.canvas.zoom_changed.connect(self._sync_status)
        self._views.append(view)
        self.stack.addWidget(view)
        idx = self.tabs.addTab(doc.title)
        self.tabs.setTabToolTip(idx, doc.path)
        self.tabs.setCurrentIndex(idx)
        self.stack.setCurrentWidget(view)
        if page:
            QTimer.singleShot(0, lambda: view.canvas.go_to_page(page))
        # form detection after first paint (banner, not a welcome shortcut)
        QTimer.singleShot(150, lambda v=view: self._detect_form(v))
        self.tab_count_changed.emit(len(self._views))

    def _detect_form(self, view):
        if view not in self._views:
            return
        n = view.doc.form_field_count()
        if n > 0:
            view.banner.show_count(n)
            if view is self._cv():
                self.mode_buttons['form'].setVisible(True)

    def _on_tab(self, i):
        if 0 <= i < len(self._views):
            self.stack.setCurrentWidget(self._views[i])
        self._sync_status()
        d = self.current_doc()
        self.mode_buttons['form'].setVisible(bool(d and d.form_field_count()))
        if self.work_panel.mode:
            if self.work_panel.mode == 'form' and not self.mode_buttons['form'].isVisible():
                self.close_work_mode()
            else:
                self.work_panel.refresh(d)
        self.current_changed.emit(d)

    def _on_moved(self, a, b):
        self._views.insert(b, self._views.pop(a))

    def _close_tab(self, i):
        if not (0 <= i < len(self._views)):
            return
        view = self._views.pop(i)
        self.tabs.removeTab(i)
        self.stack.removeWidget(view)
        path = view.doc.path
        view.deleteLater()
        self.close_doc.emit(path)
        if not self._views:
            self.close_work_mode()
        self.tab_count_changed.emit(len(self._views))

    def session_entries(self):
        return [{'path': v.doc.path, 'page': v.canvas.current_page()} for v in self._views]

    def count(self):
        return len(self._views)

    # ---- actions -----------------------------------------------------------
    def toggle_nav(self):
        vis = not (self._views and self._views[0].nav.isVisible())
        for v in self._views:
            v.nav.setVisible(vis)

    def set_nav_visible(self, vis):
        for v in self._views:
            v.nav.setVisible(vis)

    def _step(self, d):
        v = self._cv()
        if v:
            v.canvas.go_to_page(v.canvas.current_page() + d)

    def _goto_typed(self):
        v = self._cv()
        try:
            n = int(self.page_edit.text())
        except ValueError:
            return
        if v:
            v.canvas.go_to_page(n - 1)

    def _sync_status(self, *_):
        v = self._cv()
        if not v:
            self.page_edit.setText('')
            self.page_total.setText('/ 0')
            return
        self.page_edit.setText(str(v.canvas.current_page() + 1))
        self.page_total.setText(f'/ {v.canvas.page_count()}')
        self.zoom_label.setText(f'{round(v.canvas.zoom * 100)}%')

    def show_search(self):
        self.search_bar.show()
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def hide_search(self):
        self.search_bar.hide()
        v = self._cv()
        if v:
            v.canvas.highlights = {}
            v.canvas.viewport().update()

    def _search_next(self, step=1):
        v = self._cv()
        if not v:
            return
        text = self.search_edit.text().strip()
        if getattr(v, '_last_query', None) != text:
            v._last_query = text
            v.search_hits = v.doc.search(text)
            v.search_index = -1
            hl = {}
            for p, r in v.search_hits:
                hl.setdefault(p, []).append(r)
            v.canvas.highlights = hl
        if not v.search_hits:
            self.search_info.setText('결과 없음')
            v.canvas.viewport().update()
            return
        v.search_index = (v.search_index + step) % len(v.search_hits)
        page, rect = v.search_hits[v.search_index]
        self.search_info.setText(f'{v.search_index + 1} / {len(v.search_hits)}')
        v.canvas.go_to_page(page, rect[1])
        v.canvas.viewport().update()
