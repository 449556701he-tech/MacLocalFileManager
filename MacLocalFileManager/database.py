from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Iterable, Optional

from config import DEFAULT_DB_PATH, ensure_app_dirs, normalize_text
from models import FileRecord


def empty_content_columns() -> dict:
    return {
        "content_text": "",
        "normalized_content": "",
        "metadata": "",
        "content_source_size": None,
        "content_source_modified_at": None,
        "extracted_at": None,
        "content_error": "",
        "ocr_text": "",
        "normalized_ocr_text": "",
        "ocr_engine": "",
        "ocr_source_size": None,
        "ocr_source_modified_at": None,
        "ocr_extracted_at": None,
        "ocr_error": "",
    }


class FileDatabase:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        ensure_app_dirs()
        self.db_path = db_path if str(db_path) == ":memory:" else Path(db_path)
        if isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    normalized_filename TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    parent_dir TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    modified_at REAL NOT NULL,
                    indexed_at REAL NOT NULL,
                    "exists" INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS managed_dirs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL UNIQUE,
                    added_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS move_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT NOT NULL,
                    old_path TEXT NOT NULL,
                    new_path TEXT NOT NULL,
                    move_time REAL NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS file_contents (
                    file_id INTEGER PRIMARY KEY,
                    content_text TEXT NOT NULL DEFAULT '',
                    normalized_content TEXT NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL DEFAULT '',
                    source_size INTEGER NOT NULL DEFAULT -1,
                    source_modified_at REAL NOT NULL DEFAULT -1,
                    extracted_at REAL NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(file_id) REFERENCES files(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS file_ocr (
                    file_id INTEGER PRIMARY KEY,
                    ocr_text TEXT NOT NULL DEFAULT '',
                    normalized_ocr_text TEXT NOT NULL DEFAULT '',
                    engine TEXT NOT NULL DEFAULT '',
                    source_size INTEGER NOT NULL DEFAULT -1,
                    source_modified_at REAL NOT NULL DEFAULT -1,
                    extracted_at REAL NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(file_id) REFERENCES files(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic_models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_key TEXT NOT NULL UNIQUE,
                    modality TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    version TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    modality TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    text TEXT NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL DEFAULT '',
                    source_size INTEGER NOT NULL,
                    source_modified_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(file_id, modality, item_key),
                    FOREIGN KEY(file_id) REFERENCES files(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic_embeddings (
                    item_id INTEGER NOT NULL,
                    model_id INTEGER NOT NULL,
                    vector BLOB NOT NULL,
                    norm REAL NOT NULL,
                    indexed_at REAL NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(item_id, model_id),
                    FOREIGN KEY(item_id) REFERENCES semantic_items(id),
                    FOREIGN KEY(model_id) REFERENCES semantic_models(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY(file_id) REFERENCES files(id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_files_normalized_filename ON files(normalized_filename)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)")
            conn.execute('CREATE INDEX IF NOT EXISTS idx_files_exists ON files("exists")')
            conn.execute("CREATE INDEX IF NOT EXISTS idx_move_log_batch ON move_log(batch_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_move_log_status ON move_log(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file_contents_error ON file_contents(error)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file_ocr_error ON file_ocr(error)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_items_file ON semantic_items(file_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_items_modality ON semantic_items(modality)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_jobs_status ON semantic_jobs(status)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_semantic_jobs_file_type ON semantic_jobs(file_id, job_type)"
            )
            self._ensure_column(conn, "file_contents", "source_size", "INTEGER NOT NULL DEFAULT -1")
            self._ensure_column(conn, "file_contents", "source_modified_at", "REAL NOT NULL DEFAULT -1")
            self._ensure_column(conn, "file_ocr", "source_size", "INTEGER NOT NULL DEFAULT -1")
            self._ensure_column(conn, "file_ocr", "source_modified_at", "REAL NOT NULL DEFAULT -1")
            self._ensure_default_setting(conn, "semantic_enabled", "0")
            self._ensure_default_setting(conn, "semantic_pdf_enabled", "1")
            self._ensure_default_setting(conn, "semantic_image_enabled", "1")
            self._ensure_default_setting(conn, "semantic_index_on_battery", "0")
            self._ensure_default_setting(conn, "semantic_max_file_size_mb", "100")
            self._ensure_default_setting(conn, "semantic_max_pdf_pages", "300")
            self._ensure_default_setting(conn, "semantic_max_image_pixels", "25000000")
            self._ensure_default_setting(conn, "semantic_worker_sleep_ms", "10")
            conn.commit()

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing_columns = {row["name"] for row in rows}
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _ensure_default_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO app_settings(key, value)
            VALUES(?, ?)
            """,
            (key, value),
        )

    def add_managed_dir(self, path: Path | str, added_at: float) -> None:
        resolved = str(Path(path).expanduser().resolve())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO managed_dirs(path, added_at)
                VALUES(?, ?)
                ON CONFLICT(path) DO UPDATE SET added_at=excluded.added_at
                """,
                (resolved, added_at),
            )
            conn.commit()

    def remove_managed_dir(self, path: Path | str) -> None:
        resolved = str(Path(path).expanduser().resolve())
        with self.connect() as conn:
            conn.execute("DELETE FROM managed_dirs WHERE path = ?", (resolved,))
            conn.commit()

    def list_managed_dirs(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT path FROM managed_dirs ORDER BY path").fetchall()
        return [row["path"] for row in rows]

    def upsert_file(self, record: FileRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO files (
                    filename, normalized_filename, path, parent_dir, extension,
                    size, created_at, modified_at, indexed_at, "exists"
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    filename=excluded.filename,
                    normalized_filename=excluded.normalized_filename,
                    parent_dir=excluded.parent_dir,
                    extension=excluded.extension,
                    size=excluded.size,
                    created_at=excluded.created_at,
                    modified_at=excluded.modified_at,
                    indexed_at=excluded.indexed_at,
                    "exists"=1
                """,
                (
                    record.filename,
                    record.normalized_filename,
                    record.path,
                    record.parent_dir,
                    record.extension,
                    record.size,
                    record.created_at,
                    record.modified_at,
                    record.indexed_at,
                    record.exists,
                ),
            )
            conn.commit()

    def upsert_files(self, records: Iterable[FileRecord]) -> int:
        count = 0
        with self.connect() as conn:
            for record in records:
                conn.execute(
                    """
                    INSERT INTO files (
                        filename, normalized_filename, path, parent_dir, extension,
                        size, created_at, modified_at, indexed_at, "exists"
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        filename=excluded.filename,
                        normalized_filename=excluded.normalized_filename,
                        parent_dir=excluded.parent_dir,
                        extension=excluded.extension,
                        size=excluded.size,
                        created_at=excluded.created_at,
                        modified_at=excluded.modified_at,
                        indexed_at=excluded.indexed_at,
                        "exists"=1
                    """,
                    (
                        record.filename,
                        record.normalized_filename,
                        record.path,
                        record.parent_dir,
                        record.extension,
                        record.size,
                        record.created_at,
                        record.modified_at,
                        record.indexed_at,
                        record.exists,
                    ),
                )
                count += 1
            conn.commit()
        return count

    def mark_missing_under_roots(self, roots: list[Path | str], seen_paths: set[str]) -> int:
        if not roots:
            return 0

        root_strings = [str(Path(root).expanduser().resolve()) for root in roots]
        missing_ids: list[int] = []
        with self.connect() as conn:
            rows = conn.execute('SELECT id, path FROM files WHERE "exists" = 1').fetchall()
            for row in rows:
                path = row["path"]
                in_scope = any(path == root or path.startswith(root + "/") for root in root_strings)
                if in_scope and path not in seen_paths:
                    missing_ids.append(row["id"])

            if missing_ids:
                conn.executemany('UPDATE files SET "exists" = 0 WHERE id = ?', [(id_,) for id_ in missing_ids])
                conn.commit()
        return len(missing_ids)

    def fetch_existing_files(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT id, filename, normalized_filename, path, parent_dir, extension,
                       size, created_at, modified_at, indexed_at, "exists"
                FROM files
                WHERE "exists" = 1
                """
            ).fetchall()

    def fetch_existing_files_with_content(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT f.id, f.filename, f.normalized_filename, f.path, f.parent_dir,
                       f.extension, f.size, f.created_at, f.modified_at, f.indexed_at,
                       f."exists", c.content_text, c.normalized_content, c.metadata,
                       c.source_size AS content_source_size,
                       c.source_modified_at AS content_source_modified_at,
                       c.extracted_at, c.error AS content_error,
                       o.ocr_text, o.normalized_ocr_text, o.engine AS ocr_engine,
                       o.source_size AS ocr_source_size,
                       o.source_modified_at AS ocr_source_modified_at,
                       o.extracted_at AS ocr_extracted_at, o.error AS ocr_error
                FROM files f
                LEFT JOIN file_contents c ON c.file_id = f.id
                LEFT JOIN file_ocr o ON o.file_id = f.id
                WHERE f."exists" = 1
                """
            ).fetchall()

    def search_existing_files_with_content(self, normalized_query: str, limit: int = 1000) -> list[dict]:
        like_query = f"%{normalized_query}%"
        results: list[dict] = []
        seen_ids: set[int] = set()

        with self.connect() as conn:
            file_rows = conn.execute(
                """
                SELECT f.id, f.filename, f.normalized_filename, f.path, f.parent_dir,
                       f.extension, f.size, f.created_at, f.modified_at, f.indexed_at,
                       f."exists"
                FROM files f
                WHERE f."exists" = 1
                  AND (f.normalized_filename LIKE ? OR f.path LIKE ?)
                LIMIT ?
                """,
                (like_query, like_query, limit),
            ).fetchall()

            for row in file_rows:
                item = dict(row)
                item.update(empty_content_columns())
                results.append(item)
                seen_ids.add(item["id"])

            content_rows = conn.execute(
                """
                SELECT f.id, f.filename, f.normalized_filename, f.path, f.parent_dir,
                       f.extension, f.size, f.created_at, f.modified_at, f.indexed_at,
                       f."exists", c.content_text, c.normalized_content, c.metadata,
                       c.source_size AS content_source_size,
                       c.source_modified_at AS content_source_modified_at,
                       c.extracted_at, c.error AS content_error,
                       o.ocr_text, o.normalized_ocr_text, o.engine AS ocr_engine,
                       o.source_size AS ocr_source_size,
                       o.source_modified_at AS ocr_source_modified_at,
                       o.extracted_at AS ocr_extracted_at, o.error AS ocr_error
                FROM files f
                LEFT JOIN file_contents c ON c.file_id = f.id
                LEFT JOIN file_ocr o ON o.file_id = f.id
                WHERE f."exists" = 1
                  AND (c.normalized_content LIKE ? OR o.normalized_ocr_text LIKE ?)
                LIMIT ?
                """,
                (like_query, like_query, limit),
            ).fetchall()

            for row in content_rows:
                item = dict(row)
                if item["id"] in seen_ids:
                    continue
                results.append(item)
                seen_ids.add(item["id"])

        return results

    def count_existing_files(self) -> int:
        with self.connect() as conn:
            row = conn.execute('SELECT COUNT(*) AS count FROM files WHERE "exists" = 1').fetchone()
        return int(row["count"])

    def get_file(self, file_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()

    def upsert_file_content(
        self,
        file_id: int,
        content_text: str,
        metadata: str = "",
        source_size: int = -1,
        source_modified_at: float = -1,
        extracted_at: float | None = None,
        error: str = "",
    ) -> None:
        extracted_at = time.time() if extracted_at is None else extracted_at
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO file_contents(
                    file_id, content_text, normalized_content, metadata,
                    source_size, source_modified_at, extracted_at, error
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                    content_text=excluded.content_text,
                    normalized_content=excluded.normalized_content,
                    metadata=excluded.metadata,
                    source_size=excluded.source_size,
                    source_modified_at=excluded.source_modified_at,
                    extracted_at=excluded.extracted_at,
                    error=excluded.error
                """,
                (
                    file_id,
                    content_text,
                    normalize_text(content_text),
                    metadata,
                    source_size,
                    source_modified_at,
                    extracted_at,
                    error,
                ),
            )
            conn.commit()

    def get_file_content_state(self, file_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT source_size, source_modified_at, extracted_at, error
                FROM file_contents
                WHERE file_id = ?
                """,
                (file_id,),
            ).fetchone()

    def fetch_content_errors(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT f.path, c.error
                FROM file_contents c
                JOIN files f ON f.id = c.file_id
                WHERE c.error != ''
                ORDER BY c.extracted_at DESC
                """
            ).fetchall()

    def upsert_file_ocr(
        self,
        file_id: int,
        ocr_text: str,
        engine: str = "",
        source_size: int = -1,
        source_modified_at: float = -1,
        extracted_at: float | None = None,
        error: str = "",
    ) -> None:
        extracted_at = time.time() if extracted_at is None else extracted_at
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO file_ocr(
                    file_id, ocr_text, normalized_ocr_text, engine,
                    source_size, source_modified_at, extracted_at, error
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                    ocr_text=excluded.ocr_text,
                    normalized_ocr_text=excluded.normalized_ocr_text,
                    engine=excluded.engine,
                    source_size=excluded.source_size,
                    source_modified_at=excluded.source_modified_at,
                    extracted_at=excluded.extracted_at,
                    error=excluded.error
                """,
                (
                    file_id,
                    ocr_text,
                    normalize_text(ocr_text),
                    engine,
                    source_size,
                    source_modified_at,
                    extracted_at,
                    error,
                ),
            )
            conn.commit()

    def get_file_ocr_state(self, file_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT source_size, source_modified_at, extracted_at, error
                FROM file_ocr
                WHERE file_id = ?
                """,
                (file_id,),
            ).fetchone()

    def fetch_ocr_errors(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT f.path, o.error
                FROM file_ocr o
                JOIN files f ON f.id = o.file_id
                WHERE o.error != ''
                ORDER BY o.extracted_at DESC
                """
            ).fetchall()

    def fetch_semantic_summary(self) -> dict[str, dict[str, int]]:
        with self.connect() as conn:
            item_rows = conn.execute(
                """
                SELECT modality, COUNT(*) AS count
                FROM semantic_items
                GROUP BY modality
                """
            ).fetchall()
            error_rows = conn.execute(
                """
                SELECT i.modality, COUNT(*) AS count
                FROM semantic_embeddings e
                JOIN semantic_items i ON i.id = e.item_id
                WHERE e.error != ''
                GROUP BY i.modality
                """
            ).fetchall()

        summary = {
            row["modality"]: {"items": int(row["count"]), "errors": 0}
            for row in item_rows
        }
        for row in error_rows:
            modality = row["modality"]
            summary.setdefault(modality, {"items": 0, "errors": 0})
            summary[modality]["errors"] = int(row["count"])
        return summary

    def get_setting(self, key: str, default: str = "") -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return default if row is None else row["value"]

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings(key, value)
                VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (key, value),
            )
            conn.commit()

    def get_bool_setting(self, key: str, default: bool = False) -> bool:
        value = self.get_setting(key, "1" if default else "0")
        return value in {"1", "true", "True", "yes", "on"}

    def set_bool_setting(self, key: str, value: bool) -> None:
        self.set_setting(key, "1" if value else "0")

    def path_exists_in_index(self, path: Path | str) -> bool:
        resolved = str(Path(path).expanduser().resolve())
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM files WHERE path = ?", (resolved,)).fetchone()
        return row is not None

    def update_file_after_move(self, old_path: Path | str, new_path: Path | str) -> None:
        old_resolved = str(Path(old_path).expanduser().resolve())
        new_resolved = Path(new_path).expanduser().resolve()
        stat = new_resolved.stat()

        from config import normalize_text

        with self.connect() as conn:
            conn.execute(
                """
                UPDATE files
                SET filename = ?,
                    normalized_filename = ?,
                    path = ?,
                    parent_dir = ?,
                    extension = ?,
                    size = ?,
                    created_at = ?,
                    modified_at = ?,
                    indexed_at = ?,
                    "exists" = 1
                WHERE path = ?
                """,
                (
                    new_resolved.name,
                    normalize_text(new_resolved.name),
                    str(new_resolved),
                    str(new_resolved.parent),
                    new_resolved.suffix.lower().lstrip("."),
                    stat.st_size,
                    getattr(stat, "st_birthtime", stat.st_ctime),
                    stat.st_mtime,
                    time.time(),
                    old_resolved,
                ),
            )
            conn.commit()

    def log_move(
        self,
        batch_id: str,
        old_path: Path | str,
        new_path: Path | str,
        move_time: float,
        status: str,
        error: str = "",
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO move_log(batch_id, old_path, new_path, move_time, status, error)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (batch_id, str(old_path), str(new_path), move_time, status, error),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def latest_moved_batch_id(self) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT batch_id
                FROM move_log
                WHERE status = 'moved' AND batch_id NOT LIKE 'undo-%'
                ORDER BY move_time DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        return None if row is None else row["batch_id"]

    def fetch_move_logs(self, batch_id: str | None = None, status: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM move_log"
        clauses = []
        params: list[str] = []
        if batch_id is not None:
            clauses.append("batch_id = ?")
            params.append(batch_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id"
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def update_move_log_status(self, log_id: int, status: str, error: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE move_log SET status = ?, error = ? WHERE id = ?",
                (status, error, log_id),
            )
            conn.commit()
