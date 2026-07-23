from dataclasses import dataclass
from math import isfinite
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import DocSource, Document, DocumentChunk, QueryEvent, SourceVersion
from app.services.chunking import Chunk

EvidenceState = Literal["answered", "insufficient_evidence"]


@dataclass(frozen=True)
class RetrievedChunk:
    id: int
    document_id: int
    text: str
    chunk_index: int
    metadata: dict[str, Any]
    title: str | None
    repository: str
    repository_path: str
    commit_sha: str
    source_url: str
    source: str
    source_id: int
    source_version_id: int
    vector_score: float | None
    text_score: float | None
    vector_rank: int | None
    text_rank: int | None
    fused_score: float


@dataclass(frozen=True)
class AnalyticsSummary:
    document_count: int
    chunk_count: int
    active_document_count: int
    active_chunk_count: int
    source_count: int
    enabled_source_count: int
    query_count: int
    average_latency_ms: float
    positive_feedback_count: int
    negative_feedback_count: int


@dataclass(frozen=True)
class SourceVersionDocument:
    repository_path: str
    source: str
    source_url: str
    title: str | None
    content: str
    metadata: dict[str, Any]
    chunks: list[Chunk]
    embeddings: list[list[float]]


async def get_or_create_doc_source(
    session: AsyncSession,
    *,
    repository: str,
    branch: str,
    path: str,
    language: str = "pt-BR",
) -> DocSource:
    await session.execute(
        insert(DocSource)
        .values(
            source_type="github",
            source_config={"repo": repository, "branch": branch, "path": path},
            repository=repository,
            branch=branch,
            path=path,
            language=language,
            enabled=True,
        )
        .on_conflict_do_nothing(index_elements=["repository", "branch", "path"])
    )
    source = await session.scalar(
        select(DocSource).where(
            DocSource.repository == repository,
            DocSource.branch == branch,
            DocSource.path == path,
        )
    )
    if source is None:
        raise RuntimeError("Document source could not be created.")
    return source


async def get_doc_source_by_identity(
    session: AsyncSession, *, repository: str, branch: str, path: str
) -> DocSource | None:
    return await session.scalar(
        select(DocSource)
        .where(
            DocSource.repository == repository,
            DocSource.branch == branch,
            DocSource.path == path,
        )
        .execution_options(populate_existing=True)
    )


async def get_doc_source_for_update(session: AsyncSession, *, source_id: int) -> DocSource | None:
    return await session.scalar(
        select(DocSource)
        .where(DocSource.id == source_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def get_active_source_version(
    session: AsyncSession, *, source: DocSource
) -> SourceVersion | None:
    if source.active_version_id is None:
        return None
    return await session.scalar(
        select(SourceVersion).where(
            SourceVersion.id == source.active_version_id,
            SourceVersion.source_id == source.id,
        )
    )


async def get_source_version_by_commit(
    session: AsyncSession, *, source_id: int, commit_sha: str
) -> SourceVersion | None:
    return await session.scalar(
        select(SourceVersion).where(
            SourceVersion.source_id == source_id,
            SourceVersion.commit_sha == commit_sha,
        )
    )


async def create_source_version_with_documents(
    session: AsyncSession,
    *,
    source: DocSource,
    commit_sha: str,
    embedding_provider: str,
    embedding_model: str,
    embedding_dimensions: int,
    documents: list[SourceVersionDocument],
) -> SourceVersion:
    for document in documents:
        if len(document.chunks) != len(document.embeddings):
            raise ValueError("Expected one embedding per chunk.")
        if any(len(embedding) != embedding_dimensions for embedding in document.embeddings):
            raise ValueError("Embedding dimensions do not match the source version.")

    version = SourceVersion(
        source_id=source.id,
        commit_sha=commit_sha,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
        document_count=len(documents),
        chunk_count=sum(len(document.chunks) for document in documents),
    )
    session.add(version)
    await session.flush()

    for candidate in documents:
        document = Document(
            source_version_id=version.id,
            repository_path=candidate.repository_path,
            source=candidate.source,
            source_url=candidate.source_url,
            title=candidate.title,
            content=candidate.content,
            doc_metadata=candidate.metadata,
        )
        session.add(document)
        await session.flush()
        for chunk, embedding in zip(candidate.chunks, candidate.embeddings, strict=True):
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
    return version


async def promote_source_version(
    session: AsyncSession,
    *,
    source: DocSource,
    version: SourceVersion,
    retention: int = 5,
) -> None:
    if version.source_id != source.id:
        raise ValueError("Source version does not belong to source.")
    if retention < 1:
        raise ValueError("Retention must be at least one version.")

    source.active_version_id = version.id
    source.last_sync = version.synced_at
    await session.flush()

    obsolete_versions = (
        select(SourceVersion.id)
        .where(
            SourceVersion.source_id == source.id,
            SourceVersion.id != version.id,
        )
        .order_by(SourceVersion.synced_at.desc(), SourceVersion.id.desc())
        .offset(retention - 1)
    )
    await session.execute(delete(SourceVersion).where(SourceVersion.id.in_(obsolete_versions)))


async def list_doc_sources(session: AsyncSession) -> list[DocSource]:
    result = await session.scalars(
        select(DocSource)
        .options(selectinload(DocSource.active_version))
        .order_by(DocSource.last_sync.desc())
    )
    return list(result.all())


async def update_doc_source_enabled(
    session: AsyncSession,
    *,
    source_id: int,
    enabled: bool,
) -> DocSource | None:
    source = await session.scalar(
        select(DocSource)
        .options(selectinload(DocSource.active_version))
        .where(DocSource.id == source_id)
    )
    if source is None:
        return None
    source.enabled = enabled
    await session.flush()
    return source


async def get_analytics_summary(session: AsyncSession) -> AnalyticsSummary:
    document_count = await _count_rows(session, Document)
    chunk_count = await _count_rows(session, DocumentChunk)
    active_document_count = await session.scalar(
        select(func.coalesce(func.sum(SourceVersion.document_count), 0))
        .select_from(DocSource)
        .join(SourceVersion, DocSource.active_version_id == SourceVersion.id)
        .where(DocSource.enabled.is_(True))
    )
    active_chunk_count = await session.scalar(
        select(func.coalesce(func.sum(SourceVersion.chunk_count), 0))
        .select_from(DocSource)
        .join(SourceVersion, DocSource.active_version_id == SourceVersion.id)
        .where(DocSource.enabled.is_(True))
    )
    source_count = await _count_rows(session, DocSource)
    enabled_source_count = await session.scalar(
        select(func.count()).select_from(DocSource).where(DocSource.enabled.is_(True))
    )
    query_count = await _count_rows(session, QueryEvent)
    average_latency = await session.scalar(
        select(func.coalesce(func.avg(QueryEvent.latency_ms), 0))
    )
    positive_feedback_count = await session.scalar(
        select(func.count()).select_from(QueryEvent).where(QueryEvent.feedback == 1)
    )
    negative_feedback_count = await session.scalar(
        select(func.count()).select_from(QueryEvent).where(QueryEvent.feedback == -1)
    )
    return AnalyticsSummary(
        document_count=document_count,
        chunk_count=chunk_count,
        active_document_count=int(active_document_count or 0),
        active_chunk_count=int(active_chunk_count or 0),
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
    question: str,
    embedding: list[float],
    top_k: int,
    candidate_k: int,
    rrf_k: int,
    vector_weight: float,
    text_weight: float,
    source: str | None = None,
    source_id: int | None = None,
) -> list[RetrievedChunk]:
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if candidate_k <= top_k:
        raise ValueError("candidate_k must be greater than top_k")
    if rrf_k <= 0:
        raise ValueError("rrf_k must be greater than 0")
    for name, weight in (
        ("vector_weight", vector_weight),
        ("text_weight", text_weight),
    ):
        if not isfinite(weight) or weight <= 0:
            raise ValueError(f"{name} must be finite and greater than 0")
    if not embedding:
        raise ValueError("embedding must not be empty")
    if any(not isfinite(value) for value in embedding):
        raise ValueError("embedding values must be finite")
    embedding_literal = "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"
    source_clause = "AND d.source = :source" if source else ""
    source_id_clause = "AND ds.id = :source_id" if source_id is not None else ""
    statement = text(
        f"""
        WITH vector_candidates AS (
            SELECT
                dc.id,
                1 - (dc.embedding <=> (:embedding)::vector) AS vector_score,
                row_number() OVER (
                    ORDER BY dc.embedding <=> (:embedding)::vector, dc.id
                ) AS vector_rank
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            JOIN source_versions sv ON sv.id = d.source_version_id
            JOIN doc_sources ds ON ds.id = sv.source_id
            WHERE true {source_clause} {source_id_clause}
              AND ds.active_version_id = sv.id
              AND ds.enabled IS TRUE
              AND vector_norm((:embedding)::vector) > 0
              AND vector_norm(dc.embedding) > 0
            ORDER BY dc.embedding <=> (:embedding)::vector, dc.id
            LIMIT :candidate_k
        ),
        text_candidates AS (
            SELECT
                dc.id,
                ts_rank_cd(
                    dc.search_vector,
                    websearch_to_tsquery('portuguese', :question)
                ) AS text_score,
                row_number() OVER (
                    ORDER BY
                        ts_rank_cd(
                            dc.search_vector,
                            websearch_to_tsquery('portuguese', :question)
                        ) DESC,
                        dc.id
                ) AS text_rank
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            JOIN source_versions sv ON sv.id = d.source_version_id
            JOIN doc_sources ds ON ds.id = sv.source_id
            WHERE true {source_clause} {source_id_clause}
              AND ds.active_version_id = sv.id
              AND ds.enabled IS TRUE
              AND dc.search_vector @@ websearch_to_tsquery('portuguese', :question)
            ORDER BY text_score DESC, dc.id
            LIMIT :candidate_k
        ),
        candidate_ids AS (
            SELECT id FROM vector_candidates
            UNION
            SELECT id FROM text_candidates
        ),
        fused AS (
            SELECT
                candidate_ids.id,
                vector_candidates.vector_score,
                text_candidates.text_score,
                vector_candidates.vector_rank,
                text_candidates.text_rank,
                coalesce(
                    CAST(:vector_weight AS double precision) /
                    (CAST(:rrf_k AS double precision) + vector_candidates.vector_rank),
                    0.0
                ) + coalesce(
                    CAST(:text_weight AS double precision) /
                    (CAST(:rrf_k AS double precision) + text_candidates.text_rank),
                    0.0
                ) AS fused_score
            FROM candidate_ids
            LEFT JOIN vector_candidates USING (id)
            LEFT JOIN text_candidates USING (id)
        )
        SELECT
            dc.id,
            dc.document_id,
            dc.chunk_text,
            dc.chunk_index,
            dc.chunk_metadata,
            d.title,
            ds.repository,
            d.repository_path,
            sv.commit_sha,
            d.source_url,
            d.source,
            ds.id AS source_id,
            sv.id AS source_version_id,
            fused.vector_score,
            fused.text_score,
            fused.vector_rank,
            fused.text_rank,
            fused.fused_score
        FROM fused
        JOIN document_chunks dc ON dc.id = fused.id
        JOIN documents d ON d.id = dc.document_id
        JOIN source_versions sv ON sv.id = d.source_version_id
        JOIN doc_sources ds ON ds.id = sv.source_id
        ORDER BY fused_score DESC, dc.id ASC
        LIMIT :top_k
        """
    )
    rows = (
        await session.execute(
            statement,
            {
                "embedding": embedding_literal,
                "question": question,
                "top_k": top_k,
                "candidate_k": candidate_k,
                "rrf_k": rrf_k,
                "vector_weight": vector_weight,
                "text_weight": text_weight,
                "source": source,
                **({"source_id": source_id} if source_id is not None else {}),
            },
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
            repository=row["repository"],
            repository_path=row["repository_path"],
            commit_sha=row["commit_sha"],
            source_url=row["source_url"],
            source=row["source"],
            source_id=row["source_id"],
            source_version_id=row["source_version_id"],
            vector_score=(
                float(row["vector_score"]) if row["vector_score"] is not None else None
            ),
            text_score=float(row["text_score"]) if row["text_score"] is not None else None,
            vector_rank=int(row["vector_rank"]) if row["vector_rank"] is not None else None,
            text_rank=int(row["text_rank"]) if row["text_rank"] is not None else None,
            fused_score=float(row["fused_score"]),
        )
        for row in rows
    ]


async def log_query_event(
    session: AsyncSession,
    *,
    state: EvidenceState,
    latency_ms: int,
    retrieved_chunk_count: int,
    source_ids: list[int],
    source_version_ids: list[int],
    top_fused_score: float | None,
    score_gap: float | None,
) -> QueryEvent:
    event = QueryEvent(
        state=state,
        latency_ms=latency_ms,
        retrieved_chunk_count=retrieved_chunk_count,
        source_ids=sorted(set(source_ids)),
        source_version_ids=sorted(set(source_version_ids)),
        top_fused_score=top_fused_score,
        score_gap=score_gap,
    )
    session.add(event)
    await session.flush()
    return event


async def _count_rows(
    session: AsyncSession,
    model: type[Document | DocumentChunk | DocSource | QueryEvent],
) -> int:
    count = await session.scalar(select(func.count()).select_from(model))
    return count or 0


async def update_query_event_feedback(
    session: AsyncSession,
    *,
    event_id: UUID,
    feedback: int,
) -> QueryEvent | None:
    event = await session.get(QueryEvent, event_id)
    if event is None:
        return None
    event.feedback = feedback
    await session.flush()
    return event
