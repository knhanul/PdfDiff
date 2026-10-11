import os
from datetime import datetime
from pathlib import Path

import pymupdf
from PyQt6.QtCore import QEvent, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.common.loading_dialog import note_progress, style_task_progress
from app.common.pdf_images import collect_images, save_image
from app.common.styles import COLOR_BORDER, COLOR_PRIMARY, COLOR_SIDEBAR_BG, COLOR_TEXT_PRIMARY, MODERN_QSS
from app.common.user_prefs import load_dir, save_dir

OUTPUT_KEY = "output/pdf_image_extract"
COLUMNS = ("", "미리보기", "파일명", "페이지", "크기", "형식", "용량")


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


class PdfImageExtractWidget(QWidget):
    """PDF에 포함된 이미지를 파일로 저장"""

    def __init__(self, parent=None, comparison_settings=None):
        super().__init__(parent)
        self.setStyleSheet(MODERN_QSS)
        self.setAcceptDrops(True)
        self.output_dir = ""
        self._keys = set()
        self._updating_checks = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.image_table = QTableWidget(0, len(COLUMNS))
        self.header = CheckBoxHeader(self.image_table)
        self.image_table.setHorizontalHeader(self.header)
        self.image_table.setHorizontalHeaderLabels(COLUMNS)
        self.header.clicked_all.connect(self._toggle_all_checks)
        self.image_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.image_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.image_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.image_table.setShowGrid(False)
        self.image_table.setIconSize(QSize(48, 48))
        self.image_table.verticalHeader().setVisible(False)
        self.image_table.verticalHeader().setDefaultSectionSize(56)
        self.image_table.setSortingEnabled(True)
        self.header.setSortIndicator(2, Qt.SortOrder.AscendingOrder)
        self.image_table.itemChanged.connect(self._on_item_changed)
        self.image_table.cellClicked.connect(self._on_cell_clicked)
        self.image_table.setColumnWidth(0, 40)
        self.image_table.setColumnWidth(1, 72)
        self.image_table.setColumnWidth(2, 180)
        self.image_table.setColumnWidth(3, 90)
        self.image_table.setColumnWidth(4, 110)
        self.image_table.setColumnWidth(5, 70)
        self._style_table()
        left_layout.addWidget(self.image_table, 1)

        buttons = QHBoxLayout()
        for title, handler in (
            ("PDF 추가", self.add_files),
            ("폴더 추가", self.add_folder),
            ("체크 삭제", self.remove_checked),
        ):
            button = QPushButton(title)
            if title == "PDF 추가":
                button.setObjectName("actionBtn")
            button.clicked.connect(handler)
            buttons.addWidget(button)
        buttons.addStretch()
        self.count_label = QLabel("체크 0 / 전체 0")
        buttons.addWidget(self.count_label)
        left_layout.addLayout(buttons)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("PDF를 끌어다 놓으면 들어 있는 이미지를 보여 줍니다.\n체크된 이미지만 저장하고, 행을 클릭해도 하이라이트되지 않습니다.")
        hint.setWordWrap(True)
        right_layout.addWidget(hint)

        folder_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText("결과 폴더 미지정 (PDF와 같은 폴더)")
        btn_folder = QPushButton("결과 폴더")
        btn_folder.clicked.connect(self.choose_output_dir)
        btn_clear = QPushButton("해제")
        btn_clear.clicked.connect(self.clear_output_dir)
        folder_row.addWidget(self.output_edit, 1)
        folder_row.addWidget(btn_folder)
        folder_row.addWidget(btn_clear)
        right_layout.addLayout(folder_row)
        saved = load_dir(OUTPUT_KEY)
        if saved:
            self.output_dir = saved
            self.output_edit.setText(saved)

        self.btn_extract = QPushButton("이미지 추출")
        self.btn_extract.setObjectName("actionBtn")
        self.btn_extract.clicked.connect(self.extract_checked)
        right_layout.addWidget(self.btn_extract)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        style_task_progress(self.progress)
        right_layout.addWidget(self.progress)

        self.status_label = QLabel("PDF 안의 그림 파일을 원래 형식으로 저장합니다.")
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

    def _style_table(self):
        self.image_table.setStyleSheet(f"""
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
        self._add_paths([url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()])

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "PDF 선택", "", "PDF Files (*.pdf)")
        self._add_paths(paths)

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "PDF 폴더 선택", "")
        if path:
            self._add_paths([path])

    def _iter_pdfs(self, path):
        path = Path(path)
        if path.is_file() and path.suffix.lower() == ".pdf":
            yield path
            return
        if not path.is_dir():
            return
        for found in path.rglob("*.pdf"):
            if found.is_file() and not any(part.startswith(".") for part in found.parts):
                yield found

    def _add_paths(self, paths):
        pdfs = []
        for raw in paths:
            pdfs.extend(self._iter_pdfs(raw))
        if not pdfs and paths:
            self.status_label.setText("추가할 PDF가 없습니다.")
            return
        self.progress.setVisible(True)
        self.progress.setMaximum(max(1, len(pdfs)))
        self.image_table.setSortingEnabled(False)
        added = 0
        empty = 0
        for index, pdf in enumerate(pdfs, start=1):
            try:
                images = collect_images(pdf)
            except Exception as error:
                self._add_history(f"실패 {pdf.name}", [], str(error))
                note_progress(self.progress, index)
                continue
            if not images:
                empty += 1
            for image in images:
                key = (image["path"], image["xref"])
                if key in self._keys:
                    continue
                self._append_row(image)
                self._keys.add(key)
                added += 1
            note_progress(self.progress, index)
            self.status_label.setText(f"이미지 찾는 중 {index}/{len(pdfs)}")
        self.image_table.setSortingEnabled(True)
        self.progress.setVisible(False)
        self._sync_header_check()
        self._update_count()
        if added == 0:
            self.status_label.setText("추출할 이미지가 없습니다." if empty else "새 이미지가 없습니다.")
        else:
            self.status_label.setText(f"이미지 {added}개를 찾았습니다.")

    def _append_row(self, image):
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        check.setCheckState(Qt.CheckState.Checked)
        preview = QTableWidgetItem()
        thumb = image.get("thumb") or b""
        if thumb:
            pixmap = QPixmap()
            pixmap.loadFromData(thumb, "PNG")
            preview.setIcon(QIcon(pixmap))
        name = QTableWidgetItem(Path(image["path"]).name)
        name.setData(Qt.ItemDataRole.UserRole, image)
        name.setToolTip(image["path"])
        pages = ", ".join(str(page) for page in image["pages"][:6])
        if len(image["pages"]) > 6:
            pages += f" 외 {len(image['pages']) - 6}"
        page_item = QTableWidgetItem(pages)
        size_item = QTableWidgetItem(f"{image['width']}×{image['height']}")
        ext_item = QTableWidgetItem(image["ext"])
        byte_item = QTableWidgetItem(self._format_size(image["nbytes"]))
        byte_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row = self.image_table.rowCount()
        self.image_table.insertRow(row)
        for column, item in enumerate((check, preview, name, page_item, size_item, ext_item, byte_item)):
            if column != 0:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.image_table.setItem(row, column, item)

    def _format_size(self, size):
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                if unit == "B":
                    return f"{int(value)} B"
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{int(size)} B"

    def _checked_images(self):
        images = []
        for row in range(self.image_table.rowCount()):
            check = self.image_table.item(row, 0)
            name = self.image_table.item(row, 2)
            if check and name and check.checkState() == Qt.CheckState.Checked:
                images.append(name.data(Qt.ItemDataRole.UserRole))
        return images

    def _checked_count(self):
        count = 0
        for row in range(self.image_table.rowCount()):
            item = self.image_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                count += 1
        return count

    def _on_cell_clicked(self, row, column):
        if column == 0 or self._updating_checks:
            return
        item = self.image_table.item(row, 0)
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
        self._set_all_checks(self._checked_count() < self.image_table.rowCount())

    def _set_all_checks(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._updating_checks = True
        for row in range(self.image_table.rowCount()):
            item = self.image_table.item(row, 0)
            if item is not None:
                item.setCheckState(state)
        self._updating_checks = False
        self._sync_header_check()
        self._update_count()

    def _sync_header_check(self):
        total = self.image_table.rowCount()
        checked = self._checked_count()
        if total == 0 or checked == 0:
            state = Qt.CheckState.Unchecked
        elif checked == total:
            state = Qt.CheckState.Checked
        else:
            state = Qt.CheckState.PartiallyChecked
        self.header.set_state(state)

    def remove_checked(self):
        rows = [
            row for row in range(self.image_table.rowCount())
            if (item := self.image_table.item(row, 0)) and item.checkState() == Qt.CheckState.Checked
        ]
        if not rows:
            QMessageBox.warning(self, "알림", "목록에서 뺄 이미지를 체크하세요.")
            return
        for row in reversed(rows):
            name = self.image_table.item(row, 2)
            image = name.data(Qt.ItemDataRole.UserRole) if name else None
            self.image_table.removeRow(row)
            if image:
                self._keys.discard((image["path"], image["xref"]))
        self._sync_header_check()
        self._update_count()

    def _update_count(self):
        self.count_label.setText(f"체크 {self._checked_count()} / 전체 {self.image_table.rowCount()}")

    def choose_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "결과 폴더 선택", self.output_dir or "")
        if path:
            self.output_dir = path
            self.output_edit.setText(path)
            save_dir(OUTPUT_KEY, path)

    def clear_output_dir(self):
        self.output_dir = ""
        self.output_edit.clear()
        save_dir(OUTPUT_KEY, "")

    def _target_dir(self, src):
        if self.output_dir and os.path.isdir(self.output_dir):
            return Path(self.output_dir)
        return Path(src).parent

    def extract_checked(self):
        images = self._checked_images()
        if not images:
            QMessageBox.warning(self, "알림", "저장할 이미지를 체크하세요.")
            return
        self.progress.setVisible(True)
        self.progress.setMaximum(len(images))
        saved = []
        failed = []
        docs = {}
        try:
            for index, image in enumerate(images, start=1):
                try:
                    path = image["path"]
                    if path not in docs:
                        docs[path] = pymupdf.open(path)
                    dest = self._unique_dest(image, index)
                    save_image(docs[path], image["xref"], dest)
                    saved.append(str(dest))
                except Exception as error:
                    failed.append(f"{Path(image['path']).name}: {error}")
                    self._add_history(f"실패 {Path(image['path']).name}", [], str(error))
                note_progress(self.progress, index)
                self.status_label.setText(f"추출 {index}/{len(images)}")
        finally:
            for doc in docs.values():
                doc.close()
            self.progress.setVisible(False)
        if saved:
            self._add_history(f"추출 {len(saved)}개", saved)
        if failed:
            QMessageBox.warning(self, "추출 결과", f"성공 {len(saved)}개, 실패 {len(failed)}개\n\n" + "\n".join(failed[:8]))
        else:
            QMessageBox.information(self, "추출 결과", f"{len(saved)}개 이미지를 저장했습니다.")
        self.status_label.setText(f"성공 {len(saved)}개, 실패 {len(failed)}개")

    def _unique_dest(self, image, index):
        directory = self._target_dir(image["path"])
        directory.mkdir(parents=True, exist_ok=True)
        page = image["pages"][0]
        stem = f"{Path(image['path']).stem}_p{page}_{index}"
        ext = image["ext"] or "png"
        candidate = directory / f"{stem}.{ext}"
        number = 2
        while candidate.exists():
            candidate = directory / f"{stem}_{number}.{ext}"
            number += 1
        return candidate

    def _add_history(self, summary, paths, detail=""):
        stamp = datetime.now().strftime("%H:%M:%S")
        names = ", ".join(os.path.basename(path) for path in paths[:4]) if paths else detail
        if len(paths) > 4:
            names += f" 외 {len(paths) - 4}"
        item = QListWidgetItem(f"{stamp}  {summary}  →  {names}")
        item.setToolTip(detail or "\n".join(paths))
        item.setData(Qt.ItemDataRole.UserRole, list(paths))
        self.history_list.insertItem(0, item)

    def open_history_item(self, item):
        paths = item.data(Qt.ItemDataRole.UserRole) or []
        if paths:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(paths[0]).parent)))
