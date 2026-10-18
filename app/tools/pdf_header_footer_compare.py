import os
import re

import pymupdf
from PyQt6.QtCore import QRect, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QImage, QMovie, QPainter, QPen, QPixmap, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFileDialog, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QStyle, QStyleOptionButton, QVBoxLayout, QWidget,
)

from app.common.loading_dialog import make_overlay_progress, update_overlay_progress
from app.common.resources import get_timer_gif_path
from app.common.styles import (
    COLOR_HEADER_ACCENT, COLOR_PRIMARY, COLOR_WORKSPACE_DARK, COLOR_P1,
    COLOR_P2, COLOR_AREA, HEADER_FOOTER_INSTRUCTION_HTML, MODERN_QSS,
)
from app.common.pdf_search_helper import PDFSearchHelper
from app.common.pdf_compare_worker import CompareThreadManager
from app.common.pdf_text_normalizer import collect_raw_chars, normalize_raw_chars
from app.common.comparison_options import ComparisonOptions
from app.common.comparison_settings import ComparisonSettingsMixin
from app.common.tool_toggle import ToolSwitchToggle


class SyncScrollToggle(QCheckBox):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet('QCheckBox::indicator { width: 36px; height: 20px; border: none; background: transparent; image: none; }')

    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        track = QRectF(self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLOR_PRIMARY if self.isChecked() else '#A0A0A0'))
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        diameter = track.height() - 4
        x = track.right() - diameter - 2 if self.isChecked() else track.left() + 2
        painter.setBrush(QColor('white'))
        painter.drawEllipse(QRectF(x, track.top() + 2, diameter, diameter))
        painter.end()


# ──────────────────────────────────────────────────────────
# HeaderFooterLabel : 페이지 렌더링 + 드래그 가능한 Header/Footer 경계선
# ──────────────────────────────────────────────────────────
class HeaderFooterLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.page_num = -1
        self.header_ratio = 0.0   # 상단 제외 비율 (0 = 제외 없음)
        self.footer_ratio = 0.0   # 하단 제외 비율 (0 = 제외 없음)
        self._dragging_header = False
        self._dragging_footer = False
        self._hit_margin = 8
        self.setMouseTracking(True)
        self.setStyleSheet('border: 0.5px solid #C6C6C8; background-color: white; border-radius: 4px;')
        self.setMargin(0)

    # --- 좌표 계산 ---
    def _image_rect(self):
        pix = self.pixmap()
        if not pix:
            return QRect()
        contents = self.contentsRect()
        x = contents.x() + max(0, (contents.width() - pix.width()) // 2)
        y = contents.y() + max(0, (contents.height() - pix.height()) // 2)
        return QRect(x, y, pix.width(), pix.height())

    def _header_y(self):
        pix = self.pixmap()
        image_rect = self._image_rect()
        return image_rect.y() + int(pix.height() * self.header_ratio) if pix else 0

    def _footer_y(self):
        pix = self.pixmap()
        image_rect = self._image_rect()
        return image_rect.y() + int(pix.height() * (1.0 - self.footer_ratio)) if pix else self.height()

    def _ratio_from_widget_y(self, y):
        image_rect = self._image_rect()
        if image_rect.height() <= 0:
            return 0.0
        local_y = y - image_rect.y()
        return max(0.0, min(1.0, local_y / image_rect.height()))

    # --- 마우스 이벤트 ---
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        y = event.position().toPoint().y()
        if abs(y - self._header_y()) <= self._hit_margin:
            self._dragging_header = True
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            return
        if abs(y - self._footer_y()) <= self._hit_margin:
            self._dragging_footer = True
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        y = event.position().toPoint().y()
        pix = self.pixmap()
        if not pix:
            return super().mouseMoveEvent(event)
        min_gap = 0.05

        if self._dragging_header:
            max_r = max(0.0, 1.0 - self.footer_ratio - min_gap)
            self.header_ratio = max(0.0, min(max_r, self._ratio_from_widget_y(y)))
            self.update()
            return
        if self._dragging_footer:
            max_r = max(0.0, 1.0 - self.header_ratio - min_gap)
            self.footer_ratio = max(0.0, min(max_r, 1.0 - self._ratio_from_widget_y(y)))
            self.update()
            return

        # 커서 변경
        if abs(y - self._header_y()) <= self._hit_margin or abs(y - self._footer_y()) <= self._hit_margin:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging_header or self._dragging_footer:
            self._dragging_header = False
            self._dragging_footer = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            # 부모 뷰어에 변경 알림
            viewer = self.parent()
            while viewer and not isinstance(viewer, HFViewer):
                viewer = viewer.parent()
            if viewer:
                viewer.on_exclusion_changed(self.header_ratio, self.footer_ratio)
            return
        super().mouseReleaseEvent(event)

    # --- 페인트: 제외 영역 오버레이 ---
    def clear_selection(self):
        """Clear selection state - placeholder for compatibility"""
        pass

    def paintEvent(self, event):
        super().paintEvent(event)
        pix = self.pixmap()
        if not pix:
            return
        image_rect = self._image_rect()
        w, h = image_rect.width(), image_rect.height()
        hy = self._header_y()
        fy = self._footer_y()
        painter = QPainter(self)
        # 반투명 어두운 영역
        painter.fillRect(QRect(image_rect.x(), image_rect.y(), w, max(0, hy - image_rect.y())), QColor(0, 0, 0, 90))
        painter.fillRect(QRect(image_rect.x(), fy, w, max(0, image_rect.bottom() + 1 - fy)), QColor(0, 0, 0, 90))
        # 주황색 점선 경계
        pen = QPen(QColor(255, 140, 0), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        if hy > image_rect.y():
            painter.drawLine(image_rect.x(), hy, image_rect.x() + w, hy)
        if fy < image_rect.y() + h:
            painter.drawLine(image_rect.x(), fy, image_rect.x() + w, fy)
        painter.end()


# ──────────────────────────────────────────────────────────
# HFViewer : Header/Footer 제외 기능이 있는 PDF 뷰어
#   - 기존 PDFViewer의 구조를 그대로 따름
#   - 차이: SelectableLabel 대신 HeaderFooterLabel 사용
#   - 텍스트 추출: 전체 페이지, Header/Footer 영역 제외
# ──────────────────────────────────────────────────────────
class HFViewer(QScrollArea):
    DEFAULT_EXCLUSION_RATIO = 0.05

    def __init__(self, parent=None):
        super().__init__(parent)
        self.comparison_options = ComparisonOptions()
        self.setObjectName('pdfViewerArea')
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setAcceptDrops(True)

        self.scale = 1.5
        self.header_ratio = self.DEFAULT_EXCLUSION_RATIO
        self.footer_ratio = self.DEFAULT_EXCLUSION_RATIO
        self.pdf_doc = None
        self.page_labels = []
        self.page_base_pixmaps = []
        self.char_data = []        # 추출된 정규화 문자 데이터
        self.raw_text = ''
        self.word_highlights = {}
        self.last_compared_area = {}
        self.parent_tool = None

        # 툴바
        self.toolbar = QFrame()
        self.toolbar.setObjectName('pdfToolbar')
        self.toolbar.setFixedHeight(40)
        tb = QHBoxLayout(self.toolbar)
        tb.setContentsMargins(8, 4, 8, 4)
        tb.setSpacing(0)

        self.zoom_in_btn = QPushButton('🔍+')
        self.zoom_in_btn.setObjectName('toolbarBtn')
        self.zoom_in_btn.setFixedSize(36, 32)
        self.zoom_in_btn.setStyleSheet('font-size: 13px; padding: 0px; margin: 0px;')
        self.zoom_in_btn.setToolTip('확대')
        self.zoom_in_btn.clicked.connect(self.zoom_in)

        self.zoom_out_btn = QPushButton('🔍-')
        self.zoom_out_btn.setObjectName('toolbarBtn')
        self.zoom_out_btn.setFixedSize(36, 32)
        self.zoom_out_btn.setStyleSheet('font-size: 13px; padding: 0px; margin: 0px;')
        self.zoom_out_btn.setToolTip('축소')
        self.zoom_out_btn.clicked.connect(self.zoom_out)

        self.fit_width_btn = QPushButton('↔')
        self.fit_width_btn.setObjectName('toolbarBtn')
        self.fit_width_btn.setFixedSize(36, 32)
        self.fit_width_btn.setStyleSheet('font-size: 14px; padding: 0px; margin: 0px;')
        self.fit_width_btn.setToolTip('너비에 맞춤')
        self.fit_width_btn.clicked.connect(self.fit_to_width)

        self.fit_page_btn = QPushButton('📄')
        self.fit_page_btn.setObjectName('toolbarBtn')
        self.fit_page_btn.setFixedSize(36, 32)
        self.fit_page_btn.setStyleSheet('font-size: 14px; padding: 0px; margin: 0px;')
        self.fit_page_btn.setToolTip('페이지에 맞춤')
        self.fit_page_btn.clicked.connect(self.fit_to_page)

        self.zoom_label = QLineEdit(f'{int(self.scale * 100)}%')
        self.zoom_label.setObjectName('pageSpin')
        self.zoom_label.setFixedSize(64, 30)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setStyleSheet('font-size: 12px;')
        self.zoom_label.setToolTip('배율을 입력하세요. 예: 150')
        self.zoom_label.editingFinished.connect(self._apply_zoom_input)
        
        # Page navigation
        self.page_nav_label = QLabel('페이지')
        self.page_nav_label.setObjectName('toolbarLabel')
        self.page_nav_label.setFixedWidth(36)
        
        self.page_spin = QLineEdit()
        self.page_spin.setObjectName('pageSpin')
        self.page_spin.setFixedSize(50, 30)
        self.page_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_spin.setStyleSheet('font-size: 12px;')
        self.page_spin.setPlaceholderText('1')
        self.page_spin.returnPressed.connect(self._on_page_return_pressed)
        
        self.page_total_label = QLabel('/ 0')
        self.page_total_label.setObjectName('toolbarLabel')
        self.page_total_label.setFixedWidth(50)
        
        self.go_page_btn = QPushButton('→')
        self.go_page_btn.setObjectName('toolbarBtn')
        self.go_page_btn.setFixedSize(32, 30)
        self.go_page_btn.setStyleSheet('font-size: 14px; padding: 0px; margin: 0px;')
        self.go_page_btn.setToolTip('해당 페이지로 이동')
        self.go_page_btn.clicked.connect(self._on_goto_page)

        # Initialize search helper
        self.search_helper = PDFSearchHelper(self)
        
        # Add zoom controls first
        tb.addWidget(self.zoom_in_btn)
        tb.addWidget(self.zoom_out_btn)
        tb.addWidget(self.fit_width_btn)
        tb.addWidget(self.fit_page_btn)
        tb.addWidget(self.zoom_label)
        tb.addSpacing(16)
        
        # Page navigation controls
        tb.addWidget(self.page_nav_label)
        tb.addWidget(self.page_spin)
        tb.addWidget(self.page_total_label)
        tb.addWidget(self.go_page_btn)
        tb.addSpacing(16)
        
        # Setup search UI using helper
        search_input, find_prev_btn, find_next_btn, search_count_label = self.search_helper.setup_search_ui(tb)
        
        # Store references for compatibility
        self.search_input = search_input
        self.find_prev_btn = find_prev_btn
        self.find_next_btn = find_next_btn
        
        # Set Korean UI text
        self.search_helper.set_placeholder_text('검색어 입력')
        self.search_helper.set_button_text('이전', '이후')
        
        tb.addStretch()

        # 스크롤 영역
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(20, 20, 20, 20)
        self.vbox.setSpacing(20)
        self.vbox.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setWidget(self.container)

        self.drop_label = QLabel('📄 PDF 파일을 여기에 드래그 앤 드랍하세요\n또는 아래 버튼을 클릭하여 파일을 선택하세요')
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_label.setStyleSheet(
            'QLabel { color: #FFFFFF; font-size: 14px; font-weight: 500; padding: 40px 30px; '
            'border: 2px dashed #8E8E93; border-radius: 12px; background: rgba(120, 120, 128, 0.3); }'
        )
        self.vbox.addWidget(self.drop_label)

        self.open_pdf_btn = QPushButton('📁 PDF 파일 선택')
        self.open_pdf_btn.setObjectName('pdfOpenButton')
        self.open_pdf_btn.setFixedHeight(48)
        self.open_pdf_btn.setMinimumWidth(180)
        self.open_pdf_btn.setStyleSheet(
            'QPushButton { font-size: 14px; font-weight: 600; padding: 10px 20px; }'
        )
        self.open_pdf_btn.clicked.connect(self.open_pdf_via_dialog)
        self.vbox.addWidget(self.open_pdf_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll_page_changed)

    def _on_scroll_page_changed(self):
        if not self.page_labels:
            return
        scroll_y = self.verticalScrollBar().value()
        viewport_h = self.viewport().height()
        mid_y = scroll_y + viewport_h / 2
        page_top = self.vbox.contentsMargins().top()
        for i, lbl in enumerate(self.page_labels):
            lbl_h = lbl.height()
            lbl_mid = page_top + lbl_h / 2
            if mid_y < lbl_mid + lbl_h / 2:
                self.page_spin.setText(str(i + 1))
                break
            page_top += lbl_h + self.vbox.spacing()

    def set_parent_tool(self, tool):
        self.parent_tool = tool
        self.comparison_options = tool.comparison_settings.options

    # Search methods delegated to helper
    def on_search_text_changed(self, text):
        self.search_helper.on_search_text_changed(text)

    def search_in_pdf(self, text):
        self.search_helper.search_in_pdf(text)

    def highlight_search_results(self):
        self.search_helper.highlight_search_results()

    def clear_search_highlights(self):
        self.search_helper.clear_search_highlights()

    def find_next(self):
        self.search_helper.find_next()

    def find_previous(self):
        self.search_helper.find_previous()

    def go_to_search_result(self, index):
        self.search_helper.go_to_search_result(index)

    def highlight_current_result(self, page_num, rect):
        self.search_helper.highlight_current_result(page_num, rect)

    def remove_current_highlight(self):
        self.search_helper.remove_current_highlight()

    # PDF loading methods로드 ───
    def load_pdf(self, path):
        try:
            self.header_ratio = self.DEFAULT_EXCLUSION_RATIO
            self.footer_ratio = self.DEFAULT_EXCLUSION_RATIO
            self.pdf_doc = pymupdf.open(path)
            self.reload_pages()
            return True
        except Exception:
            return False

    def update_loaded_pdf_label(self, pdf_path):
        if not self.parent_tool:
            return
        if self == self.parent_tool.viewer1:
            self.parent_tool.lbl_name1.setText(f"<b style='color:{COLOR_HEADER_ACCENT}; font-size:15px; font-weight:600;'>[PDF 1] 📄 {os.path.basename(pdf_path)}</b>")
        elif self == self.parent_tool.viewer2:
            self.parent_tool.lbl_name2.setText(f"<b style='color:{COLOR_HEADER_ACCENT}; font-size:15px; font-weight:600;'>[PDF 2] 📄 {os.path.basename(pdf_path)}</b>")

    def open_pdf_via_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'PDF 파일 선택', '', 'PDF Files (*.pdf)')
        if not file_path:
            return
        self.clear_all_data()
        if self.load_pdf(file_path):
            self.update_loaded_pdf_label(file_path)
        else:
            QMessageBox.warning(self, '오류', 'PDF 파일을 불러오지 못했습니다.')

    # ─── 드래그 앤 드롭 ───
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and url.toLocalFile().lower().endswith('.pdf'):
                    event.acceptProposedAction()
                    # Highlight drop zone
                    if hasattr(self, 'drop_label') and self.drop_label.isVisible():
                        self.drop_label.setStyleSheet(
                            'QLabel { color: #FFFFFF; font-size: 14px; font-weight: 600; padding: 40px 30px; '
                            'border: 2px dashed #A44735; border-radius: 12px; background: rgba(164, 71, 53, 0.32); }'
                        )
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        super().dragLeaveEvent(event)
        # Reset drop zone styling
        if hasattr(self, 'drop_label') and self.drop_label.isVisible():
            self.drop_label.setStyleSheet(
                'QLabel { color: #FFFFFF; font-size: 14px; font-weight: 500; padding: 40px 30px; '
                'border: 2px dashed #8E8E93; border-radius: 12px; background: rgba(120, 120, 128, 0.3); }'
            )

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and url.toLocalFile().lower().endswith('.pdf'):
                    pdf_path = url.toLocalFile()
                    self.clear_all_data()
                    if self.load_pdf(pdf_path) and self.parent_tool:
                        if self == self.parent_tool.viewer1:
                            self.parent_tool.lbl_name1.setText(
                                f"<b style='color:{COLOR_HEADER_ACCENT}; font-size:15px; font-weight:600;'>[PDF 1] 📄 {os.path.basename(pdf_path)}</b>")
                        elif self == self.parent_tool.viewer2:
                            self.parent_tool.lbl_name2.setText(
                                f"<b style='color:{COLOR_HEADER_ACCENT}; font-size:15px; font-weight:600;'>[PDF 2] 📄 {os.path.basename(pdf_path)}</b>")
                    event.acceptProposedAction()
                    return
        event.ignore()

    # ─── 페이지 렌더링 ───
    def reload_pages(self):
        if not self.pdf_doc:
            return
        # 기존 비율 보존
        if self.page_labels:
            self.header_ratio = self.page_labels[0].header_ratio
            self.footer_ratio = self.page_labels[0].footer_ratio
        if hasattr(self, 'drop_label'):
            self.drop_label.hide()
        if hasattr(self, 'open_pdf_btn'):
            self.open_pdf_btn.hide()
        # Hide instruction labels when PDF is loaded
        if self.parent_tool:
            if self == self.parent_tool.viewer1:
                if hasattr(self.parent_tool, 'hf_instruction_label1'):
                    self.parent_tool.hf_instruction_label1.hide()
            elif self == self.parent_tool.viewer2:
                if hasattr(self.parent_tool, 'hf_instruction_label2'):
                    self.parent_tool.hf_instruction_label2.hide()
        for lbl in self.page_labels:
            lbl.setParent(None)
        self.page_labels.clear()
        self.page_base_pixmaps.clear()
        total_pages = len(self.pdf_doc)
        self.page_total_label.setText(f'/ {total_pages}')
        for i in range(total_pages):
            page = self.pdf_doc.load_page(i)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(self.scale, self.scale))
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            base_pixmap = QPixmap.fromImage(img.copy())
            lbl = HeaderFooterLabel(self.container)
            lbl.page_num = i
            lbl.header_ratio = self.header_ratio
            lbl.footer_ratio = self.footer_ratio
            lbl.setPixmap(base_pixmap.copy())
            self.vbox.addWidget(lbl)
            self.page_labels.append(lbl)
            self.page_base_pixmaps.append(base_pixmap)
        self.refresh_highlights()
        # Header/Footer가 모두 보이도록 스크롤 위치 조정 (완전히 레이아웃된 후)
        QTimer.singleShot(100, self._ensure_header_footer_visible)

    def _ensure_header_footer_visible(self):
        """첫 페이지의 Header와 Footer 조절 영역이 모두 보이도록 스크롤"""
        if not self.page_labels:
            return
        
        # 레이아웃 강제 업데이트
        self.container.adjustSize()
        QApplication.processEvents()
        
        first_label = self.page_labels[0]
        page_height = first_label.height()
        
        # 페이지 높이가 유효하지 않으면 다시 시도
        if page_height == 0:
            QTimer.singleShot(100, self._ensure_header_footer_visible)
            return
        
        # 상단에서 약간 아래로 스크롤 (Header 조절 영역과 본문 일부가 보이도록)
        # Footer 조절 영역도 보이려면 viewport가 충분히 커야 함
        scroll_to = int(page_height * 0.05)  # 상단에서 5% 지점
        self.verticalScrollBar().setValue(scroll_to)

    # ─── Header/Footer 변경 콜백 ───
    def on_exclusion_changed(self, header_ratio, footer_ratio):
        """Header/Footer 변경 - 각 뷰어 독립적으로 조절"""
        self.header_ratio = header_ratio
        self.footer_ratio = footer_ratio
        for lbl in self.page_labels:
            lbl.header_ratio = header_ratio
            lbl.footer_ratio = footer_ratio
            lbl.update()
        # 동기화 제거: 각 뷰어는 독립적으로 조절

    # ─── 하이라이트 ───
    def refresh_highlights(self):
        for i, lbl in enumerate(self.page_labels):
            if i >= len(self.page_base_pixmaps):
                continue
            img = self.page_base_pixmaps[i].toImage().copy()
            painter = QPainter(img)
            if i in self.last_compared_area:
                for bbox in self.last_compared_area[i]:
                    rect = QRect(int(bbox[0] * self.scale), int(bbox[1] * self.scale),
                                 int((bbox[2] - bbox[0]) * self.scale), int((bbox[3] - bbox[1]) * self.scale))
                    painter.fillRect(rect, COLOR_AREA)
            if i in self.word_highlights:
                for bbox, color in self.word_highlights[i]:
                    rect = QRect(int(bbox[0] * self.scale), int(bbox[1] * self.scale),
                                 int((bbox[2] - bbox[0]) * self.scale), int((bbox[3] - bbox[1]) * self.scale))
                    painter.fillRect(rect, color)
            # Use search helper for search highlights
            self.search_helper.render_search_highlights(painter, i, self.scale)
            painter.end()
            lbl.setPixmap(QPixmap.fromImage(img))

    # ─── 텍스트 추출 (기존 extract_and_process_text 와 동일한 로직) ───
    def extract_body_text(self):
        """모든 페이지에서 Header/Footer를 제외한 본문 텍스트를 추출"""
        self.char_data = []
        self.raw_text = ''
        if not self.pdf_doc:
            return
        all_raw_chars = []
        for page_num in range(len(self.pdf_doc)):
            page = self.pdf_doc.load_page(page_num)
            page_h = page.rect.height
            h1 = page_h * self.header_ratio        # 상단 제외 경계
            h2 = page_h * (1.0 - self.footer_ratio)  # 하단 제외 경계
            raw_dict = page.get_text('rawdict')
            # Header/Footer 영역 제외
            all_raw_chars.extend(collect_raw_chars(raw_dict, page_num, excluded_bounds=(h1, h2)))

        # Y좌표 기준 라인 그룹핑 (기존 로직 동일)
        # 정규화 + word_id 부여 (기존 로직 동일)
        self.char_data, self.raw_text = normalize_raw_chars(
            all_raw_chars, page_aware=True, options=self.comparison_options)

    def _on_page_return_pressed(self):
        self._on_goto_page()
    
    def _on_goto_page(self):
        if not self.pdf_doc:
            return
        text = self.page_spin.text().strip()
        if not text:
            return
        try:
            page_num = int(text)
        except ValueError:
            return
        self.goto_page(page_num)
    
    def goto_page(self, page_num):
        if not self.pdf_doc or not self.page_labels:
            return
        total = len(self.page_labels)
        if page_num < 1:
            page_num = 1
        if page_num > total:
            page_num = total
        idx = page_num - 1
        lbl = self.page_labels[idx]
        y = lbl.y()
        self.verticalScrollBar().setValue(y)
        self.page_spin.setText(str(page_num))
    
    # ─── 줌 ───
    def zoom_in(self):
        self.scale *= 1.2
        self.update_zoom_label()
        self.reload_pages()

    def zoom_out(self):
        self.scale /= 1.2
        self.update_zoom_label()
        self.reload_pages()

    def fit_to_width(self):
        if not self.pdf_doc or len(self.pdf_doc) == 0:
            return
        pw = self.pdf_doc.load_page(0).rect.width
        self.scale = max(100, self.viewport().width() - 40) / pw
        self.update_zoom_label()
        self.reload_pages()

    def fit_to_page(self):
        if not self.pdf_doc or len(self.pdf_doc) == 0:
            return
        r = self.pdf_doc.load_page(0).rect
        sw = max(100, self.viewport().width() - 40) / r.width
        sh = max(100, self.viewport().height() - 40) / r.height
        self.scale = min(sw, sh)
        self.update_zoom_label()
        self.reload_pages()

    def update_zoom_label(self):
        self.zoom_label.blockSignals(True)
        self.zoom_label.setText(f'{int(round(self.scale * 100))}%')
        self.zoom_label.blockSignals(False)

    def _apply_zoom_input(self):
        text = self.zoom_label.text().strip().replace('%', '').replace('％', '')
        if not text:
            self.update_zoom_label()
            return
        try:
            percent = float(text)
        except ValueError:
            self.update_zoom_label()
            return
        percent = min(800.0, max(10.0, percent))
        new_scale = percent / 100.0
        if abs(new_scale - self.scale) < 0.001:
            self.update_zoom_label()
            return
        self.scale = new_scale
        self.update_zoom_label()
        self.reload_pages()

    # ─── 초기화 ───
    def clear_all_data(self):
        self.word_highlights.clear()
        self.last_compared_area.clear()
        self.char_data.clear()
        self.raw_text = ''
        self.search_helper.clear_all_search_data()
        # Clear page labels
        for lbl in self.page_labels:
            lbl.setParent(None)
        self.page_labels.clear()
        self.page_base_pixmaps.clear()
        self.pdf_doc = None
        if hasattr(self, 'drop_label'):
            self.drop_label.show()
        if hasattr(self, 'open_pdf_btn'):
            self.open_pdf_btn.show()
        # Show instruction labels when PDF is cleared
        if self.parent_tool:
            if self == self.parent_tool.viewer1:
                if hasattr(self.parent_tool, 'hf_instruction_label1'):
                    self.parent_tool.hf_instruction_label1.show()
            elif self == self.parent_tool.viewer2:
                if hasattr(self.parent_tool, 'hf_instruction_label2'):
                    self.parent_tool.hf_instruction_label2.show()
        self.refresh_highlights()

    def get_scroll_anchor(self):
        """Convert current scroll position to (page, y) anchor"""
        center = self.verticalScrollBar().value() + self.viewport().height() / 2
        return self.anchor_from_content_y(center)

    def anchor_from_content_y(self, position):
        for page_num, label in enumerate(self.page_labels):
            if position < label.y() + label.height() + self.vbox.spacing() / 2 or page_num == len(self.page_labels) - 1:
                y = max(0.0, min((position - label.y()) / max(self.scale, 0.0001),
                                 label.height() / max(self.scale, 0.0001)))
                return page_num, y
        return None

    def anchor_to_content_y(self, anchor):
        if not anchor or not 0 <= anchor[0] < len(self.page_labels):
            return None
        label = self.page_labels[anchor[0]]
        return label.y() + max(0.0, min(anchor[1] * self.scale, label.height()))

    def scroll_to_anchor(self, anchor):
        """Immediately scroll to (page, y) anchor position"""
        position = self.anchor_to_content_y(anchor)
        if position is not None:
            self.verticalScrollBar().setValue(round(position - self.viewport().height() / 2))


# ──────────────────────────────────────────────────────────
# HFCompareWidget : 메인 비교 위젯 (MDI에 등록)
# ──────────────────────────────────────────────────────────
class HFCompareWidget(ComparisonSettingsMixin, QWidget):
    tool_key = 'pdf_hf_compare'
    tool_name = '📄 Header/Footer 제외 비교'
    window_title = 'PDF 출력물 비교'
    singleton = True
    enabled = True

    def __init__(self, parent=None, comparison_settings=None):
        super().__init__(parent)
        self.setup_comparison_settings(comparison_settings)
        self._syncing = False
        self.last_s1_norm = ''
        self.last_s2_norm = ''
        self.last_s1_raw = ''
        self.last_s2_raw = ''
        self.sync_anchor_pairs = []
        
        # Thread manager for async comparison
        self.compare_manager = None
        self.diff_list = []  # 비교 결과 목록 저장
        
        self._build_ui()

    # ─── UI 구성 ───
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(5)
        root.setContentsMargins(10, 0, 10, 10)

        self.workspace = QFrame()
        self.workspace.setObjectName('workspace')
        ws = QHBoxLayout(self.workspace)
        ws.setContentsMargins(0, 0, 0, 0)
        ws.setSpacing(16)

        # PDF 1
        p1 = QFrame(); p1.setObjectName('pdfPanel')
        l1 = QVBoxLayout(p1); l1.setContentsMargins(0, 0, 0, 0); l1.setSpacing(0)
        self.viewer1 = HFViewer()
        self.viewer1.set_parent_tool(self)
        self.lbl_name1 = QLabel(f"<b style='color:{COLOR_HEADER_ACCENT}; font-size:15px; font-weight:600;'>[PDF 1]</b>")
        self.lbl_name1.setContentsMargins(10, 6, 10, 4)
        l1.addWidget(self.lbl_name1)
        l1.addWidget(self.viewer1.toolbar)
        
        # Header/Footer instruction message for PDF1
        self.hf_instruction_label1 = QLabel(HEADER_FOOTER_INSTRUCTION_HTML)
        self.hf_instruction_label1.setObjectName('hfInstruction')
        self.hf_instruction_label1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hf_instruction_label1.setContentsMargins(10, 5, 10, 5)
        l1.addWidget(self.hf_instruction_label1)
        
        l1.addWidget(self.viewer1, 1)
        ws.addWidget(p1)

        # PDF 2
        p2 = QFrame(); p2.setObjectName('pdfPanel')
        l2 = QVBoxLayout(p2); l2.setContentsMargins(0, 0, 0, 0); l2.setSpacing(0)
        self.viewer2 = HFViewer()
        self.viewer2.set_parent_tool(self)
        self.lbl_name2 = QLabel(f"<b style='color:{COLOR_HEADER_ACCENT}; font-size:15px; font-weight:600;'>[PDF 2]</b>")
        self.lbl_name2.setContentsMargins(10, 6, 10, 4)
        l2.addWidget(self.lbl_name2)
        l2.addWidget(self.viewer2.toolbar)
        
        # Header/Footer instruction message for PDF2
        self.hf_instruction_label2 = QLabel(HEADER_FOOTER_INSTRUCTION_HTML)
        self.hf_instruction_label2.setObjectName('hfInstruction')
        self.hf_instruction_label2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hf_instruction_label2.setContentsMargins(10, 5, 10, 5)
        l2.addWidget(self.hf_instruction_label2)
        
        l2.addWidget(self.viewer2, 1)
        ws.addWidget(p2)

        root.addWidget(self.workspace, 1)
        
        # Loading Overlay (Image-based, centered)
        self.loading_overlay = QLabel(self)
        self.loading_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_overlay.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 255, 255, 0.85);
                border-radius: 12px;
            }
        """)
        self.loading_overlay.setFixedSize(400, 300)
        self.loading_overlay.hide()
        
        # Loading message label
        self.loading_message = QLabel("비교중", self.loading_overlay)
        self.loading_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_message.setStyleSheet("""
            QLabel {
                background: transparent;
                border: none;
                font-size: 16px;
                color: #333333;
                font-weight: 500;
            }
        """)
        self.loading_message.setGeometry(0, 210, 400, 30)
        
        # Loading GIF (nuni_icon_orange_spin.gif)
        self.loading_gif = QLabel(self.loading_overlay)
        self.loading_gif.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_gif.setFixedSize(160, 160)
        self.loading_gif.setGeometry(120, 30, 160, 160)
        
        gif_path = get_timer_gif_path()
        if gif_path and os.path.exists(gif_path):
            self.movie = QMovie(gif_path)
            self.movie.setScaledSize(self.loading_gif.size())
            self.loading_gif.setMovie(self.movie)
        else:
            self.loading_gif.setText("⏳")
            self.loading_gif.setStyleSheet("font-size: 48px; background: transparent; border: none;")

        self.loading_progress = make_overlay_progress(self.loading_overlay)

        # 하단 액션 바
        bar = QFrame()
        bar.setObjectName('actionBar')
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(10)

        # 동시 스크롤 체크박스
        self.sync_scroll_cb = SyncScrollToggle('동시 스크롤')
        self.sync_scroll_cb.setObjectName('actionCheckBox')
        self.sync_scroll_cb.setChecked(False)
        self.sync_scroll_cb.toggled.connect(self.toggle_sync_scroll)
        self.sync_scroll_enabled = False
        bl.addWidget(self.sync_scroll_cb)

        # 결과 목록 버튼 - 동시 스크롤 오른쪽
        self.btn_diff_list = QPushButton('📋 비교결과')
        self.btn_diff_list.setObjectName('compareUtilityBtn')
        self.btn_diff_list.setFixedHeight(40)
        self.btn_diff_list.setMinimumWidth(100)
        self.btn_diff_list.clicked.connect(self.show_diff_list_dialog)
        bl.addWidget(self.btn_diff_list)
        self.add_comparison_options_button(bl)

        bl.addStretch()

        self.btn_compare = QPushButton('▶️  비교 실행')
        self.btn_compare.setObjectName('compareActionBtn')
        self.btn_compare.setFixedHeight(42)
        self.btn_compare.setMinimumWidth(150)
        self.btn_compare.clicked.connect(self.request_comparison)
        bl.addWidget(self.btn_compare)

        bl.addStretch()

        self.btn_reset_page = QPushButton('↩  페이지 초기화')
        self.btn_reset_page.setObjectName('compareUtilityBtn')
        self.btn_reset_page.setFixedHeight(40)
        self.btn_reset_page.setMinimumWidth(130)
        self.btn_reset_page.clicked.connect(self.request_reset_page)
        bl.addWidget(self.btn_reset_page)

        self.btn_reset = QPushButton('🗑  초기화')
        self.btn_reset.setObjectName('resetBtn')
        self.btn_reset.setFixedHeight(40)
        self.btn_reset.setMinimumWidth(120)
        self.btn_reset.clicked.connect(self.request_reset)
        bl.addWidget(self.btn_reset)

        self.btn_focus_mode = QPushButton()
        self.btn_focus_mode.setObjectName('secondaryBtn')
        self.btn_focus_mode.setFixedSize(40, 40)
        self.btn_focus_mode.setCheckable(True)
        bl.addWidget(self.btn_focus_mode)

        self.switch_toggle = ToolSwitchToggle(('영역지정비교', '전체비교'))
        bl.addWidget(self.switch_toggle)

        root.addWidget(bar)
        self.bottom_action_bar = bar

        # 스크롤 동기화
        self.viewer1.verticalScrollBar().valueChanged.connect(self._sync1)
        self.viewer2.verticalScrollBar().valueChanged.connect(self._sync2)

    def _sync1(self, v):
        """viewer1 스크롤 시 viewer2 동기화"""
        if not self._syncing and self.sync_scroll_enabled:
            self._syncing = True
            try:
                source_anchor = self.viewer1.get_scroll_anchor()
                target_anchor = self._find_partner_anchor(source_anchor, source_index=0)
                if target_anchor:
                    self.viewer2.scroll_to_anchor(target_anchor)
                elif source_anchor:
                    # 페이지 수준 폴백: 같은 페이지로 이동
                    src_page = source_anchor[0]
                    if self.viewer2.page_labels and 0 <= src_page < len(self.viewer2.page_labels):
                        self.viewer2.page_spin.setText(str(src_page + 1))
                        self.viewer2._on_page_return_pressed()
            finally:
                self._syncing = False

    def _sync2(self, v):
        """viewer2 스크롤 시 viewer1 동기화"""
        if not self._syncing and self.sync_scroll_enabled:
            self._syncing = True
            try:
                source_anchor = self.viewer2.get_scroll_anchor()
                target_anchor = self._find_partner_anchor(source_anchor, source_index=1)
                if target_anchor:
                    self.viewer1.scroll_to_anchor(target_anchor)
                elif source_anchor:
                    # 페이지 수준 폴백: 같은 페이지로 이동
                    src_page = source_anchor[0]
                    if self.viewer1.page_labels and 0 <= src_page < len(self.viewer1.page_labels):
                        self.viewer1.page_spin.setText(str(src_page + 1))
                        self.viewer1._on_page_return_pressed()
            finally:
                self._syncing = False

    def toggle_sync_scroll(self, checked):
        """동시 스크롤 토글"""
        self.sync_scroll_enabled = checked
        if checked and self.viewer1.page_labels and self.viewer2.page_labels:
            self._sync1(self.viewer1.verticalScrollBar().value())

    def _find_partner_anchor(self, source_anchor, source_index):
        """일치 구간의 위치를 보간하여 반대편 뷰어의 앵커 반환"""
        source, target = ((self.viewer1, self.viewer2) if source_index == 0
                          else (self.viewer2, self.viewer1))
        source_y = source.anchor_to_content_y(source_anchor)
        if source_y is None or not target.page_labels:
            return None
        positions = {}
        for left_anchor, right_anchor in self.sync_anchor_pairs:
            candidate, partner = ((left_anchor, right_anchor) if source_index == 0
                                  else (right_anchor, left_anchor))
            x = source.anchor_to_content_y(candidate)
            y = target.anchor_to_content_y(partner)
            if x is not None and y is not None:
                positions.setdefault(x, []).append(y)
        if not positions:
            progress = source.verticalScrollBar().value() / max(1, source.verticalScrollBar().maximum())
            target_y = progress * target.verticalScrollBar().maximum() + target.viewport().height() / 2
            return target.anchor_from_content_y(target_y)
        points = []
        for x, values in sorted(positions.items()):
            points.append((x, max(points[-1][1] if points else 0, sum(values) / len(values))))
        if len(points) == 1:
            ratio = target.scale / max(source.scale, 0.0001)
            target_y = points[0][1] + (source_y - points[0][0]) * ratio
        else:
            right = next((i for i in range(1, len(points)) if points[i][0] >= source_y), len(points) - 1)
            left = right - 1
            x0, y0 = points[left]
            x1, y1 = points[right]
            target_y = y0 + (source_y - x0) * (y1 - y0) / (x1 - x0)
        return target.anchor_from_content_y(target_y)

    def _build_sync_anchor_pairs(self, opcodes):
        pairs = []
        for tag, i1, i2, j1, j2 in opcodes:
            if tag != 'equal' or i1 == i2:
                continue
            length = i2 - i1
            indices = {0, length - 1, *range(0, length, max(1, length // 200))}
            for offset in range(1, length):
                previous_left = self.viewer1.char_data[i1 + offset - 1]['page']
                previous_right = self.viewer2.char_data[j1 + offset - 1]['page']
                if (self.viewer1.char_data[i1 + offset]['page'] != previous_left
                        or self.viewer2.char_data[j1 + offset]['page'] != previous_right):
                    indices.add(offset)
            for offset in sorted(indices):
                left = self.viewer1.char_data[i1 + offset]
                right = self.viewer2.char_data[j1 + offset]
                pairs.append(((left['page'], (left['bbox'][1] + left['bbox'][3]) / 2),
                              (right['page'], (right['bbox'][1] + right['bbox'][3]) / 2)))
        return pairs

    def _build_anchor_from_range(self, viewer, start_idx, end_idx):
        """char_data 범위로부터 (page, y) 앵커 생성"""
        if start_idx >= end_idx or start_idx < 0 or end_idx > len(viewer.char_data):
            return None
        chars = viewer.char_data[start_idx:end_idx]
        if not chars:
            return None
        page_num = chars[0]['page']
        same_page_chars = [ch for ch in chars if ch['page'] == page_num]
        if not same_page_chars:
            same_page_chars = chars
        y_values = [((ch['bbox'][1] + ch['bbox'][3]) / 2) for ch in same_page_chars]
        if not y_values:
            return None
        return (page_num, sum(y_values) / len(y_values))

    def _build_page_bboxes_from_range(self, viewer, start_idx, end_idx):
        """char_data 범위를 페이지별 union bbox로 변환"""
        if start_idx >= end_idx or start_idx < 0 or end_idx > len(viewer.char_data):
            return {}
        page_boxes = {}
        for ch in viewer.char_data[start_idx:end_idx]:
            page_num = ch['page']
            x0, y0, x1, y1 = ch['bbox']
            if page_num not in page_boxes:
                page_boxes[page_num] = [x0, y0, x1, y1]
            else:
                page_boxes[page_num][0] = min(page_boxes[page_num][0], x0)
                page_boxes[page_num][1] = min(page_boxes[page_num][1], y0)
                page_boxes[page_num][2] = max(page_boxes[page_num][2], x1)
                page_boxes[page_num][3] = max(page_boxes[page_num][3], y1)
        return {page: tuple(bbox) for page, bbox in page_boxes.items()}

    def _append_compared_area(self, viewer, start_idx, end_idx):
        """비교된 실제 문자 영역을 last_compared_area에 누적"""
        page_boxes = self._build_page_bboxes_from_range(viewer, start_idx, end_idx)
        for page_num, bbox in page_boxes.items():
            if page_num not in viewer.last_compared_area:
                viewer.last_compared_area[page_num] = []
            viewer.last_compared_area[page_num].append(bbox)

    # ─── 비교 요청 ───
    def request_comparison(self):
        if not self.viewer1.pdf_doc or not self.viewer2.pdf_doc:
            QMessageBox.warning(self, '경고', '양쪽 PDF를 먼저 로드해주세요.')
            return
        self.start_async_comparison()

    # ─── 비교 실행 (비동기 QThread 방식) ───
    def start_async_comparison(self):
        """비동기 PDF 비교 시작 (QThread 사용)"""
        self._active_comparison_revision = self.comparison_settings.revision
        # 1) 텍스트 추출 (메인 스레드에서 먼저 수행 - char_data 준비)
        self.viewer1.extract_body_text()
        self.viewer2.extract_body_text()
        
        if not self.viewer1.char_data and not self.viewer2.char_data:
            message = ('추출된 텍스트가 없습니다. Header/Footer 제외 범위를 확인해주세요.'
                       if self.comparison_settings.options.mode == 'body'
                       else '현재 비교 조건과 제외 영역에서 비교할 텍스트가 없습니다.')
            QMessageBox.information(self, '안내', message)
            return
        
        # 2) 하이라이트 초기화
        self.viewer1.word_highlights.clear()
        self.viewer2.word_highlights.clear()
        self.viewer1.last_compared_area.clear()
        self.viewer2.last_compared_area.clear()
        self.sync_anchor_pairs = []
        
        # 이전 manager 정리
        if self.compare_manager:
            self.compare_manager.cleanup()
        
        # 3) 로딩 오버레이 표시
        self.show_loading(True, "비교중")
        
        # 4) Thread Manager 생성 및 설정
        self.compare_manager = CompareThreadManager(self)
        self.compare_manager.setup_worker(
            char_data1=self.viewer1.char_data,  # 참조만 전달 (복사는 run()에서)
            char_data2=self.viewer2.char_data,
            raw_text1=self.viewer1.raw_text,
            raw_text2=self.viewer2.raw_text
        )
        
        # 5) Signal 연결
        self.compare_manager.started.connect(self._on_compare_started)
        self.compare_manager.progress.connect(self._on_compare_progress)
        self.compare_manager.result_ready.connect(self._on_compare_result_ready)
        self.compare_manager.finished.connect(self._on_compare_finished)
        self.compare_manager.error.connect(self._on_compare_error)
        
        # 6) GIF 첫 프레임 렌더링 시간 확보 후 스레드 시작
        QTimer.singleShot(50, self.compare_manager.start_comparison)
    
    def _on_compare_started(self):
        """비교 시작 시 (스레드가 실제로 시작된 시점)"""
        pass  # 로딩 다이얼로그는 이미 표시됨
    
    def _on_compare_progress(self, current, total):
        """진행률 업데이트 (오버레이 메시지 업데이트)"""
        if total > 0:
            percent = update_overlay_progress(self.loading_progress, current, total)
            self.loading_message.setText(f"비교 중... ({percent}%)")
    
    def _on_compare_result_ready(self, result: dict):
        """Worker 결과를 받아 UI 업데이트 (메인 스레드)"""
        if getattr(self, '_active_comparison_revision', self.comparison_settings.revision) != self.comparison_settings.revision:
            return
        self.mark_comparison_current()
        try:
            # 결과 저장
            self.last_s1_norm = result['s1_norm']
            self.last_s2_norm = result['s2_norm']
            self.last_s1_raw = result['s1_raw']
            self.last_s2_raw = result['s2_raw']
            
            # 하이라이트 적용 (일괄 처리)
            highlights1 = result.get('highlights1', [])
            highlights2 = result.get('highlights2', [])
            
            for hl in highlights1:
                self._apply_highlight_from_dict(self.viewer1, hl, COLOR_P1)
            for hl in highlights2:
                self._apply_highlight_from_dict(self.viewer2, hl, COLOR_P2)
            
            # diff_pages 설정
            self.viewer1.diff_pages = result.get('diff_pages1', [])
            self.viewer2.diff_pages = result.get('diff_pages2', [])
            self.viewer1.diff_index = -1
            self.viewer2.diff_index = -1
            
            # Anchor pairs 복원 (동기화용) 및 diff_list 채우기
            opcodes = result.get('opcodes', [])
            self.sync_anchor_pairs = self._build_sync_anchor_pairs(opcodes)
            self.diff_list = []

            # 페이지 높이 캐시
            page_heights1 = {}
            page_heights2 = {}

            for tag, i1, i2, j1, j2 in opcodes:
                if tag == 'equal':
                    continue
                left_anchor = self._build_anchor_from_range(self.viewer1, i1, i2)
                right_anchor = self._build_anchor_from_range(self.viewer2, j1, j2)
                if tag in ('delete', 'replace'):
                    self._append_compared_area(self.viewer1, i1, i2)
                    diff_text = ''
                    if i1 < len(self.last_s1_norm):
                        diff_text = self.last_s1_norm[i1:i2] if i2 <= len(self.last_s1_norm) else self.last_s1_norm[i1:]
                    pos_info = ''
                    if self.viewer1.char_data and i1 < len(self.viewer1.char_data):
                        char = self.viewer1.char_data[i1]
                        if 'bbox' in char:
                            char_y = char.get('y', 0)
                            page_num = char.get('page', 0)
                            if page_num >= 0 and self.viewer1.pdf_doc:
                                if page_num not in page_heights1:
                                    try:
                                        page_heights1[page_num] = self.viewer1.pdf_doc.load_page(page_num).rect.height
                                    except:
                                        page_heights1[page_num] = 0
                                page_height = page_heights1.get(page_num, 0)
                                if page_height > 0:
                                    percent = (char_y / page_height) * 100
                                    percent = max(0, min(100, percent))
                                    pos_info = f"(위에서 {percent:.0f}% 지점)"
                    # PDF 1의 페이지 번호는 char_data에서 직접 가져오기
                    page_num = 0
                    if self.viewer1.char_data and i1 < len(self.viewer1.char_data):
                        page_num = self.viewer1.char_data[i1].get('page', 0) + 1  # 1-indexed
                    elif left_anchor:
                        page_num = left_anchor[0] + 1
                    
                    self.diff_list.append({
                        'type': 'delete' if tag == 'delete' else 'replace',
                        'pdf': 'PDF 1',
                        'page': page_num,
                        'position': pos_info,
                        'text': diff_text[:100]
                    })
                if tag in ('insert', 'replace'):
                    self._append_compared_area(self.viewer2, j1, j2)
                    diff_text = ''
                    if j1 < len(self.last_s2_norm):
                        diff_text = self.last_s2_norm[j1:j2] if j2 <= len(self.last_s2_norm) else self.last_s2_norm[j1:]
                    pos_info = ''
                    if self.viewer2.char_data and j1 < len(self.viewer2.char_data):
                        char = self.viewer2.char_data[j1]
                        if 'bbox' in char:
                            char_y = char.get('y', 0)
                            page_num = char.get('page', 0)
                            if page_num >= 0 and self.viewer2.pdf_doc:
                                if page_num not in page_heights2:
                                    try:
                                        page_heights2[page_num] = self.viewer2.pdf_doc.load_page(page_num).rect.height
                                    except:
                                        page_heights2[page_num] = 0
                                page_height = page_heights2.get(page_num, 0)
                                if page_height > 0:
                                    percent = (char_y / page_height) * 100
                                    percent = max(0, min(100, percent))
                                    pos_info = f"(위에서 {percent:.0f}% 지점)"
                    # PDF 2의 페이지 번호는 char_data에서 직접 가져오기
                    page_num = 0
                    if self.viewer2.char_data and j1 < len(self.viewer2.char_data):
                        page_num = self.viewer2.char_data[j1].get('page', 0) + 1  # 1-indexed
                    elif right_anchor:
                        page_num = right_anchor[0] + 1
                    
                    self.diff_list.append({
                        'type': 'insert' if tag == 'insert' else 'replace',
                        'pdf': 'PDF 2',
                        'page': page_num,
                        'position': pos_info,
                        'text': diff_text[:100]
                    })
            
            # 뷰어 갱신 (최적화: visible 페이지만 우선)
            self._refresh_viewers_optimized()
            
        except Exception:
            raise
    
    def _refresh_viewers_optimized(self):
        """뷰어 갱신 최적화 - visible 페이지 우선, 나머지는 지연 갱신"""
        # 현재 visible 페이지 확인
        visible_pages1 = self._get_visible_pages(self.viewer1)
        visible_pages2 = self._get_visible_pages(self.viewer2)
        
        # Visible 페이지만 즉시 갱신 (사용자가 볼 수 있는 부분)
        for page_num in visible_pages1:
            if page_num < len(self.viewer1.page_labels):
                self.viewer1.page_labels[page_num].update()
        for page_num in visible_pages2:
            if page_num < len(self.viewer2.page_labels):
                self.viewer2.page_labels[page_num].update()
        
        # 전체 갱신은 지연 실행 (메인 루프 여유 있을 때)
        QTimer.singleShot(100, self._deferred_full_refresh)
    
    def _get_visible_pages(self, viewer):
        """현재 뷰포트에 보이는 페이지 번호 목록 반환 (QScrollArea용)"""
        visible_pages = []
        if not viewer.page_labels:
            return visible_pages
        
        # QScrollArea의 viewport 기준으로 계산
        viewport = viewer.viewport()
        if not viewport:
            return [0]  # 기본값: 첫 페이지
        
        scroll_y = viewer.verticalScrollBar().value()
        viewport_height = viewport.height()
        
        for i, lbl in enumerate(viewer.page_labels):
            # QLabel의 위치 계산 (스크롤 영역 내 상대 위치)
            lbl_y = lbl.y() if hasattr(lbl, 'y') else i * 100  # fallback
            lbl_height = lbl.height() if hasattr(lbl, 'height') else 100
            
            # 라벨이 viewport 내에 있는지 체크
            lbl_top = lbl_y
            lbl_bottom = lbl_y + lbl_height
            
            if lbl_bottom > scroll_y and lbl_top < scroll_y + viewport_height:
                visible_pages.append(i)
        
        return visible_pages if visible_pages else [0]
    
    def _deferred_full_refresh(self):
        """지연된 전체 갱신"""
        if getattr(self, '_displayed_comparison_revision', None) != self.comparison_settings.revision:
            return
        if hasattr(self, 'viewer1') and self.viewer1:
            self.viewer1.reload_pages()
        if hasattr(self, 'viewer2') and self.viewer2:
            self.viewer2.reload_pages()
        
        total = len(self.diff_list)
        QMessageBox.information(self, 'Comparison Complete', f'Found {total} differences.')
        # 완료 메시지 후 오버레이 숨김
        self.show_loading(False)
    
    def _on_compare_finished(self):
        """비교 완료 후 정리"""
        # 오버레이는 _deferred_full_refresh에서 메시지 표시 후 숨김
        if self.compare_manager:
            self.compare_manager.cleanup()
            self.compare_manager = None
    
    def _on_compare_error(self, error_msg: str):
        """비교 오류 처리"""
        self.show_loading(False)
        QMessageBox.critical(self, "비교 오류", f"PDF 비교 중 오류가 발생했습니다:\n{error_msg}")
        if self.compare_manager:
            self.compare_manager.cleanup()
            self.compare_manager = None
    
    def _apply_highlight_from_dict(self, viewer, hl_data: dict, color):
        """Worker에서 전달받은 highlight 데이터를 뷰어에 적용"""
        page_num = hl_data['page']
        bbox = hl_data['bbox']
        
        if page_num not in viewer.word_highlights:
            viewer.word_highlights[page_num] = []
        
        # 중복 체크 (color 포함)
        existing_bboxes = [h[0] for h in viewer.word_highlights[page_num]]
        if bbox not in existing_bboxes:
            viewer.word_highlights[page_num].append((bbox, color))
    
    def run_comparison(self):
        """동기식 비교 (호환성 유지용)"""
        self.start_async_comparison()
    
    def closeEvent(self, event):
        """위젯 종료 시 스레드 정리 (좀비 프로세스 방지)"""
        # 실행 중인 비교 작업이 있으면 정리
        if self.compare_manager:
            self.compare_manager.cancel()
            self.compare_manager.cleanup()
            self.compare_manager = None
        self.show_loading(False)
        
        super().closeEvent(event)

    def resizeEvent(self, event):
        """창 크기 변경 시 로딩 오버레이 중앙 정렬"""
        super().resizeEvent(event)
        if hasattr(self, 'loading_overlay'):
            # Center the loading overlay in the widget
            x = (self.width() - self.loading_overlay.width()) // 2
            y = (self.height() - self.loading_overlay.height()) // 2
            self.loading_overlay.move(x, y)

    def show_loading(self, show: bool, message: str = ""):
        """로딩 오버레이 표시/숨김 및 workspace 활성화/비활성화"""
        self.comparison_settings.set_busy(self, show)
        if show:
            if message:
                self.loading_message.setText(message)
            self.loading_progress.setRange(0, 0)
            self.loading_progress.setFormat("진행률 계산 중")
            # Center the overlay
            x = (self.width() - self.loading_overlay.width()) // 2
            y = (self.height() - self.loading_overlay.height()) // 2
            self.loading_overlay.move(x, y)
            self.loading_overlay.show()
            self.loading_overlay.raise_()
            if hasattr(self, 'movie') and self.movie:
                self.movie.start()
            # Disable workspace to block user input
            self.workspace.setEnabled(False)
        else:
            self.loading_overlay.hide()
            if hasattr(self, 'movie') and self.movie:
                self.movie.stop()
            # Re-enable workspace
            self.workspace.setEnabled(True)

    def _add_hl(self, viewer, info, color):
        page_num = info['page']
        if page_num not in viewer.word_highlights:
            viewer.word_highlights[page_num] = []
        if not any(h[0] == info['bbox'] and h[1] == color for h in viewer.word_highlights[page_num]):
            viewer.word_highlights[page_num].append((info['bbox'], color))

    # Reset methods
    def get_current_page(self, viewer):
        if not viewer.pdf_doc or not viewer.page_labels:
            return None
        scroll_top = viewer.verticalScrollBar().value()
        scroll_bottom = scroll_top + viewer.viewport().height()
        return max(range(len(viewer.page_labels)), key=lambda page: max(
            0, min(scroll_bottom, viewer.page_labels[page].y() + viewer.page_labels[page].height())
            - max(scroll_top, viewer.page_labels[page].y())
        ))

    def request_reset_page(self):
        if self.compare_manager:
            return
        self.reset_current_page()

    def reset_current_page(self):
        page1 = self.get_current_page(self.viewer1)
        page2 = self.get_current_page(self.viewer2)
        for viewer, page in ((self.viewer1, page1), (self.viewer2, page2)):
            if page is None:
                continue
            viewer.word_highlights.pop(page, None)
            viewer.last_compared_area.pop(page, None)
            viewer.diff_pages = [item for item in getattr(viewer, 'diff_pages', []) if item[0] != page]
            viewer.diff_index = -1
            viewer.refresh_highlights()
        self.diff_list = [item for item in self.diff_list if not (
            (item['pdf'] == 'PDF 1' and page1 is not None and item['page'] == page1 + 1)
            or (item['pdf'] == 'PDF 2' and page2 is not None and item['page'] == page2 + 1)
        )]
        self.sync_anchor_pairs = [
            (left, right) for left, right in self.sync_anchor_pairs
            if not ((left and page1 is not None and left[0] == page1)
                    or (right and page2 is not None and right[0] == page2))
        ]

    def request_reset(self):
        """초기화 요청 - show_loading 사용"""
        self.show_loading(True, "하이라이트 초기화 중...")
        # GIF 애니메이션이 시작될 시간을 확보 후 단계별 실행
        QTimer.singleShot(120, lambda: self._do_reset(0))

    def _do_reset(self, step_index=0):
        """실제 초기화 작업 수행 (단계별 실행)"""
        viewers = [self.viewer1, self.viewer2]

        if step_index >= len(viewers):
            self.last_s1_norm = ''
            self.last_s2_norm = ''
            self.sync_anchor_pairs = []
            self.show_loading(False)
            return

        try:
            viewer = viewers[step_index]
            viewer.word_highlights.clear()
            viewer.last_compared_area.clear()
            viewer.diff_pages = []
            viewer.diff_index = -1
            viewer.reload_pages()
            QTimer.singleShot(10, lambda: self._do_reset(step_index + 1))
        except Exception:
            self.show_loading(False)
            raise

    def show_legend_caution_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('📋 범례 및 주의사항')
        dialog.setFixedSize(600, 450)
        dialog.setStyleSheet(MODERN_QSS)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)

        # Legend group
        legend_group = QGroupBox('🎨 하이라이트 범례')
        legend_group_layout = QVBoxLayout(legend_group)
        legend_group_layout.setContentsMargins(15, 15, 15, 15)
        legend_group_layout.setSpacing(10)

        legend_content = QLabel(
            f"<div style='font-size:14px; line-height:1.8;'>"
            f"<div style='margin-bottom:10px;'>"
            f"<span style='color:rgba(255,149,0,0.6); background:rgba(255,149,0,0.3); padding:6px 12px; border-radius:4px; margin-right:10px;'>■</span>"
            f"<b>PDF1 (주황색)</b>: PDF 1에서 삭제되거나 변경된 내용"
            f"</div>"
            f"<div>"
            f"<span style='color:rgba(0,255,127,0.6); background:rgba(0,255,127,0.3); padding:6px 12px; border-radius:4px; margin-right:10px;'>■</span>"
            f"<b>PDF2 (연두색)</b>: PDF 2에서 추가되거나 변경된 내용"
            f"</div>"
            f"</div>"
        )
        legend_group_layout.addWidget(legend_content)
        layout.addWidget(legend_group)

        # Caution group
        caution_group = QGroupBox('⚠️ 주의사항')
        caution_group_layout = QVBoxLayout(caution_group)
        caution_group_layout.setContentsMargins(15, 15, 15, 15)
        caution_group_layout.setSpacing(8)

        caution_content = QLabel(
            "<div style='font-size:14px; line-height:1.8;'>"
            + self.comparison_caution_html() +
            "<div style='margin-bottom:12px;'>• <b>머릿글/바닥글</b>: 설정된 영역은 비교에서 제외됨</div>"
            "<div style='margin-bottom:12px;'>• <b>하이라이트</b>: 결과는 한쪽에만 표시될 수 있음</div>"
            "<div>• <b>정확도</b>: 100% 완벽하지 않을 수 있음, 참고용으로 활용</div>"
            "</div>"
        )
        caution_group_layout.addWidget(caution_content)
        layout.addWidget(caution_group)

        layout.addStretch()

        close_btn = QPushButton('닫기')
        close_btn.setObjectName('actionBtn')
        close_btn.setFixedHeight(38)
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec()

    def show_diff_list_dialog(self):
        """비교 결과 목록을 팝업으로 표시"""
        if not self.diff_list:
            QMessageBox.information(self, '결과 목록', '비교 결과가 없습니다. 먼저 비교를 실행해주세요.')
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f'📋 비교 결과 목록 · {self.comparison_settings.options.label}')
        dialog.setFixedSize(700, 500)
        dialog.setStyleSheet(MODERN_QSS)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)

        # 결과 요약
        total = len(self.diff_list)
        delete_count = sum(1 for d in self.diff_list if d['type'] == 'delete')
        insert_count = sum(1 for d in self.diff_list if d['type'] == 'insert')
        replace_count = sum(1 for d in self.diff_list if d['type'] == 'replace')

        summary = QLabel(
            f"<div style='font-size:14px; margin-bottom:15px;'>"
            f"<b>총 {total}개 차이점</b> | "
            f"<span style='color:#FF9500;'>삭제: {delete_count}</span> | "
            f"<span style='color:#34C759;'>추가: {insert_count}</span> | "
            f"<span style='color:#C2410C;'>변경: {replace_count}</span>"
            f"</div>"
        )
        layout.addWidget(summary)

        # 결과 리스트 위젯
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
        list_widget = QListWidget()
        list_widget.setSpacing(5)
        list_widget.setToolTip('␠: 공백 / ⇥: 탭 / ↵: 줄바꿈 / ⍽: 줄 바꿈 없는 공백')

        for i, diff in enumerate(self.diff_list):
            type_icon = {'delete': '❌', 'insert': '➕', 'replace': '🔄'}.get(diff['type'], '•')
            type_text = {'delete': '삭제', 'insert': '추가', 'replace': '변경'}.get(diff['type'], '•')
            pos = diff.get('position', '')

            item_text = f"{type_icon} [{diff['pdf']}] 페이지 {diff['page']} {pos} - {type_text}: {self.display_difference_text(diff['text'])}"
            item = QListWidgetItem(item_text)
            item.setData(1, diff)  # diff 데이터 저장
            list_widget.addItem(item)

        def on_item_clicked(item):
            diff = item.data(1)
            if not diff:
                return
            page_num = diff.get('page', 1) - 1  # 0-indexed
            viewer = self.viewer1 if diff.get('pdf') == 'PDF 1' else self.viewer2
            if viewer and viewer.page_labels and page_num < len(viewer.page_labels):
                lbl = viewer.page_labels[page_num]

                pos_str = diff.get('position', '')
                import re
                percent = None
                match = re.search(r'(\d+)%', pos_str)
                if match:
                    percent = int(match.group(1)) / 100

                def scroll_to_target():
                    page_top = lbl.y()
                    page_height_px = lbl.height() if lbl.height() > 0 else 1
                    target_y = page_top
                    if percent is not None:
                        target_y = page_top + page_height_px * percent
                    # 뷰어 중앙에 위치하도록 보정
                    target_scroll = int(target_y - viewer.viewport().height() / 2)
                    target_scroll = max(0, min(target_scroll, viewer.verticalScrollBar().maximum()))
                    viewer.verticalScrollBar().setValue(target_scroll)

                # 페이지 전체가 로드되었는지 확인 후 스크롤
                QTimer.singleShot(0, scroll_to_target)

        list_widget.itemClicked.connect(on_item_clicked)

        layout.addWidget(list_widget)

        # 버튼 행
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        # 전체 복사 버튼
        copy_btn = QPushButton('📋 전체 복사')
        copy_btn.setObjectName('secondaryBtn')
        copy_btn.setFixedHeight(38)
        copy_btn.setMinimumWidth(100)
        copy_btn.clicked.connect(lambda: self._copy_diff_list_to_clipboard(list_widget))
        btn_layout.addWidget(copy_btn)

        btn_layout.addStretch()

        # 닫기 버튼
        close_btn = QPushButton('닫기')
        close_btn.setObjectName('actionBtn')
        close_btn.setFixedHeight(38)
        close_btn.setMinimumWidth(80)
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        self.diff_list_dialog = dialog
        dialog.show()

    def _copy_diff_list_to_clipboard(self, list_widget):
        """결과 목록을 클립보드에 복사"""
        if not self.diff_list:
            return
        lines = []
        for diff in self.diff_list:
            type_icon = {'delete': '❌', 'insert': '➕', 'replace': '🔄'}.get(diff['type'], '•')
            type_text = {'delete': '삭제', 'insert': '추가', 'replace': '변경'}.get(diff['type'], '•')
            pos = diff.get('position', '')
            lines.append(f"{type_icon} [{diff['pdf']}] 페이지 {diff['page']} {pos} - {type_text}: {self.display_difference_text(diff['text'])}")
        text = '\n'.join(lines)
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, '복사 완료', '결과 목록이 클립보드에 복사되었습니다.')
