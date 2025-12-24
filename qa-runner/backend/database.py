from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import psycopg2
import psycopg2.extras


def _ok(**data: Any) -> Dict[str, Any]:
    return {"status": "ok", **data}


def _err(code: str, message: str, **data: Any) -> Dict[str, Any]:
    payload = {"status": "error", "error": {"code": code, "message": message}}
    if data:
        payload["error"]["details"] = data
    return payload


@dataclass(frozen=True)
class DBConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str
    connect_timeout: int = 5

    @staticmethod
    def from_env(prefix: str = "QA_DB_") -> "DBConfig":
        # Required (no defaults for secrets)
        host = os.getenv(prefix + "HOST")
        port = os.getenv(prefix + "PORT")
        dbname = os.getenv(prefix + "NAME") or os.getenv(prefix + "DBNAME")
        user = os.getenv(prefix + "USER")
        password = os.getenv(prefix + "PASSWORD")
        cto = os.getenv(prefix + "CONNECT_TIMEOUT")

        missing = [k for k, v in {
            "HOST": host,
            "PORT": port,
            "NAME": dbname,
            "USER": user,
            "PASSWORD": password,
        }.items() if not v]

        if missing:
            raise ValueError(f"Missing DB env vars: {', '.join(prefix + m for m in missing)}")

        try:
            port_i = int(port)  # type: ignore[arg-type]
        except Exception:
            raise ValueError("QA_DB_PORT must be an integer")

        connect_timeout = 5
        if cto:
            try:
                connect_timeout = int(cto)
            except Exception:
                connect_timeout = 5

        return DBConfig(
            host=str(host),
            port=port_i,
            dbname=str(dbname),
            user=str(user),
            password=str(password),
            connect_timeout=max(1, min(connect_timeout, 30)),
        )


def _connect(cfg: DBConfig):
    # Never return password in any error payload
    return psycopg2.connect(
        host=cfg.host,
        port=cfg.port,
        dbname=cfg.dbname,
        user=cfg.user,
        password=cfg.password,
        connect_timeout=cfg.connect_timeout,
        application_name="qa-backend",
    )


def connection_test(cfg: Optional[DBConfig] = None) -> Dict[str, Any]:
    try:
        cfg2 = cfg or DBConfig.from_env()
        t0 = time.perf_counter()
        conn = _connect(cfg2)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        finally:
            conn.close()
        dt_ms = int((time.perf_counter() - t0) * 1000)
        return _ok(connection_time_ms=dt_ms)
    except ValueError as e:
        return _err("CONFIG", str(e))
    except psycopg2.OperationalError:
        return _err("CONNECTION_FAILED", "Could not connect to Postgres (host/port/auth)")
    except Exception:
        return _err("UNKNOWN", "Unexpected DB error")


def postgres_version(cfg: Optional[DBConfig] = None) -> Dict[str, Any]:
    try:
        cfg2 = cfg or DBConfig.from_env()
        conn = _connect(cfg2)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                ver = cur.fetchone()
        finally:
            conn.close()

        version_str = str(ver[0]) if ver and ver[0] else ""
        if not version_str:
            return _err("DB_QUERY", "Empty version() result")
        return _ok(postgres_version=version_str)
    except ValueError as e:
        return _err("CONFIG", str(e))
    except psycopg2.OperationalError:
        return _err("CONNECTION_FAILED", "Could not connect to Postgres (host/port/auth)")
    except Exception:
        return _err("UNKNOWN", "Unexpected DB error")


def count_orders(cfg: Optional[DBConfig] = None, table: str = "public.qa_orders") -> Dict[str, Any]:
    """
    Counts rows in public.qa_orders by default.
    Table name is restricted to safe characters to avoid injection.
    """
    try:
        # Hard safety: allow only [a-zA-Z0-9_ .]
        for ch in table:
            if not (ch.isalnum() or ch in "._"):
                return _err("VALIDATION", "Invalid table name")

        cfg2 = cfg or DBConfig.from_env()
        conn = _connect(cfg2)
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table};")  # table already validated
                n = cur.fetchone()
        finally:
            conn.close()

        count = int(n[0]) if n and n[0] is not None else 0
        return _ok(orders_count=count)
    except ValueError as e:
        return _err("CONFIG", str(e))
    except psycopg2.errors.UndefinedTable:
        return _err("DB_TABLE", "Table does not exist", table=table)
    except psycopg2.OperationalError:
        return _err("CONNECTION_FAILED", "Could not connect to Postgres (host/port/auth)")
    except Exception:
        return _err("UNKNOWN", "Unexpected DB error")


def run_database_suite(cfg: Optional[DBConfig] = None) -> Dict[str, Any]:
    """
    Aggregates DB checks into one structured response.
    """
    ct = connection_test(cfg)
    if ct.get("status") != "ok":
        return ct

    ver = postgres_version(cfg)
    if ver.get("status") != "ok":
        return ver

    cnt = count_orders(cfg)
    if cnt.get("status") != "ok":
        return cnt

    return _ok(
        postgres_version=ver["postgres_version"],
        orders_count=cnt["orders_count"],
        connection_time_ms=ct["connection_time_ms"],
    )
