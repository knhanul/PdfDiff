import os
from pathlib import Path

import pymupdf
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QSpinBox, QLineEdit, QGroupBox, QRadioButton, QButtonGroup, QMessageBox,
    QProgressBar, QFrame, QStyle
)

from app.common.styles import MODERN_QSS


class PdfSplitWidget(QWidget):
    """PDF 분할 도구 (페이지 범위 / N페이지마다 / 개별 추출)"""

    def __init__(self, parent=None, comparison_settings=None):
        super().__init__(parent)
        self.setStyleSheet(MODERN_QSS)
        self.pdf_path = None
        self.doc = None

        # Focus mode 호환용 (기존 코드가 참조할 수 있음)
        self.lbl_name1 = QLabel()
        self.lbl_name2 = QLabel()
        self.lbl_name1.hide()
        self.lbl_name2.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 파일 선택
        file_box = QGroupBox("PDF 파일")
        file_layout = QHBoxLayout(file_box)
        self.lbl_file = QLabel("선택된 파일 없음")
        self.lbl_file.setWordWrap(True)
        btn_open = QPushButton("파일 열기")
        btn_open.setObjectName("actionBtn")
        btn_open.clicked.connect(self.open_file)
        file_layout.addWidget(self.lbl_file, 1)
        file_layout.addWidget(btn_open)
        layout.addWidget(file_box)

        self.lbl_info = QLabel("페이지 수: -")
        layout.addWidget(self.lbl_info)

        # 분할 방식
        mode_box = QGroupBox("분할 방식")
        mode_layout = QVBoxLayout(mode_box)
        self.radio_range = QRadioButton("페이지 범위로 분할 (예: 1-5, 6-10, 11-)")
        self.radio_every = QRadioButton("N페이지마다 분할")
        self.radio_each = QRadioButton("각 페이지를 개별 파일로 추출")
        self.radio_range.setChecked(True)
        mode_layout.addWidget(self.radio_range)
        mode_layout.addWidget(self.radio_every)
        mode_layout.addWidget(self.radio_each)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("범위:"))
        self.edit_range = QLineEdit()
        self.edit_range.setPlaceholderText("1-5, 6-10, 11-")
        range_row.addWidget(self.edit_range)
        mode_layout.addLayout(range_row)

        every_row = QHBoxLayout()
        every_row.addWidget(QLabel("N페이지:"))
        self.spin_every = QSpinBox()
        self.spin_every.setRange(1, 9999)
        self.spin_every.setValue(10)
        every_row.addWidget(self.spin_every)
        every_row.addStretch()
        mode_layout.addLayout(every_row)
        layout.addWidget(mode_box)

        # 출력
        out_box = QGroupBox("출력")
        out_layout = QHBoxLayout(out_box)
        self.lbl_out = QLabel("원본과 같은 폴더에 저장")
        btn_out = QPushButton("출력 폴더 선택")
        btn_out.clicked.connect(self.select_output)
        self.output_dir = None
        out_layout.addWidget(self.lbl_out, 1)
        out_layout.addWidget(btn_out)
        layout.addWidget(out_box)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # 실행
        btn_run = QPushButton("분할 실행")
        btn_run.setObjectName("actionBtn")
        btn_run.clicked.connect(self.run_split)
        layout.addWidget(btn_run)
        layout.addStretch()

        # Bottom bar for focus mode
        self._create_bottom_bar(layout)

    def _create_bottom_bar(self, parent_layout):
        bar = QFrame()
        bar.setObjectName("actionBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 4, 8, 4)
        self.btn_switch_tool = QPushButton()  # 사용 안 함, 숨김
        self.btn_switch_tool.hide()
        self.btn_focus_mode = QPushButton()
        self.btn_focus_mode.setObjectName("secondaryBtn")
        self.btn_focus_mode.setFixedSize(40, 40)
        self.btn_focus_mode.setCheckable(True)
        self.btn_focus_mode.setToolTip("집중 모드")
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
            self.lbl_file.setText(os.path.basename(path))
            self.lbl_info.setText(f"페이지 수: {self.doc.page_count}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"PDF를 열 수 없습니다:\n{e}")

    def select_output(self):
        d = QFileDialog.getExistingDirectory(self, "출력 폴더 선택")
        if d:
            self.output_dir = d
            self.lbl_out.setText(d)

    def run_split(self):
        if not self.doc or not self.pdf_path:
            QMessageBox.warning(self, "알림", "먼저 PDF 파일을 열어주세요.")
            return

        out_dir = self.output_dir or str(Path(self.pdf_path).parent)
        base = Path(self.pdf_path).stem
        total = self.doc.page_count

        try:
            if self.radio_range.isChecked():
                self._split_by_range(out_dir, base, total)
            elif self.radio_every.isChecked():
                self._split_every_n(out_dir, base, total)
            else:
                self._split_each(out_dir, base, total)
            QMessageBox.information(self, "완료", "분할이 완료되었습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"분할 중 오류:\n{e}")
        finally:
            self.progress.setVisible(False)

    def _split_by_range(self, out_dir, base, total):
        text = self.edit_range.text().strip()
        if not text:
            raise ValueError("페이지 범위를 입력하세요. 예: 1-5, 6-10")
        ranges = []
        for part in text.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                start = int(a) - 1 if a else 0
                end = int(b) if b else total
                ranges.append((max(0, start), min(total, end)))
            else:
                p = int(part) - 1
                ranges.append((p, p + 1))
        self.progress.setVisible(True)
        self.progress.setMaximum(len(ranges))
        for i, (s, e) in enumerate(ranges):
            if s >= e or s < 0:
                continue
            new_doc = pymupdf.open()
            new_doc.insert_pdf(self.doc, from_page=s, to_page=e - 1)
            out_path = Path(out_dir) / f"{base}_p{s+1}-{e}.pdf"
            new_doc.save(str(out_path))
            new_doc.close()
            self.progress.setValue(i + 1)

    def _split_every_n(self, out_dir, base, total):
        n = self.spin_every.value()
        self.progress.setVisible(True)
        count = (total + n - 1) // n
        self.progress.setMaximum(count)
        idx = 1
        for start in range(0, total, n):
            end = min(start + n, total)
            new_doc = pymupdf.open()
            new_doc.insert_pdf(self.doc, from_page=start, to_page=end - 1)
            out_path = Path(out_dir) / f"{base}_part{idx}.pdf"
            new_doc.save(str(out_path))
            new_doc.close()
            self.progress.setValue(idx)
            idx += 1

    def _split_each(self, out_dir, base, total):
        self.progress.setVisible(True)
        self.progress.setMaximum(total)
        for i in range(total):
            new_doc = pymupdf.open()
            new_doc.insert_pdf(self.doc, from_page=i, to_page=i)
            out_path = Path(out_dir) / f"{base}_p{i+1}.pdf"
            new_doc.save(str(out_path))
            new_doc.close()
            self.progress.setValue(i + 1)

    def closeEvent(self, event):
        if self.doc:
            self.doc.close()
            self.doc = None
        super().closeEvent(event)
