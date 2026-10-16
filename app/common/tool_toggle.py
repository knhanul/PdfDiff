from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton


class ToolSwitchToggle(QFrame):
    """두 도구를 전환하는 세그먼트 토글.

    활성 세그먼트는 흰색 pill로 강조되고, 다른 세그먼트를 클릭하면
    index_changed(index) 시그널이 발생한다.
    """

    index_changed = pyqtSignal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setObjectName('toolToggle')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons = []
        for index, label in enumerate(labels):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked, i=index: self.index_changed.emit(i))
            layout.addWidget(button)
            self._group.addButton(button, index)
            self.buttons.append(button)

        self.setStyleSheet('''
            QFrame#toolToggle {
                background-color: #E5E5EA;
                border-radius: 10px;
            }
            QFrame#toolToggle QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 7px;
                color: #777777;
                font-size: 12px;
                font-weight: 500;
                padding: 6px 14px;
            }
            QFrame#toolToggle QPushButton:hover {
                color: #343434;
            }
            QFrame#toolToggle QPushButton:checked {
                background-color: #FFFFFF;
                color: #343434;
                font-weight: 600;
            }
        ''')

    def set_active(self, index):
        """활성 세그먼트 표시 (시그널 발생 없음)."""
        self.buttons[index].setChecked(True)
