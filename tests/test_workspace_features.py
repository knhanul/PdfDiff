import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from tests.test_viewer_shell import _make_pdf  # noqa: E402


@pytest.fixture
def win(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.services import app_settings, recent_docs, workspace_session
    ini = str(tmp_path / 'settings.ini')
    for mod in (app_settings, recent_docs, workspace_session):
        monkeypatch.setattr(mod, '_settings', lambda: QSettings(ini, QSettings.Format.IniFormat))
    from app.main_window import MdiMainWindow
    w = MdiMainWindow()
    w.resize(1700, 1000)
    w.show()
    app.processEvents()
    yield w, app, tmp_path
    w.close()
    from app.viewer.render_service import reset_render_service
    reset_render_service()


def test_settings_page_persists(win):
    w, app, _ = win
    from app.services import app_settings
    w.show_settings()
    assert w.mode_stack.currentWidget() is w.settings_page
    sp = w.settings_page
    sp.tool_max.setValue(2)
    sp.zoom.setCurrentIndex(sp.zoom.findData('page'))
    assert app_settings.get('perf/tool_cache_max') == 2
    assert w.tool_cache_max == 2
    assert w.viewer.default_fit == 'page'
    sp._reset()
    assert app_settings.get('perf/tool_cache_max') == 3


def test_global_search_grouped_and_jump(win):
    w, app, tmp = win
    a, b = tmp / 'a.pdf', tmp / 'b.pdf'
    _make_pdf(str(a), pages=2)
    _make_pdf(str(b), pages=4)
    w.open_pdf(str(a))
    w.open_pdf(str(b))
    w.show_global_search()
    gs = w.viewer.global_search
    assert gs.isVisible()
    gs.edit.setText('page 2')
    res = gs.run()
    assert len(res) == 2 and gs.tree.topLevelItemCount() == 2
    item = gs.tree.topLevelItem(0).child(0)
    gs._activate(item)
    assert w.viewer.tabs.currentIndex() == 0
    assert w.viewer._cv().canvas.highlights


def test_work_panel_modes(win):
    w, app, tmp = win
    a = tmp / 'f.pdf'
    _make_pdf(str(a), form=True)
    w.open_pdf(str(a))
    v = w.viewer
    assert not v.work_panel.isVisible()  # closed by default
    v.toggle_work_mode('info')
    assert v.work_panel.isVisible() and v.mode_bar.isVisible()
    assert '3쪽' in v.work_panel.info_labels['쪽수'].text()
    v.open_work_mode('form')
    assert v.work_panel.field_list.count() == 1
    v.toggle_work_mode('form')
    assert not v.work_panel.isVisible() and not v.mode_bar.isVisible()


def test_command_palette_lists_tools_and_actions(win):
    w, *_ = win
    from app.shell.command_palette import match
    cmds = w.palette_commands()
    titles = [c['title'] for c in cmds]
    for d in w.tool_definitions:
        assert d['menu_title'] in titles
    assert match('설정', cmds)[0]['title'] == '설정'
    assert any(c['title'] == '전체비교' for c in match('비교', cmds))


def test_narrow_window_compacts_sidebar(win):
    w, app, _ = win
    from app.main_window import SIDEBAR_COMPACT_WIDTH
    assert not w.sidebar_compact
    w.resize(1366, 768)
    app.processEvents()
    assert w.sidebar_compact and w.sidebar.width() == SIDEBAR_COMPACT_WIDTH
    w.resize(1700, 1000)
    app.processEvents()
    assert not w.sidebar_compact
    # focus mode still hides sidebar entirely and restores afterwards
    w.toggle_sidebar()
    assert w.focus_mode
    w.toggle_sidebar()
    assert not w.focus_mode
