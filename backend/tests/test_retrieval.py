import pytest

from app.services.repositories import retrieve_chunks


class FakeResult:
    def mappings(self) -> list[dict[str, object]]:
        return []


class FakeSession:
    def __init__(self) -> None:
        self.statement = ""
        self.params: dict[str, object] | None = None

    async def execute(self, statement: object, params: dict[str, object]) -> FakeResult:
        self.statement = str(statement)
        self.params = params
        return FakeResult()


@pytest.mark.asyncio
async def test_retrieve_chunks_requires_enabled_active_source_version() -> None:
    session = FakeSession()

    chunks = await retrieve_chunks(session, embedding=[0.1, 0.2], top_k=5, source="github")

    assert chunks == []
    assert "JOIN source_versions sv ON sv.id = d.source_version_id" in session.statement
    assert "JOIN doc_sources ds ON ds.id = sv.source_id" in session.statement
    assert "ds.active_version_id = sv.id" in session.statement
    assert "ds.enabled IS TRUE" in session.statement
    assert "LEFT JOIN" not in session.statement
    assert session.params == {
        "embedding": "[0.10000000,0.20000000]",
        "top_k": 5,
        "source": "github",
    }


@pytest.mark.asyncio
async def test_retrieve_chunks_can_filter_by_internal_source_id() -> None:
    session = FakeSession()

    chunks = await retrieve_chunks(
        session,
        embedding=[0.1, 0.2],
        top_k=5,
        source="github",
        source_id=17,
    )

    assert chunks == []
    assert "ds.id = :source_id" in session.statement
    assert session.params == {
        "embedding": "[0.10000000,0.20000000]",
        "top_k": 5,
        "source": "github",
        "source_id": 17,
    }
