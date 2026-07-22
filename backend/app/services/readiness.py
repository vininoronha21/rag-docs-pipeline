import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import ReadinessResponse

logger = logging.getLogger(__name__)


async def check_readiness(session: AsyncSession, request_id: str | None) -> ReadinessResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        _log_readiness_failure(exc, request_id)
        return ReadinessResponse(status="not_ready", database="error", pgvector="unknown")

    try:
        result = await session.execute(
            text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        )
        has_pgvector = bool(result.scalar_one())
    except Exception as exc:
        _log_readiness_failure(exc, request_id)
        return ReadinessResponse(status="not_ready", database="ok", pgvector="error")

    if not has_pgvector:
        return ReadinessResponse(status="not_ready", database="ok", pgvector="missing")

    return ReadinessResponse(status="ready", database="ok", pgvector="ok")


def _log_readiness_failure(exc: Exception, request_id: str | None) -> None:
    logger.warning(
        "Readiness check failed",
        extra={"exception_class": exc.__class__.__name__, "request_id": request_id},
    )
