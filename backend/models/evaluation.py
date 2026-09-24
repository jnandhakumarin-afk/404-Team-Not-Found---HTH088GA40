from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class EvaluationMetrics(BaseModel):
    true_positives: int = Field(default=0, description="Count of correctly detected real issues")
    false_positives: int = Field(default=0, description="Count of detected issues not in ground truth")
    false_negatives: int = Field(default=0, description="Count of ground truth issues missed")
    precision: float = Field(default=0.0, description="TP / (TP + FP)")
    recall: float = Field(default=0.0, description="TP / (TP + FN)")
    actionable_findings: int = Field(default=0, description="Count of actionable real findings")
    total_findings: int = Field(default=0, description="Total findings evaluated")
    signal_ratio: float = Field(default=0.0, description="actionable / total findings")
    signal_ratio_pct: str = Field(default="0.0%", description="Signal ratio as percentage string")


class EvaluationRequest(BaseModel):
    findings: List[Dict[str, Any]] = Field(default_factory=list, description="Findings to evaluate")
    use_dataset: bool = Field(default=True, description="Whether to evaluate against built-in dataset")
    expected: Optional[List[Dict[str, Any]]] = Field(None, description="Optional custom ground truth issues")
