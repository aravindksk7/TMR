"""
tests/test_transformer.py — Unit tests for the Transformer.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from qa_pipeline.models.transformer import TransformerConfig
from qa_pipeline.transformer.transformer import Transformer, _account, _parse_ts, _nested_key


# ── Utility function tests ─────────────────────────────────────────────────────

class TestAccount:
    def test_dict_returns_display_name(self):
        assert _account({"displayName": "Alice", "accountId": "001"}) == "Alice"

    def test_dict_falls_back_to_account_id(self):
        assert _account({"accountId": "001"}) == "001"

    def test_string_passthrough(self):
        assert _account("alice@example.com") == "alice@example.com"

    def test_none_returns_none(self):
        assert _account(None) is None


class TestParseTs:
    def test_iso_with_z(self):
        dt = _parse_ts("2024-03-01T12:00:00Z")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.year == 2024

    def test_iso_with_offset(self):
        dt = _parse_ts("2024-03-01T12:00:00+05:30")
        assert dt is not None

    def test_none_input(self):
        assert _parse_ts(None) is None

    def test_empty_string(self):
        assert _parse_ts("") is None

    def test_invalid_string(self):
        assert _parse_ts("not-a-date") is None


class TestNestedKey:
    def test_happy_path(self):
        payload = {"test": {"key": "QA-100"}}
        assert _nested_key(payload, ["test", "key"]) == "QA-100"

    def test_missing_intermediate(self):
        assert _nested_key({}, ["test", "key"]) is None

    def test_none_value(self):
        payload = {"test": {"key": None}}
        assert _nested_key(payload, ["test", "key"]) is None


# ── Transformer integration tests ──────────────────────────────────────────────

def _make_staging_cursor(rows: list[tuple]):
    """Return a mock cursor that yields rows when iterated."""
    cursor = MagicMock()
    cursor.__iter__ = MagicMock(return_value=iter(rows))
    return cursor


@pytest.fixture
def staging_conn(jira_issue_payload):
    """Mock staging connection that returns one jira_issue row."""
    conn = MagicMock()
    row = (
        "QA-1",
        json.dumps(jira_issue_payload),
    )

    def _execute(sql, *args):
        cursor = MagicMock()
        cursor.__iter__ = MagicMock(return_value=iter([row]))
        return cursor

    conn.execute.side_effect = _execute
    return conn


@pytest.fixture
def reporting_conn():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)   # simulate SK lookups returning 1
    conn.execute.return_value = cursor
    return conn


@pytest.fixture
def transformer_config(tmp_path):
    import shutil, os
    src = "config/custom_field_map.json"
    dst = tmp_path / "custom_field_map.json"
    shutil.copy(src, dst)
    return TransformerConfig(
        custom_field_map_path=str(dst),
        mode="incremental",
        transformer_watermark=None,
    )


class TestTransformerRun:
    def test_commits_on_success(self, staging_conn, reporting_conn, transformer_config):
        t = Transformer(staging_conn, reporting_conn, transformer_config)

        # Patch _run_all so we don't need a full DB
        with patch.object(t, "_run_all", return_value=(5, 5)):
            result = t.run()

        assert result.status == "success"
        assert result.rows_processed == 5
        reporting_conn.commit.assert_called_once()
        reporting_conn.rollback.assert_not_called()

    def test_rolls_back_on_error(self, staging_conn, reporting_conn, transformer_config):
        t = Transformer(staging_conn, reporting_conn, transformer_config)

        with patch.object(t, "_run_all", side_effect=RuntimeError("DB error")):
            result = t.run()

        assert result.status == "failed"
        assert "DB error" in result.error_message
        reporting_conn.rollback.assert_called_once()
        reporting_conn.commit.assert_not_called()

    def test_warnings_collected(self, staging_conn, reporting_conn, transformer_config):
        from qa_pipeline.models.transformer import Warning
        t = Transformer(staging_conn, reporting_conn, transformer_config)
        t._warnings.append(Warning(source_key="QA-1", field_id="cf_10200",
                                   message="coerce error"))

        with patch.object(t, "_run_all", return_value=(1, 1)):
            result = t.run()

        assert len(result.warnings) == 1
        assert result.warnings[0].source_key == "QA-1"


class TestIterStaging:
    def test_yields_parsed_dict(self, tmp_path, reporting_conn):
        payload = {"key": "QA-1", "fields": {"summary": "Test"}}
        row = ("QA-1", json.dumps(payload))

        conn = MagicMock()
        cursor = MagicMock()
        cursor.__iter__ = MagicMock(return_value=iter([row]))
        conn.execute.return_value = cursor

        import shutil
        dst = tmp_path / "custom_field_map.json"
        shutil.copy("config/custom_field_map.json", dst)
        cfg = TransformerConfig(custom_field_map_path=str(dst))

        t = Transformer(conn, reporting_conn, cfg)
        items = list(t._iter_staging("stg_jira_issues", watermark=None))
        assert len(items) == 1
        assert items[0][0] == "QA-1"
        assert items[0][1]["key"] == "QA-1"

    def test_skips_invalid_json(self, tmp_path, reporting_conn):
        row = ("QA-1", "NOT JSON {{")

        conn = MagicMock()
        cursor = MagicMock()
        cursor.__iter__ = MagicMock(return_value=iter([row]))
        conn.execute.return_value = cursor

        import shutil
        dst = tmp_path / "custom_field_map.json"
        shutil.copy("config/custom_field_map.json", dst)
        cfg = TransformerConfig(custom_field_map_path=str(dst))

        t = Transformer(conn, reporting_conn, cfg)
        items = list(t._iter_staging("stg_jira_issues", watermark=None))
        assert items == []
