"""
tests/conftest.py — Shared fixtures for the QA Pipeline test suite.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock

import pytest

from qa_pipeline.models.extractor import ExtractorConfig
from qa_pipeline.models.staging import StagingRecord
from qa_pipeline.models.transformer import TransformerConfig


# ── ExtractorConfig fixture ────────────────────────────────────────────────────

@pytest.fixture
def ext_config() -> ExtractorConfig:
    return ExtractorConfig(
        jira_base_url="https://jira.example.com",
        xray_base_url="https://jira.example.com",
        auth_token="Bearer test-token",
        xray_variant="server",
        project_keys=["QA", "PROJ"],
        max_results_per_page=50,
        rate_limit_retry_max=2,
        rate_limit_backoff_base_ms=100,
    )


# ── Sample Jira issue payload ──────────────────────────────────────────────────

@pytest.fixture
def jira_issue_payload() -> dict:
    return {
        "key": "QA-1",
        "fields": {
            "summary": "As a user I can log in",
            "issuetype": {"name": "Story"},
            "status":    {"name": "In Progress"},
            "priority":  {"name": "High"},
            "assignee":  {"displayName": "Alice", "accountId": "acc-001"},
            "reporter":  {"displayName": "Bob",   "accountId": "acc-002"},
            "created":   "2024-01-15T09:00:00.000+0000",
            "updated":   "2024-03-01T12:00:00.000+0000",
            "resolutiondate": None,
            "customfield_10200": "Platform",
            "customfield_10201": "Squad A",
            "fixVersions": [{"name": "v1.0"}],
        },
    }


# ── Sample Xray test payload ───────────────────────────────────────────────────

@pytest.fixture
def xray_test_payload() -> dict:
    return {
        "key": "QA-100",
        "fields": {
            "summary": "Login with valid credentials",
            "status":  {"name": "Active"},
            "assignee": {"displayName": "Alice", "accountId": "acc-001"},
            "created":  "2024-01-20T08:00:00.000+0000",
            "updated":  "2024-03-01T10:00:00.000+0000",
            "customfield_10100": {"value": "Manual"},
            "customfield_10101": "/regression/auth",
            "customfield_10102": json.dumps([
                {"index": 1, "step": "Open browser", "data": "", "result": "Browser opens"},
                {"index": 2, "step": "Enter credentials", "data": "user/pass", "result": "Login succeeds"},
            ]),
            "customfield_10103": None,
            "customfield_10104": None,
        },
    }


# ── Sample test run payload ────────────────────────────────────────────────────

@pytest.fixture
def xray_test_run_payload() -> dict:
    return {
        "id": "99001",
        "status": {"name": "PASS"},
        "startedOn":  "2024-03-01T09:00:00Z",
        "finishedOn": "2024-03-01T09:05:30Z",
        "assignee": {"displayName": "Alice"},
        "comment": "All steps passed",
        "defects": [],
        "steps": [
            {"id": "s1", "index": 1, "status": {"name": "PASS"},
             "actualResult": "OK", "comment": ""},
            {"id": "s2", "index": 2, "status": {"name": "PASS"},
             "actualResult": "Logged in", "comment": ""},
        ],
        "test": {"key": "QA-100"},
        "_execution_key": "QA-200",
        "fixVersions": ["v1.0"],
    }


# ── StagingRecord factory ──────────────────────────────────────────────────────

@pytest.fixture
def run_id() -> uuid.UUID:
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def make_staging_record(run_id):
    def _make(source_key: str, entity_type: str, payload: dict) -> StagingRecord:
        return StagingRecord(
            run_id=run_id,
            source_key=source_key,
            entity_type=entity_type,
            raw_json=payload,
        )
    return _make


# ── Mock pyodbc connection ─────────────────────────────────────────────────────

@pytest.fixture
def mock_conn():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fast_executemany = False
    cursor.fetchone.return_value = None
    conn.cursor.return_value = cursor
    conn.execute.return_value = cursor
    return conn


# ── TransformerConfig ──────────────────────────────────────────────────────────

@pytest.fixture
def transformer_config(tmp_path) -> TransformerConfig:
    """TransformerConfig pointing at a temp copy of the real field map."""
    import shutil
    src = "config/custom_field_map.json"
    dst = tmp_path / "custom_field_map.json"
    shutil.copy(src, dst)
    return TransformerConfig(
        custom_field_map_path=str(dst),
        mode="incremental",
        transformer_watermark=None,
    )
