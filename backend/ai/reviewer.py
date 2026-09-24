import os
import json
import re
from typing import List, Dict, Any, Optional, Union

try:
    import anthropic
except ImportError:
    anthropic = None

from models.review import ReviewFinding, LLMReviewPayload, ReviewResponse
from ai.prompts import SYSTEM_PROMPT, build_review_user_prompt, build_retry_prompt

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    Extract JSON payload from raw LLM text, stripping markdown code fences if present.
    """
    cleaned = text.strip()
    # Look for ```json ... ```
    if "```json" in cleaned:
        parts = cleaned.split("```json")
        if len(parts) > 1:
            block = parts[1].split("```")[0].strip()
            return json.loads(block)
    elif "```" in cleaned:
        parts = cleaned.split("```")
        if len(parts) > 1:
            block = parts[1].strip()
            return json.loads(block)

    # Search for first '{' and last '}'
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return json.loads(cleaned[first_brace : last_brace + 1])

    return json.loads(cleaned)


def static_finding_to_review_finding(sf: Union[Dict[str, Any], Any]) -> ReviewFinding:
    """
    Convert a normalized static finding (from Stage 2) into the required ReviewFinding schema
    with detailed problem, impact, why_it_happens, and suggested fix details.
    """
    if hasattr(sf, "model_dump"):
        sf_dict = sf.model_dump()
    elif isinstance(sf, dict):
        sf_dict = sf
    else:
        sf_dict = dict(sf)

    file_path = str(sf_dict.get("file", "unknown"))
    line = int(sf_dict.get("line", 1))
    rule_id = str(sf_dict.get("rule_id", "STATIC"))
    tool = str(sf_dict.get("tool", "")).lower()
    raw_sev = str(sf_dict.get("severity", "MEDIUM")).upper()
    message = str(sf_dict.get("message", "Static analysis issue detected"))
    evidence = str(sf_dict.get("evidence") or sf_dict.get("code_snippet") or message)

    # Map category
    if "bandit" in tool or rule_id.startswith("S") or "sec" in rule_id.lower() or (tool == "bandit"):
        category = "security"
    elif "perf" in tool or rule_id.startswith("PERF"):
        category = "performance"
    elif rule_id.startswith("STYLE") or "style" in tool:
        category = "style"
    else:
        category = "bug"

    confidence = "high" if raw_sev in ("HIGH", "CRITICAL") else "moderate"

    # Deep code-impact analysis defaults based on known rule families
    problem = message
    if rule_id in ("B307", "eval") or "eval" in message.lower():
        problem = "Use of dangerous dynamic eval() on untrusted input"
        impact = "Critical arbitrary code execution (RCE) allowing attackers to run arbitrary Python code or system commands."
        why_it_happens = "eval() parses and executes string arguments directly in the Python runtime environment."
        suggested_fix = "Use ast.literal_eval() for safe literal parsing, or json.loads() for structured data."
    elif rule_id in ("B602", "B404", "B607") or "shell=true" in message.lower():
        problem = "Execution of system command via subprocess with shell=True"
        impact = "High-severity command injection allowing attackers to execute arbitrary system commands via shell metacharacters."
        why_it_happens = "shell=True invokes an OS shell interpreter which parses characters like ;, &&, |, and ` in arguments."
        suggested_fix = "Pass command and arguments as a sequence of strings with shell=False: subprocess.run(['cmd', arg1], shell=False)."
    elif rule_id == "B105" or "hardcoded_password" in message.lower():
        problem = "Possible hardcoded password or credential token in source code"
        impact = "Credential exposure leading to unauthorized access, privilege escalation, and credential harvesting."
        why_it_happens = "Plaintext credentials stored in source code persist in version control history and distribution artifacts."
        suggested_fix = "Load sensitive secrets from environment variables (os.environ) or a secure secrets manager."
    elif rule_id == "B006" or "mutable default" in message.lower():
        problem = "Mutable default argument (list/dict/set) used in function definition"
        impact = "State leaks across function invocations causing memory leaks and hard-to-diagnose logical bugs."
        why_it_happens = "Python evaluates default parameter expressions once at definition time, sharing the identical instance across all calls."
        suggested_fix = "Use None as the default argument value and initialize the collection inside the function."
    elif rule_id == "E722" or "bare except" in message.lower():
        problem = "Bare except clause without explicit exception type"
        impact = "Silently swallows critical system exceptions such as KeyboardInterrupt and SystemExit, masking fatal defects."
        why_it_happens = "An unqualified 'except:' catches BaseException, intercepting signals and memory errors unintended by the author."
        suggested_fix = "Catch specific exceptions like 'except Exception as e:' or narrower types like 'except ValueError:'."
    elif category == "security":
        impact = "Potential security exposure, vulnerability exploitation, or unauthorized execution risk."
        why_it_happens = f"Static security rule {rule_id} triggered: {message}"
        suggested_fix = f"Resolve {rule_id} flagged by {tool or 'static analyzer'}."
    elif category == "performance":
        impact = "Performance degradation, increased latency, or excessive resource consumption."
        why_it_happens = f"Static performance rule {rule_id} triggered: {message}"
        suggested_fix = f"Optimize code pattern flagged by {rule_id}."
    elif category == "style":
        impact = "Code readability and maintainability degradation."
        why_it_happens = f"Style rule {rule_id} triggered: {message}"
        suggested_fix = f"Reformat or adjust style according to {rule_id}."
    else:
        impact = "Unexpected application behavior, runtime exception, or application instability."
        why_it_happens = f"Static analysis rule {rule_id} triggered: {message}"
        suggested_fix = f"Resolve {rule_id} flagged by {tool or 'static analyzer'}."

    return ReviewFinding(
        file=file_path,
        line=line,
        category=category,
        source="static",
        rule_id=rule_id,
        evidence=evidence,
        problem=problem,
        impact=impact,
        why_it_happens=why_it_happens,
        explanation=message,
        suggested_fix=suggested_fix,
        confidence=confidence,
    )


def merge_and_deduplicate(
    static_findings: List[ReviewFinding],
    llm_findings: List[ReviewFinding]
) -> List[ReviewFinding]:
    """
    Deduplicate findings, treating static findings as ground truth:
    - Match LLM findings to static findings by rule_id or (file, line).
    - If matched, keep static source and rule_id, enhancing with AI impact analysis.
    - If LLM-only, ensure source='llm' and rule_id=None with exact code evidence.
    - Preserve all unmatched static findings.
    """
    final_findings: List[ReviewFinding] = []
    matched_static_keys = set()

    static_by_rule = {}
    static_by_file_line = {}
    for sf in static_findings:
        if sf.rule_id:
            static_by_rule[(sf.file, sf.rule_id)] = sf
        static_by_file_line[(sf.file, sf.line)] = sf

    for lf in llm_findings:
        matched_sf = None
        if lf.rule_id and (lf.file, lf.rule_id) in static_by_rule:
            matched_sf = static_by_rule[(lf.file, lf.rule_id)]
        elif (lf.file, lf.line) in static_by_file_line:
            matched_sf = static_by_file_line[(lf.file, lf.line)]

        if matched_sf:
            key = (matched_sf.file, matched_sf.line, matched_sf.rule_id)
            if key not in matched_static_keys:
                matched_static_keys.add(key)
                merged = ReviewFinding(
                    file=matched_sf.file,
                    line=matched_sf.line,
                    category=matched_sf.category,
                    source="static",
                    rule_id=matched_sf.rule_id,
                    evidence=lf.evidence if lf.evidence else matched_sf.evidence,
                    problem=lf.problem if lf.problem else matched_sf.problem,
                    impact=lf.impact if lf.impact else matched_sf.impact,
                    why_it_happens=lf.why_it_happens if lf.why_it_happens else matched_sf.why_it_happens,
                    explanation=lf.explanation if lf.explanation else matched_sf.explanation,
                    suggested_fix=lf.suggested_fix if lf.suggested_fix else matched_sf.suggested_fix,
                    confidence="high"
                )
                final_findings.append(merged)
        else:
            # LLM-only finding
            llm_clean = ReviewFinding(
                file=lf.file,
                line=lf.line,
                category=lf.category,
                source="llm",
                rule_id=None,
                evidence=lf.evidence,
                problem=lf.problem,
                impact=lf.impact,
                why_it_happens=lf.why_it_happens,
                explanation=lf.explanation,
                suggested_fix=lf.suggested_fix,
                confidence=lf.confidence
            )
            final_findings.append(llm_clean)

    # Ensure all static findings are present (ground truth guarantee)
    for sf in static_findings:
        key = (sf.file, sf.line, sf.rule_id)
        if key not in matched_static_keys:
            final_findings.append(sf)

    # Sort deterministically
    final_findings.sort(key=lambda x: (x.file, x.line))
    return final_findings


def review_code(
    code: Optional[str] = None,
    static_issues: Optional[List[Any]] = None,
    files: Optional[List[Dict[str, Any]]] = None,
    diff: Optional[str] = None,
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Main contextual code review function (Stage 3).

    Accepts code/diff/files and static findings, invokes the Anthropic API
    with the system review policy, validates output with Pydantic, retries
    once on failure, and falls back to static findings if unavailable.
    """
    static_raw = static_issues or []
    # Convert all raw static issues into normalized ReviewFinding objects
    normalized_static: List[ReviewFinding] = [
        static_finding_to_review_finding(item) for item in static_raw
    ]

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    errors: List[str] = []

    # Fallback if API key is missing
    if not api_key and client is None:
        errors.append("ANTHROPIC_API_KEY environment variable is not set. Falling back to static findings.")
        findings_dicts = [f.model_dump() for f in normalized_static]
        return {
            "summary": "Review completed using static analysis findings (LLM unavailable).",
            "findings": findings_dicts,
            "total_findings": len(findings_dicts),
            "issues": findings_dicts,
            "total_issues": len(findings_dicts),
            "fallback_to_static": True,
            "errors": errors,
        }

    # Initialize Anthropic client if not provided (e.g. for testing)
    if client is None:
        if anthropic is None:
            errors.append("Anthropic SDK is not installed. Falling back to static findings.")
            findings_dicts = [f.model_dump() for f in normalized_static]
            return {
                "summary": "Review completed using static analysis findings (Anthropic SDK not installed).",
                "findings": findings_dicts,
                "total_findings": len(findings_dicts),
                "issues": findings_dicts,
                "total_issues": len(findings_dicts),
                "fallback_to_static": True,
                "errors": errors,
            }
        try:
            client = anthropic.Anthropic(api_key=api_key)
        except Exception as e:
            errors.append(f"Failed to initialize Anthropic client: {type(e).__name__}")
            findings_dicts = [f.model_dump() for f in normalized_static]
            return {
                "summary": "Review completed using static analysis findings.",
                "findings": findings_dicts,
                "total_findings": len(findings_dicts),
                "issues": findings_dicts,
                "total_issues": len(findings_dicts),
                "fallback_to_static": True,
                "errors": errors,
            }

    # Prepare static findings dicts for prompt
    static_prompt_data = [
        {
            "file": sf.file,
            "line": sf.line,
            "category": sf.category,
            "rule_id": sf.rule_id,
            "message": sf.explanation,
        }
        for sf in normalized_static
    ]

    user_prompt = build_review_user_prompt(
        files=files,
        diff=diff,
        code=code,
        static_findings=static_prompt_data
    )

    llm_payload: Optional[LLMReviewPayload] = None
    last_error: Optional[str] = None

    # ATTEMPT 1
    try:
        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=4096,
            temperature=0.0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        content_text = ""
        for block in getattr(response, "content", []):
            if getattr(block, "type", "") == "text":
                content_text += getattr(block, "text", "")
            elif isinstance(block, dict) and block.get("type") == "text":
                content_text += block.get("text", "")

        raw_json = extract_json_from_text(content_text)
        llm_payload = LLMReviewPayload.model_validate(raw_json)
    except Exception as e:
        safe_msg = re.sub(r"sk-ant-[a-zA-Z0-9_\-]+", "[REDACTED_KEY]", str(e))
        last_error = f"{type(e).__name__}: {safe_msg}"
        errors.append(f"Anthropic API call attempt 1 failed: {last_error}")

    # RETRY ONCE (ATTEMPT 2) if invalid JSON or validation failed
    if llm_payload is None and last_error is not None:
        try:
            retry_prompt = build_retry_prompt(user_prompt, last_error)
            retry_response = client.messages.create(
                model=DEFAULT_MODEL,
                max_tokens=4096,
                temperature=0.0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": retry_prompt}],
            )
            content_text = ""
            for block in getattr(retry_response, "content", []):
                if getattr(block, "type", "") == "text":
                    content_text += getattr(block, "text", "")
                elif isinstance(block, dict) and block.get("type") == "text":
                    content_text += block.get("text", "")

            raw_json = extract_json_from_text(content_text)
            llm_payload = LLMReviewPayload.model_validate(raw_json)
        except Exception as retry_err:
            safe_retry_msg = re.sub(r"sk-ant-[a-zA-Z0-9_\-]+", "[REDACTED_KEY]", str(retry_err))
            retry_error_desc = f"{type(retry_err).__name__}: {safe_retry_msg}"
            errors.append(f"Anthropic API call attempt 2 (retry) failed: {retry_error_desc}")
            last_error = retry_error_desc
            llm_payload = None

    # If both attempts failed or API errored, fall back to static findings
    if llm_payload is None:
        reason_detail = f" ({last_error})" if last_error else ""
        errors.append(f"LLM review failed{reason_detail}. Returning static analysis findings as fallback.")
        findings_dicts = [f.model_dump() for f in normalized_static]
        return {
            "summary": f"Review completed with static analysis findings (LLM unavailable{reason_detail}).",
            "findings": findings_dicts,
            "total_findings": len(findings_dicts),
            "issues": findings_dicts,
            "total_issues": len(findings_dicts),
            "fallback_to_static": True,
            "errors": errors,
        }

    # Deduplicate and combine findings
    combined_findings = merge_and_deduplicate(
        static_findings=normalized_static,
        llm_findings=llm_payload.findings
    )
    findings_dicts = [f.model_dump() for f in combined_findings]

    return {
        "summary": llm_payload.summary,
        "findings": findings_dicts,
        "total_findings": len(findings_dicts),
        "issues": findings_dicts,
        "total_issues": len(findings_dicts),
        "fallback_to_static": False,
        "errors": errors,
    }