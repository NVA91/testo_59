from __future__ import annotations

import os
from pathlib import Path
from typing import List, Sequence, Tuple

from fastapi import HTTPException

from config import AppConfig


def normalize_tokens(tokens: Sequence[str]) -> Tuple[str, ...]:
    return tuple(str(t) for t in tokens)


def is_safe_path(base_dir: Path, target: Path) -> bool:
    try:
        base = base_dir.resolve()
        t = target.resolve()
        return str(t).startswith(str(base) + os.sep) or t == base
    except Exception:
        return False


class WhitelistValidator:
    """
    Strict whitelist:
      - Only exact token lists from config are allowed.
      - No shell, no pipes, no redirects (we never use shell=True anyway).
    """

    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.allowed = {
            "files": {normalize_tokens(cmd) for cmd in cfg.suites.files},
            "db": {normalize_tokens(cmd) for cmd in cfg.suites.db},
            "network": {normalize_tokens(cmd) for cmd in cfg.suites.network},
            "dev": {normalize_tokens(cmd) for cmd in cfg.suites.dev},
        }

    def validate_command(self, suite: str, tokens: List[str]) -> None:
        tok = normalize_tokens(tokens)
        if suite not in self.allowed:
            raise HTTPException(status_code=400, detail="Unknown suite")
        if tok not in self.allowed[suite]:
            raise HTTPException(status_code=403, detail="Command not allowed (whitelist)")

        # Additional hardening: require absolute executable paths
        exe = tokens[0]
        if not exe.startswith("/"):
            raise HTTPException(status_code=403, detail="Executable must be an absolute path")

        # Ensure executable exists and is a file
        p = Path(exe)
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=403, detail="Executable not available on system")
