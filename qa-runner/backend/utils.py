from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, Request, UploadFile
from pydantic import ValidationError

from config import AppConfig
from models import JobFile, JobStatusResponse, LogEntry, SuiteName
from security import WhitelistValidator, is_safe_path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps_safe(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


async def safe_parse_json_body(request: Request) -> Dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")
    return data


class JSONLLogger:
    def __init__(self, path: Path):
        self.path = path

    def log(self, level: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        entry = {
            "timestamp": utc_now_iso(),
            "level": level,
            "message": message,
        }
        if data is not None:
            entry["data"] = data
        line = json_dumps_safe(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


class SubprocessRunner:
    def __init__(self, cfg: AppConfig, validator: WhitelistValidator, logger: JSONLLogger):
        self.cfg = cfg
        self.validator = validator
        self.logger = logger

    def run(self, suite: str, tokens: List[str]) -> Tuple[int, str, str]:
        self.validator.validate_command(suite, tokens)

        timeout = self.cfg.subprocess.timeout_seconds
        self.logger.log("INFO", "Executing command", {"cmd": tokens, "timeout_s": timeout})

        try:
            proc = subprocess.run(
                tokens,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={},  # avoid leaking environment secrets into subprocesses
            )
            out = (proc.stdout or "").strip()
            err = (proc.stderr or "").strip()
            self.logger.log(
                "INFO",
                "Command finished",
                {"returncode": proc.returncode, "stdout_len": len(out), "stderr_len": len(err)},
            )
            return proc.returncode, out, err
        except subprocess.TimeoutExpired:
            self.logger.log("ERROR", "Command timeout", {"cmd": tokens, "timeout_s": timeout})
            return 124, "", f"timeout after {timeout}s"
        except Exception:
            # No sensitive details to client logs; server logs contain generic marker.
            self.logger.log("ERROR", "Command execution error")
            return 125, "", "execution error"


class JobManager:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.validator = WhitelistValidator(cfg)

    def job_path(self, job_id: str) -> Path:
        return self.cfg.paths.jobs_dir / f"{job_id}.json"

    def log_path(self, job_id: str) -> Path:
        return self.cfg.paths.logs_dir / f"{job_id}.log"

    def upload_target_path(self, filename: str) -> Path:
        # Normalize filename: keep only name, prevent traversal.
        safe_name = Path(filename).name
        # Prefix with UUID to avoid collisions
        return self.cfg.paths.uploads_dir / f"{uuid.uuid4()}_{safe_name}"

    def create_job(self, job_id: str, suite: SuiteName, options: Dict[str, Any], queued_at: str) -> None:
        jf = JobFile(
            id=job_id,
            suite=suite,
            status="queued",
            progress=0,
            created_at=utc_now_iso(),
            queued_at=queued_at,
            options=options or {},
            result={},
        )
        self._save_jobfile(jf)
        # Initialize log file
        JSONLLogger(self.log_path(job_id)).log("INFO", "Job queued", {"suite": suite})

    def _save_jobfile(self, jf: JobFile) -> None:
        p = self.job_path(jf.id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(jf.model_dump_json(indent=2), encoding="utf-8")

    def load_job(self, job_id: str) -> Optional[JobFile]:
        p = self.job_path(job_id)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            return JobFile.model_validate(data)
        except Exception:
            # Corrupted job file
            return None

    def save_uploaded_csv(self, file: UploadFile) -> str:
        # Validate extension
        original = file.filename or "upload.csv"
        ext = Path(original).suffix.lower()
        if ext != self.cfg.upload.allowed_ext:
            raise HTTPException(status_code=400, detail="Only .csv uploads are allowed")

        # Enforce size limit by streaming and counting
        max_bytes = self.cfg.upload.max_bytes
        target = self.upload_target_path(original)

        # Ensure target stays under uploads_dir
        if not is_safe_path(self.cfg.paths.uploads_dir, target):
            raise HTTPException(status_code=400, detail="Invalid upload path")

        total = 0
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            with target.open("wb") as out:
                while True:
                    chunk = file.file.read(1024 * 1024)  # 1MB
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        out.close()
                        target.unlink(missing_ok=True)
                        raise HTTPException(status_code=413, detail="Upload too large")
                    out.write(chunk)
        finally:
            try:
                file.file.close()
            except Exception:
                pass

        return str(target)

    def to_job_status_response(self, job_id: str) -> JobStatusResponse:
        jf = self.load_job(job_id)
        if jf is None:
            raise HTTPException(status_code=404, detail="Job not found")

        logs = self.read_logs(job_id, limit=200)
        return JobStatusResponse(
            id=jf.id,
            status=jf.status,
            progress=jf.progress,
            logs=logs,
            result=jf.result or {},
        )

    def read_logs(self, job_id: str, limit: int = 200) -> List[LogEntry]:
        p = self.log_path(job_id)
        if not p.exists():
            return []
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-limit:]
        out: List[LogEntry] = []
        for line in tail:
            try:
                obj = json.loads(line)
                out.append(LogEntry.model_validate(obj))
            except Exception:
                # Ignore malformed lines
                continue
        return out

    def run_job(self, job_id: str) -> None:
        jf = self.load_job(job_id)
        if jf is None:
            return

        logger = JSONLLogger(self.log_path(job_id))
        runner = SubprocessRunner(self.cfg, self.validator, logger)

        jf.status = "running"
        jf.started_at = utc_now_iso()
        jf.progress = 1
        jf.error = None
        self._save_jobfile(jf)
        logger.log("INFO", "Job started", {"suite": jf.suite})

        commands = self._commands_for_suite(jf.suite)
        total = max(len(commands), 1)

        results: List[Dict[str, Any]] = []
        success = True

        for idx, cmd in enumerate(commands, start=1):
            # progress: 1..99 during execution
            jf.progress = min(99, int((idx - 1) / total * 98) + 1)
            self._save_jobfile(jf)

            rc, out, err = runner.run(jf.suite, cmd)
            step = {
                "cmd": cmd,
                "returncode": rc,
                "stdout": out,
                "stderr": err,
            }
            results.append(step)

            if rc != 0:
                success = False
                logger.log("ERROR", "Step failed", {"returncode": rc})
                break

        jf.progress = 100
        jf.finished_at = utc_now_iso()

        jf.result = {
            "suite": jf.suite,
            "steps": results,
        }

        if success:
            jf.status = "success"
            logger.log("INFO", "Job finished successfully")
        else:
            jf.status = "failed"
            # Keep error message generic
            jf.error = "Suite execution failed"
            logger.log("ERROR", "Job finished with failure")

        self._save_jobfile(jf)

    def _commands_for_suite(self, suite: SuiteName) -> List[List[str]]:
        if suite == "files":
            return self.cfg.suites.files
        if suite == "db":
            return self.cfg.suites.db
        if suite == "network":
            return self.cfg.suites.network
        if suite == "dev":
            return self.cfg.suites.dev
        # Should never happen due to typing
        return []
