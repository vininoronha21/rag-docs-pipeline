# Opus Validation Prompt

Paste this prompt into Opus for one more focused validation round:

```text
You are reviewing a portfolio RAG documentation QA release. Please review the repository in two independent fronts and prioritize concrete findings with file/line references, severity, risk, and suggested verification commands.

Front 1: Backend infrastructure and data correctness
- Review FastAPI public/admin API boundaries, privacy guarantees, production settings, CORS validation, database URL split, Alembic/pgvector schema assumptions, GitHub ingestion/versioning, active source/version filtering, anonymous query events, sanitized error paths, Render/Neon deployment readiness, and evaluation/smoke gates.
- Look specifically for data leaks, schema/runtime mismatches, unsafe deployment defaults, broken active-version semantics, hidden persistence of visitor content, and failure paths that could expose secrets or request bodies.

Front 2: Frontend UI/UX quality
- Review the Next.js public chat and admin shell for Portuguese clarity, citation-first answer flow, evidence panel usability, mobile behavior, accessibility, loading/error states, feedback affordances, admin secret handling, stale async race handling, and Vercel environment assumptions.
- Look specifically for confusing refusal states, citation/evidence mismatch, poor mobile ergonomics, inaccessible controls, weak admin UX, and any client-side behavior that could accidentally expose secrets or stale data.

Context to assume:
- Target source: https://github.com/fastapi/fastapi, branch master, path docs/pt/docs.
- Default answer mode is extractive; no external chat LLM is implemented.
- Privacy contract: do not persist visitor question, answer text, citation snapshots, IP, user agent, request bodies, request paths, or public history.
- Latest local gate reported: backend 315 tests passed, frontend 23 tests passed, production build passed, evaluation passed answerable_top3=14/16, unsupported_refusals=4/4, answer_sentence_validation_failures=0.

Return results in this structure:
1. Critical findings
2. Important findings
3. Minor findings
4. Backend/data verification commands to run next
5. Frontend UI/UX verification checks to run next
6. Residual risks if no findings are present
```

---

## Session Audit Log (2026-07-23)

State carried into the "other notebook" run. This session did two things: a two-front validation review, and a full frontend redesign. The one open item is a backend CI failure that could not be reproduced locally for lack of tooling — it is the priority for the next run.

### Two-front validation review — outcome

- No Critical findings. Privacy contract verified holding (no hidden persistence of visitor content; sanitized error paths; observability logs route names not paths; admin/public boundary intact; CORS production validation; DB URL split; embedding dimension lock; active source/version filtering).
- Backend Important: rate limiter keys on `request.client.host` (`backend/app/core/rate_limit.py:32-34`); behind Render's proxy without `--proxy-headers`/`--forwarded-allow-ips` every visitor collapses into one bucket. Availability bug, not privacy.
- Backend Minor: `render.yaml:9` health check uses `/api/health` (no DB touch) instead of `/api/ready`; in-memory limiter does not survive restart/scale; `ALLOWED_ORIGINS` must be a JSON array or boot fails.
- Frontend Important (now FIXED in redesign): refusal gating by sentence count vs state; query/feedback errors rendered off-screen on mobile; `localhost:8000` fallback baked into the client bundle for the Docker build path (no env guard); sub-44px feedback tap targets.

### Frontend redesign — shipped on branch `dev`

Commits `edc7871..6625c60` (8 commits). Delivered the "Evidence Bench" redesign: persistent evidence panel beside the answer on desktop, Radix bottom sheet on mobile, layout gated by a JS `useMediaQuery("(min-width: 1024px)")` hook (jsdom ignores CSS breakpoints). Identity: Inter body + Fraunces serif headings + monospace citations, warm paper tokens. Fixes folded in: `isRefusal` gating on evidence state, inline error above composer with focus-move, feedback confirmation + no re-fire, ≥44px feedback targets, mobile sheet auto-open on answered-but-empty refusal, readiness detail restored into an `aria-live` region. Verification: `npm run typecheck` clean, `npm run test:run` 35 passing, `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000 npm run build` succeeds. Design spec and plan live under `docs/superpowers/`.

Deferred cosmetic/test-hygiene Minors (non-blocking): font test-mock returns identical variable for both fonts; `useMediaQuery` test does not assert `removeEventListener` args nor cover unmount; empty-state dialog title gained `font-serif`; redundant `response &&` in the feedback gate; `<aside>` carries redundant `hidden lg:flex` alongside the JS gate.

### Backend CI failure — for the next run to diagnose and fix

Facts gathered via the public GitHub API (could not go deeper: this machine has no `gh`, no `docker`, no `pyenv`/Python 3.12 — only Python 3.14 — and the Actions log download returns HTTP 403 without auth):

- Repository: `https://github.com/vininoronha21/rag-docs-pipeline`
- Latest `main` run: FAILURE. Run id `30023576763`, commit "v7.9" (`ad2c4374012891f145d1de211a165f07a72b0389`).
- Failing job: `backend`. Failing step: `Run pytest backend/tests --ignore=backend/tests/integration` (the UNIT test step). Preceding steps `pip install` and `ruff check backend` passed; the integration step was `skipped` because the unit step failed; the `frontend` job passed.
- CI env (`.github/workflows/ci.yml`): Python from `.python-version` = `3.12.13`, deps from `backend/requirements.txt`. The unit step runs WITHOUT `TEST_DATABASE_URL` (only the integration step sets it). The unit tests do not reference `TEST_DATABASE_URL`, so a missing DB URL is not the cause.
- Branch note: at the time of inspection `dev` and `main` were content-identical (7 "commit vN" commits on `main` changed no files), so the failure reproduces on the working tree too — it is not fixed in another branch.

Paste this into Opus on the machine that has `gh`, Docker, and Python 3.12.13:

```text
You are debugging a failing GitHub Actions run for the repository at this checkout (github.com/vininoronha21/rag-docs-pipeline). The `backend` job fails at the step `pytest backend/tests --ignore=backend/tests/integration` (unit tests) on Python 3.12.13; `ruff` and `pip install` pass; the frontend job passes. The unit step runs with NO TEST_DATABASE_URL set.

Do this in order and report findings with file/line references and the exact failing test names and assertion output:

1. Pull the real failure. Run `gh run view 30023576763 --log-failed` (or `gh run list --branch main` then `gh run view <id> --log-failed`) and quote the failing test node ids and the assertion/traceback lines verbatim.
2. Reproduce locally under the CI-matching interpreter: create a Python 3.12.13 venv, `pip install -r backend/requirements.txt`, then run `pytest backend/tests --ignore=backend/tests/integration -q` with NO TEST_DATABASE_URL in the environment. Confirm the same failure.
3. Diagnose root cause. Candidates to check first: tests that need a database or network but are not marked `integration` and only "passed" locally because a DATABASE_URL/TEST_DATABASE_URL was present; Python 3.12-vs-newer behavior differences; tests that spawn subprocesses (e.g. backend/tests/test_deployment_manifests.py, backend/tests/test_smoke_contract.py) and depend on PATH/tooling; time- or ordering-dependent tests; a pending-deprecation warning promoted to error.
4. Propose and apply the minimal fix (correct the test or the code it exercises — do not delete or skip the test to make CI green unless the test itself is wrong, and justify if so).
5. Verify: re-run the unit step command locally and confirm green, run `ruff check backend`, and confirm you did not break the integration suite contract.
6. Report: root cause, the fix, files changed, and the exact commands + output proving green.
```

