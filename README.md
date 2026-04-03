A document management with text editing and hybrid search. Built with FastAPI, PostgreSQL, and pgvector.

Documents go through two phases: **Drafting** (free edits with auto-save) → **Redlining** (freeze the document, propose changes as suggestions, peer-approve). 

## Quick Start

```bash
pip install -r requirements.txt
make dev    # starts PostgreSQL (Docker) + uvicorn
open http://localhost:8000
```

> **Requires:** Docker (for PostgreSQL + pgvector). Starts automatically via `docker compose`.

The app seeds 3 documents: a frozen NDA with pending suggestions, and two editable agreements. See `sample_requests.sh` for runnable curl examples covering all endpoints.

## API

### Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/documents` | Create a document |
| `GET` | `/documents` | List (paginated: `limit`, `offset`) |
| `GET` | `/documents/{id}` | Get document |
| `DELETE` | `/documents/{id}` | Delete document |
| `PUT` | `/documents/{id}/content` | Inline edit (drafting only, version required) |
| `POST` | `/documents/{id}/freeze` | Freeze for redlining (irreversible) |
| `PATCH` | `/documents/{id}` | Apply targeted redline changes |
| `GET` | `/documents/{id}/history` | Change audit trail |

### Suggestions (frozen documents only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/documents/{id}/suggestions` | Propose a change |
| `GET` | `/documents/{id}/suggestions` | List (`?status=pending`) |
| `PATCH` | `/documents/{id}/suggestions/{sid}` | Accept or reject |
| `DELETE` | `/documents/{id}/suggestions/{sid}` | Delete |
| `POST` | `/documents/{id}/suggestions/{sid}/comments` | Comment |

### Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/search?q=...` | Search all documents |
| `GET` | `/documents/{id}/search?q=...` | Search within one document |

### Redline Changes — `PATCH /documents/{id}`

Two targeting modes, mixable in one request:

```json
{
  "version": 1,
  "changes": [
    {
      "target": { "text": "Party A", "occurrence": 2 },
      "replacement": "Acme Corp"
    },
    {
      "range": { "start": 100, "end": 108 },
      "replacement": "new text"
    }
  ]
}
```

- **Occurrence-based**: `occurrence` is 1-indexed. Use `0` to replace all.
- **Position-based**: byte offsets, auto-adjusted for accumulated shifts from earlier changes.
- Changes apply sequentially. Partial failure allowed — successful changes persist, failed ones return details.

### Error Handling

All errors return `{ "error": "...", "code": N }`. Custom exceptions for 404 (not found), 409 (version conflict), 403 (frozen/self-approval), 400/422 (bad request).

## Testing

```bash
make test                              # all 109 tests
pytest tests/test_redline.py tests/test_search.py -v   # unit tests (fast, no DB)
pytest tests/test_performance.py -v    # performance benchmarks (1MB + 10MB)
```

Tests use an isolated `redline_test` database, truncated between tests.

## Performance

Benchmarks cover both unit-level (pure function, no DB) and integration-level (full HTTP roundtrip via TestClient) tests. Documents tested up to 100MB (~35K pages). Run `make perf` for full scaling analysis with charts.

### Unit Benchmarks (redline engine + search, no DB)

| Operation | 1MB (~350 pg) | 10MB (~3.5K pg) | Complexity |
|-----------|---------------|-----------------|------------|
| Single replacement | < 1s | < 3s | O(n) — `str.find()` scan |
| Replace all occurrences | < 2s | — | O(n * k) — reversed iteration avoids position recalc |
| 100 sequential changes | < 2s | — | O(n * m) — offset delta tracks position shifts |
| Position-based replacement | < 0.1s | — | O(1) — direct slice, no search |
| Text search (snippet extraction) | < 1s | < 5s | O(n) — case-insensitive `re.finditer` |

Uses `str.find()` instead of regex for text replacement to avoid catastrophic backtracking on legal text with special characters (parentheses, dollar signs, section symbols).

### Integration Benchmarks (full API, 3 iterations per tier)

Results from `make perf` — measures real HTTP → DB → service → response latency:

| Endpoint | Dimension | 1KB (~⅓ pg) | 100KB (~35 pg) | 1MB (~350 pg) | 10MB (~3.5K pg) | 100MB (~35K pg) | Scaling |
|----------|-----------|-------------|----------------|---------------|-----------------|-----------------|---------|
| `POST /documents` | content size | 19ms | 36ms | 180ms | 1.6s | 18.2s | ~O(n) |
| `GET /documents/{id}` | content size | 19ms | 19ms | 31ms | 143ms | 1.3s | sub-linear |
| `PUT /{id}/content` | content size | 19ms | 42ms | 200ms | 1.8s | 20.2s | ~O(n) |
| `PATCH /documents/{id}` | num changes | — | — | 71ms @1K | 3.5s @10K | — | ~O(sqrt(n)) |

| Endpoint | Dimension | 10 docs | 1K docs | 10K docs | 100K docs | Scaling |
|----------|-----------|---------|---------|----------|-----------|---------|
| `GET /documents` | corpus size | 18ms | 18ms | 25ms | 43ms | ~O(1) |
| `GET /search` | corpus size | 17ms | 31ms | 168ms | 1.9s | ~O(sqrt(n)) |
| `GET /{id}/search` | content size | 19ms @1KB | 56ms @1MB | 423ms @10MB | 4.3s @100MB | ~O(sqrt(n)) |
| `GET /{id}/suggestions` | suggestions | 20ms @10 | 32ms @1K | 97ms @5K | 1.0s @50K | sub-linear |
| `GET /{id}/history` | entries | 17ms @10 | 27ms @1K | 62ms @5K | 577ms @50K | sub-linear |

### Key Design Decisions Driven by Benchmarks

- **Line-level diffing** for content updates — character-level `SequenceMatcher` was O(n^2), hitting 81s at 100MB. Switching to line-level brought it to 20s (4x faster) while preserving useful change summaries.
- **Batch comment fetching** for suggestion lists — fetching comments per-suggestion (N+1 queries) scaled at 0.28ms/suggestion. A single `WHERE suggestion_id = ANY(...)` query brought 50K suggestions from 13.8s to 1.0s (13.5x faster).
- **List pagination capped at 100** — `GET /documents` stays ~O(1) regardless of table size. `COUNT(*)` for pagination adds minimal overhead even at 100K docs.
- **GIN index on tsvector** — corpus-wide search scales sub-linearly (~sqrt(n)). 100K documents searched in 1.9s via PostgreSQL's inverted index.
- **HNSW index on pgvector** — approximate nearest neighbor for semantic search, O(log n) vs O(n) brute-force cosine similarity.

## Design Rationale

**Freeze model over OT/CRDTs.** Optimized for high document throughput with low per-document concurrency (1-2 editors, not 10 simultaneous). Optimistic locking (`UPDATE WHERE version = N` → 409 on conflict) 

**Pure-function redline engine.** `apply_changes(content, changes) → (new_content, results)` — no state, no I/O. Testable in isolation, deterministic.

**Hybrid search.** PostgreSQL tsvector (stemming, stop words, GIN index) + pgvector (768-dim embeddings, HNSW index). Combined: `α × text_score + (1-α) × semantic_score`. Degrades gracefully without embedding API — text search always works via database trigger.

**Near-zero runtime memory.** All embeddings (768-dim vectors) and text search indexes (tsvector) live in PostgreSQL, not in Python memory. The app is stateless — just a connection pool. An in-memory approach (custom inverted index + cached embeddings) would grow RAM linearly with the corpus; with Postgres, the DB manages its own buffer cache and evicts cold data, so app memory stays near-constant regardless of document count.

**Suggestions as independent objects.** After freeze, concurrent reviewers propose suggestions without conflict. The conflict surface shrinks from "entire document content" to "individual suggestion acceptance."

## Production Architecture

See [INFRA.md](INFRA.md) for the full production infrastructure design — architecture diagrams, CI/CD, security & compliance, scalability, monitoring, and cost analysis.

## Project Structure

```
app/
├── main.py              # FastAPI app, lifespan, error handlers
├── config.py            # Pydantic Settings (env-based)
├── database.py          # PostgreSQL schema, pool, pgvector
├── models.py            # Request/response schemas
├── errors.py            # Custom exception hierarchy
├── seed.py              # Sample legal documents
├── routers/
│   ├── documents.py     # CRUD, redline, freeze, inline edit
│   ├── search.py        # Hybrid tsvector + pgvector search
│   └── suggestions.py   # Propose, approve, discuss
├── services/
│   ├── redline.py       # Pure-function text replacement engine
│   ├── search.py        # Text snippet extraction
│   ├── embeddings.py    # Semantic embeddings (optional)
│   └── llm.py           # LLM change summaries (optional)
└── static/
    └── index.html       # Single-page frontend
tests/
├── test_redline.py      # Unit: redline engine
├── test_search.py       # Unit: text search
├── test_api_documents.py # Integration: document lifecycle
├── test_api_search.py   # Integration: search
├── test_api_suggestions.py # Integration: suggestions
└── test_performance.py  # Benchmarks (1MB + 10MB)
```
