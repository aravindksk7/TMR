"""
tests/test_xray_extractor.py — Unit tests for XrayServerExtractor and build_xray_extractor.
"""
from __future__ import annotations

import base64
import json
import time
import uuid
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from qa_pipeline.extractor.xray import (
    XrayCloudExtractor,
    XrayServerExtractor,
    build_xray_extractor,
)
from qa_pipeline.models.extractor import ExtractorConfig


@pytest.fixture
def run_id():
    return uuid.uuid4()


@pytest.fixture
def server_config():
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


@pytest.fixture
def cloud_config():
    return ExtractorConfig(
        jira_base_url="https://jira.atlassian.net",
        xray_base_url="https://xray.cloud.getxray.app",
        auth_token="Bearer cloud-token",
        xray_variant="cloud",
        project_keys=["QA"],
        max_results_per_page=50,
        rate_limit_retry_max=1,
        rate_limit_backoff_base_ms=10,
    )


class TestBuildXrayExtractor:
    def test_returns_server_extractor_for_server_variant(self, server_config, run_id):
        ext = build_xray_extractor(server_config, run_id)
        assert isinstance(ext, XrayServerExtractor)

    def test_returns_cloud_extractor_for_cloud_variant(self, cloud_config, run_id):
        with patch.object(XrayCloudExtractor, "_authenticate", return_value="mock-token"):
            ext = build_xray_extractor(cloud_config, run_id)
        assert isinstance(ext, XrayCloudExtractor)


class TestXrayServerExtractor:
    @respx.mock
    def test_extract_tests_returns_records(self, server_config, run_id):
        respx.get("https://jira.example.com/rest/raven/2.0/test").mock(
            return_value=httpx.Response(200, json=[
                {"key": "QA-100", "summary": "Login test"},
                {"key": "QA-101", "summary": "Logout test"},
            ])
        )
        with XrayServerExtractor(server_config, run_id) as ext:
            records, result = ext.extract_tests("QA")

        assert result.status == "success"
        assert result.records_extracted == 2
        assert all(r.entity_type == "xray_test" for r in records)

    @respx.mock
    def test_extract_tests_fails_gracefully(self, server_config, run_id):
        respx.get("https://jira.example.com/rest/raven/2.0/test").mock(
            return_value=httpx.Response(500, json={"error": "server error"})
        )
        with XrayServerExtractor(server_config, run_id) as ext:
            records, result = ext.extract_tests("QA")

        assert result.status == "failed"

    @respx.mock
    def test_extract_test_runs_explodes_steps(self, server_config, run_id):
        respx.get("https://jira.example.com/rest/raven/2.0/testrun").mock(
            return_value=httpx.Response(200, json=[
                {
                    "id": "9001",
                    "key": "QA-200",
                    "status": {"name": "PASS"},
                    "steps": [
                        {"id": "s1", "index": 1, "status": {"name": "PASS"}},
                        {"id": "s2", "index": 2, "status": {"name": "PASS"}},
                    ],
                }
            ])
        )
        with XrayServerExtractor(server_config, run_id) as ext:
            run_recs, step_recs = ext.extract_test_runs("QA-200")

        assert len(run_recs) == 1
        assert run_recs[0].entity_type == "xray_test_run"
        assert len(step_recs) == 2
        assert all(r.entity_type == "xray_test_step_result" for r in step_recs)

    @respx.mock
    def test_step_result_source_key_includes_run_id(self, server_config, run_id):
        respx.get("https://jira.example.com/rest/raven/2.0/testrun").mock(
            return_value=httpx.Response(200, json=[
                {
                    "id": "9001",
                    "status": {"name": "FAIL"},
                    "steps": [{"id": "s1", "index": 1, "status": {"name": "FAIL"}}],
                }
            ])
        )
        with XrayServerExtractor(server_config, run_id) as ext:
            _, step_recs = ext.extract_test_runs("QA-200")

        assert "9001" in step_recs[0].source_key
        assert "s1" in step_recs[0].source_key

    @respx.mock
    def test_extract_test_executions(self, server_config, run_id):
        respx.get("https://jira.example.com/rest/raven/2.0/testexecution").mock(
            return_value=httpx.Response(200, json=[
                {"key": "QA-200", "summary": "Sprint 1 Execution"},
            ])
        )
        with XrayServerExtractor(server_config, run_id) as ext:
            records, result = ext.extract_test_executions("QA")

        assert result.status == "success"
        assert records[0].entity_type == "xray_test_execution"

    @respx.mock
    def test_extract_test_sets(self, server_config, run_id):
        respx.get("https://jira.example.com/rest/raven/2.0/testset").mock(
            return_value=httpx.Response(200, json=[{"key": "QA-300"}])
        )
        with XrayServerExtractor(server_config, run_id) as ext:
            records, _ = ext.extract_test_sets("QA")

        assert records[0].entity_type == "xray_test_set"

    @respx.mock
    def test_extract_preconditions(self, server_config, run_id):
        respx.get("https://jira.example.com/rest/raven/2.0/precondition").mock(
            return_value=httpx.Response(200, json=[{"key": "QA-400"}])
        )
        with XrayServerExtractor(server_config, run_id) as ext:
            records, _ = ext.extract_preconditions("QA")

        assert records[0].entity_type == "xray_precondition"


def _make_jwt(exp_offset: int = 3600) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": int(time.time()) + exp_offset}).encode()
    ).decode().rstrip("=")
    return f"header.{payload}.signature"


class TestXrayCloudExtractorTestRuns:
    _GQL_URL = "https://xray.cloud.getxray.app/api/v2/graphql"
    # base_url is https://xray.cloud.getxray.app; client appends /api/v2/graphql

    def _make_extractor(self, cloud_config, run_id):
        with patch.object(XrayCloudExtractor, "_authenticate", return_value=_make_jwt()):
            return XrayCloudExtractor(cloud_config, run_id)

    @respx.mock
    def test_extract_test_runs_returns_run_and_step_records(self, cloud_config, run_id):
        respx.post(self._GQL_URL).mock(
            return_value=httpx.Response(200, json={
                "data": {
                    "getTestRuns": {
                        "total": 1,
                        "results": [
                            {
                                "id": "run-1",
                                "status": {"name": "PASS"},
                                "startedOn": "2024-01-01T10:00:00Z",
                                "finishedOn": "2024-01-01T10:05:00Z",
                                "assigneeId": "user-abc",
                                "comment": None,
                                "defects": [],
                                "evidence": [],
                                "steps": [
                                    {"id": "s1", "status": {"name": "PASS"}, "comment": None,
                                     "actualResult": None, "evidence": []},
                                    {"id": "s2", "status": {"name": "PASS"}, "comment": None,
                                     "actualResult": None, "evidence": []},
                                ],
                                "test": {
                                    "issueId": "12345",
                                    "testType": {"name": "Manual"},
                                    "jira": {"key": "QA-100", "summary": "Login test"},
                                    "customFields": [{"id": "cf1", "name": "Priority", "values": ["High"]}],
                                },
                            }
                        ],
                    }
                }
            })
        )
        ext = self._make_extractor(cloud_config, run_id)
        run_recs, step_recs = ext.extract_test_runs("exec-issue-id-1")

        assert len(run_recs) == 1
        assert run_recs[0].entity_type == "xray_test_run"
        assert run_recs[0].source_key == "run-1"
        assert len(step_recs) == 2
        assert all(r.entity_type == "xray_test_step_result" for r in step_recs)

    @respx.mock
    def test_extract_test_runs_step_source_key_includes_run_id(self, cloud_config, run_id):
        respx.post(self._GQL_URL).mock(
            return_value=httpx.Response(200, json={
                "data": {
                    "getTestRuns": {
                        "total": 1,
                        "results": [
                            {
                                "id": "run-99",
                                "status": {"name": "FAIL"},
                                "assigneeId": None,
                                "comment": None,
                                "defects": [],
                                "evidence": [],
                                "steps": [
                                    {"id": "step-x", "status": {"name": "FAIL"}, "comment": None,
                                     "actualResult": "wrong output", "evidence": []},
                                ],
                                "test": {"issueId": "99999", "testType": {"name": "Manual"},
                                         "jira": {}, "customFields": []},
                            }
                        ],
                    }
                }
            })
        )
        ext = self._make_extractor(cloud_config, run_id)
        _, step_recs = ext.extract_test_runs("exec-issue-id-99")

        assert "run-99" in step_recs[0].source_key
        assert "step-x" in step_recs[0].source_key

    @respx.mock
    def test_extract_test_runs_empty_results(self, cloud_config, run_id):
        respx.post(self._GQL_URL).mock(
            return_value=httpx.Response(200, json={
                "data": {"getTestRuns": {"total": 0, "results": []}}
            })
        )
        ext = self._make_extractor(cloud_config, run_id)
        run_recs, step_recs = ext.extract_test_runs("exec-issue-id-empty")

        assert run_recs == []
        assert step_recs == []

    @respx.mock
    def test_extract_test_runs_api_error_returns_empty(self, cloud_config, run_id):
        respx.post(self._GQL_URL).mock(
            return_value=httpx.Response(500, json={"error": "internal server error"})
        )
        ext = self._make_extractor(cloud_config, run_id)
        run_recs, step_recs = ext.extract_test_runs("exec-issue-id-fail")

        assert run_recs == []
        assert step_recs == []
