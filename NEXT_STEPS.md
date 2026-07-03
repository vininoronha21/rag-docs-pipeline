# Next Steps

## Working Principles

- Keep the project simple and practical.
- Backend first: database, integration, retrieval correctness, and tests.
- Frontend work stays functional until the design sprint.
- Avoid visual redesign, animations, and UI polish for now.
- Prefer small, verified increments.
- Update `README.md`, `SUMMARY.md`, and `NEXT_STEPS.md` when project direction or progress changes.
- For each code change, provide a suggested commit message and a short explanation.

## Immediate Priority

The next milestone is to prove the full backend loop against the real local database. Before that, use a clean supported toolchain because the latest local audit found environment-specific failures in the global Python 3.13/sandbox setup.

Recommended local toolchain:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python -m ruff check backend
python -m pytest backend/tests
```

Latest local audit on 2026-07-03:

- `python3 -m ruff check backend` passed.
- `python3 -m pytest backend/tests` failed during collection because global Python 3.13 loaded incompatible Starlette 1.3.1 with FastAPI 0.111.1.
- `cd frontend && npm run build` failed in the restricted sandbox with a Turbopack port-binding permission error.

Core validation steps:

1. Start Postgres/pgvector with Docker.
2. Run Alembic migrations.
3. Ingest a real GitHub repository.
4. Confirm documents, chunks, sources, and embeddings are persisted.
5. Query the indexed repository.
6. Inspect citations and retrieved chunk quality.
7. Convert the most important parts of that flow into repeatable tests or a lightweight verification script.

This should happen before investing in frontend design or deployment.

## Current Recommended Order

### 1. Clean Environment Verification

- Create or refresh a Python 3.12 virtualenv.
- Install `backend/requirements.txt` into that virtualenv.
- Run backend ruff and tests from the virtualenv.
- Retry frontend `npm run build` locally or in CI where Turbopack can create its worker process.

Acceptance criteria:

- Backend lint passes.
- Backend tests pass under Python 3.12 with pinned dependencies.
- Frontend build result is known outside the restricted sandbox.

### 2. Database Integration Validation

- Start `postgres` through Docker Compose.
- Run `alembic upgrade head`.
- Confirm the schema has `documents`, `document_chunks`, `queries`, and `doc_sources`.
- Ingest a small real repo with a low `max_files` value.
- Query the repo and verify citations point to stored chunks.
- Check that disabled document sources are excluded from retrieval.

Acceptance criteria:

- A real repository can be ingested without manual database fixes.
- Query returns a logged answer with citations.
- Query logs include latency and retrieved chunk count.
- Source disabling affects retrieval as expected.

### 3. Integration Test Or Verification Script

- Add a focused integration test or script for ingest -> persist -> retrieve -> query.
- Keep it lightweight and local-project friendly.
- Avoid heavy fixture systems unless needed.
- Prefer explicit setup/teardown over a large testing framework.

Acceptance criteria:

- The project has a repeatable command that validates the core RAG database loop.
- The command is documented in `README.md`.

### 4. Repository Sync And Deduplication Review

Current state:

- Documents are upserted by `source_url`.
- Chunks have content hashes.
- Existing chunks are deleted and recreated on document update.
- Document sources track repo, branch, path, last sync, and enabled state.

Next improvements:

- Review whether `source_url` is enough as the document identity.
- Decide whether SHA/path-based identity is needed.
- Confirm repeated ingestion does not create duplicate documents or bad source records.
- Add tests around repeated ingestion of the same repository/path.

Acceptance criteria:

- Re-ingesting the same source behaves predictably.
- Docs explain the current identity/deduplication behavior.

### 5. Retrieval Quality Pass

- Test with at least one real documentation repo.
- Inspect retrieved chunk text and citation quality.
- Tune chunk size and overlap only if real examples justify it.
- Review `RETRIEVAL_MIN_SCORE` behavior with local embeddings.
- Keep reranking postponed unless retrieval quality clearly needs it.

Acceptance criteria:

- The app answers basic questions from indexed docs with relevant citations.
- Weak or unrelated retrieval returns the fallback message more often than misleading answers.

### 6. External Provider Hardening

Already done:

- Embedding provider failures are wrapped.
- Malformed embedding payloads are rejected.
- Invalid vector dimensions are rejected.
- Missing OpenAI key configuration returns a clear error.
- Malformed GitHub responses return clear 502 errors.

Still useful:

- Add simple retry/backoff for GitHub and OpenAI transient failures.
- Add embedding batching if real ingestion runs show it is needed.
- Document OpenAI embedding setup clearly.

Acceptance criteria:

- Transient external failures are less disruptive.
- Configuration errors remain clear.
- No complex provider abstraction is added before needed.

### 7. LLM Answer Provider

Current state:

- Answer generation is extractive.
- This is safe, simple, and good for MVP stability.
- `LLM_PROVIDER=openai` and `OPENAI_CHAT_MODEL` are present in settings but are not wired into answer generation yet.

Future step:

- Add an optional LLM answer provider behind the existing extractive fallback.
- Keep extractive mode as the default local/free mode.
- Add prompt-injection safeguards before sending retrieved content to an external LLM.

Acceptance criteria:

- The app still works with no paid key.
- External LLM mode is opt-in.
- Prompt construction is tested.
- The answer still returns citations.

### 8. Frontend Functionality Before Design

Do now only if backend validation is stable:

- Show better ingestion status.
- Add query history view.
- Add source management controls.
- Add citation preview details.
- Add empty indexed-database guidance.

Do later in design sprint:

- Visual redesign.
- Dark mode direction.
- Motion/animation work.
- Detailed layout polish.

Acceptance criteria:

- Frontend additions expose backend functionality without changing the visual direction too much.

### 9. Deployment Preparation

Do after backend validation:

- Document production environment variables.
- Add notes for managed Postgres/pgvector options.
- Add Render/Railway backend deployment notes.
- Add Vercel frontend deployment notes.
- Add CI checks for backend tests and lint.
- Consider Docker build checks.

Acceptance criteria:

- A clean README path exists for local setup and deployment setup.
- CI validates the important backend path before deployment.

## Backlog

### Backend

- Full ingest -> database -> retrieval integration test.
- Re-ingestion behavior tests.
- Retry/backoff for GitHub and embedding providers.
- Optional embedding batching.
- Optional LLM answer provider.
- Stronger prompt-injection protections.
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

## Next Best Task

First, verify the clean Python environment. Then run and document a real local database validation:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python -m ruff check backend
python -m pytest backend/tests
docker compose up -d postgres
cd backend
alembic upgrade head
python -m app.cli ingest-github https://github.com/tiangolo/fastapi --max-files 5
python -m app.cli query "How do I run FastAPI locally?" --source github
```

Then record the result in `README.md` and update this file with any issue found.
