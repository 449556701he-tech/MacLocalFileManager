import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from database import FileDatabase
from indexer import FileIndexer
from models import OcrExtractResult
from ocr.base import BaseOcrEngine
from ocr.registry import OcrRegistry
from ocr_indexer import OCR_ENABLED_SETTING, OcrIndexer
from searcher import FileSearcher


class FakeOcrEngine(BaseOcrEngine):
    supported_extensions = {"png", "jpg", "jpeg", "heic"}

    def recognize(self, path: Path) -> OcrExtractResult:
        return OcrExtractResult("图片里有付款确认文字", "Fake OCR")


class FailingOcrEngine(BaseOcrEngine):
    supported_extensions = {"png", "jpg", "jpeg", "heic"}

    def recognize(self, path: Path) -> OcrExtractResult:
        raise RuntimeError("OCR 测试失败")


class OcrSearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.managed = self.root / "managed"
        self.managed.mkdir()
        self.db = FileDatabase(self.root / "test.sqlite3")
        self.indexer = FileIndexer(self.db)
        self.searcher = FileSearcher(self.db)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_file(self, relative: str, content=b"test") -> Path:
        path = self.managed / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def test_ocr_is_disabled_by_default(self) -> None:
        self.create_file("图片.png")
        self.indexer.add_directory(self.managed)
        self.indexer.ocr_indexer = OcrIndexer(self.db, OcrRegistry(FakeOcrEngine()))

        stats = self.indexer.scan_all()

        self.assertEqual(stats.ocr_indexed, 0)
        self.assertEqual(self.searcher.search("付款确认"), [])

    def test_ocr_hit_ranks_after_content_hit(self) -> None:
        self.create_file("报告.txt", "正文里有付款确认文字")
        self.create_file("截图.png")
        self.db.set_bool_setting(OCR_ENABLED_SETTING, True)
        self.indexer.add_directory(self.managed)
        self.indexer.ocr_indexer = OcrIndexer(self.db, OcrRegistry(FakeOcrEngine()))

        stats = self.indexer.scan_all()
        self.assertEqual(stats.ocr_indexed, 1)
        self.assertEqual(stats.ocr_failed, 0)

        results = self.searcher.search("付款确认")
        self.assertEqual([result.match_type for result in results[:2]], ["内容命中", "OCR 命中"])
        self.assertEqual([result.rank for result in results[:2]], [5, 6])
        self.assertIn("图片里有付款确认文字", results[1].snippet)

    def test_ocr_failure_is_recorded_without_crashing(self) -> None:
        self.create_file("截图.jpg")
        self.db.set_bool_setting(OCR_ENABLED_SETTING, True)
        self.indexer.add_directory(self.managed)
        self.indexer.ocr_indexer = OcrIndexer(self.db, OcrRegistry(FailingOcrEngine()))

        stats = self.indexer.scan_all()

        self.assertEqual(stats.ocr_failed, 1)
        errors = self.db.fetch_ocr_errors()
        self.assertEqual(len(errors), 1)
        self.assertIn("OCR 测试失败", errors[0]["error"])

    def test_previous_ocr_failure_is_retried_on_next_scan(self) -> None:
        self.create_file("截图.png")
        self.db.set_bool_setting(OCR_ENABLED_SETTING, True)
        self.indexer.add_directory(self.managed)
        self.indexer.ocr_indexer = OcrIndexer(self.db, OcrRegistry(FailingOcrEngine()))

        first = self.indexer.scan_all()
        self.assertEqual(first.ocr_failed, 1)

        self.indexer.ocr_indexer = OcrIndexer(self.db, OcrRegistry(FakeOcrEngine()))
        second = self.indexer.scan_all()
        self.assertEqual(second.ocr_indexed, 1)
        self.assertEqual(second.ocr_skipped, 0)
        self.assertEqual(self.searcher.search("付款确认")[0].match_type, "OCR 命中")


if __name__ == "__main__":
    unittest.main()
