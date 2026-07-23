import time
from dataclasses import dataclass
from urllib.parse import quote
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.services.embeddings import EmbeddingProvider
from app.services.rag import (
    ExtractiveAnswer,
    answer_has_query_term_support,
    build_extractive_answer,
    filter_chunks_by_min_score,
    filter_prompt_injection_chunks,
)
from app.services.repositories import (
    EvidenceState,
    RetrievedChunk,
    log_query_event,
    retrieve_chunks,
)


@dataclass(frozen=True)
class Evidence:
    citation_id: str | None
    supported_text: str | None
    excerpt: str
    title: str | None
    repository_path: str
    section: str | None
    commit_sha: str
    source_url: str
    vector_score: float | None
    text_score: float | None
    fused_score: float
    chunk_id: int


@dataclass(frozen=True)
class QueryExecutionMetrics:
    latency_ms: int
    retrieved_chunk_count: int
    top_fused_score: float | None
    score_gap: float | None


@dataclass(frozen=True)
class QueryExecutionResult:
    event_id: UUID
    state: EvidenceState
    answer: ExtractiveAnswer | None
    evidence: list[Evidence]
    metrics: QueryExecutionMetrics


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

    top_fused_score = chunks[0].fused_score if chunks else None
    score_gap = chunks[0].fused_score - chunks[1].fused_score if len(chunks) > 1 else None
    meets_retrieval_thresholds = top_fused_score is not None and (
        top_fused_score >= settings.retrieval_min_fused_score
        and (score_gap is None or score_gap >= settings.retrieval_min_score_gap)
    )
    candidate_answer = (
        build_extractive_answer(question, chunks) if meets_retrieval_thresholds else None
    )
    used_chunk_ids = (
        {sentence.chunk_id for sentence in candidate_answer.sentences}
        if candidate_answer is not None
        else set()
    )
    has_lexical_support = any(
        chunk.id in used_chunk_ids and chunk.text_score is not None and chunk.text_score > 0
        for chunk in chunks
    )
    has_sentence_support = (
        candidate_answer is not None
        and answer_has_query_term_support(question, candidate_answer)
    )
    state: EvidenceState = (
        "answered"
        if has_sentence_support or has_lexical_support
        else "insufficient_evidence"
    )
    answer = candidate_answer if state == "answered" else None
    evidence = (
        _build_answer_evidence(answer, chunks)
        if answer is not None
        else [_build_evidence(chunk, citation_id=None, supported_text=None) for chunk in chunks]
    )

    latency_ms = round((time.perf_counter() - started_at) * 1000)
    metrics = QueryExecutionMetrics(
        latency_ms=latency_ms,
        retrieved_chunk_count=len(chunks),
        top_fused_score=top_fused_score,
        score_gap=score_gap,
    )
    try:
        event = await log_query_event(
            session,
            state=state,
            latency_ms=latency_ms,
            retrieved_chunk_count=len(chunks),
            source_ids=sorted({chunk.source_id for chunk in chunks}),
            source_version_ids=sorted({chunk.source_version_id for chunk in chunks}),
            top_fused_score=top_fused_score,
            score_gap=score_gap,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return QueryExecutionResult(
        event_id=event.id,
        state=state,
        answer=answer,
        evidence=evidence,
        metrics=metrics,
    )


def _build_answer_evidence(
    answer: ExtractiveAnswer,
    chunks: list[RetrievedChunk],
) -> list[Evidence]:
    used_chunk_ids = list(dict.fromkeys(sentence.chunk_id for sentence in answer.sentences))
    chunks_by_id = {chunk.id: chunk for chunk in chunks}
    return [
        _build_evidence(
            chunks_by_id[chunk_id],
            citation_id=f"citation-{index}",
            supported_text=" ".join(
                sentence.text for sentence in answer.sentences if sentence.chunk_id == chunk_id
            ),
        )
        for index, chunk_id in enumerate(used_chunk_ids, start=1)
        if chunk_id in chunks_by_id
    ]


def _build_evidence(
    chunk: RetrievedChunk,
    *,
    citation_id: str | None,
    supported_text: str | None,
) -> Evidence:
    section = chunk.metadata.get("section")
    return Evidence(
        citation_id=citation_id,
        supported_text=supported_text,
        excerpt=chunk.text,
        title=chunk.title,
        repository_path=chunk.repository_path,
        section=str(section) if section is not None else None,
        commit_sha=chunk.commit_sha,
        source_url=_immutable_source_url(chunk),
        vector_score=chunk.vector_score,
        text_score=chunk.text_score,
        fused_score=chunk.fused_score,
        chunk_id=chunk.id,
    )


def _immutable_source_url(chunk: RetrievedChunk) -> str:
    if chunk.source == "github":
        encoded_path = quote(chunk.repository_path, safe="/")
        return (
            f"https://github.com/{chunk.repository}/blob/"
            f"{chunk.commit_sha}/{encoded_path}"
        )
    return chunk.source_url
