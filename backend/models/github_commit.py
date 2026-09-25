from pydantic import BaseModel, Field
from typing import Optional


class GitHubCommitRequest(BaseModel):
    url: str = Field(..., description="GitHub PR, commit, or repository URL", examples=["https://github.com/owner/repo/pull/1"])
    file: str = Field(..., description="Relative file path in repository", examples=["backend/ai/reviewer.py"])
    fixed_code: str = Field(..., description="The new replacement code content")
    original_code: Optional[str] = Field(None, description="The original code snippet being replaced")
    line: Optional[int] = Field(None, description="Line number of the issue")
    message: Optional[str] = Field(None, description="Custom commit message")


class GitHubCommitResponse(BaseModel):
    success: bool = Field(..., description="Whether the commit was successfully pushed to GitHub")
    message: str = Field(..., description="Status or result message")
    commit_url: Optional[str] = Field(None, description="Web URL to view the commit on GitHub")
    commit_sha: Optional[str] = Field(None, description="SHA hash of the created commit")
    branch: Optional[str] = Field(None, description="Branch where the commit was pushed")
    error: Optional[str] = Field(None, description="Error detail if commit failed")
