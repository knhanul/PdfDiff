from PyQt6.QtGui import QColor
from app.common.resources import THEME_COLOR_PRIMARY

COLOR_PRIMARY = THEME_COLOR_PRIMARY
COLOR_SECONDARY = '#FF6D00'
COLOR_SIDEBAR_BG = '#FFF4E6'
COLOR_HEADER_BG = '#FFFFFF'
COLOR_MDI_BG = '#F2F2F7'
COLOR_WORKSPACE_DARK = '#2A1F18'  # warm dark brown for PDF viewers
COLOR_TEXT_PRIMARY = '#1C1C1E'
COLOR_TEXT_SECONDARY = '#3C3C43'
COLOR_TEXT_MUTED = '#8E8E93'
COLOR_BORDER = '#D1D1D6'
COLOR_BORDER_LIGHT = '#E5E5EA'
COLOR_HOVER = '#E8E8ED'
COLOR_ACTIVE = '#D1D1D6'

COLOR_P1 = QColor(255, 149, 0, 140)  # Orange for PDF1
COLOR_P2 = QColor(0, 255, 127, 140)  # Green for PDF2
COLOR_AREA = QColor(255, 107, 0, 20)  # Orange area highlight

# POSID Orange brand colors (Yellow + Red)
_PRIMARY = '#FF6B00'
_PRIMARY_HOVER = '#E65C00'
_PRIMARY_PRESSED = '#CC5200'
_PRIMARY_LIGHT = 'rgba(255, 107, 0, 0.08)'
_PRIMARY_LIGHT_STRONG = 'rgba(255, 107, 0, 0.15)'
_PRIMARY_SELECTION = 'rgba(255, 107, 0, 0.25)'
_SIDEBAR_BG = '#EAE7E4'          # warm greige background
_SIDEBAR_BORDER = '#DCD5D0'      # soft warm gray border
_SIDEBAR_TEXT = '#55504D'        # deep gray for unselected menu text
_SIDEBAR_HOVER = '#DCD5D0'       # light warm gray hover
_SIDEBAR_ACTIVE_BG = '#A63F2B'   # deep terracotta for selected menu

_IOS_GREEN = '#34C759'
_IOS_ORANGE = '#FF9500'
_IOS_ORANGE_HOVER = '#E68600'
_IOS_ORANGE_PRESSED = '#CC7700'
_IOS_RED = '#FF3B30'
_IOS_GRAY_BG = '#F2F2F7'
_IOS_GROUPED_BG = '#FFFFFF'
_IOS_SEPARATOR = '#C6C6C8'
_IOS_FILL = '#E5E5EA'

MODERN_QSS = f"""
QWidget {{
    font-family: 'Segoe UI', 'SF Pro Display', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
    font-size: 13px;
    color: {COLOR_TEXT_PRIMARY};
}}

QMainWindow, QDialog {{
    background-color: {_IOS_GRAY_BG};
    border: none;
}}

/* ── Sidebar ── */
QFrame#sidebar {{
    background-color: {_SIDEBAR_BG};
    border: none;
    border-right: 1px solid {_SIDEBAR_BORDER};
}}

QLabel#sidebarBrandTitle {{
    color: {_PRIMARY};
    font-size: 17px;
    font-weight: 700;
    letter-spacing: -0.4px;
}}

QLabel#sidebarBrandSubtitle {{
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 400;
}}

QPushButton#sidebarBtn {{
    background-color: transparent;
    border: none;
    border-radius: 12px;
    padding: 12px 16px;
    color: {_SIDEBAR_TEXT};
    font-size: 14px;
    font-weight: 500;
    text-align: left;
}}

QPushButton#sidebarBtn[collapsed='true'] {{
    padding: 8px;
    text-align: center;
    font-size: 20px;
    color: {_SIDEBAR_TEXT};
}}

QPushButton#sidebarBtn:hover {{
    background-color: {_SIDEBAR_HOVER};
    color: {_SIDEBAR_TEXT};
}}

QPushButton#sidebarBtn[active='true'] {{
    background-color: {_SIDEBAR_ACTIVE_BG};
    color: #FFFFFF;
}}

/* ── Header Bar ── */
QFrame#headerBar {{
    background-color: rgba(255, 255, 255, 0.92);
    border: none;
    border-bottom: 0.5px solid {_IOS_SEPARATOR};
}}

QLabel#headerTitle {{
    color: {COLOR_TEXT_PRIMARY};
    font-size: 17px;
    font-weight: 700;
    letter-spacing: -0.4px;
}}

QLabel#headerTarget {{
    color: {COLOR_TEXT_MUTED};
    font-size: 12px;
    font-weight: 400;
}}

QPushButton#hamburgerBtn {{
    background-color: transparent;
    border: none;
    border-radius: 10px;
    padding: 8px;
    font-size: 18px;
    color: {_PRIMARY};
    min-width: 40px;
    min-height: 40px;
}}

QPushButton#hamburgerBtn:hover {{
    background-color: {_PRIMARY_LIGHT};
}}

QPushButton#hamburgerBtn:pressed {{
    background-color: {_PRIMARY_LIGHT_STRONG};
}}

/* ── MDI Area ── */
QMdiArea {{
    background-color: {_IOS_GRAY_BG};
    border: none;
}}

QMdiSubWindow {{
    background-color: {_IOS_GROUPED_BG};
    border: 0.5px solid {_IOS_SEPARATOR};
    border-radius: 14px;
}}

/* ── Buttons (Default) ── */
QPushButton {{
    background-color: {_IOS_GROUPED_BG};
    border: 0.5px solid {_IOS_SEPARATOR};
    border-radius: 10px;
    padding: 8px 18px;
    color: {_PRIMARY};
    font-weight: 500;
    font-size: 13px;
}}

QPushButton:hover {{
    background-color: {_IOS_FILL};
    border-color: {_IOS_SEPARATOR};
    color: {_PRIMARY_HOVER};
}}

QPushButton:pressed {{
    background-color: {COLOR_ACTIVE};
}}

/* Primary action button */
QPushButton#actionBtn {{
    background-color: {_PRIMARY};
    color: #FFFFFF;
    border: none;
    border-radius: 12px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 600;
}}

QPushButton#actionBtn:hover {{
    background-color: {_PRIMARY_HOVER};
}}

QPushButton#actionBtn:pressed {{
    background-color: {_PRIMARY_PRESSED};
}}

/* Compare button (accent) */
QPushButton#compareBtn {{
    background-color: {_PRIMARY};
    color: #FFFFFF;
    border: none;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 600;
    min-height: 38px;
    padding: 8px 20px;
}}

QPushButton#compareBtn:hover {{
    background-color: {_PRIMARY_HOVER};
}}

QPushButton#compareBtn:pressed {{
    background-color: {_PRIMARY_PRESSED};
}}

QPushButton#zoomBtn {{
    background-color: {COLOR_WORKSPACE_DARK};
    border: none;
    border-radius: 8px;
    font-size: 11px;
    color: #FFFFFF;
    padding: 6px 10px;
    min-width: 32px;
    min-height: 28px;
}}

QPushButton#zoomBtn:hover {{
    background-color: #3A3A3C;
}}

/* ── Cards & Frames ── */
QFrame#cardFrame, QFrame#toolCard, QFrame#sidebarLogoCard {{
    background-color: {_IOS_GROUPED_BG};
    border: 0.5px solid {_IOS_SEPARATOR};
    border-radius: 14px;
}}

/* ── PDF Viewer ── */
QScrollArea#pdfViewerArea {{
    background-color: {COLOR_WORKSPACE_DARK};
    border: 0.5px solid {_IOS_SEPARATOR};
    border-radius: 14px;
}}

QScrollArea#pdfViewerArea > QWidget > QWidget {{
    background-color: {COLOR_WORKSPACE_DARK};
}}

/* ── Text Edit ── */
QTextEdit {{
    background-color: {_IOS_GROUPED_BG};
    border: 0.5px solid {_IOS_SEPARATOR};
    border-radius: 12px;
    padding: 12px;
    selection-background-color: {_PRIMARY_SELECTION};
}}

/* ── Scrollbars (thin, iOS-style) ── */
QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 6px;
    margin: 4px 1px;
}}

QScrollBar::handle:vertical {{
    background-color: rgba(0, 0, 0, 0.18);
    min-height: 28px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: rgba(0, 0, 0, 0.35);
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    border: none;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollArea#pdfViewerArea QScrollBar:vertical {{
    background: rgba(255, 255, 255, 0.08);
    width: 8px;
    margin: 4px 1px;
    border-radius: 4px;
}}

QScrollArea#pdfViewerArea QScrollBar::handle:vertical {{
    background-color: rgba(255, 255, 255, 0.65);
    min-height: 30px;
    border-radius: 3px;
}}

QScrollArea#pdfViewerArea QScrollBar::handle:vertical:hover {{
    background-color: rgba(255, 255, 255, 0.9);
}}

QScrollBar:horizontal {{
    border: none;
    background: transparent;
    height: 6px;
    margin: 1px 4px;
}}

QScrollBar::handle:horizontal {{
    background-color: rgba(0, 0, 0, 0.18);
    min-width: 28px;
    border-radius: 3px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: rgba(0, 0, 0, 0.35);
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
    border: none;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* ── Info Button ── */
#infoBtn {{
    background: transparent;
    border: none;
    border-radius: 8px;
    font-size: 18px;
    padding: 4px 8px;
    min-width: 32px;
    max-width: 32px;
    color: {_PRIMARY};
}}

#infoBtn:hover {{
    background-color: {_PRIMARY_LIGHT};
}}

#infoBtn:pressed {{
    background-color: {_PRIMARY_LIGHT_STRONG};
}}

/* ── Close Tool Button ── */
#closeToolBtn {{
    background: transparent;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    padding: 6px 10px;
    color: {_IOS_RED};
    font-weight: 600;
}}

#closeToolBtn:hover {{
    background-color: rgba(255, 59, 48, 0.08);
}}

#closeToolBtn:pressed {{
    background-color: rgba(255, 59, 48, 0.15);
}}

/* Calm orange for header/footer exclusion bars */
QLabel#hfInstruction {{
    color: #FFFFFF;
    background-color: #C2410C;
    padding: 10px 15px;
    border-radius: 8px;
    font-size: 13px;
}}
#pdfToolbar {{
    background-color: rgba(248, 248, 250, 0.95);
    border-bottom: 0.5px solid {_IOS_SEPARATOR};
    border-top-left-radius: 14px;
    border-top-right-radius: 14px;
}}

#toolbarBtn {{
    background: transparent;
    border: 0.5px solid {_IOS_SEPARATOR};
    border-radius: 8px;
    font-size: 12px;
    padding: 5px 8px;
    color: {_PRIMARY};
}}

#toolbarBtn:hover {{
    background-color: {_PRIMARY_LIGHT};
    border-color: {_PRIMARY};
}}

#toolbarBtn:pressed {{
    background-color: {_PRIMARY_LIGHT_STRONG};
}}

#toolbarLabel {{
    font-size: 12px;
    color: {COLOR_TEXT_MUTED};
    font-weight: 600;
}}

#toolbarSearch {{
    border: 0.5px solid {_IOS_SEPARATOR};
    border-radius: 10px;
    padding: 5px 10px;
    font-size: 12px;
    background-color: {_IOS_FILL};
    color: {COLOR_TEXT_PRIMARY};
}}

#toolbarSearch:focus {{
    border-color: {_PRIMARY};
    background-color: #FFFFFF;
}}

/* ── Checkbox ── */
QCheckBox {{
    color: {COLOR_TEXT_PRIMARY};
    spacing: 8px;
    font-size: 13px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1.5px solid {_IOS_SEPARATOR};
    border-radius: 5px;
    background: #FFFFFF;
}}

QCheckBox::indicator:checked {{
    background: {_PRIMARY};
    border: 1.5px solid {_PRIMARY};
}}

QCheckBox#actionCheckBox {{
    font-size: 13px;
    font-weight: 500;
    color: {COLOR_TEXT_SECONDARY};
}}

/* ── Action Bar (bottom strip) ── */
QFrame#actionBar {{
    background-color: rgba(248, 248, 250, 0.96);
    border: none;
    border-top: 0.5px solid {_IOS_SEPARATOR};
    padding: 6px 0px;
    min-height: 56px;
}}

/* Secondary (ghost) button */
QPushButton#secondaryBtn {{
    background-color: transparent;
    border: 1px solid {_PRIMARY};
    border-radius: 12px;
    padding: 0px 18px;
    color: {_PRIMARY};
    font-weight: 600;
    font-size: 13px;
    min-height: 38px;
}}

QPushButton#secondaryBtn:hover {{
    background-color: {_PRIMARY_LIGHT};
}}

QPushButton#secondaryBtn:pressed {{
    background-color: {_PRIMARY_LIGHT_STRONG};
}}

/* Reset / destructive (soft) */
QPushButton#resetBtn {{
    background-color: rgba(255, 59, 48, 0.07);
    border: 1px solid rgba(255, 59, 48, 0.35);
    border-radius: 12px;
    padding: 0px 18px;
    color: #FF3B30;
    font-weight: 600;
    font-size: 13px;
    min-height: 38px;
}}

QPushButton#resetBtn:hover {{
    background-color: rgba(255, 59, 48, 0.14);
    border-color: #FF3B30;
}}

QPushButton#resetBtn:pressed {{
    background-color: rgba(255, 59, 48, 0.22);
}}
"""
