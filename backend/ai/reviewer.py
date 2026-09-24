def review_code(code: str, static_issues: list):
    return {
        "summary": "Code review completed.",
        "issues": static_issues,
        "total_issues": len(static_issues)
    }