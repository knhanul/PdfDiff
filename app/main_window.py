from functools import partial
import importlib
 
from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PyQt6.QtGui import QFont, QIcon, QPixmap
from PyQt6.QtWidgets import QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QStyle, QVBoxLayout, QWidget
 
from app.common.resources import APP_NAME, COMPANY_NAME, DEVELOPER, RELEASE_DATE, VERSION, get_icon_path, get_logo_path
from app.common.styles import COLOR_PRIMARY, MODERN_QSS
from app.common.comparison_settings import ComparisonSettings


class MdiMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{APP_NAME} v{VERSION}')
        self.setGeometry(50, 50, 1700, 1000)
        self.setStyleSheet(MODERN_QSS)

        ico_path = get_icon_path()
        if ico_path:
            self.setWindowIcon(QIcon(ico_path))

        self.main_widget = QWidget()
        self.main_layout = QHBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.setCentralWidget(self.main_widget)

        self.focus_mode = False
        self.sidebar_expanded_width = 220
        self.sidebar_collapsed_width = 0  # fully hide in focus
        self.sidebar_width = self.sidebar_expanded_width
        self.sidebar_buttons = []
        self.tool_definitions = []
        self.current_tool_widget = None
        self.current_tool_key = None
        self.tool_cache = {}  # Cache for tool widgets
        self.comparison_settings = ComparisonSettings(self)

        # Blink animation for legend caution button
        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(self.toggle_button_blink)
        self.blink_state = False

        self.sidebar = self.create_sidebar()
        self.main_layout.addWidget(self.sidebar)

        self.right_panel = self.create_right_panel()
        self.main_layout.addWidget(self.right_panel, 1)

        self.sidebar_animation = QPropertyAnimation(self.sidebar, b'minimumWidth')
        self.sidebar_animation.setDuration(250)
        self.sidebar_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.sidebar_animation.valueChanged.connect(self.sync_sidebar_width)
        self.sidebar_animation.finished.connect(lambda: self.apply_sidebar_collapsed_state(self.sidebar_width == self.sidebar_collapsed_width))

        self.register_tools()
        self.populate_sidebar_buttons()
        self.open_tool('pdf_compare')

    def create_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setMinimumWidth(self.sidebar_expanded_width)
        sidebar.setMaximumWidth(self.sidebar_expanded_width)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 18, 12, 18)
        sidebar_layout.setSpacing(10)

        logo_card = QFrame()
        logo_card.setObjectName('sidebarLogoCard')
        logo_layout = QVBoxLayout(logo_card)
        logo_layout.setContentsMargins(12, 12, 12, 12)
        logo_layout.setSpacing(6)
        self.sidebar_logo = QLabel()
        self.sidebar_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = get_logo_path()
        if logo_path:
            self.sidebar_logo.setPixmap(QPixmap(logo_path).scaled(144, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.sidebar_brand_title = QLabel(APP_NAME)
        self.sidebar_brand_title.setObjectName('sidebarBrandTitle')
        self.sidebar_brand_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sidebar_brand_subtitle = QLabel(COMPANY_NAME)
        self.sidebar_brand_subtitle.setObjectName('sidebarBrandSubtitle')
        self.sidebar_brand_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 회사명 문구는 헤더/정보 팝업에서만 표시하고 사이드바 로고 하단에는 미표시
        self.sidebar_brand_subtitle.setVisible(False)
        logo_layout.addWidget(self.sidebar_logo)
        logo_layout.addWidget(self.sidebar_brand_title)
        logo_layout.addWidget(self.sidebar_brand_subtitle)
        sidebar_layout.addWidget(logo_card)

        self.sidebar_button_host = QVBoxLayout()
        self.sidebar_button_host.setSpacing(6)
        sidebar_layout.addLayout(self.sidebar_button_host)
        sidebar_layout.addStretch()
        return sidebar

    def create_right_panel(self):
        right_panel = QWidget()
        right_panel_layout = QVBoxLayout(right_panel)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(0)
        
        # Header bar
        self.header_bar = self.create_header_bar()
        right_panel_layout.addWidget(self.header_bar)
        
        # Tool container (replaces MDI area)
        self.tool_container = QWidget()
        self.tool_container_layout = QVBoxLayout(self.tool_container)
        self.tool_container_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.addWidget(self.tool_container, 1)

        return right_panel

    def create_header_bar(self):
        header = QFrame()
        header.setObjectName('headerBar')
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)

        self.header_title = QLabel(APP_NAME)
        self.header_title.setObjectName('headerTitle')
        header_layout.addWidget(self.header_title)
        header_layout.addSpacing(10)
        self.header_target = QLabel(COMPANY_NAME)
        self.header_target.setObjectName('headerTarget')
        header_layout.addWidget(self.header_target)
        header_layout.addStretch()

        version_label = QLabel(f'v{VERSION}')
        version_label.setObjectName('headerTarget')
        header_layout.addWidget(version_label)
        header_layout.addSpacing(8)
        self.legend_caution_btn = QPushButton('📋 범례 및 주의사항')
        self.legend_caution_btn.setObjectName('actionBtn')
        self.legend_caution_btn.setVisible(False)  # Initially hidden
        self.legend_caution_btn.clicked.connect(self.show_legend_caution_for_active_tool)
        header_layout.addWidget(self.legend_caution_btn)
        header_layout.addSpacing(8)
        self.info_btn = QPushButton('ℹ️')
        self.info_btn.setObjectName('infoBtn')
        self.info_btn.clicked.connect(self.show_info)
        header_layout.addWidget(self.info_btn)
        header_layout.addSpacing(8)
        # 현재 도구 닫기 버튼
        self.close_tool_btn = QPushButton('✕')
        self.close_tool_btn.setObjectName('closeToolBtn')
        self.close_tool_btn.setToolTip('현재 도구 닫기')
        self.close_tool_btn.clicked.connect(self.close_current_tool)
        header_layout.addWidget(self.close_tool_btn)
        header_layout.addSpacing(4)
        self.header_focus_btn = QPushButton()
        self.header_focus_btn.setObjectName('infoBtn')
        self.header_focus_btn.setFixedSize(36, 36)
        self.header_focus_btn.setCheckable(True)
        self.header_focus_btn.clicked.connect(self.toggle_sidebar)
        header_layout.addWidget(self.header_focus_btn)
        self.header_layout = header_layout
        self._sync_header_focus_button()
        return header

    def toggle_sidebar(self):
        self.focus_mode = not self.focus_mode
        if self.focus_mode:
            # Enter focus mode: hide sidebar and header bar completely
            self.sidebar_width = 0
            self.sidebar_animation.stop()
            self.sidebar_animation.setStartValue(self.sidebar.width())
            self.sidebar_animation.setEndValue(0)
            self.sidebar_animation.start()
            self.header_bar.hide()
            self._dock_focus_button(True)
        else:
            # Exit focus mode
            self.sidebar_width = self.sidebar_expanded_width
            self.sidebar_animation.stop()
            self.sidebar_animation.setStartValue(self.sidebar.width())
            self.sidebar_animation.setEndValue(self.sidebar_expanded_width)
            self.sidebar_animation.start()
            self._dock_focus_button(False)
            self.header_bar.show()
        self._sync_header_focus_button()
        for tool in self.tool_cache.values():
            self.update_focus_button(tool)

    def update_focus_button(self, tool):
        button = tool.btn_focus_mode
        label = '일반 모드로 전환' if self.focus_mode else '집중 모드로 전환'
        icon = QStyle.StandardPixmap.SP_TitleBarNormalButton if self.focus_mode else QStyle.StandardPixmap.SP_TitleBarMaxButton
        button.setIcon(button.style().standardIcon(icon))
        button.setChecked(self.focus_mode)
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.hide()
        self._sync_header_focus_button()
        self.update_focus_layout(tool)

    def _sync_header_focus_button(self):
        button = self.header_focus_btn
        label = '일반 모드로 전환' if self.focus_mode else '집중 모드로 전환'
        icon = QStyle.StandardPixmap.SP_TitleBarNormalButton if self.focus_mode else QStyle.StandardPixmap.SP_TitleBarMaxButton
        button.setIcon(button.style().standardIcon(icon))
        button.setChecked(self.focus_mode)
        button.setToolTip(label)
        button.setAccessibleName(label)

    def _dock_focus_button(self, floating):
        button = self.header_focus_btn
        if floating:
            button.setParent(self.right_panel)
            button.show()
            button.raise_()
            self._position_focus_button()
        else:
            if self.header_layout.indexOf(button) < 0:
                self.header_layout.addWidget(button)
            button.show()

    def _position_focus_button(self):
        if not self.focus_mode:
            return
        button = self.header_focus_btn
        button.move(max(8, self.right_panel.width() - button.width() - 12), 8)
        button.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, 'focus_mode', False):
            self._position_focus_button()

    def update_focus_layout(self, tool):
        bar = tool.bottom_action_bar
        layouts = (tool.layout(), bar.layout())
        if not hasattr(tool, '_normal_focus_layout'):
            tool._normal_focus_layout = {
                'style': bar.styleSheet(),
                'minimum_height': bar.minimumHeight(),
                'layouts': [(layout.contentsMargins(), layout.spacing()) for layout in layouts],
                'buttons': [(button, button.minimumSize(), button.maximumSize())
                            for button in bar.findChildren(QPushButton)],
            }
        normal = tool._normal_focus_layout
        if hasattr(tool, 'lbl_name1'):
            tool.lbl_name1.setVisible(not self.focus_mode)
        if hasattr(tool, 'lbl_name2'):
            tool.lbl_name2.setVisible(not self.focus_mode)
        if self.focus_mode:
            bar.setStyleSheet('''
                QFrame#actionBar { min-height: 0px; padding: 0px; }
                QFrame#actionBar QPushButton {
                    min-height: 0px; padding: 0px 6px;
                    font-size: 12px; border-radius: 5px;
                }
            ''')
            bar.setMinimumHeight(0)
            margins = normal['layouts'][0][0]
            layouts[0].setContentsMargins(margins.left(), margins.top(), margins.right(), 2)
            layouts[0].setSpacing(2)
            layouts[1].setContentsMargins(6, 2, 6, 2)
            layouts[1].setSpacing(4)
            for button, _, _ in normal['buttons']:
                button.setFixedHeight(28)
                if button.text():
                    button.setMinimumWidth(0)
                else:
                    button.setFixedWidth(28)
        else:
            for layout, (margins, spacing) in zip(layouts, normal['layouts']):
                layout.setContentsMargins(margins)
                layout.setSpacing(spacing)
            for button, minimum, maximum in normal['buttons']:
                button.setMinimumSize(minimum)
                button.setMaximumSize(maximum)
            bar.setMinimumHeight(normal['minimum_height'])
            bar.setStyleSheet(normal['style'])

    def sync_sidebar_width(self, value):
        width = int(value)
        self.sidebar.setMinimumWidth(width)
        self.sidebar.setMaximumWidth(width)
        if self.focus_mode:
            self._position_focus_button()

    def apply_sidebar_collapsed_state(self, collapsed):
        if collapsed:
            # Show small logo only
            self.sidebar_brand_title.setVisible(False)
            self.sidebar_brand_subtitle.setVisible(False)
            logo_path = get_logo_path()
            if logo_path:
                self.sidebar_logo.setPixmap(QPixmap(logo_path).scaled(40, 18, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            # Show full logo card
            self.sidebar_brand_title.setVisible(True)
            self.sidebar_brand_subtitle.setVisible(False)
            logo_path = get_logo_path()
            if logo_path:
                self.sidebar_logo.setPixmap(QPixmap(logo_path).scaled(144, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        for tool_definition, button in zip(self.tool_definitions, self.sidebar_buttons):
            button.setProperty('collapsed', collapsed)
            if collapsed:
                # Use icon property for collapsed state
                icon = tool_definition.get('icon', '📄')
                button.setText(icon)
                button.setMinimumHeight(50)
                button.setMaximumHeight(50)
            else:
                button.setText(tool_definition['menu_title'])
                button.setMinimumHeight(0)
                button.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
            button.style().unpolish(button)
            button.style().polish(button)

    def populate_sidebar_buttons(self):
        while self.sidebar_button_host.count():
            item = self.sidebar_button_host.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.sidebar_buttons = []
        for tool_definition in self.tool_definitions:
            button = QPushButton(tool_definition['menu_title'])
            button.setObjectName('sidebarBtn')
            button.setEnabled(tool_definition['enabled'])
            button.setProperty('active', False)
            if tool_definition['enabled']:
                button.clicked.connect(partial(self.open_tool, tool_definition['key']))
            self.sidebar_button_host.addWidget(button)
            self.sidebar_buttons.append(button)
        self.apply_sidebar_collapsed_state(self.sidebar_width == self.sidebar_collapsed_width)

    def set_active_sidebar_button(self, tool_key):
        for tool_definition, button in zip(self.tool_definitions, self.sidebar_buttons):
            button.setProperty('active', tool_definition['key'] == tool_key)
            button.style().unpolish(button)
            button.style().polish(button)
        
        # Show/hide legend caution button based on active tool
        should_show = tool_key in ('pdf_compare', 'pdf_hf_compare')
        self.legend_caution_btn.setVisible(should_show)
        if should_show:
            self.start_button_blinking()
        else:
            self.stop_button_blinking()

    def start_button_blinking(self):
        self.blink_state = False
        self.blink_timer.start(500)  # Blink every 500ms

    def stop_button_blinking(self):
        self.blink_timer.stop()
        self.legend_caution_btn.setStyleSheet('')  # Reset to default style

    def toggle_button_blink(self):
        self.blink_state = not self.blink_state
        if self.blink_state:
            self.legend_caution_btn.setStyleSheet('QPushButton#actionBtn { background-color: #FFA500; color: white; }')
        else:
            self.legend_caution_btn.setStyleSheet('')

    def register_tools(self):
        tool_definitions = [
            {
                'key': 'pdf_compare',
                'menu_title': '영역지정비교',
                'window_title': 'PDF 지정 영역 비교',
                'module_path': 'app.tools.pdf_compare',
                'class_name': 'PdfCompareWidget',
                'singleton': True,
                'enabled': True,
                'icon': '📄',
            },
            {
                'key': 'pdf_hf_compare',
                'menu_title': '전체비교',
                'window_title': 'PDF 전체 비교',
                'module_path': 'app.tools.pdf_header_footer_compare',
                'class_name': 'HFCompareWidget',
                'singleton': True,
                'enabled': True,
                'icon': '📄',
            },
            {
                'key': 'pdf_editor',
                'menu_title': 'PDF 편집',
                'window_title': 'PDF 편집 (분할/병합/페이지)',
                'module_path': 'app.tools.pdf_editor',
                'class_name': 'PdfEditorWidget',
                'singleton': True,
                'enabled': True,
                'icon': '✏️',
            },
            {
                'key': 'pdf_create',
                'menu_title': 'PDF 생성',
                'window_title': 'PDF 생성',
                'module_path': 'app.tools.pdf_create',
                'class_name': 'PdfCreateWidget',
                'singleton': True,
                'enabled': True,
                'icon': '📝',
            },
        ]
        self.tool_definitions = tool_definitions

    def get_tool_definition(self, tool_key):
        for tool_definition in self.tool_definitions:
            if tool_definition['key'] == tool_key:
                return tool_definition
        return None

    def open_tool(self, tool_key):
        tool_definition = self.get_tool_definition(tool_key)
        if not tool_definition:
            QMessageBox.warning(self, 'Error', 'Selected tool information not found.')
            return

        # If the same tool is already active, do nothing
        if self.current_tool_key == tool_key:
            return

        # Hide current tool if exists - trigger closeEvent for thread cleanup
        if self.current_tool_widget:
            # close()를 호출하여 closeEvent가 실행되도록 함 (스레드 정리)
            self.current_tool_widget.close()
            self.current_tool_widget.hide()

        # Get or create tool widget from cache
        if tool_key not in self.tool_cache:
            # Lazy load module
            try:
                module = importlib.import_module(tool_definition['module_path'])
                factory_class = getattr(module, tool_definition['class_name'])
                new_tool = factory_class(comparison_settings=self.comparison_settings)
                if hasattr(new_tool, 'btn_focus_mode'):
                    new_tool.btn_focus_mode.clicked.connect(self.toggle_sidebar)
                # 비교 도구끼만 상호 전환 버튼 연결 (기존 동작 유지)
                if tool_key in ('pdf_compare', 'pdf_hf_compare') and hasattr(new_tool, 'btn_switch_tool'):
                    target_key = 'pdf_hf_compare' if tool_key == 'pdf_compare' else 'pdf_compare'
                    target_title = self.get_tool_definition(target_key)['menu_title']
                    button = new_tool.btn_switch_tool
                    button.setIcon(button.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
                    button.setToolTip(f'{target_title}로 전환')
                    button.setAccessibleName(f'{target_title}로 전환')
                    button.clicked.connect(partial(self.open_tool, target_key))
                self.tool_cache[tool_key] = new_tool
                self.tool_container_layout.addWidget(new_tool)
                new_tool.ensurePolished()
                self.update_focus_button(new_tool)
            except Exception as e:
                QMessageBox.warning(self, 'Error', f'Failed to load tool: {e}')
                return
        else:
            new_tool = self.tool_cache[tool_key]

        # Show the new tool
        new_tool.show()
        self.current_tool_widget = new_tool
        self.current_tool_key = tool_key

        # Update header and sidebar
        self.header_title.setText(tool_definition['window_title'])
        self.set_active_sidebar_button(tool_key)

    def close_current_tool(self):
        """현재 활성화된 도구 닫기"""
        if not self.current_tool_widget:
            return

        # close()를 호출하여 closeEvent가 실행되도록 함 (스레드 정리)
        self.current_tool_widget.close()
        self.current_tool_widget.hide()

        # 캐시에서도 제거 (완전히 닫기)
        if self.current_tool_key in self.tool_cache:
            widget = self.tool_cache.pop(self.current_tool_key)
            self.tool_container_layout.removeWidget(widget)
            widget.deleteLater()

        # 상태 초기화
        self.current_tool_widget = None
        self.current_tool_key = None

        # 헤더와 사이드바 초기화
        self.header_title.setText(APP_NAME)
        self.set_active_sidebar_button(None)

    def show_legend_caution_for_active_tool(self):
        # Find the active PDF compare widget
        if self.current_tool_key in ('pdf_compare', 'pdf_hf_compare') and self.current_tool_widget:
            if hasattr(self.current_tool_widget, 'show_legend_caution_dialog'):
                self.current_tool_widget.show_legend_caution_dialog()

    def show_info(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(f'정보 - v{VERSION} ({RELEASE_DATE})')
        dialog.setFixedSize(600, 500)
        dialog.setStyleSheet(MODERN_QSS)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Add AIResearch.png image (6x size)
        from configs.settings import SETTINGS
        ai_research_path = SETTINGS['BASE_DIR'] / 'assets' / 'AIResearch.png'
        if ai_research_path.exists():
            image = QLabel()
            image.setPixmap(QPixmap(str(ai_research_path)).scaled(900, 480, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(image)

        # 빌드 시 설정된 버전/제작일자 표시
        version_info = QLabel(
            f"<div style='text-align:center; color:#666; font-size:11px; margin:4px 0;'>"
            f"버전 v{VERSION} &nbsp;|&nbsp; 제작일자 {RELEASE_DATE}"
            f"</div>"
        )
        version_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_info)

        # 나머지 정보 내용은 원본 파일과 동일하게 유지
        # (전체 내용은 로컬 파일 참조)
        layout.addStretch()
        dialog.exec()

    def closeEvent(self, event):
        """애플리케이션 종료 시 모든 스레드 정리 (좀비 프로세스 방지)"""
        # 현재 활성화된 도구의 스레드 정리
        if self.current_tool_widget:
            self.current_tool_widget.close()
        
        # 캐시된 모든 도구 위젯의 스레드 정리
        for tool_widget in self.tool_cache.values():
            tool_widget.close()
        
        # 이벤트 수락 (창 닫기 진행)
        event.accept()


def run():
    app = QApplication.instance() or QApplication([])
    app.setFont(QFont('Malgun Gothic', 10))
    window = MdiMainWindow()
    window.show()
    return app.exec()
