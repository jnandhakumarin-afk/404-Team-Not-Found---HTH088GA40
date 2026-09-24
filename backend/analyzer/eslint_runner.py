"""
ESLint runner for JavaScript and TypeScript files.

Uses `npx eslint` so no global install is required — only Node.js
needs to be present on the machine.

We configure ESLint inline (no config file needed) with rules focused
on security and correctness only.  No formatting / style rules are enabled.

Rules applied
-------------
no-eval                 — security: use of eval()
no-implied-eval         — security: implied eval (setTimeout with string)
no-new-func             — security: Function() constructor as eval
no-script-url           — security: javascript: URL
no-prototype-builtins   — bug: unsafe prototype method calls
no-undef                — bug: undefined variables
no-unused-vars          — bug: variables defined but never used
no-unreachable          — bug: dead code after return/throw
eqeqeq                  — bug: == instead of === (silent coercion bugs)
no-constant-condition   — bug: while(true) / if(true) dead branches
use-isnan               — bug: comparison with NaN (always false)
valid-typeof            — bug: typeof comparisons to invalid strings
"""

import json
import os
import shutil
import subprocess
import tempfile
from typing import List, Tuple

from models.analysis import Finding

# ------------------------------------------------------------------ #
# Locate Node / npx                                                   #
# ------------------------------------------------------------------ #
NPX_EXE: str | None = shutil.which("npx")
NODE_EXE: str | None = shutil.which("node")

# We need at least npx
ESLINT_AVAILABLE: bool = NPX_EXE is not None

# Inline ESLint flat-config (ESLint >= 9 uses flat config by default)
# Rules: security + correctness only.
_ESLINT_FLAT_CONFIG = {
    "rules": {
        # Security
        "no-eval": "error",
        "no-implied-eval": "error",
        "no-new-func": "error",
        "no-script-url": "error",
        # Correctness / bugs
        "no-prototype-builtins": "warn",
        "no-undef": "warn",
        "no-unused-vars": "warn",
        "no-unreachable": "error",
        "eqeqeq": ["warn", "always"],
        "no-constant-condition": "warn",
        "use-isnan": "error",
        "valid-typeof": "error",
    }
}

_ESLINT_SEVERITY_MAP = {
    1: "MEDIUM",  # warn
    2: "HIGH",    # error
}


def _map_severity(eslint_severity: int) -> str:
    return _ESLINT_SEVERITY_MAP.get(eslint_severity, "LOW")


def run_eslint(code: str, filename: str) -> Tuple[List[Finding], List[str]]:
    """
    Run ESLint on the given JavaScript / TypeScript source code.

    A minimal inline flat config is passed via stdin so no project-level
    eslint.config.js is required.

    Returns (findings, errors).
    """
    findings: List[Finding] = []
    errors: List[str] = []

    if not ESLINT_AVAILABLE:
        errors.append(
            "eslint: npx not found - Node.js must be installed to analyse JS/TS files"
        )
        return findings, errors

    ext = ".js"
    lower = filename.lower()
    if lower.endswith(".ts") or lower.endswith(".tsx"):
        ext = ".ts"
    elif lower.endswith(".jsx"):
        ext = ".jsx"

    tmp_code: str | None = None
    tmp_cfg: str | None = None
    try:
        # Write source to temp file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=ext,
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(code)
            tmp_code = f.name

        # Write flat config to temp JS file
        rules_json = json.dumps(_ESLINT_FLAT_CONFIG["rules"], indent=2)
        flat_config_content = (
            "export default [{\n"
            f"  rules: {rules_json}\n"
            "}];\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".mjs",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(flat_config_content)
            tmp_cfg = f.name

        result = subprocess.run(
            [
                NPX_EXE,
                "--yes",
                "eslint",
                "--format", "json",
                "--flag", "unstable_config_lookup_from_file",
                "--config", tmp_cfg,
                tmp_code,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        stdout = result.stdout.strip()
        if not stdout:
            return findings, errors

        # ESLint exits 1 on lint errors — expected
        try:
            raw = json.loads(stdout)
        except json.JSONDecodeError:
            # ESLint sometimes puts warnings before the JSON
            # Try to find the JSON array in the output
            start = stdout.find("[")
            if start != -1:
                raw = json.loads(stdout[start:])
            else:
                errors.append(f"eslint: could not parse JSON output for {filename}")
                return findings, errors

        for file_result in raw:
            for msg in file_result.get("messages", []):
                rule = msg.get("ruleId") or "ESLINT"
                sev = _map_severity(msg.get("severity", 1))
                findings.append(Finding(
                    file=filename,
                    line=msg.get("line", 1),
                    rule_id=rule,
                    tool="eslint",
                    severity=sev,
                    message=msg.get("message", ""),
                ))

    except subprocess.TimeoutExpired:
        errors.append(f"eslint: timed out analysing {filename}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"eslint: unexpected error - {exc}")
    finally:
        for p in (tmp_code, tmp_cfg):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    return findings, errors
