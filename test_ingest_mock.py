import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_mocked_pr_ingestion():
    mock_files = [
        {
            "filename": "src/app.py",
            "status": "modified",
            "additions": 10,
            "deletions": 5,
            "patch": "@@ -1,5 +1,10 @@\n+print('hello')\n-old()\n"
        },
        {
            "filename": "web/index.ts",
            "status": "added",
            "additions": 300,
            "deletions": 250,  # 550 changed lines -> truncated!
            "patch": "\n".join([f"+line {i}" for i in range(550)])
        },
        {
            "filename": "unknown.xyz",
            "status": "added",
            "additions": 1,
            "deletions": 0,
            "patch": "+custom"
        }
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.is_error = False
    mock_resp.json.return_value = mock_files

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        res = client.post("/api/ingest", json={"url": "https://github.com/my-org/my-repo/pull/42"})
        assert res.status_code == 200
        data = res.json()
        assert data["repository"] == "my-org/my-repo"
        assert data["source_type"] == "pull_request"
        assert data["source_id"] == "42"
        assert data["total_files"] == 3
        assert data["total_changed_lines"] == (15 + 550 + 1)
        assert data["truncated_files"] == ["web/index.ts"]

        # Check file 0
        f0 = data["files"][0]
        assert f0["file"] == "src/app.py"
        assert f0["language"] == "python"
        assert f0["changed_lines"] == 15
        assert f0["truncated"] is False

        # Check file 1 (over 500 lines)
        f1 = data["files"][1]
        assert f1["file"] == "web/index.ts"
        assert f1["language"] == "typescript"
        assert f1["changed_lines"] == 550
        assert f1["truncated"] is True
        assert "[TRUNCATED: Exceeded 500 changed lines]" in f1["patch"]

        # Check file 2 (unknown language)
        f2 = data["files"][2]
        assert f2["file"] == "unknown.xyz"
        assert f2["language"] == "unknown"
        assert f2["truncated"] is False

    print("Mocked PR ingestion verified successfully!")

def test_mocked_commit_ingestion():
    mock_payload = {
        "sha": "a1b2c3d4e5f6",
        "files": [
            {
                "filename": "main.go",
                "status": "modified",
                "additions": 20,
                "deletions": 2,
                "patch": "@@ -1,2 +1,20 @@\n+package main\n"
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.is_error = False
    mock_resp.json.return_value = mock_payload

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        res = client.post("/api/ingest", json={"url": "https://github.com/my-org/my-repo/commit/a1b2c3d4e5f6"})
        assert res.status_code == 200
        data = res.json()
        assert data["repository"] == "my-org/my-repo"
        assert data["source_type"] == "commit"
        assert data["source_id"] == "a1b2c3d4e5f6"
        assert data["total_files"] == 1
        assert data["files"][0]["language"] == "go"
        assert data["files"][0]["changed_lines"] == 22

    print("Mocked Commit ingestion verified successfully!")

if __name__ == "__main__":
    test_mocked_pr_ingestion()
    test_mocked_commit_ingestion()
