import pymupdf as fitz
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.common.pdf_form.field_models import WidgetInstance
from app.common.pdf_form.form_service import FormDocumentSession

HANDLE_SIZE = 8.0


class PdfFormCanvas(QWidget):
    """PDF 페이지 렌더링과 입력란 강조·선택·배치·크기조정을 처리하는 캔버스."""

    widget_selected = pyqtSignal(int)         # xref (0 if deselected)
    rect_drawn = pyqtSignal(int, object)      # page_index, (x0, y0, x1, y1) in PDF coords
    widget_moved = pyqtSignal(int, object)    # xref, (x0, y0, x1, y1) in PDF coords
    widget_resized = pyqtSignal(int, object)  # xref, (x0, y0, x1, y1) in PDF coords
    delete_requested = pyqtSignal(int)        # xref
    escape_pressed = pyqtSignal()
    zoom_requested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.session: FormDocumentSession | None = None
        self.page_index: int = 0
        self.zoom: float = 1.0
        self.mode: str = "create"  # "create" or "fill"
        self.creation_tool: str | None = None  # None = selection/move mode, else field_type
        self.widgets: list[WidgetInstance] = []
        self.selected_xref: int = 0
        self.highlighted_field_name: str = ""
        self._pixmap: QPixmap | None = None
        self._page_rect = fitz.Rect(0, 0, 595, 842)
        self._rotation_matrix = fitz.Identity
        self._derotation_matrix = fitz.Identity

        self._drag_mode: str | None = None  # "draw", "move", "resize"
        self._resize_handle: str = ""
        self._drag_start_view = QPointF()
        self._drag_current_view = QPointF()
        self._orig_view_rect = QRectF()
        self._preview_view_rect: QRectF | None = None

    def set_Creation_tool(self, tool_type: str | None):
        self.creation_tool = tool_type
        self.setCursor(
            Qt.CursorShape.CrossCursor if (self.mode == "create" and self.creation_tool) else Qt.CursorShape.ArrowCursor
        )
        self.update()

    def load_page_state(
        self,
        session: FormDocumentSession | None,
        page_index: int = 0,
        zoom: float = 1.0,
    ):
        self.session = session
        if session is None:
            self._pixmap = None
            self.widgets = []
            self.selected_xref = 0
            self.setMinimumSize(400, 300)
            self.resize(400, 300)
            self.update()
            return

        self.page_index = max(0, min(page_index, session.page_count - 1))
        self.zoom = max(0.3, min(float(zoom), 3.0))
        page = session.doc[self.page_index]
        self._page_rect = page.rect
        self._rotation_matrix = page.rotation_matrix
        self._derotation_matrix = page.derotation_matrix

        samples, width, height, stride = session.render_page_rgb(self.page_index, self.zoom)
        qimg = QImage(samples, width, height, stride, QImage.Format.Format_RGB888).copy()
        self._pixmap = QPixmap.fromImage(qimg)
        self.widgets = session.list_widgets(self.page_index)
        self.setFixedSize(width, height)
        self.update()

    def pdf_rect_to_view(self, rect: tuple[float, float, float, float]) -> QRectF:
        r = fitz.Rect(rect) * self._rotation_matrix * fitz.Matrix(self.zoom, self.zoom)
        return QRectF(r.x0, r.y0, r.width, r.height).normalized()

    def view_rect_to_pdf(self, qrect: QRectF) -> tuple[float, float, float, float]:
        norm = qrect.normalized()
        inv_scale = 1.0 / max(self.zoom, 0.01)
        r = fitz.Rect(norm.left(), norm.top(), norm.right(), norm.bottom()) * fitz.Matrix(inv_scale, inv_scale) * self._derotation_matrix
        r.normalize()
        bounds = self._page_rect * self._derotation_matrix
        bounds.normalize()
        x0 = max(bounds.x0, min(r.x0, bounds.x1 - 14.0))
        y0 = max(bounds.y0, min(r.y0, bounds.y1 - 14.0))
        x1 = max(x0 + 14.0, min(r.x1, bounds.x1))
        y1 = max(y0 + 14.0, min(r.y1, bounds.y1))
        return (float(x0), float(y0), float(x1), float(y1))

    def _handle_rects(self, rect: QRectF) -> dict[str, QRectF]:
        hs = HANDLE_SIZE
        half = hs / 2.0
        cx = rect.center().x()
        cy = rect.center().y()
        return {
            "tl": QRectF(rect.left() - half, rect.top() - half, hs, hs),
            "tc": QRectF(cx - half, rect.top() - half, hs, hs),
            "tr": QRectF(rect.right() - half, rect.top() - half, hs, hs),
            "mr": QRectF(rect.right() - half, cy - half, hs, hs),
            "br": QRectF(rect.right() - half, rect.bottom() - half, hs, hs),
            "bc": QRectF(cx - half, rect.bottom() - half, hs, hs),
            "bl": QRectF(rect.left() - half, rect.bottom() - half, hs, hs),
            "ml": QRectF(rect.left() - half, cy - half, hs, hs),
        }

    def _hit_test_handle(self, pos: QPointF) -> str:
        if self.mode != "create" or not self.selected_xref:
            return ""
        sel = next((w for w in self.widgets if w.xref == self.selected_xref), None)
        if sel is None:
            return ""
        vrect = self.pdf_rect_to_view(sel.rect)
        for name, hrect in self._handle_rects(vrect).items():
            if hrect.adjusted(-3, -3, 3, 3).contains(pos):
                return name
        return ""

    def _hit_test_widget(self, pos: QPointF) -> WidgetInstance | None:
        for w in reversed(self.widgets):
            if self.pdf_rect_to_view(w.rect).contains(pos):
                return w
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._pixmap is None:
            painter.fillRect(self.rect(), QColor("#F3F2EF"))
            return

        painter.drawPixmap(0, 0, self._pixmap)
        label_font = QFont("Malgun Gothic", 8)
        label_font.setBold(True)
        painter.setFont(label_font)

        for w in self.widgets:
            is_selected = (w.xref == self.selected_xref) or (
                bool(self.highlighted_field_name) and w.field_name == self.highlighted_field_name
            )
            vrect = self.pdf_rect_to_view(w.rect)
            if is_selected and self._preview_view_rect is not None and w.xref == self.selected_xref:
                vrect = self._preview_view_rect

            if is_selected:
                fill = QColor(166, 63, 43, 38)
                pen = QPen(QColor("#A63F2B"), 2.2)
            elif w.read_only:
                fill = QColor(140, 140, 145, 28)
                pen = QPen(QColor("#8E8E93"), 1.2, Qt.PenStyle.DashLine)
            else:
                fill = QColor(59, 130, 246, 26)
                pen = QPen(QColor("#3B82F6"), 1.4)

            painter.fillRect(vrect, fill)
            painter.setPen(pen)
            painter.drawRect(vrect)

            if self.mode == "create" or is_selected:
                badge_text = w.display_name + (" *" if w.required else "")
                metrics = painter.fontMetrics()
                bw = min(max(44, metrics.horizontalAdvance(badge_text) + 10), 190)
                bh = 16
                by = max(0.0, vrect.top() - bh - 1)
                badge_rect = QRectF(vrect.left(), by, bw, bh)
                badge_bg = QColor("#A63F2B") if is_selected else QColor("#2563EB")
                painter.fillRect(badge_rect, badge_bg)
                painter.setPen(QColor("#FFFFFF"))
                elided = metrics.elidedText(badge_text, Qt.TextElideMode.ElideRight, int(bw - 6))
                painter.drawText(badge_rect.adjusted(3, 0, -3, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)

            if is_selected and self.mode == "create" and w.xref == self.selected_xref:
                painter.setPen(QPen(QColor("#FFFFFF"), 1.0))
                for hrect in self._handle_rects(vrect).values():
                    painter.fillRect(hrect, QColor("#A63F2B"))
                    painter.drawRect(hrect)

        if self._drag_mode == "draw" and self._preview_view_rect is not None:
            painter.fillRect(self._preview_view_rect, QColor(37, 99, 235, 36))
            pen = QPen(QColor("#2563EB"), 1.8, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(self._preview_view_rect)

    def mousePressEvent(self, event):
        if self.session is None or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        self.setFocus()
        pos = event.position()

        handle = self._hit_test_handle(pos)
        if handle:
            sel = next((w for w in self.widgets if w.xref == self.selected_xref), None)
            if sel is not None:
                self._drag_mode = "resize"
                self._resize_handle = handle
                self._drag_start_view = pos
                self._orig_view_rect = self.pdf_rect_to_view(sel.rect)
                self._preview_view_rect = QRectF(self._orig_view_rect)
                return

        hit = self._hit_test_widget(pos)
        if hit is not None:
            self.selected_xref = hit.xref
            self.highlighted_field_name = hit.field_name
            self.widget_selected.emit(hit.xref)
            if self.mode == "create":
                self._drag_mode = "move"
                self._drag_start_view = pos
                self._orig_view_rect = self.pdf_rect_to_view(hit.rect)
                self._preview_view_rect = QRectF(self._orig_view_rect)
            self.update()
            return

        if self.mode == "create" and self.creation_tool:
            self._drag_mode = "draw"
            self._drag_start_view = pos
            self._drag_current_view = pos
            self._preview_view_rect = QRectF(pos, pos)
            self.update()
            return

        self.selected_xref = 0
        self.highlighted_field_name = ""
        self.widget_selected.emit(0)
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._drag_mode is None:
            handle = self._hit_test_handle(pos)
            if handle in ("tl", "br"):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif handle in ("tr", "bl"):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif handle in ("tc", "bc"):
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            elif handle in ("ml", "mr"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif self._hit_test_widget(pos) is not None:
                self.setCursor(Qt.CursorShape.PointingHandCursor if self.mode == "fill" else Qt.CursorShape.SizeAllCursor)
            elif self.mode == "create" and self.creation_tool:
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        dx = pos.x() - self._drag_start_view.x()
        dy = pos.y() - self._drag_start_view.y()
        bounds = QRectF(0, 0, self.width(), self.height())

        if self._drag_mode == "draw":
            clamped_end = QPointF(
                max(0.0, min(pos.x(), float(self.width()))),
                max(0.0, min(pos.y(), float(self.height()))),
            )
            self._preview_view_rect = QRectF(self._drag_start_view, clamped_end).normalized()
        elif self._drag_mode == "move":
            moved = self._orig_view_rect.translated(dx, dy)
            if moved.left() < bounds.left():
                moved.moveLeft(bounds.left())
            if moved.top() < bounds.top():
                moved.moveTop(bounds.top())
            if moved.right() > bounds.right():
                moved.moveRight(bounds.right())
            if moved.bottom() > bounds.bottom():
                moved.moveBottom(bounds.bottom())
            self._preview_view_rect = moved
        elif self._drag_mode == "resize":
            r = QRectF(self._orig_view_rect)
            h = self._resize_handle
            min_px = max(14.0, 14.0 * self.zoom)
            if "l" in h:
                r.setLeft(min(r.right() - min_px, max(0.0, r.left() + dx)))
            if "r" in h:
                r.setRight(max(r.left() + min_px, min(float(self.width()), r.right() + dx)))
            if "t" in h:
                r.setTop(min(r.bottom() - min_px, max(0.0, r.top() + dy)))
            if "b" in h:
                r.setBottom(max(r.top() + min_px, min(float(self.height()), r.bottom() + dy)))
            self._preview_view_rect = r
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._drag_mode is None:
            super().mouseReleaseEvent(event)
            return

        mode = self._drag_mode
        preview = self._preview_view_rect
        self._drag_mode = None
        self._preview_view_rect = None

        if preview is None:
            self.update()
            return

        if mode == "draw":
            if preview.width() < 12 or preview.height() < 12:
                default_w = 24.0 * self.zoom if self.creation_tool in ("checkbox", "radio") else 140.0 * self.zoom
                default_h = 24.0 * self.zoom if self.creation_tool in ("checkbox", "radio") else 26.0 * self.zoom
                preview = QRectF(
                    preview.left(),
                    preview.top(),
                    min(default_w, max(16.0, self.width() - preview.left())),
                    min(default_h, max(16.0, self.height() - preview.top())),
                )
            pdf_rect = self.view_rect_to_pdf(preview)
            self.rect_drawn.emit(self.page_index, pdf_rect)
        elif mode == "move" and self.selected_xref:
            if (preview.topLeft() - self._orig_view_rect.topLeft()).manhattanLength() >= 2.0:
                pdf_rect = self.view_rect_to_pdf(preview)
                self.widget_moved.emit(self.selected_xref, pdf_rect)
        elif mode == "resize" and self.selected_xref:
            if preview != self._orig_view_rect:
                pdf_rect = self.view_rect_to_pdf(preview)
                self.widget_resized.emit(self.selected_xref, pdf_rect)
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.mode == "create" and self.selected_xref:
            self.delete_requested.emit(self.selected_xref)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._drag_mode = None
            self._preview_view_rect = None
            self.escape_pressed.emit()
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else (1.0 / 1.15)
            self.zoom_requested.emit(max(0.4, min(3.0, self.zoom * factor)))
            event.accept()
            return
        super().wheelEvent(event)


class PdfFormViewerPane(QFrame):
    """페이지 탐색·확대/축소·화면 맞춤 바를 갖춘 PDF 미리보기 컨테이너."""

    page_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session: FormDocumentSession | None = None
        self.current_page: int = 0
        self.zoom: float = 1.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        nav = QFrame()
        nav.setObjectName("viewerToolbar")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(8, 6, 8, 6)
        nav_layout.setSpacing(6)

        self.btn_prev = QPushButton("◀ 이전")
        self.btn_prev.setObjectName("toolbarBtn")
        self.btn_prev.clicked.connect(lambda: self.go_to_page(self.current_page - 1))

        self.spin_page = QSpinBox()
        self.spin_page.setMinimum(1)
        self.spin_page.setMaximum(1)
        self.spin_page.setFixedWidth(64)
        self.spin_page.valueChanged.connect(lambda val: self.go_to_page(val - 1))

        self.lbl_total_pages = QLabel("/ 1 페이지")
        self.btn_next = QPushButton("다음 ▶")
        self.btn_next.setObjectName("toolbarBtn")
        self.btn_next.clicked.connect(lambda: self.go_to_page(self.current_page + 1))

        self.btn_zoom_out = QPushButton("축소 -")
        self.btn_zoom_out.setObjectName("toolbarBtn")
        self.btn_zoom_out.clicked.connect(lambda: self.set_zoom(self.zoom / 1.15))

        self.combo_zoom = QComboBox()
        self.combo_zoom.addItems(["75%", "100%", "125%", "150%", "200%"])
        self.combo_zoom.setCurrentText("100%")
        self.combo_zoom.currentTextChanged.connect(self._on_zoom_combo)

        self.btn_zoom_in = QPushButton("확대 +")
        self.btn_zoom_in.setObjectName("toolbarBtn")
        self.btn_zoom_in.clicked.connect(lambda: self.set_zoom(self.zoom * 1.15))

        self.btn_fit_width = QPushButton("너비 맞춤")
        self.btn_fit_width.setObjectName("toolbarBtn")
        self.btn_fit_width.clicked.connect(self.fit_to_width)

        self.btn_fit_page = QPushButton("페이지 맞춤")
        self.btn_fit_page.setObjectName("toolbarBtn")
        self.btn_fit_page.clicked.connect(self.fit_to_page)

        for w in (
            self.btn_prev,
            self.spin_page,
            self.lbl_total_pages,
            self.btn_next,
        ):
            nav_layout.addWidget(w)
        nav_layout.addStretch(1)
        for w in (
            self.btn_zoom_out,
            self.combo_zoom,
            self.btn_zoom_in,
            self.btn_fit_width,
            self.btn_fit_page,
        ):
            nav_layout.addWidget(w)
        layout.addWidget(nav)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setStyleSheet("QScrollArea { background-color: #E7E4DF; border: 1px solid #D5D0CA; border-radius: 8px; }")
        self.canvas = PdfFormCanvas()
        self.canvas.zoom_requested.connect(self.set_zoom)
        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll, 1)

    def bind_session(self, session: FormDocumentSession | None, page_index: int = 0):
        self.session = session
        self.current_page = 0 if session is None else max(0, min(page_index, session.page_count - 1))
        total = session.page_count if session else 1
        self.spin_page.blockSignals(True)
        self.spin_page.setRange(1, max(1, total))
        self.spin_page.setValue(self.current_page + 1)
        self.spin_page.blockSignals(False)
        self.lbl_total_pages.setText(f"/ {total} 페이지")
        self.refresh_view()

    def refresh_view(self):
        total = self.session.page_count if self.session else 1
        self.btn_prev.setEnabled(bool(self.session and self.current_page > 0))
        self.btn_next.setEnabled(bool(self.session and self.current_page + 1 < total))
        self.canvas.load_page_state(self.session, self.current_page, self.zoom)

    def go_to_page(self, page_index: int):
        if not self.session:
            return
        clamped = max(0, min(page_index, self.session.page_count - 1))
        if clamped == self.current_page and self.spin_page.value() == clamped + 1:
            return
        self.current_page = clamped
        self.spin_page.blockSignals(True)
        self.spin_page.setValue(clamped + 1)
        self.spin_page.blockSignals(False)
        self.refresh_view()
        self.page_changed.emit(clamped)

    def set_zoom(self, zoom: float):
        self.zoom = max(0.4, min(3.0, float(zoom)))
        pct = f"{round(self.zoom * 100)}%"
        self.combo_zoom.blockSignals(True)
        self.combo_zoom.setCurrentText(pct)
        self.combo_zoom.blockSignals(False)
        self.refresh_view()

    def _on_zoom_combo(self, text: str):
        raw = text.replace("%", "").strip()
        try:
            val = float(raw) / 100.0
            self.set_zoom(val)
        except ValueError:
            pass

    def fit_to_width(self):
        if not self.session:
            return
        page = self.session.doc[self.current_page]
        avail_w = max(240, self.scroll.viewport().width() - 32)
        self.set_zoom(avail_w / max(page.rect.width, 1.0))

    def fit_to_page(self):
        if not self.session:
            return
        page = self.session.doc[self.current_page]
        avail_w = max(240, self.scroll.viewport().width() - 32)
        avail_h = max(240, self.scroll.viewport().height() - 32)
        self.set_zoom(min(avail_w / max(page.rect.width, 1.0), avail_h / max(page.rect.height, 1.0)))

    def ensure_widget_visible(self, w: WidgetInstance):
        if w.page_index != self.current_page:
            self.go_to_page(w.page_index)
        vrect = self.canvas.pdf_rect_to_view(w.rect)
        center = vrect.center().toPoint()
        self.scroll.ensureVisible(center.x(), center.y(), 80, 80)
