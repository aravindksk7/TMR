"""
db/connection.py — pyodbc connection factory, watermark helpers, and run-log helpers.

All SQL Server interaction goes through this module so the rest of the codebase
never constructs raw connection strings.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import pyodbc
import structlog

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)


# ── Connection factory ─────────────────────────────────────────────────────────

def build_connection(dsn: str) -> pyodbc.Connection:
    """
    Open a pyodbc connection with correct UTF-8 encoding for SQL Server.
    AutoCommit is controlled via the DSN (AutoCommit=True).
    """
    conn = pyodbc.connect(dsn)
    conn.setdecoding(pyodbc.SQL_WCHAR, encoding="utf-8")
    conn.setencoding(encoding="utf-8")
    return conn


# ── Watermark helpers ──────────────────────────────────────────────────────────

_GET_WM = "SELECT last_success_ts FROM pipeline_watermarks WHERE job_name = ?"

_UPSERT_WM = """
MERGE pipeline_watermarks AS tgt
USING (VALUES (?, ?)) AS src (job_name, last_success_ts)
ON tgt.job_name = src.job_name
WHEN MATCHED THEN
    UPDATE SET last_success_ts = src.last_success_ts,
               updated_at      = SYSUTCDATETIME()
WHEN NOT MATCHED THEN
    INSERT (job_name, last_success_ts)
    VALUES (src.job_name, src.last_success_ts);
"""


def get_watermark(conn: pyodbc.Connection, job_name: str) -> datetime | None:
    """Return the last successful watermark for *job_name*, or None if not set."""
    row = conn.execute(_GET_WM, job_name).fetchone()
    if row is None:
        return None
    ts: datetime = row[0]
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts


def set_watermark(conn: pyodbc.Connection, job_name: str, ts: datetime) -> None:
    """Persist *ts* as the new watermark for *job_name* and commit."""
    conn.execute(_UPSERT_WM, job_name, ts)
    conn.commit()
    log.info("watermark.updated", job_name=job_name, ts=ts.isoformat())


# ── Pipeline run-log helpers ───────────────────────────────────────────────────

_INSERT_RUN = """
INSERT INTO pipeline_run_log
    (pipeline_run_id, job_name, status, started_at,
     watermark_before, watermark_after)
VALUES (?, ?, 'running', SYSUTCDATETIME(), ?, ?)
"""

_UPDATE_RUN = """
UPDATE pipeline_run_log
SET    status            = ?,
       finished_at       = SYSUTCDATETIME(),
       records_extracted = ?,
       rows_processed    = ?,
       rows_upserted     = ?,
       watermark_after   = ?,
       error_message     = ?,
       alert_sent        = ?
WHERE  pipeline_run_id   = ?
"""


def start_run_log(
    conn: pyodbc.Connection,
    job_name: str,
    watermark_before: datetime | None = None,
    watermark_after: datetime | None = None,
) -> uuid.UUID:
    """Insert a 'running' row and return the new pipeline_run_id."""
    run_id = uuid.uuid4()
    conn.execute(_INSERT_RUN, str(run_id), job_name, watermark_before, watermark_after)
    conn.commit()
    return run_id


def finish_run_log(
    conn: pyodbc.Connection,
    run_id: uuid.UUID,
    *,
    status: str,
    records_extracted: int = 0,
    rows_processed: int = 0,
    rows_upserted: int = 0,
    watermark_after: datetime | None = None,
    error_message: str | None = None,
    alert_sent: bool = False,
) -> None:
    """Update an existing run-log row to its final state."""
    conn.execute(
        _UPDATE_RUN,
        status,
        records_extracted,
        rows_processed,
        rows_upserted,
        watermark_after,
        error_message,
        int(alert_sent),
        str(run_id),
    )
    conn.commit()
