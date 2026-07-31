# Project Summary

## Purpose

`rag-docs-pipeline` is a portfolio RAG application for documentation QA. It ingests GitHub Markdown, stores versioned documents and chunks in PostgreSQL with pgvector, retrieves hybrid evidence, and returns citation-first answers or explicit insufficient-evidence refusals.

The validated release target is the FastAPI Portuguese documentation corpus:

- Repository: `https://github.com/fastapi/fastapi`
- Branch: `master`
- Path: `docs/pt/docs`
- Evaluation dataset: `evaluation/pt-br/questions.jsonl`

This summary reflects the locally audited `dev` branch state on 2026-07-30.

## Current Release State

- Backend: FastAPI monolith with public query/readiness endpoints and Bearer-protected admin endpoints.
- Frontend: Next.js citation-first public chat and protected admin shell.
- Database: PostgreSQL plus pgvector with versioned source snapshots and active-version retrieval.
- Answer mode: extractive only; unsupported `LLM_PROVIDER` values fail during configuration instead of being silently ignored.
- Default embeddings: local deterministic embeddings; OpenAI embeddings are optional but not required for the first deploy.
- Deployment target: Render backend, Vercel frontend, Neon-compatible PostgreSQL/pgvector.
- Final review status: frontend, backend, integrations, dependency security, containers, and browser flows are locally validated.

## Backend Surface

Public API:

- `GET /api/health`
- `GET /api/ready`
- `POST /api/query`
- `PATCH /api/query-events/{uuid}/feedback`

Admin API:

- `POST /api/admin/ingest/github`
- `GET /api/admin/sources`
- `PATCH /api/admin/sources/{id}`
- `GET /api/admin/analytics/summary`

Backend controls:

- `ADMIN_SECRET` is required in production.
- Query, feedback, and sync rate limits are separate.
- Runtime `DATABASE_URL` must use `postgresql+asyncpg`.
- Migration `MIGRATION_DATABASE_URL` must use `postgresql+psycopg`.
- `EMBEDDING_DIMENSIONS` is locked to `1536` for the current fixed pgvector schema.
- Production `ALLOWED_ORIGINS` must be explicitly set, exact, non-wildcard, non-local, and path/query/fragment-free.

## Ingestion And Storage

- `DocSource` identifies a source by repository, branch, and path.
- `SourceVersion` stores immutable commit snapshots with embedding provider, model, dimensions, document count, and chunk count.
- Active versions are promoted after successful synchronization; retained versions remain available for pruning and audit.
- Sources with no indexable Markdown are rejected before source creation or version promotion.
- Documents are unique by source version and repository path.
- Chunks store text, hash, metadata, pgvector embedding, and PostgreSQL full-text search vector.
- The GitHub client uses API requests with optional Bearer auth for GitHub API endpoints and a separate unauthenticated client for `raw.githubusercontent.com` file downloads.

## Retrieval And Answering

- Retrieval combines pgvector cosine search and PostgreSQL full-text search with reciprocal-rank fusion.
- Retrieval excludes disabled sources and inactive source versions.
- Public query input is bounded server-side for `question` and `source`.
- Extractive answer generation selects cited sentences from retrieved chunks.
- Answered responses must include citation IDs that resolve to evidence items with commit-pinned GitHub blob URLs.
- Unsupported questions return `state="insufficient_evidence"`, no answer, and best available evidence.
- The evaluation gate now fails answerable cases that retrieve expected evidence but do not produce answered, cited sentences.

## Privacy Contract

The release privacy contract is intentionally strict:

- Do not persist visitor questions.
- Do not persist answer text.
- Do not persist citation snapshots.
- Do not persist public request bodies.
- Do not persist IP addresses or user agents.
- Do not retain request paths in application or Uvicorn access logs.
- Do not expose public query history.

`query_events` stores only opaque operational telemetry: UUID, state, latency, retrieved count, source IDs, source version IDs, top fused score, score gap, optional feedback, and timestamp.

Additional privacy hardening:

- Uvicorn access logs are disabled in Docker and Render commands.
- Request-completion logs use operation names instead of route paths.
- Public query SQLAlchemy failures return a generic `503` and log only sanitized error class names plus request ID.
- Rollback failures in the public query error path are also sanitized.

## Frontend Surface

- Next.js 16.2.11 application.
- Portuguese public UX for documentation questions.
- Citation-first answer layout with sentence-level citation IDs.
- Evidence panel shows commit-pinned source links.
- Feedback controls use opaque event UUIDs.
- Public question composer mirrors the backend maximum question length.
- Admin shell keeps the Bearer secret in memory only.
- Admin sync sends `max_files: 500` to support the approved FastAPI PT-BR corpus.
- Admin ingestion uses a five-minute client timeout; ordinary API calls retain the short default timeout.
- Admin source cards show active commit/version and active document/chunk counts.

## Deployment

- `render.yaml` defines the Render backend service, Dockerfile path, startup migration command, health path, free plan, and required secrets.
- `backend/Dockerfile` runs Alembic migrations before Uvicorn and includes `--no-access-log`.
- `frontend/vercel.json` requires `NEXT_PUBLIC_BACKEND_URL` from the Vercel provider environment before `npm run build`.
- No deployable placeholder backend URL is committed in the Vercel manifest.
- `docs/deployment.md` documents Render, Vercel, Neon TLS URL split, exact CORS origins, and smoke steps.
- `scripts/smoke.sh` validates frontend availability, backend health/readiness, answered query, unsupported query refusal, and unauthenticated admin `401` without printing response bodies.

## Verification Evidence

Latest final verification from the audited `dev` branch:

- `git diff --check`: passed.
- `./.venv/bin/python -m ruff check backend`: passed.
- `TEST_DATABASE_URL=postgresql+psycopg://rag:rag@127.0.0.1:5432/rag_docs_test ./.venv/bin/python -m pytest backend/tests`: `317 passed`, with five upstream deprecation warnings.
- `npm --prefix frontend run typecheck`: passed.
- `npm --prefix frontend run test:run`: `36 passed`.
- `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000 npm --prefix frontend run build`: passed.
- `npm audit --audit-level=high`: no known vulnerabilities.
- `pip-audit -r backend/requirements.txt`: no known vulnerabilities.
- Live GitHub synchronization promoted FastAPI commit `95f8322ee1dcda7ceace7b1c4f6c9915b36d748f` with 124 documents and 1,353 chunks.
- `PYTHONPATH=backend ./.venv/bin/python backend/scripts/evaluate_retrieval.py --dataset evaluation/pt-br/questions.jsonl --top-k 3 --output /private/tmp/rag-evaluation-post-sync.json`: `Evaluation PASSED: answerable_top3=14/16, unsupported_refusals=4/4, answer_sentence_validation_failures=0` after the new version was promoted.
- `docker compose up --build -d postgres backend frontend`: images built and all services started; PostgreSQL reported healthy.
- Runtime smoke: frontend `200`, backend health `ok`, readiness `database=ok` and `pgvector=ok`, both local CORS origins accepted, answered query cited commit-pinned evidence, unsupported query refused, and unauthenticated admin returned `401`.
- Firefox WebDriver BiDi check: five screenshots captured, no browser errors, and no framework error overlay.

## Known Remaining Work

- Live deployed smoke is still pending real Vercel and Render origins plus smoke questions.
- OpenAI embedding batching is not implemented.
- External LLM synthesis is not implemented by design in the current extractive answer mode.
- Local hash embeddings are deterministic and free but weaker than semantic embeddings.
- There is no scheduled sync, worker queue, reranker, or non-GitHub connector.
- Starlette currently emits five non-blocking deprecation warnings in backend tests; these are upstream compatibility warnings, not test failures.

## Useful Commands

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
