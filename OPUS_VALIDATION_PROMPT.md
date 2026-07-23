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
