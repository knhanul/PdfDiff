import os
import subprocess
import sys

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_startup_does_not_import_tools_or_pymupdf():
    code = (
        "import os, sys; os.environ['QT_QPA_PLATFORM']='offscreen';"
        "from PyQt6.QtWidgets import QApplication; app=QApplication([]);"
        "from app.main_window import MdiMainWindow; w=MdiMainWindow(); w.show(); app.processEvents();"
        "bad=[m for m in sys.modules if m.startswith('app.tools') or m in ('pymupdf','fitz')];"
        "assert w.mode_stack.currentWidget() is w.welcome_page, 'not welcome';"
        "print('LOADED', bad); sys.exit(1 if bad else 0)"
    )
    r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_welcome_has_no_form_shortcut():
    from app.shell.welcome_page import WELCOME_SHORTCUTS
    keys = [k for k, *_ in WELCOME_SHORTCUTS]
    titles = [t for _, t, _ in WELCOME_SHORTCUTS]
    assert 'pdf_form' not in keys
    assert not any('입력' in t for t in titles)


def test_page_cache_lru_budget():
    from PyQt6.QtGui import QImage
    from app.viewer.page_cache import PageCache
    img = QImage(100, 100, QImage.Format.Format_RGB888)
    c = PageCache(max_bytes=img.sizeInBytes() * 2)
    for i in range(5):
        c.put(('a', i, 1000), img)
    assert c.get(('a', 0, 1000)) is None
    assert c.get(('a', 4, 1000)) is not None
    assert c.size_bytes <= img.sizeInBytes() * 2


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _make_pdf(path, pages=3, form=False):
    import pymupdf
    doc = pymupdf.open()
    for i in range(pages):
        p = doc.new_page()
        p.insert_text((72, 72), f'hello page {i + 1}')
    if form:
        w = pymupdf.Widget()
        w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        w.field_name = 'name'
        w.rect = pymupdf.Rect(72, 100, 200, 120)
        doc[0].add_widget(w)
    doc.save(path)


def test_open_split_and_form_banner(qapp, tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    from app.services import recent_docs, workspace_session
    ini = str(tmp_path / 'settings.ini')
    monkeypatch.setattr(recent_docs, '_settings', lambda: QSettings(ini, QSettings.Format.IniFormat))
    monkeypatch.setattr(workspace_session, '_settings', lambda: QSettings(ini, QSettings.Format.IniFormat))
    a, b = tmp_path / 'a.pdf', tmp_path / 'b.pdf'
    _make_pdf(str(a), form=True)
    _make_pdf(str(b), pages=5)
    from app.main_window import MdiMainWindow
    w = MdiMainWindow()
    w.resize(1366, 768)
    w.show()
    assert w.open_pdf(str(a))
    assert w.open_pdf(str(b))
    assert w.viewer.count() == 2
    assert w.mode_stack.currentWidget() is w.viewer
    view = w.viewer._views[0]
    w.viewer._detect_form(view)
    assert '1개' in view.banner.label.text()
    # search
    w.viewer.tabs.setCurrentIndex(1)
    w.viewer.search_edit.setText('page 3')
    w.viewer._search_next()
    assert w.viewer._cv().search_hits
    # split view sync
    w.open_split_view()
    sv = w.split_view
    sv.set_documents(right=w.doc_manager.get(str(a)))
    qapp.processEvents()
    sv.left.canvas.set_position(1.5)
    qapp.processEvents()
    assert sv.right.canvas.position()[0] > 0.5
    # close tabs → welcome
    w.show_viewer()
    w.viewer._close_tab(0)
    w.viewer._close_tab(0)
    assert w.mode_stack.currentWidget() is w.welcome_page
    w.close()
    from app.viewer.render_service import reset_render_service
    reset_render_service()
