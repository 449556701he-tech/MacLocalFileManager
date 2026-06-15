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
from semantic.config import JOB_DONE, JOB_FAILED, JOB_PENDING, JOB_RUNNING, JOB_TYPE_PDF
from semantic.scheduler import SemanticJobQueue


class SemanticJobQueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = FileDatabase(self.root / "test.sqlite3")
        self.indexer = FileIndexer(self.db)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_file_id(self) -> int:
        path = self.root / "报告.pdf"
        path.write_text("fixture", encoding="utf-8")
        timestamp = time.time()
        os.utime(path, (timestamp, timestamp))
        self.indexer.add_directory(self.root)
        self.indexer.scan_all(include_content=False, include_ocr=False)
        return int(self.db.fetch_existing_files()[0]["id"])

    def test_enqueue_fetch_and_status_counts(self) -> None:
        file_id = self.create_file_id()
        queue = SemanticJobQueue(self.db)

        job_id = queue.enqueue(file_id, JOB_TYPE_PDF)
        duplicate_id = queue.enqueue(file_id, JOB_TYPE_PDF)
        self.assertEqual(job_id, duplicate_id)
        self.assertEqual(queue.counts()[JOB_PENDING], 1)

        job = queue.fetch_next()
        self.assertIsNotNone(job)
        self.assertEqual(job.file_id, file_id)

        queue.mark_running(job.id)
        self.assertEqual(queue.counts()[JOB_RUNNING], 1)
        running_job = queue.fetch_next()
        self.assertIsNone(running_job)

        queue.mark_done(job.id)
        self.assertEqual(queue.counts()[JOB_DONE], 1)

    def test_failed_job_records_error(self) -> None:
        file_id = self.create_file_id()
        queue = SemanticJobQueue(self.db)
        job_id = queue.enqueue(file_id, JOB_TYPE_PDF)

        queue.mark_failed(job_id, "测试失败")

        self.assertEqual(queue.counts()[JOB_FAILED], 1)
        with self.db.connect() as conn:
            row = conn.execute("SELECT last_error FROM semantic_jobs WHERE id = ?", (job_id,)).fetchone()
        self.assertEqual(row["last_error"], "测试失败")


if __name__ == "__main__":
    unittest.main()
