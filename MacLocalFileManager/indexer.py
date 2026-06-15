from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from content_indexer import ContentIndexer
from database import FileDatabase
from models import ScanStats
from ocr_indexer import OCR_ENABLED_SETTING, OcrIndexer
from semantic.indexer import ImageOcrSemanticIndexer, ImageVisualSemanticIndexer, PdfSemanticIndexer
from scanner import DirectoryScanner, is_protected_path


class FileIndexer:
    def __init__(self, db: FileDatabase) -> None:
        self.db = db
        self.scanner = DirectoryScanner(db)
        self.content_indexer = ContentIndexer(db)
        self.ocr_indexer = OcrIndexer(db)
        self.pdf_semantic_indexer = PdfSemanticIndexer(db)
        self.image_ocr_semantic_indexer = ImageOcrSemanticIndexer(db)
        self.image_visual_semantic_indexer = ImageVisualSemanticIndexer(db)

    def add_directory(self, path: str | Path) -> None:
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise ValueError(f"目录不存在或不是文件夹: {resolved}")
        if is_protected_path(resolved):
            raise ValueError(f"安全限制：不能扫描受保护目录: {resolved}")
        self.db.add_managed_dir(resolved, time.time())

    def remove_directory(self, path: str | Path) -> None:
        self.db.remove_managed_dir(path)

    def scan_all(
        self,
        progress_callback: Callable[[str], None] | None = None,
        include_content: bool = True,
        include_ocr: bool | None = None,
    ) -> ScanStats:
        self._progress(progress_callback, "准备开始扫描")
        stats = self.scanner.scan(self.db.list_managed_dirs(), progress_callback=progress_callback)
        content_indexed = content_failed = content_skipped = 0
        ocr_indexed = ocr_failed = ocr_skipped = 0
        semantic_pdf_indexed = semantic_pdf_failed = semantic_pdf_skipped = 0
        semantic_ocr_indexed = semantic_ocr_failed = semantic_ocr_skipped = 0
        semantic_image_indexed = semantic_image_failed = semantic_image_skipped = 0

        if include_content:
            content_indexed, content_failed, content_skipped = self.content_indexer.index_existing_files(
                progress_callback=progress_callback
            )
            (
                semantic_pdf_indexed,
                semantic_pdf_failed,
                semantic_pdf_skipped,
            ) = self.pdf_semantic_indexer.index_existing_pdf_content(progress_callback=progress_callback)
        else:
            self._progress(progress_callback, "文档内容索引未运行")

        if include_ocr is None:
            include_ocr = self.db.get_bool_setting(OCR_ENABLED_SETTING, False)
        if include_ocr:
            ocr_indexed, ocr_failed, ocr_skipped = self.ocr_indexer.index_existing_files(
                progress_callback=progress_callback
            )
            (
                semantic_ocr_indexed,
                semantic_ocr_failed,
                semantic_ocr_skipped,
            ) = self.image_ocr_semantic_indexer.index_existing_ocr_text(progress_callback=progress_callback)
            (
                semantic_image_indexed,
                semantic_image_failed,
                semantic_image_skipped,
            ) = self.image_visual_semantic_indexer.index_existing_images(progress_callback=progress_callback)
        else:
            self._progress(progress_callback, "OCR 未运行")

        self._progress(progress_callback, "索引刷新完成")
        return ScanStats(
            scanned_files=stats.scanned_files,
            updated_files=stats.updated_files,
            missing_files=stats.missing_files,
            skipped_dirs=stats.skipped_dirs,
            content_indexed=content_indexed,
            content_failed=content_failed,
            content_skipped=content_skipped,
            ocr_indexed=ocr_indexed,
            ocr_failed=ocr_failed,
            ocr_skipped=ocr_skipped,
            semantic_pdf_indexed=semantic_pdf_indexed,
            semantic_pdf_failed=semantic_pdf_failed,
            semantic_pdf_skipped=semantic_pdf_skipped,
            semantic_ocr_indexed=semantic_ocr_indexed,
            semantic_ocr_failed=semantic_ocr_failed,
            semantic_ocr_skipped=semantic_ocr_skipped,
            semantic_image_indexed=semantic_image_indexed,
            semantic_image_failed=semantic_image_failed,
            semantic_image_skipped=semantic_image_skipped,
        )

    @staticmethod
    def _progress(progress_callback: Callable[[str], None] | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)
