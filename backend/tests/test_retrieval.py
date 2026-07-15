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


def retrieval_kwargs() -> dict[str, object]:
    return {
        "question": "como executar",
        "embedding": [0.1, 0.2],
        "top_k": 5,
        "candidate_k": 20,
        "rrf_k": 60,
        "vector_weight": 0.7,
        "text_weight": 0.3,
    }


@pytest.mark.asyncio
async def test_retrieve_chunks_requires_enabled_active_source_version() -> None:
    session = FakeSession()

    chunks = await retrieve_chunks(
        session,
        question="como executar",
        embedding=[0.1, 0.2],
        top_k=5,
        candidate_k=20,
        rrf_k=60,
        vector_weight=0.7,
        text_weight=0.3,
        source="github",
    )

    assert chunks == []
    assert session.statement.count("JOIN source_versions sv ON sv.id = d.source_version_id") == 3
    assert session.statement.count("JOIN doc_sources ds ON ds.id = sv.source_id") == 3
    assert session.statement.count("ds.active_version_id = sv.id") == 2
    assert session.statement.count("ds.enabled IS TRUE") == 2
    assert "websearch_to_tsquery('portuguese', :question)" in session.statement
    assert "dc.embedding <=> (:embedding)::vector" in session.statement
    assert "ORDER BY fused_score DESC, dc.id ASC" in session.statement
    assert session.params == {
        "embedding": "[0.10000000,0.20000000]",
        "question": "como executar",
        "top_k": 5,
        "candidate_k": 20,
        "rrf_k": 60,
        "vector_weight": 0.7,
        "text_weight": 0.3,
        "source": "github",
    }


@pytest.mark.asyncio
async def test_retrieve_chunks_can_filter_by_internal_source_id() -> None:
    session = FakeSession()

    chunks = await retrieve_chunks(
        session,
        question="como executar",
        embedding=[0.1, 0.2],
        top_k=5,
        candidate_k=20,
        rrf_k=60,
        vector_weight=0.7,
        text_weight=0.3,
        source="github",
        source_id=17,
    )

    assert chunks == []
    assert session.statement.count("ds.id = :source_id") == 2
    assert session.statement.count("d.source = :source") == 2
    assert session.params == {
        "embedding": "[0.10000000,0.20000000]",
        "question": "como executar",
        "top_k": 5,
        "candidate_k": 20,
        "rrf_k": 60,
        "vector_weight": 0.7,
        "text_weight": 0.3,
        "source": "github",
        "source_id": 17,
    }


@pytest.mark.asyncio
async def test_retrieve_chunks_requires_more_candidates_than_results() -> None:
    with pytest.raises(ValueError, match="candidate_k must be greater than top_k"):
        await retrieve_chunks(
            FakeSession(),
            question="como executar",
            embedding=[0.1, 0.2],
            top_k=5,
            candidate_k=5,
            rrf_k=60,
            vector_weight=0.7,
            text_weight=0.3,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("top_k", [0, -1])
async def test_retrieve_chunks_requires_positive_top_k(top_k: int) -> None:
    kwargs = retrieval_kwargs()
    kwargs["top_k"] = top_k

    with pytest.raises(ValueError, match="top_k must be at least 1"):
        await retrieve_chunks(FakeSession(), **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("rrf_k", [0, -1])
async def test_retrieve_chunks_requires_positive_rrf_k(rrf_k: int) -> None:
    kwargs = retrieval_kwargs()
    kwargs["rrf_k"] = rrf_k

    with pytest.raises(ValueError, match="rrf_k must be greater than 0"):
        await retrieve_chunks(FakeSession(), **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["vector_weight", "text_weight"])
@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf"), float("-inf")])
async def test_retrieve_chunks_requires_positive_finite_weights(
    field: str, value: float
) -> None:
    kwargs = retrieval_kwargs()
    kwargs[field] = value

    with pytest.raises(ValueError, match=rf"{field} must be finite and greater than 0"):
        await retrieve_chunks(FakeSession(), **kwargs)


@pytest.mark.asyncio
async def test_retrieve_chunks_requires_non_empty_embedding() -> None:
    kwargs = retrieval_kwargs()
    kwargs["embedding"] = []

    with pytest.raises(ValueError, match="embedding must not be empty"):
        await retrieve_chunks(FakeSession(), **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
async def test_retrieve_chunks_requires_finite_embedding_values(value: float) -> None:
    kwargs = retrieval_kwargs()
    kwargs["embedding"] = [0.1, value]

    with pytest.raises(ValueError, match="embedding values must be finite"):
        await retrieve_chunks(FakeSession(), **kwargs)
