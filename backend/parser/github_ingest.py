import os
import re
from typing import Tuple, List, Optional
import httpx
from fastapi import HTTPException

from models.ingest import ChangedFile, IngestResponse

# Language mapping definition according to project specifications
EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".html": "html",
    ".css": "css",
    ".json": "json",
}

MAX_CHANGED_LINES = 500

PR_REGEX = re.compile(
    r"^https?://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/pull/(?P<pull_number>\d+)/?.*$"
)
COMMIT_REGEX = re.compile(
    r"^https?://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/commit/(?P<commit_sha>[0-9a-fA-F]+)/?.*$"
)


def detect_language(filename: str) -> str:
    """Detect programming language from file extension, returning 'unknown' if not mapped."""
    _, ext = os.path.splitext(filename.lower())
    return EXTENSION_TO_LANGUAGE.get(ext, "unknown")


def parse_github_url(url: str) -> Tuple[str, str, str, str]:
    """
    Parse a GitHub PR or commit URL.
    Returns: (owner, repo, source_type, source_id)
    Raises: HTTPException(400) if URL format is invalid.
    """
    if not isinstance(url, str):
        raise HTTPException(status_code=400, detail="Invalid URL format provided.")

    clean_url = url.strip()
    pr_match = PR_REGEX.match(clean_url)
    if pr_match:
        owner = pr_match.group("owner")
        repo = pr_match.group("repo")
        pull_number = pr_match.group("pull_number")
        return owner, repo, "pull_request", pull_number

    commit_match = COMMIT_REGEX.match(clean_url)
    if commit_match:
        owner = commit_match.group("owner")
        repo = commit_match.group("repo")
        commit_sha = commit_match.group("commit_sha")
        return owner, repo, "commit", commit_sha

    raise HTTPException(
        status_code=400,
        detail="Invalid GitHub URL. Expected a public Pull Request (https://github.com/owner/repo/pull/123) or Commit (https://github.com/owner/repo/commit/<sha>)."
    )


def process_patch(raw_patch: Optional[str], additions: int, deletions: int) -> Tuple[Optional[str], bool, int]:
    """
    Calculate changed lines and enforce the 500 changed-line limit.
    If changed_lines > 500, truncates the patch to the first 500 lines
    and flags truncated=True.
    """
    changed_lines = additions + deletions
    if raw_patch is None:
        is_truncated = changed_lines > MAX_CHANGED_LINES
        return None, is_truncated, changed_lines

    if changed_lines > MAX_CHANGED_LINES:
        lines = raw_patch.splitlines(keepends=True)
        safe_patch = "".join(lines[:MAX_CHANGED_LINES]) + "\n... [TRUNCATED: Exceeded 500 changed lines]"
        return safe_patch, True, changed_lines

    return raw_patch, False, changed_lines


async def ingest_github(url: str) -> IngestResponse:
    """
    Fetch PR or commit metadata and diffs from the GitHub public API.
    """
    owner, repo, source_type, source_id = parse_github_url(url)
    repository_name = f"{owner}/{repo}"

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-Code-Review-Assistant/1.0",
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            if source_type == "pull_request":
                api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{source_id}/files?per_page=100"
                response = await client.get(api_url, headers=headers)
            else:
                api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{source_id}"
                response = await client.get(api_url, headers=headers)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Network error while connecting to GitHub API: {str(exc)}"
            )

        if response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"GitHub repository or {source_type.replace('_', ' ')} not found."
            )
        elif response.status_code == 403:
            raise HTTPException(
                status_code=403,
                detail="GitHub API rate limit exceeded or access forbidden."
            )
        elif response.is_error:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"GitHub API error: {response.status_code} - {response.reason_phrase}"
            )

        try:
            payload = response.json()
        except Exception:
            raise HTTPException(
                status_code=502,
                detail="Malformed response received from GitHub API."
            )

    raw_files = payload if source_type == "pull_request" else payload.get("files", [])
    if not isinstance(raw_files, list):
        raw_files = []

    files: List[ChangedFile] = []
    truncated_files: List[str] = []
    total_changed_lines = 0

    for item in raw_files:
        if not isinstance(item, dict):
            continue

        filename = item.get("filename", "unknown")
        status = item.get("status", "modified")
        additions = item.get("additions", 0)
        deletions = item.get("deletions", 0)
        raw_patch = item.get("patch")

        safe_patch, is_truncated, changed_lines = process_patch(raw_patch, additions, deletions)

        if is_truncated:
            truncated_files.append(filename)

        total_changed_lines += changed_lines

        files.append(
            ChangedFile(
                file=filename,
                language=detect_language(filename),
                status=status,
                additions=additions,
                deletions=deletions,
                changed_lines=changed_lines,
                patch=safe_patch,
                truncated=is_truncated
            )
        )

    return IngestResponse(
        source_url=url,
        repository=repository_name,
        source_type=source_type,
        source_id=source_id,
        files=files,
        total_files=len(files),
        total_changed_lines=total_changed_lines,
        truncated_files=truncated_files
    )
