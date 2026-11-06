"""Recent documents list (QSettings, metadata only)."""
import os

from PyQt6.QtCore import QSettings

_KEY = 'viewer/recent_docs'
MAX_RECENT = 12


def _settings():
    return QSettings('PdfCompare', 'Workspace')


def load_recent():
    v = _settings().value(_KEY, [])
    if isinstance(v, str):
        v = [v]
    return [p for p in (v or []) if isinstance(p, str)]


def add_recent(path):
    path = os.path.abspath(path)
    items = [p for p in load_recent() if os.path.normcase(p) != os.path.normcase(path)]
    items.insert(0, path)
    _settings().setValue(_KEY, items[:MAX_RECENT])


def remove_recent(path):
    _settings().setValue(_KEY, [p for p in load_recent() if p != path])


def clear_recent():
    _settings().setValue(_KEY, [])
