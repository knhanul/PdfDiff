"""Ctrl+K command palette: fuzzy-ish search over tools and common actions."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout


def match(query, commands):
    q = query.strip().lower().replace(' ', '')
    if not q:
        return list(commands)
    res = []
    for c in commands:
        hay = (c['title'] + ' ' + c.get('keywords', '')).lower().replace(' ', '')
        if q in hay:
            res.append((0 if hay.startswith(q) else 1, c))
        else:
            it = iter(hay)
            if all(ch in it for ch in q):
                res.append((2, c))
    return [c for _, c in sorted(res, key=lambda x: x[0])]


class CommandPalette(QDialog):
    def __init__(self, commands, parent=None):
        super().__init__(parent)
        self.setObjectName('commandPalette')
        self.setWindowTitle('명령 찾기')
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setMinimumWidth(520)
        self.commands = commands
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText('도구나 명령 이름 입력 (예: 비교, 열기, 설정)')
        self.list = QListWidget()
        lay.addWidget(self.edit)
        lay.addWidget(self.list)
        self.edit.textChanged.connect(self.refresh)
        self.edit.returnPressed.connect(self.run_selected)
        self.list.itemActivated.connect(lambda _i: self.run_selected())
        self.edit.installEventFilter(self)
        self.refresh('')

    def refresh(self, text):
        self.list.clear()
        for c in match(text, self.commands):
            it = QListWidgetItem(c['title'] + (f"    {c['shortcut']}" if c.get('shortcut') else ''))
            it.setData(Qt.ItemDataRole.UserRole, c)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if obj is self.edit and ev.type() == QEvent.Type.KeyPress and ev.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            r = self.list.currentRow() + (1 if ev.key() == Qt.Key.Key_Down else -1)
            if 0 <= r < self.list.count():
                self.list.setCurrentRow(r)
            return True
        return super().eventFilter(obj, ev)

    def run_selected(self):
        it = self.list.currentItem()
        if not it:
            return
        c = it.data(Qt.ItemDataRole.UserRole)
        self.accept()
        c['run']()
