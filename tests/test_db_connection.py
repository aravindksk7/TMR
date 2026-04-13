"""
tests/test_db_connection.py — Unit tests for db/connection.py helpers.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from qa_pipeline.db.connection import (
    finish_run_log,
    get_watermark,
    set_watermark,
    start_run_log,
)


# ── get_watermark ──────────────────────────────────────────────────────────────

class TestGetWatermark:
    def test_returns_none_when_no_row(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        result = get_watermark(conn, "test_job")
        assert result is None

    def test_returns_datetime_with_utc(self):
        naive_dt = datetime(2024, 6, 1, 12, 0, 0)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (naive_dt,)
        result = get_watermark(conn, "test_job")
        assert result is not None
        assert result.tzinfo is not None
        assert result.year == 2024

    def test_preserves_existing_tzinfo(self):
        aware_dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (aware_dt,)
        result = get_watermark(conn, "test_job")
        assert result == aware_dt


# ── set_watermark ──────────────────────────────────────────────────────────────

class TestSetWatermark:
    def test_executes_merge_and_commits(self):
        conn = MagicMock()
        ts = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        set_watermark(conn, "test_job", ts)
        conn.execute.assert_called_once()
        conn.commit.assert_called_once()

    def test_passes_job_name_and_ts(self):
        conn = MagicMock()
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        set_watermark(conn, "my_job", ts)
        call_args = conn.execute.call_args
        assert "my_job" in call_args[0]
        assert ts in call_args[0]


# ── start_run_log ──────────────────────────────────────────────────────────────

class TestStartRunLog:
    def test_returns_uuid(self):
        conn = MagicMock()
        run_id = start_run_log(conn, "full_load")
        assert isinstance(run_id, uuid.UUID)

    def test_commits(self):
        conn = MagicMock()
        start_run_log(conn, "full_load")
        conn.commit.assert_called_once()

    def test_inserts_running_status(self):
        conn = MagicMock()
        start_run_log(conn, "delta")
        sql = conn.execute.call_args[0][0]
        assert "'running'" in sql


# ── finish_run_log ─────────────────────────────────────────────────────────────

class TestFinishRunLog:
    def test_commits_after_update(self):
        conn = MagicMock()
        run_id = uuid.uuid4()
        finish_run_log(conn, run_id, status="success", rows_upserted=42)
        conn.commit.assert_called_once()

    def test_passes_correct_status(self):
        conn = MagicMock()
        run_id = uuid.uuid4()
        finish_run_log(conn, run_id, status="failed", error_message="boom")
        call_args = conn.execute.call_args[0]
        # status is the first parameter after the SQL string
        assert "failed" in call_args

    def test_alert_sent_cast_to_int(self):
        conn = MagicMock()
        run_id = uuid.uuid4()
        finish_run_log(conn, run_id, status="success", alert_sent=True)
        call_args = conn.execute.call_args[0]
        assert 1 in call_args   # int(True) == 1
