import os
from pathlib import Path

import pymupdf
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QListWidget, QListWidgetItem, QMessageBox, QFrame, QGroupBox, QCheckBox
)

from app.common.styles import MODERN_QSS


class PdfPageEditorWidget(QWidget):
    """페이지 추출 / 삭제 / 재정렬"""

    def __init__(self, parent=None, comparison_settings=None):
        super().__init__(parent)
        self.setStyleSheet(MODERN_QSS)
        self.pdf_path = None
        self.doc = None
        self.page_order = []  # list of original page indices (0-based)

        self.lbl_name1 = QLabel()
        self.lbl_name2 = QLabel()
        self.lbl_name1.hide()
        self.lbl_name2.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 파일
        file_row = QHBoxLayout()
        self.lbl_file = QLabel("선택된 파일 없음")
        btn_open = QPushButton("PDF 열기")
        btn_open.setObjectName("actionBtn")
        btn_open.clicked.connect(self.open_file)
        file_row.addWidget(self.lbl_file, 1)
        file_row.addWidget(btn_open)
        layout.addLayout(file_row)

        self.lbl_info = QLabel("페이지: -")
        layout.addWidget(self.lbl_info)

        # 페이지 목록
        page_box = QGroupBox("페이지 목록 (체크 = 선택)")
        page_layout = QVBoxLayout(page_box)
        self.list_widget = QListWidget()
        page_layout.addWidget(self.list_widget)

        ctrl_row = QHBoxLayout()
        btn_all = QPushButton("전체 선택")
        btn_all.clicked.connect(self.select_all)
        btn_none = QPushButton("선택 해제")
        btn_none.clicked.connect(self.select_none)
        btn_up = QPushButton("위로")
        btn_up.clicked.connect(self.move_up)
        btn_down = QPushButton("아래로")
        btn_down.clicked.connect(self.move_down)
        ctrl_row.addWidget(btn_all)
        ctrl_row.addWidget(btn_none)
        ctrl_row.addWidget(btn_up)
        ctrl_row.addWidget(btn_down)
        ctrl_row.addStretch()
        page_layout.addLayout(ctrl_row)
        layout.addWidget(page_box)

        # 작업 버튼
        action_row = QHBoxLayout()
        btn_extract = QPushButton("선택 페이지 추출")
        btn_extract.setObjectName("actionBtn")
        btn_extract.clicked.connect(self.extract_selected)
        btn_delete = QPushButton("선택 페이지 삭제")
        btn_delete.clicked.connect(self.delete_selected)
        btn_save = QPushButton("현재 순서로 저장")
        btn_save.setObjectName("actionBtn")
        btn_save.clicked.connect(self.save_current_order)
        action_row.addWidget(btn_extract)
        action_row.addWidget(btn_delete)
        action_row.addWidget(btn_save)
        layout.addLayout(action_row)
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

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "PDF 선택", "", "PDF Files (*.pdf)")
        if not path:
            return
        try:
            if self.doc:
                self.doc.close()
            self.doc = pymupdf.open(path)
            self.pdf_path = path
            self.page_order = list(range(self.doc.page_count))
            self.lbl_file.setText(os.path.basename(path))
            self.lbl_info.setText(f"총 {self.doc.page_count} 페이지")
            self._refresh_list()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"PDF를 열 수 없습니다:\n{e}")

    def _refresh_list(self):
        self.list_widget.clear()
        for idx in self.page_order:
            item = QListWidgetItem(f"페이지 {idx + 1}")
            item.setData(Qt.ItemDataRole.UserRole, idx)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)

    def select_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Checked)

    def select_none(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _selected_indices(self):
        """현재 리스트에서 체크된 항목의 원본 페이지 인덱스 반환"""
        result = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    def move_up(self):
        row = self.list_widget.currentRow()
        if row > 0:
            self.page_order[row], self.page_order[row - 1] = self.page_order[row - 1], self.page_order[row]
            self._refresh_list()
            self.list_widget.setCurrentRow(row - 1)

    def move_down(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.page_order) - 1:
            self.page_order[row], self.page_order[row + 1] = self.page_order[row + 1], self.page_order[row]
            self._refresh_list()
            self.list_widget.setCurrentRow(row + 1)

    def extract_selected(self):
        selected = self._selected_indices()
        if not selected:
            QMessageBox.warning(self, "알림", "추출할 페이지를 체크해주세요.")
            return
        if not self.doc:
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "추출 파일 저장", "extracted.pdf", "PDF Files (*.pdf)")
        if not save_path:
            return
        try:
            out = pymupdf.open()
            for idx in selected:
                out.insert_pdf(self.doc, from_page=idx, to_page=idx)
            out.save(save_path)
            out.close()
            QMessageBox.information(self, "완료", f"추출 완료:\n{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    def delete_selected(self):
        selected = set(self._selected_indices())
        if not selected:
            QMessageBox.warning(self, "알림", "삭제할 페이지를 체크해주세요.")
            return
        if len(selected) == len(self.page_order):
            QMessageBox.warning(self, "알림", "모든 페이지를 삭제할 수 없습니다.")
            return
        reply = QMessageBox.question(
            self, "확인",
            f"선택한 {len(selected)}개 페이지를 목록에서 제거합니다.\n(원본 파일은 변경되지 않습니다)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.page_order = [i for i in self.page_order if i not in selected]
        self._refresh_list()
        self.lbl_info.setText(f"현재 {len(self.page_order)} 페이지")

    def save_current_order(self):
        if not self.doc or not self.page_order:
            QMessageBox.warning(self, "알림", "저장할 페이지가 없습니다.")
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "저장", "edited.pdf", "PDF Files (*.pdf)")
        if not save_path:
            return
        try:
            out = pymupdf.open()
            for idx in self.page_order:
                out.insert_pdf(self.doc, from_page=idx, to_page=idx)
            out.save(save_path)
            out.close()
            QMessageBox.information(self, "완료", f"저장 완료:\n{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    def closeEvent(self, event):
        if self.doc:
            self.doc.close()
            self.doc = None
        super().closeEvent(event)
