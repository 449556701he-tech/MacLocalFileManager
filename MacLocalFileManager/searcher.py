from __future__ import annotations

from pathlib import Path

from config import normalize_text
from database import FileDatabase
from file_categories import CATEGORY_ALL, ARCHIVE_EXTENSIONS, classify_file
from models import SearchResult
from semantic.search import SemanticSearcher
from semantic_search import expand_query


REASON_EXACT = "完全匹配"
REASON_STARTS = "开头匹配"
REASON_FILENAME_CONTAINS = "文件名包含"
REASON_PATH_CONTAINS = "路径包含"
REASON_FILENAME_FUZZY = "文件名模糊匹配"
REASON_PATH_FUZZY = "路径模糊匹配"
REASON_SEMANTIC = "语义扩展匹配"
REASON_CONTENT_CONTAINS = "内容包含"
REASON_OCR_CONTAINS = "OCR 包含"


class FileSearcher:
    def __init__(self, db: FileDatabase) -> None:
        self.db = db

    def search(
        self,
        query: str,
        limit: int = 200,
        category: str = CATEGORY_ALL,
        semantic: bool = False,
    ) -> list[SearchResult]:
        normalized_query = normalize_text(query)
        if not normalized_query:
            return []

        terms = [normalized_query]
        if semantic:
            terms.extend(expand_query(normalized_query))

        results_by_id: dict[int, SearchResult] = {}
        candidate_limit = max(limit * 8, 1200)
        seen_ids = set()
        for term_index, term in enumerate(terms):
            for row in self.db.search_existing_files_with_content(term, candidate_limit):
                seen_ids.add(row["id"])
                result = self._row_to_result(row, term, term_index > 0)
                if result is None or not matches_category(result, category):
                    continue
                keep_best_result(results_by_id, result)

        if len(results_by_id) < limit and should_run_fuzzy_fallback(normalized_query):
            for row in self.db.fetch_existing_files():
                if row["id"] in seen_ids:
                    continue
                result = self._row_to_result(row, normalized_query, False)
                if result is None or not matches_category(result, category):
                    continue
                keep_best_result(results_by_id, result)

        if semantic and len(results_by_id) < limit:
            semantic_searcher = SemanticSearcher(self.db)
            for result in semantic_searcher.search_pdf(normalized_query, limit=limit, category=category):
                keep_best_result(results_by_id, result)
            for result in semantic_searcher.search_image_ocr(normalized_query, limit=limit, category=category):
                keep_best_result(results_by_id, result)
            for result in semantic_searcher.search_image_visual(normalized_query, limit=limit, category=category):
                keep_best_result(results_by_id, result)

        results = list(results_by_id.values())
        results.sort(key=lambda item: (item.rank, archive_priority(item.extension), -item.modified_at, item.filename))
        return results[:limit]

    def _row_to_result(self, row, query: str, semantic_match: bool) -> SearchResult | None:
        rank_reason = self._rank(
            row["filename"],
            row["normalized_filename"],
            row["path"],
            row_value(row, "normalized_content"),
            row_value(row, "content_text"),
            row_value(row, "metadata"),
            row_value(row, "normalized_ocr_text"),
            row_value(row, "ocr_text"),
            row_value(row, "ocr_engine"),
            query,
        )
        if rank_reason is None:
            return None

        rank, reason, match_type, snippet, content_detail = rank_reason
        if semantic_match:
            rank += 7
            reason = REASON_SEMANTIC
            match_type = "语义命中"

        category = classify_file(row["path"], row["extension"])
        return SearchResult(
            id=row["id"],
            filename=row["filename"],
            path=row["path"],
            parent_dir=row["parent_dir"],
            extension=row["extension"],
            size=row["size"],
            created_at=row["created_at"],
            modified_at=row["modified_at"],
            indexed_at=row["indexed_at"],
            exists=row["exists"],
            reason=reason,
            rank=rank,
            match_type=match_type,
            snippet=snippet,
            content_detail=content_detail,
            category=category,
        )

    @staticmethod
    def _rank(
        filename: str,
        normalized_filename: str,
        path: str,
        normalized_content: str,
        content_text: str,
        metadata: str,
        normalized_ocr_text: str,
        ocr_text: str,
        ocr_engine: str,
        query: str,
    ) -> tuple[int, str, str, str, str] | None:
        stem = normalize_text(Path(filename).stem)
        normalized_path = normalize_text(path)

        if normalized_filename == query or stem == query:
            return 1, REASON_EXACT, "文件名命中", "", ""
        if normalized_filename.startswith(query) or stem.startswith(query):
            return 2, REASON_STARTS, "文件名命中", "", ""
        if query in normalized_filename or query in stem:
            return 3, REASON_FILENAME_CONTAINS, "文件名命中", "", ""
        if is_fuzzy_match(query, normalized_filename) or is_fuzzy_match(query, stem):
            return 3.5, REASON_FILENAME_FUZZY, "文件名命中", "", ""
        if query in normalized_path:
            return 4, REASON_PATH_CONTAINS, "路径命中", "", ""
        if is_fuzzy_match(query, normalized_path):
            return 4.5, REASON_PATH_FUZZY, "路径命中", "", ""
        if query in normalized_content:
            return 5, REASON_CONTENT_CONTAINS, "内容命中", make_snippet(content_text, query), metadata
        if query in normalized_ocr_text:
            return 6, REASON_OCR_CONTAINS, "OCR 命中", make_snippet(ocr_text, query), ocr_engine
        return None


def make_snippet(content_text: str, query: str, radius: int = 36) -> str:
    for raw_line in content_text.splitlines():
        line = " ".join(raw_line.split())
        normalized_line = normalize_text(line)
        position = normalized_line.find(query)
        if position == -1:
            continue
        start = max(0, position - radius)
        end = min(len(line), position + len(query) + radius)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(line) else ""
        return f"{prefix}{line[start:end]}{suffix}"

    normalized_content = normalize_text(content_text)
    position = normalized_content.find(query)
    if position == -1:
        return ""
    start = max(0, position - radius)
    end = min(len(content_text), position + len(query) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(content_text) else ""
    return f"{prefix}{content_text[start:end]}{suffix}"


def is_fuzzy_match(query: str, target: str) -> bool:
    compact_query = "".join(query.split())
    if len(compact_query) < 2:
        return False
    position = 0
    for char in compact_query:
        found = target.find(char, position)
        if found == -1:
            return False
        position = found + 1
    return True


def should_run_fuzzy_fallback(query: str) -> bool:
    return len("".join(query.split())) >= 2


def archive_priority(extension: str) -> int:
    return 0 if extension.lower() in ARCHIVE_EXTENSIONS else 1


def matches_category(result: SearchResult, category: str) -> bool:
    return category == CATEGORY_ALL or result.category == category


def keep_best_result(results_by_id: dict[int, SearchResult], result: SearchResult) -> None:
    existing = results_by_id.get(result.id)
    if existing is None or result.rank < existing.rank:
        results_by_id[result.id] = result


def row_value(row, key: str, default: str = "") -> str:
    if isinstance(row, dict):
        return row.get(key) or default
    if key not in row.keys():
        return default
    return row[key] or default
