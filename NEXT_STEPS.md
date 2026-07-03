# Next Steps

## Working Principles

- Keep the project simple and practical.
- Backend first: database, integration, retrieval correctness, and tests.
- Frontend work stays functional until the design sprint.
- Avoid visual redesign, animations, and UI polish for now.
- Prefer small, verified increments.
- Update `README.md`, `SUMMARY.md`, and `NEXT_STEPS.md` when project direction or progress changes.
- For each code change, provide a suggested commit message and a short explanation.

## Completed: Pre-Opus Database Confidence Sprint (2026-07-03)

All items in this sprint are done.

Environment used:

- Python 3.12.13 via pyenv
- Docker 29.6.1, Docker Compose v5.1.4
- PostgreSQL via `pgvector/pgvector:pg15` Docker Compose (Option A)

What passed:

- `python -m ruff check backend` — passed
- `python -m pytest backend/tests` — 55/55 passed under Python 3.12.13
- `alembic upgrade head` — 3 migrations applied cleanly
- All expected tables confirmed: `documents`, `document_chunks`, `doc_sources`, `queries`, `alembic_version`
- Ingest `tiangolo/fastapi` (5 files) — 5 documents, 82 chunks
- Query "How do I run FastAPI locally?" — answer + 3 citations, 5 chunks, 42ms, query log persisted
- Source disable filter — 0 chunks when disabled, source re-enabled
- `PYTHONPATH=. python scripts/verify_pipeline.py` — all 6 checks passed

What was not tested in this sprint:

- Frontend build (not retried; previous sandbox failure appears environment-specific, not a regression)

## Completed: External Provider Hardening Sprint (2026-07-03)

Done. GitHub and OpenAI embedding calls are now resilient to transient failures.

What shipped:

- Shared `request_with_retry` helper in `app/services/http_retry.py` (exponential backoff; retries transient 429/5xx and `httpx.RequestError`).
- `GithubClient` routes all requests through the helper and uses `HTTP_TIMEOUT_SECONDS`.
- `OpenAIEmbeddingProvider` wraps its request in the helper and uses the configurable timeout.
- New settings: `HTTP_TIMEOUT_SECONDS` (default 30.0), `HTTP_MAX_RETRIES` (default 2), `HTTP_RETRY_BACKOFF_SECONDS` (default 0.5).
- 14 new mocked-HTTP unit tests (retry helper, GitHub retry, OpenAI embedding retry, config validation).

Verification note:

- Ruff passed on `backend`.
- The 4 affected test files (27 tests, incl. 14 new) passed. The full 55+-test suite requires the project's Python 3.12.13 venv; this machine currently only has Python 3.14 without a C compiler, so `asyncpg`/`sqlalchemy` could not be installed here. Re-run the full suite in the 3.12.13 venv or CI to confirm no regressions.
- Embedding batching was intentionally NOT added (defer until real ingestion runs justify it).

## Immediate Priority

External provider hardening is done. The next sprint is:

```text
Re-Ingestion And Retrieval Quality Review
```

## Current Recommended Order

### 1. Re-Ingestion And Retrieval Quality Review

Current state:

- Documents are upserted by `source_url`.
- Chunks have content hashes.
- Existing chunks are deleted and recreated on document update.
- Source identity tracks repo, branch, path, last sync, and enabled state.

Next improvements:

- Confirm repeated ingestion of the same repo/path behaves predictably.
- Add tests around repeated ingestion.
- Review `RETRIEVAL_MIN_SCORE` behavior with local and semantic embeddings.
- Inspect real retrieved chunk text quality.
- Tune chunk size and overlap only if real examples justify it.

Acceptance criteria:

- Re-ingesting the same source behaves predictably (no duplicate docs/chunks).
- Retrieval quality is understood for at least one real documentation repo.

### 2. Optional LLM Answer Provider

Current state:

- Answer generation is extractive.
- `LLM_PROVIDER=openai` and `OPENAI_CHAT_MODEL` exist in settings but are not wired.

Future step:

- Add an optional LLM answer provider behind the existing extractive fallback.
- Keep extractive mode as the default local/free mode.
- Add prompt-injection safeguards before sending content to an external LLM.

Acceptance criteria:

- The app still works with no paid key (extractive mode).
- External LLM mode is opt-in.
- Prompt construction is tested.
- Answer still returns citations.

### 3. Frontend Functionality Before Design

Do only if backend validation is stable:

- Ingestion status.
- Query history view.
- Source management controls.
- Citation preview details.
- Empty indexed-database guidance.

Do later in design sprint:

- Visual redesign.
- Dark mode direction.
- Motion/animation work.
- Detailed layout polish.

### 4. Deployment Preparation

Do after backend validation:

- Document production environment variables.
- Add notes for managed Postgres/pgvector options.
- Add Render/Railway backend deployment notes.
- Add Vercel frontend deployment notes.
- Add CI checks for backend tests and lint.

## Verification Commands

```bash
# Toolchain check
source .venv/bin/activate
python -m ruff check backend
python -m pytest backend/tests

# Full pipeline verification
docker compose up -d postgres
cd backend
alembic upgrade head
PYTHONPATH=. python scripts/verify_pipeline.py
```

## Backlog

### Backend

- Retry/backoff for GitHub and embedding providers. (done 2026-07-03)
- Connection timeout configuration. (done 2026-07-03)
- Optional embedding batching.
- Optional LLM answer provider.
- Stronger prompt-injection protections.
- Re-ingestion behavior tests.
- Better structured logging.
- Lightweight seed/demo script.

### Retrieval And RAG

- Real repository retrieval quality review.
- Chunk size and overlap tuning from examples.
- Minimum relevance threshold tuning.
- Citation formatting improvements.
- Optional reranking.
- Better refusal behavior for weak context.

### Frontend

- Ingestion status.
- Query history.
- Source management.
- Citation previews.
- Empty state.
- Later visual design system.

### DevOps

- CI for backend lint/tests.
- Docker build validation.
- Deployment notes.
- Managed Postgres/pgvector notes.
- Scheduled ingestion after MVP stability.

## What Not To Do Yet

- Do not build a complex multi-tenant system.
- Do not add auth before deployment needs are clearer.
- Do not redesign the frontend now.
- Do not add heavy orchestration or queues before ingestion proves it needs them.
- Do not replace the extractive fallback until external LLM mode is tested and optional.
- Do not optimize for massive scale before the project has a stable personal-project MVP.
