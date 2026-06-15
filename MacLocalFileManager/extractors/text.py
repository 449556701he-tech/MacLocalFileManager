from __future__ import annotations

import csv
from pathlib import Path

from config import MAX_EXTRACTED_TEXT_CHARS
from extractors.base import BaseExtractor
from models import ContentExtractResult


class TextExtractor(BaseExtractor):
    supported_extensions = {"txt", "md"}

    def extract(self, path: Path) -> ContentExtractResult:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            return ContentExtractResult(handle.read(MAX_EXTRACTED_TEXT_CHARS))


class CsvExtractor(BaseExtractor):
    supported_extensions = {"csv"}

    def extract(self, path: Path) -> ContentExtractResult:
        lines: list[str] = []
        with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
            reader = csv.reader(handle)
            for row_number, row in enumerate(reader, start=1):
                values = [value.strip() for value in row if value and value.strip()]
                if values:
                    lines.append(f"[CSV 行{row_number}] " + " ".join(values))
                if sum(len(line) for line in lines) >= MAX_EXTRACTED_TEXT_CHARS:
                    return ContentExtractResult("\n".join(lines)[:MAX_EXTRACTED_TEXT_CHARS], "CSV")
        return ContentExtractResult("\n".join(lines)[:MAX_EXTRACTED_TEXT_CHARS], "CSV")
