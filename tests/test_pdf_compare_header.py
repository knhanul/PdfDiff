import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel

from app.common.about_dialog import get_about_info
from app.common.resources import COMPANY_NAME, VERSION
from app.common.styles import COLOR_HEADER_ACCENT, HEADER_FOOTER_INSTRUCTION_HTML
from app.main_window import MdiMainWindow


class SharedHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MdiMainWindow()
        self.window.show()
        self.addCleanup(self.window.close)

    def test_menu_header_only_shows_current_title(self):
        for key, title in (
            ("pdf_compare", "PDF 지정 영역 비교"),
            ("pdf_hf_compare", "PDF 전체 비교"),
            ("pdf_editor", "PDF 편집 (분할/병합/페이지)"),
            ("pdf_modify", "PDF 수정 (텍스트 직접 편집)"),
            ("pdf_create", "PDF 생성"),
            ("file_rename", "파일 이름 관리"),
        ):
            with self.subTest(tool=key):
                self.window.open_tool(key)
                self.assertEqual(self.window.header_title.text(), title)
                labels = self.window.header_bar.findChildren(QLabel)
                self.assertEqual([label.text() for label in labels], [title])
                self.assertNotIn(COMPANY_NAME, title)
                self.assertNotIn(VERSION, title)
                self.assertEqual(self.window.header_accent.width(), 3)
                self.assertEqual(self.window.header_accent.height(), 22)

    def test_about_info_keeps_company_and_version(self):
        info = get_about_info()
        self.assertIn(COMPANY_NAME, repr(info))
        self.assertIn(VERSION, repr(info))
        self.assertEqual(self.window.info_btn.toolTip(), "프로그램 정보")

    def test_focus_mode_round_trip_and_close_tool_action(self):
        self.window.header_focus_btn.click()
        self.app.processEvents()
        self.assertTrue(self.window.focus_mode)
        self.assertFalse(self.window.header_bar.isVisible())
        self.assertTrue(self.window.header_focus_btn.isChecked())
        self.window.header_focus_btn.click()
        self.app.processEvents()
        self.assertFalse(self.window.focus_mode)
        self.assertTrue(self.window.header_bar.isVisible())
        self.assertFalse(self.window.header_focus_btn.isChecked())
        self.assertEqual(self.window.close_tool_btn.toolTip(),
                         "현재 도구 닫기 (프로그램은 종료되지 않습니다)")
        self.window.close_tool_btn.click()
        self.app.processEvents()
        self.assertTrue(self.window.isVisible())
        self.assertIsNone(self.window.current_tool_widget)

    def test_legend_visibility_is_limited_to_comparison_tools(self):
        for key, expected in (
            ("pdf_compare", True), ("pdf_hf_compare", True),
            ("pdf_modify", False), ("pdf_editor", False),
            ("pdf_create", False), ("file_rename", False),
        ):
            with self.subTest(tool=key):
                self.window.open_tool(key)
                self.assertEqual(self.window.legend_caution_btn.isVisible(), expected)
        self.assertEqual(self.window.legend_caution_btn.objectName(), "headerLegendBtn")
        self.window.blink_timer.stop()

    def test_comparison_controls_and_both_instruction_panels_share_styles(self):
        for key in ("pdf_compare", "pdf_hf_compare"):
            self.window.open_tool(key)
            tool = self.window.current_tool_widget
            self.assertEqual(tool.viewer1.open_pdf_btn.objectName(), "pdfOpenButton")
            self.assertEqual(tool.viewer2.open_pdf_btn.objectName(), "pdfOpenButton")
            self.assertEqual(tool.btn_compare.objectName(), "compareActionBtn")
            self.assertEqual(tool.btn_diff_list.objectName(), "compareUtilityBtn")
            self.assertEqual(tool.btn_comparison_options.objectName(), "compareUtilityBtn")
            self.assertEqual(tool.btn_reset_page.objectName(), "compareUtilityBtn")
            if key == "pdf_compare":
                self.assertEqual(tool.btn_reset_all.objectName(), "resetBtn")
            else:
                self.assertEqual(tool.btn_reset.objectName(), "resetBtn")
            margins = []
            for panel in (tool.hf_instruction_label1, tool.hf_instruction_label2):
                self.assertEqual(panel.text(), HEADER_FOOTER_INSTRUCTION_HTML)
                margin = panel.contentsMargins()
                margins.append((margin.left(), margin.top(), margin.right(), margin.bottom()))
            self.assertEqual(margins[0], margins[1])
            self.assertLessEqual(margins[0][1], 11)
        self.assertIn(COLOR_HEADER_ACCENT, self.window.styleSheet())
