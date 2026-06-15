import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from database import FileDatabase
from indexer import FileIndexer
from scanner import should_skip_full_disk_child


class ScanProgressTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.managed = self.root / "managed"
        self.managed.mkdir()
        self.db = FileDatabase(self.root / "test.sqlite3")
        self.indexer = FileIndexer(self.db)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_scan_all_reports_progress_messages(self) -> None:
        (self.managed / "测试文稿.txt").write_text("进度测试", encoding="utf-8")
        self.indexer.add_directory(self.managed)
        messages = []

        stats = self.indexer.scan_all(progress_callback=messages.append)

        self.assertEqual(stats.scanned_files, 1)
        self.assertTrue(any("开始扫描" in message for message in messages))
        self.assertTrue(any("文档内容索引" in message for message in messages))
        self.assertTrue(any("索引刷新完成" in message for message in messages))

    def test_full_disk_scan_skips_volumes_container(self) -> None:
        self.assertTrue(should_skip_full_disk_child(Path("/"), Path("/Volumes")))
        self.assertTrue(should_skip_full_disk_child(Path("/"), Path("/private")))
        self.assertTrue(should_skip_full_disk_child(Path("/"), Path("/usr")))
        self.assertFalse(should_skip_full_disk_child(Path("/Volumes/USB"), Path("/Volumes/USB/Docs")))
        self.assertFalse(should_skip_full_disk_child(Path("/tmp/project"), Path("/tmp/project/private")))


if __name__ == "__main__":
    unittest.main()
