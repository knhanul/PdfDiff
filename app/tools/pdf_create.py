import os
from datetime import datetime
from pathlib import Path

import pymupdf

from PyQt6.QtCore import QEvent, QFileInfo, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QFileIconProvider, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from app.common.pdf_convert import SUPPORTED_EXTS, is_supported
from app.common.pdf_convert_worker import ConvertThreadManager
from app.common.pdf_images import collect_images, extract_pdf_text, save_image
from app.services import app_settings
from app.shell.theme import build_shell_qss, header_section_qss, tool_table_qss
from app.common.styles import COLOR_BORDER, COLOR_PRIMARY, MODERN_QSS
from app.common.loading_dialog import note_progress, style_task_progress
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
        self.setStyleSheet(MODERN_QSS + build_shell_qss(app_settings.get('ui/theme')))
        self.setAcceptDrops(True)
        self.output_dir = ""
        self.paths = []
        self._updating_checks = False
        self._splitter_ready = False
        self.icon_provider = QFileIconProvider()
        self.convert_manager = None
        self._converting = False
        self._skipped_pdfs = 0
        self._convert_result = None

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
        self.file_table.setAlternatingRowColors(False)
        self.file_table.setIconSize(QSize(20, 20))
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setSortingEnabled(True)
        self.header.setSortIndicator(1, Qt.SortOrder.AscendingOrder)
        self.file_table.itemChanged.connect(self._on_item_changed)
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

        self.action_tabs = QTabWidget()

        convert_page = QWidget()
        convert_layout = QVBoxLayout(convert_page)
        convert_layout.setContentsMargins(0, 8, 0, 0)
        convert_hint = QLabel("일반 문서와 이미지를 PDF로 만듭니다. 병합을 체크하면 기존 PDF도 함께 한 파일로 합칩니다.")
        convert_hint.setWordWrap(True)
        convert_layout.addWidget(convert_hint)
        convert_formats = QLabel(
            "변환 가능: hwp, hwpx, doc, docx, rtf, xls, xlsx, ppt, pptx, odt, ods, odp, md, txt, csv, log, "
            "png, jpg, jpeg, bmp, gif, tif, tiff, webp"
        )
        convert_formats.setWordWrap(True)
        convert_formats.setStyleSheet("color: #6E6863; font-size: 12px;")
        convert_layout.addWidget(convert_formats)
        convert_row = QHBoxLayout()
        self.btn_convert = QPushButton("변환 실행")
        self.btn_convert.setObjectName("actionBtn")
        self.btn_convert.clicked.connect(self.convert_checked)
        self.merge_check = QCheckBox("한 개 파일로 병합")
        self.merge_check.setToolTip("체크하면 체크한 파일을 목록 순서대로 하나의 PDF로 합칩니다. PDF는 그대로 포함됩니다.")
        self.btn_cancel = QPushButton("변환 취소")
        self.btn_cancel.setToolTip("진행 중인 변환을 중지합니다. 현재 변환 중인 파일은 끝까지 처리된 뒤 멈춥니다.")
        self.btn_cancel.clicked.connect(self.cancel_conversion)
        self.btn_cancel.hide()
        convert_row.addWidget(self.btn_convert)
        convert_row.addWidget(self.merge_check)
        convert_row.addWidget(self.btn_cancel)
        convert_row.addStretch()
        convert_layout.addLayout(convert_row)
        convert_layout.addStretch()
        self.action_tabs.addTab(convert_page, "PDF로 만들기")

        extract_page = QWidget()
        extract_layout = QVBoxLayout(extract_page)
        extract_layout.setContentsMargins(0, 8, 0, 0)
        extract_hint = QLabel("체크한 PDF에서만 동작합니다. 이미지와 글자를 결과 폴더에 저장합니다.")
        extract_hint.setWordWrap(True)
        extract_layout.addWidget(extract_hint)
        extract_row = QHBoxLayout()
        self.btn_extract = QPushButton("이미지 추출")
        self.btn_extract.setToolTip("체크한 PDF에서 이미지를 저장합니다.")
        self.btn_extract.clicked.connect(self.extract_images)
        self.btn_text = QPushButton("글자 추출")
        self.btn_text.setToolTip("체크한 PDF의 글자를 텍스트 파일로 저장합니다.")
        self.btn_text.clicked.connect(self.extract_text)
        extract_row.addWidget(self.btn_extract)
        extract_row.addWidget(self.btn_text)
        extract_row.addStretch()
        extract_layout.addLayout(extract_row)
        extract_layout.addStretch()
        self.action_tabs.addTab(extract_page, "추출")
        self.action_tabs.currentChanged.connect(self._on_action_tab)
        self.action_tabs.setMaximumHeight(170)
        right_layout.addWidget(self.action_tabs)

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

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        style_task_progress(self.progress)
        right_layout.addWidget(self.progress)

        self.status_label = QLabel("")
        self._on_action_tab(0)
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
        self._style_file_table()

    def _style_file_table(self):
        theme_id = app_settings.get('ui/theme')
        self.setStyleSheet(MODERN_QSS + build_shell_qss(theme_id))
        self.file_table.setStyleSheet(tool_table_qss(theme_id, selectable=False))
        if hasattr(self, 'progress'):
            style_task_progress(self.progress)

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

    def _on_action_tab(self, index):
        if index == 1:
            self.status_label.setText("추출 대상: 체크한 PDF. 이미지는 원본 형식, 글자는 txt로 저장합니다.")
        else:
            self.status_label.setText("일반 문서와 이미지를 PDF로 만듭니다.")

    def _target_dir(self, src):
        if self.output_dir and os.path.isdir(self.output_dir):
            return self.output_dir
        return str(Path(src).parent)

    def convert_checked(self):
        if self._converting:
            return
        paths = self._checked_paths()
        if not paths:
            QMessageBox.warning(self, "알림", "PDF로 만들 파일을 체크하세요.")
            return
        if self.merge_check.isChecked():
            jobs = [(src, self._target_dir(src)) for src in paths]
            self._start_conversion(
                jobs, merge=True,
                merge_dir=self._target_dir(paths[0]),
                merge_stem=f"{Path(paths[0]).stem}_병합",
            )
            return
        others = [src for src in paths if Path(src).suffix.lower() != ".pdf"]
        self._skipped_pdfs = len(paths) - len(others)
        if not others:
            QMessageBox.information(self, "알림", "PDF만 체크되어 있습니다.\n한 개 파일로 병합을 체크하거나 이미지 추출, 글자 추출을 사용하세요.")
            return
        jobs = [(src, self._target_dir(src)) for src in others]
        self._start_conversion(jobs, merge=False)

    def _start_conversion(self, jobs, merge, merge_dir="", merge_stem=""):
        """변환 작업을 백그라운드 스레드에서 시작 (COM 블로킹 시에도 UI 유지)"""
        self._converting = True
        self._convert_result = None
        self.progress.setMaximum(max(len(jobs), 1))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self._set_action_buttons_enabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setVisible(True)
        self.status_label.setText("변환 준비 중...")
        if not self.convert_manager:
            self.convert_manager = ConvertThreadManager(self)
            self.convert_manager.progress.connect(self._on_convert_progress)
            self.convert_manager.file_done.connect(self._on_convert_file_done)
            self.convert_manager.result_ready.connect(self._on_convert_result)
            self.convert_manager.finished.connect(self._on_convert_finished)
            self.convert_manager.error.connect(self._on_convert_error)
        self.convert_manager.setup_worker(
            jobs, merge=merge, merge_dir=merge_dir, merge_stem=merge_stem)
        self.convert_manager.start()

    def cancel_conversion(self):
        """변환 취소 - 현재 파일 처리 후 중지 (COM이 멈춘 경우 강제 정리)"""
        if not self._converting or not self.convert_manager:
            return
        self.btn_cancel.setEnabled(False)
        self.status_label.setText("취소 요청 중... (현재 파일 완료 후 중지)")
        self.convert_manager.cancel()
        # 멈춘 COM 호출이 강제 종료되면 finished 신호가 오지 않으므로 UI를 여기서 복원
        self._finish_conversion_ui()
        self.status_label.setText("변환을 중지했습니다.")

    def _set_action_buttons_enabled(self, enabled):
        for widget in (self.btn_convert, self.merge_check, self.btn_extract, self.btn_text):
            widget.setEnabled(enabled)

    def _finish_conversion_ui(self):
        self.progress.setVisible(False)
        self.btn_cancel.setVisible(False)
        self._set_action_buttons_enabled(True)
        self._converting = False

    def _on_convert_progress(self, current, total):
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(current)
        self.status_label.setText(f"진행 {current}/{total}")

    def _on_convert_file_done(self, src, ok, dest, error):
        name = Path(src).name
        if ok:
            if dest and dest != src:
                self._add_history(f"변환 {name}", [dest])
        else:
            self._add_history(f"실패 {name}", [], error)

    def _on_convert_result(self, result):
        self._convert_result = result

    def _on_convert_error(self, message):
        self._finish_conversion_ui()
        self._convert_result = None
        first_line = (message or "알 수 없는 오류").splitlines()[0]
        QMessageBox.warning(self, "변환 오류", f"변환 중 오류가 발생했습니다.\n{first_line}")
        self.status_label.setText("변환 오류")

    def _on_convert_finished(self):
        self._finish_conversion_ui()
        result = self._convert_result or {}
        self._convert_result = None
        skipped = self._skipped_pdfs
        self._skipped_pdfs = 0
        if result.get('kind') == 'merged':
            if result.get('cancelled'):
                self.status_label.setText("병합을 중지했습니다.")
            elif result.get('ok'):
                self._add_history(f"병합 {result.get('count', 0)}개", [result.get('dest', '')])
                QMessageBox.information(self, "변환 결과", "체크한 파일을 하나의 PDF로 저장했습니다.")
                self.status_label.setText("성공 1개, 실패 0개")
            else:
                failed = result.get('failed', [])
                QMessageBox.warning(self, "변환 결과", f"성공 0개, 실패 {len(failed)}개\n\n" + "\n".join(failed[:8]))
                self.status_label.setText(f"성공 0개, 실패 {len(failed)}개")
            return
        ok = result.get('ok', 0)
        failed = result.get('failed', [])
        extra = f"\nPDF {skipped}개는 병합, 이미지 추출, 글자 추출에서 처리됩니다." if skipped else ""
        if result.get('cancelled'):
            QMessageBox.information(self, "변환 결과", f"변환을 중지했습니다. 성공 {ok}개, 실패 {len(failed)}개{extra}")
        elif failed:
            QMessageBox.warning(self, "변환 결과", f"성공 {ok}개, 실패 {len(failed)}개{extra}\n\n" + "\n".join(failed[:8]))
        else:
            QMessageBox.information(self, "변환 결과", f"{ok}개 파일을 PDF로 저장했습니다.{extra}")
        self.status_label.setText(f"성공 {ok}개, 실패 {len(failed)}개")

    def closeEvent(self, event):
        """위젯 종료 시 변환 스레드 정리 (멈춘 COM 호출이 있어도 종료 보장)"""
        if self.convert_manager:
            self.convert_manager.cancel()
            self.convert_manager.cleanup()
            self.convert_manager = None
        super().closeEvent(event)

    def extract_images(self):
        pdfs = [src for src in self._checked_paths() if Path(src).suffix.lower() == ".pdf"]
        if not pdfs:
            QMessageBox.warning(self, "알림", "이미지를 추출할 PDF를 체크하세요.")
            return
        self.progress.setVisible(True)
        self.progress.setMaximum(len(pdfs))
        saved = []
        failed = []
        for index, src in enumerate(pdfs, start=1):
            doc = None
            try:
                images = collect_images(src)
                if not images:
                    self._add_history(f"이미지 없음 {Path(src).name}", [])
                else:
                    doc = pymupdf.open(src)
                    for image_index, image in enumerate(images, start=1):
                        dest = self._unique_image_path(src, image, image_index)
                        save_image(doc, image["xref"], dest)
                        saved.append(str(dest))
            except Exception as error:
                failed.append(f"{Path(src).name}: {error}")
                self._add_history(f"실패 {Path(src).name}", [], str(error))
            finally:
                if doc is not None:
                    doc.close()
            note_progress(self.progress, index)
            self.status_label.setText(f"이미지 추출 {index}/{len(pdfs)}")
        self.progress.setVisible(False)
        if saved:
            self._add_history(f"이미지 추출 {len(saved)}개", saved)
        if failed:
            QMessageBox.warning(self, "추출 결과", f"성공 {len(saved)}개, 실패 {len(failed)}개\n\n" + "\n".join(failed[:8]))
        elif not saved:
            QMessageBox.information(self, "추출 결과", "체크한 PDF에서 이미지를 찾지 못했습니다.")
        else:
            QMessageBox.information(self, "추출 결과", f"{len(saved)}개 이미지를 저장했습니다.")
        self.status_label.setText(f"이미지 {len(saved)}개, 실패 {len(failed)}개")

    def extract_text(self):
        pdfs = [src for src in self._checked_paths() if Path(src).suffix.lower() == ".pdf"]
        if not pdfs:
            QMessageBox.warning(self, "알림", "글자를 추출할 PDF를 체크하세요.")
            return
        self.progress.setVisible(True)
        self.progress.setMaximum(len(pdfs))
        saved = []
        failed = []
        empty = 0
        for index, src in enumerate(pdfs, start=1):
            try:
                text = extract_pdf_text(src)
                if not text or not any(line.strip() and not line.startswith("----- ") for line in text.splitlines()):
                    empty += 1
                    self._add_history(f"글자 없음 {Path(src).name}", [], "추출된 글자가 없습니다.")
                else:
                    dest = self._unique_text_path(src)
                    dest.write_text(text + "\n", encoding="utf-8")
                    saved.append(str(dest))
            except Exception as error:
                failed.append(f"{Path(src).name}: {error}")
                self._add_history(f"실패 {Path(src).name}", [], str(error))
            note_progress(self.progress, index)
            self.status_label.setText(f"글자 추출 {index}/{len(pdfs)}")
        self.progress.setVisible(False)
        if saved:
            self._add_history(f"글자 추출 {len(saved)}개", saved)
        if failed:
            QMessageBox.warning(self, "추출 결과", f"성공 {len(saved)}개, 실패 {len(failed)}개\n\n" + "\n".join(failed[:8]))
        elif not saved:
            QMessageBox.information(self, "추출 결과", "체크한 PDF에서 글자를 찾지 못했습니다.")
        else:
            QMessageBox.information(self, "추출 결과", f"{len(saved)}개 텍스트 파일을 저장했습니다.")
        self.status_label.setText(f"글자 {len(saved)}개, 없음 {empty}개, 실패 {len(failed)}개")

    def _unique_text_path(self, src):
        directory = Path(self._target_dir(src))
        directory.mkdir(parents=True, exist_ok=True)
        stem = Path(src).stem
        candidate = directory / f"{stem}.txt"
        number = 2
        while candidate.exists():
            candidate = directory / f"{stem}_{number}.txt"
            number += 1
        return candidate

    def _unique_image_path(self, src, image, index):
        directory = Path(self._target_dir(src))
        directory.mkdir(parents=True, exist_ok=True)
        page = image["pages"][0]
        stem = f"{Path(src).stem}_p{page}_{index}"
        ext = image.get("ext") or "png"
        candidate = directory / f"{stem}.{ext}"
        number = 2
        while candidate.exists():
            candidate = directory / f"{stem}_{number}.{ext}"
            number += 1
        return candidate

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
