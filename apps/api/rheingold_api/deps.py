"""Wiring: mart location + read-only DuckDB connections + rate limiter (spec §10).

The mart path comes from env RHEINGOLD_MART (default: <repo>/data/mart/rheingold.duckdb).
Connections are opened read_only and cached per resolved path; each caller gets a
cursor (a cheap child connection) so FastAPI threadpool threads never share one.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
from slowapi import Limiter
from slowapi.util import get_remote_address

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MART = _REPO_ROOT / "data" / "mart" / "rheingold.duckdb"

#: Shared limiter — routes decorate with it, app.py registers the handler.
limiter = Limiter(key_func=get_remote_address)


class MartMissingError(RuntimeError):
    """The DuckDB mart file does not exist — routes map this to 503 + 'make data'."""


def mart_path() -> Path:
    return Path(os.environ.get("RHEINGOLD_MART", str(DEFAULT_MART)))


def mart_dir() -> Path:
    """Directory holding the mart sidecar artifacts (fleet.json.gz, *_meta.json...)."""
    return mart_path().parent


def repo_root() -> Path:
    return _REPO_ROOT


_connections: dict[str, duckdb.DuckDBPyConnection] = {}


def get_conn() -> duckdb.DuckDBPyConnection:
    """Read-only cursor on the mart. Raises MartMissingError when the file is absent."""
    p = mart_path()
    if not p.exists():
        raise MartMissingError(
            f"DuckDB mart not found at {p} — run 'make data' to build it (or set RHEINGOLD_MART)."
        )
    key = str(p.resolve())
    conn = _connections.get(key)
    if conn is None:
        conn = duckdb.connect(key, read_only=True)
        _connections[key] = conn
    return conn.cursor()


def reset_connections() -> None:
    """Close and drop all cached connections (used by tests)."""
    for conn in _connections.values():
        conn.close()
    _connections.clear()
