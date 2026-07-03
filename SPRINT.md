# Pre-Opus Sprint: Database Confidence

## Status: COMPLETED — 2026-07-03

All acceptance criteria were met. See "Observed Results" section for details.

---

## Purpose

This sprint validates the real backend loop before asking Opus for higher-level review or the next architecture sprint.

The goal is to replace uncertainty with evidence: the project should prove that it can ingest GitHub Markdown, persist documents and chunks in PostgreSQL with pgvector, retrieve relevant chunks, answer with citations, and record query metrics.

## Why This Comes Before Opus

Opus will be more useful after the core database path has been validated or its blockers have been documented. Without this sprint, Opus would mostly reason from code and docs, not from observed runtime behavior.

After this sprint, Opus should receive updated docs and focus on a sprint that does not depend on local Docker/Postgres execution, such as external provider hardening or architecture review.

## Sprint Objective

Validate the full local RAG database loop:

```text
GitHub Markdown -> cleanup -> chunking -> embeddings -> PostgreSQL/pgvector
-> retrieval -> extractive answer with citations -> query log/metrics
```

## Observed Results (2026-07-03)

### Environment Used

- Python 3.12.13 via pyenv (`PYENV_VERSION=3.12.13 python3 -m venv .venv`)
- Docker 29.6.1, Docker Compose v5.1.4
- Database: Option A (Docker Compose `pgvector/pgvector:pg15`)

### Step 1: Verify Tooling — PASSED

```
python -m ruff check backend     → All checks passed.
python -m pytest backend/tests   → 55 passed in 2.74s (Python 3.12.13)
```

Note: `python3.12` is not the system default (pyenv global is 3.13.14). Use `PYENV_VERSION=3.12.13 python3 -m venv .venv` to create the correct virtualenv.

### Step 2: Prepare Database — PASSED

```
docker compose up -d postgres     → Container rag-docs-postgres Running (healthy)
cd backend && alembic upgrade head → 3 migrations applied cleanly
```

Tables confirmed: `documents`, `document_chunks`, `doc_sources`, `queries`, `alembic_version`.

### Step 3: Ingest Real Documentation — PASSED

```
python -m app.cli ingest-github https://github.com/tiangolo/fastapi --max-files 5

Output:
  Ingested 5 documents from fastapi/fastapi
  Total chunks: 82
```

### Step 4: Query The Indexed Content — PASSED

```
python -m app.cli query "How do I run FastAPI locally?" --source github

Output:
  **Documentation**: [...] **Source Code**: [...]
  Sources: [1], [2], [3]
  Query 3: 5 chunks in 42ms
```

### Step 5: Inspect Persistence — PASSED

```
documents       | 5
document_chunks | 82
doc_sources     | 1
queries         | 3

doc_sources:  id=1, source_type=github, enabled=true
documents:    5 rows, all linked to doc_source_id=1
chunks:       chunk_hash confirmed, chunk_index confirmed
queries:      retrieved_chunk_count=5, latency_ms=42
```

### Step 6: Validate Source Disable Behavior — PASSED

Disabled source via SQL (`UPDATE doc_sources SET enabled = false WHERE id = 1`).

```
Query returned: "I could not find indexed documentation that answers this question."
Query 4: 0 chunks in 47ms
```

Source re-enabled immediately after test.

### Step 7: Verification Script — PASSED

Added `backend/scripts/verify_pipeline.py`. Run with:

```bash
cd backend
PYTHONPATH=. python scripts/verify_pipeline.py
```

Output:

```
Database connection                       PASS
Expected tables exist                     PASS
Ingest documents and chunks               PASS  (5 docs, 82 chunks)
Persistence counts                        PASS
Query returns answer with citations       PASS  (5 chunks in 4ms)
Disabled source excluded from retrieval   PASS

All checks passed.
```

### Frontend

Not retried in this sprint. Previous failure (Turbopack port-binding) appears environment/sandbox specific. Retry locally or in CI before treating as a regression.

---

## Definition Of Done

This sprint is complete when:

- [x] Backend lint has been run.
- [x] Backend tests have been run in a clean supported environment.
- [x] PostgreSQL with pgvector has been prepared through one of the accepted options.
- [x] Alembic migrations have been run.
- [x] A real GitHub repository has been ingested.
- [x] A query has been executed against persisted chunks.
- [x] Persistence and citations have been inspected.
- [x] Docs have been updated with observed results.
- [x] The next Opus sprint is clearly defined.

---

## Expected Opus Handoff After This Sprint

After this sprint, Opus should not be asked to validate local DB execution. Instead, use Opus for:

**Recommended first Opus sprint:**

```text
External Provider Hardening Review
```

Opus should review GitHub and OpenAI integration behavior, propose simple retry/backoff and timeout improvements, and recommend unit tests with mocks. It should NOT depend on Docker, local PostgreSQL, pgvector runtime validation, frontend redesign, auth, deployment, or external LLM synthesis.

Other valid Opus sprints (in order):

1. External Provider Hardening Review ← recommended first
2. Re-Ingestion And Retrieval Quality Review
3. Architecture And Roadmap Review
4. Optional LLM Provider Design

---

## Current Constraints (Preserved For Reference)

- Docker may not be available on the target machine.
- If Docker is unavailable, use either local PostgreSQL with pgvector or a managed PostgreSQL provider that supports pgvector.
- Keep the sprint backend-first.
- Do not redesign the frontend.
- Do not add auth, queues, multi-tenancy, deployment work, or external LLM synthesis.
- Keep changes small and verified.
- Update docs with observed results.

## Database Provisioning Options (Preserved For Reference)

### Option A: Docker (Used In This Sprint)

```bash
docker compose up -d postgres
```

### Option B: Local PostgreSQL Without Docker

1. Install PostgreSQL.
2. Install the pgvector extension.
3. Create the `rag_docs` database.
4. Configure `DATABASE_URL`.
5. Run Alembic migrations.

Expected `DATABASE_URL` shape:

```text
postgresql+asyncpg://rag:rag@localhost:5432/rag_docs
```

### Option C: Managed PostgreSQL With pgvector

1. Provision a managed PostgreSQL database that supports pgvector.
2. Enable the pgvector extension if required by the provider.
3. Set `DATABASE_URL` to the provider connection string.
4. Run Alembic migrations.

---

# Opus Sprint: External Provider Hardening

## Status: COMPLETED — 2026-07-03

## Objective

Make GitHub and OpenAI embedding integrations resilient to transient failures without adding unnecessary abstraction.

## What Shipped

- **Shared retry helper**: `backend/app/services/http_retry.py` — `request_with_retry(send, *, max_retries, backoff_seconds, sleep)`. Retries transient HTTP status codes (429, 500, 502, 503, 504) and `httpx.RequestError` (connect/timeout/network) with exponential backoff (`backoff * 2**attempt`). Non-transient responses are returned unchanged for the caller to handle via `raise_for_status`. Injectable `sleep` keeps tests instant.
- **GitHub client** (`github.py`): all requests routed through a new `_get` wrapper using the helper; timeout now sourced from `HTTP_TIMEOUT_SECONDS`. Class-level retry defaults keep `__new__`-based test construction safe.
- **OpenAI embeddings** (`embeddings.py`): request wrapped in the helper; constructor gains `timeout_seconds`, `max_retries`, `backoff_seconds`, `sleep` (backward-compatible defaults). `build_embedding_provider` wires settings through.
- **Settings** (`config.py`): `HTTP_TIMEOUT_SECONDS` (30.0), `HTTP_MAX_RETRIES` (2), `HTTP_RETRY_BACKOFF_SECONDS` (0.5), all validated.

## Tests Added (14)

- `test_http_retry.py` (7): status classification, immediate success, transient-status retry, exhaustion returns last response, network-error retry, network-error exhaustion raises, zero-retry passthrough.
- `test_github.py` (+2): transient status retried then succeeds; raises after retries exhausted.
- `test_embeddings.py` (+2): transient status retried then succeeds; network error retried then wrapped error.
- `test_config.py` (+3): hardening defaults; reject negative retries; reject non-positive timeout.

## Verification (2026-07-03)

- `ruff check backend` → **passed**.
- Affected files `test_http_retry.py test_embeddings.py test_github.py test_config.py` → **27 passed** (13 pre-existing + 14 new).
- Full 55+-test suite **not run in this environment**: only Python 3.14 available (no C compiler), so pinned `asyncpg`/`sqlalchemy` could not build. Changed code imports only `httpx`/`pydantic`, so affected-file coverage is the meaningful surface. Re-run full suite in the project's 3.12.13 venv or CI to confirm no regressions.

## Decisions

- Embedding batching intentionally deferred (no evidence yet it is needed).
- No provider abstraction layer added — a single small helper covers both integrations.

## Next Sprint

```text
Re-Ingestion And Retrieval Quality Review
```
