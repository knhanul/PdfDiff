"""Workspace session: remembers which PDFs were open (paths + page), never loads them at start-up."""
import json
import os

from PyQt6.QtCore import QSettings

_KEY = 'viewer/last_session'


def _settings():
    return QSettings('PdfCompare', 'Workspace')


def save_session(entries):
    """entries: list of {'path': str, 'page': int}"""
    _settings().setValue(_KEY, json.dumps(entries, ensure_ascii=False))


def load_session():
    raw = _settings().value(_KEY, '')
    try:
        data = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict) and os.path.isfile(e.get('path', ''))]
