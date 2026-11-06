"""Light side-by-side view of two PDFs with synchronized scroll and zoom.

This is *not* a comparison tool; it only shows two documents together.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QMessageBox,
                             QPushButton, QSplitter, QVBoxLayout, QWidget)

from app.viewer.pdf_canvas import PdfCanvas


class _Pane(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QFrame()
        bar.setObjectName('splitPaneBar')
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 4, 8, 4)
        self.label = QLabel(title)
        self.label.setObjectName('splitPaneTitle')
        self.open_btn = QPushButton('열기…')
        self.open_btn.setObjectName('viewerToolBtn')
        self.page_label = QLabel('')
        self.page_label.setObjectName('mutedLabel')
        bl.addWidget(self.label, 1)
        bl.addWidget(self.page_label)
        bl.addWidget(self.open_btn)
        self.canvas = PdfCanvas()
        lay.addWidget(bar)
        lay.addWidget(self.canvas, 1)
        self.canvas.page_changed.connect(self._upd)

    def set_document(self, doc):
        self.canvas.set_document(doc)
        self.label.setText(doc.title if doc else '문서 없음')
        self.label.setToolTip(doc.path if doc else '')
        self._upd()

    def _upd(self, *_):
        c = self.canvas
        self.page_label.setText(f'{c.current_page() + 1} / {c.page_count()}' if c.doc else '')


class SplitView(QWidget):
    open_compare = pyqtSignal(str)   # tool key
    closed = pyqtSignal()

    def __init__(self, doc_manager, parent=None):
        super().__init__(parent)
        self.dm = doc_manager
        self._syncing = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QFrame()
        bar.setObjectName('contextToolbar')
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 4, 10, 4)
        bl.setSpacing(6)
        title = QLabel('두 PDF 동시 보기')
        title.setObjectName('contextTitle')
        self.sync_scroll = QCheckBox('스크롤 동기화')
        self.sync_scroll.setChecked(True)
        self.sync_zoom = QCheckBox('확대 동기화')
        self.sync_zoom.setChecked(True)
        btn_fit = QPushButton('폭 맞춤')
        btn_fit.setObjectName('viewerToolBtn')
        btn_fit.clicked.connect(lambda: [p.canvas.set_fit('width') for p in (self.left, self.right)])
        btn_zo = QPushButton('−')
        btn_zo.setObjectName('viewerToolBtn')
        btn_zi = QPushButton('+')
        btn_zi.setObjectName('viewerToolBtn')
        btn_zo.clicked.connect(lambda: self.left.canvas.zoom_out())
        btn_zi.clicked.connect(lambda: self.left.canvas.zoom_in())
        btn_cmp = QPushButton('영역지정비교로 열기')
        btn_cmp.setObjectName('viewerToolBtn')
        btn_cmp.clicked.connect(lambda: self.open_compare.emit('pdf_compare'))
        btn_cmp2 = QPushButton('전체비교로 열기')
        btn_cmp2.setObjectName('viewerToolBtn')
        btn_cmp2.clicked.connect(lambda: self.open_compare.emit('pdf_hf_compare'))
        btn_close = QPushButton('✕ 닫기')
        btn_close.setObjectName('viewerToolBtn')
        btn_close.clicked.connect(self.closed.emit)
        for w in (title, self.sync_scroll, self.sync_zoom, btn_zo, btn_zi, btn_fit):
            bl.addWidget(w)
        bl.addStretch()
        for w in (btn_cmp, btn_cmp2, btn_close):
            bl.addWidget(w)
        lay.addWidget(bar)

        self.left = _Pane('왼쪽 문서')
        self.right = _Pane('오른쪽 문서')
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(self.left)
        sp.addWidget(self.right)
        sp.setChildrenCollapsible(False)
        lay.addWidget(sp, 1)

        self.left.open_btn.clicked.connect(lambda: self._pick(self.left))
        self.right.open_btn.clicked.connect(lambda: self._pick(self.right))
        for a, b in ((self.left, self.right), (self.right, self.left)):
            a.canvas.scrolled.connect(lambda pos, hr, b=b: self._sync_scroll(b, pos, hr))
            a.canvas.zoom_changed.connect(lambda z, a=a, b=b: self._sync_zoom(a, b, z))

    def paths(self):
        return [p.canvas.doc.path if p.canvas.doc else None for p in (self.left, self.right)]

    def set_documents(self, left=None, right=None):
        if left is not None:
            self.left.set_document(left)
        if right is not None:
            self.right.set_document(right)

    def _pick(self, pane):
        from app.shell.open_doc_picker import pick_document
        path = pick_document(self, self.dm, title='열린 문서에서 선택')
        if not path:
            return
        try:
            doc, _ = self.dm.open(path)
        except Exception as e:
            QMessageBox.warning(self, 'PDF 열기 실패', str(e))
            return
        pane.set_document(doc)

    def _sync_scroll(self, target, pos, hr):
        if self._syncing or not self.sync_scroll.isChecked():
            return
        self._syncing = True
        try:
            target.canvas.set_position(pos, hr)
        finally:
            self._syncing = False

    def _sync_zoom(self, src, target, z):
        if self._syncing or not self.sync_zoom.isChecked():
            return
        self._syncing = True
        try:
            target.canvas.fit_mode = src.canvas.fit_mode
            target.canvas.set_zoom(z, keep_fit=src.canvas.fit_mode is not None)
        finally:
            self._syncing = False
