from typing import List, Dict, Any, Optional, Union

# Exact Stage 4 category weights
CATEGORY_WEIGHTS: Dict[str, Union[int, float]] = {
    "security": 3,
    "bug": 2,
    "performance": 1.5,
    "style": 0.5,
}

CATEGORY_PRIORITY: Dict[str, int] = {
    "security": 1,
    "bug": 2,
    "performance": 3,
    "style": 4,
}

CONFIDENCE_PRIORITY: Dict[str, int] = {
    "high": 1,
    "moderate": 2,
    "low": 3,
}

SEVERITY_PRIORITY: Dict[str, int] = {
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
    "info": 5,
}


def extract_finding_category(f_dict: Dict[str, Any]) -> str:
    """Extract or infer category from finding dictionary."""
    cat = str(f_dict.get("category", "")).lower().strip()
    if cat in CATEGORY_WEIGHTS:
        return cat

    rule = str(f_dict.get("rule_id", "")).upper()
    tool = str(f_dict.get("tool", "")).lower()
    typ = str(f_dict.get("type", "")).lower()

    if (
        "sec" in cat
        or "security" in typ
        or "bandit" in tool
        or rule.startswith("S")
        or rule.startswith("B3")
        or rule.startswith("B4")
        or rule.startswith("B6")
    ):
        return "security"
    if "perf" in cat or "performance" in typ or rule.startswith("PERF"):
        return "performance"
    if "style" in cat or "smell" in typ or rule.startswith("STYLE") or rule.startswith("E1") or rule.startswith("W"):
        return "style"
    return "bug"


def sort_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deterministically sort findings:
    1. Category order: security -> bug -> performance -> style
    2. Confidence: high -> moderate -> low
    3. Severity: critical -> high -> medium -> low -> info
    4. File path (alphabetical)
    5. Line number (ascending)
    6. Rule ID
    """
    def sort_key(item: Dict[str, Any]):
        cat = extract_finding_category(item)
        cat_prio = CATEGORY_PRIORITY.get(cat, 5)

        conf = str(item.get("confidence", "moderate")).lower()
        conf_prio = CONFIDENCE_PRIORITY.get(conf, 4)

        sev = str(item.get("severity", "")).lower()
        sev_prio = SEVERITY_PRIORITY.get(sev, 6)

        file_name = str(item.get("file", ""))
        try:
            line_num = int(item.get("line", 0))
        except (ValueError, TypeError):
            line_num = 0

        rule_id = str(item.get("rule_id") or "")
        return (cat_prio, conf_prio, sev_prio, file_name, line_num, rule_id)

    return sorted(findings, key=sort_key)


def calculate_risk(issues: Optional[List[Any]] = None) -> Dict[str, Any]:
    """
    Deterministically calculate release-risk score and breakdown from findings.

    Category weights:
      security    = 3
      bug         = 2
      performance = 1.5
      style       = 0.5
    """
    if not issues:
        empty_breakdown = {
            "security": {"count": 0, "weight": 3, "score": 0},
            "bug": {"count": 0, "weight": 2, "score": 0},
            "performance": {"count": 0, "weight": 1.5, "score": 0},
            "style": {"count": 0, "weight": 0.5, "score": 0},
            "total_risk": 0,
        }
        return {
            "total_risk": 0,
            "risk_score": 0,
            "breakdown": empty_breakdown,
            "security": empty_breakdown["security"],
            "bug": empty_breakdown["bug"],
            "performance": empty_breakdown["performance"],
            "style": empty_breakdown["style"],
            "top_must_fix": [],
            "must_fix": [],
            "ordered_findings": [],
            "total_issues": 0,
            "risk_level": "Low",
            "release_status": "SAFE TO RELEASE",
        }

    # Normalize objects to dicts preserving all original metadata
    finding_dicts: List[Dict[str, Any]] = []
    for item in issues:
        if hasattr(item, "model_dump"):
            d = item.model_dump()
        elif isinstance(item, dict):
            d = dict(item)
        else:
            d = dict(item)
        finding_dicts.append(d)

    # Calculate category counts
    counts = {"security": 0, "bug": 0, "performance": 0, "style": 0}
    for f in finding_dicts:
        cat = extract_finding_category(f)
        counts[cat] += 1

    # Calculate category scores
    sec_score = counts["security"] * 3
    bug_score = counts["bug"] * 2
    perf_raw = counts["performance"] * 1.5
    perf_score = int(perf_raw) if perf_raw == int(perf_raw) else round(perf_raw, 2)
    style_raw = counts["style"] * 0.5
    style_score = int(style_raw) if style_raw == int(style_raw) else round(style_raw, 2)

    total_raw = sec_score + bug_score + perf_score + style_score
    total_risk = int(total_raw) if total_raw == int(total_raw) else round(total_raw, 2)

    breakdown = {
        "security": {
            "count": counts["security"],
            "weight": 3,
            "score": sec_score,
        },
        "bug": {
            "count": counts["bug"],
            "weight": 2,
            "score": bug_score,
        },
        "performance": {
            "count": counts["performance"],
            "weight": 1.5,
            "score": perf_score,
        },
        "style": {
            "count": counts["style"],
            "weight": 0.5,
            "score": style_score,
        },
        "total_risk": total_risk,
    }

    # Deterministically order findings: security -> bug -> performance -> style
    ordered_findings = sort_findings(finding_dicts)
    top_must_fix = ordered_findings[:3]

    # Backward compatibility indicators
    if total_risk >= 10:
        risk_level = "Critical"
        release_status = "BLOCK RELEASE"
    elif total_risk >= 6:
        risk_level = "High"
        release_status = "BLOCK RELEASE"
    elif total_risk >= 2:
        risk_level = "Medium"
        release_status = "REVIEW REQUIRED"
    else:
        risk_level = "Low"
        release_status = "SAFE TO RELEASE"

    return {
        "total_risk": total_risk,
        "risk_score": total_risk,
        "breakdown": breakdown,
        "security": breakdown["security"],
        "bug": breakdown["bug"],
        "performance": breakdown["performance"],
        "style": breakdown["style"],
        "top_must_fix": top_must_fix,
        "must_fix": top_must_fix,
        "ordered_findings": ordered_findings,
        "total_issues": len(finding_dicts),
        "risk_level": risk_level,
        "release_status": release_status,
    }