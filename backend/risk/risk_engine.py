SEVERITY_SCORES = {
    "Critical": 40,
    "High": 30,
    "Medium": 15,
    "Low": 5
}


def calculate_risk(issues):
    total_score = 0

    for issue in issues:
        severity = issue.get("severity", "Low")
        total_score += SEVERITY_SCORES.get(severity, 0)

    risk_score = min(total_score, 100)

    if risk_score >= 70:
        risk_level = "Critical"
        release_status = "BLOCK RELEASE"
    elif risk_score >= 40:
        risk_level = "High"
        release_status = "BLOCK RELEASE"
    elif risk_score >= 20:
        risk_level = "Medium"
        release_status = "REVIEW REQUIRED"
    else:
        risk_level = "Low"
        release_status = "SAFE TO RELEASE"

    sorted_issues = sorted(
        issues,
        key=lambda issue: SEVERITY_SCORES.get(
            issue.get("severity", "Low"), 0
        ),
        reverse=True
    )

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "release_status": release_status,
        "total_issues": len(issues),
        "must_fix": sorted_issues[:3]
    }