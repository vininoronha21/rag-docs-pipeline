# Next Steps

## Working Principles

- Preserve the small FastAPI monolith unless a real bottleneck justifies splitting services.
- Keep public API surface narrow: health, readiness, query, and feedback only.
- Keep administration Bearer-protected under `/api/admin/*`.
- Do not persist visitor question text, answer text, citation snapshots, IP addresses, user agents, or public history.
- Prefer evidence-driven retrieval changes over speculative tuning.
- Do not commit real deployment URLs, provider secrets, smoke questions from production logs, or response bodies.

## Completed In The Portfolio Release

- Versioned GitHub ingestion with `DocSource` and immutable `SourceVersion` commit snapshots.
- Same-commit ingestion no-op behavior.
- Active-version corpus counts and source enable/disable filtering.
- Hybrid retrieval using pgvector, PostgreSQL full-text search, and reciprocal-rank fusion.
- Anonymous `QueryEvent` telemetry with opaque UUID, state, timing, source IDs, source version IDs, score summaries, retrieved count, optional feedback, and timestamp.
- Public `/api/query` and `/api/query-events/{uuid}/feedback` with rate limits.
- Bearer-protected `/api/admin/ingest/github`, `/api/admin/sources`, `/api/admin/sources/{id}`, and `/api/admin/analytics/summary`.
- Public `/api/health` and `/api/ready` readiness checks.
- Citation-first Next.js frontend and protected admin shell.
- Evaluation dataset at `evaluation/pt-br/questions.jsonl`.
- Render, Vercel, and environment documentation with explicit async/sync database URL split.
- Post-deploy smoke script and manual workflow contract.

## Latest Release Evidence

- Backend broad suite from Task 5: `273 passed`, with one existing Starlette warning.
- Frontend from Task 4: 22 Vitest tests, typecheck, build, and `npm audit` passed after Next 16.2.11.
- Evaluation after Task 4: `answerable_top3=14/16`, `unsupported_refusals=4/4`, `answer_sentence_validation_failures=0`.
- Sprint 06 Task 5 verifier focus: `backend/scripts/verify_pipeline.py` now targets FastAPI PT-BR docs and validates source versions, active counts, no-op sync, anonymous events, commit-pinned citations, disabled-source exclusion, and restoration in `finally` blocks.

## Immediate Release Blockers

1. Provision deployed URLs.
   - Render backend URL and Vercel frontend URL are intentionally not committed.
   - Set Render `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `ALLOWED_ORIGINS`, and generated/secret `ADMIN_SECRET` in the provider dashboard.
   - Set Vercel `NEXT_PUBLIC_BACKEND_URL` to the Render backend URL.

2. Run post-deploy smoke.
   - Use placeholder-shaped commands only in docs.
   - Run `scripts/smoke.sh` with `FRONTEND_URL`, `BACKEND_URL`, `SMOKE_ANSWERABLE_QUESTION`, and `SMOKE_UNSUPPORTED_QUESTION` supplied from a secure local shell or GitHub environment secrets.

3. Retry Docker runtime verification.
   - Task 3 Docker runtime verification was blocked by Docker Hub metadata timeout.
   - Re-run when Docker Hub is reachable; do not treat the timeout as an application regression without a new reproduction.

## Verification Commands

Run from the repository root:

```bash
git diff --check
PYENV_VERSION=3.12.13 python -m ruff check backend
PYENV_VERSION=3.12.13 python -m pytest backend/tests/test_verify_pipeline.py
PYENV_VERSION=3.12.13 TEST_DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag_docs_test python -m pytest backend/tests
npm --prefix frontend run build
```

Local full-pipeline verifier:

```bash
docker compose up -d postgres
cd backend
PYENV_VERSION=3.12.13 python -m alembic upgrade head
PYENV_VERSION=3.12.13 PYTHONPATH=. python scripts/verify_pipeline.py
```

Post-deploy smoke template:

```bash
FRONTEND_URL=https://your-vercel-project.vercel.app \
BACKEND_URL=https://your-render-service.onrender.com \
SMOKE_ANSWERABLE_QUESTION='Como passo o path do arquivo `main.py` para `fastapi dev` ou a opção `--entrypoint main:app` para ele deduzir o objeto da aplicação?' \
SMOKE_UNSUPPORTED_QUESTION='Qual é a política de preços da FastAPI Cloud para planos Enterprise anuais?' \
scripts/smoke.sh
```

## Backlog After Release

- Add OpenAI embedding batching only if ingestion runs show it matters.
- Add an optional external LLM answer provider behind the extractive fallback.
- Add scheduled sync or a worker queue only after manual/admin ingestion becomes a real bottleneck.
- Add reranking if evaluation misses point to ranking rather than corpus/chunking issues.
- Extend source connectors beyond GitHub Markdown.
- Improve frontend visual design after the release contract is stable.
- Add production observability beyond current structured request logs if deployed use justifies it.

## Do Not Do Yet

- Do not make ingestion or source management public.
- Do not add public query history.
- Do not persist visitor content for debugging convenience.
- Do not introduce multi-tenancy, billing, or account systems for this portfolio release.
- Do not replace the extractive fallback until external LLM mode is implemented, tested, and optional.
