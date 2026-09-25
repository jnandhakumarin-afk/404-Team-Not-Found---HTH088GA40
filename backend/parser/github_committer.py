import base64
import logging
import re
from typing import Dict, Any, Optional
import httpx

from parser.github_ingest import get_github_headers, PR_REGEX, COMMIT_REGEX
from models.github_commit import GitHubCommitRequest, GitHubCommitResponse

logger = logging.getLogger(__name__)


def _parse_repo_from_url(url: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Extract (owner, repo, type, identifier) from GitHub URL.
    type is 'pr', 'commit', or 'repo'.
    """
    clean_url = url.strip()
    pr_m = PR_REGEX.match(clean_url)
    if pr_m:
        return pr_m.group("owner"), pr_m.group("repo"), "pr", pr_m.group("pull_number")

    commit_m = COMMIT_REGEX.match(clean_url)
    if commit_m:
        return commit_m.group("owner"), commit_m.group("repo"), "commit", commit_m.group("commit_sha")

    repo_m = re.match(r"^https?://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/?.*$", clean_url)
    if repo_m:
        return repo_m.group("owner"), repo_m.group("repo"), "repo", None

    return None, None, None, None


async def commit_fix_to_github(req: GitHubCommitRequest) -> GitHubCommitResponse:
    """
    Applies the code fix directly to the target GitHub repository branch
    using the GitHub Contents API and personal access token.
    """
    owner, repo, url_type, identifier = _parse_repo_from_url(req.url)
    if not owner or not repo:
        return GitHubCommitResponse(
            success=False,
            message="Invalid GitHub URL provided.",
            error="Could not parse owner and repository name from URL."
        )

    headers = get_github_headers()
    if "Authorization" not in headers:
        return GitHubCommitResponse(
            success=False,
            message="GitHub authentication token missing.",
            error="GITHUB_TOKEN environment variable is not configured."
        )

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Determine target branch & target repo (handles PR branches vs default branch)
        target_owner = owner
        target_repo = repo
        target_branch = "main"

        try:
            if url_type == "pr" and identifier:
                pr_resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}/pulls/{identifier}", headers=headers)
                if pr_resp.status_code == 200:
                    pr_data = pr_resp.json()
                    target_branch = pr_data.get("head", {}).get("ref", "main")
                    head_repo_full = pr_data.get("head", {}).get("repo", {}).get("full_name")
                    if head_repo_full and "/" in head_repo_full:
                        target_owner, target_repo = head_repo_full.split("/", 1)
            else:
                repo_resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers)
                if repo_resp.status_code == 200:
                    target_branch = repo_resp.json().get("default_branch", "main")
        except Exception as e:
            logger.warning("Could not query branch info for %s/%s: %s", owner, repo, e)

        # 2. Fetch current file content and sha
        clean_file_path = req.file.lstrip("/")
        contents_url = f"https://api.github.com/repos/{target_owner}/{target_repo}/contents/{clean_file_path}"
        
        file_sha = None
        current_content = ""
        try:
            get_file_resp = await client.get(contents_url, params={"ref": target_branch}, headers=headers)
            if get_file_resp.status_code == 200:
                file_data = get_file_resp.json()
                file_sha = file_data.get("sha")
                raw_b64 = file_data.get("content", "")
                if raw_b64:
                    current_content = base64.b64decode(raw_b64).decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning("Error fetching file content from GitHub: %s", e)

        # 3. Calculate new file content
        new_content = current_content
        original_snip = (req.original_code or "").strip()
        fixed_snip = req.fixed_code.strip()

        if current_content and original_snip and original_snip in current_content:
            new_content = current_content.replace(original_snip, fixed_snip, 1)
        elif current_content and req.line and req.line > 0:
            lines = current_content.splitlines()
            line_idx = req.line - 1
            if 0 <= line_idx < len(lines):
                # Replace the line or patch
                lines[line_idx] = fixed_snip
                new_content = "\n".join(lines)
            else:
                new_content = fixed_snip
        elif not current_content:
            new_content = fixed_snip
        else:
            # If original snippet wasn't an exact match, try matching normalized lines
            new_content = current_content.replace(original_snip.splitlines()[0], fixed_snip, 1) if original_snip else fixed_snip

        # 4. Push commit via PUT /contents/{path}
        b64_new = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
        commit_msg = req.message or f"fix({clean_file_path}): resolve issue via AI Code Review Assistant"
        
        payload: Dict[str, Any] = {
            "message": commit_msg,
            "content": b64_new,
            "branch": target_branch,
        }
        if file_sha:
            payload["sha"] = file_sha

        try:
            put_resp = await client.put(contents_url, json=payload, headers=headers)
            if put_resp.status_code in (200, 201):
                resp_json = put_resp.json()
                commit_info = resp_json.get("commit", {})
                return GitHubCommitResponse(
                    success=True,
                    message=f"Successfully committed and pushed fix to {target_owner}/{target_repo} on branch '{target_branch}'.",
                    commit_url=commit_info.get("html_url"),
                    commit_sha=commit_info.get("sha"),
                    branch=target_branch,
                )
            else:
                err_detail = "Commit failed"
                try:
                    err_json = put_resp.json()
                    err_detail = err_json.get("message", put_resp.text)
                except Exception:
                    err_detail = put_resp.text
                return GitHubCommitResponse(
                    success=False,
                    message=f"GitHub rejected commit (HTTP {put_resp.status_code})",
                    error=f"{err_detail}. Verify that your GITHUB_TOKEN has write/push permissions for {target_owner}/{target_repo}."
                )
        except Exception as e:
            return GitHubCommitResponse(
                success=False,
                message="Network error committing to GitHub",
                error=str(e)
            )
