from typing import Optional, Literal
from pydantic import BaseModel, Field


class FixRequest(BaseModel):
    file: str = Field(..., description="File path of the finding", examples=["src/example.py"])
    code: str = Field(..., description="Actual relevant code around the finding", examples=["password = 'secret'"])
    line: int = Field(..., ge=0, description="Line number of the finding", examples=[42])
    category: str = Field(..., description="Category: security, bug, performance, style", examples=["security"])
    source: str = Field(..., description="Finding source: 'static' or 'llm'", examples=["static"])
    rule_id: Optional[str] = Field(None, description="Static analysis rule ID if available", examples=["B105"])
    evidence: str = Field(..., description="Exact code evidence or snippet", examples=["password = 'secret'"])
    explanation: str = Field(..., description="Explanation of why this is a problem", examples=["Possible hardcoded password in source code"])
    suggested_fix: Optional[str] = Field(None, description="Initial suggested remediation if available", examples=["Use os.environ.get('PASSWORD')"])


class FixResponse(BaseModel):
    status: str = Field(..., description="Status of the fix: 'success', 'failed', or 'unavailable'", examples=["success"])
    file: str = Field(..., description="File path of the finding", examples=["src/example.py"])
    original_code: str = Field(..., description="Original code before fix", examples=["password = 'secret'"])
    fixed_code: str = Field(..., description="AI-generated replacement code", examples=["password = os.environ.get('PASSWORD', '')"])
    explanation: str = Field(..., description="Why this fixes the issue", examples=["Replaces hardcoded plaintext secret with environment variable lookup."])
    changes: str = Field(..., description="Summary of changes made", examples=["Replaced string literal with os.environ.get('PASSWORD', '')"])
    confidence: Literal["high", "moderate", "low"] = Field("high", description="Confidence level of the generated fix", examples=["high"])
    provider: Optional[str] = Field("gemini", description="Provider that generated the fix ('gemini', 'groq', 'rule-fallback', 'none')", examples=["gemini"])
