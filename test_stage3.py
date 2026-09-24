"""
Stage 3 - AI/LLM Code Review Tests (Gemini + Groq providers)
=============================================================
Covers:
  - Missing AI keys falls back to static-only findings
  - Valid Gemini response parsing
  - Valid Groq fallback when Gemini fails
  - Malformed JSON response triggers retry
  - Pydantic validation failure triggers retry
  - Retry failure falls back to static-only findings
  - API failure falls back to static-only findings
  - Static finding deduplication
  - LLM-only finding schema and source
  - Source and rule_id schema validation
  - POST /api/review integration (static fallback when no keys)
  - Gemini code-impact analysis fields (Problem, Impact, Why, Fix, Evidence)
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


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_mock_gemini_response(text_content: str):
    """Create a mock Gemini generate_content response object (.text attribute)."""
    mock_resp = MagicMock()
    mock_resp.text = text_content
    return mock_resp


def _make_mock_groq_response(text_content: str):
    """Create a mock Groq chat.completions.create response object."""
    mock_choice = MagicMock()
    mock_choice.message.content = text_content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


# ---------------------------------------------------------------------------
# 1. Missing API Keys Test
# ---------------------------------------------------------------------------
def test_missing_api_key():
    print("Testing missing GEMINI_API_KEY and GROQ_API_KEY...")
    clean_env = {k: v for k, v in os.environ.items()
                 if k not in ("GEMINI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY")}
    with patch.dict(os.environ, clean_env, clear=True):
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
        assert result["fallback_to_static"] is True, f"Expected fallback, got: {result}"
        assert result["provider"] == "static"
        assert result["total_findings"] == 1
        assert result["findings"][0]["rule_id"] == "B307"
        assert result["findings"][0]["source"] == "static"
        assert len(result["errors"]) > 0
    print("  PASS  Missing API keys handled gracefully with static fallback")


# ---------------------------------------------------------------------------
# 2. Valid Gemini Response Test
# ---------------------------------------------------------------------------
def test_valid_gemini_response():
    print("Testing valid Gemini response parsing...")
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
                "confidence": "high",
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
                "confidence": "high",
            },
        ],
    }

    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.return_value = _make_mock_gemini_response(
        json.dumps(mock_llm_json)
    )

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
        client=mock_gemini,
    )

    assert result["fallback_to_static"] is False
    assert result["provider"] == "gemini"
    assert result["total_findings"] == 2
    assert result["summary"] == "Found 1 security vulnerability and 1 bug."

    f0 = result["findings"][0]
    assert f0["file"] == "main.py"
    assert f0["source"] == "static"
    assert f0["rule_id"] == "B307"

    f1 = result["findings"][1]
    assert f1["file"] == "main.py"
    assert f1["source"] == "llm"
    assert f1["rule_id"] is None
    print("  PASS  Valid Gemini response parsed and validated")


# ---------------------------------------------------------------------------
# 3. Groq Fallback When Gemini Fails
# ---------------------------------------------------------------------------
def test_groq_fallback_when_gemini_fails():
    print("Testing Groq fallback when Gemini fails...")
    mock_llm_json = {
        "summary": "Groq fallback review completed.",
        "findings": [
            {
                "file": "util.py",
                "line": 7,
                "category": "bug",
                "source": "llm",
                "rule_id": None,
                "evidence": "return None",
                "explanation": "Function returns None unexpectedly.",
                "suggested_fix": "Return an explicit value or raise an exception.",
                "confidence": "moderate",
            }
        ],
    }

    # Gemini client that always raises an exception
    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = Exception("Gemini connection refused")

    # Groq client that returns a valid response
    mock_groq = MagicMock()
    mock_groq.chat.completions.create.return_value = _make_mock_groq_response(
        json.dumps(mock_llm_json)
    )

    result = review_code(
        code="return None",
        static_issues=[],
        client=mock_gemini,
        groq_client=mock_groq,
    )

    assert result["fallback_to_static"] is False
    assert result["provider"] == "groq"
    assert result["total_findings"] == 1
    assert result["summary"] == "Groq fallback review completed."
    assert result["findings"][0]["source"] == "llm"
    print("  PASS  Groq fallback succeeds when Gemini fails")


# ---------------------------------------------------------------------------
# 4. Malformed JSON Response Triggers Retry (Gemini)
# ---------------------------------------------------------------------------
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
                "confidence": "high",
            }
        ],
    }

    bad_resp = _make_mock_gemini_response("This is not JSON at all: { broken ...")
    good_resp = _make_mock_gemini_response(json.dumps(valid_json))

    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = [bad_resp, good_resp]

    result = review_code(code="return a / 0", static_issues=[], client=mock_gemini)

    assert mock_gemini.models.generate_content.call_count == 2
    assert result["fallback_to_static"] is False
    assert result["provider"] == "gemini"
    assert result["total_findings"] == 1
    assert result["summary"] == "Recovered on retry."
    print("  PASS  Malformed JSON triggers exactly 1 retry and recovers")


# ---------------------------------------------------------------------------
# 5. Pydantic Validation Failure Triggers Retry (Gemini)
# ---------------------------------------------------------------------------
def test_pydantic_validation_failure_retry():
    print("Testing Pydantic validation failure retry...")
    invalid_schema_json = {
        "summary": "Invalid schema",
        "findings": [
            {
                "file": "app.py",
                "category": "not_a_valid_category",
                "source": "invalid_source",
            }
        ],
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
                "confidence": "high",
            }
        ],
    }

    bad_resp = _make_mock_gemini_response(json.dumps(invalid_schema_json))
    good_resp = _make_mock_gemini_response(json.dumps(valid_json))

    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = [bad_resp, good_resp]

    result = review_code(code="token = '12345'", static_issues=[], client=mock_gemini)

    assert mock_gemini.models.generate_content.call_count == 2
    assert result["fallback_to_static"] is False
    assert result["provider"] == "gemini"
    assert result["findings"][0]["category"] == "security"
    print("  PASS  Pydantic validation failure triggers retry and succeeds")


# ---------------------------------------------------------------------------
# 6. Static-Only Fallback After Both Providers Exhaust Retries
# ---------------------------------------------------------------------------
def test_static_fallback_after_retry_fails():
    print("Testing static-only fallback after all retries fail...")
    bad_resp1 = _make_mock_gemini_response("Invalid 1")
    bad_resp2 = _make_mock_gemini_response("Invalid 2")

    bad_groq1 = _make_mock_groq_response("Invalid groq 1")
    bad_groq2 = _make_mock_groq_response("Invalid groq 2")

    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = [bad_resp1, bad_resp2]

    mock_groq = MagicMock()
    mock_groq.chat.completions.create.side_effect = [bad_groq1, bad_groq2]

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
        client=mock_gemini,
        groq_client=mock_groq,
    )

    assert result["fallback_to_static"] is True
    assert result["provider"] == "static"
    assert result["total_findings"] == 1
    assert result["findings"][0]["rule_id"] == "B006"
    assert result["findings"][0]["source"] == "static"
    print("  PASS  All providers failing triggers static-only fallback")


# ---------------------------------------------------------------------------
# 7. API Failure / Exception Fallback
# ---------------------------------------------------------------------------
def test_api_failure_fallback():
    print("Testing API failure / exception fallback...")
    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = Exception("Connection timeout")

    mock_groq = MagicMock()
    mock_groq.chat.completions.create.side_effect = Exception("Groq connection timeout")

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
        client=mock_gemini,
        groq_client=mock_groq,
    )

    assert result["fallback_to_static"] is True
    assert result["provider"] == "static"
    assert result["total_findings"] == 1
    assert result["findings"][0]["rule_id"] == "SEC001"
    print("  PASS  API exception triggers static-only fallback without crash")


# ---------------------------------------------------------------------------
# 8. Static Finding Deduplication
# ---------------------------------------------------------------------------
def test_static_finding_deduplication():
    print("Testing static finding deduplication...")
    static_sf = [
        static_finding_to_review_finding(
            {
                "file": "app.py",
                "line": 5,
                "rule_id": "B307",
                "tool": "bandit",
                "severity": "HIGH",
                "message": "eval used",
            }
        )
    ]

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
            confidence="high",
        )
    ]

    merged = merge_and_deduplicate(static_sf, llm_sf)
    assert len(merged) == 1
    assert merged[0].rule_id == "B307"
    assert merged[0].source == "static"
    assert "Dynamic evaluation" in merged[0].explanation
    print("  PASS  Static finding deduplicated and enriched")


# ---------------------------------------------------------------------------
# 9. LLM-Only Finding Requirement
# ---------------------------------------------------------------------------
def test_llm_only_finding():
    print("Testing LLM-only finding source and rule_id constraints...")
    static_sf = [
        static_finding_to_review_finding(
            {
                "file": "app.py",
                "line": 2,
                "rule_id": "B006",
                "tool": "ruff",
                "severity": "HIGH",
                "message": "Mutable default",
            }
        )
    ]

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
            confidence="moderate",
        )
    ]

    merged = merge_and_deduplicate(static_sf, llm_sf)
    assert len(merged) == 2

    assert merged[0].rule_id == "B006"
    assert merged[0].source == "static"

    assert merged[1].source == "llm"
    assert merged[1].rule_id is None
    assert merged[1].line == 10
    assert "if count < 0" in merged[1].evidence
    print("  PASS  LLM-only finding has source=llm and rule_id=None")


# ---------------------------------------------------------------------------
# 10. Source and Schema Validation
# ---------------------------------------------------------------------------
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
        confidence="high",
    )
    assert valid_f.source == "static"
    assert valid_f.rule_id == "SEC1"

    llm_f = ReviewFinding(
        file="foo.py",
        line=2,
        category="performance",
        source="llm",
        rule_id="null",
        evidence="loop",
        explanation="slow",
        suggested_fix="fast",
        confidence="moderate",
    )
    assert llm_f.source == "llm"
    assert llm_f.rule_id is None

    try:
        ReviewFinding(
            file="foo.py",
            line=3,
            category="unsupported_category",
            source="llm",
            evidence="code",
            explanation="expl",
            suggested_fix="fix",
            confidence="high",
        )
        assert False, "Should have raised ValidationError for invalid category"
    except Exception:
        pass

    print("  PASS  ReviewFinding schema constraints validated")


# ---------------------------------------------------------------------------
# 11. POST /api/review Integration Test (static fallback without keys)
# ---------------------------------------------------------------------------
def test_post_api_review_endpoint():
    print("Testing POST /api/review endpoint integration...")
    clean_env = {k: v for k, v in os.environ.items()
                 if k not in ("GEMINI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY")}
    with patch.dict(os.environ, clean_env, clear=True):
        resp = test_client.post("/api/review", json={"code": "eval('bad')"})
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "findings" in data
        assert "issues" in data
        assert "risk" in data
        assert "provider" in data
        assert data["fallback_to_static"] is True
        assert len(data["findings"]) >= 1
    print("  PASS  POST /api/review returns valid schema with static fallback")


# ---------------------------------------------------------------------------
# 12. Gemini Code-Impact Analysis Fields
# ---------------------------------------------------------------------------
def test_gemini_code_impact_analysis():
    print("Testing Gemini meaningful code-impact analysis fields...")
    mock_llm_json = {
        "summary": "Deep code review completed: 1 critical security flaw detected.",
        "findings": [
            {
                "file": "auth.py",
                "line": 42,
                "category": "security",
                "source": "llm",
                "rule_id": None,
                "problem": "Unauthenticated access token verification allows signature bypass",
                "evidence": "jwt.decode(token, verify=False)",
                "impact": "Full authentication bypass allowing arbitrary account takeover across the application.",
                "why_it_happens": "Setting verify=False disables cryptographic signature verification entirely.",
                "suggested_fix": "Always verify signatures using the configured public key: jwt.decode(token, key=PUBLIC_KEY, algorithms=['RS256']).",
                "confidence": "high",
            }
        ],
    }

    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.return_value = _make_mock_gemini_response(
        json.dumps(mock_llm_json)
    )

    result = review_code(
        code="jwt.decode(token, verify=False)",
        client=mock_gemini,
    )

    assert result["fallback_to_static"] is False
    assert result["provider"] == "gemini"
    assert result["total_findings"] == 1
    f = result["findings"][0]
    assert f["problem"] == "Unauthenticated access token verification allows signature bypass"
    assert f["evidence"] == "jwt.decode(token, verify=False)"
    assert "Full authentication bypass" in f["impact"]
    assert "disables cryptographic signature" in f["why_it_happens"]
    assert "jwt.decode(token, key=PUBLIC_KEY" in f["suggested_fix"]
    assert f["confidence"] == "high"
    print("  PASS  Gemini code-impact analysis (Problem, Impact, Why, Fix, Evidence) verified")


# ---------------------------------------------------------------------------
# 13. API Key Sanitization — no keys in errors
# ---------------------------------------------------------------------------
def test_api_key_not_in_errors():
    print("Testing that API keys are never exposed in error messages...")
    fake_key = "AIzaSyFAKEKEY12345abcdefghijklmnopqrstuv"
    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = Exception(
        f"Request failed with key {fake_key}"
    )

    result = review_code(code="x = 1", static_issues=[], client=mock_gemini)

    for err in result["errors"]:
        assert fake_key not in err, f"API key leaked in error: {err}"
        assert "AIza" not in err, f"API key prefix leaked in error: {err}"
    print("  PASS  API key is sanitized from all error messages")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        test_missing_api_key,
        test_valid_gemini_response,
        test_groq_fallback_when_gemini_fails,
        test_malformed_json_retry_once,
        test_pydantic_validation_failure_retry,
        test_static_fallback_after_retry_fails,
        test_api_failure_fallback,
        test_static_finding_deduplication,
        test_llm_only_finding,
        test_source_and_rule_id_validation,
        test_post_api_review_endpoint,
        test_gemini_code_impact_analysis,
        test_api_key_not_in_errors,
    ]

    total = 0
    passed = 0
    failed = 0

    print(f"\n{'-' * 60}")
    print("  Stage 3 - Gemini/Groq AI Code Review Test Suite")
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
