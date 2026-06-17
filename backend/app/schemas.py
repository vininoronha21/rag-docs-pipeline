from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str


class GithubIngestRequest(BaseModel):
    repo_url: HttpUrl = Field(
        examples=["https://github.com/tiangolo/fastapi"],
        description="GitHub repository URL.",
    )
    branch: str | None = Field(
        default=None,
        description="Branch or tag. Defaults to repo default branch.",
    )
    path: str = Field(default="", description="Optional folder path to ingest from.")
    max_files: int = Field(default=50, ge=1, le=500)


class IngestedDocument(BaseModel):
    source_url: str
    title: str | None
    chunk_count: int


class IngestResponse(BaseModel):
    repository: str
    documents: list[IngestedDocument]
    total_chunks: int


class DocSourceItem(BaseModel):
    id: int
    source_type: str
    source_config: dict[str, Any]
    last_sync: datetime | None
    enabled: bool


class DocSourceListResponse(BaseModel):
    items: list[DocSourceItem]


class DocSourceUpdateRequest(BaseModel):
    enabled: bool


class QueryRequest(BaseModel):
    question: str = Field(min_length=2)
    top_k: int = Field(default=5, ge=1, le=12)
    source: str | None = None


class Citation(BaseModel):
    chunk_id: int
    title: str | None
    source_url: str
    score: float
    metadata: dict[str, Any]


class QueryResponse(BaseModel):
    query_id: int
    answer: str
    citations: list[Citation]
    retrieved_chunk_ids: list[int]
    latency_ms: int
    retrieved_chunk_count: int


class QueryFeedbackRequest(BaseModel):
    feedback: int = Field(
        ge=-1,
        le=1,
        description="Feedback score: -1 negative, 0 neutral/reset, 1 positive.",
    )


class QueryFeedbackResponse(BaseModel):
    query_id: int
    feedback: int


class QueryHistoryItem(BaseModel):
    id: int
    question: str
    answer: str
    retrieved_chunk_ids: list[int]
    feedback: int | None
    latency_ms: int
    retrieved_chunk_count: int
    created_at: datetime


class QueryHistoryResponse(BaseModel):
    items: list[QueryHistoryItem]
    total: int
    limit: int
    offset: int
