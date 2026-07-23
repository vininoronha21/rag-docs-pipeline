from __future__ import annotations

import json
import os
import shutil
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
    assert "FRONTEND_URL: ${{ secrets.FRONTEND_URL }}" in workflow
    assert "BACKEND_URL: ${{ secrets.BACKEND_URL }}" in workflow
    assert "SMOKE_ANSWERABLE_QUESTION: ${{ secrets.SMOKE_ANSWERABLE_QUESTION }}" in workflow
    assert "SMOKE_UNSUPPORTED_QUESTION: ${{ secrets.SMOKE_UNSUPPORTED_QUESTION }}" in workflow
    assert "vars.FRONTEND_URL" not in workflow
    assert "vars.BACKEND_URL" not in workflow
    assert "vars.SMOKE_ANSWERABLE_QUESTION" not in workflow
    assert "vars.SMOKE_UNSUPPORTED_QUESTION" not in workflow
    assert "bash scripts/smoke.sh" in workflow


def test_smoke_uses_bounded_retry_for_all_network_checks(tmp_path: Path) -> None:
    real_curl = shutil.which("curl")
    assert real_curl is not None
    curl_log = tmp_path / "curl.jsonl"
    curl_wrapper = tmp_path / "curl"
    curl_wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import subprocess\n"
        "import sys\n"
        "with open(os.environ['SMOKE_CURL_LOG'], 'a', encoding='utf-8') as log:\n"
        "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "raise SystemExit(subprocess.call([os.environ['SMOKE_REAL_CURL'], *sys.argv[1:]]))\n",
    )
    curl_wrapper.chmod(0o755)
    scenario = SmokeScenario(
        answered_payload=answered_payload(), unsupported_payload=unsupported_payload()
    )

    with fake_smoke_server(scenario) as base_url:
        result = run_smoke(
            base_url,
            env_overrides={
                "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
                "SMOKE_CURL_LOG": str(curl_log),
                "SMOKE_REAL_CURL": real_curl,
            },
        )

    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in curl_log.read_text().splitlines()]
    calls_by_url = {args[-1]: args for args in calls if args}

    retried_fail_fast_urls = [
        base_url,
        f"{base_url}/api/health",
        f"{base_url}/api/ready",
        f"{base_url}/api/query",
    ]
    for url in retried_fail_fast_urls:
        matching_calls = [args for args in calls if args and args[-1] == url]
        assert matching_calls, f"missing curl call for {url}"
        for args in matching_calls:
            assert "--fail" in args
            assert_curl_uses_required_retry(args)

    admin_args = calls_by_url[f"{base_url}/api/admin/sources"]
    assert "--fail" not in admin_args
    assert "--output" in admin_args
    assert admin_args[admin_args.index("--output") + 1] == "/dev/null"
    assert "--write-out" in admin_args
    assert admin_args[admin_args.index("--write-out") + 1] == "%{http_code}"
    assert_curl_uses_required_retry(admin_args)


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


def run_smoke(
    base_url: str, env_overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ | {
        "FRONTEND_URL": f"{base_url}/",
        "BACKEND_URL": f"{base_url}/",
        "SMOKE_ANSWERABLE_QUESTION": ANSWERABLE_QUESTION,
        "SMOKE_UNSUPPORTED_QUESTION": UNSUPPORTED_QUESTION,
    }
    if env_overrides is not None:
        env.update(env_overrides)
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


def assert_curl_uses_required_retry(args: list[str]) -> None:
    assert "--silent" in args
    assert "--show-error" in args
    assert_ordered_args(args, ["--retry", "12", "--retry-all-errors", "--retry-delay", "10"])


def assert_ordered_args(args: list[str], expected: list[str]) -> None:
    start = 0
    for item in expected:
        position = args.index(item, start)
        start = position + 1
