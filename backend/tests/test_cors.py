from fastapi.testclient import TestClient

from app import main
from app.core.config import Settings


def test_cors_allows_exact_origin_without_credentials_or_wildcards(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: Settings(
            allowed_origins=["https://docs.example.com"],
            _env_file=None,
        ),
    )

    response = TestClient(main.create_app()).options(
        "/api/query",
        headers={
            "Origin": "https://docs.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization, X-Request-ID",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://docs.example.com"
    assert "access-control-allow-credentials" not in response.headers
    assert {
        method.strip()
        for method in response.headers["access-control-allow-methods"].split(",")
    } == {"GET", "POST", "PATCH"}
    allow_headers = response.headers["access-control-allow-headers"]
    assert "*" not in allow_headers
    assert {header.strip().lower() for header in allow_headers.split(",")} >= {
        "content-type",
        "authorization",
        "x-request-id",
    }


def test_cors_rejects_unconfigured_origin(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: Settings(
            allowed_origins=["https://docs.example.com"],
            _env_file=None,
        ),
    )

    response = TestClient(main.create_app()).options(
        "/api/query",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization, X-Request-ID",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
