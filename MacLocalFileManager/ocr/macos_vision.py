from __future__ import annotations

from pathlib import Path

from models import OcrExtractResult
from ocr.base import BaseOcrEngine


class MacOSVisionOcrEngine(BaseOcrEngine):
    supported_extensions = {"png", "jpg", "jpeg", "heic"}

    def recognize(self, path: Path) -> OcrExtractResult:
        try:
            import Foundation
            import Vision
        except ImportError as exc:
            raise RuntimeError(
                "macOS Vision OCR 需要安装 PyObjC：pip install pyobjc-framework-Vision pyobjc-framework-Quartz"
            ) from exc

        url = Foundation.NSURL.fileURLWithPath_(str(path))
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)
        if hasattr(request, "setRecognitionLanguages_"):
            request.setRecognitionLanguages_(["zh-Hans", "zh-Hant", "en-US"])

        ok, error = handler.performRequests_error_([request], None)
        if not ok:
            message = str(error) if error is not None else "macOS Vision OCR 失败"
            raise RuntimeError(message)

        lines: list[str] = []
        for observation in request.results() or []:
            candidates = observation.topCandidates_(1)
            if candidates:
                text = str(candidates[0].string()).strip()
                if text:
                    lines.append(text)

        return OcrExtractResult("\n".join(lines), "macOS Vision")

