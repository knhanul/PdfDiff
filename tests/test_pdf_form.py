import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as fitz
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtWidgets import QApplication

from app.common.pdf_form import (
    FormDocumentSession,
    FormError,
    analyze_import_data,
    apply_import_analysis,
    ensure_sample_form_pdf,
    export_fields_to_csv,
    export_fields_to_json,
    export_template_csv,
    load_external_data_file,
)
from app.main_window import MdiMainWindow
from app.tools.pdf_form import PdfFormWidget


class PdfFormEngineAndUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_plain_pdf(self, pages: int = 2, rotation: int = 0) -> Path:
        path = self.root / "plain.pdf"
        with fitz.open() as doc:
            for i in range(pages):
                p = doc.new_page(width=595, height=842)
                p.insert_text((50, 60), f"Plain Page {i + 1}", fontsize=14)
                if rotation:
                    p.set_rotation(rotation)
            doc.save(str(path))
        return path

    # 테스트 1 — 일반 PDF에 양식 생성 (텍스트, 여러줄, 날짜, 체크박스, 라디오, 드롭다운, 목록상자)
    def test_1_create_fields_on_plain_pdf_and_reopen(self):
        src = self.make_plain_pdf(pages=2)
        session = FormDocumentSession(src)
        self.addCleanup(session.close)

        w_text = session.add_field(
            0, (100, 100, 300, 126),
            field_type="text",
            field_name="user_name",
            field_label="신청자 이름",
            default_value="홍길동",
            required=True,
            max_len=30,
        )
        self.assertEqual(w_text.field_name, "user_name")
        self.assertEqual(w_text.field_label, "신청자 이름")
        self.assertTrue(w_text.required)

        # 중복 필드명은 기본적으로 차단
        with self.assertRaises(FormError):
            session.add_field(0, (100, 140, 300, 166), field_type="text", field_name="user_name")

        w_cb = session.add_field(
            0, (100, 180, 122, 202),
            field_type="checkbox",
            field_name="agree_terms",
            field_label="약관 동의",
            default_value=True,
        )
        self.assertTrue(w_cb.value)

        w_combo = session.add_field(
            0, (100, 220, 280, 248),
            field_type="combobox",
            field_name="dept",
            field_label="부서",
            choices=["기획팀", "개발팀", "디자인팀"],
            default_value="개발팀",
        )
        self.assertEqual(w_combo.value, "개발팀")

        w_list = session.add_field(
            1, (100, 100, 280, 160),
            field_type="listbox",
            field_name="city",
            field_label="근무 지역",
            choices=["서울특별시", "나주시", "부산광역시"],
            default_value="나주시",
        )
        self.assertEqual(w_list.page_index, 1)

        # 저장 시 원본 덮어쓰기 차단 확인
        with self.assertRaises(FormError):
            session.save_form_pdf(src)

        saved_path = self.root / "created_form.pdf"
        session.save_form_pdf(saved_path)
        self.assertFalse(session.dirty)

        reopened = FormDocumentSession(saved_path)
        self.addCleanup(reopened.close)
        fields = {lf.field_name: lf for lf in reopened.list_logical_fields()}
        self.assertEqual(set(fields.keys()), {"user_name", "agree_terms", "dept", "city"})
        self.assertEqual(fields["user_name"].value, "홍길동")
        self.assertTrue(fields["agree_terms"].value)
        self.assertEqual(fields["dept"].choices, ["기획팀", "개발팀", "디자인팀"])
        self.assertEqual(fields["city"].primary_page, 2)

    # 테스트 2 — 필드 위치 조정, 크기 변경, 삭제, Undo/Redo, 확대/축소·회전 좌표 변환
    def test_2_move_resize_delete_undo_and_coordinate_transform(self):
        src = self.make_plain_pdf(pages=2, rotation=90)
        session = FormDocumentSession(src)
        self.addCleanup(session.close)

        w = session.add_field(0, (80, 90, 220, 120), field_type="text", field_name="f_move", field_label="이동 테스트")
        # 이동 및 크기 변경 (페이지 경계 밖 좌표도 안전하게 클램핑됨)
        moved = session.update_widget_properties(w.xref, rect=(-50, 150, 310, 190))
        self.assertGreaterEqual(moved.rect[0], 0.0)
        self.assertAlmostEqual(moved.rect[1], 150.0, places=1)

        # 삭제 및 Undo / Redo 확인
        session.delete_widget(moved.xref)
        self.assertEqual(len(session.list_widgets(0)), 0)
        self.assertTrue(session.undo())
        self.assertEqual(len(session.list_widgets(0)), 1)
        self.assertTrue(session.redo())
        self.assertEqual(len(session.list_widgets(0)), 0)

        # 캔버스 확대/축소 및 회전 상태 좌표 왕복 검증
        ui = PdfFormWidget()
        self.addCleanup(ui.close)
        ui.load_pdf(src)
        for zoom in (0.75, 1.0, 1.5):
            ui.viewer_pane.set_zoom(zoom)
            canvas = ui.viewer_pane.canvas
            orig = (100.0, 120.0, 260.0, 155.0)
            vrect = canvas.pdf_rect_to_view(orig)
            roundtrip = canvas.view_rect_to_pdf(vrect)
            for a, b in zip(orig, roundtrip):
                self.assertAlmostEqual(a, b, delta=1.5)

    # 테스트 3 — 양식 작성 (한글/영문/특수문자, 여러줄, 체크박스, 라디오, 드롭다운) 및 재열기
    def test_3_fill_various_korean_strings_and_controls(self):
        sample = ensure_sample_form_pdf()
        session = FormDocumentSession(sample)
        self.addCleanup(session.close)

        # 여러 줄 필드 추가 후 다양한 한글 문자열 입력 테스트
        session.add_field(0, (50, 480, 500, 560), field_type="multiline", field_name="memo", field_label="비고")

        for korean_text in (
            "홍길동",
            "서울특별시",
            "가나다라마바사",
            "한글과 English 혼합",
            "2026-11-02 (특수문자 !@#$%)",
        ):
            session.set_field_value("applicant_name", korean_text)
            self.assertEqual(session.get_logical_field("applicant_name").value, korean_text)

        multiline_val = "첫째 줄: 서울특별시 나주시\n둘째 줄: 한글과 English 12345!"
        session.set_field_value("memo", multiline_val)
        session.set_field_value("privacy_agree", False)
        session.set_field_value("gender", "여성")
        session.set_field_value("category", "업무 양식 표준화")
        session.set_field_value("apply_date", "2026.10.15")  # YYYY-MM-DD로 정규화

        filled_path = self.root / "filled_sample.pdf"
        session.save_form_pdf(filled_path)

        reopened = FormDocumentSession(filled_path)
        self.addCleanup(reopened.close)
        lf_map = {lf.field_name: lf for lf in reopened.list_logical_fields()}
        self.assertEqual(lf_map["applicant_name"].value, "2026-11-02 (특수문자 !@#$%)")
        self.assertIn("첫째 줄: 서울특별시 나주시", lf_map["memo"].value)
        self.assertFalse(lf_map["privacy_agree"].value)
        self.assertEqual(lf_map["gender"].value, "여성")
        self.assertEqual(lf_map["category"].value, "업무 양식 표준화")
        self.assertEqual(lf_map["apply_date"].value, "2026-10-15")

    # 테스트 4 & 5 — 데이터 추출(CSV UTF-8 BOM / JSON) 및 외부 데이터 자동·수동 매칭/오류 검증
    def test_4_and_5_data_extract_and_import_matching(self):
        sample = ensure_sample_form_pdf()
        session = FormDocumentSession(sample)
        self.addCleanup(session.close)

        # 동일 논리 필드를 1페이지에 하나 더 배치해 반복 필드 공유 테스트
        session.add_field(
            0, (430, 141, 540, 165),
            field_type="text",
            field_name="applicant_name",
            field_label="이름",
            allow_duplicate_name=True,
        )
        session.set_field_value("applicant_name", "이순신")

        # 읽기 전용 필드 추가
        session.add_field(
            0, (188, 465, 360, 488),
            field_type="text",
            field_name="doc_code",
            field_label="문서 번호",
            default_value="DOC-001",
            read_only=True,
        )

        csv_path = self.root / "export.csv"
        json_path = self.root / "export.json"
        tpl_path = self.root / "template.csv"

        export_fields_to_csv(session, csv_path, include_restricted=True)
        export_fields_to_json(session, json_path, include_restricted=True)
        export_template_csv(session, tpl_path)

        # CSV UTF-8 BOM 확인
        raw_csv = csv_path.read_bytes()
        self.assertTrue(raw_csv.startswith(b"\xef\xbb\xbf"))
        loaded_csv = load_external_data_file(csv_path)
        self.assertEqual(loaded_csv["applicant_name"], "이순신")

        loaded_json = json.loads(json_path.read_text(encoding="utf-8"))
        name_entry = next(f for f in loaded_json["fields"] if f["field_name"] == "applicant_name")
        self.assertEqual(len(name_entry["locations"]), 2)

        # 외부 데이터 가져오기 검증 (정상 매칭, 매칭 실패, 읽기 전용, 선택지 오류, 날짜 형식 오류)
        ext_data = {
            "applicant_name": "강감찬",
            "custom_phone_col": "010-9999-8888",   # 미매칭 -> 수동 매칭 테스트용
            "doc_code": "HACK-999",               # 읽기 전용
            "category": "존재하지않는분야",          # 선택 목록 오류
            "apply_date": "잘못된날짜",              # 값 형식 오류
            "privacy_agree": "동의",               # 체크박스 정규화 True
            "gender": "남성",
        }
        analysis = analyze_import_data(session, ext_data)
        self.assertEqual(analysis.count_by_status("matched"), 3)  # applicant_name, privacy_agree, gender
        self.assertEqual(analysis.count_by_status("unmatched_data"), 1)
        self.assertEqual(analysis.count_by_status("read_only"), 1)
        self.assertEqual(analysis.count_by_status("invalid_choice"), 1)
        self.assertEqual(analysis.count_by_status("invalid_format"), 1)

        # 수동 매칭으로 custom_phone_col -> phone 연결
        analysis2 = analyze_import_data(session, ext_data, manual_mapping={"custom_phone_col": "phone"})
        self.assertEqual(analysis2.count_by_status("matched"), 4)
        applied, skipped = apply_import_analysis(session, analysis2)
        self.assertEqual(applied, 4)
        self.assertEqual(len(skipped), 3)
        self.assertEqual(session.get_logical_field("applicant_name").value, "강감찬")
        self.assertEqual(session.get_logical_field("phone").value, "010-9999-8888")
        # 동일 논리 필드 두 위젯 모두 '강감찬'으로 반영되었는지 확인
        name_widgets = [w for w in session.list_widgets() if w.field_name == "applicant_name"]
        self.assertEqual([w.value for w in name_widgets], ["강감찬", "강감찬"])

    # 테스트 6 — 입력 내용 고정 (bake) 저장
    def test_6_bake_preserves_visual_content_and_keeps_session_editable(self):
        sample = ensure_sample_form_pdf()
        session = FormDocumentSession(sample)
        self.addCleanup(session.close)
        session.set_field_value("applicant_name", "세종대왕")

        baked_path = self.root / "baked.pdf"
        session.save_baked_pdf(baked_path)

        # 작업 세션은 계속 편집 가능해야 함
        self.assertGreater(len(session.list_widgets()), 0)

        # 고정본은 위젯이 0개이고 텍스트('세종대왕')가 페이지 본문에 남아 있어야 함
        with fitz.open(str(baked_path)) as bdoc:
            self.assertEqual(len(list(bdoc[0].widgets() or [])), 0)
            self.assertIn("세종대왕", bdoc[0].get_text())

    # 테스트 7 — 예외 및 호환성 (양식 없는 PDF, 암호화 PDF, 전자서명 PDF, XFA 감지, 손상 PDF, 탭 간 UI 연동)
    def test_7_edge_cases_and_ui_workflow(self):
        # 1) 손상된 PDF
        bad = self.root / "corrupt.pdf"
        bad.write_bytes(b"not a valid pdf")
        with self.assertRaises(FormError):
            FormDocumentSession(bad)

        # 2) 암호화 PDF
        plain = self.make_plain_pdf(pages=1)
        enc_path = self.root / "encrypted.pdf"
        with fitz.open(str(plain)) as doc:
            doc.save(
                str(enc_path),
                encryption=fitz.PDF_ENCRYPT_AES_256,
                owner_pw="owner123",
                user_pw="user123",
                permissions=fitz.PDF_PERM_PRINT,
            )
        with self.assertRaises(FormError):
            FormDocumentSession(enc_path, password="wrong")
        enc_session = FormDocumentSession(enc_path, password="user123")
        self.addCleanup(enc_session.close)
        self.assertFalse(enc_session.can_modify)
        self.assertIn("권한", enc_session.restriction_message())

        # 3) 전자서명 필드가 있는 PDF
        sig_path = self.root / "with_sig.pdf"
        with fitz.open(str(plain)) as doc:
            w = fitz.Widget()
            w.field_name = "sig_field"
            w.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
            w.rect = fitz.Rect(50, 200, 200, 250)
            doc[0].add_widget(w)
            doc.save(str(sig_path))
        sig_session = FormDocumentSession(sig_path)
        self.addCleanup(sig_session.close)
        has_sig, has_signed = sig_session.signature_status()
        self.assertTrue(has_sig)
        self.assertFalse(has_signed)
        self.assertIn("전자서명", sig_session.restriction_message())

        # 4) 메인 윈도우 사이드바 통합 및 3탭 연동 UI 검증
        window = MdiMainWindow()
        window.show()
        self.addCleanup(window.close)
        window.open_tool("pdf_form")
        self.assertEqual(window.current_tool_key, "pdf_form")
        tool: PdfFormWidget = window.current_tool_widget

        # 시작 화면 표시 확인 후 예제 양식 로드
        self.assertEqual(tool.main_stack.currentIndex(), 0)
        tool.open_sample_form()
        self.assertEqual(tool.main_stack.currentIndex(), 1)
        self.assertEqual(tool.tabs.currentIndex(), 1)  # 양식 있으므로 '양식 작성하기' 탭 자동 선택

        # 양식 없는 일반 PDF 로드 시 '양식 작성하기' 탭의 빈 안내 표시 확인
        tool.load_pdf(plain, prefer_tab=1)
        self.assertFalse(tool.filler_panel.empty_box.isHidden())


if __name__ == "__main__":
    unittest.main()
