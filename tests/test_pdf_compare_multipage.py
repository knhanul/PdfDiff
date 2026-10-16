import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from app.common.pdf_compare_worker import PdfCompareWorker
from app.common.pdf_text_normalizer import collect_raw_chars, normalize_raw_chars
from app.tools.pdf_compare import PDFViewer, PdfCompareWidget
from app.tools.pdf_header_footer_compare import HFCompareWidget, HFViewer


class MultiPageSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def make_pdf(self, name, texts):
        path = Path(self.temp.name) / name
        pdf = pymupdf.open()
        for text in texts:
            page = pdf.new_page(width=300, height=400)
            page.insert_text((40, 75), text, fontsize=16)
        pdf.save(path)
        pdf.close()
        return path

    def select(self, viewer, page):
        viewer.on_selection_complete(page, QRect(30, 55, 260, 110))

    def test_bottom_focus_button_toggles_modes_without_changing_actions(self):
        from app.main_window import MdiMainWindow

        window = MdiMainWindow()
        self.addCleanup(window.close)
        window.show()
        self.assertFalse(hasattr(window, 'hamburger_btn'))
        self.assertFalse(hasattr(window, 'focus_exit_btn'))
        for key in ('pdf_compare', 'pdf_hf_compare', 'pdf_compare'):
            window.open_tool(key)
            tool = window.current_tool_widget
            layout = tool.bottom_action_bar.layout()
            button = tool.btn_focus_mode
            self.assertIs(layout.itemAt(layout.count() - 1).widget(), tool.switch_toggle)
            self.assertIs(layout.itemAt(layout.count() - 2).widget(), button)
            actions = [layout.itemAt(i).widget() for i in range(layout.count() - 1)
                       if layout.itemAt(i).widget() is not None]
            before = [(action.isVisible(), action.minimumSize(), action.maximumSize())
                      for action in actions]
            for focused in (True, False):
                button.click()
                self.assertEqual(window.focus_mode, focused)
                self.assertEqual(window.header_bar.isVisible(), not focused)
                self.assertEqual(button.isChecked(), focused)
                self.assertTrue(button.isVisible())
                self.assertFalse(button.icon().isNull())
                self.assertEqual(button.toolTip(), '일반 모드로 전환' if focused else '집중 모드로 전환')
                self.assertTrue(all(action.isVisible() for action in actions))
                self.assertEqual(tool.lbl_name1.isVisible(), not focused)
                self.assertEqual(tool.lbl_name2.isVisible(), not focused)
                self.assertTrue(tool.viewer1.toolbar.isVisible())
                self.assertTrue(tool.viewer2.toolbar.isVisible())
                if focused:
                    self.assertEqual(tool.btn_compare.height(), 28)
                else:
                    self.assertEqual(before, [(action.isVisible(), action.minimumSize(), action.maximumSize())
                                              for action in actions])
                self.app.processEvents()

    def test_bottom_tool_switch_preserves_focus_and_scroll_toggle(self):
        from app.main_window import MdiMainWindow
        from app.tools.pdf_header_footer_compare import SyncScrollToggle

        window = MdiMainWindow()
        self.addCleanup(window.close)
        window.show()
        area = window.current_tool_widget
        for focused in (False, True):
            if window.focus_mode != focused:
                window.current_tool_widget.btn_focus_mode.click()
            area.switch_toggle.buttons[1].click()
            self.assertEqual(window.current_tool_key, 'pdf_hf_compare')
            full = window.current_tool_widget
            self.assertIsInstance(full.sync_scroll_cb, SyncScrollToggle)
            self.assertTrue(full.switch_toggle.buttons[1].isChecked())
            for tool in (area, full):
                bar_layout = tool.bottom_action_bar.layout()
                self.assertIs(bar_layout.itemAt(bar_layout.count() - 1).widget(), tool.switch_toggle)
                self.assertTrue(tool.switch_toggle.isEnabled())
            full.sync_scroll_cb.click()
            self.assertTrue(full.sync_scroll_enabled)
            full.sync_scroll_cb.click()
            self.assertFalse(full.sync_scroll_enabled)
            full.switch_toggle.buttons[0].click()
            self.assertEqual(window.current_tool_key, 'pdf_compare')
            self.assertIs(window.current_tool_widget, area)
            self.assertEqual(window.focus_mode, focused)
            self.assertEqual(window.header_bar.isVisible(), not focused)
            self.app.processEvents()

    def test_focus_compact_layout_restores_after_switching_and_loading_pdf(self):
        from app.main_window import MdiMainWindow

        window = MdiMainWindow()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        area = window.current_tool_widget
        normal_height = area.bottom_action_bar.height()
        normal_button_height = area.btn_compare.height()
        normal_margins = area.layout().contentsMargins()
        area.btn_focus_mode.click()
        self.app.processEvents()
        self.assertLess(area.bottom_action_bar.height(), normal_height)
        self.assertLessEqual(area.bottom_action_bar.height(), 36)
        area.switch_toggle.buttons[1].click()
        self.app.processEvents()
        full = window.current_tool_widget
        self.assertTrue(full.lbl_name1.isHidden())
        self.assertLessEqual(full.bottom_action_bar.height(), 36)
        path = self.make_pdf('focus.pdf', ['Focus content'])
        for tool in (area, full):
            self.assertTrue(tool.viewer1.load_pdf(path))
            self.addCleanup(tool.viewer1.pdf_doc.close)
            tool.viewer1.update_loaded_pdf_label(path)
            self.assertIn('focus.pdf', tool.lbl_name1.text())
            self.assertTrue(tool.lbl_name1.isHidden())
        full.btn_focus_mode.click()
        self.app.processEvents()
        self.assertTrue(full.lbl_name1.isVisible())
        full.switch_toggle.buttons[0].click()
        self.app.processEvents()
        self.assertEqual(area.bottom_action_bar.height(), normal_height)
        self.assertEqual(area.layout().contentsMargins(), normal_margins)
        self.assertTrue(area.lbl_name1.isVisible())
        self.assertEqual(area.btn_compare.height(), normal_button_height)
        self.assertEqual(area.btn_focus_mode.width(), 40)

    def test_shared_normalization_preserves_filtering_and_word_ids(self):
        characters = [('A', 10), ('A', 10.5), (' ', 14), ('B', 18),
                      ('?', 22), ('\t', 26), ('C', 30), ('e\u0301', 34)]
        raw_dict = {'blocks': [
            {'type': 0, 'lines': [{'spans': [{'chars': [
                {'c': character, 'bbox': (x, 10, x + 2, 18)} for character, x in characters
            ]}]}]},
            {'type': 1, 'lines': [{'spans': [{'chars': [
                {'c': 'Z', 'bbox': (40, 10, 42, 18)}
            ]}]}]},
        ]}
        area_chars, area_raw = normalize_raw_chars(collect_raw_chars(raw_dict, 0))
        self.assertEqual(''.join(char['char'] for char in area_chars), 'ab?cz')
        self.assertEqual(area_raw, 'AA B?\tCéZ')
        self.assertEqual([char['word_id'] for char in area_chars], [1, 2, 2, 3, 4])
        full_chars, full_raw = normalize_raw_chars(
            collect_raw_chars(raw_dict, 0, excluded_bounds=(0, 100)), page_aware=True
        )
        self.assertEqual(''.join(char['char'] for char in full_chars), 'ab?c')
        self.assertEqual(full_raw, 'AA B?\tCé')
        self.assertEqual([char['word_id'] for char in full_chars], [1, 2, 2, 3])
        self.assertEqual(collect_raw_chars(raw_dict, 0, excluded_bounds=(18, 100)), [])
        self.assertEqual(normalize_raw_chars([]), ([], ''))

    def test_area_and_full_text_extraction_contract(self):
        path = Path(self.temp.name) / 'contract.pdf'
        pdf = pymupdf.open()
        for body in ('Alpha (1)', 'Beta - XYZ'):
            page = pdf.new_page(width=300, height=400)
            page.insert_text((40, 15), 'HEAD', fontsize=10)
            page.insert_text((40, 75), body, fontsize=16)
        pdf.save(path)
        pdf.close()
        area = PDFViewer()
        full = HFViewer()
        self.assertTrue(area.load_pdf(path))
        self.addCleanup(area.pdf_doc.close)
        self.assertTrue(full.load_pdf(path))
        self.addCleanup(full.pdf_doc.close)
        chars, raw = area.extract_and_process_text(0, QRect(30, 55, 280, 100))
        self.assertEqual(''.join(char['char'] for char in chars), 'alpha(1)')
        self.assertEqual(raw, 'Alpha (1)')
        self.assertEqual({char['page'] for char in chars}, {0})
        full.extract_body_text()
        self.assertEqual(''.join(char['char'] for char in full.char_data), 'alpha(1)beta-xyz')
        self.assertEqual(full.raw_text, 'Alpha (1)\nBeta - XYZ')
        self.assertEqual({char['page'] for char in full.char_data}, {0, 1})
        self.assertEqual([(char['char'], char['word_id']) for char in chars],
                         [(char['char'], char['word_id']) for char in full.char_data if char['page'] == 0])
        full.header_ratio = 0
        full.extract_body_text()
        self.assertIn('head', ''.join(char['char'] for char in full.char_data))
        area.close()
        full.close()

    def test_single_selection_and_navigation_keep_previous_page(self):
        viewer = PDFViewer()
        self.assertTrue(viewer.load_pdf(self.make_pdf('a.pdf', ['First', 'Second', 'Third'])))
        self.addCleanup(viewer.pdf_doc.close)
        self.select(viewer, 1)
        viewer.goto_page(3)
        self.select(viewer, 0)
        self.assertEqual(set(viewer.selection_areas), {0})
        self.assertEqual(''.join(c['char'] for c in viewer.char_data), 'first')
        self.assertEqual(set(viewer.last_compared_area), {0})
        self.assertEqual({c['page'] for c in viewer.char_data}, {0})
        self.assertEqual(len({c['word_id'] for c in viewer.char_data}), 1)
        viewer.zoom_in()
        self.assertEqual(set(viewer.last_compared_area), {0})
        viewer.clear_all_data()
        self.assertFalse(viewer.selection_areas)
        self.assertIsNone(viewer.pending_selection_rect)
        self.assertFalse(viewer.char_data)
        viewer.close()

    def selection_viewer(self):
        viewer = PDFViewer()
        self.assertTrue(viewer.load_pdf(self.make_pdf('selection.pdf', ['Alpha', 'Beta', 'Alpha'])))
        self.addCleanup(viewer.close)
        self.addCleanup(viewer.pdf_doc.close)
        return viewer

    def select_pdf_rect(self, viewer, page, bounds):
        x0, y0, x1, y1 = bounds
        viewer.on_selection_complete(page, QRect(
            round(x0 * viewer.scale), round(y0 * viewer.scale),
            round((x1 - x0) * viewer.scale), round((y1 - y0) * viewer.scale)
        ))

    def document_point(self, viewer, page, x, y):
        from PyQt6.QtCore import QPoint
        return viewer.page_image_rect(page).topLeft() + QPoint(round(x * viewer.scale), round(y * viewer.scale))

    def select_pages(self, viewer, first, last, reverse=False):
        window = viewer.window()
        window.resize(650, 450) if window is viewer else window.resize(1600, 700)
        window.show()
        self.app.processEvents()
        start = self.document_point(viewer, first, 30, 55)
        end = self.document_point(viewer, last, 290, 100)
        if reverse:
            start, end = end, start
        viewer.begin_selection(start, viewer.container.mapToGlobal(start))
        viewer.move_selection(end, viewer.container.mapToGlobal(end))
        viewer.finish_selection(end)

    def test_continuous_drag_and_reverse_drag_preserve_page_order(self):
        viewer = self.selection_viewer()
        self.select_pages(viewer, 0, 2)
        self.assertEqual(set(viewer.selection_areas), {0, 1, 2})
        self.assertEqual(viewer.raw_text, 'Alpha\nBeta\nAlpha')
        self.assertEqual(''.join(c['char'] for c in viewer.char_data), 'alphabetaalpha')
        self.assertEqual(len({c['word_id'] for c in viewer.char_data}), 3)
        original = viewer.char_data.copy(), viewer.raw_text
        self.select_pages(viewer, 0, 2, reverse=True)
        self.assertEqual((viewer.char_data, viewer.raw_text), original)
        viewer.zoom_in()
        self.assertEqual((viewer.char_data, viewer.raw_text), original)

    def test_new_drag_replaces_previous_selection(self):
        viewer = self.selection_viewer()
        self.select_pages(viewer, 0, 2)
        self.select_pdf_rect(viewer, 1, (30, 60, 160, 80))
        self.assertEqual(set(viewer.selection_areas), {1})
        self.assertEqual(viewer.raw_text, 'Beta')
        self.select_pdf_rect(viewer, 1, (30, 60, 160, 80))
        self.assertEqual(viewer.raw_text, 'Beta')
        self.assertEqual(len(viewer.selection_areas[1]), 1)

    def test_center_based_extraction_includes_clipped_boundary_glyphs(self):
        viewer = self.selection_viewer()
        self.select_pdf_rect(viewer, 0, (30, 60, 160, 78))
        self.assertEqual(viewer.raw_text, 'Alpha')
        chars, raw = viewer.extract_and_process_text(0, QRect(45, 90, 195, 27))
        self.assertEqual(raw, 'Alpha')
        self.assertEqual(''.join(c['char'] for c in chars), 'alpha')

    def test_click_and_cancel_keep_previous_selection(self):
        viewer = self.selection_viewer()
        self.select_pages(viewer, 0, 1)
        original = viewer.char_data.copy(), viewer.raw_text
        viewer.on_selection_complete(0, QRect(30, 55, 100, 2))
        start = self.document_point(viewer, 0, 40, 70)
        viewer.begin_selection(start, viewer.container.mapToGlobal(start))
        viewer.finish_selection(start)
        self.assertEqual((viewer.char_data, viewer.raw_text), original)
        viewer.begin_selection(start, viewer.container.mapToGlobal(start))
        viewer.cancel_selection()
        self.assertFalse(viewer.auto_scroll_timer.isActive())
        self.assertIsNone(viewer.drag_start)
        self.assertEqual((viewer.char_data, viewer.raw_text), original)

    def test_mouse_events_cross_page_boundary_and_gap(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        viewer = self.selection_viewer()
        viewer.resize(650, 450)
        viewer.show()
        self.app.processEvents()
        label = viewer.page_labels[0]
        start = label.mapFrom(viewer.container, self.document_point(viewer, 0, 30, 55))
        end = label.mapFrom(viewer.container, self.document_point(viewer, 1, 290, 100))
        QTest.mousePress(label, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(label, end)
        self.assertIsNotNone(viewer.page_labels[1].selection_start)
        QTest.mouseRelease(label, Qt.MouseButton.LeftButton, pos=end)
        self.assertEqual(viewer.raw_text, 'Alpha\nBeta')
        self.assertFalse(viewer.auto_scroll_timer.isActive())

    def test_auto_scroll_moves_endpoint_without_changing_start(self):
        from PyQt6.QtCore import QPoint
        viewer = self.selection_viewer()
        viewer.resize(650, 450)
        viewer.show()
        self.app.processEvents()
        start = self.document_point(viewer, 0, 30, 55)
        edge = viewer.viewport().mapToGlobal(QPoint(200, viewer.viewport().height() - 1))
        viewer.begin_selection(start, edge)
        viewer.auto_scroll_selection()
        self.assertGreater(viewer.verticalScrollBar().value(), 0)
        self.assertEqual(viewer.drag_start, start)
        self.assertEqual(viewer.drag_end, viewer.container.mapFromGlobal(edge))
        viewer.drag_global_pos = viewer.viewport().mapToGlobal(QPoint(200, 0))
        before = viewer.verticalScrollBar().value()
        viewer.auto_scroll_selection()
        self.assertLess(viewer.verticalScrollBar().value(), before)
        viewer.cancel_selection()

    def test_exclusion_filters_each_page_and_can_be_changed_after_selection(self):
        path = Path(self.temp.name) / 'header_footer.pdf'
        pdf = pymupdf.open()
        for text in ('Alpha', 'Beta'):
            page = pdf.new_page(width=300, height=400)
            for y, value in ((25, 'HEAD'), (75, text), (380, 'FOOT')):
                page.insert_text((40, y), value, fontsize=10)
        pdf.save(path)
        pdf.close()
        viewer = PDFViewer()
        self.assertTrue(viewer.load_pdf(path))
        self.addCleanup(viewer.close)
        self.addCleanup(viewer.pdf_doc.close)
        self.select_pages(viewer, 0, 1)
        self.assertIn('FOOT', viewer.raw_text)
        self.assertIn('HEAD', viewer.raw_text)
        viewer.set_exclusion_ratios(0.1, 0.1)
        self.assertEqual(viewer.raw_text, 'Alpha\nBeta')
        self.assertAlmostEqual(viewer.last_compared_area[0][0].y1, 360)
        self.assertAlmostEqual(viewer.last_compared_area[1][0].y0, 40)
        viewer.set_exclusion_ratios(0, 0)
        self.assertIn('FOOT', viewer.raw_text)
        self.assertIn('HEAD', viewer.raw_text)

    def test_drag_keeps_horizontal_bounds_on_every_page(self):
        path = Path(self.temp.name) / 'columns.pdf'
        pdf = pymupdf.open()
        for _ in range(2):
            page = pdf.new_page(width=300, height=400)
            page.insert_text((40, 75), 'Left', fontsize=12)
            page.insert_text((220, 75), 'Right', fontsize=12)
        pdf.save(path)
        pdf.close()
        viewer = PDFViewer()
        self.assertTrue(viewer.load_pdf(path))
        self.addCleanup(viewer.close)
        self.addCleanup(viewer.pdf_doc.close)
        viewer.resize(650, 450)
        viewer.show()
        self.app.processEvents()
        start = self.document_point(viewer, 0, 30, 55)
        end = self.document_point(viewer, 1, 160, 100)
        viewer.begin_selection(start, viewer.container.mapToGlobal(start))
        viewer.finish_selection(end)
        self.assertEqual(viewer.raw_text, 'Left\nLeft')

    def test_exclusion_change_invalidates_comparison_without_erasing_selection(self):
        widget = PdfCompareWidget()
        self.addCleanup(widget.close)
        for viewer in (widget.viewer1, widget.viewer2):
            self.assertTrue(viewer.load_pdf(self.make_pdf(f'{id(viewer)}.pdf', ['First', 'Second'])))
            self.addCleanup(viewer.pdf_doc.close)
            self.select_pages(viewer, 0, 1)
        for viewer in (widget.viewer1, widget.viewer2):
            viewer.word_highlights = {0: [((40, 50, 100, 80), 1, QColor(255, 0, 0))]}
            viewer.diff_pages = [(0, 60)]
            viewer.diff_index = 0
        widget.last_s1_norm = widget.last_s2_norm = 'old'
        widget.last_s1_raw = widget.last_s2_raw = 'Old'
        widget.diff_list = [{'pdf': 'PDF 1', 'page': 1}]
        widget.viewer1.set_exclusion_ratios(0.1, 0.1)
        self.assertAlmostEqual(widget.viewer2.header_ratio, 0.05)
        self.assertAlmostEqual(widget.viewer2.footer_ratio, 0.05)
        for viewer in (widget.viewer1, widget.viewer2):
            self.assertEqual(set(viewer.selection_areas), {0, 1})
            self.assertEqual(viewer.raw_text, 'First\nSecond')
            self.assertFalse(viewer.word_highlights)
            self.assertFalse(viewer.diff_pages)
            self.assertEqual(viewer.diff_index, -1)
        self.assertEqual(widget.last_s1_norm, '')
        self.assertEqual(widget.last_s2_norm, '')
        self.assertEqual(widget.last_s1_raw, '')
        self.assertEqual(widget.last_s2_raw, '')
        self.assertFalse(widget.diff_list)

    def test_instruction_labels_and_default_exclusion_match_full_compare(self):
        widget = PdfCompareWidget()
        self.addCleanup(widget.close)
        for label in (widget.hf_instruction_label1, widget.hf_instruction_label2):
            self.assertIn('머릿글/바닥글 제외 설정', label.text())
            self.assertFalse(label.isHidden())
        for viewer in (widget.viewer1, widget.viewer2):
            self.assertTrue(viewer.load_pdf(self.make_pdf(f'{id(viewer)}.pdf', ['First'])))
            self.addCleanup(viewer.pdf_doc.close)
            self.assertAlmostEqual(viewer.header_ratio, 0.05)
            self.assertAlmostEqual(viewer.footer_ratio, 0.05)
        self.assertTrue(widget.hf_instruction_label1.isHidden())
        self.assertTrue(widget.hf_instruction_label2.isHidden())
        widget.viewer1.clear_all_data()
        self.assertFalse(widget.hf_instruction_label1.isHidden())
        self.assertTrue(widget.hf_instruction_label2.isHidden())

    def test_exclusion_edges_drag_directly_without_starting_selection(self):
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtTest import QTest
        viewer = self.selection_viewer()
        self.select_pages(viewer, 0, 1)
        original = viewer.raw_text
        self.assertFalse(hasattr(viewer, 'exclusion_mode_btn'))
        self.assertFalse(hasattr(viewer, 'header_spin'))
        self.assertFalse(hasattr(viewer, 'footer_spin'))
        label = viewer.page_labels[0]
        image = label._image_rect()
        point = QPoint(image.center().x(), image.y() + round(image.height() * 0.05))
        QTest.mouseMove(label, point)
        self.assertEqual(label.cursor().shape(), Qt.CursorShape.SizeVerCursor)
        QTest.mousePress(label, Qt.MouseButton.LeftButton, pos=point)
        point.setY(image.y() + round(image.height() * 0.1))
        QTest.mouseMove(label, point)
        QTest.mouseRelease(label, Qt.MouseButton.LeftButton, pos=point)
        self.assertAlmostEqual(viewer.header_ratio, 0.1)
        self.assertEqual(viewer.raw_text, original)
        self.assertIsNone(viewer.drag_start)
        self.assertFalse(viewer.auto_scroll_timer.isActive())
        label = viewer.page_labels[1]
        image = label._image_rect()
        point = QPoint(image.center().x(), image.y() + round(image.height() * 0.95))
        QTest.mousePress(label, Qt.MouseButton.LeftButton, pos=point)
        point.setY(image.y() + round(image.height() * 0.9))
        QTest.mouseMove(label, point)
        QTest.mouseRelease(label, Qt.MouseButton.LeftButton, pos=point)
        self.assertAlmostEqual(viewer.footer_ratio, 0.1)
        self.assertEqual(viewer.raw_text, original)
        viewer.zoom_in()
        self.app.processEvents()
        self.assertAlmostEqual(viewer.header_ratio, 0.1)
        self.assertAlmostEqual(viewer.footer_ratio, 0.1)
        self.select_pages(viewer, 0, 2)
        self.assertEqual(viewer.raw_text, 'Alpha\nBeta\nAlpha')

    def test_header_drag_does_not_move_footer_when_boundaries_meet(self):
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtTest import QTest
        viewer = self.selection_viewer()
        self.select_pages(viewer, 0, 1)
        viewer.set_exclusion_ratios(0.1, 0.2)
        label = viewer.page_labels[0]
        image = label._image_rect()
        point = QPoint(image.center().x(), image.y() + round(image.height() * 0.1))
        QTest.mousePress(label, Qt.MouseButton.LeftButton, pos=point)
        point.setY(image.bottom())
        QTest.mouseMove(label, point)
        QTest.mouseRelease(label, Qt.MouseButton.LeftButton, pos=point)
        self.assertAlmostEqual(viewer.header_ratio, 0.75)
        self.assertAlmostEqual(viewer.footer_ratio, 0.2)

    def test_context_menu_clears_whole_range_after_zoom(self):
        from PyQt6.QtCore import QPoint
        from PyQt6.QtGui import QContextMenuEvent
        viewer = self.selection_viewer()
        self.select_pages(viewer, 0, 2)
        viewer.zoom_in()
        label = viewer.page_labels[1]
        label.resize(label.pixmap().width() + 100, label.pixmap().height() + 60)
        point = label._image_rect().topLeft() + QPoint(round(40 * viewer.scale), round(70 * viewer.scale))
        event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, label.mapToGlobal(point))
        with patch('app.tools.pdf_compare.QMenu.exec', lambda menu, pos: menu.actions()[0]):
            label.contextMenuEvent(event)
        self.assertFalse(viewer.selection_areas)
        self.assertFalse(viewer.char_data)
        self.assertFalse(viewer.last_compared_area)
        self.assertEqual(viewer.raw_text, '')
        self.assertIsNone(viewer.pending_selection_rect)

    def test_supplied_pdf_boundary_selection_extracts_items_one_to_six(self):
        paths = list(Path(__file__).parent.glob('기초서류*.pdf'))
        if not paths:
            self.skipTest('Local PDF regression fixture is not available')
        viewer = PDFViewer()
        viewer.pdf_doc = pymupdf.open(paths[0])
        self.addCleanup(viewer.close)
        self.addCleanup(viewer.pdf_doc.close)
        viewer.selection_areas = {
            7: [pymupdf.Rect(55, 690, 559, 842)],
            8: [pymupdf.Rect(55, 0, 559, 103)],
        }
        viewer.set_exclusion_ratios(0.1, 0.05)
        self.assertTrue(viewer.raw_text.startswith('주) 1.'))
        for number in range(2, 7):
            self.assertIn(f'{number}. ', viewer.raw_text)
        self.assertNotIn('본 상품설명서는', viewer.raw_text)
        self.assertNotIn('고객보관용', viewer.raw_text)
        self.assertEqual({c['page'] for c in viewer.char_data}, {7, 8})

    def test_widget_comparison_reports_differences_on_selected_pages(self):
        from PyQt6.QtCore import QEventLoop, QTimer
        widget = PdfCompareWidget()
        self.assertTrue(widget.viewer1.load_pdf(self.make_pdf('compare1.pdf', ['Match', 'Left'])))
        self.addCleanup(widget.viewer1.pdf_doc.close)
        self.assertTrue(widget.viewer2.load_pdf(self.make_pdf('compare2.pdf', ['Skip', 'Match', 'Right'])))
        self.addCleanup(widget.viewer2.pdf_doc.close)
        self.select_pages(widget.viewer1, 0, 1)
        self.select_pages(widget.viewer2, 1, 2)
        widget.btn_compare.click()
        loop = QEventLoop()
        widget.compare_manager.result_ready.connect(loop.quit)
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
        self.assertEqual(widget.last_s1_norm, 'matchleft')
        self.assertEqual(widget.last_s2_norm, 'matchright')
        self.assertEqual({item['page'] for item in widget.diff_list if item['pdf'] == 'PDF 1'}, {2})
        self.assertEqual({item['page'] for item in widget.diff_list if item['pdf'] == 'PDF 2'}, {3})
        loop = QEventLoop()
        QTimer.singleShot(200, loop.quit)
        loop.exec()
        widget.close()

    def test_area_comparison_keeps_each_viewers_scroll_position(self):
        from PyQt6.QtCore import QEventLoop, QTimer
        widget = PdfCompareWidget()
        self.addCleanup(widget.close)
        for viewer, name, texts in (
            (widget.viewer1, 'position1.pdf', ['Cover', 'Same', 'Left', 'Tail']),
            (widget.viewer2, 'position2.pdf', ['Cover', 'Same', 'Right', 'Tail']),
        ):
            self.assertTrue(viewer.load_pdf(self.make_pdf(name, texts)))
            self.addCleanup(viewer.pdf_doc.close)
            self.select_pages(viewer, 1, 2)
        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()
        widget.viewer1.verticalScrollBar().setValue(widget.viewer1.page_labels[1].y() + 40)
        widget.viewer2.verticalScrollBar().setValue(widget.viewer2.page_labels[2].y() + 60)
        positions = [(viewer.verticalScrollBar().value(), viewer.horizontalScrollBar().value(), viewer.page_spin.text())
                     for viewer in (widget.viewer1, widget.viewer2)]
        labels = [list(viewer.page_labels) for viewer in (widget.viewer1, widget.viewer2)]
        for _ in range(2):
            widget.btn_compare.click()
            loop = QEventLoop()
            widget.compare_manager.result_ready.connect(loop.quit)
            QTimer.singleShot(3000, loop.quit)
            loop.exec()
            self.assertEqual(widget.last_s1_norm, 'sameleft')
            self.assertEqual(widget.last_s2_norm, 'sameright')
            loop = QEventLoop()
            QTimer.singleShot(350, loop.quit)
            loop.exec()
            self.assertTrue(widget.btn_compare.isEnabled())
            for viewer, position, previous_labels in zip((widget.viewer1, widget.viewer2), positions, labels):
                self.assertEqual((viewer.verticalScrollBar().value(), viewer.horizontalScrollBar().value(),
                                  viewer.page_spin.text()), position)
                self.assertEqual(viewer.page_labels, previous_labels)
                self.assertTrue(viewer.word_highlights)
                self.assertNotEqual(viewer.page_labels[2].pixmap().toImage(), viewer.page_base_pixmaps[2].toImage())

    def test_full_compare_scroll_stays_continuous_before_comparison(self):
        from PyQt6.QtCore import QEventLoop, QTimer
        widget = HFCompareWidget()
        texts = ['First', 'Second', 'Third']
        self.assertTrue(widget.viewer1.load_pdf(self.make_pdf('scroll1.pdf', texts)))
        self.addCleanup(widget.viewer1.pdf_doc.close)
        self.assertTrue(widget.viewer2.load_pdf(self.make_pdf('scroll2.pdf', texts)))
        self.addCleanup(widget.viewer2.pdf_doc.close)
        widget.resize(1200, 700)
        widget.show()
        loop = QEventLoop()
        QTimer.singleShot(150, loop.quit)
        loop.exec()
        widget.viewer1.verticalScrollBar().setValue(180)
        widget.sync_scroll_cb.setChecked(True)
        self.assertLess(abs(widget.viewer2.verticalScrollBar().value() - 180), 30)
        widget.viewer1.verticalScrollBar().setValue(100)
        first = widget.viewer2.verticalScrollBar().value()
        widget.viewer1.verticalScrollBar().setValue(140)
        second = widget.viewer2.verticalScrollBar().value()
        self.assertGreater(second, first)
        self.assertLess(abs(second - 140), 30)
        widget.viewer2.verticalScrollBar().setValue(250)
        self.assertLess(abs(widget.viewer1.verticalScrollBar().value() - 250), 30)
        widget.close()

    def test_full_compare_scroll_without_matches_tracks_document_progress(self):
        from PyQt6.QtCore import QEventLoop, QTimer
        widget = HFCompareWidget()
        self.assertTrue(widget.viewer1.load_pdf(self.make_pdf('short.pdf', ['A', 'B'])))
        self.addCleanup(widget.viewer1.pdf_doc.close)
        self.assertTrue(widget.viewer2.load_pdf(self.make_pdf('long.pdf', ['A', 'B', 'C', 'D'])))
        self.addCleanup(widget.viewer2.pdf_doc.close)
        widget.resize(1200, 700)
        widget.show()
        loop = QEventLoop()
        QTimer.singleShot(150, loop.quit)
        loop.exec()
        widget.sync_scroll_cb.setChecked(True)
        source = widget.viewer1.verticalScrollBar()
        target = widget.viewer2.verticalScrollBar()
        source.setValue(source.maximum() // 2)
        self.assertLess(abs(target.value() / target.maximum() - 0.5), 0.05)
        target.setValue(target.maximum() * 3 // 4)
        self.assertLess(abs(source.value() / source.maximum() - 0.75), 0.05)
        widget.close()

    def test_full_compare_scroll_aligns_matching_pages_after_comparison(self):
        from PyQt6.QtCore import QEventLoop, QTimer
        widget = HFCompareWidget()
        self.assertTrue(widget.viewer1.load_pdf(self.make_pdf('match1.pdf', ['Alpha', 'Bravo', 'Charlie'])))
        self.addCleanup(widget.viewer1.pdf_doc.close)
        self.assertTrue(widget.viewer2.load_pdf(self.make_pdf('match2.pdf', ['Cover', 'Alpha', 'Bravo', 'Charlie'])))
        self.addCleanup(widget.viewer2.pdf_doc.close)
        widget.resize(1200, 700)
        widget.show()
        loop = QEventLoop()
        QTimer.singleShot(150, loop.quit)
        loop.exec()
        for viewer in (widget.viewer1, widget.viewer2):
            viewer.extract_body_text()
        from app.common.pdf_compare_worker import PdfCompareWorker
        results = []
        worker = PdfCompareWorker(widget.viewer1.char_data, widget.viewer2.char_data,
                                  widget.viewer1.raw_text, widget.viewer2.raw_text)
        worker.result_ready.connect(results.append)
        worker.run()
        with patch.object(widget, '_refresh_viewers_optimized'):
            widget._on_compare_result_ready(results[0])
        widget.sync_scroll_cb.setChecked(True)
        widget.viewer1.verticalScrollBar().setValue(widget.viewer1.page_labels[1].y() + 100)
        self.assertEqual(widget.get_current_page(widget.viewer2), 2)
        widget.viewer2.verticalScrollBar().setValue(widget.viewer2.page_labels[1].y() + 100)
        self.assertEqual(widget.get_current_page(widget.viewer1), 0)
        widget.viewer2.zoom_in()
        loop = QEventLoop()
        QTimer.singleShot(150, loop.quit)
        loop.exec()
        widget.viewer1.verticalScrollBar().setValue(widget.viewer1.page_labels[2].y() + 90)
        self.assertEqual(widget.get_current_page(widget.viewer2), 3)
        widget.close()

    def test_full_compare_can_compare_again_after_page_reset(self):
        from PyQt6.QtCore import QEventLoop, QTimer
        widget = HFCompareWidget()
        self.assertTrue(widget.viewer1.load_pdf(self.make_pdf('again1.pdf', ['Same', 'Left'])))
        self.addCleanup(widget.viewer1.pdf_doc.close)
        self.assertTrue(widget.viewer2.load_pdf(self.make_pdf('again2.pdf', ['Same', 'Right'])))
        self.addCleanup(widget.viewer2.pdf_doc.close)

        def compare():
            widget.viewer1.extract_body_text()
            widget.viewer2.extract_body_text()
            self.assertTrue(widget.viewer1.char_data)
            self.assertTrue(widget.viewer2.char_data)
            widget.start_async_comparison()
            loop = QEventLoop()
            widget.compare_manager.result_ready.connect(loop.quit)
            QTimer.singleShot(3000, loop.quit)
            loop.exec()
            self.assertEqual(widget.last_s1_norm, 'sameleft')
            self.assertEqual(widget.last_s2_norm, 'sameright')
            loop = QEventLoop()
            QTimer.singleShot(150, loop.quit)
            loop.exec()

        with patch('app.tools.pdf_header_footer_compare.QMessageBox.information'):
            compare()
            widget.get_current_page = lambda viewer: 1
            widget.btn_reset_page.click()
            self.assertNotIn(1, widget.viewer1.word_highlights)
            self.assertNotIn(1, widget.viewer2.word_highlights)
            compare()
            self.assertIn(1, widget.viewer1.word_highlights)
            self.assertIn(1, widget.viewer2.word_highlights)
        widget.close()

    def test_full_compare_reset_uses_each_viewers_visible_page(self):
        from PyQt6.QtCore import QEventLoop, QTimer
        widget = HFCompareWidget()
        self.assertTrue(widget.viewer1.load_pdf(self.make_pdf('visible1.pdf', ['One', 'Two', 'Three'])))
        self.addCleanup(widget.viewer1.pdf_doc.close)
        self.assertTrue(widget.viewer2.load_pdf(self.make_pdf('visible2.pdf', ['One', 'Two', 'Three'])))
        self.addCleanup(widget.viewer2.pdf_doc.close)
        widget.resize(1200, 700)
        widget.show()
        loop = QEventLoop()
        QTimer.singleShot(150, loop.quit)
        loop.exec()
        widget.viewer1.goto_page(2)
        widget.viewer2.goto_page(3)
        self.app.processEvents()
        self.assertEqual(widget.get_current_page(widget.viewer1), 1)
        self.assertEqual(widget.get_current_page(widget.viewer2), 2)
        for viewer in (widget.viewer1, widget.viewer2):
            viewer.last_compared_area = {page: [(40, 50, 100, 80)] for page in range(3)}
        widget.btn_reset_page.click()
        self.assertEqual(set(widget.viewer1.last_compared_area), {0, 2})
        self.assertEqual(set(widget.viewer2.last_compared_area), {0, 1})
        widget.close()

    def test_full_compare_page_reset_preserves_other_page_results(self):
        widget = HFCompareWidget()
        self.assertTrue(widget.viewer1.load_pdf(self.make_pdf('full1.pdf', ['First', 'Second', 'Third'])))
        self.addCleanup(widget.viewer1.pdf_doc.close)
        self.assertTrue(widget.viewer2.load_pdf(self.make_pdf('full2.pdf', ['First', 'Second', 'Third'])))
        self.addCleanup(widget.viewer2.pdf_doc.close)
        self.assertIn('페이지 초기화', widget.btn_reset_page.text())
        for viewer in (widget.viewer1, widget.viewer2):
            viewer.word_highlights = {page: [((40, 50, 100, 80), QColor(255, 0, 0))] for page in range(3)}
            viewer.last_compared_area = {page: [(40, 50, 100, 80)] for page in range(3)}
            viewer.diff_pages = [(page, 60) for page in range(3)]
            viewer.diff_index = 1
        widget.diff_list = [
            {'pdf': 'PDF 1', 'page': page + 1} for page in range(3)
        ] + [{'pdf': 'PDF 2', 'page': page + 1} for page in range(3)]
        widget.sync_anchor_pairs = [((0, 60), (0, 60)), ((1, 60), (2, 60))]
        widget.viewer1.header_ratio = 0.1
        widget.viewer2.footer_ratio = 0.12
        widget.get_current_page = lambda viewer: 1 if viewer is widget.viewer1 else 2
        widget.reset_current_page()
        self.assertEqual(set(widget.viewer1.word_highlights), {0, 2})
        self.assertEqual(set(widget.viewer2.word_highlights), {0, 1})
        self.assertEqual(set(widget.viewer1.last_compared_area), {0, 2})
        self.assertEqual(set(widget.viewer2.last_compared_area), {0, 1})
        self.assertEqual(widget.viewer1.diff_pages, [(0, 60), (2, 60)])
        self.assertEqual(widget.viewer2.diff_pages, [(0, 60), (1, 60)])
        self.assertEqual(widget.viewer1.diff_index, -1)
        self.assertEqual(widget.viewer2.diff_index, -1)
        self.assertEqual(widget.diff_list, [
            {'pdf': 'PDF 1', 'page': 1}, {'pdf': 'PDF 1', 'page': 3},
            {'pdf': 'PDF 2', 'page': 1}, {'pdf': 'PDF 2', 'page': 2},
        ])
        self.assertEqual(widget.sync_anchor_pairs, [((0, 60), (0, 60))])
        self.assertEqual(widget.viewer1.header_ratio, 0.1)
        self.assertEqual(widget.viewer2.footer_ratio, 0.12)
        widget.close()

    def test_page_reset_keeps_other_page_selection(self):
        widget = PdfCompareWidget()
        self.assertTrue(widget.viewer1.load_pdf(self.make_pdf('reset1.pdf', ['First', 'Second'])))
        self.addCleanup(widget.viewer1.pdf_doc.close)
        self.assertTrue(widget.viewer2.load_pdf(self.make_pdf('reset2.pdf', ['First', 'Second'])))
        self.addCleanup(widget.viewer2.pdf_doc.close)
        self.select_pages(widget.viewer1, 0, 1)
        self.select_pages(widget.viewer2, 0, 1)
        widget.get_current_page = lambda viewer: 1
        widget._do_reset_current_page(0)
        from PyQt6.QtCore import QEventLoop, QTimer
        loop = QEventLoop()
        QTimer.singleShot(150, loop.quit)
        loop.exec()
        for viewer in (widget.viewer1, widget.viewer2):
            self.assertEqual(set(viewer.selection_areas), {0})
            self.assertEqual(''.join(c['char'] for c in viewer.char_data), 'first')
            self.assertEqual(viewer.pending_selection_rect[0], 0)
        widget._do_reset_all(0)
        loop = QEventLoop()
        QTimer.singleShot(150, loop.quit)
        loop.exec()
        for viewer in (widget.viewer1, widget.viewer2):
            self.assertFalse(viewer.selection_areas)
            self.assertIsNone(viewer.pending_selection_rect)
            self.assertFalse(viewer.char_data)
        widget.close()


if __name__ == '__main__':
    unittest.main()
