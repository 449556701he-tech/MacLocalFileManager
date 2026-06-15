from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class FileRecord:
    filename: str
    normalized_filename: str
    path: str
    parent_dir: str
    extension: str
    size: int
    created_at: float
    modified_at: float
    indexed_at: float
    exists: int = 1
    id: Optional[int] = None

    @classmethod
    def from_path(cls, path: Path, indexed_at: float) -> "FileRecord":
        stat = path.stat()
        filename = path.name
        extension = path.suffix.lower().lstrip(".")
        from config import normalize_text

        return cls(
            filename=filename,
            normalized_filename=normalize_text(filename),
            path=str(path),
            parent_dir=str(path.parent),
            extension=extension,
            size=stat.st_size,
            created_at=getattr(stat, "st_birthtime", stat.st_ctime),
            modified_at=stat.st_mtime,
            indexed_at=indexed_at,
            exists=1,
        )


@dataclass(frozen=True)
class SearchResult:
    id: int
    filename: str
    path: str
    parent_dir: str
    extension: str
    size: int
    created_at: float
    modified_at: float
    indexed_at: float
    exists: int
    reason: str
    rank: float
    match_type: str = ""
    snippet: str = ""
    content_detail: str = ""
    category: str = "other"


@dataclass(frozen=True)
class ScanStats:
    scanned_files: int
    updated_files: int
    missing_files: int
    skipped_dirs: int
    content_indexed: int = 0
    content_failed: int = 0
    content_skipped: int = 0
    ocr_indexed: int = 0
    ocr_failed: int = 0
    ocr_skipped: int = 0
    semantic_pdf_indexed: int = 0
    semantic_pdf_failed: int = 0
    semantic_pdf_skipped: int = 0
    semantic_ocr_indexed: int = 0
    semantic_ocr_failed: int = 0
    semantic_ocr_skipped: int = 0
    semantic_image_indexed: int = 0
    semantic_image_failed: int = 0
    semantic_image_skipped: int = 0
    semantic_similarity_indexed: int = 0
    semantic_similarity_failed: int = 0
    semantic_similarity_skipped: int = 0


@dataclass(frozen=True)
class OrganizeSuggestion:
    file_id: int
    filename: str
    source_path: str
    target_path: str
    category: str
    reason: str


@dataclass(frozen=True)
class MoveResult:
    source_path: str
    target_path: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class ContentExtractResult:
    content_text: str
    metadata: str = ""


@dataclass(frozen=True)
class OcrExtractResult:
    ocr_text: str
    engine: str = ""
