"""Lightweight PDF document handle (main-thread only).

PyMuPDF is imported lazily so that application start-up never pays for it.
Render workers never share this object; they open their own handle by path.
"""
import os


def _fitz():
    import pymupdf  # lazy
    return pymupdf


class PdfDocument:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.title = os.path.basename(path)
        fitz = _fitz()
        self._doc = fitz.open(self.path)
        if self._doc.needs_pass:
            self._doc.close()
            raise ValueError('암호로 보호된 PDF는 아직 지원하지 않습니다.')
        # page sizes in PDF points (cheap; no rendering)
        self.page_sizes = [(p.rect.width, p.rect.height) for p in self._doc]
        self.modified = False

    @property
    def page_count(self):
        return len(self.page_sizes)

    def form_field_count(self):
        try:
            n = self._doc.is_form_pdf
            return int(n) if n else 0
        except Exception:
            return 0

    def form_fields(self, limit=1000):
        out = []
        try:
            for i, page in enumerate(self._doc):
                for w in page.widgets() or ():
                    out.append((w.field_name or '(이름 없음)', i))
                    if len(out) >= limit:
                        return out
        except Exception:
            pass
        return out

    def search(self, text, max_hits=500):
        hits = []
        if not text:
            return hits
        for i, page in enumerate(self._doc):
            for r in page.search_for(text):
                hits.append((i, (r.x0, r.y0, r.x1, r.y1)))
                if len(hits) >= max_hits:
                    return hits
        return hits

    def close(self):
        try:
            self._doc.close()
        except Exception:
            pass
