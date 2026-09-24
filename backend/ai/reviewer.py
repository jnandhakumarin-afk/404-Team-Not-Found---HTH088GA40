import os
import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

try:
    from groq import Groq
except ImportError:
    Groq = None

from models.review import ReviewFinding, LLMReviewPayload, ReviewResponse
from ai.prompts import SYSTEM_PROMPT, build_review_user_prompt, build_retry_prompt

logger = logging.getLogger(__name__)

# Model defaults — overridable via environment variables
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"


_ENV_LOADED = False


def _load_env_if_present(force: bool = False) -> None:
    """Load environment variables from .env if present and not already loaded."""
    global _ENV_LOADED
    if _ENV_LOADED and not force:
        return
    _ENV_LOADED = True
    try:
        from dotenv import load_dotenv
        here = Path(__file__).resolve().parent.parent  # backend directory
        root = here.parent
        load_dotenv(here / ".env")
        load_dotenv(root / ".env")
    except ImportError:
        for env_path in [Path("backend/.env"), Path(".env"), Path("../.env")]:
            if env_path.exists():
                try:
                    for line in env_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip("'\"")
                            if k and k not in os.environ:
                                os.environ[k] = v
                except Exception:
                    pass


# Initial environment load
_load_env_if_present()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    Extract JSON payload from raw LLM text, stripping markdown code fences if present.
    Robust against markdown code blocks and backticks inside string literals.
    """
    cleaned = text.strip()

    # 1. Try direct parsing
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # 2. Strip leading/trailing code fence
    fence_pattern = r"^```(?:json)?\s*(.*?)\s*```$"
    match = re.search(fence_pattern, cleaned, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate)
        except Exception:
            pass

    # 3. Strip simple markdown prefixes/suffixes if present
    s = cleaned
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()
    try:
        return json.loads(s)
    except Exception:
        pass

    # 4. Find the outermost JSON object bounds { ... }
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = cleaned[first_brace : last_brace + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    return json.loads(cleaned)


def _sanitize_error(msg: str) -> str:
    """
    Scrub all known API key patterns from error strings before they are
    logged or returned to callers. Never exposes credentials.
    """
    msg = re.sub(r"AQ\.[a-zA-Z0-9_\-]+", "[REDACTED_KEY]", msg)
    msg = re.sub(r"AIza[a-zA-Z0-9_\-]{30,}", "[REDACTED_KEY]", msg)
    msg = re.sub(r"gsk_[a-zA-Z0-9_\-]+", "[REDACTED_KEY]", msg)
    msg = re.sub(r"sk-ant-[a-zA-Z0-9_\-]+", "[REDACTED_KEY]", msg)
    msg = re.sub(r"Bearer\s+[a-zA-Z0-9_\-\.]+", "Bearer [REDACTED]", msg)
    return msg


def _call_gemini(client: Any, user_prompt: str) -> str:
    """Invoke the Gemini API and return the raw text response."""
    configured_model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    models_to_try = [configured_model]
    for candidate in ["gemini-3.5-flash-lite", "gemini-3-flash-preview", "gemini-2.5-flash", "gemini-3.6-flash"]:
        if candidate not in models_to_try:
            models_to_try.append(candidate)

    last_exc = None
    for model_name in models_to_try:
        try:
            config = None
            if genai_types is not None:
                config_kwargs = {
                    "system_instruction": SYSTEM_PROMPT,
                    "temperature": 0.0,
                    "max_output_tokens": 8192,
                }
                try:
                    config = genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        **config_kwargs,
                    )
                except Exception:
                    config = genai_types.GenerateContentConfig(**config_kwargs)

            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=config,
            )
            return response.text
        except Exception as e:
            last_exc = e
            err_str = str(e)
            if not any(k in err_str for k in ("503", "404", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "NOT_FOUND")):
                raise
    if last_exc:
        raise last_exc
    return ""


def _call_groq(client: Any, user_prompt: str) -> str:
    """Invoke the Groq API and return the raw text response."""
    model_name = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=4096,
    )
    return response.choices[0].message.content


def _try_llm_with_retry(
    call_fn,
    user_prompt: str,
    provider_name: str,
    errors: List[str],
) -> Optional[LLMReviewPayload]:
    """
    Attempt a single LLM call with one automatic retry on parse / validation failure.

    Returns a validated LLMReviewPayload on success, or None on failure.
    Safe error messages (no API keys) are appended to `errors`.
    """
    last_error: Optional[str] = None
    payload: Optional[LLMReviewPayload] = None

    # --- Attempt 1 ---
    try:
        raw_text = call_fn(user_prompt)
        raw_json = extract_json_from_text(raw_text)
        payload = LLMReviewPayload.model_validate(raw_json)
    except Exception as e:
        safe_msg = _sanitize_error(str(e))
        last_error = f"{type(e).__name__}: {safe_msg}"
        errors.append(f"{provider_name} attempt 1 failed: {last_error}")
        logger.warning("%s request failed: %s", provider_name, safe_msg)
        print(f"{provider_name} request failed: {safe_msg}")

    # --- Retry once on failure ---
    if payload is None and last_error is not None:
        try:
            retry_prompt = build_retry_prompt(user_prompt, last_error)
            raw_text = call_fn(retry_prompt)
            raw_json = extract_json_from_text(raw_text)
            payload = LLMReviewPayload.model_validate(raw_json)
        except Exception as retry_e:
            safe_retry = _sanitize_error(str(retry_e))
            retry_error = f"{type(retry_e).__name__}: {safe_retry}"
            errors.append(f"{provider_name} attempt 2 (retry) failed: {retry_error}")
            logger.warning("%s request failed: %s", provider_name, safe_retry)
            print(f"{provider_name} request failed: {safe_retry}")
            payload = None

    return payload


# ---------------------------------------------------------------------------
# Static → ReviewFinding converter  (unchanged from Stage 3)
# ---------------------------------------------------------------------------

def static_finding_to_review_finding(sf: Union[Dict[str, Any], Any]) -> ReviewFinding:
    """
    Convert a normalized static finding (from Stage 2) into the required ReviewFinding
    schema with detailed problem, impact, why_it_happens, and suggested fix.
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


# ---------------------------------------------------------------------------
# Deduplication  (unchanged from Stage 3)
# ---------------------------------------------------------------------------

def merge_and_deduplicate(
    static_findings: List[ReviewFinding],
    llm_findings: List[ReviewFinding],
) -> List[ReviewFinding]:
    """
    Deduplicate findings, treating static findings as ground truth.
    - Match LLM findings to static findings by rule_id or (file, line).
    - If matched, keep static source and rule_id, enhancing with AI impact analysis.
    - If LLM-only, ensure source='llm' and rule_id=None with exact code evidence.
    - Preserve all unmatched static findings.
    """
    final_findings: List[ReviewFinding] = []
    matched_static_keys: set = set()

    static_by_rule: Dict = {}
    static_by_file_line: Dict = {}
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
                    confidence="high",
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
                confidence=lf.confidence,
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


# ---------------------------------------------------------------------------
# Main review function — Gemini -> Groq -> Static fallback
# ---------------------------------------------------------------------------

def review_code(
    code: Optional[str] = None,
    static_issues: Optional[List[Any]] = None,
    files: Optional[List[Dict[str, Any]]] = None,
    diff: Optional[str] = None,
    client: Optional[Any] = None,        # Gemini client (injectable for testing)
    groq_client: Optional[Any] = None,   # Groq client (injectable for testing)
) -> Dict[str, Any]:
    """
    Main contextual code review function.

    Tries providers in order:
      1. Google Gemini (GEMINI_API_KEY)
      2. Groq          (GROQ_API_KEY)
      3. Static-only fallback

    Never crashes on API unavailability.
    Never exposes API keys in logs or return values.
    Returns a `provider` key: "gemini" | "groq" | "static"
    """
    _load_env_if_present()

    static_raw = static_issues or []
    normalized_static: List[ReviewFinding] = [
        static_finding_to_review_finding(item) for item in static_raw
    ]

    errors: List[str] = []

    # ------------------------------------------------------------------
    # Build user prompt (shared across all providers)
    # ------------------------------------------------------------------
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
        static_findings=static_prompt_data,
    )

    llm_payload: Optional[LLMReviewPayload] = None
    active_provider: str = "static"

    # ==================================================================
    # PROVIDER 1: Google Gemini
    # ==================================================================
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    gemini_client = client  # `client` param = Gemini client in tests

    gemini_key_detected = "YES" if bool(gemini_api_key or gemini_client) else "NO"
    logger.info("Gemini key detected: %s", gemini_key_detected)
    print(f"Gemini key detected: {gemini_key_detected}")

    if gemini_client is None:
        if not gemini_api_key:
            errors.append("GEMINI_API_KEY not set — skipping Gemini.")
        elif genai is None:
            errors.append("google-genai SDK not installed — skipping Gemini.")
            logger.warning("google-genai SDK not installed.")
        else:
            try:
                gemini_client = genai.Client(api_key=gemini_api_key)
            except Exception as e:
                safe = _sanitize_error(str(e))
                errors.append(f"Gemini client init failed: {type(e).__name__}: {safe}")
                logger.warning("Gemini request failed: %s", safe)
                print(f"Gemini request failed: {safe}")
                gemini_client = None

    if gemini_client is not None and llm_payload is None:
        llm_payload = _try_llm_with_retry(
            call_fn=lambda prompt: _call_gemini(gemini_client, prompt),
            user_prompt=user_prompt,
            provider_name="Gemini",
            errors=errors,
        )
        if llm_payload is not None:
            active_provider = "gemini"
            logger.info("Gemini review succeeded.")

    # ==================================================================
    # PROVIDER 2: Groq fallback
    # ==================================================================
    if llm_payload is None:
        groq_api_key = os.environ.get("GROQ_API_KEY")
        effective_groq_client = groq_client

        groq_key_detected = "YES" if bool(groq_api_key or effective_groq_client) else "NO"
        logger.info("Groq key detected: %s", groq_key_detected)
        print(f"Groq key detected: {groq_key_detected}")

        if effective_groq_client is None:
            if not groq_api_key:
                errors.append("GROQ_API_KEY not set — skipping Groq.")
            elif Groq is None:
                errors.append("groq SDK not installed — skipping Groq.")
                logger.warning("groq SDK not installed.")
            else:
                try:
                    effective_groq_client = Groq(api_key=groq_api_key)
                except Exception as e:
                    safe = _sanitize_error(str(e))
                    errors.append(f"Groq client init failed: {type(e).__name__}: {safe}")
                    logger.warning("Groq request failed: %s", safe)
                    print(f"Groq request failed: {safe}")

        if effective_groq_client is not None:
            llm_payload = _try_llm_with_retry(
                call_fn=lambda prompt: _call_groq(effective_groq_client, prompt),
                user_prompt=user_prompt,
                provider_name="Groq",
                errors=errors,
            )
            if llm_payload is not None:
                active_provider = "groq"
                logger.info("Groq review succeeded.")

    # ==================================================================
    # PROVIDER 3: Static-only fallback
    # ==================================================================
    if llm_payload is None:
        reason_detail = f" ({errors[-1]})" if errors else ""
        errors.append(f"All AI providers failed{reason_detail}. Returning static analysis findings.")
        findings_dicts = [f.model_dump() for f in normalized_static]
        return {
            "summary": "Review completed using static analysis findings (AI providers unavailable).",
            "findings": findings_dicts,
            "total_findings": len(findings_dicts),
            "issues": findings_dicts,
            "total_issues": len(findings_dicts),
            "fallback_to_static": True,
            "provider": "static",
            "errors": errors,
        }

    # ==================================================================
    # Deduplicate and combine findings
    # ==================================================================
    combined_findings = merge_and_deduplicate(
        static_findings=normalized_static,
        llm_findings=llm_payload.findings,
    )
    findings_dicts = [f.model_dump() for f in combined_findings]

    return {
        "summary": llm_payload.summary,
        "findings": findings_dicts,
        "total_findings": len(findings_dicts),
        "issues": findings_dicts,
        "total_issues": len(findings_dicts),
        "fallback_to_static": False,
        "provider": active_provider,
        "errors": errors,
    }