import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import app
from database import FileDatabase


class AppDefaultsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = FileDatabase(self.root / "test.sqlite3")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_documents_dir_is_seeded_once_when_no_managed_dirs_exist(self) -> None:
        documents = self.root / "Documents"
        documents.mkdir()

        with patch.object(app, "default_managed_dirs", return_value=[documents]):
            app.ensure_default_managed_dirs(self.db)
            app.ensure_default_managed_dirs(self.db)

        self.assertEqual(self.db.list_managed_dirs(), [str(documents.resolve())])

    def test_existing_managed_dirs_are_kept_and_full_disk_is_added(self) -> None:
        existing = self.root / "Existing"
        documents = self.root / "Documents"
        existing.mkdir()
        documents.mkdir()
        self.db.add_managed_dir(existing, 1.0)

        with patch.object(app, "default_managed_dirs", return_value=[documents]):
            app.ensure_default_managed_dirs(self.db)

        self.assertEqual(self.db.list_managed_dirs(), [str(documents.resolve()), str(existing.resolve())])

    def test_existing_managed_dirs_are_kept_when_full_disk_is_added(self) -> None:
        existing = self.root / "Existing"
        existing.mkdir()
        self.db.add_managed_dir(existing, 1.0)

        with patch.object(app, "default_managed_dirs", return_value=[Path("/")]):
            app.ensure_default_managed_dirs(self.db)

        self.assertEqual(self.db.list_managed_dirs(), ["/", str(existing.resolve())])

    def test_old_documents_only_default_is_migrated_to_full_disk_default(self) -> None:
        documents = Path.home() / "Documents"
        self.db.add_managed_dir(documents, 1.0)

        with patch.object(app, "default_managed_dirs", return_value=[Path("/")]):
            app.ensure_default_managed_dirs(self.db)

        self.assertEqual(self.db.list_managed_dirs(), ["/"])


if __name__ == "__main__":
    unittest.main()
