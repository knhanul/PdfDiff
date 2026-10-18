"""Shared, session-scoped comparison settings and the common settings dialog."""

from html import escape

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QLabel, QPushButton, QVBoxLayout, QWidget)

from app.common.comparison_options import ComparisonOptions, visible_whitespace


class ComparisonSettings(QObject):
    changed = pyqtSignal(object)
    busy_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.options = ComparisonOptions()
        self.revision = 0
        self._busy_owners = set()

    @property
    def busy(self):
        return bool(self._busy_owners)

    def set_busy(self, owner, busy):
        was_busy = self.busy
        if busy:
            self._busy_owners.add(id(owner))
        else:
            self._busy_owners.discard(id(owner))
        if self.busy != was_busy:
            self.busy_changed.emit(self.busy)

    def set_options(self, options):
        if self.busy or options == self.options:
            return False
        self.options = options
        self.revision += 1
        self.changed.emit(options)
        return True


class ComparisonOptionsDialog(QDialog):
    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setWindowTitle('비교 조건')
        self.setMinimumWidth(490)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        self.mode_combo = QComboBox()
        for label, mode in (('본문 비교 (기존 방식)', 'body'),
                            ('엄격한 텍스트 비교', 'strict'), ('사용자 설정', 'custom')):
            self.mode_combo.addItem(label, mode)
        layout.addWidget(self.mode_combo)
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        self.option_panel = QWidget()
        option_layout = QVBoxLayout(self.option_panel)
        option_layout.setContentsMargins(0, 0, 0, 0)
        option_layout.setSpacing(10)
        self.checkboxes = {}
        for name, label in (
            ('ignore_spaces', '공백 차이 비교 (띄어쓰기·탭 포함)'),
            ('ignore_line_breaks', '줄바꿈 차이 비교'),
            ('ignore_case', '영문 대소문자 차이 비교'),
            ('ignore_symbols', '특수문자 차이 비교 (문장부호·%·+·=·₩ 등)'),
        ):
            checkbox = QCheckBox(label)
            checkbox.setChecked(not getattr(options, name))
            option_layout.addWidget(checkbox)
            self.checkboxes[name] = checkbox
        layout.addWidget(self.option_panel)

        note = QLabel('두 비교 화면에 함께 적용됩니다. 조건 변경 후에는 다시 비교해주세요.\n'
                      '줄바꿈은 PDF에서 추출한 줄·페이지 경계를 기준으로 비교합니다.\n'
                      '글꼴·색상·이미지는 텍스트 비교 대상에 포함되지 않습니다.')
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('적용')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(options.mode))
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        self._mode_changed()

    def _mode_changed(self):
        mode = self.mode_combo.currentData()
        self.option_panel.setVisible(mode != 'body')
        self.option_panel.setEnabled(mode == 'custom')
        if mode == 'strict':
            for checkbox in self.checkboxes.values():
                checkbox.setChecked(True)
        self.description_label.setText(
            '체크한 항목의 차이를 비교합니다. 체크를 해제하면 해당 차이를 무시합니다.'
            if mode == 'custom' else ComparisonOptions(mode=mode).description)

    def selected_options(self):
        return ComparisonOptions(mode=self.mode_combo.currentData(), **{
            name: not checkbox.isChecked() for name, checkbox in self.checkboxes.items()
        })


class ComparisonSettingsMixin:
    def setup_comparison_settings(self, settings=None):
        self.comparison_settings = settings if settings is not None else ComparisonSettings(self)
        self.comparison_settings.changed.connect(self._comparison_options_changed)

    def add_comparison_options_button(self, layout):
        self.btn_comparison_options = QPushButton()
        self.btn_comparison_options.setObjectName('compareUtilityBtn')
        self.btn_comparison_options.setFixedHeight(40)
        self.btn_comparison_options.clicked.connect(self.show_comparison_options)
        self.comparison_settings.busy_changed.connect(self._set_options_busy)
        self._set_options_busy(self.comparison_settings.busy)
        self._update_options_button()
        layout.addWidget(self.btn_comparison_options)

    def _set_options_busy(self, busy):
        self.btn_comparison_options.setEnabled(not busy)

    def _update_options_button(self):
        options = self.comparison_settings.options
        self.btn_comparison_options.setText(f'비교 조건 · {options.label}')
        self.btn_comparison_options.setToolTip(options.description)

    def show_comparison_options(self):
        if self.comparison_settings.busy:
            return
        dialog = ComparisonOptionsDialog(self.comparison_settings.options, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.comparison_settings.set_options(dialog.selected_options())

    def _comparison_options_changed(self, options):
        self._update_options_button()
        self._displayed_comparison_revision = None
        # Existing nonmodal result windows must not continue displaying stale data.
        dialog = getattr(self, 'diff_list_dialog', None)
        if dialog is not None:
            try:
                dialog.close()
            except RuntimeError:  # The user may already have closed/deleteLater'd it.
                pass
            self.diff_list_dialog = None
        self.last_s1_norm = self.last_s2_norm = ''
        self.last_s1_raw = self.last_s2_raw = ''
        self.diff_list.clear()
        if hasattr(self, 'sync_anchor_pairs'):
            self.sync_anchor_pairs = []
        for viewer in (self.viewer1, self.viewer2):
            viewer.comparison_options = options
            viewer.char_data = []
            viewer.raw_text = ''
            viewer.word_highlights.clear()
            viewer.diff_pages = []
            viewer.diff_index = -1
            viewer.last_compared_area.clear()
            if hasattr(viewer, 'rebuild_selection_data'):
                viewer.rebuild_selection_data()
            viewer.refresh_highlights()
        if self.viewer1.pdf_doc or self.viewer2.pdf_doc:
            self.btn_compare.setText('▶️  재비교')
            self.btn_compare.setToolTip('비교 조건이 변경되었습니다. 다시 비교해주세요.')

    def mark_comparison_current(self):
        self._displayed_comparison_revision = self.comparison_settings.revision
        self.btn_compare.setText('▶️  비교 실행')
        self.btn_compare.setToolTip('')

    def display_difference_text(self, text):
        return text if self.comparison_settings.options.mode == 'body' else visible_whitespace(text)

    def comparison_caution_html(self):
        options = self.comparison_settings.options
        return (f'<div style="margin-bottom:12px;">• <b>비교 조건 ({options.label})</b>: '
                f'{escape(options.description)}</div>')
