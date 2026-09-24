"""
Stage 4 - Explainable Release-Risk Scoring Tests
=================================================
Covers:
  - Security findings scoring (weight = 3)
  - Bug findings scoring (weight = 2)
  - Performance findings scoring (weight = 1.5)
  - Style findings scoring (weight = 0.5)
  - Mixed findings and exact mathematical totals
  - Empty findings behavior (total_risk = 0, counts = 0, top_must_fix = [])
  - Complete weighted breakdown schema
  - Deterministic finding ordering (security -> bug -> performance -> style)
  - Top 3 must-fix selection logic
  - Preservation of source, rule_id, evidence, explanation, suggested_fix, confidence
  - More than 3 findings selection
  - API integration via POST /api/review
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app
from risk.risk_engine import calculate_risk, sort_findings
from models.review import ReviewFinding

client = TestClient(app)


def _make_finding(
    category: str,
    file: str = "app.py",
    line: int = 1,
    source: str = "static",
    rule_id: str = "RULE01",
    evidence: str = "code snippet",
    explanation: str = "issue explanation",
    suggested_fix: str = "fix it",
    confidence: str = "high"
) -> dict:
    return {
        "file": file,
        "line": line,
        "category": category,
        "source": source,
        "rule_id": rule_id,
        "evidence": evidence,
        "explanation": explanation,
        "suggested_fix": suggested_fix,
        "confidence": confidence
    }


# ----------------------------------------------------------------------
# 1. Security Findings Weight (weight = 3)
# ----------------------------------------------------------------------
def test_security_findings_weight():
    print("Testing security findings weight (x 3)...")
    findings = [
        _make_finding("security", line=10, rule_id="B307"),
        _make_finding("security", line=20, rule_id="SEC001"),
    ]
    result = calculate_risk(findings)
    assert result["security"]["count"] == 2
    assert result["security"]["weight"] == 3
    assert result["security"]["score"] == 6
    assert result["total_risk"] == 6
    print("  PASS  Security findings: 2 * 3 = 6")


# ----------------------------------------------------------------------
# 2. Bug Findings Weight (weight = 2)
# ----------------------------------------------------------------------
def test_bug_findings_weight():
    print("Testing bug findings weight (x 2)...")
    findings = [
        _make_finding("bug", line=5),
        _make_finding("bug", line=12),
        _make_finding("bug", line=18),
    ]
    result = calculate_risk(findings)
    assert result["bug"]["count"] == 3
    assert result["bug"]["weight"] == 2
    assert result["bug"]["score"] == 6
    assert result["total_risk"] == 6
    print("  PASS  Bug findings: 3 * 2 = 6")


# ----------------------------------------------------------------------
# 3. Performance Findings Weight (weight = 1.5)
# ----------------------------------------------------------------------
def test_performance_findings_weight():
    print("Testing performance findings weight (x 1.5)...")
    findings = [
        _make_finding("performance", line=5),
        _make_finding("performance", line=15),
    ]
    result = calculate_risk(findings)
    assert result["performance"]["count"] == 2
    assert result["performance"]["weight"] == 1.5
    assert result["performance"]["score"] == 3
    assert result["total_risk"] == 3
    print("  PASS  Performance findings: 2 * 1.5 = 3")


# ----------------------------------------------------------------------
# 4. Style Findings Weight (weight = 0.5)
# ----------------------------------------------------------------------
def test_style_findings_weight():
    print("Testing style findings weight (x 0.5)...")
    findings = [
        _make_finding("style", line=2),
        _make_finding("style", line=8),
        _make_finding("style", line=14),
    ]
    result = calculate_risk(findings)
    assert result["style"]["count"] == 3
    assert result["style"]["weight"] == 0.5
    assert result["style"]["score"] == 1.5
    assert result["total_risk"] == 1.5
    print("  PASS  Style findings: 3 * 0.5 = 1.5")


# ----------------------------------------------------------------------
# 5. Mixed Findings and Mathematical Total
# ----------------------------------------------------------------------
def test_mixed_findings_and_exact_math():
    print("Testing mixed findings mathematical total...")
    # 2 Security (6) + 1 Bug (2) + 2 Performance (3) + 1 Style (0.5) = 11.5
    findings = [
        _make_finding("security", line=10),
        _make_finding("security", line=20),
        _make_finding("bug", line=30),
        _make_finding("performance", line=40),
        _make_finding("performance", line=50),
        _make_finding("style", line=60),
    ]
    result = calculate_risk(findings)
    assert result["security"]["score"] == 6
    assert result["bug"]["score"] == 2
    assert result["performance"]["score"] == 3
    assert result["style"]["score"] == 0.5
    assert result["total_risk"] == 11.5
    print("  PASS  Mixed findings math: 6 + 2 + 3 + 0.5 = 11.5")


# ----------------------------------------------------------------------
# 6. Empty Findings Behavior
# ----------------------------------------------------------------------
def test_empty_findings():
    print("Testing empty findings handling...")
    for empty_input in ([], None):
        result = calculate_risk(empty_input)
        assert result["total_risk"] == 0
        assert result["security"]["count"] == 0
        assert result["security"]["score"] == 0
        assert result["bug"]["count"] == 0
        assert result["bug"]["score"] == 0
        assert result["performance"]["count"] == 0
        assert result["performance"]["score"] == 0
        assert result["style"]["count"] == 0
        assert result["style"]["score"] == 0
        assert result["top_must_fix"] == []
    print("  PASS  Empty findings returns total_risk=0, counts=0, top_must_fix=[]")


# ----------------------------------------------------------------------
# 7. Required Breakdown Schema
# ----------------------------------------------------------------------
def test_required_breakdown_schema():
    print("Testing required breakdown structure...")
    findings = [_make_finding("security")]
    result = calculate_risk(findings)
    breakdown = result["breakdown"]

    for cat, expected_weight in [("security", 3), ("bug", 2), ("performance", 1.5), ("style", 0.5)]:
        assert cat in breakdown, f"Missing category {cat} in breakdown"
        assert "count" in breakdown[cat]
        assert "weight" in breakdown[cat]
        assert "score" in breakdown[cat]
        assert breakdown[cat]["weight"] == expected_weight

    assert "total_risk" in breakdown
    print("  PASS  Complete breakdown schema matches requirements")


# ----------------------------------------------------------------------
# 8. Deterministic Finding Ordering
# ----------------------------------------------------------------------
def test_deterministic_finding_ordering():
    print("Testing deterministic finding ordering (security -> bug -> performance -> style)...")
    # Feed findings in reverse / random category order
    findings = [
        _make_finding("style", file="z.py", line=1),
        _make_finding("performance", file="b.py", line=5),
        _make_finding("bug", file="c.py", line=2),
        _make_finding("security", file="a.py", line=10),
    ]
    result = calculate_risk(findings)
    ordered = result["ordered_findings"]

    categories = [f["category"] for f in ordered]
    assert categories == ["security", "bug", "performance", "style"], f"Unexpected order: {categories}"
    print("  PASS  Finding ordering strictly follows security -> bug -> performance -> style")


# ----------------------------------------------------------------------
# 9. Top 3 Must-Fix Issues Selection
# ----------------------------------------------------------------------
def test_top_3_must_fix_selection():
    print("Testing top 3 must-fix selection logic...")
    findings = [
        _make_finding("style", file="a.py", line=1),
        _make_finding("performance", file="b.py", line=2),
        _make_finding("bug", file="c.py", line=3),
        _make_finding("security", file="d.py", line=4),
        _make_finding("security", file="e.py", line=5),
    ]
    result = calculate_risk(findings)
    top_3 = result["top_must_fix"]

    assert len(top_3) == 3
    # Top 3 should be 2 security findings and 1 bug finding
    assert top_3[0]["category"] == "security"
    assert top_3[1]["category"] == "security"
    assert top_3[2]["category"] == "bug"
    print("  PASS  Top 3 selects the 3 highest weighted findings (security, security, bug)")


# ----------------------------------------------------------------------
# 10. Metadata Preservation
# ----------------------------------------------------------------------
def test_metadata_preservation():
    print("Testing metadata preservation during risk scoring...")
    original = _make_finding(
        category="security",
        file="auth.py",
        line=42,
        source="llm",
        rule_id=None,
        evidence="api_key = 'raw_secret'",
        explanation="Hardcoded token found in auth logic.",
        suggested_fix="Use environment variable instead.",
        confidence="high"
    )
    result = calculate_risk([original])
    scored = result["top_must_fix"][0]

    assert scored["file"] == "auth.py"
    assert scored["line"] == 42
    assert scored["category"] == "security"
    assert scored["source"] == "llm"
    assert scored["rule_id"] is None
    assert scored["evidence"] == "api_key = 'raw_secret'"
    assert scored["explanation"] == "Hardcoded token found in auth logic."
    assert scored["suggested_fix"] == "Use environment variable instead."
    assert scored["confidence"] == "high"
    print("  PASS  All metadata fields (source, rule_id, evidence, confidence) preserved")


# ----------------------------------------------------------------------
# 11. Deterministic Tie-Breaking (Confidence, File, Line)
# ----------------------------------------------------------------------
def test_deterministic_tie_breaking():
    print("Testing deterministic tie-breaking within the same category...")
    findings = [
        _make_finding("security", file="z.py", line=10, confidence="moderate"),
        _make_finding("security", file="a.py", line=50, confidence="high"),
        _make_finding("security", file="a.py", line=10, confidence="high"),
    ]
    sorted_f = sort_findings(findings)

    # high confidence before moderate
    assert sorted_f[0]["confidence"] == "high"
    assert sorted_f[1]["confidence"] == "high"
    assert sorted_f[2]["confidence"] == "moderate"

    # For same confidence ('high') and same file ('a.py'), line 10 precedes line 50
    assert sorted_f[0]["line"] == 10
    assert sorted_f[1]["line"] == 50
    print("  PASS  Tie-breaking: confidence -> file -> line is deterministic")


# ----------------------------------------------------------------------
# 12. API Review Integration Test
# ----------------------------------------------------------------------
def test_api_review_risk_integration():
    print("Testing POST /api/review Stage 4 risk integration...")
    resp = client.post(
        "/api/review",
        json={"code": "eval('bad')"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "risk" in data
    risk = data["risk"]

    assert "total_risk" in risk
    assert "breakdown" in risk
    assert "security" in risk["breakdown"]
    assert "bug" in risk["breakdown"]
    assert "performance" in risk["breakdown"]
    assert "style" in risk["breakdown"]
    assert "top_must_fix" in risk

    # The findings in the response must match the ordered_findings
    findings = data["findings"]
    for i in range(len(findings) - 1):
        cat_a = findings[i]["category"]
        cat_b = findings[i + 1]["category"]
        prio_map = {"security": 1, "bug": 2, "performance": 3, "style": 4}
        assert prio_map.get(cat_a, 5) <= prio_map.get(cat_b, 5)

    print("  PASS  POST /api/review returns explainable risk breakdown and ordered findings")


# ----------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        test_security_findings_weight,
        test_bug_findings_weight,
        test_performance_findings_weight,
        test_style_findings_weight,
        test_mixed_findings_and_exact_math,
        test_empty_findings,
        test_required_breakdown_schema,
        test_deterministic_finding_ordering,
        test_top_3_must_fix_selection,
        test_metadata_preservation,
        test_deterministic_tie_breaking,
        test_api_review_risk_integration,
    ]

    total = 0
    passed = 0
    failed = 0

    print(f"\n{'-' * 60}")
    print("  Stage 4 - Explainable Release-Risk Scoring Test Suite")
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
