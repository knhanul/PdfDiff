import os
import tempfile
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QEvent, QFileInfo, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QFileIconProvider, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.common.pdf_convert import SUPPORTED_EXTS, convert_to_pdf, is_supported, merge_pdfs, unique_pdf_path
from app.common.styles import COLOR_BORDER, COLOR_PRIMARY, COLOR_SIDEBAR_BG, COLOR_TEXT_PRIMARY, MODERN_QSS
from app.common.user_prefs import load_dir, save_dir

CREATE_OUTPUT_KEY = "output/pdf_create"
COLUMNS = ("", "파일명", "파일유형", "수정일자", "크기", "경로")


class _SortValueItem(QTableWidgetItem):
    def __lt__(self, other):
        left = self.data(Qt.ItemDataRole.UserRole)
        right = other.data(Qt.ItemDataRole.UserRole)
        if left is not None and right is not None:
            return left < right
        return super().__lt__(other)


class CheckBoxHeader(QHeaderView):
    clicked_all = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setSectionsMovable(True)
        self.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setStretchLastSection(True)
        self.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.box = QCheckBox(self)
        self.box.setTristate(True)
        self.box.installEventFilter(self)
        self.sectionResized.connect(lambda *_: self.place_box())
        self.sectionMoved.connect(lambda *_: self.place_box())

    def eventFilter(self, obj, event):
        if obj is self.box and event.type() == QEvent.Type.MouseButtonRelease:
            self.clicked_all.emit()
            return True
        return super().eventFilter(obj, event)

    def set_state(self, state):
        self.box.blockSignals(True)
        self.box.setCheckState(state)
        self.box.blockSignals(False)

    def mousePressEvent(self, event):
        if self.logicalIndexAt(event.position().toPoint()) == 0:
            event.accept()
            return
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.place_box()

    def place_box(self):
        size = 18
        x = self.sectionViewportPosition(0)
        width = self.sectionSize(0)
        self.box.setGeometry(x + max(0, (width - size) // 2), max(0, (self.height() - size) // 2), size, size)
        self.box.raise_()


class PdfCreateWidget(QWidget):
    """한글, 오피스, 마크다운, 텍스트, 이미지를 PDF로 변환"""

    def __init__(self, parent=None, comparison_settings=None):
        super().__init__(parent)
        self.setStyleSheet(MODERN_QSS)
        self.setAcceptDrops(True)
        self.output_dir = ""
        self.paths = []
        self._updating_checks = False
        self._splitter_ready = False
        self.icon_provider = QFileIconProvider()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.file_table = QTableWidget(0, len(COLUMNS))
        self.header = CheckBoxHeader(self.file_table)
        self.file_table.setHorizontalHeader(self.header)
        self.file_table.setHorizontalHeaderLabels(COLUMNS)
        self.header.clicked_all.connect(self._toggle_all_checks)
        self.file_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.file_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.file_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.file_table.setShowGrid(False)
        self.file_table.setAlternatingRowColors(True)
        self.file_table.setIconSize(QSize(20, 20))
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setSortingEnabled(True)
        self.header.setSortIndicator(1, Qt.SortOrder.AscendingOrder)
        self.file_table.itemChanged.connect(self._on_item_changed)
        self.file_table.cellClicked.connect(self._on_cell_clicked)
        self.file_table.setColumnWidth(0, 40)
        self.file_table.setColumnWidth(1, 220)
        self.file_table.setColumnWidth(2, 140)
        self.file_table.setColumnWidth(3, 140)
        self.file_table.setColumnWidth(4, 80)
        self._style_file_table()
        left_layout.addWidget(self.file_table, 1)

        buttons = QHBoxLayout()
        for title, handler in (
            ("파일 추가", self.add_files),
            ("폴더 추가", self.add_folder),
            ("체크 삭제", self.remove_checked),
        ):
            button = QPushButton(title)
            if title == "파일 추가":
                button.setObjectName("actionBtn")
            button.clicked.connect(handler)
            buttons.addWidget(button)
        buttons.addStretch()
        self.count_label = QLabel("체크 0 / 전체 0")
        buttons.addWidget(self.count_label)
        left_layout.addLayout(buttons)
        self.splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("불러온 파일은 모두 체크됩니다. 변환하지 않을 파일은 체크를 끄세요.\n체크한 파일만 PDF로 만들고, 행을 클릭해도 하이라이트되지 않습니다.")
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
        saved_dir = load_dir(CREATE_OUTPUT_KEY)
        if saved_dir:
            self.output_dir = saved_dir
            self.output_edit.setText(saved_dir)

        action_row = QHBoxLayout()
        self.btn_convert = QPushButton("변환 실행")
        self.btn_convert.setObjectName("actionBtn")
        self.btn_convert.clicked.connect(self.convert_checked)
        self.merge_toggle = QPushButton("한 개 파일로 병합")
        self.merge_toggle.setCheckable(True)
        self.merge_toggle.setToolTip("켜면 체크한 파일을 목록 순서대로 하나의 PDF로 합칩니다.")
        self.merge_toggle.toggled.connect(self._style_merge_toggle)
        action_row.addWidget(self.btn_convert)
        action_row.addWidget(self.merge_toggle)
        right_layout.addLayout(action_row)

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
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 12)
        self.splitter.setStretchFactor(1, 13)
        root.addWidget(self.splitter, 1)
        self._create_bottom_bar(root)
        self._style_merge_toggle(False)

    def _style_file_table(self):
        self.file_table.setStyleSheet(f"""
            QTableWidget {{
                background: white;
                alternate-background-color: #FFF8F2;
                border: 1px solid {COLOR_BORDER};
                selection-background-color: transparent;
                selection-color: {COLOR_TEXT_PRIMARY};
                outline: none;
            }}
            QTableWidget::item {{
                border: none;
                padding: 2px 4px;
            }}
            QHeaderView::section {{
                background-color: {COLOR_SIDEBAR_BG};
                color: {COLOR_TEXT_PRIMARY};
                font-weight: 600;
                border: none;
                border-right: 1px solid #FFD4A8;
                border-bottom: 2px solid {COLOR_PRIMARY};
                padding: 6px 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1.5px solid #C6C6C8;
                border-radius: 5px;
                background: white;
            }}
            QCheckBox::indicator:checked {{
                background: {COLOR_PRIMARY};
                border: 1.5px solid {COLOR_PRIMARY};
            }}
            QCheckBox::indicator:indeterminate {{
                background: rgba(255, 107, 0, 0.35);
                border: 1.5px solid {COLOR_PRIMARY};
            }}
        """)

    def _style_merge_toggle(self, checked):
        if checked:
            self.merge_toggle.setStyleSheet(
                f"background:{COLOR_PRIMARY}; color:white; border:none; border-radius:10px; padding:8px 14px; font-weight:600;"
            )
        else:
            self.merge_toggle.setStyleSheet("")

    def showEvent(self, event):
        super().showEvent(event)
        if not self._splitter_ready:
            self._splitter_ready = True
            self._apply_splitter_width()

    def _apply_splitter_width(self):
        total = self.splitter.width()
        if total < 100:
            return
        left = int(total * 12 / 25)
        self.splitter.setSizes([left, total - left])

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
        self.file_table.setSortingEnabled(False)
        for raw in paths:
            for found in self._iter_supported(Path(raw)):
                text = str(found.resolve())
                if text in self.paths:
                    continue
                self._append_row(found, text)
                added += 1
        self.file_table.setSortingEnabled(True)
        self._sync_header_check()
        if added == 0 and paths:
            self.status_label.setText("추가할 수 있는 변환 파일이 없습니다.")
        self._update_count()

    def _append_row(self, found, text):
        info = QFileInfo(text)
        stat = found.stat()
        check_item = QTableWidgetItem()
        check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        check_item.setCheckState(Qt.CheckState.Checked)
        name_item = QTableWidgetItem(self.icon_provider.icon(info), found.name)
        name_item.setData(Qt.ItemDataRole.UserRole, text)
        name_item.setToolTip(text)
        type_item = QTableWidgetItem(self.icon_provider.type(info) or found.suffix.lower())
        modified = datetime.fromtimestamp(stat.st_mtime)
        date_item = _SortValueItem(modified.strftime("%Y-%m-%d %H:%M"))
        date_item.setData(Qt.ItemDataRole.UserRole, stat.st_mtime)
        size_item = _SortValueItem(self._format_size(stat.st_size))
        size_item.setData(Qt.ItemDataRole.UserRole, stat.st_size)
        size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        path_item = QTableWidgetItem(str(found.parent))
        path_item.setToolTip(str(found.parent))
        row = self.file_table.rowCount()
        self.file_table.insertRow(row)
        enabled = Qt.ItemFlag.ItemIsEnabled
        for column, item in enumerate((check_item, name_item, type_item, date_item, size_item, path_item)):
            if column != 0:
                item.setFlags(enabled)
            self.file_table.setItem(row, column, item)
        self.paths.append(text)

    def _format_size(self, size):
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                if unit == "B":
                    return f"{int(value)} B"
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{int(size)} B"

    def _iter_supported(self, path):
        if path.is_file() and is_supported(path):
            yield path
            return
        if not path.is_dir():
            return
        for found in path.rglob("*"):
            if found.is_file() and is_supported(found) and not any(part.startswith(".") for part in found.parts):
                yield found

    def _checked_paths(self):
        paths = []
        for row in range(self.file_table.rowCount()):
            check = self.file_table.item(row, 0)
            name = self.file_table.item(row, 1)
            if check and name and check.checkState() == Qt.CheckState.Checked:
                paths.append(name.data(Qt.ItemDataRole.UserRole))
        return paths

    def _checked_count(self):
        count = 0
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                count += 1
        return count

    def _on_cell_clicked(self, row, column):
        if column == 0 or self._updating_checks:
            return
        item = self.file_table.item(row, 0)
        if item is None:
            return
        item.setCheckState(
            Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
        )

    def _on_item_changed(self, item):
        if self._updating_checks or item.column() != 0:
            return
        self._sync_header_check()
        self._update_count()

    def _toggle_all_checks(self):
        total = self.file_table.rowCount()
        self._set_all_checks(self._checked_count() < total)

    def _set_all_checks(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._updating_checks = True
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item is not None:
                item.setCheckState(state)
        self._updating_checks = False
        self._sync_header_check()
        self._update_count()

    def _sync_header_check(self):
        total = self.file_table.rowCount()
        checked = self._checked_count()
        if total == 0 or checked == 0:
            state = Qt.CheckState.Unchecked
        elif checked == total:
            state = Qt.CheckState.Checked
        else:
            state = Qt.CheckState.PartiallyChecked
        self.header.set_state(state)

    def remove_checked(self):
        rows = []
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                rows.append(row)
        if not rows:
            QMessageBox.warning(self, "알림", "목록에서 뺄 파일을 체크하세요.")
            return
        for row in reversed(rows):
            name = self.file_table.item(row, 1)
            path = name.data(Qt.ItemDataRole.UserRole) if name else None
            self.file_table.removeRow(row)
            if path in self.paths:
                self.paths.remove(path)
        self._sync_header_check()
        self._update_count()

    def _update_count(self):
        self.count_label.setText(f"체크 {self._checked_count()} / 전체 {self.file_table.rowCount()}")

    def choose_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "결과 폴더 선택", self.output_dir or "")
        if path:
            self.output_dir = path
            self.output_edit.setText(path)
            save_dir(CREATE_OUTPUT_KEY, path)

    def clear_output_dir(self):
        self.output_dir = ""
        self.output_edit.clear()
        save_dir(CREATE_OUTPUT_KEY, "")

    def _target_dir(self, src):
        if self.output_dir and os.path.isdir(self.output_dir):
            return self.output_dir
        return str(Path(src).parent)

    def convert_checked(self):
        paths = self._checked_paths()
        if not paths:
            QMessageBox.warning(self, "알림", "PDF로 만들 파일을 체크하세요.")
            return
        self.progress.setVisible(True)
        self.progress.setMaximum(len(paths))
        ok = 0
        failed = []
        if self.merge_toggle.isChecked():
            self._convert_merged(paths, failed)
            ok = 0 if failed else 1
        else:
            for index, src in enumerate(paths, start=1):
                try:
                    dest = convert_to_pdf(src, self._target_dir(src))
                except Exception as error:
                    failed.append(f"{Path(src).name}: {error}")
                    self._add_history(f"실패 {Path(src).name}", [], str(error))
                else:
                    ok += 1
                    self._add_history(f"변환 {Path(src).name}", [str(dest)])
                self.progress.setValue(index)
                self.status_label.setText(f"진행 {index}/{len(paths)}")
        self.progress.setVisible(False)
        if failed:
            QMessageBox.warning(self, "변환 결과", f"성공 {ok}개, 실패 {len(failed)}개\n\n" + "\n".join(failed[:8]))
        elif self.merge_toggle.isChecked():
            QMessageBox.information(self, "변환 결과", "체크한 파일을 하나의 PDF로 저장했습니다.")
        else:
            QMessageBox.information(self, "변환 결과", f"{ok}개 파일을 PDF로 저장했습니다.")
        self.status_label.setText(f"성공 {ok}개, 실패 {len(failed)}개")

    def _convert_merged(self, paths, failed):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdfs = []
            for index, src in enumerate(paths, start=1):
                try:
                    pdfs.append(str(convert_to_pdf(src, temp_dir)))
                except Exception as error:
                    failed.append(f"{Path(src).name}: {error}")
                    self._add_history(f"실패 {Path(src).name}", [], str(error))
                    self.progress.setValue(index)
                    return
                self.progress.setValue(index)
                self.status_label.setText(f"진행 {index}/{len(paths)}")
            dest = unique_pdf_path(self._target_dir(paths[0]), f"{Path(paths[0]).stem}_병합")
            merge_pdfs(pdfs, dest)
            self._add_history(f"병합 {len(pdfs)}개", [str(dest)])

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
