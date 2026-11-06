"""PDF 파일 열기 공통 헬퍼 — 마지막 폴더 기억, 오류 메시지, 다중 선택 지원."""
from __future__ import annotations

import os
from pathlib import Path

import pymupdf as fitz
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from app.common.user_prefs import load_dir, save_dir

OPEN_DIR_KEY = "open/last_pdf_dir"


def _remember_dir(path: str):
    if path:
        save_dir(OPEN_DIR_KEY, str(Path(path).parent))


def open_pdf_dialog(parent: QWidget, title: str = "PDF 파일 선택", multi: bool = False) -> list[str]:
    """PDF 선택 대화상자. 마지막 폴더를 기억한다.

    multi=False 이면 최대 1개, True 이면 여러 개 선택 가능.
    """
    start = load_dir(OPEN_DIR_KEY) or ""
    if multi:
        paths, _ = QFileDialog.getOpenFileNames(parent, title, start, "PDF Files (*.pdf)")
    else:
        path, _ = QFileDialog.getOpenFileName(parent, title, start, "PDF Files (*.pdf)")
        paths = [path] if path else []
    if paths:
        _remember_dir(paths[0])
    return [p for p in paths if p]


def explain_open_error(path: str, exc: Exception | None = None) -> str:
    """열기 실패 원인을 사용자 친화적으로 설명한다."""
    name = Path(path).name if path else "파일"
    if not path or not os.path.exists(path):
        return f"'{name}' 파일을 찾을 수 없습니다."
    if not os.access(path, os.R_OK):
        return f"'{name}' 파일을 읽을 권한이 없습니다."
    msg = str(exc or "")
    lower = msg.lower()
    if "password" in lower or "encrypt" in lower or "encrypted" in lower:
        return f"'{name}'은(는) 암호화된 PDF입니다. 암호를 입력해야 열 수 있습니다."
    if "damaged" in lower or "corrupt" in lower or "invalid" in lower:
        return f"'{name}' 파일이 손상되었거나 올바른 PDF 형식이 아닙니다."
    return f"'{name}'을(를) 열 수 없습니다.\n{msg}" if msg else f"'{name}'을(를) 열 수 없습니다."


def try_open_pdf(path: str, password: str = "") -> tuple[fitz.Document | None, str]:
    """PDF를 열고 (doc, error_message)를 반환한다. 실패 시 doc=None."""
    try:
        doc = fitz.open(path)
        if doc.needs_pass:
            if password:
                if not doc.authenticate(password):
                    doc.close()
                    return None, explain_open_error(path, Exception("password"))
            else:
                doc.close()
                return None, explain_open_error(path, Exception("encrypted"))
        return doc, ""
    except Exception as exc:
        return None, explain_open_error(path, exc)


def show_open_error(parent: QWidget, path: str, message: str):
    QMessageBox.warning(parent, "PDF 열기 실패", message)
