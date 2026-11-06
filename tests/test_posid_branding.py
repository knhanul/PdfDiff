"""PoSID corporate identity: official emblem, Posid PDF name, themed headers."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from app.shell.theme import THEMES, build_shell_qss, header_section_qss


def test_posid_app_name_is_posid_pdf():
    from configs.target_posid import TARGET
    from configs.settings import SETTINGS
    assert TARGET['APP_NAME'] == 'Posid PDF'
    assert SETTINGS['BUILD_TARGET'] == 'posid'
    assert SETTINGS['APP_NAME'] == 'Posid PDF'


def test_header_section_qss_tracks_each_theme_accent():
    for tid, tokens in THEMES.items():
        qss = header_section_qss(tid)
        assert 'QHeaderView::section' in qss
        assert tokens['accent'] in qss
        assert tokens['accent_hover'] in qss
        shell = build_shell_qss(tid)
        assert 'QHeaderView::section' in shell
        assert tokens['accent'] in shell


@pytest.fixture
def brand_env(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    from app.services import app_settings, recent_docs, workspace_session
    app = QApplication.instance() or QApplication([])
    ini = str(tmp_path / 'workspace.ini')
    for module in (app_settings, recent_docs, workspace_session):
        monkeypatch.setattr(module, '_settings', lambda: QSettings(ini, QSettings.Format.IniFormat))
    yield app


def test_sidebar_uses_official_emblem_not_document_mark(brand_env):
    from PyQt6.QtGui import QColor, QImage
    from app.common.resources import APP_NAME, get_logo_path
    from app.main_window import MdiMainWindow
    from app.shell.sidebar_icons import brand_mark

    assert get_logo_path()
    assert APP_NAME == 'Posid PDF'
    w = MdiMainWindow()
    try:
        assert w.sidebar_brand_title.text() == 'Posid PDF'
        assert w.sidebar_brand_subtitle.text() == 'PDF Workspace'
        assert w.windowTitle().startswith('Posid PDF')
        pm = w.sidebar_logo.pixmap()
        assert pm is not None and not pm.isNull()
        # Official emblem is richer than the flat terracotta document mark.
        fake = brand_mark('#A44735', 32)
        assert pm.toImage().pixelColor(16, 16) != fake.toImage().pixelColor(16, 16) or (
            pm.toImage().pixelColor(8, 8) != fake.toImage().pixelColor(8, 8)
        )
        # Emblem must not be recolored when switching themes (same logo asset).
        from app.services import app_settings
        app_settings.set('ui/theme', 'silver')
        w.apply_settings('ui/theme')
        brand_env.processEvents()
        pm_silver = w.sidebar_logo.pixmap()
        assert not pm_silver.isNull()
        # Black theme still shows a pixmap (with light pad); not the document mark fill.
        app_settings.set('ui/theme', 'black')
        w.apply_settings('ui/theme')
        brand_env.processEvents()
        pm_black = w.sidebar_logo.pixmap()
        assert not pm_black.isNull()
        assert pm_black.toImage().pixelColor(16, 16) != QColor('#AFC4DA')
    finally:
        w.close()
        w.deleteLater()
        brand_env.processEvents()


def test_tool_table_header_restyles_on_theme_change(brand_env):
    from app.main_window import MdiMainWindow
    from app.services import app_settings
    from app.tools.pdf_editor import PdfEditorWidget

    w = MdiMainWindow()
    try:
        editor = PdfEditorWidget(w)
        w.tool_cache['pdf_editor'] = editor
        editor._style_file_table()
        assert THEMES['default']['accent'] in editor.file_table.styleSheet()
        app_settings.set('ui/theme', 'gold')
        w.apply_settings('ui/theme')
        brand_env.processEvents()
        assert THEMES['gold']['accent'] in editor.file_table.styleSheet()
        assert THEMES['default']['accent'] not in editor.file_table.styleSheet() or \
            THEMES['default']['accent'] == THEMES['gold']['accent']
    finally:
        w.close()
        w.deleteLater()
        brand_env.processEvents()
