from pathlib import Path

import pymupdf


def collect_images(path, include_thumb=False):
    """PDF에 포함된 이미지를 페이지 순서로 모은다. 같은 이미지는 한 번만 담는다."""
    doc = pymupdf.open(path)
    found = {}
    order = []
    try:
        if doc.is_encrypted and not doc.authenticate(""):
            raise RuntimeError("암호가 걸린 PDF는 이미지를 추출할 수 없습니다.")
        for page_index in range(doc.page_count):
            for image in doc.get_page_images(page_index):
                xref = image[0]
                page_no = page_index + 1
                if xref in found:
                    if page_no not in found[xref]["pages"]:
                        found[xref]["pages"].append(page_no)
                    continue
                try:
                    info = doc.extract_image(xref)
                except Exception:
                    continue
                raw = info.get("image") or b""
                if not raw:
                    continue
                found[xref] = {
                    "path": str(path),
                    "xref": xref,
                    "pages": [page_no],
                    "ext": (info.get("ext") or "png").lower(),
                    "width": int(info.get("width") or 0),
                    "height": int(info.get("height") or 0),
                    "nbytes": len(raw),
                    "thumb": _thumbnail(doc, xref) if include_thumb else b"",
                }
                order.append(xref)
    finally:
        doc.close()
    return [found[xref] for xref in order]


def save_image(doc, xref, dest):
    info = doc.extract_image(xref)
    raw = info.get("image") if info else None
    if not raw:
        raise RuntimeError("이미지 데이터를 읽지 못했습니다.")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return dest


def _thumbnail(doc, xref):
    try:
        pix = pymupdf.Pixmap(doc, xref)
        if pix.colorspace is not None and pix.n - pix.alpha > 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        while max(pix.width, pix.height) > 96 and min(pix.width, pix.height) > 2:
            pix.shrink(1)
        return pix.tobytes("png")
    except Exception:
        return b""
