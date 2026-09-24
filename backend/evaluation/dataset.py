"""
Stage 5 Evaluation Dataset
===========================
A self-contained, hand-tagged dataset of 2-3 sample code snippets
with known issues used to evaluate precision, recall, and signal ratio.

Each sample contains:
  - name: Human-readable identifier
  - file: Logical filename
  - code: The code being reviewed
  - patch: Unified-diff style patch (simulates Stage 1 output)
  - expected_issues: Ground-truth findings

Each expected issue contains:
  - file: Matches the file field
  - line_approx: Approximate line number (matching uses a +-3 window)
  - category: security | bug | performance | style
  - description: Human description for clarity (not used in matching)
  - rule_hint: Optional rule_id substring hint for matching
"""

from typing import List, Dict, Any

# ---------------------------------------------------------------------------
# Sample 1 — Python file with security vulnerabilities + bugs
# ---------------------------------------------------------------------------
SAMPLE_VULNERABLE_PY = """\
import subprocess
import os

SECRET_TOKEN = "abc123supersecret"  # line 4

def run_cmd(user_input):
    # Direct shell injection risk
    result = subprocess.run(user_input, shell=True)  # line 8
    return result

def process_data(items=[]):           # line 11 — mutable default argument
    for item in items:
        eval(item)                    # line 13 — dangerous eval
    return items

def divide(a, b):
    return a / b                      # line 17 — no zero-division guard

try:
    x = int("bad")
except:                               # line 21 — bare except
    pass
"""

SAMPLE_VULNERABLE_PY_PATCH = "\n".join(
    f"+{line}" for line in SAMPLE_VULNERABLE_PY.splitlines()
)

SAMPLE_VULNERABLE_PY_ISSUES: List[Dict[str, Any]] = [
    {
        "file": "vulnerable.py",
        "line_approx": 4,
        "category": "security",
        "description": "Hardcoded secret token in source code",
        "rule_hint": "B105",
    },
    {
        "file": "vulnerable.py",
        "line_approx": 8,
        "category": "security",
        "description": "subprocess.run with shell=True is a shell injection risk",
        "rule_hint": "B602",
    },
    {
        "file": "vulnerable.py",
        "line_approx": 11,
        "category": "bug",
        "description": "Mutable default argument (list) is shared across calls",
        "rule_hint": "B006",
    },
    {
        "file": "vulnerable.py",
        "line_approx": 13,
        "category": "security",
        "description": "Use of eval() evaluates arbitrary input",
        "rule_hint": "B307",
    },
    {
        "file": "vulnerable.py",
        "line_approx": 21,
        "category": "bug",
        "description": "Bare except clause catches all exceptions silently",
        "rule_hint": "E722",
    },
]

# ---------------------------------------------------------------------------
# Sample 2 — JavaScript file with security + bug
# ---------------------------------------------------------------------------
SAMPLE_VULNERABLE_JS = """\
const express = require('express');
const app = express();

app.get('/exec', (req, res) => {
    const userCode = req.query.code;
    const result = eval(userCode);    // line 6 — eval of user input
    res.send(result);
});

function fetchUser(id) {
    if (id == null) {                 // line 11 — == instead of ===
        return null;
    }
    return users[id];
}
"""

SAMPLE_VULNERABLE_JS_PATCH = "\n".join(
    f"+{line}" for line in SAMPLE_VULNERABLE_JS.splitlines()
)

SAMPLE_VULNERABLE_JS_ISSUES: List[Dict[str, Any]] = [
    {
        "file": "app.js",
        "line_approx": 6,
        "category": "security",
        "description": "eval() used on user-controlled query parameter",
        "rule_hint": "no-eval",
    },
    {
        "file": "app.js",
        "line_approx": 11,
        "category": "bug",
        "description": "Loose equality (==) used instead of strict equality (===)",
        "rule_hint": "eqeqeq",
    },
]

# ---------------------------------------------------------------------------
# Sample 3 — Clean Python file (no expected issues)
# ---------------------------------------------------------------------------
SAMPLE_CLEAN_PY = """\
import logging

logger = logging.getLogger(__name__)

def add(a: int, b: int) -> int:
    \"\"\"Return sum of two integers.\"\"\"
    return a + b

def safe_divide(a: float, b: float) -> float:
    \"\"\"Safely divide a by b, raising ValueError for zero divisor.\"\"\"
    if b == 0:
        raise ValueError("Division by zero")
    return a / b

def greet(name: str) -> str:
    logger.info("Greeting user: %s", name)
    return f"Hello, {name}!"
"""

SAMPLE_CLEAN_PY_PATCH = "\n".join(
    f"+{line}" for line in SAMPLE_CLEAN_PY.splitlines()
)

SAMPLE_CLEAN_PY_ISSUES: List[Dict[str, Any]] = []  # No expected findings

# ---------------------------------------------------------------------------
# Evaluation dataset: list of all samples
# ---------------------------------------------------------------------------
EVAL_SAMPLES: List[Dict[str, Any]] = [
    {
        "name": "vulnerable_python",
        "file": "vulnerable.py",
        "language": "python",
        "code": SAMPLE_VULNERABLE_PY,
        "patch": SAMPLE_VULNERABLE_PY_PATCH,
        "expected_issues": SAMPLE_VULNERABLE_PY_ISSUES,
    },
    {
        "name": "vulnerable_javascript",
        "file": "app.js",
        "language": "javascript",
        "code": SAMPLE_VULNERABLE_JS,
        "patch": SAMPLE_VULNERABLE_JS_PATCH,
        "expected_issues": SAMPLE_VULNERABLE_JS_ISSUES,
    },
    {
        "name": "clean_python",
        "file": "utils.py",
        "language": "python",
        "code": SAMPLE_CLEAN_PY,
        "patch": SAMPLE_CLEAN_PY_PATCH,
        "expected_issues": SAMPLE_CLEAN_PY_ISSUES,
    },
]

# Total expected issues across all samples
ALL_EXPECTED_ISSUES: List[Dict[str, Any]] = [
    dict(issue, file=sample["file"])
    for sample in EVAL_SAMPLES
    for issue in sample["expected_issues"]
]
