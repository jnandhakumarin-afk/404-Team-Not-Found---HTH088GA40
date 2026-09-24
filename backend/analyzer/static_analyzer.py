def analyze_code(code: str):
    issues = []
    lines = code.splitlines()

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()

        if "print(" in stripped:
            issues.append({
                "type": "Code Smell",
                "severity": "Low",
                "line": index,
                "confidence": 0.90,
                "evidence": stripped,
                "explanation": "Debug-style output may be left in production code.",
                "suggested_fix": "Remove or replace the print statement with proper logging."
            })

        if "eval(" in stripped:
            issues.append({
                "type": "Security",
                "severity": "High",
                "line": index,
                "confidence": 0.96,
                "evidence": stripped,
                "explanation": "Dynamic evaluation of input can create a security risk.",
                "suggested_fix": "Avoid eval() and use a safer, explicitly controlled alternative."
            })

        if "except:" in stripped:
            issues.append({
                "type": "Code Smell",
                "severity": "Medium",
                "line": index,
                "confidence": 0.94,
                "evidence": stripped,
                "explanation": "A bare except catches every exception and can hide unexpected errors.",
                "suggested_fix": "Catch specific exception types instead."
            })

    return issues