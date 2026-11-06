"""Continuous-scroll PDF canvas (QAbstractScrollArea, renders only visible pages)."""
from PyQt6.QtCore import QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QAbstractScrollArea

from app.viewer.render_service import render_service

PAGE_GAP = 12
MARGIN = 16
CANVAS_BG = QColor('#E7E3DF')


class PdfCanvas(QAbstractScrollArea):
    page_changed = pyqtSignal(int)          # 0-based
    zoom_changed = pyqtSignal(float)
    scrolled = pyqtSignal(float, float)     # fractional position (page-relative y, x ratio)

    MIN_ZOOM, MAX_ZOOM = 0.1, 6.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None
        self.zoom = 1.0
        self.fit_mode = 'width'  # 'width' | 'page' | None
        self._tops = []
        self._content_w = 0
        self._current_page = 0
        self.highlights = {}  # page -> list of rects (pt)
        self._service = render_service()
        self._service.rendered.connect(self._on_rendered)
        self.viewport().setAutoFillBackground(False)
        self.setFrameShape(QAbstractScrollArea.Shape.NoFrame)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(self._on_scroll)

    # ---- document / layout -------------------------------------------------
    def set_document(self, doc):
        self.doc = doc
        self.highlights = {}
        self._relayout()
        self.verticalScrollBar().setValue(0)
        self.viewport().update()

    def _dpi_scale(self):
        return self.devicePixelRatioF() * 96.0 / 72.0

    def _scale(self):
        return self.zoom * 96.0 / 72.0  # logical px per pt

    def _relayout(self):
        if not self.doc:
            self._tops = []
            return
        if self.fit_mode:
            self._apply_fit()
        s = self._scale()
        y = MARGIN
        self._tops = []
        maxw = 0
        for w, h in self.doc.page_sizes:
            self._tops.append(y)
            y += h * s + PAGE_GAP
            maxw = max(maxw, w * s)
        self._content_w = int(maxw + 2 * MARGIN)
        total_h = int(y + MARGIN)
        vp = self.viewport().size()
        self.verticalScrollBar().setRange(0, max(0, total_h - vp.height()))
        self.verticalScrollBar().setPageStep(vp.height())
        self.verticalScrollBar().setSingleStep(40)
        self.horizontalScrollBar().setRange(0, max(0, self._content_w - vp.width()))
        self.horizontalScrollBar().setPageStep(vp.width())

    def _apply_fit(self):
        vp = self.viewport().size()
        if not self.doc.page_sizes or vp.width() < 50:
            return
        idx = min(self._current_page, len(self.doc.page_sizes) - 1)
        w, h = self.doc.page_sizes[idx]
        k = 72.0 / 96.0
        zw = (vp.width() - 2 * MARGIN) / w * k
        if self.fit_mode == 'page':
            zh = (vp.height() - 2 * MARGIN) / h * k
            zw = min(zw, zh)
        z = max(self.MIN_ZOOM, min(self.MAX_ZOOM, zw))
        if abs(z - self.zoom) > 1e-3:
            self.zoom = z
            self.zoom_changed.emit(z)

    def set_zoom(self, zoom, keep_fit=False):
        if not keep_fit:
            self.fit_mode = None
        zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, zoom))
        frac = self.position()
        self.zoom = zoom
        self._relayout()
        self.set_position(*frac)
        self.zoom_changed.emit(self.zoom)
        self.viewport().update()

    def zoom_in(self):
        self.set_zoom(self.zoom * 1.2)

    def zoom_out(self):
        self.set_zoom(self.zoom / 1.2)

    def set_fit(self, mode):
        self.fit_mode = mode
        page = self._current_page
        self._relayout()
        self.go_to_page(page)
        self.zoom_changed.emit(self.zoom)
        self.viewport().update()

    # ---- navigation --------------------------------------------------------
    def page_count(self):
        return self.doc.page_count if self.doc else 0

    def current_page(self):
        return self._current_page

    def go_to_page(self, index, y_pt=None):
        if not self._tops:
            return
        index = max(0, min(index, len(self._tops) - 1))
        y = self._tops[index] - MARGIN
        if y_pt is not None:
            y = self._tops[index] + y_pt * self._scale() - self.viewport().height() / 3
        self.verticalScrollBar().setValue(int(y))

    def position(self):
        """(page + fraction within page, horizontal ratio) — zoom independent."""
        if not self._tops:
            return (0.0, 0.0)
        y = self.verticalScrollBar().value() + MARGIN
        i = self._page_at(y)
        h = self.doc.page_sizes[i][1] * self._scale() + PAGE_GAP
        frac = (y - self._tops[i]) / h if h else 0
        hs = self.horizontalScrollBar()
        hr = hs.value() / hs.maximum() if hs.maximum() else 0.0
        return (i + max(0.0, min(1.0, frac)), hr)

    def set_position(self, pos, hratio=0.0):
        if not self._tops:
            return
        i = int(pos)
        i = max(0, min(i, len(self._tops) - 1))
        h = self.doc.page_sizes[i][1] * self._scale() + PAGE_GAP
        self.verticalScrollBar().setValue(int(self._tops[i] + (pos - i) * h - MARGIN))
        hs = self.horizontalScrollBar()
        hs.setValue(int(hratio * hs.maximum()))

    def _page_at(self, y):
        lo, hi = 0, len(self._tops) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._tops[mid] <= y:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def _on_scroll(self, *_):
        if self._tops:
            y = self.verticalScrollBar().value() + self.viewport().height() / 3
            p = self._page_at(y)
            if p != self._current_page:
                self._current_page = p
                self.page_changed.emit(p)
        self.scrolled.emit(*self.position())
        self.viewport().update()

    # ---- painting ----------------------------------------------------------
    def _page_rect(self, i):
        s = self._scale()
        w, h = self.doc.page_sizes[i]
        pw = w * s
        x = max(MARGIN, (max(self._content_w, self.viewport().width()) - pw) / 2)
        x -= self.horizontalScrollBar().value()
        y = self._tops[i] - self.verticalScrollBar().value()
        return QRectF(x, y, pw, h * s)

    def paintEvent(self, event):
        p = QPainter(self.viewport())
        p.fillRect(self.viewport().rect(), CANVAS_BG)
        if not self.doc or not self._tops:
            p.setPen(QColor('#77706D'))
            p.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, 'PDF 파일을 열어 주세요')
            return
        vh = self.viewport().height()
        top = self.verticalScrollBar().value()
        first = self._page_at(top)
        render_zoom = self.zoom * self._dpi_scale() / (96.0 / 72.0) * (96.0 / 72.0)
        render_zoom = round(render_zoom, 2)
        s = self._scale()
        for i in range(first, len(self._tops)):
            r = self._page_rect(i)
            if r.top() > vh:
                break
            p.fillRect(r.translated(2, 2), QColor(0, 0, 0, 28))
            img = self._service.get(self.doc.path, i, render_zoom)
            if img is None:
                p.fillRect(r, QColor('white'))
            else:
                p.drawImage(r, img)
            for (x0, y0, x1, y1) in self.highlights.get(i, ()):
                hr = QRectF(r.left() + x0 * s, r.top() + y0 * s, (x1 - x0) * s, (y1 - y0) * s)
                p.fillRect(hr, QColor(255, 200, 0, 90))
                p.setPen(QPen(QColor('#A44735'), 1))
                p.drawRect(hr)
        # prefetch next page
        nxt = self._page_at(top + vh) + 1
        if nxt < len(self._tops):
            self._service.get(self.doc.path, nxt, render_zoom)

    def _on_rendered(self, key):
        if self.doc and key[0] == self.doc.path:
            self.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.doc:
            pos = self.position()
            self._relayout()
            self.set_position(*pos)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        k = event.key()
        if k in (Qt.Key.Key_PageDown,):
            self.go_to_page(self._current_page + 1)
        elif k in (Qt.Key.Key_PageUp,):
            self.go_to_page(self._current_page - 1)
        elif k == Qt.Key.Key_Home:
            self.go_to_page(0)
        elif k == Qt.Key.Key_End:
            self.go_to_page(self.page_count() - 1)
        else:
            super().keyPressEvent(event)
