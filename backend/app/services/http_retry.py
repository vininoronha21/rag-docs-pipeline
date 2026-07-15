import asyncio
from collections.abc import Awaitable, Callable

import httpx

TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def is_transient_status(status_code: int) -> bool:
    return status_code in TRANSIENT_STATUS_CODES


async def request_with_retry(
    send: Callable[[], Awaitable[httpx.Response]],
    *,
    max_retries: int,
    backoff_seconds: float,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> httpx.Response:
    """Call ``send`` and retry transient failures with exponential backoff.

    Retries on httpx transport/timeout errors (``httpx.RequestError``) and on
    transient HTTP status codes (429 and 5xx). Non-transient responses are
    returned unchanged so the caller can handle them (for example via
    ``raise_for_status``). The last response or error is surfaced once retries
    are exhausted.
    """
    attempt = 0
    while True:
        try:
            response = await send()
        except httpx.RequestError:
            if attempt >= max_retries:
                raise
        else:
            if attempt >= max_retries or not is_transient_status(
                getattr(response, "status_code", 200)
            ):
                return response
        await sleep(backoff_seconds * (2**attempt))
        attempt += 1
