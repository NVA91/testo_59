from __future__ import annotations

import json
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _ok(**data: Any) -> Dict[str, Any]:
    return {"status": "ok", **data}


def _err(code: str, message: str, **data: Any) -> Dict[str, Any]:
    payload = {"status": "error", "error": {"code": code, "message": message}}
    if data:
        payload["error"]["details"] = data
    return payload


def _run(tokens: list[str], timeout: int = 10) -> Tuple[int, str, str]:
    """
    Fixed-command runner (shell=False). Intended to be used only with hard-coded command tokens.
    """
    try:
        p = subprocess.run(
            tokens,
            shell=False,
            capture_output=True,
            text=True,
            timeout=max(1, min(int(timeout), 30)),
            env={},  # avoid leaking environment secrets
        )
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except Exception:
        return 125, "", "execution error"


def docker_context_show() -> Dict[str, Any]:
    rc, out, err = _run(["/usr/bin/docker", "context", "show"], timeout=10)
    if rc == 0 and out:
        return _ok(docker_context=out)
    if "No such file" in err or rc == 125:
        return _err("DOCKER_MISSING", "docker not installed or not in /usr/bin/docker")
    return _err("DOCKER_ERROR", "docker context show failed")


def docker_info_parse() -> Dict[str, Any]:
    """
    Uses: docker info --format '{{json .}}'
    Parses key fields: OS, Name, ServerVersion, Driver
    """
    rc, out, err = _run(["/usr/bin/docker", "info", "--format", "{{json .}}"], timeout=10)
    if rc != 0 or not out:
        if "No such file" in err or rc == 125:
            return _err("DOCKER_MISSING", "docker not installed or not in /usr/bin/docker")
        return _err("DOCKER_ERROR", "docker info failed")

    try:
        info = json.loads(out)
        return _ok(
            os=str(info.get("OperatingSystem", "")),
            name=str(info.get("Name", "")),
            docker_version=str(info.get("ServerVersion", "")),
            storage_driver=str(info.get("Driver", "")),
        )
    except Exception:
        return _err("PARSE", "Could not parse docker info output")


def _os_release() -> str:
    p = Path("/etc/os-release")
    if not p.exists():
        return platform.platform()
    data = p.read_text(encoding="utf-8", errors="replace").splitlines()
    kv = {}
    for line in data:
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip().strip('"')
    pretty = kv.get("PRETTY_NAME")
    return pretty or platform.platform()


def _cpu_cores() -> int:
    try:
        return os.cpu_count() or 0
    except Exception:
        return 0


def _ram_gb() -> float:
    """
    Parses /proc/meminfo for MemTotal.
    """
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^MemTotal:\s+(\d+)\s+kB", meminfo, flags=re.MULTILINE)
        if not m:
            return 0.0
        kb = int(m.group(1))
        gb = kb / (1024 * 1024)
        return round(gb, 1)
    except Exception:
        return 0.0


def hostname_check() -> Dict[str, Any]:
    rc1, host, _ = _run(["/bin/hostname"], timeout=5)
    if rc1 != 0 or not host:
        host = ""

    # Use JSON output for robust parsing
    rc2, ip_json, _ = _run(["/usr/sbin/ip", "-j", "a"], timeout=10)
    ip = ""
    if rc2 == 0 and ip_json:
        try:
            arr = json.loads(ip_json)
            # pick first non-loopback IPv4
            for iface in arr:
                if iface.get("ifname") == "lo":
                    continue
                for addr in iface.get("addr_info", []) or []:
                    if addr.get("family") == "inet":
                        candidate = addr.get("local")
                        if candidate and candidate != "127.0.0.1":
                            ip = str(candidate)
                            raise StopIteration
        except StopIteration:
            pass
        except Exception:
            ip = ""

    return _ok(hostname=host, ip=ip)


def proof_vps() -> Dict[str, Any]:
    """
    "Proof it's running on VPS" = gather multiple signals:
      - OS release
      - hostname
      - primary IPv4 (if any)
      - cpu cores
      - RAM
      - docker context + docker info if available
    """
    try:
        os_name = _os_release()
        hc = hostname_check()
        if hc.get("status") != "ok":
            return hc

        ctx = docker_context_show()
        di = docker_info_parse()

        payload: Dict[str, Any] = {
            "os": os_name,
            "hostname": hc.get("hostname", ""),
            "ip": hc.get("ip", ""),
            "cpu_cores": _cpu_cores(),
            "ram_gb": _ram_gb(),
        }

        if ctx.get("status") == "ok":
            payload["docker_context"] = ctx.get("docker_context", "")
        else:
            payload["docker_context"] = ""

        if di.get("status") == "ok":
            payload["docker"] = {
                "os": di.get("os", ""),
                "name": di.get("name", ""),
                "docker_version": di.get("docker_version", ""),
                "storage_driver": di.get("storage_driver", ""),
            }
        else:
            payload["docker"] = {}

        return _ok(**payload)
    except Exception:
        return _err("UNKNOWN", "Unexpected error while collecting VPS proof data")


def run_dev_suite() -> Dict[str, Any]:
    """
    Aggregates:
      - docker_context_show
      - docker_info_parse
      - hostname_check
      - proof_vps
    """
    p = proof_vps()
    if p.get("status") != "ok":
        return p

    # Top-level format like requested
    return _ok(
        docker_context=p.get("docker_context", ""),
        os=p.get("os", ""),
        hostname=p.get("hostname", ""),
        ip=p.get("ip", ""),
        cpu_cores=p.get("cpu_cores", 0),
        ram_gb=p.get("ram_gb", 0.0),
    )
