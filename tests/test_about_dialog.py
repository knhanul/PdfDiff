import os
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from app.common.about_dialog import (
    IMAGE_MAX_HEIGHT, NO_INFO_TEXT, POPUP_MARGIN, POPUP_WIDTH,
    AboutDialog, AboutInfo, _normalize_build_date, get_about_info,
)
from app.common.resources import RELEASE_DATE, VERSION
from configs.settings import SETTINGS

CONTENT_WIDTH = POPUP_WIDTH - 2 * POPUP_MARGIN


def _make_image(width, height, directory):
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor('#2266AA'))
    path = os.path.join(directory, f'img_{width}x{height}.png')
    pixmap.save(path, 'PNG')
    return path


class BuildDateNormalizationTests(unittest.TestCase):
    def test_normalizes_common_formats(self):
        self.assertEqual(_normalize_build_date('2026-10-09'), '2026.10.09')
        self.assertEqual(_normalize_build_date('2026/1/5'), '2026.01.05')
        self.assertEqual(_normalize_build_date('2026.10.9'), '2026.10.09')

    def test_passthrough_and_empty(self):
        self.assertEqual(_normalize_build_date('unknown'), 'unknown')
        self.assertEqual(_normalize_build_date(''), '')
        self.assertEqual(_normalize_build_date(None), '')


class AboutDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _dialog(self, **kwargs):
        kwargs.setdefault('app_name', 'TestApp')
        return AboutDialog(AboutInfo(**kwargs))

    def _image_label(self, dialog):
        return dialog.findChild(QLabel, 'aboutImage')

    def test_missing_info_shows_placeholder(self):
        dialog = self._dialog(version='', build_date='', creator='', image_path=None)
        values = [label.text() for label in dialog.findChildren(QLabel, 'aboutInfoValue')]
        self.assertEqual(values, [NO_INFO_TEXT, NO_INFO_TEXT, NO_INFO_TEXT])

    def test_rows_show_version_build_date_creator(self):
        dialog = self._dialog(version='1.2.0-dev', build_date='2026.10.13',
                              creator='테스트 조직', image_path=None)
        keys = [label.text() for label in dialog.findChildren(QLabel, 'aboutInfoKey')]
        values = [label.text() for label in dialog.findChildren(QLabel, 'aboutInfoValue')]
        self.assertEqual(keys, ['버전', '빌드일자', '제작'])
        self.assertEqual(values, ['1.2.0-dev', '2026.10.13', '테스트 조직'])

    def test_missing_image_hides_area(self):
        for path in (None, 'Z:/nonexistent/image.png'):
            dialog = self._dialog(image_path=path)
            self.assertIsNone(self._image_label(dialog))

    def test_images_keep_ratio_and_fit_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases = [
                (800, 400),   # 가로형
                (400, 800),   # 세로형
                (600, 600),   # 정사각형
                (100, 60),    # 작은 이미지 (확대하지 않음)
            ]
            for width, height in cases:
                path = _make_image(width, height, tmp)
                dialog = self._dialog(image_path=path)
                label = self._image_label(dialog)
                self.assertIsNotNone(label)
                size = label.pixmap().size()
                self.assertLessEqual(size.width(), CONTENT_WIDTH)
                self.assertLessEqual(size.height(), IMAGE_MAX_HEIGHT)
                self.assertAlmostEqual(
                    size.width() / size.height(), width / height, places=2)
                if width <= CONTENT_WIDTH and height <= IMAGE_MAX_HEIGHT:
                    self.assertEqual(size.width(), width)
                    self.assertEqual(size.height(), height)
                dialog.deleteLater()

    def test_long_strings_wrap(self):
        dialog = self._dialog(
            app_name='매우 긴 프로그램 이름 ' * 6,
            creator='아주 긴 제작 조직명 ' * 8,
            image_path=None)
        name_label = dialog.findChild(QLabel, 'aboutAppName')
        self.assertTrue(name_label.wordWrap())
        values = dialog.findChildren(QLabel, 'aboutInfoValue')
        self.assertTrue(all(label.wordWrap() for label in values))

    def test_close_button_accepts(self):
        dialog = self._dialog(image_path=None)
        button = dialog.findChild(QPushButton, 'aboutCloseBtn')
        self.assertIsNotNone(button)
        dialog.show()
        button.click()
        self.assertFalse(dialog.isVisible())

    def test_popup_width(self):
        dialog = self._dialog(image_path=None)
        self.assertEqual(dialog.width(), POPUP_WIDTH)


class AboutInfoDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_reads_settings_and_build_metadata(self):
        info = get_about_info()
        self.assertEqual(info.app_name, SETTINGS['APP_NAME'])
        self.assertEqual(info.version, VERSION)
        self.assertEqual(info.build_date, _normalize_build_date(RELEASE_DATE))
        self.assertEqual(info.accent_color, SETTINGS['THEME_COLOR_PRIMARY'])
        self.assertTrue(info.creator)

    def test_image_path_resolves_aikickoff(self):
        info = get_about_info()
        self.assertIsNotNone(info.image_path)
        self.assertTrue(info.image_path.endswith('AIKickOff.png'))
        self.assertTrue(os.path.exists(info.image_path))


if __name__ == '__main__':
    unittest.main()
