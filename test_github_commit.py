import sys
sys.path.insert(0, "backend")
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from models.github_commit import GitHubCommitRequest, GitHubCommitResponse
from parser.github_committer import _parse_repo_from_url, commit_fix_to_github



def test_parse_repo_from_url():
    owner, repo, utype, ident = _parse_repo_from_url("https://github.com/octocat/Hello-World/pull/42")
    assert owner == "octocat"
    assert repo == "Hello-World"
    assert utype == "pr"
    assert ident == "42"

    owner, repo, utype, ident = _parse_repo_from_url("https://github.com/owner/my-repo/commit/abc1234")
    assert owner == "owner"
    assert repo == "my-repo"
    assert utype == "commit"
    assert ident == "abc1234"

    owner, repo, utype, ident = _parse_repo_from_url("https://github.com/owner/my-repo")
    assert owner == "owner"
    assert repo == "my-repo"
    assert utype == "repo"


@pytest.mark.asyncio
async def test_commit_fix_invalid_url():
    req = GitHubCommitRequest(
        url="not-a-valid-url",
        file="app.py",
        fixed_code="x = 1"
    )
    res = await commit_fix_to_github(req)
    assert res.success is False
    assert "Invalid GitHub URL" in res.message


@pytest.mark.asyncio
async def test_commit_fix_mocked_success():
    req = GitHubCommitRequest(
        url="https://github.com/owner/repo/pull/1",
        file="main.py",
        fixed_code="val = 42",
        original_code="val = 0"
    )

    mock_client = AsyncMock()
    # Mock PR call
    mock_pr_resp = MagicMock(status_code=200)
    mock_pr_resp.json.return_value = {"head": {"ref": "patch-1", "repo": {"full_name": "owner/repo"}}}

    # Mock file contents GET
    import base64
    mock_file_resp = MagicMock(status_code=200)
    mock_file_resp.json.return_value = {
        "sha": "blob_sha_123",
        "content": base64.b64encode(b"val = 0\nprint(val)").decode("utf-8")
    }

    # Mock file contents PUT
    mock_put_resp = MagicMock(status_code=200)
    mock_put_resp.json.return_value = {
        "commit": {
            "sha": "commit_sha_999",
            "html_url": "https://github.com/owner/repo/commit/commit_sha_999"
        }
    }

    mock_client.get.side_effect = [mock_pr_resp, mock_file_resp]
    mock_client.put.return_value = mock_put_resp

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__.return_value = mock_client
        res = await commit_fix_to_github(req)
        assert res.success is True
        assert res.commit_sha == "commit_sha_999"
        assert res.branch == "patch-1"
        assert "Successfully committed" in res.message
