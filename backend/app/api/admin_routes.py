from fastapi import APIRouter, Depends

from app.api.routes import analytics_summary, doc_sources, ingest_github, update_doc_source
from app.core.config import get_settings
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import require_admin
from app.schemas import (
    AnalyticsSummaryResponse,
    DocSourceItem,
    DocSourceListResponse,
    IngestResponse,
)

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])

sync_rate_limit = InMemoryRateLimiter(
    max_requests=get_settings().sync_rate_limit_per_minute,
)

router.add_api_route(
    "/ingest/github",
    ingest_github,
    methods=["POST"],
    response_model=IngestResponse,
    dependencies=[Depends(sync_rate_limit)],
)
router.add_api_route(
    "/sources",
    doc_sources,
    methods=["GET"],
    response_model=DocSourceListResponse,
)
router.add_api_route(
    "/sources/{source_id}",
    update_doc_source,
    methods=["PATCH"],
    response_model=DocSourceItem,
)
router.add_api_route(
    "/analytics/summary",
    analytics_summary,
    methods=["GET"],
    response_model=AnalyticsSummaryResponse,
)
