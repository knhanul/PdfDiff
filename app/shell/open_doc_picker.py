"""공통: 열린 PDF 목록에서 고르거나 파일에서 열기."""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)


class OpenDocPicker(QDialog):
    """열린 문서 목록 + 「파일에서 열기…」. 선택 시 accept, 취소 시 reject."""

    ROLE_PATH = Qt.ItemDataRole.UserRole

    def __init__(self, docs: list[tuple[str, str]], title: str = '열린 문서에서 선택', parent=None):
        super().__init__(parent)
        self.setObjectName('openDocPicker')
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self.setMinimumHeight(280)
        self._path: str | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        hint = QLabel('이미 열린 PDF 중에서 고르거나, 아래에서 파일을 여세요.')
        hint.setObjectName('mutedLabel')
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.list = QListWidget()
        self.list.setObjectName('openDocList')
        for doc_title, path in docs:
            it = QListWidgetItem(doc_title)
            it.setData(self.ROLE_PATH, path)
            it.setToolTip(path)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemActivated.connect(self._accept_item)
        lay.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.btn_file = QPushButton('파일에서 열기…')
        self.btn_file.setObjectName('viewerToolBtn')
        self.btn_file.clicked.connect(self._from_file)
        row.addWidget(self.btn_file)
        row.addStretch()
        btn_cancel = QPushButton('취소')
        btn_cancel.setObjectName('viewerToolBtn')
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton('선택')
        btn_ok.setObjectName('primaryBtn')
        btn_ok.clicked.connect(self._accept_current)
        row.addWidget(btn_cancel)
        row.addWidget(btn_ok)
        lay.addLayout(row)

    def selected_path(self) -> str | None:
        return self._path

    def _accept_item(self, item: QListWidgetItem):
        path = item.data(self.ROLE_PATH)
        if path:
            self._path = path
            self.accept()

    def _accept_current(self):
        it = self.list.currentItem()
        if it:
            self._accept_item(it)

    def _from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'PDF 열기', '', 'PDF 파일 (*.pdf)')
        if path:
            self._path = path
            self.accept()


def _doc_entries(doc_manager, exclude_paths=None) -> list[tuple[str, str]]:
    exclude = {os.path.abspath(p) for p in (exclude_paths or []) if p}
    out = []
    for path in doc_manager.paths():
        if path in exclude:
            continue
        doc = doc_manager.get(path)
        title = doc.title if doc else os.path.basename(path)
        out.append((title, path))
    return out


def pick_document(parent: QWidget | None, doc_manager, title: str = '열린 문서에서 선택',
                  exclude_paths=None) -> str | None:
    """열린 문서 피커. 취소·닫기면 None. 열린 문서가 없으면 바로 파일 대화상자.

    「파일에서 열기…」로 고른 경로도 반환한다.
    """
    docs = _doc_entries(doc_manager, exclude_paths)
    if not docs:
        path, _ = QFileDialog.getOpenFileName(parent, 'PDF 열기', '', 'PDF 파일 (*.pdf)')
        return path or None
    dlg = OpenDocPicker(docs, title=title, parent=parent)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    return dlg.selected_path()
