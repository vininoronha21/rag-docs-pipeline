import httpx
import pytest

from app.services.github import GithubClient, GithubClientError, GithubRepo


class FakeResponse:
    text = "# Docs"

    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://api.github.com")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                "error", request=request, response=response
            )

    def json(self) -> object:
        if isinstance(self.payload, ValueError):
            raise self.payload
        return self.payload


class FakeGithubHttpClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses

    async def get(self, *args: object, **kwargs: object) -> FakeResponse:
        assert args
        assert kwargs is not None
        return self.responses.pop(0)


class SleepRecorder:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)


def make_client(fake_http_client: FakeGithubHttpClient) -> GithubClient:
    client = GithubClient.__new__(GithubClient)
    client._client = fake_http_client
    return client


def make_retrying_client(
    responses: list[FakeResponse], recorder: SleepRecorder
) -> GithubClient:
    client = GithubClient.__new__(GithubClient)
    client._client = FakeGithubHttpClient(responses)
    client._max_retries = 3
    client._backoff_seconds = 0.5
    client._sleep = recorder.sleep
    return client


@pytest.mark.asyncio
async def test_github_client_rejects_invalid_repo_payload() -> None:
    client = make_client(FakeGithubHttpClient([FakeResponse({"full_name": "example/project"})]))

    with pytest.raises(GithubClientError, match="invalid repository response"):
        await client.get_repo("https://github.com/example/project")


@pytest.mark.asyncio
async def test_github_client_rejects_invalid_contents_payload() -> None:
    client = make_client(FakeGithubHttpClient([FakeResponse([{"type": "file"}])]))

    with pytest.raises(GithubClientError, match="invalid contents response"):
        await client._walk_contents("example", "project", "docs", "main", max_files=1)


@pytest.mark.asyncio
async def test_github_client_rejects_invalid_file_payload() -> None:
    client = make_client(FakeGithubHttpClient([]))

    async def fake_walk_contents(*args: object, **kwargs: object) -> list[dict[str, object]]:
        return [{"path": "docs/index.md"}]

    client._walk_contents = fake_walk_contents

    with pytest.raises(GithubClientError, match="invalid file response"):
        await client.fetch_markdown_files(
            GithubRepo(
                owner="example",
                name="project",
                full_name="example/project",
                default_branch="main",
            )
        )


@pytest.mark.asyncio
async def test_github_client_retries_transient_status_then_succeeds() -> None:
    recorder = SleepRecorder()
    client = make_retrying_client(
        [
            FakeResponse(None, status_code=503),
            FakeResponse(
                {"full_name": "example/project", "default_branch": "main"},
                status_code=200,
            ),
        ],
        recorder,
    )

    repo = await client.get_repo("https://github.com/example/project")

    assert repo.full_name == "example/project"
    assert repo.default_branch == "main"
    assert recorder.delays == [0.5]


@pytest.mark.asyncio
async def test_github_client_raises_after_retries_exhausted() -> None:
    recorder = SleepRecorder()
    client = make_retrying_client(
        [FakeResponse(None, status_code=502) for _ in range(4)],
        recorder,
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_repo("https://github.com/example/project")

    assert recorder.delays == [0.5, 1.0, 2.0]
