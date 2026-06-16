from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.schemas import (
    Citation,
    GithubIngestRequest,
    HealthResponse,
    IngestedDocument,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)
from app.services.embeddings import EmbeddingProvider, build_embedding_provider
from app.services.pipeline import ingest_github_repository
from app.services.rag import build_extractive_answer
from app.services.repositories import log_query, retrieve_chunks

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
    repository, results = await ingest_github_repository(
        session,
        settings=settings,
        embeddings=embeddings,
        repo_url=str(payload.repo_url),
        branch=payload.branch,
        path=payload.path,
        max_files=payload.max_files,
    )
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


@router.post("/query", response_model=QueryResponse)
async def query_docs(
    payload: QueryRequest,
    session: AsyncSession = Depends(get_session),
    embeddings: EmbeddingProvider = Depends(get_embedding_provider),
) -> QueryResponse:
    query_embedding = await embeddings.embed_query(payload.question)
    chunks = await retrieve_chunks(
        session,
        embedding=query_embedding,
        top_k=payload.top_k,
        source=payload.source,
    )
    answer = build_extractive_answer(payload.question, chunks)
    chunk_ids = [chunk.id for chunk in chunks]
    await log_query(
        session,
        question=payload.question,
        retrieved_chunk_ids=chunk_ids,
        answer=answer,
    )
    await session.commit()

    return QueryResponse(
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
