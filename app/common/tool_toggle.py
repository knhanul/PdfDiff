from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton


class ToolSwitchToggle(QFrame):
    """두 화면을 전환하는 세그먼트 토글.

    활성 화면은 채워진 pill로 표시되고, 다른 세그먼트를 누르면
    index_changed(index) 시그널이 발생한다.
    """

    index_changed = pyqtSignal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setObjectName("toolToggle")
        self.setToolTip("비교 화면 전환")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        caption = QLabel("화면")
        caption.setObjectName("toolToggleCaption")
        layout.addWidget(caption)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons = []
        for index, label in enumerate(labels):
            button = QPushButton(label)
            button.setObjectName("toolToggleBtn")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(f"{label} 화면으로 전환")
            button.clicked.connect(lambda checked, i=index: self.index_changed.emit(i))
            layout.addWidget(button)
            self._group.addButton(button, index)
            self.buttons.append(button)

        self.apply_theme()

    def apply_theme(self, theme_id=None):
        """현재 테마에 맞춰 세그먼트 토글 색상을 갱신한다 (기본 테마는 기존 스타일 유지)."""
        from app.services import app_settings
        from app.shell.theme import THEMES, theme_tokens

        if theme_id is None:
            theme_id = app_settings.get("ui/theme")
        if theme_id not in THEMES or theme_id == "default":
            self.setStyleSheet("""
                QFrame#toolToggle {
                    background-color: #E7E2DE;
                    border: 1px solid #D5CEC8;
                    border-radius: 12px;
                }
                QLabel#toolToggleCaption {
                    color: #8E4235;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 0 4px 0 6px;
                    background: transparent;
                }
                QFrame#toolToggle QPushButton#toolToggleBtn {
                    background-color: transparent;
                    border: none;
                    border-radius: 8px;
                    color: #6B6562;
                    font-size: 12px;
                    font-weight: 500;
                    padding: 4px 12px;
                    min-height: 22px;
                }
                QFrame#toolToggle QPushButton#toolToggleBtn:hover {
                    background-color: rgba(164, 71, 53, 0.08);
                    color: #343434;
                }
                QFrame#toolToggle QPushButton#toolToggleBtn:checked {
                    background-color: #A44735;
                    color: #FFFFFF;
                    font-weight: 700;
                }
            """)
            return

        tokens = theme_tokens(theme_id)
        on_accent = "#202124" if theme_id in ("energy", "black") else "#FFFFFF"
        self.setStyleSheet(f"""
            QFrame#toolToggle {{
                background-color: {tokens['sidebar_bg']};
                border: 1px solid {tokens['border']};
                border-radius: 12px;
            }}
            QLabel#toolToggleCaption {{
                color: {tokens['accent']};
                font-size: 11px;
                font-weight: 700;
                padding: 0 4px 0 6px;
                background: transparent;
            }}
            QFrame#toolToggle QPushButton#toolToggleBtn {{
                background-color: transparent;
                border: none;
                border-radius: 8px;
                color: {tokens['text_muted']};
                font-size: 12px;
                font-weight: 500;
                padding: 4px 12px;
                min-height: 22px;
            }}
            QFrame#toolToggle QPushButton#toolToggleBtn:hover {{
                background-color: {tokens['hover']};
                color: {tokens['text']};
            }}
            QFrame#toolToggle QPushButton#toolToggleBtn:checked {{
                background-color: {tokens['accent']};
                color: {on_accent};
                font-weight: 700;
            }}
        """)

    def set_active(self, index):
        """활성 세그먼트 표시 (시그널 발생 없음)."""
        self.buttons[index].setChecked(True)

