from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticModelInfo:
    id: int | None
    model_key: str
    modality: str
    dimensions: int
    version: str


@dataclass(frozen=True)
class SemanticItem:
    id: int | None
    file_id: int
    modality: str
    item_key: str
    text: str
    metadata: str
    source_size: int
    source_modified_at: float


@dataclass(frozen=True)
class SemanticSearchHit:
    item_id: int
    file_id: int
    model_key: str
    modality: str
    item_key: str
    text: str
    metadata: str
    similarity: float


@dataclass(frozen=True)
class SemanticJob:
    id: int
    file_id: int
    job_type: str
    status: str
    attempts: int
    last_error: str

