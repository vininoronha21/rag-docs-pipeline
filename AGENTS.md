# AI Agents Architecture - RAG for Documentation

This project is implemented as a FastAPI monolith, but the pipeline is organized around clear logical agents. The current release is citation-first, privacy-preserving, and admin-protected.

## 1. Ingestion And Normalization Agent

- Responsibility: pull Markdown documentation from GitHub and normalize it without corrupting structure.
- Current implementation: `GithubClient`, `ingest_github_repository`, Markdown cleanup, source locking, retry/backoff for transient GitHub HTTP failures, and admin-only `/api/admin/ingest/github`.
- Version model: `DocSource` is unique by repository, branch, and path. Each synchronized commit creates or reuses a `SourceVersion`; active versions are promoted and older retained versions can be pruned.
- Success metric: ingest the target FastAPI PT-BR docs from `https://github.com/fastapi/fastapi`, branch `master`, path `docs/pt/docs`, with documents tied to one commit SHA.
- Current limitations: no scheduled sync, no queue/worker split, no streaming progress UI, and no source connectors beyond GitHub Markdown.

## 2. Semantic Partitioning Agent

- Responsibility: split long Markdown documents into coherent, independently retrievable chunks.
- Current implementation: Markdown cleanup, title extraction, heading-aware splitting, size-aware overlap, chunk hashes, and metadata injection for repository path, section, chunk index, source version, and commit-pinned provenance.
- Success metric: chunks preserve complete ideas, support sentence-level citations, and avoid cutting important sections or code context where practical.
- Current limitation: chunk quality is evaluated against the PT-BR FastAPI dataset, but further tuning should be driven by observed retrieval misses rather than speculative changes.

## 3. Vector Indexing And Retrieval Agent

- Responsibility: bridge natural-language questions and persisted evidence.
- Current implementation: local deterministic embeddings by default, optional OpenAI embeddings with timeout/retry, PostgreSQL/pgvector vectors, PostgreSQL full-text search, reciprocal-rank fusion, enabled-source filtering, active-version filtering, and score thresholds.
- Public query surface: `POST /api/query` only. Retrieval excludes disabled sources and returns evidence from active source versions.
- Success metric: return top evidence that answers supported PT-BR questions and refuse unsupported ones.
- Current limitation: local hash embeddings are not semantically strong, OpenAI embedding batching is not implemented, and there is no reranker.

## 4. Synthesis And Citation Guard Agent

- Responsibility: turn retrieved chunks into a safe answer or refusal while preserving provenance.
- Current implementation: shared API/CLI `run_query`, prompt-injection-like chunk filtering, extractive answer generation, `state="answered"` or `state="insufficient_evidence"`, citation IDs, evidence excerpts, commit SHA, and immutable GitHub blob URLs.
- Privacy contract: no visitor question, answer text, citation snapshot, IP, user agent, or public history is persisted. `query_events` stores only an opaque UUID, state, latency, retrieved count, source IDs, source version IDs, score summaries, optional feedback, and timestamp.
- Success metric: answerable questions include citation-linked sentences and commit-pinned evidence; unsupported questions refuse while still exposing best evidence.
- Current limitation: `LLM_PROVIDER=openai` and `OPENAI_CHAT_MODEL` exist in settings, but no external chat synthesis provider is implemented.

## 5. Operations And Admin Agent

- Responsibility: keep production boundaries explicit and verifiable.
- Current implementation: public `/api/health` and `/api/ready`, Bearer-protected `/api/admin/*`, `ADMIN_SECRET` required in production, CORS allow-listing, query/feedback/sync rate limits, Render and Vercel manifests, Neon-compatible async/sync DB URLs, and `scripts/smoke.sh`.
- Verification: `backend/scripts/verify_pipeline.py`, backend tests, frontend typecheck/tests/build, evaluation gate, and post-deploy smoke.
- Current blockers: live deployed smoke awaits real frontend/backend URLs; Docker runtime verification previously hit Docker Hub metadata timeout.
