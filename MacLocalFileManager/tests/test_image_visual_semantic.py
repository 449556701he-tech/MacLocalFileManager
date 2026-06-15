from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from database import FileDatabase
from file_categories import CATEGORY_IMAGES
from indexer import FileIndexer
from searcher import FileSearcher
from semantic.config import SEMANTIC_ENABLED_SETTING
from semantic.indexer import ImageVisualSemanticIndexer
from semantic.search import REASON_IMAGE_VISUAL_SEMANTIC


class ImageVisualSemanticTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = FileDatabase(self.root / "test.sqlite3")
        self.indexer = FileIndexer(self.db)
        self.searcher = FileSearcher(self.db)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_indexed_image(self, name: str = "IMG_0001.jpg", payload: bytes | None = None) -> int:
        path = self.root / name
        path.write_bytes(payload or "海岸 晚霞 蓝色海面".encode("utf-8"))
        timestamp = time.time()
        os.utime(path, (timestamp, timestamp))
        self.indexer.add_directory(self.root)
        self.indexer.scan_all(include_content=False, include_ocr=False)
        with self.db.connect() as conn:
            row = conn.execute("SELECT id FROM files WHERE filename = ?", (name,)).fetchone()
        return int(row["id"])

    def test_image_visual_semantic_indexer_indexes_existing_images(self) -> None:
        self.create_indexed_image()
        self.db.set_bool_setting(SEMANTIC_ENABLED_SETTING, True)

        indexed, failed, skipped = ImageVisualSemanticIndexer(self.db).index_existing_images()

        self.assertEqual((indexed, failed, skipped), (1, 0, 0))
        second = ImageVisualSemanticIndexer(self.db).index_existing_images()
        self.assertEqual(second, (0, 0, 1))

    def test_searcher_returns_image_visual_semantic_hits_when_enabled(self) -> None:
        self.create_indexed_image()
        self.db.set_bool_setting(SEMANTIC_ENABLED_SETTING, True)
        ImageVisualSemanticIndexer(self.db).index_existing_images()

        results = self.searcher.search("海岸晚霞", semantic=True, category=CATEGORY_IMAGES)

        self.assertEqual(results[0].filename, "IMG_0001.jpg")
        self.assertEqual(results[0].reason, REASON_IMAGE_VISUAL_SEMANTIC)
        self.assertEqual(results[0].match_type, "语义命中")

    def test_image_visual_semantic_results_are_hidden_when_disabled(self) -> None:
        self.create_indexed_image()

        results = self.searcher.search("海岸晚霞", semantic=True, category=CATEGORY_IMAGES)

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
