from pathlib import Path

from models import OcrExtractResult


class BaseOcrEngine:
    supported_extensions: set[str] = set()

    def recognize(self, path: Path) -> OcrExtractResult:
        raise NotImplementedError

