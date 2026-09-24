"""
Bandit runner for Python files.

Bandit focuses specifically on security vulnerabilities in Python code.
We run it with HIGH + MEDIUM confidence filters so we don't surface
low-value noise.
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
# Locate bandit                                                       #
# ------------------------------------------------------------------ #
_SCRIPT_DIR = Path(__file__).resolve().parent.parent  # backend/
_VENV_SCRIPTS = _SCRIPT_DIR / "venv" / "Scripts"
_VENV_BIN = _SCRIPT_DIR / "venv" / "bin"

BANDIT_EXE: str | None = (
    shutil.which("bandit", path=str(_VENV_SCRIPTS))
    or shutil.which("bandit", path=str(_VENV_BIN))
    or shutil.which("bandit")
)

# Map bandit severity strings to normalized severity
_BANDIT_SEVERITY_MAP = {
    "HIGH": "HIGH",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
}
_BANDIT_CONFIDENCE_KEEP = {"HIGH", "MEDIUM"}


def _map_severity(raw: str) -> str:
    return _BANDIT_SEVERITY_MAP.get(raw.upper(), "MEDIUM")


def run_bandit(code: str, filename: str) -> Tuple[List[Finding], List[str]]:
    """
    Run Bandit on the given Python source code.

    Only issues with MEDIUM or HIGH confidence are reported.
    Returns (findings, errors).
    """
    findings: List[Finding] = []
    errors: List[str] = []

    if not BANDIT_EXE:
        errors.append("bandit: tool not installed or not found on PATH - skipping Python security scan")
        return findings, errors

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        result = subprocess.run(
            [
                BANDIT_EXE,
                "-f", "json",
                "-q",           # quiet — no progress bars
                tmp_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Bandit exits 1 when it finds issues — that is expected and NOT an error
        stdout = result.stdout.strip()
        if not stdout:
            return findings, errors

        raw = json.loads(stdout)
        for item in raw.get("results", []):
            confidence = item.get("issue_confidence", "LOW").upper()
            if confidence not in _BANDIT_CONFIDENCE_KEEP:
                continue

            findings.append(Finding(
                file=filename,
                line=item.get("line_number", 1),
                rule_id=item.get("test_id", "BANDIT"),
                tool="bandit",
                severity=_map_severity(item.get("issue_severity", "MEDIUM")),
                message=item.get("issue_text", ""),
            ))

    except subprocess.TimeoutExpired:
        errors.append(f"bandit: timed out analysing {filename}")
    except json.JSONDecodeError as exc:
        errors.append(f"bandit: could not parse JSON output - {exc}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"bandit: unexpected error - {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return findings, errors
