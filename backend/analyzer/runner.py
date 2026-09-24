"""
Static-analysis dispatcher.

Given a list of ChangedFile dicts (as produced by Stage 1 /api/ingest),
this module:
  1. Detects the language from the ``language`` field.
  2. Dispatches to the correct tool runner(s).
  3. Collects and deduplicates findings.
  4. Returns a unified list of normalized Finding objects.

Language → Tools mapping
------------------------
python      → ruff (bugs + security), bandit (security)
javascript  → eslint
typescript  → eslint
other       → skipped (recorded in skipped_files)
"""

from typing import List, Tuple

from models.analysis import Finding
from analyzer.ruff_runner import run_ruff
from analyzer.bandit_runner import run_bandit
from analyzer.eslint_runner import run_eslint

_PYTHON_LANGUAGES = {"python"}
_JS_TS_LANGUAGES = {"javascript", "typescript"}


def analyze_changed_files(
    files: List[dict],
) -> Tuple[List[Finding], List[str], List[str]]:
    """
    Run static analysis over all changed files from a Stage 1 ingest response.

    Parameters
    ----------
    files:
        List of dicts, each matching the ``ChangedFile`` schema from Stage 1.
        Required keys: ``file`` (path), ``language``, ``patch`` (may be None).

    Returns
    -------
    (findings, skipped_files, tool_errors)
    findings      — deduplicated, sorted list of Finding objects
    skipped_files — filenames whose language is unsupported
    tool_errors   — non-fatal diagnostic strings (missing tools, timeouts, …)
    """
    all_findings: List[Finding] = []
    skipped_files: List[str] = []
    tool_errors: List[str] = []

    for f in files:
        filename: str = f.get("file", "unknown")
        language: str = (f.get("language") or "unknown").lower()
        patch: str | None = f.get("patch")

        # We analyse the diff patch.  If there is no patch (binary files,
        # very large truncated patches, etc.) we skip gracefully.
        if not patch:
            skipped_files.append(filename)
            continue

        # Extract only the added / changed lines from the unified diff
        # so the tool sees syntactically plausible code rather than raw diff.
        code = _extract_code_from_patch(patch)

        if not code.strip():
            skipped_files.append(filename)
            continue

        if language in _PYTHON_LANGUAGES:
            r_findings, r_errors = run_ruff(code, filename)
            b_findings, b_errors = run_bandit(code, filename)
            all_findings.extend(r_findings)
            all_findings.extend(b_findings)
            tool_errors.extend(r_errors)
            tool_errors.extend(b_errors)

        elif language in _JS_TS_LANGUAGES:
            e_findings, e_errors = run_eslint(code, filename)
            all_findings.extend(e_findings)
            tool_errors.extend(e_errors)

        else:
            skipped_files.append(filename)

    # Deduplicate: same file + line + rule_id + tool
    seen: set = set()
    deduped: List[Finding] = []
    for finding in all_findings:
        key = (finding.file, finding.line, finding.rule_id, finding.tool)
        if key not in seen:
            seen.add(key)
            deduped.append(finding)

    # Sort: file → line → tool
    deduped.sort(key=lambda x: (x.file, x.line, x.tool))

    # Deduplicate tool_errors too
    tool_errors = list(dict.fromkeys(tool_errors))

    return deduped, list(dict.fromkeys(skipped_files)), tool_errors


def _extract_code_from_patch(patch: str) -> str:
    """
    Extract the code lines added/unchanged from a unified diff patch.

    Lines prefixed with '+' are new code; context lines (no prefix or
    starting with ' ') are kept for surrounding context.
    Lines starting with '-' are removed code and are excluded.
    Diff headers (@@ …) are stripped.
    """
    lines: List[str] = []
    for raw_line in patch.splitlines():
        if raw_line.startswith("@@"):
            # hunk header — skip
            continue
        if raw_line.startswith("---") or raw_line.startswith("+++"):
            # file header — skip
            continue
        if raw_line.startswith("-"):
            # removed line — skip (we only analyse what remains)
            continue
        if raw_line.startswith("+"):
            # added line — strip the leading '+'
            lines.append(raw_line[1:])
        else:
            # context line — keep as-is
            lines.append(raw_line)
    return "\n".join(lines)
