import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from database import FileDatabase
from models import FileRecord
from semantic.backends.deterministic import DeterministicTextEmbeddingBackend
from semantic.config import MODALITY_PDF_TEXT
from semantic.models import SemanticItem
from semantic.vector_store import SemanticVectorStore


class SemanticSchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_semantic_tables_are_created_for_fresh_database(self) -> None:
        db = FileDatabase(self.root / "fresh.sqlite3")

        with db.connect() as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table'
                    """
                ).fetchall()
            }

        self.assertIn("semantic_models", tables)
        self.assertIn("semantic_items", tables)
        self.assertIn("semantic_embeddings", tables)
        self.assertIn("semantic_jobs", tables)
        self.assertFalse(db.get_bool_setting("semantic_enabled", True))
        self.assertTrue(db.get_bool_setting("semantic_pdf_enabled", False))

    def test_semantic_tables_are_added_to_existing_database(self) -> None:
        db_path = self.root / "existing.sqlite3"
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE app_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.commit()

        db = FileDatabase(db_path)

        with db.connect() as conn:
            row = conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name = 'semantic_items'
                """
            ).fetchone()

        self.assertIsNotNone(row)

    def test_semantic_summary_counts_items_and_errors(self) -> None:
        db = FileDatabase(self.root / "summary.sqlite3")
        path = self.root / "合同.pdf"
        path.write_text("fixture", encoding="utf-8")
        db.upsert_file(FileRecord.from_path(path, 1.0))
        with db.connect() as conn:
            row = conn.execute("SELECT id FROM files WHERE path = ?", (str(path),)).fetchone()

        backend = DeterministicTextEmbeddingBackend()
        store = SemanticVectorStore(db)
        item_id = store.upsert_item(
            SemanticItem(
                id=None,
                file_id=row["id"],
                modality=MODALITY_PDF_TEXT,
                item_key="pdf:0",
                text="合同付款节点",
                metadata="PDF",
                source_size=1,
                source_modified_at=2,
            )
        )
        model_id = store.ensure_model(backend)
        store.upsert_embedding(item_id, model_id, [0.0 for _ in range(backend.dimensions)], error="测试错误")

        summary = db.fetch_semantic_summary()

        self.assertEqual(summary[MODALITY_PDF_TEXT]["items"], 1)
        self.assertEqual(summary[MODALITY_PDF_TEXT]["errors"], 1)


if __name__ == "__main__":
    unittest.main()
