import os

from PyQt6.QtCore import QSettings


def load_dir(key):
    path = QSettings("PdfDiff", "PdfDiff").value(key, "") or ""
    return path if path and os.path.isdir(str(path)) else ""


def save_dir(key, path):
    QSettings("PdfDiff", "PdfDiff").setValue(key, path or "")
