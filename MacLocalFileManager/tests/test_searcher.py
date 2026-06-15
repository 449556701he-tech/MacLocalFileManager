import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from database import FileDatabase
from file_categories import (
    CATEGORY_ARCHIVES,
    CATEGORY_BILLS,
    CATEGORY_CAD,
    CATEGORY_DOCUMENTS,
    CATEGORY_DRAWINGS,
    CATEGORY_IMAGES,
)
from indexer import FileIndexer
from searcher import FileSearcher


class SearcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = FileDatabase(self.root / "test.sqlite3")
        self.indexer = FileIndexer(self.db)
        self.searcher = FileSearcher(self.db)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_file(self, relative: str, modified_offset: int = 0) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test", encoding="utf-8")
        timestamp = time.time() + modified_offset
        os.utime(path, (timestamp, timestamp))
        return path

    def test_chinese_search_ranking_is_controlled(self) -> None:
        self.create_file("合同.txt", modified_offset=0)
        self.create_file("合同预算.xlsx", modified_offset=50)
        self.create_file("项目合同资料.docx", modified_offset=100)
        self.create_file("合同归档/预算.txt", modified_offset=1000)

        self.indexer.add_directory(self.root)
        self.indexer.scan_all()

        results = self.searcher.search("合同")
        filenames = [result.filename for result in results]
        reasons = [result.reason for result in results]

        self.assertEqual(filenames[:4], ["合同.txt", "合同预算.xlsx", "项目合同资料.docx", "预算.txt"])
        self.assertEqual(reasons[:4], ["完全匹配", "开头匹配", "文件名包含", "路径包含"])
        self.assertEqual([result.rank for result in results[:4]], [1, 2, 3, 4])

    def test_same_rank_sorts_by_recent_modified_time(self) -> None:
        self.create_file("项目合同A.txt", modified_offset=10)
        self.create_file("项目合同B.txt", modified_offset=100)

        self.indexer.add_directory(self.root)
        self.indexer.scan_all()

        results = self.searcher.search("项目")
        self.assertEqual([result.filename for result in results[:2]], ["项目合同B.txt", "项目合同A.txt"])

    def test_fuzzy_filename_match_and_archive_priority(self) -> None:
        self.create_file("60亩图纸资料.xlsx", modified_offset=100)
        self.create_file("60亩图纸资料.zip", modified_offset=0)
        self.create_file("60亩图纸资料.7z", modified_offset=50)

        self.indexer.add_directory(self.root)
        self.indexer.scan_all()

        results = self.searcher.search("60图资")
        self.assertEqual([result.filename for result in results[:3]], ["60亩图纸资料.7z", "60亩图纸资料.zip", "60亩图纸资料.xlsx"])
        self.assertEqual(results[0].reason, "文件名模糊匹配")

    def test_search_can_filter_by_file_category(self) -> None:
        self.create_file("海边照片.jpg")
        self.create_file("海边攻略.pdf")
        self.create_file("海边资料.zip")

        self.indexer.add_directory(self.root)
        self.indexer.scan_all()

        self.assertEqual(self.searcher.search("海边", category=CATEGORY_IMAGES)[0].filename, "海边照片.jpg")
        self.assertEqual(self.searcher.search("海边", category=CATEGORY_DOCUMENTS)[0].filename, "海边攻略.pdf")
        self.assertEqual(self.searcher.search("海边", category=CATEGORY_ARCHIVES)[0].filename, "海边资料.zip")

    def test_search_can_filter_drawings_cad_and_bill_files(self) -> None:
        self.create_file("60亩总平面图.pdf")
        self.create_file("60亩建筑施工图.dwg")
        self.create_file("60亩工程量清单.gcfx")
        self.create_file("60亩工程量清单.sgcfx")

        self.indexer.add_directory(self.root)
        self.indexer.scan_all()

        self.assertEqual(self.searcher.search("60亩", category=CATEGORY_DRAWINGS)[0].filename, "60亩总平面图.pdf")
        self.assertEqual(self.searcher.search("60亩", category=CATEGORY_CAD)[0].filename, "60亩建筑施工图.dwg")
        bill_names = [result.filename for result in self.searcher.search("60亩", category=CATEGORY_BILLS)]
        self.assertEqual(set(bill_names), {"60亩工程量清单.gcfx", "60亩工程量清单.sgcfx"})

    def test_semantic_search_expands_local_keywords(self) -> None:
        self.create_file("三亚旅游攻略.pdf")
        self.create_file("预算资料.xlsx")

        self.indexer.add_directory(self.root)
        self.indexer.scan_all()

        results = self.searcher.search("海边", semantic=True)
        self.assertEqual(results[0].filename, "三亚旅游攻略.pdf")
        self.assertEqual(results[0].reason, "语义扩展匹配")

    def test_missing_file_is_marked_not_deleted(self) -> None:
        path = self.create_file("临时文件.txt")
        self.indexer.add_directory(self.root)
        self.indexer.scan_all()
        path.unlink()

        stats = self.indexer.scan_all()
        self.assertEqual(stats.missing_files, 1)
        self.assertEqual(self.searcher.search("临时文件"), [])

        with self.db.connect() as conn:
            row = conn.execute('SELECT "exists" FROM files WHERE filename = ?', ("临时文件.txt",)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["exists"], 0)


if __name__ == "__main__":
    unittest.main()
