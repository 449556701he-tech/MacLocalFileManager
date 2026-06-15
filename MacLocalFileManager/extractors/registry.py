from __future__ import annotations

from pathlib import Path

from extractors.base import BaseExtractor
from extractors.office import DocxExtractor, XlsxExtractor
from extractors.pdf import PdfExtractor
from extractors.text import CsvExtractor, TextExtractor


class ExtractorRegistry:
    def __init__(self) -> None:
        extractors: list[BaseExtractor] = [
            TextExtractor(),
            CsvExtractor(),
            DocxExtractor(),
            XlsxExtractor(),
            PdfExtractor(),
        ]
        self.extractors: dict[str, BaseExtractor] = {}
        for extractor in extractors:
            for extension in extractor.supported_extensions:
                self.extractors[extension] = extractor

    def supports(self, extension: str) -> bool:
        return extension.lower().lstrip(".") in self.extractors

    def extractor_for(self, path: Path) -> BaseExtractor | None:
        return self.extractors.get(path.suffix.lower().lstrip("."))
