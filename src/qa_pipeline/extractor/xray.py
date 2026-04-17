"""
extractor/xray.py — XrayExtractor (Server/DC) + XrayCloudExtractor.

Extracts from Xray:
  • xray_test            — Test issue metadata
  • xray_test_execution  — Test Execution issues
  • xray_test_run        — Individual test-run results (linked to executions)
  • xray_test_step_result — Step-level results per test run
  • xray_test_set        — Test Set issues
  • xray_precondition    — Precondition issues

Routing:
  xray_variant="server" → Xray Server/DC REST  /rest/raven/2.0/
  xray_variant="cloud"  → Xray Cloud GraphQL   https://xray.cloud.getxray.app/api/v2/graphql
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog

from qa_pipeline.extractor.client import ApiClient
from qa_pipeline.models.extractor import ExtractorConfig, ExtractorResult
from qa_pipeline.models.staging import StagingRecord

log = structlog.get_logger(__name__)

# ── GraphQL queries (Xray Cloud) ───────────────────────────────────────────────

_GQL_TEST_EXECUTIONS = """
query GetTestExecutions($projectKey: String!, $limit: Int!, $start: Int!) {
  getTestExecutions(projectKey: $projectKey, limit: $limit, start: $start) {
    total
    results {
      issueId
      jira(fields: ["key","summary","status","assignee","created","updated",
                    "customfield_10300","customfield_10301","customfield_10302"])
    }
  }
}
"""

_GQL_TEST_RUNS = """
query GetTestRuns($testExecIssueId: String!, $limit: Int!, $start: Int!) {
  getTestRuns(testExecIssueId: $testExecIssueId, limit: $limit, start: $start) {
    total
    results {
      id
      status { name }
      startedOn
      finishedOn
      assignee { accountId displayName }
      comment
      defects { issueId jira(fields: ["key"]) }
      evidence { filename }
      steps {
        id
        status { name }
        comment
        actualResult
        evidence { filename }
      }
      test { issueId jira(fields: ["key","summary","customfield_10100"]) }
    }
  }
}
"""

_GQL_TESTS = """
query GetTests($projectKey: String!, $limit: Int!, $start: Int!) {
  getTests(projectKey: $projectKey, limit: $limit, start: $start) {
    total
    results {
      issueId
      testType { name }
      steps { id action data result }
      gherkin
      unstructured
      jira(fields: ["key","summary","status","assignee","created","updated",
                    "customfield_10101","customfield_10103","customfield_10104"])
    }
  }
}
"""


# ── Server/DC extractor ────────────────────────────────────────────────────────

class XrayServerExtractor:
    """
    Extracts Xray entities from Xray Server / Data Centre via REST.

    Base path: ``/rest/raven/2.0/``
    """

    _BASE = "/rest/raven/2.0"

    def __init__(self, config: ExtractorConfig, run_id: UUID) -> None:
        self._config = config
        self._run_id = run_id
        self._client = ApiClient(
            base_url=config.xray_base_url,
            auth_token=config.auth_token,
            retry_max=config.rate_limit_retry_max,
            backoff_base_ms=config.rate_limit_backoff_base_ms,
            http_proxy=config.http_proxy,
            https_proxy=config.https_proxy,
        )

    def __enter__(self) -> XrayServerExtractor:
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    # ── Tests ──────────────────────────────────────────────────────────────────

    def extract_tests(
        self,
        project_key: str,
        watermark: datetime | None = None,
    ) -> tuple[list[StagingRecord], ExtractorResult]:
        records: list[StagingRecord] = []
        try:
            for page in self._client.paginate_xray_server(
                f"{self._BASE}/test",
                page_size=self._config.max_results_per_page,
                projectKey=project_key,
            ):
                for item in page:
                    records.append(_make_record(self._run_id, item, "xray_test"))

            return records, _ok_result(self._run_id, "xray_tests", records, watermark)
        except Exception as exc:  # noqa: BLE001
            return records, _fail_result(self._run_id, "xray_tests", records, watermark, exc)

    # ── Test Executions ────────────────────────────────────────────────────────

    def extract_test_executions(
        self,
        project_key: str,
        watermark: datetime | None = None,
    ) -> tuple[list[StagingRecord], ExtractorResult]:
        records: list[StagingRecord] = []
        try:
            for page in self._client.paginate_xray_server(
                f"{self._BASE}/testexecution",
                page_size=self._config.max_results_per_page,
                projectKey=project_key,
            ):
                for item in page:
                    records.append(_make_record(self._run_id, item, "xray_test_execution"))

            return records, _ok_result(self._run_id, "xray_test_executions", records, watermark)
        except Exception as exc:  # noqa: BLE001
            return records, _fail_result(self._run_id, "xray_test_executions", records, watermark, exc)

    # ── Test Runs + Step Results ───────────────────────────────────────────────

    def extract_test_runs(
        self,
        execution_key: str,
    ) -> tuple[list[StagingRecord], list[StagingRecord]]:
        """
        Return (test_run_records, step_result_records) for one execution.
        """
        run_records: list[StagingRecord] = []
        step_records: list[StagingRecord] = []

        try:
            for page in self._client.paginate_xray_server(
                f"{self._BASE}/testrun",
                page_size=self._config.max_results_per_page,
                testExecIssueKey=execution_key,
            ):
                for item in page:
                    run_id_key = str(item.get("id", item.get("key", "")))
                    run_records.append(_make_record(self._run_id, item, "xray_test_run"))

                    # Explode step results
                    for step in item.get("steps", []):
                        step_payload = {
                            **step,
                            "_test_run_id": run_id_key,
                            "_execution_key": execution_key,
                        }
                        step_key = f"{run_id_key}:{step.get('id', '')}"
                        step_records.append(
                            StagingRecord(
                                run_id=self._run_id,
                                source_key=step_key,
                                entity_type="xray_test_step_result",
                                raw_json=step_payload,
                            )
                        )
        except Exception as exc:  # noqa: BLE001
            log.error("xray_server.extract_test_runs_failed",
                      execution_key=execution_key, error=str(exc))

        return run_records, step_records

    # ── Test Sets ─────────────────────────────────────────────────────────────

    def extract_test_sets(
        self,
        project_key: str,
    ) -> tuple[list[StagingRecord], ExtractorResult]:
        records: list[StagingRecord] = []
        try:
            for page in self._client.paginate_xray_server(
                f"{self._BASE}/testset",
                page_size=self._config.max_results_per_page,
                projectKey=project_key,
            ):
                for item in page:
                    records.append(_make_record(self._run_id, item, "xray_test_set"))

            return records, _ok_result(self._run_id, "xray_test_sets", records, None)
        except Exception as exc:  # noqa: BLE001
            return records, _fail_result(self._run_id, "xray_test_sets", records, None, exc)

    # ── Preconditions ─────────────────────────────────────────────────────────

    def extract_preconditions(
        self,
        project_key: str,
    ) -> tuple[list[StagingRecord], ExtractorResult]:
        records: list[StagingRecord] = []
        try:
            for page in self._client.paginate_xray_server(
                f"{self._BASE}/precondition",
                page_size=self._config.max_results_per_page,
                projectKey=project_key,
            ):
                for item in page:
                    records.append(_make_record(self._run_id, item, "xray_precondition"))

            return records, _ok_result(self._run_id, "xray_preconditions", records, None)
        except Exception as exc:  # noqa: BLE001
            return records, _fail_result(self._run_id, "xray_preconditions", records, None, exc)


# ── Cloud extractor ────────────────────────────────────────────────────────────

class XrayCloudExtractor:
    """
    Extracts Xray Cloud entities via GraphQL.

    base_url should be ``https://xray.cloud.getxray.app/api/v2``
    """

    def __init__(self, config: ExtractorConfig, run_id: UUID) -> None:
        self._config = config
        self._run_id = run_id
        self._client = ApiClient(
            base_url=config.xray_base_url,
            auth_token=config.auth_token,
            retry_max=config.rate_limit_retry_max,
            backoff_base_ms=config.rate_limit_backoff_base_ms,
            http_proxy=config.http_proxy,
            https_proxy=config.https_proxy,
        )

    def __enter__(self) -> XrayCloudExtractor:
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    def extract_tests(
        self,
        project_key: str,
        watermark: datetime | None = None,
    ) -> tuple[list[StagingRecord], ExtractorResult]:
        records: list[StagingRecord] = []
        try:
            for page in self._client.paginate_xray_cloud_graphql(
                query=_GQL_TESTS,
                variables={"projectKey": project_key},
                results_path=["getTests", "results"],
                page_size=self._config.max_results_per_page,
            ):
                for item in page:
                    key = item.get("issueId", "")
                    records.append(
                        StagingRecord(
                            run_id=self._run_id,
                            source_key=key,
                            entity_type="xray_test",
                            raw_json=item,
                        )
                    )
            return records, _ok_result(self._run_id, "xray_tests", records, watermark)
        except Exception as exc:  # noqa: BLE001
            return records, _fail_result(self._run_id, "xray_tests", records, watermark, exc)

    def extract_test_executions(
        self,
        project_key: str,
        watermark: datetime | None = None,
    ) -> tuple[list[StagingRecord], ExtractorResult]:
        records: list[StagingRecord] = []
        try:
            for page in self._client.paginate_xray_cloud_graphql(
                query=_GQL_TEST_EXECUTIONS,
                variables={"projectKey": project_key},
                results_path=["getTestExecutions", "results"],
                page_size=self._config.max_results_per_page,
            ):
                for item in page:
                    key = item.get("issueId", "")
                    records.append(
                        StagingRecord(
                            run_id=self._run_id,
                            source_key=key,
                            entity_type="xray_test_execution",
                            raw_json=item,
                        )
                    )
            return records, _ok_result(self._run_id, "xray_test_executions", records, watermark)
        except Exception as exc:  # noqa: BLE001
            return records, _fail_result(self._run_id, "xray_test_executions", records, watermark, exc)

    def extract_test_runs(
        self,
        execution_issue_id: str,
    ) -> tuple[list[StagingRecord], list[StagingRecord]]:
        run_records: list[StagingRecord] = []
        step_records: list[StagingRecord] = []

        try:
            for page in self._client.paginate_xray_cloud_graphql(
                query=_GQL_TEST_RUNS,
                variables={"testExecIssueId": execution_issue_id},
                results_path=["getTestRuns", "results"],
                page_size=self._config.max_results_per_page,
            ):
                for item in page:
                    run_id_key = str(item.get("id", ""))
                    run_records.append(
                        StagingRecord(
                            run_id=self._run_id,
                            source_key=run_id_key,
                            entity_type="xray_test_run",
                            raw_json=item,
                        )
                    )
                    for step in item.get("steps", []):
                        step_payload = {
                            **step,
                            "_test_run_id": run_id_key,
                            "_execution_issue_id": execution_issue_id,
                        }
                        step_key = f"{run_id_key}:{step.get('id', '')}"
                        step_records.append(
                            StagingRecord(
                                run_id=self._run_id,
                                source_key=step_key,
                                entity_type="xray_test_step_result",
                                raw_json=step_payload,
                            )
                        )
        except Exception as exc:  # noqa: BLE001
            log.error("xray_cloud.extract_test_runs_failed",
                      execution_issue_id=execution_issue_id, error=str(exc))

        return run_records, step_records


# ── Factory ────────────────────────────────────────────────────────────────────

def build_xray_extractor(
    config: ExtractorConfig,
    run_id: UUID,
) -> XrayServerExtractor | XrayCloudExtractor:
    """Return the correct extractor based on config.xray_variant."""
    if config.xray_variant == "cloud":
        return XrayCloudExtractor(config, run_id)
    return XrayServerExtractor(config, run_id)


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _make_record(
    run_id: UUID,
    item: dict[str, Any],
    entity_type: str,
) -> StagingRecord:
    key = str(item.get("key") or item.get("id") or item.get("issueId") or "")
    return StagingRecord(
        run_id=run_id,
        source_key=key,
        entity_type=entity_type,  # type: ignore[arg-type]
        raw_json=item,
    )


def _ok_result(
    run_id: UUID,
    entity_type: str,
    records: list[StagingRecord],
    watermark: datetime | None,
) -> ExtractorResult:
    return ExtractorResult(
        run_id=run_id,
        run_type="delta" if watermark else "full",
        entity_type=entity_type,
        records_extracted=len(records),
        watermark_before=watermark,
        status="success",
    )


def _fail_result(
    run_id: UUID,
    entity_type: str,
    records: list[StagingRecord],
    watermark: datetime | None,
    exc: Exception,
) -> ExtractorResult:
    log.error(f"xray.extract_failed.{entity_type}", error=str(exc))
    return ExtractorResult(
        run_id=run_id,
        run_type="delta" if watermark else "full",
        entity_type=entity_type,
        records_extracted=len(records),
        watermark_before=watermark,
        status="failed",
        error_message=str(exc),
    )
