import httpx
import pytest

from app.services.github import (
    GithubClient,
    GithubClientError,
    GithubRepo,
    normalize_repository_path,
)


class FakeResponse:
    def __init__(
        self,
        payload: object,
        status_code: int = 200,
        content: bytes = b"# Docs",
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.content = content

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://api.github.com")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self) -> object:
        if isinstance(self.payload, ValueError):
            raise self.payload
        return self.payload


class FakeGithubHttpClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def get(self, *args: object, **kwargs: object) -> FakeResponse:
        assert args
        assert kwargs is not None
        self.requests.append((args, kwargs))
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


def make_retrying_client(responses: list[FakeResponse], recorder: SleepRecorder) -> GithubClient:
    client = GithubClient.__new__(GithubClient)
    client._client = FakeGithubHttpClient(responses)
    client._max_retries = 3
    client._backoff_seconds = 0.5
    client._sleep = recorder.sleep
    return client


def make_repo() -> GithubRepo:
    return GithubRepo(
        owner="example",
        name="project",
        full_name="example/project",
        default_branch="main",
    )


@pytest.mark.parametrize(
    "path",
    ["", ".", "../docs", "/docs", "docs\\api", "docs/../api", "docs/./api"],
)
def test_normalize_repository_path_rejects_non_curated_paths(path: str) -> None:
    with pytest.raises(ValueError):
        normalize_repository_path(path)


def test_normalize_repository_path_returns_posix_path() -> None:
    assert normalize_repository_path("docs/pt/docs") == "docs/pt/docs"


@pytest.mark.asyncio
async def test_resolves_branch_head_and_fetches_recursively_by_commit() -> None:
    commit_sha = "a" * 40
    http_client = FakeGithubHttpClient(
        [
            FakeResponse({"sha": commit_sha}),
            FakeResponse(
                [
                    {
                        "type": "dir",
                        "path": "docs/reference",
                    },
                    {
                        "type": "file",
                        "path": "docs/index.md",
                        "name": "index.md",
                        "sha": "index-blob",
                    },
                ]
            ),
            FakeResponse(
                [
                    {
                        "type": "file",
                        "path": "docs/reference/api.mdx",
                        "name": "api.mdx",
                        "sha": "api-blob",
                    }
                ]
            ),
            FakeResponse(None),
            FakeResponse(None),
        ]
    )
    client = make_client(http_client)

    resolved_sha = await client.resolve_commit(make_repo(), branch="main")
    files = await client.fetch_markdown_files(
        make_repo(), commit_sha=resolved_sha, path="docs", max_files=50
    )

    assert resolved_sha == commit_sha
    assert [file.path for file in files] == [
        "docs/reference/api.mdx",
        "docs/index.md",
    ]
    assert all(f"/blob/{commit_sha}/" in file.html_url for file in files)
    assert all(f"/{commit_sha}/" in file.download_url for file in files)
    assert http_client.requests[:3] == [
        (("/repos/example/project/commits/main",), {}),
        (("/repos/example/project/contents/docs",), {"params": {"ref": commit_sha}}),
        (
            ("/repos/example/project/contents/docs/reference",),
            {"params": {"ref": commit_sha}},
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("sha", [None, "A" * 40, "a" * 39, "g" * 40])
async def test_resolve_commit_rejects_invalid_sha(sha: object) -> None:
    client = make_client(FakeGithubHttpClient([FakeResponse({"sha": sha})]))

    with pytest.raises(GithubClientError, match="invalid commit response"):
        await client.resolve_commit(make_repo(), branch="main")


@pytest.mark.asyncio
async def test_fetch_markdown_files_fails_when_max_files_would_be_exceeded() -> None:
    commit_sha = "b" * 40
    client = make_client(
        FakeGithubHttpClient(
            [
                FakeResponse(
                    [
                        {
                            "type": "file",
                            "path": "docs/one.md",
                            "name": "one.md",
                            "sha": "one-blob",
                        },
                        {
                            "type": "file",
                            "path": "docs/two.md",
                            "name": "two.md",
                            "sha": "two-blob",
                        },
                    ]
                )
            ]
        )
    )

    with pytest.raises(GithubClientError, match="exceeds the maximum of 1 files"):
        await client.fetch_markdown_files(
            make_repo(), commit_sha=commit_sha, path="docs", max_files=1
        )


@pytest.mark.asyncio
async def test_fetch_markdown_files_rejects_possibly_truncated_directory() -> None:
    http_client = FakeGithubHttpClient(
        [
            FakeResponse(
                [
                    {
                        "type": "file",
                        "path": f"docs/file-{index}.txt",
                        "name": f"file-{index}.txt",
                        "sha": f"blob-{index}",
                    }
                    for index in range(1_000)
                ]
            )
        ]
    )
    client = make_client(http_client)

    with pytest.raises(GithubClientError, match="directory response may be truncated"):
        await client.fetch_markdown_files(
            make_repo(), commit_sha="c" * 40, path="docs", max_files=2_000
        )

    assert len(http_client.requests) == 1


@pytest.mark.asyncio
async def test_fetch_markdown_files_rejects_entries_outside_curated_path() -> None:
    client = make_client(
        FakeGithubHttpClient([FakeResponse([{"type": "dir", "path": "other/private"}])])
    )

    with pytest.raises(GithubClientError, match="invalid contents response"):
        await client.fetch_markdown_files(
            make_repo(), commit_sha="c" * 40, path="docs", max_files=50
        )


@pytest.mark.asyncio
async def test_fetch_markdown_files_rejects_invalid_utf8_content() -> None:
    client = make_client(
        FakeGithubHttpClient(
            [
                FakeResponse(
                    [
                        {
                            "type": "file",
                            "path": "docs/index.md",
                            "name": "index.md",
                            "sha": "index-blob",
                        }
                    ]
                ),
                FakeResponse(None, content=b"\xff"),
            ]
        )
    )

    with pytest.raises(GithubClientError, match="invalid UTF-8 file response"):
        await client.fetch_markdown_files(
            make_repo(), commit_sha="d" * 40, path="docs", max_files=50
        )


@pytest.mark.asyncio
async def test_fetch_markdown_files_preserves_valid_utf8_content() -> None:
    client = make_client(
        FakeGithubHttpClient(
            [
                FakeResponse(
                    [
                        {
                            "type": "file",
                            "path": "docs/index.md",
                            "name": "index.md",
                            "sha": "index-blob",
                        }
                    ]
                ),
                FakeResponse(None, content=b"# Ol\xc3\xa1"),
            ]
        )
    )

    files = await client.fetch_markdown_files(
        make_repo(), commit_sha="e" * 40, path="docs", max_files=50
    )

    assert [file.content for file in files] == ["# Ol\u00e1"]


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
            make_repo(),
            commit_sha="a" * 40,
            path="docs",
            max_files=50,
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
