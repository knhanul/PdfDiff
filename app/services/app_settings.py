"""Workspace settings (QSettings). Pure-Python, no PyMuPDF import."""
from PyQt6.QtCore import QSettings

DEFAULTS = {
    'ui/theme': 'default',              # shell palette (applied live)
    'viewer/default_zoom': 'width',      # 'width' | 'page' | '100'
    'viewer/open_mode': 'new_tab',       # 'new_tab' | 'replace'
    'viewer/show_nav': True,
    'workspace/auto_restore': False,     # reopen last session on launch
    'workspace/offer_restore': True,     # show 「지난 작업 복원」 on welcome
    'perf/render_cache_mb': 256,
    'perf/tool_cache_max': 3,
    'perf/render_threads': 2,
    'ui/auto_compact_sidebar': True,     # icon sidebar on narrow windows
    'ui/compact_threshold': 1500,        # window width (logical px)
}
_BOOL = {k for k, v in DEFAULTS.items() if isinstance(v, bool)}
_INT = {k for k, v in DEFAULTS.items() if isinstance(v, int) and not isinstance(v, bool)}


def _settings():
    return QSettings('PdfCompare', 'Workspace')


def get(key):
    default = DEFAULTS.get(key)
    v = _settings().value(key, default)
    if key in _BOOL:
        return v if isinstance(v, bool) else str(v).lower() in ('1', 'true', 'yes')
    if key in _INT:
        try:
            return int(v)
        except (TypeError, ValueError):
            return default
    return v


def set(key, value):  # noqa: A001
    _settings().setValue(key, value)


def reset():
    s = _settings()
    for k in DEFAULTS:
        s.remove(k)
