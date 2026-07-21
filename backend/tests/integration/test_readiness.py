import os

import httpx
import pytest
from fastapi import status

from app.db import session as db_session
from app.db.session import get_session
from app.main import create_app


@pytest.mark.integration
async def test_ready_uses_real_database_and_pgvector(sync_connection) -> None:
    assert sync_connection is not None
    engine = db_session.create_async_engine(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
    session_factory = db_session.async_sessionmaker(engine, expire_on_commit=False)

    async def test_session():
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = test_session
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/ready")
    finally:
        await engine.dispose()

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ready", "database": "ok", "pgvector": "ok"}
