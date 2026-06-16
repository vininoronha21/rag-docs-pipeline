import pytest
from app.services.embeddings import LocalHashEmbeddingProvider


@pytest.mark.asyncio
async def test_local_embeddings_are_deterministic_and_normalized() -> None:
    provider = LocalHashEmbeddingProvider(dimensions=32)

    first = await provider.embed_query("FastAPI vector search")
    second = await provider.embed_query("FastAPI vector search")

    assert first == second
    assert len(first) == 32
    assert sum(value * value for value in first) == pytest.approx(1.0)
