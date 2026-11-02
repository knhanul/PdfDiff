"""Coordinates are unrotated, CropBox-relative PDF points, like get_text()."""
from dataclasses import dataclass

import pymupdf as fitz


@dataclass(frozen=True)
class PageTransform:
    rotation: tuple
    zoom: float
    offset: tuple = (0, 0)

    @classmethod
    def for_page(cls, page, zoom, offset=(0, 0)):
        if zoom <= 0:
            raise ValueError("Zoom must be positive")
        return cls(tuple(page.rotation_matrix), zoom, offset)

    def to_view(self, point):
        p = fitz.Point(point) * fitz.Matrix(*self.rotation)
        return fitz.Point(p.x * self.zoom + self.offset[0],
                          p.y * self.zoom + self.offset[1])

    def to_pdf(self, point):
        p = fitz.Point((point[0] - self.offset[0]) / self.zoom,
                       (point[1] - self.offset[1]) / self.zoom)
        return p * ~fitz.Matrix(*self.rotation)

    def rect_to_view(self, rect):
        r = fitz.Rect(rect) * fitz.Matrix(*self.rotation)
        return fitz.Rect(r.x0 * self.zoom + self.offset[0],
                         r.y0 * self.zoom + self.offset[1],
                         r.x1 * self.zoom + self.offset[0],
                         r.y1 * self.zoom + self.offset[1])
