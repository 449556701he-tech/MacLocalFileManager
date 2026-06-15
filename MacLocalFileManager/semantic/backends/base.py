from __future__ import annotations

from abc import ABC, abstractmethod


class BaseEmbeddingBackend(ABC):
    model_key: str
    modality: str
    dimensions: int
    version: str

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_image(self, path: str) -> list[float]:
        raise NotImplementedError("This backend does not support image embeddings")

