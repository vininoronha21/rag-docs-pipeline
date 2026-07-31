import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NODE_IMAGE = "node:22.16.0-alpine"


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text()


def test_backend_dockerfile_pins_python_and_runs_uvicorn_as_non_root_on_port_env() -> None:
    dockerfile = _read("backend/Dockerfile")

    assert "FROM python:3.12.13-slim" in dockerfile
    assert re.search(r"^USER\s+app$", dockerfile, flags=re.MULTILINE)
    assert "python -m alembic upgrade head && exec python -m uvicorn" in dockerfile
    assert "--port ${PORT:-8000}" in dockerfile
    assert "--no-access-log" in dockerfile
    assert "--port 8000" not in dockerfile


def test_frontend_dockerfile_pins_node_and_bakes_public_backend_url_at_build() -> None:
    dockerfile = _read("frontend/Dockerfile")

    assert dockerfile.count(f"FROM {NODE_IMAGE}") == 3
    assert "ARG NEXT_PUBLIC_BACKEND_URL=http://localhost:8000" in dockerfile
    assert "NEXT_PUBLIC_BACKEND_URL=${NEXT_PUBLIC_BACKEND_URL}" in dockerfile
    assert "RUN npm run build" in dockerfile
    assert re.search(r"^USER\s+nextjs$", dockerfile, flags=re.MULTILINE)


def test_compose_preserves_database_url_driver_split_and_frontend_build_arg() -> None:
    compose = _read("docker-compose.yml")

    assert "DATABASE_URL: postgresql+asyncpg://rag:rag@postgres:5432/rag_docs" in compose
    assert (
        "MIGRATION_DATABASE_URL: postgresql+psycopg://rag:rag@postgres:5432/rag_docs"
        in compose
    )
    assert "args:" in compose
    assert "NEXT_PUBLIC_BACKEND_URL: http://localhost:8000" in compose
    assert 'ALLOWED_ORIGINS: \'["http://localhost:3000","http://127.0.0.1:3000"]\'' in compose


def test_render_manifest_declares_health_start_command_and_secret_sources() -> None:
    render = _read("render.yaml")

    assert "runtime: docker" in render
    assert "plan: free" in render
    assert "healthCheckPath: /api/health" in render
    assert "python -m alembic upgrade head" in render
    assert "exec python -m uvicorn app.main:app" in render
    assert "--port ${PORT:-8000}" in render
    assert "--no-access-log" in render
    assert "key: ADMIN_SECRET" in render
    assert "generateValue: true" in render
    assert render.count("sync: false") >= 3

    for required_key in (
        "ENVIRONMENT",
        "ADMIN_SECRET",
        "DATABASE_URL",
        "MIGRATION_DATABASE_URL",
        "ALLOWED_ORIGINS",
    ):
        assert f"key: {required_key}" in render

    assert "rag:rag" not in render
    assert "example_password" not in render


def test_vercel_manifest_requires_provider_backend_url_without_committed_placeholder() -> None:
    vercel = json.loads(_read("frontend/vercel.json"))
    manifest = _read("frontend/vercel.json")

    assert vercel["framework"] == "nextjs"
    assert "NEXT_PUBLIC_BACKEND_URL" in vercel["buildCommand"]
    assert "npm run build" in vercel["buildCommand"]
    assert "env" not in vercel or "NEXT_PUBLIC_BACKEND_URL" not in vercel.get("env", {})
    assert "your-render-service" not in manifest


def test_vercel_build_command_fails_before_build_when_backend_url_is_missing(
    tmp_path: Path,
) -> None:
    vercel = json.loads(_read("frontend/vercel.json"))
    sentinel = tmp_path / "npm-called"
    fake_npm = tmp_path / "npm"
    fake_npm.write_text(
        "#!/bin/sh\n"
        "printf called > \"$NPM_SENTINEL\"\n"
        "exit 0\n"
    )
    fake_npm.chmod(0o755)
    env = os.environ.copy()
    env.pop("NEXT_PUBLIC_BACKEND_URL", None)
    env["PATH"] = str(tmp_path)
    env["NPM_SENTINEL"] = str(sentinel)

    result = subprocess.run(
        ["/bin/sh", "-c", vercel["buildCommand"]],
        cwd=ROOT / "frontend",
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "NEXT_PUBLIC_BACKEND_URL must be set" in result.stderr
    assert not sentinel.exists()


def test_deployment_docs_cover_neon_tls_migrations_vercel_root_and_exact_cors() -> None:
    docs = _read("docs/deployment.md")

    assert "CREATE EXTENSION IF NOT EXISTS vector;" in docs
    assert "postgresql+asyncpg://" in docs
    assert "?ssl=require" in docs
    assert "postgresql+psycopg://" in docs
    assert "?sslmode=require" in docs
    assert "MIGRATION_DATABASE_URL" in docs
    assert "python -m alembic upgrade head" in docs
    assert "Project root: `frontend`" in docs
    assert "Build command:" in docs
    assert "NEXT_PUBLIC_BACKEND_URL" in docs
    assert "Render plan: `free`" in docs
    assert "your-render-service" not in docs
    assert "your-vercel-project" not in docs
    assert "*" not in docs


def test_frontend_ci_runs_typecheck_tests_and_build() -> None:
    ci = _read(".github/workflows/ci.yml")

    assert "npm run typecheck" in ci
    assert "npm run test:run" in ci
    assert "npm run build" in ci
