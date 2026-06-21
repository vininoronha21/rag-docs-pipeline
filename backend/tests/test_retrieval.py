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
async def test_retrieve_chunks_filters_disabled_linked_sources() -> None:
    session = FakeSession()

    chunks = await retrieve_chunks(session, embedding=[0.1, 0.2], top_k=5, source="github")

    assert chunks == []
    assert "LEFT JOIN doc_sources ds ON ds.id = d.doc_source_id" in session.statement
    assert "(d.doc_source_id IS NULL OR ds.enabled IS TRUE)" in session.statement
    assert session.params == {
        "embedding": "[0.10000000,0.20000000]",
        "top_k": 5,
        "source": "github",
    }
