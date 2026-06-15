from __future__ import annotations

import sys
import tempfile
import types
import unittest
import struct
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from semantic.config import DEFAULT_DIMENSIONS, MODALITY_IMAGE, MODALITY_IMAGE_SIMILARITY


class FakeUrl:
    pass


class FakeFoundation(types.SimpleNamespace):
    class NSURL:
        @staticmethod
        def fileURLWithPath_(path: str) -> FakeUrl:
            return FakeUrl()


class FakeClassificationObservation:
    def __init__(self, identifier: str, confidence: float) -> None:
        self._identifier = identifier
        self._confidence = confidence

    def identifier(self) -> str:
        return self._identifier

    def confidence(self) -> float:
        return self._confidence


class FakeClassifyRequest:
    _latest: "FakeClassifyRequest | None" = None

    @classmethod
    def alloc(cls):
        return cls()

    def init(self):
        type(self)._latest = self
        self.maximum_observations = None
        return self

    def setMaximumObservations_(self, value: int) -> None:
        self.maximum_observations = value

    def results(self):
        return [
            FakeClassificationObservation("document", 0.92),
            FakeClassificationObservation("receipt", 0.81),
            FakeClassificationObservation("low confidence", 0.12),
        ]


class FakeHandler:
    @classmethod
    def alloc(cls):
        return cls()

    def initWithURL_options_(self, url: FakeUrl, options):
        return self

    def performRequests_error_(self, requests, error):
        return True, None


class FakeVision(types.SimpleNamespace):
    VNClassifyImageRequest = FakeClassifyRequest
    VNGenerateImageFeaturePrintRequest = None
    VNImageRequestHandler = FakeHandler


class FakeFeaturePrintObservation:
    def __init__(self) -> None:
        values = [0.0 for _ in range(768)]
        values[0] = 0.25
        values[1] = -0.5
        values[767] = 1.0
        self._data = struct.pack("<768f", *values)

    def data(self) -> bytes:
        return self._data

    def elementCount(self) -> int:
        return 768


class FakeFeaturePrintRequest:
    _latest: "FakeFeaturePrintRequest | None" = None

    @classmethod
    def alloc(cls):
        return cls()

    def init(self):
        type(self)._latest = self
        return self

    def results(self):
        return [FakeFeaturePrintObservation()]


class FakeFeaturePrintVision(types.SimpleNamespace):
    VNGenerateImageFeaturePrintRequest = FakeFeaturePrintRequest
    VNImageRequestHandler = FakeHandler


class AppleVisionBackendTest(unittest.TestCase):
    def test_describe_image_returns_vision_classification_labels_above_threshold(self) -> None:
        with patch.dict(sys.modules, {"Foundation": FakeFoundation(), "Vision": FakeVision()}):
            from semantic.backends.apple_vision import AppleVisionImageEmbeddingBackend

            with tempfile.TemporaryDirectory() as temp_dir:
                image_path = Path(temp_dir) / "receipt.jpg"
                image_path.write_bytes(b"fake image bytes")

                backend = AppleVisionImageEmbeddingBackend(min_confidence=0.2)
                description = backend.describe_image(str(image_path))
                vector = backend.embed_image(str(image_path))

        self.assertEqual(backend.model_key, "apple-vision-image-labels-v1")
        self.assertEqual(backend.modality, MODALITY_IMAGE)
        self.assertEqual(len(vector), DEFAULT_DIMENSIONS)
        self.assertIn("document", description)
        self.assertIn("receipt", description)
        self.assertNotIn("low confidence", description)
        self.assertEqual(FakeClassifyRequest._latest.maximum_observations, 12)

    def test_embed_text_uses_same_dimensions_as_image_labels(self) -> None:
        with patch.dict(sys.modules, {"Foundation": FakeFoundation(), "Vision": FakeVision()}):
            from semantic.backends.apple_vision import AppleVisionImageEmbeddingBackend

            backend = AppleVisionImageEmbeddingBackend()

        self.assertEqual(len(backend.embed_text("receipt document")), backend.dimensions)

    def test_featureprint_backend_extracts_apple_vision_feature_vector(self) -> None:
        with patch.dict(sys.modules, {"Foundation": FakeFoundation(), "Vision": FakeFeaturePrintVision()}):
            from semantic.backends.apple_vision import AppleVisionFeaturePrintBackend

            with tempfile.TemporaryDirectory() as temp_dir:
                image_path = Path(temp_dir) / "similar.png"
                image_path.write_bytes(b"fake image bytes")

                backend = AppleVisionFeaturePrintBackend()
                vector = backend.embed_image(str(image_path))

        self.assertEqual(backend.model_key, "apple-vision-featureprint-v1")
        self.assertEqual(backend.modality, MODALITY_IMAGE_SIMILARITY)
        self.assertEqual(len(vector), 768)
        self.assertAlmostEqual(vector[0], 0.25)
        self.assertAlmostEqual(vector[1], -0.5)
        self.assertAlmostEqual(vector[-1], 1.0)


if __name__ == "__main__":
    unittest.main()
