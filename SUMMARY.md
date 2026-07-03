# Project Summary

## Project

`rag-docs-pipeline` is a personal, portfolio-oriented RAG application for documentation. It indexes Markdown documentation from GitHub repositories, stores chunks and embeddings in PostgreSQL with pgvector, and answers questions with cited retrieved context.

The project is intentionally scoped as a practical MVP, not a large-scale platform. The current priority is backend stability, database integration, and test validation. Frontend visual design is postponed until a later dedicated system design sprint.

## Current Moment

The project is in backend stabilization after the MVP foundation. The current branch is `dev`; latest local commit observed is `7458b2f fix: share query input validation`.

Completed:

- Sprint 1 foundation is effectively complete: Docker, Postgres/pgvector, GitHub Markdown ingestion, cleaning, chunking, and tests exist.
- Sprint 2 MVP backend is mostly complete: embeddings, vector persistence, retrieval, query API, citations, query logging, and feedback are implemented.
- Sprint 3 has a functional frontend shell, but visual design is intentionally not the priority yet.

Current focus:

- Keep hardening backend behavior.
- Keep tests passing.
- Validate real database flows.
- Avoid spending time on visual polish until backend confidence is higher.

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

## Recent Backend Hardening

- API and CLI query behavior now share one backend query workflow.
- Query validation is shared by the API, CLI, and backend query service.
- Repository persistence validates chunk and embedding counts before writes.
- Embedding providers validate configured and returned vector dimensions.
- OpenAI embedding responses reject malformed, non-numeric, wrong-sized, or wrong-count vectors.
- Missing OpenAI API key configuration is returned as a clear server configuration error.
- External embedding failures return clear 502 API responses.
- GitHub HTTP errors are mapped to clearer API responses.
- Malformed GitHub upstream responses are wrapped as clear 502 API errors.
- Settings validate embedding dimensions at startup.

## Tests And Validation

Expected validation:

```bash
python3 -m ruff check backend
python3 -m pytest backend/tests
cd frontend && npm run build
```

Latest local validation on 2026-07-03:

- Ruff passed.
- Backend tests failed during collection in the global Python 3.13 environment because FastAPI 0.111.1 imported incompatible global Starlette 1.3.1.
- Frontend build failed in the sandbox with a Turbopack port-binding permission error while processing `app/globals.css`.

Interpretation:

- The backend test failure appears to be an environment dependency issue, not a direct application-code failure. CI uses Python 3.12 and installs from `backend/requirements.txt`.
- Re-run backend tests in a clean Python 3.12 virtualenv before treating the current failure as a product regression.
- Re-run the frontend build outside the restricted sandbox or in CI before treating the Turbopack failure as a frontend regression.

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

The project is in a healthy MVP state. The core backend loop exists: ingest documentation, clean it, chunk it, embed it, persist it, retrieve relevant chunks, answer with citations, log the query, and collect feedback.

The strongest part of the project right now is the backend foundation and incremental test coverage. Recent work has reduced several failure modes around external providers and inconsistent query handling.

The main risk is that the system has more unit-level confidence than real end-to-end database confidence. The next technical milestone should be a focused integration validation path against Postgres/pgvector: ingest a real repository, confirm persisted documents/chunks/sources, query it, inspect citations, and assert the behavior in tests where practical.

The project should not move deeply into visual polish or deployment before the real database ingestion/query path is validated again.

## Current Git/Docs Notes

- Current working branch: `dev`.
- Latest local commit observed: `7458b2f fix: share query input validation`.
- `README.md`, `SUMMARY.md`, and `NEXT_STEPS.md` are currently root-level project docs and may be untracked depending on git state.
- All root `.md` files were untracked in the current local git status when this audit started.
- Keep these docs updated as part of each meaningful implementation step.

## Suggested Next Commit For This Documentation Update

```text
docs: refresh project summary and next steps
```

Short explanation: updates the project handoff docs with the current backend state, constraints, completed work, limitations, and next priorities.
