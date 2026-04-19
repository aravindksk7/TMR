"""
tests/test_jira_extractor.py — Unit tests for JiraExtractor.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from qa_pipeline.extractor.jira import JiraExtractor, _parse_iso
from qa_pipeline.models.extractor import ExtractorConfig


@pytest.fixture
def run_id():
    return uuid.uuid4()


@pytest.fixture
def config():
    return ExtractorConfig(
        jira_base_url="https://jira.example.com",
        xray_base_url="https://jira.example.com",
        auth_token="Bearer token",
        xray_variant="server",
        project_keys=["QA"],
        max_results_per_page=50,
        rate_limit_retry_max=1,
        rate_limit_backoff_base_ms=10,
    )


class TestExtract:
    @respx.mock
    def test_extracts_issues(self, config, run_id):
        respx.post("https://jira.example.com/rest/api/3/search/jql").mock(
            return_value=httpx.Response(200, json={
                "issues": [
                    {
                        "key": "QA-1",
                        "fields": {
                            "issuetype": {"name": "Story"},
                            "summary": "Login feature",
                            "status": {"name": "In Progress"},
                            "priority": {"name": "High"},
                            "assignee": None,
                            "reporter": None,
                            "created": "2024-01-01T00:00:00.000+0000",
                            "updated": "2024-03-01T00:00:00.000+0000",
                            "resolutiondate": None,
                        },
                    }
                ],
            })
        )
        with JiraExtractor(config, run_id) as ext:
            records, result = ext.extract()

        assert result.status == "success"
        assert result.records_extracted == 1
        assert records[0].source_key == "QA-1"
        assert records[0].entity_type == "jira_issue"

    @respx.mock
    def test_bug_classified_as_defect(self, config, run_id):
        respx.post("https://jira.example.com/rest/api/3/search/jql").mock(
            return_value=httpx.Response(200, json={
                "issues": [
                    {
                        "key": "QA-99",
                        "fields": {
                            "issuetype": {"name": "Bug"},
                            "updated": "2024-03-01T00:00:00.000+0000",
                        },
                    }
                ],
            })
        )
        with JiraExtractor(config, run_id) as ext:
            records, result = ext.extract()

        assert records[0].entity_type == "jira_defect"

    @respx.mock
    def test_returns_failed_result_on_error(self, config, run_id):
        respx.post("https://jira.example.com/rest/api/3/search/jql").mock(
            return_value=httpx.Response(500, json={"error": "server error"})
        )
        with JiraExtractor(config, run_id) as ext:
            records, result = ext.extract()

        assert result.status == "failed"
        assert result.error_message is not None

    def test_jql_with_watermark(self, config, run_id):
        wm = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        with JiraExtractor(config, run_id) as ext:
            jql = ext._build_jql(wm)
        assert '2024-03-01 12:00' in jql
        assert 'updated >' in jql

    def test_jql_without_watermark(self, config, run_id):
        with JiraExtractor(config, run_id) as ext:
            jql = ext._build_jql(None)
        assert 'updated >' not in jql   # watermark filter must be absent
        assert 'project in' in jql


class TestParseIso:
    def test_z_suffix(self):
        dt = _parse_iso("2024-03-01T12:00:00.000Z")
        assert dt.tzinfo is not None

    def test_offset(self):
        dt = _parse_iso("2024-03-01T12:00:00.000+0000")
        assert dt.tzinfo is not None

    def test_preserves_value(self):
        dt = _parse_iso("2024-06-15T09:30:00Z")
        assert dt.year == 2024
        assert dt.month == 6
        assert dt.day == 15
