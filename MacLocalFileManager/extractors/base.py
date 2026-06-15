from pathlib import Path

from models import ContentExtractResult


class BaseExtractor:
    supported_extensions: set[str] = set()

    def extract(self, path: Path) -> ContentExtractResult:
        raise NotImplementedError

