from __future__ import annotations

import struct
from pathlib import Path

from semantic.backends.base import BaseEmbeddingBackend
from semantic.backends.deterministic import (
    DeterministicImageEmbeddingBackend,
    DeterministicImageSimilarityBackend,
    stable_text_embedding,
)
from semantic.config import (
    APPLE_VISION_FEATUREPRINT_DIMENSIONS,
    DEFAULT_DIMENSIONS,
    MODALITY_IMAGE,
    MODALITY_IMAGE_SIMILARITY,
)


class AppleVisionImageEmbeddingBackend(BaseEmbeddingBackend):
    """Local image labels from Apple Vision, embedded into the existing text vector space."""

    model_key = "apple-vision-image-labels-v1"
    modality = MODALITY_IMAGE
    dimensions = DEFAULT_DIMENSIONS
    version = "1"

    def __init__(self, min_confidence: float = 0.18, max_observations: int = 12) -> None:
        self.min_confidence = min_confidence
        self.max_observations = max_observations
        self._description_cache: dict[str, str] = {}

    @classmethod
    def is_available(cls) -> bool:
        try:
            import Vision
        except ImportError:
            return False
        return hasattr(Vision, "VNClassifyImageRequest") and hasattr(Vision, "VNImageRequestHandler")

    def embed_text(self, text: str) -> list[float]:
        return stable_text_embedding(text, self.dimensions)

    def embed_image(self, path: str) -> list[float]:
        description = self.describe_image(path)
        if not description:
            description = Path(path).stem
        return stable_text_embedding(description, self.dimensions)

    def describe_image(self, path: str) -> str:
        cache_key = str(path)
        cached = self._description_cache.get(cache_key)
        if cached is not None:
            return cached
        labels = self.classify_image(path)
        description = " ".join(labels)
        self._description_cache[cache_key] = description
        return description

    def classify_image(self, path: str) -> list[str]:
        try:
            import Foundation
            import Vision
        except ImportError as exc:
            raise RuntimeError(
                "Apple Vision 图片识别需要安装 PyObjC：pip install pyobjc-framework-Vision pyobjc-framework-Quartz"
            ) from exc

        if not hasattr(Vision, "VNClassifyImageRequest"):
            raise RuntimeError("当前 macOS Vision 不支持 VNClassifyImageRequest")

        url = Foundation.NSURL.fileURLWithPath_(str(path))
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
        request = Vision.VNClassifyImageRequest.alloc().init()
        if hasattr(request, "setMaximumObservations_"):
            request.setMaximumObservations_(self.max_observations)

        ok, error = handler.performRequests_error_([request], None)
        if not ok:
            message = str(error) if error is not None else "Apple Vision 图片识别失败"
            raise RuntimeError(message)

        labels: list[str] = []
        for observation in request.results() or []:
            identifier = str(observation.identifier()).strip()
            confidence = float(observation.confidence()) if hasattr(observation, "confidence") else 1.0
            if identifier and confidence >= self.min_confidence:
                labels.append(identifier)
        return labels


class AppleVisionFeaturePrintBackend(BaseEmbeddingBackend):
    """Apple Vision FeaturePrint vector for image-to-image similarity."""

    model_key = "apple-vision-featureprint-v1"
    modality = MODALITY_IMAGE_SIMILARITY
    dimensions = APPLE_VISION_FEATUREPRINT_DIMENSIONS
    version = "1"

    @classmethod
    def is_available(cls) -> bool:
        try:
            import Vision
        except ImportError:
            return False
        return hasattr(Vision, "VNGenerateImageFeaturePrintRequest") and hasattr(Vision, "VNImageRequestHandler")

    def embed_text(self, text: str) -> list[float]:
        return [0.0 for _ in range(self.dimensions)]

    def embed_image(self, path: str) -> list[float]:
        observation = self._featureprint_observation(path)
        raw_data = bytes(observation.data())
        element_count = int(observation.elementCount())
        expected_bytes = element_count * 4
        if element_count != self.dimensions or len(raw_data) != expected_bytes:
            raise RuntimeError(
                f"Apple Vision FeaturePrint 维度不匹配：elementCount={element_count}, bytes={len(raw_data)}"
            )
        return list(struct.unpack(f"<{element_count}f", raw_data))

    def _featureprint_observation(self, path: str):
        try:
            import Foundation
            import Vision
        except ImportError as exc:
            raise RuntimeError(
                "Apple Vision FeaturePrint 需要安装 PyObjC：pip install pyobjc-framework-Vision pyobjc-framework-Quartz"
            ) from exc

        if not hasattr(Vision, "VNGenerateImageFeaturePrintRequest"):
            raise RuntimeError("当前 macOS Vision 不支持 VNGenerateImageFeaturePrintRequest")

        url = Foundation.NSURL.fileURLWithPath_(str(path))
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
        request = Vision.VNGenerateImageFeaturePrintRequest.alloc().init()
        ok, error = handler.performRequests_error_([request], None)
        if not ok:
            message = str(error) if error is not None else "Apple Vision FeaturePrint 失败"
            raise RuntimeError(message)

        results = request.results() or []
        if not results:
            raise RuntimeError("Apple Vision FeaturePrint 未返回结果")
        observation = results[0]
        if not hasattr(observation, "data") or not hasattr(observation, "elementCount"):
            raise RuntimeError("Apple Vision FeaturePrint 结果缺少 data/elementCount")
        return observation


def create_default_image_embedding_backend(db=None) -> BaseEmbeddingBackend:
    if AppleVisionImageEmbeddingBackend.is_available():
        return AppleVisionImageEmbeddingBackend()
    return DeterministicImageEmbeddingBackend()


def create_default_image_similarity_backend() -> BaseEmbeddingBackend:
    if AppleVisionFeaturePrintBackend.is_available():
        return AppleVisionFeaturePrintBackend()
    return DeterministicImageSimilarityBackend()
