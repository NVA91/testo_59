from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


CONFIG_PATH = Path("/app/config.yaml")


class AppMeta(BaseModel):
    name: str = "qa-backend"
    version: str = "1.0"


class PathsConfig(BaseModel):
    base_dir: Path = Path("/app")
    jobs_dir: Path = Path("/app/jobs")
    logs_dir: Path = Path("/app/logs")
    uploads_dir: Path = Path("/app/uploads")

    @field_validator("base_dir", "jobs_dir", "logs_dir", "uploads_dir", mode="before")
    @classmethod
    def _as_path(cls, v: Any) -> Path:
        return v if isinstance(v, Path) else Path(str(v))

    def ensure(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)


class UploadConfig(BaseModel):
    max_bytes: int = Field(default=2_000_000, ge=1)  # 2 MB default
    allowed_ext: Literal[".csv"] = ".csv"


class SubprocessConfig(BaseModel):
    timeout_seconds: int = Field(default=30, ge=1, le=30)


class SuitesConfig(BaseModel):
    """
    Each suite defines a list of commands. Each command is a list of tokens.
    Only these exact token lists are allowed to execute (whitelist).
    """
    files: List[List[str]] = Field(default_factory=list)
    db: List[List[str]] = Field(default_factory=list)
    network: List[List[str]] = Field(default_factory=list)
    dev: List[List[str]] = Field(default_factory=list)


class AppConfig(BaseModel):
    app: AppMeta = Field(default_factory=AppMeta)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    upload: UploadConfig = Field(default_factory=UploadConfig)
    subprocess: SubprocessConfig = Field(default_factory=SubprocessConfig)
    suites: SuitesConfig = Field(default_factory=SuitesConfig)

    @field_validator("suites")
    @classmethod
    def _ensure_minimal_suites(cls, v: SuitesConfig) -> SuitesConfig:
        # If config omitted commands, provide safe, local-only defaults:
        # - No network egress by default.
        if not v.files:
            v.files = [
                ["/bin/ls", "-lah", "/app"],
            ]
        if not v.dev:
            v.dev = [
                ["/usr/bin/python", "--version"],
            ]
        if not v.db:
            # DB suite intentionally local-only placeholder command (no secrets)
            v.db = [
                ["/bin/echo", "db-suite-not-configured"],
            ]
        if not v.network:
            v.network = [
                ["/bin/echo", "network-suite-not-configured"],
            ]
        return v


def load_yaml_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        # Start with defaults if missing; still create dirs.
        return {}
    raw = path.read_text(encoding="utf-8", errors="replace")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError("config.yaml must contain a YAML mapping/object at top level")
    return data


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    data = load_yaml_config(CONFIG_PATH)
    try:
        cfg = AppConfig.model_validate(data)
    except ValidationError as e:
        # Do not leak internal validation details beyond config problem summary.
        raise RuntimeError("Invalid /app/config.yaml configuration") from e

    cfg.paths.ensure()
    return cfg
