"""
Ruff runner for Python files.

Runs Ruff with security- and correctness-focused rule sets:
  F   — Pyflakes   (undefined names, unused imports, etc.)
  B   — flake8-bugbear (likely bugs, correctness)
  S   — flake8-bandit alias rules inside ruff (security)
  E7  — pycodestyle error subset (bare excepts, syntax)

Style / formatting rules (E1, E2, E3, W, I, N, ANN …) are deliberately
excluded so we only surface real bugs and security issues.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

from models.analysis import Finding

# ------------------------------------------------------------------ #
# Locate ruff                                                         #
# ------------------------------------------------------------------ #
_SCRIPT_DIR = Path(__file__).resolve().parent.parent  # backend/
_VENV_SCRIPTS = _SCRIPT_DIR / "venv" / "Scripts"
_VENV_BIN = _SCRIPT_DIR / "venv" / "bin"

RUFF_EXE: str | None = (
    shutil.which("ruff", path=str(_VENV_SCRIPTS))
    or shutil.which("ruff", path=str(_VENV_BIN))
    or shutil.which("ruff")
)

# Rule sets: bugs + security only; no pure style
_RUFF_SELECT = "F,B,S,E711,E712,E721,E741,ASYNC"

# Map ruff severity field to normalized severity
_RUFF_SEVERITY_MAP = {
    "error": "HIGH",
    "warning": "MEDIUM",
    "information": "LOW",
    "hint": "LOW",
}


def _map_severity(raw: str) -> str:
    return _RUFF_SEVERITY_MAP.get(raw.lower(), "MEDIUM")


def run_ruff(code: str, filename: str) -> Tuple[List[Finding], List[str]]:
    """
    Run Ruff on the given Python source code.

    Returns (findings, errors).
    ``errors`` is a list of non-fatal diagnostic strings (e.g. tool missing).
    """
    findings: List[Finding] = []
    errors: List[str] = []

    if not RUFF_EXE:
        errors.append("ruff: tool not installed or not found on PATH - skipping Python lint")
        return findings, errors

    suffix = ".py"
    if filename and "." in filename:
        suffix = "." + filename.rsplit(".", 1)[-1]

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=suffix,
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        result = subprocess.run(
            [
                RUFF_EXE,
                "check",
                "--output-format", "json",
                "--select", _RUFF_SELECT,
                "--no-cache",
                tmp_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if not result.stdout.strip():
            return findings, errors

        raw = json.loads(result.stdout)
        for item in raw:
            findings.append(Finding(
                file=filename,
                line=item.get("location", {}).get("row", 1),
                rule_id=item.get("code", "RUFF"),
                tool="ruff",
                severity=_map_severity(item.get("severity", "warning")),
                message=item.get("message", ""),
            ))

    except subprocess.TimeoutExpired:
        errors.append(f"ruff: timed out analysing {filename}")
    except json.JSONDecodeError as exc:
        errors.append(f"ruff: could not parse JSON output - {exc}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ruff: unexpected error - {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return findings, errors
