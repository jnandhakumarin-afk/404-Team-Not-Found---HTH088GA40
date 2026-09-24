import json
from typing import List, Dict, Any, Optional

SYSTEM_PROMPT = """You are a code review assistant.

Analyze the provided code changes and static-analysis findings.

Rules:
1. Report bugs or security issues only when:
   - they match an existing static-analysis finding, OR
   - there is exact evidence in the changed code.
2. Static-analysis findings must be explained using source=static and their original rule_id.
3. Do not duplicate the same static-analysis finding as an LLM finding.
4. LLM-only findings must use source=llm and include an exact quoted code snippet in evidence.
5. Do not flag idiomatic code, formatting, naming, or personal style as bugs.
6. If uncertain, use a lower category or do not report the issue.
7. Do not invent code, vulnerabilities, or evidence.
8. Return ONLY valid JSON matching the required schema."""


def build_review_user_prompt(
    files: Optional[List[Dict[str, Any]]] = None,
    diff: Optional[str] = None,
    code: Optional[str] = None,
    static_findings: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Construct the structured user prompt containing changed files, diffs,
    and normalized static analysis findings.
    """
    prompt_parts = [
        "Please review the following code changes and static-analysis findings according to the policy.",
        "\n### Static Analysis Findings (Ground Truth):"
    ]

    if static_findings:
        prompt_parts.append(json.dumps(static_findings, indent=2))
    else:
        prompt_parts.append("No static analysis findings reported.")

    prompt_parts.append("\n### Changed Files & Code:")
    if files:
        for idx, f in enumerate(files, 1):
            fname = f.get("file", "unknown")
            lang = f.get("language", "unknown")
            patch = f.get("patch", "")
            code_content = f.get("code") or f.get("content") or ""
            prompt_parts.append(f"\n--- File {idx}: {fname} ({lang}) ---")
            if patch:
                prompt_parts.append("Diff patch:")
                prompt_parts.append(patch)
            if code_content:
                prompt_parts.append("Full content:")
                prompt_parts.append(code_content)
    elif diff:
        prompt_parts.append("Diff:")
        prompt_parts.append(diff)
    elif code:
        prompt_parts.append("Code:")
        prompt_parts.append(code)
    else:
        prompt_parts.append("No code or diff provided.")

    prompt_parts.append("""
### Expected Output Schema:
Return ONLY a valid JSON object matching this schema:
{
  "summary": "Overall summary of code review findings",
  "findings": [
    {
      "file": "path/to/file",
      "line": 1,
      "category": "security | bug | performance | style",
      "source": "static | llm",
      "rule_id": "rule_id_string_or_null",
      "evidence": "exact quoted snippet from the changed code",
      "explanation": "clear explanation of why this is an issue",
      "suggested_fix": "concrete recommendation to resolve the issue",
      "confidence": "high | moderate"
    }
  ]
}
""")
    return "\n".join(prompt_parts)


def build_retry_prompt(original_prompt: str, error_details: str) -> str:
    """
    Construct a retry prompt including previous error details.
    """
    return (
        f"{original_prompt}\n\n"
        f"### ATTENTION - PREVIOUS ATTEMPT FAILED:\n"
        f"Your previous response could not be parsed or failed schema validation with error:\n"
        f"{error_details}\n\n"
        f"Please correct the errors and return ONLY a valid JSON object matching the required schema. "
        f"Do NOT include markdown commentary or backticks outside the JSON."
    )