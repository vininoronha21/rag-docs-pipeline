from fastapi import APIRouter, Depends

from app.api.routes import analytics_summary, doc_sources, ingest_github, update_doc_source
from app.core.security import require_admin
from app.schemas import (
    AnalyticsSummaryResponse,
    DocSourceItem,
    DocSourceListResponse,
    IngestResponse,
)

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])

router.add_api_route(
    "/ingest/github",
    ingest_github,
    methods=["POST"],
    response_model=IngestResponse,
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
