from dataclasses import dataclass, field
from datetime import datetime
import re


class FormError(ValueError):
    """사용자 안내용 PDF 양식 처리 예외."""


FIELD_TYPE_LABELS = {
    "text": "한 줄 입력란",
    "multiline": "여러 줄 입력란",
    "date": "날짜 입력란",
    "checkbox": "체크박스",
    "radio": "라디오 버튼",
    "combobox": "드롭다운 목록",
    "listbox": "목록 상자",
    "signature": "전자서명",
    "button": "버튼",
}

CREATABLE_FIELD_TYPES = (
    ("text", "한 줄 입력란", "이름, 연락처, 주소 등의 문자열 입력"),
    ("multiline", "여러 줄 입력란", "의견, 비고, 상세 내용"),
    ("date", "날짜 입력란", "YYYY-MM-DD 형식의 날짜 입력"),
    ("checkbox", "체크박스", "동의 여부, 항목 선택"),
    ("radio", "라디오 버튼", "여러 선택지 중 하나 선택"),
    ("combobox", "드롭다운 목록", "사전에 정한 항목 중 선택"),
    ("listbox", "목록 상자", "목록 형태로 선택"),
)

FIELD_TYPE_PREFIXES = {
    "text": "text",
    "multiline": "multiline",
    "date": "date",
    "checkbox": "checkbox",
    "radio": "radio",
    "combobox": "dropdown",
    "listbox": "listbox",
}

ALIGN_LABELS = {
    0: "왼쪽 정렬",
    1: "가운데 정렬",
    2: "오른쪽 정렬",
}

_DATE_PATTERNS = (
    ("%Y-%m-%d", re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    ("%Y.%m.%d", re.compile(r"^\d{4}\.\d{2}\.\d{2}$")),
    ("%Y/%m/%d", re.compile(r"^\d{4}/\d{2}/\d{2}$")),
    ("%Y%m%d", re.compile(r"^\d{8}$")),
)


def validate_date_string(value: str) -> tuple[bool, str]:
    """날짜 문자열이 유효한지 검증하고 정규화된 YYYY-MM-DD 문자열을 반환한다."""
    text = (value or "").strip()
    if not text:
        return True, ""
    for fmt, pattern in _DATE_PATTERNS:
        if pattern.match(text):
            try:
                parsed = datetime.strptime(text, fmt)
                return True, parsed.strftime("%Y-%m-%d")
            except ValueError:
                return False, "존재하지 않는 날짜입니다. 예: 2026-05-01"
    return False, "날짜 형식이 올바르지 않습니다. 예: 2026-05-01"


def normalize_bool_value(raw, on_state: str = "Yes") -> tuple[bool, bool]:
    """외부 입력값을 체크박스용 bool로 변환한다. (성공 여부, bool 값) 반환."""
    if isinstance(raw, bool):
        return True, raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return True, bool(raw)
    text = str(raw if raw is not None else "").strip()
    lower = text.lower()
    on_lower = (on_state or "Yes").lower()
    if lower in ("1", "true", "yes", "y", "on", "checked", "체크", "선택", "동의", "예", on_lower):
        return True, True
    if lower in ("0", "false", "no", "n", "off", "unchecked", "", "미선택", "해제", "비동의", "아니오"):
        return True, False
    return False, False


@dataclass
class WidgetInstance:
    xref: int
    page_index: int
    rect: tuple[float, float, float, float]
    field_name: str
    field_label: str
    field_type: str
    value: object
    default_value: str = ""
    required: bool = False
    read_only: bool = False
    no_export: bool = False
    is_password: bool = False
    max_len: int = 0
    choices: list[str] = field(default_factory=list)
    on_state: str = "Yes"
    button_states: list[str] = field(default_factory=list)
    button_caption: str = ""
    font_size: float = 11.0
    text_color: tuple[float, float, float] = (0.1, 0.1, 0.1)
    fill_color: tuple[float, float, float] | None = None
    border_color: tuple[float, float, float] | None = None
    border_width: float = 0.0
    align: int = 0
    is_signed: bool | None = None

    @property
    def display_name(self) -> str:
        return (self.field_label or "").strip() or self.field_name

    @property
    def type_label(self) -> str:
        return FIELD_TYPE_LABELS.get(self.field_type, self.field_type)


@dataclass
class LogicalField:
    field_name: str
    field_label: str
    field_type: str
    value: object
    default_value: str = ""
    required: bool = False
    read_only: bool = False
    no_export: bool = False
    is_password: bool = False
    max_len: int = 0
    choices: list[str] = field(default_factory=list)
    radio_options: list[str] = field(default_factory=list)
    widgets: list[WidgetInstance] = field(default_factory=list)
    is_signed: bool | None = None

    @property
    def display_name(self) -> str:
        return (self.field_label or "").strip() or self.field_name

    @property
    def type_label(self) -> str:
        return FIELD_TYPE_LABELS.get(self.field_type, self.field_type)

    @property
    def pages(self) -> list[int]:
        return sorted({w.page_index + 1 for w in self.widgets})

    @property
    def hierarchy_path(self) -> list[str]:
        """점(.) 구분 필드명을 계층 경로로 해석한다. (예: applicant.name -> ['applicant', 'name'])"""
        parts = [part.strip() for part in (self.field_name or "").split(".") if part.strip()]
        return parts if len(parts) > 1 else []

    @property
    def parent_group(self) -> str:
        """계층이 있으면 상위 그룹명, 없으면 빈 문자열."""
        path = self.hierarchy_path
        return path[0] if path else ""

    @property
    def leaf_name(self) -> str:
        path = self.hierarchy_path
        return path[-1] if path else self.field_name

    @property
    def is_shared_value(self) -> bool:
        """동일 논리 필드가 여러 위치에 있는 경우 (라디오 제외)."""
        return len(self.widgets) > 1 and self.field_type != "radio"

    @property
    def primary_page(self) -> int:
        return self.pages[0] if self.pages else 1

    @property
    def primary_widget(self) -> WidgetInstance | None:
        return self.widgets[0] if self.widgets else None

    @property
    def editable(self) -> bool:
        return not self.read_only and self.field_type not in ("signature", "button")

    def is_filled(self) -> bool:
        """사용자가 값을 작성했는지 판정한다.
        체크박스는 선택하지 않는 것(False)도 유효한 상태이나,
        필수(required) 체크박스인 경우에는 체크(True)되어야 필수 항목 충족으로 본다.
        """
        if self.field_type == "checkbox":
            if self.required:
                return bool(self.value is True)
            return True
        if self.field_type == "radio":
            val = str(self.value or "").strip()
            return bool(val and val != "Off")
        text = str(self.value if self.value is not None else "").strip()
        return bool(text)

    def validate_candidate_value(self, raw_value) -> tuple[bool, object, str]:
        """외부/사용자 입력값이 이 논리 필드에 유효한지 검사한다.
        반환: (성공여부, 정규화된 값, 오류 사유)
        """
        if self.field_type in ("signature", "button"):
            return False, None, "지원하지 않는 필드 유형입니다."
        if self.read_only:
            return False, None, "읽기 전용 필드입니다."

        if self.field_type == "checkbox":
            on_state = self.primary_widget.on_state if self.primary_widget else "Yes"
            ok, bval = normalize_bool_value(raw_value, on_state)
            if not ok:
                return False, None, f"체크박스 값 형식 오류: '{raw_value}'"
            return True, bval, ""

        if self.field_type == "radio":
            text = str(raw_value if raw_value is not None else "").strip()
            if not text or text.lower() in ("off", "false", "0", "미선택"):
                return True, "", ""
            if text in self.radio_options:
                return True, text, ""
            return False, None, f"라디오 선택 목록에 없는 값입니다 ({', '.join(self.radio_options)})"

        if self.field_type in ("combobox", "listbox"):
            text = str(raw_value if raw_value is not None else "").strip()
            if not text:
                return True, "", ""
            if self.choices and text not in self.choices:
                return False, None, f"선택 목록에 없는 값입니다 ({', '.join(self.choices)})"
            return True, text, ""

        text = str(raw_value if raw_value is not None else "")
        if self.field_type != "multiline":
            text = text.replace("\r\n", " ").replace("\n", " ").strip()
        if self.max_len and self.max_len > 0 and len(text) > self.max_len:
            return False, None, f"최대 글자 수({self.max_len}자)를 초과했습니다 ({len(text)}자)"
        if self.field_type == "date":
            ok, normalized = validate_date_string(text)
            if not ok:
                return False, None, normalized
            return True, normalized, ""
        return True, text, ""


@dataclass
class ImportCandidateItem:
    source_key: str
    raw_value: object
    target_field_name: str | None
    status: str  # matched, unmatched_data, read_only, unsupported_type, invalid_format, invalid_choice
    normalized_value: object = None
    reason: str = ""


@dataclass
class ImportAnalysis:
    items: list[ImportCandidateItem] = field(default_factory=list)
    missing_pdf_fields: list[str] = field(default_factory=list)

    @property
    def matched_items(self) -> list[ImportCandidateItem]:
        return [item for item in self.items if item.status == "matched"]

    def count_by_status(self, status: str) -> int:
        return sum(1 for item in self.items if item.status == status)
