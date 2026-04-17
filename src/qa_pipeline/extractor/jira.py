"""
extractor/jira.py — JiraExtractor.

Extracts Jira issues (stories, epics, defects) via the Jira REST API
(v2 for Server/DC, v3 for Cloud) using JQL with optional watermark filtering.

Produces StagingRecord objects for:
  • jira_issue  — stories, tasks, epics (non-defect issue types)
  • jira_defect — Bug issue types
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

# Issue types treated as defects
_DEFECT_TYPES = frozenset({"Bug", "Defect"})

# Fields requested from Jira (keeps response size bounded)
_ISSUE_FIELDS = (
    "summary,description,status,issuetype,priority,assignee,reporter,"
    "created,updated,resolutiondate,labels,components,fixVersionions,"
    "customfield_10200,customfield_10201,"   # program_name, squad_name
    "parent,subtasks,issuelinks,versions,fixVersions,"
    "customfield_10014"                       # epic link (classic projects)
)


class JiraExtractor:
    """
    Extract Jira issues for the configured project keys.

    Parameters
    ----------
    config:
        Shared ExtractorConfig (base URL, auth token, page size, etc.)
    run_id:
        UUID of the current pipeline run (stamped onto every StagingRecord).
    """

    def __init__(self, config: ExtractorConfig, run_id: UUID) -> None:
        self._config = config
        self._run_id = run_id
        self._client = ApiClient(
            base_url=config.jira_base_url,
            auth_token=config.auth_token,
            retry_max=config.rate_limit_retry_max,
            backoff_base_ms=config.rate_limit_backoff_base_ms,
            http_proxy=config.http_proxy,
            https_proxy=config.https_proxy,
            ssl_ca_bundle=config.ssl_ca_bundle,
        )

    def __enter__(self) -> JiraExtractor:
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    # ── Public API ─────────────────────────────────────────────────────────────

    def extract(
        self,
        watermark: datetime | None = None,
    ) -> tuple[list[StagingRecord], ExtractorResult]:
        """
        Pull all issues for configured project_keys updated after *watermark*.
        Returns (records, result).
        """
        jql = self._build_jql(watermark)
        log.info("jira.extract_start", jql=jql, projects=self._config.project_keys)

        records: list[StagingRecord] = []
        newest_ts: datetime | None = None

        try:
            for page in self._client.paginate_jira_post(
                path="/rest/api/3/search/jql",
                body={
                    "jql": jql,
                    "fields": _ISSUE_FIELDS.split(","),
                },
                results_key="issues",
                page_size=self._config.max_results_per_page,
            ):
                for issue in page:
                    entity_type = (
                        "jira_defect"
                        if issue.get("fields", {}).get("issuetype", {}).get("name") in _DEFECT_TYPES
                        else "jira_issue"
                    )
                    records.append(
                        StagingRecord(
                            run_id=self._run_id,
                            source_key=issue["key"],
                            entity_type=entity_type,
                            raw_json=issue,
                        )
                    )
                    updated_str: str | None = issue.get("fields", {}).get("updated")
                    if updated_str:
                        updated_dt = _parse_iso(updated_str)
                        if newest_ts is None or updated_dt > newest_ts:
                            newest_ts = updated_dt

            log.info("jira.extract_done", records=len(records))
            return records, ExtractorResult(
                run_id=self._run_id,
                run_type="delta" if watermark else "full",
                entity_type="jira_issues",
                records_extracted=len(records),
                watermark_before=watermark,
                watermark_after=newest_ts,
                status="success",
            )

        except Exception as exc:  # noqa: BLE001
            log.error("jira.extract_failed", error=str(exc))
            return records, ExtractorResult(
                run_id=self._run_id,
                run_type="delta" if watermark else "full",
                entity_type="jira_issues",
                records_extracted=len(records),
                watermark_before=watermark,
                watermark_after=newest_ts,
                status="failed",
                error_message=str(exc),
            )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build_jql(self, watermark: datetime | None) -> str:
        parts: list[str] = []

        if self._config.project_keys:
            keys_csv = ", ".join(f'"{k}"' for k in self._config.project_keys)
            parts.append(f"project in ({keys_csv})")

        if watermark:
            # Jira JQL datetime format: "yyyy-MM-dd HH:mm"
            wm_str = watermark.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
            parts.append(f'updated > "{wm_str}"')

        parts.append("ORDER BY updated ASC")
        return " AND ".join(parts[:-1]) + " " + parts[-1] if len(parts) > 1 else parts[-1]


# ── Utility ────────────────────────────────────────────────────────────────────

def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string from the Jira API into an aware datetime."""
    # Python 3.11 fromisoformat handles the Jira 'Z' suffix and offsets
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
