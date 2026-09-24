"""
Stage 3 - AI/LLM Code Review Tests
===================================
Covers:
  - Valid Anthropic response parsing
  - Malformed JSON response triggers retry
  - Pydantic validation failure triggers retry
  - Retry failure falls back to static-only findings
  - API failure falls back to static-only findings
  - Static finding deduplication
  - LLM-only finding schema and source
  - Missing ANTHROPIC_API_KEY handling
  - Source and rule_id schema validation
  - Empty diff / empty static findings handling
  - POST /api/review integration with Stage 3
"""

import sys
import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure backend/ is in sys.path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app
from models.review import ReviewFinding, LLMReviewPayload, ReviewResponse
from ai.reviewer import review_code, static_finding_to_review_finding, merge_and_deduplicate

test_client = TestClient(app)


def _make_mock_anthropic_response(text_content: str):
    """Create a mock Anthropic messages response object."""
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = text_content

    mock_resp = MagicMock()
    mock_resp.content = [mock_block]
    return mock_resp


# ----------------------------------------------------------------------
# 1. Missing API Key Test
# ----------------------------------------------------------------------
def test_missing_api_key():
    print("Testing missing ANTHROPIC_API_KEY...")
    with patch.dict(os.environ, {}, clear=True):
        if "ANTHROPIC_API_KEY" in os.environ:
            del os.environ["ANTHROPIC_API_KEY"]

        static_issues = [
            {
                "file": "app.py",
                "line": 4,
                "rule_id": "B307",
                "tool": "bandit",
                "severity": "HIGH",
                "message": "Use of eval detected",
            }
        ]
        result = review_code(code="eval('bad')", static_issues=static_issues)
        assert result["fallback_to_static"] is True
        assert result["total_findings"] == 1
        assert result["findings"][0]["rule_id"] == "B307"
        assert result["findings"][0]["source"] == "static"
        assert any("ANTHROPIC_API_KEY" in err for err in result["errors"])
    print("  PASS  Missing API key handled gracefully with static fallback")


# ----------------------------------------------------------------------
# 2. Valid Anthropic Response Test
# ----------------------------------------------------------------------
def test_valid_anthropic_response():
    print("Testing valid Anthropic response parsing...")
    mock_llm_json = {
        "summary": "Found 1 security vulnerability and 1 bug.",
        "findings": [
            {
                "file": "main.py",
                "line": 10,
                "category": "security",
                "source": "static",
                "rule_id": "B307",
                "evidence": "eval(user_input)",
                "explanation": "Dynamic code evaluation via eval().",
                "suggested_fix": "Use ast.literal_eval or safe alternatives.",
                "confidence": "high"
            },
            {
                "file": "main.py",
                "line": 25,
                "category": "bug",
                "source": "llm",
                "rule_id": None,
                "evidence": "if x is 5:",
                "explanation": "Comparison of literal using identity operator.",
                "suggested_fix": "Use '==' instead of 'is'.",
                "confidence": "high"
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_anthropic_response(json.dumps(mock_llm_json))

    static_issues = [
        {
            "file": "main.py",
            "line": 10,
            "rule_id": "B307",
            "tool": "bandit",
            "severity": "HIGH",
            "message": "eval detected",
        }
    ]

    result = review_code(
        code="eval(user_input)",
        static_issues=static_issues,
        client=mock_client
    )

    assert result["fallback_to_static"] is False
    assert result["total_findings"] == 2
    assert result["summary"] == "Found 1 security vulnerability and 1 bug."

    # Validate findings schema
    f0 = result["findings"][0]
    assert f0["file"] == "main.py"
    assert f0["source"] == "static"
    assert f0["rule_id"] == "B307"

    f1 = result["findings"][1]
    assert f1["file"] == "main.py"
    assert f1["source"] == "llm"
    assert f1["rule_id"] is None
    print("  PASS  Valid Anthropic response parsed and validated")


# ----------------------------------------------------------------------
# 3. Malformed JSON Response Triggers Retry
# ----------------------------------------------------------------------
def test_malformed_json_retry_once():
    print("Testing malformed JSON retry behavior...")
    valid_json = {
        "summary": "Recovered on retry.",
        "findings": [
            {
                "file": "service.py",
                "line": 15,
                "category": "bug",
                "source": "llm",
                "rule_id": None,
                "evidence": "return a / 0",
                "explanation": "Division by zero.",
                "suggested_fix": "Ensure denominator is non-zero.",
                "confidence": "high"
            }
        ]
    }

    # Attempt 1 returns broken JSON; Attempt 2 returns valid JSON
    bad_resp = _make_mock_anthropic_response("This is not JSON at all: { broken ...")
    good_resp = _make_mock_anthropic_response(json.dumps(valid_json))

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [bad_resp, good_resp]

    result = review_code(
        code="return a / 0",
        static_issues=[],
        client=mock_client
    )

    assert mock_client.messages.create.call_count == 2
    assert result["fallback_to_static"] is False
    assert result["total_findings"] == 1
    assert result["summary"] == "Recovered on retry."
    print("  PASS  Malformed JSON triggers exactly 1 retry and recovers")


# ----------------------------------------------------------------------
# 4. Pydantic Validation Failure Triggers Retry
# ----------------------------------------------------------------------
def test_pydantic_validation_failure_retry():
    print("Testing Pydantic validation failure retry...")
    invalid_schema_json = {
        "summary": "Invalid schema",
        "findings": [
            {
                "file": "app.py",
                # Missing line, invalid category
                "category": "not_a_valid_category",
                "source": "invalid_source",
            }
        ]
    }

    valid_json = {
        "summary": "Valid after retry",
        "findings": [
            {
                "file": "app.py",
                "line": 12,
                "category": "security",
                "source": "llm",
                "rule_id": None,
                "evidence": "token = '12345'",
                "explanation": "Hardcoded secret token.",
                "suggested_fix": "Use environment variables.",
                "confidence": "high"
            }
        ]
    }

    bad_resp = _make_mock_anthropic_response(json.dumps(invalid_schema_json))
    good_resp = _make_mock_anthropic_response(json.dumps(valid_json))

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [bad_resp, good_resp]

    result = review_code(
        code="token = '12345'",
        static_issues=[],
        client=mock_client
    )

    assert mock_client.messages.create.call_count == 2
    assert result["fallback_to_static"] is False
    assert result["findings"][0]["category"] == "security"
    print("  PASS  Pydantic validation failure triggers retry and succeeds")


# ----------------------------------------------------------------------
# 5. Static-Only Fallback After Retry Fails
# ----------------------------------------------------------------------
def test_static_fallback_after_retry_fails():
    print("Testing static-only fallback after retry fails...")
    bad_resp1 = _make_mock_anthropic_response("Invalid 1")
    bad_resp2 = _make_mock_anthropic_response("Invalid 2")

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [bad_resp1, bad_resp2]

    static_issues = [
        {
            "file": "test.py",
            "line": 3,
            "rule_id": "B006",
            "tool": "ruff",
            "severity": "HIGH",
            "message": "Mutable default argument",
        }
    ]

    result = review_code(
        code="def f(x=[]): pass",
        static_issues=static_issues,
        client=mock_client
    )

    assert mock_client.messages.create.call_count == 2
    assert result["fallback_to_static"] is True
    assert result["total_findings"] == 1
    assert result["findings"][0]["rule_id"] == "B006"
    assert result["findings"][0]["source"] == "static"
    print("  PASS  Both attempts failing cleanly triggers static-only fallback")


# ----------------------------------------------------------------------
# 6. API Failure Fallback (Timeouts / Network Errors)
# ----------------------------------------------------------------------
def test_api_failure_fallback():
    print("Testing API failure / timeout fallback...")
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("Anthropic API connection timeout")

    static_issues = [
        {
            "file": "vuln.py",
            "line": 1,
            "rule_id": "SEC001",
            "tool": "bandit",
            "severity": "CRITICAL",
            "message": "Critical security bug",
        }
    ]

    result = review_code(
        code="bad()",
        static_issues=static_issues,
        client=mock_client
    )

    assert result["fallback_to_static"] is True
    assert result["total_findings"] == 1
    assert result["findings"][0]["rule_id"] == "SEC001"
    print("  PASS  API exception triggers static-only fallback without crash")


# ----------------------------------------------------------------------
# 7. Static Finding Deduplication
# ----------------------------------------------------------------------
def test_static_finding_deduplication():
    print("Testing static finding deduplication...")
    # Static analyzer found rule B307 on line 5
    static_sf = [
        static_finding_to_review_finding({
            "file": "app.py",
            "line": 5,
            "rule_id": "B307",
            "tool": "bandit",
            "severity": "HIGH",
            "message": "eval used",
        })
    ]

    # LLM also reports B307 on line 5 with better explanation
    llm_sf = [
        ReviewFinding(
            file="app.py",
            line=5,
            category="security",
            source="static",
            rule_id="B307",
            evidence="eval('1 + 1')",
            explanation="Dynamic evaluation is risky in production.",
            suggested_fix="Use ast.literal_eval.",
            confidence="high"
        )
    ]

    merged = merge_and_deduplicate(static_sf, llm_sf)
    assert len(merged) == 1
    assert merged[0].rule_id == "B307"
    assert merged[0].source == "static"
    assert "Dynamic evaluation" in merged[0].explanation
    print("  PASS  Static finding deduplicated and enriched")


# ----------------------------------------------------------------------
# 8. LLM-Only Finding Requirement
# ----------------------------------------------------------------------
def test_llm_only_finding():
    print("Testing LLM-only finding source and rule_id constraints...")
    static_sf = [
        static_finding_to_review_finding({
            "file": "app.py",
            "line": 2,
            "rule_id": "B006",
            "tool": "ruff",
            "severity": "HIGH",
            "message": "Mutable default",
        })
    ]

    # LLM reports a separate logic bug that static tool did not catch
    llm_sf = [
        ReviewFinding(
            file="app.py",
            line=10,
            category="bug",
            source="llm",
            rule_id=None,
            evidence="if count < 0: return",
            explanation="Negative count logic flaw.",
            suggested_fix="Raise ValueError on negative count.",
            confidence="moderate"
        )
    ]

    merged = merge_and_deduplicate(static_sf, llm_sf)
    assert len(merged) == 2

    # Check static finding
    assert merged[0].rule_id == "B006"
    assert merged[0].source == "static"

    # Check LLM-only finding
    assert merged[1].source == "llm"
    assert merged[1].rule_id is None
    assert merged[1].line == 10
    assert "if count < 0" in merged[1].evidence
    print("  PASS  LLM-only finding has source=llm and rule_id=None")


# ----------------------------------------------------------------------
# 9. Source and Schema Validation
# ----------------------------------------------------------------------
def test_source_and_rule_id_validation():
    print("Testing ReviewFinding Pydantic schema validation...")
    valid_f = ReviewFinding(
        file="foo.py",
        line=1,
        category="security",
        source="static",
        rule_id="SEC1",
        evidence="code",
        explanation="expl",
        suggested_fix="fix",
        confidence="high"
    )
    assert valid_f.source == "static"
    assert valid_f.rule_id == "SEC1"

    # Clean null string into None
    llm_f = ReviewFinding(
        file="foo.py",
        line=2,
        category="performance",
        source="llm",
        rule_id="null",
        evidence="loop",
        explanation="slow",
        suggested_fix="fast",
        confidence="moderate"
    )
    assert llm_f.source == "llm"
    assert llm_f.rule_id is None

    # Invalid category rejection
    try:
        ReviewFinding(
            file="foo.py",
            line=3,
            category="unsupported_category",
            source="llm",
            evidence="code",
            explanation="expl",
            suggested_fix="fix",
            confidence="high"
        )
        assert False, "Should have raised ValidationError for invalid category"
    except Exception:
        pass

    print("  PASS  ReviewFinding schema constraints validated")


# ----------------------------------------------------------------------
# 10. POST /api/review Integration Test
# ----------------------------------------------------------------------
def test_post_api_review_endpoint():
    print("Testing POST /api/review endpoint integration...")
    # Test POST /api/review with missing key (fallback)
    with patch.dict(os.environ, {}, clear=True):
        if "ANTHROPIC_API_KEY" in os.environ:
            del os.environ["ANTHROPIC_API_KEY"]

        resp = test_client.post(
            "/api/review",
            json={"code": "eval('bad')"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "findings" in data
        assert "issues" in data
        assert "risk" in data
        assert data["fallback_to_static"] is True
        assert len(data["findings"]) >= 1

    print("  PASS  POST /api/review endpoint returns valid schema with fallback")


# ----------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        test_missing_api_key,
        test_valid_anthropic_response,
        test_malformed_json_retry_once,
        test_pydantic_validation_failure_retry,
        test_static_fallback_after_retry_fails,
        test_api_failure_fallback,
        test_static_finding_deduplication,
        test_llm_only_finding,
        test_source_and_rule_id_validation,
        test_post_api_review_endpoint,
    ]

    total = 0
    passed = 0
    failed = 0

    print(f"\n{'-' * 60}")
    print("  Stage 3 - AI/LLM Code Review Test Suite")
    print(f"{'-' * 60}")

    for t in tests:
        total += 1
        try:
            t()
            passed += 1
        except Exception as exc:
            failed += 1
            print(f"  FAIL  {t.__name__}: {exc}")

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    print(f"{'=' * 60}")
    if failed:
        sys.exit(1)
