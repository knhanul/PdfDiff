"""Left navigation panel with lazily rendered page thumbnails."""
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QListView, QListWidget, QListWidgetItem

from app.viewer.render_service import render_service

THUMB_ZOOM = 0.2
ICON_W, ICON_H = 110, 146
GRID_W, GRID_H = 140, 180


def _scaled_icon(img):
    pix = QPixmap.fromImage(img) if not isinstance(img, QPixmap) else img
    return QIcon(pix.scaled(
        ICON_W, ICON_H,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    ))


class NavPanel(QListWidget):
    page_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('navPanel')
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.TopToBottom)
        self.setWrapping(False)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Fixed)
        self.setUniformItemSizes(True)
        self.setIconSize(QSize(ICON_W, ICON_H))
        self.setGridSize(QSize(GRID_W, GRID_H))
        self.setSpacing(6)
        self.setFixedWidth(156)
        self.doc = None
        self._svc = render_service()
        self._svc.rendered.connect(self._on_rendered)
        self.itemClicked.connect(lambda it: self.page_selected.emit(self.row(it)))
        self.verticalScrollBar().valueChanged.connect(self._request_visible)

    def set_document(self, doc):
        self.clear()
        self.doc = doc
        if not doc:
            return
        blank = QPixmap(ICON_W, ICON_H)
        blank.fill(Qt.GlobalColor.white)
        icon = QIcon(blank)
        for i in range(doc.page_count):
            it = QListWidgetItem(icon, str(i + 1))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.addItem(it)
        self._request_visible()

    def set_current(self, page):
        if 0 <= page < self.count():
            self.blockSignals(True)
            self.setCurrentRow(page)
            self.blockSignals(False)
            self.scrollToItem(self.item(page))

    def _request_visible(self, *_):
        if not self.doc or not self.isVisible():
            return
        vp = self.viewport().rect()
        for i in range(self.count()):
            it = self.item(i)
            if not self.visualItemRect(it).intersects(vp):
                continue
            img = self._svc.get(self.doc.path, i, THUMB_ZOOM)
            if img is not None:
                it.setIcon(_scaled_icon(img))

    def _on_rendered(self, key):
        if not self.doc or key[0] != self.doc.path or key[2] != int(THUMB_ZOOM * 1000):
            return
        img = self._svc.cache.get(key)
        it = self.item(key[1])
        if img is not None and it is not None:
            it.setIcon(_scaled_icon(img))

    def showEvent(self, e):
        super().showEvent(e)
        self._request_visible()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._request_visible()
