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

## Immediate Priority

The database loop is validated. The next sprint for Opus is:

```text
External Provider Hardening Review
```

Opus should review GitHub and OpenAI integration behavior, propose simple retry/backoff and timeout improvements, and recommend unit tests with mocks. Opus should NOT be asked to validate local DB execution, run Docker, or work on frontend redesign, auth, deployment, or external LLM synthesis.

## Current Recommended Order

### 1. External Provider Hardening (Next Opus Sprint)

Current state:

- GitHub HTTP errors and malformed upstream responses already return clear API responses.
- OpenAI embedding failures return 502 and wrap clearly.
- Missing OpenAI API key returns a clear server configuration error.

Still needed:

- Simple retry/backoff for transient GitHub and OpenAI embedding failures.
- Connection timeout configuration for external HTTP calls.
- Unit tests with mocked HTTP clients covering retry behavior.
- Optional embedding batching only if real ingestion runs show it is needed.

Acceptance criteria:

- Transient external failures are less likely to hard-fail ingestion or queries.
- Retry/backoff is simple and testable.
- Configuration errors remain clear.
- No complex provider abstraction is added before needed.

### 2. Re-Ingestion And Retrieval Quality Review

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

### 3. Optional LLM Answer Provider

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

### 4. Frontend Functionality Before Design

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

### 5. Deployment Preparation

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

- Retry/backoff for GitHub and embedding providers.
- Connection timeout configuration.
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
