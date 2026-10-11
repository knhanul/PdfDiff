import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QEvent, QFileInfo, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QFileIconProvider, QFormLayout,
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QPushButton, QRadioButton, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QInputDialog,
)

from app.common.file_names import build_new_name, direct_name, unique_name
from app.common.loading_dialog import note_progress, style_task_progress
from app.common.styles import COLOR_BORDER, COLOR_PRIMARY, COLOR_SIDEBAR_BG, COLOR_TEXT_PRIMARY, MODERN_QSS
from app.common.user_prefs import load_dir, save_dir

OUTPUT_KEY = "output/file_rename"
COLUMNS = ("", "현재 이름", "변경 이름", "유형", "수정일자", "경로")


class CheckBoxHeader(QHeaderView):
    clicked_all = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setSectionsMovable(True)
        self.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setStretchLastSection(True)
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


class FileRenameWidget(QWidget):
    """체크한 파일의 이름을 규칙에 맞게 바꾼다."""

    def __init__(self, parent=None, comparison_settings=None):
        super().__init__(parent)
        self.setStyleSheet(MODERN_QSS)
        self.setAcceptDrops(True)
        self.output_dir = ""
        self.paths = []
        self._updating = False
        self.icon_provider = QFileIconProvider()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.file_table = QTableWidget(0, len(COLUMNS))
        self.header = CheckBoxHeader(self.file_table)
        self.file_table.setHorizontalHeader(self.header)
        self.file_table.setHorizontalHeaderLabels(COLUMNS)
        self.header.clicked_all.connect(self._toggle_all)
        self.file_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.file_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.file_table.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.file_table.setShowGrid(False)
        self.file_table.setIconSize(QSize(20, 20))
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.itemChanged.connect(self._on_item_changed)
        self.file_table.cellClicked.connect(self._on_cell_clicked)
        self.file_table.setColumnWidth(0, 40)
        self.file_table.setColumnWidth(1, 220)
        self.file_table.setColumnWidth(2, 240)
        self.file_table.setColumnWidth(3, 120)
        self.file_table.setColumnWidth(4, 140)
        self._style_table()
        left_layout.addWidget(self.file_table, 1)
        buttons = QHBoxLayout()
        for title, handler in (("파일 추가", self.add_files), ("폴더 추가", self.add_folder), ("체크 삭제", self.remove_checked)):
            button = QPushButton(title)
            if title == "파일 추가":
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
        hint = QLabel("변경 이름을 더블클릭하거나 이름 변경을 누르면 그 파일 이름을 직접 고칠 수 있습니다.\n직접 고친 이름은 규칙을 바꿔도 유지됩니다. 칸을 비우면 규칙으로 돌아갑니다.")
        hint.setWordWrap(True)
        right_layout.addWidget(hint)

        form = QFormLayout()
        self.find_edit = QLineEdit()
        self.replace_edit = QLineEdit()
        self.prefix_edit = QLineEdit()
        self.suffix_edit = QLineEdit()
        form.addRow("찾을 글자", self.find_edit)
        form.addRow("바꿀 글자", self.replace_edit)
        form.addRow("앞에 추가", self.prefix_edit)
        form.addRow("뒤에 추가", self.suffix_edit)
        right_layout.addLayout(form)

        number_row = QHBoxLayout()
        self.number_check = QCheckBox("번호 붙이기")
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 999999)
        self.start_spin.setValue(1)
        self.digits_spin = QSpinBox()
        self.digits_spin.setRange(1, 6)
        self.digits_spin.setValue(3)
        self.number_front = QRadioButton("이름 앞")
        self.number_back = QRadioButton("이름 뒤")
        self.number_front.setChecked(True)
        number_row.addWidget(self.number_check)
        number_row.addWidget(QLabel("시작"))
        number_row.addWidget(self.start_spin)
        number_row.addWidget(QLabel("자릿수"))
        number_row.addWidget(self.digits_spin)
        number_row.addWidget(self.number_front)
        number_row.addWidget(self.number_back)
        right_layout.addLayout(number_row)

        folder_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText("결과 폴더 미지정 (원래 위치에서 이름 변경)")
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

        self.btn_rename = QPushButton("이름 변경")
        self.btn_rename.setToolTip("체크한 파일 하나의 이름을 직접 입력합니다.")
        self.btn_rename.clicked.connect(self.rename_checked)
        self.btn_apply = QPushButton("이름 적용")
        self.btn_apply.setObjectName("actionBtn")
        self.btn_apply.clicked.connect(self.apply_names)
        action_row = QHBoxLayout()
        action_row.addWidget(self.btn_apply)
        action_row.addWidget(self.btn_rename)
        right_layout.addLayout(action_row)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        style_task_progress(self.progress)
        right_layout.addWidget(self.progress)
        self.status_label = QLabel("파일이나 폴더를 추가하세요.")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)
        right_layout.addWidget(QLabel("작업 이력"))
        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(self.open_history_item)
        right_layout.addWidget(self.history_list, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)
        self._create_bottom_bar(root)

        for widget in (self.find_edit, self.replace_edit, self.prefix_edit, self.suffix_edit):
            widget.textChanged.connect(self.refresh_preview)
        self.number_check.toggled.connect(self._toggle_number)
        self.number_check.toggled.connect(self.refresh_preview)
        self.start_spin.valueChanged.connect(self.refresh_preview)
        self.digits_spin.valueChanged.connect(self.refresh_preview)
        self.number_front.toggled.connect(self.refresh_preview)
        self._toggle_number(False)

    def _style_table(self):
        self.file_table.setStyleSheet(f"""
            QTableWidget {{
                background: white;
                border: 1px solid {COLOR_BORDER};
                outline: none;
                selection-background-color: transparent;
                selection-color: {COLOR_TEXT_PRIMARY};
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
                width: 18px; height: 18px; border: 1.5px solid #C6C6C8; border-radius: 5px; background: white;
            }}
            QCheckBox::indicator:checked {{
                background: {COLOR_PRIMARY}; border: 1.5px solid {COLOR_PRIMARY};
            }}
            QCheckBox::indicator:indeterminate {{
                background: rgba(255, 107, 0, 0.35); border: 1.5px solid {COLOR_PRIMARY};
            }}
        """)

    def _create_bottom_bar(self, parent_layout):
        bar = QFrame()
        bar.setObjectName("actionBar")
        layout = QHBoxLayout(bar)
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

    def _toggle_number(self, checked):
        for widget in (self.start_spin, self.digits_spin, self.number_front, self.number_back):
            widget.setEnabled(checked)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        self._add_paths([url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()])

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "파일 선택", "", "모든 파일 (*.*)")
        self._add_paths(paths)

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "폴더 선택", "")
        if path:
            self._add_paths([path])

    def _iter_files(self, path):
        path = Path(path)
        if path.is_file():
            yield path
            return
        if path.is_dir():
            for found in path.rglob("*"):
                if found.is_file() and not any(part.startswith(".") for part in found.parts):
                    yield found

    def _add_paths(self, paths):
        added = 0
        for raw in paths:
            for found in self._iter_files(raw):
                text = str(found.resolve())
                if text in self.paths:
                    continue
                self._append_row(found, text)
                self.paths.append(text)
                added += 1
        if added == 0 and paths:
            self.status_label.setText("추가할 파일이 없습니다.")
        self._sync_header()
        self._update_count()
        self.refresh_preview()

    def _append_row(self, found, text):
        info = QFileInfo(text)
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        check.setCheckState(Qt.CheckState.Checked)
        name = QTableWidgetItem(self.icon_provider.icon(info), found.name)
        name.setData(Qt.ItemDataRole.UserRole, text)
        name.setToolTip(text)
        new_name = QTableWidgetItem(found.name)
        type_item = QTableWidgetItem(self.icon_provider.type(info) or found.suffix.lower())
        modified = datetime.fromtimestamp(found.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        folder = QTableWidgetItem(str(found.parent))
        row = self.file_table.rowCount()
        self.file_table.insertRow(row)
        for column, item in enumerate((check, name, new_name, type_item, QTableWidgetItem(modified), folder)):
            if column == 2:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable)
            elif column != 0:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.file_table.setItem(row, column, item)

    def _checked_rows(self):
        rows = []
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                rows.append(row)
        return rows

    def refresh_preview(self):
        if self._updating:
            return
        self._updating = True
        reserved = set()
        number = self.start_spin.value() if self.number_check.isChecked() else None
        checked = set(self._checked_rows())
        freeing = set()
        if not self.output_dir:
            for row in checked:
                source = self.file_table.item(row, 1)
                if source is not None:
                    freeing.add(Path(source.data(Qt.ItemDataRole.UserRole)).resolve())
        for row in range(self.file_table.rowCount()):
            source = self.file_table.item(row, 1)
            target = self.file_table.item(row, 2)
            if source is None or target is None:
                continue
            src = Path(source.data(Qt.ItemDataRole.UserRole))
            if row not in checked:
                if not target.data(Qt.ItemDataRole.UserRole + 1):
                    target.setText(src.name)
                target.setData(Qt.ItemDataRole.UserRole, "")
                target.setToolTip("체크되지 않아 유지됩니다.")
                continue
            if target.data(Qt.ItemDataRole.UserRole + 1):
                new_name = direct_name(src.name, target.text())
            else:
                new_name = build_new_name(
                    src.name,
                    self.find_edit.text(),
                    self.replace_edit.text(),
                    self.prefix_edit.text(),
                    self.suffix_edit.text(),
                    number,
                    self.digits_spin.value(),
                    self.number_back.isChecked(),
                )
                if number is not None:
                    number += 1
            directory = Path(self.output_dir) if self.output_dir else src.parent
            final_name = unique_name(directory, new_name, reserved, src, freeing)
            target.setText(final_name)
            target.setData(Qt.ItemDataRole.UserRole, str(directory / final_name))
            target.setToolTip(str(directory / final_name))
        self._updating = False

    def rename_checked(self):
        rows = self._checked_rows()
        if len(rows) != 1:
            QMessageBox.information(self, "알림", "이름을 바꿀 파일 하나만 체크하세요.\n여러 파일이면 변경 이름 칸을 더블클릭해 고칩니다.")
            return
        row = rows[0]
        current = self.file_table.item(row, 2)
        typed, ok = QInputDialog.getText(self, "이름 변경", "새 파일 이름", text=current.text() if current else "")
        if not ok or current is None:
            return
        self._updating = True
        current.setText(typed)
        self._updating = False
        self._accept_typed_name(current)

    def _accept_typed_name(self, item):
        source = self.file_table.item(item.row(), 1)
        if source is None:
            return
        typed = item.text().strip()
        src_name = Path(source.data(Qt.ItemDataRole.UserRole)).name
        self._updating = True
        if typed:
            item.setText(direct_name(src_name, typed))
            item.setData(Qt.ItemDataRole.UserRole + 1, True)
        else:
            item.setData(Qt.ItemDataRole.UserRole + 1, False)
        self._updating = False
        self.refresh_preview()

    def apply_names(self):
        self.refresh_preview()
        plans = []
        for row in self._checked_rows():
            source = self.file_table.item(row, 1)
            target = self.file_table.item(row, 2)
            src = Path(source.data(Qt.ItemDataRole.UserRole))
            dest_text = target.data(Qt.ItemDataRole.UserRole) or ""
            if not dest_text:
                continue
            dest = Path(dest_text)
            if src.name == dest.name and src.parent == dest.parent:
                continue
            plans.append((row, src, dest))
        if not plans:
            QMessageBox.information(self, "알림", "바꿀 이름이 없습니다. 규칙을 입력하고 파일을 체크하세요.")
            return
        self.progress.setVisible(True)
        self.progress.setMaximum(len(plans))
        ok = 0
        failed = []
        if self.output_dir:
            for index, (row, src, dest) in enumerate(plans, start=1):
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    ok += 1
                    self._add_history(f"복사 {src.name}", [str(dest)])
                except Exception as error:
                    failed.append(f"{src.name}: {error}")
                note_progress(self.progress, index)
        else:
            temps = []
            try:
                for index, (row, src, dest) in enumerate(plans, start=1):
                    tmp = src.with_name(f".rename-{uuid.uuid4().hex}{src.suffix}")
                    os.replace(src, tmp)
                    temps.append((row, tmp, dest, src.name))
                    note_progress(self.progress, index)
                for row, tmp, dest, old_name in temps:
                    os.replace(tmp, dest)
                    self._rewrite_row(row, dest)
                    ok += 1
                    self._add_history(f"이름 변경 {old_name}", [str(dest)])
                temps.clear()
            except Exception as error:
                failed.append(str(error))
                for row, tmp, dest, old_name in temps:
                    if not tmp.exists():
                        continue
                    target = dest if not dest.exists() else tmp.with_name(old_name)
                    os.replace(tmp, target)
                    self._rewrite_row(row, target)
        self.progress.setVisible(False)
        self.refresh_preview()
        self.status_label.setText(f"성공 {ok}개, 실패 {len(failed)}개")
        if failed:
            QMessageBox.warning(self, "이름 적용", f"성공 {ok}개, 실패 {len(failed)}개\n\n" + "\n".join(failed[:8]))
        else:
            QMessageBox.information(self, "이름 적용", f"{ok}개 파일 이름을 적용했습니다.")

    def _rewrite_row(self, row, dest):
        text = str(dest.resolve())
        old = self.file_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        if old in self.paths:
            self.paths.remove(old)
        if text not in self.paths:
            self.paths.append(text)
        info = QFileInfo(text)
        name = self.file_table.item(row, 1)
        name.setText(dest.name)
        name.setIcon(self.icon_provider.icon(info))
        name.setData(Qt.ItemDataRole.UserRole, text)
        name.setToolTip(text)
        self.file_table.item(row, 5).setText(str(dest.parent))

    def _on_cell_clicked(self, row, column):
        if column in (0, 2) or self._updating:
            return
        item = self.file_table.item(row, 0)
        if item is None:
            return
        item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)

    def _on_item_changed(self, item):
        if self._updating:
            return
        if item.column() == 2:
            self._accept_typed_name(item)
            return
        if item.column() != 0:
            return
        self._sync_header()
        self._update_count()
        self.refresh_preview()

    def _toggle_all(self):
        checked = len(self._checked_rows()) < self.file_table.rowCount()
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._updating = True
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item is not None:
                item.setCheckState(state)
        self._updating = False
        self._sync_header()
        self._update_count()
        self.refresh_preview()

    def _sync_header(self):
        total = self.file_table.rowCount()
        checked = len(self._checked_rows())
        if total == 0 or checked == 0:
            state = Qt.CheckState.Unchecked
        elif checked == total:
            state = Qt.CheckState.Checked
        else:
            state = Qt.CheckState.PartiallyChecked
        self.header.set_state(state)

    def remove_checked(self):
        rows = self._checked_rows()
        if not rows:
            QMessageBox.warning(self, "알림", "목록에서 뺄 파일을 체크하세요.")
            return
        for row in reversed(rows):
            path = self.file_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            self.file_table.removeRow(row)
            if path in self.paths:
                self.paths.remove(path)
        self._sync_header()
        self._update_count()
        self.refresh_preview()

    def _update_count(self):
        self.count_label.setText(f"체크 {len(self._checked_rows())} / 전체 {self.file_table.rowCount()}")

    def choose_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "결과 폴더 선택", self.output_dir or "")
        if path:
            self.output_dir = path
            self.output_edit.setText(path)
            save_dir(OUTPUT_KEY, path)
            self.refresh_preview()

    def clear_output_dir(self):
        self.output_dir = ""
        self.output_edit.clear()
        save_dir(OUTPUT_KEY, "")
        self.refresh_preview()

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
