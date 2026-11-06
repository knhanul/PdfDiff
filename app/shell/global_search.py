"""Screen 6 — 열린 모든 PDF에서 찾기 (결과를 파일별로 묶어 표시).

Runs on the UI thread against the main-thread PdfDocument objects (no cross-thread sharing).
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout

MAX_HITS_PER_DOC = 200
SNIPPET = 36


def _snippet(doc, page, rect):
    try:
        import pymupdf
        pg = doc._doc[page]
        r = pymupdf.Rect(rect)
        line = pymupdf.Rect(pg.rect.x0, r.y0 - 1, pg.rect.x1, r.y1 + 1)
        text = ' '.join(pg.get_textbox(line).split())
        return text[:SNIPPET * 2]
    except Exception:
        return ''


def search_documents(docs, text, max_hits=MAX_HITS_PER_DOC):
    """[(doc, [(page, rect, snippet), ...]), ...] — only docs with hits."""
    out = []
    for doc in docs:
        hits = doc.search(text, max_hits=max_hits)
        if hits:
            out.append((doc, [(p, r, _snippet(doc, p, r)) for p, r in hits]))
    return out


class GlobalSearchPanel(QFrame):
    result_activated = pyqtSignal(str, int, object)  # path, page, rect
    closed = pyqtSignal()

    def __init__(self, docs_provider, parent=None):
        super().__init__(parent)
        self.setObjectName('globalSearchPanel')
        self.setMinimumWidth(260)
        self.setMaximumWidth(360)
        self._docs = docs_provider
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        head = QHBoxLayout()
        t = QLabel('열린 PDF 전체에서 찾기')
        t.setObjectName('sectionLabel')
        x = QPushButton('✕')
        x.setObjectName('viewerToolBtn')
        x.setFixedWidth(28)
        x.clicked.connect(self.closed.emit)
        head.addWidget(t, 1)
        head.addWidget(x)
        lay.addLayout(head)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText('찾을 내용 입력 후 Enter')
        self.edit.returnPressed.connect(self.run)
        lay.addWidget(self.edit)
        self.info = QLabel('')
        self.info.setObjectName('mutedLabel')
        lay.addWidget(self.info)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemActivated.connect(self._activate)
        self.tree.itemClicked.connect(self._activate)
        lay.addWidget(self.tree, 1)

    def focus_input(self):
        self.edit.setFocus()
        self.edit.selectAll()

    def run(self):
        text = self.edit.text().strip()
        self.tree.clear()
        if not text:
            self.info.setText('')
            return []
        docs = list(self._docs())
        results = search_documents(docs, text)
        total = 0
        for doc, hits in results:
            top = QTreeWidgetItem([f'{doc.title}  ({len(hits)})'])
            top.setToolTip(0, doc.path)
            self.tree.addTopLevelItem(top)
            for page, rect, snip in hits:
                it = QTreeWidgetItem([f'{page + 1}쪽  {snip}'])
                it.setData(0, Qt.ItemDataRole.UserRole, (doc.path, page, rect))
                top.addChild(it)
            top.setExpanded(True)
            total += len(hits)
        self.info.setText(f'{len(docs)}개 문서 중 {len(results)}개 문서에서 {total}건' if total else '결과 없음')
        return results

    def _activate(self, item, _col=0):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            self.result_activated.emit(*data)
