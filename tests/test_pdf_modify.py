import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf as fitz

from app.common.pdf_modify_coordinates import PageTransform
from app.common.pdf_text_edit import (
    EditError, EditSession, analyze, characters, edit_document, hit_test, verify_outside,
)


class TextEditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_pdf(self, texts=("2025년", "10년", "100,000원", "보험기간"), background=True):
        path = self.root / "source.pdf"
        with fitz.open() as doc:
            page = doc.new_page(width=420, height=420)
            font = fitz.Font("cjk")
            page.insert_font(fontname="Original", fontbuffer=font.buffer)
            if background:
                page.draw_rect(fitz.Rect(20, 20, 400, 300), fill=(.8, .9, .75))
                for y in (40, 90, 140, 190, 240):
                    page.draw_line((20, y), (400, y), color=(0, 0, 0))
            for i, text in enumerate(texts):
                page.insert_text((40, 70 + i * 50), text, fontname="Original", fontsize=14)
                page.insert_text((250, 70 + i * 50), "Keep intact", fontsize=12)
            page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(300, 350, 390, 370),
                              "uri": "https://example.com"})
            doc.save(path)
        return path

    def test_phase1_korean_replacements_in_table_and_paragraph(self):
        for background in (False, True):
            path = self.make_pdf(background=background)
            data = path.read_bytes()
            for old, new in (("2025년", "2026년"), ("10년", "20년"),
                             ("100,000원", "120,000원"), ("보험기간", "보장기간")):
                with fitz.open(stream=data, filetype="pdf") as doc:
                    target = next(r for r in analyze(doc[0]) if r.text == old)
                result, command = edit_document(data, 0, target, new)
                with fitz.open(stream=data, filetype="pdf") as a, fitz.open(stream=result, filetype="pdf") as b:
                    self.assertNotIn(old, b[0].get_text())
                    self.assertIn(new, b[0].get_text())
                    self.assertEqual(a[0].get_drawings(), b[0].get_drawings())
                    verify_outside(a[0], b[0], command.rect)
                data = result

    def test_coordinate_roundtrip_crop_rotation_zoom(self):
        with fitz.open() as doc:
            page = doc.new_page(width=600, height=800)
            page.insert_text((140, 170), "Hello")
            page.set_cropbox(fitz.Rect(100, 100, 500, 700))
            for rotation in (0, 90, 180, 270):
                page.set_rotation(rotation)
                for zoom in (.5, 1, 1.25, 1.5, 2.5):
                    transform = PageTransform.for_page(page, zoom, (23, -100))
                    run = analyze(page)[0]
                    p = fitz.Rect(run.boxes[0]).tl + (2, 2)
                    view = transform.to_view(p)
                    actual = transform.to_pdf(view)
                    self.assertAlmostEqual(p.x, actual.x, places=4)
                    self.assertAlmostEqual(p.y, actual.y, places=4)
                    self.assertEqual(hit_test([run], actual).text, "Hello")

    def test_snapshots_branching_save_and_source_preservation(self):
        path = self.make_pdf()
        original = path.read_bytes()
        session = EditSession(path)
        self.addCleanup(session.close)
        def change(old, new):
            with fitz.open(stream=session.data, filetype="pdf") as d:
                target = next(r for r in analyze(d[0], session.revision) if r.text == old)
            session.commit(session.prepare(0, target, new))
        change("10년", "20년")
        first = session.data
        change("20년", "15년")
        session.undo()
        self.assertEqual(session.data, first)
        session.redo()
        with fitz.open(stream=session.data, filetype="pdf") as d:
            self.assertIn("15년", d[0].get_text())
        session.undo()
        change("20년", "30년")
        self.assertEqual(len(session.commands), 2)
        session.undo()
        session.undo()
        self.assertEqual(session.data, original)
        session.redo()
        destination = self.root / "edited.pdf"
        session.save_as(destination)
        self.assertFalse(session.dirty)
        self.assertEqual(path.read_bytes(), original)
        with fitz.open(destination) as d:
            self.assertIn("20년", d[0].get_text())
        with self.assertRaises(EditError):
            session.save_as(path)

    def test_overflow_overlap_and_stale_selection_rejected(self):
        path = self.make_pdf()
        session = EditSession(path)
        self.addCleanup(session.close)
        with fitz.open(path) as doc:
            target = next(r for r in analyze(doc[0]) if r.text == "10년")
        with self.assertRaises(EditError):
            session.prepare(0, target, "123456789년")
        session.commit(session.prepare(0, target, "20년"))
        with self.assertRaises(EditError):
            session.prepare(0, target, "30년")
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((50, 50), "Overlap")
            page.insert_text((50, 50), "Other")
            target = analyze(page)[0]
            with self.assertRaises(EditError):
                edit_document(doc.tobytes(), 0, target, "")

    def test_delete_and_add_actual_content(self):
        path = self.make_pdf()
        with fitz.open(path) as doc:
            target = next(r for r in analyze(doc[0]) if r.text == "10년")
        data, _ = edit_document(path.read_bytes(), 0, target, "")
        font_path = self.root / "font.ttf"
        font_path.write_bytes(fitz.Font("cjk").buffer)
        data, _ = edit_document(data, 0, None, "추가 123", font_path=font_path,
                                origin=(40, 330), width=150, size=14, color=0x803020)
        with fitz.open(stream=data, filetype="pdf") as doc:
            self.assertNotIn("10년", doc[0].get_text())
            self.assertIn("추가 123", doc[0].get_text())

    def test_english_bold_sizes_colors_and_subset(self):
        for name in ("helv", "hebo", "heit", "tiro", "cour"):
            with fitz.open() as doc:
                page = doc.new_page()
                page.insert_text((40, 80), "Policy 2025 / ABC", fontname=name,
                                 fontsize=17, color=(.4, .2, .1))
                runs = analyze(page)
                # Select a word within a larger span using precise character coordinates.
                run = runs[0].subset(7, 11)
                result, command = edit_document(doc.tobytes(), 0, run, "2026")
                with fitz.open(stream=result, filetype="pdf") as saved:
                    self.assertIn("2026", saved[0].get_text())
                    self.assertEqual(command.size, 17)
                    self.assertEqual(command.color, run.color)

    def test_image_background_and_other_page_unchanged(self):
        with fitz.open() as doc:
            page = doc.new_page(width=300, height=300)
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 100), False)
            pix.clear_with(190)
            page.insert_image(fitz.Rect(0, 0, 300, 300), pixmap=pix)
            page.insert_text((40, 80), "2025", fontsize=14)
            other = doc.new_page(width=500, height=400)
            other.insert_text((40, 100), "Other page")
            target = analyze(doc[0])[0]
            source = doc.tobytes()
            result, command = edit_document(source, 0, target, "2026")
            with fitz.open(stream=result, filetype="pdf") as saved:
                self.assertEqual(doc[0].get_image_info(hashes=True)[0]["digest"],
                                 saved[0].get_image_info(hashes=True)[0]["digest"])
                self.assertEqual(doc[1].get_pixmap().samples, saved[1].get_pixmap().samples)
                verify_outside(doc[0], saved[0], command.rect)

    def test_rotated_cropped_page_edit(self):
        for rotation in (0, 90, 180, 270):
            with fitz.open() as doc:
                page = doc.new_page(width=500, height=700)
                page.insert_text((120, 200), "2025")
                page.set_cropbox(fitz.Rect(80, 100, 450, 600))
                page.set_rotation(rotation)
                target = analyze(page)[0]
                result, _ = edit_document(doc.tobytes(), 0, target, "2026")
                with fitz.open(stream=result, filetype="pdf") as saved:
                    self.assertEqual(saved[0].rotation, rotation)
                    self.assertEqual(saved[0].cropbox, page.cropbox)
                    self.assertIn("2026", saved[0].get_text())

    def test_reject_links_redactions_vertical_and_missing_glyph(self):
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((40, 80), "Hello")
            run = analyze(page)[0]
            with self.assertRaises(EditError):
                edit_document(doc.tobytes(), 0, run, "한글")
            page.insert_link({"kind": fitz.LINK_URI, "from": run.rect, "uri": "https://example.com"})
            with self.assertRaises(EditError):
                edit_document(doc.tobytes(), 0, run, "")

    def test_subset_font_and_shared_form_fail_closed(self):
        with fitz.open() as source:
            page = source.new_page()
            font = fitz.Font("cjk")
            page.insert_font(fontname="Subset", fontbuffer=font.buffer)
            page.insert_text((40, 80), "보험기간", fontname="Subset")
            source.subset_fonts()
            data = source.tobytes(garbage=4)
        with fitz.open(stream=data, filetype="pdf") as doc:
            target = analyze(doc[0])[0]
            with self.assertRaises(EditError):
                edit_document(data, 0, target, "보장기간")
            with fitz.open() as form_doc:
                page = form_doc.new_page()
                page.show_pdf_page(page.rect, doc, 0)
                target = analyze(page)[0]
                with self.assertRaises(EditError):
                    edit_document(form_doc.tobytes(), 0, target, "")
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((80, 200), "Rotate", rotate=90)
            run = analyze(page)[0]
            self.assertFalse(run.writable)
            with self.assertRaises(EditError):
                edit_document(doc.tobytes(), 0, run, "")
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((40, 80), "Hello")
            run = analyze(page)[0]
            page.add_redact_annot(fitz.Rect(300, 300, 400, 400))
            with self.assertRaises(EditError):
                edit_document(doc.tobytes(), 0, run, "")

    def test_encrypted_scan_signature_and_corrupt_documents(self):
        source = self.make_pdf()
        encrypted = self.root / "encrypted.pdf"
        with fitz.open(source) as doc:
            doc.save(encrypted, encryption=fitz.PDF_ENCRYPT_AES_256,
                     owner_pw="owner", user_pw="reader", permissions=fitz.PDF_PERM_PRINT)
        session = EditSession(encrypted, "reader")
        self.addCleanup(session.close)
        self.assertTrue(session.restriction)
        with self.assertRaises(EditError):
            session.save_as(self.root / "blocked.pdf")
        signed = self.root / "signed.pdf"
        with fitz.open() as doc:
            page = doc.new_page()
            widget = fitz.Widget()
            widget.field_name = "Signature"
            widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
            widget.rect = fitz.Rect(30, 30, 150, 90)
            page.add_widget(widget)
            doc.save(signed)
        session2 = EditSession(signed)
        self.addCleanup(session2.close)
        self.assertTrue(session2.restriction)
        scan = self.root / "scan.pdf"
        with fitz.open() as doc:
            page = doc.new_page()
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), False)
            pix.clear_with(200)
            page.insert_image(page.rect, pixmap=pix)
            doc.save(scan)
            self.assertEqual(analyze(page), [])
        bad = self.root / "bad.pdf"
        bad.write_bytes(b"Not a PDF")
        with self.assertRaises(Exception):
            EditSession(bad)

    def test_save_failure_keeps_existing_destination(self):
        session = EditSession(self.make_pdf())
        self.addCleanup(session.close)
        destination = self.root / "existing.pdf"
        destination.write_bytes(b"unchanged")
        with patch("app.common.pdf_text_edit.os.replace", side_effect=OSError("denied")):
            with self.assertRaises(OSError):
                session.save_as(destination)
        self.assertEqual(destination.read_bytes(), b"unchanged")
        self.assertEqual(list(self.root.glob(".posid-*")), [])

    def test_explicit_substitute_font_shrink_and_color(self):
        path = self.make_pdf()
        font_path = self.root / "font.ttf"
        font_path.write_bytes(fitz.Font("cjk").buffer)
        with fitz.open(path) as doc:
            target = next(r for r in analyze(doc[0]) if r.text == "10년")
        with self.assertRaises(EditError):
            edit_document(path.read_bytes(), 0, target, "123년", font_path=font_path)
        result, command = edit_document(path.read_bytes(), 0, target, "123년",
                                        font_path=font_path, shrink_min=10, color=0xA44735)
        self.assertLess(command.size, 14)
        self.assertGreaterEqual(command.size, 10)
        self.assertTrue(command.replacement_font)
        with fitz.open(stream=result, filetype="pdf") as doc:
            changed = next(r for r in analyze(doc[0]) if r.text == "123년")
            self.assertEqual(changed.color, 0xA44735)


class EditorUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def wait(self, widget):
        import time
        from PyQt6.QtTest import QTest
        until = time.monotonic() + 30
        while widget.job or widget.preview_timer.isActive():
            self.app.processEvents()
            QTest.qWait(20)
            self.assertLess(time.monotonic(), until, "background operation timeout")
        widget.thumb_timer.stop()
        self.app.processEvents()

    def test_click_inline_preview_apply_undo_save_and_menu(self):
        from PyQt6.QtCore import Qt, QPoint
        from PyQt6.QtTest import QTest
        from app.main_window import MdiMainWindow
        helper = TextEditTests()
        helper.setUp()
        path = helper.make_pdf()
        window = MdiMainWindow()
        window.show()
        window.open_tool("pdf_modify")
        widget = window.current_tool_widget
        self.assertEqual(window.current_tool_key, "pdf_modify")
        try:
            widget.load_pdf(str(path))
            self.wait(widget)
            self.assertIsNotNone(widget.session)
            target = next(r for r in widget.canvas.runs if r.text == "10년")
            point = widget.canvas.transform.to_view(fitz.Rect(target.boxes[0]).tl + (3, 5))
            QTest.mouseClick(widget.canvas, Qt.MouseButton.LeftButton,
                             pos=QPoint(round(point.x), round(point.y)))
            self.assertEqual(widget.text_edit.text(), "10년")
            QTest.mouseDClick(widget.canvas, Qt.MouseButton.LeftButton,
                              pos=QPoint(round(point.x), round(point.y)))
            self.assertTrue(widget.canvas.inline.isVisible())
            widget.canvas.inline.setText("20년")
            widget.canvas.inline.textEdited.emit("20년")
            self.wait(widget)
            self.assertEqual(widget.text_edit.text(), "20년")
            self.assertIsNotNone(widget.prepared, widget.support.text())
            self.assertEqual(widget.session.index, 0)
            widget.apply_edit()
            self.wait(widget)
            self.assertEqual(widget.session.index, 1)
            widget.canvas.setFocus()
            QTest.keyClick(widget.canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
            self.wait(widget)
            self.assertEqual(widget.session.index, 0)
            QTest.keyClick(widget.canvas, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
            self.wait(widget)
            self.assertEqual(widget.session.index, 1)
            saved = helper.root / "ui_saved.pdf"
            widget.session.save_as(saved)
            self.assertFalse(widget.session.dirty)
            widget.original_button.click()
            self.wait(widget)
            self.assertTrue(widget.canvas.read_only)
            self.assertIn("10년", [r.text for r in widget.canvas.runs])
            widget.original_button.click()
            self.wait(widget)
            self.assertFalse(widget.canvas.read_only)
            # Use the main window's integration without changing the comparison engine.
            widget.compare_requested.emit(str(path), str(saved))
            self.assertEqual(window.current_tool_key, "pdf_hf_compare")
            full = window.current_tool_widget
            self.assertIn("10년", full.viewer1.pdf_doc[0].get_text())
            self.assertIn("20년", full.viewer2.pdf_doc[0].get_text())
            window.open_tool("pdf_compare")
            window.open_tool("pdf_modify")
            self.assertIs(widget, window.current_tool_widget)
            for key in ("pdf_hf_compare", "pdf_editor", "pdf_create", "file_rename"):
                window.open_tool(key)
                self.assertEqual(window.current_tool_key, key)
        finally:
            self.wait(widget)
            widget.dispose()
            for tool in window.tool_cache.values():
                for name in ("viewer1", "viewer2"):
                    viewer = getattr(tool, name, None)
                    if viewer is not None and viewer.pdf_doc:
                        viewer.pdf_doc.close()
            window.close()
            helper.temp.cleanup()


if __name__ == "__main__":
    unittest.main()
