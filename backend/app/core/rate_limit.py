import asyncio
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    def __init__(
        self,
        *,
        max_requests: int,
        window_seconds: int = 60,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._monotonic = monotonic
        self._requests: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def __call__(self, request: Request) -> None:
        client = request.client
        client_key = client.host if client is not None else ""
        now = self._monotonic()
        cutoff = now - self.window_seconds

        async with self._lock:
            timestamps = self._requests.setdefault(client_key, deque())
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= self.max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Try again later.",
                )

            timestamps.append(now)
