from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.observability import get_request_id, set_query_log_context
from app.core.rate_limit import InMemoryRateLimiter
from app.db.session import get_session
from app.schemas import (
    AnalyticsSummaryResponse,
    AnswerSentence,
    DocSourceItem,
    DocSourceListResponse,
    DocSourceUpdateRequest,
    EvidenceItem,
    ExtractiveAnswerResponse,
    GithubIngestRequest,
    HealthResponse,
    IngestedDocument,
    IngestResponse,
    QueryFeedbackRequest,
    QueryFeedbackResponse,
    QueryMetrics,
    QueryRequest,
    QueryResponse,
    ReadinessResponse,
)
from app.services.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderError,
    build_embedding_provider,
)
from app.services.github import GithubClientError
from app.services.pipeline import SourceSynchronizationConflict, ingest_github_repository
from app.services.querying import run_query
from app.services.readiness import check_readiness
from app.services.repositories import (
    get_analytics_summary,
    list_doc_sources,
    update_doc_source_enabled,
    update_query_event_feedback,
)

router = APIRouter()

query_rate_limit = InMemoryRateLimiter(
    max_requests=get_settings().query_rate_limit_per_minute,
)
feedback_rate_limit = InMemoryRateLimiter(
    max_requests=get_settings().feedback_rate_limit_per_minute,
)


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


@router.get("/ready", response_model=ReadinessResponse)
async def ready(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> ReadinessResponse:
    request_id = get_request_id(request)
    readiness = ReadinessResponse.model_validate(
        await check_readiness(session, request_id=request_id)
    )
    if readiness.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return readiness


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


async def ingest_github(
    payload: GithubIngestRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    embeddings: EmbeddingProvider = Depends(get_embedding_provider),
) -> IngestResponse:
    try:
        result = await ingest_github_repository(
            session,
            settings=settings,
            embeddings=embeddings,
            repo_url=str(payload.repo_url),
            branch=payload.branch,
            path=payload.path,
            max_files=payload.max_files,
        )
    except SourceSynchronizationConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source changed during synchronization. Retry the request.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except EmbeddingProviderError as exc:
        raise _embedding_provider_exception(exc) from exc
    except GithubClientError as exc:
        raise _github_client_exception(exc) from exc
    except httpx.HTTPStatusError as exc:
        raise _github_http_exception(exc) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach GitHub. Try again later.",
        ) from exc

    documents = [
        IngestedDocument(
            source_url=document.source_url,
            title=document.title,
            chunk_count=document.chunk_count,
        )
        for document in result.documents
    ]
    return IngestResponse(
        status=result.status,
        repository=result.repository,
        branch=result.branch,
        path=result.path,
        commit_sha=result.commit_sha,
        source_id=result.source_id,
        source_version_id=result.source_version_id,
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


def _github_client_exception(exc: GithubClientError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=str(exc),
    )


def _embedding_provider_exception(exc: EmbeddingProviderError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=str(exc),
    )


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


@router.post("/query", response_model=QueryResponse, dependencies=[Depends(query_rate_limit)])
async def query_docs(
    payload: QueryRequest,
    request: Request = None,
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
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    citation_ids = {
        item.chunk_id: item.citation_id
        for item in result.evidence
        if item.citation_id is not None
    }
    answer = None
    if result.answer is not None:
        answer = ExtractiveAnswerResponse(
            sentences=[
                AnswerSentence(text=sentence.text, citation_id=citation_ids[sentence.chunk_id])
                for sentence in result.answer.sentences
            ]
        )
    response = QueryResponse(
        event_id=result.event_id,
        state=result.state,
        answer=answer,
        evidence=[
            EvidenceItem(
                citation_id=item.citation_id,
                supported_text=item.supported_text,
                excerpt=item.excerpt,
                title=item.title,
                repository_path=item.repository_path,
                section=item.section,
                commit_sha=item.commit_sha,
                source_url=item.source_url,
                vector_score=item.vector_score,
                text_score=item.text_score,
                fused_score=item.fused_score,
            )
            for item in result.evidence
        ],
        metrics=QueryMetrics(
            latency_ms=result.metrics.latency_ms,
            retrieved_chunk_count=result.metrics.retrieved_chunk_count,
            top_fused_score=result.metrics.top_fused_score,
            score_gap=result.metrics.score_gap,
        ),
    )
    set_query_log_context(
        request,
        event_id=response.event_id,
        evidence_state=response.state,
    )
    return response


@router.patch(
    "/query-events/{event_id}/feedback",
    response_model=QueryFeedbackResponse,
    dependencies=[Depends(feedback_rate_limit)],
)
async def record_query_feedback(
    event_id: UUID,
    payload: QueryFeedbackRequest,
    session: AsyncSession = Depends(get_session),
) -> QueryFeedbackResponse:
    event = await update_query_event_feedback(
        session,
        event_id=event_id,
        feedback=payload.feedback,
    )
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Query event not found.",
        )
    await session.commit()
    return QueryFeedbackResponse(event_id=event.id, feedback=event.feedback)
