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
from semantic.backends.deterministic import DeterministicTextEmbeddingBackend
from semantic.config import MODALITY_TEXT
from semantic.models import SemanticItem
from semantic.vector_store import SemanticVectorStore, cosine_similarity, decode_vector, encode_vector, vector_norm


class VectorStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = FileDatabase(self.root / "test.sqlite3")
        self.indexer = FileIndexer(self.db)
        self.store = SemanticVectorStore(self.db)
        self.backend = DeterministicTextEmbeddingBackend()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_file(self, name: str) -> int:
        path = self.root / name
        path.write_text("fixture", encoding="utf-8")
        timestamp = time.time()
        os.utime(path, (timestamp, timestamp))
        self.indexer.add_directory(self.root)
        self.indexer.scan_all(include_content=False, include_ocr=False)
        return int(self.db.fetch_existing_files()[0]["id"])

    def test_vector_roundtrip_and_cosine(self) -> None:
        vector = [1.0, 0.5, -0.25]
        decoded = decode_vector(encode_vector(vector))

        self.assertEqual(len(decoded), 3)
        self.assertAlmostEqual(decoded[0], 1.0)
        self.assertAlmostEqual(cosine_similarity(vector, vector_norm(vector), decoded, vector_norm(decoded)), 1.0)

    def test_semantic_search_ranks_most_similar_item_first(self) -> None:
        file_id = self.create_file("语义测试.txt")
        self.store.index_text_item(
            self.backend,
            SemanticItem(
                id=None,
                file_id=file_id,
                modality=MODALITY_TEXT,
                item_key="chunk:0",
                text="三亚海边旅游攻略",
                metadata="fixture",
                source_size=100,
                source_modified_at=1.0,
            ),
        )
        self.store.index_text_item(
            self.backend,
            SemanticItem(
                id=None,
                file_id=file_id,
                modality=MODALITY_TEXT,
                item_key="chunk:1",
                text="合同预算审批资料",
                metadata="fixture",
                source_size=100,
                source_modified_at=1.0,
            ),
        )

        query_vector = self.backend.embed_text("海边旅游")
        hits = self.store.search(self.backend, query_vector, limit=2)

        self.assertEqual(hits[0].item_key, "chunk:0")
        self.assertGreaterEqual(hits[0].similarity, hits[1].similarity)


if __name__ == "__main__":
    unittest.main()

