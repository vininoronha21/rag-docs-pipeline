# Project Summary

## Project

`rag-docs-pipeline` is a personal, portfolio-oriented RAG application for documentation. It indexes Markdown documentation from GitHub repositories, stores chunks and embeddings in PostgreSQL with pgvector, and answers questions with cited retrieved context.

The project is intentionally scoped as a practical MVP, not a large-scale platform. The current priority is backend stability, database integration, and test validation. Frontend visual design is postponed until a later dedicated system design sprint.

## Current Moment

The project has completed the **Pre-Opus Database Confidence sprint on 2026-07-03**. The full local RAG loop has been validated against a real PostgreSQL/pgvector instance.

Current branch: `dev`. Latest local commit observed: `1def05a docs: record Database Confidence sprint results and add verify_pipeline.py`.

Completed:

- Sprint 1 foundation is effectively complete: Docker, Postgres/pgvector, GitHub Markdown ingestion, cleaning, chunking, and tests exist.
- Sprint 2 MVP backend is mostly complete: embeddings, vector persistence, retrieval, query API, citations, query logging, and feedback are implemented.
- Sprint 3 has a functional frontend shell, but visual design is intentionally not the priority yet.
- **Pre-Opus Database Confidence sprint**: full local loop validated, 55/55 tests pass, repeatable verification script added.

Current focus:

- Backend database confidence is now validated.
- Ready for Opus External Provider Hardening Review.

## Sprint Validation Results (2026-07-03)

### Environment

- Python 3.12.13 via pyenv (`PYENV_VERSION=3.12.13`)
- Docker 29.6.1, Docker Compose v5.1.4
- Database: Docker Compose `pgvector/pgvector:pg15` (Option A)

### What Passed

| Check | Result |
|---|---|
| `python -m ruff check backend` | Passed |
| `python -m pytest backend/tests` (55 tests, Python 3.12.13) | All passed |
| `alembic upgrade head` | 3 migrations applied cleanly |
| Tables: `documents`, `document_chunks`, `doc_sources`, `queries`, `alembic_version` | All exist |
| Ingest `tiangolo/fastapi` (max 5 files) | 5 docs, 82 chunks |
| Query: "How do I run FastAPI locally?" | Answer + 3 citations, 5 chunks, 42ms, query_id persisted |
| Source disable filter | 0 chunks returned when source disabled |
| `PYTHONPATH=. python scripts/verify_pipeline.py` | All 6 checks passed |

### What Failed Or Was Not Tested

- Frontend build: not retried in this sprint (sandbox restriction from previous audit). Should be retried locally or in CI.
- No real Turbopack issue is expected outside a restricted sandbox environment.

### Workarounds

- `python3.12` is not the system default; use `PYENV_VERSION=3.12.13 python3 -m venv .venv`.
- The verification script requires `PYTHONPATH=.` when run from the `backend/` directory.

## Project Requirements And Constraints

- Keep the project simple, focused, and personal-project friendly.
- Avoid over-engineering, premature scale patterns, complex abstractions, and large platform features.
- Prioritize backend infrastructure, database correctness, integration reliability, and tests.
- Keep frontend work functional and integration-focused for now.
- Postpone visual design, animations, and detailed UI polish until the dedicated design sprint.
- Keep `README.md` updated as progress changes.
- For each implementation, provide a suggested commit message and a short friendly explanation.
- Prefer incremental changes with clear verification.
- Do not revert user or automation changes unless explicitly requested.

## Implemented System

### Backend

- FastAPI application with API prefix configuration.
- Pydantic settings loaded from environment variables.
- PostgreSQL + pgvector database integration through SQLAlchemy async.
- Alembic migrations for the current schema.
- Dockerfile and Docker Compose support.
- GitHub Markdown ingestion endpoint.
- GitHub client with redirect support and explicit upstream error handling.
- Markdown cleaning and title extraction.
- Heading-aware Markdown chunking.
- Chunk deduplication using normalized content hashes.
- Local deterministic hash embeddings for zero-cost development.
- Optional OpenAI embeddings through environment configuration.
- Embedding provider validation for dimensions, malformed payloads, non-numeric vectors, count mismatches, upstream errors, and missing API key configuration.
- pgvector retrieval with source filtering.
- Disabled linked document sources are excluded from retrieval.
- Shared query workflow used by API and CLI.
- Query validation shared across API, CLI, and backend service.
- Prompt-injection-like retrieved chunks are filtered before answer generation.
- Extractive answer generation with citations.
- `LLM_PROVIDER=openai` exists as configuration, but no OpenAI chat answer provider is implemented yet.
- Query logging with latency and retrieved chunk count.
- Query feedback endpoint.
- Query history endpoint.
- Document source list and enable/disable endpoints.
- Analytics summary endpoint.
- Repeatable verification script: `backend/scripts/verify_pipeline.py`.

### API Surface

- `GET /api/health`
- `POST /api/ingest/github`
- `POST /api/query`
- `GET /api/sources`
- `PATCH /api/sources/{source_id}`
- `GET /api/queries`
- `PATCH /api/queries/{query_id}/feedback`
- `GET /api/analytics/summary`

### CLI

- `python -m app.cli ingest-github ...`
- `python -m app.cli query ...`
- CLI query flow uses the same backend query service as the API.
- CLI query validates `top_k` and invalid query input consistently.

### Database

Current logical tables:

- `documents`
- `document_chunks`
- `queries`
- `doc_sources`
- `alembic_version`

Current data model includes:

- Documents linked to optional document sources.
- Chunks with vector embeddings, metadata, and content hash.
- Query logs with retrieved chunk ids, answer, latency, retrieved count, and feedback.
- Document sources with source config, last sync, and enabled/disabled state.

### Frontend

- Next.js frontend exists and is functional.
- Repository indexing form exists.
- Chat flow exists.
- Citations display exists.
- Answer feedback controls exist.
- Frontend is intentionally still visually simple.

## Tests And Validation

```bash
# From project root, with .venv activated
python -m ruff check backend
python -m pytest backend/tests

# Full pipeline verification (requires Docker Postgres running)
cd backend
PYTHONPATH=. python scripts/verify_pipeline.py
```

Latest local validation on 2026-07-03 (Pre-Opus sprint):

- Ruff passed.
- All 55 backend tests passed under Python 3.12.13 with pinned dependencies.
- Alembic migrations applied cleanly (3 new).
- Ingest: 5 documents, 82 chunks from `tiangolo/fastapi`.
- Query: answer with citations, 5 chunks retrieved, 42ms latency.
- Source disable: 0 chunks retrieved when source disabled.
- `verify_pipeline.py`: all 6 checks passed.

Test coverage currently includes:

- Analytics summary.
- Chunking and chunk hashing.
- CLI query flow.
- Settings validation.
- Document sources.
- Embedding providers and embedding error handling.
- Query feedback.
- GitHub client malformed response handling.
- Ingestion error mapping.
- Markdown cleanup.
- Pipeline source linking.
- Query history.
- Query metrics.
- Query route behavior.
- Shared query service behavior.
- RAG filtering and extractive answer generation.
- Repository persistence.
- Retrieval source filtering.

## Current Known Limitations

- Answer generation is still extractive, not LLM-generated.
- The configured OpenAI chat model is not used yet because an LLM answer provider has not been implemented.
- Local hash embeddings are useful for free local development but are not semantically strong.
- OpenAI embeddings are available, but production-grade provider retry/backoff and batching still need work.
- There is no real LLM answer provider behind the extractive fallback yet.
- Prompt-injection filtering is basic and heuristic.
- Retrieval quality still needs real repository evaluation.
- No reranking yet.
- No streaming ingestion progress.
- No scheduled sync.
- No authentication.
- No deployment configuration is finalized.
- Frontend does not yet include the planned polished design system.

## Project Review

The project is in a healthy, validated MVP state. The core backend loop has been confirmed against a real PostgreSQL/pgvector database: ingest documentation, clean it, chunk it, embed it, persist it, retrieve relevant chunks, answer with citations, log the query, and collect feedback. Source disable filtering is working correctly.

The strongest part of the project right now is the backend foundation, incremental test coverage, and confirmed real database loop. The verification script provides a repeatable path to re-confirm the full loop.

The next technical milestone is External Provider Hardening: retry/backoff for transient GitHub and OpenAI embedding failures, and proposed unit tests with mocks.

## Current Git/Docs Notes

- Current working branch: `dev`.
- Latest local commit observed: `1def05a docs: record Database Confidence sprint results and add verify_pipeline.py`.
- `README.md`, `SUMMARY.md`, `NEXT_STEPS.md`, and `SPRINT.md` are root-level project docs.
- Keep these docs updated as part of each meaningful implementation step.

## Suggested Commit For This Update

```text
docs: record Pre-Opus Database Confidence sprint results and add verify_pipeline.py
```

Short explanation: updates project docs with sprint validation results, Python environment, confirmed DB loop, verification script, and next recommended Opus sprint.
