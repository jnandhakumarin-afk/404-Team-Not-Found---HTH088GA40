import sys
import os
import asyncio
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app
from parser.github_ingest import detect_language, process_patch, parse_github_url

client = TestClient(app)

def test_health():
    print("Testing GET /health...")
    resp = client.get("/health")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    assert data == {"status": "success"}, f"Unexpected data: {data}"
    print("  -> PASSED: /health")

def test_api_status():
    print("Testing GET /api/status...")
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    print("  -> PASSED: /api/status")

def test_existing_endpoints():
    print("Testing existing endpoints...")
    # parse-code
    r1 = client.post("/api/parse-code", json={"code": "x = 1\ny = 2"})
    assert r1.status_code == 200
    assert r1.json()["total_lines"] == 2
    
    # parse-diff
    r2 = client.post("/api/parse-diff", json={"diff": "+line1\n-line2\n+line3"})
    assert r2.status_code == 200
    assert r2.json()["total_changed_lines"] == 2

    # analyze
    r3 = client.post("/api/analyze", json={"code": "print('hello')"})
    assert r3.status_code == 200
    assert r3.json()["total_issues"] == 1

    # review (deduplicated)
    r4 = client.post("/api/review", json={"code": "eval('bad')"})
    assert r4.status_code == 200
    res = r4.json()
    assert "summary" in res
    assert "issues" in res
    assert "risk" in res
    print("  -> PASSED: existing endpoints & deduplicated /api/review")

def test_language_detection():
    print("Testing language detection...")
    assert detect_language("script.py") == "python"
    assert detect_language("app.js") == "javascript"
    assert detect_language("component.jsx") == "javascript"
    assert detect_language("service.ts") == "typescript"
    assert detect_language("ui.tsx") == "typescript"
    assert detect_language("Main.java") == "java"
    assert detect_language("code.cpp") == "cpp"
    assert detect_language("main.c") == "c"
    assert detect_language("Program.cs") == "csharp"
    assert detect_language("server.go") == "go"
    assert detect_language("lib.rs") == "rust"
    assert detect_language("index.php") == "php"
    assert detect_language("script.rb") == "ruby"
    assert detect_language("App.swift") == "swift"
    assert detect_language("Main.kt") == "kotlin"
    assert detect_language("index.html") == "html"
    assert detect_language("style.css") == "css"
    assert detect_language("data.json") == "json"
    assert detect_language("README.md") == "unknown"
    assert detect_language("archive.tar.gz") == "unknown"
    assert detect_language("Dockerfile") == "unknown"
    print("  -> PASSED: language detection (all required + unknown)")

def test_truncation_logic():
    print("Testing 500 changed-line truncation limit...")
    # Under limit (50 lines)
    patch_under = "".join([f"+line {i}\n" for i in range(50)])
    p1, trunc1, changed1 = process_patch(patch_under, 30, 20)
    assert not trunc1
    assert changed1 == 50
    assert p1 == patch_under

    # Exactly 500 lines
    patch_500 = "".join([f"+line {i}\n" for i in range(500)])
    p2, trunc2, changed2 = process_patch(patch_500, 250, 250)
    assert not trunc2
    assert changed2 == 500

    # Over 500 lines (e.g. 600 lines)
    patch_over = "".join([f"+line {i}\n" for i in range(600)])
    p3, trunc3, changed3 = process_patch(patch_over, 400, 200)
    assert trunc3 is True
    assert changed3 == 600
    assert "TRUNCATED" in p3
    assert len(p3.splitlines()) <= 502  # 500 lines + truncation notice
    print("  -> PASSED: 500 changed-line truncation logic")

def test_invalid_urls():
    print("Testing invalid GitHub URLs...")
    r1 = client.post("/api/ingest", json={"url": "https://notgithub.com/foo/bar"})
    assert r1.status_code == 400
    
    r2 = client.post("/api/ingest", json={"url": "https://github.com/owner/repo"})
    assert r2.status_code == 400

    r3 = client.post("/api/ingest", json={"url": "not a url"})
    assert r3.status_code == 400
    print("  -> PASSED: invalid GitHub URLs return HTTP 400")

def test_real_pr_ingest():
    print("Testing real public GitHub PR ingestion...")
    # Public pull request on a stable public repo: pallets/flask PR #6162
    url = "https://github.com/pallets/flask/pull/6162"
    resp = client.post("/api/ingest", json={"url": url})
    print(f"  Response status: {resp.status_code}")
    if resp.status_code in (403, 404):
        print(f"  -> NOTE: GitHub API returned {resp.status_code}, handled gracefully as expected")
    else:
        assert resp.status_code == 200, f"Error: {resp.text}"
        data = resp.json()
        assert data["source_url"] == url
        assert data["repository"] == "pallets/flask"
        assert data["source_type"] == "pull_request"
        assert data["source_id"] == "6162"
        assert "files" in data
        assert isinstance(data["files"], list)
        assert data["total_files"] == len(data["files"])
        assert "total_changed_lines" in data
        assert "truncated_files" in data
        print(f"  Files count: {data['total_files']}, Total changed lines: {data['total_changed_lines']}")
        print("  -> PASSED: Public GitHub PR ingestion")

def test_real_commit_ingest():
    print("Testing real public GitHub commit ingestion...")
    # Public commit on pallets/flask
    sha = "d73fa1cdcbd8b1465c151db8924ba58b1dd14e35"
    url = f"https://github.com/pallets/flask/commit/{sha}"
    resp = client.post("/api/ingest", json={"url": url})
    print(f"  Response status: {resp.status_code}")
    if resp.status_code in (403, 404, 422):
        print(f"  -> NOTE: GitHub API returned {resp.status_code}, handled gracefully as expected")
    else:
        assert resp.status_code == 200, f"Error: {resp.text}"
        data = resp.json()
        assert data["source_url"] == url
        assert data["repository"] == "pallets/flask"
        assert data["source_type"] == "commit"
        assert data["source_id"] == sha
        assert "files" in data
        assert isinstance(data["files"], list)
        assert data["total_files"] == len(data["files"])
        print(f"  Files count: {data['total_files']}, Total changed lines: {data['total_changed_lines']}")
        print("  -> PASSED: Public GitHub commit ingestion")

if __name__ == "__main__":
    test_health()
    test_api_status()
    test_existing_endpoints()
    test_language_detection()
    test_truncation_logic()
    test_invalid_urls()
    test_real_pr_ingest()
    test_real_commit_ingest()

    test_token_header_construction()
    test_no_github_token()
    test_invalid_token_error()
    test_simulated_403_rate_limit()
    test_simulated_403_forbidden()
    test_simulated_404()
    test_public_pr_other_users_repo()

    print("\n==========================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("==========================================")


def test_token_header_construction():
    print("Testing GITHUB_TOKEN header construction...")
    from parser.github_ingest import get_github_headers
    orig_token = os.environ.get("GITHUB_TOKEN")
    os.environ["GITHUB_TOKEN"] = "dummy_token_for_test"
    headers = get_github_headers()
    assert headers["Authorization"] == "Bearer dummy_token_for_test"
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"

    os.environ["GITHUB_TOKEN"] = "Bearer dummy_token_2"
    headers = get_github_headers()
    assert headers["Authorization"] == "Bearer dummy_token_2"

    if orig_token is not None:
        os.environ["GITHUB_TOKEN"] = orig_token
    else:
        os.environ.pop("GITHUB_TOKEN", None)
    print("  -> PASSED: GITHUB_TOKEN header construction")


def test_no_github_token():
    print("Testing unauthenticated headers when GITHUB_TOKEN is not set...")
    from parser.github_ingest import get_github_headers
    orig_token = os.environ.get("GITHUB_TOKEN")
    os.environ.pop("GITHUB_TOKEN", None)
    headers = get_github_headers()
    assert "Authorization" not in headers
    assert headers["Accept"] == "application/vnd.github+json"
    if orig_token is not None:
        os.environ["GITHUB_TOKEN"] = orig_token
    print("  -> PASSED: No GITHUB_TOKEN allows unauthenticated access")


def test_invalid_token_error():
    print("Testing 401 invalid token handling...")
    import httpx
    from fastapi import HTTPException
    from parser.github_ingest import handle_github_error_response
    req = httpx.Request("GET", "https://api.github.com/repos/pallets/flask/pulls/1/files")
    resp_401 = httpx.Response(401, request=req, json={"message": "Bad credentials"})
    try:
        handle_github_error_response(resp_401, "pull_request")
        assert False, "Should have raised HTTPException(401)"
    except HTTPException as exc:
        assert exc.status_code == 401
        assert "GitHub authentication failed" in exc.detail
        assert "token" in exc.detail.lower()
    print("  -> PASSED: 401 invalid token returns safe message")


def test_simulated_403_rate_limit():
    print("Testing simulated 403 rate-limit response...")
    import httpx
    from fastapi import HTTPException
    from parser.github_ingest import handle_github_error_response
    req = httpx.Request("GET", "https://api.github.com/repos/pallets/flask/pulls/1/files")
    resp_403_rl = httpx.Response(
        403,
        request=req,
        headers={"x-ratelimit-remaining": "0"},
        json={"message": "API rate limit exceeded for 1.2.3.4"}
    )
    try:
        handle_github_error_response(resp_403_rl, "pull_request")
        assert False, "Should have raised HTTPException(403)"
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "rate limit exceeded" in exc.detail.lower()
        assert "configure a github token" in exc.detail.lower()
    print("  -> PASSED: 403 rate limit returns clear advice")


def test_simulated_403_forbidden():
    print("Testing simulated 403 forbidden access...")
    import httpx
    from fastapi import HTTPException
    from parser.github_ingest import handle_github_error_response
    req = httpx.Request("GET", "https://api.github.com/repos/pallets/flask/pulls/1/files")
    resp_403_fb = httpx.Response(
        403,
        request=req,
        headers={"x-ratelimit-remaining": "4000"},
        json={"message": "Must have admin rights to Repository"}
    )
    try:
        handle_github_error_response(resp_403_fb, "pull_request")
        assert False, "Should have raised HTTPException(403)"
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "forbidden" in exc.detail.lower()
    print("  -> PASSED: 403 forbidden distinguishes from rate limit")


def test_simulated_404():
    print("Testing simulated 404 not found response...")
    import httpx
    from fastapi import HTTPException
    from parser.github_ingest import handle_github_error_response
    req = httpx.Request("GET", "https://api.github.com/repos/pallets/flask/pulls/99999/files")
    resp_404 = httpx.Response(404, request=req, json={"message": "Not Found"})
    try:
        handle_github_error_response(resp_404, "pull_request")
        assert False, "Should have raised HTTPException(404)"
    except HTTPException as exc:
        assert exc.status_code == 404
        assert "not found" in exc.detail.lower()
    print("  -> PASSED: 404 returns not found message")


def test_public_pr_other_users_repo():
    print("Testing public PR from another user's public repository...")
    url = "https://github.com/pallets/flask/pull/6162"
    resp = client.post("/api/ingest", json={"url": url})
    assert resp.status_code == 200, f"Failed: {resp.text}"
    data = resp.json()
    assert data["repository"] == "pallets/flask"
    assert data["total_files"] >= 1
    print(f"  -> PASSED: Successfully fetched {data['total_files']} files from pallets/flask")
