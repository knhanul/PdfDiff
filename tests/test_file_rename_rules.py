import os
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from app.tools.file_rename import FileRenameWidget


class FileRenameRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.widget = FileRenameWidget()
        self.addCleanup(self.widget.close)

    def add_files(self, *names):
        paths = []
        for name in names:
            path = Path(self.temp.name) / name
            path.write_text("test", encoding="utf-8")
            paths.append(str(path))
        self.widget._add_paths(paths)

    def test_initial_preview_is_not_treated_as_user_typed_name(self):
        self.add_files("alpha.txt", "beta.txt")
        for row, name in enumerate(("alpha.txt", "beta.txt")):
            item = self.widget.file_table.item(row, 2)
            self.assertFalse(bool(item.data(Qt.ItemDataRole.UserRole + 1)))
            self.assertEqual(item.text(), name)

    def test_date_and_sequence_rules_preview_and_rename_all_checked_files(self):
        self.add_files("alpha.txt", "beta.txt")
        self.widget.date_check.setChecked(True)
        self.widget.number_check.setChecked(True)
        today = datetime.now().strftime("%Y-%m-%d")

        expected = (
            f"001_{today}_alpha.txt",
            f"002_{today}_beta.txt",
        )
        self.assertEqual(
            tuple(self.widget.file_table.item(row, 2).text() for row in range(2)),
            expected,
        )

        with patch("app.tools.file_rename.QMessageBox.information"):
            self.widget.apply_names()

        self.assertTrue(all((Path(self.temp.name) / name).is_file() for name in expected))
        self.assertEqual(self.widget.count_label.text(), "체크 2 / 전체 2")

    def test_no_rules_message_explains_checked_files_have_no_changes(self):
        self.add_files("alpha.txt")
        with patch("app.tools.file_rename.QMessageBox.information") as information:
            self.widget.apply_names()
        information.assert_called_once()
        self.assertIn("현재와 같습니다", information.call_args.args[2])

    def test_editing_name_cell_still_marks_a_manual_override(self):
        self.add_files("alpha.txt")
        item = self.widget.file_table.item(0, 2)
        item.setText("renamed.txt")
        self.assertTrue(item.data(Qt.ItemDataRole.UserRole + 1))
        self.assertEqual(item.text(), "renamed.txt")


if __name__ == "__main__":
    unittest.main()
