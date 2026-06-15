from __future__ import annotations

from typing import Callable

from database import FileDatabase
from file_categories import IMAGE_EXTENSIONS
from semantic.backends.base import BaseEmbeddingBackend
from semantic.backends.deterministic import DeterministicImageEmbeddingBackend, DeterministicTextEmbeddingBackend
from semantic.chunker import chunk_text
from semantic.config import (
    MODALITY_IMAGE,
    MODALITY_IMAGE_OCR_TEXT,
    MODALITY_PDF_TEXT,
    SEMANTIC_ENABLED_SETTING,
    SEMANTIC_IMAGE_ENABLED_SETTING,
    SEMANTIC_MAX_FILE_SIZE_MB_SETTING,
    SEMANTIC_PDF_ENABLED_SETTING,
)
from semantic.models import SemanticItem
from semantic.vector_store import SemanticVectorStore


class PdfSemanticIndexer:
    def __init__(self, db: FileDatabase, backend: BaseEmbeddingBackend | None = None) -> None:
        self.db = db
        self.backend = backend or DeterministicTextEmbeddingBackend()
        self.store = SemanticVectorStore(db)

    def index_existing_pdf_content(
        self,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[int, int, int]:
        if not self.db.get_bool_setting(SEMANTIC_ENABLED_SETTING, False):
            self._progress(progress_callback, "PDF 语义索引未启用")
            return 0, 0, 0
        if not self.db.get_bool_setting(SEMANTIC_PDF_ENABLED_SETTING, True):
            self._progress(progress_callback, "PDF 语义索引已关闭")
            return 0, 0, 0

        rows = self._fetch_pdf_content_rows()
        total = len(rows)
        indexed = 0
        failed = 0
        skipped = 0
        self._progress(progress_callback, f"PDF 语义索引：处理 0/{total} 个，索引 0 个，跳过 0 个，失败 0 个")

        for seen, row in enumerate(rows, start=1):
            try:
                if self._is_unchanged(row):
                    skipped += 1
                    continue
                chunks = chunk_text(
                    row["content_text"],
                    prefix="pdf",
                    metadata=row["metadata"] or "PDF",
                )
                self.store.delete_items_for_file(row["file_id"], MODALITY_PDF_TEXT)
                for chunk in chunks:
                    self.store.index_text_item(
                        self.backend,
                        SemanticItem(
                            id=None,
                            file_id=row["file_id"],
                            modality=MODALITY_PDF_TEXT,
                            item_key=chunk.item_key,
                            text=chunk.text,
                            metadata=chunk.metadata,
                            source_size=row["source_size"],
                            source_modified_at=row["source_modified_at"],
                        ),
                    )
                indexed += 1
            except Exception as exc:  # noqa: BLE001 - semantic indexing must not crash app indexing.
                failed += 1
                self._record_failed_item(row, str(exc))

            if seen % 10 == 0 or seen == total:
                self._progress(
                    progress_callback,
                    f"PDF 语义索引：处理 {seen}/{total} 个，索引 {indexed} 个，跳过 {skipped} 个，失败 {failed} 个",
                )

        self._progress(progress_callback, f"PDF 语义索引完成：索引 {indexed} 个，跳过 {skipped} 个，失败 {failed} 个")
        return indexed, failed, skipped

    def _fetch_pdf_content_rows(self):
        with self.db.connect() as conn:
            return conn.execute(
                """
                SELECT f.id AS file_id, f.extension, c.content_text, c.metadata,
                       c.source_size, c.source_modified_at, c.error
                FROM file_contents c
                JOIN files f ON f.id = c.file_id
                WHERE f."exists" = 1
                  AND f.extension = 'pdf'
                  AND c.error = ''
                  AND c.content_text != ''
                ORDER BY f.path
                """
            ).fetchall()

    def _is_unchanged(self, row) -> bool:
        with self.db.connect() as conn:
            existing = conn.execute(
                """
                SELECT 1
                FROM semantic_items
                WHERE file_id = ?
                  AND modality = ?
                  AND source_size = ?
                  AND source_modified_at = ?
                LIMIT 1
                """,
                (row["file_id"], MODALITY_PDF_TEXT, row["source_size"], row["source_modified_at"]),
            ).fetchone()
        return existing is not None

    def _record_failed_item(self, row, error: str) -> None:
        item_id = self.store.upsert_item(
            SemanticItem(
                id=None,
                file_id=row["file_id"],
                modality=MODALITY_PDF_TEXT,
                item_key="pdf:error",
                text="",
                metadata="PDF semantic indexing failed",
                source_size=row["source_size"],
                source_modified_at=row["source_modified_at"],
            )
        )
        model_id = self.store.ensure_model(self.backend)
        self.store.upsert_embedding(item_id, model_id, [0.0 for _ in range(self.backend.dimensions)], error=error)

    @staticmethod
    def _progress(progress_callback: Callable[[str], None] | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)


class ImageOcrSemanticIndexer:
    def __init__(self, db: FileDatabase, backend: BaseEmbeddingBackend | None = None) -> None:
        self.db = db
        self.backend = backend or DeterministicTextEmbeddingBackend()
        self.store = SemanticVectorStore(db)

    def index_existing_ocr_text(
        self,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[int, int, int]:
        if not self.db.get_bool_setting(SEMANTIC_ENABLED_SETTING, False):
            self._progress(progress_callback, "图片 OCR 语义索引未启用")
            return 0, 0, 0
        if not self.db.get_bool_setting(SEMANTIC_IMAGE_ENABLED_SETTING, True):
            self._progress(progress_callback, "图片 OCR 语义索引已关闭")
            return 0, 0, 0

        rows = self._fetch_ocr_rows()
        total = len(rows)
        indexed = 0
        failed = 0
        skipped = 0
        self._progress(progress_callback, f"图片 OCR 语义索引：处理 0/{total} 个，索引 0 个，跳过 0 个，失败 0 个")

        for seen, row in enumerate(rows, start=1):
            try:
                if self._is_unchanged(row):
                    skipped += 1
                    continue
                self.store.delete_items_for_file(row["file_id"], MODALITY_IMAGE_OCR_TEXT)
                self.store.index_text_item(
                    self.backend,
                    SemanticItem(
                        id=None,
                        file_id=row["file_id"],
                        modality=MODALITY_IMAGE_OCR_TEXT,
                        item_key="ocr:0",
                        text=row["ocr_text"],
                        metadata=row["engine"] or "OCR",
                        source_size=row["source_size"],
                        source_modified_at=row["source_modified_at"],
                    ),
                )
                indexed += 1
            except Exception as exc:  # noqa: BLE001 - semantic indexing must continue after a bad row.
                failed += 1
                self._record_failed_item(row, str(exc))

            if seen % 10 == 0 or seen == total:
                self._progress(
                    progress_callback,
                    f"图片 OCR 语义索引：处理 {seen}/{total} 个，索引 {indexed} 个，跳过 {skipped} 个，失败 {failed} 个",
                )

        self._progress(progress_callback, f"图片 OCR 语义索引完成：索引 {indexed} 个，跳过 {skipped} 个，失败 {failed} 个")
        return indexed, failed, skipped

    def _fetch_ocr_rows(self):
        with self.db.connect() as conn:
            return conn.execute(
                """
                SELECT f.id AS file_id, f.extension, o.ocr_text, o.engine,
                       o.source_size, o.source_modified_at, o.error
                FROM file_ocr o
                JOIN files f ON f.id = o.file_id
                WHERE f."exists" = 1
                  AND o.error = ''
                  AND o.ocr_text != ''
                ORDER BY f.path
                """
            ).fetchall()

    def _is_unchanged(self, row) -> bool:
        with self.db.connect() as conn:
            existing = conn.execute(
                """
                SELECT 1
                FROM semantic_items
                WHERE file_id = ?
                  AND modality = ?
                  AND source_size = ?
                  AND source_modified_at = ?
                LIMIT 1
                """,
                (row["file_id"], MODALITY_IMAGE_OCR_TEXT, row["source_size"], row["source_modified_at"]),
            ).fetchone()
        return existing is not None

    def _record_failed_item(self, row, error: str) -> None:
        item_id = self.store.upsert_item(
            SemanticItem(
                id=None,
                file_id=row["file_id"],
                modality=MODALITY_IMAGE_OCR_TEXT,
                item_key="ocr:error",
                text="",
                metadata="Image OCR semantic indexing failed",
                source_size=row["source_size"],
                source_modified_at=row["source_modified_at"],
            )
        )
        model_id = self.store.ensure_model(self.backend)
        self.store.upsert_embedding(item_id, model_id, [0.0 for _ in range(self.backend.dimensions)], error=error)

    @staticmethod
    def _progress(progress_callback: Callable[[str], None] | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)


class ImageVisualSemanticIndexer:
    def __init__(self, db: FileDatabase, backend: BaseEmbeddingBackend | None = None) -> None:
        self.db = db
        self.backend = backend or DeterministicImageEmbeddingBackend()
        self.store = SemanticVectorStore(db)

    def index_existing_images(
        self,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[int, int, int]:
        if not self.db.get_bool_setting(SEMANTIC_ENABLED_SETTING, False):
            self._progress(progress_callback, "图片视觉语义索引未启用")
            return 0, 0, 0
        if not self.db.get_bool_setting(SEMANTIC_IMAGE_ENABLED_SETTING, True):
            self._progress(progress_callback, "图片视觉语义索引已关闭")
            return 0, 0, 0

        rows = self._fetch_image_rows()
        total = len(rows)
        indexed = 0
        failed = 0
        skipped = 0
        max_file_size = self._max_file_size_bytes()
        self._progress(progress_callback, f"图片视觉语义索引：处理 0/{total} 个，索引 0 个，跳过 0 个，失败 0 个")

        for seen, row in enumerate(rows, start=1):
            try:
                if row["size"] > max_file_size or self._is_unchanged(row):
                    skipped += 1
                    continue
                self.store.delete_items_for_file(row["file_id"], MODALITY_IMAGE)
                self.store.index_image_item(
                    self.backend,
                    SemanticItem(
                        id=None,
                        file_id=row["file_id"],
                        modality=MODALITY_IMAGE,
                        item_key="image:0",
                        text=row["filename"],
                        metadata="Image visual semantic",
                        source_size=row["size"],
                        source_modified_at=row["modified_at"],
                    ),
                    row["path"],
                )
                indexed += 1
            except Exception as exc:  # noqa: BLE001 - one broken image must not stop the scan.
                failed += 1
                self._record_failed_item(row, str(exc))

            if seen % 10 == 0 or seen == total:
                self._progress(
                    progress_callback,
                    f"图片视觉语义索引：处理 {seen}/{total} 个，索引 {indexed} 个，跳过 {skipped} 个，失败 {failed} 个",
                )

        self._progress(progress_callback, f"图片视觉语义索引完成：索引 {indexed} 个，跳过 {skipped} 个，失败 {failed} 个")
        return indexed, failed, skipped

    def _fetch_image_rows(self):
        extensions = sorted(IMAGE_EXTENSIONS)
        placeholders = ", ".join("?" for _ in extensions)
        with self.db.connect() as conn:
            return conn.execute(
                f"""
                SELECT id AS file_id, filename, path, extension, size, modified_at
                FROM files
                WHERE "exists" = 1
                  AND extension IN ({placeholders})
                ORDER BY path
                """,
                extensions,
            ).fetchall()

    def _is_unchanged(self, row) -> bool:
        with self.db.connect() as conn:
            existing = conn.execute(
                """
                SELECT 1
                FROM semantic_items
                WHERE file_id = ?
                  AND modality = ?
                  AND source_size = ?
                  AND source_modified_at = ?
                LIMIT 1
                """,
                (row["file_id"], MODALITY_IMAGE, row["size"], row["modified_at"]),
            ).fetchone()
        return existing is not None

    def _record_failed_item(self, row, error: str) -> None:
        item_id = self.store.upsert_item(
            SemanticItem(
                id=None,
                file_id=row["file_id"],
                modality=MODALITY_IMAGE,
                item_key="image:error",
                text="",
                metadata="Image visual semantic indexing failed",
                source_size=row["size"],
                source_modified_at=row["modified_at"],
            )
        )
        model_id = self.store.ensure_model(self.backend)
        self.store.upsert_embedding(item_id, model_id, [0.0 for _ in range(self.backend.dimensions)], error=error)

    def _max_file_size_bytes(self) -> int:
        raw_value = self.db.get_setting(SEMANTIC_MAX_FILE_SIZE_MB_SETTING, "100")
        try:
            value = max(1, int(raw_value))
        except ValueError:
            value = 100
        return value * 1024 * 1024

    @staticmethod
    def _progress(progress_callback: Callable[[str], None] | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)
