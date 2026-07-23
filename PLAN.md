# Plan: RAG for Documentation

## Project Intent

Build a portfolio-ready RAG pipeline that turns GitHub Markdown documentation into cited answers. The release should demonstrate versioned ingestion, hybrid retrieval, privacy-preserving query analytics, protected administration, and reproducible local/deployed demos without overbuilding a multi-tenant platform.

Pitch:

```text
A citation-first documentation RAG app that indexes GitHub Markdown by commit, stores chunks in PostgreSQL/pgvector, retrieves hybrid evidence, and answers or refuses with transparent source links.
```

## Current Architecture

```text
[GitHub Markdown Source]
    -> [Admin Bearer Ingestion]
    -> [DocSource + SourceVersion]
    -> [Markdown Cleanup]
    -> [Heading-Aware Chunking + Chunk Hashing]
    -> [Embedding Provider: local hash or optional OpenAI]
    -> [PostgreSQL + pgvector + full-text search]
    -> [Hybrid Retrieval + RRF + Enabled Source Filter]
    -> [Extractive Answer Or Insufficient-Evidence Refusal]
    -> [Commit-Pinned Evidence]
    -> [Anonymous QueryEvent + Optional Feedback]
    -> [Next.js Citation-First UI]
```

## Implemented API Surface

Public:

- `GET /api/health`
- `GET /api/ready`
- `POST /api/query`
- `PATCH /api/query-events/{uuid}/feedback`

Admin, all protected by `Authorization: Bearer <ADMIN_SECRET>`:

- `POST /api/admin/ingest/github`
- `GET /api/admin/sources`
- `PATCH /api/admin/sources/{id}`
- `GET /api/admin/analytics/summary`

Removed/stale claims: ingestion, source management, analytics, and query history are not public endpoints in the current release.

## Database Model

Current logical tables:

- `documents`
- `document_chunks`
- `doc_sources`
- `source_versions`
- `query_events`
- `alembic_version`

There are six Alembic migration files under `backend/alembic/versions`.

Important behavior:

- `doc_sources` are identified by repository, branch, and path.
- `source_versions` are immutable commit snapshots with document and chunk counts.
- `documents` are unique by source version and repository path.
- `document_chunks` store vector embeddings, full-text search vectors, chunk hashes, and citation metadata.
- `query_events` are anonymous telemetry rows. They do not store visitor question text, answer text, citation snapshots, IP addresses, user agents, or public history.
- Feedback updates only the opaque query event UUID via `PATCH /api/query-events/{uuid}/feedback`.

## Verification Status

Latest recorded release evidence after Sprint 06 Task 5:

- Backend broad suite: `273 passed`, with one existing Starlette warning.
- Frontend: 22 Vitest tests, typecheck, build, and `npm audit` passed after Next 16.2.11.
- Evaluation: `answerable_top3=14/16`, `unsupported_refusals=4/4`, `answer_sentence_validation_failures=0` on `evaluation/pt-br/questions.jsonl`.
- Deployment manifests: Render backend, Vercel frontend, Neon-compatible async/sync DB URL split.
- Smoke contract: `scripts/smoke.sh` plus manual GitHub Actions post-deploy job.

Sprint 06 Task 5 updates `backend/scripts/verify_pipeline.py` to validate the PT-BR FastAPI corpus, `SourceVersion` integrity, active corpus counts, same-commit no-op sync, anonymous query event schema, answered citation metadata, disabled-source exclusion, and `finally` restoration.

Verification commands:

```bash
git diff --check
PYENV_VERSION=3.12.13 python -m ruff check backend
PYENV_VERSION=3.12.13 python -m pytest backend/tests/test_verify_pipeline.py
PYENV_VERSION=3.12.13 TEST_DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag_docs_test python -m pytest backend/tests
npm --prefix frontend run build
```

## Local Demo Plan

1. Start local PostgreSQL with `docker compose up -d postgres`.
2. Apply migrations from `backend/` with `python -m alembic upgrade head`.
3. Ingest the release source with `PYTHONPATH=. python -m app.cli ingest-github https://github.com/fastapi/fastapi docs/pt/docs --branch master --max-files 500`.
4. Run `PYTHONPATH=. python scripts/verify_pipeline.py`.
5. Start `uvicorn app.main:app --reload` and `npm --prefix frontend run dev`.
6. Ask the PT-BR smoke question and inspect commit-pinned evidence.

## Deployment Plan

- Backend deploys to Render from `render.yaml` using `backend/Dockerfile`, `/api/health`, generated `ADMIN_SECRET`, and explicit `DATABASE_URL`/`MIGRATION_DATABASE_URL` secrets.
- Database deploys to Neon or another PostgreSQL provider with pgvector enabled and driver-specific TLS parameters.
- Frontend deploys to Vercel from `frontend/vercel.json` with `NEXT_PUBLIC_BACKEND_URL` supplied by the Vercel project environment.
- Post-deploy smoke uses caller-supplied deployed origins and smoke questions:

```bash
FRONTEND_URL='<frontend-origin>' \
BACKEND_URL='<backend-origin>' \
SMOKE_ANSWERABLE_QUESTION='<answerable-smoke-question>' \
SMOKE_UNSUPPORTED_QUESTION='<unsupported-smoke-question>' \
scripts/smoke.sh
```

Do not commit real deployed URLs or secrets.

## Remaining Scope

Short-term release blockers:

- Run live deployed smoke after real Render and Vercel URLs are available.
- Retry Docker runtime verification when Docker Hub metadata requests are not timing out.

Deferred product work:

- OpenAI embedding batching.
- External LLM synthesis provider behind the extractive fallback.
- Scheduled sync or background worker queue.
- More source connectors.
- Reranking and deeper retrieval-quality tuning.
- Polished design-system pass beyond the current citation-first frontend.

Excluded for this portfolio release:

- Multi-tenancy.
- Public ingestion or public admin operations.
- Persisted visitor content or public query history.
- Complex orchestration before the simple monolith needs it.
