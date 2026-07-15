import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.services.embeddings import EmbeddingProvider
from app.services.rag import (
    build_extractive_answer,
    filter_chunks_by_min_score,
    filter_prompt_injection_chunks,
)
from app.services.repositories import RetrievedChunk, log_query, retrieve_chunks


@dataclass(frozen=True)
class QueryExecutionResult:
    query_id: int
    answer: str
    chunks: list[RetrievedChunk]
    retrieved_chunk_ids: list[int]
    latency_ms: int
    retrieved_chunk_count: int


def validate_query_request(*, question: str, top_k: int) -> None:
    if len(question.strip()) < 2:
        raise ValueError("Question must contain at least two non-whitespace characters.")
    if top_k < 1 or top_k > 12:
        raise ValueError("top_k must be between 1 and 12.")


async def run_query(
    session: AsyncSession,
    *,
    question: str,
    top_k: int,
    source: str | None,
    settings: Settings,
    embeddings: EmbeddingProvider,
    source_id: int | None = None,
) -> QueryExecutionResult:
    validate_query_request(question=question, top_k=top_k)
    started_at = time.perf_counter()
    query_embedding = await embeddings.embed_query(question)
    retrieval_options = {
        "question": question,
        "embedding": query_embedding,
        "top_k": top_k,
        "candidate_k": settings.retrieval_candidate_k,
        "rrf_k": settings.retrieval_rrf_k,
        "vector_weight": settings.retrieval_vector_weight,
        "text_weight": settings.retrieval_text_weight,
        "source": source,
    }
    if source_id is not None:
        retrieval_options["source_id"] = source_id
    chunks = await retrieve_chunks(session, **retrieval_options)
    chunks = filter_chunks_by_min_score(chunks, min_score=settings.retrieval_min_score)
    chunks = filter_prompt_injection_chunks(chunks)
    answer = build_extractive_answer(question, chunks)
    chunk_ids = [chunk.id for chunk in chunks]
    latency_ms = round((time.perf_counter() - started_at) * 1000)
    query_log = await log_query(
        session,
        question=question,
        retrieved_chunk_ids=chunk_ids,
        answer=answer,
        latency_ms=latency_ms,
        retrieved_chunk_count=len(chunk_ids),
    )
    await session.commit()
    return QueryExecutionResult(
        query_id=query_log.id,
        answer=answer,
        chunks=chunks,
        retrieved_chunk_ids=chunk_ids,
        latency_ms=query_log.latency_ms,
        retrieved_chunk_count=query_log.retrieved_chunk_count,
    )
