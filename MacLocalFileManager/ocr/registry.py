from __future__ import annotations

from pathlib import Path

from ocr.base import BaseOcrEngine
from ocr.macos_vision import MacOSVisionOcrEngine


class OcrRegistry:
    def __init__(self, engine: BaseOcrEngine | None = None) -> None:
        self.engine = engine or MacOSVisionOcrEngine()

    def supports(self, extension: str) -> bool:
        return extension.lower().lstrip(".") in self.engine.supported_extensions

    def engine_for(self, path: Path) -> BaseOcrEngine | None:
        if self.supports(path.suffix):
            return self.engine
        return None

