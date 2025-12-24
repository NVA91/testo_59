from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


SuiteName = Literal["files", "db", "network", "dev"]
JobState = Literal["queued", "running", "success", "failed"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    timestamp: str


class RunRequest(BaseModel):
    options: Optional[Dict[str, Any]] = None


class RunAcceptedResponse(BaseModel):
    job_id: str
    status: Literal["queued"]
    queued_at: str


class LogEntry(BaseModel):
    timestamp: str
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]
    message: str
    data: Optional[Dict[str, Any]] = None


class JobStatusResponse(BaseModel):
    id: str
    status: JobState
    progress: int = Field(ge=0, le=100)
    logs: List[LogEntry] = Field(default_factory=list)
    result: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("progress")
    @classmethod
    def _progress_int(cls, v: Any) -> int:
        try:
            v2 = int(v)
        except Exception:
            raise ValueError("progress must be an integer")
        if v2 < 0 or v2 > 100:
            raise ValueError("progress must be between 0 and 100")
        return v2


class JobFile(BaseModel):
    """
    Persistent job state stored as JSON on disk.
    """
    id: str
    suite: SuiteName
    status: JobState
    progress: int
    created_at: str
    queued_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    options: Dict[str, Any] = Field(default_factory=dict)
    result: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
