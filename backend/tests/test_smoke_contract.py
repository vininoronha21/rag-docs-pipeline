from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "smoke.sh"

ANSWERABLE_QUESTION = "SENSITIVE_ANSWERABLE_SMOKE_QUESTION"
UNSUPPORTED_QUESTION = "SENSITIVE_UNSUPPORTED_SMOKE_QUESTION"
ANSWER_TEXT = "SENSITIVE_ANSWER_BODY_TEXT"
EVIDENCE_TEXT = "SENSITIVE_EVIDENCE_BODY_TEXT"
ADMIN_BODY = "SENSITIVE_ADMIN_UNAUTHORIZED_BODY"
COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"


@dataclass
class SmokeScenario:
    answered_payload: dict[str, Any] = field(default_factory=dict)
    unsupported_payload: dict[str, Any] = field(default_factory=dict)
    request_bodies: list[dict[str, Any]] = field(default_factory=list)
    request_paths: list[str] = field(default_factory=list)


def test_smoke_accepts_valid_contract_without_logging_private_bodies() -> None:
    scenario = SmokeScenario(
        answered_payload=answered_payload(), unsupported_payload=unsupported_payload()
    )

    with fake_smoke_server(scenario) as base_url:
        result = run_smoke(base_url)

    assert result.returncode == 0, result.stderr
    assert [body["question"] for body in scenario.request_bodies] == [
        ANSWERABLE_QUESTION,
        UNSUPPORTED_QUESTION,
    ]
    assert "//api/" not in "\n".join(scenario.request_paths)
    assert_private_values_not_logged(result)


@pytest.mark.parametrize(
    ("mutate_payload", "expected_message"),
    [
        pytest.param(
            lambda payload: payload.__setitem__("evidence", []),
            "Answered smoke query did not satisfy the response contract.",
            id="answered-without-evidence",
        ),
        pytest.param(
            lambda payload: payload["evidence"][0].__setitem__("commit_sha", "abc123"),
            "Answered smoke query did not satisfy the response contract.",
            id="answered-with-short-commit-sha",
        ),
        pytest.param(
            lambda payload: payload["evidence"][0].__setitem__(
                "source_url", "https://github.com/acme/docs/blob/main/docs/guide.md"
            ),
            "Answered smoke query did not satisfy the response contract.",
            id="answered-with-branch-url",
        ),
    ],
)
def test_smoke_rejects_answered_payloads_without_commit_pinned_evidence(
    mutate_payload: Callable[[dict[str, Any]], None], expected_message: str
) -> None:
    payload = answered_payload()
    mutate_payload(payload)
    scenario = SmokeScenario(answered_payload=payload, unsupported_payload=unsupported_payload())

    with fake_smoke_server(scenario) as base_url:
        result = run_smoke(base_url)

    assert result.returncode != 0
    assert expected_message in result.stderr
    assert_private_values_not_logged(result)


def test_smoke_rejects_unsupported_query_that_is_answered() -> None:
    scenario = SmokeScenario(
        answered_payload=answered_payload(), unsupported_payload=answered_payload()
    )

    with fake_smoke_server(scenario) as base_url:
        result = run_smoke(base_url)

    assert result.returncode != 0
    assert "Unsupported smoke query did not return insufficient_evidence." in result.stderr
    assert_private_values_not_logged(result)


def test_smoke_requires_environment_without_printing_present_values() -> None:
    env = os.environ.copy()
    for name in (
        "FRONTEND_URL",
        "BACKEND_URL",
        "SMOKE_ANSWERABLE_QUESTION",
        "SMOKE_UNSUPPORTED_QUESTION",
    ):
        env.pop(name, None)
    env.update(
        {
            "FRONTEND_URL": "https://frontend.example.invalid",
            "BACKEND_URL": "https://backend.example.invalid",
            "SMOKE_ANSWERABLE_QUESTION": ANSWERABLE_QUESTION,
        }
    )

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode != 0
    assert "SMOKE_UNSUPPORTED_QUESTION is required." in result.stderr
    assert_private_values_not_logged(result)


def test_ci_defines_manual_post_deploy_smoke_job_only_for_workflow_dispatch() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "post-deploy-smoke:" in workflow
    assert "if: github.event_name == 'workflow_dispatch'" in workflow
    assert "environment: ${{ inputs.environment }}" in workflow
    assert "FRONTEND_URL: ${{ vars.FRONTEND_URL }}" in workflow
    assert "BACKEND_URL: ${{ vars.BACKEND_URL }}" in workflow
    assert "SMOKE_ANSWERABLE_QUESTION: ${{ vars.SMOKE_ANSWERABLE_QUESTION }}" in workflow
    assert "SMOKE_UNSUPPORTED_QUESTION: ${{ vars.SMOKE_UNSUPPORTED_QUESTION }}" in workflow
    assert "bash scripts/smoke.sh" in workflow


def answered_payload() -> dict[str, Any]:
    return {
        "event_id": "11111111-1111-4111-8111-111111111111",
        "state": "answered",
        "answered": True,
        "insufficient_evidence": False,
        "answer": {
            "sentences": [
                {
                    "text": ANSWER_TEXT,
                    "citation_id": "citation-1",
                }
            ]
        },
        "evidence": [
            {
                "citation_id": "citation-1",
                "supported_text": ANSWER_TEXT,
                "excerpt": EVIDENCE_TEXT,
                "title": "Guide",
                "repository_path": "docs/guide.md",
                "section": "Install",
                "commit_sha": COMMIT_SHA,
                "source_url": f"https://github.com/acme/docs/blob/{COMMIT_SHA}/docs/guide.md",
                "vector_score": 0.91,
                "text_score": 0.83,
                "fused_score": 0.88,
            }
        ],
        "metrics": {
            "latency_ms": 12,
            "retrieved_chunk_count": 1,
            "top_fused_score": 0.88,
            "score_gap": None,
        },
    }


def unsupported_payload() -> dict[str, Any]:
    return {
        "event_id": "22222222-2222-4222-8222-222222222222",
        "state": "insufficient_evidence",
        "answered": False,
        "insufficient_evidence": True,
        "answer": None,
        "evidence": [],
        "metrics": {
            "latency_ms": 9,
            "retrieved_chunk_count": 0,
            "top_fused_score": None,
            "score_gap": None,
        },
    }


def run_smoke(base_url: str) -> subprocess.CompletedProcess[str]:
    env = os.environ | {
        "FRONTEND_URL": f"{base_url}/",
        "BACKEND_URL": f"{base_url}/",
        "SMOKE_ANSWERABLE_QUESTION": ANSWERABLE_QUESTION,
        "SMOKE_UNSUPPORTED_QUESTION": UNSUPPORTED_QUESTION,
    }
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )


@contextmanager
def fake_smoke_server(scenario: SmokeScenario) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), smoke_handler(scenario))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def smoke_handler(scenario: SmokeScenario) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            scenario.request_paths.append(self.path)
            if self.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"ok")
                return
            if self.path == "/api/health":
                self.write_json(
                    200, {"status": "ok", "app": "rag-docs-pipeline", "environment": "test"}
                )
                return
            if self.path == "/api/ready":
                self.write_json(
                    200, {"status": "ready", "database": "ok", "pgvector": "ok"}
                )
                return
            if self.path == "/api/admin/sources":
                self.write_json(401, {"detail": ADMIN_BODY})
                return
            self.write_json(404, {"detail": "not found"})

        def do_POST(self) -> None:
            scenario.request_paths.append(self.path)
            if self.path != "/api/query":
                self.write_json(404, {"detail": "not found"})
                return

            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            scenario.request_bodies.append(body)
            if body["question"] == ANSWERABLE_QUESTION:
                self.write_json(200, scenario.answered_payload)
                return
            if body["question"] == UNSUPPORTED_QUESTION:
                self.write_json(200, scenario.unsupported_payload)
                return
            self.write_json(400, {"detail": "unexpected question"})

        def write_json(self, status: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def assert_private_values_not_logged(result: subprocess.CompletedProcess[str]) -> None:
    combined_output = result.stdout + result.stderr
    for private_value in (
        ANSWERABLE_QUESTION,
        UNSUPPORTED_QUESTION,
        ANSWER_TEXT,
        EVIDENCE_TEXT,
        ADMIN_BODY,
    ):
        assert private_value not in combined_output
