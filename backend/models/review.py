from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


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
    problem: Optional[str] = Field(
        None, description="Clear statement of what is wrong in the code"
    )
    impact: Optional[str] = Field(
        None, description="Specific impact on the project/application (e.g. security exposure, data loss, crash)"
    )
    why_it_happens: Optional[str] = Field(
        None, description="Technical explanation of why the code causes the problem"
    )
    explanation: str = Field(..., description="Concise explanation of the issue")
    suggested_fix: str = Field(..., description="Actionable fix recommendation with example")
    confidence: Literal["high", "moderate"] = Field(
        ..., description="Confidence level of the finding"
    )

    @model_validator(mode="before")
    @classmethod
    def populate_impact_analysis(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Synchronize problem and explanation
            prob = data.get("problem")
            expl = data.get("explanation")
            if prob and not expl:
                data["explanation"] = prob
            elif expl and not prob:
                data["problem"] = expl
            elif not prob and not expl:
                data["problem"] = "Issue detected in code."
                data["explanation"] = "Issue detected in code."

            cat = str(data.get("category", "bug")).lower().strip()
            rule = data.get("rule_id")

            # Default impact if missing
            if not data.get("impact"):
                if cat == "security":
                    data["impact"] = "Potential security exposure, vulnerability exploitation, or unauthorized execution risk."
                elif cat == "performance":
                    data["impact"] = "Performance degradation, increased latency, or excessive resource consumption."
                elif cat == "style":
                    data["impact"] = "Code readability and maintainability degradation."
                else:
                    data["impact"] = "Unexpected application behavior, runtime exception, or application instability."

            # Default why_it_happens if missing
            if not data.get("why_it_happens"):
                msg = data.get("explanation") or data.get("problem") or ""
                if rule:
                    data["why_it_happens"] = f"Triggered by rule {rule}: {msg}"
                else:
                    data["why_it_happens"] = msg or "Code pattern violates expected safety or correctness constraints."
        return data

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
    model_config = {"extra": "ignore"}

    url: Optional[str] = Field(
        None,
        description="Public GitHub Pull Request or Commit URL",
        examples=["https://github.com/pallets/flask/pull/6162"],
    )
    code: Optional[str] = Field(
        None,
        description="Raw code snippet to review directly",
        examples=["import subprocess\nsubprocess.run(cmd, shell=True)"],
    )
    diff: Optional[str] = Field(
        None,
        description="Unified diff patch to review",
    )
    files: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="List of changed files from Stage 1 ingestion",
    )
    filename: Optional[str] = Field(
        "input.py",
        description="Logical filename when reviewing raw code",
    )
    static_findings: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Pre-computed static analysis findings",
    )
    expected: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Optional custom ground truth issues for evaluation",
    )


class ReviewResponse(BaseModel):
    summary: str
    findings: List[ReviewFinding]
    total_findings: int
    fallback_to_static: bool = False
    errors: List[str] = Field(default_factory=list)
