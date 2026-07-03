# AI Agents Architecture — RAG for Documentation

This document defines the logical agents that make up the AI-ready data pipeline for the project. Although the MVP is monolithic (FastAPI), the architecture is designed with a clear separation of concerns across the RAG stages.

---

## 1. Ingestion & Normalization Agent (The Scraper)
- **Responsibility:** Monitor external sources (GitHub repositories) and extract raw documents in a clean format.
- **Current implementation:** `GithubClient`, `ingest_github_repository`, Markdown cleaning, and document/source upsert logic inside the FastAPI monolith.
- **Tasks:**
  - Authenticate and consume the GitHub API efficiently (respecting rate limits).
  - Locate `.md` files and extract raw metadata (branch, path, SHA, last modified).
  - Filter out code noise, broken relative links, and useless assets.
  - Upsert `doc_sources` by source configuration and documents by `source_url`.
- **Success Metric:** Ingest 100% of target documents without corrupting text structure.
- **Current limitation:** No scheduled sync, no retry/backoff, and no source connectors beyond GitHub Markdown.

## 2. Semantic Partitioning Agent (The Chunker)
- **Responsibility:** Break long documents into semantically coherent, independent chunks enriched with metadata.
- **Current implementation:** Custom Markdown cleanup, heading-aware splitting, overlap handling, metadata injection, and content-hash deduplication.
- **Tasks:**
  - Apply heading-aware and size-aware Markdown splitting strategies.
  - Maintain an appropriate overlap window to preserve context continuity.
  - Inject hierarchical metadata into each chunk (e.g. `{"parent_doc": "README.md", "section": "Installation"}`).
  - Preserve useful source metadata such as repository, path, SHA, section, and chunk index.
- **Success Metric:** Produce chunks that contain complete ideas and avoid cutting sentences or code blocks.
- **Current limitation:** Chunk quality still needs review against real repositories before tuning.

## 3. Vector Indexing & Retrieval Agent (The Retriever)
- **Responsibility:** Bridge user natural language queries and mathematical storage in the vector database.
- **Current implementation:** Local deterministic hash embeddings by default, optional OpenAI embeddings, PostgreSQL/pgvector persistence, and cosine retrieval.
- **Tasks:**
  - Generate embeddings through the configured provider.
  - Persist and index vectors in PostgreSQL using the `pgvector` extension.
  - Execute cosine-similarity searches using an HNSW index for low-latency retrieval (< 500ms).
  - Exclude chunks linked to disabled document sources.
  - Apply `RETRIEVAL_MIN_SCORE` before answer generation.
- **Success Metric:** Return Top-K chunks that genuinely answer the user's question.
- **Current limitation:** OpenAI embedding batching and retry/backoff are not implemented yet; local hash embeddings are not semantically strong.

## 4. Synthesis & Citation Guard Agent (The Orchestrator / LLM Layer)
- **Responsibility:** Consume retrieved chunks, generate a final natural-language answer, and ensure factual anchoring (minimize hallucinations).
- **Current implementation:** Shared API/CLI query service, prompt-injection-like chunk filtering, extractive answer generation, citations, query logging, feedback, history, and analytics.
- **Tasks:**
  - Assemble system prompts hardened against prompt injection and hallucination.
  - Keep extractive answer mode as the safe local default.
  - Add an optional LLM provider later without removing extractive fallback.
  - Track the origin of each piece of information used and include citation metadata.
- **Success Metric:** Provide direct, clear answers that explicitly cite the source link(s) used.
- **Current limitation:** No true external LLM synthesis provider is implemented yet, even though `LLM_PROVIDER` and `OPENAI_CHAT_MODEL` settings exist.
