from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional

import requests


def _ok(**data: Any) -> Dict[str, Any]:
    return {"status": "ok", **data}


def _err(code: str, message: str, **data: Any) -> Dict[str, Any]:
    payload = {"status": "error", "error": {"code": code, "message": message}}
    if data:
        payload["error"]["details"] = data
    return payload


_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,63}$")
_IP_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


def _validate_domain(domain: str) -> bool:
    return bool(_DOMAIN_RE.match(domain.strip()))


def _validate_ip(ip: str) -> bool:
    if not _IP_RE.match(ip.strip()):
        return False
    parts = ip.split(".")
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except Exception:
        return False


def _preview(text: str, limit: int = 200) -> str:
    t = (text or "").strip()
    return t[:limit]


def curl_domain(domain: str, timeout: int = 10) -> Dict[str, Any]:
    """
    HTTP GET https://{domain}/ via requests (no shell, no subprocess).
    """
    try:
        if not _validate_domain(domain):
            return _err("VALIDATION", "Invalid domain format", domain=domain)

        timeout_s = max(1, min(int(timeout), 30))
        url = f"https://{domain}/"

        t0 = time.perf_counter()
        r = requests.get(url, timeout=timeout_s, allow_redirects=True)
        dt_ms = int((time.perf_counter() - t0) * 1000)

        return _ok(
            domain=domain,
            response_code=int(r.status_code),
            response_time_ms=dt_ms,
            body_preview=_preview(r.text),
        )
    except requests.Timeout:
        return _err("TIMEOUT", "HTTP request timed out")
    except requests.ConnectionError:
        return _err("CONNECTION", "Could not connect to host")
    except Exception:
        return _err("UNKNOWN", "Unexpected network error")


def curl_ip(ip: str, timeout: int = 10) -> Dict[str, Any]:
    """
    HTTP GET https://{ip}/ via requests.
    Note: HTTPS to raw IP may fail certificate validation. We keep verify=True for security.
    """
    try:
        if not _validate_ip(ip):
            return _err("VALIDATION", "Invalid IPv4 address", ip=ip)

        timeout_s = max(1, min(int(timeout), 30))
        url = f"https://{ip}/"

        t0 = time.perf_counter()
        r = requests.get(url, timeout=timeout_s, allow_redirects=True, verify=True)
        dt_ms = int((time.perf_counter() - t0) * 1000)

        return _ok(
            ip=ip,
            response_code=int(r.status_code),
            response_time_ms=dt_ms,
            body_preview=_preview(r.text),
        )
    except requests.exceptions.SSLError:
        return _err("SSL", "TLS certificate validation failed for IP HTTPS endpoint")
    except requests.Timeout:
        return _err("TIMEOUT", "HTTP request timed out")
    except requests.ConnectionError:
        return _err("CONNECTION", "Could not connect to host")
    except Exception:
        return _err("UNKNOWN", "Unexpected network error")


def validate_host_routing(domain: str, ip: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Sends request to https://{ip}/ but sets Host header to {domain}.
    This validates reverse-proxy routing by Host header.
    Note: TLS SNI will still be for the IP. This often fails TLS verification.
    We keep verify=True; for SNI-correct test you typically need curl --resolve.
    """
    try:
        if not _validate_domain(domain):
            return _err("VALIDATION", "Invalid domain format", domain=domain)
        if not _validate_ip(ip):
            return _err("VALIDATION", "Invalid IPv4 address", ip=ip)

        timeout_s = max(1, min(int(timeout), 30))
        url = f"https://{ip}/"

        headers = {"Host": domain}

        t0 = time.perf_counter()
        r = requests.get(url, headers=headers, timeout=timeout_s, allow_redirects=True, verify=True)
        dt_ms = int((time.perf_counter() - t0) * 1000)

        return _ok(
            domain=domain,
            ip=ip,
            response_code=int(r.status_code),
            response_time_ms=dt_ms,
            body_preview=_preview(r.text),
        )
    except requests.exceptions.SSLError:
        return _err("SSL", "TLS certificate validation failed (SNI mismatch likely)")
    except requests.Timeout:
        return _err("TIMEOUT", "HTTP request timed out")
    except requests.ConnectionError:
        return _err("CONNECTION", "Could not connect to host")
    except Exception:
        return _err("UNKNOWN", "Unexpected network error")


def run_network_suite(domain: str, ip: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Aggregates network checks into one response.
    """
    d = curl_domain(domain, timeout=timeout)
    if d.get("status") != "ok":
        return d

    hr = validate_host_routing(domain, ip, timeout=timeout)
    if hr.get("status") != "ok":
        return hr

    return _ok(
        domain=domain,
        response_code=d["response_code"],
        response_time_ms=d["response_time_ms"],
        body_preview=d["body_preview"],
        host_routing={
            "ip": ip,
            "response_code": hr["response_code"],
            "response_time_ms": hr["response_time_ms"],
        },
    )
