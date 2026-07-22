import json
import logging
import time
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger(__name__)


def validate_request_id(value: str | None) -> str:
    if value:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return str(uuid4())


def get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if request_id is None:
        request_id = validate_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
    return str(request_id)


def set_query_log_context(
    request: Request | None,
    *,
    event_id: UUID,
    evidence_state: str,
) -> None:
    if request is None:
        return
    request.state.query_event_id = str(event_id)
    request.state.evidence_state = evidence_state


class RequestObservabilityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = validate_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        scope.setdefault("state", {})["request_id"] = request_id
        started_at = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            self._log_completion(
                scope=scope,
                request_id=request_id,
                status_code=status_code,
                duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
            )

    def _log_completion(
        self,
        *,
        scope: Scope,
        request_id: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        state = scope.get("state") or {}
        event: dict[str, Any] = {
            "event": "request_completed",
            "route": _route_template(scope),
            "status": status_code,
            "duration_ms": duration_ms,
            "request_id": request_id,
        }

        query_event_id = state.get("query_event_id")
        evidence_state = state.get("evidence_state")
        if query_event_id is not None:
            event["event_id"] = query_event_id
        if evidence_state is not None:
            event["evidence_state"] = evidence_state

        logger.info(json.dumps(event, sort_keys=True, separators=(",", ":")))


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    if route is None:
        return "<unmatched>"
    route_path = getattr(route, "path", None) or getattr(route, "path_format", None)
    if route_path is None:
        return "<unknown>"
    return str(route_path)
