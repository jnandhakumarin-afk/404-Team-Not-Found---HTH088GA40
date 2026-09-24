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
    print("\n==========================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("==========================================")
