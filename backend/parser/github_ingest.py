import os
import re
from pathlib import Path
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


_ENV_LOADED = False


def _load_env_if_present(force: bool = False) -> None:
    """Safely load .env files if present without raising exceptions."""
    global _ENV_LOADED
    if _ENV_LOADED and not force:
        return
    _ENV_LOADED = True

    try:
        from dotenv import load_dotenv
        here = Path(__file__).resolve().parent.parent  # backend directory
        root = here.parent
        load_dotenv(here / ".env")
        load_dotenv(root / ".env")
    except Exception:
        pass

    for env_path in [Path("backend/.env"), Path(".env"), Path("../.env")]:
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass


_load_env_if_present()


def get_github_headers() -> dict:
    """
    Build standard GitHub API request headers.
    Includes Authorization header with GITHUB_TOKEN if configured.
    Never exposes or logs the token.
    """
    _load_env_if_present()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AI-Code-Review-Assistant/1.0",
    }
    raw_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if raw_token:
        token = raw_token[7:].strip() if raw_token.lower().startswith("bearer ") else raw_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
    return headers


def handle_github_error_response(response: httpx.Response, source_type: str) -> None:
    """
    Inspect GitHub response status code and headers to distinguish between:
      - 401: Invalid authentication / token
      - 403: Rate limit exceeded vs. Access forbidden
      - 404: Repository or PR/commit not found
      - 422: Unprocessable entity / empty diff
      - other: Generic API error
    Never exposes sensitive authentication info or raw internal stack traces.
    """
    status = response.status_code

    if status == 401:
        raise HTTPException(
            status_code=401,
            detail="GitHub authentication failed. Please check your GitHub token."
        )

    if status == 403:
        remaining = response.headers.get("x-ratelimit-remaining")
        retry_after = response.headers.get("retry-after")
        body_text = ""
        try:
            payload = response.json()
            body_text = str(payload.get("message", "")).lower()
        except Exception:
            body_text = response.text.lower()

        is_rate_limit = (
            remaining == "0"
            or retry_after is not None
            or "rate limit" in body_text
            or "secondary rate" in body_text
        )

        if is_rate_limit:
            raise HTTPException(
                status_code=403,
                detail="GitHub API rate limit exceeded. Please configure a GitHub token or try again later."
            )
        else:
            raise HTTPException(
                status_code=403,
                detail="GitHub access was forbidden for this repository or resource."
            )

    if status == 404:
        raise HTTPException(
            status_code=404,
            detail="GitHub repository or PR/commit was not found or is not accessible."
        )

    if status == 422:
        raise HTTPException(
            status_code=422,
            detail="GitHub was unable to process this request or the PR diff is empty/too large."
        )

    if response.is_error:
        raise HTTPException(
            status_code=status,
            detail=f"GitHub API error: {status} - {response.reason_phrase}"
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


async def ingest_github(url: str, client: Optional[httpx.AsyncClient] = None) -> IngestResponse:
    """
    Fetch PR or commit metadata and diffs from the GitHub public API.
    Optionally accepts an httpx.AsyncClient for dependency injection / testing.
    """
    owner, repo, source_type, source_id = parse_github_url(url)
    repository_name = f"{owner}/{repo}"

    headers = get_github_headers()

    if source_type == "pull_request":
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{source_id}/files?per_page=100"
    else:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{source_id}"

    if client is not None:
        try:
            response = await client.get(api_url, headers=headers)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Network error while connecting to GitHub API: {str(exc)}"
            )

        if response.is_error:
            handle_github_error_response(response, source_type)

        try:
            payload = response.json()
        except Exception:
            raise HTTPException(
                status_code=502,
                detail="Malformed response received from GitHub API."
            )
    else:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as default_client:
            try:
                response = await default_client.get(api_url, headers=headers)
            except httpx.RequestError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Network error while connecting to GitHub API: {str(exc)}"
                )

            if response.is_error:
                handle_github_error_response(response, source_type)

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
