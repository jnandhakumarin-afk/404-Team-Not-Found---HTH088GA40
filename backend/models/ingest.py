from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class ChangedFile(BaseModel):
    file: str = Field(..., description="File path and name")
    language: str = Field(..., description="Detected programming language")
    status: str = Field(..., description="Status of the change (e.g., modified, added, removed)")
    additions: int = Field(..., description="Number of added lines")
    deletions: int = Field(..., description="Number of deleted lines")
    changed_lines: int = Field(..., description="Total changed lines (additions + deletions)")
    patch: Optional[str] = Field(None, description="Safe diff patch or None")
    truncated: bool = Field(False, description="True if changed lines exceed 500")


class IngestRequest(BaseModel):
    url: str = Field(..., description="Public GitHub Pull Request or Commit URL")


class IngestResponse(BaseModel):
    source_url: str
    repository: str
    source_type: Literal["pull_request", "commit"]
    source_id: str
    files: List[ChangedFile]
    total_files: int
    total_changed_lines: int
    truncated_files: List[str]
