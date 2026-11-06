"""Selectable shell palettes (default: warm greige + terracotta).

Append generated QSS after MODERN_QSS. Tool-local styles stay independent.
"""
TOKENS = {
    'app_bg': '#F5F2F0',
    'sidebar_bg': '#F3F0ED',
    'sidebar_border': '#E2DED9',
    'sidebar_text': '#5C5550',
    'sidebar_icon': '#8A827A',
    'sidebar_group': '#A39B93',
    'sidebar_active_bg': 'rgba(164, 71, 53, 0.08)',
    'brand_bg': '#FBFAF9',
    'brand_border': '#E2DED9',
    'brand_title': '#292D33',
    'brand_subtitle': '#77706D',
    'feature_bg': '#F9F1EE',
    'feature_border': '#DEC2B9',
    'feature_hover': '#F3E4DF',
    'feature_selected': '#EDDAD3',
    'feature_icon_bg': 'rgba(164, 71, 53, 0.12)',
    'card_bg': '#FBFAF9',
    'card_border': '#DED8D5',
    'card_hover': '#F3ECE9',
    'canvas_bg': '#E7E3DF',
    'panel_bg': '#FBFAF9',
    'text': '#292D33',
    'text_muted': '#77706D',
    'accent': '#A44735',
    'accent_hover': '#873729',
    'accent_subtle': 'rgba(164, 71, 53, 0.12)',
    'on_accent': '#FFFFFF',
    'selected': '#F5EAE6',
    'hover': '#EFEAE7',
    'warning_bg': '#FFF4E0',
    'border': '#DED8D5',
    'radius': '6px',
    'toolbar_h': '36px',
}

THEME_CHOICES = [('default', '기본'), ('energy', '역동'), ('silver', '실버'),
                 ('gold', '골드'), ('black', '블랙')]

# Keep the original TOKENS intact; only UI chrome, never official logos or PDF
# page content, uses these palettes.
THEMES = {
    'default': dict(TOKENS),
    'energy': dict(TOKENS, sidebar_active_bg='rgba(255, 72, 5, 0.08)', sidebar_border='#DED9D3', app_bg='#F7F5F2', sidebar_bg='#ECE9E5',
                   brand_bg='#FCFBF9', brand_border='#DED9D3', brand_title='#292D33', brand_subtitle='#77706D',
                   feature_bg='#FFF3EC', feature_border='#F3C3AD', feature_hover='#FFE8DB',
                   feature_selected='#FFDFCF', feature_icon_bg='rgba(255, 72, 5, 0.12)',
                   card_bg='#FCFBF9', card_border='#DED9D3', card_hover='#F6EFEA',
                   panel_bg='#FCFBF9', accent='#FF4805', accent_hover='#D83B00',
                   accent_subtle='rgba(255, 72, 5, 0.12)',
                   on_accent='#FFFFFF',
                   selected='#FFF0E6', hover='#F2EBE5', border='#DED9D3'),
    'silver': dict(TOKENS, sidebar_active_bg='rgba(83, 101, 119, 0.12)', sidebar_border='#C5CCD3',
                   sidebar_text='#3E4750', sidebar_icon='#6F7A85', sidebar_group='#7D8792', app_bg='#F1F3F5', sidebar_bg='#DDE1E5',
                   brand_bg='#F5F7F9', brand_border='#C5CCD3', brand_title='#252B32', brand_subtitle='#626D78',
                   feature_bg='#E9EEF3', feature_border='#AFC0D0', feature_hover='#DFE7EF',
                   feature_selected='#D5E0EB', feature_icon_bg='rgba(83, 101, 119, 0.15)',
                   card_bg='#FAFBFC', card_border='#C5CCD3', card_hover='#EDF1F5',
                   canvas_bg='#D7DCE1', panel_bg='#FAFBFC', text='#252B32',
                   text_muted='#626D78', accent='#536577', accent_hover='#3F5061',
                   accent_subtle='rgba(83, 101, 119, 0.14)',
                   on_accent='#FFFFFF',
                   selected='#E1E7EE', hover='#E9EDF1', warning_bg='#F0EDE4',
                   border='#C5CCD3'),
    'gold': dict(TOKENS, sidebar_active_bg='rgba(128, 99, 45, 0.12)', sidebar_border='#D5C9AB',
                 sidebar_text='#4A4232', sidebar_icon='#857859', sidebar_group='#968A6D', app_bg='#F6F3EB', sidebar_bg='#E7DFC9',
                 brand_bg='#F8F5EC', brand_border='#D5C9AB', brand_title='#342F25', brand_subtitle='#786D55',
                 feature_bg='#F3ECDA', feature_border='#C7B487', feature_hover='#ECE2C8',
                 feature_selected='#E5D8B6', feature_icon_bg='rgba(128, 99, 45, 0.15)',
                 card_bg='#FCFAF4', card_border='#D5C9AB', card_hover='#F4EFE0',
                 canvas_bg='#E3DDCF', panel_bg='#FCFAF4', text='#342F25',
                 text_muted='#786D55', accent='#80632D', accent_hover='#644C20',
                 accent_subtle='rgba(128, 99, 45, 0.14)',
                 selected='#EFE4C8', hover='#F0EBDD', warning_bg='#F6EBCF',
                 on_accent='#FFFFFF',
                 border='#D5C9AB'),
    'black': dict(TOKENS, sidebar_active_bg='rgba(175, 196, 218, 0.14)', sidebar_border='#2E3036',
                  sidebar_text='#D2D5DB', sidebar_icon='#9AA0AA', sidebar_group='#7E848E', app_bg='#202124', sidebar_bg='#17181B',
                  brand_bg='#202227', brand_border='#2E3036', brand_title='#ECEEF2', brand_subtitle='#9AA0AA',
                  feature_bg='#22262E', feature_border='#4A586B', feature_hover='#2B313C',
                  feature_selected='#323B49', feature_icon_bg='rgba(175, 196, 218, 0.16)',
                  card_bg='#292B30', card_border='#3C4048', card_hover='#32363E',
                  canvas_bg='#111214', panel_bg='#292B30', text='#ECEEF2',
                  text_muted='#ADB2BC', accent='#AFC4DA', accent_hover='#CDDEEF',
                  accent_subtle='rgba(175, 196, 218, 0.16)',
                  on_accent='#202124', selected='#384452', hover='#34373D', warning_bg='#433B29',
                  border='#484C54'),
}


def theme_tokens(theme_id='default'):
    """Return an independent palette; unknown saved IDs use the default."""
    return dict(THEMES.get(theme_id, THEMES['default']))


_SHELL_TEMPLATE = """
QWidget#welcomePage {{ background: {app_bg}; }}
QLabel#welcomeTitle {{ font-size: 22px; font-weight: 700; color: {text}; letter-spacing: -0.3px; }}
QLabel#sectionLabel {{ font-size: 12px; font-weight: 700; color: {text_muted}; margin-top: 8px; letter-spacing: 0.3px; }}
QLabel#mutedLabel {{ color: {text_muted}; font-size: 12px; }}
QFrame#dropZone {{ background: {card_bg}; border: 1.5px dashed {card_border}; border-radius: 10px; }}
QFrame#dropZone[dragActive='true'] {{ background: {selected}; border: 1.5px solid {accent}; }}
QPushButton#primaryBtn {{ background: {accent}; color: {on_accent}; border: 1px solid {accent}; border-radius: {radius};
    padding: 7px 18px; font-weight: 600; font-size: 13px; }}
QPushButton#primaryBtn:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton#shortcutTile {{ background: {card_bg}; border: 1px solid {card_border}; border-radius: 8px;
    padding: 10px 12px; text-align: left; color: {text}; min-height: 56px; }}
QPushButton#shortcutTile:hover {{ background: {card_hover}; border-color: {accent}; }}
QPushButton#shortcutTile:focus {{ border: 1.5px solid {accent}; }}
QPushButton#shortcutTile[featured='true'] {{ background: {feature_bg}; border: 1px solid {feature_border}; min-height: 60px; }}
QPushButton#shortcutTile[featured='true']:hover {{ background: {feature_hover}; border-color: {accent}; }}
QPushButton#shortcutTile[featured='true']:focus {{ border: 1.5px solid {accent}; }}
QLabel#shortcutTileTitle {{ color: {text}; font-size: 13px; font-weight: 700; background: transparent; }}
QLabel#shortcutTileTitle[featured='true'] {{ color: {accent}; font-size: 13px; font-weight: 700; background: transparent; }}
QLabel#shortcutTileDesc {{ color: {text_muted}; font-size: 11px; font-weight: 400; background: transparent; }}
QLabel#shortcutTileIcon {{ background: {accent_subtle}; border-radius: 6px; }}
QListWidget#recentList {{ background: {card_bg}; border: 1px solid {card_border}; border-radius: 8px; padding: 4px; outline: none; }}
QListWidget#recentList::item {{ padding: 6px 8px; border-radius: 5px; border: 1px solid transparent; }}
QListWidget#recentList::item:hover {{ background: {hover}; }}
QListWidget#recentList::item:selected {{ background: {selected}; color: {accent}; border: 1px solid {feature_border}; }}
QLabel#recentItemTitle {{ color: {text}; font-size: 12px; font-weight: 600; background: transparent; }}
QLabel#recentItemPath {{ color: {text_muted}; font-size: 11px; background: transparent; }}
QTabBar#docTabs {{ background: {sidebar_bg}; }}
QTabBar#docTabs::tab {{ background: transparent; padding: 6px 12px; border: none; max-width: 220px;
    color: {text_muted}; }}
QTabBar#docTabs::tab:selected {{ background: {panel_bg}; color: {text}; border-top: 2px solid {accent}; }}
QTabBar#docTabs::tab:hover {{ background: {hover}; }}
QFrame#viewerToolbar, QFrame#contextToolbar, QFrame#splitPaneBar {{ background: {panel_bg};
    border-bottom: 1px solid {border}; }}
QLabel#contextTitle, QLabel#splitPaneTitle {{ font-weight: 600; color: {text}; }}
QPushButton#viewerToolBtn {{ background: transparent; border: 1px solid transparent; border-radius: {radius};
    padding: 4px 8px; min-height: 22px; color: {text}; }}
QPushButton#viewerToolBtn:hover {{ background: {hover}; border-color: {border}; }}
QPushButton#openPdfTabBtn {{ background: {accent}; color: {on_accent}; border: 1px solid {accent};
    border-radius: {radius}; padding: 4px 12px; min-height: 24px; font-weight: 700; }}
QPushButton#openPdfTabBtn:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QLineEdit#pageEdit {{ padding: 2px; }}
QListWidget#navPanel {{ background: {sidebar_bg}; border: none; border-right: 1px solid {border}; }}
QListWidget#navPanel::item:selected {{ background: {selected}; color: {accent}; }}
QFrame#formBanner {{ background: {warning_bg}; border-bottom: 1px solid {border}; }}
QLabel#sidebarGroupLabel {{ color: {text_muted}; font-size: 11px; font-weight: 600; padding: 8px 4px 2px 4px; }}
QPushButton#viewerToolBtn:checked {{ background: {selected}; border-color: {accent}; color: {accent}; }}
QFrame#workPanel, QFrame#globalSearchPanel {{ background: {panel_bg}; border-left: 1px solid {border}; }}
QWidget#settingsPage {{ background: {app_bg}; }}
QDialog#commandPalette {{ background: {panel_bg}; border: 1px solid {border}; border-radius: 8px; }}
QDialog#commandPalette QListWidget {{ border: none; }}
QDialog#commandPalette QListWidget::item:selected {{ background: {selected}; color: {accent}; }}
QWidget#docTabRow {{ background: {sidebar_bg}; }}
QDialog#openDocPicker {{ background: {panel_bg}; }}
QListWidget#openDocList {{ background: {panel_bg}; border: 1px solid {border}; border-radius: {radius}; }}
QListWidget#openDocList::item {{ padding: 6px 8px; border-radius: 4px; }}
QListWidget#openDocList::item:selected {{ background: {selected}; color: {accent}; }}
QListWidget#openDocList::item:hover {{ background: {hover}; }}
"""


# Explicit ID/state selectors win over the legacy warm sidebar/header rules.
_CHROME_TEMPLATE = """
QWidget {{ color: {text}; background-color: {app_bg}; }}
QMainWindow, QDialog, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {app_bg}; }}
QLabel, QCheckBox, QRadioButton {{ background: transparent; color: {text}; }}
QWidget:disabled {{ color: {text_muted}; }}
QFrame#sidebar {{ background: {sidebar_bg}; border: none; border-right: 1px solid {sidebar_border}; }}
QScrollArea#sidebarScroll, QScrollArea#sidebarScroll > QWidget > QWidget, QWidget#sidebarScrollBody {{
    background: transparent; border: none;
}}
QFrame#sidebar QLabel, QFrame#sidebarFooter {{ background: transparent; }}
QFrame#sidebarLogoCard {{
    background: {brand_bg}; border: 1px solid {brand_border}; border-radius: 8px;
}}
QFrame#sidebarLogoCard[collapsed='true'] {{
    background: transparent; border: none;
}}
QFrame#sidebarDivider {{ background: {sidebar_border}; border: none; max-height: 1px; min-height: 1px; }}
QFrame#sidebarFooter {{ border: none; border-top: 1px solid {sidebar_border}; }}
QLabel#sidebarBrandTitle {{ color: {brand_title}; font-size: 14px; font-weight: 700; letter-spacing: -0.2px; }}
QLabel#sidebarBrandSubtitle {{ color: {brand_subtitle}; font-size: 11px; font-weight: 500; }}
QPushButton#hamburgerBtn {{ color: {accent}; }}
QLabel#headerTarget {{ color: {text_muted}; }}
QLabel#sidebarGroupLabel {{ color: {sidebar_group}; font-size: 10px; font-weight: 700; letter-spacing: 0.8px; padding: 10px 8px 3px 8px; }}
QPushButton#sidebarBtn {{ color: {sidebar_text}; background: transparent; border: 1px solid transparent; border-left: 2px solid transparent;
    border-radius: 6px; padding: 0 10px; min-height: 34px; max-height: 34px; text-align: left; font-size: 13px; font-weight: 500; }}
QPushButton#sidebarBtn[collapsed='true'] {{ padding: 0; text-align: center; color: {sidebar_text}; min-height: 36px; max-height: 36px; }}
QPushButton#sidebarBtn:hover {{ background: {hover}; color: {text}; }}
QPushButton#sidebarBtn:focus {{ border-color: {accent}; }}
QPushButton#sidebarBtn[active='true'] {{ background: {sidebar_active_bg}; color: {accent}; border-left: 2px solid {accent};
    border-top-left-radius: 0; border-bottom-left-radius: 0; font-weight: 600; }}
QPushButton#sidebarFeatureBtn {{
    color: {text}; background: {feature_bg}; border: 1px solid {feature_border};
    border-left: 3px solid {accent}; border-radius: 7px; padding: 6px 10px;
    min-height: 46px; max-height: 52px; text-align: left;
}}
QPushButton#sidebarFeatureBtn:hover {{
    background: {feature_hover}; border-color: {accent}; border-left: 3px solid {accent};
}}
QPushButton#sidebarFeatureBtn:focus {{
    border: 1.5px solid {accent}; border-left: 3px solid {accent};
}}
QPushButton#sidebarFeatureBtn[active='true'] {{
    background: {feature_selected}; color: {accent}; border: 1px solid {accent};
    border-left: 3px solid {accent}; font-weight: 700;
}}
QPushButton#sidebarFeatureBtn[collapsed='true'] {{
    padding: 0; text-align: center; min-height: 40px; max-height: 40px;
    border-left: 2px solid {accent};
}}
QPushButton#sidebarFeatureBtn:disabled {{
    background: {sidebar_bg}; color: {text_muted}; border-color: {sidebar_border};
}}
QLabel#sidebarFeatureTitle {{ color: {text}; font-size: 13px; font-weight: 700; background: transparent; }}
QLabel#sidebarFeatureTitle[active='true'] {{ color: {accent}; font-weight: 700; }}
QLabel#sidebarFeatureDesc {{ color: {text_muted}; font-size: 11px; font-weight: 400; background: transparent; }}
QLabel#sidebarFeatureIcon {{ background: {feature_icon_bg}; border-radius: 5px; }}
QFrame#headerBar {{ background: {app_bg}; border-bottom: 1px solid {border}; }}
QLabel#headerTitle {{ color: {text}; }}
QFrame#headerAccent {{ background: {accent}; }}
QPushButton#headerLegendBtn, QPushButton#headerFocusBtn {{ background: {panel_bg}; color: {accent}; border-color: {border}; }}
QPushButton#headerLegendBtn:hover, QPushButton#headerLegendBtn:pressed,
QPushButton#headerFocusBtn:hover, QPushButton#headerFocusBtn:checked {{ background: {selected}; color: {accent}; border-color: {accent}; }}
QPushButton#headerLegendBtn:disabled {{ background: {app_bg}; color: {text_muted}; border-color: {border}; }}
#infoBtn, #closeToolBtn {{ color: {text_muted}; }}
#infoBtn:hover, #infoBtn:pressed, #closeToolBtn:hover, #closeToolBtn:pressed,
QPushButton#hamburgerBtn:hover, QPushButton#hamburgerBtn:pressed {{ background: {hover}; }}
QPushButton {{ background: {panel_bg}; color: {text}; border-color: {border}; }}
QPushButton:hover, QPushButton:pressed {{ background: {hover}; color: {text}; border-color: {border}; }}
QPushButton:disabled {{ color: {text_muted}; background: {sidebar_bg}; }}
QPushButton#primaryBtn, QPushButton#primaryBtn:hover {{ color: {on_accent}; }}
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit,
QListWidget, QTreeWidget, QComboBox QAbstractItemView {{
    background: {panel_bg}; color: {text}; border: 1px solid {border};
    selection-background-color: {selected}; selection-color: {text};
}}
QLineEdit, QSpinBox, QComboBox {{ border-radius: {radius}; padding: 4px 6px; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {accent}; }}
QListWidget#navPanel::item {{ color: {text}; }}
QListWidget#navPanel::item:hover {{ background: {hover}; }}
QListWidget#navPanel::item:selected {{ background: {selected}; color: {accent}; border-color: {accent}; }}
QListWidget#recentList::item:selected {{ background: {selected}; color: {accent}; }}
QCheckBox::indicator, QRadioButton::indicator {{ background: {panel_bg}; border: 1px solid {border}; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QToolTip {{ background: {panel_bg}; color: {text}; border: 1px solid {border}; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: {text_muted}; border-radius: 3px; }}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: {accent}; }}
QSplitter::handle {{ background: {border}; }}
QHeaderView::section {{
    background-color: {accent}; color: {on_accent}; font-weight: 600; border: none;
    border-right: 1px solid {accent_hover}; border-bottom: 2px solid {accent_hover}; padding: 6px 8px;
}}
"""


_NON_DEFAULT_CHROME_TEMPLATE = """
QPushButton {{
    background-color: {panel_bg}; color: {accent}; border: 1px solid {border};
}}
QPushButton:hover, QPushButton:pressed {{
    background-color: {selected}; color: {accent_hover}; border-color: {accent};
}}
QPushButton:checked {{
    background-color: {selected}; color: {accent}; border: 1px solid {accent}; font-weight: 600;
}}
QPushButton:disabled {{
    background-color: {sidebar_bg}; color: {text_muted}; border-color: {border};
}}
QPushButton#primaryBtn,
QPushButton#actionBtn,
QPushButton#compareBtn,
QPushButton#compareActionBtn,
QPushButton#pdfOpenButton {{
    background-color: {accent}; color: {on_accent}; border: 1px solid {accent};
}}
QPushButton#primaryBtn:hover, QPushButton#primaryBtn:pressed,
QPushButton#actionBtn:hover, QPushButton#actionBtn:pressed,
QPushButton#compareBtn:hover, QPushButton#compareBtn:pressed,
QPushButton#compareActionBtn:hover, QPushButton#compareActionBtn:pressed,
QPushButton#pdfOpenButton:hover, QPushButton#pdfOpenButton:pressed {{
    background-color: {accent_hover}; color: {on_accent}; border-color: {accent_hover};
}}
QPushButton#primaryBtn:disabled,
QPushButton#actionBtn:disabled,
QPushButton#compareBtn:disabled,
QPushButton#compareActionBtn:disabled,
QPushButton#pdfOpenButton:disabled {{
    background-color: {sidebar_bg}; color: {text_muted}; border-color: {border};
}}
QPushButton#secondaryBtn {{
    background-color: {panel_bg}; color: {accent}; border: 1px solid {accent};
}}
QPushButton#secondaryBtn:hover,
QPushButton#secondaryBtn:pressed,
QPushButton#secondaryBtn:checked {{
    background-color: {selected}; color: {accent_hover}; border-color: {accent_hover};
}}
QPushButton#secondaryBtn:disabled {{
    background-color: {sidebar_bg}; color: {text_muted}; border-color: {border};
}}
QPushButton#compareUtilityBtn {{
    background-color: {panel_bg}; color: {accent}; border: 1px solid {border};
}}
QPushButton#compareUtilityBtn:hover,
QPushButton#compareUtilityBtn:pressed {{
    background-color: {selected}; color: {accent_hover}; border-color: {accent};
}}
QPushButton#compareUtilityBtn:disabled {{
    background-color: {sidebar_bg}; color: {text_muted}; border-color: {border};
}}
#toolbarBtn, QPushButton#toolbarBtn {{
    background-color: {panel_bg}; color: {accent}; border: 1px solid {border};
}}
#toolbarBtn:hover, #toolbarBtn:pressed, #toolbarBtn:checked,
QPushButton#toolbarBtn:hover, QPushButton#toolbarBtn:pressed, QPushButton#toolbarBtn:checked {{
    background-color: {selected}; color: {accent_hover}; border-color: {accent};
}}
#toolbarBtn:disabled, QPushButton#toolbarBtn:disabled {{
    background-color: {sidebar_bg}; color: {text_muted}; border-color: {border};
}}
QPushButton#viewerToolBtn {{
    background-color: {panel_bg}; color: {accent}; border: 1px solid {border};
}}
QPushButton#viewerToolBtn:hover, QPushButton#viewerToolBtn:pressed, QPushButton#viewerToolBtn:checked {{
    background-color: {selected}; color: {accent_hover}; border-color: {accent};
}}
QFrame#toolToggle {{
    background-color: {sidebar_bg}; border: 1px solid {border}; border-radius: 12px;
}}
QLabel#toolToggleCaption {{
    color: {accent}; font-size: 11px; font-weight: 700; padding: 0 4px 0 6px; background: transparent;
}}
QFrame#toolToggle QPushButton#toolToggleBtn {{
    background-color: transparent; border: none; border-radius: 8px;
    color: {text_muted}; font-size: 12px; font-weight: 500; padding: 4px 12px; min-height: 22px;
}}
QFrame#toolToggle QPushButton#toolToggleBtn:hover {{
    background-color: {hover}; color: {text};
}}
QFrame#toolToggle QPushButton#toolToggleBtn:checked {{
    background-color: {accent}; color: {on_accent}; font-weight: 700;
}}
#pdfToolbar, QFrame#actionBar {{
    background-color: {panel_bg}; border-color: {border};
}}
#toolbarLabel {{ color: {text_muted}; }}
#toolbarSearch {{
    background-color: {app_bg}; color: {text}; border: 1px solid {border};
}}
#toolbarSearch:focus {{
    border-color: {accent}; background-color: {panel_bg};
}}
QLabel#hfInstruction {{
    background-color: {selected}; color: {text}; border: 1px solid {border};
}}
QTabWidget::pane {{
    border: 1px solid {border}; background: {panel_bg}; border-radius: 6px;
}}
QTabBar::tab {{
    background: {sidebar_bg}; color: {text_muted}; border: 1px solid {border};
    border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px;
    padding: 6px 12px; margin-right: 2px;
}}
QTabBar::tab:hover {{
    background: {hover}; color: {text};
}}
QTabBar::tab:selected {{
    background: {panel_bg}; color: {accent}; border-color: {border};
    border-top: 2px solid {accent}; font-weight: 600;
}}
QTableWidget, QTableView {{
    background-color: {panel_bg}; color: {text}; gridline-color: {border};
    border: 1px solid {border}; selection-background-color: {selected}; selection-color: {text};
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {selected}; color: {text};
}}
QHeaderView {{
    background-color: {accent}; border: none;
}}
QTableCornerButton::section {{
    background-color: {accent}; border: none;
}}
QHeaderView QCheckBox::indicator {{
    background-color: {panel_bg}; border: 1.5px solid {on_accent};
}}
QHeaderView QCheckBox::indicator:checked {{
    background-color: {accent_hover}; border: 1.5px solid {on_accent};
}}
QHeaderView QCheckBox::indicator:indeterminate {{
    background-color: {selected}; border: 1.5px solid {on_accent};
}}
QProgressBar {{
    border: 1px solid {border}; border-radius: 6px; background: {sidebar_bg};
    text-align: center; color: {text};
}}
QProgressBar::chunk {{
    background-color: {accent}; border-radius: 5px;
}}
"""


def header_section_qss(theme_id='default'):
    """QHeaderView::section colors for the active shell theme (tool tables)."""
    tokens = theme_tokens(theme_id)
    on_accent = '#202124' if theme_id in ('energy', 'black') else '#FFFFFF'
    return (
        f"QHeaderView {{ background-color: {tokens['accent']}; border: none; }} "
        'QHeaderView::section {'
        f" background-color: {tokens['accent']}; color: {on_accent}; font-weight: 600;"
        ' border: none;'
        f" border-right: 1px solid {tokens['accent_hover']};"
        f" border-bottom: 2px solid {tokens['accent_hover']};"
        ' padding: 6px 8px; } '
        f"QTableCornerButton::section {{ background-color: {tokens['accent']}; border: none; }}"
    )


def tool_table_qss(theme_id='default', selectable=True):
    """Complete QTableWidget + QHeaderView + QCheckBox stylesheet for tool grids."""
    header = header_section_qss(theme_id)
    if theme_id not in THEMES or theme_id == 'default':
        sel_bg = '#FFF8F2' if selectable else 'transparent'
        return f"""
            QTableWidget {{
                background: white;
                border: 1px solid #D1D1D6;
                outline: none;
                selection-background-color: {sel_bg};
                selection-color: #1C1C1E;
            }}
            QTableWidget::item {{
                border: none;
                padding: 2px 4px;
            }}
            QTableWidget::item:selected {{
                background-color: {sel_bg};
                color: #1C1C1E;
            }}
            {header}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1.5px solid #C6C6C8;
                border-radius: 5px;
                background: white;
            }}
            QCheckBox::indicator:checked {{
                background: #FF6B00;
                border: 1.5px solid #FF6B00;
            }}
            QCheckBox::indicator:indeterminate {{
                background: rgba(255, 107, 0, 0.35);
                border: 1.5px solid #FF6B00;
            }}
        """
    tokens = theme_tokens(theme_id)
    on_accent = '#202124' if theme_id in ('energy', 'black') else '#FFFFFF'
    sel_bg = tokens['selected'] if selectable else 'transparent'
    return f"""
        QTableWidget {{
            background: {tokens['panel_bg']};
            color: {tokens['text']};
            gridline-color: {tokens['border']};
            border: 1px solid {tokens['border']};
            outline: none;
            selection-background-color: {sel_bg};
            selection-color: {tokens['text']};
        }}
        QTableWidget::item {{
            border: none;
            padding: 2px 4px;
        }}
        QTableWidget::item:selected {{
            background-color: {sel_bg};
            color: {tokens['text']};
        }}
        {header}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1.5px solid {tokens['border']};
            border-radius: 5px;
            background: {tokens['panel_bg']};
        }}
        QCheckBox::indicator:checked {{
            background: {tokens['accent']};
            border: 1.5px solid {tokens['accent_hover']};
        }}
        QCheckBox::indicator:indeterminate {{
            background: {tokens['selected']};
            border: 1.5px solid {tokens['accent']};
        }}
        QHeaderView QCheckBox::indicator {{
            background: {tokens['panel_bg']};
            border: 1.5px solid {on_accent};
        }}
        QHeaderView QCheckBox::indicator:checked {{
            background: {tokens['accent_hover']};
            border: 1.5px solid {on_accent};
        }}
        QHeaderView QCheckBox::indicator:indeterminate {{
            background: {tokens['selected']};
            border: 1.5px solid {on_accent};
        }}
    """


def build_shell_qss(theme_id='default'):
    tokens = theme_tokens(theme_id)
    # Dark text has better small-label contrast on bright energy orange.
    tokens['on_accent'] = '#202124' if theme_id in ('energy', 'black') else '#FFFFFF'
    qss = (_SHELL_TEMPLATE + _CHROME_TEMPLATE).format(**tokens)
    if theme_id in THEMES and theme_id != 'default':
        qss += _NON_DEFAULT_CHROME_TEMPLATE.format(**tokens)
    return qss


SHELL_QSS = build_shell_qss()  # compatibility for existing imports
