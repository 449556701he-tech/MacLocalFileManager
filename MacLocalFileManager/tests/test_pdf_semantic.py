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
from semantic.chunker import chunk_text
from semantic.config import SEMANTIC_ENABLED_SETTING
from semantic.indexer import PdfSemanticIndexer
from semantic.search import REASON_PDF_SEMANTIC


class PdfSemanticTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = FileDatabase(self.root / "test.sqlite3")
        self.indexer = FileIndexer(self.db)
        self.searcher = FileSearcher(self.db)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_indexed_pdf(self, name: str = "旅行资料.pdf") -> int:
        path = self.root / name
        path.write_text("not a real pdf fixture", encoding="utf-8")
        timestamp = time.time()
        os.utime(path, (timestamp, timestamp))
        self.indexer.add_directory(self.root)
        self.indexer.scan_all(include_content=False, include_ocr=False)
        with self.db.connect() as conn:
            row = conn.execute("SELECT id FROM files WHERE filename = ?", (name,)).fetchone()
        return int(row["id"])

    def test_chunk_text_uses_stable_keys_and_overlap(self) -> None:
        chunks = chunk_text("一" * 10 + "二" * 10 + "三" * 10, prefix="pdf", target_size=12, overlap=2)

        self.assertEqual([chunk.item_key for chunk in chunks], ["pdf:0", "pdf:1", "pdf:2"])
        self.assertTrue(chunks[0].text.endswith("二二"))
        self.assertTrue(chunks[1].text.startswith("二二二"))

    def test_pdf_semantic_indexer_indexes_existing_pdf_content(self) -> None:
        file_id = self.create_indexed_pdf()
        self.db.upsert_file_content(
            file_id=file_id,
            content_text="三亚沙滩度假攻略，包含酒店、海岸和出行建议。",
            metadata="[PDF 第1页]",
            source_size=123,
            source_modified_at=456,
        )
        self.db.set_bool_setting(SEMANTIC_ENABLED_SETTING, True)

        indexed, failed, skipped = PdfSemanticIndexer(self.db).index_existing_pdf_content()

        self.assertEqual((indexed, failed, skipped), (1, 0, 0))
        second = PdfSemanticIndexer(self.db).index_existing_pdf_content()
        self.assertEqual(second, (0, 0, 1))

    def test_searcher_returns_pdf_semantic_hits_when_enabled(self) -> None:
        file_id = self.create_indexed_pdf()
        self.db.upsert_file_content(
            file_id=file_id,
            content_text="三亚沙滩度假攻略，包含酒店、海岸和出行建议。",
            metadata="[PDF 第1页]",
            source_size=123,
            source_modified_at=456,
        )
        self.db.set_bool_setting(SEMANTIC_ENABLED_SETTING, True)
        PdfSemanticIndexer(self.db).index_existing_pdf_content()

        results = self.searcher.search("度假推荐", semantic=True)

        self.assertEqual(results[0].filename, "旅行资料.pdf")
        self.assertEqual(results[0].reason, REASON_PDF_SEMANTIC)
        self.assertEqual(results[0].match_type, "语义命中")

    def test_semantic_results_are_hidden_when_disabled(self) -> None:
        file_id = self.create_indexed_pdf()
        self.db.upsert_file_content(
            file_id=file_id,
            content_text="三亚沙滩度假攻略，包含酒店、海岸和出行建议。",
            metadata="[PDF 第1页]",
            source_size=123,
            source_modified_at=456,
        )

        results = self.searcher.search("度假推荐", semantic=True)

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
