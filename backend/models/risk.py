from typing import Dict, Any, List, Union
from pydantic import BaseModel, Field


class CategoryBreakdown(BaseModel):
    count: int = Field(default=0, description="Number of findings in this category")
    weight: Union[int, float] = Field(..., description="Weight multiplier for this category")
    score: Union[int, float] = Field(default=0, description="count * weight")


class RiskBreakdown(BaseModel):
    security: CategoryBreakdown
    bug: CategoryBreakdown
    performance: CategoryBreakdown
    style: CategoryBreakdown
    total_risk: Union[int, float] = Field(default=0, description="Sum of all category scores")


class RiskSummary(BaseModel):
    total_risk: Union[int, float]
    breakdown: RiskBreakdown
    top_must_fix: List[Dict[str, Any]]
    ordered_findings: List[Dict[str, Any]]
