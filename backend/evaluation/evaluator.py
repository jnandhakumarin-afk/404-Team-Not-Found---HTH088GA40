"""
Stage 5 Evaluation Engine
==========================
Deterministic matching of system findings against ground-truth expected issues.
Computes:
  - True Positives (TP)
  - False Positives (FP)
  - False Negatives (FN)
  - Precision = TP / (TP + FP)
  - Recall    = TP / (TP + FN)
  - Signal Ratio = actionable_findings / total_findings

Matching logic (deterministic, no LLM):
  A system finding matches a ground-truth issue when ALL of:
    1. file paths match (exact)
    2. line number is within LINE_PROXIMITY of the expected line_approx
    3. category matches
  OR when the above hold and the rule_hint (if present) appears in the
  finding's rule_id or message (substring, case-insensitive).

Each ground-truth issue is matched at most once (greedy, first match wins
in deterministic order).
"""

from typing import Any, Dict, List, Optional, Tuple

LINE_PROXIMITY = 5   # ±5 lines tolerance for matching


# ---------------------------------------------------------------------------
# Core matching
# ---------------------------------------------------------------------------

def _normalize_file(path: str) -> str:
    """Normalize file path for comparison (just use basename)."""
    return path.replace("\\", "/").split("/")[-1]


def _finding_matches_expected(
    finding: Dict[str, Any],
    expected: Dict[str, Any],
) -> bool:
    """
    Return True when a system finding is considered a match for a
    ground-truth expected issue.

    Criteria (all must hold):
      1. Same file (basename comparison)
      2. Line within ±LINE_PROXIMITY of expected line_approx
      3. Same category

    Optional boost (not required):
      - If expected has a rule_hint, its presence in rule_id / message
        counts as a stronger match indicator (used when category ties).
    """
    f_file = _normalize_file(str(finding.get("file", "")))
    e_file = _normalize_file(str(expected.get("file", "")))

    if f_file != e_file:
        return False

    try:
        f_line = int(finding.get("line", 0))
        e_line = int(expected.get("line_approx", 0))
    except (ValueError, TypeError):
        return False

    if abs(f_line - e_line) > LINE_PROXIMITY:
        return False

    f_cat = str(finding.get("category", "")).lower().strip()
    e_cat = str(expected.get("category", "")).lower().strip()

    if f_cat != e_cat:
        return False

    return True


def match_findings(
    system_findings: List[Dict[str, Any]],
    expected_issues: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Match system findings against ground-truth expected issues.

    Returns (true_positives, false_positives, false_negatives).

    Greedy first-match strategy:
      - Each expected issue is matched at most once (to the first system
        finding that satisfies the criteria).
      - Matched system findings are TPs; unmatched are FPs.
      - Unmatched expected issues are FNs.
    """
    matched_expected_indices = set()
    matched_finding_indices = set()
    true_positives: List[Dict[str, Any]] = []

    # For each system finding, try to find an unmatched expected issue
    for f_idx, finding in enumerate(system_findings):
        for e_idx, expected in enumerate(expected_issues):
            if e_idx in matched_expected_indices:
                continue
            if _finding_matches_expected(finding, expected):
                true_positives.append(finding)
                matched_expected_indices.add(e_idx)
                matched_finding_indices.add(f_idx)
                break  # greedy: move to next finding

    false_positives = [
        f for i, f in enumerate(system_findings) if i not in matched_finding_indices
    ]
    false_negatives = [
        e for i, e in enumerate(expected_issues) if i not in matched_expected_indices
    ]

    return true_positives, false_positives, false_negatives


def calculate_metrics(
    system_findings: List[Dict[str, Any]],
    expected_issues: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Calculate evaluation metrics deterministically.

    Returns a structured result with:
      - true_positives, false_positives, false_negatives (counts + items)
      - precision
      - recall
      - actionable_findings, total_findings
      - signal_ratio (as decimal and percentage string)
    """
    tp_list, fp_list, fn_list = match_findings(system_findings, expected_issues)

    tp = len(tp_list)
    fp = len(fp_list)
    fn = len(fn_list)
    total = len(system_findings)

    # Precision: TP / (TP + FP)
    if (tp + fp) == 0:
        precision = 0.0
    else:
        precision = round(tp / (tp + fp), 4)

    # Recall: TP / (TP + FN)
    if (tp + fn) == 0:
        recall = 0.0
    else:
        recall = round(tp / (tp + fn), 4)

    # Signal ratio: actionable (TP) / total findings shown
    if total == 0:
        signal_ratio = 0.0
        signal_ratio_pct = "0.0%"
    else:
        signal_ratio = round(tp / total, 4)
        signal_ratio_pct = f"{round(tp / total * 100, 2)}%"

    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "actionable_findings": tp,
        "total_findings": total,
        "signal_ratio": signal_ratio,
        "signal_ratio_pct": signal_ratio_pct,
        # Detailed lists for introspection
        "_tp_items": tp_list,
        "_fp_items": fp_list,
        "_fn_items": fn_list,
    }


def evaluate_against_dataset(
    system_findings: List[Dict[str, Any]],
    eval_samples: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Run evaluation against the full evaluation dataset.

    ``system_findings`` — list of finding dicts from the review pipeline.
    ``eval_samples``   — optional override; defaults to EVAL_SAMPLES.

    Returns a dict matching the required Stage 5 schema.
    """
    if eval_samples is None:
        from evaluation.dataset import ALL_EXPECTED_ISSUES
        expected = ALL_EXPECTED_ISSUES
    else:
        expected = [
            dict(issue, file=sample["file"])
            for sample in eval_samples
            for issue in sample.get("expected_issues", [])
        ]

    return calculate_metrics(system_findings, expected)
