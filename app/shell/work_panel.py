"""Right-hand work panel (closed by default) for 정보 / 편집 / 입력폼 modes.

Each mode also gets a slim situational toolbar above the canvas (built by ViewerWorkspace).
The panel never edits PDFs itself; it hands off to existing tools via signals.
"""
import os

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QFormLayout, QFrame, QHBoxLayout, QLabel, QListWidget, QPushButton,
                             QStackedWidget, QVBoxLayout, QWidget)

MODES = {'info': '문서 정보', 'edit': 'PDF 편집', 'form': '입력 항목'}


class WorkPanel(QFrame):
    tool_requested = pyqtSignal(str)       # tool key
    closed = pyqtSignal()
    field_selected = pyqtSignal(int)        # page

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('workPanel')
        self.setFixedWidth(300)
        self.mode = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        head = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName('sectionLabel')
        x = QPushButton('✕')
        x.setObjectName('viewerToolBtn')
        x.setFixedWidth(28)
        x.setToolTip('작업 패널 닫기')
        x.clicked.connect(self.closed.emit)
        head.addWidget(self.title, 1)
        head.addWidget(x)
        lay.addLayout(head)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.pages = {'info': self._info_page(), 'edit': self._edit_page(), 'form': self._form_page()}
        for w in self.pages.values():
            self.stack.addWidget(w)
        self.hide()

    def _btn(self, text, key):
        b = QPushButton(text)
        b.setObjectName('viewerToolBtn')
        b.clicked.connect(lambda: self.tool_requested.emit(key))
        return b

    def _info_page(self):
        w = QWidget()
        self.info_form = QFormLayout(w)
        self.info_labels = {}
        for k in ('파일', '폴더', '쪽수', '크기', '입력 항목'):
            lbl = QLabel('-')
            lbl.setWordWrap(True)
            self.info_labels[k] = lbl
            self.info_form.addRow(k, lbl)
        return w

    def _edit_page(self):
        w = QWidget()
        v = QVBoxLayout(w)
        d = QLabel('분할·병합·페이지 회전/이동은 「PDF 편집」 도구에서 합니다. 현재 문서를 그대로 넘겨 엽니다.')
        d.setWordWrap(True)
        d.setObjectName('mutedLabel')
        v.addWidget(d)
        v.addWidget(self._btn('PDF 편집 열기', 'pdf_editor'))
        v.addWidget(self._btn('PDF 생성 (변환·추출)', 'pdf_create'))
        v.addWidget(self._btn('영역지정비교로 보내기', 'pdf_compare'))
        v.addStretch()
        return w

    def _form_page(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.form_info = QLabel()
        self.form_info.setObjectName('mutedLabel')
        self.form_info.setWordWrap(True)
        v.addWidget(self.form_info)
        self.field_list = QListWidget()
        self.field_list.itemClicked.connect(lambda it: self.field_selected.emit(it.data(256)))
        v.addWidget(self.field_list, 1)
        v.addWidget(self._btn('PDF 입력폼 관리에서 작성·생성·추출', 'pdf_form'))
        return w

    def open_mode(self, mode, doc):
        self.mode = mode
        self.title.setText(MODES[mode])
        self.stack.setCurrentWidget(self.pages[mode])
        self.refresh(doc)
        self.show()

    def close_panel(self):
        self.mode = None
        self.hide()

    def refresh(self, doc):
        if doc is None:
            return
        if self.mode == 'info':
            size = os.path.getsize(doc.path) if os.path.isfile(doc.path) else 0
            vals = {'파일': doc.title, '폴더': os.path.dirname(doc.path), '쪽수': f'{doc.page_count}쪽',
                    '크기': f'{size / 1024 / 1024:.2f} MB', '입력 항목': f'{doc.form_field_count()}개'}
            for k, v in vals.items():
                self.info_labels[k].setText(v)
        elif self.mode == 'form':
            from PyQt6.QtWidgets import QListWidgetItem
            self.field_list.clear()
            fields = doc.form_fields() if hasattr(doc, 'form_fields') else []
            for name, page in fields:
                it = QListWidgetItem(f'{page + 1}쪽 · {name}')
                it.setData(256, page)
                self.field_list.addItem(it)
            self.form_info.setText(f'입력 항목 {len(fields)}개. 항목을 누르면 해당 쪽으로 이동합니다.'
                                   if fields else '이 문서에는 입력 항목이 없습니다.')
