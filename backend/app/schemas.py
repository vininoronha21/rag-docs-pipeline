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
    answer: str
    citations: list[Citation]
    retrieved_chunk_ids: list[int]
