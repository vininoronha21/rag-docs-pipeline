from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import Settings


@dataclass(frozen=True)
class GithubFile:
    path: str
    sha: str
    html_url: str
    download_url: str
    content: str


@dataclass(frozen=True)
class GithubRepo:
    owner: str
    name: str
    full_name: str
    default_branch: str


class GithubClientError(RuntimeError):
    """Raised when GitHub returns a response that cannot be parsed safely."""


class GithubClient:
    def __init__(self, settings: Settings) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": settings.github_user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self._client = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers=headers,
            follow_redirects=True,
            timeout=30,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_repo(self, repo_url: str) -> GithubRepo:
        owner, name = parse_repo_url(repo_url)
        response = await self._client.get(f"/repos/{owner}/{name}")
        response.raise_for_status()
        payload = _response_json(
            response,
            error_message="GitHub returned an invalid repository response. Try again later.",
        )
        try:
            full_name = payload["full_name"]
            default_branch = payload["default_branch"]
        except (KeyError, TypeError) as exc:
            raise GithubClientError(
                "GitHub returned an invalid repository response. Try again later."
            ) from exc
        if not isinstance(full_name, str) or not isinstance(default_branch, str):
            raise GithubClientError(
                "GitHub returned an invalid repository response. Try again later."
            )
        return GithubRepo(
            owner=owner,
            name=name,
            full_name=full_name,
            default_branch=default_branch,
        )

    async def fetch_markdown_files(
        self,
        repo: GithubRepo,
        *,
        branch: str | None = None,
        path: str = "",
        max_files: int = 50,
    ) -> list[GithubFile]:
        ref = branch or repo.default_branch
        entries = await self._walk_contents(repo.owner, repo.name, path, ref, max_files=max_files)
        files: list[GithubFile] = []
        for entry in entries[:max_files]:
            try:
                entry_path = entry["path"]
                entry_sha = entry["sha"]
                entry_html_url = entry["html_url"]
                entry_download_url = entry["download_url"]
            except (KeyError, TypeError) as exc:
                raise GithubClientError(
                    "GitHub returned an invalid file response. Try again later."
                ) from exc
            if not all(
                isinstance(value, str)
                for value in (entry_path, entry_sha, entry_html_url, entry_download_url)
            ):
                raise GithubClientError(
                    "GitHub returned an invalid file response. Try again later."
                )

            raw = await self._client.get(entry_download_url)
            raw.raise_for_status()
            files.append(
                GithubFile(
                    path=entry_path,
                    sha=entry_sha,
                    html_url=entry_html_url,
                    download_url=entry_download_url,
                    content=raw.text,
                )
            )
        return files

    async def _walk_contents(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str,
        *,
        max_files: int,
    ) -> list[dict[str, Any]]:
        response = await self._client.get(
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
        )
        response.raise_for_status()
        payload = _response_json(
            response,
            error_message="GitHub returned an invalid contents response. Try again later.",
        )
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = [payload]
        else:
            raise GithubClientError(
                "GitHub returned an invalid contents response. Try again later."
            )
        markdown_files: list[dict[str, Any]] = []

        for item in items:
            if len(markdown_files) >= max_files:
                break
            try:
                item_type = item["type"]
                item_path = item["path"]
            except (KeyError, TypeError) as exc:
                raise GithubClientError(
                    "GitHub returned an invalid contents response. Try again later."
                ) from exc
            if not isinstance(item_type, str) or not isinstance(item_path, str):
                raise GithubClientError(
                    "GitHub returned an invalid contents response. Try again later."
                )

            if item_type == "file" and _is_markdown_file(item):
                markdown_files.append(item)
            elif item_type == "dir" and _is_documentation_path(item_path):
                markdown_files.extend(
                    await self._walk_contents(
                        owner,
                        repo,
                        item_path,
                        ref,
                        max_files=max_files - len(markdown_files),
                    )
                )

        return markdown_files


def parse_repo_url(repo_url: str) -> tuple[str, str]:
    parsed = urlparse(repo_url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if parsed.netloc.lower() != "github.com" or len(parts) < 2:
        raise ValueError("Expected a GitHub repository URL like https://github.com/owner/repo")
    return parts[0], parts[1].removesuffix(".git")


def _response_json(response: httpx.Response, *, error_message: str) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise GithubClientError(error_message) from exc


def _is_markdown_file(item: dict[str, Any]) -> bool:
    try:
        name = item["name"]
    except KeyError as exc:
        raise GithubClientError(
            "GitHub returned an invalid contents response. Try again later."
        ) from exc
    if not isinstance(name, str):
        raise GithubClientError(
            "GitHub returned an invalid contents response. Try again later."
        )
    return name.lower().endswith((".md", ".mdx"))


def _is_documentation_path(path: str) -> bool:
    lowered = path.lower()
    if lowered in {"docs", "documentation", ".github"}:
        return True
    return any(segment in {"docs", "documentation", "guides"} for segment in lowered.split("/"))
