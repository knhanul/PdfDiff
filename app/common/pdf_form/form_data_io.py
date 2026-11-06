import csv
import json
from pathlib import Path

from app.common.pdf_form.field_models import (
    FormError,
    ImportAnalysis,
    ImportCandidateItem,
    LogicalField,
)
from app.common.pdf_form.form_service import FormDocumentSession

CSV_COLUMNS = (
    "field_name",
    "field_label",
    "field_type",
    "value",
    "page",
    "required",
    "read_only",
)


def serialize_field_value_for_export(lf: LogicalField) -> str:
    if lf.is_password:
        return ""
    if lf.field_type == "checkbox":
        return "1" if lf.value is True else "0"
    if lf.value is None:
        return ""
    return str(lf.value)


def build_extraction_rows(
    session: FormDocumentSession, include_restricted: bool = False
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for lf in session.list_logical_fields():
        if not include_restricted and (lf.no_export or lf.is_password or lf.field_type == "signature"):
            continue
        pages_text = ", ".join(str(p) for p in lf.pages)
        locations = [
            {
                "page": w.page_index + 1,
                "rect": [round(v, 2) for v in w.rect],
            }
            for w in lf.widgets
        ]
        rows.append(
            {
                "field_name": lf.field_name,
                "field_label": lf.display_name,
                "field_type": lf.field_type,
                "type_label": lf.type_label,
                "value": serialize_field_value_for_export(lf),
                "raw_value": lf.value if not lf.is_password else "",
                "page": pages_text,
                "required": 1 if lf.required else 0,
                "read_only": 1 if lf.read_only else 0,
                "choices": list(lf.radio_options if lf.field_type == "radio" else lf.choices),
                "widget_count": len(lf.widgets),
                "locations": locations,
            }
        )
    return rows


def export_fields_to_csv(
    session: FormDocumentSession, dest_path: str | Path, include_restricted: bool = False
) -> Path:
    target = Path(dest_path)
    rows = build_extraction_rows(session, include_restricted=include_restricted)
    try:
        with open(target, "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({col: row[col] for col in CSV_COLUMNS})
    except OSError as exc:
        raise FormError(f"CSV 파일을 저장할 수 없습니다: {exc}") from exc
    return target


def export_fields_to_json(
    session: FormDocumentSession, dest_path: str | Path, include_restricted: bool = False
) -> Path:
    target = Path(dest_path)
    rows = build_extraction_rows(session, include_restricted=include_restricted)
    payload = {
        "document": session.source_path.name,
        "page_count": session.page_count,
        "field_count": len(rows),
        "fields": [
            {
                "field_name": r["field_name"],
                "field_label": r["field_label"],
                "field_type": r["field_type"],
                "value": r["raw_value"],
                "page": r["page"],
                "required": bool(r["required"]),
                "read_only": bool(r["read_only"]),
                "choices": r["choices"],
                "locations": r["locations"],
            }
            for r in rows
        ],
    }
    try:
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        raise FormError(f"JSON 파일을 저장할 수 없습니다: {exc}") from exc
    return target


def export_template_csv(session: FormDocumentSession, dest_path: str | Path) -> Path:
    """현재 PDF의 입력 가능한 필드명을 기반으로 빈 입력용 CSV 템플릿(UTF-8 BOM)을 저장한다."""
    target = Path(dest_path)
    editable_fields = [
        lf for lf in session.list_logical_fields()
        if lf.editable and not lf.no_export and not lf.is_password
    ]
    if not editable_fields:
        raise FormError("템플릿으로 내보낼 수 있는 입력 필드가 없습니다.")
    try:
        with open(target, "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for lf in editable_fields:
                writer.writerow(
                    {
                        "field_name": lf.field_name,
                        "field_label": lf.display_name,
                        "field_type": lf.field_type,
                        "value": "",
                        "page": ", ".join(str(p) for p in lf.pages),
                        "required": 1 if lf.required else 0,
                        "read_only": 0,
                    }
                )
    except OSError as exc:
        raise FormError(f"CSV 템플릿을 저장할 수 없습니다: {exc}") from exc
    return target


def load_external_data_file(path: str | Path) -> dict[str, object]:
    """외부 CSV 또는 JSON 파일을 읽어 {키: 값} 사전을 반환한다.
    지원 형식:
    1) CSV (세로형): field_name, value 컬럼을 포함한 행 목록
    2) CSV (가로형): 첫 행이 필드명 헤더이고 둘째 행이 값인 테이블
    3) JSON: {"fields": [{"field_name": ..., "value": ...}]} 또는 {"field_name": "value", ...}
    """
    source = Path(path)
    if not source.exists():
        raise FormError("가져올 데이터 파일을 찾을 수 없습니다.")

    suffix = source.suffix.lower()
    if suffix == ".json":
        try:
            raw_text = source.read_text(encoding="utf-8-sig")
            parsed = json.loads(raw_text)
        except Exception as exc:
            raise FormError(f"JSON 파일을 읽을 수 없습니다: {exc}") from exc

        result: dict[str, object] = {}
        if isinstance(parsed, dict):
            if isinstance(parsed.get("fields"), list):
                for entry in parsed["fields"]:
                    if isinstance(entry, dict) and entry.get("field_name"):
                        result[str(entry["field_name"]).strip()] = entry.get("value", "")
            else:
                for k, v in parsed.items():
                    if isinstance(v, dict) and "value" in v:
                        result[str(k).strip()] = v["value"]
                    elif not isinstance(v, (list, dict)):
                        result[str(k).strip()] = v
        elif isinstance(parsed, list):
            for entry in parsed:
                if isinstance(entry, dict) and entry.get("field_name"):
                    result[str(entry["field_name"]).strip()] = entry.get("value", "")
        else:
            raise FormError("지원하지 않는 JSON 구조입니다.")
        return result

    if suffix == ".csv":
        raw_bytes = source.read_bytes()
        text = None
        for enc in ("utf-8-sig", "cp949", "utf-8"):
            try:
                text = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise FormError("CSV 파일 문자 인코딩을 해석할 수 없습니다.")

        rows = list(csv.reader(text.splitlines()))
        rows = [r for r in rows if any(cell.strip() for cell in r)]
        if not rows:
            raise FormError("CSV 파일에 데이터가 없습니다.")

        headers = [h.strip() for h in rows[0]]
        lower_headers = [h.lower() for h in headers]

        if "field_name" in lower_headers and "value" in lower_headers:
            fn_idx = lower_headers.index("field_name")
            val_idx = lower_headers.index("value")
            result = {}
            for row in rows[1:]:
                if len(row) <= max(fn_idx, val_idx):
                    continue
                key = row[fn_idx].strip()
                if key:
                    result[key] = row[val_idx]
            return result

        if len(rows) >= 2:
            values_row = rows[1]
            return {
                headers[i]: (values_row[i] if i < len(values_row) else "")
                for i in range(len(headers))
                if headers[i]
            }
        raise FormError("CSV 파일에서 필드명과 값을 찾을 수 없습니다.")

    raise FormError("지원하지 않는 파일 형식입니다. CSV 또는 JSON 파일을 선택하세요.")


def analyze_import_data(
    session: FormDocumentSession,
    external_data: dict[str, object],
    manual_mapping: dict[str, str | None] | None = None,
) -> ImportAnalysis:
    """외부 데이터와 현재 PDF의 필드를 매칭하고 적용 전 유효성을 검증한다.
    자동 매칭은 내부 필드명(field_name) 정확 일치만 수행하며 임의 추정하지 않는다.
    """
    fields_by_name = {lf.field_name: lf for lf in session.list_logical_fields()}
    mapping = manual_mapping or {}
    items: list[ImportCandidateItem] = []
    targeted_pdf_fields: set[str] = set()

    for src_key, raw_val in external_data.items():
        if src_key in mapping:
            target_name = mapping[src_key]
        elif src_key in fields_by_name:
            target_name = src_key
        else:
            target_name = None

        if not target_name:
            items.append(
                ImportCandidateItem(
                    source_key=src_key,
                    raw_value=raw_val,
                    target_field_name=None,
                    status="unmatched_data",
                    reason="일치하는 PDF 필드가 없습니다 (수동 연결 가능)",
                )
            )
            continue

        lf = fields_by_name.get(target_name)
        if lf is None:
            items.append(
                ImportCandidateItem(
                    source_key=src_key,
                    raw_value=raw_val,
                    target_field_name=target_name,
                    status="unmatched_data",
                    reason=f"PDF에 '{target_name}' 필드가 없습니다.",
                )
            )
            continue

        targeted_pdf_fields.add(lf.field_name)
        if lf.field_type in ("signature", "button"):
            items.append(
                ImportCandidateItem(
                    source_key=src_key,
                    raw_value=raw_val,
                    target_field_name=lf.field_name,
                    status="unsupported_type",
                    reason=f"지원하지 않는 필드 유형({lf.type_label})",
                )
            )
            continue

        if lf.read_only:
            items.append(
                ImportCandidateItem(
                    source_key=src_key,
                    raw_value=raw_val,
                    target_field_name=lf.field_name,
                    status="read_only",
                    reason="읽기 전용 필드입니다.",
                )
            )
            continue

        ok, normalized, reason = lf.validate_candidate_value(raw_val)
        if not ok:
            status = "invalid_choice" if lf.field_type in ("combobox", "listbox", "radio") else "invalid_format"
            items.append(
                ImportCandidateItem(
                    source_key=src_key,
                    raw_value=raw_val,
                    target_field_name=lf.field_name,
                    status=status,
                    reason=reason,
                )
            )
            continue

        items.append(
            ImportCandidateItem(
                source_key=src_key,
                raw_value=raw_val,
                target_field_name=lf.field_name,
                status="matched",
                normalized_value=normalized,
                reason="정상 매칭",
            )
        )

    missing_pdf = [
        lf.field_name
        for lf in session.list_logical_fields()
        if lf.editable and lf.field_name not in targeted_pdf_fields
    ]
    return ImportAnalysis(items=items, missing_pdf_fields=missing_pdf)


def apply_import_analysis(
    session: FormDocumentSession, analysis: ImportAnalysis
) -> tuple[int, list[ImportCandidateItem]]:
    """검증 통과(matched) 항목만 PDF에 반영하고 실패/제외 항목 목록을 함께 반환한다."""
    values_to_apply = {
        item.target_field_name: item.normalized_value
        for item in analysis.matched_items
        if item.target_field_name
    }
    skipped = [item for item in analysis.items if item.status != "matched"]
    if not values_to_apply:
        return 0, skipped
    applied_count, runtime_errors = session.set_multiple_field_values(
        values_to_apply, description="외부 데이터 자동 입력"
    )
    for fname, err in runtime_errors:
        skipped.append(
            ImportCandidateItem(
                source_key=fname,
                raw_value=values_to_apply.get(fname),
                target_field_name=fname,
                status="invalid_format",
                reason=err,
            )
        )
    return applied_count, skipped


def collect_fields_from_multiple_pdfs(
    pdf_paths: list[str | Path],
    include_restricted: bool = False,
) -> tuple[list[dict[str, object]], list[str]]:
    """동일한 양식의 여러 PDF에서 필드 값을 추출해 테이블 행 목록으로 반환한다.

    Returns:
        (rows, warnings)
        rows: [{"filename": ..., "field_name": ..., "value": ..., ...}, ...]
    """
    rows: list[dict[str, object]] = []
    warnings: list[str] = []
    field_sets: list[set[str]] = []

    for path in pdf_paths:
        path = Path(path)
        try:
            session = FormDocumentSession(path)
            try:
                fields = session.list_logical_fields()
                names = {lf.field_name for lf in fields}
                field_sets.append(names)
                for lf in fields:
                    if not include_restricted and (lf.no_export or lf.is_password or lf.field_type == "signature"):
                        continue
                    rows.append(
                        {
                            "filename": path.name,
                            "field_name": lf.field_name,
                            "field_label": lf.display_name,
                            "field_type": lf.field_type,
                            "value": serialize_field_value_for_export(lf),
                            "pages": ", ".join(str(p) for p in lf.pages),
                            "required": "Y" if lf.required else "N",
                            "shared_locations": len(lf.widgets),
                        }
                    )
            finally:
                session.close()
        except Exception as exc:
            warnings.append(f"{path.name}: {exc}")

    if len(field_sets) > 1:
        base = field_sets[0]
        for i, s in enumerate(field_sets[1:], start=2):
            if s != base:
                warnings.append(f"파일 {i}의 필드 구조가 첫 번째 파일과 다릅니다.")

    return rows, warnings


def export_collected_rows_to_csv(rows: list[dict], dest_path: str | Path) -> Path:
    dest = Path(dest_path)
    if not rows:
        raise FormError("내보낼 데이터가 없습니다.")
    fieldnames = list(rows[0].keys())
    with dest.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return dest
