from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocSource, Document, DocumentChunk, QueryLog
from app.services.chunking import Chunk


@dataclass(frozen=True)
class RetrievedChunk:
    id: int
    document_id: int
    text: str
    chunk_index: int
    metadata: dict[str, Any]
    title: str | None
    source_url: str
    source: str
    score: float


@dataclass(frozen=True)
class AnalyticsSummary:
    document_count: int
    chunk_count: int
    source_count: int
    enabled_source_count: int
    query_count: int
    average_latency_ms: float
    positive_feedback_count: int
    negative_feedback_count: int


async def upsert_document_with_chunks(
    session: AsyncSession,
    *,
    source: str,
    source_url: str,
    title: str | None,
    content: str,
    metadata: dict[str, Any],
    chunks: list[Chunk],
    embeddings: list[list[float]],
    doc_source_id: int | None = None,
) -> Document:
    if len(chunks) != len(embeddings):
        raise ValueError("Expected one embedding per chunk.")

    existing = await session.scalar(select(Document).where(Document.source_url == source_url))
    if existing is None:
        document = Document(
            doc_source_id=doc_source_id,
            source=source,
            source_url=source_url,
            title=title,
            content=content,
            doc_metadata=metadata,
        )
        session.add(document)
        await session.flush()
    else:
        document = existing
        document.doc_source_id = doc_source_id
        document.source = source
        document.title = title
        document.content = content
        document.doc_metadata = metadata
        await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        await session.flush()

    for chunk, embedding in zip(chunks, embeddings, strict=True):
        session.add(
            DocumentChunk(
                document_id=document.id,
                chunk_text=chunk.text,
                chunk_index=chunk.index,
                chunk_hash=chunk.content_hash,
                embedding=embedding,
                chunk_metadata=chunk.metadata,
            )
        )

    await session.flush()
    return document


async def upsert_doc_source(
    session: AsyncSession,
    *,
    source_type: str,
    source_config: dict[str, Any],
    last_sync: datetime,
    enabled: bool = True,
) -> DocSource:
    source = await session.scalar(
        select(DocSource).where(
            DocSource.source_type == source_type,
            DocSource.source_config == source_config,
        )
    )
    if source is None:
        source = DocSource(
            source_type=source_type,
            source_config=source_config,
            last_sync=last_sync,
            enabled=enabled,
        )
        session.add(source)
    else:
        source.last_sync = last_sync
        source.enabled = enabled

    await session.flush()
    return source


async def list_doc_sources(session: AsyncSession) -> list[DocSource]:
    result = await session.scalars(select(DocSource).order_by(DocSource.last_sync.desc()))
    return list(result.all())


async def update_doc_source_enabled(
    session: AsyncSession,
    *,
    source_id: int,
    enabled: bool,
) -> DocSource | None:
    source = await session.get(DocSource, source_id)
    if source is None:
        return None
    source.enabled = enabled
    await session.flush()
    return source


async def get_analytics_summary(session: AsyncSession) -> AnalyticsSummary:
    document_count = await _count_rows(session, Document)
    chunk_count = await _count_rows(session, DocumentChunk)
    source_count = await _count_rows(session, DocSource)
    enabled_source_count = await session.scalar(
        select(func.count()).select_from(DocSource).where(DocSource.enabled.is_(True))
    )
    query_count = await _count_rows(session, QueryLog)
    average_latency = await session.scalar(select(func.coalesce(func.avg(QueryLog.latency_ms), 0)))
    positive_feedback_count = await session.scalar(
        select(func.count()).select_from(QueryLog).where(QueryLog.user_feedback == 1)
    )
    negative_feedback_count = await session.scalar(
        select(func.count()).select_from(QueryLog).where(QueryLog.user_feedback == -1)
    )
    return AnalyticsSummary(
        document_count=document_count,
        chunk_count=chunk_count,
        source_count=source_count,
        enabled_source_count=enabled_source_count or 0,
        query_count=query_count,
        average_latency_ms=round(float(average_latency or 0), 2),
        positive_feedback_count=positive_feedback_count or 0,
        negative_feedback_count=negative_feedback_count or 0,
    )


async def retrieve_chunks(
    session: AsyncSession,
    *,
    embedding: list[float],
    top_k: int,
    source: str | None = None,
) -> list[RetrievedChunk]:
    embedding_literal = "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"
    source_clause = "AND d.source = :source" if source else ""
    statement = text(
        f"""
        SELECT
            dc.id,
            dc.document_id,
            dc.chunk_text,
            dc.chunk_index,
            dc.chunk_metadata,
            d.title,
            d.source_url,
            d.source,
            1 - (dc.embedding <=> (:embedding)::vector) AS score
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        LEFT JOIN doc_sources ds ON ds.id = d.doc_source_id
        WHERE true {source_clause}
          AND (d.doc_source_id IS NULL OR ds.enabled IS TRUE)
        ORDER BY dc.embedding <=> (:embedding)::vector
        LIMIT :top_k
        """
    )
    rows = (
        await session.execute(
            statement,
            {"embedding": embedding_literal, "top_k": top_k, "source": source},
        )
    ).mappings()
    return [
        RetrievedChunk(
            id=row["id"],
            document_id=row["document_id"],
            text=row["chunk_text"],
            chunk_index=row["chunk_index"],
            metadata=row["chunk_metadata"] or {},
            title=row["title"],
            source_url=row["source_url"],
            source=row["source"],
            score=float(row["score"]),
        )
        for row in rows
    ]


async def log_query(
    session: AsyncSession,
    *,
    question: str,
    retrieved_chunk_ids: list[int],
    answer: str,
    latency_ms: int,
    retrieved_chunk_count: int,
) -> QueryLog:
    query = QueryLog(
        user_query=question,
        retrieved_chunks_ids=retrieved_chunk_ids,
        llm_response=answer,
        latency_ms=latency_ms,
        retrieved_chunk_count=retrieved_chunk_count,
    )
    session.add(query)
    await session.flush()
    return query


async def _count_rows(
    session: AsyncSession,
    model: type[Document | DocumentChunk | DocSource | QueryLog],
) -> int:
    count = await session.scalar(select(func.count()).select_from(model))
    return count or 0


async def list_queries(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> tuple[list[QueryLog], int]:
    total = await session.scalar(select(func.count()).select_from(QueryLog))
    result = await session.scalars(
        select(QueryLog)
        .order_by(QueryLog.created_at.desc(), QueryLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.all()), total or 0


async def update_query_feedback(
    session: AsyncSession,
    *,
    query_id: int,
    feedback: int,
) -> QueryLog | None:
    query = await session.get(QueryLog, query_id)
    if query is None:
        return None
    query.user_feedback = feedback
    await session.flush()
    return query
