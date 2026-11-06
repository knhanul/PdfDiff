"""Unit tests for the common open-document picker."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _FakeDoc:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.title = os.path.basename(path)


class _FakeDM:
    def __init__(self, paths):
        self._docs = {os.path.abspath(p): _FakeDoc(p) for p in paths}

    def paths(self):
        return list(self._docs)

    def get(self, path):
        return self._docs.get(os.path.abspath(path))


def test_picker_lists_open_docs(qapp, tmp_path):
    from app.shell.open_doc_picker import OpenDocPicker, _doc_entries
    a = str(tmp_path / 'alpha.pdf')
    b = str(tmp_path / 'beta.pdf')
    dm = _FakeDM([a, b])
    entries = _doc_entries(dm)
    assert [t for t, _ in entries] == ['alpha.pdf', 'beta.pdf']
    dlg = OpenDocPicker(entries, title='열린 문서에서 선택')
    assert dlg.list.count() == 2
    assert dlg.list.item(0).toolTip() == os.path.abspath(a)
    assert dlg.btn_file.text() == '파일에서 열기…'


def test_picker_exclude_paths(qapp, tmp_path):
    from app.shell.open_doc_picker import _doc_entries
    a = str(tmp_path / 'a.pdf')
    b = str(tmp_path / 'b.pdf')
    dm = _FakeDM([a, b])
    entries = _doc_entries(dm, exclude_paths=[a])
    assert [p for _, p in entries] == [os.path.abspath(b)]


def test_pick_document_cancel(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QDialog
    from app.shell import open_doc_picker as mod

    a = str(tmp_path / 'a.pdf')
    dm = _FakeDM([a])

    class _Cancel(mod.OpenDocPicker):
        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(mod, 'OpenDocPicker', _Cancel)
    assert mod.pick_document(None, dm) is None


def test_pick_document_file_fallback_when_empty(qapp, monkeypatch):
    from app.shell import open_doc_picker as mod

    dm = _FakeDM([])
    monkeypatch.setattr(
        mod.QFileDialog, 'getOpenFileName',
        staticmethod(lambda *a, **k: ('/tmp/from_disk.pdf', 'PDF')),
    )
    assert mod.pick_document(None, dm) == '/tmp/from_disk.pdf'

    monkeypatch.setattr(
        mod.QFileDialog, 'getOpenFileName',
        staticmethod(lambda *a, **k: ('', '')),
    )
    assert mod.pick_document(None, dm) is None


def test_viewer_has_tab_open_button(qapp):
    from app.shell.viewer_workspace import ViewerWorkspace
    v = ViewerWorkspace()
    assert hasattr(v, 'btn_open_tab')
    assert v.btn_open_tab.toolTip() == 'PDF 열기 (Ctrl+O)'
    assert v.btn_open_tab.text() == '＋ PDF 열기'
    assert v.btn_open_tab.objectName() == 'openPdfTabBtn'
    assert v.tabs.parentWidget().layout().indexOf(v.btn_open_tab) == \
        v.tabs.parentWidget().layout().indexOf(v.tabs) + 1
    # signal exists
    assert hasattr(v, 'open_requested')
