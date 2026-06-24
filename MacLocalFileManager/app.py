import sys
from pathlib import Path

from config import default_managed_dirs
from database import FileDatabase
from indexer import FileIndexer


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from macos_integration import MacOSAppController, should_install_macos_integration
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    db = FileDatabase()
    ensure_default_managed_dirs(db)
    window = MainWindow(db)
    controller = None
    if should_install_macos_integration():
        controller = MacOSAppController(app, window, db)
        controller.install()
        app.macos_controller = controller
    window.show()
    return app.exec()


def ensure_default_managed_dirs(db: FileDatabase) -> None:
    existing_dirs = db.list_managed_dirs()
    documents = str(Path.home() / "Documents")
    if existing_dirs == [documents]:
        db.remove_managed_dir(documents)
        existing_dirs = []

    if "/" in existing_dirs:
        return
    indexer = FileIndexer(db)
    for directory in default_managed_dirs():
        try:
            indexer.add_directory(directory)
        except ValueError:
            continue


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--extract":
        from extractor_runner import main as extractor_main

        raise SystemExit(extractor_main(sys.argv[2:]))
    raise SystemExit(main())
