import re
from dataclasses import dataclass

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout,
)

from app.common.resources import RELEASE_DATE, VERSION, get_about_image_path
from configs.settings import SETTINGS

POPUP_WIDTH = 360
POPUP_MARGIN = 20
POPUP_RADIUS = 15
IMAGE_MAX_HEIGHT = 200
IMAGE_RADIUS = 11

COLOR_BG = '#FCFAF7'
COLOR_TEXT = '#343434'
COLOR_TEXT_MUTED = '#777777'
COLOR_DIVIDER = '#E8E5E1'
COLOR_BTN_BG = '#EFEDEA'
COLOR_BTN_HOVER = '#E5E2DD'
COLOR_BTN_PRESSED = '#DBD8D2'

NO_INFO_TEXT = '정보 없음'
DEFAULT_CREATOR = '우체국금융개발원 나주 AI킥오프 모임'
DEFAULT_ACCENT_COLOR = '#0869ED'


@dataclass
class AboutInfo:
    """공통 정보(About) 팝업 설정 객체.

    프로그램별로 이미지, 이름, 제작자, 브랜드 컬러만 지정하면
    동일한 디자인의 팝업을 재사용할 수 있다.
    """
    app_name: str
    version: str = ''
    build_date: str = ''
    creator: str = DEFAULT_CREATOR
    accent_color: str = DEFAULT_ACCENT_COLOR
    image_path: str | None = None


def _normalize_build_date(value):
    """빌드일자를 YYYY.MM.DD 형식으로 정규화."""
    text = str(value or '').strip()
    match = re.match(r'^(\d{4})[-./](\d{1,2})[-./](\d{1,2})', text)
    if match:
        return f'{match.group(1)}.{int(match.group(2)):02d}.{int(match.group(3)):02d}'
    return text


def get_about_info():
    """현재 프로그램 설정(SETTINGS)과 빌드 메타데이터로 AboutInfo 생성."""
    return AboutInfo(
        app_name=str(SETTINGS.get('APP_NAME') or ''),
        version=str(VERSION or ''),
        build_date=_normalize_build_date(RELEASE_DATE),
        creator=str(SETTINGS.get('ABOUT_CREATOR') or DEFAULT_CREATOR),
        accent_color=str(SETTINGS.get('THEME_COLOR_PRIMARY') or DEFAULT_ACCENT_COLOR),
        image_path=get_about_image_path(),
    )


class AboutDialog(QDialog):
    """nuni 공통 정보(About) 팝업.

    미니멀한 Windows/macOS 스타일의 소형 팝업으로, AboutInfo에 지정된
    대표 이미지, 프로그램명, 버전, 빌드일자, 제작 정보를 표시한다.
    """

    def __init__(self, info: AboutInfo, parent=None):
        super().__init__(parent)
        self._info = info
        self._drag_offset = None
        self._centered = False

        self.setWindowTitle(f'정보 - {info.app_name}')
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedWidth(POPUP_WIDTH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName('aboutCard')
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(POPUP_MARGIN, POPUP_MARGIN, POPUP_MARGIN, 14)
        layout.setSpacing(10)

        image_label = self._build_image_label()
        if image_label:
            image_row = QHBoxLayout()
            image_row.addStretch()
            image_row.addWidget(image_label)
            image_row.addStretch()
            layout.addLayout(image_row)

        name_label = QLabel(info.app_name or NO_INFO_TEXT)
        name_label.setObjectName('aboutAppName')
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        divider = QFrame()
        divider.setObjectName('aboutDivider')
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(1, 1)
        rows = (
            ('버전', info.version),
            ('빌드일자', info.build_date),
            ('제작', info.creator),
        )
        for row, (title, value) in enumerate(rows):
            title_label = QLabel(title)
            title_label.setObjectName('aboutInfoKey')
            value_label = QLabel(value or NO_INFO_TEXT)
            value_label.setObjectName('aboutInfoValue')
            value_label.setWordWrap(True)
            grid.addWidget(title_label, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value_label, row, 1, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(grid)

        button_row = QHBoxLayout()
        button_row.addStretch()
        close_btn = QPushButton('닫기')
        close_btn.setObjectName('aboutCloseBtn')
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        card.setStyleSheet(f'''
            QFrame#aboutCard {{
                background-color: {COLOR_BG};
                border: 1px solid {COLOR_DIVIDER};
                border-radius: {POPUP_RADIUS}px;
            }}
            QLabel#aboutAppName {{
                color: {info.accent_color};
                font-size: 24px;
                font-weight: 700;
                background: transparent;
            }}
            QLabel#aboutImage {{
                background: transparent;
            }}
            QFrame#aboutDivider {{
                background-color: {COLOR_DIVIDER};
                border: none;
            }}
            QLabel#aboutInfoKey {{
                color: {COLOR_TEXT_MUTED};
                font-size: 12px;
                background: transparent;
            }}
            QLabel#aboutInfoValue {{
                color: {COLOR_TEXT};
                font-size: 12px;
                background: transparent;
            }}
            QPushButton#aboutCloseBtn {{
                background-color: {COLOR_BTN_BG};
                color: {COLOR_TEXT};
                border: none;
                border-radius: 8px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton#aboutCloseBtn:hover {{
                background-color: {COLOR_BTN_HOVER};
            }}
            QPushButton#aboutCloseBtn:pressed {{
                background-color: {COLOR_BTN_PRESSED};
            }}
        ''')

    def _build_image_label(self):
        """대표 이미지 라벨 생성. 원본 비율 유지, 팝업 너비/최대 높이 내 축소.

        이미지가 없거나 로드할 수 없으면 None을 반환해 영역 자체를 숨긴다.
        """
        path = self._info.image_path
        if not path:
            return None
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return None

        content_width = POPUP_WIDTH - 2 * POPUP_MARGIN
        scale = min(
            content_width / pixmap.width(),
            IMAGE_MAX_HEIGHT / pixmap.height(),
            1.0,
        )
        width = max(1, round(pixmap.width() * scale))
        height = max(1, round(pixmap.height() * scale))
        scaled = pixmap.scaled(
            width, height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        rounded = self._rounded_pixmap(scaled, IMAGE_RADIUS)

        label = QLabel()
        label.setObjectName('aboutImage')
        label.setPixmap(rounded)
        label.setFixedSize(rounded.size())
        return label

    @staticmethod
    def _rounded_pixmap(pixmap: QPixmap, radius: float) -> QPixmap:
        """픽스맵 모서리에 라운드를 적용한 새 픽스맵 반환."""
        dpr = pixmap.devicePixelRatio()
        result = QPixmap(pixmap.size())
        result.setDevicePixelRatio(dpr)
        result.fill(Qt.GlobalColor.transparent)

        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(result.rect()), radius * dpr, radius * dpr)
        painter.setClipPath(clip)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return result

    def showEvent(self, event):
        super().showEvent(event)
        if self._centered:
            return
        self._centered = True
        parent = self.parentWidget()
        if parent:
            anchor = parent.window().frameGeometry().center()
        else:
            anchor = QApplication.primaryScreen().availableGeometry().center()
        self.move(anchor - self.rect().center())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)
