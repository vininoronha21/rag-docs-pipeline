from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RAG Docs Pipeline"
    environment: Literal["local", "test", "production"] = "local"
    api_prefix: str = "/api"

    database_url: str = Field(
        default="postgresql+asyncpg://rag:rag@localhost:5432/rag_docs",
        description="Async SQLAlchemy database URL.",
    )

    github_token: str | None = None
    github_user_agent: str = "rag-docs-pipeline"

    embedding_provider: Literal["local", "openai"] = "local"
    embedding_dimensions: int = 1536
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"

    llm_provider: Literal["extractive", "openai"] = "extractive"
    openai_chat_model: str = "gpt-4.1-mini"

    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    public_backend_url: HttpUrl | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
