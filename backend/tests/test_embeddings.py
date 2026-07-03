import httpx
import pytest

from app.services.embeddings import (
    EmbeddingProviderError,
    LocalHashEmbeddingProvider,
    OpenAIEmbeddingProvider,
)


@pytest.mark.asyncio
async def test_local_embeddings_are_deterministic_and_normalized() -> None:
    provider = LocalHashEmbeddingProvider(dimensions=32)

    first = await provider.embed_query("FastAPI vector search")
    second = await provider.embed_query("FastAPI vector search")

    assert first == second
    assert len(first) == 32
    assert sum(value * value for value in first) == pytest.approx(1.0)


def test_local_embeddings_reject_non_positive_dimensions() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        LocalHashEmbeddingProvider(dimensions=0)


@pytest.mark.asyncio
async def test_openai_embeddings_wrap_http_status_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["timeout"] == 30

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(self, *args: object, **kwargs: object) -> httpx.Response:
            assert args == ("https://api.openai.com/v1/embeddings",)
            request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
            return httpx.Response(429, request=request)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=1536,
    )

    with pytest.raises(EmbeddingProviderError, match="upstream error"):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_openai_embeddings_wrap_invalid_response_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["timeout"] == 30

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(self, *args: object, **kwargs: object) -> httpx.Response:
            request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
            return httpx.Response(200, json={"unexpected": []}, request=request)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=1536,
    )

    with pytest.raises(EmbeddingProviderError, match="invalid response"):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_openai_embeddings_wrap_invalid_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["timeout"] == 30

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(self, *args: object, **kwargs: object) -> httpx.Response:
            request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
            return httpx.Response(200, content=b"not-json", request=request)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=1536,
    )

    with pytest.raises(EmbeddingProviderError, match="invalid response"):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_openai_embeddings_reject_unexpected_embedding_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["timeout"] == 30

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(self, *args: object, **kwargs: object) -> httpx.Response:
            request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
            return httpx.Response(
                200,
                json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]},
                request=request,
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=1536,
    )

    with pytest.raises(EmbeddingProviderError, match="unexpected number"):
        await provider.embed_texts(["hello", "world"])


@pytest.mark.asyncio
async def test_openai_embeddings_reject_unexpected_vector_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["timeout"] == 30

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(self, *args: object, **kwargs: object) -> httpx.Response:
            request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
            return httpx.Response(
                200,
                json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]},
                request=request,
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=3,
    )

    with pytest.raises(EmbeddingProviderError, match="unexpected dimensions"):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_openai_embeddings_reject_non_numeric_vectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["timeout"] == 30

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(self, *args: object, **kwargs: object) -> httpx.Response:
            request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
            return httpx.Response(
                200,
                json={"data": [{"index": 0, "embedding": [1.0, "bad"]}]},
                request=request,
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=2,
    )

    with pytest.raises(EmbeddingProviderError, match="invalid embedding vectors"):
        await provider.embed_texts(["hello"])


class _SleepRecorder:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)


@pytest.mark.asyncio
async def test_openai_embeddings_retry_transient_status_then_succeed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _SleepRecorder()
    responses = [429, 503, 200]

    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["timeout"] == 30

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(self, *args: object, **kwargs: object) -> httpx.Response:
            request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
            status = responses.pop(0)
            if status == 200:
                return httpx.Response(
                    200,
                    json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]},
                    request=request,
                )
            return httpx.Response(status, request=request)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=2,
        max_retries=3,
        backoff_seconds=0.5,
        sleep=recorder.sleep,
    )

    embeddings = await provider.embed_texts(["hello"])

    assert embeddings == [[1.0, 0.0]]
    assert recorder.delays == [0.5, 1.0]


@pytest.mark.asyncio
async def test_openai_embeddings_retry_network_error_then_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _SleepRecorder()

    class FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["timeout"] == 30

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(self, *args: object, **kwargs: object) -> httpx.Response:
            raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=2,
        max_retries=2,
        backoff_seconds=0.1,
        sleep=recorder.sleep,
    )

    with pytest.raises(EmbeddingProviderError, match="Could not reach"):
        await provider.embed_texts(["hello"])

    assert recorder.delays == [0.1, 0.2]
