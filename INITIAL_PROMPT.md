# Opus Handoff Prompt

Use this prompt when starting a new Opus chat for this project.

```text
You are helping me continue a personal portfolio project named `rag-docs-pipeline`.

First read the attached Markdown files in this order:

1. SUMMARY.md
2. NEXT_STEPS.md
3. README.md
4. PLAN.md
5. AGENTS.md

Project constraints:

- Keep the scope simple and practical.
- Work backend-first: database correctness, retrieval quality, integration reliability, and tests come before visual polish.
- Avoid over-engineering, multi-tenancy, auth, queues, or heavy orchestration unless the code proves they are needed.
- Keep extractive answers as the default free/local mode.
- Treat external LLM synthesis as optional future work.
- Do not redesign the frontend yet; keep frontend work functional and integration-focused.
- Prefer small, verified increments.
- Do not revert existing user or automation changes unless explicitly requested.
- When making code changes, also update the relevant docs if project state changes.
- For each implementation, provide a suggested commit message and a short explanation.

Current project state:

- Backend MVP is mostly implemented: GitHub Markdown ingestion, cleanup, chunking, local/OpenAI embeddings, pgvector persistence, retrieval, extractive answers with citations, query logging, feedback, history, source management, and analytics.
- Frontend exists as a simple functional Next.js shell for indexing, chat, citations, and feedback.
- Current focus is backend stabilization and real local Postgres/pgvector validation.
- Latest local audit found environment-specific verification issues: ruff passed, pytest failed in global Python 3.13 because of incompatible global Starlette, and frontend build failed in a restricted sandbox with a Turbopack port-binding error. Re-test in a clean Python 3.12 virtualenv and normal local/CI frontend environment before treating those as product regressions.

Your first task:

1. Check git status.
2. Use a clean Python 3.12 environment if running backend tests.
3. Continue from NEXT_STEPS.md.
4. Prioritize validating the real local database loop:
   - docker compose up -d postgres
   - alembic upgrade head
   - ingest a small real GitHub repo
   - query it
   - inspect persisted documents/chunks/sources/citations
   - document the result

If you understand the project and constraints, briefly summarize the current state and propose the next concrete action before editing files.
```

## Required Markdown Attachments

Attach these `.md` files to give Opus a complete understanding of the project, requirements, limitations, checkpoints, and next sprint:

1. `SUMMARY.md`
2. `NEXT_STEPS.md`
3. `README.md`
4. `PLAN.md`
5. `AGENTS.md`

## Optional Markdown Attachment

Attach this only if you want Opus to see the original handoff prompt too:

1. `INITIAL_PROMPT.md`

## Optional Code Attachments For Backend Work

If the next chat will implement backend changes, attach these files after the Markdown docs:

1. `backend/app/services/querying.py`
2. `backend/app/services/pipeline.py`
3. `backend/app/services/repositories.py`
4. `backend/app/services/github.py`
5. `backend/app/services/embeddings.py`
6. `backend/app/services/rag.py`
7. `backend/app/api/routes.py`
8. `backend/app/db/models.py`
9. `backend/app/core/config.py`
10. `backend/app/schemas.py`
11. `backend/app/cli.py`
12. `backend/requirements.txt`
13. `pyproject.toml`
14. `docker-compose.yml`
15. `.env.example`

## Optional Test Attachments

Attach these when asking Opus to fix or extend backend behavior:

1. `backend/tests/test_querying.py`
2. `backend/tests/test_repositories.py`
3. `backend/tests/test_pipeline_sources.py`
4. `backend/tests/test_retrieval.py`
5. `backend/tests/test_query_route.py`
6. `backend/tests/test_query_history.py`
7. `backend/tests/test_doc_sources.py`
8. `backend/tests/test_embeddings.py`
9. `backend/tests/test_github.py`
10. `backend/tests/test_ingest_errors.py`
11. `backend/tests/test_analytics.py`
12. `backend/tests/test_cli.py`

## Optional Frontend Attachments

Attach these only for frontend integration or UI work:

1. `frontend/app/page.tsx`
2. `frontend/components/chat-shell.tsx`
3. `frontend/lib/api.ts`
4. `frontend/app/globals.css`
5. `frontend/package.json`
6. `frontend/next.config.mjs`
