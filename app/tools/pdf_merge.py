import os
from pathlib import Path

import pymupdf
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QListWidget, QListWidgetItem, QMessageBox, QFrame, QGroupBox
)

from app.common.styles import MODERN_QSS


class PdfMergeWidget(QWidget):
    """여러 PDF를 순서대로 병합"""

    def __init__(self, parent=None, comparison_settings=None):
        super().__init__(parent)
        self.setStyleSheet(MODERN_QSS)
        self.file_paths = []  # ordered list of paths

        self.lbl_name1 = QLabel()
        self.lbl_name2 = QLabel()
        self.lbl_name1.hide()
        self.lbl_name2.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        info = QLabel("병합할 PDF 파일들을 추가한 후 순서를 조정하세요. 위에서부터 순서대로 병합됩니다.")
        info.setWordWrap(True)
        layout.addWidget(info)

        list_box = QGroupBox("파일 목록")
        list_layout = QVBoxLayout(list_box)
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        list_layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("파일 추가")
        btn_add.setObjectName("actionBtn")
        btn_add.clicked.connect(self.add_files)
        btn_remove = QPushButton("선택 삭제")
        btn_remove.clicked.connect(self.remove_selected)
        btn_up = QPushButton("위로")
        btn_up.clicked.connect(self.move_up)
        btn_down = QPushButton("아래로")
        btn_down.clicked.connect(self.move_down)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_remove)
        btn_row.addWidget(btn_up)
        btn_row.addWidget(btn_down)
        btn_row.addStretch()
        list_layout.addLayout(btn_row)
        layout.addWidget(list_box)

        btn_merge = QPushButton("병합 후 저장")
        btn_merge.setObjectName("actionBtn")
        btn_merge.clicked.connect(self.merge_and_save)
        layout.addWidget(btn_merge)
        layout.addStretch()

        self._create_bottom_bar(layout)

    def _create_bottom_bar(self, parent_layout):
        bar = QFrame()
        bar.setObjectName("actionBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 4, 8, 4)
        self.btn_switch_tool = QPushButton()
        self.btn_switch_tool.hide()
        self.btn_focus_mode = QPushButton()
        self.btn_focus_mode.setObjectName("secondaryBtn")
        self.btn_focus_mode.setFixedSize(40, 40)
        self.btn_focus_mode.setCheckable(True)
        bl.addStretch()
        bl.addWidget(self.btn_focus_mode)
        parent_layout.addWidget(bar)
        self.bottom_action_bar = bar

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "PDF 선택", "", "PDF Files (*.pdf)")
        for path in paths:
            if path not in self.file_paths:
                self.file_paths.append(path)
                item = QListWidgetItem(os.path.basename(path))
                item.setData(Qt.ItemDataRole.UserRole, path)
                self.list_widget.addItem(item)

    def remove_selected(self):
        for item in self.list_widget.selectedItems():
            path = item.data(Qt.ItemDataRole.UserRole)
            if path in self.file_paths:
                self.file_paths.remove(path)
            self.list_widget.takeItem(self.list_widget.row(item))

    def move_up(self):
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row - 1, item)
            self.list_widget.setCurrentRow(row - 1)
            self._sync_paths()

    def move_down(self):
        row = self.list_widget.currentRow()
        if 0 <= row < self.list_widget.count() - 1:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row + 1, item)
            self.list_widget.setCurrentRow(row + 1)
            self._sync_paths()

    def _sync_paths(self):
        self.file_paths = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            self.file_paths.append(item.data(Qt.ItemDataRole.UserRole))

    def merge_and_save(self):
        self._sync_paths()
        if len(self.file_paths) < 2:
            QMessageBox.warning(self, "알림", "병합할 PDF를 2개 이상 추가해주세요.")
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, "병합 파일 저장", "merged.pdf", "PDF Files (*.pdf)"
        )
        if not save_path:
            return

        try:
            out_doc = pymupdf.open()
            for path in self.file_paths:
                src = pymupdf.open(path)
                out_doc.insert_pdf(src)
                src.close()
            out_doc.save(save_path)
            out_doc.close()
            QMessageBox.information(self, "완료", f"병합 완료:\n{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"병합 중 오류:\n{e}")
