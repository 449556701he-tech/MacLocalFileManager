from __future__ import annotations

import array
import math
import time
from typing import Iterable

from database import FileDatabase
from semantic.backends.base import BaseEmbeddingBackend
from semantic.models import SemanticItem, SemanticSearchHit


class SemanticVectorStore:
    def __init__(self, db: FileDatabase) -> None:
        self.db = db

    def ensure_model(self, backend: BaseEmbeddingBackend) -> int:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO semantic_models(model_key, modality, dimensions, version, created_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(model_key) DO UPDATE SET
                    modality=excluded.modality,
                    dimensions=excluded.dimensions,
                    version=excluded.version
                """,
                (backend.model_key, backend.modality, backend.dimensions, backend.version, time.time()),
            )
            row = conn.execute("SELECT id FROM semantic_models WHERE model_key = ?", (backend.model_key,)).fetchone()
            conn.commit()
        return int(row["id"])

    def upsert_item(self, item: SemanticItem) -> int:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO semantic_items(
                    file_id, modality, item_key, text, metadata,
                    source_size, source_modified_at, created_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id, modality, item_key) DO UPDATE SET
                    text=excluded.text,
                    metadata=excluded.metadata,
                    source_size=excluded.source_size,
                    source_modified_at=excluded.source_modified_at
                """,
                (
                    item.file_id,
                    item.modality,
                    item.item_key,
                    item.text,
                    item.metadata,
                    item.source_size,
                    item.source_modified_at,
                    time.time(),
                ),
            )
            row = conn.execute(
                """
                SELECT id FROM semantic_items
                WHERE file_id = ? AND modality = ? AND item_key = ?
                """,
                (item.file_id, item.modality, item.item_key),
            ).fetchone()
            conn.commit()
        return int(row["id"])

    def upsert_embedding(self, item_id: int, model_id: int, vector: Iterable[float], error: str = "") -> None:
        values = [float(value) for value in vector]
        norm = vector_norm(values)
        payload = encode_vector(values)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO semantic_embeddings(item_id, model_id, vector, norm, indexed_at, error)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id, model_id) DO UPDATE SET
                    vector=excluded.vector,
                    norm=excluded.norm,
                    indexed_at=excluded.indexed_at,
                    error=excluded.error
                """,
                (item_id, model_id, payload, norm, time.time(), error),
            )
            conn.commit()

    def index_text_item(self, backend: BaseEmbeddingBackend, item: SemanticItem) -> int:
        model_id = self.ensure_model(backend)
        item_id = self.upsert_item(item)
        self.upsert_embedding(item_id, model_id, backend.embed_text(item.text))
        return item_id

    def index_image_item(self, backend: BaseEmbeddingBackend, item: SemanticItem, path: str) -> int:
        model_id = self.ensure_model(backend)
        item_id = self.upsert_item(item)
        self.upsert_embedding(item_id, model_id, backend.embed_image(path))
        return item_id

    def search(
        self,
        backend: BaseEmbeddingBackend,
        query_vector: Iterable[float],
        limit: int = 20,
        modality: str | None = None,
    ) -> list[SemanticSearchHit]:
        model_id = self.ensure_model(backend)
        query = [float(value) for value in query_vector]
        query_norm = vector_norm(query)
        if query_norm == 0:
            return []

        hits: list[SemanticSearchHit] = []
        with self.db.connect() as conn:
            params: list[object] = [model_id]
            modality_filter = ""
            if modality is not None:
                modality_filter = " AND i.modality = ?"
                params.append(modality)
            rows = conn.execute(
                f"""
                SELECT i.id AS item_id, i.file_id, i.modality, i.item_key, i.text, i.metadata,
                       m.model_key, e.vector, e.norm
                FROM semantic_embeddings e
                JOIN semantic_items i ON i.id = e.item_id
                JOIN semantic_models m ON m.id = e.model_id
                JOIN files f ON f.id = i.file_id
                WHERE e.model_id = ?
                  AND e.error = ''
                  AND f."exists" = 1
                  {modality_filter}
                """,
                params,
            ).fetchall()

        for row in rows:
            vector = decode_vector(row["vector"])
            similarity = cosine_similarity(query, query_norm, vector, float(row["norm"]))
            hits.append(
                SemanticSearchHit(
                    item_id=row["item_id"],
                    file_id=row["file_id"],
                    model_key=row["model_key"],
                    modality=row["modality"],
                    item_key=row["item_key"],
                    text=row["text"],
                    metadata=row["metadata"],
                    similarity=similarity,
                )
            )

        hits.sort(key=lambda hit: hit.similarity, reverse=True)
        return hits[:limit]

    def delete_items_for_file(self, file_id: int, modality: str) -> None:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id FROM semantic_items WHERE file_id = ? AND modality = ?",
                (file_id, modality),
            ).fetchall()
            item_ids = [row["id"] for row in rows]
            if item_ids:
                conn.executemany("DELETE FROM semantic_embeddings WHERE item_id = ?", [(item_id,) for item_id in item_ids])
                conn.executemany("DELETE FROM semantic_items WHERE id = ?", [(item_id,) for item_id in item_ids])
            conn.commit()


def encode_vector(values: Iterable[float]) -> bytes:
    payload = array.array("f", [float(value) for value in values])
    if payload.itemsize != 4:
        raise RuntimeError("float32 vector encoding is not available on this platform")
    if not is_little_endian():
        payload.byteswap()
    return payload.tobytes()


def decode_vector(payload: bytes) -> list[float]:
    values = array.array("f")
    values.frombytes(payload)
    if not is_little_endian():
        values.byteswap()
    return [float(value) for value in values]


def vector_norm(values: Iterable[float]) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in values))


def cosine_similarity(query: list[float], query_norm: float, vector: list[float], norm: float) -> float:
    if query_norm == 0 or norm == 0 or len(query) != len(vector):
        return 0.0
    dot = sum(left * right for left, right in zip(query, vector))
    return dot / (query_norm * norm)


def is_little_endian() -> bool:
    return array.array("H", [1]).tobytes()[0] == 1
