from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.api import admin_routes, routes
from app.core.config import Settings


def build_limiter(
    *,
    max_requests: int,
    window_seconds: int,
    monotonic,
):
    try:
        from app.core.rate_limit import InMemoryRateLimiter
    except ModuleNotFoundError as exc:
        pytest.fail(f"rate limiter module is missing: {exc}")

    return InMemoryRateLimiter(
        max_requests=max_requests,
        window_seconds=window_seconds,
        monotonic=monotonic,
    )


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def request_for(host: str, headers: dict[str, str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=host), headers=headers or {})


def always_limited() -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="limited",
    )


@pytest.mark.asyncio
async def test_limiter_blocks_after_limit_and_resets_after_window() -> None:
    clock = FakeClock()
    limiter = build_limiter(max_requests=2, window_seconds=60, monotonic=clock.monotonic)
    request = request_for("198.51.100.10")

    await limiter(request)
    await limiter(request)

    with pytest.raises(HTTPException) as exc_info:
        await limiter(request)

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert exc_info.value.detail == "Rate limit exceeded. Try again later."

    clock.advance(60)

    await limiter(request)


@pytest.mark.asyncio
async def test_limiter_isolates_different_client_hosts() -> None:
    clock = FakeClock()
    limiter = build_limiter(max_requests=1, window_seconds=60, monotonic=clock.monotonic)

    await limiter(request_for("198.51.100.10"))

    with pytest.raises(HTTPException):
        await limiter(request_for("198.51.100.10"))

    await limiter(request_for("203.0.113.25"))


@pytest.mark.asyncio
async def test_limiter_uses_client_host_not_caller_supplied_headers() -> None:
    clock = FakeClock()
    limiter = build_limiter(max_requests=1, window_seconds=60, monotonic=clock.monotonic)

    await limiter(
        request_for(
            "198.51.100.10",
            headers={"x-forwarded-for": "203.0.113.1"},
        )
    )

    with pytest.raises(HTTPException):
        await limiter(
            request_for(
                "198.51.100.10",
                headers={"x-forwarded-for": "203.0.113.2"},
            )
        )


@pytest.mark.asyncio
async def test_limiter_does_not_retain_raw_client_host_in_state_keys() -> None:
    clock = FakeClock()
    limiter = build_limiter(max_requests=2, window_seconds=60, monotonic=clock.monotonic)
    raw_host = "198.51.100.10"

    await limiter(request_for(raw_host))

    assert raw_host not in limiter._requests
    assert all(raw_host not in key for key in limiter._requests)


@pytest.mark.asyncio
async def test_limiter_removes_empty_stale_client_queues_when_handling_requests() -> None:
    clock = FakeClock()
    limiter = build_limiter(max_requests=2, window_seconds=60, monotonic=clock.monotonic)

    await limiter(request_for("198.51.100.10"))
    await limiter(request_for("203.0.113.25"))
    stale_keys = set(limiter._requests)

    clock.advance(60)
    await limiter(request_for("192.0.2.44"))

    assert stale_keys
    assert stale_keys.isdisjoint(limiter._requests)
    assert len(limiter._requests) == 1


def test_rate_limit_settings_match_portfolio_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.query_rate_limit_per_minute == 20
    assert settings.feedback_rate_limit_per_minute == 30
    assert settings.sync_rate_limit_per_minute == 2


def test_query_route_uses_query_rate_limit_dependency() -> None:
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    assert hasattr(routes, "query_rate_limit")
    app.dependency_overrides[routes.query_rate_limit] = always_limited

    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/query",
        json={"question": "How do I run the project?", "top_k": 5},
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["detail"] == "limited"


def test_feedback_route_uses_feedback_rate_limit_dependency() -> None:
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    assert hasattr(routes, "feedback_rate_limit")
    app.dependency_overrides[routes.feedback_rate_limit] = always_limited

    response = TestClient(app, raise_server_exceptions=False).patch(
        f"/api/query-events/{uuid4()}/feedback",
        json={"feedback": 1},
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["detail"] == "limited"


def test_admin_sync_route_uses_sync_rate_limit_dependency() -> None:
    app = FastAPI()
    app.include_router(admin_routes.router, prefix="/api")
    app.dependency_overrides[admin_routes.require_admin] = lambda: None
    assert hasattr(admin_routes, "sync_rate_limit")
    app.dependency_overrides[admin_routes.sync_rate_limit] = always_limited

    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/admin/ingest/github",
        json={"repo_url": "https://github.com/example/project", "path": "docs"},
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["detail"] == "limited"
