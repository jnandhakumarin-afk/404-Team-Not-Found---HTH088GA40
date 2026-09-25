import os
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock

# Add backend to path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app
from models.fix import FixRequest, FixResponse
from ai.fixer import (
    generate_code_fix,
    build_fix_user_prompt,
    SYSTEM_FIX_PROMPT,
)

client = TestClient(app)


def test_fix_request_response_schema():
    """Verify FixRequest and FixResponse schemas have proper types without additionalProp1."""
    req_schema = FixRequest.model_json_schema()
    assert "file" in req_schema["properties"]
    assert "code" in req_schema["properties"]
    assert "line" in req_schema["properties"]
    assert "category" in req_schema["properties"]
    assert "source" in req_schema["properties"]
    assert "rule_id" in req_schema["properties"]
    assert "evidence" in req_schema["properties"]
    assert "explanation" in req_schema["properties"]
    assert "suggested_fix" in req_schema["properties"]

    resp_schema = FixResponse.model_json_schema()
    assert "status" in resp_schema["properties"]
    assert "original_code" in resp_schema["properties"]
    assert "fixed_code" in resp_schema["properties"]
    assert "explanation" in resp_schema["properties"]
    assert "changes" in resp_schema["properties"]
    assert "confidence" in resp_schema["properties"]


def test_build_fix_user_prompt_static():
    """Static finding prompt must include the static rule_id and exact evidence."""
    req = FixRequest(
        file="src/auth.py",
        code="password = 'admin123'",
        line=15,
        category="security",
        source="static",
        rule_id="B105",
        evidence="password = 'admin123'",
        explanation="Possible hardcoded password.",
        suggested_fix="Use os.environ.get('AUTH_PASSWORD')",
    )
    prompt = build_fix_user_prompt(req)
    assert "B105" in prompt
    assert "src/auth.py" in prompt
    assert "password = 'admin123'" in prompt
    assert "Possible hardcoded password." in prompt


def test_build_fix_user_prompt_llm():
    """LLM finding prompt must include category, explanation, code and evidence."""
    req = FixRequest(
        file="src/calculator.py",
        code="def divide(a, b): return a / b",
        line=8,
        category="bug",
        source="llm",
        rule_id=None,
        evidence="return a / b",
        explanation="ZeroDivisionError occurs if b is 0.",
        suggested_fix="Check if b == 0 before dividing.",
    )
    prompt = build_fix_user_prompt(req)
    assert "src/calculator.py" in prompt
    assert "BUG" in prompt
    assert "ZeroDivisionError" in prompt
    assert "return a / b" in prompt


def test_fix_gemini_success():
    """Gemini generates a successful fix."""
    mock_gemini = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "fixed_code": "password = os.environ.get('APP_PASSWORD', '')",
        "explanation": "Loaded secret from environment instead of hardcoding.",
        "changes": "Replaced hardcoded string literal with os.environ call.",
        "confidence": "high",
    })
    mock_gemini.models.generate_content.return_value = mock_resp

    req = FixRequest(
        file="src/config.py",
        code="password = 'secret'",
        line=10,
        category="security",
        source="static",
        rule_id="B105",
        evidence="password = 'secret'",
        explanation="Hardcoded password detected.",
    )

    result = generate_code_fix(req, gemini_client=mock_gemini)
    assert result.status == "success"
    assert result.provider == "gemini"
    assert "os.environ" in result.fixed_code
    assert result.confidence == "high"


def test_fix_groq_fallback():
    """When Gemini fails, Groq generates the fix."""
    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = RuntimeError("Gemini quota exhausted")

    mock_groq = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = json.dumps({
        "fixed_code": "if b == 0: raise ValueError('Division by zero'); return a / b",
        "explanation": "Guarded against zero division.",
        "changes": "Added boundary zero check.",
        "confidence": "high",
    })
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_groq.chat.completions.create.return_value.choices = [mock_choice]

    req = FixRequest(
        file="src/math_ops.py",
        code="def div(a, b): return a / b",
        line=5,
        category="bug",
        source="llm",
        rule_id=None,
        evidence="return a / b",
        explanation="Zero division potential.",
    )

    result = generate_code_fix(req, gemini_client=mock_gemini, groq_client=mock_groq)
    assert result.status == "success"
    assert result.provider == "groq"
    assert "Division by zero" in result.fixed_code


def test_fix_both_fail_graceful():
    """When both providers fail and no suggestion exists, return unavailable without crashing."""
    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = RuntimeError("Gemini error")

    mock_groq = MagicMock()
    mock_groq.chat.completions.create.side_effect = RuntimeError("Groq error")

    req = FixRequest(
        file="src/db.py",
        code="cursor.execute(f'SELECT * FROM users WHERE id={uid}')",
        line=20,
        category="security",
        source="static",
        rule_id="B608",
        evidence="f'SELECT * FROM users WHERE id={uid}'",
        explanation="SQL injection vulnerability.",
        suggested_fix=None,
    )

    result = generate_code_fix(req, gemini_client=mock_gemini, groq_client=mock_groq)
    assert result.status == "unavailable"
    assert "AI fix unavailable" in result.explanation


def test_fix_rule_fallback_when_suggestion_provided():
    """When both AI providers fail, fall back to the rule-provided remediation if available."""
    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = RuntimeError("Gemini error")

    mock_groq = MagicMock()
    mock_groq.chat.completions.create.side_effect = RuntimeError("Groq error")

    req = FixRequest(
        file="src/db.py",
        code="eval(user_code)",
        line=12,
        category="security",
        source="static",
        rule_id="B307",
        evidence="eval(user_code)",
        explanation="Use of eval detected.",
        suggested_fix="ast.literal_eval(user_code)",
    )

    result = generate_code_fix(req, gemini_client=mock_gemini, groq_client=mock_groq)
    assert result.status == "success"
    assert result.provider == "rule-fallback"
    assert "ast.literal_eval" in result.fixed_code


def test_api_fix_endpoint():
    """Test POST /api/fix via FastAPI TestClient."""
    payload = {
        "file": "src/example.py",
        "code": "eval('2 + 2')",
        "line": 42,
        "category": "security",
        "source": "static",
        "rule_id": "B307",
        "evidence": "eval('2 + 2')",
        "explanation": "Use of dangerous eval() statement.",
        "suggested_fix": "ast.literal_eval('2 + 2')",
    }
    resp = client.post("/api/fix", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "fixed_code" in data
    assert "explanation" in data
    assert "changes" in data
    assert "confidence" in data
    assert data["file"] == "src/example.py"


def test_no_api_key_leaks_in_fix():
    """Verify that credentials are never exposed in responses or errors."""
    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = RuntimeError("Unauthorized AIzaSyDummyKeySecretValue1234567890")

    req = FixRequest(
        file="src/app.py",
        code="x = 1",
        line=1,
        category="bug",
        source="llm",
        rule_id=None,
        evidence="x = 1",
        explanation="Bug",
    )
    result = generate_code_fix(req, gemini_client=mock_gemini)
    assert "AIzaSyDummyKeySecretValue" not in result.explanation
    assert "AIzaSyDummyKeySecretValue" not in result.changes
