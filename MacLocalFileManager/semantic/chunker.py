from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    item_key: str
    text: str
    metadata: str


def chunk_text(
    text: str,
    prefix: str = "text",
    metadata: str = "",
    target_size: int = 800,
    overlap: int = 100,
) -> list[TextChunk]:
    normalized = normalize_chunk_source(text)
    if not normalized:
        return []

    if target_size <= 0:
        raise ValueError("target_size must be positive")
    if overlap < 0 or overlap >= target_size:
        raise ValueError("overlap must be non-negative and smaller than target_size")

    chunks: list[TextChunk] = []
    start = 0
    index = 0
    while start < len(normalized):
        end = min(len(normalized), start + target_size)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(TextChunk(f"{prefix}:{index}", chunk, metadata))
            index += 1
        if end >= len(normalized):
            break
        start = end - overlap
    return chunks


def normalize_chunk_source(text: str) -> str:
    lines = [" ".join(line.split()) for line in (text or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()
