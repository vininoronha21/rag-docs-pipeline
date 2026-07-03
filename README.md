# RAG for Documentation — AI-Ready Data Pipeline
This repository provides a complete example of a Retrieval-Augmented Generation (RAG) pipeline for documentation. It includes:

## Current Project Priorities

- Keep the scope simple and practical because this is a personal project.
- Focus first on backend infrastructure, database integration, and test validation.
- Keep frontend work limited to functionality and integration for now.
- Postpone visual design decisions until the dedicated system design sprint.

## Current Progress

- Current branch: `dev`.
- Latest local commit observed: `7458b2f fix: share query input validation`.
- Backend tests now cover the ingestion orchestration path from GitHub Markdown cleanup through chunking, embedding calls, and persistence payloads.
- Query route tests validate retrieval, relevance filtering, prompt-injection filtering, answer generation, query logging, and response metadata.
- CLI queries now use the same backend retrieval safeguards as the API and persist query metrics.
- API and CLI queries now share one backend query service to keep retrieval, filtering, and logging behavior consistent.
- Repository persistence now validates chunk and embedding counts before database writes and has focused document/chunk upsert tests.
- Document source management, query history, feedback, and analytics endpoints are implemented.
- External embedding failures now return clear 502 API responses instead of being confused with GitHub errors.
- Malformed embedding provider responses are now wrapped as explicit provider errors.
- Embedding providers now validate configured and returned vector dimensions before persistence.
- OpenAI embedding responses now reject non-numeric vector payloads before storage.
- Settings now validate embedding dimensions at startup before providers or pgvector use them.
- API embedding dependencies now return a clear server configuration error when OpenAI embeddings are enabled without the required key.
- GitHub ingestion now wraps malformed upstream responses as clear 502 API errors.
- Query validation is now shared by the API, CLI, and backend query service.
- Frontend has a functional indexing/chat shell with citations and feedback controls, but visual design remains intentionally simple.
- Project handoff docs now summarize the current state, requirements, review, and next backend-first priorities.

## Stack

- Backend: FastAPI, SQLAlchemy, Alembic, PostgreSQL + pgvector
- Pipeline: GitHub Markdown ingestion, Markdown cleaning, semantic chunking, embeddings, vector retrieval
- Embeddings: local deterministic hash embeddings by default; OpenAI embeddings can be enabled by env vars
- Frontend: Next.js, React, TailwindCSS
- Infra: Docker Compose, GitHub Actions CI

## Quick Start With Docker

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/api/health
- API docs: http://localhost:8000/docs

The backend container runs Alembic migrations on startup. The default embedding provider is local and deterministic, so no paid API key is required.

## Local Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
docker compose up -d postgres
cd backend
alembic upgrade head
uvicorn app.main:app --reload
```

Useful CLI commands:

```bash
cd backend
python -m app.cli ingest-github https://github.com/tiangolo/fastapi --max-files 25
python -m app.cli query "How do I run FastAPI locally?" --source github
```

## Local Frontend

```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000` when the backend is not running on the default URL.

## API Flow

1. `POST /api/ingest/github` indexes Markdown files from a GitHub repository.
2. The backend cleans Markdown, chunks by headings and size, creates embeddings, and stores chunks in pgvector.
3. `POST /api/query` embeds the question, retrieves top-k chunks by cosine distance, filters unsafe instruction-override text, and returns an extractive answer with citations and query metrics.
4. `GET /api/sources` returns indexed document sources and their last sync time.
5. `PATCH /api/sources/{source_id}` enables or disables an indexed source. Disabled linked sources are excluded from retrieval.
6. `GET /api/analytics/summary` returns aggregate document, chunk, source, query, latency, and feedback metrics.
7. `GET /api/queries` returns paginated query history with answers, citation ids, feedback, latency, retrieval counts, and timestamps.

Example ingestion request:

```bash
curl -X POST http://localhost:8000/api/ingest/github \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/tiangolo/fastapi","max_files":25}'
```

Example query request:

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"How do I run FastAPI locally?","top_k":5}'
```

Example query history request:

```bash
curl "http://localhost:8000/api/queries?limit=20&offset=0"
```

Example source list request:

```bash
curl http://localhost:8000/api/sources
```

Example source update request:

```bash
curl -X PATCH http://localhost:8000/api/sources/1 \
  -H "Content-Type: application/json" \
  -d '{"enabled":false}'
```

Example analytics summary request:

```bash
curl http://localhost:8000/api/analytics/summary
```

## Configuration

Environment variables are documented in `.env.example`.

Default local mode:

```bash
EMBEDDING_PROVIDER=local
LLM_PROVIDER=extractive
RETRIEVAL_MIN_SCORE=0.0
```

`RETRIEVAL_MIN_SCORE` filters weak vector matches before answer generation. Increase it when the app should prefer saying no indexed documentation matched over answering from low-similarity chunks.

OpenAI embeddings:

```bash
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

Keep `EMBEDDING_DIMENSIONS=1536` unless you also create a matching Alembic migration for the `document_chunks.embedding` vector column.

## Verification

```bash
python3 -m pytest backend/tests
python3 -m ruff check backend
cd frontend && npm run build
```

Latest local verification on 2026-07-03:

- `python3 -m ruff check backend` passed.
- `python3 -m pytest backend/tests` did not run cleanly in the global Python 3.13 environment because FastAPI 0.111.1 imported incompatible global Starlette 1.3.1. Use a clean Python 3.12 virtualenv and `pip install -r backend/requirements.txt`.
- `cd frontend && npm run build` failed in the sandbox with a Turbopack port-binding permission error while processing `app/globals.css`; this looks environment/sandbox related and should be retried locally or in CI.

Expected backend environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python -m pytest backend/tests
```
