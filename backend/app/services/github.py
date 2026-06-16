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
        payload = response.json()
        return GithubRepo(
            owner=owner,
            name=name,
            full_name=payload["full_name"],
            default_branch=payload["default_branch"],
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
            raw = await self._client.get(entry["download_url"])
            raw.raise_for_status()
            files.append(
                GithubFile(
                    path=entry["path"],
                    sha=entry["sha"],
                    html_url=entry["html_url"],
                    download_url=entry["download_url"],
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
        payload = response.json()
        items = payload if isinstance(payload, list) else [payload]
        markdown_files: list[dict[str, Any]] = []

        for item in items:
            if len(markdown_files) >= max_files:
                break
            if item["type"] == "file" and item["name"].lower().endswith((".md", ".mdx")):
                markdown_files.append(item)
            elif item["type"] == "dir" and _is_documentation_path(item["path"]):
                markdown_files.extend(
                    await self._walk_contents(
                        owner,
                        repo,
                        item["path"],
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


def _is_documentation_path(path: str) -> bool:
    lowered = path.lower()
    if lowered in {"docs", "documentation", ".github"}:
        return True
    return any(segment in {"docs", "documentation", "guides"} for segment in lowered.split("/"))
