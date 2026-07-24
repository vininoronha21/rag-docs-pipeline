# RAG for Documentation - AI-Ready Data Pipeline

Portfolio RAG application for GitHub Markdown documentation. It ingests versioned FastAPI PT-BR docs, chunks and embeds them, stores vectors in PostgreSQL with pgvector, retrieves with hybrid vector/full-text search, and answers public questions with citation-first, commit-pinned evidence.

## Current Release

- Backend: FastAPI monolith with SQLAlchemy async, Alembic, PostgreSQL 15, pgvector, readiness checks, structured request logging, and in-memory rate limits.
- Ingestion: GitHub Markdown under admin-only `/api/admin/ingest/github`, tracked by `DocSource` and immutable `SourceVersion` rows keyed by repository, branch, path, and commit SHA.
- Retrieval: hybrid pgvector cosine search plus PostgreSQL full-text search, fused with reciprocal-rank fusion and filtered by enabled source/version and score thresholds.
- Answers: local extractive fallback by default, citation-first response shape, prompt-injection-like chunk filtering, unsupported-question refusal via `state="insufficient_evidence"`.
- Privacy: anonymous `query_events` only. The app does not persist visitor question text, answer text, citation snapshots, IP addresses, user agents, or public query history.
- Frontend: Next.js 16.2.11 citation-first chat and protected admin shell. Latest recorded frontend checks from Task 4 passed typecheck, build, and 22 Vitest tests with `npm audit` clean.
- Deployment: Render backend manifest, Vercel frontend manifest, Neon-compatible async/sync database URL split, and `scripts/smoke.sh` for post-deploy smoke checks.

## Public And Admin API

Public endpoints:

- `GET /api/health`
- `GET /api/ready`
- `POST /api/query`
- `PATCH /api/query-events/{uuid}/feedback`

Bearer-protected admin endpoints:

- `POST /api/admin/ingest/github`
- `GET /api/admin/sources`
- `PATCH /api/admin/sources/{id}`
- `GET /api/admin/analytics/summary`

There is no public ingestion endpoint, public source-management endpoint, or public query-history endpoint in the current release.

## Local Demo

Start PostgreSQL, install backend dependencies, migrate, and ingest the release corpus:

```bash
cp .env.example .env
docker compose up -d postgres
PYENV_VERSION=3.12.13 python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
python -m alembic upgrade head
PYTHONPATH=. python -m app.cli ingest-github \
  https://github.com/fastapi/fastapi \
  docs/pt/docs \
  --branch master \
  --max-files 500
PYTHONPATH=. python scripts/verify_pipeline.py
```

Run the backend and frontend locally:

```bash
# terminal 1
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload

# terminal 2
npm --prefix frontend install
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000 npm --prefix frontend run dev
```

Open:

- Frontend: `http://localhost:3000`
- Source management: `http://localhost:3000/admin` using local secret `local-admin-secret`
- Backend health: `http://localhost:8000/api/health`
- Backend readiness: `http://localhost:8000/api/ready`
- API docs: `http://localhost:8000/docs`

Local workflow:

1. Open `http://localhost:3000/admin`.
2. Unlock with `local-admin-secret`.
3. Register a GitHub repository URL, branch, and Markdown folder path.
4. Return to `http://localhost:3000` and query the synchronized documentation.

The public home only queries enabled sources that are already indexed. Repository registration is intentionally protected by `ADMIN_SECRET` because it triggers network requests, database writes, and embedding/indexing work.

## API Examples

Admin ingestion requires `Authorization: Bearer <ADMIN_SECRET>`:

```bash
curl -X POST http://localhost:8000/api/admin/ingest/github \
  -H "Authorization: Bearer $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/fastapi/fastapi","branch":"master","path":"docs/pt/docs","max_files":500}'
```

Public query:

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Como passo o path do arquivo `main.py` para `fastapi dev` ou a opção `--entrypoint main:app` para ele deduzir o objeto da aplicação?","top_k":5,"source":"github"}'
```

Public feedback on the returned opaque event UUID:

```bash
curl -X PATCH http://localhost:8000/api/query-events/<event_uuid>/feedback \
  -H "Content-Type: application/json" \
  -d '{"feedback":1}'
```

Protected source list:

```bash
curl http://localhost:8000/api/admin/sources \
  -H "Authorization: Bearer $ADMIN_SECRET"
```

## Configuration

Environment variables are documented in `.env.example` and `docs/environment.md`.

Default local mode:

```bash
EMBEDDING_PROVIDER=local
LLM_PROVIDER=extractive
RETRIEVAL_MIN_SCORE=0.0
RETRIEVAL_MIN_FUSED_SCORE=0.0
RETRIEVAL_MIN_SCORE_GAP=0.0
```

Production requires explicit runtime and migration URLs with different SQLAlchemy drivers:

```bash
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>/<database>?ssl=require
MIGRATION_DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>/<database>?sslmode=require
```

OpenAI embeddings are optional:

```bash
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=<set-in-provider-dashboard>
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

`LLM_PROVIDER=openai` and `OPENAI_CHAT_MODEL` exist in settings, but external LLM synthesis is not implemented yet. Extractive mode remains the safe default.

## Verification

Use these checks from the repository root:

```bash
git diff --check
PYENV_VERSION=3.12.13 python -m ruff check backend
PYENV_VERSION=3.12.13 python -m pytest backend/tests/test_verify_pipeline.py
PYENV_VERSION=3.12.13 TEST_DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag_docs_test python -m pytest backend/tests
npm --prefix frontend run build
```

Latest recorded release evidence after this docs refresh:

- Backend broad suite from Task 5: `273 passed`, with one existing Starlette warning.
- Frontend from Task 4: 22 Vitest tests, typecheck, build, and `npm audit` passed after Next 16.2.11.
- Evaluation gate after Task 4: `answerable_top3=14/16`, `unsupported_refusals=4/4`, `answer_sentence_validation_failures=0` on `evaluation/pt-br/questions.jsonl`.
- Alembic: six migration files are present under `backend/alembic/versions`.

`backend/scripts/verify_pipeline.py` now validates the PT-BR FastAPI source (`https://github.com/fastapi/fastapi`, branch `master`, path `docs/pt/docs`), `SourceVersion` integrity, active corpus counts, same-commit no-op sync, answered citations with commit-pinned GitHub URLs, anonymous query-event schema, disabled-source exclusion, and source restoration in `finally` blocks.

## Deployed Demo

Do not commit deployed URLs or secrets. Configure provider environment values before deploying.

Render backend:

```bash
# render.yaml defines the web service, Dockerfile, health check, and generated ADMIN_SECRET.
# Set DATABASE_URL, MIGRATION_DATABASE_URL, ADMIN_SECRET, and ALLOWED_ORIGINS in Render.
```

Vercel frontend:

```bash
# frontend/vercel.json defines the Next.js build.
# Set NEXT_PUBLIC_BACKEND_URL in the Vercel project environment before building.
# Use the Render backend origin, for example https://<backend-service>.onrender.com.
```

Post-deploy smoke:

```bash
FRONTEND_URL='<frontend-origin>' \
BACKEND_URL='<backend-origin>' \
SMOKE_ANSWERABLE_QUESTION='<answerable-smoke-question>' \
SMOKE_UNSUPPORTED_QUESTION='<unsupported-smoke-question>' \
scripts/smoke.sh
```

## Release Blockers

- Live deployed smoke is still pending real `FRONTEND_URL` and `BACKEND_URL` values.
- Docker runtime verification from Task 3 was blocked by Docker Hub metadata timeout; retry when Docker Hub is reachable.
- OpenAI embedding batching and external LLM synthesis are intentionally deferred.
