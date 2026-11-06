from collections import OrderedDict
from functools import partial
import importlib
import os
 
from PyQt6.QtCore import QEasingCurve, QLibraryInfo, QLocale, QPropertyAnimation, QSize, Qt, QTimer, QTranslator
from PyQt6.QtGui import QFont, QIcon, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea, QStackedWidget, QStyle, QVBoxLayout, QWidget
 
from app.common.about_dialog import AboutDialog, get_about_info
from app.common.resources import APP_NAME, DEVELOPER, VERSION, get_about_icon_path, get_icon_path, get_logo_path
from app.common.styles import COLOR_PRIMARY, MODERN_QSS
from app.common.comparison_settings import ComparisonSettings
from app.services import app_settings, recent_docs, workspace_session
from app.shell.theme import build_shell_qss, theme_tokens
from app.shell.sidebar_icons import brand_mark, line_icon, official_brand_pixmap
from app.shell.viewer_workspace import ViewerWorkspace
from app.shell.welcome_page import WelcomePage
from app.viewer.document_manager import DocumentManager

TOOL_CACHE_MAX = 3  # default LRU limit for tool widgets (설정 › 성능에서 변경)
SIDEBAR_COMPACT_WIDTH = 56


class MdiMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{APP_NAME} v{VERSION}')
        self.setGeometry(50, 50, 1700, 1000)
        self.setAcceptDrops(True)

        ico_path = get_icon_path()
        if ico_path:
            self.setWindowIcon(QIcon(ico_path))

        self.main_widget = QWidget()
        self.main_layout = QHBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.setCentralWidget(self.main_widget)

        self.focus_mode = False
        self.sidebar_expanded_width = 224
        self.sidebar_collapsed_width = 0  # fully hide in focus
        self.sidebar_width = self.sidebar_expanded_width
        self.sidebar_compact = False      # icon-only sidebar (narrow window or manual)
        self.sidebar_manual = None        # None = automatic; True/False = user choice
        self.settings_page = None
        self.sidebar_buttons = []
        self.tool_definitions = []
        self.current_tool_widget = None
        self.current_tool_key = None
        self.tool_cache = OrderedDict()  # LRU cache for tool widgets (max TOOL_CACHE_MAX)
        self.doc_manager = DocumentManager(self)
        self.split_view = None
        self.nav_buttons = {}
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
        self.sidebar_animation.finished.connect(lambda: self.apply_sidebar_collapsed_state(self.sidebar_width < self.sidebar_expanded_width))

        self.register_tools()
        self.populate_sidebar_buttons()
        # Viewer-first: start on the welcome page. No tool module is imported here.
        self.apply_settings()
        self.show_welcome()
        QShortcut(QKeySequence('Ctrl+O'), self, activated=self.open_pdf_dialog)
        QShortcut(QKeySequence('Ctrl+K'), self, activated=self.show_command_palette)
        QShortcut(QKeySequence('Ctrl+Shift+F'), self, activated=self.show_global_search)
        QShortcut(QKeySequence('Ctrl+,'), self, activated=self.show_settings)
        if app_settings.get('workspace/auto_restore') and workspace_session.load_session():
            QTimer.singleShot(0, self.restore_session)  # after first paint

    def create_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setMinimumWidth(self.sidebar_expanded_width)
        sidebar.setMaximumWidth(self.sidebar_expanded_width)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 14, 10, 14)
        sidebar_layout.setSpacing(6)

        self.logo_card = QFrame()
        self.logo_card.setObjectName('sidebarLogoCard')
        logo_layout = QHBoxLayout(self.logo_card)
        logo_layout.setContentsMargins(8, 6, 8, 6)
        logo_layout.setSpacing(10)
        self.sidebar_logo = QLabel()
        self.sidebar_logo.setObjectName('sidebarBrandMark')
        self.sidebar_logo.setFixedSize(36, 36)
        self.sidebar_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._refresh_brand_mark()
        brand_text = QVBoxLayout()
        brand_text.setContentsMargins(0, 0, 0, 0)
        brand_text.setSpacing(1)
        self.sidebar_brand_title = QLabel(APP_NAME)
        self.sidebar_brand_title.setObjectName('sidebarBrandTitle')
        self.sidebar_brand_subtitle = QLabel('PDF Workspace')
        self.sidebar_brand_subtitle.setObjectName('sidebarBrandSubtitle')
        brand_text.addWidget(self.sidebar_brand_title)
        brand_text.addWidget(self.sidebar_brand_subtitle)
        logo_layout.addWidget(self.sidebar_logo, 0, Qt.AlignmentFlag.AlignVCenter)
        logo_layout.addLayout(brand_text, 1)
        sidebar_layout.addWidget(self.logo_card)

        self.sidebar_brand_divider = QFrame()
        self.sidebar_brand_divider.setObjectName('sidebarDivider')
        self.sidebar_brand_divider.setFrameShape(QFrame.Shape.HLine)
        sidebar_layout.addWidget(self.sidebar_brand_divider)

        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setObjectName('sidebarScroll')
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_body = QWidget()
        scroll_body.setObjectName('sidebarScrollBody')
        scroll_layout = QVBoxLayout(scroll_body)
        scroll_layout.setContentsMargins(0, 2, 0, 2)
        scroll_layout.setSpacing(4)

        self.view_button_host = QVBoxLayout()
        self.view_button_host.setSpacing(2)
        for key, title in (('home', '홈'), ('viewer', 'PDF 보기'), ('split', '두 PDF 동시 보기')):
            icon = key
            btn = QPushButton(title)
            btn.setObjectName('sidebarBtn')
            btn.setProperty('active', False)
            btn.setProperty('nav_icon', icon)
            btn.setProperty('nav_title', title)
            btn.clicked.connect(partial(self.activate_view, key))
            self.view_button_host.addWidget(btn)
            self.nav_buttons[key] = btn
        scroll_layout.addLayout(self.view_button_host)

        self.feature_group_label = QLabel('핵심 기능')
        self.feature_group_label.setObjectName('sidebarGroupLabel')
        scroll_layout.addWidget(self.feature_group_label)
        self.feature_button_host = QVBoxLayout()
        self.feature_button_host.setSpacing(6)
        scroll_layout.addLayout(self.feature_button_host)

        self.tools_group_label = QLabel('도구')
        self.tools_group_label.setObjectName('sidebarGroupLabel')
        scroll_layout.addWidget(self.tools_group_label)
        self.sidebar_button_host = QVBoxLayout()
        self.sidebar_button_host.setSpacing(2)
        scroll_layout.addLayout(self.sidebar_button_host)
        scroll_layout.addStretch()
        self.sidebar_scroll.setWidget(scroll_body)
        sidebar_layout.addWidget(self.sidebar_scroll, 1)

        footer = QFrame()
        footer.setObjectName('sidebarFooter')
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(0, 8, 0, 0)
        btn = QPushButton('설정')
        btn.setObjectName('sidebarBtn')
        btn.setProperty('active', False)
        btn.setProperty('nav_icon', 'settings')
        btn.setProperty('nav_title', '설정')
        btn.setToolTip('설정 및 작업 공간 관리 (Ctrl+,)')
        btn.clicked.connect(partial(self.activate_view, 'settings'))
        footer_layout.addWidget(btn)
        sidebar_layout.addWidget(footer)
        self.nav_buttons['settings'] = btn
        return sidebar

    # ---- Quiet Brand line icons ------------------------------------------------
    def _sidebar_tokens(self):
        try:
            return theme_tokens(app_settings.get('ui/theme'))
        except Exception:
            return theme_tokens('default')

    def _refresh_brand_mark(self):
        theme_id = 'default'
        try:
            theme_id = app_settings.get('ui/theme') or 'default'
        except Exception:
            pass
        tokens = self._sidebar_tokens()
        # Official 기관문양 — do not recolor; neutral light pad keeps crisp contrast across themes.
        pm = official_brand_pixmap(34, light_pad=True, pad_bg='#FFFFFF', pad_border=tokens['brand_border'])
        if pm is None or pm.isNull():
            pm = brand_mark(tokens['accent'], 34)
        self.sidebar_logo.setPixmap(pm)

    def refresh_sidebar_icons(self):
        tokens = self._sidebar_tokens()
        pairs = [(b.property('nav_icon'), b) for b in self.nav_buttons.values()]
        pairs += [(d['key'], b) for d, b in zip(self.tool_definitions, self.sidebar_buttons)]
        for key, b in pairs:
            is_featured = bool(b.property('featured'))
            is_active = bool(b.property('active'))
            if is_featured or is_active:
                color = tokens['accent']
            else:
                color = tokens['sidebar_icon']
            stroke = 1.75 if is_featured else 1.5
            icon = line_icon(key, color, 18, stroke=stroke)
            feat_icon_lbl = getattr(b, '_feature_icon_label', None)
            if feat_icon_lbl is not None and not b.property('collapsed'):
                b.setIcon(QIcon())
                feat_icon_lbl.setPixmap(icon.pixmap(QSize(18, 18)))
            else:
                b.setIcon(icon)
                b.setIconSize(QSize(18, 18))
        if hasattr(self, 'header_focus_btn') and getattr(self, 'focus_mode', False):
            self.header_focus_btn.setIcon(line_icon('exit_focus', tokens['accent'], 16))
            self.header_focus_btn.setIconSize(QSize(16, 16))
        if hasattr(self, 'welcome_page') and hasattr(self.welcome_page, 'refresh_theme_icons'):
            self.welcome_page.refresh_theme_icons(tokens)

    def create_right_panel(self):
        right_panel = QWidget()
        right_panel_layout = QVBoxLayout(right_panel)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(0)
        
        # Header bar
        self.header_bar = self.create_header_bar()
        right_panel_layout.addWidget(self.header_bar)
        
        # Mode stack: Welcome | Viewer | Split | Tool host
        self.mode_stack = QStackedWidget()
        self.welcome_page = WelcomePage()
        self.welcome_page.open_requested.connect(self.open_pdf_dialog)
        self.welcome_page.open_path.connect(self.open_pdf)
        self.welcome_page.action_requested.connect(self._on_welcome_action)
        self.welcome_page.restore_requested.connect(self.restore_session)
        self.mode_stack.addWidget(self.welcome_page)

        self.viewer = ViewerWorkspace()
        self.viewer.form_fill_requested.connect(self.open_form_for)
        self.viewer.split_requested.connect(self.open_split_view)
        self.viewer.open_requested.connect(self.open_pdf_dialog)
        self.viewer.close_doc.connect(self._on_viewer_doc_closed)
        self.viewer.current_changed.connect(self._update_title)
        self.viewer.tool_requested.connect(self._on_viewer_tool_request)
        self.mode_stack.addWidget(self.viewer)

        # Tool container (existing tools are hosted here unchanged)
        self.tool_container = QWidget()
        self.tool_container_layout = QVBoxLayout(self.tool_container)
        self.tool_container_layout.setContentsMargins(0, 0, 0, 0)
        self.mode_stack.addWidget(self.tool_container)
        right_panel_layout.addWidget(self.mode_stack, 1)

        return right_panel

    def create_header_bar(self):
        header = QFrame()
        header.setObjectName('headerBar')
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)

        self.header_accent = QFrame()
        self.header_accent.setObjectName('headerAccent')
        self.header_accent.setFixedSize(3, 22)
        header_layout.addWidget(self.header_accent)
        header_layout.addSpacing(10)
        self.header_title = QLabel(APP_NAME)
        self.header_title.setObjectName('headerTitle')
        header_layout.addWidget(self.header_title)
        header_layout.addStretch()

        self.legend_caution_btn = QPushButton('📋 범례 및 주의사항')
        self.legend_caution_btn.setObjectName('headerLegendBtn')
        self.legend_caution_btn.setVisible(False)  # Initially hidden
        self.legend_caution_btn.clicked.connect(self.show_legend_caution_for_active_tool)
        header_layout.addWidget(self.legend_caution_btn)
        header_layout.addSpacing(8)
        self.info_btn = QPushButton()
        self.info_btn.setObjectName('infoBtn')
        about_icon = get_about_icon_path()
        if about_icon and not QPixmap(about_icon).isNull():
            self.info_btn.setIcon(QIcon(about_icon))
            self.info_btn.setIconSize(QSize(20, 20))
        else:
            self.info_btn.setText('ⓘ')
        self.info_btn.setToolTip('프로그램 정보')
        self.info_btn.clicked.connect(self.show_info)
        header_layout.addWidget(self.info_btn)
        header_layout.addSpacing(8)
        # 현재 도구 닫기 버튼
        self.close_tool_btn = QPushButton('✕')
        self.close_tool_btn.setObjectName('closeToolBtn')
        self.close_tool_btn.setToolTip('현재 도구 닫기 (프로그램은 종료되지 않습니다)')
        self.close_tool_btn.clicked.connect(self.close_current_tool)
        header_layout.addWidget(self.close_tool_btn)
        header_layout.addSpacing(4)
        self.header_focus_btn = QPushButton('집중모드')
        self.header_focus_btn.setObjectName('headerFocusBtn')
        self.header_focus_btn.setCheckable(True)
        self.header_focus_btn.clicked.connect(self.toggle_sidebar)
        header_layout.addWidget(self.header_focus_btn)
        self.header_layout = header_layout
        self._sync_header_focus_button()
        return header

    def toggle_sidebar(self):
        self.focus_mode = not self.focus_mode
        self._sync_header_focus_button()
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
            self.sidebar_width = self._normal_sidebar_width()
            self.sidebar_animation.stop()
            self.sidebar_animation.setStartValue(self.sidebar.width())
            self.sidebar_animation.setEndValue(self.sidebar_width)
            self.sidebar_animation.start()
            self._dock_focus_button(False)
            self.header_bar.show()
        for tool in self.tool_cache.values():
            self.update_focus_button(tool)

    def update_focus_button(self, tool):
        self._sync_header_focus_button()
        if not hasattr(tool, 'btn_focus_mode'):
            return
        button = tool.btn_focus_mode
        label = '일반 모드로 전환' if self.focus_mode else '집중 모드로 전환'
        icon = QStyle.StandardPixmap.SP_TitleBarNormalButton if self.focus_mode else QStyle.StandardPixmap.SP_TitleBarMaxButton
        button.setIcon(button.style().standardIcon(icon))
        button.setChecked(self.focus_mode)
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.hide()
        if hasattr(tool, 'bottom_action_bar'):
            self.update_focus_layout(tool)

    def _sync_header_focus_button(self):
        button = self.header_focus_btn
        label = '일반 모드로 전환' if self.focus_mode else '집중 모드로 전환'
        button.setProperty('floating', self.focus_mode)
        if self.focus_mode:
            button.setText('')
            button.setIcon(line_icon('exit_focus', self._sidebar_tokens()['accent'], 16))
            button.setIconSize(QSize(16, 16))
            button.setFixedSize(28, 28)
        else:
            button.setText('집중모드')
            button.setIcon(QIcon())
            button.setMinimumSize(0, 0)
            button.setMaximumSize(16777215, 16777215)
        button.setChecked(self.focus_mode)
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.style().unpolish(button)
        button.style().polish(button)
        if self.focus_mode:
            self._position_focus_button()

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
        elif hasattr(self, 'sidebar_animation'):
            self.update_sidebar_compact()

    # ---- narrow window: icon sidebar --------------------------------------
    def _normal_sidebar_width(self):
        return SIDEBAR_COMPACT_WIDTH if self.sidebar_compact else self.sidebar_expanded_width

    def update_sidebar_compact(self, animate=False):
        if self.sidebar_manual is not None:
            want = self.sidebar_manual
        elif app_settings.get('ui/auto_compact_sidebar'):
            want = self.width() < app_settings.get('ui/compact_threshold')
        else:
            want = False
        if want == self.sidebar_compact and self.sidebar.width() == self._normal_sidebar_width():
            return
        self.sidebar_compact = want
        if self.focus_mode:
            return
        self.sidebar_width = self._normal_sidebar_width()
        self.sidebar_animation.stop()
        if animate:
            self.sidebar_animation.setStartValue(self.sidebar.width())
            self.sidebar_animation.setEndValue(self.sidebar_width)
            self.sidebar_animation.start()
        else:
            self.sync_sidebar_width(self.sidebar_width)
            self.apply_sidebar_collapsed_state(want)
        self.sidebar.layout().setContentsMargins(*((4, 12, 4, 12) if want else (10, 14, 10, 14)))

    def toggle_sidebar_compact(self):
        self.sidebar_manual = not self.sidebar_compact
        self.update_sidebar_compact(animate=True)

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
                'toggles': [(widget, widget.layout().contentsMargins())
                            for widget in bar.findChildren(QFrame, 'toolToggle')],
            }
        normal = tool._normal_focus_layout
        if hasattr(tool, 'lbl_name1'):
            tool.lbl_name1.setVisible(not self.focus_mode)
        if hasattr(tool, 'lbl_name2'):
            tool.lbl_name2.setVisible(not self.focus_mode)
        # 도구 전환 토글은 집중모드(사이드바 숨김)에서만 표시
        if hasattr(tool, 'switch_toggle'):
            tool.switch_toggle.setVisible(self.focus_mode)
        if self.focus_mode:
            bar.setStyleSheet('''
                QFrame#actionBar { min-height: 0px; padding: 0px; }
                QFrame#actionBar QPushButton {
                    min-height: 0px; padding: 0px 6px;
                    font-size: 12px; border-radius: 5px;
                }
                QFrame#actionBar QFrame#toolToggle QPushButton#toolToggleBtn {
                    padding: 3px 12px;
                    border-radius: 8px;
                    font-size: 12px;
                    min-height: 22px;
                }
            ''')
            bar.setMinimumHeight(0)
            margins = normal['layouts'][0][0]
            layouts[0].setContentsMargins(margins.left(), margins.top(), margins.right(), 2)
            layouts[0].setSpacing(2)
            layouts[1].setContentsMargins(6, 2, 6, 2)
            layouts[1].setSpacing(4)
            for button, _, _ in normal['buttons']:
                if button.objectName() == 'toolToggleBtn':
                    continue
                button.setFixedHeight(28)
                if button.text():
                    button.setMinimumWidth(0)
                else:
                    button.setFixedWidth(28)
            for widget, _ in normal['toggles']:
                widget.layout().setContentsMargins(2, 0, 2, 0)
                widget.setMaximumHeight(30)
        else:
            for layout, (margins, spacing) in zip(layouts, normal['layouts']):
                layout.setContentsMargins(margins)
                layout.setSpacing(spacing)
            for button, minimum, maximum in normal['buttons']:
                button.setMinimumSize(minimum)
                button.setMaximumSize(maximum)
            for widget, margins in normal['toggles']:
                widget.layout().setContentsMargins(margins)
                widget.setMaximumHeight(16777215)
            bar.setMinimumHeight(normal['minimum_height'])
            bar.setStyleSheet(normal['style'])

    def sync_sidebar_width(self, value):
        width = int(value)
        self.sidebar.setMinimumWidth(width)
        self.sidebar.setMaximumWidth(width)
        if self.focus_mode:
            self._position_focus_button()

    def apply_sidebar_collapsed_state(self, collapsed):
        # Quiet Brand: the official mark stays; only the title block collapses.
        self.sidebar_brand_title.setVisible(not collapsed)
        self.sidebar_brand_subtitle.setVisible(not collapsed)
        if hasattr(self, 'logo_card'):
            self.logo_card.setProperty('collapsed', collapsed)
            self.logo_card.style().unpolish(self.logo_card)
            self.logo_card.style().polish(self.logo_card)
        if hasattr(self, 'feature_group_label'):
            self.feature_group_label.setVisible(not collapsed)
        self.tools_group_label.setVisible(not collapsed)
        for button in self.nav_buttons.values():
            button.setProperty('collapsed', collapsed)
            title = button.property('nav_title') or ''
            if collapsed:
                button.setText('')
                button.setToolTip(title)
            else:
                button.setText(title)
                button.setToolTip('설정 및 작업 공간 관리 (Ctrl+,)' if button.property('nav_icon') == 'settings' else '')
            button.style().unpolish(button)
            button.style().polish(button)
        for tool_definition, button in zip(self.tool_definitions, self.sidebar_buttons):
            button.setProperty('collapsed', collapsed)
            title = tool_definition['menu_title']
            subtitle = tool_definition.get('menu_subtitle', '')
            is_featured = bool(tool_definition.get('featured'))
            if is_featured and hasattr(button, '_feature_title_label'):
                button.setText('')
                button._feature_title_label.setVisible(not collapsed)
                button._feature_desc_label.setVisible(not collapsed)
                button._feature_icon_label.setVisible(not collapsed)
                if collapsed:
                    button.setToolTip(f'{title} — {subtitle}' if subtitle else title)
                    button.setMinimumHeight(40)
                    button.setMaximumHeight(40)
                else:
                    button.setToolTip(tool_definition.get('window_title', ''))
                    button.setMinimumHeight(46)
                    button.setMaximumHeight(52)
            else:
                if collapsed:
                    button.setText('')
                    button.setToolTip(title)
                    button.setMinimumHeight(40 if self.sidebar_compact else 50)
                    button.setMaximumHeight(40 if self.sidebar_compact else 50)
                else:
                    button.setText(title)
                    button.setToolTip('')
                    button.setMinimumHeight(0)
                    button.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
            button.style().unpolish(button)
            button.style().polish(button)
        self.refresh_sidebar_icons()

    def _create_feature_sidebar_button(self, tool_definition):
        title = tool_definition['menu_title']
        subtitle = tool_definition.get('menu_subtitle', '')
        button = QPushButton()
        button.setObjectName('sidebarFeatureBtn')
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setEnabled(tool_definition['enabled'])
        button.setProperty('active', False)
        button.setProperty('featured', True)
        button.setProperty('nav_icon', tool_definition['key'])
        button.setProperty('nav_title', title)
        button.setProperty('nav_subtitle', subtitle)
        lay = QHBoxLayout(button)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)
        icon_lbl = QLabel()
        icon_lbl.setObjectName('sidebarFeatureIcon')
        icon_lbl.setFixedSize(28, 28)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)
        title_lbl = QLabel(title)
        title_lbl.setObjectName('sidebarFeatureTitle')
        title_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        desc_lbl = QLabel(subtitle)
        desc_lbl.setObjectName('sidebarFeatureDesc')
        desc_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_col.addWidget(title_lbl)
        text_col.addWidget(desc_lbl)
        lay.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(text_col, 1)
        button._feature_icon_label = icon_lbl
        button._feature_title_label = title_lbl
        button._feature_desc_label = desc_lbl
        return button

    def populate_sidebar_buttons(self):
        for host in (self.feature_button_host, self.sidebar_button_host):
            while host.count():
                item = host.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
        self.sidebar_buttons = []
        for tool_definition in self.tool_definitions:
            is_featured = bool(tool_definition.get('featured'))
            if is_featured:
                button = self._create_feature_sidebar_button(tool_definition)
                host = self.feature_button_host
            else:
                icon = tool_definition.get('icon', '📄')
                title = tool_definition['menu_title']
                button = QPushButton(title)
                button.setObjectName('sidebarBtn')
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setEnabled(tool_definition['enabled'])
                button.setProperty('active', False)
                button.setProperty('featured', False)
                button.setProperty('nav_icon', icon)
                button.setProperty('nav_title', title)
                host = self.sidebar_button_host
            if tool_definition['enabled']:
                button.clicked.connect(partial(self.open_tool, tool_definition['key']))
            host.addWidget(button)
            self.sidebar_buttons.append(button)
        self.apply_sidebar_collapsed_state(self.sidebar_width < self.sidebar_expanded_width)

    def set_active_sidebar_button(self, tool_key):
        for tool_definition, button in zip(self.tool_definitions, self.sidebar_buttons):
            is_active = tool_definition['key'] == tool_key
            button.setProperty('active', is_active)
            button.style().unpolish(button)
            button.style().polish(button)
            title_lbl = getattr(button, '_feature_title_label', None)
            if title_lbl is not None:
                title_lbl.setProperty('active', is_active)
                title_lbl.style().unpolish(title_lbl)
                title_lbl.style().polish(title_lbl)
        self._set_active_nav(None if tool_key else self._active_view_key())

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
            color = theme_tokens(app_settings.get('ui/theme'))['selected']
            self.legend_caution_btn.setStyleSheet(
                f'QPushButton#headerLegendBtn {{ background-color: {color}; }}')
        else:
            self.legend_caution_btn.setStyleSheet('')
            self._refresh_brand_mark()
            self.refresh_sidebar_icons()

    def register_tools(self):
        tool_definitions = [
            {
                'key': 'pdf_compare',
                'menu_title': '영역지정비교',
                'menu_subtitle': '지정 영역 비교',
                'window_title': 'PDF 지정 영역 비교',
                'module_path': 'app.tools.pdf_compare',
                'class_name': 'PdfCompareWidget',
                'singleton': True,
                'enabled': True,
                'featured': True,
                'icon': '🔍',
            },
            {
                'key': 'pdf_hf_compare',
                'menu_title': '전체비교',
                'menu_subtitle': '페이지 전체 비교',
                'window_title': 'PDF 전체 비교',
                'module_path': 'app.tools.pdf_header_footer_compare',
                'class_name': 'HFCompareWidget',
                'singleton': True,
                'enabled': True,
                'featured': True,
                'icon': '📑',
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
            {
                'key': 'file_rename',
                'menu_title': '파일이름',
                'window_title': '파일 이름 관리',
                'module_path': 'app.tools.file_rename',
                'class_name': 'FileRenameWidget',
                'singleton': True,
                'enabled': True,
                'icon': '🏷️',
            },
            {
                'key': 'pdf_form',
                'menu_title': 'PDF 입력폼 관리',
                'window_title': 'PDF 입력폼 관리',
                'module_path': 'app.tools.pdf_form',
                'class_name': 'PdfFormWidget',
                'singleton': True,
                'enabled': True,
                'icon': '📋',
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

        # If the same tool is already active, just bring the tool host forward
        if self.current_tool_key == tool_key and self.current_tool_widget:
            self.mode_stack.setCurrentWidget(self.tool_container)
            self.set_active_sidebar_button(tool_key)
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
                # 비교 도구 전환 토글 연결 (영역지정비교 ↔ 전체비교)
                if tool_key in ('pdf_compare', 'pdf_hf_compare') and hasattr(new_tool, 'switch_toggle'):
                    toggle = new_tool.switch_toggle
                    toggle.buttons[0].setText(self.get_tool_definition('pdf_compare')['menu_title'])
                    toggle.buttons[1].setText(self.get_tool_definition('pdf_hf_compare')['menu_title'])
                    toggle.index_changed.connect(
                        lambda index: self.open_tool('pdf_compare' if index == 0 else 'pdf_hf_compare'))
                self.tool_cache[tool_key] = new_tool
                self.tool_container_layout.addWidget(new_tool)
                new_tool.ensurePolished()
                self.update_focus_button(new_tool)
            except Exception as e:
                QMessageBox.warning(self, 'Error', f'Failed to load tool: {e}')
                return
        else:
            new_tool = self.tool_cache[tool_key]
        self.tool_cache.move_to_end(tool_key)
        self._evict_tools(keep=tool_key)

        # Show the new tool
        self.mode_stack.setCurrentWidget(self.tool_container)
        new_tool.show()
        self.current_tool_widget = new_tool
        self.current_tool_key = tool_key
        self._refresh_tool_table_themes()

        # Update header and sidebar
        self.header_title.setText(tool_definition['window_title'])
        self.set_active_sidebar_button(tool_key)
        if hasattr(new_tool, 'switch_toggle'):
            new_tool.switch_toggle.set_active(0 if tool_key == 'pdf_compare' else 1)

    def close_current_tool(self):
        """현재 활성화된 도구 닫기"""
        if not self.current_tool_widget:
            return
        if hasattr(self.current_tool_widget, 'confirm_discard_changes'):
            if not self.current_tool_widget.confirm_discard_changes():
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

        # 헤더와 사이드바 초기화 → 뷰어(열린 문서가 있으면) 또는 시작 화면으로 복귀
        self.header_title.setText(APP_NAME)
        self.set_active_sidebar_button(None)
        if self.viewer.count():
            self.show_viewer()
        else:
            self.show_welcome()

    # ------------------------------------------------------------------
    # Viewer-first shell
    # ------------------------------------------------------------------
    def _evict_tools(self, keep=None):
        """LRU: keep at most TOOL_CACHE_MAX tool widgets; skip tools with unsaved changes."""
        for key in list(self.tool_cache):
            if len(self.tool_cache) <= self.tool_cache_max:
                break
            if key in (keep, self.current_tool_key):
                continue
            widget = self.tool_cache[key]
            # Tools that manage unsaved edits are never evicted silently.
            if hasattr(widget, 'confirm_discard_changes'):
                continue
            self.tool_cache.pop(key)
            widget.close()
            self.tool_container_layout.removeWidget(widget)
            widget.deleteLater()

    def _hide_current_tool(self):
        if self.current_tool_widget:
            self.current_tool_widget.hide()
        self.current_tool_key = None
        self.current_tool_widget = None
        self.set_active_sidebar_button(None)

    def _active_view_key(self):
        w = self.mode_stack.currentWidget() if hasattr(self, 'mode_stack') else None
        if w is self.welcome_page:
            return 'home'
        if w is self.viewer:
            return 'viewer'
        if self.split_view is not None and w is self.split_view:
            return 'split'
        if self.settings_page is not None and w is self.settings_page:
            return 'settings'
        return None

    def _set_active_nav(self, key):
        for k, b in self.nav_buttons.items():
            b.setProperty('active', k == key)
            b.style().unpolish(b)
            b.style().polish(b)
        self.refresh_sidebar_icons()

    def activate_view(self, key):
        if key == 'home':
            self.show_welcome()
        elif key == 'viewer':
            if self.viewer.count():
                self.show_viewer()
            else:
                self.open_pdf_dialog()
        elif key == 'split':
            self.open_split_view()
        elif key == 'settings':
            self.show_settings()

    # ---- settings (screen 7) --------------------------------------------------
    def apply_settings(self, key='*'):
        if key in ('*', 'ui/theme'):
            self.setStyleSheet(MODERN_QSS + build_shell_qss(app_settings.get('ui/theme')))
            # Local blink styles otherwise win over the new palette.
            self.legend_caution_btn.setStyleSheet('')
            self._refresh_brand_mark()
            self.refresh_sidebar_icons()
            self._refresh_tool_table_themes()
        self.tool_cache_max = max(1, app_settings.get('perf/tool_cache_max'))
        self.viewer.default_fit = app_settings.get('viewer/default_zoom')
        self.viewer.nav_default_visible = app_settings.get('viewer/show_nav')
        if key in ('*', 'viewer/show_nav'):
            self.viewer.set_nav_visible(self.viewer.nav_default_visible)
        if 'app.viewer.render_service' in __import__('sys').modules:
            from app.viewer.render_service import render_service
            render_service().configure(app_settings.get('perf/render_cache_mb'), app_settings.get('perf/render_threads'))
        if key in ('*', 'ui/auto_compact_sidebar'):
            self.sidebar_manual = None
            self.update_sidebar_compact()
        if key == 'perf/tool_cache_max':
            self._evict_tools(keep=self.current_tool_key)


    def _refresh_tool_table_themes(self):
        """Re-apply tool table header colors when the shell theme changes."""
        widgets = list(self.tool_cache.values())
        if self.current_tool_widget is not None and self.current_tool_widget not in widgets:
            widgets.append(self.current_tool_widget)
        for widget in widgets:
            for name in ('_style_file_table', '_style_table'):
                fn = getattr(widget, name, None)
                if callable(fn):
                    fn()
                    break

    def show_settings(self):
        if self.settings_page is None:
            from app.shell.settings_page import SettingsPage  # lazy
            self.settings_page = SettingsPage()
            self.settings_page.settings_changed.connect(self.apply_settings)
            self.settings_page.recent_cleared.connect(lambda: self.welcome_page.set_recent([]))
            self.mode_stack.addWidget(self.settings_page)
        else:
            self.settings_page.load()
        self._hide_current_tool()
        self.mode_stack.setCurrentWidget(self.settings_page)
        self.header_title.setText('설정')
        self._set_active_nav('settings')

    # ---- unified search / command palette ------------------------------------
    def show_global_search(self):
        if not self.viewer.count():
            return
        self.show_viewer()
        self.viewer.show_global_search()

    def _on_viewer_tool_request(self, key, path):
        if key == 'pdf_form' and path:
            self.open_form_for(path)
        elif key in ('pdf_compare', 'pdf_hf_compare') and path:
            paths = [path]
            others = [p for p in self.doc_manager.paths() if p != path]
            if others:
                from app.shell.open_doc_picker import pick_document
                second = pick_document(
                    self, self.doc_manager,
                    title='비교할 두 번째 PDF 선택',
                    exclude_paths=[path],
                )
                if second:
                    paths.append(second)
            self.open_tool(key)
            self._handoff_to_compare(paths)
        else:
            self.open_tool(key)

    def palette_commands(self):
        cmds = [
            {'title': 'PDF 열기', 'keywords': 'open 파일', 'shortcut': 'Ctrl+O', 'run': self.open_pdf_dialog},
            {'title': '홈 (시작 화면)', 'keywords': 'home welcome', 'run': self.show_welcome},
            {'title': 'PDF 보기', 'keywords': 'viewer 뷰어', 'run': lambda: self.activate_view('viewer')},
            {'title': '두 PDF 동시 보기', 'keywords': 'split 나란히 분할', 'run': self.open_split_view},
            {'title': '열린 PDF 전체에서 찾기', 'keywords': 'search 검색 통합', 'shortcut': 'Ctrl+Shift+F',
             'run': self.show_global_search},
            {'title': '문서에서 찾기', 'keywords': 'find 검색', 'shortcut': 'Ctrl+F',
             'run': lambda: (self.show_viewer(), self.viewer.show_search()) if self.viewer.count() else None},
            {'title': '문서 정보 패널', 'keywords': 'info 속성',
             'run': lambda: self._viewer_mode('info')},
            {'title': '편집 작업 패널', 'keywords': 'edit',
             'run': lambda: self._viewer_mode('edit')},
            {'title': '설정', 'keywords': 'settings 옵션 캐시 테마', 'shortcut': 'Ctrl+,', 'run': self.show_settings},
            {'title': '집중모드 전환', 'keywords': 'focus', 'run': self.toggle_sidebar},
            {'title': '사이드바 아이콘으로 줄이기/펼치기', 'keywords': 'sidebar compact', 'run': self.toggle_sidebar_compact},
            {'title': '지난 작업 복원', 'keywords': 'restore session', 'run': self.restore_session},
        ]
        for d in self.tool_definitions:
            if d['enabled']:
                cmds.append({'title': d['menu_title'], 'keywords': d['window_title'] + ' 도구',
                             'run': partial(self.open_tool, d['key'])})
        return cmds

    def _viewer_mode(self, mode):
        if self.viewer.count():
            self.show_viewer()
            self.viewer.open_work_mode(mode)

    def show_command_palette(self):
        from app.shell.command_palette import CommandPalette  # lazy
        dlg = CommandPalette(self.palette_commands(), self)
        g = self.geometry()
        dlg.move(g.x() + (g.width() - 520) // 2, g.y() + 80)
        self._palette = dlg
        dlg.exec()

    def show_welcome(self):
        self._hide_current_tool()
        self.welcome_page.set_recent(recent_docs.load_recent())
        self.welcome_page.set_restore_available(app_settings.get('workspace/offer_restore')
                                                and bool(workspace_session.load_session()) and not self.viewer.count())
        self.mode_stack.setCurrentWidget(self.welcome_page)
        self.header_title.setText(APP_NAME)
        self._set_active_nav('home')

    def show_viewer(self):
        self._hide_current_tool()
        self.mode_stack.setCurrentWidget(self.viewer)
        self._update_title(self.viewer.current_doc())
        self._set_active_nav('viewer')

    def _update_title(self, doc):
        if self.mode_stack.currentWidget() is self.viewer:
            self.header_title.setText(doc.title if doc else 'PDF 보기')
            self.setWindowTitle(f'{doc.title} — {APP_NAME}' if doc else f'{APP_NAME} v{VERSION}')

    def open_pdf_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'PDF 열기', '', 'PDF 파일 (*.pdf)')
        for p in paths:
            self.open_pdf(p)

    def open_pdf(self, path, page=0):
        if not path:
            return False
        if not os.path.isfile(path):
            QMessageBox.warning(self, 'PDF 열기', f'파일을 찾을 수 없습니다.\n{path}')
            recent_docs.remove_recent(path)
            self.welcome_page.set_recent(recent_docs.load_recent())
            return False
        try:
            doc, _ = self.doc_manager.open(path)
        except Exception as e:
            QMessageBox.warning(self, 'PDF 열기 실패', f'{os.path.basename(path)}\n{e}')
            return False
        recent_docs.add_recent(doc.path)
        if app_settings.get('viewer/open_mode') == 'replace' and self.viewer.count():
            self.viewer.replace_current(doc, page)
        else:
            self.viewer.add_document(doc, page)
        self.show_viewer()
        return True

    def _on_viewer_doc_closed(self, path):
        in_split = self.split_view is not None and path in self.split_view.paths()
        if not in_split:
            self.doc_manager.close(path)
        if not self.viewer.count() and self.mode_stack.currentWidget() is self.viewer:
            self.show_welcome()

    def restore_session(self):
        for e in workspace_session.load_session():
            self.open_pdf(e['path'], int(e.get('page', 0)))

    def _on_welcome_action(self, key):
        if key == 'split_view':
            self.open_split_view()
        else:
            self.open_tool(key)

    def open_split_view(self):
        created = self.split_view is None
        if created:
            from app.viewer.split_view import SplitView  # lazy
            self.split_view = SplitView(self.doc_manager)
            self.split_view.closed.connect(lambda: self.show_viewer() if self.viewer.count() else self.show_welcome())
            self.split_view.open_compare.connect(self._split_to_compare)
            self.mode_stack.addWidget(self.split_view)
            cur = self.viewer.current_doc()
            if cur:
                self.split_view.set_documents(left=cur)
        self._hide_current_tool()
        self.mode_stack.setCurrentWidget(self.split_view)
        self.header_title.setText('두 PDF 동시 보기')
        self._set_active_nav('split')
        # 왼쪽이 있고 오른쪽이 비었으며 다른 열린 탭이 있으면 피커를 한 번 연다
        if self.split_view.paths()[1] is None:
            left = self.split_view.paths()[0]
            others = [p for p in self.doc_manager.paths() if p != left]
            if left and others:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, self._prompt_split_right)

    def _prompt_split_right(self):
        if self.split_view is None or self.split_view.paths()[1] is not None:
            return
        left = self.split_view.paths()[0]
        others = [p for p in self.doc_manager.paths() if p != left]
        if not (left and others):
            return
        from app.shell.open_doc_picker import pick_document
        path = pick_document(self, self.doc_manager, title='오른쪽 문서 선택')
        if not path:
            return
        try:
            doc, _ = self.doc_manager.open(path)
        except Exception as e:
            QMessageBox.warning(self, 'PDF 열기 실패', str(e))
            return
        self.split_view.set_documents(right=doc)

    def _split_to_compare(self, tool_key):
        paths = self.split_view.paths() if self.split_view else []
        self.open_tool(tool_key)
        self._handoff_to_compare(paths)

    def _handoff_to_compare(self, paths):
        """Best-effort: load already-open PDFs into the existing compare tool's two viewers."""
        tool = self.current_tool_widget
        for viewer_attr, path in zip(('viewer1', 'viewer2'), paths):
            viewer = getattr(tool, viewer_attr, None)
            if not path or viewer is None or not hasattr(viewer, 'load_pdf'):
                continue
            try:
                if viewer.load_pdf(path) and hasattr(viewer, 'update_loaded_pdf_label'):
                    viewer.update_loaded_pdf_label(path)
            except Exception:
                pass

    def open_form_for(self, path):
        self.open_tool('pdf_form')
        tool = self.tool_cache.get('pdf_form')
        if tool is not None and hasattr(tool, 'load_pdf'):
            try:
                tool.load_pdf(path)
            except Exception as e:
                QMessageBox.warning(self, 'PDF 입력폼 관리', str(e))

    # drag & drop -----------------------------------------------------
    def dragEnterEvent(self, event):
        if any(u.toLocalFile().lower().endswith('.pdf') for u in event.mimeData().urls()):
            if self.mode_stack.currentWidget() is self.welcome_page:
                self.welcome_page._set_drag_active(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        if hasattr(self, 'welcome_page'):
            self.welcome_page._set_drag_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if hasattr(self, 'welcome_page'):
            self.welcome_page._set_drag_active(False)
        if self.current_tool_widget is not None:
            return  # existing tools handle their own drops
        for u in event.mimeData().urls():
            p = u.toLocalFile()
            if p.lower().endswith('.pdf'):
                self.open_pdf(p)

    def show_legend_caution_for_active_tool(self):
        # Find the active PDF compare widget
        if self.current_tool_key in ('pdf_compare', 'pdf_hf_compare') and self.current_tool_widget:
            if hasattr(self.current_tool_widget, 'show_legend_caution_dialog'):
                self.current_tool_widget.show_legend_caution_dialog()

    def show_info(self):
        AboutDialog(get_about_info(), self).exec()

    def closeEvent(self, event):
        """애플리케이션 종료 시 모든 스레드 정리 (좀비 프로세스 방지)"""
        for tool in self.tool_cache.values():
            if hasattr(tool, 'confirm_discard_changes') and not tool.confirm_discard_changes():
                event.ignore()
                return
        # 현재 활성화된 도구의 스레드 정리
        if self.current_tool_widget:
            self.current_tool_widget.close()
        
        # 캐시된 모든 도구 위젯의 스레드 정리
        for tool_widget in self.tool_cache.values():
            tool_widget.close()
        
        try:
            workspace_session.save_session(self.viewer.session_entries())
        except Exception:
            pass
        self.doc_manager.close_all()
        if 'app.viewer.render_service' in __import__('sys').modules:
            from app.viewer.render_service import reset_render_service
            reset_render_service()

        # 이벤트 수락 (창 닫기 진행)
        event.accept()


def _close_splash_screen():
    """PyInstaller --splash 스플래시 화면을 닫는다 (개발 모드에서는 무시)."""
    try:
        import pyi_splash
        if pyi_splash.is_alive():
            pyi_splash.close()
    except ImportError:
        pass


def run():
    app = QApplication.instance() or QApplication([])
    app.setFont(QFont('Malgun Gothic', 10))
    translator = QTranslator(app)
    if translator.load(QLocale(QLocale.Language.Korean), "qtbase", "_",
                       QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    window = MdiMainWindow()
    window.show()
    _close_splash_screen()
    return app.exec()
