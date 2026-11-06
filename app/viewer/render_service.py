"""Background page rendering.

Each worker thread opens its *own* PyMuPDF document by path (thread-local),
so no fitz.Document is ever shared across threads.
"""
import threading

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtGui import QImage

from app.viewer.page_cache import PageCache

_local = threading.local()


def _open_local(path):
    docs = getattr(_local, 'docs', None)
    if docs is None:
        docs = _local.docs = {}
    doc = docs.get(path)
    if doc is None:
        import pymupdf
        if len(docs) > 8:
            for d in docs.values():
                d.close()
            docs.clear()
        doc = docs[path] = pymupdf.open(path)
    return doc


class _Signals(QObject):
    done = pyqtSignal(object, QImage)


class _RenderJob(QRunnable):
    def __init__(self, key, signals):
        super().__init__()
        self.key = key
        self.signals = signals

    def run(self):
        path, page_no, zoom_milli = self.key
        try:
            import pymupdf
            doc = _open_local(path)
            zoom = zoom_milli / 1000.0
            pix = doc[page_no].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                         QImage.Format.Format_RGB888).copy()
        except Exception:
            img = QImage()
        self.signals.done.emit(self.key, img)


def _alive(obj):
    if obj is None:
        return False
    try:
        from PyQt6 import sip
        return not sip.isdeleted(obj)
    except Exception:
        try:
            obj.objectName()
            return True
        except RuntimeError:
            return False


class RenderService(QObject):
    rendered = pyqtSignal(object)  # key

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cache = PageCache()
        # Unparented pool: survives window teardown; Python holds the ref.
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(2)
        self._pending = set()
        self._signals = _Signals()
        self._signals.done.connect(self._on_done)

    def _ensure_pool(self):
        if _alive(self.pool):
            return self.pool
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(2)
        return self.pool

    @staticmethod
    def make_key(path, page_no, zoom):
        return (path, page_no, int(round(zoom * 1000)))

    def get(self, path, page_no, zoom):
        key = self.make_key(path, page_no, zoom)
        img = self.cache.get(key)
        if img is None and key not in self._pending:
            self._pending.add(key)
            self._ensure_pool().start(_RenderJob(key, self._signals))
        return img

    def _on_done(self, key, img):
        self._pending.discard(key)
        if not img.isNull():
            self.cache.put(key, img)
            self.rendered.emit(key)

    def configure(self, cache_mb=None, threads=None):
        if cache_mb:
            self.cache.max_bytes = int(cache_mb) * 1024 * 1024
            self.cache.put_trim()
        if threads:
            self._ensure_pool().setMaxThreadCount(max(1, int(threads)))

    def forget(self, path):
        self.cache.drop_path(path)

    def shutdown(self):
        pool = self.pool
        if _alive(pool):
            pool.clear()
            pool.waitForDone(2000)


_service = None


def render_service():
    global _service
    if not _alive(_service):
        _service = RenderService()
        try:
            from app.services import app_settings
            _service.configure(
                app_settings.get('perf/render_cache_mb'),
                app_settings.get('perf/render_threads'),
            )
        except Exception:
            pass
    return _service


def reset_render_service():
    """Drop the process-wide singleton (tests / app exit)."""
    global _service
    if _alive(_service):
        try:
            _service.shutdown()
        except RuntimeError:
            pass
    _service = None
