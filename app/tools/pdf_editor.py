import os
from pathlib import Path

import pymupdf
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QImage, QDragEnterEvent, QDropEvent, QIcon, QTransform
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QListWidget, QListWidgetItem, QMessageBox, QFrame, QSplitter,
    QTabWidget, QLineEdit, QSpinBox, QRadioButton, QProgressBar,
    QAbstractItemView, QButtonGroup,
)

from app.common.styles import MODERN_QSS

BASE_ICON = (120, 160)


class PdfEditorWidget(QWidget):
    """통합 PDF 편집: 분할 / 병합 / 페이지 편집 (미리보기 후 실행)"""

    def __init__(self, parent=None, comparison_settings=None):
        super().__init__(parent)
        self.setStyleSheet(MODERN_QSS)
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

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        file_head = QHBoxLayout()
        file_head.addWidget(QLabel("불러온 PDF"))
        file_head.addStretch()
        btn_add = QPushButton("파일 추가")
        btn_add.setObjectName("actionBtn")
        btn_add.clicked.connect(self.add_files)
        file_head.addWidget(btn_add)
        left_layout.addLayout(file_head)

        self.empty_hint = QLabel("PDF를 끌어다 놓거나 파일 추가")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setStyleSheet("color: #888; padding: 12px;")
        left_layout.addWidget(self.empty_hint)

        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(160)
        self.file_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.file_list.currentRowChanged.connect(self.on_file_selected)
        self.file_list.model().rowsMoved.connect(self._on_file_order_changed)
        left_layout.addWidget(self.file_list)

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
        self.page_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.page_list.setSpacing(8)
        self.page_list.itemChanged.connect(self._on_page_item_changed)
        self.page_list.itemPressed.connect(self._on_page_pressed)
        self.page_list.itemClicked.connect(self._on_page_clicked)
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
        right_layout.addWidget(self.tabs)

        self.preview_label = QLabel("페이지를 체크하거나 하이라이트한 뒤 작업을 선택하세요. 실행 전까지 원본은 바뀌지 않습니다.")
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet("background: #f8f8f8; padding: 8px; border-radius: 4px;")
        right_layout.addWidget(self.preview_label)

        btn_row = QHBoxLayout()
        self.btn_preview = QPushButton("미리보기")
        self.btn_preview.clicked.connect(self.do_preview)
        self.btn_execute = QPushButton("실행")
        self.btn_execute.setObjectName("actionBtn")
        self.btn_execute.clicked.connect(self.do_execute)
        btn_row.addWidget(self.btn_preview)
        btn_row.addWidget(self.btn_execute)
        right_layout.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        right_layout.addWidget(self.progress)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self._create_bottom_bar(root)
        self._update_empty_hint()

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

    def _create_split_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.split_group = QButtonGroup(w)
        self.radio_keep = QRadioButton("체크한 페이지 / 나머지로 두 파일")
        self.radio_groups = QRadioButton("체크한 연속 구간마다 파일")
        self.radio_range = QRadioButton("페이지 범위 (예: 1-5, 6-10)")
        self.radio_every = QRadioButton("N페이지마다")
        self.radio_each = QRadioButton("각 페이지 개별 추출")
        for radio in (self.radio_keep, self.radio_groups, self.radio_range, self.radio_every, self.radio_each):
            self.split_group.addButton(radio)
            lay.addWidget(radio)
        self.radio_keep.setChecked(True)
        self.edit_range = QLineEdit()
        self.edit_range.setPlaceholderText("1-5, 6-10, 11-")
        lay.addWidget(self.edit_range)
        row = QHBoxLayout()
        row.addWidget(QLabel("N:"))
        self.spin_every = QSpinBox()
        self.spin_every.setRange(1, 9999)
        self.spin_every.setValue(10)
        row.addWidget(self.spin_every)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()
        return w

    def _create_merge_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("여러 PDF를 끌어다 놓거나 [파일 추가]로 불러오세요.\n왼쪽 목록 순서대로 병합됩니다."))
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
        lay.addWidget(QLabel("미리보기에서 체크하거나 하이라이트한 페이지에 적용합니다.\n썸네일이 바로 바뀌고, 실행을 눌러야 파일로 저장됩니다."))
        actions = [
            ("선택 페이지 추출", lambda: self._stage_page("extract")),
            ("선택 페이지 삭제", self._delete_checked),
            ("선택 페이지 90° 회전", self._rotate_checked),
            ("선택 페이지 맨 앞으로", lambda: self._move_checked("front")),
            ("선택 페이지 맨 뒤로", lambda: self._move_checked("back")),
            ("현재 구성으로 저장", lambda: self._stage_page("save")),
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
        paths, _ = QFileDialog.getOpenFileNames(self, "PDF 선택", "", "PDF Files (*.pdf)")
        if paths:
            self._load_files(paths)

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
            self.docs.append(doc)
            self.file_paths.append(path)
            item = QListWidgetItem(f"{os.path.basename(path)}  ({doc.page_count}p)")
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.file_list.addItem(item)
            if first_new is None:
                first_new = self.file_list.count() - 1
        self._update_empty_hint()
        if self.current_index < 0 and first_new is not None:
            self.file_list.setCurrentRow(first_new)

    def _update_empty_hint(self):
        self.empty_hint.setVisible(self.file_list.count() == 0)

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

    def _refresh_page_thumbnails(self):
        self._updating_pages = True
        self.page_list.clear()
        for plan in self.page_plan:
            label = f"p{plan['src'] + 1}"
            if plan["rot"] % 360:
                label += f" {plan['rot'] % 360}°"
            item = QListWidgetItem(QIcon(self._display_pixmap(plan)), label)
            item.setData(Qt.ItemDataRole.UserRole, plan["src"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = plan["src"] in self.checked
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            item.setSelected(checked)
            self.page_list.addItem(item)
        self._updating_pages = False
        self._update_sel_label()

    def _apply_zoom_size(self):
        scale = self.thumb_scale
        w = int(BASE_ICON[0] * scale)
        h = int(BASE_ICON[1] * scale)
        self.page_list.setIconSize(QSize(w, h))
        self.page_list.setGridSize(QSize(w + 28, h + 40))
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
            if item.checkState() == Qt.CheckState.Checked or item.isSelected():
                sources.add(item.data(Qt.ItemDataRole.UserRole))
        self.checked = sources
        return sources

    def _on_page_pressed(self, item):
        self._press_check = item.checkState()

    def _on_page_clicked(self, item):
        if self._updating_pages:
            return
        if item.checkState() != getattr(self, "_press_check", item.checkState()):
            return
        src = item.data(Qt.ItemDataRole.UserRole)
        self._updating_pages = True
        if src in self.checked:
            self.checked.discard(src)
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            self.checked.add(src)
            item.setCheckState(Qt.CheckState.Checked)
        self._updating_pages = False
        self._update_sel_label()

    def _on_page_item_changed(self, item):
        if self._updating_pages:
            return
        src = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self.checked.add(src)
        else:
            self.checked.discard(src)
        self._update_sel_label()

    def _update_sel_label(self):
        self.lbl_sel.setText(f"선택 {len(self.checked)} / 전체 {len(self.page_plan)}")

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
            QMessageBox.warning(self, "알림", "페이지 미리보기에서 페이지를 체크하거나 선택하세요.")
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

    def move_file_up(self):
        row = self.file_list.currentRow()
        if row > 0:
            self._swap_files(row, row - 1)

    def move_file_down(self):
        row = self.file_list.currentRow()
        if 0 <= row < self.file_list.count() - 1:
            self._swap_files(row, row + 1)

    def _on_file_order_changed(self):
        new_docs = []
        new_paths = []
        for i in range(self.file_list.count()):
            path = self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
            if path not in self.file_paths:
                return
            idx = self.file_paths.index(path)
            new_docs.append(self.docs[idx])
            new_paths.append(path)
        self.docs = new_docs
        self.file_paths = new_paths
        item = self.file_list.currentItem()
        if item is not None and item.data(Qt.ItemDataRole.UserRole) in self.file_paths:
            self.current_index = self.file_paths.index(item.data(Qt.ItemDataRole.UserRole))

    def _swap_files(self, a, b):
        self.file_list.model().blockSignals(True)
        item = self.file_list.takeItem(a)
        self.file_list.insertItem(b, item)
        self.file_list.model().blockSignals(False)
        self._on_file_order_changed()
        self.file_list.setCurrentRow(b)

    def do_preview(self):
        tab = self.tabs.currentIndex()
        if tab == 0:
            self._preview_split()
        elif tab == 1:
            self._preview_merge()
        elif self._planned_action and self._planned_action[0] == "page":
            self._preview_page()
        else:
            self.preview_label.setText("페이지 편집에서 작업을 먼저 선택하세요.")

    def _preview_split(self):
        self._sync_checked()
        if self.current_index < 0:
            self._planned_action = None
            self.preview_label.setText("먼저 PDF를 불러오세요.")
            return False
        doc = self.docs[self.current_index]
        total = doc.page_count
        base = Path(self.file_paths[self.current_index]).stem
        if self.radio_groups.isChecked() or self.radio_keep.isChecked():
            if not self.checked:
                self._planned_action = None
                self.preview_label.setText("나눌 페이지를 미리보기에서 체크하세요.")
                return False
            if self.radio_groups.isChecked():
                groups = [[dict(plan) for plan in group] for group in self._checked_groups()]
                if not groups:
                    self._planned_action = None
                    self.preview_label.setText("나눌 페이지를 미리보기에서 체크하세요.")
                    return False
                desc = ", ".join(self._plan_range_text(group) for group in groups)
                self._planned_action = ("split", {"mode": "groups", "base": base, "groups": groups})
                self.preview_label.setText(f"분할 미리보기: 연속 구간 {len(groups)}개 파일\n{desc}")
            else:
                picked = [dict(plan) for plan in self.page_plan if plan["src"] in self.checked]
                rest = [dict(plan) for plan in self.page_plan if plan["src"] not in self.checked]
                if not picked or not rest:
                    self._planned_action = None
                    self.preview_label.setText("선택 페이지와 나머지 페이지가 모두 있어야 두 파일로 나눌 수 있습니다.")
                    return False
                self._planned_action = ("split", {"mode": "keep", "base": base, "picked": picked, "rest": rest})
                self.preview_label.setText(f"분할 미리보기: 선택 {len(picked)}페이지 / 나머지 {len(rest)}페이지")
        elif self.radio_range.isChecked():
            text = self.edit_range.text().strip()
            if not text:
                self._planned_action = None
                self.preview_label.setText("범위를 입력하세요. 예: 1-5, 6-10")
                return False
            ranges = self._parse_ranges(text, total)
            self._planned_action = ("split", {"mode": "range", "ranges": ranges, "base": base})
            desc = ", ".join(f"{s + 1}-{e}" for s, e in ranges)
            self.preview_label.setText(f"분할 미리보기: {len(ranges)}개 파일\n{desc}")
        elif self.radio_every.isChecked():
            n = self.spin_every.value()
            parts = (total + n - 1) // n
            self._planned_action = ("split", {"mode": "every", "n": n, "base": base})
            self.preview_label.setText(f"분할 미리보기: {n}페이지마다 → {parts}개 파일")
        else:
            self._planned_action = ("split", {"mode": "each", "base": base})
            self.preview_label.setText(f"분할 미리보기: {total}개 개별 파일")
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
        if len(self.docs) < 2:
            self.preview_label.setText("병합하려면 PDF를 2개 이상 불러오세요.")
            return False
        names = [os.path.basename(path) for path in self.file_paths]
        self._planned_action = ("merge", {})
        self.preview_label.setText("병합 미리보기 (순서):\n" + " → ".join(names))
        return True

    def _stage_page(self, mode):
        if not self._require_doc():
            return
        self._sync_checked()
        if mode == "extract":
            plans = [dict(plan) for plan in self.page_plan if plan["src"] in self.checked]
            if not plans:
                self.preview_label.setText("추출할 페이지를 체크하세요.")
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
            self.preview_label.setText("추출 미리보기: 페이지 " + ", ".join(pages))
        else:
            rotated = sum(1 for plan in plans if plan["rot"] % 360)
            notes = []
            if rotated:
                notes.append(f"회전 {rotated}페이지")
            notes.append(f"저장 {len(plans)}페이지")
            self.preview_label.setText("페이지 편집 미리보기: " + ", ".join(notes))

    def do_execute(self):
        tab = self.tabs.currentIndex()
        if tab == 0:
            if not self._preview_split():
                return
        elif tab == 1:
            if not self._preview_merge():
                return
        elif not (self._planned_action and self._planned_action[0] == "page"):
            self.preview_label.setText("페이지 편집에서 작업을 먼저 선택하세요.")
            return
        if not self._planned_action:
            return
        kind = self._planned_action[0]
        try:
            if kind == "split":
                self._exec_split()
            elif kind == "merge":
                self._exec_merge()
            elif kind == "page":
                self._exec_page()
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))
        finally:
            self.progress.setVisible(False)

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
        out_dir = Path(self.file_paths[self.current_index]).parent
        base = params["base"]
        total = doc.page_count
        self.progress.setVisible(True)
        mode = params["mode"]
        written = []

        if mode == "groups":
            groups = params["groups"]
            self.progress.setMaximum(len(groups))
            for i, group in enumerate(groups, start=1):
                path = str(out_dir / f"{base}_sel{i}.pdf")
                self._write_plans(doc, group, path)
                written.append(path)
                self.progress.setValue(i)
        elif mode == "keep":
            picked = params["picked"]
            rest = params["rest"]
            self.progress.setMaximum(2)
            selected_path = str(out_dir / f"{base}_selected.pdf")
            rest_path = str(out_dir / f"{base}_rest.pdf")
            self._write_plans(doc, picked, selected_path)
            self.progress.setValue(1)
            self._write_plans(doc, rest, rest_path)
            self.progress.setValue(2)
            written = [selected_path, rest_path]
        elif mode == "range":
            ranges = params["ranges"]
            self.progress.setMaximum(len(ranges))
            for i, (start, end) in enumerate(ranges):
                if start >= end:
                    continue
                path = str(out_dir / f"{base}_p{start + 1}-{end}.pdf")
                plans = [{"src": page, "rot": 0} for page in range(start, end)]
                self._write_plans(doc, plans, path)
                written.append(path)
                self.progress.setValue(i + 1)
        elif mode == "every":
            n = params["n"]
            count = (total + n - 1) // n
            self.progress.setMaximum(count)
            part = 1
            for start in range(0, total, n):
                end = min(start + n, total)
                path = str(out_dir / f"{base}_part{part}.pdf")
                plans = [{"src": page, "rot": 0} for page in range(start, end)]
                self._write_plans(doc, plans, path)
                written.append(path)
                self.progress.setValue(part)
                part += 1
        else:
            self.progress.setMaximum(total)
            for i in range(total):
                path = str(out_dir / f"{base}_p{i + 1}.pdf")
                self._write_plans(doc, [{"src": i, "rot": 0}], path)
                written.append(path)
                self.progress.setValue(i + 1)
        names = "\n".join(os.path.basename(path) for path in written)
        QMessageBox.information(self, "완료", f"분할이 완료되었습니다.\n{out_dir}\n{names}")

    def _exec_merge(self):
        save_path, _ = QFileDialog.getSaveFileName(self, "병합 파일 저장", "merged.pdf", "PDF Files (*.pdf)")
        if not save_path:
            return
        out = pymupdf.open()
        for doc in self.docs:
            out.insert_pdf(doc)
        out.save(save_path)
        out.close()
        QMessageBox.information(self, "완료", f"병합 완료:\n{save_path}")

    def _exec_page(self):
        doc = self.docs[self.current_index]
        save_path, _ = QFileDialog.getSaveFileName(self, "저장", "edited.pdf", "PDF Files (*.pdf)")
        if not save_path:
            return
        plans = self._planned_action[1]["plans"]
        if not plans:
            QMessageBox.warning(self, "알림", "저장할 페이지가 없습니다.")
            return
        self._write_plans(doc, plans, save_path)
        QMessageBox.information(self, "완료", f"저장 완료:\n{save_path}")

    def closeEvent(self, event):
        for doc in self.docs:
            try:
                doc.close()
            except Exception:
                pass
        self.docs.clear()
        super().closeEvent(event)
