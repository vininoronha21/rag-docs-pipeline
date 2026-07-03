import httpx
import pytest

from app.services.http_retry import is_transient_status, request_with_retry


def _response(status_code: int) -> httpx.Response:
    request = httpx.Request("GET", "https://example.test")
    return httpx.Response(status_code, request=request)


class _Recorder:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)


def test_transient_status_classification() -> None:
    assert is_transient_status(429)
    assert is_transient_status(503)
    assert not is_transient_status(200)
    assert not is_transient_status(404)


@pytest.mark.asyncio
async def test_returns_immediately_on_success_without_sleeping() -> None:
    recorder = _Recorder()
    calls = 0

    async def send() -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(200)

    response = await request_with_retry(
        send, max_retries=3, backoff_seconds=0.5, sleep=recorder.sleep
    )

    assert response.status_code == 200
    assert calls == 1
    assert recorder.delays == []


@pytest.mark.asyncio
async def test_retries_transient_status_then_succeeds() -> None:
    recorder = _Recorder()
    statuses = [503, 429, 200]

    async def send() -> httpx.Response:
        return _response(statuses.pop(0))

    response = await request_with_retry(
        send, max_retries=3, backoff_seconds=0.5, sleep=recorder.sleep
    )

    assert response.status_code == 200
    assert recorder.delays == [0.5, 1.0]  # exponential backoff


@pytest.mark.asyncio
async def test_returns_last_transient_response_when_retries_exhausted() -> None:
    recorder = _Recorder()

    async def send() -> httpx.Response:
        return _response(503)

    response = await request_with_retry(
        send, max_retries=2, backoff_seconds=0.1, sleep=recorder.sleep
    )

    assert response.status_code == 503
    assert len(recorder.delays) == 2


@pytest.mark.asyncio
async def test_retries_request_error_then_succeeds() -> None:
    recorder = _Recorder()
    attempts = 0

    async def send() -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("boom")
        return _response(200)

    response = await request_with_retry(
        send, max_retries=3, backoff_seconds=0.2, sleep=recorder.sleep
    )

    assert response.status_code == 200
    assert attempts == 3
    assert recorder.delays == [0.2, 0.4]


@pytest.mark.asyncio
async def test_raises_request_error_when_retries_exhausted() -> None:
    recorder = _Recorder()

    async def send() -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    with pytest.raises(httpx.ConnectTimeout):
        await request_with_retry(
            send, max_retries=1, backoff_seconds=0.1, sleep=recorder.sleep
        )

    assert len(recorder.delays) == 1


@pytest.mark.asyncio
async def test_no_retries_returns_first_transient_response() -> None:
    recorder = _Recorder()

    async def send() -> httpx.Response:
        return _response(500)

    response = await request_with_retry(
        send, max_retries=0, backoff_seconds=0.5, sleep=recorder.sleep
    )

    assert response.status_code == 500
    assert recorder.delays == []
