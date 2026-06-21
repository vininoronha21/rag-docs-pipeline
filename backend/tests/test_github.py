import pytest

from app.services.github import GithubClient, GithubClientError, GithubRepo


class FakeResponse:
    text = "# Docs"

    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        pass

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


def make_client(fake_http_client: FakeGithubHttpClient) -> GithubClient:
    client = GithubClient.__new__(GithubClient)
    client._client = fake_http_client
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
