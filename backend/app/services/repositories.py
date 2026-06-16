from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentChunk, QueryLog
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
) -> Document:
    existing = await session.scalar(select(Document).where(Document.source_url == source_url))
    if existing is None:
        document = Document(
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
                embedding=embedding,
                chunk_metadata=chunk.metadata,
            )
        )

    await session.flush()
    return document


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
        WHERE true {source_clause}
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
) -> QueryLog:
    query = QueryLog(
        user_query=question,
        retrieved_chunks_ids=retrieved_chunk_ids,
        llm_response=answer,
    )
    session.add(query)
    await session.flush()
    return query


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
