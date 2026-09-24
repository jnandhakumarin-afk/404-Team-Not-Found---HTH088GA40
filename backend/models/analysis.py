from typing import List
from pydantic import BaseModel, Field


class Finding(BaseModel):
    """Normalized static-analysis finding — consistent across all tools."""
    file: str = Field(..., description="Relative file path")
    line: int = Field(..., description="1-based line number of the finding")
    rule_id: str = Field(..., description="Tool-specific rule or check identifier")
    tool: str = Field(..., description="Tool that produced this finding (ruff, bandit, eslint)")
    severity: str = Field(..., description="HIGH, MEDIUM, or LOW")
    message: str = Field(..., description="Human-readable description of the issue")


class AnalyzeFilesRequest(BaseModel):
    """Request body for POST /api/analyze-files.

    Accepts the ``files`` list exactly as returned by POST /api/ingest,
    so Stage 1 output can be piped directly into Stage 2.
    """
    files: List[dict] = Field(
        ...,
        description="List of ChangedFile objects from the /api/ingest response"
    )


class AnalyzeFilesResponse(BaseModel):
    total_findings: int
    findings: List[Finding]
    skipped_files: List[str] = Field(
        default_factory=list,
        description="Files skipped because the language is unsupported"
    )
    tool_errors: List[str] = Field(
        default_factory=list,
        description="Non-fatal tool errors (e.g. tool not installed)"
    )
