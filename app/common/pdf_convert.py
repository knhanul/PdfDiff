import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pymupdf

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
TEXT_EXTS = {".txt", ".csv", ".log"}
MARKDOWN_EXTS = {".md", ".markdown"}
XML_OFFICE_EXTS = {".docx", ".xlsx", ".pptx", ".hwpx"}
EXTERNAL_EXTS = {".doc", ".xls", ".ppt", ".hwp", ".rtf", ".odt", ".ods", ".odp"}
SUPPORTED_EXTS = IMAGE_EXTS | TEXT_EXTS | MARKDOWN_EXTS | XML_OFFICE_EXTS | EXTERNAL_EXTS

A4 = (595.0, 842.0)


def is_supported(path):
    return Path(path).suffix.lower() in SUPPORTED_EXTS


def read_text_file(path):
    data = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def unique_pdf_path(directory, stem):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stem}.pdf"
    if not candidate.exists():
        return candidate
    number = 2
    while True:
        candidate = directory / f"{stem}_{number}.pdf"
        if not candidate.exists():
            return candidate
        number += 1


def convert_to_pdf(src, out_dir):
    src = Path(src)
    ext = src.suffix.lower()
    dest = unique_pdf_path(out_dir, src.stem)
    if ext in IMAGE_EXTS:
        _image_to_pdf(src, dest)
    elif ext in TEXT_EXTS:
        _text_to_pdf(read_text_file(src), dest)
    elif ext in MARKDOWN_EXTS:
        _markdown_to_pdf(read_text_file(src), dest)
    elif ext in XML_OFFICE_EXTS or ext in EXTERNAL_EXTS:
        if not _try_external_convert(src, dest):
            if ext == ".docx":
                _text_to_pdf(_docx_text(src), dest)
            elif ext == ".xlsx":
                _text_to_pdf(_xlsx_text(src), dest)
            elif ext == ".pptx":
                _text_to_pdf(_pptx_text(src), dest)
            elif ext == ".hwpx":
                _text_to_pdf(_hwpx_text(src), dest)
            else:
                raise RuntimeError(
                    "이 형식은 LibreOffice 또는 한글/오피스가 설치되어 있어야 PDF로 변환할 수 있습니다."
                )
    else:
        raise RuntimeError("지원하지 않는 형식입니다.")
    return dest


def _image_to_pdf(src, dest):
    doc = pymupdf.open()
    page = doc.new_page(width=A4[0], height=A4[1])
    page.insert_image(page.rect, filename=str(src), keep_proportion=True)
    doc.save(dest)
    doc.close()


def _text_to_pdf(text, dest):
    font = pymupdf.Font("korea")
    fontsize = 11
    margin = 48
    width, height = A4
    max_width = width - margin * 2
    line_gap = fontsize * 1.45
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    y = margin + fontsize
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        pieces = _wrap(font, raw_line, fontsize, max_width) or [""]
        for piece in pieces:
            if y > height - margin:
                page = doc.new_page(width=width, height=height)
                y = margin + fontsize
            page.insert_text((margin, y), piece, fontname="korea", fontsize=fontsize)
            y += line_gap
    if doc.page_count == 0:
        doc.new_page(width=width, height=height)
    doc.save(dest)
    doc.close()


def _markdown_to_pdf(text, dest):
    font = pymupdf.Font("korea")
    margin = 48
    width, height = A4
    max_width = width - margin * 2
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    y = margin

    def new_page():
        nonlocal page, y
        page = doc.new_page(width=width, height=height)
        y = margin

    def draw(line, fontsize, gap):
        nonlocal y
        if y + gap > height - margin:
            new_page()
        page.insert_text((margin, y + fontsize), line, fontname="korea", fontsize=fontsize)
        y += gap

    for kind, content in _markdown_blocks(text):
        if kind == "h":
            level, title = content
            size = {1: 18, 2: 15}.get(level, 13)
            for line in _wrap(font, title, size, max_width):
                draw(line, size, size * 1.5)
            y += 4
        elif kind == "code":
            for line in content.split("\n"):
                for piece in _wrap(font, line, 10, max_width):
                    draw(piece, 10, 15)
            y += 6
        elif kind == "list":
            for item in content:
                for index, piece in enumerate(_wrap(font, item, 11, max_width - 16)):
                    prefix = "• " if index == 0 else "  "
                    draw(prefix + piece, 11, 16)
            y += 4
        else:
            for piece in _wrap(font, content, 11, max_width):
                draw(piece, 11, 16)
            y += 6
    doc.save(dest)
    doc.close()


def _markdown_blocks(text):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            code = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                code.append(lines[index])
                index += 1
            blocks.append(("code", "\n".join(code)))
            index += 1
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            blocks.append(("h", (min(level, 3), line[level:].strip())))
            index += 1
            continue
        if line.startswith(("- ", "* ")):
            items = []
            while index < len(lines) and lines[index].startswith(("- ", "* ")):
                items.append(lines[index][2:].strip())
                index += 1
            blocks.append(("list", items))
            continue
        if not line.strip():
            index += 1
            continue
        paragraph = [line.strip()]
        index += 1
        while index < len(lines) and lines[index].strip() and not lines[index].startswith(("#", "- ", "* ", "```")):
            paragraph.append(lines[index].strip())
            index += 1
        blocks.append(("p", " ".join(paragraph)))
    return blocks


def _wrap(font, text, fontsize, max_width):
    if text is None:
        return []
    if font.text_length(text, fontsize=fontsize) <= max_width:
        return [text]
    lines = []
    current = ""
    for char in text:
        trial = current + char
        if current and font.text_length(trial, fontsize=fontsize) > max_width:
            lines.append(current)
            current = char
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def _try_external_convert(src, dest):
    if _convert_with_soffice(src, dest):
        return True
    return _convert_with_com(src, dest)


def _soffice_path():
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    candidates = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def _convert_with_soffice(src, dest):
    soffice = _soffice_path()
    if not soffice:
        return False
    with tempfile.TemporaryDirectory() as temp_dir:
        result = subprocess.run(
            [soffice, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", temp_dir, str(src)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        produced = Path(temp_dir) / f"{Path(src).stem}.pdf"
        if result.returncode != 0 or not produced.exists():
            return False
        shutil.move(str(produced), dest)
    return True


def _convert_with_com(src, dest):
    if os.name != "nt":
        return False
    try:
        import win32com.client
    except ImportError:
        return False
    ext = Path(src).suffix.lower()
    src_text = str(src)
    dest_text = str(dest)
    if ext in {".hwp", ".hwpx"}:
        return _convert_hwp_com(win32com, src_text, dest_text)
    if ext in {".doc", ".docx", ".rtf"}:
        return _convert_word_com(win32com, src_text, dest_text)
    if ext in {".xls", ".xlsx"}:
        return _convert_excel_com(win32com, src_text, dest_text)
    if ext in {".ppt", ".pptx"}:
        return _convert_powerpoint_com(win32com, src_text, dest_text)
    return False


def _convert_word_com(win32com, src, dest):
    app = None
    try:
        app = win32com.client.Dispatch("Word.Application")
        app.Visible = False
        document = app.Documents.Open(src)
        document.SaveAs(dest, FileFormat=17)
        document.Close(False)
        return Path(dest).exists()
    except Exception:
        return False
    finally:
        if app is not None:
            app.Quit()


def _convert_excel_com(win32com, src, dest):
    app = None
    try:
        app = win32com.client.Dispatch("Excel.Application")
        app.Visible = False
        app.DisplayAlerts = False
        workbook = app.Workbooks.Open(src)
        workbook.ExportAsFixedFormat(0, dest)
        workbook.Close(False)
        return Path(dest).exists()
    except Exception:
        return False
    finally:
        if app is not None:
            app.Quit()


def _convert_powerpoint_com(win32com, src, dest):
    app = None
    try:
        app = win32com.client.Dispatch("PowerPoint.Application")
        presentation = app.Presentations.Open(src, WithWindow=False)
        presentation.SaveAs(dest, 32)
        presentation.Close()
        return Path(dest).exists()
    except Exception:
        return False
    finally:
        if app is not None:
            app.Quit()


def _convert_hwp_com(win32com, src, dest):
    app = None
    try:
        app = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
        app.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        app.Open(src)
        action = app.HParameterSet.HFileOpenSave
        app.HAction.GetDefault("FileSaveAs_S", action.HSet)
        action.filename = dest
        action.Format = "PDF"
        app.HAction.Execute("FileSaveAs_S", action.HSet)
        app.Clear(1)
        return Path(dest).exists()
    except Exception:
        return False
    finally:
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass


def _xml_text(path, inner_path, paragraph_tag, text_tag):
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read(inner_path))
    paragraphs = []
    for paragraph in root.iter(paragraph_tag):
        texts = [node.text or "" for node in paragraph.iter(text_tag)]
        paragraphs.append("".join(texts))
    return "\n".join(paragraphs).strip()


def _docx_text(path):
    text = _xml_text(
        path,
        "word/document.xml",
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p",
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t",
    )
    if not text:
        raise RuntimeError("워드 문서에서 텍스트를 읽지 못했습니다.")
    return text


def _xlsx_text(path):
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.iter(f"{ns}si"):
                shared.append("".join(node.text or "" for node in item.iter(f"{ns}t")))
        sheets = sorted(name for name in names if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))
        blocks = []
        for sheet in sheets:
            root = ET.fromstring(archive.read(sheet))
            rows = []
            for row in root.iter(f"{ns}row"):
                values = []
                for cell in row.findall(f"{ns}c"):
                    value = cell.find(f"{ns}v")
                    if cell.get("t") == "s" and value is not None and value.text:
                        values.append(shared[int(value.text)])
                    elif cell.get("t") == "inlineStr":
                        values.append("".join(node.text or "" for node in cell.iter(f"{ns}t")))
                    elif value is not None and value.text:
                        values.append(value.text)
                if values:
                    rows.append("\t".join(values))
            if rows:
                blocks.append(f"[{Path(sheet).stem}]\n" + "\n".join(rows))
    text = "\n\n".join(blocks).strip()
    if not text:
        raise RuntimeError("엑셀 문서에서 텍스트를 읽지 못했습니다.")
    return text


def _pptx_text(path):
    tag = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
    with zipfile.ZipFile(path) as archive:
        slides = sorted(name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
        blocks = []
        for index, slide in enumerate(slides, start=1):
            root = ET.fromstring(archive.read(slide))
            lines = [node.text for node in root.iter(tag) if node.text]
            if lines:
                blocks.append(f"[슬라이드 {index}]\n" + "\n".join(lines))
    text = "\n\n".join(blocks).strip()
    if not text:
        raise RuntimeError("프레젠테이션에서 텍스트를 읽지 못했습니다.")
    return text


def _hwpx_text(path):
    with zipfile.ZipFile(path) as archive:
        sections = sorted(name for name in archive.namelist() if name.startswith("Contents/section") and name.endswith(".xml"))
        paragraphs = []
        for section in sections:
            root = ET.fromstring(archive.read(section))
            for paragraph in root.iter():
                if not paragraph.tag.endswith("}p"):
                    continue
                texts = [node.text or "" for node in paragraph.iter() if node.tag.endswith("}t") and node.text]
                if texts:
                    paragraphs.append("".join(texts))
    text = "\n".join(paragraphs).strip()
    if not text:
        raise RuntimeError("한글 문서에서 텍스트를 읽지 못했습니다.")
    return text
