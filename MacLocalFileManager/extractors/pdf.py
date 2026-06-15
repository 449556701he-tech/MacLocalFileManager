from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader

from config import MAX_EXTRACTED_TEXT_CHARS
from extractors.base import BaseExtractor
from models import ContentExtractResult


class PdfExtractor(BaseExtractor):
    supported_extensions = {"pdf"}

    def extract(self, path: Path) -> ContentExtractResult:
        logging.getLogger("pypdf").setLevel(logging.CRITICAL)
        reader = PdfReader(str(path))
        parts: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                parts.append(f"[PDF 第{page_number}页] {text}")
            if sum(len(part) for part in parts) >= MAX_EXTRACTED_TEXT_CHARS:
                return ContentExtractResult("\n".join(parts)[:MAX_EXTRACTED_TEXT_CHARS], "PDF")
        return ContentExtractResult("\n".join(parts)[:MAX_EXTRACTED_TEXT_CHARS], "PDF")
