# v7 Offline Semantic Index Architecture

v7 focuses on offline semantic search for PDF documents and images. Video and audio are intentionally excluded from the v7 scope to keep indexing time, model size, memory use, and product complexity under control.

## 1. Product Boundary

### Goals

- Keep the existing exact Chinese filename search as the fastest and highest priority path.
- Add offline semantic search for PDF content and local images.
- Use local-only indexing and inference. No online AI calls.
- Keep semantic indexing optional and controllable from Settings.
- Run semantic indexing in the background with progress, pause/cancel, and resumable state.
- Make each implementation stage verifiable with unit tests, integration tests, and a small fixture dataset.

### Non-goals

- No chat assistant.
- No automatic file organization.
- No video or audio semantic indexing in v7.
- No cloud model API.
- No default heavy model indexing on first launch.

## 2. Architecture Overview

```text
UI
  |
  | search query, category filter, semantic toggle
  v
Hybrid Searcher
  | exact filename/path/content/OCR search
  | semantic PDF/image vector search
  v
SQLite
  | files
  | file_contents
  | file_ocr
  | semantic_items
  | semantic_embeddings
  | semantic_jobs
  | semantic_models

Background Workers
  | semantic scheduler
  | PDF chunk indexer
  | image OCR indexer
  | image visual embedding indexer
  v
Local Model Runtime
  | Phase 1: deterministic fake/local hashing backend for testability
  | Phase 2: local text embedding backend
  | Phase 3: Core ML image embedding helper
```

The app should use a hybrid ranking model:

1. Filename exact match.
2. Filename prefix match.
3. Filename contains or fuzzy match.
4. Path contains or fuzzy match.
5. Existing extracted document/OCR keyword match.
6. Semantic PDF text match.
7. Semantic image visual match.

Semantic results should not replace exact search; they should supplement it.

## 3. Module Layout

Add these modules:

```text
semantic/
  __init__.py
  config.py
  models.py
  chunker.py
  vector_store.py
  scheduler.py
  indexer.py
  search.py
  backends/
    __init__.py
    base.py
    deterministic.py
    text_local.py
    image_coreml.py
  helpers/
    README.md
    macos_coreml_image_embedder/
```

### Module Responsibilities

- `semantic/config.py`: model names, enabled flags, batch sizes, limits.
- `semantic/models.py`: dataclasses for chunks, embeddings, jobs, search hits.
- `semantic/chunker.py`: split PDF/text content into stable chunks.
- `semantic/vector_store.py`: SQLite persistence for embeddings and cosine search.
- `semantic/scheduler.py`: enqueue/resume/cancel semantic jobs.
- `semantic/indexer.py`: dispatch files to PDF or image semantic pipelines.
- `semantic/search.py`: semantic query expansion and vector search.
- `semantic/backends/base.py`: embedding backend interface.
- `semantic/backends/deterministic.py`: deterministic test backend.
- `semantic/backends/text_local.py`: local text embedding backend placeholder.
- `semantic/backends/image_coreml.py`: Core ML image embedding helper wrapper.

## 4. Database Design

Keep `files`, `file_contents`, and `file_ocr`. Add v7 tables:

```sql
CREATE TABLE semantic_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_key TEXT NOT NULL UNIQUE,
    modality TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    version TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE semantic_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    modality TEXT NOT NULL,
    item_key TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '',
    source_size INTEGER NOT NULL,
    source_modified_at REAL NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(file_id, modality, item_key),
    FOREIGN KEY(file_id) REFERENCES files(id)
);

CREATE TABLE semantic_embeddings (
    item_id INTEGER NOT NULL,
    model_id INTEGER NOT NULL,
    vector BLOB NOT NULL,
    norm REAL NOT NULL,
    indexed_at REAL NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(item_id, model_id),
    FOREIGN KEY(item_id) REFERENCES semantic_items(id),
    FOREIGN KEY(model_id) REFERENCES semantic_models(id)
);

CREATE TABLE semantic_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY(file_id) REFERENCES files(id)
);
```

Recommended indexes:

```sql
CREATE INDEX idx_semantic_items_file ON semantic_items(file_id);
CREATE INDEX idx_semantic_items_modality ON semantic_items(modality);
CREATE INDEX idx_semantic_jobs_status ON semantic_jobs(status);
CREATE INDEX idx_semantic_jobs_file_type ON semantic_jobs(file_id, job_type);
```

Vector format for MVP:

- Store `float32` arrays as little-endian BLOBs.
- Store `norm` separately.
- For up to tens of thousands of chunks/images, SQLite scan with Python cosine is acceptable for MVP.
- Later, add approximate nearest neighbor if performance demands it.

## 5. Settings and Safety

Add settings:

- `semantic_enabled`: default `false`.
- `semantic_pdf_enabled`: default `true` when semantic is enabled.
- `semantic_image_enabled`: default `true` when semantic is enabled.
- `semantic_index_on_battery`: default `false`.
- `semantic_max_file_size_mb`: default `100`.
- `semantic_max_pdf_pages`: default `300`.
- `semantic_max_image_pixels`: default `25000000`.
- `semantic_worker_sleep_ms`: default `10`.

UI requirements:

- Add Settings section: "离线语义索引".
- Show model size and current index size.
- Show indexing queue count, done count, failed count.
- Buttons: Enable, Pause, Resume, Rebuild semantic index.
- Never run heavy semantic indexing automatically on first launch.

## 6. Implementation Phases

### v7-1: Semantic Infrastructure

Status: implemented as the initial foundation. Real model backends are still out of scope for v7-1.

Deliverables:

- Add semantic database tables and migration.
- Add deterministic embedding backend for tests.
- Add vector serialization/deserialization.
- Add cosine similarity search.
- Add semantic job queue with pending/running/done/failed statuses.
- Add Settings flags, default disabled.

Verification:

- Unit test vector roundtrip.
- Unit test cosine ranking.
- Unit test job enqueue/resume.
- Unit test schema migration on a fresh DB and existing DB.
- No UI freezes during job processing.

Acceptance criteria:

- `python -m unittest discover -s tests` passes.
- A test file can create 3 semantic items and retrieve the most similar one.
- Disabling semantic search produces no semantic results.

### v7-2: PDF Semantic Index

Status: implemented with deterministic text embeddings. Real local text models are still out of scope for this step.

Deliverables:

- Reuse existing PDF/text extraction from `file_contents`.
- Chunk extracted text with stable chunk ids.
- Index PDF/text chunks using deterministic backend first.
- Add semantic PDF results into hybrid search.
- Add result reason: `PDF语义命中`.

Chunking rules:

- Target chunk size: 600-1000 Chinese characters.
- Overlap: 80-120 characters.
- Include metadata: page number when available, chunk index, source extractor.
- Stable `item_key`: `pdf:{page}:{chunk}` or `text:{chunk}`.

Verification:

- Fixture PDF/text with known content.
- Query synonym or related phrase returns expected PDF chunk.
- If file size/modified time unchanged, semantic item is skipped.
- If file changes, old semantic items are replaced.

Acceptance criteria:

- Existing exact filename search still ranks above semantic results.
- Semantic PDF search works with semantic toggle enabled.
- Search result shows source file, path, and snippet.

### v7-3: Image OCR Semantic Index

Status: implemented with deterministic text embeddings over existing OCR text.

Deliverables:

- Use existing OCR text in `file_ocr`.
- Create semantic items for OCR text.
- Add result reason: `图片文字语义命中`.
- Keep OCR scanning separate from visual image indexing.

Verification:

- Fixture image OCR text inserted through fake OCR backend.
- Semantic search finds image through OCR text.
- OCR failures do not block visual indexing.

Acceptance criteria:

- Image with OCR text can be found by semantically related Chinese query.
- Failed OCR rows are visible in error logs but do not crash indexing.

### v7-4: Image Visual Semantic Index

Status: implemented with deterministic image embeddings as a replaceable offline scaffold.

Deliverables:

- Add image visual embedding backend interface.
- MVP backend uses deterministic embeddings for tests.
- Mac production backend should be a Core ML helper process or a local model backend.
- Store one visual embedding per image file.
- Add result reason: `图片视觉语义命中`.

Recommended production design:

- Keep PySide6 as UI.
- Add a helper executable for Core ML image embedding.
- Python calls helper by subprocess with file path input.
- Helper returns JSON: model key, dimensions, vector, error.
- This isolates macOS model runtime from PyInstaller/Python stability issues.

Verification:

- Deterministic backend test: images with known labels/vectors rank correctly.
- Repeated indexing skips unchanged images.
- Semantic disabled state hides visual semantic results.
- Bad/corrupt image records error and continues.
- Large image downscaling is reserved for the production backend.
- Re-index only when file size or modified time changes.

Acceptance criteria:

- Searching "海边" can return images that do not contain "海边" in filename when visual backend is available.
- Without production visual backend installed, app still runs with the deterministic offline scaffold.

### v7-5: UI Integration and Packaging

Status: implemented for settings integration and packaging configuration checks.

Deliverables:

- Settings page for semantic indexing controls.
- Status bar progress for semantic queue.
- Result badges: `文件名`, `内容`, `OCR`, `PDF语义`, `图片语义`.
- PyInstaller spec includes semantic Python modules.

Verification:

- Launch app with semantic disabled.
- Enable semantic indexing and process fixture folder.
- Pause/resume semantic queue.
- Rebuild semantic index.
- Package and verify `.dmg`.

Acceptance criteria:

- App can launch without bundled semantic model.
- App can package semantic Python modules through PyInstaller spec hidden imports.
- No heavy semantic indexing starts until user enables it and runs the related slow task.
- UI remains responsive while indexing.

## 7. Resource Budget

Target budgets:

- App without model: keep near current package size.
- App with small model: target 300 MB to 800 MB.
- Upper acceptable local package size: about 2 GB.
- Runtime memory during indexing: target under 2 GB for small model.
- Runtime memory during normal search: target under 800 MB incremental overhead.

Index size rough estimates:

- Text/PDF chunk embedding: 384 dimensions float32 = about 1.5 KB per chunk before DB overhead.
- 100,000 chunks = about 150 MB raw vectors plus SQLite overhead.
- Image embedding: 512 dimensions float32 = about 2 KB per image before DB overhead.
- 50,000 images = about 100 MB raw vectors plus SQLite overhead.

Operational controls:

- Batch indexing.
- Skip unchanged files.
- Downscale images.
- Limit PDF pages by default.
- Pause on battery by default.
- Never block filename search.

## 8. Model Runtime Strategy

### Option A: Python-only Local Model

Pros:

- Faster to prototype.
- Easier to test inside existing app.

Cons:

- Larger dependencies.
- More memory overhead.
- Harder to use Apple Neural Engine reliably.
- Packaging is heavier and more fragile.

Best use:

- Prototype and deterministic tests.

### Option B: Swift/Core ML Helper

Pros:

- Better fit for Apple Silicon.
- Cleaner Core ML integration.
- More predictable packaging and runtime isolation.

Cons:

- Requires Swift helper project.
- Requires model conversion to Core ML.
- More build steps.

Best use:

- Production image visual embedding.

### Recommendation

Use deterministic backend for v7-1 and tests. Use Python/local text backend for v7-2 if acceptable. Use Swift/Core ML helper for v7-4 image visual embeddings.

## 9. Search Ranking Contract

Hybrid search should return a unified list:

```text
rank_score = exact_rank + semantic_penalty - recency_bonus - semantic_similarity_bonus
```

Rules:

- Exact filename match always beats semantic.
- Filename hit always beats path hit.
- Path/content/OCR keyword hits usually beat semantic hits.
- Semantic results can outrank weak path-only hits only if similarity is high and no filename hit exists.
- Archive priority still applies within equivalent ranks.

For transparency, every semantic result must show:

- Match type.
- Similarity score bucket: high / medium / low.
- Snippet or visual label when available.
- Model/backend name.

## 10. Test Fixture Plan

Create `tests/fixtures/semantic/`:

```text
pdf/
  beach_trip.txt
  contract_budget.txt
images/
  beach_photo.jpg
  invoice_screenshot.jpg
```

For deterministic tests, do not require real model files. Use filenames or fixture metadata to produce deterministic vectors.

Required tests:

- `test_semantic_schema.py`
- `test_vector_store.py`
- `test_semantic_jobs.py`
- `test_pdf_semantic_indexer.py`
- `test_image_semantic_indexer.py`
- `test_hybrid_search_ranking.py`
- `test_semantic_disabled.py`

## 11. Milestones

### Part 1: Foundation

Build semantic tables, vector store, deterministic backend, settings flags, and tests.

### Part 2: PDF Semantic

Chunk existing extracted text, index chunks, add semantic PDF search, add UI result reason.

### Part 3: Image OCR Semantic

Index OCR text into semantic items and search through OCR semantic vectors.

### Part 4: Image Visual Semantic

Add deterministic visual embeddings now; keep Core ML helper wrapper as the next production backend.

### Part 5: Product Polish

Settings, progress, pause/resume, package verification, index size reporting.

Implemented scope:

- Persist semantic search toggle in `app_settings`.
- Add PDF/image semantic switches in the settings dialog.
- Show semantic item/error counts in the settings dialog.
- Include semantic modules in the PyInstaller spec.
- Add tests for semantic settings text, semantic summary counts, and packaging config.

## 12. Immediate Next Step

Runtime verification has started. Continue with production-backend planning and broader real-world scan testing. Do not add online model dependencies.

Implementation checklist:

- Packaged `.app` starts with an isolated data directory.
- Installer-like mounted volumes are filtered from external disk prompts.
- Search box result backfill is covered by a PySide runtime test.
- Main UI no longer shows the scan-range sidebar; scan control is moved to Settings.
- Engineering categories now include drawing, CAD, and bill files.
- Check search responsiveness while content/OCR/semantic stages are running.
- Decide whether Core ML image embedding should be a helper executable or an in-process backend.

This gives a verified base before any large model or Core ML helper enters the project.
