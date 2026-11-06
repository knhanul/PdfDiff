"""Screen 7 — 설정 및 작업 공간 관리."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from app.services import app_settings, recent_docs, workspace_session
from app.shell.theme import THEME_CHOICES

ZOOM_CHOICES = [('width', '폭 맞춤'), ('page', '쪽 맞춤'), ('100', '100%')]
OPEN_CHOICES = [('new_tab', '새 탭에서 열기'), ('replace', '현재 탭 바꾸기')]


class SettingsPage(QWidget):
    settings_changed = pyqtSignal(str)
    recent_cleared = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('settingsPage')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        body.setMaximumWidth(720)
        scroll.setWidget(body)
        col = QVBoxLayout(body)
        col.setContentsMargins(24, 16, 24, 24)
        col.setSpacing(12)

        def section(title):
            lbl = QLabel(title)
            lbl.setObjectName('sectionLabel')
            col.addWidget(lbl)
            f = QFormLayout()
            f.setHorizontalSpacing(16)
            col.addLayout(f)
            return f

        f = section('화면')
        self.theme = QComboBox()
        self.theme.setObjectName('themeCombo')
        for key, title in THEME_CHOICES:
            self.theme.addItem(title, key)
        f.addRow('테마', self.theme)
        self.compact = QCheckBox('좁은 창에서 사이드바를 아이콘으로 줄이기')
        f.addRow('사이드바', self.compact)

        f = section('문서 열기')
        self.zoom = QComboBox()
        for k, t in ZOOM_CHOICES:
            self.zoom.addItem(t, k)
        f.addRow('기본 확대율', self.zoom)
        self.open_mode = QComboBox()
        for k, t in OPEN_CHOICES:
            self.open_mode.addItem(t, k)
        f.addRow('기본 열기 방식', self.open_mode)
        self.show_nav = QCheckBox('페이지 탐색 패널 표시')
        f.addRow('탐색 패널', self.show_nav)

        f = section('최근 문서 · 작업 공간')
        self.recent_info = QLabel()
        clear = QPushButton('최근 문서 목록 지우기')
        clear.setObjectName('viewerToolBtn')
        clear.clicked.connect(self._clear_recent)
        row = QHBoxLayout()
        row.addWidget(self.recent_info)
        row.addWidget(clear)
        row.addStretch()
        f.addRow('최근 문서', row)
        self.offer_restore = QCheckBox('시작 화면에 「지난 작업 복원」 표시')
        self.auto_restore = QCheckBox('실행할 때 지난 작업 자동으로 다시 열기')
        f.addRow('작업 공간 복원', self.offer_restore)
        f.addRow('', self.auto_restore)
        forget = QPushButton('저장된 작업 공간 지우기')
        forget.setObjectName('viewerToolBtn')
        forget.clicked.connect(lambda: workspace_session.save_session([]))
        f.addRow('', forget)

        f = section('성능 · 캐시')
        self.cache_mb = QSpinBox()
        self.cache_mb.setRange(64, 2048)
        self.cache_mb.setSingleStep(64)
        self.cache_mb.setSuffix(' MB')
        f.addRow('페이지 이미지 캐시', self.cache_mb)
        self.tool_max = QSpinBox()
        self.tool_max.setRange(1, 6)
        self.tool_max.setSuffix(' 개')
        f.addRow('열어 둘 도구 수', self.tool_max)
        self.threads = QSpinBox()
        self.threads.setRange(1, 4)
        f.addRow('렌더링 작업 수', self.threads)
        hint = QLabel('값을 크게 하면 빠르지만 메모리를 더 사용합니다. 렌더링 작업 수는 다음 실행부터 적용됩니다.')
        hint.setObjectName('mutedLabel')
        hint.setWordWrap(True)
        col.addWidget(hint)

        reset = QPushButton('기본값으로 되돌리기')
        reset.setObjectName('viewerToolBtn')
        reset.clicked.connect(self._reset)
        col.addWidget(reset)
        col.addStretch()

        self._binds = [
            (self.theme, 'ui/theme'),
            (self.compact, 'ui/auto_compact_sidebar'), (self.zoom, 'viewer/default_zoom'),
            (self.open_mode, 'viewer/open_mode'), (self.show_nav, 'viewer/show_nav'),
            (self.offer_restore, 'workspace/offer_restore'), (self.auto_restore, 'workspace/auto_restore'),
            (self.cache_mb, 'perf/render_cache_mb'), (self.tool_max, 'perf/tool_cache_max'),
            (self.threads, 'perf/render_threads'),
        ]
        self.load()
        for w, key in self._binds:
            if isinstance(w, QCheckBox):
                w.toggled.connect(lambda v, k=key: self._save(k, bool(v)))
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(lambda _i, k=key, c=w: self._save(k, c.currentData()))
            else:
                w.valueChanged.connect(lambda v, k=key: self._save(k, int(v)))

    def load(self):
        self._loading = True
        for w, key in self._binds:
            v = app_settings.get(key)
            if isinstance(w, QCheckBox):
                w.setChecked(bool(v))
            elif isinstance(w, QComboBox):
                i = w.findData(v)
                w.setCurrentIndex(max(0, i))
            else:
                w.setValue(int(v))
        self.recent_info.setText(f'{len(recent_docs.load_recent())}개 저장됨')
        self._loading = False

    def _save(self, key, value):
        if self._loading:
            return
        app_settings.set(key, value)
        self.settings_changed.emit(key)

    def _clear_recent(self):
        recent_docs.clear_recent()
        self.recent_info.setText('0개 저장됨')
        self.recent_cleared.emit()

    def _reset(self):
        app_settings.reset()
        self.load()
        self.settings_changed.emit('*')
