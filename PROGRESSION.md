# Progression Log

## Purpose

This file is an AI-readable progression log for the portfolio RAG release work. It records the release branch state, major implementation changes, review fixes, validation evidence, and remaining operational blockers in direct English.

## Branch Context

- Documentation updated on branch: `dev`.
- Validated implementation branch: `feature/portfolio-rag-release`.
- Merge base used for final whole-branch review: `34255b1`.
- Final validated implementation HEAD: `4139fc3 fix: reject local production origin variants`.
- Main workspace had pre-existing untracked `docs/sprints/` and `docs/superpowers/` content before this documentation update; those existing files were not modified except for the new plan file created for this docs task.

## Release Target

- Source repository: `https://github.com/fastapi/fastapi`.
- Branch: `master`.
- Curated path: `docs/pt/docs`.
- Language: Portuguese documentation.
- Evaluation dataset: `evaluation/pt-br/questions.jsonl`.
- First deploy target: Vercel frontend, Render backend, Neon-compatible PostgreSQL/pgvector.

## Sprint Progression

### Baseline And Database Confidence

- Established Python `3.12.13` and Node 22 expectations.
- Added baseline backend/frontend verification and CI confidence.
- Added PostgreSQL safety checks for test database usage.
- Approved the FastAPI PT-BR documentation source.

### Versioned GitHub Ingestion

- Added GitHub ingestion for Markdown/MDX under a curated repository path.
- Introduced `DocSource` identity by repository, branch, and path.
- Introduced `SourceVersion` for commit-pinned synchronized snapshots.
- Moved document ownership to `SourceVersion` and repository path.
- Added active-version promotion and retained-version handling.
- Added commit-pinned source URLs and source-version metadata.

### Retrieval And Answer Reliability

- Added hybrid retrieval using pgvector cosine search plus PostgreSQL full-text search.
- Added reciprocal-rank fusion and active-source filtering.
- Added anonymous `QueryEvent` telemetry instead of public query history.
- Added extractive answer generation with citation IDs.
- Added insufficient-evidence behavior for unsupported or weakly supported questions.
- Added disabled-source exclusion and active-version retrieval enforcement.

### API Security And Observability

- Protected admin routes with Bearer `ADMIN_SECRET`.
- Required `ADMIN_SECRET` in production.
- Added query, feedback, and sync rate limiting.
- Split public `/api/health` from readiness `/api/ready`.
- Added structured request completion logging.
- Hardened CORS around explicit allowed origins.

### Citation-First Frontend

- Added typed frontend API helpers.
- Added Portuguese public chat shell.
- Added sentence citation rendering and evidence panel.
- Added feedback controls tied to opaque query event UUIDs.
- Added protected admin shell that keeps the secret in memory only.
- Fixed stale admin async results after logout/new sessions.
- Added admin source cards with active commit/version/count metadata.

### Evaluation And Deployment

- Added PT-BR evaluation dataset with 16 answerable and 4 unsupported questions.
- Added evaluation runner for ranked retrieval, refusals, and cited sentence validation.
- Added deployment manifests for Render and Vercel.
- Added Neon-compatible async/sync database URL split.
- Added post-deploy smoke script and workflow.
- Updated local verifier to target the FastAPI PT-BR source and validate source versions, active counts, no-op sync, anonymous events, commit-pinned citations, disabled-source exclusion, and cleanup.

## Final Review Fix Progression

### `1c17f05 fix: address final review findings`

- Disabled Uvicorn access logs in `backend/Dockerfile` and `render.yaml`.
- Removed deployable placeholder `NEXT_PUBLIC_BACKEND_URL` from `frontend/vercel.json`.
- Added public query input bounds for `question` and `source`.
- Mirrored public question max length in the frontend composer.
- Enforced `EMBEDDING_DIMENSIONS=1536` for the fixed pgvector schema.
- Added active version metadata to admin source API responses and cards.
- Added active searchable corpus counts to analytics.

### `803b455 fix: harden final deployment privacy checks`

- Fixed the Vercel build guard so missing `NEXT_PUBLIC_BACKEND_URL` fails before `npm run build`.
- Added an executable test using fake `npm` to prevent guard regressions.
- Replaced request-completion log `route` path with privacy-safe `operation` labels.
- Added tests proving `/api/query` path is not retained in structured logs.

### `dd78ba1 test: cover user agent log redaction`

- Added a user-agent sentinel to observability tests.
- Confirmed structured logs do not retain user-agent content.

### `1ccf6de fix: close final release review blockers`

- Tightened the evaluation gate so answerable cases must return `answered` with at least one validated cited sentence.
- Added sanitized `SQLAlchemyError` handling for public query database failures.
- Returned generic `503` for public query DB failures without exposing SQL params or visitor questions.
- Added `max_files: 500` to admin GitHub sync payloads.
- Required explicit production `ALLOWED_ORIGINS`.
- Rejected wildcard and local production origins.
- Split GitHub raw file downloads into a separate unauthenticated HTTP client.
- Added frontend CI steps for typecheck, tests, and build.
- Adjusted answer decision logic to allow vector-only chunks only when cited sentences have meaningful query-term support.
- Preserved unsupported refusals by ignoring generic support terms and requiring meaningful overlap or high-signal import-prefix support.

### `7614442 fix: harden release blocker edge cases`

- Protected rollback inside the public query `SQLAlchemyError` handler.
- Logged only sanitized rollback error class names when rollback fails.
- Expanded support-term stopwords for English generic terms such as `how`, `what`, `the`, `with`, `use`, and `using`.
- Added regression tests for vector-only unsupported English generic overlap.
- Strengthened production origin validation for empty lists, blank values, paths, queries, fragments, IPv6 loopback, wildcard hostnames, userinfo, and invalid ports.
- Added `answerable_answered_with_citations_required` to evaluation report quality-gate JSON.

### `6a888cd fix: reject malformed production origins`

- Rejected wildcard characters anywhere in production origins.
- Rejected userinfo in production origins.
- Forced URL port parsing so malformed text ports fail validation.
- Normalized trailing dots before localhost/loopback checks.

### `4139fc3 fix: reject local production origin variants`

- Rejected `.localhost` subdomains such as `http://app.localhost:3000`.
- Rejected dangling empty port delimiters such as `https://example.com:`.
- Final focused review found no Critical, Important, or Minor issues for this CORS edge fix.

## Final Verification Evidence

Latest verification from final implementation HEAD `4139fc3`:

- `git diff --check`: passed.
- `PYENV_VERSION=3.12.13 python -m ruff check backend`: passed.
- `TEST_DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag_docs_test PYENV_VERSION=3.12.13 python -m pytest backend/tests`: `315 passed`, one existing Starlette multipart pending-deprecation warning.
- `npm --prefix frontend run typecheck`: passed.
- `npm --prefix frontend run test:run`: `23 passed`.
- `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000 npm --prefix frontend run build`: passed.
- `PYENV_VERSION=3.12.13 PYTHONPATH=backend python backend/scripts/evaluate_retrieval.py --dataset evaluation/pt-br/questions.jsonl --top-k 3 --output evaluation/pt-br/latest-report.json`: `Evaluation PASSED: answerable_top3=14/16, unsupported_refusals=4/4, answer_sentence_validation_failures=0`.

## Review Status

- Final whole-branch review initially found blockers in evaluation, public query DB failure privacy, admin `max_files`, production CORS, GitHub raw token handling, and frontend CI coverage.
- All Critical and Important findings were fixed with regression tests.
- Follow-up CORS edge reviews found additional malformed-origin cases.
- Final focused review for `4139fc3` returned no Critical, Important, or Minor findings.

## Remaining Operational Blockers

- Live deployed smoke has not run because real Vercel and Render URLs were not provided.
- Docker runtime verification remains pending because prior runtime verification hit a Docker Hub metadata timeout.
- Public production validation still needs real provider environment values: `NEXT_PUBLIC_BACKEND_URL`, `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `ADMIN_SECRET`, and exact `ALLOWED_ORIGINS`.

## Recommended Next Validations

- Run a fresh review focused on backend infrastructure/data correctness and frontend UI/UX quality.
- After deploy, run `scripts/smoke.sh` with real `FRONTEND_URL`, `BACKEND_URL`, and two smoke questions.
- Retry Docker runtime verification when Docker Hub metadata access is stable.
- Confirm provider-level logs on Render and Vercel do not conflict with the project privacy contract.
