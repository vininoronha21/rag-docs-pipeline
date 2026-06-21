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


async def run_query(
    session: AsyncSession,
    *,
    question: str,
    top_k: int,
    source: str | None,
    settings: Settings,
    embeddings: EmbeddingProvider,
) -> QueryExecutionResult:
    started_at = time.perf_counter()
    query_embedding = await embeddings.embed_query(question)
    chunks = await retrieve_chunks(
        session,
        embedding=query_embedding,
        top_k=top_k,
        source=source,
    )
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
