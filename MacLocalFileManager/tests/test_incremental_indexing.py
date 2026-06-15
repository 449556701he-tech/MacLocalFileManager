import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from content_indexer import ContentIndexer
from database import FileDatabase
from extractors.base import BaseExtractor
from indexer import FileIndexer
from models import ContentExtractResult, OcrExtractResult
from ocr.base import BaseOcrEngine
from ocr.registry import OcrRegistry
from ocr_indexer import OCR_ENABLED_SETTING, OcrIndexer
from searcher import FileSearcher


class CountingTextExtractor(BaseExtractor):
    supported_extensions = {"txt"}

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, path: Path) -> ContentExtractResult:
        self.calls += 1
        return ContentExtractResult(path.read_text(encoding="utf-8"), "CountingText")


class SingleExtractorRegistry:
    def __init__(self, extractor: BaseExtractor) -> None:
        self.extractor = extractor

    def supports(self, extension: str) -> bool:
        return extension.lower().lstrip(".") in self.extractor.supported_extensions

    def extractor_for(self, path: Path):
        return self.extractor if self.supports(path.suffix) else None


class CountingOcrEngine(BaseOcrEngine):
    supported_extensions = {"png"}

    def __init__(self) -> None:
        self.calls = 0

    def recognize(self, path: Path) -> OcrExtractResult:
        self.calls += 1
        return OcrExtractResult("增量 OCR 文本", "CountingOCR")


class IncrementalIndexingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.managed = self.root / "managed"
        self.managed.mkdir()
        self.db = FileDatabase(self.root / "test.sqlite3")
        self.indexer = FileIndexer(self.db)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_file(self, relative: str, content=b"test", timestamp: float = 1_700_000_000) -> Path:
        path = self.managed / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        os.utime(path, (timestamp, timestamp))
        return path

    def test_unchanged_content_file_skips_reextraction_until_modified(self) -> None:
        text_path = self.create_file("报告.txt", "第一次内容", timestamp=1_700_000_000)
        extractor = CountingTextExtractor()
        self.indexer.content_indexer = ContentIndexer(self.db, SingleExtractorRegistry(extractor))
        self.indexer.add_directory(self.managed)

        first = self.indexer.scan_all()
        second = self.indexer.scan_all()

        self.assertEqual(first.content_indexed, 1)
        self.assertEqual(first.content_skipped, 0)
        self.assertEqual(second.content_indexed, 0)
        self.assertEqual(second.content_skipped, 1)
        self.assertEqual(extractor.calls, 1)

        text_path.write_text("第二次内容", encoding="utf-8")
        os.utime(text_path, (1_700_000_100, 1_700_000_100))
        third = self.indexer.scan_all()

        self.assertEqual(third.content_indexed, 1)
        self.assertEqual(third.content_skipped, 0)
        self.assertEqual(extractor.calls, 2)
        self.assertEqual(FileSearcher(self.db).search("第二次内容")[0].match_type, "内容命中")

    def test_unchanged_ocr_file_skips_rerecognition_until_modified(self) -> None:
        image_path = self.create_file("截图.png", b"fake image bytes", timestamp=1_700_000_000)
        engine = CountingOcrEngine()
        self.db.set_bool_setting(OCR_ENABLED_SETTING, True)
        self.indexer.ocr_indexer = OcrIndexer(self.db, OcrRegistry(engine))
        self.indexer.add_directory(self.managed)

        first = self.indexer.scan_all()
        second = self.indexer.scan_all()

        self.assertEqual(first.ocr_indexed, 1)
        self.assertEqual(first.ocr_skipped, 0)
        self.assertEqual(second.ocr_indexed, 0)
        self.assertEqual(second.ocr_skipped, 1)
        self.assertEqual(engine.calls, 1)

        image_path.write_bytes(b"new fake image bytes")
        os.utime(image_path, (1_700_000_100, 1_700_000_100))
        third = self.indexer.scan_all()

        self.assertEqual(third.ocr_indexed, 1)
        self.assertEqual(third.ocr_skipped, 0)
        self.assertEqual(engine.calls, 2)


if __name__ == "__main__":
    unittest.main()

