import os
import json
import logging
from typing import Dict, Any, Optional

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

from models.fix import FixRequest, FixResponse
from ai.reviewer import _load_env_if_present, _sanitize_error, extract_json_from_text

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"

SYSTEM_FIX_PROMPT = """You are an expert software security and code-fixing assistant.

You are given an actual code snippet and a detected code issue.

Generate the smallest safe code change that fixes the reported issue.

Rules:

1. Fix only the reported issue.
2. Do not perform unrelated refactoring.
3. Preserve existing application behavior.
4. Do not invent missing code.
5. Do not remove security protections.
6. Do not weaken authentication or authorization.
7. Never introduce hardcoded passwords, API keys, tokens, or secrets.
8. Use the exact provided code as the source of truth.
9. If the issue is based on a static-analysis rule, respect that rule.
10. If you are uncertain, do not claim the issue is fixed.
11. Explain exactly what changed and why.
12. Return ONLY valid JSON.

Required JSON:

{
  "fixed_code": "complete replacement for the supplied code section",
  "explanation": "why this fixes the issue",
  "changes": "what was changed",
  "confidence": "high|moderate"
}"""


from pathlib import Path

def _extract_local_file_snippet(file_path_str: str, line_no: int) -> Optional[str]:
    """If the target file exists locally, read a few lines of context around line_no."""
    if not file_path_str:
        return None
    candidates = [
        Path(file_path_str),
        Path("backend") / file_path_str,
        Path("..") / file_path_str,
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                if 1 <= line_no <= len(lines):
                    start = max(0, line_no - 3)
                    end = min(len(lines), line_no + 2)
                    return "\n".join(lines[start:end])
            except Exception:
                pass
    return None


def build_fix_user_prompt(req: FixRequest) -> str:
    """Build targeted prompt based on whether finding source is static or llm."""
    base_code = req.code.strip() if req.code and req.code.strip() else req.evidence.strip()
    if (base_code == req.explanation.strip() or len(base_code.splitlines()) <= 1) and req.file and req.line > 0:
        local_snip = _extract_local_file_snippet(req.file, req.line)
        if local_snip:
            base_code = local_snip

    if req.source.lower() == "static":
        return f"""[TASK: FIX STATIC ANALYSIS CODE ISSUE]
File: {req.file}
Line: {req.line}
Category: {req.category.upper()}
Static Rule ID: {req.rule_id or 'STATIC_RULE'}
Detected Issue: {req.explanation}

Code Evidence:
```
{req.evidence}
```

Relevant Code to Fix:
```
{base_code}
```
{f"Initial remediation guidance: {req.suggested_fix}" if req.suggested_fix else ""}

Generate the exact safe replacement for the code above that resolves rule {req.rule_id or 'the detected issue'}.
Preserve existing logic and variables. Return ONLY the requested JSON object."""
    else:
        return f"""[TASK: FIX AI-DETECTED CODE ISSUE]
File: {req.file}
Line: {req.line}
Category: {req.category.upper()}
Issue Explanation: {req.explanation}

Code Evidence:
```
{req.evidence}
```

Relevant Code to Fix:
```
{base_code}
```
{f"Initial remediation guidance: {req.suggested_fix}" if req.suggested_fix else ""}

Generate the exact safe replacement for the code above that fixes this {req.category} issue.
Preserve surrounding context and functionality. Return ONLY the requested JSON object."""


def _call_gemini_fix(client: Any, user_prompt: str) -> str:
    """Invoke the Gemini API for code fixing."""
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
                    "system_instruction": SYSTEM_FIX_PROMPT,
                    "temperature": 0.0,
                    "max_output_tokens": 4096,
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


def _call_groq_fix(client: Any, user_prompt: str) -> str:
    """Invoke the Groq API for code fixing."""
    model_name = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_FIX_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content or ""


def generate_code_fix(
    req: FixRequest,
    gemini_client: Optional[Any] = None,
    groq_client: Optional[Any] = None,
) -> FixResponse:
    """
    Generate an AI code fix using the primary Gemini provider, falling back to
    Groq if Gemini is unavailable, or returning 'unavailable' without crashing.
    """
    _load_env_if_present()

    original_target_code = req.code.strip() if req.code and req.code.strip() else req.evidence.strip()
    if (original_target_code == req.explanation.strip() or len(original_target_code.splitlines()) <= 1) and req.file and req.line > 0:
        local_snip = _extract_local_file_snippet(req.file, req.line)
        if local_snip:
            original_target_code = local_snip
    user_prompt = build_fix_user_prompt(req)
    errors = []

    # ------------------------------------------------------------------
    # 1. Primary: Google Gemini
    # ------------------------------------------------------------------
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    active_gemini = gemini_client

    if active_gemini is None and gemini_api_key and genai is not None:
        try:
            active_gemini = genai.Client(api_key=gemini_api_key)
        except Exception as e:
            errors.append(f"Gemini client init: {_sanitize_error(str(e))}")
            active_gemini = None

    if active_gemini is not None:
        try:
            raw_text = _call_gemini_fix(active_gemini, user_prompt)
            data = extract_json_from_text(raw_text)
            if isinstance(data, dict) and data.get("fixed_code"):
                conf = str(data.get("confidence", "high")).lower()
                if conf not in ("high", "moderate", "low"):
                    conf = "high"
                return FixResponse(
                    status="success",
                    file=req.file,
                    original_code=original_target_code,
                    fixed_code=str(data["fixed_code"]),
                    explanation=str(data.get("explanation", "AI fix applied successfully.")),
                    changes=str(data.get("changes", "Code modified to resolve detected issue.")),
                    confidence=conf,
                    provider="gemini",
                )
        except Exception as e:
            safe_err = _sanitize_error(str(e))
            errors.append(f"Gemini fix call failed: {safe_err}")
            logger.warning("Gemini fix generation failed: %s", safe_err)

    # ------------------------------------------------------------------
    # 2. Fallback: Groq
    # ------------------------------------------------------------------
    groq_api_key = os.environ.get("GROQ_API_KEY")
    active_groq = groq_client

    if active_groq is None and groq_api_key and Groq is not None:
        try:
            active_groq = Groq(api_key=groq_api_key)
        except Exception as e:
            errors.append(f"Groq client init: {_sanitize_error(str(e))}")
            active_groq = None

    if active_groq is not None:
        try:
            raw_text = _call_groq_fix(active_groq, user_prompt)
            data = extract_json_from_text(raw_text)
            if isinstance(data, dict) and data.get("fixed_code"):
                conf = str(data.get("confidence", "high")).lower()
                if conf not in ("high", "moderate", "low"):
                    conf = "high"
                return FixResponse(
                    status="success",
                    file=req.file,
                    original_code=original_target_code,
                    fixed_code=str(data["fixed_code"]),
                    explanation=str(data.get("explanation", "AI fix applied successfully via Groq.")),
                    changes=str(data.get("changes", "Code modified to resolve detected issue.")),
                    confidence=conf,
                    provider="groq",
                )
        except Exception as e:
            safe_err = _sanitize_error(str(e))
            errors.append(f"Groq fix call failed: {safe_err}")
            logger.warning("Groq fix generation failed: %s", safe_err)

    # ------------------------------------------------------------------
    # 3. Fallback: Rule-guided or Unavailable
    # ------------------------------------------------------------------
    if req.suggested_fix and req.suggested_fix.strip():
        return FixResponse(
            status="success",
            file=req.file,
            original_code=original_target_code,
            fixed_code=req.suggested_fix.strip(),
            explanation=f"Rule-guided remediation based on {req.rule_id or req.category}: {req.explanation}",
            changes="Applied standard security/bug fix pattern for this rule.",
            confidence="moderate",
            provider="rule-fallback",
        )

    return FixResponse(
        status="unavailable",
        file=req.file,
        original_code=original_target_code,
        fixed_code=original_target_code,
        explanation="AI fix unavailable. Both Gemini and Groq providers were unreachable or credentials were not configured.",
        changes="No automated changes could be generated.",
        confidence="low",
        provider="none",
    )
