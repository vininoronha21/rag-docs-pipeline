# Plan: RAG for Documentation

## Project Intent

Build a personal, portfolio-oriented RAG pipeline that turns GitHub Markdown documentation into cited answers. The project should stay practical: backend correctness, database confidence, retrieval quality, and clear documentation matter more than platform breadth or visual polish right now.

Pitch:

```text
A pipeline that indexes messy documentation, chunks it, stores embeddings in PostgreSQL/pgvector, and answers natural-language questions with cited source context.
```

## Current Status

The project is past the initial scaffold. It has a working monolithic MVP shape:

- FastAPI backend with GitHub Markdown ingestion.
- Markdown cleaning and heading-aware chunking.
- Local deterministic embeddings by default.
- Optional OpenAI embeddings through environment configuration.
- PostgreSQL with pgvector and Alembic migrations.
- Vector retrieval with source filtering and disabled-source exclusion.
- Extractive answer generation with citations.
- Query logging, feedback, history, and analytics endpoints.
- Typer CLI for ingestion and querying.
- Next.js frontend shell for repository indexing, chat, citations, and feedback.
- GitHub Actions CI configured for backend lint/tests and frontend build.
- Repeatable full-pipeline verification script: `backend/scripts/verify_pipeline.py`.

The local database loop has been validated, and External Provider Hardening is complete: GitHub and OpenAI calls now have configurable timeouts and retry/backoff on transient failures. The next milestone is Re-Ingestion and Retrieval Quality Review.

## Current Architecture

```text
[GitHub Markdown Ingestion]
    -> [Markdown Cleanup]
    -> [Heading-Aware Chunking + Chunk Hashing]
    -> [Embedding Provider: local hash or OpenAI]
    -> [PostgreSQL + pgvector]
    -> [Vector Retrieval + Source Filtering]
    -> [Extractive Answer + Citations]
    -> [Query Logs, Feedback, Analytics]
    -> [Next.js Functional Chat UI]
```

## Current Tech Stack

Backend:

- FastAPI
- SQLAlchemy async
- Alembic
- PostgreSQL 15 with pgvector
- Typer CLI
- httpx GitHub/OpenAI calls
- Pydantic settings

Retrieval and RAG:

- Custom Markdown cleaning and chunking
- Local deterministic hash embeddings for free development
- Optional OpenAI embeddings
- pgvector cosine similarity search
- Extractive answer fallback
- Basic prompt-injection-like chunk filtering

Frontend:

- Next.js
- React
- TailwindCSS
- lucide-react

DevOps:

- Docker Compose
- GitHub Actions
- Python 3.12 expected in CI
- Node 20 expected in CI

## Implemented API Surface

- `GET /api/health`
- `POST /api/ingest/github`
- `POST /api/query`
- `GET /api/sources`
- `PATCH /api/sources/{source_id}`
- `GET /api/queries`
- `PATCH /api/queries/{query_id}/feedback`
- `GET /api/analytics/summary`

## Database Model

Current logical tables:

- `documents`
- `document_chunks`
- `queries`
- `doc_sources`
- `alembic_version`

Important current behavior:

- `documents.source_url` is unique and is the current document identity.
- Documents can be linked to a `doc_sources` row.
- Re-ingesting an existing document updates the document and deletes/recreates its chunks.
- Chunks include `chunk_hash`, `chunk_metadata`, and a pgvector `embedding`.
- `doc_sources.source_config` tracks GitHub repository, branch, and path.
- Disabled linked sources are excluded from retrieval.
- Query logs include retrieved chunk ids, answer, feedback, latency, retrieved count, and creation time.

## Current Constraints

- Keep scope simple and personal-project friendly.
- Avoid multi-tenant architecture, auth, queues, and heavy orchestration until needed.
- Keep extractive answers as the default free mode.
- Treat external LLM generation as optional future work, not required MVP behavior.
- Prioritize backend integration and database correctness before frontend polish.
- Do not spend a design sprint until the real database path is validated.
- Update `README.md`, `SUMMARY.md`, and `NEXT_STEPS.md` whenever project state changes materially.

## Known Limitations

- Answer generation is extractive, not true LLM synthesis.
- `LLM_PROVIDER=openai` exists in config but there is no implemented OpenAI chat answer provider yet.
- Local hash embeddings are deterministic and free but weaker than semantic embeddings.
- OpenAI embedding calls now have retry/backoff and configurable timeout; batching is not yet implemented.
- Prompt-injection filtering is basic and heuristic.
- Retrieval quality needs real repository evaluation.
- No reranking.
- No scheduled sync.
- No streaming ingestion progress.
- No authentication.
- Deployment is not finalized.
- Frontend is functional but not yet a polished design system.

## Verification Status

Latest local check on 2026-07-03 (Pre-Opus Database Confidence sprint — COMPLETED):

- Environment: Python 3.12.13 via pyenv, Docker 29.6.1, Docker Compose v5.1.4.
- `python -m ruff check backend` — passed.
- `python -m pytest backend/tests` — 55/55 passed (Python 3.12.13, pinned deps).
- `alembic upgrade head` — 3 migrations applied cleanly.
- Ingest `tiangolo/fastapi` (5 files) — 5 documents, 82 chunks.
- Query "How do I run FastAPI locally?" — answer + 3 citations, 5 chunks, 42ms, query log persisted.
- Source disable filter — 0 chunks when disabled.
- `PYTHONPATH=. python scripts/verify_pipeline.py` — all 6 checks passed.

Note: `python3.12` is not the system default on this machine. Use `PYENV_VERSION=3.12.13 python3 -m venv .venv`.

Verification path:

```bash
PYENV_VERSION=3.12.13 python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python -m ruff check backend
python -m pytest backend/tests

# Full pipeline verification
docker compose up -d postgres
cd backend
alembic upgrade head
PYTHONPATH=. python scripts/verify_pipeline.py
```

## Next Milestone

Re-Ingestion and Retrieval Quality Review:

1. Confirm repeated ingestion of the same repo/path behaves predictably (no duplicate docs/chunks).
2. Add tests around repeated ingestion.
3. Review `RETRIEVAL_MIN_SCORE` behavior with local and semantic embeddings.
4. Inspect real retrieved chunk text quality; tune chunk size/overlap only if examples justify it.

## Roadmap

### Sprint 1: Database Confidence — COMPLETED (2026-07-03)

- Full local Postgres/pgvector validation completed.
- Observed commands, outputs, and results documented in SPRINT.md and SUMMARY.md.
- Repeatable verification script added: `backend/scripts/verify_pipeline.py`.

### Sprint 2: External Provider Hardening — COMPLETED (2026-07-03)

- Added retry/backoff for transient GitHub and OpenAI embedding failures via shared `request_with_retry` helper.
- Added connection timeout configuration (`HTTP_TIMEOUT_SECONDS`).
- Added 14 unit tests with mocked HTTP clients.
- Embedding batching deferred until real ingestion runs justify it.

### Sprint 3: Re-Ingestion And Retrieval Quality

- Test repeated ingestion of the same repo/path.
- Confirm document/source identity behavior is acceptable.
- Inspect real retrieved chunks and tune chunk size, overlap, or `RETRIEVAL_MIN_SCORE` only if examples justify it.

### Sprint 4: Optional LLM Provider

- Add an optional answer provider behind the existing extractive fallback.
- Keep extractive mode as the default local/free mode.
- Test prompt construction and citation preservation.

### Sprint 5: Functional Frontend Additions

- Add ingestion status.
- Add query history.
- Add source management controls.
- Add citation preview details.
- Add empty database guidance.

Visual redesign, motion, and detailed UI polish should remain postponed until backend validation is stable.

## Excluded Scope For Now

- Confluence, Notion, Slack, or wiki connectors.
- Fine-tuning embeddings.
- Multi-user auth.
- Multi-tenancy.
- Queues and distributed workers.
- Complex orchestration.
- Production-scale observability.

## Showcase Narrative

```text
Built an end-to-end RAG pipeline for documentation using FastAPI, PostgreSQL/pgvector, and Next.js. It ingests GitHub Markdown, chunks and embeds docs, retrieves relevant context, answers with citations, and tracks query quality through feedback and analytics.
```
