# Portfolio RAG Deployment Design

**Date:** 2026-07-13  
**Status:** Approved in design review  
**Initial release:** One curated PT-BR documentation source

## 1. Purpose

This specification defines the next product architecture for the documentation RAG portfolio. The first public release must demonstrate trustworthy retrieval, source traceability, safe administration, and a deployable user experience without paid APIs.

The release will run as an evolutionary monolith. It will preserve the existing FastAPI, Next.js, PostgreSQL, and pgvector foundation while fixing source identity, synchronization, citation accuracy, privacy, and deployment boundaries.

## 2. Product Goals

The initial release must:

1. Deploy the public frontend on Vercel.
2. Deploy the FastAPI backend on Render.
3. Use a free PostgreSQL service with pgvector, with Neon as the selected provider.
4. Ingest one administrator-curated PT-BR documentation directory from GitHub.
5. Synchronize that source manually and version it by Git commit.
6. Remove deleted upstream files from the active corpus after a successful synchronization.
7. Answer from extracted source text without a generative LLM.
8. Attach every displayed sentence to the exact supporting chunk.
9. Open the original highlighted evidence when requested or when evidence is insufficient.
10. Avoid storing visitor questions, answers, or citation snapshots.
11. Protect ingestion and source management from public access.
12. Validate retrieval quality against a curated 20-question PT-BR evaluation set.

## 3. Non-Goals

The initial release will not include:

- a generative LLM;
- paid AI APIs;
- English documentation sources;
- cross-language retrieval;
- visitor accounts or authentication;
- visitor query history;
- automatic or scheduled synchronization;
- GitHub webhooks;
- queues or background workers;
- multiple tenants;
- private GitHub repositories;
- public ingestion controls;
- indefinite source-version retention.

These exclusions are deliberate. The architecture must leave clear extension points for a future LLM and English-source release without implementing them now.

## 4. Architecture

### 4.1 Runtime components

The system has three deployed components:

1. **Vercel frontend:** Next.js public query experience and a separate administrative route.
2. **Render backend:** FastAPI monolith for source management, ingestion, retrieval, extractive answers, anonymous metrics, and authorization.
3. **Neon database:** PostgreSQL with pgvector for source versions, documents, chunks, vectors, full-text indexes, and anonymous query events.

GitHub remains the only document connector.

### 4.2 Boundaries

The backend keeps explicit internal boundaries:

- GitHub connector: repository metadata, commit resolution, and curated-path traversal;
- ingestion service: synchronization orchestration and atomic version promotion;
- Markdown normalization and chunking;
- embedding provider contract;
- hybrid retrieval service;
- extractive answer and citation service;
- public query API;
- protected administration API;
- anonymous metrics service.

No new microservice, queue, worker, or scheduler is introduced.

### 4.3 Deployment data flow

Public query flow:

```text
Browser -> Vercel -> Render query API -> Neon retrieval
                                    -> extractive answer and evidence
        <- citation-aware response <-
```

Administrative synchronization flow:

```text
Admin browser -> Vercel /admin -> Render admin API -> GitHub
                                                  -> chunking/embedding
                                                  -> Neon new version
                                                  -> atomic promotion
```

## 5. Source Identity and Versioning

### 5.1 Stable source identity

A source is uniquely identified by:

```text
canonical repository + branch + normalized documentation path
```

The source path is mandatory and must identify an explicitly curated directory. Whole-repository ingestion is not allowed in the initial release.

The source also stores an administrator-selected language. The initial supported value is `pt-BR`. Language is source configuration, not part of source identity.

### 5.2 Immutable versions

Each successful source synchronization creates an immutable version identified by the resolved Git commit SHA. A source points to exactly one active version.

A version records:

- source ID;
- commit SHA;
- synchronization timestamp;
- embedding provider identifier;
- embedding model or algorithm identifier;
- embedding dimensions;
- document and chunk counts.

The embedding metadata prevents logically incompatible vectors from being mixed without an explicit reindexing operation.

### 5.3 Document and chunk ownership

Documents belong to source versions rather than directly representing mutable source state. A document is unique by `(source_version_id, repository_path)`.

Chunks belong to documents. Every chunk can therefore be traced through:

```text
chunk -> document -> source version -> source -> repository/branch/path
```

Source URLs shown to users must be pinned to the version commit rather than a mutable branch URL.

### 5.4 Retention

The system retains the five most recent successful versions for each source. Older versions are deleted only after a newer version has been promoted successfully.

Because the product does not expose or retain visitor query history, deleted source versions do not need citation snapshots.

## 6. Manual Synchronization

Synchronization is initiated only by an authenticated administrator.

The flow is:

1. Normalize and validate repository, branch, and source path.
2. Resolve the branch head commit.
3. Return `no-op` when that commit is already active.
4. Recursively traverse only the configured source path.
5. Accept Markdown and MDX files under that path.
6. Normalize, chunk, and embed all accepted files into an isolated candidate version.
7. Validate candidate document and chunk counts.
8. Atomically mark the candidate as active.
9. Update source synchronization metadata.
10. Delete successful versions older than the five-version retention limit.

If GitHub, parsing, embedding, or persistence fails, the previous active version remains unchanged. The source stores a sanitized last-synchronization status and timestamp, but no incomplete version becomes active.

Files removed from GitHub disappear naturally from the new active version because each synchronization builds a complete version for the curated path.

## 7. Retrieval

### 7.1 Language behavior

The initial release accepts PT-BR questions only for the PT-BR source. It does not translate queries or search across languages.

Future English sources will be assigned `en` by an administrator. Query-language routing can then restrict retrieval to compatible active sources.

### 7.2 Hybrid ranking

Retrieval combines:

- pgvector cosine similarity using the local embedding implementation;
- PostgreSQL full-text search configured for Portuguese;
- rank fusion to combine semantic and exact technical-term matches.

Only chunks from active versions of enabled, language-compatible sources are eligible.

The full-text index must be database-backed and suitable for the query plan used in production. Ranking weights and the evidence threshold are configuration selected through the version-controlled evaluation set rather than guessed from isolated examples.

### 7.3 Evidence confidence

The initial product does not claim to measure LLM confidence. It classifies the strength of retrieved evidence using retrieval signals, including:

- fused score of the leading chunks;
- score separation from weaker results;
- presence of supporting evidence across relevant chunks;
- minimum retrieval thresholds calibrated by evaluation.

The API returns one of two product states:

- `answered`: sufficient evidence exists for an extractive response;
- `insufficient_evidence`: the system refuses to construct an answer and returns the best source excerpts for inspection.

The frontend must not display a fabricated confidence percentage.

## 8. Extractive Answers and Citations

### 8.1 Sentence-level provenance

Every sentence in an extractive answer must retain the identifier of the exact chunk from which it was selected. The answer renderer adds an inline citation immediately after that sentence.

The API must never attach the first retrieved sources generically to an answer. Only chunks that directly supplied displayed text are answer citations.

### 8.2 Evidence payload

Each cited evidence item contains:

- citation identifier;
- exact displayed sentence or supported span;
- original chunk excerpt;
- document title;
- repository path;
- heading or section;
- commit SHA;
- immutable GitHub URL;
- retrieval scores needed by the UI or diagnostics.

### 8.3 User interaction

The approved interaction is inline citations with an evidence panel:

- clicking a citation opens its supporting excerpt in a side panel on desktop;
- the same panel becomes a bottom sheet on mobile;
- `View sources` opens the evidence collection;
- the cited text is highlighted within the original excerpt;
- `insufficient_evidence` opens the evidence panel automatically;
- the answer remains visible while evidence is inspected.

## 9. Future LLM Contract

No LLM is integrated or presented in the initial deployment.

A future generation provider must consume the same retrieved evidence and return a structured list of claims. Each claim must include one or more source chunk IDs. A citation guard must reject, remove, or regenerate claims that lack valid evidence before a response reaches the user.

The future generated-answer response must preserve the current evidence payload and UI contract. This allows the extractive mode to remain a fallback when generation is unavailable, evidence is weak, or a user opens a citation.

## 10. API Design

### 10.1 Public endpoints

The public API contains:

- `GET /api/health`: process liveness only;
- `GET /api/ready`: database and pgvector readiness;
- `POST /api/query`: query, extractive answer, evidence state, and anonymous event ID;
- `PATCH /api/query-events/{id}/feedback`: positive or negative feedback for an anonymous event.

There is no public query-history or analytics endpoint.

### 10.2 Administrative endpoints

Administrative endpoints support:

- source creation;
- source listing and status;
- manual synchronization;
- source enable and disable operations;
- source removal when safe;
- aggregate operational and quality metrics.

All administrative endpoints require a Bearer secret.

### 10.3 Error contracts

The API returns stable error codes and sanitized messages for:

- invalid source configuration;
- unauthorized administration;
- GitHub rate limits or upstream failure;
- synchronization conflict;
- no active source;
- insufficient evidence;
- database or internal failure.

Insufficient evidence is a successful query outcome, not an HTTP server error.

## 11. Security and Privacy

### 11.1 Administration

The administrator secret is stored only in Render environment configuration. The backend compares credentials using a constant-time operation.

The Vercel `/admin` route asks the administrator for the secret and keeps it only in application memory. It is not written to local storage, session storage, logs, or analytics. Reloading the page requires authentication again.

### 11.2 Public protections

The backend applies configurable per-IP rate limits to public query and feedback operations. Initial defaults are:

- query: 20 requests per minute per IP;
- feedback: 30 requests per minute per IP;
- synchronization: 2 attempts per minute for an authenticated administrator.

The single-instance Render deployment may use an in-process limiter for the portfolio release. A distributed limiter is deferred until horizontal scaling exists.

CORS allows only explicitly configured Vercel production and approved preview origins. GitHub credentials remain backend-only.

### 11.3 Data minimization

The backend does not persist:

- visitor question text;
- answer text;
- query history;
- citation snapshots;
- IP addresses;
- administrator credentials.

Anonymous query events may persist:

- opaque event ID;
- timestamp;
- source and version IDs;
- latency;
- retrieval score summary;
- confidence state;
- result count;
- optional feedback.

Logs must follow the same policy and must not contain question or answer content.

## 12. Frontend Experience

### 12.1 Public route

The public page provides:

- a PT-BR question input;
- loading and backend-wakeup states;
- an extractive answer labeled as based directly on documentation;
- sentence-level inline citations;
- the evidence side panel or mobile bottom sheet;
- a clear insufficient-evidence state;
- optional positive or negative feedback;
- no visitor history.

The frontend may request readiness on initial load so that Render free-tier cold starts produce a clear `Starting the service` state instead of an unexplained failure.

### 12.2 Administrative route

The separate `/admin` route provides:

- in-memory secret entry;
- source registration with repository, branch, curated path, and language;
- source state and active commit;
- manual synchronization;
- enable and disable controls;
- last synchronization result;
- aggregate metrics without query content.

The existing public ingestion form must move out of the public query experience.

### 12.3 Responsive evidence interaction

Desktop uses a side panel that does not replace the answer. Mobile uses an accessible bottom sheet with focus management, keyboard support, and a clear close action.

## 13. Resilience and Observability

The release includes:

- existing HTTP timeout and retry behavior for GitHub;
- structured backend logs;
- request or correlation IDs;
- synchronization start, completion, failure, duration, and counts;
- query duration, confidence state, and retrieved-result count without content;
- liveness and readiness separation;
- atomic version promotion;
- friendly frontend recovery for Render cold start and transient failures.

The release does not add distributed tracing, a metrics cluster, a circuit breaker, or a job queue.

## 14. Deployment

### 14.1 Vercel

Vercel configuration supplies the public Render API URL at build time. Production CORS configuration must match the deployed Vercel origin. Preview origins are opt-in rather than globally wildcarded.

### 14.2 Render

Render configuration supplies:

- Neon database URL;
- administrator secret;
- GitHub token when higher rate limits are needed;
- allowed origins;
- retrieval and rate-limit settings;
- environment and logging settings.

Database migrations run as an explicit deploy step when the hosting plan supports it. If the free plan does not provide a separate release command, startup may run idempotent `alembic upgrade head` before starting a single API instance.

### 14.3 Neon

The Neon project must enable pgvector and use TLS. Connection-pool settings must account for Render cold starts and Neon connection limits.

## 15. Testing Strategy

### 15.1 Automated tests

The backend test suite must cover:

- stable source identity and uniqueness;
- commit-based version creation;
- same-commit no-op;
- atomic promotion and rollback behavior;
- upstream file deletion in a new active version;
- retention of exactly five successful versions;
- embedding metadata compatibility;
- active-version retrieval filters;
- Portuguese full-text and vector rank fusion;
- insufficient-evidence behavior;
- sentence-to-chunk citation correctness;
- administrator authorization;
- rate limiting;
- privacy constraints for events and logs;
- migration upgrade against real PostgreSQL and pgvector.

Frontend tests must cover:

- answer and citation rendering;
- evidence panel and mobile bottom sheet behavior;
- automatic evidence expansion on insufficient evidence;
- no public history;
- administrator secret lifecycle;
- backend cold-start and error states.

### 15.2 Retrieval evaluation

Before public deployment, the selected PT-BR repository must have a version-controlled evaluation set containing:

- 16 answerable questions with expected source documents or sections;
- 4 questions intentionally unsupported by the documentation.

Acceptance requires:

- expected evidence in the Top-3 for at least 14 of 16 answerable questions;
- all 4 unsupported questions classified as `insufficient_evidence`;
- every displayed answer sentence linked to its actual source chunk;
- no citation generated from an unrelated retrieved chunk.

The source repository itself has not yet been selected. Source selection is therefore an explicit prerequisite: candidates must have a coherent PT-BR documentation directory, a stable public GitHub history, enough content for 20 meaningful questions, and a license compatible with public demonstration.

### 15.3 Performance and deployment checks

Acceptance also requires:

- backend unit and integration tests passing on Python 3.12;
- Ruff passing;
- frontend production build and TypeScript checks passing;
- migration tests passing against PostgreSQL with pgvector in CI;
- warm query latency below one second for the curated demonstration corpus;
- a post-deploy smoke test across Vercel, Render, and Neon.

Render cold-start latency is measured separately and does not count against warm query latency.

## 16. Migration from the Current MVP

The implementation must account for these current-state changes:

- mutable documents become version-owned documents;
- source identity gains a database uniqueness constraint;
- branch/path/commit configuration moves from loosely structured metadata into explicit versioned fields where appropriate;
- retrieval changes from vector-only ranking to hybrid PT-BR ranking;
- extractive answer generation retains sentence-level chunk provenance;
- public history and analytics routes are removed or protected;
- raw query and answer persistence is replaced by anonymous metrics;
- the public ingestion form moves to `/admin`;
- Docker and hosted environments must receive the same required configuration;
- embedding dimensions and provider metadata become schema-controlled rather than only environment-controlled.

Existing local development data is disposable for this portfolio migration unless a later implementation plan identifies a concrete need to preserve it.

## 17. Future Extensions

The following work belongs to separate future designs and sprints:

1. Select and integrate a free or paid generative LLM provider behind a provider interface.
2. Add structured claim generation and citation validation.
3. Preserve extractive mode as fallback for low evidence, provider failure, and user source inspection.
4. Add English sources and language-compatible query routing.
5. Evaluate a stronger multilingual or language-specific embedding model when infrastructure permits.
6. Introduce asynchronous ingestion only when corpus size or request duration justifies a worker.
7. Add scheduled synchronization or GitHub webhooks only when source freshness becomes a product requirement.

## 18. Final Acceptance Boundary

The initial release is complete when a public visitor can ask a PT-BR question about one curated PT-BR source, receive a fast extractive answer whose every sentence opens the exact commit-pinned supporting passage, receive a safe refusal with visible evidence when support is weak, and cannot access ingestion, global history, analytics, or stored query content.

An administrator must be able to register and manually synchronize the curated source without exposing credentials, while a failed synchronization leaves the last valid version fully queryable.
