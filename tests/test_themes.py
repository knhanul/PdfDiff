"""Theme persistence, actual widget palettes and live switching regressions."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from app.shell.theme import THEMES, TOKENS, THEME_CHOICES, build_shell_qss, theme_tokens


@pytest.fixture
def theme_env(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    from app.services import app_settings, recent_docs, workspace_session
    app = QApplication.instance() or QApplication([])
    ini = str(tmp_path / 'workspace.ini')
    for module in (app_settings, recent_docs, workspace_session):
        monkeypatch.setattr(module, '_settings', lambda: QSettings(ini, QSettings.Format.IniFormat))
    yield app


def test_default_and_unknown_theme(theme_env):
    from app.services import app_settings
    assert app_settings.DEFAULTS['ui/theme'] == 'default'
    assert app_settings.get('ui/theme') == 'default'
    assert THEMES['default'] == TOKENS
    assert build_shell_qss() == build_shell_qss('unknown')
    palette = theme_tokens('silver')
    palette['accent'] = 'changed'
    assert THEMES['silver']['accent'] != 'changed'


@pytest.mark.parametrize('theme_id', list(THEMES))
def test_settings_persist_and_apply_live(theme_env, theme_id):
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QFrame, QPushButton
    from app.main_window import MdiMainWindow
    from app.services import app_settings
    from app.shell.settings_page import SettingsPage
    w = MdiMainWindow()
    try:
        w.show()
        w.show_settings()
        page = w.settings_page
        assert [page.theme.itemText(i) for i in range(page.theme.count())] == [t for _, t in THEME_CHOICES]
        # Always exercise a real change, including when testing the default.
        page.theme.setCurrentIndex(page.theme.findData('black' if theme_id != 'black' else 'silver'))
        changes = []
        page.settings_changed.connect(changes.append)
        page.theme.setCurrentIndex(page.theme.findData(theme_id))
        theme_env.processEvents()
        assert changes == ['ui/theme']
        assert app_settings.get('ui/theme') == theme_id
        assert build_shell_qss(theme_id) in w.styleSheet()
        tokens = theme_tokens(theme_id)
        assert w.sidebar.palette().color(QPalette.ColorRole.Window).name().upper() == tokens['sidebar_bg']
        header = w.findChild(QFrame, 'headerBar')
        assert header.palette().color(QPalette.ColorRole.Window).name().upper() == tokens['app_bg']
        assert w.header_title.palette().color(QPalette.ColorRole.WindowText).name().upper() == tokens['text']
        assert page.theme.palette().color(QPalette.ColorRole.Base).name().upper() == tokens['panel_bg']
        primary = w.welcome_page.findChild(QPushButton, 'primaryBtn')
        assert primary.palette().color(QPalette.ColorRole.Button).name().upper() == tokens['accent']
        # Recreating the settings page must load the saved key, not its label.
        restored = SettingsPage(w)
        assert restored.theme.currentData() == theme_id
        restored.deleteLater()
        # Changing chrome does not replace/rebuild the settings page.
        assert w.mode_stack.currentWidget() is page
        page._reset()
        theme_env.processEvents()
        assert app_settings.get('ui/theme') == 'default'
        assert page.theme.currentData() == 'default'
        assert build_shell_qss('default') in w.styleSheet()
    finally:
        w.close()
        w.deleteLater()
        theme_env.processEvents()


@pytest.mark.parametrize('theme_id', list(THEMES) + ['removed-theme'])
def test_saved_theme_used_at_startup(theme_env, theme_id):
    from app.main_window import MdiMainWindow
    from app.services import app_settings
    app_settings.set('ui/theme', theme_id)
    w = MdiMainWindow()
    try:
        assert build_shell_qss(theme_id) in w.styleSheet()
        w.blink_state = False
        w.toggle_button_blink()
        assert theme_tokens(theme_id)['selected'] in w.legend_caution_btn.styleSheet()
        w.apply_settings('ui/theme')
        assert not w.legend_caution_btn.styleSheet()
    finally:
        w.close()
        w.deleteLater()
        theme_env.processEvents()


@pytest.mark.parametrize('theme_id', [t for t in THEMES if t != 'default'])
def test_non_default_themes_style_all_screen_buttons_and_grid_headers(theme_env, theme_id):
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QPushButton
    from app.main_window import MdiMainWindow
    from app.services import app_settings
    from app.shell.theme import header_section_qss, tool_table_qss

    app_settings.set('ui/theme', 'default')
    w = MdiMainWindow()
    try:
        w.show()
        # Verify default theme does not inject non-default button chrome overrides
        default_qss = build_shell_qss('default')
        assert 'QPushButton#compareActionBtn' not in default_qss
        assert 'QPushButton#pdfOpenButton' not in default_qss

        # Open tools and switch to non-default theme live
        app_settings.set('ui/theme', theme_id)
        w.apply_settings('ui/theme')
        theme_env.processEvents()

        tokens = theme_tokens(theme_id)
        qss = build_shell_qss(theme_id)
        for selector in (
            'QPushButton#actionBtn',
            'QPushButton#compareActionBtn',
            'QPushButton#pdfOpenButton',
            'QPushButton#secondaryBtn',
            'QPushButton#compareUtilityBtn',
            'QPushButton#toolbarBtn',
            'QPushButton#viewerToolBtn',
            'QPushButton#toolToggleBtn',
            'QHeaderView::section',
        ):
            assert selector in qss

        for tool_key in ('pdf_compare', 'pdf_hf_compare', 'pdf_editor', 'pdf_create', 'file_rename', 'pdf_form'):
            w.open_tool(tool_key)
            theme_env.processEvents()
            tool = w.current_tool_widget
            assert tool is not None

            # Check action/primary buttons use theme accent background
            for obj_name in ('actionBtn', 'compareActionBtn', 'pdfOpenButton', 'compareBtn'):
                for btn in tool.findChildren(QPushButton, obj_name):
                    if btn.isEnabled():
                        assert btn.palette().color(QPalette.ColorRole.Button).name().upper() == tokens['accent']

            # Check secondary/toolbar/utility buttons use theme panel_bg and accent colors
            for obj_name in ('secondaryBtn', 'compareUtilityBtn', 'toolbarBtn'):
                for btn in tool.findChildren(QPushButton, obj_name):
                    if btn.isEnabled():
                        assert btn.palette().color(QPalette.ColorRole.Button).name().upper() == tokens['panel_bg']
                        assert btn.palette().color(QPalette.ColorRole.ButtonText).name().upper() == tokens['accent']

            # Check grid tables and headers have theme colors applied
            tables = []
            if hasattr(tool, 'file_table'):
                tables.append(tool.file_table)
            if hasattr(tool, 'extract_table'):
                tables.extend([tool.extract_table, tool.import_table, tool.creator_panel.field_table])
            for table in tables:
                hdr = table.horizontalHeader()
                assert hdr.palette().color(QPalette.ColorRole.Window).name().upper() == tokens['accent']
                assert 'QHeaderView::section' in table.styleSheet()
                assert tokens['accent'] in table.styleSheet()
                assert tokens['accent_hover'] in table.styleSheet()
                assert tokens['border'] in table.styleSheet()
    finally:
        w.close()
        w.deleteLater()
        theme_env.processEvents()

