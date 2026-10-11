import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QProgressBar, QPushButton, QSplitter,
    QVBoxLayout, QWidget, QLineEdit,
)

from app.common.pdf_convert import SUPPORTED_EXTS, convert_to_pdf, is_supported
from app.common.styles import MODERN_QSS


class PdfCreateWidget(QWidget):
    """한글, 오피스, 마크다운, 텍스트, 이미지를 PDF로 변환"""

    def __init__(self, parent=None, comparison_settings=None):
        super().__init__(parent)
        self.setStyleSheet(MODERN_QSS)
        self.setAcceptDrops(True)
        self.output_dir = ""
        self.paths = []

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.file_list.itemSelectionChanged.connect(self._update_count)
        left_layout.addWidget(self.file_list, 1)

        buttons = QHBoxLayout()
        for title, handler in (
            ("파일 추가", self.add_files),
            ("폴더 추가", self.add_folder),
            ("선택 삭제", self.remove_selected),
            ("전체 선택", self.select_all),
            ("선택 해제", self.clear_selection),
        ):
            button = QPushButton(title)
            if title == "파일 추가":
                button.setObjectName("actionBtn")
            button.clicked.connect(handler)
            buttons.addWidget(button)
        buttons.addStretch()
        self.count_label = QLabel("선택 0 / 전체 0")
        buttons.addWidget(self.count_label)
        left_layout.addLayout(buttons)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("한글, 오피스, 마크다운, 텍스트, 이미지를 PDF로 변환합니다.\n파일이나 폴더를 끌어다 놓은 뒤 변환할 항목을 여러 개 선택하세요.")
        hint.setWordWrap(True)
        right_layout.addWidget(hint)

        folder_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText("결과 폴더 미지정 (원본 폴더에 저장)")
        btn_folder = QPushButton("결과 폴더")
        btn_folder.clicked.connect(self.choose_output_dir)
        btn_clear = QPushButton("해제")
        btn_clear.clicked.connect(self.clear_output_dir)
        folder_row.addWidget(self.output_edit, 1)
        folder_row.addWidget(btn_folder)
        folder_row.addWidget(btn_clear)
        right_layout.addLayout(folder_row)

        self.btn_convert = QPushButton("변환 실행")
        self.btn_convert.setObjectName("actionBtn")
        self.btn_convert.clicked.connect(self.convert_selected)
        right_layout.addWidget(self.btn_convert)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        right_layout.addWidget(self.progress)

        self.status_label = QLabel("지원 형식: hwp, hwpx, doc, docx, xls, xlsx, ppt, pptx, md, txt, 이미지")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)
        right_layout.addWidget(QLabel("작업 이력"))
        self.history_list = QListWidget()
        self.history_list.setMinimumHeight(160)
        self.history_list.itemDoubleClicked.connect(self.open_history_item)
        right_layout.addWidget(self.history_list, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)
        self._create_bottom_bar(root)

    def _create_bottom_bar(self, parent_layout):
        bar = QFrame()
        bar.setObjectName("actionBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        self.btn_switch_tool = QPushButton()
        self.btn_switch_tool.hide()
        self.btn_focus_mode = QPushButton()
        self.btn_focus_mode.setObjectName("secondaryBtn")
        self.btn_focus_mode.setFixedSize(40, 40)
        self.btn_focus_mode.setCheckable(True)
        layout.addStretch()
        layout.addWidget(self.btn_focus_mode)
        parent_layout.addWidget(bar)
        self.bottom_action_bar = bar
        bar.hide()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
        self._add_paths(paths)

    def add_files(self):
        filters = "지원 파일 (" + " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTS)) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self, "변환할 파일 선택", "", filters)
        self._add_paths(paths)

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "변환할 폴더 선택", "")
        if path:
            self._add_paths([path])

    def _add_paths(self, paths):
        added = 0
        for raw in paths:
            for found in self._iter_supported(Path(raw)):
                text = str(found)
                if text in self.paths:
                    continue
                self.paths.append(text)
                item = QListWidgetItem(f"{found.name}   ({found.suffix.lower()})")
                item.setData(Qt.ItemDataRole.UserRole, text)
                item.setToolTip(text)
                self.file_list.addItem(item)
                item.setSelected(True)
                added += 1
        if added == 0 and paths:
            self.status_label.setText("추가할 수 있는 변환 파일이 없습니다.")
        self._update_count()

    def _iter_supported(self, path):
        if path.is_file() and is_supported(path):
            yield path
            return
        if not path.is_dir():
            return
        for found in path.rglob("*"):
            if found.is_file() and is_supported(found) and not any(part.startswith(".") for part in found.parts):
                yield found

    def remove_selected(self):
        rows = sorted((self.file_list.row(item) for item in self.file_list.selectedItems()), reverse=True)
        if not rows:
            QMessageBox.warning(self, "알림", "목록에서 제외할 파일을 선택하세요.")
            return
        for row in rows:
            item = self.file_list.takeItem(row)
            path = item.data(Qt.ItemDataRole.UserRole)
            if path in self.paths:
                self.paths.remove(path)
        self._update_count()

    def select_all(self):
        self.file_list.selectAll()

    def clear_selection(self):
        self.file_list.clearSelection()

    def _update_count(self):
        self.count_label.setText(f"선택 {len(self.file_list.selectedItems())} / 전체 {self.file_list.count()}")

    def choose_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "결과 폴더 선택", self.output_dir or "")
        if path:
            self.output_dir = path
            self.output_edit.setText(path)

    def clear_output_dir(self):
        self.output_dir = ""
        self.output_edit.clear()

    def _target_dir(self, src):
        if self.output_dir and os.path.isdir(self.output_dir):
            return self.output_dir
        return str(Path(src).parent)

    def convert_selected(self):
        items = self.file_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "알림", "변환할 파일을 목록에서 선택하세요.")
            return
        self.progress.setVisible(True)
        self.progress.setMaximum(len(items))
        ok = 0
        failed = []
        for index, item in enumerate(items, start=1):
            src = item.data(Qt.ItemDataRole.UserRole)
            try:
                dest = convert_to_pdf(src, self._target_dir(src))
            except Exception as error:
                failed.append(f"{Path(src).name}: {error}")
                self._add_history(f"실패 {Path(src).name}", [], str(error))
            else:
                ok += 1
                self._add_history(f"변환 {Path(src).name}", [str(dest)])
            self.progress.setValue(index)
            self.status_label.setText(f"진행 {index}/{len(items)}")
        self.progress.setVisible(False)
        if failed:
            QMessageBox.warning(self, "변환 결과", f"성공 {ok}개, 실패 {len(failed)}개\n\n" + "\n".join(failed[:8]))
        else:
            QMessageBox.information(self, "변환 결과", f"{ok}개 파일을 PDF로 저장했습니다.")
        self.status_label.setText(f"성공 {ok}개, 실패 {len(failed)}개")

    def _add_history(self, summary, paths, detail=""):
        stamp = datetime.now().strftime("%H:%M:%S")
        names = ", ".join(os.path.basename(path) for path in paths) if paths else detail
        item = QListWidgetItem(f"{stamp}  {summary}  →  {names}")
        item.setToolTip(detail or "\n".join(paths))
        item.setData(Qt.ItemDataRole.UserRole, list(paths))
        self.history_list.insertItem(0, item)

    def open_history_item(self, item):
        paths = item.data(Qt.ItemDataRole.UserRole) or []
        if paths:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(paths[0]).parent)))
