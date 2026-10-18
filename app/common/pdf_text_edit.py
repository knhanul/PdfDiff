"""Conservative text editing. All destructive work happens in a disposable PDF.

No white cover rectangles, no silent font fallback, no in-place source saves.
This module has no Qt dependency and is also the Phase 1 prototype API.
"""
from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import math
import os
from pathlib import Path
import tempfile

import pymupdf as fitz


class EditError(ValueError):
    pass


@dataclass(frozen=True)
class TextRun:
    page: int
    key: tuple
    chars: tuple
    boxes: tuple
    origins: tuple
    font: str
    size: float
    color: int
    flags: int
    direction: tuple
    writable: bool
    reason: str
    revision: int = 0

    @property
    def text(self):
        return "".join(self.chars)

    @property
    def rect(self):
        result = fitz.Rect(self.boxes[0])
        for box in self.boxes[1:]:
            result |= fitz.Rect(box)
        return result

    def subset(self, start, end):
        if not 0 <= start < end <= len(self.chars):
            raise EditError("문자 선택 범위가 올바르지 않습니다.")
        return replace(self, key=(*self.key[:3], self.key[3] + start),
                       chars=self.chars[start:end], boxes=self.boxes[start:end],
                       origins=self.origins[start:end])


def analyze(page, revision=0):
    runs = []
    raw = page.get_text("rawdict", flags=fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES)
    for bi, block in enumerate(raw["blocks"]):
        for li, line in enumerate(block.get("lines", [])):
            for si, span in enumerate(line["spans"]):
                chars = span["chars"]
                if not chars:
                    continue
                direction = tuple(line["dir"])
                safe = (line.get("wmode", 0) == 0 and
                        abs(direction[0] - 1) < 1e-5 and abs(direction[1]) < 1e-5 and
                        span.get("alpha", 255) == 255 and
                        all(c["c"] != "\ufffd" and len(c["c"]) == 1 for c in chars))
                runs.append(TextRun(page.number, (bi, li, si, 0),
                    tuple(c["c"] for c in chars), tuple(tuple(c["bbox"]) for c in chars),
                    tuple(tuple(c["origin"]) for c in chars), span["font"], span["size"],
                    span["color"], span["flags"], direction, safe,
                    "" if safe else "세로쓰기·기울어진 텍스트·투명 문자·불명확한 문자 인코딩은 지원하지 않습니다.",
                    revision))
    return runs


def hit_test(runs, point):
    """Pick only unambiguous character hits; expand within the same span/word."""
    hits = [(run, i) for run in runs for i, box in enumerate(run.boxes)
            if not run.chars[i].isspace() and fitz.Point(point) in fitz.Rect(box)]
    if len(hits) != 1:
        return None
    run, index = hits[0]
    start, end = index, index + 1
    while start and not run.chars[start - 1].isspace():
        start -= 1
    while end < len(run.chars) and not run.chars[end].isspace():
        end += 1
    return run.subset(start, end)


def _char_key(char, box, origin):
    return char, tuple(round(v, 2) for v in box), tuple(round(v, 2) for v in origin)


def characters(runs):
    return Counter(_char_key(c, b, o) for r in runs
                   for c, b, o in zip(r.chars, r.boxes, r.origins))


def _name(name):
    return name.split("+")[-1].replace(" ", "").replace("-", "").lower()


class FontManager:
    @staticmethod
    def resolve(doc, page, run, text, font_path=None):
        if font_path:
            font = fitz.Font(fontfile=str(font_path))
        else:
            candidates = []
            for entry in page.get_fonts(full=True):
                xref, _, _, base, *_ = entry
                if _name(base) != _name(run.font):
                    continue
                if xref:
                    _, _, _, buffer = doc.extract_font(xref)
                    if buffer:
                        try:
                            candidates.append(fitz.Font(fontbuffer=buffer))
                        except Exception:
                            pass
                if base in fitz.Base14_fontnames:
                    candidates.append(fitz.Font(base))
            unique = {hashlib.sha256(f.buffer).hexdigest(): f for f in candidates}
            if len(unique) != 1:
                raise EditError("원본 글꼴을 정확히 재사용할 수 없습니다. 원본 서식 유지를 해제하고 사용 권한이 있는 글꼴 파일을 선택하세요.")
            font = next(iter(unique.values()))
        if any(not font.has_glyph(ord(c), fallback=False) for c in text if not c.isspace()):
            raise EditError("선택한 글꼴에 필요한 문자가 없습니다. 한글을 지원하는 글꼴 파일을 선택하세요.")
        return font


def document_restriction(doc):
    if doc.needs_pass or doc.is_encrypted:
        return "암호화 PDF는 1차 버전에서 열람만 지원합니다."
    if doc.is_repaired:
        return "복구된 손상 PDF는 안전한 수정을 보장할 수 없어 열람만 지원합니다."
    if not doc.permissions & fitz.PDF_PERM_MODIFY:
        return "문서에 편집 권한이 없습니다."
    if doc.get_sigflags() > 0:
        return "전자서명 또는 서명 필드가 있는 PDF는 수정 저장을 지원하지 않습니다."
    if doc.get_ocgs():
        return "선택적 콘텐츠(레이어)가 있는 PDF는 열람만 지원합니다."
    if tuple(map(int, fitz.VersionBind.split(".")[:2])) < (1, 24):
        return "안전한 텍스트 제거에는 PyMuPDF 1.24 이상이 필요합니다."
    return ""


def inspect_document(source, password=""):
    with fitz.open(stream=source, filetype="pdf") as doc:
        encrypted = doc.needs_pass or doc.is_encrypted
        if doc.needs_pass and not doc.authenticate(password):
            raise EditError("PDF 암호가 필요하거나 올바르지 않습니다.")
        if not doc.is_pdf or doc.page_count == 0:
            raise EditError("유효한 PDF 문서가 아닙니다.")
        reason = document_restriction(doc)
        if encrypted:
            reason = "암호화 PDF는 열람만 지원합니다."
        return doc.page_count, reason


def rasterize(source, number, zoom, revision, password="", thumbnail=False, include_text=True):
    """Process-safe result: RGB bytes and plain Python text/transform data."""
    from app.common.pdf_modify_coordinates import PageTransform
    with fitz.open(stream=source, filetype="pdf") as doc:
        if doc.needs_pass and not doc.authenticate(password):
            raise EditError("열람 암호가 올바르지 않습니다.")
        page = doc[number]
        if thumbnail:
            zoom = min(95 / page.rect.width, 125 / page.rect.height)
        if page.rect.width * page.rect.height * zoom * zoom > 16_000_000:
            raise EditError("표시 배율이 너무 큽니다. 배율을 낮춰 주세요.")
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False,
                             colorspace=fitz.csRGB)
        return (pix.samples, pix.width, pix.height, pix.stride,
                [] if thumbnail or not include_text else analyze(page, revision),
                PageTransform.for_page(page, zoom))


def _page_guard(page, region):
    if page.get_xobjects():
        raise EditError("다른 페이지와 공유될 수 있는 묶음 콘텐츠가 있어 이 페이지는 열람만 지원합니다.")
    # apply_redactions applies ALL existing redactions; never apply user annotations.
    if any(a.type[0] == fitz.PDF_ANNOT_REDACT for a in page.annots() or ()):
        raise EditError("기존 가림 주석이 있는 페이지는 수정할 수 없습니다.")
    for rect in ([fitz.Rect(link["from"]) for link in page.get_links()] +
                 [a.rect for a in page.annots() or ()] +
                 [w.rect for w in page.widgets() or ()]):
        if region.intersects(rect):
            raise EditError("수정 영역에 링크·주석·폼 필드가 겹칩니다.")
    # Hidden/stroked text and non-opaque text cannot be faithfully reproduced.
    for trace in page.get_texttrace():
        if region.intersects(fitz.Rect(trace["bbox"])):
            if trace["type"] != 0 or trace["opacity"] < .999:
                raise EditError("보이지 않는 문자·윤곽선 문자·반투명 문자는 수정할 수 없습니다.")


def _graphics(page):
    drawings = [{k: v for k, v in d.items() if k not in ("seqno",)}
                for d in page.get_drawings()]
    images = [(tuple(i["bbox"]), i["width"], i["height"], i["digest"])
              for i in page.get_image_info(hashes=True)]
    return drawings, images


def _render(page, scale=1.5):
    if page.rect.width * page.rect.height * scale * scale > 12_000_000:
        raise EditError("페이지가 너무 커서 안전한 시각 검증 범위를 초과합니다.")
    return page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False,
                           colorspace=fitz.csRGB)


def verify_outside(before, after, area, scale=1.5):
    """Exact raster comparison outside the edit rectangle plus a 2px AA margin."""
    a, b = _render(before, scale), _render(after, scale)
    if (a.width, a.height, a.n) != (b.width, b.height, b.n):
        raise EditError("수정 전후 페이지 크기가 달라졌습니다.")
    r = fitz.Rect(area) * before.rotation_matrix * fitz.Matrix(scale, scale)
    x0, y0 = max(0, math.floor(r.x0) - 2), max(0, math.floor(r.y0) - 2)
    x1, y1 = min(a.width, math.ceil(r.x1) + 2), min(a.height, math.ceil(r.y1) + 2)
    aa, bb = a.samples, b.samples
    for y in range(a.height):
        offset = y * a.stride
        ranges = ((0, a.stride),) if y < y0 or y >= y1 else ((0, x0 * 3), (x1 * 3, a.stride))
        for start, end in ranges:
            if aa[offset + start:offset + end] != bb[offset + start:offset + end]:
                raise EditError("수정 영역 밖의 화면 변화가 감지되어 적용을 취소했습니다.")


@dataclass(frozen=True)
class EditCommand:
    page: int
    before: str
    after: str
    rect: tuple
    font: str
    size: float
    color: int
    replacement_font: bool


def edit_document(source, page_number, target, text, *, font_path=None,
                  size=None, color=None, origin=None, width=None, shrink_min=None):
    if "\n" in text or "\r" in text or any(ord(c) < 32 for c in text):
        raise EditError("1차 버전은 한 줄 텍스트만 지원합니다.")
    with fitz.open(stream=source, filetype="pdf") as before, fitz.open(stream=source, filetype="pdf") as work:
        reason = document_restriction(before)
        if reason:
            raise EditError(reason)
        page, edited = before[page_number], work[page_number]
        old_runs = analyze(page)
        if target:
            if not target.writable:
                raise EditError(target.reason)
            if target.page != page_number or not characters([target]) <= characters(old_runs):
                raise EditError("선택한 텍스트가 현재 문서와 일치하지 않습니다. 다시 선택하세요.")
            region = target.rect
            origin = target.origins[0]
            size = target.size if size is None else size
            color = target.color if color is None else color
            width = region.width if width is None else width
        else:
            if not text or origin is None or width is None or font_path is None:
                raise EditError("추가할 텍스트, 위치, 영역 너비와 글꼴을 지정하세요.")
            size, color = size or 12, color or 0
            region = fitz.Rect(origin[0], origin[1] - size, origin[0] + width, origin[1] + size * .3)
        if size <= 0 or width <= 0:
            raise EditError("글꼴 크기와 너비는 양수여야 합니다.")
        _page_guard(page, region)
        font = FontManager.resolve(before, page, target, text, font_path) if text else None
        if target and text and not font_path:
            for i in range(len(target.chars) - 1):
                advance = target.origins[i + 1][0] - target.origins[i][0]
                expected = font.text_length(target.chars[i], fontsize=target.size)
                if abs(advance - expected) > .3:
                    raise EditError("문자 간격·가로 배율을 재현할 수 없습니다. 원본 서식 유지 해제 후 글꼴을 지정하세요.")
        insertion = fitz.Rect(region)
        if text:
            length = font.text_length(text, fontsize=size)
            # PDF /Widths entries round font advances to 1/1000 em.
            if length > width + .15:
                if shrink_min and length and size * width / length >= shrink_min:
                    size *= width / length
                else:
                    raise EditError("문구가 지정 영역보다 깁니다. 문구를 줄이거나 최소 크기/영역 너비를 명시적으로 조정하세요.")
            length = font.text_length(text, fontsize=size)
            insertion = fitz.Rect(origin[0], origin[1] - font.ascender * size,
                                  origin[0] + length, origin[1] - font.descender * size)
        area = region | insertion
        if not (area in (page.rect * page.derotation_matrix)):
            raise EditError("텍스트 영역이 페이지 밖으로 나갑니다.")
        _page_guard(page, area)
        others = characters(old_runs) - (characters([target]) if target else Counter())
        # Reject overlap before redaction, including invisible extraction boundaries.
        redactions = []
        if target:
            for box in target.boxes:
                r = fitz.Rect(box)
                if r.is_empty:
                    raise EditError("문자 경계가 불명확합니다.")
                redactions.append(fitz.Rect(r.x0 + .05, r.y0 + .05, r.x1 - .05, r.y1 - .05))
        for (_, box, _), count in others.items():
            overlap = fitz.Rect(box) & insertion
            if count and (any(fitz.Rect(box).intersects(r) for r in redactions) or
                          (text and overlap.width > .01 and overlap.height > .01)):
                raise EditError("인접 문자와 영역이 겹쳐 안전하게 수정할 수 없습니다.")
        # Expansion/additions may not cross a table line or image boundary.
        if not target or width > region.width + .05:
            for drawing in page.get_drawings():
                rect = fitz.Rect(drawing["rect"]) + (-.5, -.5, .5, .5)
                if insertion.intersects(rect) and not insertion in rect:
                    raise EditError("확장 영역이 도형/표 경계와 겹칩니다.")
            for image in page.get_image_info():
                rect = fitz.Rect(image["bbox"])
                if insertion.intersects(rect) and not insertion in rect:
                    raise EditError("확장 영역이 이미지 경계와 겹칩니다.")
        for rect in redactions:
            edited.add_redact_annot(rect, fill=False, cross_out=False)
        if redactions:
            edited.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE, text=fitz.PDF_REDACT_TEXT_REMOVE)
        if characters(analyze(edited)) != others:
            raise EditError("선택 영역 외 문자가 제거되거나 기존 문자가 남아 적용을 취소했습니다.")
        if _graphics(page) != _graphics(edited):
            raise EditError("표·도형·이미지 정보가 달라져 적용을 취소했습니다.")
        # Background + vector preservation is checked before inserting new text, everywhere.
        verify_outside(page, edited, region)
        if text:
            alias = "PosidEdit" + hashlib.sha256(font.buffer).hexdigest()[:12]
            edited.insert_font(fontname=alias, fontbuffer=font.buffer)
            rgb = ((color >> 16 & 255) / 255, (color >> 8 & 255) / 255, (color & 255) / 255)
            edited.insert_text(origin, text, fontname=alias, fontsize=size, color=rgb)
        after_runs = analyze(edited)
        after_chars = characters(after_runs)
        if not others <= after_chars:
            raise EditError("주변 문자의 추출 결과가 달라졌습니다.")
        added = after_chars - others
        extracted = "".join(c for run in after_runs for c, b, o in zip(run.chars, run.boxes, run.origins)
                            if _char_key(c, b, o) in added)
        if extracted != text:
            raise EditError("삽입 텍스트의 추출 검증에 실패했습니다. 다른 글꼴을 선택하세요.")
        verify_outside(page, edited, area)
        # Redaction must not remove pre-existing links/annotations.
        if page.get_links() != edited.get_links():
            raise EditError("링크 정보가 변경되어 적용을 취소했습니다.")
        result = work.tobytes(garbage=4, deflate=True)
        with fitz.open(stream=result, filetype="pdf") as reopened:
            if characters(analyze(reopened[page_number])) != after_chars:
                raise EditError("저장 후 텍스트가 달라졌습니다.")
            if _render(reopened[page_number]).samples != _render(edited).samples:
                raise EditError("저장 후 화면 검증에 실패했습니다.")
        return result, EditCommand(page_number, target.text if target else "", text, tuple(area),
                                   font.name if font else "", size, color, bool(font_path))


class EditSession:
    """Disk snapshots give exact multi-step undo, including destructive redactions."""
    def __init__(self, path, password="", executor=None):
        self.source_path = Path(path).resolve()
        self.executor = executor
        source = self.source_path.read_bytes()
        self.page_count, self.restriction = self.call(inspect_document, source, password)
        self.password = password
        self.storage = tempfile.TemporaryDirectory(prefix="posid-edit-")
        self.snapshots = []
        self.commands = []
        self.index = 0
        self.revision = 0
        self._append_snapshot(source)
        self.saved_digest = hashlib.sha256(source).digest()
        self.digests = [self.saved_digest]
        self.last_saved_path = None

    def call(self, function, *args, **kwargs):
        if self.executor:
            return self.executor.submit(function, *args, **kwargs).result()
        return function(*args, **kwargs)

    def _append_snapshot(self, data):
        path = Path(self.storage.name) / f"{self.revision}-{len(self.snapshots)}.pdf"
        path.write_bytes(data)
        self.snapshots.append(path)

    @property
    def data(self):
        return self.snapshots[self.index].read_bytes()

    @property
    def dirty(self):
        return self.digests[self.index] != self.saved_digest

    def prepare(self, page, target, text, **options):
        if self.restriction:
            raise EditError(self.restriction)
        if target and target.revision != self.revision:
            raise EditError("이전 상태의 선택입니다. 텍스트를 다시 선택하세요.")
        return self.call(edit_document, self.data, page, target, text, **options)

    def commit(self, prepared):
        data, command = prepared
        # Write successfully before altering undo/redo history.
        fd, name = tempfile.mkstemp(prefix="state-", suffix=".pdf", dir=self.storage.name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
        except Exception:
            os.unlink(name)
            raise
        self.revision += 1
        for path in self.snapshots[self.index + 1:]:
            path.unlink()
        self.snapshots = self.snapshots[:self.index + 1]
        self.commands = self.commands[:self.index]
        self.digests = self.digests[:self.index + 1]
        self.snapshots.append(Path(name))
        self.digests.append(hashlib.sha256(data).digest())
        self.commands.append(command)
        self.index += 1

    def undo(self):
        if self.index:
            self.index -= 1
            self.revision += 1

    def redo(self):
        if self.index < len(self.commands):
            self.index += 1
            self.revision += 1

    def save_as(self, destination):
        if self.restriction:
            raise EditError(self.restriction)
        target = Path(destination).resolve()
        if target == self.source_path or (target.exists() and os.path.samefile(target, self.source_path)):
            raise EditError("원본 파일에는 저장할 수 없습니다. 다른 파일명을 선택하세요.")
        data = self.data
        fd, name = tempfile.mkstemp(prefix=".posid-", suffix=".pdf", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            self.call(validate_saved, name, data, self.page_count,
                      {c.page for c in self.commands[:self.index]})
            os.replace(name, target)
            self.saved_digest = hashlib.sha256(data).digest()
            self.last_saved_path = target
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def close(self):
        self.password = ""
        self.storage.cleanup()


def validate_saved(name, data, page_count, changed_pages):
    with fitz.open(name) as saved, fitz.open(stream=data, filetype="pdf") as current:
        if saved.page_count != page_count:
            raise EditError("저장된 페이지 수가 다릅니다.")
        for i in range(saved.page_count):
            if (saved[i].rect != current[i].rect or saved[i].cropbox != current[i].cropbox
                    or saved[i].rotation != current[i].rotation
                    or saved[i].mediabox != current[i].mediabox):
                raise EditError("저장된 페이지 크기가 다릅니다.")
        for i in changed_pages:
            if characters(analyze(saved[i])) != characters(analyze(current[i])):
                raise EditError("저장된 텍스트 검증에 실패했습니다.")
            if _render(saved[i]).samples != _render(current[i]).samples:
                raise EditError("저장된 화면 검증에 실패했습니다.")
