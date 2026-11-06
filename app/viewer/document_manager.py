"""Single source of truth for open PDF documents."""
import os

from PyQt6.QtCore import QObject, pyqtSignal


class DocumentManager(QObject):
    document_opened = pyqtSignal(object)
    document_closed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._docs = {}

    def open(self, path):
        path = os.path.abspath(path)
        if path in self._docs:
            return self._docs[path], False
        from app.viewer.document import PdfDocument  # lazy (imports pymupdf)
        doc = PdfDocument(path)
        self._docs[path] = doc
        self.document_opened.emit(doc)
        return doc, True

    def get(self, path):
        return self._docs.get(os.path.abspath(path))

    def close(self, path):
        doc = self._docs.pop(os.path.abspath(path), None)
        if doc:
            doc.close()
            from app.viewer.render_service import render_service
            render_service().forget(doc.path)
            self.document_closed.emit(doc.path)

    def paths(self):
        return list(self._docs)

    def close_all(self):
        for p in list(self._docs):
            self.close(p)
