from __future__ import annotations

import hashlib
import math
from pathlib import Path

from semantic.backends.base import BaseEmbeddingBackend
from semantic.config import (
    DEFAULT_DIMENSIONS,
    DEFAULT_IMAGE_MODEL_KEY,
    DEFAULT_IMAGE_SIMILARITY_MODEL_KEY,
    DEFAULT_TEXT_MODEL_KEY,
    MODALITY_IMAGE,
    MODALITY_IMAGE_SIMILARITY,
    MODALITY_TEXT,
)


class DeterministicTextEmbeddingBackend(BaseEmbeddingBackend):
    model_key = DEFAULT_TEXT_MODEL_KEY
    modality = MODALITY_TEXT
    dimensions = DEFAULT_DIMENSIONS
    version = "1"

    def embed_text(self, text: str) -> list[float]:
        return stable_text_embedding(text, self.dimensions)


class DeterministicImageEmbeddingBackend(BaseEmbeddingBackend):
    model_key = DEFAULT_IMAGE_MODEL_KEY
    modality = MODALITY_IMAGE
    dimensions = DEFAULT_DIMENSIONS
    version = "1"

    def embed_text(self, text: str) -> list[float]:
        return stable_text_embedding(text, self.dimensions)

    def embed_image(self, path: str) -> list[float]:
        image_path = Path(path)
        descriptor_parts = [image_path.stem, image_path.suffix.lower().lstrip(".")]
        try:
            sample = image_path.read_bytes()[:4096]
        except OSError:
            sample = b""
        decoded_sample = sample.decode("utf-8", errors="ignore")
        if decoded_sample:
            descriptor_parts.append(decoded_sample)
        descriptor_parts.append(hashlib.sha256(sample).hexdigest())
        return stable_text_embedding(" ".join(descriptor_parts), self.dimensions)


class DeterministicImageSimilarityBackend(DeterministicImageEmbeddingBackend):
    model_key = DEFAULT_IMAGE_SIMILARITY_MODEL_KEY
    modality = MODALITY_IMAGE_SIMILARITY


def stable_text_embedding(text: str, dimensions: int) -> list[float]:
    vector = [0.0 for _ in range(dimensions)]
    normalized = (text or "").casefold()
    if not normalized:
        return vector

    for token in character_ngrams(normalized):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "little") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def character_ngrams(text: str) -> list[str]:
    compact = "".join(text.split())
    if not compact:
        return []
    grams = list(compact)
    grams.extend(compact[index : index + 2] for index in range(max(0, len(compact) - 1)))
    return grams
