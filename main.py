if __name__ == "__main__":
    # PyInstaller's worker dispatch must run before importing Qt / starting the UI.
    from multiprocessing import freeze_support
    freeze_support()
    from app.main_window import run
    raise SystemExit(run())