import os
import tempfile
from datetime import datetime
from pathlib import Path

import pymupdf
from PyQt6.QtCore import Qt, QSize, QUrl, QFileInfo
from PyQt6.QtGui import QPixmap, QImage, QDragEnterEvent, QDropEvent, QIcon, QTransform, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QListWidget, QListWidgetItem, QMessageBox, QFrame, QSplitter, QDialog,
    QTabWidget, QLineEdit, QSpinBox, QRadioButton, QProgressBar,
    QAbstractItemView, QButtonGroup, QTableWidget, QTableWidgetItem,
    QFileIconProvider,
)

from app.services import app_settings
from app.shell.theme import THEMES, build_shell_qss, header_section_qss, theme_tokens, tool_table_qss
from app.common.styles import (
    COLOR_BORDER, COLOR_PRIMARY, COLOR_TEXT_PRIMARY, MODERN_QSS,
)
from app.common.loading_dialog import note_progress, style_task_progress
from app.common.user_prefs import load_dir, save_dir
from app.common.pdf_text_block import extract_text_blocks, preview_text_edit
from app.common.pdf_file_open import open_pdf_dialog
from app.tools.pdf_create import CheckBoxHeader

EDITOR_OUTPUT_KEY = "output/pdf_editor"

BASE_ICON = (120, 160)

FILE_COLUMNS = ("", "파일명", "페이지", "수정일자", "크기", "경로")


class PdfEditorWidget(QWidget):
    """통합 PDF 편집: 분할 / 병합 / 페이지 편집 (미리보기 후 실행)"""

    def __init__(self, parent=None, comparison_settings=None):
        super().__init__(parent)
        self.setStyleSheet(MODERN_QSS + build_shell_qss(app_settings.get('ui/theme')))
        self.setAcceptDrops(True)

        self.docs = []
        self.file_paths = []
        self.current_index = -1
        self.page_plan = []          # [{"src": int, "rot": int}, ...]
        self.checked = set()         # source page indices
        self._thumb_cache = {}
        self._updating_pages = False
        self.thumb_scale = 1.0
        self._planned_action = None
        self.output_dir = ""
        self.icon_provider = QFileIconProvider()
        self._updating_checks = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.file_table = QTableWidget(0, len(FILE_COLUMNS))
        self.file_header = CheckBoxHeader(self.file_table)
        self.file_table.setHorizontalHeader(self.file_header)
        self.file_table.setHorizontalHeaderLabels(FILE_COLUMNS)
        self.file_header.clicked_all.connect(self._toggle_all_file_checks)
        self.file_table.setMaximumHeight(200)
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.file_table.setShowGrid(False)
        self.file_table.setAlternatingRowColors(False)
        self.file_table.setIconSize(QSize(20, 20))
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.currentCellChanged.connect(self._on_current_cell_changed)
        self.file_table.itemChanged.connect(self._on_file_item_changed)
        self.file_table.setColumnWidth(0, 40)
        self.file_table.setColumnWidth(1, 200)
        self.file_table.setColumnWidth(2, 60)
        self.file_table.setColumnWidth(3, 140)
        self.file_table.setColumnWidth(4, 80)
        self._style_file_table()
        left_layout.addWidget(self.file_table)

        file_btns = QHBoxLayout()
        btn_add = QPushButton("파일 추가")
        btn_add.setObjectName("actionBtn")
        btn_add.clicked.connect(self.add_files)
        btn_remove = QPushButton("체크 삭제")
        btn_remove.clicked.connect(self.remove_checked_files)
        file_btns.addWidget(btn_add)
        file_btns.addWidget(btn_remove)
        file_btns.addStretch()
        self.count_label = QLabel("체크 0 / 전체 0")
        self.count_label.setObjectName("toolbarLabel")
        file_btns.addWidget(self.count_label)
        left_layout.addLayout(file_btns)

        viewer = QFrame()
        viewer_layout = QVBoxLayout(viewer)
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.setSpacing(0)

        toolbar = QFrame()
        toolbar.setObjectName("pdfToolbar")
        toolbar.setFixedHeight(40)
        page_head = QHBoxLayout(toolbar)
        page_head.setContentsMargins(8, 4, 8, 4)
        page_head.setSpacing(4)

        btn_zoom_out = QPushButton("축소")
        btn_zoom_out.setObjectName("toolbarBtn")
        btn_zoom_out.setFixedSize(46, 30)
        btn_zoom_out.clicked.connect(self.zoom_out)
        btn_zoom_in = QPushButton("확대")
        btn_zoom_in.setObjectName("toolbarBtn")
        btn_zoom_in.setFixedSize(46, 30)
        btn_zoom_in.clicked.connect(self.zoom_in)
        self.lbl_zoom = QLineEdit("100%")
        self.lbl_zoom.setObjectName("pageSpin")
        self.lbl_zoom.setFixedSize(64, 30)
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_zoom.setToolTip("배율을 입력하세요. 예: 150")
        self.lbl_zoom.editingFinished.connect(self._apply_thumb_zoom_input)
        self.lbl_sel = QLabel("선택 0 / 전체 0")
        self.lbl_sel.setObjectName("toolbarLabel")
        btn_all = QPushButton("전체")
        btn_all.setObjectName("toolbarBtn")
        btn_all.setFixedSize(46, 30)
        btn_all.clicked.connect(self._select_all)
        btn_odd = QPushButton("홀수")
        btn_odd.setObjectName("toolbarBtn")
        btn_odd.setFixedSize(46, 30)
        btn_odd.clicked.connect(lambda: self._select_parity(True))
        btn_even = QPushButton("짝수")
        btn_even.setObjectName("toolbarBtn")
        btn_even.setFixedSize(46, 30)
        btn_even.clicked.connect(lambda: self._select_parity(False))
        btn_clear = QPushButton("해제")
        btn_clear.setObjectName("toolbarBtn")
        btn_clear.setFixedSize(46, 30)
        btn_clear.setToolTip("선택 해제")
        btn_clear.clicked.connect(self._clear_checks)
        page_head.addWidget(btn_zoom_out)
        page_head.addWidget(btn_zoom_in)
        page_head.addWidget(self.lbl_zoom)
        page_head.addSpacing(8)
        page_head.addWidget(btn_all)
        page_head.addWidget(btn_odd)
        page_head.addWidget(btn_even)
        page_head.addWidget(btn_clear)
        page_head.addStretch()
        page_head.addWidget(self.lbl_sel)
        viewer_layout.addWidget(toolbar)

        self.page_list = QListWidget()
        self.page_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.page_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.page_list.setMovement(QListWidget.Movement.Static)
        self.page_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.page_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.page_list.setSpacing(8)
        self.page_list.setStyleSheet(
            "QListWidget { background: white; border: none; }"
            "QListWidget::item { border: 2px solid transparent; border-radius: 8px; padding: 4px; }"
            "QListWidget::item:selected { background: #FFF1E8; border: 2px solid #E4572E; color: #9A3412; }"
        )
        self.page_list.itemSelectionChanged.connect(self._on_page_selection_changed)
        viewer_layout.addWidget(self.page_list, 1)
        left_layout.addWidget(viewer, 1)
        self._apply_zoom_size()

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_split_tab(), "분할")
        self.tabs.addTab(self._create_merge_tab(), "병합")
        self.tabs.addTab(self._create_page_tab(), "페이지 편집")
        right_layout.addWidget(self.tabs, 1)

        folder_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText("결과 폴더 미지정 (원본 폴더에 저장)")
        btn_folder = QPushButton("결과 폴더")
        btn_folder.clicked.connect(self._choose_output_dir)
        btn_folder_clear = QPushButton("해제")
        btn_folder_clear.clicked.connect(self._clear_output_dir)
        folder_row.addWidget(self.output_edit, 1)
        folder_row.addWidget(btn_folder)
        folder_row.addWidget(btn_folder_clear)
        right_layout.addLayout(folder_row)
        saved_dir = load_dir(EDITOR_OUTPUT_KEY)
        if saved_dir:
            self.output_dir = saved_dir
            self.output_edit.setText(saved_dir)

        right_layout.addWidget(QLabel("실행 이력"))
        self.history_list = QListWidget()
        self.history_list.setMinimumHeight(140)
        self.history_list.itemDoubleClicked.connect(self._open_history_item)
        right_layout.addWidget(self.history_list)

        self.status_label = QLabel("페이지를 클릭하면 선택됩니다. 실행 전까지 원본은 바뀌지 않습니다.")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        self.btn_execute = QPushButton("실행")
        self.btn_execute.setObjectName("actionBtn")
        self.btn_execute.clicked.connect(self.do_execute)
        btn_row.addWidget(self.btn_execute)
        right_layout.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        style_task_progress(self.progress)
        right_layout.addWidget(self.progress)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self._create_bottom_bar(root)
        self._style_file_table()


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
        bar.hide()

    def _create_split_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.split_group = QButtonGroup(w)
        self.radio_keep = QRadioButton("선택한 페이지 / 나머지로 두 파일")
        self.radio_groups = QRadioButton("선택한 연속 구간마다 파일")
        self.radio_range = QRadioButton("페이지 범위 (예: 1-5, 6-10)")
        self.radio_every = QRadioButton("N페이지마다")
        self.radio_each = QRadioButton("각 페이지 개별 추출")
        self.radio_keep.setChecked(True)

        lay.addWidget(self.radio_keep)
        lay.addWidget(self.radio_groups)

        lay.addWidget(self.radio_range)
        self.range_row = QWidget()
        range_lay = QHBoxLayout(self.range_row)
        range_lay.setContentsMargins(24, 0, 0, 0)
        self.edit_range = QLineEdit()
        self.edit_range.setPlaceholderText("1-5, 6-10, 11-")
        range_lay.addWidget(self.edit_range)
        lay.addWidget(self.range_row)

        lay.addWidget(self.radio_every)
        self.every_row = QWidget()
        every_lay = QHBoxLayout(self.every_row)
        every_lay.setContentsMargins(24, 0, 0, 0)
        every_lay.addWidget(QLabel("N:"))
        self.spin_every = QSpinBox()
        self.spin_every.setRange(1, 9999)
        self.spin_every.setValue(10)
        every_lay.addWidget(self.spin_every)
        every_lay.addStretch()
        lay.addWidget(self.every_row)

        lay.addWidget(self.radio_each)
        for radio in (self.radio_keep, self.radio_groups, self.radio_range, self.radio_every, self.radio_each):
            self.split_group.addButton(radio)

        self.radio_range.toggled.connect(self._on_range_toggled)
        self.radio_every.toggled.connect(self._on_every_toggled)
        self.range_row.setVisible(False)
        self.every_row.setVisible(False)
        lay.addStretch()
        return w

    def _on_range_toggled(self, checked):
        self.range_row.setVisible(checked)
        if checked:
            self.edit_range.setFocus()

    def _on_every_toggled(self, checked):
        self.every_row.setVisible(checked)

    def _create_merge_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("여러 PDF를 끌어다 놓거나 [파일 추가]로 불러오세요.\n체크한 파일이 왼쪽 목록 순서대로 병합됩니다."))
        btn_up = QPushButton("선택 파일 위로")
        btn_up.clicked.connect(self.move_file_up)
        btn_down = QPushButton("선택 파일 아래로")
        btn_down.clicked.connect(self.move_file_down)
        lay.addWidget(btn_up)
        lay.addWidget(btn_down)
        lay.addStretch()
        return w

    def _create_page_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("페이지를 클릭해 선택한 뒤 아래 작업을 사용하세요.\n썸네일이 바로 바뀌고, 실행을 눌러야 파일로 저장됩니다."))
        actions = [
            ("텍스트 블록 보기", self._show_text_blocks),
            ("선택 페이지 추출", lambda: self._stage_page("extract")),
            ("선택 페이지 삭제", self._delete_checked),
            ("선택 페이지 90° 회전", self._rotate_checked),
            ("선택 페이지 맨 앞으로", lambda: self._move_checked("front")),
            ("선택 페이지 맨 뒤로", lambda: self._move_checked("back")),
            ("편집 취소", self._reset_page_edits),
        ]
        for title, handler in actions:
            btn = QPushButton(title)
            btn.clicked.connect(handler)
            lay.addWidget(btn)
        lay.addStretch()
        return w

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile().lower().endswith(".pdf")]
        if paths:
            self._load_files(paths)

    def add_files(self):
        paths = open_pdf_dialog(self, "PDF 선택", multi=True)
        if paths:
            self._load_files(paths)

    def _style_file_table(self):
        theme_id = app_settings.get('ui/theme')
        self.setStyleSheet(MODERN_QSS + build_shell_qss(theme_id))
        self.file_table.setStyleSheet(tool_table_qss(theme_id, selectable=True))
        if hasattr(self, 'page_list'):
            if theme_id not in THEMES or theme_id == 'default':
                self.page_list.setStyleSheet(
                    "QListWidget { background: white; border: none; }"
                    "QListWidget::item { border: 2px solid transparent; border-radius: 8px; padding: 4px; }"
                    "QListWidget::item:selected { background: #FFF1E8; border: 2px solid #E4572E; color: #9A3412; }"
                )
            else:
                tokens = theme_tokens(theme_id)
                self.page_list.setStyleSheet(
                    f"QListWidget {{ background: {tokens['panel_bg']}; border: none; }}"
                    "QListWidget::item { border: 2px solid transparent; border-radius: 8px; padding: 4px; }"
                    f"QListWidget::item:selected {{ background: {tokens['selected']}; border: 2px solid {tokens['accent']}; color: {tokens['accent']}; }}"
                )
        if hasattr(self, 'progress'):
            style_task_progress(self.progress)

    def _load_files(self, paths):
        first_new = None
        for path in paths:
            if path in self.file_paths:
                continue
            try:
                doc = pymupdf.open(path)
            except Exception as e:
                QMessageBox.warning(self, "오류", f"{os.path.basename(path)}\n{e}")
                continue
            row = self.file_table.rowCount()
            self._append_file_row(row, path, doc.page_count)
            self.docs.append(doc)
            self.file_paths.append(path)
            if first_new is None:
                first_new = row
        self._sync_header_check()
        self._update_count()
        if self.current_index < 0 and first_new is not None:
            self.file_table.selectRow(first_new)

    def _append_file_row(self, row, path, page_count):
        found = Path(path)
        info = QFileInfo(path)
        stat = found.stat()
        enabled = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        check_item = QTableWidgetItem()
        check_item.setFlags(enabled | Qt.ItemFlag.ItemIsUserCheckable)
        check_item.setCheckState(Qt.CheckState.Checked)
        name_item = QTableWidgetItem(self.icon_provider.icon(info), found.name)
        name_item.setData(Qt.ItemDataRole.UserRole, str(found))
        name_item.setToolTip(str(found))
        page_item = QTableWidgetItem(str(page_count))
        page_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        date_item = QTableWidgetItem(datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"))
        size_item = QTableWidgetItem(self._format_size(stat.st_size))
        size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        path_item = QTableWidgetItem(str(found.parent))
        path_item.setToolTip(str(found.parent))
        self.file_table.insertRow(row)
        for column, item in enumerate((check_item, name_item, page_item, date_item, size_item, path_item)):
            if column != 0:
                item.setFlags(enabled)
            self.file_table.setItem(row, column, item)

    @staticmethod
    def _format_size(size):
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                if unit == "B":
                    return f"{int(value)} B"
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{int(size)} B"

    def _checked_file_rows(self):
        rows = []
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                rows.append(row)
        return rows

    def _on_current_cell_changed(self, row, column, prev_row, prev_col):
        if row == prev_row or row < 0 or row >= len(self.docs):
            return
        if self.file_paths[row] != getattr(self, "_shown_path", None) and not self._confirm_page_edit_switch():
            self.file_table.blockSignals(True)
            self.file_table.selectRow(self.current_index)
            self.file_table.blockSignals(False)
            return
        self.on_file_selected(row)

    def _page_plan_dirty(self):
        if self.current_index < 0 or self.current_index >= len(self.docs):
            return False
        doc = self.docs[self.current_index]
        if len(self.page_plan) != doc.page_count:
            return True
        return any(plan["src"] != i or plan["rot"] % 360 for i, plan in enumerate(self.page_plan))

    def _confirm_page_edit_switch(self):
        if not self._page_plan_dirty():
            return True
        name = Path(self.file_paths[self.current_index]).name
        box = QMessageBox(self)
        box.setWindowTitle("페이지 편집")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"'{name}'의 페이지 편집 내용이 저장되지 않았습니다.\n저장하고 다른 PDF로 이동하시겠습니까?")
        btn_save = box.addButton("저장", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("저장하지 않음", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(btn_save)
        box.exec()
        if box.clickedButton() == btn_save:
            return self._save_page_edits()
        return True

    def _save_page_edits(self):
        plans = [dict(plan) for plan in self.page_plan]
        saved = self._save_page_inplace(plans)
        if saved:
            QMessageBox.information(self, "완료", f"원본에 저장했습니다.\n{saved}")
        return bool(saved)

    def _on_file_item_changed(self, item):
        if self._updating_checks or item.column() != 0:
            return
        self._sync_header_check()
        self._update_count()

    def _toggle_all_file_checks(self):
        self._set_all_file_checks(len(self._checked_file_rows()) < self.file_table.rowCount())

    def _set_all_file_checks(self, checked):
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
        checked = len(self._checked_file_rows())
        if total == 0 or checked == 0:
            state = Qt.CheckState.Unchecked
        elif checked == total:
            state = Qt.CheckState.Checked
        else:
            state = Qt.CheckState.PartiallyChecked
        self.file_header.set_state(state)

    def _update_count(self):
        self.count_label.setText(f"체크 {len(self._checked_file_rows())} / 전체 {self.file_table.rowCount()}")

    def remove_checked_files(self):
        rows = self._checked_file_rows()
        if not rows:
            QMessageBox.warning(self, "알림", "목록에서 삭제할 PDF를 체크하세요.")
            return
        self.file_table.blockSignals(True)
        for row in reversed(rows):
            if row >= len(self.docs):
                self.file_table.removeRow(row)
                continue
            path = self.file_paths[row]
            try:
                self.docs[row].close()
            except Exception:
                pass
            del self.docs[row]
            del self.file_paths[row]
            self._thumb_cache = {key: pixmap for key, pixmap in self._thumb_cache.items() if key[0] != path}
            self.file_table.removeRow(row)
        self.file_table.blockSignals(False)
        self._shown_path = None
        self.current_index = -1
        self.page_plan = []
        self.checked = set()
        if self.file_table.rowCount():
            target = min(rows[0], self.file_table.rowCount() - 1)
            self.file_table.selectRow(target)
            self.on_file_selected(target)
        else:
            self.page_list.clear()
            self._update_sel_label()
        self._sync_header_check()
        self._update_count()

    def on_file_selected(self, row):
        if row < 0 or row >= len(self.docs):
            return
        path = self.file_paths[row]
        self.current_index = row
        if self.page_plan and getattr(self, "_shown_path", None) == path:
            return
        self._shown_path = path
        doc = self.docs[row]
        self.page_plan = [{"src": i, "rot": 0} for i in range(doc.page_count)]
        self.checked = set()
        self._refresh_page_thumbnails()

    def _source_pixmap(self, src_index):
        key = (self.file_paths[self.current_index], src_index)
        cached = self._thumb_cache.get(key)
        if cached is not None:
            return cached
        page = self.docs[self.current_index][src_index]
        zoom = 320 / max(page.rect.width, 1)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        fmt = QImage.Format.Format_RGB888 if pix.n < 4 else QImage.Format.Format_RGBA8888
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
        pixmap = QPixmap.fromImage(image)
        self._thumb_cache[key] = pixmap
        return pixmap

    def _display_pixmap(self, item_plan):
        pixmap = self._source_pixmap(item_plan["src"])
        rot = item_plan["rot"] % 360
        if rot:
            pixmap = pixmap.transformed(QTransform().rotate(rot), Qt.TransformationMode.SmoothTransformation)
        side = int(BASE_ICON[0] * self.thumb_scale * 2)
        return pixmap.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

    def _page_label(self, plan, selected):
        label = f"p{plan['src'] + 1}"
        if plan["rot"] % 360:
            label += f" {plan['rot'] % 360}°"
        if selected:
            label = "✓ " + label
        return label

    def _refresh_page_thumbnails(self):
        self._updating_pages = True
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.page_list.clear()
            for plan in self.page_plan:
                selected = plan["src"] in self.checked
                item = QListWidgetItem(QIcon(self._display_pixmap(plan)), self._page_label(plan, selected))
                item.setData(Qt.ItemDataRole.UserRole, plan["src"])
                item.setSelected(selected)
                self.page_list.addItem(item)
        finally:
            QApplication.restoreOverrideCursor()
            self._updating_pages = False
        self._update_sel_label()

    def _apply_zoom_size(self):
        scale = self.thumb_scale
        w = int(BASE_ICON[0] * scale)
        h = int(BASE_ICON[1] * scale)
        self.page_list.setIconSize(QSize(w, h))
        self.page_list.setGridSize(QSize(w + 36, h + 52))
        self.lbl_zoom.blockSignals(True)
        self.lbl_zoom.setText(f"{int(round(scale * 100))}%")
        self.lbl_zoom.blockSignals(False)

    def _set_thumb_scale(self, scale):
        self.thumb_scale = min(3.0, max(0.4, scale))
        self._apply_zoom_size()
        if self.page_plan:
            self._refresh_page_thumbnails()

    def zoom_in(self):
        self._set_thumb_scale(self.thumb_scale * 1.25)

    def zoom_out(self):
        self._set_thumb_scale(self.thumb_scale / 1.25)

    def _apply_thumb_zoom_input(self):
        text = self.lbl_zoom.text().strip().replace("%", "").replace("％", "")
        if not text:
            self._apply_zoom_size()
            return
        try:
            percent = float(text)
        except ValueError:
            self._apply_zoom_size()
            return
        self._set_thumb_scale(percent / 100.0)

    def _sync_checked(self):
        sources = set()
        for i in range(self.page_list.count()):
            item = self.page_list.item(i)
            if item.isSelected():
                sources.add(item.data(Qt.ItemDataRole.UserRole))
        self.checked = sources
        return sources

    def _on_page_selection_changed(self):
        if self._updating_pages:
            return
        selected = set()
        for i in range(self.page_list.count()):
            item = self.page_list.item(i)
            src = item.data(Qt.ItemDataRole.UserRole)
            is_on = item.isSelected()
            if is_on:
                selected.add(src)
            plan = next((entry for entry in self.page_plan if entry["src"] == src), {"src": src, "rot": 0})
            text = self._page_label(plan, is_on)
            if item.text() != text:
                item.setText(text)
        self.checked = selected
        self._update_sel_label()

    def _choose_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "결과 폴더 선택", self.output_dir or "")
        if not path:
            return
        self.output_dir = path
        self.output_edit.setText(path)
        save_dir(EDITOR_OUTPUT_KEY, path)

    def _clear_output_dir(self):
        self.output_dir = ""
        self.output_edit.clear()
        save_dir(EDITOR_OUTPUT_KEY, "")

    def _result_dir(self, fallback_file):
        if self.output_dir and os.path.isdir(self.output_dir):
            return Path(self.output_dir)
        return Path(fallback_file).parent

    def _unique_path(self, directory, name):
        path = Path(directory) / name
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        number = 2
        while True:
            candidate = Path(directory) / f"{stem}_{number}{suffix}"
            if not candidate.exists():
                return candidate
            number += 1

    def _add_history(self, summary, paths):
        stamp = datetime.now().strftime("%H:%M:%S")
        names = ", ".join(os.path.basename(path) for path in paths)
        item = QListWidgetItem(f"{stamp}  {summary}  →  {names}")
        item.setToolTip("\n".join(paths))
        item.setData(Qt.ItemDataRole.UserRole, list(paths))
        self.history_list.insertItem(0, item)
        self.history_list.setCurrentRow(0)

    def _open_history_item(self, item):
        paths = item.data(Qt.ItemDataRole.UserRole) or []
        if not paths:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(paths[0]).parent)))

    def _update_sel_label(self):
        self.lbl_sel.setText(f"선택 {len(self.checked)} / 전체 {len(self.page_plan)}")

    def _select_all(self):
        self.checked = {plan["src"] for plan in self.page_plan}
        self._refresh_page_thumbnails()

    def _select_parity(self, odd):
        if odd:
            self.checked = {plan["src"] for plan in self.page_plan if plan["src"] % 2 == 0}
        else:
            self.checked = {plan["src"] for plan in self.page_plan if plan["src"] % 2 == 1}
        self._refresh_page_thumbnails()

    def _clear_checks(self):
        self.checked = set()
        self._refresh_page_thumbnails()

    def _require_doc(self):
        if self.current_index < 0 or not self.page_plan:
            QMessageBox.warning(self, "알림", "먼저 PDF를 선택하세요.")
            return False
        return True

    def _require_checked(self):
        if not self._require_doc():
            return False
        self._sync_checked()
        if not self.checked:
            QMessageBox.warning(self, "알림", "페이지를 클릭해 선택하세요.")
            return False
        return True

    def _delete_checked(self):
        if not self._require_checked():
            return
        if len(self.checked) >= len(self.page_plan):
            QMessageBox.warning(self, "알림", "모든 페이지를 삭제할 수 없습니다.")
            return
        self.page_plan = [plan for plan in self.page_plan if plan["src"] not in self.checked]
        self.checked = set()
        self._refresh_page_thumbnails()
        self._stage_page("save")

    def _rotate_checked(self):
        if not self._require_checked():
            return
        for plan in self.page_plan:
            if plan["src"] in self.checked:
                plan["rot"] = (plan["rot"] + 90) % 360
        self._refresh_page_thumbnails()
        self._stage_page("save")

    def _move_checked(self, where):
        if not self._require_checked():
            return
        picked = [plan for plan in self.page_plan if plan["src"] in self.checked]
        rest = [plan for plan in self.page_plan if plan["src"] not in self.checked]
        self.page_plan = picked + rest if where == "front" else rest + picked
        self._refresh_page_thumbnails()
        self._stage_page("save")

    def _reset_page_edits(self):
        if not self._require_doc():
            return
        doc = self.docs[self.current_index]
        self.page_plan = [{"src": i, "rot": 0} for i in range(doc.page_count)]
        self.checked = set()
        self._planned_action = None
        self._refresh_page_thumbnails()
        self.status_label.setText("페이지 편집을 불러온 상태로 되돌렸습니다.")

    def move_file_up(self):
        row = self.file_table.currentRow()
        if 0 < row < len(self.docs):
            self._swap_files(row, row - 1)

    def move_file_down(self):
        row = self.file_table.currentRow()
        if 0 <= row < len(self.docs) - 1:
            self._swap_files(row, row + 1)

    def _swap_files(self, a, b):
        if not (0 <= a < len(self.docs) and 0 <= b < len(self.docs)):
            return
        self._updating_checks = True
        self.file_table.blockSignals(True)
        for column in range(self.file_table.columnCount()):
            item_a = self.file_table.takeItem(a, column)
            item_b = self.file_table.takeItem(b, column)
            self.file_table.setItem(a, column, item_b)
            self.file_table.setItem(b, column, item_a)
        self.file_table.blockSignals(False)
        self._updating_checks = False
        self.docs[a], self.docs[b] = self.docs[b], self.docs[a]
        self.file_paths[a], self.file_paths[b] = self.file_paths[b], self.file_paths[a]
        if self.current_index == a:
            self.current_index = b
        elif self.current_index == b:
            self.current_index = a
        self.file_table.selectRow(b)

    def _preview_split(self):
        self._sync_checked()
        if self.current_index < 0:
            self._planned_action = None
            self.status_label.setText("먼저 PDF를 불러오세요.")
            return False
        doc = self.docs[self.current_index]
        total = doc.page_count
        base = Path(self.file_paths[self.current_index]).stem
        if self.radio_groups.isChecked() or self.radio_keep.isChecked():
            if not self.checked:
                self._planned_action = None
                self.status_label.setText("나눌 페이지를 클릭해 선택하세요.")
                return False
            if self.radio_groups.isChecked():
                groups = [[dict(plan) for plan in group] for group in self._checked_groups()]
                if not groups:
                    self._planned_action = None
                    self.status_label.setText("나눌 페이지를 클릭해 선택하세요.")
                    return False
                desc = ", ".join(self._plan_range_text(group) for group in groups)
                self._planned_action = ("split", {"mode": "groups", "base": base, "groups": groups})
                self.status_label.setText(f"연속 구간 {len(groups)}개 파일: {desc}")
            else:
                picked = [dict(plan) for plan in self.page_plan if plan["src"] in self.checked]
                rest = [dict(plan) for plan in self.page_plan if plan["src"] not in self.checked]
                if not picked or not rest:
                    self._planned_action = None
                    self.status_label.setText("선택 페이지와 나머지 페이지가 모두 있어야 두 파일로 나눌 수 있습니다.")
                    return False
                self._planned_action = ("split", {"mode": "keep", "base": base, "picked": picked, "rest": rest})
                self.status_label.setText(f"선택 {len(picked)}페이지 / 나머지 {len(rest)}페이지")
        elif self.radio_range.isChecked():
            text = self.edit_range.text().strip()
            if not text:
                self._planned_action = None
                self.status_label.setText("범위를 입력하세요. 예: 1-5, 6-10")
                return False
            ranges = self._parse_ranges(text, total)
            self._planned_action = ("split", {"mode": "range", "ranges": ranges, "base": base})
            desc = ", ".join(f"{s + 1}-{e}" for s, e in ranges)
            self.status_label.setText(f"범위 분할 {len(ranges)}개 파일: {desc}")
        elif self.radio_every.isChecked():
            n = self.spin_every.value()
            parts = (total + n - 1) // n
            self._planned_action = ("split", {"mode": "every", "n": n, "base": base})
            self.status_label.setText(f"{n}페이지마다 {parts}개 파일")
        else:
            self._planned_action = ("split", {"mode": "each", "base": base})
            self.status_label.setText(f"페이지별 {total}개 파일")
        return True

    def _checked_groups(self):
        groups = []
        current = []
        for plan in self.page_plan:
            if plan["src"] in self.checked:
                current.append(plan)
            elif current:
                groups.append(current)
                current = []
        if current:
            groups.append(current)
        return groups

    def _plan_range_text(self, group):
        pages = [plan["src"] + 1 for plan in group]
        if pages[0] == pages[-1]:
            return str(pages[0])
        return f"{pages[0]}-{pages[-1]}"

    def _preview_merge(self):
        rows = self._checked_file_rows()
        if len(rows) < 2:
            self.status_label.setText("병합하려면 PDF를 2개 이상 체크하세요.")
            return False
        names = [os.path.basename(self.file_paths[row]) for row in rows]
        self._planned_action = ("merge", {"rows": rows})
        self.status_label.setText("병합 순서: " + " → ".join(names))
        return True

    def _stage_page(self, mode):
        if not self._require_doc():
            return
        self._sync_checked()
        if mode == "extract":
            plans = [dict(plan) for plan in self.page_plan if plan["src"] in self.checked]
            if not plans:
                self.status_label.setText("추출할 페이지를 클릭해 선택하세요.")
                return
        else:
            plans = [dict(plan) for plan in self.page_plan]
        self._planned_action = ("page", {"mode": mode, "plans": plans})
        self._preview_page()

    def _preview_page(self):
        action = self._planned_action[1]
        plans = action["plans"]
        if action["mode"] == "extract":
            pages = [str(plan["src"] + 1) for plan in plans]
            self.status_label.setText("추출: 페이지 " + ", ".join(pages))
        else:
            rotated = sum(1 for plan in plans if plan["rot"] % 360)
            notes = []
            if rotated:
                notes.append(f"회전 {rotated}페이지")
            notes.append(f"저장 {len(plans)}페이지")
            self.status_label.setText("페이지 편집: " + ", ".join(notes) + " → 원본에 저장")

    def do_execute(self):
        tab = self.tabs.currentIndex()
        if tab == 0:
            if not self._preview_split():
                return
        elif tab == 1:
            if not self._preview_merge():
                return
        elif not (self._planned_action and self._planned_action[0] == "page"):
            if self._page_plan_dirty():
                self._stage_page("save")
            else:
                self.status_label.setText("페이지 편집에서 작업을 먼저 선택하세요.")
                return
        if not self._planned_action:
            return
        kind = self._planned_action[0]
        summary = self.status_label.text().replace("\n", " ")
        paths = None
        try:
            if kind == "split":
                paths = self._exec_split()
            elif kind == "merge":
                paths = self._exec_merge()
            elif kind == "page":
                paths = self._exec_page()
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))
        finally:
            self.progress.setVisible(False)
        if paths:
            self._add_history(summary, paths)

    def _parse_ranges(self, text, total):
        ranges = []
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start_text, end_text = part.split("-", 1)
                start = int(start_text) - 1 if start_text else 0
                end = int(end_text) if end_text else total
                ranges.append((max(0, start), min(total, end)))
            else:
                page = int(part) - 1
                ranges.append((page, page + 1))
        return ranges

    def _write_plans(self, doc, plans, path):
        out = pymupdf.open()
        for plan in plans:
            src = plan["src"]
            out.insert_pdf(doc, from_page=src, to_page=src)
            extra = plan.get("rot", 0) % 360
            if extra:
                out[-1].set_rotation((doc[src].rotation + extra) % 360)
        out.save(path)
        out.close()

    def _exec_split(self):
        params = self._planned_action[1]
        doc = self.docs[self.current_index]
        out_dir = self._result_dir(self.file_paths[self.current_index])
        base = params["base"]
        total = doc.page_count
        self.progress.setVisible(True)
        mode = params["mode"]
        written = []

        if mode == "groups":
            groups = params["groups"]
            self.progress.setMaximum(len(groups))
            for i, group in enumerate(groups, start=1):
                path = str(self._unique_path(out_dir, f"{base}_sel{i}.pdf"))
                self._write_plans(doc, group, path)
                written.append(path)
                note_progress(self.progress, i)
        elif mode == "keep":
            picked = params["picked"]
            rest = params["rest"]
            self.progress.setMaximum(2)
            selected_path = str(self._unique_path(out_dir, f"{base}_selected.pdf"))
            rest_path = str(self._unique_path(out_dir, f"{base}_rest.pdf"))
            self._write_plans(doc, picked, selected_path)
            note_progress(self.progress, 1)
            self._write_plans(doc, rest, rest_path)
            note_progress(self.progress, 2)
            written = [selected_path, rest_path]
        elif mode == "range":
            ranges = params["ranges"]
            self.progress.setMaximum(len(ranges))
            for i, (start, end) in enumerate(ranges):
                if start >= end:
                    continue
                path = str(self._unique_path(out_dir, f"{base}_p{start + 1}-{end}.pdf"))
                plans = [{"src": page, "rot": 0} for page in range(start, end)]
                self._write_plans(doc, plans, path)
                written.append(path)
                note_progress(self.progress, i + 1)
        elif mode == "every":
            n = params["n"]
            count = (total + n - 1) // n
            self.progress.setMaximum(count)
            part = 1
            for start in range(0, total, n):
                end = min(start + n, total)
                path = str(self._unique_path(out_dir, f"{base}_part{part}.pdf"))
                plans = [{"src": page, "rot": 0} for page in range(start, end)]
                self._write_plans(doc, plans, path)
                written.append(path)
                note_progress(self.progress, part)
                part += 1
        else:
            self.progress.setMaximum(total)
            for i in range(total):
                path = str(self._unique_path(out_dir, f"{base}_p{i + 1}.pdf"))
                self._write_plans(doc, [{"src": i, "rot": 0}], path)
                written.append(path)
                note_progress(self.progress, i + 1)
        names = "\n".join(os.path.basename(path) for path in written)
        QMessageBox.information(self, "완료", f"분할이 완료되었습니다.\n{out_dir}\n{names}")
        return written

    def _save_target(self, default_name, fallback_file):
        if self.output_dir and os.path.isdir(self.output_dir):
            return str(self._unique_path(self.output_dir, default_name))
        start = str(Path(fallback_file).parent / default_name)
        path, _ = QFileDialog.getSaveFileName(self, "저장", start, "PDF Files (*.pdf)")
        return path or None

    def _exec_merge(self):
        rows = self._planned_action[1].get("rows") or list(range(len(self.docs)))
        if not rows:
            return None
        save_path = self._save_target("merged.pdf", self.file_paths[rows[0]])
        if not save_path:
            return None
        self.progress.setVisible(True)
        self.progress.setMaximum(len(rows))
        out = pymupdf.open()
        for index, row in enumerate(rows, start=1):
            out.insert_pdf(self.docs[row])
            note_progress(self.progress, index)
        out.save(save_path)
        out.close()
        QMessageBox.information(self, "완료", f"병합 완료:\n{save_path}")
        return [save_path]

    def _exec_page(self):
        doc = self.docs[self.current_index]
        plans = self._planned_action[1]["plans"]
        if not plans:
            QMessageBox.warning(self, "알림", "저장할 페이지가 없습니다.")
            return None
        if self._planned_action[1]["mode"] == "save":
            name = Path(self.file_paths[self.current_index]).name
            box = QMessageBox(self)
            box.setWindowTitle("원본 저장")
            box.setIcon(QMessageBox.Icon.Question)
            box.setText(f"'{name}' 원본 파일에 편집 내용을 저장합니다.\n계속하시겠습니까?")
            btn_save = box.addButton("저장", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(btn_save)
            box.exec()
            if box.clickedButton() != btn_save:
                return None
            self.progress.setVisible(True)
            self.progress.setMaximum(1)
            self.progress.setValue(0)
            saved = self._save_page_inplace(plans)
            note_progress(self.progress, 1)
            if saved:
                QMessageBox.information(self, "완료", f"저장 완료:\n{saved}")
                return [saved]
            return None
        save_path = self._save_target("edited.pdf", self.file_paths[self.current_index])
        if not save_path:
            return None
        self.progress.setVisible(True)
        self.progress.setMaximum(max(1, len(plans)))
        self.progress.setValue(0)
        self._write_plans(doc, plans, save_path)
        note_progress(self.progress, len(plans))
        QMessageBox.information(self, "완료", f"저장 완료:\n{save_path}")
        return [save_path]

    def _save_page_inplace(self, plans):
        path = self.file_paths[self.current_index]
        doc = self.docs[self.current_index]
        fd, tmp_name = tempfile.mkstemp(suffix=".pdf", prefix="pdfedit_", dir=Path(path).parent)
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            self._write_plans(doc, plans, str(tmp_path))
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            QMessageBox.critical(self, "오류", f"저장 중 오류가 발생했습니다.\n{e}")
            return None
        try:
            doc.close()
            os.replace(tmp_path, path)
            self.docs[self.current_index] = pymupdf.open(path)
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            QMessageBox.critical(self, "오류", f"원본 파일을 덮어쓸 수 없습니다.\n{e}")
            try:
                self.docs[self.current_index] = pymupdf.open(path)
            except Exception:
                pass
            return None
        self._thumb_cache = {key: pixmap for key, pixmap in self._thumb_cache.items() if key[0] != path}
        self.page_plan = [{"src": i, "rot": 0} for i in range(self.docs[self.current_index].page_count)]
        self.checked = set()
        self._refresh_page_thumbnails()
        return path

    def closeEvent(self, event):
        for doc in self.docs:
            try:
                doc.close()
            except Exception:
                pass
        self.docs.clear()
        super().closeEvent(event)

    def _show_text_blocks(self):
        """현재 선택된 페이지의 텍스트 블록을 보여주고 편집 미리보기를 제공한다."""
        if self.current_index < 0 or not self.docs:
            QMessageBox.information(self, "안내", "먼저 PDF 파일을 선택하세요.")
            return
        # 현재 보이는 페이지 중 첫 번째 또는 선택된 페이지
        page_idx = 0
        if self.checked:
            page_idx = min(self.checked)
        elif self.page_plan:
            page_idx = 0
        doc = self.docs[self.current_index]
        blocks = extract_text_blocks(doc, page_idx)
        if not blocks:
            QMessageBox.information(self, "텍스트 블록", "이 페이지에서 텍스트 블록을 찾지 못했습니다.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"텍스트 블록 (페이지 {page_idx + 1})")
        dlg.resize(640, 480)
        lay = QVBoxLayout(dlg)

        info = QLabel("블록을 선택하면 원본 텍스트와 속성을 확인할 수 있습니다.\n수정 후 '미리보기'를 누르면 길이 변화와 영역 초과 가능성을 보여줍니다.")
        lay.addWidget(info)

        list_w = QListWidget()
        for i, b in enumerate(blocks):
            preview = (b["text"][:40] + "...") if len(b["text"]) > 40 else b["text"]
            fs = f" {b['font_size']:.1f}pt" if b.get("font_size") else ""
            list_w.addItem(f"{i+1}. {preview}{fs}")
        lay.addWidget(list_w, 1)

        edit = QLineEdit()
        edit.setPlaceholderText("선택한 블록의 텍스트를 수정해 보세요")
        lay.addWidget(edit)

        result_lbl = QLabel("")
        result_lbl.setWordWrap(True)
        lay.addWidget(result_lbl)

        def on_select():
            row = list_w.currentRow()
            if row < 0:
                return
            edit.setText(blocks[row]["text"])
            result_lbl.setText("")

        def on_preview():
            row = list_w.currentRow()
            if row < 0:
                return
            prev = preview_text_edit(blocks[row], edit.text())
            msg = f"원본 길이: {len(prev['original'])} → 수정 후: {len(prev['new'])} (차이 {prev['length_change']:+d})"
            if prev.get("font_size"):
                msg += f"\n글자 크기: {prev['font_size']:.1f}pt"
            if prev.get("font_name"):
                msg += f" · 글꼴: {prev['font_name']}"
            if prev["warning"]:
                msg += f"\n⚠️ {prev['warning']}"
            else:
                msg += "\n영역 초과 가능성 낮음"
            result_lbl.setText(msg)

        list_w.currentRowChanged.connect(lambda _: on_select())
        btn_preview = QPushButton("편집 미리보기")
        btn_preview.clicked.connect(on_preview)
        lay.addWidget(btn_preview)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)

        if blocks:
            list_w.setCurrentRow(0)
        dlg.exec()

