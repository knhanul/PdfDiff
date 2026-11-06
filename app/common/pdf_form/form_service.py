from collections import OrderedDict
import hashlib
import os
from pathlib import Path
import re
import tempfile

import pymupdf as fitz

from app.common.resources import _runtime_base_path
from app.common.pdf_form.field_models import (
    FIELD_TYPE_PREFIXES,
    FormError,
    LogicalField,
    WidgetInstance,
    validate_date_string,
)


def decode_pdf_name(name: str) -> str:
    """PDF Name 객체의 #XX 16진수 시퀀스를 UTF-8 문자열로 복원한다."""
    if not name or "#" not in str(name):
        return str(name or "")
    text = str(name)
    raw = bytearray()
    i = 0
    while i < len(text):
        if text[i] == "#" and i + 2 < len(text):
            try:
                raw.append(int(text[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        raw.extend(text[i].encode("utf-8"))
        i += 1
    return raw.decode("utf-8", errors="replace")


def encode_pdf_name_token(value: str) -> str:
    """PDF Name 토큰(/키)으로 안전하게 쓸 수 있도록 공백/특수문자/비ASCII를 #XX로 인코딩한다."""
    text = (value or "").strip() or "Yes"
    out = []
    for byte in text.encode("utf-8"):
        if 33 <= byte <= 126 and chr(byte) not in "#()/[]<>%{}\\ ":
            out.append(chr(byte))
        else:
            out.append(f"#{byte:02X}")
    return "".join(out)


def _clean_pdf_string(kind: str, val: str) -> str:
    if kind != "string" or not val:
        return ""
    if val.startswith("(") and val.endswith(")"):
        return val[1:-1]
    return val


def detect_xfa(doc: fitz.Document) -> bool:
    """실제 /Root/AcroForm/XFA 항목이 존재하는 경우에만 True를 반환한다."""
    try:
        kind, val = doc.xref_get_key(-1, "Root/AcroForm/XFA")
        return kind in ("array", "stream", "xref", "dict") and val not in ("null", "")
    except Exception:
        return False


class FormDocumentSession:
    """PDF 양식(AcroForm) 열기·편집·작성·추출·저장을 담당하는 공통 세션."""

    def __init__(self, path: str | Path, password: str = ""):
        self.source_path = Path(path).resolve()
        if not self.source_path.exists():
            raise FormError("PDF 파일을 찾을 수 없습니다.")
        try:
            raw = self.source_path.read_bytes()
        except OSError as exc:
            raise FormError(f"PDF 파일을 읽을 수 없습니다: {exc}") from exc

        try:
            doc = fitz.open(stream=raw, filetype="pdf")
        except Exception as exc:
            raise FormError("유효한 PDF 문서가 아니거나 손상된 파일입니다.") from exc

        self.needs_password = bool(doc.needs_pass)
        self.is_encrypted = bool(doc.needs_pass or doc.is_encrypted)
        if doc.needs_pass:
            if not password or not doc.authenticate(password):
                doc.close()
                raise FormError("암호가 필요하거나 입력한 암호가 올바르지 않습니다.")
            raw = doc.tobytes()
        if not doc.is_pdf or doc.page_count == 0:
            doc.close()
            raise FormError("유효한 PDF 페이지가 없습니다.")

        self.password = password
        self.can_modify = bool(doc.permissions & fitz.PDF_PERM_MODIFY)
        self.is_xfa = detect_xfa(doc)
        self.sig_flags = int(doc.get_sigflags() or 0)
        doc.close()

        self._snapshots: list[bytes] = [raw]
        self._descriptions: list[str] = ["문서 열기"]
        self._index = 0
        self._saved_digest = hashlib.sha256(raw).digest()
        self.last_saved_path: Path | None = None
        self._doc: fitz.Document | None = None
        self._reopen_current()

    def _reopen_current(self):
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass
        self._doc = fitz.open(stream=self._snapshots[self._index], filetype="pdf")
        if self._doc.needs_pass and self.password:
            self._doc.authenticate(self.password)

    @property
    def doc(self) -> fitz.Document:
        if self._doc is None or self._doc.is_closed:
            self._reopen_current()
        return self._doc

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    @property
    def current_bytes(self) -> bytes:
        return self._snapshots[self._index]

    @property
    def dirty(self) -> bool:
        return hashlib.sha256(self.current_bytes).digest() != self._saved_digest

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        return self._index + 1 < len(self._snapshots)

    def _commit_current_doc(self, description: str):
        data = self.doc.tobytes(garbage=2, deflate=True)
        self._snapshots = self._snapshots[:self._index + 1]
        self._descriptions = self._descriptions[:self._index + 1]
        self._snapshots.append(data)
        self._descriptions.append(description)
        self._index += 1
        self._reopen_current()

    def undo(self) -> bool:
        if not self.can_undo:
            return False
        self._index -= 1
        self._reopen_current()
        return True

    def redo(self) -> bool:
        if not self.can_redo:
            return False
        self._index += 1
        self._reopen_current()
        return True

    def signature_status(self) -> tuple[bool, bool]:
        """(서명 필드 존재 여부, 실제 서명 완료 여부)를 반환한다."""
        has_sig_field = False
        has_signed = False
        for page in self.doc:
            for w in page.widgets() or []:
                if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    has_sig_field = True
                    if w.is_signed:
                        has_signed = True
        return has_sig_field, has_signed

    def restriction_message(self) -> str:
        """문서 차원의 제한/주의 안내 메시지를 반환한다."""
        if not self.can_modify:
            return "이 PDF에는 편집 권한 제한이 설정되어 있어 양식 생성·수정이 제한됩니다."
        if self.is_xfa:
            return "이 문서는 XFA 기반 동적 양식을 포함하고 있습니다. 본 도구는 표준 AcroForm 양식만 지원합니다."
        has_sig, has_signed = self.signature_status()
        if has_signed:
            return "전자서명이 완료된 문서입니다. 양식을 수정하거나 필드를 변경하면 기존 서명의 유효성이 훼손될 수 있습니다."
        if has_sig:
            return "전자서명 입력란이 포함된 문서입니다. 서명 필드는 열람만 가능하며 일반 입력란만 작성할 수 있습니다."
        return ""

    def ensure_modifiable(self, allow_signed: bool = False):
        if not self.can_modify:
            raise FormError("이 PDF 문서에는 편집 권한이 없어 변경할 수 없습니다.")
        if self.is_xfa:
            raise FormError("XFA 양식 문서는 편집을 지원하지 않습니다.")
        _, has_signed = self.signature_status()
        if has_signed and not allow_signed:
            raise FormError("전자서명이 완료된 PDF는 서명 무결성 보호를 위해 양식 수정을 차단합니다.")

    def _read_widget_instance(self, page: fitz.Page, w: fitz.Widget) -> WidgetInstance:
        doc = self.doc
        xref = int(w.xref)
        ft = w.field_type
        flags = int(w.field_flags or 0)
        required = bool(flags & fitz.PDF_FIELD_IS_REQUIRED)
        read_only = bool(flags & fitz.PDF_FIELD_IS_READ_ONLY)
        no_export = bool(flags & fitz.PDF_FIELD_IS_NO_EXPORT)
        is_password = False

        sub_kind, sub_val = doc.xref_get_key(xref, "PosidSubType")
        custom_subtype = _clean_pdf_string(sub_kind, sub_val)

        if ft == fitz.PDF_WIDGET_TYPE_TEXT:
            is_password = bool(flags & fitz.PDF_TX_FIELD_IS_PASSWORD)
            if flags & fitz.PDF_TX_FIELD_IS_MULTILINE:
                field_type = "multiline"
            elif custom_subtype == "date" or w.text_format == fitz.PDF_WIDGET_TX_FORMAT_DATE:
                field_type = "date"
            else:
                field_type = "text"
        elif ft == fitz.PDF_WIDGET_TYPE_CHECKBOX:
            field_type = "checkbox"
        elif ft == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
            field_type = "radio"
        elif ft == fitz.PDF_WIDGET_TYPE_COMBOBOX:
            field_type = "combobox"
        elif ft == fitz.PDF_WIDGET_TYPE_LISTBOX:
            field_type = "listbox"
        elif ft == fitz.PDF_WIDGET_TYPE_SIGNATURE:
            field_type = "signature"
        else:
            field_type = "button"

        raw_on = w.on_state() if ft in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON) else "Yes"
        on_state = decode_pdf_name(raw_on) if isinstance(raw_on, str) else "Yes"
        bstates_dict = w.button_states() or {}
        normal_states = [decode_pdf_name(s) for s in (bstates_dict.get("normal") or []) if s]

        if field_type == "checkbox":
            raw_val = w.field_value
            is_checked = (
                raw_val is True
                or decode_pdf_name(str(raw_val or "")) in (on_state, "Yes", "True", "1")
            )
            value: object = bool(is_checked)
        elif field_type == "radio":
            as_kind, as_val = doc.xref_get_key(xref, "AS")
            as_name = decode_pdf_name(as_val[1:] if as_kind == "name" and as_val.startswith("/") else str(w.field_value or ""))
            value = "" if as_name in ("", "Off", "False") else as_name
        else:
            value = str(w.field_value or "")

        dv_kind, dv_val = doc.xref_get_key(xref, "DV")
        if dv_kind == "string":
            default_value = _clean_pdf_string(dv_kind, dv_val)
        elif dv_kind == "name":
            default_value = decode_pdf_name(dv_val.lstrip("/"))
        else:
            default_value = ""

        q_kind, q_val = doc.xref_get_key(xref, "Q")
        align = int(q_val) if q_kind == "int" and q_val in ("0", "1", "2") else 0

        raw_choices = w.choice_values or []
        choices = []
        for item in raw_choices:
            if isinstance(item, (tuple, list)) and item:
                choices.append(str(item[0]))
            else:
                choices.append(str(item))

        tcol = tuple(float(c) for c in (w.text_color or (0.1, 0.1, 0.1)))
        if len(tcol) == 1:
            tcol = (tcol[0], tcol[0], tcol[0])
        elif len(tcol) != 3:
            tcol = (0.1, 0.1, 0.1)

        fcol = tuple(float(c) for c in w.fill_color) if w.fill_color and len(w.fill_color) == 3 else None
        bcol = tuple(float(c) for c in w.border_color) if w.border_color and len(w.border_color) == 3 else None

        # PyMuPDF는 BS/W가 0이어도 widget.border_width를 1로 돌려주는 경우가 있어 xref를 우선한다.
        bw_kind, bw_val = doc.xref_get_key(xref, "BS/W")
        if bw_kind in ("float", "int") and bw_val not in ("", None):
            border_width = float(bw_val)
        else:
            border_width = float(w.border_width if w.border_width is not None else 0.0)

        rect = w.rect
        return WidgetInstance(
            xref=xref,
            page_index=page.number,
            rect=(float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)),
            field_name=str(w.field_name or f"field_{xref}"),
            field_label=str(w.field_label or ""),
            field_type=field_type,
            value=value,
            default_value=default_value,
            required=required,
            read_only=read_only,
            no_export=no_export,
            is_password=is_password,
            max_len=int(w.text_maxlen or 0),
            choices=choices,
            on_state=on_state or "Yes",
            button_states=normal_states,
            button_caption=str(w.button_caption or ""),
            font_size=float(w.text_fontsize or 11.0),
            text_color=tcol,
            fill_color=fcol,
            border_color=bcol,
            border_width=border_width,
            align=align,
            is_signed=w.is_signed,
        )

    def list_widgets(self, page_index: int | None = None) -> list[WidgetInstance]:
        items: list[WidgetInstance] = []
        pages = [self.doc[page_index]] if page_index is not None else list(self.doc)
        for page in pages:
            for w in page.widgets() or []:
                items.append(self._read_widget_instance(page, w))
        return items

    def get_widget_by_xref(self, xref: int) -> WidgetInstance | None:
        for w in self.list_widgets():
            if w.xref == xref:
                return w
        return None

    def list_logical_fields(self) -> list[LogicalField]:
        grouped: OrderedDict[str, list[WidgetInstance]] = OrderedDict()
        for item in self.list_widgets():
            grouped.setdefault(item.field_name, []).append(item)

        fields: list[LogicalField] = []
        for fname, widgets in grouped.items():
            first = widgets[0]
            # 계층형 필드명(점 구분)이면 마지막 부분을 기본 라벨로 사용
            leaf = fname.split(".")[-1] if "." in fname else fname
            label = next((w.field_label for w in widgets if w.field_label), "") or leaf
            required = any(w.required for w in widgets)
            read_only = all(w.read_only for w in widgets)
            no_export = any(w.no_export for w in widgets)
            is_password = any(w.is_password for w in widgets)
            is_signed = any(bool(w.is_signed) for w in widgets) if first.field_type == "signature" else None

            if first.field_type == "radio":
                radio_options = []
                selected_val = ""
                for w in widgets:
                    opt = w.on_state or w.button_caption or f"option_{len(radio_options) + 1}"
                    if opt not in radio_options:
                        radio_options.append(opt)
                    if w.value and str(w.value) != "Off":
                        selected_val = str(w.value)
                value: object = selected_val
            elif first.field_type == "checkbox":
                value = any(bool(w.value) for w in widgets)
                radio_options = []
            else:
                value = next((w.value for w in widgets if str(w.value or "") != ""), first.value)
                radio_options = []

            fields.append(
                LogicalField(
                    field_name=fname,
                    field_label=label,
                    field_type=first.field_type,
                    value=value,
                    default_value=first.default_value,
                    required=required,
                    read_only=read_only,
                    no_export=no_export,
                    is_password=is_password,
                    max_len=first.max_len,
                    choices=list(first.choices),
                    radio_options=radio_options,
                    widgets=widgets,
                    is_signed=is_signed,
                )
            )
        return fields

    def get_logical_field(self, field_name: str) -> LogicalField | None:
        for lf in self.list_logical_fields():
            if lf.field_name == field_name:
                return lf
        return None

    def generate_unique_field_name(self, field_type: str) -> str:
        prefix = FIELD_TYPE_PREFIXES.get(field_type, "field")
        existing = {w.field_name for w in self.list_widgets()}
        index = 1
        while True:
            candidate = f"{prefix}_{index:03d}"
            if candidate not in existing:
                return candidate
            index += 1

    def _clamp_rect_to_page(
        self, page_index: int, rect: tuple[float, float, float, float], min_size: float = 14.0
    ) -> fitz.Rect:
        page = self.doc[page_index]
        bounds = page.rect
        x0, y0, x1, y1 = float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        width = max(min_size, min(x1 - x0, bounds.width))
        height = max(min_size, min(y1 - y0, bounds.height))
        x0 = max(bounds.x0, min(x0, bounds.x1 - width))
        y0 = max(bounds.y0, min(y0, bounds.y1 - height))
        return fitz.Rect(x0, y0, x0 + width, y0 + height)

    def _set_radio_widget_option_state(self, xref: int, option_value: str, selected: bool):
        token = encode_pdf_name_token(option_value)
        ap_n = self.doc.xref_get_key(xref, "AP/N")
        off_ref = self.doc.xref_get_key(xref, "AP/N/Off")
        on_ref = ("null", "")
        if ap_n[0] == "dict":
            matches = re.findall(r"/([^\s/<>]+)\s+(\d+\s+0\s+R)", ap_n[1])
            for key_name, ref_str in matches:
                if key_name != "Off":
                    on_ref = ("xref", ref_str)
                    break
        if off_ref[0] == "xref" and on_ref[0] == "xref":
            self.doc.xref_set_key(xref, "AP/N", f"<</Off {off_ref[1]}/{token} {on_ref[1]}>>")
        if selected:
            self.doc.xref_set_key(xref, "AS", f"/{token}")
            self.doc.xref_set_key(xref, "V", f"/{token}")
        else:
            self.doc.xref_set_key(xref, "AS", "/Off")
            self.doc.xref_set_key(xref, "V", "/Off")


    def link_as_alias(self, source_xref: int, target_field_name: str) -> WidgetInstance:
        """선택한 위젯을 기존 논리 필드와 동일한 값을 공유하도록 연결한다 (Widget Alias).

        필드명을 동일하게 맞추고, 유형이 호환되는 경우에만 허용한다.
        """
        self.ensure_modifiable()
        source = self.get_widget_by_xref(source_xref)
        if source is None:
            raise FormError("연결할 입력란을 찾을 수 없습니다.")
        target_name = (target_field_name or "").strip()
        if not target_name:
            raise FormError("연결할 대상 필드명을 지정하세요.")
        existing = {lf.field_name: lf for lf in self.list_logical_fields()}
        if target_name not in existing:
            raise FormError(f"대상 필드 '{target_name}'을(를) 찾을 수 없습니다.")
        target_lf = existing[target_name]
        if source.field_type != target_lf.field_type:
            raise FormError(
                f"유형이 다릅니다. 원본은 {source.type_label}, 대상은 {target_lf.type_label}입니다."
            )
        if source.field_type == "radio":
            raise FormError("라디오 버튼은 '라디오 그룹'으로 연결하세요. Alias 연결은 텍스트·체크박스 등에 사용합니다.")
        # 필드명만 변경하면 동일 논리 필드로 취급된다
        updated = self.update_widget_properties(
            source_xref,
            field_name=target_name,
            allow_duplicate_name=True,
        )
        self._commit_current_doc(f"동일 값 공유 연결: {target_name}")
        return updated

    def normalize_radio_group(self, field_name: str) -> int:
        """비표준 라디오 그룹의 On/Off 상태를 정리한다.

        같은 field_name을 가진 라디오 위젯들 중 하나만 선택 상태가 되도록 맞추고,
        나머지는 Off로 설정한다. 원본을 직접 덮어쓰지 않고 현재 세션 문서에만 적용한다.
        Returns: 정리한 위젯 수
        """
        self.ensure_modifiable()
        widgets = [w for w in self.list_widgets() if w.field_name == field_name and w.field_type == "radio"]
        if len(widgets) < 2:
            raise FormError("라디오 그룹으로 정리할 항목이 2개 이상 필요합니다.")
        # 현재 선택된 항목 찾기
        selected = None
        for w in widgets:
            if w.value and str(w.value) not in ("", "Off", "False"):
                selected = w
                break
        if selected is None:
            selected = widgets[0]  # 없으면 첫 번째를 기본 선택
        count = 0
        for w in widgets:
            is_sel = (w.xref == selected.xref)
            self._set_radio_widget_option_state(w.xref, w.on_state or "Yes", is_sel)
            count += 1
        self._commit_current_doc(f"라디오 그룹 상태 정리: {field_name}")
        return count

    def add_radio_option(
        self,
        group_field_name: str,
        page_index: int,
        rect: tuple[float, float, float, float],
        option_value: str,
        field_label: str = "",
    ) -> WidgetInstance:
        """기존 라디오 그룹에 새로운 선택 항목을 추가한다."""
        existing = {lf.field_name: lf for lf in self.list_logical_fields()}
        if group_field_name not in existing or existing[group_field_name].field_type != "radio":
            raise FormError(f"'{group_field_name}'은(는) 라디오 그룹이 아닙니다.")
        return self.add_field(
            page_index=page_index,
            rect=rect,
            field_type="radio",
            field_name=group_field_name,
            field_label=field_label or option_value,
            radio_option=option_value,
            allow_duplicate_name=True,
        )


    def _force_clear_widget_border(self, xref: int) -> None:
        """widget.update()가 다시 채운 /BS·/Border·/MK 테두리를 xref에서 강제 제거한다."""
        self.doc.xref_set_key(xref, "BS", "<</W 0 /S /S>>")
        self.doc.xref_set_key(xref, "Border", "[0 0 0]")
        self.doc.xref_set_key(xref, "MK", "<<>>")

    def add_field(
        self,
        page_index: int,
        rect: tuple[float, float, float, float],
        field_type: str = "text",
        field_name: str | None = None,
        field_label: str = "",
        default_value: object = "",
        required: bool = False,
        read_only: bool = False,
        max_len: int = 0,
        choices: list[str] | None = None,
        radio_option: str = "",
        font_size: float = 11.0,
        text_color: tuple[float, float, float] = (0.1, 0.1, 0.1),
        fill_color: tuple[float, float, float] | None = None,
        border_color: tuple[float, float, float] | None = None,
        border_width: float = 0.0,
        align: int = 0,
        allow_duplicate_name: bool = False,
        allow_signed: bool = False,
    ) -> WidgetInstance:
        self.ensure_modifiable(allow_signed=allow_signed)
        if page_index < 0 or page_index >= self.page_count:
            raise FormError("유효하지 않은 페이지 번호입니다.")

        existing_fields = {lf.field_name: lf for lf in self.list_logical_fields()}
        name = (field_name or "").strip() or self.generate_unique_field_name(field_type)
        if name in existing_fields:
            existing_lf = existing_fields[name]
            if field_type == "radio" and existing_lf.field_type == "radio":
                allow_duplicate_name = True
            if not allow_duplicate_name:
                raise FormError(
                    f"필드명 '{name}'이(가) 이미 사용 중입니다. "
                    "같은 값을 공유하거나 라디오 그룹으로 묶으려면 중복 허용 옵션을 선택하세요."
                )
            if existing_lf.field_type != field_type:
                raise FormError(
                    f"이미 다른 유형({existing_lf.type_label})으로 사용 중인 필드명('{name}')입니다."
                )

        clamped_rect = self._clamp_rect_to_page(page_index, rect)
        page = self.doc[page_index]
        w = fitz.Widget()
        w.field_name = name
        w.field_label = (field_label or "").strip() or name
        w.rect = clamped_rect
        w.text_fontsize = float(font_size if font_size is not None else 11.0)
        w.text_color = tuple(text_color or (0.1, 0.1, 0.1))
        # 인쇄 시 테두리/배경이 나오지 않도록 기본은 투명.
        # 텍스트·멀티라인·날짜는 호출 인자와 무관하게 강제 투명.
        if field_type in ("text", "multiline", "date"):
            effective_fill = None
            effective_border = None
            effective_border_width = 0.0
        else:
            # 체크박스/라디오도 기본 투명(체크 표시는 appearance에서 생성).
            effective_fill = fill_color
            effective_border = border_color
            effective_border_width = 0.0 if border_width is None else float(border_width)
        w.fill_color = tuple(effective_fill) if effective_fill else None
        w.border_color = tuple(effective_border) if effective_border else None
        w.border_width = float(effective_border_width)

        flags = 0
        if required:
            flags |= fitz.PDF_FIELD_IS_REQUIRED
        if read_only:
            flags |= fitz.PDF_FIELD_IS_READ_ONLY

        if field_type in ("text", "multiline", "date"):
            w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            if field_type == "multiline":
                flags |= fitz.PDF_TX_FIELD_IS_MULTILINE
            if field_type == "date":
                w.text_format = fitz.PDF_WIDGET_TX_FORMAT_DATE
            if max_len and max_len > 0:
                w.text_maxlen = int(max_len)
            init_str = str(default_value or "")
            if field_type == "date" and init_str:
                ok, normalized = validate_date_string(init_str)
                if not ok:
                    raise FormError(normalized)
                init_str = normalized
            w.field_value = init_str
        elif field_type == "checkbox":
            w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
            w.field_value = bool(default_value) if isinstance(default_value, bool) else str(default_value).lower() in ("true", "1", "yes", "on")
        elif field_type == "radio":
            w.field_type = fitz.PDF_WIDGET_TYPE_RADIOBUTTON
            w.field_value = False
        elif field_type == "combobox":
            w.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX
            opts = [str(c).strip() for c in (choices or ["항목 1", "항목 2"]) if str(c).strip()]
            if not opts:
                opts = ["항목 1"]
            w.choice_values = opts
            w.field_value = str(default_value) if str(default_value or "") in opts else opts[0]
        elif field_type == "listbox":
            w.field_type = fitz.PDF_WIDGET_TYPE_LISTBOX
            opts = [str(c).strip() for c in (choices or ["항목 1", "항목 2"]) if str(c).strip()]
            if not opts:
                opts = ["항목 1"]
            w.choice_values = opts
            w.field_value = str(default_value) if str(default_value or "") in opts else opts[0]
        else:
            raise FormError(f"지원하지 않는 필드 유형입니다: {field_type}")

        w.field_flags = flags
        annot = page.add_widget(w)
        xref = int(annot.xref)
        # 입력값이 인쇄에 포함되도록 PRINT 플래그 유지.
        annot.set_flags(int(annot.flags) | fitz.PDF_ANNOT_IS_PRINT)

        if field_type == "date":
            self.doc.xref_set_key(xref, "PosidSubType", fitz.get_pdf_str("date"))
        if align in (0, 1, 2):
            self.doc.xref_set_key(xref, "Q", str(int(align)))
        if default_value not in (None, "", False):
            self.doc.xref_set_key(xref, "DV", fitz.get_pdf_str(str(default_value)))

        if field_type == "radio":
            existing_count = len([x for x in self.list_widgets() if x.field_name == name])
            opt_name = (radio_option or "").strip() or f"선택_{existing_count}"
            is_selected = bool(default_value is True or (isinstance(default_value, str) and default_value == opt_name))
            if is_selected:
                for other_page in self.doc:
                    for other_w in other_page.widgets() or []:
                        if other_w.field_name == name and int(other_w.xref) != xref:
                            self.doc.xref_set_key(int(other_w.xref), "AS", "/Off")
                            self.doc.xref_set_key(int(other_w.xref), "V", "/Off")
            self._set_radio_widget_option_state(xref, opt_name, is_selected)

        for pw in page.widgets() or []:
            if int(pw.xref) == xref:
                if field_type in ("text", "multiline", "date"):
                    pw.fill_color = None
                    pw.border_color = None
                    pw.border_width = 0.0
                elif field_type in ("checkbox", "radio") and effective_fill is None and effective_border is None:
                    pw.fill_color = None
                    pw.border_color = None
                    pw.border_width = float(effective_border_width)
                # PRINT 플래그는 annot 쪽에 이미 설정됨. appearance 갱신.
                pw.update()
                # update()가 /BS·/MK·/AP 테두리를 다시 만들 수 있어, 직후 xref로 강제 무효화.
                # (이 뒤에는 다시 update()를 호출하면 안 된다 — BS/W가 1로 복원됨.)
                if field_type in ("text", "multiline", "date"):
                    self._force_clear_widget_border(xref)
                elif effective_fill is None and effective_border is None and float(effective_border_width) == 0.0:
                    # 체크·라디오·콤보 등도 기본 투명이면 동일하게 테두리 제거
                    self._force_clear_widget_border(xref)
                break

        self._commit_current_doc(f"입력란 추가 ({w.field_label})")
        created = self.get_widget_by_xref(xref)
        if created is None:
            widgets = [x for x in self.list_widgets(page_index) if x.field_name == name]
            created = widgets[-1]
        return created

    def update_widget_properties(
        self,
        xref: int,
        *,
        rect: tuple[float, float, float, float] | None = None,
        field_name: str | None = None,
        field_label: str | None = None,
        field_type: str | None = None,
        default_value: object = None,
        required: bool | None = None,
        read_only: bool | None = None,
        max_len: int | None = None,
        choices: list[str] | None = None,
        radio_option: str | None = None,
        radio_default_selected: bool | None = None,
        font_size: float | None = None,
        text_color: tuple[float, float, float] | None = None,
        fill_color: tuple[float, float, float] | None = None,
        clear_fill_color: bool = False,
        border_color: tuple[float, float, float] | None = None,
        border_width: float | None = None,
        align: int | None = None,
        allow_duplicate_name: bool = False,
        allow_signed: bool = False,
    ) -> WidgetInstance:
        self.ensure_modifiable(allow_signed=allow_signed)
        current = self.get_widget_by_xref(xref)
        if current is None:
            raise FormError("수정할 입력란을 찾을 수 없습니다.")

        target_name = (field_name if field_name is not None else current.field_name).strip()
        if not target_name:
            raise FormError("내부 필드명은 비워둘 수 없습니다.")
        target_type = field_type or current.field_type

        if target_name != current.field_name:
            other_widgets = [w for w in self.list_widgets() if w.field_name == target_name and w.xref != xref]
            if other_widgets:
                if target_type == "radio" and other_widgets[0].field_type == "radio":
                    allow_duplicate_name = True
                if not allow_duplicate_name:
                    raise FormError(
                        f"필드명 '{target_name}'이(가) 이미 존재합니다. "
                        "동일 값 공유 또는 라디오 그룹 연결인 경우에만 중복 허용을 켜주세요."
                    )

        page = self.doc[current.page_index]
        target_w = next((w for w in page.widgets() or [] if int(w.xref) == xref), None)
        if target_w is None:
            raise FormError("PDF 페이지에서 입력란 객체를 찾을 수 없습니다.")

        if rect is not None:
            target_w.rect = self._clamp_rect_to_page(current.page_index, rect)

        target_w.field_name = target_name
        if field_label is not None:
            target_w.field_label = field_label.strip()

        req = current.required if required is None else bool(required)
        ro = current.read_only if read_only is None else bool(read_only)
        flags = int(target_w.field_flags or 0)
        flags = (flags | fitz.PDF_FIELD_IS_REQUIRED) if req else (flags & ~fitz.PDF_FIELD_IS_REQUIRED)
        flags = (flags | fitz.PDF_FIELD_IS_READ_ONLY) if ro else (flags & ~fitz.PDF_FIELD_IS_READ_ONLY)

        if current.field_type in ("text", "multiline", "date") and target_type in ("text", "multiline", "date"):
            if target_type == "multiline":
                flags |= fitz.PDF_TX_FIELD_IS_MULTILINE
            else:
                flags &= ~fitz.PDF_TX_FIELD_IS_MULTILINE
            if target_type == "date":
                target_w.text_format = fitz.PDF_WIDGET_TX_FORMAT_DATE
                self.doc.xref_set_key(xref, "PosidSubType", fitz.get_pdf_str("date"))
            else:
                target_w.text_format = fitz.PDF_WIDGET_TX_FORMAT_NONE
                self.doc.xref_set_key(xref, "PosidSubType", "null")
        target_w.field_flags = flags

        if max_len is not None and target_type in ("text", "multiline", "date"):
            target_w.text_maxlen = max(0, int(max_len))
            if int(max_len) == 0:
                self.doc.xref_set_key(xref, "MaxLen", "null")

        if font_size is not None:
            target_w.text_fontsize = float(font_size)
        if text_color is not None:
            target_w.text_color = tuple(text_color)
        if clear_fill_color:
            target_w.fill_color = None
            self.doc.xref_set_key(xref, "MK/BG", "null")
        elif fill_color is not None:
            target_w.fill_color = tuple(fill_color)
        if border_color is not None:
            target_w.border_color = tuple(border_color)
        if border_width is not None:
            target_w.border_width = float(border_width)
        if align is not None and align in (0, 1, 2):
            self.doc.xref_set_key(xref, "Q", str(int(align)))

        if choices is not None and current.field_type in ("combobox", "listbox"):
            clean_choices = [str(c).strip() for c in choices if str(c).strip()]
            if not clean_choices:
                raise FormError("선택 목록에는 최소 1개 이상의 항목이 필요합니다.")
            target_w.choice_values = clean_choices
            if str(target_w.field_value or "") not in clean_choices:
                target_w.field_value = clean_choices[0]

        if default_value is not None:
            if current.field_type == "checkbox":
                bval = bool(default_value) if isinstance(default_value, bool) else str(default_value).lower() in ("true", "1", "yes", "on")
                target_w.field_value = bval
                self.doc.xref_set_key(xref, "DV", "/Yes" if bval else "/Off")
            elif current.field_type != "radio":
                dstr = str(default_value)
                if target_type == "date" and dstr:
                    ok, normalized = validate_date_string(dstr)
                    if not ok:
                        raise FormError(normalized)
                    dstr = normalized
                target_w.field_value = dstr
                self.doc.xref_set_key(xref, "DV", fitz.get_pdf_str(dstr))

        target_w.update()

        # update() 직후 텍스트 계열(또는 투명 배경 요청)은 xref로 테두리/배경 강제 제거.
        effective_type = target_type or current.field_type
        want_clear = False
        if effective_type in ("text", "multiline", "date"):
            want_clear = True
        elif clear_fill_color or (
            fill_color is None and border_color is None and border_width is not None and float(border_width) == 0.0
        ):
            want_clear = True
        elif border_width is not None and float(border_width) == 0.0 and clear_fill_color:
            want_clear = True
        if want_clear:
            self._force_clear_widget_border(xref)

        if current.field_type == "radio":
            opt_val = (radio_option.strip() if radio_option is not None else current.on_state) or "Yes"
            is_sel = (
                bool(radio_default_selected)
                if radio_default_selected is not None
                else bool(current.value and current.value != "Off")
            )
            if is_sel:
                for p in self.doc:
                    for ow in p.widgets() or []:
                        if ow.field_name == target_name and int(ow.xref) != xref:
                            self.doc.xref_set_key(int(ow.xref), "AS", "/Off")
                            self.doc.xref_set_key(int(ow.xref), "V", "/Off")
            self._set_radio_widget_option_state(xref, opt_val, is_sel)

        self._commit_current_doc(f"입력란 속성 변경 ({target_w.field_label or target_name})")
        updated = self.get_widget_by_xref(xref)
        if updated is None:
            raise FormError("속성 반영 후 입력란을 다시 읽지 못했습니다.")
        return updated

    def delete_widget(self, xref: int, allow_signed: bool = False):
        self.ensure_modifiable(allow_signed=allow_signed)
        current = self.get_widget_by_xref(xref)
        if current is None:
            raise FormError("삭제할 입력란을 찾을 수 없습니다.")
        if current.field_type == "signature":
            raise FormError("전자서명 필드는 삭제할 수 없습니다.")
        page = self.doc[current.page_index]
        target_w = next((w for w in page.widgets() or [] if int(w.xref) == xref), None)
        if target_w is None:
            raise FormError("페이지에서 삭제할 입력란을 찾을 수 없습니다.")
        page.delete_widget(target_w)
        self._commit_current_doc(f"입력란 삭제 ({current.display_name})")

    def set_field_value(
        self,
        field_name: str,
        raw_value: object,
        *,
        commit: bool = True,
        allow_signed: bool = False,
    ) -> LogicalField:
        self.ensure_modifiable(allow_signed=allow_signed)
        lf = self.get_logical_field(field_name)
        if lf is None:
            raise FormError(f"필드 '{field_name}'을(를) 찾을 수 없습니다.")
        ok, normalized, reason = lf.validate_candidate_value(raw_value)
        if not ok:
            raise FormError(reason)

        for page in self.doc:
            page_changed = False
            for w in page.widgets() or []:
                if w.field_name != field_name:
                    continue
                xref = int(w.xref)
                if lf.field_type == "checkbox":
                    on_name = decode_pdf_name(w.on_state() or "Yes")
                    w.field_value = on_name if normalized else False
                    w.update()
                    page_changed = True
                elif lf.field_type == "radio":
                    w_inst = self._read_widget_instance(page, w)
                    opt = w_inst.on_state
                    selected = bool(normalized and opt == str(normalized))
                    self._set_radio_widget_option_state(xref, opt, selected)
                    page_changed = True
                else:
                    w.field_value = str(normalized)
                    w.update()
                    page_changed = True
            if page_changed:
                self.doc.reload_page(page)

        if commit:
            self._commit_current_doc(f"값 입력 ({lf.display_name})")
        return self.get_logical_field(field_name)

    def set_multiple_field_values(
        self, values: dict[str, object], description: str = "데이터 일괄 입력"
    ) -> tuple[int, list[tuple[str, str]]]:
        """여러 필드 값을 한 번의 스냅샷으로 반영한다. (성공 건수, [(필드명, 오류사유)]) 반환."""
        self.ensure_modifiable()
        applied = 0
        errors: list[tuple[str, str]] = []
        for fname, val in values.items():
            try:
                self.set_field_value(fname, val, commit=False)
                applied += 1
            except FormError as exc:
                errors.append((fname, str(exc)))
        if applied > 0:
            self._commit_current_doc(description)
        return applied, errors

    def render_page_rgb(self, page_index: int, zoom: float = 1.0) -> tuple[bytes, int, int, int]:
        page = self.doc[page_index]
        scale = max(0.25, min(float(zoom), 4.0))
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, colorspace=fitz.csRGB)
        return bytes(pix.samples), pix.width, pix.height, pix.stride

    def _validate_save_destination(self, destination: str | Path, allow_overwrite_source: bool = False) -> Path:
        target = Path(destination).resolve()
        if not allow_overwrite_source:
            try:
                if target == self.source_path or (target.exists() and os.path.samefile(target, self.source_path)):
                    raise FormError(
                        "원본 PDF 보호를 위해 원본 파일과 다른 파일명으로 저장해주세요."
                    )
            except OSError:
                pass
        if not target.parent.exists():
            raise FormError(f"저장할 폴더가 존재하지 않습니다: {target.parent}")
        return target

    def save_form_pdf(self, destination: str | Path, allow_overwrite_source: bool = False) -> Path:
        """편집/입력 가능한 AcroForm 상태를 유지하여 새 파일로 저장한다."""
        self.ensure_modifiable()
        target = self._validate_save_destination(destination, allow_overwrite_source=allow_overwrite_source)
        data = self.doc.tobytes(garbage=3, deflate=True)
        self._atomic_write_pdf(target, data, expect_widgets=len(self.list_widgets()) > 0)
        self._saved_digest = hashlib.sha256(self.current_bytes).digest()
        self.last_saved_path = target
        return target

    def save_baked_pdf(self, destination: str | Path) -> Path:
        """작업 세션은 그대로 유지한 채, 복제본에서 입력 내용을 페이지에 고정(bake)하여 별도 파일로 저장한다."""
        self.ensure_modifiable()
        target = self._validate_save_destination(destination, allow_overwrite_source=False)
        clone = fitz.open(stream=self.current_bytes, filetype="pdf")
        try:
            clone.bake(annots=False, widgets=True)
            baked_bytes = clone.tobytes(garbage=3, deflate=True)
        finally:
            clone.close()
        self._atomic_write_pdf(target, baked_bytes, expect_widgets=False)
        return target

    @staticmethod
    def _atomic_write_pdf(target: Path, data: bytes, expect_widgets: bool):
        fd, tmp_name = tempfile.mkstemp(prefix=".posid-form-", suffix=".pdf", dir=str(target.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            with fitz.open(str(tmp_path)) as check_doc:
                if not check_doc.is_pdf or check_doc.page_count == 0:
                    raise FormError("저장된 PDF 검증에 실패했습니다.")
                if not expect_widgets:
                    remaining = sum(len(list(p.widgets() or [])) for p in check_doc)
                    if remaining != 0:
                        raise FormError("입력 내용 고정 후에도 양식 입력란이 남아 있어 저장을 중단했습니다.")
            os.replace(tmp_path, target)
        except FormError:
            tmp_path.unlink(missing_ok=True)
            raise
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            raise FormError(f"파일을 저장할 수 없습니다 (권한 또는 잠금 확인): {exc}") from exc
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            raise FormError(f"PDF 저장 중 오류가 발생했습니다: {exc}") from exc

    def close(self):
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass
            self._doc = None


def flatten_form_pdf(src: str | Path, dst: str | Path) -> Path:
    """양식 위젯을 페이지에 고정(bake)한 인쇄용 PDF를 만든다.

    ``doc.bake(annots=False, widgets=True)``로 일반 주석은 유지하고
    AcroForm 위젯만 평탄화한다. 원본과 다른 경로로 저장해야 한다.
    """
    source = Path(src)
    target = Path(dst)
    if not source.exists():
        raise FormError(f"원본 PDF를 찾을 수 없습니다: {source}")
    try:
        if source.resolve() == target.resolve():
            raise FormError("원본 PDF와 다른 파일명으로 저장해주세요.")
    except OSError:
        pass
    if not target.parent.exists():
        raise FormError(f"저장할 폴더가 존재하지 않습니다: {target.parent}")

    doc = fitz.open(str(source))
    try:
        doc.bake(annots=False, widgets=True)
        baked = doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()
    FormDocumentSession._atomic_write_pdf(target, baked, expect_widgets=False)
    return target


def get_sample_form_pdf_path() -> Path:
    base = Path(_runtime_base_path())
    candidate = base / "assets" / "sample_form.pdf"
    if candidate.exists():
        return candidate
    local_assets = Path(__file__).resolve().parents[3] / "assets" / "sample_form.pdf"
    return local_assets


def build_sample_form_pdf(dest_path: str | Path) -> Path:
    """요구사항 5절의 6개 필드를 갖춘 실제 AcroForm 예제 PDF를 생성한다."""
    target = Path(dest_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    cjk_font = fitz.Font("cjk")
    page.insert_font(fontname="Kor", fontbuffer=cjk_font.buffer)

    page.draw_rect(fitz.Rect(40, 40, 555, 105), fill=(0.95, 0.94, 0.92), color=(0.82, 0.78, 0.75), width=1)
    page.insert_text((60, 72), "서비스 교육·체험 참가 신청서 (예제 양식)", fontname="Kor", fontsize=17, color=(0.2, 0.18, 0.16))
    page.insert_text((60, 93), "아래 입력란을 클릭해 직접 작성하거나, 데이터 추출·입력 탭에서 엑셀(CSV) 연동이 가능합니다.", fontname="Kor", fontsize=10, color=(0.4, 0.38, 0.36))

    rows = [
        ("이름 *", 135, "신청자 성명을 입력하세요"),
        ("연락처 *", 190, "예: 010-1234-5678"),
        ("신청일", 245, "예: 2026-05-01 (YYYY-MM-DD)"),
        ("성별", 300, "남성               여성"),
        ("신청 분야 *", 355, ""),
        ("개인정보 동의 *", 415, "본 신청서의 개인정보 수집 및 이용에 동의합니다."),
    ]
    for label, y, hint in rows:
        page.draw_rect(fitz.Rect(50, y, 175, y + 36), fill=(0.97, 0.96, 0.95), color=(0.85, 0.83, 0.8), width=0.8)
        page.draw_rect(fitz.Rect(175, y, 545, y + 36), fill=(1, 1, 1), color=(0.85, 0.83, 0.8), width=0.8)
        page.insert_text((62, y + 23), label, fontname="Kor", fontsize=11, color=(0.2, 0.2, 0.2))
        if hint and label in ("성별", "개인정보 동의 *"):
            offset_x = 215 if label == "성별" else 218
            page.insert_text((offset_x, y + 23), hint, fontname="Kor", fontsize=10.5, color=(0.25, 0.25, 0.25))

    tmp_path = target.with_suffix(".tmp.pdf")
    doc.save(str(tmp_path))
    doc.close()

    session = FormDocumentSession(tmp_path)
    try:
        session.add_field(
            0, (188, 141, 420, 165),
            field_type="text",
            field_name="applicant_name",
            field_label="이름",
            default_value="홍길동",
            required=True,
            max_len=40,
        )
        session.add_field(
            0, (188, 196, 420, 220),
            field_type="text",
            field_name="phone",
            field_label="연락처",
            default_value="010-1234-5678",
            required=True,
            max_len=20,
        )
        session.add_field(
            0, (188, 251, 360, 275),
            field_type="date",
            field_name="apply_date",
            field_label="신청일",
            default_value="2026-05-01",
            required=False,
        )
        session.add_field(
            0, (190, 308, 210, 328),
            field_type="radio",
            field_name="gender",
            field_label="성별",
            radio_option="남성",
            default_value="남성",
            allow_duplicate_name=True,
        )
        session.add_field(
            0, (252, 308, 272, 328),
            field_type="radio",
            field_name="gender",
            field_label="성별",
            radio_option="여성",
            default_value="",
            allow_duplicate_name=True,
        )
        session.add_field(
            0, (188, 361, 420, 385),
            field_type="combobox",
            field_name="category",
            field_label="신청 분야",
            choices=["AI 문서 자동화", "데이터 비교·검증", "업무 양식 표준화", "기타"],
            default_value="AI 문서 자동화",
            required=True,
        )
        session.add_field(
            0, (190, 423, 210, 443),
            field_type="checkbox",
            field_name="privacy_agree",
            field_label="개인정보 동의",
            default_value=True,
            required=True,
        )
        session.save_form_pdf(target, allow_overwrite_source=True)
    finally:
        session.close()
        tmp_path.unlink(missing_ok=True)
    return target


def ensure_sample_form_pdf() -> Path:
    path = get_sample_form_pdf_path()
    if path.exists():
        return path
    try:
        return build_sample_form_pdf(path)
    except Exception:
        fallback = Path(tempfile.gettempdir()) / "posid_sample_form.pdf"
        return build_sample_form_pdf(fallback)
