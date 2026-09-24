from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator


class ReviewFinding(BaseModel):
    file: str = Field(..., description="File path of the finding")
    line: int = Field(..., ge=0, description="Line number of the finding")
    category: Literal["security", "bug", "performance", "style"] = Field(
        ..., description="Category of the issue"
    )
    source: Literal["static", "llm"] = Field(
        ..., description="Origin of finding: 'static' for analyzer tools, 'llm' for AI"
    )
    rule_id: Optional[str] = Field(
        None, description="Original static rule ID if source='static', null if source='llm'"
    )
    evidence: str = Field(..., description="Exact quoted code snippet or evidence")
    explanation: str = Field(..., description="Concise explanation of the issue")
    suggested_fix: str = Field(..., description="Actionable fix recommendation")
    confidence: Literal["high", "moderate"] = Field(
        ..., description="Confidence level of the finding"
    )

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, v: Any) -> str:
        if isinstance(v, str):
            v_lower = v.lower().strip()
            if v_lower in ("static", "llm"):
                return v_lower
        return v

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v: Any) -> str:
        if isinstance(v, str):
            v_lower = v.lower().strip()
            if v_lower in ("security", "bug", "performance", "style"):
                return v_lower
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, v: Any) -> str:
        if isinstance(v, str):
            v_lower = v.lower().strip()
            if v_lower in ("high", "moderate"):
                return v_lower
            if v_lower in ("critical", "medium"):
                return "high" if v_lower == "critical" else "moderate"
        return v

    @field_validator("rule_id", mode="before")
    @classmethod
    def clean_rule_id(cls, v: Any) -> Optional[str]:
        if v is None or v == "" or v == "null" or v == "None":
            return None
        return str(v).strip()


class LLMReviewPayload(BaseModel):
    summary: str = Field(default="Code review completed.", description="Review summary")
    findings: List[ReviewFinding] = Field(default_factory=list, description="List of findings")


class ReviewRequest(BaseModel):
    code: Optional[str] = None
    diff: Optional[str] = None
    filename: Optional[str] = "input.py"
    files: Optional[List[Dict[str, Any]]] = None
    static_findings: Optional[List[Dict[str, Any]]] = None
    url: Optional[str] = None


class ReviewResponse(BaseModel):
    summary: str
    findings: List[ReviewFinding]
    total_findings: int
    fallback_to_static: bool = False
    errors: List[str] = Field(default_factory=list)
