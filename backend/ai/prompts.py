import json
from typing import List, Dict, Any, Optional

SYSTEM_PROMPT = """You are a senior code review and application security expert.

Analyze the provided code changes and static-analysis findings to provide meaningful code-impact analysis, not just superficial bug labels.

Rules:
1. Report bugs, security vulnerabilities, or performance defects only when:
   - they match an existing static-analysis finding, OR
   - there is exact, verifiable code evidence in the changed code/diff.
2. Static-analysis findings must be enriched with context and marked using source="static" with their original rule_id.
3. Do not duplicate the same static-analysis finding as an LLM finding.
4. LLM-only findings must use source="llm", set rule_id=null, and MUST include an exact quoted code snippet in "evidence".
5. For EVERY genuine finding, provide a complete, deep code-impact analysis:
   - "problem": Clearly explain what is wrong in the code.
   - "evidence": Exact quoted code snippet from the changed code/file.
   - "impact": Explain what effect this issue can have on the actual project/application (e.g. security exposure, incorrect application behavior, data corruption/loss, performance degradation, application crash, authentication/authorization risk, reliability problems).
   - "why_it_happens": Explain the technical reason the code causes the problem.
   - "suggested_fix": Concrete and practical correction approach, including a small corrected-code example where useful.
   - "confidence": "high" or "moderate".
6. Do not flag idiomatic code, formatting, indentation, naming, or personal stylistic preferences.
7. Do not invent code, vulnerabilities, or ungrounded evidence.
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
  "summary": "Overall summary of code review findings and release impact",
  "findings": [
    {
      "file": "path/to/file",
      "line": 1,
      "category": "security | bug | performance | style",
      "source": "static | llm",
      "rule_id": "rule_id_string_or_null",
      "problem": "clear explanation of what is wrong in the code",
      "evidence": "exact quoted snippet from the changed code",
      "impact": "concrete effect on the application (e.g. security exposure, data loss, crash)",
      "why_it_happens": "technical reason why the code causes this issue",
      "suggested_fix": "concrete recommendation and corrected code approach",
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