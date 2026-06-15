import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from database import FileDatabase
from indexer import FileIndexer
from mover import SafeFileMover
from organizer import RuleOrganizer


class OrganizerMoverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.managed = self.root / "managed"
        self.managed.mkdir()
        self.db = FileDatabase(self.root / "test.sqlite3")
        self.indexer = FileIndexer(self.db)
        self.rule_path = self.root / "categories.yaml"
        self.rule_path.write_text(
            """
categories:
  - name: 工资表
    target_dir: 工资表
    match_mode: keyword_and_extension
    filename_keywords: [工资, 工资表, 薪资]
    extensions: [xlsx, xls, csv]
  - name: 合同
    target_dir: 合同
    match_mode: keyword_and_extension
    filename_keywords: [合同, 协议]
    extensions: [pdf, docx]
  - name: 图纸
    target_dir: 图纸
    match_mode: any
    filename_keywords: [图纸, 平面图]
    extensions: [dwg, dxf]
""",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_file(self, relative: str, content: str = "test") -> Path:
        path = self.managed / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def scan(self) -> None:
        self.indexer.add_directory(self.managed)
        self.indexer.scan_all()

    def test_generates_rule_based_suggestions(self) -> None:
        self.create_file("待整理/6月工资表.xlsx")
        self.create_file("待整理/项目合同.pdf")
        self.create_file("待整理/一层平面图.txt")
        self.create_file("待整理/普通照片.jpg")
        self.scan()

        suggestions = RuleOrganizer(self.db, self.rule_path).generate_suggestions()
        by_name = {suggestion.filename: suggestion for suggestion in suggestions}

        self.assertEqual(by_name["6月工资表.xlsx"].category, "工资表")
        self.assertEqual(by_name["项目合同.pdf"].category, "合同")
        self.assertEqual(by_name["一层平面图.txt"].category, "图纸")
        self.assertNotIn("普通照片.jpg", by_name)
        target = Path(by_name["6月工资表.xlsx"].target_path)
        self.assertEqual(target.parent.name, "待整理")
        self.assertEqual(target.parent.parent.name, "工资表")

    def test_execute_move_logs_and_undo_last_batch(self) -> None:
        source = self.create_file("待整理/6月工资表.xlsx", "new")
        existing = self.create_file("工资表/6月工资表.xlsx", "old")
        self.scan()

        suggestions = RuleOrganizer(self.db, self.rule_path).generate_suggestions()
        source_resolved = str(source.resolve())
        suggestion = next(item for item in suggestions if item.source_path == source_resolved)
        self.assertTrue(suggestion.target_path.endswith("工资表/待整理/6月工资表.xlsx"))

        mover = SafeFileMover(self.db)
        results = mover.execute_batch([suggestion])
        self.assertEqual(results[0].status, "moved")
        moved_path = Path(results[0].target_path)
        self.assertFalse(source.exists())
        self.assertTrue(moved_path.exists())
        self.assertEqual(existing.read_text(encoding="utf-8"), "old")

        moved_logs = self.db.fetch_move_logs(status="moved")
        self.assertEqual(len(moved_logs), 1)
        self.assertEqual(moved_logs[0]["old_path"], source_resolved)
        self.assertEqual(moved_logs[0]["new_path"], str(moved_path))

        undo_results = mover.undo_last_batch()
        self.assertEqual(undo_results[0].status, "undo_moved")
        self.assertTrue(source.exists())
        self.assertFalse(moved_path.exists())

        undone_logs = self.db.fetch_move_logs(status="undone")
        undo_logs = self.db.fetch_move_logs(status="undo_moved")
        self.assertEqual(len(undone_logs), 1)
        self.assertEqual(len(undo_logs), 1)

    def test_undo_all_batches_restores_multiple_moves(self) -> None:
        first = self.create_file("一版/项目合同.pdf", "first")
        second = self.create_file("二版/项目合同.pdf", "second")
        self.scan()
        suggestions = RuleOrganizer(self.db, self.rule_path).generate_suggestions()

        mover = SafeFileMover(self.db)
        results = mover.execute_batch(suggestions)
        self.assertEqual(sum(1 for result in results if result.status == "moved"), 2)
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())

        undo_results = mover.undo_all_batches()
        self.assertEqual(sum(1 for result in undo_results if result.status == "undo_moved"), 2)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())


if __name__ == "__main__":
    unittest.main()
