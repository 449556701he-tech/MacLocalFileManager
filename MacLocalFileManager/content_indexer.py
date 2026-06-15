from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from config import (
    CONTENT_EXTRACTION_TIMEOUT_SECONDS,
    MAX_CONTENT_FILE_SIZE_BYTES,
    MAX_EXTRACTED_TEXT_CHARS,
    PROJECT_ROOT,
    SUBPROCESS_EXTRACT_EXTENSIONS,
)
from database import FileDatabase
from extractors.registry import ExtractorRegistry
from models import ContentExtractResult


class ContentIndexer:
    def __init__(self, db: FileDatabase, registry: ExtractorRegistry | None = None) -> None:
        self.db = db
        self.registry = registry or ExtractorRegistry()

    def index_existing_files(self, progress_callback: Callable[[str], None] | None = None) -> tuple[int, int, int]:
        indexed = 0
        failed = 0
        skipped = 0
        rows = [row for row in self.db.fetch_existing_files() if self.registry.supports(row["extension"])]
        total = len(rows)
        seen = 0
        self._progress(progress_callback, f"文档内容索引：处理 0/{total} 个，索引 0 个，跳过 0 个，失败 0 个")

        for row in rows:
            extension = row["extension"]
            seen += 1

            if self._is_unchanged(row):
                skipped += 1
                if seen % 20 == 0:
                    self._progress(progress_callback, f"文档内容索引：处理 {seen}/{total} 个，跳过 {skipped} 个")
                continue

            path = Path(row["path"])
            extractor = self.registry.extractor_for(path)
            if extractor is None:
                continue

            try:
                self._progress(progress_callback, f"文档内容索引：处理 {seen}/{total} 个，正在提取 {path.name}")
                if row["size"] > MAX_CONTENT_FILE_SIZE_BYTES:
                    raise RuntimeError(f"文件过大，跳过内容提取：{row['size']} bytes")
                result = self._extract(path, extractor, extension)
                self.db.upsert_file_content(
                    file_id=row["id"],
                    content_text=result.content_text,
                    metadata=result.metadata,
                    source_size=row["size"],
                    source_modified_at=row["modified_at"],
                    extracted_at=time.time(),
                    error="",
                )
                indexed += 1
            except Exception as exc:  # noqa: BLE001 - extraction must not crash indexing.
                self.db.upsert_file_content(
                    file_id=row["id"],
                    content_text="",
                    metadata=extension,
                    source_size=row["size"],
                    source_modified_at=row["modified_at"],
                    extracted_at=time.time(),
                    error=str(exc),
                )
                failed += 1
            if seen % 20 == 0:
                self._progress(
                    progress_callback,
                    f"文档内容索引：处理 {seen}/{total} 个，索引 {indexed} 个，跳过 {skipped} 个，失败 {failed} 个",
                )

        self._progress(
            progress_callback,
            f"文档内容索引完成：索引 {indexed} 个，跳过 {skipped} 个，失败 {failed} 个",
        )
        return indexed, failed, skipped

    def _is_unchanged(self, row) -> bool:
        state = self.db.get_file_content_state(row["id"])
        if state is None:
            return False
        return state["source_size"] == row["size"] and state["source_modified_at"] == row["modified_at"]

    def _extract(self, path: Path, extractor, extension: str) -> ContentExtractResult:
        if should_use_subprocess(self.registry, extension):
            return extract_in_subprocess(path)
        result = extractor.extract(path)
        return ContentExtractResult(result.content_text[:MAX_EXTRACTED_TEXT_CHARS], result.metadata)

    @staticmethod
    def _progress(progress_callback: Callable[[str], None] | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)


def should_use_subprocess(registry, extension: str) -> bool:
    return registry.__class__.__name__ == "ExtractorRegistry" and extension in SUBPROCESS_EXTRACT_EXTENSIONS


def extract_in_subprocess(path: Path) -> ContentExtractResult:
    runner = PROJECT_ROOT / "extractor_runner.py"
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--extract", str(path)]
    else:
        command = [sys.executable, str(runner), str(path)]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=CONTENT_EXTRACTION_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"内容提取超时：超过 {CONTENT_EXTRACTION_TIMEOUT_SECONDS} 秒") from exc

    stdout = completed.stdout.strip()
    if not stdout:
        stderr = completed.stderr.strip()
        raise RuntimeError(stderr or "内容提取失败：无输出")

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("内容提取失败：输出无法解析") from exc

    if not payload.get("ok"):
        raise RuntimeError(payload.get("error") or "内容提取失败")
    return ContentExtractResult(payload.get("content_text", ""), payload.get("metadata", ""))
