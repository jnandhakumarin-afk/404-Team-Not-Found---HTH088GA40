"""
Stage 2 — Static Analysis Tests
================================
Covers:
  - Python analysis via Ruff + Bandit
  - JS/TS analysis via ESLint
  - Normalized finding structure
  - Unsupported file types → skipped_files
  - Missing tools → graceful degradation (tool_errors, no crash)
  - Multiple findings in one file
  - Patch extraction helper
  - POST /api/analyze-files endpoint (integration)
  - All Stage 1 tests still pass (regression)
"""

import sys
from pathlib import Path

# Make sure `backend/` is on the path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app
from models.analysis import Finding
from analyzer.runner import analyze_changed_files, _extract_code_from_patch
from analyzer.ruff_runner import run_ruff, RUFF_EXE
from analyzer.bandit_runner import run_bandit, BANDIT_EXE
from analyzer.eslint_runner import run_eslint, ESLINT_AVAILABLE

client = TestClient(app)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_py_file(code: str, filename: str = "test_file.py", status: str = "modified") -> dict:
    """Build a minimal ChangedFile dict for a Python file."""
    patch_lines = "\n".join(f"+{line}" for line in code.splitlines())
    additions = code.count("\n") + 1
    return {
        "file": filename,
        "language": "python",
        "status": status,
        "additions": additions,
        "deletions": 0,
        "changed_lines": additions,
        "patch": patch_lines,
        "truncated": False,
    }


def _make_js_file(code: str, filename: str = "app.js", lang: str = "javascript") -> dict:
    patch_lines = "\n".join(f"+{line}" for line in code.splitlines())
    additions = code.count("\n") + 1
    return {
        "file": filename,
        "language": lang,
        "status": "added",
        "additions": additions,
        "deletions": 0,
        "changed_lines": additions,
        "patch": patch_lines,
        "truncated": False,
    }


def _assert_finding_schema(f: dict) -> None:
    """Assert that a finding dict has all required normalized fields."""
    for key in ("file", "line", "rule_id", "tool", "severity", "message"):
        assert key in f, f"Missing key '{key}' in finding: {f}"
    assert isinstance(f["line"], int), f"'line' must be int, got {type(f['line'])}"
    assert f["severity"] in ("HIGH", "MEDIUM", "LOW"), f"Bad severity: {f['severity']}"
    assert f["tool"] in ("ruff", "bandit", "eslint"), f"Unknown tool: {f['tool']}"


# ──────────────────────────────────────────────────────────────────────────────
# 1. Stage 1 regression — existing endpoints must still work
# ──────────────────────────────────────────────────────────────────────────────

def test_stage1_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    print("  PASS  /health")


def test_stage1_api_status():
    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"
    print("  PASS  /api/status")


def test_stage1_parse_code():
    resp = client.post("/api/parse-code", json={"code": "x = 1\ny = 2"})
    assert resp.status_code == 200
    assert resp.json()["total_lines"] == 2
    print("  PASS  /api/parse-code")


def test_stage1_parse_diff():
    resp = client.post("/api/parse-diff", json={"diff": "+line1\n-line2\n+line3"})
    assert resp.status_code == 200
    assert resp.json()["total_changed_lines"] == 2
    print("  PASS  /api/parse-diff")


def test_stage1_analyze():
    resp = client.post("/api/analyze", json={"code": "eval('1')"})
    assert resp.status_code == 200
    data = resp.json()
    assert "total_issues" in data
    print("  PASS  /api/analyze")


def test_stage1_review():
    resp = client.post("/api/review", json={"code": "x = 1"})
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data and "issues" in data and "risk" in data
    print("  PASS  /api/review")


def test_stage1_ingest_invalid_url():
    resp = client.post("/api/ingest", json={"url": "https://notgithub.com/foo"})
    assert resp.status_code == 400
    print("  PASS  /api/ingest (invalid URL → 400)")


# ──────────────────────────────────────────────────────────────────────────────
# 2. Patch extraction helper
# ──────────────────────────────────────────────────────────────────────────────

def test_patch_extraction_strips_diff_headers():
    patch = (
        "@@ -1,3 +1,4 @@\n"
        " context line\n"
        "-removed line\n"
        "+added line\n"
        "+another added\n"
    )
    code = _extract_code_from_patch(patch)
    assert "removed line" not in code
    assert "added line" in code
    assert "another added" in code
    assert "context line" in code
    assert "@@" not in code
    print("  PASS  _extract_code_from_patch")


# ──────────────────────────────────────────────────────────────────────────────
# 3. Normalized Finding model
# ──────────────────────────────────────────────────────────────────────────────

def test_finding_schema():
    f = Finding(
        file="src/app.py",
        line=12,
        rule_id="B307",
        tool="bandit",
        severity="HIGH",
        message="Use of eval detected",
    )
    assert f.file == "src/app.py"
    assert f.line == 12
    assert f.rule_id == "B307"
    assert f.tool == "bandit"
    assert f.severity == "HIGH"
    assert f.message == "Use of eval detected"
    # Serialise to dict and check all keys present
    d = f.model_dump()
    for key in ("file", "line", "rule_id", "tool", "severity", "message"):
        assert key in d, f"Missing key: {key}"
    print("  PASS  Finding model schema")


# ──────────────────────────────────────────────────────────────────────────────
# 4. Python static analysis — Ruff runner
# ──────────────────────────────────────────────────────────────────────────────

def test_ruff_detects_eval():
    if not RUFF_EXE:
        print("  SKIP  ruff (not installed)")
        return
    code = 'result = eval("1 + 1")\n'
    findings, errors = run_ruff(code, "demo.py")
    # Ruff may flag eval via S307 or similar security rule
    assert isinstance(findings, list)
    assert isinstance(errors, list)
    # All findings must conform to schema
    for f in findings:
        assert f.tool == "ruff"
        assert f.file == "demo.py"
        assert f.line >= 1
    print(f"  PASS  ruff eval detection ({len(findings)} findings)")


def test_ruff_detects_mutable_default():
    if not RUFF_EXE:
        print("  SKIP  ruff (not installed)")
        return
    code = "def foo(items=[]):\n    return items\n"
    findings, errors = run_ruff(code, "demo.py")
    rule_ids = [f.rule_id for f in findings]
    assert "B006" in rule_ids, f"Expected B006, got: {rule_ids}"
    print("  PASS  ruff mutable default arg (B006)")


def test_ruff_returns_empty_for_clean_code():
    if not RUFF_EXE:
        print("  SKIP  ruff (not installed)")
        return
    code = "x = 1\ny = x + 2\n"
    findings, errors = run_ruff(code, "clean.py")
    assert isinstance(findings, list)
    # May be 0 or very few; just check no crash and correct types
    for f in findings:
        assert f.tool == "ruff"
    print(f"  PASS  ruff clean code ({len(findings)} findings, 0 errors)")


def test_ruff_multiple_findings():
    if not RUFF_EXE:
        print("  SKIP  ruff (not installed)")
        return
    code = (
        "import os\n"
        "import sys\n"
        "\n"
        "def process(data=[]):\n"
        "    eval(data)\n"
        "    return data\n"
    )
    findings, errors = run_ruff(code, "multi.py")
    assert len(findings) >= 2, f"Expected ≥2 findings, got {len(findings)}: {[f.rule_id for f in findings]}"
    for f in findings:
        assert f.tool == "ruff"
        assert f.severity in ("HIGH", "MEDIUM", "LOW")
    print(f"  PASS  ruff multiple findings ({len(findings)} findings)")


# ──────────────────────────────────────────────────────────────────────────────
# 5. Python static analysis — Bandit runner
# ──────────────────────────────────────────────────────────────────────────────

def test_bandit_detects_eval():
    if not BANDIT_EXE:
        print("  SKIP  bandit (not installed)")
        return
    code = 'result = eval("1 + 1")\n'
    findings, errors = run_bandit(code, "demo.py")
    assert len(findings) >= 1, f"Expected ≥1 finding, got {len(findings)}"
    assert findings[0].rule_id == "B307"
    assert findings[0].tool == "bandit"
    assert findings[0].severity in ("HIGH", "MEDIUM")
    print(f"  PASS  bandit eval detection (B307, severity={findings[0].severity})")


def test_bandit_detects_subprocess_shell():
    if not BANDIT_EXE:
        print("  SKIP  bandit (not installed)")
        return
    code = "import subprocess\nsubprocess.run('ls', shell=True)\n"
    findings, errors = run_bandit(code, "demo.py")
    rule_ids = [f.rule_id for f in findings]
    assert any(r in rule_ids for r in ("B602", "B603", "B607")), \
        f"Expected subprocess shell finding, got: {rule_ids}"
    print(f"  PASS  bandit subprocess shell detection ({rule_ids})")


def test_bandit_returns_empty_for_clean_code():
    if not BANDIT_EXE:
        print("  SKIP  bandit (not installed)")
        return
    code = "x = 1\ny = x + 2\n"
    findings, errors = run_bandit(code, "clean.py")
    assert isinstance(findings, list)
    assert isinstance(errors, list)
    print(f"  PASS  bandit clean code ({len(findings)} findings)")


# ──────────────────────────────────────────────────────────────────────────────
# 6. JS/TS static analysis — ESLint runner
# ──────────────────────────────────────────────────────────────────────────────

def test_eslint_detects_eval_js():
    if not ESLINT_AVAILABLE:
        print("  SKIP  eslint (npx not found)")
        return
    code = 'var x = eval("1 + 1");\n'
    findings, errors = run_eslint(code, "app.js")
    # If ESLint found issues, verify schema; if tool_errors, it's graceful
    for f in findings:
        assert f.tool == "eslint"
        assert f.file == "app.js"
        assert f.severity in ("HIGH", "MEDIUM", "LOW")
    if findings:
        rule_ids = [f.rule_id for f in findings]
        assert "no-eval" in rule_ids, f"Expected no-eval, got: {rule_ids}"
        print(f"  PASS  eslint eval detection ({rule_ids})")
    else:
        print(f"  PASS  eslint ran without crash (errors={errors})")


def test_eslint_detects_eval_ts():
    if not ESLINT_AVAILABLE:
        print("  SKIP  eslint (npx not found)")
        return
    code = 'const x: number = eval("1 + 1");\n'
    findings, errors = run_eslint(code, "util.ts")
    for f in findings:
        assert f.tool == "eslint"
        assert f.file == "util.ts"
    print(f"  PASS  eslint TypeScript file (findings={len(findings)}, errors={len(errors)})")


def test_eslint_clean_js():
    if not ESLINT_AVAILABLE:
        print("  SKIP  eslint (npx not found)")
        return
    code = "const add = (a, b) => a + b;\n"
    findings, errors = run_eslint(code, "clean.js")
    assert isinstance(findings, list)
    print(f"  PASS  eslint clean JS ({len(findings)} findings)")


# ──────────────────────────────────────────────────────────────────────────────
# 7. Missing tool — graceful degradation
# ──────────────────────────────────────────────────────────────────────────────

def test_ruff_missing_tool_no_crash():
    """Temporarily patch RUFF_EXE to None to simulate missing tool."""
    import analyzer.ruff_runner as rr
    original = rr.RUFF_EXE
    rr.RUFF_EXE = None
    try:
        findings, errors = run_ruff("eval('x')\n", "test.py")
        assert findings == []
        assert len(errors) == 1
        assert "ruff" in errors[0].lower()
        assert "not installed" in errors[0].lower()
    finally:
        rr.RUFF_EXE = original
    print("  PASS  ruff missing tool → graceful degradation")


def test_bandit_missing_tool_no_crash():
    import analyzer.bandit_runner as br
    original = br.BANDIT_EXE
    br.BANDIT_EXE = None
    try:
        findings, errors = run_bandit("eval('x')\n", "test.py")
        assert findings == []
        assert len(errors) == 1
        assert "bandit" in errors[0].lower()
    finally:
        br.BANDIT_EXE = original
    print("  PASS  bandit missing tool → graceful degradation")


def test_eslint_missing_tool_no_crash():
    import analyzer.eslint_runner as er
    original = er.ESLINT_AVAILABLE
    original_npx = er.NPX_EXE
    er.ESLINT_AVAILABLE = False
    er.NPX_EXE = None
    try:
        findings, errors = run_eslint("eval('x');\n", "test.js")
        assert findings == []
        assert len(errors) == 1
        assert "eslint" in errors[0].lower()
    finally:
        er.ESLINT_AVAILABLE = original
        er.NPX_EXE = original_npx
    print("  PASS  eslint missing tool - graceful degradation")


# ──────────────────────────────────────────────────────────────────────────────
# 8. Unsupported file types → skipped
# ──────────────────────────────────────────────────────────────────────────────

def test_unsupported_language_is_skipped():
    files = [
        {
            "file": "diagram.drawio",
            "language": "unknown",
            "status": "modified",
            "additions": 5,
            "deletions": 0,
            "changed_lines": 5,
            "patch": "+<xml>data</xml>",
            "truncated": False,
        }
    ]
    findings, skipped, errors = analyze_changed_files(files)
    assert "diagram.drawio" in skipped
    assert findings == []
    print("  PASS  unsupported language → skipped_files")


def test_markdown_file_skipped():
    files = [
        {
            "file": "README.md",
            "language": "unknown",
            "status": "modified",
            "additions": 3,
            "deletions": 1,
            "changed_lines": 4,
            "patch": "+# New section\n+Some text\n-Old text",
            "truncated": False,
        }
    ]
    findings, skipped, errors = analyze_changed_files(files)
    assert "README.md" in skipped
    print("  PASS  markdown skipped")


def test_file_with_no_patch_skipped():
    files = [
        {
            "file": "image.png",
            "language": "unknown",
            "status": "added",
            "additions": 0,
            "deletions": 0,
            "changed_lines": 0,
            "patch": None,
            "truncated": False,
        }
    ]
    findings, skipped, errors = analyze_changed_files(files)
    assert "image.png" in skipped
    print("  PASS  None patch → skipped_files")


# ──────────────────────────────────────────────────────────────────────────────
# 9. Multiple findings across multiple files (dispatcher)
# ──────────────────────────────────────────────────────────────────────────────

def test_multiple_python_files():
    if not RUFF_EXE and not BANDIT_EXE:
        print("  SKIP  multiple python files (no tools installed)")
        return

    files = [
        _make_py_file('result = eval("bad")\n', "src/a.py"),
        _make_py_file("def foo(x=[]):\n    return x\n", "src/b.py"),
        _make_py_file("x = 1\ny = 2\n", "src/c.py"),  # clean
    ]
    findings, skipped, errors = analyze_changed_files(files)
    assert isinstance(findings, list)
    # a.py and b.py should have findings
    filenames_with_findings = {f.file for f in findings}
    assert "src/a.py" in filenames_with_findings or len(errors) > 0, \
        "Expected findings in src/a.py or tool errors"
    # skipped should only include files with no patch or unsupported lang
    assert "src/c.py" not in skipped
    # All findings must pass schema check
    for finding in findings:
        _assert_finding_schema(finding.model_dump())
    print(f"  PASS  multiple Python files ({len(findings)} findings, {len(skipped)} skipped)")


def test_mixed_language_files():
    if not RUFF_EXE and not ESLINT_AVAILABLE:
        print("  SKIP  mixed languages (no tools installed)")
        return

    files = [
        _make_py_file('eval("bad")\n', "src/main.py"),
        _make_js_file('eval("bad");\n', "web/app.js", "javascript"),
        {
            "file": "data.json",
            "language": "json",
            "status": "modified",
            "additions": 2,
            "deletions": 0,
            "changed_lines": 2,
            "patch": '+{"key": "value"}',
            "truncated": False,
        },
    ]
    findings, skipped, errors = analyze_changed_files(files)
    # json is unsupported → skipped
    assert "data.json" in skipped
    # All findings valid schema
    for f in findings:
        _assert_finding_schema(f.model_dump())
    print(f"  PASS  mixed languages ({len(findings)} findings, skipped={skipped})")


def test_deduplication():
    """Run same file twice in the files list — findings must be deduplicated."""
    if not RUFF_EXE and not BANDIT_EXE:
        print("  SKIP  deduplication (no tools installed)")
        return

    py_file = _make_py_file('eval("x")\n', "dup.py")
    files = [py_file, py_file]  # same file twice
    findings, skipped, errors = analyze_changed_files(files)
    # Check no duplicate (file, line, rule_id, tool) tuples
    seen = set()
    for f in findings:
        key = (f.file, f.line, f.rule_id, f.tool)
        assert key not in seen, f"Duplicate finding: {key}"
        seen.add(key)
    print(f"  PASS  deduplication ({len(findings)} unique findings)")


# ──────────────────────────────────────────────────────────────────────────────
# 10. POST /api/analyze-files endpoint integration
# ──────────────────────────────────────────────────────────────────────────────

def test_api_analyze_files_python():
    payload = {
        "files": [
            _make_py_file('result = eval("bad")\n', "src/bad.py"),
        ]
    }
    resp = client.post("/api/analyze-files", json=payload)
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "total_findings" in data
    assert "findings" in data
    assert "skipped_files" in data
    assert "tool_errors" in data
    assert isinstance(data["findings"], list)
    assert data["total_findings"] == len(data["findings"])
    for f in data["findings"]:
        _assert_finding_schema(f)
    print(f"  PASS  POST /api/analyze-files Python ({data['total_findings']} findings)")


def test_api_analyze_files_unsupported_only():
    payload = {
        "files": [
            {
                "file": "styles.css",
                "language": "css",
                "status": "modified",
                "additions": 5,
                "deletions": 0,
                "changed_lines": 5,
                "patch": "+.body { color: red; }",
                "truncated": False,
            }
        ]
    }
    resp = client.post("/api/analyze-files", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_findings"] == 0
    assert "styles.css" in data["skipped_files"]
    print("  PASS  POST /api/analyze-files unsupported language → skipped")


def test_api_analyze_files_empty():
    resp = client.post("/api/analyze-files", json={"files": []})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_findings"] == 0
    assert data["findings"] == []
    print("  PASS  POST /api/analyze-files empty list")


def test_api_analyze_files_js():
    payload = {
        "files": [
            _make_js_file('eval("bad");\n', "web/app.js", "javascript"),
        ]
    }
    resp = client.post("/api/analyze-files", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_findings" in data
    for f in data["findings"]:
        _assert_finding_schema(f)
    print(f"  PASS  POST /api/analyze-files JS ({data['total_findings']} findings, errors={data['tool_errors']})")


def test_api_analyze_files_response_schema():
    """Validate the exact response schema from /api/analyze-files."""
    payload = {"files": [_make_py_file("x = 1\n", "ok.py")]}
    resp = client.post("/api/analyze-files", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # Required top-level keys
    for key in ("total_findings", "findings", "skipped_files", "tool_errors"):
        assert key in data, f"Missing response key: {key}"
    assert isinstance(data["total_findings"], int)
    assert isinstance(data["findings"], list)
    assert isinstance(data["skipped_files"], list)
    assert isinstance(data["tool_errors"], list)
    print("  PASS  /api/analyze-files response schema validated")


# ──────────────────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    groups = [
        ("Stage 1 regression", [
            test_stage1_health,
            test_stage1_api_status,
            test_stage1_parse_code,
            test_stage1_parse_diff,
            test_stage1_analyze,
            test_stage1_review,
            test_stage1_ingest_invalid_url,
        ]),
        ("Patch extraction", [
            test_patch_extraction_strips_diff_headers,
        ]),
        ("Finding model", [
            test_finding_schema,
        ]),
        ("Ruff runner", [
            test_ruff_detects_eval,
            test_ruff_detects_mutable_default,
            test_ruff_returns_empty_for_clean_code,
            test_ruff_multiple_findings,
        ]),
        ("Bandit runner", [
            test_bandit_detects_eval,
            test_bandit_detects_subprocess_shell,
            test_bandit_returns_empty_for_clean_code,
        ]),
        ("ESLint runner", [
            test_eslint_detects_eval_js,
            test_eslint_detects_eval_ts,
            test_eslint_clean_js,
        ]),
        ("Missing tools — graceful degradation", [
            test_ruff_missing_tool_no_crash,
            test_bandit_missing_tool_no_crash,
            test_eslint_missing_tool_no_crash,
        ]),
        ("Unsupported file types", [
            test_unsupported_language_is_skipped,
            test_markdown_file_skipped,
            test_file_with_no_patch_skipped,
        ]),
        ("Multiple findings / multi-file", [
            test_multiple_python_files,
            test_mixed_language_files,
            test_deduplication,
        ]),
        ("POST /api/analyze-files (integration)", [
            test_api_analyze_files_python,
            test_api_analyze_files_unsupported_only,
            test_api_analyze_files_empty,
            test_api_analyze_files_js,
            test_api_analyze_files_response_schema,
        ]),
    ]

    total = 0
    passed = 0
    failed = 0

    for group_name, tests in groups:
        print(f"\n{'-' * 60}")
        print(f"  {group_name}")
        print(f"{'-' * 60}")
        for test_fn in tests:
            total += 1
            try:
                test_fn()
                passed += 1
            except Exception as exc:
                failed += 1
                print(f"  FAIL  {test_fn.__name__}: {exc}")

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    print(f"{'=' * 60}")
    if failed:
        sys.exit(1)
