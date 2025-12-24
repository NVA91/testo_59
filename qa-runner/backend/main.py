from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from config import AppConfig, get_config
from models import (
    HealthResponse,
    JobStatusResponse,
    RunAcceptedResponse,
    RunRequest,
    SuiteName,
)
from utils import JobManager, safe_parse_json_body


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def create_app() -> FastAPI:
    app = FastAPI(title="QA Backend", version="1.0")

    # Minimal, safe defaults (no wildcards by default)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type", "authorization"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception):
        # Never leak secrets or internal details.
        # Log server-side only (stdout); client gets generic message.
        # FastAPI will also log stacktrace depending on uvicorn log level.
        return HTTPException(status_code=500, detail="Internal server error")

    @app.get("/health", response_model=HealthResponse)
    async def health(cfg: AppConfig = Depends(get_config)):
        # No DB calls, no external checks.
        return HealthResponse(status="ok", version=cfg.app.version, timestamp=utc_now_iso())

    @app.post("/run/{suite}", response_model=RunAcceptedResponse, status_code=202)
    async def run_suite(
        suite: SuiteName,
        background: BackgroundTasks,
        request: Request,
        cfg: AppConfig = Depends(get_config),
        # Optional multipart support (file + options_json)
        file: Optional[UploadFile] = File(default=None),
        options_json: Optional[str] = Form(default=None),
    ):
        """
        Supports:
          - application/json: {"options": {...}}
          - multipart/form-data: file=<csv>, options_json='{"options": {...}}'
        """
        jm = JobManager(cfg)

        options: Dict[str, Any] = {}

        content_type = (request.headers.get("content-type") or "").lower()

        if "application/json" in content_type:
            body = await safe_parse_json_body(request)
            rr = RunRequest.model_validate(body)
            options = rr.options or {}
        elif "multipart/form-data" in content_type:
            if options_json:
                rr = RunRequest.model_validate_json(options_json)
                options = rr.options or {}
        else:
            # Allow empty body as well (options optional)
            # but reject unknown content types
            if content_type.strip() not in ("", "application/octet-stream"):
                raise HTTPException(status_code=415, detail="Unsupported Content-Type")

        # Handle optional upload (files suite commonly uses it, but we allow for all suites)
        uploaded_path: Optional[str] = None
        if file is not None:
            uploaded_path = jm.save_uploaded_csv(file)
            options = {**options, "uploaded_csv": uploaded_path}

        job_id = str(uuid.uuid4())
        queued_at = utc_now_iso()

        jm.create_job(job_id=job_id, suite=suite, options=options, queued_at=queued_at)

        # Run in background (in-process). For multi-worker deployments, use a real queue.
        background.add_task(jm.run_job, job_id)

        return RunAcceptedResponse(job_id=job_id, status="queued", queued_at=queued_at)

    @app.get("/jobs/{job_id}", response_model=JobStatusResponse)
    async def get_job(job_id: str, cfg: AppConfig = Depends(get_config)):
        jm = JobManager(cfg)
        job = jm.load_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        # Return parsed logs (last N) + current job state
        return jm.to_job_status_response(job_id)

    @app.get("/logs/{job_id}", response_class=PlainTextResponse)
    async def get_logs(job_id: str, cfg: AppConfig = Depends(get_config)):
        jm = JobManager(cfg)
        log_path = jm.log_path(job_id)
        if not log_path.exists():
            # job might exist but no logs yet; try job existence
            if jm.load_job(job_id) is None:
                raise HTTPException(status_code=404, detail="Job not found")
            return PlainTextResponse("", status_code=200)

        # Raw JSONL text
        return PlainTextResponse(log_path.read_text(encoding="utf-8", errors="replace"))

    return app


app = create_app()
