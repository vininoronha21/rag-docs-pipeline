from datetime import datetime
from typing import Any, Literal
from uuid import UUID

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
    path: str = Field(min_length=1, description="Repository folder path to ingest from.")
    max_files: int = Field(default=50, ge=1, le=500)


class IngestedDocument(BaseModel):
    source_url: str
    title: str | None
    chunk_count: int


class IngestResponse(BaseModel):
    status: Literal["synchronized", "no_op"]
    repository: str
    branch: str
    path: str
    commit_sha: str
    source_id: int
    source_version_id: int
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


class AnalyticsSummaryResponse(BaseModel):
    document_count: int
    chunk_count: int
    source_count: int
    enabled_source_count: int
    query_count: int
    average_latency_ms: float
    positive_feedback_count: int
    negative_feedback_count: int


class QueryRequest(BaseModel):
    question: str = Field(min_length=2)
    top_k: int = Field(default=5, ge=1, le=12)
    source: str | None = None


class AnswerSentence(BaseModel):
    text: str
    citation_id: str


class ExtractiveAnswerResponse(BaseModel):
    sentences: list[AnswerSentence]


class EvidenceItem(BaseModel):
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


class QueryMetrics(BaseModel):
    latency_ms: int
    retrieved_chunk_count: int
    top_fused_score: float | None
    score_gap: float | None


class QueryResponse(BaseModel):
    event_id: UUID
    state: Literal["answered", "insufficient_evidence"]
    answer: ExtractiveAnswerResponse | None
    evidence: list[EvidenceItem]
    metrics: QueryMetrics


class QueryFeedbackRequest(BaseModel):
    feedback: Literal[-1, 1] = Field(
        description="Feedback score: -1 negative or 1 positive.",
    )


class QueryFeedbackResponse(BaseModel):
    event_id: UUID
    feedback: Literal[-1, 1]
