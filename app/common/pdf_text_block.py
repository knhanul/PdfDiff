"""텍스트 블록 추출 및 편집 미리보기 헬퍼.

기존 PDF 편집(페이지 단위) 기능을 유지하면서,
사용자가 텍스트 블록을 선택하고 수정 결과를 미리 확인할 수 있도록 한다.
"""
from __future__ import annotations

from typing import Any

import pymupdf as fitz


def extract_text_blocks(doc: fitz.Document, page_index: int) -> list[dict[str, Any]]:
    """페이지에서 텍스트 블록을 추출한다.

    Returns list of:
        {page, bbox, text, font_size, font_name, color, block_type}
    추출 가능한 정보만 채우고, 없는 정보는 None으로 둔다.
    """
    if page_index < 0 or page_index >= len(doc):
        return []
    page = doc[page_index]
    blocks = []
    try:
        # dict 모드로 더 자세한 정보 시도
        d = page.get_text("dict") or {}
        for b in d.get("blocks", []):
            if b.get("type") != 0:  # 텍스트 블록만
                continue
            text_parts = []
            font_size = None
            font_name = None
            color = None
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    text_parts.append(span.get("text", ""))
                    if font_size is None and span.get("size"):
                        font_size = float(span["size"])
                    if font_name is None and span.get("font"):
                        font_name = str(span["font"])
                    if color is None and "color" in span:
                        color = span["color"]
            text = "".join(text_parts).strip()
            if not text:
                continue
            blocks.append({
                "page": page_index,
                "bbox": tuple(b.get("bbox", (0, 0, 0, 0))),
                "text": text,
                "font_size": font_size,
                "font_name": font_name,
                "color": color,
                "block_type": "text",
            })
    except Exception:
        # 폴백: blocks 모드
        for b in page.get_text("blocks") or []:
            if len(b) >= 5 and b[4]:
                blocks.append({
                    "page": page_index,
                    "bbox": tuple(b[:4]),
                    "text": str(b[4]).strip(),
                    "font_size": None,
                    "font_name": None,
                    "color": None,
                    "block_type": "text",
                })
    return blocks


def preview_text_edit(block: dict, new_text: str) -> dict[str, Any]:
    """편집 결과를 미리 분석한다.

    Returns:
        {
            "original": str,
            "new": str,
            "length_change": int,
            "exceeds_area": bool,   # 단순 길이 기준 추정
            "warning": str | None,
        }
    """
    original = block.get("text") or ""
    new = new_text or ""
    len_diff = len(new) - len(original)
    # 간단한 추정: 길이가 30% 이상 늘어나면 영역 초과 가능성
    exceeds = len(new) > len(original) * 1.3 and len(new) > 20
    warning = None
    if exceeds:
        warning = "수정한 글자가 원본보다 길어 영역 밖으로 나갈 수 있습니다."
    elif len(new) == 0:
        warning = "내용이 비어 있습니다. 블록이 삭제될 수 있습니다."
    return {
        "original": original,
        "new": new,
        "length_change": len_diff,
        "exceeds_area": exceeds,
        "warning": warning,
        "font_size": block.get("font_size"),
        "font_name": block.get("font_name"),
    }
