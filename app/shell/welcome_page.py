"""Start screen shown immediately on launch (no PDF / tool imports).

Shortcuts intentionally exclude 「PDF 입력폼 관리」; that tool is reachable only from the sidebar menu.
"""
import os

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QPushButton, QVBoxLayout, QWidget)

from app.services import app_settings
from app.shell.sidebar_icons import line_icon
from app.shell.theme import theme_tokens

# (action key, title, description) — no pdf_form here on purpose
WELCOME_SHORTCUTS = [
    ('split_view', '두 PDF 동시 보기', '두 문서를 나란히 열고 함께 스크롤'),
    ('pdf_compare', '영역지정비교', '지정한 영역의 글자를 비교'),
    ('pdf_hf_compare', '전체비교', '페이지 전체를 비교'),
    ('pdf_editor', 'PDF 편집', '분할·병합·페이지 편집'),
    ('pdf_create', 'PDF 생성', '문서·이미지를 PDF로 변환'),
]

FEATURED_SHORTCUT_KEYS = {'pdf_compare', 'pdf_hf_compare'}


def _elide_middle(text, max_chars=48):
    if not text or len(text) <= max_chars:
        return text
    keep = max(10, (max_chars - 3) // 2)
    return f'{text[:keep]}...{text[-keep:]}'


class WelcomePage(QWidget):
    open_requested = pyqtSignal()
    open_path = pyqtSignal(str)
    action_requested = pyqtSignal(str)
    restore_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('welcomePage')
        self.setAcceptDrops(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 20, 28, 20)
        outer.addStretch(1)
        center = QWidget()
        center.setMaximumWidth(800)
        col = QVBoxLayout(center)
        col.setSpacing(14)

        title = QLabel('PDF를 빠르게 열고, 필요한 작업을 한곳에서')
        title.setObjectName('welcomeTitle')
        col.addWidget(title)

        self.drop_zone = QFrame()
        self.drop_zone.setObjectName('dropZone')
        self.drop_zone.setProperty('dragActive', False)
        dl = QVBoxLayout(self.drop_zone)
        dl.setContentsMargins(24, 18, 24, 18)
        dl.setSpacing(10)
        hint = QLabel('여기에 PDF를 끌어다 놓거나')
        hint.setObjectName('mutedLabel')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch()
        btn = QPushButton('PDF 열기  (Ctrl+O)')
        btn.setObjectName('primaryBtn')
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.open_requested.emit)
        row.addWidget(btn)
        self.restore_btn = QPushButton('지난 작업 복원')
        self.restore_btn.setObjectName('viewerToolBtn')
        self.restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restore_btn.clicked.connect(self.restore_requested.emit)
        self.restore_btn.hide()
        row.addWidget(self.restore_btn)
        row.addStretch()
        dl.addWidget(hint)
        dl.addLayout(row)
        col.addWidget(self.drop_zone)

        sc_label = QLabel('주요 작업')
        sc_label.setObjectName('sectionLabel')
        col.addWidget(sc_label)

        self.shortcut_keys = []
        self.shortcut_buttons = {}

        # Row 1: Core differentiation tools (영역지정비교 / 전체비교) side-by-side
        featured_grid = QGridLayout()
        featured_grid.setSpacing(10)
        featured_items = [item for item in WELCOME_SHORTCUTS if item[0] in FEATURED_SHORTCUT_KEYS]
        for col_idx, (key, name, desc) in enumerate(featured_items):
            b = self._create_shortcut_card(key, name, desc, featured=True)
            featured_grid.addWidget(b, 0, col_idx)
        col.addLayout(featured_grid)

        # Row 2: General PDF tools (3 columns)
        general_grid = QGridLayout()
        general_grid.setSpacing(10)
        general_items = [item for item in WELCOME_SHORTCUTS if item[0] not in FEATURED_SHORTCUT_KEYS]
        for col_idx, (key, name, desc) in enumerate(general_items):
            b = self._create_shortcut_card(key, name, desc, featured=False)
            general_grid.addWidget(b, 0, col_idx)
        col.addLayout(general_grid)

        # Preserve WELCOME_SHORTCUTS order in self.shortcut_keys
        self.shortcut_keys = [k for k, *_ in WELCOME_SHORTCUTS]

        rl = QLabel('최근 문서')
        rl.setObjectName('sectionLabel')
        col.addWidget(rl)
        self.recent_list = QListWidget()
        self.recent_list.setObjectName('recentList')
        self.recent_list.setMaximumHeight(210)
        self.recent_list.setIconSize(QSize(18, 18))
        self.recent_list.itemActivated.connect(self._on_recent_activated)
        self.recent_list.itemClicked.connect(self._on_recent_activated)
        col.addWidget(self.recent_list)

        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(center, 4)
        h.addStretch()
        outer.addLayout(h)
        outer.addStretch(2)
        self._recent_paths = []
        self.refresh_theme_icons()

    def _create_shortcut_card(self, key, name, desc, featured=False):
        b = QPushButton()
        b.setObjectName('shortcutTile')
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setProperty('featured', featured)
        b.setProperty('shortcut_key', key)
        icon_key = 'split' if key == 'split_view' else key
        b.setProperty('icon_key', icon_key)
        b.setToolTip(f'{name} — {desc}')
        lay = QHBoxLayout(b)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)
        icon_lbl = QLabel()
        icon_lbl.setObjectName('shortcutTileIcon')
        icon_lbl.setFixedSize(32 if featured else 28, 32 if featured else 28)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        title_lbl = QLabel(name)
        title_lbl.setObjectName('shortcutTileTitle')
        title_lbl.setProperty('featured', featured)
        title_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        desc_lbl = QLabel(desc)
        desc_lbl.setObjectName('shortcutTileDesc')
        desc_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_col.addWidget(title_lbl)
        text_col.addWidget(desc_lbl)
        lay.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(text_col, 1)
        b._icon_label = icon_lbl
        b._title_label = title_lbl
        b._desc_label = desc_lbl
        b.clicked.connect(lambda _=False, k=key: self.action_requested.emit(k))
        self.shortcut_buttons[key] = b
        return b

    def _current_tokens(self):
        try:
            return theme_tokens(app_settings.get('ui/theme'))
        except Exception:
            return theme_tokens('default')

    def refresh_theme_icons(self, tokens=None):
        tokens = tokens or self._current_tokens()
        for key, btn in self.shortcut_buttons.items():
            featured = bool(btn.property('featured'))
            icon_key = btn.property('icon_key') or key
            color = tokens['accent'] if featured else tokens['sidebar_icon']
            sz = 18 if featured else 16
            ic = line_icon(icon_key, color, sz, stroke=1.75 if featured else 1.5)
            btn._icon_label.setPixmap(ic.pixmap(QSize(sz, sz)))
        doc_ic = line_icon('doc', tokens['accent'], 16)
        for i in range(self.recent_list.count()):
            it = self.recent_list.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole):
                it.setIcon(doc_ic)

    def _on_recent_activated(self, item):
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.open_path.emit(path)

    def set_recent(self, paths):
        self._recent_paths = list(paths or [])
        self.recent_list.clear()
        tokens = self._current_tokens()
        doc_ic = line_icon('doc', tokens['accent'], 16)
        for p in self._recent_paths:
            fname = os.path.basename(p)
            folder = _elide_middle(os.path.dirname(p), 54)
            it = QListWidgetItem(doc_ic, '')
            it.setData(Qt.ItemDataRole.UserRole, p)
            it.setToolTip(p)
            it.setSizeHint(QSize(0, 36))
            exists = os.path.isfile(p)
            if not exists:
                it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(it)
            row_w = QWidget()
            row_w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(6, 4, 8, 4)
            rl.setSpacing(10)
            name_lbl = QLabel(fname)
            name_lbl.setObjectName('recentItemTitle')
            name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            path_lbl = QLabel(folder)
            path_lbl.setObjectName('recentItemPath')
            path_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            path_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            if not exists:
                name_lbl.setEnabled(False)
                path_lbl.setEnabled(False)
            rl.addWidget(name_lbl, 0)
            rl.addWidget(path_lbl, 1)
            self.recent_list.setItemWidget(it, row_w)
        if not self._recent_paths:
            it = QListWidgetItem('최근에 연 문서가 없습니다')
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(it)

    def set_restore_available(self, available):
        self.restore_btn.setVisible(bool(available))

    def _set_drag_active(self, active):
        if self.drop_zone.property('dragActive') == active:
            return
        self.drop_zone.setProperty('dragActive', active)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)

    def dragEnterEvent(self, event):
        if any(u.toLocalFile().lower().endswith('.pdf') for u in event.mimeData().urls()):
            self._set_drag_active(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._set_drag_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._set_drag_active(False)
        for u in event.mimeData().urls():
            p = u.toLocalFile()
            if p.lower().endswith('.pdf'):
                self.open_path.emit(p)
        event.acceptProposedAction()
