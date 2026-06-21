import pytest

from app.api import routes
from app.schemas import AnalyticsSummaryResponse
from app.services.repositories import AnalyticsSummary


@pytest.mark.asyncio
async def test_analytics_summary_route_returns_aggregate_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = AnalyticsSummary(
        document_count=10,
        chunk_count=120,
        source_count=3,
        enabled_source_count=2,
        query_count=8,
        average_latency_ms=41.25,
        positive_feedback_count=5,
        negative_feedback_count=1,
    )

    async def fake_get_analytics_summary(session: object) -> AnalyticsSummary:
        assert session == "session"
        return summary

    monkeypatch.setattr(routes, "get_analytics_summary", fake_get_analytics_summary)

    response = await routes.analytics_summary(session="session")

    assert response == AnalyticsSummaryResponse(
        document_count=10,
        chunk_count=120,
        source_count=3,
        enabled_source_count=2,
        query_count=8,
        average_latency_ms=41.25,
        positive_feedback_count=5,
        negative_feedback_count=1,
    )
