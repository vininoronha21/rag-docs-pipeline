# RAG for Documentation — AI-Ready Data Pipeline

A personal, portfolio-oriented RAG pipeline that indexes GitHub Markdown documentation, stores chunks and embeddings in PostgreSQL with pgvector, and answers natural-language questions with cited retrieved context.

## Current Project Priorities

- Keep the scope simple and practical because this is a personal project.
- Focus first on backend infrastructure, database integration, and test validation.
- Keep frontend work limited to functionality and integration for now.
- Postpone visual design decisions until the dedicated system design sprint.

## Current Progress

- Current branch: `dev`.
- Latest local commit observed: `1def05a docs: record Database Confidence sprint results and add verify_pipeline.py`.
- **Pre-Opus Database Confidence sprint completed on 2026-07-03.**
- Full local RAG loop validated: ingest → persist → retrieve → query → citations → query log.
- Backend lint (ruff) passes.
- All 55 backend tests pass under Python 3.12.13 with pinned dependencies.
- Alembic migrations applied cleanly (3 new migrations applied).
- 5 documents and 82 chunks ingested from `tiangolo/fastapi`.
- Query returned an answer with citations and logged 5 chunks in 42ms.
- Source disable filter confirmed: disabled source returns 0 chunks.
- Repeatable verification script added: `backend/scripts/verify_pipeline.py`.

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
PYENV_VERSION=3.12.13 python3 -m venv .venv   # use pyenv if python3.12 is not default
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
# Toolchain check
source .venv/bin/activate
python -m ruff check backend
python -m pytest backend/tests

# Full pipeline integration verification
docker compose up -d postgres
cd backend
alembic upgrade head
PYTHONPATH=. python scripts/verify_pipeline.py
```

`verify_pipeline.py` validates the complete loop: database connectivity, pgvector, table existence, ingest (5 files from `tiangolo/fastapi`), persistence counts, query with citations, and source disable behavior. All steps use local embeddings — no paid API key required.

Latest local verification on 2026-07-03 (Pre-Opus Database Confidence sprint):

- Environment: Python 3.12.13 via pyenv, Docker 29.6.1 with Docker Compose v5.1.4.
- Database: Docker Compose `pgvector/pgvector:pg15`, Option A.
- `python -m ruff check backend` → **passed**.
- `python -m pytest backend/tests` → **55/55 passed** (Python 3.12.13, pinned deps).
- `alembic upgrade head` → **3 migrations applied** cleanly.
- Ingest: **5 documents, 82 chunks** from `tiangolo/fastapi`.
- Query: answer with citations, **5 chunks retrieved in 42ms**, query log persisted.
- Source disable: **0 chunks returned** when source is disabled.
- `PYTHONPATH=. python scripts/verify_pipeline.py` → **all 6 checks passed**.

Expected backend environment:

```bash
PYENV_VERSION=3.12.13 python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python -m pytest backend/tests
```
