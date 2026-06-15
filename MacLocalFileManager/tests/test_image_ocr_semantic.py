import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from database import FileDatabase
from indexer import FileIndexer
from searcher import FileSearcher
from semantic.config import SEMANTIC_ENABLED_SETTING
from semantic.indexer import ImageOcrSemanticIndexer
from semantic.search import REASON_IMAGE_OCR_SEMANTIC


class ImageOcrSemanticTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = FileDatabase(self.root / "test.sqlite3")
        self.indexer = FileIndexer(self.db)
        self.searcher = FileSearcher(self.db)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_indexed_image(self, name: str = "付款截图.png") -> int:
        path = self.root / name
        path.write_bytes(b"fake image")
        timestamp = time.time()
        os.utime(path, (timestamp, timestamp))
        self.indexer.add_directory(self.root)
        self.indexer.scan_all(include_content=False, include_ocr=False)
        with self.db.connect() as conn:
            row = conn.execute("SELECT id FROM files WHERE filename = ?", (name,)).fetchone()
        return int(row["id"])

    def test_image_ocr_semantic_indexer_indexes_existing_ocr_text(self) -> None:
        file_id = self.create_indexed_image()
        self.db.upsert_file_ocr(
            file_id=file_id,
            ocr_text="图片里有三亚沙滩付款确认文字",
            engine="Fake OCR",
            source_size=321,
            source_modified_at=654,
        )
        self.db.set_bool_setting(SEMANTIC_ENABLED_SETTING, True)

        indexed, failed, skipped = ImageOcrSemanticIndexer(self.db).index_existing_ocr_text()

        self.assertEqual((indexed, failed, skipped), (1, 0, 0))
        second = ImageOcrSemanticIndexer(self.db).index_existing_ocr_text()
        self.assertEqual(second, (0, 0, 1))

    def test_searcher_returns_image_ocr_semantic_hits_when_enabled(self) -> None:
        file_id = self.create_indexed_image()
        self.db.upsert_file_ocr(
            file_id=file_id,
            ocr_text="图片里有三亚沙滩付款确认文字",
            engine="Fake OCR",
            source_size=321,
            source_modified_at=654,
        )
        self.db.set_bool_setting(SEMANTIC_ENABLED_SETTING, True)
        ImageOcrSemanticIndexer(self.db).index_existing_ocr_text()

        results = self.searcher.search("付款凭证", semantic=True)

        self.assertEqual(results[0].filename, "付款截图.png")
        self.assertEqual(results[0].reason, REASON_IMAGE_OCR_SEMANTIC)
        self.assertEqual(results[0].match_type, "语义命中")

    def test_image_ocr_semantic_results_are_hidden_when_disabled(self) -> None:
        file_id = self.create_indexed_image()
        self.db.upsert_file_ocr(
            file_id=file_id,
            ocr_text="图片里有三亚沙滩付款确认文字",
            engine="Fake OCR",
            source_size=321,
            source_modified_at=654,
        )

        results = self.searcher.search("付款凭证", semantic=True)

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
