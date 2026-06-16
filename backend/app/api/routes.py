import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.schemas import (
    Citation,
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
from app.services.embeddings import EmbeddingProvider, build_embedding_provider
from app.services.pipeline import ingest_github_repository
from app.services.rag import build_extractive_answer, filter_chunks_by_min_score
from app.services.repositories import (
    list_queries,
    log_query,
    retrieve_chunks,
    update_query_feedback,
)

router = APIRouter()


def get_embedding_provider(settings: Settings = Depends(get_settings)) -> EmbeddingProvider:
    return build_embedding_provider(settings)


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name, environment=settings.environment)


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


@router.post("/query", response_model=QueryResponse)
async def query_docs(
    payload: QueryRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    embeddings: EmbeddingProvider = Depends(get_embedding_provider),
) -> QueryResponse:
    query_embedding = await embeddings.embed_query(payload.question)
    chunks = await retrieve_chunks(
        session,
        embedding=query_embedding,
        top_k=payload.top_k,
        source=payload.source,
    )
    chunks = filter_chunks_by_min_score(chunks, min_score=settings.retrieval_min_score)
    answer = build_extractive_answer(payload.question, chunks)
    chunk_ids = [chunk.id for chunk in chunks]
    query_log = await log_query(
        session,
        question=payload.question,
        retrieved_chunk_ids=chunk_ids,
        answer=answer,
    )
    await session.commit()

    return QueryResponse(
        query_id=query_log.id,
        answer=answer,
        retrieved_chunk_ids=chunk_ids,
        citations=[
            Citation(
                chunk_id=chunk.id,
                title=chunk.title,
                source_url=chunk.source_url,
                score=chunk.score,
                metadata=chunk.metadata,
            )
            for chunk in chunks
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
