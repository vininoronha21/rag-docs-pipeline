# Project Summary

## Project

`rag-docs-pipeline` is a personal portfolio RAG application for documentation. It indexes GitHub Markdown, stores versioned chunks and embeddings in PostgreSQL with pgvector, retrieves hybrid evidence, and returns cited answers or explicit insufficient-evidence refusals.

The release target is the FastAPI Portuguese documentation source:

- Repository: `https://github.com/fastapi/fastapi`
- Branch: `master`
- Path: `docs/pt/docs`
- Evaluation dataset: `evaluation/pt-br/questions.jsonl`

## Current Moment

Sprint 06 Tasks 1-4 delivered the portfolio release foundation: evaluation gate, protected admin, anonymous query events, readiness/logging/rate limiting, citation-first frontend, deployment manifests, and post-deploy smoke contract. Sprint 06 Task 5 refreshes stale documentation and the local verifier.

## Implemented System

### Backend

- FastAPI app with public `/api/health`, `/api/ready`, `/api/query`, and `/api/query-events/{uuid}/feedback`.
- Bearer-protected `/api/admin/ingest/github`, `/api/admin/sources`, `/api/admin/sources/{id}`, and `/api/admin/analytics/summary`.
- `ADMIN_SECRET` required in production.
- Query, feedback, and sync rate limits.
- Structured request logging with query event ID and evidence state context.
- Readiness checks for database and pgvector.
- GitHub client with timeout and retry/backoff for transient upstream failures.
- Pydantic settings with explicit async `DATABASE_URL` and sync `MIGRATION_DATABASE_URL` validation.

### Ingestion And Storage

- `DocSource` tracks repository, branch, path, language, active version, sync time, and enabled state.
- `SourceVersion` tracks immutable commit snapshots, embedding provider/model/dimensions, document count, and chunk count.
- Documents are unique by source version and repository path.
- Chunks store text, hash, metadata, pgvector embedding, and PostgreSQL full-text search vector.
- Six Alembic migrations are present under `backend/alembic/versions`.

### Retrieval And Answering

- Local deterministic embeddings by default.
- Optional OpenAI embeddings with configured API key, timeout, and retry/backoff.
- Hybrid retrieval combines pgvector cosine search and PostgreSQL full-text search with reciprocal-rank fusion.
- Retrieval excludes disabled sources and inactive source versions.
- Extractive answer generation remains the default and only implemented LLM layer.
- Answers include citation IDs and evidence items with repository path, section, excerpt, commit SHA, scores, and commit-pinned GitHub blob URLs.
- Unsupported questions return `state="insufficient_evidence"`, no answer, and best available evidence.

### Privacy

The current privacy policy is intentionally narrow:

- No persisted visitor question text.
- No persisted answer text.
- No persisted citation snapshot.
- No persisted IP address or user agent.
- No public query history.

`query_events` stores only an opaque UUID, state, latency, retrieved chunk count, source IDs, source version IDs, top fused score, score gap, optional feedback, and timestamp.

### Frontend

- Next.js 16.2.11 frontend.
- Citation-first public chat.
- Evidence panel with commit-pinned links.
- Feedback controls tied to opaque event UUIDs.
- Protected admin shell for source ingestion and management.
- Latest recorded Task 4 frontend validation: typecheck passed, production build passed, 22 Vitest tests passed, and `npm audit` was clean.

### Deployment

- `render.yaml` defines the Render backend service, Dockerfile, startup migration command, health path, and required environment variables.
- `frontend/vercel.json` defines the Vercel Next.js build and requires `NEXT_PUBLIC_BACKEND_URL` from the provider environment.
- `docs/environment.md` and `docs/deployment.md` document Neon-compatible runtime/migration database URL split.
- `scripts/smoke.sh` validates frontend availability, backend health/readiness, answered public query, unsupported public query, and unauthenticated admin `401` without printing response bodies.

## API Surface

Public:

- `GET /api/health`
- `GET /api/ready`
- `POST /api/query`
- `PATCH /api/query-events/{uuid}/feedback`

Admin:

- `POST /api/admin/ingest/github`
- `GET /api/admin/sources`
- `PATCH /api/admin/sources/{id}`
- `GET /api/admin/analytics/summary`

Ingestion, source management, analytics, and history are admin-only or absent from the public API in this release.

## Verification Evidence

Latest recorded after Sprint 06 Task 5:

- Backend broad suite: `273 passed`, with one existing Starlette warning.
- Frontend: 22 Vitest tests, typecheck, build, and audit passed.
- Evaluation: `answerable_top3=14/16`, `unsupported_refusals=4/4`, `answer_sentence_validation_failures=0`.
- Docker runtime verification from Task 3 was blocked by Docker Hub metadata timeout.
- Live deployed smoke remains pending deployed URLs.

Sprint 06 Task 5 verifier update:

- `backend/scripts/verify_pipeline.py` targets the FastAPI PT-BR docs source.
- It checks the anonymous `query_events` table.
- It validates source versions, active counts, no-op re-sync, anonymous query event schema, answered citation metadata, disabled-source exclusion, and source restoration.

Commands:

```bash
git diff --check
PYENV_VERSION=3.12.13 python -m ruff check backend
PYENV_VERSION=3.12.13 python -m pytest backend/tests/test_verify_pipeline.py
PYENV_VERSION=3.12.13 TEST_DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag_docs_test python -m pytest backend/tests
npm --prefix frontend run build
```

## Demo Commands

Local ingestion and verification:

```bash
docker compose up -d postgres
cd backend
PYENV_VERSION=3.12.13 python -m alembic upgrade head
PYENV_VERSION=3.12.13 PYTHONPATH=. python -m app.cli ingest-github \
  https://github.com/fastapi/fastapi \
  docs/pt/docs \
  --branch master \
  --max-files 500
PYENV_VERSION=3.12.13 PYTHONPATH=. python scripts/verify_pipeline.py
```

Deployed smoke template:

```bash
FRONTEND_URL='<frontend-origin>' \
BACKEND_URL='<backend-origin>' \
SMOKE_ANSWERABLE_QUESTION='<answerable-smoke-question>' \
SMOKE_UNSUPPORTED_QUESTION='<unsupported-smoke-question>' \
scripts/smoke.sh
```

## Current Limitations

- Live deployed smoke has not run because real URLs were not provided.
- Docker runtime verification should be retried after the Docker Hub metadata timeout clears.
- OpenAI embedding batching is not implemented.
- External LLM synthesis is not implemented; extractive answer mode is the only answer provider.
- Local hash embeddings are deterministic and free but weaker than semantic embeddings.
- There is no scheduled sync, worker queue, reranker, or non-GitHub connector.
