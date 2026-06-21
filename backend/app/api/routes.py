import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.schemas import (
    AnalyticsSummaryResponse,
    Citation,
    DocSourceItem,
    DocSourceListResponse,
    DocSourceUpdateRequest,
    GithubIngestRequest,
    HealthResponse,
    IngestedDocument,
    IngestResponse,
    QueryFeedbackRequest,
    QueryFeedbackResponse,
    QueryHistoryItem,
    QueryHistoryResponse,
    QueryRequest,
    QueryResponse,
)
from app.services.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderError,
    build_embedding_provider,
)
from app.services.pipeline import ingest_github_repository
from app.services.querying import run_query
from app.services.repositories import (
    get_analytics_summary,
    list_doc_sources,
    list_queries,
    update_doc_source_enabled,
    update_query_feedback,
)

router = APIRouter()


def get_embedding_provider(settings: Settings = Depends(get_settings)) -> EmbeddingProvider:
    try:
        return build_embedding_provider(settings)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding provider is not configured correctly: {exc}",
        ) from exc


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name, environment=settings.environment)


@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
async def analytics_summary(
    session: AsyncSession = Depends(get_session),
) -> AnalyticsSummaryResponse:
    summary = await get_analytics_summary(session)
    return AnalyticsSummaryResponse(
        document_count=summary.document_count,
        chunk_count=summary.chunk_count,
        source_count=summary.source_count,
        enabled_source_count=summary.enabled_source_count,
        query_count=summary.query_count,
        average_latency_ms=summary.average_latency_ms,
        positive_feedback_count=summary.positive_feedback_count,
        negative_feedback_count=summary.negative_feedback_count,
    )


@router.post("/ingest/github", response_model=IngestResponse)
async def ingest_github(
    payload: GithubIngestRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    embeddings: EmbeddingProvider = Depends(get_embedding_provider),
) -> IngestResponse:
    try:
        repository, results = await ingest_github_repository(
            session,
            settings=settings,
            embeddings=embeddings,
            repo_url=str(payload.repo_url),
            branch=payload.branch,
            path=payload.path,
            max_files=payload.max_files,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except EmbeddingProviderError as exc:
        raise _embedding_provider_exception(exc) from exc
    except httpx.HTTPStatusError as exc:
        raise _github_http_exception(exc) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach GitHub. Try again later.",
        ) from exc

    documents = [
        IngestedDocument(
            source_url=result.source_url,
            title=result.title,
            chunk_count=result.chunk_count,
        )
        for result in results
    ]
    return IngestResponse(
        repository=repository,
        documents=documents,
        total_chunks=sum(document.chunk_count for document in documents),
    )


def _github_http_exception(exc: httpx.HTTPStatusError) -> HTTPException:
    status_code = exc.response.status_code
    if status_code == status.HTTP_404_NOT_FOUND:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GitHub repository, branch, or path was not found.",
        )
    if status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub rejected the request. Check credentials or rate limits.",
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="GitHub returned an upstream error. Try again later.",
    )


def _embedding_provider_exception(exc: EmbeddingProviderError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=str(exc),
    )


@router.get("/sources", response_model=DocSourceListResponse)
async def doc_sources(session: AsyncSession = Depends(get_session)) -> DocSourceListResponse:
    sources = await list_doc_sources(session)
    return DocSourceListResponse(
        items=[
            DocSourceItem(
                id=source.id,
                source_type=source.source_type,
                source_config=source.source_config,
                last_sync=source.last_sync,
                enabled=source.enabled,
            )
            for source in sources
        ]
    )


@router.patch("/sources/{source_id}", response_model=DocSourceItem)
async def update_doc_source(
    source_id: int,
    payload: DocSourceUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> DocSourceItem:
    source = await update_doc_source_enabled(
        session,
        source_id=source_id,
        enabled=payload.enabled,
    )
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document source not found.",
        )
    await session.commit()
    return DocSourceItem(
        id=source.id,
        source_type=source.source_type,
        source_config=source.source_config,
        last_sync=source.last_sync,
        enabled=source.enabled,
    )


@router.post("/query", response_model=QueryResponse)
async def query_docs(
    payload: QueryRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    embeddings: EmbeddingProvider = Depends(get_embedding_provider),
) -> QueryResponse:
    try:
        result = await run_query(
            session,
            question=payload.question,
            top_k=payload.top_k,
            source=payload.source,
            settings=settings,
            embeddings=embeddings,
        )
    except EmbeddingProviderError as exc:
        raise _embedding_provider_exception(exc) from exc
    return QueryResponse(
        query_id=result.query_id,
        answer=result.answer,
        retrieved_chunk_ids=result.retrieved_chunk_ids,
        latency_ms=result.latency_ms,
        retrieved_chunk_count=result.retrieved_chunk_count,
        citations=[
            Citation(
                chunk_id=chunk.id,
                title=chunk.title,
                source_url=chunk.source_url,
                score=chunk.score,
                metadata=chunk.metadata,
            )
            for chunk in result.chunks
        ],
    )


@router.get("/queries", response_model=QueryHistoryResponse)
async def query_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> QueryHistoryResponse:
    queries, total = await list_queries(session, limit=limit, offset=offset)
    return QueryHistoryResponse(
        items=[
            QueryHistoryItem(
                id=query.id,
                question=query.user_query,
                answer=query.llm_response,
                retrieved_chunk_ids=query.retrieved_chunks_ids,
                feedback=query.user_feedback,
                latency_ms=query.latency_ms,
                retrieved_chunk_count=query.retrieved_chunk_count,
                created_at=query.created_at,
            )
            for query in queries
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/queries/{query_id}/feedback", response_model=QueryFeedbackResponse)
async def record_query_feedback(
    query_id: int,
    payload: QueryFeedbackRequest,
    session: AsyncSession = Depends(get_session),
) -> QueryFeedbackResponse:
    query = await update_query_feedback(
        session,
        query_id=query_id,
        feedback=payload.feedback,
    )
    if query is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Query not found.",
        )
    await session.commit()
    return QueryFeedbackResponse(query_id=query.id, feedback=query.user_feedback)
