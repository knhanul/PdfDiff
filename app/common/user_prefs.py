import os

from PyQt6.QtCore import QSettings


def load_dir(key):
    path = QSettings("PdfCompare", "PdfCompare").value(key, "") or ""
    return path if path and os.path.isdir(str(path)) else ""


def save_dir(key, path):
    QSettings("PdfCompare", "PdfCompare").setValue(key, path or "")
