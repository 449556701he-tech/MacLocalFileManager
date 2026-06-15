from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from database import FileDatabase
from ocr.registry import OcrRegistry


OCR_ENABLED_SETTING = "ocr_enabled"


class OcrIndexer:
    def __init__(self, db: FileDatabase, registry: OcrRegistry | None = None) -> None:
        self.db = db
        self.registry = registry or OcrRegistry()

    def index_existing_files(self, progress_callback: Callable[[str], None] | None = None) -> tuple[int, int, int]:
        if not self.db.get_bool_setting(OCR_ENABLED_SETTING, False):
            self._progress(progress_callback, "OCR 未启用，跳过图片文字识别")
            return 0, 0, 0

        indexed = 0
        failed = 0
        skipped = 0
        rows = [row for row in self.db.fetch_existing_files() if self.registry.supports(row["extension"])]
        total = len(rows)
        seen = 0
        self._progress(progress_callback, f"OCR：处理 0/{total} 个，识别 0 个，跳过 0 个，失败 0 个")

        for row in rows:
            seen += 1

            if self._is_unchanged(row):
                skipped += 1
                if seen % 5 == 0:
                    self._progress(progress_callback, f"OCR：处理 {seen}/{total} 个，跳过 {skipped} 个")
                continue

            path = Path(row["path"])
            engine = self.registry.engine_for(path)
            if engine is None:
                continue

            try:
                result = engine.recognize(path)
                self.db.upsert_file_ocr(
                    file_id=row["id"],
                    ocr_text=result.ocr_text,
                    engine=result.engine,
                    source_size=row["size"],
                    source_modified_at=row["modified_at"],
                    extracted_at=time.time(),
                    error="",
                )
                indexed += 1
            except Exception as exc:  # noqa: BLE001 - OCR must never crash scanning.
                self.db.upsert_file_ocr(
                    file_id=row["id"],
                    ocr_text="",
                    engine=engine.__class__.__name__,
                    source_size=row["size"],
                    source_modified_at=row["modified_at"],
                    extracted_at=time.time(),
                    error=str(exc),
                )
                failed += 1
            if seen % 5 == 0:
                self._progress(
                    progress_callback,
                    f"OCR：处理 {seen}/{total} 个，识别 {indexed} 个，跳过 {skipped} 个，失败 {failed} 个",
                )

        self._progress(progress_callback, f"OCR 完成：识别 {indexed} 个，跳过 {skipped} 个，失败 {failed} 个")
        return indexed, failed, skipped

    def _is_unchanged(self, row) -> bool:
        state = self.db.get_file_ocr_state(row["id"])
        if state is None:
            return False
        if state["error"]:
            return False
        return state["source_size"] == row["size"] and state["source_modified_at"] == row["modified_at"]

    @staticmethod
    def _progress(progress_callback: Callable[[str], None] | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)
