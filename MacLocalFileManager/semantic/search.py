from __future__ import annotations

from database import FileDatabase
from file_categories import CATEGORY_ALL, classify_file
from models import SearchResult
from semantic.backends.base import BaseEmbeddingBackend
from semantic.backends.deterministic import DeterministicImageEmbeddingBackend, DeterministicTextEmbeddingBackend
from semantic.config import MODALITY_IMAGE, MODALITY_IMAGE_OCR_TEXT, MODALITY_PDF_TEXT, SEMANTIC_ENABLED_SETTING
from semantic.vector_store import SemanticVectorStore


REASON_PDF_SEMANTIC = "PDF语义命中"
REASON_IMAGE_OCR_SEMANTIC = "图片文字语义命中"
REASON_IMAGE_VISUAL_SEMANTIC = "图片视觉语义命中"


class SemanticSearcher:
    def __init__(
        self,
        db: FileDatabase,
        backend: BaseEmbeddingBackend | None = None,
        image_backend: BaseEmbeddingBackend | None = None,
    ) -> None:
        self.db = db
        self.backend = backend or DeterministicTextEmbeddingBackend()
        self.image_backend = image_backend or DeterministicImageEmbeddingBackend()
        self.store = SemanticVectorStore(db)

    def search_pdf(self, query: str, limit: int = 20, category: str = CATEGORY_ALL) -> list[SearchResult]:
        if not self.db.get_bool_setting(SEMANTIC_ENABLED_SETTING, False):
            return []
        query_vector = self.backend.embed_text(query)
        hits = self.store.search(self.backend, query_vector, limit=limit * 4, modality=MODALITY_PDF_TEXT)

        results_by_file: dict[int, SearchResult] = {}
        for hit in hits:
            file_row = self.db.get_file(hit.file_id)
            if file_row is None or file_row["extension"] != "pdf":
                continue
            result = semantic_hit_to_result(file_row, hit, category, REASON_PDF_SEMANTIC)
            if result is None:
                continue
            existing = results_by_file.get(result.id)
            if existing is None or result.rank < existing.rank:
                results_by_file[result.id] = result

        results = list(results_by_file.values())
        results.sort(key=lambda item: (item.rank, -item.modified_at, item.filename))
        return results[:limit]

    def search_image_visual(self, query: str, limit: int = 20, category: str = CATEGORY_ALL) -> list[SearchResult]:
        if not self.db.get_bool_setting(SEMANTIC_ENABLED_SETTING, False):
            return []
        query_vector = self.image_backend.embed_text(query)
        hits = self.store.search(self.image_backend, query_vector, limit=limit * 4, modality=MODALITY_IMAGE)

        results_by_file: dict[int, SearchResult] = {}
        for hit in hits:
            file_row = self.db.get_file(hit.file_id)
            if file_row is None:
                continue
            result = semantic_hit_to_result(file_row, hit, category, REASON_IMAGE_VISUAL_SEMANTIC)
            if result is None:
                continue
            existing = results_by_file.get(result.id)
            if existing is None or result.rank < existing.rank:
                results_by_file[result.id] = result

        results = list(results_by_file.values())
        results.sort(key=lambda item: (item.rank, -item.modified_at, item.filename))
        return results[:limit]

    def search_image_ocr(self, query: str, limit: int = 20, category: str = CATEGORY_ALL) -> list[SearchResult]:
        if not self.db.get_bool_setting(SEMANTIC_ENABLED_SETTING, False):
            return []
        query_vector = self.backend.embed_text(query)
        hits = self.store.search(self.backend, query_vector, limit=limit * 4, modality=MODALITY_IMAGE_OCR_TEXT)

        results_by_file: dict[int, SearchResult] = {}
        for hit in hits:
            file_row = self.db.get_file(hit.file_id)
            if file_row is None:
                continue
            result = semantic_hit_to_result(file_row, hit, category, REASON_IMAGE_OCR_SEMANTIC)
            if result is None:
                continue
            existing = results_by_file.get(result.id)
            if existing is None or result.rank < existing.rank:
                results_by_file[result.id] = result

        results = list(results_by_file.values())
        results.sort(key=lambda item: (item.rank, -item.modified_at, item.filename))
        return results[:limit]


def semantic_hit_to_result(file_row, hit, category: str, reason: str) -> SearchResult | None:
    file_category = classify_file(file_row["path"], file_row["extension"])
    if category != CATEGORY_ALL and file_category != category:
        return None
    rank = 7.0 + max(0.0, 1.0 - hit.similarity)
    snippet = make_semantic_snippet(hit.text)
    return SearchResult(
        id=file_row["id"],
        filename=file_row["filename"],
        path=file_row["path"],
        parent_dir=file_row["parent_dir"],
        extension=file_row["extension"],
        size=file_row["size"],
        created_at=file_row["created_at"],
        modified_at=file_row["modified_at"],
        indexed_at=file_row["indexed_at"],
        exists=file_row["exists"],
        reason=reason,
        rank=rank,
        match_type="语义命中",
        snippet=snippet,
        content_detail=f"{hit.model_key} similarity={hit.similarity:.3f}",
        category=file_category,
    )


def make_semantic_snippet(text: str, limit: int = 90) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."
