"""Independent single-line PDF content editor; PDF work runs off the GUI thread."""
from pathlib import Path
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

import pymupdf as fitz
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QImage, QPixmap, QPainter, QPen, QShortcut, QKeySequence, QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton, QLabel,
    QLineEdit, QCheckBox, QDoubleSpinBox, QSpinBox, QComboBox, QFileDialog,
    QMessageBox, QSplitter, QScrollArea, QListWidget, QListWidgetItem,
    QFrame, QDialog, QTableWidget, QTableWidgetItem, QInputDialog, QApplication,
)

from app.common.styles import MODERN_QSS, COLOR_WORKSPACE_DARK
from app.common.pdf_text_edit import EditSession, EditError, hit_test, rasterize


def render_page(executor, data, number, zoom, revision, password="", thumbnail=False, cached_runs=None):
    samples, width, height, stride, runs, transform = executor.submit(
        rasterize, data, number, zoom, revision, password, thumbnail, cached_runs is None).result()
    image = QImage(samples, width, height, stride, QImage.Format.Format_RGB888).copy()
    return image, runs if cached_runs is None else cached_runs, transform


class _Job(QThread):
    def __init__(self, function, parent):
        super().__init__(parent)
        self.function = function
        self.value = None
        self.error = None

    def run(self):
        try:
            self.value = self.function()
        except Exception as exc:
            self.error = str(exc)


class EditCanvas(QLabel):
    selected = pyqtSignal(object)
    edit_requested = pyqtSignal()
    add_requested = pyqtSignal(object)
    draft_changed = pyqtSignal(str)
    cancelled = pyqtSignal()
    confirmed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.runs = []
        self.transform = None
        self.target_rect = None
        self.changed_rects = []
        self.add_mode = False
        self.read_only = False
        self.inline = QLineEdit(self)
        self.inline.setStyleSheet("QLineEdit { background: white; color: #292D33; border: 2px solid #A44735; padding: 2px; }")
        self.inline.hide()
        self.inline.textEdited.connect(self.draft_changed)
        self.inline.returnPressed.connect(self.confirmed)
        shortcut = QShortcut(QKeySequence("Escape"), self.inline)
        shortcut.activated.connect(self.cancelled)

    def show_page(self, rendered):
        image, self.runs, self.transform = rendered
        self.setPixmap(QPixmap.fromImage(image))
        self.setFixedSize(image.size())
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.transform:
            return
        if self.read_only:
            return
        point = self.transform.to_pdf((event.position().x(), event.position().y()))
        if self.add_mode:
            self.add_requested.emit((point.x, point.y))
        else:
            self.selected.emit(hit_test(self.runs, point))

    def mouseDoubleClickEvent(self, event):
        self.mousePressEvent(event)
        if self.target_rect and not self.read_only:
            self.edit_requested.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)

    def begin_inline(self, text):
        if not self.transform or not self.target_rect:
            return
        r = self.transform.rect_to_view(self.target_rect)
        self.inline.setGeometry(int(r.x0), int(r.y0), max(100, int(r.width) + 12),
                                max(30, int(r.height) + 6))
        self.inline.setText(text)
        self.inline.show()
        self.inline.raise_()
        self.inline.setFocus()
        self.inline.selectAll()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.transform:
            return
        from PyQt6.QtCore import QRectF
        painter = QPainter(self)
        for rect in self.changed_rects:
            r = self.transform.rect_to_view(rect)
            painter.setPen(QPen(QColor("#A44735"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(r.x0, r.y0, r.width, r.height))
        if self.target_rect:
            r = self.transform.rect_to_view(self.target_rect)
            painter.setPen(QPen(QColor("#A44735"), 1.5))
            painter.setBrush(QColor(164, 71, 53, 30))
            painter.drawRect(QRectF(r.x0, r.y0, r.width, r.height))
        painter.end()


class PdfModifyWidget(QWidget):
    compare_requested = pyqtSignal(str, str)

    def __init__(self, parent=None, comparison_settings=None):
        super().__init__(parent)
        self.setStyleSheet(MODERN_QSS + """
            QPushButton:disabled, QPushButton#actionBtn:disabled, QPushButton#toolbarBtn:disabled {
                background: #EAECF0; color: #667085; border-color: #DDE1E6;
            }
        """)
        self.setAcceptDrops(True)
        self.session = None
        # MuPDF is not thread-safe. Only this child process touches edit documents.
        # _Job threads wait for results; QWidget/QPixmap operations stay on the GUI thread.
        self.executor = ProcessPoolExecutor(max_workers=1,
                                            mp_context=multiprocessing.get_context("spawn"))
        self.job = None
        self.target = None
        self.add_origin = None
        self.page_number = 0
        self.zoom = 1.25
        self.prepared = None
        self.font_path = None
        self._changing = False
        self._thumbs = set()
        self._last_render = None
        self._text_cache = OrderedDict()
        self._draft_dirty = False
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        self.toolbar = QWidget()
        tools = QHBoxLayout(self.toolbar)
        tools.setContentsMargins(0, 0, 0, 0)

        def button(text, handler, layout=tools):
            b = QPushButton(text)
            b.setObjectName("toolbarBtn")
            b.clicked.connect(handler)
            layout.addWidget(b)
            return b

        self.open_button = button("PDF 열기", self.open_dialog)
        self.select_button = button("텍스트 선택", self.select_mode)
        self.edit_button = button("텍스트 수정", self.begin_edit)
        self.add_button = button("텍스트 추가", self.add_mode)
        self.undo_button = button("실행 취소", self.undo)
        self.redo_button = button("다시 실행", self.redo)
        self.original_button = button("원본 보기", self.toggle_original)
        self.original_button.setCheckable(True)
        self.history_button = button("변경 내용", self.show_history)
        self.save_button = button("다른 이름으로 저장", self.save_dialog)
        tools.addStretch()
        root.addWidget(self.toolbar)
        self.navigation = QWidget()
        nav = QHBoxLayout(self.navigation)
        nav.setContentsMargins(0, 0, 0, 0)
        button("이전", lambda: self.page_spin.setValue(self.page_number), nav)
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.valueChanged.connect(self.change_page)
        nav.addWidget(self.page_spin)
        self.pages_label = QLabel("/ 0 페이지")
        nav.addWidget(self.pages_label)
        button("다음", lambda: self.page_spin.setValue(self.page_number + 2), nav)
        nav.addStretch()
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["50%", "75%", "100%", "125%", "150%", "200%"])
        self.zoom_combo.setCurrentText("125%")
        self.zoom_combo.currentTextChanged.connect(self.change_zoom)
        nav.addWidget(self.zoom_combo)
        root.addWidget(self.navigation)
        self.splitter = QSplitter()
        self.thumbnails = QListWidget()
        self.thumbnails.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbnails.setFlow(QListWidget.Flow.TopToBottom)
        self.thumbnails.setWrapping(False)
        self.thumbnails.setMovement(QListWidget.Movement.Static)
        self.thumbnails.setIconSize(QSize(95, 125))
        self.thumbnails.setMinimumWidth(115)
        self.thumbnails.setMaximumWidth(210)
        self.thumbnails.currentRowChanged.connect(lambda row: self.page_spin.setValue(row + 1))
        self.thumbnails.verticalScrollBar().valueChanged.connect(lambda: self.thumb_timer.start())
        self.splitter.addWidget(self.thumbnails)
        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setStyleSheet(f"QScrollArea {{ background: {COLOR_WORKSPACE_DARK}; }}")
        self.canvas = EditCanvas()
        self.scroll.setWidget(self.canvas)
        self.canvas.selected.connect(self.select_target)
        self.canvas.edit_requested.connect(self.begin_edit)
        self.canvas.add_requested.connect(self.start_add)
        self.canvas.draft_changed.connect(self.inline_changed)
        self.canvas.cancelled.connect(self.cancel_edit)
        self.canvas.confirmed.connect(self.apply_edit)
        self.splitter.addWidget(self.scroll)
        self.properties = QWidget()
        form = QFormLayout(self.properties)
        self.properties.setMinimumWidth(270)
        self.properties.setMaximumWidth(370)
        self.original_text = QLineEdit()
        self.original_text.setReadOnly(True)
        form.addRow("원본 텍스트", self.original_text)
        self.range_button = QPushButton("선택한 문자만 수정")
        self.range_button.setToolTip("위 원본 텍스트에서 마우스로 일부 문자를 선택한 뒤 누르세요.")
        self.range_button.clicked.connect(self.narrow_selection)
        form.addRow(self.range_button)
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("수정할 한 줄 텍스트")
        self.text_edit.textChanged.connect(self.draft_changed)
        form.addRow("수정할 텍스트", self.text_edit)
        self.keep_format = QCheckBox("원본 서식 유지")
        self.keep_format.setChecked(True)
        self.keep_format.toggled.connect(self.format_changed)
        form.addRow(self.keep_format)
        self.font_label = QLabel("선택 없음")
        self.font_label.setWordWrap(True)
        form.addRow("원본 글꼴", self.font_label)
        self.font_button = QPushButton("대체 / 추가 글꼴 파일 선택")
        self.font_button.clicked.connect(self.choose_font)
        form.addRow(self.font_button)
        self.font_choice = QLabel("원본 글꼴을 우선 재사용합니다.")
        self.font_choice.setWordWrap(True)
        form.addRow(self.font_choice)
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(1, 200)
        self.size_spin.setDecimals(2)
        self.size_spin.setValue(12)
        self.size_spin.valueChanged.connect(self.options_changed)
        form.addRow("크기 (pt)", self.size_spin)
        self.color_edit = QLineEdit("#000000")
        self.color_edit.textChanged.connect(self.options_changed)
        form.addRow("글자색", self.color_edit)
        self.flags_label = QLabel("확인 불가")
        self.flags_label.setWordWrap(True)
        form.addRow("굵게 / 기울임", self.flags_label)
        self.position_label = QLabel("—")
        self.position_label.setWordWrap(True)
        form.addRow("원본 위치", self.position_label)
        self.x_spin, self.y_spin = QDoubleSpinBox(), QDoubleSpinBox()
        for spin in (self.x_spin, self.y_spin):
            spin.setRange(0, 20000)
            spin.setDecimals(2)
            spin.valueChanged.connect(self.options_changed)
        form.addRow("추가 X (pt)", self.x_spin)
        form.addRow("추가 기준선 Y (pt)", self.y_spin)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(.1, 20000)
        self.width_spin.setDecimals(2)
        self.width_spin.valueChanged.connect(self.options_changed)
        form.addRow("영역 너비 (pt)", self.width_spin)
        self.shrink = QCheckBox("지정한 최소 크기까지 축소 허용")
        self.shrink.toggled.connect(self.options_changed)
        self.min_size = QDoubleSpinBox()
        self.min_size.setRange(1, 200)
        self.min_size.setValue(10)
        self.min_size.valueChanged.connect(self.options_changed)
        form.addRow(self.shrink)
        form.addRow("최소 크기 (pt)", self.min_size)
        self.support = QLabel("PDF를 열고 텍스트를 클릭하세요.")
        self.support.setWordWrap(True)
        form.addRow(self.support)
        self.apply_button = QPushButton("수정 적용")
        self.apply_button.setObjectName("actionBtn")
        self.apply_button.clicked.connect(self.apply_edit)
        form.addRow(self.apply_button)
        self.cancel_button = QPushButton("수정 취소")
        self.cancel_button.clicked.connect(self.cancel_edit)
        form.addRow(self.cancel_button)
        self.delete_button = QPushButton("선택 텍스트 삭제")
        self.delete_button.clicked.connect(self.delete_text)
        form.addRow(self.delete_button)
        prop_scroll = QScrollArea()
        prop_scroll.setWidgetResizable(True)
        prop_scroll.setWidget(self.properties)
        prop_scroll.setMinimumWidth(290)
        self.splitter.addWidget(prop_scroll)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([145, 900, 300])
        root.addWidget(self.splitter, 1)
        self.bottom_action_bar = QFrame()
        bottom = QHBoxLayout(self.bottom_action_bar)
        self.status = QLabel("PDF 수정 · 한 줄 텍스트 편집")
        self.status.setWordWrap(True)
        bottom.addWidget(self.status, 1)
        self.btn_focus_mode = QPushButton()
        self.btn_focus_mode.setCheckable(True)
        self.btn_focus_mode.hide()
        bottom.addWidget(self.btn_focus_mode)
        root.addWidget(self.bottom_action_bar)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(500)
        self.preview_timer.timeout.connect(self.preview)
        self.thumb_timer = QTimer(self)
        self.thumb_timer.setSingleShot(True)
        self.thumb_timer.setInterval(100)
        self.thumb_timer.timeout.connect(self.load_thumbnail)
        for key, handler in (("Ctrl+Z", self.undo), ("Ctrl+Y", self.redo),
                             ("Ctrl+Shift+S", self.save_dialog), ("Escape", self.cancel_edit)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(handler)
        self.update_controls()

    def submit(self, function, callback, message="처리 중…"):
        if self.job:
            return
        self.preview_timer.stop()
        self.thumb_timer.stop()
        self.status.setText(message)
        focus = QApplication.focusWidget()
        if focus is not None and not self.isAncestorOf(focus):
            focus = None
        job = _Job(function, self)
        self.job = job
        def finished():
            self.job = None
            self.update_controls()
            if self.isVisible():
                if focus is not None and focus.isVisible() and focus.isEnabled():
                    focus.setFocus()
                else:
                    self.canvas.setFocus()
            if job.error:
                self.prepared = None
                if self._last_render:
                    self.canvas.show_page(self._last_render)
                self.support.setText(job.error)
                self.status.setText("처리하지 못했습니다: " + job.error)
            else:
                callback(job.value)
            job.deleteLater()
            self.thumb_timer.start()
        job.finished.connect(finished)
        self.update_controls()
        job.start()

    def update_controls(self):
        busy = self.job is not None
        loaded = self.session is not None
        writable = loaded and not self.session.restriction and not self.original_button.isChecked()
        self.toolbar.setEnabled(not busy)
        self.navigation.setEnabled(loaded and not busy)
        self.splitter.setEnabled(not busy)
        for b in (self.select_button, self.edit_button, self.add_button):
            b.setEnabled(bool(writable))
        self.undo_button.setEnabled(bool(writable and self.session.index))
        self.redo_button.setEnabled(bool(writable and self.session.index < len(self.session.commands)))
        self.save_button.setEnabled(bool(writable))
        self.original_button.setEnabled(loaded)
        self.history_button.setEnabled(loaded)
        editable = writable and (self.target is not None or self.add_origin is not None)
        self.properties.setEnabled(bool(editable))
        self.canvas.read_only = not writable
        self.font_button.setEnabled(not self.keep_format.isChecked() or self.add_origin is not None)
        self.size_spin.setEnabled(not self.keep_format.isChecked())
        self.color_edit.setEnabled(not self.keep_format.isChecked())
        self.x_spin.setEnabled(self.add_origin is not None)
        self.y_spin.setEnabled(self.add_origin is not None)
        self.delete_button.setEnabled(self.target is not None)
        if self.target and not self.target.writable:
            self.delete_button.setEnabled(False)
        self.apply_button.setEnabled(bool(editable and self._draft_dirty and
                                          (not self.target or self.target.writable)))
        self.edit_button.setEnabled(bool(writable and self.target and self.target.writable))
        self.range_button.setEnabled(self.target is not None)
        self.keep_format.setEnabled(self.target is not None)

    def status_text(self):
        if not self.session:
            return
        dirty = "저장되지 않은 변경" if self.session.dirty else "저장 상태"
        self.status.setText(f"{self.page_number + 1} / {self.session.page_count} 페이지 · "
                            f"{self.zoom:.0%} · {dirty} · 적용 {self.session.index}건"
                            + (" · 원본 보기" if self.original_button.isChecked() else ""))

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "수정할 PDF 열기", "", "PDF (*.pdf)")
        if path:
            self.load_pdf(path)

    def load_pdf(self, path):
        if not self.confirm_discard():
            return
        password = ""
        try:
            with fitz.open(path) as d:
                if d.needs_pass:
                    password, ok = QInputDialog.getText(self, "암호화 PDF", "열람 암호", QLineEdit.EchoMode.Password)
                    if not ok:
                        return
        except Exception as exc:
            QMessageBox.warning(self, "PDF 열기", str(exc))
            return
        self.submit(lambda: EditSession(path, password, self.executor), self.opened, "PDF 확인 중…")

    def opened(self, session):
        if self.session:
            self.session.close()
        self.session = session
        self._text_cache.clear()
        self._last_render = None
        self.page_number = 0
        self._thumbs.clear()
        self.clear_draft()
        self.original_button.setChecked(False)
        self.thumbnails.blockSignals(True)
        self.thumbnails.clear()
        for n in range(session.page_count):
            item = QListWidgetItem(f"{n + 1} 페이지")
            item.setSizeHint(QSize(110, 150))
            self.thumbnails.addItem(item)
        self.thumbnails.setCurrentRow(0)
        self.thumbnails.blockSignals(False)
        self.page_spin.blockSignals(True)
        self.page_spin.setRange(1, session.page_count)
        self.page_spin.setValue(1)
        self.page_spin.blockSignals(False)
        self.pages_label.setText(f"/ {session.page_count} 페이지")
        self.support.setText(session.restriction or "클릭하여 선택 · 더블클릭하여 수정")
        self.refresh_page()

    def current_data(self):
        if self.original_button.isChecked():
            return self.session.snapshots[0].read_bytes()
        return self.session.data

    def refresh_page(self):
        if not self.session:
            return
        data = self.current_data()
        number, zoom, revision = self.page_number, self.zoom, self.session.revision
        password = self.session.password
        cache_key = (revision, number, self.original_button.isChecked())
        cached = self._text_cache.get(cache_key)
        self.submit(lambda: render_page(self.executor, data, number, zoom, revision, password,
                                       cached_runs=cached),
                    self.page_rendered, "페이지 표시 중…")

    def page_rendered(self, result):
        self._last_render = result
        key = (self.session.revision, self.page_number, self.original_button.isChecked())
        self._text_cache[key] = result[1]
        self._text_cache.move_to_end(key)
        while len(self._text_cache) > 8:
            self._text_cache.popitem(last=False)
        self.canvas.show_page(result)
        self.canvas.changed_rects = ([] if self.original_button.isChecked() else
            [c.rect for c in self.session.commands[:self.session.index] if c.page == self.page_number])
        if not result[1]:
            self.support.setText("추출 가능한 텍스트가 없습니다. 스캔·윤곽선 문자는 수정할 수 없습니다.")
        self.canvas.update()
        self.status_text()
        self.update_controls()

    def load_thumbnail(self):
        if not self.session or self.job or self._draft_dirty or not self.isVisible():
            return
        top = max(0, self.thumbnails.indexAt(self.thumbnails.viewport().rect().topLeft()).row())
        for n in range(top, min(top + 6, self.session.page_count)):
            if n in self._thumbs:
                continue
            data, revision, password = self.current_data(), self.session.revision, self.session.password
            def render():
                return render_page(self.executor, data, n, 1, revision, password, thumbnail=True)[0]
            def shown(image, page=n):
                self.thumbnails.item(page).setIcon(QIcon(QPixmap.fromImage(image)))
                self._thumbs.add(page)
                if len(self._thumbs) > 64:
                    farthest = max(self._thumbs, key=lambda i: abs(i - page))
                    self._thumbs.remove(farthest)
                    self.thumbnails.item(farthest).setIcon(QIcon())
                self.status_text()
            self.submit(render, shown, "페이지 썸네일 표시 중…")
            break

    def allow_draft_change(self):
        if not self._draft_dirty:
            return True
        return QMessageBox.question(self, "미확정 수정", "입력 중인 수정을 취소하고 이동할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def change_page(self, number):
        if not self.session or number - 1 == self.page_number:
            return
        if not self.allow_draft_change():
            self.page_spin.blockSignals(True)
            self.page_spin.setValue(self.page_number + 1)
            self.page_spin.blockSignals(False)
            self.thumbnails.blockSignals(True)
            self.thumbnails.setCurrentRow(self.page_number)
            self.thumbnails.blockSignals(False)
            return
        self.clear_draft()
        self.page_number = number - 1
        self._last_render = None
        self.canvas.clear()
        self.canvas.runs = []
        self.canvas.transform = None
        self.thumbnails.setCurrentRow(self.page_number)
        self.refresh_page()

    def change_zoom(self, text):
        self.zoom = int(text.rstrip("%")) / 100
        self.canvas.inline.hide()
        self.prepared = None
        self.refresh_page()
        if self._draft_dirty:
            self.preview_timer.start()

    def clear_draft(self):
        self.preview_timer.stop()
        self._changing = True
        self.target = None
        self.add_origin = None
        self.prepared = None
        self._draft_dirty = False
        self.original_text.clear()
        self.text_edit.clear()
        self.canvas.inline.hide()
        self.canvas.target_rect = None
        self.canvas.update()
        self._changing = False
        self.update_controls()

    def select_target(self, target):
        if self.job or not self.allow_draft_change():
            return
        self.clear_draft()
        if not target:
            if self._last_render:
                self.canvas.show_page(self._last_render)
            return
        self._changing = True
        self.target = target
        self.canvas.target_rect = tuple(target.rect)
        self.original_text.setText(target.text)
        self.text_edit.setText(target.text)
        self.font_label.setText(target.font or "확인 불가")
        self.keep_format.setChecked(True)
        self.size_spin.setValue(target.size)
        self.color_edit.setText(f"#{target.color:06X}")
        self.width_spin.setValue(target.rect.width)
        self.min_size.setValue(max(1, target.size * .9))
        self.shrink.setChecked(False)
        self.position_label.setText(f"X {target.origins[0][0]:.2f} / 기준선 Y {target.origins[0][1]:.2f} pt")
        self.flags_label.setText(f"굵게: {'예' if target.flags & 16 else '아니오'} / "
                                 f"기울임: {'예' if target.flags & 2 else '아니오'} (PDF 추출 정보)")
        self.support.setText(target.reason or "문자 선택됨 · 적용 전 글꼴·겹침·주변 화면 검증")
        if not target.writable:
            self.status.setText(target.reason)
        self._changing = False
        if self._last_render:
            self.canvas.show_page(self._last_render)
        self.update_controls()

    def narrow_selection(self):
        if not self.target or not self.original_text.selectedText():
            return
        # Qt uses UTF-16 indices; Python uses Unicode code points.
        utf16 = self.original_text.text().encode("utf-16-le")
        start = len(utf16[:self.original_text.selectionStart() * 2].decode("utf-16-le"))
        end = start + len(self.original_text.selectedText())
        self.select_target(self.target.subset(start, end))

    def select_mode(self):
        self.canvas.add_mode = False
        self.support.setText("텍스트를 클릭하세요. 겹친 문자는 선택하지 않습니다.")

    def begin_edit(self):
        if self.target and self.target.writable and not self.job:
            self.canvas.begin_inline(self.text_edit.text())

    def add_mode(self):
        if not self.allow_draft_change():
            return
        self.clear_draft()
        self.canvas.add_mode = True
        self.support.setText("추가할 위치를 클릭하세요. 글꼴 파일 선택이 필요합니다.")
        self.status.setText("텍스트 추가 · PDF에서 기준선 위치를 클릭하세요.")

    def start_add(self, point):
        if not self.allow_draft_change():
            return
        self.clear_draft()
        self._changing = True
        self.add_origin = point
        self.keep_format.setChecked(False)
        self.x_spin.setValue(point[0])
        self.y_spin.setValue(point[1])
        self.size_spin.setValue(12)
        self.width_spin.setValue(120)
        self.color_edit.setText("#000000")
        self.canvas.target_rect = (point[0], point[1] - 12, point[0] + 120, point[1] + 4)
        self.font_label.setText("추가 텍스트")
        self.flags_label.setText("선택한 글꼴 파일의 서식 사용")
        self._changing = False
        self.update_controls()
        self.text_edit.setFocus()
        self.canvas.update()

    def inline_changed(self, text):
        self.text_edit.setText(text)

    def draft_changed(self, *args):
        if self._changing or not (self.target or self.add_origin):
            return
        self.canvas.inline.setText(self.text_edit.text())
        self._draft_dirty = True
        self.prepared = None
        self.update_controls()
        self.preview_timer.start()

    def options_changed(self, *args):
        self.draft_changed()

    def format_changed(self, *args):
        self.update_controls()
        self.draft_changed()

    def choose_font(self):
        path, _ = QFileDialog.getOpenFileName(self, "사용 권한이 있는 글꼴 선택", "",
                                             "글꼴 (*.ttf *.otf)")
        if path:
            self.font_path = path
            self.font_choice.setText(f"대체 글꼴: {Path(path).name}\n원본과 모양이 달라질 수 있습니다.")
            self.draft_changed()

    def edit_options(self):
        custom = not self.keep_format.isChecked()
        color = QColor(self.color_edit.text())
        if not color.isValid():
            raise EditError("글자색은 #RRGGBB 형식으로 입력하세요.")
        if custom and not self.font_path:
            raise EditError("사용 권한이 있는 대체/추가 글꼴 파일을 먼저 선택하세요.")
        return dict(font_path=self.font_path if custom else None,
                    size=self.size_spin.value() if custom else None,
                    color=(color.rgb() & 0xFFFFFF) if custom else None,
                    width=self.width_spin.value(),
                    origin=(self.x_spin.value(), self.y_spin.value()) if self.add_origin else None,
                    shrink_min=self.min_size.value() if self.shrink.isChecked() else None)

    def preview(self):
        if self.job:
            self.preview_timer.start()
            return
        if not self.session or not (self.target or self.add_origin):
            return
        try:
            options = self.edit_options()
        except EditError as exc:
            self.support.setText(str(exc))
            return
        page, target, text = self.page_number, self.target, self.text_edit.text()
        zoom, revision = self.zoom, self.session.revision
        def prepare():
            candidate = self.session.prepare(page, target, text, **options)
            rendered = render_page(self.executor, candidate[0], page, zoom, revision, cached_runs=[])
            return candidate, rendered
        def show(value):
            self.prepared, rendered = value
            # Keep hit testing against committed text, not the uncommitted preview.
            self.canvas.show_page((rendered[0], self._last_render[1], self._last_render[2]))
            self.support.setText("미리보기 검증 통과 · 적용 버튼을 눌러 확정하세요."
                                + (" 대체 글꼴이 사용됩니다." if options["font_path"] else ""))
            self.status.setText("미확정 미리보기 · 실제 문서는 아직 변경되지 않았습니다.")
        self.submit(prepare, show, "수정 미리보기 및 주변 콘텐츠 검증 중…")

    def apply_edit(self):
        if self.job or not self.session or not self._draft_dirty or not (self.target or self.add_origin):
            return
        try:
            options = self.edit_options()
        except EditError as exc:
            self.support.setText(str(exc))
            return
        self.canvas.inline.hide()
        target, text, page = self.target, self.text_edit.text(), self.page_number
        prepared = self.prepared
        def apply():
            self.session.commit(prepared or self.session.prepare(page, target, text, **options))
        self.submit(apply, lambda _: self.applied(), "변경 적용 중…")

    def applied(self):
        self.clear_draft()
        self._thumbs.discard(self.page_number)
        self.support.setText("수정 적용됨 · 다른 이름으로 저장하여 파일을 만드세요.")
        self.refresh_page()

    def delete_text(self):
        if self.target:
            self.text_edit.clear()
            self.apply_edit()

    def cancel_edit(self):
        if self.job:
            return
        self.clear_draft()
        if self._last_render:
            self.canvas.show_page(self._last_render)
        self.status_text()

    def undo(self):
        if self.job or not self.session or not self.session.index or not self.allow_draft_change():
            return
        self.clear_draft()
        self.session.undo()
        self._thumbs.clear()
        self.refresh_page()

    def redo(self):
        if self.job or not self.session or self.session.index == len(self.session.commands) or not self.allow_draft_change():
            return
        self.clear_draft()
        self.session.redo()
        self._thumbs.clear()
        self.refresh_page()

    def toggle_original(self):
        if not self.allow_draft_change():
            self.original_button.setChecked(not self.original_button.isChecked())
            return
        self.clear_draft()
        self._thumbs.clear()
        self.refresh_page()

    def show_history(self):
        if not self.session:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("적용한 변경 내용")
        dialog.resize(750, 400)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(self.session.index, 5)
        table.setHorizontalHeaderLabels(["페이지", "수정 전", "수정 후", "글꼴", "크기"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        for row, command in enumerate(self.session.commands[:self.session.index]):
            for col, text in enumerate((str(command.page + 1), command.before, command.after,
                                        command.font, f"{command.size:.2f}")):
                table.setItem(row, col, QTableWidgetItem(text))
        layout.addWidget(table)
        note = QLabel("원본 보기와 변경 영역 점선으로 수정 전후를 확인할 수 있습니다.")
        layout.addWidget(note)
        compare = QPushButton("원본과 저장본을 전체비교로 열기")
        compare.setEnabled(bool(self.session.last_saved_path and not self.session.dirty))
        compare.setToolTip("다른 이름으로 저장한 뒤 사용할 수 있습니다. 전체비교의 비교 실행 버튼으로 비교합니다.")
        def open_comparison():
            try:
                # The source may have been changed by another application since opening.
                if (self.session.source_path.read_bytes() != self.session.snapshots[0].read_bytes()
                        or self.session.last_saved_path.read_bytes() != self.session.data):
                    raise EditError("원본 또는 저장본이 외부에서 변경되었습니다. 파일을 다시 확인하세요.")
            except (OSError, EditError) as exc:
                QMessageBox.warning(dialog, "비교 파일 확인", str(exc))
                return
            dialog.accept()
            self.compare_requested.emit(str(self.session.source_path), str(self.session.last_saved_path))
        compare.clicked.connect(open_comparison)
        layout.addWidget(compare)
        dialog.exec()

    def save_dialog(self):
        if self.job or not self.session:
            return
        if self._draft_dirty:
            QMessageBox.information(self, "미확정 수정", "입력한 내용을 먼저 적용하거나 취소하세요.")
            return
        source = self.session.source_path
        path, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 저장",
            str(source.with_name(source.stem + "_수정.pdf")), "PDF (*.pdf)")
        if path:
            self.submit(lambda: self.session.save_as(path),
                        lambda _: self.saved(path), "저장 및 재열기 검증 중…")

    def saved(self, path):
        self.status_text()
        self.support.setText(f"저장 및 재열기 검증 완료\n{path}")

    def confirm_discard(self):
        if self.job:
            QMessageBox.information(self, "처리 중", "현재 작업이 끝난 뒤 다시 시도하세요.")
            return False
        if not (self._draft_dirty or (self.session and self.session.dirty)):
            return True
        return QMessageBox.question(self, "저장되지 않은 변경",
            "저장하지 않은 변경을 버릴까요? 보존하려면 취소 후 다른 이름으로 저장하세요.",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Discard

    def dispose(self):
        self.preview_timer.stop()
        self.thumb_timer.stop()
        if self.session:
            self.session.close()
            self.session = None
        self.executor.shutdown(wait=True, cancel_futures=True)

    def hideEvent(self, event):
        # Sidebar navigation keeps the session and draft alive in the tool cache.
        self.preview_timer.stop()
        self.thumb_timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self.session:
            self.thumb_timer.start()
            if self._draft_dirty:
                self.preview_timer.start()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.job:
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.toLocalFile().lower().endswith(".pdf"):
                self.load_pdf(url.toLocalFile())
                event.acceptProposedAction()
                break
