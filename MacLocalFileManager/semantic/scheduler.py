from __future__ import annotations

import time

from database import FileDatabase
from semantic.config import JOB_DONE, JOB_FAILED, JOB_PENDING, JOB_RUNNING
from semantic.models import SemanticJob


class SemanticJobQueue:
    def __init__(self, db: FileDatabase) -> None:
        self.db = db

    def enqueue(self, file_id: int, job_type: str) -> int:
        now = time.time()
        with self.db.connect() as conn:
            existing = conn.execute(
                """
                SELECT id, status FROM semantic_jobs
                WHERE file_id = ? AND job_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (file_id, job_type),
            ).fetchone()
            if existing is not None and existing["status"] in {JOB_PENDING, JOB_RUNNING}:
                return int(existing["id"])

            conn.execute(
                """
                INSERT INTO semantic_jobs(file_id, job_type, status, attempts, last_error, created_at, updated_at)
                VALUES(?, ?, ?, 0, '', ?, ?)
                """,
                (file_id, job_type, JOB_PENDING, now, now),
            )
            row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
            conn.commit()
        return int(row["id"])

    def fetch_next(self, job_type: str | None = None) -> SemanticJob | None:
        with self.db.connect() as conn:
            if job_type is None:
                row = conn.execute(
                    """
                    SELECT id, file_id, job_type, status, attempts, last_error
                    FROM semantic_jobs
                    WHERE status = ?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (JOB_PENDING,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT id, file_id, job_type, status, attempts, last_error
                    FROM semantic_jobs
                    WHERE status = ? AND job_type = ?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (JOB_PENDING, job_type),
                ).fetchone()
        return None if row is None else row_to_job(row)

    def mark_running(self, job_id: int) -> None:
        self._update_status(job_id, JOB_RUNNING, increment_attempts=True)

    def mark_done(self, job_id: int) -> None:
        self._update_status(job_id, JOB_DONE, last_error="")

    def mark_failed(self, job_id: int, error: str) -> None:
        self._update_status(job_id, JOB_FAILED, last_error=error)

    def counts(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM semantic_jobs
                GROUP BY status
                """
            ).fetchall()
        counts = {JOB_PENDING: 0, JOB_RUNNING: 0, JOB_DONE: 0, JOB_FAILED: 0}
        counts.update({row["status"]: int(row["count"]) for row in rows})
        return counts

    def _update_status(
        self,
        job_id: int,
        status: str,
        increment_attempts: bool = False,
        last_error: str | None = None,
    ) -> None:
        with self.db.connect() as conn:
            if increment_attempts:
                conn.execute(
                    """
                    UPDATE semantic_jobs
                    SET status = ?, attempts = attempts + 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, time.time(), job_id),
                )
            elif last_error is None:
                conn.execute(
                    """
                    UPDATE semantic_jobs
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, time.time(), job_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE semantic_jobs
                    SET status = ?, last_error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, last_error, time.time(), job_id),
                )
            conn.commit()


def row_to_job(row) -> SemanticJob:
    return SemanticJob(
        id=int(row["id"]),
        file_id=int(row["file_id"]),
        job_type=row["job_type"],
        status=row["status"],
        attempts=int(row["attempts"]),
        last_error=row["last_error"],
    )
