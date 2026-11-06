import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pymupdf
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication, QDialog

from app.common.comparison_options import ComparisonOptions, visible_whitespace
from app.common.comparison_settings import ComparisonOptionsDialog, ComparisonSettings
from app.common.pdf_compare_worker import PdfCompareWorker
from app.common.pdf_text_normalizer import collect_raw_chars, normalize_raw_chars
from app.main_window import MdiMainWindow
from app.tools.pdf_compare import PdfCompareWidget
from app.tools.pdf_header_footer_compare import HFCompareWidget


def glyphs(text, page=0):
    raw_dict = {'blocks': [{'type': 0, 'lines': [
        {'spans': [{'chars': [
            {'c': character, 'bbox': (10 + i * 8, 50 + line_no * 18,
                                      18 + i * 8, 62 + line_no * 18)}
            for i, character in enumerate(line)
        ]}]} for line_no, line in enumerate(text.split('\n'))
    ]}]}
    return collect_raw_chars(raw_dict, page)


def normalized(text, options):
    records, _ = normalize_raw_chars(glyphs(text), options=options)
    return ''.join(record['char'] for record in records)


class ComparisonPolicyTests(unittest.TestCase):
    def test_default_keeps_legacy_filter_case_spaces_and_punctuation(self):
        text = 'A B (1), 3.5% + = ₩ 中文 é\nC!'
        self.assertEqual(normalized(text, None), 'ab(1),3.5c!')
        self.assertEqual(normalized(text, ComparisonOptions()), normalized(text, None))

    def test_strict_preserves_unicode_symbols_whitespace_and_case(self):
        text = 'A\t B %+ = ₩ 中文 é e\u0301\nSecond'
        self.assertEqual(normalized(text, ComparisonOptions.strict()), text)

    def test_each_custom_option_is_independent(self):
        strict = ComparisonOptions(mode='custom', ignore_spaces=False,
                                   ignore_line_breaks=False, ignore_case=False, ignore_symbols=False)
        for field, left, right in (
            ('ignore_spaces', 'A\t B\u00a0', 'AB'),
            ('ignore_line_breaks', 'A\nB', 'AB'),
            ('ignore_case', 'AbC', 'abc'),
            ('ignore_symbols', 'A%+=₩.!', 'A'),
        ):
            with self.subTest(field=field):
                self.assertNotEqual(normalized(left, strict), normalized(right, strict))
                ignored = replace(strict, **{field: True})
                self.assertEqual(normalized(left, ignored), normalized(right, ignored))
        self.assertEqual(normalized('A B\nC', replace(strict, ignore_spaces=True)), 'AB\nC')
        self.assertEqual(normalized('A B\nC', replace(strict, ignore_line_breaks=True)), 'A BC')

    def test_custom_symbol_filter_preserves_letters_and_numbers(self):
        options = ComparisonOptions(mode='custom', ignore_case=False)
        self.assertEqual(normalized('한글中文é 123 %+₩', options), '한글中文é123')

    def test_presets_cannot_have_inconsistent_flags(self):
        self.assertFalse(ComparisonOptions(mode='strict').ignore_symbols)
        self.assertTrue(ComparisonOptions(mode='body', ignore_spaces=False).ignore_spaces)

    def test_multicodepoint_glyph_and_case_expansion_keep_one_offset_per_record(self):
        raw = glyphs('İ')
        raw[0]['source_char'] = 'İe\u0301'
        options = ComparisonOptions(mode='custom', ignore_symbols=False)
        records, text = normalize_raw_chars(raw, options=options)
        self.assertEqual(text, 'İe\u0301')
        self.assertEqual(''.join(char['char'] for char in records), 'i\u0307e\u0301')
        self.assertTrue(all(len(char['char']) == 1 for char in records))
        self.assertTrue(all(char['bbox'] == raw[0]['bbox'] for char in records))

    def test_line_and_page_breaks_have_valid_highlight_anchors(self):
        raw = glyphs('Alpha\nBeta', 0) + glyphs('Gamma', 1)
        records, _ = normalize_raw_chars(raw, page_aware=True, options=ComparisonOptions.strict())
        self.assertEqual(''.join(char['char'] for char in records), 'Alpha\nBeta\nGamma')
        breaks = [char for char in records if char['char'] == '\n']
        self.assertEqual(len(breaks), 2)
        for char in breaks:
            self.assertEqual(char['page'], 0)
            self.assertTrue(char['synthetic'])
            self.assertGreater(char['bbox'][2], char['bbox'][0])

    def test_worker_maps_preserved_symbol_to_its_original_rectangle(self):
        left, _ = normalize_raw_chars(glyphs('10%'), options=ComparisonOptions.strict())
        right, _ = normalize_raw_chars(glyphs('10'), options=ComparisonOptions.strict())
        results = []
        worker = PdfCompareWorker(left, right, '10%', '10')
        worker.result_ready.connect(results.append)
        worker.run()
        self.assertEqual(results[0]['opcodes'][-1][0], 'delete')
        self.assertIn(left[-1]['bbox'], [item['bbox'] for item in results[0]['highlights1']])
        self.assertFalse(results[0]['highlights2'])

    def test_invisible_differences_are_readable(self):
        self.assertEqual(visible_whitespace(' \t\n\u00a0'), '␠⇥↵⍽')


class ComparisonOptionsUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.info = patch('PyQt6.QtWidgets.QMessageBox.information')
        self.info_mock = self.info.start()
        self.addCleanup(self.info.stop)

    def make_pdf(self, name, pages):
        path = Path(self.temp.name) / name
        with pymupdf.open() as pdf:
            for text in pages:
                page = pdf.new_page(width=300, height=400)
                page.insert_text((40, 75), text, fontsize=16)
            pdf.save(path)
        return path

    def load_pair(self, widget, left=('Alpha +10%',), right=('Alpha 10%',)):
        for viewer, name, pages in ((widget.viewer1, 'left.pdf', left),
                                    (widget.viewer2, 'right.pdf', right)):
            self.assertTrue(viewer.load_pdf(self.make_pdf(name, pages)))
            self.addCleanup(viewer.pdf_doc.close)
            if hasattr(viewer, 'selection_areas'):
                viewer.selection_areas = {n: [pymupdf.Rect(20, 40, 280, 350)] for n in range(len(pages))}
                viewer.rebuild_selection_data()

    def wait_for_comparison(self, widget):
        loop = QEventLoop()
        poll = QTimer()
        poll.setInterval(10)
        poll.timeout.connect(lambda: loop.quit() if not widget.comparison_settings.busy else None)
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        poll.start()
        timeout.start(4000)
        loop.exec()
        poll.stop()
        timeout.stop()
        self.assertFalse(widget.comparison_settings.busy, 'Comparison did not finish')
        self.assertIsNone(widget.compare_manager)

    def test_dialog_presets_and_cancel_do_not_change_shared_state(self):
        settings = ComparisonSettings()
        dialog = ComparisonOptionsDialog(settings.options)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.selected_options(), ComparisonOptions())
        dialog.mode_combo.setCurrentIndex(1)
        self.assertEqual(dialog.selected_options(), ComparisonOptions.strict())
        self.assertTrue(all(box.isChecked() for box in dialog.checkboxes.values()))
        dialog.mode_combo.setCurrentIndex(2)
        dialog.checkboxes['ignore_symbols'].setChecked(False)
        self.assertTrue(dialog.selected_options().ignore_symbols)
        self.assertFalse(dialog.selected_options().ignore_spaces)
        dialog.reject()
        self.assertEqual(settings.options, ComparisonOptions())

    def test_both_tools_share_settings_including_new_and_reopened_tools(self):
        window = MdiMainWindow()
        self.addCleanup(window.close)
        window.open_tool('pdf_compare')  # viewer-first: tools open on demand
        area = window.current_tool_widget
        with patch.object(ComparisonOptionsDialog, 'exec', return_value=QDialog.DialogCode.Accepted), \
             patch.object(ComparisonOptionsDialog, 'selected_options', return_value=ComparisonOptions.strict()):
            area.btn_comparison_options.click()
        window.open_tool('pdf_hf_compare')
        full = window.current_tool_widget
        self.assertIs(area.comparison_settings, full.comparison_settings)
        self.assertEqual(full.viewer1.comparison_options, ComparisonOptions.strict())
        self.assertIn('엄격', full.btn_comparison_options.text())
        full.btn_focus_mode.click()
        self.assertFalse(full.btn_comparison_options.isHidden())
        self.assertEqual(full.btn_comparison_options.height(), 28)
        window.close_current_tool()
        window.open_tool('pdf_hf_compare')
        self.assertEqual(window.current_tool_widget.viewer1.comparison_options, ComparisonOptions.strict())
        window.comparison_settings.set_options(ComparisonOptions())
        self.assertEqual(area.viewer1.comparison_options, ComparisonOptions())

    def test_changes_invalidate_results_but_keep_selection_exclusions_and_search(self):
        for widget_class in (PdfCompareWidget, HFCompareWidget):
            with self.subTest(tool=widget_class.__name__):
                widget = widget_class()
                self.addCleanup(widget.close)
                self.load_pair(widget)
                widget.viewer1.search_input.setText('Alpha')
                widget.viewer1.header_ratio = 0.07
                selected = dict(getattr(widget.viewer1, 'selection_areas', {}))
                widget.diff_list = [{'type': 'delete', 'pdf': 'PDF 1', 'page': 1, 'text': 'old'}]
                widget.last_s1_norm = 'old'
                widget.viewer1.word_highlights = {0: [((40, 60, 50, 80), None)]}
                widget.show_diff_list_dialog()
                widget.comparison_settings.set_options(ComparisonOptions.strict())
                self.assertEqual(widget.diff_list, [])
                self.assertEqual(widget.last_s1_norm, '')
                self.assertEqual(widget.viewer1.word_highlights, {})
                self.assertIsNone(widget.diff_list_dialog)
                self.assertEqual(widget.viewer1.search_input.text(), 'Alpha')
                self.assertEqual(widget.viewer1.header_ratio, 0.07)
                self.assertEqual(getattr(widget.viewer1, 'selection_areas', {}), selected)
                self.assertIn('재비교', widget.btn_compare.text())

    def test_options_are_locked_during_work_and_unlocked_on_close(self):
        settings = ComparisonSettings()
        area = PdfCompareWidget(comparison_settings=settings)
        full = HFCompareWidget(comparison_settings=settings)
        self.addCleanup(area.close)
        self.addCleanup(full.close)
        area.show_loading(True)
        self.assertFalse(area.btn_comparison_options.isEnabled())
        self.assertFalse(full.btn_comparison_options.isEnabled())
        self.assertFalse(settings.set_options(ComparisonOptions.strict()))
        area.close()
        self.assertTrue(full.btn_comparison_options.isEnabled())
        self.assertTrue(settings.set_options(ComparisonOptions.strict()))

    def test_area_and_full_extraction_agree_on_strict_page_breaks(self):
        for widget_class in (PdfCompareWidget, HFCompareWidget):
            with self.subTest(tool=widget_class.__name__):
                widget = widget_class()
                self.addCleanup(widget.close)
                self.load_pair(widget, left=('Alpha B', 'Second +10%'))
                widget.comparison_settings.set_options(ComparisonOptions.strict())
                if isinstance(widget, HFCompareWidget):
                    widget.viewer1.extract_body_text()
                self.assertEqual(''.join(char['char'] for char in widget.viewer1.char_data),
                                 'Alpha B\nSecond +10%')
                self.assertEqual({char['page'] for char in widget.viewer1.char_data}, {0, 1})

    def test_async_compare_default_strict_and_return_to_default_in_both_tools(self):
        for widget_class in (PdfCompareWidget, HFCompareWidget):
            with self.subTest(tool=widget_class.__name__):
                widget = widget_class()
                self.addCleanup(widget.close)
                self.load_pair(widget)
                for options, has_changes in ((ComparisonOptions(), False),
                                             (ComparisonOptions.strict(), True),
                                             (ComparisonOptions(), False)):
                    widget.comparison_settings.set_options(options)
                    widget.btn_compare.click()
                    self.wait_for_comparison(widget)
                    self.assertEqual(bool(widget.diff_list), has_changes)
                    self.assertEqual(bool(widget.viewer1.word_highlights), has_changes)
                    self.assertIn('비교 실행', widget.btn_compare.text())
                    if has_changes:
                        plus = next(char for char in widget.viewer1.char_data if char['char'] == '+')
                        self.assertIn(plus['bbox'], [item[0] for item in widget.viewer1.word_highlights[0]])

    def test_late_result_from_old_options_is_ignored(self):
        for widget_class in (PdfCompareWidget, HFCompareWidget):
            widget = widget_class()
            self.addCleanup(widget.close)
            widget._active_comparison_revision = widget.comparison_settings.revision
            widget.comparison_settings.set_options(ComparisonOptions.strict())
            widget._on_compare_result_ready({'s1_norm': 'obsolete'})
            self.assertEqual(widget.last_s1_norm, '')
            widget.comparison_settings.set_options(ComparisonOptions())
            widget._on_compare_result_ready({'s1_norm': 'still obsolete'})
            self.assertEqual(widget.last_s1_norm, '')
            widget._deferred_full_refresh()
            self.info_mock.assert_not_called()

    def test_area_custom_can_compare_when_one_side_is_entirely_ignored(self):
        widget = PdfCompareWidget()
        self.addCleanup(widget.close)
        self.load_pair(widget, left=('%+=',), right=('100',))
        widget.comparison_settings.set_options(ComparisonOptions(mode='custom'))
        self.assertEqual(widget.viewer1.char_data, [])
        with patch('PyQt6.QtWidgets.QMessageBox.warning') as warning:
            widget.btn_compare.click()
            self.wait_for_comparison(widget)
            warning.assert_not_called()
        self.assertEqual(widget.diff_list[0]['type'], 'insert')
        self.assertEqual(widget.diff_list[0]['text'], '100')


if __name__ == '__main__':
    unittest.main()
