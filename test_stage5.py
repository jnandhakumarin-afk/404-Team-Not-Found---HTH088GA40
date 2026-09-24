"""
Stage 5 â€” Test Harness & Evaluation Metrics Tests
====================================================
All tests use static/mocked data only.
No real GitHub or Anthropic API calls are made.

Covers:
  - True positive matching
  - False positive detection
  - False negative detection
  - Precision calculation (TP / (TP + FP))
  - Recall calculation (TP / (TP + FN))
  - Signal ratio calculation (TP / total)
  - Zero findings (all zeros)
  - Clean file produces no spurious matches
  - Mixed findings across files
  - Multiple files
  - Deterministic matching (same inputs -> same outputs)
  - POST /api/evaluate endpoint integration
  - Dataset integrity check
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app
from evaluation.evaluator import (
    calculate_metrics,
    match_findings,
    _finding_matches_expected,
    evaluate_against_dataset,
)
from evaluation.dataset import (
    EVAL_SAMPLES,
    ALL_EXPECTED_ISSUES,
    SAMPLE_VULNERABLE_PY_ISSUES,
    SAMPLE_VULNERABLE_JS_ISSUES,
    SAMPLE_CLEAN_PY_ISSUES,
)

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_finding(file, line, category, rule_id=None, source="static"):
    return {
        "file": file,
        "line": line,
        "category": category,
        "source": source,
        "rule_id": rule_id or "RULE",
        "evidence": "code snippet",
        "explanation": "issue found",
        "suggested_fix": "fix it",
        "confidence": "high",
    }


def _expected(file, line_approx, category, rule_hint=None, description="issue"):
    return {
        "file": file,
        "line_approx": line_approx,
        "category": category,
        "description": description,
        "rule_hint": rule_hint,
    }


# ---------------------------------------------------------------------------
# 1. Deterministic Matching â€” _finding_matches_expected
# ---------------------------------------------------------------------------
def test_exact_match():
    print("Testing exact finding match...")
    f = _make_finding("app.py", 8, "security")
    e = _expected("app.py", 8, "security")
    assert _finding_matches_expected(f, e) is True
    print("  PASS  Exact match (file, line, category)")


def test_no_match_wrong_file():
    print("Testing no match on wrong file...")
    f = _make_finding("other.py", 8, "security")
    e = _expected("app.py", 8, "security")
    assert _finding_matches_expected(f, e) is False
    print("  PASS  Wrong file -> no match")


def test_no_match_wrong_category():
    print("Testing no match on wrong category...")
    f = _make_finding("app.py", 8, "style")
    e = _expected("app.py", 8, "security")
    assert _finding_matches_expected(f, e) is False
    print("  PASS  Wrong category -> no match")


def test_line_proximity_within():
    print("Testing line proximity match (within Â+/-5)...")
    f = _make_finding("app.py", 12, "security")
    e = _expected("app.py", 10, "security")
    assert _finding_matches_expected(f, e) is True
    print("  PASS  Line within proximity -> match")


def test_line_proximity_outside():
    print("Testing line proximity outside range (>5)...")
    f = _make_finding("app.py", 20, "security")
    e = _expected("app.py", 8, "security")
    assert _finding_matches_expected(f, e) is False
    print("  PASS  Line outside proximity -> no match")


def test_basename_normalization():
    print("Testing path basename normalization...")
    f = _make_finding("src/utils/app.py", 5, "bug")
    e = _expected("app.py", 5, "bug")
    assert _finding_matches_expected(f, e) is True
    print("  PASS  Full path normalized to basename for matching")


# ---------------------------------------------------------------------------
# 2. True Positives
# ---------------------------------------------------------------------------
def test_true_positives():
    print("Testing true positive detection...")
    expected = [
        _expected("vuln.py", 8, "security"),
        _expected("vuln.py", 13, "security"),
    ]
    system = [
        _make_finding("vuln.py", 8, "security"),
        _make_finding("vuln.py", 13, "security"),
    ]
    tp, fp, fn = match_findings(system, expected)
    assert len(tp) == 2
    assert len(fp) == 0
    assert len(fn) == 0
    print("  PASS  Both findings matched -> 2 TP, 0 FP, 0 FN")


# ---------------------------------------------------------------------------
# 3. False Positives
# ---------------------------------------------------------------------------
def test_false_positives():
    print("Testing false positive detection...")
    expected = [_expected("vuln.py", 8, "security")]
    system = [
        _make_finding("vuln.py", 8, "security"),   # TP
        _make_finding("vuln.py", 50, "style"),      # FP â€” no matching expected
    ]
    tp, fp, fn = match_findings(system, expected)
    assert len(tp) == 1
    assert len(fp) == 1
    assert len(fn) == 0
    print("  PASS  Unmatched finding -> 1 FP detected")


# ---------------------------------------------------------------------------
# 4. False Negatives
# ---------------------------------------------------------------------------
def test_false_negatives():
    print("Testing false negative detection...")
    expected = [
        _expected("vuln.py", 8, "security"),
        _expected("vuln.py", 13, "bug"),
    ]
    system = [
        _make_finding("vuln.py", 8, "security"),  # TP
        # Bug at line 13 NOT reported -> FN
    ]
    tp, fp, fn = match_findings(system, expected)
    assert len(tp) == 1
    assert len(fp) == 0
    assert len(fn) == 1
    print("  PASS  Missed expected issue -> 1 FN detected")


# ---------------------------------------------------------------------------
# 5. Precision Calculation
# ---------------------------------------------------------------------------
def test_precision_calculation():
    print("Testing precision = TP / (TP + FP)...")
    # 2 TP, 2 FP -> precision = 2/4 = 0.5
    expected = [
        _expected("f.py", 1, "security"),
        _expected("f.py", 5, "bug"),
    ]
    system = [
        _make_finding("f.py", 1, "security"),  # TP
        _make_finding("f.py", 5, "bug"),        # TP
        _make_finding("f.py", 20, "style"),     # FP
        _make_finding("f.py", 30, "style"),     # FP
    ]
    result = calculate_metrics(system, expected)
    assert result["true_positives"] == 2
    assert result["false_positives"] == 2
    assert result["precision"] == 0.5
    print("  PASS  Precision = 2/(2+2) = 0.5")


def test_precision_zero_predictions():
    print("Testing precision with zero predictions...")
    result = calculate_metrics([], [_expected("f.py", 5, "security")])
    assert result["precision"] == 0.0
    print("  PASS  Zero predictions -> precision = 0.0")


def test_precision_all_correct():
    print("Testing precision = 1.0 when all predictions correct...")
    expected = [_expected("f.py", 5, "security")]
    system = [_make_finding("f.py", 5, "security")]
    result = calculate_metrics(system, expected)
    assert result["precision"] == 1.0
    print("  PASS  All predictions correct -> precision = 1.0")


# ---------------------------------------------------------------------------
# 6. Recall Calculation
# ---------------------------------------------------------------------------
def test_recall_calculation():
    print("Testing recall = TP / (TP + FN)...")
    # 1 TP, 1 FN -> recall = 1/2 = 0.5
    expected = [
        _expected("f.py", 1, "security"),
        _expected("f.py", 10, "bug"),   # missed
    ]
    system = [_make_finding("f.py", 1, "security")]
    result = calculate_metrics(system, expected)
    assert result["true_positives"] == 1
    assert result["false_negatives"] == 1
    assert result["recall"] == 0.5
    print("  PASS  Recall = 1/(1+1) = 0.5")


def test_recall_no_expected():
    print("Testing recall with no expected issues...")
    result = calculate_metrics([_make_finding("f.py", 5, "bug")], [])
    assert result["recall"] == 0.0
    print("  PASS  No expected issues -> recall = 0.0")


# ---------------------------------------------------------------------------
# 7. Signal Ratio Calculation
# ---------------------------------------------------------------------------
def test_signal_ratio_calculation():
    print("Testing signal_ratio = actionable / total...")
    # 5 total, 3 TP -> signal_ratio = 3/5 = 0.6
    expected = [
        _expected("f.py", 1, "security"),
        _expected("f.py", 5, "security"),
        _expected("f.py", 10, "bug"),
    ]
    system = [
        _make_finding("f.py", 1, "security"),   # TP
        _make_finding("f.py", 5, "security"),   # TP
        _make_finding("f.py", 10, "bug"),       # TP
        _make_finding("f.py", 20, "style"),     # FP
        _make_finding("f.py", 30, "style"),     # FP
    ]
    result = calculate_metrics(system, expected)
    assert result["signal_ratio"] == 0.6
    assert result["signal_ratio_pct"] == "60.0%"
    assert result["actionable_findings"] == 3
    assert result["total_findings"] == 5
    print("  PASS  Signal ratio = 3/5 = 60.0%")


def test_signal_ratio_zero_total():
    print("Testing signal_ratio with no findings...")
    result = calculate_metrics([], [])
    assert result["signal_ratio"] == 0.0
    assert result["signal_ratio_pct"] == "0.0%"
    print("  PASS  Zero total findings -> signal_ratio = 0.0")


# ---------------------------------------------------------------------------
# 8. Zero Findings
# ---------------------------------------------------------------------------
def test_zero_findings():
    print("Testing zero findings result...")
    result = calculate_metrics([], [])
    assert result["true_positives"] == 0
    assert result["false_positives"] == 0
    assert result["false_negatives"] == 0
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["signal_ratio"] == 0.0
    assert result["total_findings"] == 0
    assert result["actionable_findings"] == 0
    print("  PASS  Zero findings -> all metrics = 0")


# ---------------------------------------------------------------------------
# 9. Clean File Test
# ---------------------------------------------------------------------------
def test_clean_file_no_expected_issues():
    print("Testing clean file sample has no expected issues...")
    assert SAMPLE_CLEAN_PY_ISSUES == []
    # If system reports nothing for clean code, FP = 0
    result = calculate_metrics([], SAMPLE_CLEAN_PY_ISSUES)
    assert result["false_positives"] == 0
    assert result["false_negatives"] == 0
    print("  PASS  Clean file has 0 expected issues -> no FPs or FNs when no findings")


# ---------------------------------------------------------------------------
# 10. Multiple Files
# ---------------------------------------------------------------------------
def test_multiple_files():
    print("Testing evaluation across multiple files...")
    expected = [
        _expected("a.py", 5, "security"),
        _expected("b.py", 10, "bug"),
    ]
    system = [
        _make_finding("a.py", 5, "security"),  # TP
        _make_finding("b.py", 10, "bug"),      # TP
    ]
    result = calculate_metrics(system, expected)
    assert result["true_positives"] == 2
    assert result["false_positives"] == 0
    assert result["false_negatives"] == 0
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    print("  PASS  Multiple files: 2/2 correct -> precision=1.0, recall=1.0")


# ---------------------------------------------------------------------------
# 11. Mixed Findings
# ---------------------------------------------------------------------------
def test_mixed_findings():
    print("Testing mixed TP/FP/FN across different categories...")
    expected = [
        _expected("app.py", 4, "security"),    # Hardcoded secret
        _expected("app.py", 8, "security"),    # Shell injection
        _expected("app.py", 11, "bug"),        # Mutable default
    ]
    system = [
        _make_finding("app.py", 4, "security"),  # TP
        _make_finding("app.py", 8, "security"),  # TP
        # Bug at line 11 missed -> FN
        _make_finding("app.py", 99, "style"),    # FP
    ]
    result = calculate_metrics(system, expected)
    assert result["true_positives"] == 2
    assert result["false_positives"] == 1
    assert result["false_negatives"] == 1
    assert result["precision"] == round(2 / 3, 4)
    assert result["recall"] == round(2 / 3, 4)
    print("  PASS  Mixed: 2 TP, 1 FP, 1 FN -> precision=0.6667, recall=0.6667")


# ---------------------------------------------------------------------------
# 12. Deterministic â€” same input -> same output
# ---------------------------------------------------------------------------
def test_deterministic_evaluation():
    print("Testing deterministic behavior (same input -> same output)...")
    expected = [
        _expected("f.py", 5, "security"),
        _expected("f.py", 15, "bug"),
    ]
    system = [
        _make_finding("f.py", 5, "security"),
        _make_finding("f.py", 15, "bug"),
        _make_finding("f.py", 25, "style"),
    ]
    result_a = calculate_metrics(system, expected)
    result_b = calculate_metrics(system, expected)
    assert result_a["precision"] == result_b["precision"]
    assert result_a["recall"] == result_b["recall"]
    assert result_a["signal_ratio"] == result_b["signal_ratio"]
    assert result_a["true_positives"] == result_b["true_positives"]
    print("  PASS  Same inputs produce identical metric outputs")


# ---------------------------------------------------------------------------
# 13. Dataset Integrity Check
# ---------------------------------------------------------------------------
def test_dataset_integrity():
    print("Testing evaluation dataset integrity...")
    assert len(EVAL_SAMPLES) == 3
    assert EVAL_SAMPLES[0]["name"] == "vulnerable_python"
    assert EVAL_SAMPLES[1]["name"] == "vulnerable_javascript"
    assert EVAL_SAMPLES[2]["name"] == "clean_python"

    assert len(SAMPLE_VULNERABLE_PY_ISSUES) == 5
    assert len(SAMPLE_VULNERABLE_JS_ISSUES) == 2
    assert len(SAMPLE_CLEAN_PY_ISSUES) == 0
    assert len(ALL_EXPECTED_ISSUES) == 7

    for issue in ALL_EXPECTED_ISSUES:
        assert "file" in issue
        assert "line_approx" in issue
        assert "category" in issue
        assert "description" in issue
    print("  PASS  Dataset has 3 samples, 7 total expected issues, schema valid")


# ---------------------------------------------------------------------------
# 14. POST /api/evaluate Endpoint
# ---------------------------------------------------------------------------
def test_evaluate_endpoint_with_findings():
    print("Testing POST /api/evaluate with findings...")
    # Send perfect findings for all 7 expected issues
    perfect_findings = [
        {"file": i["file"], "line": i["line_approx"], "category": i["category"],
         "source": "static", "rule_id": "RULE", "evidence": "code",
         "explanation": "found", "suggested_fix": "fix", "confidence": "high"}
        for i in ALL_EXPECTED_ISSUES
    ]
    resp = client.post("/api/evaluate", json={"findings": perfect_findings, "use_dataset": True})
    assert resp.status_code == 200
    data = resp.json()
    assert "true_positives" in data
    assert "false_positives" in data
    assert "false_negatives" in data
    assert "precision" in data
    assert "recall" in data
    assert "signal_ratio" in data
    assert "signal_ratio_pct" in data
    assert "actionable_findings" in data
    assert "total_findings" in data
    assert data["true_positives"] == 7
    assert data["precision"] == 1.0
    assert data["recall"] == 1.0
    print("  PASS  POST /api/evaluate with perfect findings -> precision=1.0, recall=1.0")


def test_evaluate_endpoint_empty_findings():
    print("Testing POST /api/evaluate with empty findings...")
    resp = client.post("/api/evaluate", json={"findings": [], "use_dataset": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["true_positives"] == 0
    assert data["false_positives"] == 0
    assert data["false_negatives"] == 7  # all expected missed
    assert data["precision"] == 0.0
    assert data["recall"] == 0.0
    assert data["signal_ratio"] == 0.0
    print("  PASS  Empty findings -> 0 TP, 0 FP, 7 FN")


def test_evaluate_endpoint_custom_expected():
    print("Testing POST /api/evaluate with custom expected list...")
    custom_expected = [
        {"file": "myfile.py", "line_approx": 5, "category": "bug",
         "description": "test issue", "rule_hint": None}
    ]
    system_findings = [
        {"file": "myfile.py", "line": 5, "category": "bug",
         "source": "static", "rule_id": "R1", "evidence": "code",
         "explanation": "found", "suggested_fix": "fix", "confidence": "high"}
    ]
    resp = client.post(
        "/api/evaluate",
        json={"findings": system_findings, "expected": custom_expected}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["true_positives"] == 1
    assert data["precision"] == 1.0
    assert data["recall"] == 1.0
    print("  PASS  Custom expected list matched correctly")


def test_evaluate_endpoint_no_private_fields():
    print("Testing POST /api/evaluate response has no private fields...")
    resp = client.post("/api/evaluate", json={"findings": [], "use_dataset": False})
    assert resp.status_code == 200
    data = resp.json()
    for key in data:
        assert not key.startswith("_"), f"Private field leaked: {key}"
    print("  PASS  No _tp_items/_fp_items/_fn_items in public response")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        test_exact_match,
        test_no_match_wrong_file,
        test_no_match_wrong_category,
        test_line_proximity_within,
        test_line_proximity_outside,
        test_basename_normalization,
        test_true_positives,
        test_false_positives,
        test_false_negatives,
        test_precision_calculation,
        test_precision_zero_predictions,
        test_precision_all_correct,
        test_recall_calculation,
        test_recall_no_expected,
        test_signal_ratio_calculation,
        test_signal_ratio_zero_total,
        test_zero_findings,
        test_clean_file_no_expected_issues,
        test_multiple_files,
        test_mixed_findings,
        test_deterministic_evaluation,
        test_dataset_integrity,
        test_evaluate_endpoint_with_findings,
        test_evaluate_endpoint_empty_findings,
        test_evaluate_endpoint_custom_expected,
        test_evaluate_endpoint_no_private_fields,
    ]

    total = 0
    passed = 0
    failed = 0

    print(f"\n{'-' * 60}")
    print("  Stage 5 - Test Harness & Evaluation Metrics Test Suite")
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

