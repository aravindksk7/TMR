"""
transformer/transformer.py — Transformer (Staging → Reporting).

Reads raw JSON from stg_* tables in Staging_DB and upserts into the
dimension/fact tables in Reporting_DB.

All writes happen inside a single pyodbc transaction — the whole batch
either succeeds or rolls back atomically.

Supported modes
---------------
incremental  — Only process staging rows loaded after transformer_watermark.
full_refresh — Process all staging rows. dim_date is never truncated.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pyodbc
import structlog

from qa_pipeline.models.transformer import TransformerConfig, TransformerResult, Warning
from qa_pipeline.transformer.cf_mapper import CustomFieldMapper

log = structlog.get_logger(__name__)

# ── SELECT queries against Staging_DB ─────────────────────────────────────────

_SELECT_ISSUES = """
SELECT source_key, raw_json
FROM   {table}
{where}
ORDER BY source_key
"""

# ── MERGE templates for Reporting_DB ──────────────────────────────────────────

_MERGE_DIM_PROGRAM = """
MERGE dim_program AS tgt
USING (VALUES (?, ?)) AS src (program_name, description)
ON tgt.program_name = src.program_name
WHEN NOT MATCHED THEN
    INSERT (program_name, description) VALUES (src.program_name, src.description);
"""

_MERGE_DIM_APPLICATION = """
MERGE dim_application AS tgt
USING (VALUES (?, ?, ?)) AS src (application_name, platform, program_sk)
ON tgt.application_name = src.application_name
WHEN MATCHED THEN
    UPDATE SET platform = src.platform, program_sk = src.program_sk
WHEN NOT MATCHED THEN
    INSERT (application_name, platform, program_sk)
    VALUES (src.application_name, src.platform, src.program_sk);
"""

_MERGE_DIM_SQUAD = """
MERGE dim_squad AS tgt
USING (VALUES (?, ?, ?)) AS src (squad_name, program_sk, application_sk)
ON tgt.squad_name = src.squad_name
WHEN MATCHED THEN
    UPDATE SET program_sk = src.program_sk, application_sk = src.application_sk
WHEN NOT MATCHED THEN
    INSERT (squad_name, program_sk, application_sk)
    VALUES (src.squad_name, src.program_sk, src.application_sk);
"""

_MERGE_DIM_RELEASE = """
MERGE dim_release AS tgt
USING (VALUES (?, ?, ?, ?, ?, ?)) AS src
      (release_name, release_date, release_train,
       planned_start_date, planned_end_date, release_status)
ON tgt.release_name = src.release_name
WHEN MATCHED THEN
    UPDATE SET
        release_date       = COALESCE(src.release_date, tgt.release_date),
        release_train      = COALESCE(src.release_train, tgt.release_train),
        planned_start_date = COALESCE(src.planned_start_date, tgt.planned_start_date),
        planned_end_date   = COALESCE(src.planned_end_date, tgt.planned_end_date),
        release_status     = COALESCE(src.release_status, tgt.release_status),
        is_released        = CASE WHEN src.release_status = 'Released' THEN 1 ELSE tgt.is_released END
WHEN NOT MATCHED THEN
    INSERT (release_name, release_date, release_train,
            planned_start_date, planned_end_date, release_status)
    VALUES (src.release_name, src.release_date, src.release_train,
            src.planned_start_date, src.planned_end_date, src.release_status);
"""

_MERGE_DIM_ENVIRONMENT = """
MERGE dim_environment AS tgt
USING (VALUES (?, ?, ?)) AS src (environment_name, environment_type, criticality)
ON tgt.environment_name = src.environment_name
WHEN MATCHED THEN
    UPDATE SET
        environment_type = COALESCE(src.environment_type, tgt.environment_type),
        criticality      = COALESCE(src.criticality, tgt.criticality)
WHEN NOT MATCHED THEN
    INSERT (environment_name, environment_type, criticality)
    VALUES (src.environment_name, src.environment_type, src.criticality);
"""

_MERGE_DIM_TESTER = """
MERGE dim_tester AS tgt
USING (VALUES (?, ?, ?, ?)) AS src (tester_id, tester_name, email, team_name)
ON tgt.tester_id = src.tester_id
WHEN MATCHED THEN
    UPDATE SET
        tester_name = COALESCE(src.tester_name, tgt.tester_name),
        email       = COALESCE(src.email, tgt.email),
        team_name   = COALESCE(src.team_name, tgt.team_name)
WHEN NOT MATCHED THEN
    INSERT (tester_id, tester_name, email, team_name)
    VALUES (src.tester_id, src.tester_name, src.email, src.team_name);
"""

_MERGE_DIM_ISSUE = """
MERGE dim_issue AS tgt
USING (VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)) AS src
      (issue_key,issue_type,summary,status,priority,
       program_sk,squad_sk,reporter,assignee,
       created_at,updated_at,resolution_date,
       critical_flag,business_area)
ON tgt.issue_key = src.issue_key
WHEN MATCHED THEN
    UPDATE SET issue_type=src.issue_type, summary=src.summary,
               status=src.status, priority=src.priority,
               program_sk=src.program_sk, squad_sk=src.squad_sk,
               reporter=src.reporter, assignee=src.assignee,
               created_at=src.created_at, updated_at=src.updated_at,
               resolution_date=src.resolution_date,
               critical_flag=src.critical_flag,
               business_area=src.business_area
WHEN NOT MATCHED THEN
    INSERT (issue_key,issue_type,summary,status,priority,
            program_sk,squad_sk,reporter,assignee,
            created_at,updated_at,resolution_date,
            critical_flag,business_area)
    VALUES (src.issue_key,src.issue_type,src.summary,src.status,src.priority,
            src.program_sk,src.squad_sk,src.reporter,src.assignee,
            src.created_at,src.updated_at,src.resolution_date,
            src.critical_flag,src.business_area);
"""

_MERGE_DIM_DEFECT = """
MERGE dim_defect AS tgt
USING (VALUES (?,?,?,?,?,?,?,?,?,?,?)) AS src
      (defect_key,summary,status,priority,severity,
       squad_sk,application_sk,reporter,assignee,
       created_at,resolved_at)
ON tgt.defect_key = src.defect_key
WHEN MATCHED THEN
    UPDATE SET summary=src.summary, status=src.status,
               priority=src.priority, severity=src.severity,
               squad_sk=src.squad_sk, application_sk=src.application_sk,
               reporter=src.reporter, assignee=src.assignee,
               created_at=src.created_at, resolved_at=src.resolved_at
WHEN NOT MATCHED THEN
    INSERT (defect_key,summary,status,priority,severity,
            squad_sk,application_sk,reporter,assignee,
            created_at,resolved_at)
    VALUES (src.defect_key,src.summary,src.status,src.priority,src.severity,
            src.squad_sk,src.application_sk,src.reporter,src.assignee,
            src.created_at,src.resolved_at);
"""

_MERGE_DIM_TEST = """
MERGE dim_test AS tgt
USING (VALUES (?,?,?,?,?,?,?,?,?,?,?)) AS src
      (test_key,summary,status,test_type_sk,
       repository_path,gherkin_definition,generic_definition,
       squad_sk,assignee,created_at,updated_at)
ON tgt.test_key = src.test_key
WHEN MATCHED THEN
    UPDATE SET summary=src.summary, status=src.status,
               test_type_sk=src.test_type_sk,
               repository_path=src.repository_path,
               gherkin_definition=src.gherkin_definition,
               generic_definition=src.generic_definition,
               squad_sk=src.squad_sk, assignee=src.assignee,
               created_at=src.created_at, updated_at=src.updated_at
WHEN NOT MATCHED THEN
    INSERT (test_key,summary,status,test_type_sk,
            repository_path,gherkin_definition,generic_definition,
            squad_sk,assignee,created_at,updated_at)
    VALUES (src.test_key,src.summary,src.status,src.test_type_sk,
            src.repository_path,src.gherkin_definition,src.generic_definition,
            src.squad_sk,src.assignee,src.created_at,src.updated_at);
"""

_MERGE_DIM_TEST_EXECUTION = """
MERGE dim_test_execution AS tgt
USING (VALUES (?,?,?,?,?,?,?,?)) AS src
      (execution_key,summary,status,test_plan_key,
       environments_json,revision,assignee,executed_at)
ON tgt.execution_key = src.execution_key
WHEN MATCHED THEN
    UPDATE SET summary=src.summary, status=src.status,
               test_plan_key=src.test_plan_key,
               environments_json=src.environments_json,
               revision=src.revision, assignee=src.assignee,
               executed_at=src.executed_at
WHEN NOT MATCHED THEN
    INSERT (execution_key,summary,status,test_plan_key,
            environments_json,revision,assignee,executed_at)
    VALUES (src.execution_key,src.summary,src.status,src.test_plan_key,
            src.environments_json,src.revision,src.assignee,src.executed_at);
"""

_MERGE_FACT_TEST_RUN = """
MERGE fact_test_run AS tgt
USING (VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)) AS src
      (test_run_id,test_sk,execution_sk,release_sk,
       environment_sk,tester_sk,status_sk,root_cause_sk,date_sk,
       run_status,run_sequence,is_automated,block_reason,
       started_at,finished_at,duration_s,
       executed_by,comment,defect_count)
ON  tgt.test_run_id = src.test_run_id
AND tgt.release_sk  = src.release_sk
WHEN MATCHED THEN
    UPDATE SET test_sk=src.test_sk, execution_sk=src.execution_sk,
               environment_sk=src.environment_sk, tester_sk=src.tester_sk,
               status_sk=src.status_sk, root_cause_sk=src.root_cause_sk,
               date_sk=src.date_sk,
               run_status=src.run_status, run_sequence=src.run_sequence,
               is_automated=src.is_automated, block_reason=src.block_reason,
               started_at=src.started_at, finished_at=src.finished_at,
               duration_s=src.duration_s,
               executed_by=src.executed_by, comment=src.comment,
               defect_count=src.defect_count
WHEN NOT MATCHED THEN
    INSERT (test_run_id,test_sk,execution_sk,release_sk,
            environment_sk,tester_sk,status_sk,root_cause_sk,date_sk,
            run_status,run_sequence,is_automated,block_reason,
            started_at,finished_at,duration_s,
            executed_by,comment,defect_count)
    VALUES (src.test_run_id,src.test_sk,src.execution_sk,src.release_sk,
            src.environment_sk,src.tester_sk,src.status_sk,src.root_cause_sk,src.date_sk,
            src.run_status,src.run_sequence,src.is_automated,src.block_reason,
            src.started_at,src.finished_at,src.duration_s,
            src.executed_by,src.comment,src.defect_count);
"""

_MERGE_FACT_STEP_RESULT = """
MERGE fact_test_step_result AS tgt
USING (VALUES (?,?,?,?,?,?)) AS src
      (step_result_id,test_run_id,step_order,step_status,
       actual_result,comment)
ON tgt.step_result_id = src.step_result_id
WHEN MATCHED THEN
    UPDATE SET step_status=src.step_status,
               actual_result=src.actual_result,
               comment=src.comment
WHEN NOT MATCHED THEN
    INSERT (step_result_id,test_run_id,step_order,step_status,
            actual_result,comment)
    VALUES (src.step_result_id,src.test_run_id,src.step_order,src.step_status,
            src.actual_result,src.comment);
"""

_INSERT_FACT_DEFECT_LINK = """
IF NOT EXISTS (
    SELECT 1 FROM fact_defect_link
    WHERE defect_key = ? AND test_run_id = ? AND release_sk = ?
)
INSERT INTO fact_defect_link (defect_key, defect_sk, test_run_id, release_sk, link_type, open_flag)
VALUES (?, ?, ?, ?, ?, ?);
"""

_LOOKUP_SK = "SELECT {sk_col} FROM {table} WHERE {key_col} = ?"

_UPSERT_CYCLE_SNAPSHOT = """
MERGE fact_cycle_snapshot AS tgt
USING (VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)) AS src
      (snapshot_date_sk,release_sk,squad_sk,
       total_tests,executed_tests,passed_tests,failed_tests,
       blocked_tests,not_run_tests,automated_executions,
       covered_requirements,total_requirements,
       open_critical_defects,avg_duration_s)
ON  tgt.snapshot_date_sk = src.snapshot_date_sk
AND tgt.release_sk       = src.release_sk
AND (tgt.squad_sk = src.squad_sk OR (tgt.squad_sk IS NULL AND src.squad_sk IS NULL))
WHEN MATCHED THEN
    UPDATE SET total_tests=src.total_tests, executed_tests=src.executed_tests,
               passed_tests=src.passed_tests, failed_tests=src.failed_tests,
               blocked_tests=src.blocked_tests, not_run_tests=src.not_run_tests,
               automated_executions=src.automated_executions,
               covered_requirements=src.covered_requirements,
               total_requirements=src.total_requirements,
               open_critical_defects=src.open_critical_defects,
               avg_duration_s=src.avg_duration_s
WHEN NOT MATCHED THEN
    INSERT (snapshot_date_sk,release_sk,squad_sk,
            total_tests,executed_tests,passed_tests,failed_tests,
            blocked_tests,not_run_tests,automated_executions,
            covered_requirements,total_requirements,
            open_critical_defects,avg_duration_s)
    VALUES (src.snapshot_date_sk,src.release_sk,src.squad_sk,
            src.total_tests,src.executed_tests,src.passed_tests,src.failed_tests,
            src.blocked_tests,src.not_run_tests,src.automated_executions,
            src.covered_requirements,src.total_requirements,
            src.open_critical_defects,src.avg_duration_s);
"""


class Transformer:
    """
    Reads from Staging_DB, transforms, and writes to Reporting_DB.

    Parameters
    ----------
    staging_conn:
        Open pyodbc connection to Staging_DB (read-only used here).
    reporting_conn:
        Open pyodbc connection to Reporting_DB (autocommit=False).
    config:
        TransformerConfig (mode, watermark, field-map path).
    """

    def __init__(
        self,
        staging_conn: pyodbc.Connection,
        reporting_conn: pyodbc.Connection,
        config: TransformerConfig,
    ) -> None:
        self._stg = staging_conn
        self._rpt = reporting_conn
        self._cfg = config
        self._mapper = CustomFieldMapper(config.custom_field_map_path)
        self._warnings: list[Warning] = []

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(self) -> TransformerResult:
        result = TransformerResult()
        try:
            rows_p, rows_u = self._run_all()
            result.rows_processed = rows_p
            result.rows_upserted  = rows_u
            result.warnings       = self._warnings
            self._rpt.commit()
            log.info("transformer.committed", rows_processed=rows_p, rows_upserted=rows_u)
        except Exception as exc:  # noqa: BLE001
            self._rpt.rollback()
            log.error("transformer.rolled_back", error=str(exc))
            result.status        = "failed"
            result.error_message = str(exc)
        return result

    # ── Orchestration ──────────────────────────────────────────────────────────

    def _run_all(self) -> tuple[int, int]:
        processed = upserted = 0
        wm = self._cfg.transformer_watermark

        # 1. Jira versions → dim_release (enriches release metadata)
        for key, payload in self._iter_staging("stg_jira_versions", wm):
            self._handle_jira_version(key, payload)
            processed += 1
            upserted  += 1

        # 2. Jira issues → dim_program, dim_application, dim_squad, dim_issue
        for key, payload in self._iter_staging("stg_jira_issues", wm):
            self._handle_jira_issue(key, payload, "jira_issue")
            processed += 1
            upserted  += 1

        # 3. Jira defects → dim_defect
        for key, payload in self._iter_staging("stg_jira_defects", wm):
            self._handle_jira_defect(key, payload)
            processed += 1
            upserted  += 1

        # 4. Xray tests → dim_test
        for key, payload in self._iter_staging("stg_xray_tests", wm):
            self._handle_xray_test(key, payload)
            processed += 1
            upserted  += 1

        # 5. Xray test executions → dim_test_execution + dim_environment
        for key, payload in self._iter_staging("stg_xray_test_executions", wm):
            self._handle_xray_test_execution(key, payload)
            processed += 1
            upserted  += 1

        # 6. Xray test runs → fact_test_run + fact_defect_link
        for key, payload in self._iter_staging("stg_xray_test_runs", wm):
            self._handle_xray_test_run(key, payload)
            processed += 1
            upserted  += 1

        # 7. Step results → fact_test_step_result
        for key, payload in self._iter_staging("stg_xray_test_step_results", wm):
            self._handle_step_result(key, payload)
            processed += 1
            upserted  += 1

        # 8. Build nightly cycle snapshot (always refreshed for today)
        self._build_cycle_snapshot()

        return processed, upserted

    # ── Per-entity handlers ────────────────────────────────────────────────────

    def _handle_jira_version(
        self,
        source_key: str,
        payload: dict[str, Any],
    ) -> None:
        """Map a Jira project version to dim_release with full metadata."""
        name = payload.get("name")
        if not name:
            return

        release_date = _parse_date(payload.get("releaseDate") or payload.get("userReleaseDate"))
        start_date   = _parse_date(payload.get("startDate") or payload.get("userStartDate"))
        status = (
            "Released"    if payload.get("released") else
            "On Hold"     if payload.get("archived") else
            "In Progress" if payload.get("overdue") else
            "Planning"
        )
        self._rpt.execute(
            _MERGE_DIM_RELEASE,
            name,
            release_date,
            payload.get("description"),           # used as release_train if no dedicated field
            start_date,
            release_date,
            status,
        )
        # Back-fill date_sk on dim_release
        if release_date:
            date_sk = _date_to_sk(release_date)
            self._rpt.execute(
                "UPDATE dim_release SET release_date_sk = ? WHERE release_name = ? AND release_date_sk IS NULL",
                date_sk, name,
            )

    def _handle_jira_issue(
        self,
        source_key: str,
        payload: dict[str, Any],
        entity_type: str,
    ) -> None:
        fields = payload.get("fields", {})
        cf = self._mapper.extract(fields, entity_type)

        # Ensure dim_program row exists
        program_name: str | None = cf.get("program_name")
        program_sk: int | None = None
        if program_name:
            self._rpt.execute(_MERGE_DIM_PROGRAM, program_name, None)
            row = self._rpt.execute(
                _LOOKUP_SK.format(sk_col="program_sk", table="dim_program", key_col="program_name"),
                program_name,
            ).fetchone()
            program_sk = row[0] if row else None

        # Ensure dim_application row exists
        application_name: str | None = (
            cf.get("application_name")
            or _first_component(fields.get("components"))
        )
        application_sk: int | None = None
        if application_name:
            platform = cf.get("platform")
            self._rpt.execute(_MERGE_DIM_APPLICATION, application_name, platform, program_sk)
            row = self._rpt.execute(
                _LOOKUP_SK.format(sk_col="application_sk", table="dim_application", key_col="application_name"),
                application_name,
            ).fetchone()
            application_sk = row[0] if row else None

        # Ensure dim_squad row exists
        squad_name: str | None = cf.get("squad_name")
        squad_sk: int | None = None
        if squad_name:
            self._rpt.execute(_MERGE_DIM_SQUAD, squad_name, program_sk, application_sk)
            row = self._rpt.execute(
                _LOOKUP_SK.format(sk_col="squad_sk", table="dim_squad", key_col="squad_name"),
                squad_name,
            ).fetchone()
            squad_sk = row[0] if row else None

        # Derive critical_flag: P0/P1/Highest priority or Critical priority name
        priority_name = (fields.get("priority") or {}).get("name", "")
        critical_flag = 1 if priority_name in {"P0", "P1", "Highest", "Critical"} else 0

        self._rpt.execute(
            _MERGE_DIM_ISSUE,
            source_key,
            fields.get("issuetype", {}).get("name"),
            fields.get("summary"),
            fields.get("status", {}).get("name"),
            priority_name,
            program_sk,
            squad_sk,
            _account(fields.get("reporter")),
            _account(fields.get("assignee")),
            _parse_ts(fields.get("created")),
            _parse_ts(fields.get("updated")),
            _parse_ts(fields.get("resolutiondate")),
            critical_flag,
            cf.get("business_area"),
        )

    def _handle_jira_defect(
        self,
        source_key: str,
        payload: dict[str, Any],
    ) -> None:
        fields = payload.get("fields", {})
        cf = self._mapper.extract(fields, "jira_defect")

        squad_sk       = self._lookup_squad(cf.get("squad_name"))
        application_sk = self._lookup_application(
            cf.get("application_name") or _first_component(fields.get("components"))
        )

        severity = (
            cf.get("severity")
            or _extract_select(fields.get("customfield_10204"))
            or _extract_select(fields.get("customfield_10010"))  # common severity field
        )

        self._rpt.execute(
            _MERGE_DIM_DEFECT,
            source_key,
            fields.get("summary"),
            fields.get("status", {}).get("name"),
            fields.get("priority", {}).get("name"),
            severity,
            squad_sk,
            application_sk,
            _account(fields.get("reporter")),
            _account(fields.get("assignee")),
            _parse_ts(fields.get("created")),
            _parse_ts(fields.get("resolutiondate")),
        )

    def _handle_xray_test(
        self,
        source_key: str,
        payload: dict[str, Any],
    ) -> None:
        # payload may be Xray Server (has "fields" wrapper) or Cloud (flat)
        fields = payload.get("fields", payload)
        cf = self._mapper.extract(fields, "xray_test")

        # test_type from Cloud top-level or custom field
        test_type_name: str | None = (
            _nested_key(payload, ["testType", "name"])
            or cf.get("test_type")
        )
        test_type_sk: int | None = None
        if test_type_name:
            self._rpt.execute(
                "MERGE dim_test_type AS t USING (VALUES(?)) AS s(name) ON t.test_type_name=s.name "
                "WHEN NOT MATCHED THEN INSERT (test_type_name) VALUES (s.name);",
                test_type_name,
            )
            row = self._rpt.execute(
                "SELECT test_type_sk FROM dim_test_type WHERE test_type_name = ?",
                test_type_name,
            ).fetchone()
            test_type_sk = row[0] if row else None

        squad_sk = self._lookup_squad(fields.get("squad_name") or cf.get("squad_name"))

        self._rpt.execute(
            _MERGE_DIM_TEST,
            source_key,
            fields.get("summary"),
            fields.get("status", {}).get("name") if isinstance(fields.get("status"), dict) else fields.get("status"),
            test_type_sk,
            cf.get("test_repository_path"),
            cf.get("gherkin_definition") or payload.get("gherkin"),
            cf.get("generic_definition") or payload.get("unstructured"),
            squad_sk,
            _account(fields.get("assignee")),
            _parse_ts(fields.get("created")),
            _parse_ts(fields.get("updated")),
        )

    def _handle_xray_test_execution(
        self,
        source_key: str,
        payload: dict[str, Any],
    ) -> None:
        fields = payload.get("fields", payload)
        cf = self._mapper.extract(fields, "xray_test_execution")

        environments_raw = cf.get("test_environments") or fields.get("customfield_10300")
        environments_json: str | None = None
        if environments_raw:
            if isinstance(environments_raw, list):
                environments_json = json.dumps(environments_raw)
                # Upsert each environment into dim_environment
                for env in environments_raw:
                    env_name = env if isinstance(env, str) else env.get("name") or env.get("value")
                    if env_name:
                        self._upsert_environment(env_name)
            else:
                environments_json = str(environments_raw)

        self._rpt.execute(
            _MERGE_DIM_TEST_EXECUTION,
            source_key,
            fields.get("summary"),
            fields.get("status", {}).get("name") if isinstance(fields.get("status"), dict) else fields.get("status"),
            cf.get("test_plan_key"),
            environments_json,
            cf.get("revision"),
            _account(fields.get("assignee")),
            _parse_ts(fields.get("updated")),
        )

    def _handle_xray_test_run(
        self,
        source_key: str,
        payload: dict[str, Any],
    ) -> None:
        # Resolve test and execution keys
        test_key = (
            _nested_key(payload, ["test", "jira", "key"])
            or _nested_key(payload, ["test", "key"])
        )
        exec_key = payload.get("_execution_key") or payload.get("_execution_issue_id", "")

        test_sk      = self._lookup_test(test_key)
        execution_sk = self._lookup_execution(exec_key)

        # Tester: upsert dim_tester from assignee object
        tester_obj = payload.get("assignee") or {}
        tester_sk: int | None = None
        if isinstance(tester_obj, dict) and (tester_obj.get("accountId") or tester_obj.get("displayName")):
            tester_id   = tester_obj.get("accountId") or tester_obj.get("displayName", "")
            tester_name = tester_obj.get("displayName")
            email       = tester_obj.get("email") or tester_obj.get("emailAddress")
            team_name   = tester_obj.get("teamName")
            self._rpt.execute(_MERGE_DIM_TESTER, tester_id, tester_name, email, team_name)
            row = self._rpt.execute(
                _LOOKUP_SK.format(sk_col="tester_sk", table="dim_tester", key_col="tester_id"),
                tester_id,
            ).fetchone()
            tester_sk = row[0] if row else None

        # Status normalisation → dim_status
        run_status = (
            (payload.get("status") or {}).get("name")
            if isinstance(payload.get("status"), dict)
            else payload.get("status")
        )
        status_sk: int | None = None
        if run_status:
            row = self._rpt.execute(
                "SELECT status_sk FROM dim_status WHERE status_name = ?", run_status
            ).fetchone()
            if not row:
                # Insert unknown status with fallback category
                self._rpt.execute(
                    "INSERT INTO dim_status (status_name, status_category) VALUES (?, ?)",
                    run_status, "Unknown",
                )
                row = self._rpt.execute(
                    "SELECT status_sk FROM dim_status WHERE status_name = ?", run_status
                ).fetchone()
            status_sk = row[0] if row else None

        # Root cause from custom fields or defect labels
        root_cause_name = _extract_custom_field(payload, "root_cause") or "Not Applicable"
        row = self._rpt.execute(
            "SELECT root_cause_sk FROM dim_root_cause WHERE root_cause_name = ?", root_cause_name
        ).fetchone()
        root_cause_sk = row[0] if row else None

        # is_automated: true if test_type is not Manual
        test_type_name = _nested_key(payload, ["test", "testType", "name"]) or ""
        is_automated = 0 if "manual" in (test_type_name or "").lower() else 1

        # Timestamps and duration
        started_at  = _parse_ts(payload.get("startedOn") or payload.get("started_at"))
        finished_at = _parse_ts(payload.get("finishedOn") or payload.get("finished_at"))
        duration_s: float | None = None
        if started_at and finished_at:
            duration_s = (finished_at - started_at).total_seconds()

        # date_sk from start date for dim_date relationship
        date_sk: int | None = _date_to_sk(started_at.date()) if started_at else None

        # Environment: first entry from execution's environments_json
        environment_sk: int | None = None
        if execution_sk:
            row = self._rpt.execute(
                "SELECT environments_json FROM dim_test_execution WHERE execution_sk = ?",
                execution_sk,
            ).fetchone()
            if row and row[0]:
                try:
                    envs = json.loads(row[0])
                    first_env = (envs[0] if envs else None)
                    if first_env:
                        env_name = first_env if isinstance(first_env, str) else first_env.get("name") or first_env.get("value")
                        if env_name:
                            self._upsert_environment(env_name)
                            env_row = self._rpt.execute(
                                "SELECT environment_sk FROM dim_environment WHERE environment_name = ?",
                                env_name,
                            ).fetchone()
                            environment_sk = env_row[0] if env_row else None
                except (json.JSONDecodeError, TypeError, IndexError):
                    pass

        defect_count = len(payload.get("defects") or [])
        executed_by  = _account(payload.get("assignee"))
        comment      = payload.get("comment")
        block_reason = payload.get("blockReason") or payload.get("block_reason")

        # Fix versions → fan-out one row per release
        fix_versions: list[str] = payload.get("fixVersions") or []
        if not fix_versions:
            # Try test.jira.fixVersions
            test_jira = _nested_dict(payload, ["test", "jira"]) or {}
            fix_versions = [v.get("name") for v in (test_jira.get("fixVersions") or []) if v.get("name")]
        if not fix_versions:
            fix_versions = ["UNVERSIONED"]

        defects = payload.get("defects") or []

        for version in fix_versions:
            release_sk = self._lookup_or_create_release(version)

            self._rpt.execute(
                _MERGE_FACT_TEST_RUN,
                source_key,
                test_sk,
                execution_sk,
                release_sk,
                environment_sk,
                tester_sk,
                status_sk,
                root_cause_sk,
                date_sk,
                run_status,
                1,               # run_sequence (future: derive from repeat runs)
                is_automated,
                block_reason,
                started_at,
                finished_at,
                duration_s,
                executed_by,
                comment,
                defect_count,
            )

            # Populate fact_defect_link for each linked defect
            for defect in defects:
                defect_key = (
                    _nested_key(defect, ["jira", "key"])
                    or defect.get("key")
                    or str(defect.get("issueId", ""))
                )
                if not defect_key:
                    continue
                defect_sk = self._lookup_defect(defect_key)
                # Determine open_flag from defect status if available
                defect_status = _nested_key(defect, ["jira", "status", "name"]) or ""
                open_flag = 0 if defect_status.lower() in {"closed", "done", "resolved", "won't fix"} else 1
                self._rpt.execute(
                    _INSERT_FACT_DEFECT_LINK,
                    defect_key, source_key, release_sk,
                    defect_key, defect_sk, source_key, release_sk, "Caused By", open_flag,
                )

    def _handle_step_result(
        self,
        source_key: str,
        payload: dict[str, Any],
    ) -> None:
        test_run_id = payload.get("_test_run_id", "")
        step_order  = payload.get("index") or payload.get("order") or 0
        step_status = (payload.get("status") or {}).get("name") if isinstance(payload.get("status"), dict) else payload.get("status")

        self._rpt.execute(
            _MERGE_FACT_STEP_RESULT,
            source_key,
            test_run_id,
            step_order,
            step_status,
            payload.get("actualResult") or payload.get("actual_result"),
            payload.get("comment"),
        )

    # ── Cycle snapshot builder ─────────────────────────────────────────────────

    def _build_cycle_snapshot(self) -> None:
        """
        Compute today's aggregated snapshot from fact_test_run +
        fact_requirement_coverage + dim_defect and upsert into
        fact_cycle_snapshot. Runs after all other handlers.
        """
        today = datetime.now(tz=timezone.utc).date()
        today_sk = _date_to_sk(today)

        # Check dim_date has a row for today
        row = self._rpt.execute(
            "SELECT date_sk FROM dim_date WHERE date_sk = ?", today_sk
        ).fetchone()
        if not row:
            log.warning("transformer.snapshot_skipped_no_date_row", date_sk=today_sk)
            return

        snapshot_sql = """
        SELECT
            tr.release_sk,
            t.squad_sk,
            COUNT(*)                                                      AS total_tests,
            SUM(CASE WHEN tr.run_status NOT IN ('TODO','EXECUTING') THEN 1 ELSE 0 END) AS executed_tests,
            SUM(CASE WHEN tr.run_status = 'PASS'    THEN 1 ELSE 0 END)   AS passed_tests,
            SUM(CASE WHEN tr.run_status = 'FAIL'    THEN 1 ELSE 0 END)   AS failed_tests,
            SUM(CASE WHEN tr.run_status = 'BLOCKED' THEN 1 ELSE 0 END)   AS blocked_tests,
            SUM(CASE WHEN tr.run_status = 'TODO'    THEN 1 ELSE 0 END)   AS not_run_tests,
            SUM(CAST(tr.is_automated AS INT))                             AS automated_executions,
            AVG(tr.duration_s)                                            AS avg_duration_s
        FROM fact_test_run tr
        LEFT JOIN dim_test t ON tr.test_sk = t.test_sk
        GROUP BY tr.release_sk, t.squad_sk
        """

        coverage_sql = """
        SELECT
            fc.release_sk,
            i.squad_sk,
            SUM(CAST(fc.is_covered AS INT))  AS covered_requirements,
            COUNT(*)                          AS total_requirements
        FROM fact_requirement_coverage fc
        JOIN dim_issue i ON fc.issue_sk = i.issue_sk
        GROUP BY fc.release_sk, i.squad_sk
        """

        defect_sql = """
        SELECT
            fdl.release_sk,
            d.squad_sk,
            COUNT(DISTINCT fdl.defect_key) AS open_critical_defects
        FROM fact_defect_link fdl
        LEFT JOIN dim_defect d ON fdl.defect_sk = d.defect_sk
        WHERE fdl.open_flag = 1 AND ISNULL(d.critical_flag, 0) = 1
        GROUP BY fdl.release_sk, d.squad_sk
        """

        run_rows     = self._rpt.execute(snapshot_sql).fetchall()
        coverage_map = {(r[0], r[1]): r for r in self._rpt.execute(coverage_sql).fetchall()}
        defect_map   = {(r[0], r[1]): r[2] for r in self._rpt.execute(defect_sql).fetchall()}

        for r in run_rows:
            (release_sk, squad_sk, total, executed, passed, failed,
             blocked, not_run, automated, avg_dur) = r

            cov_key = (release_sk, squad_sk)
            cov = coverage_map.get(cov_key, [None, None, 0, 0])
            covered     = cov[2] if len(cov) > 2 else 0
            total_reqs  = cov[3] if len(cov) > 3 else 0
            open_crit   = defect_map.get(cov_key, 0)

            self._rpt.execute(
                _UPSERT_CYCLE_SNAPSHOT,
                today_sk, release_sk, squad_sk,
                total, executed, passed, failed,
                blocked, not_run, automated,
                covered, total_reqs, open_crit, avg_dur,
            )

        log.info("transformer.cycle_snapshot_built", date_sk=today_sk, rows=len(run_rows))

    # ── Lookup helpers ─────────────────────────────────────────────────────────

    def _lookup_test(self, test_key: str | None) -> int | None:
        if not test_key:
            return None
        row = self._rpt.execute(
            "SELECT test_sk FROM dim_test WHERE test_key = ?", test_key
        ).fetchone()
        return row[0] if row else None

    def _lookup_execution(self, exec_key: str | None) -> int | None:
        if not exec_key:
            return None
        row = self._rpt.execute(
            "SELECT execution_sk FROM dim_test_execution WHERE execution_key = ?", exec_key
        ).fetchone()
        return row[0] if row else None

    def _lookup_squad(self, squad_name: str | None) -> int | None:
        if not squad_name:
            return None
        row = self._rpt.execute(
            "SELECT squad_sk FROM dim_squad WHERE squad_name = ?", squad_name
        ).fetchone()
        return row[0] if row else None

    def _lookup_application(self, application_name: str | None) -> int | None:
        if not application_name:
            return None
        row = self._rpt.execute(
            "SELECT application_sk FROM dim_application WHERE application_name = ?", application_name
        ).fetchone()
        return row[0] if row else None

    def _lookup_defect(self, defect_key: str | None) -> int | None:
        if not defect_key:
            return None
        row = self._rpt.execute(
            "SELECT defect_sk FROM dim_defect WHERE defect_key = ?", defect_key
        ).fetchone()
        return row[0] if row else None

    def _lookup_or_create_release(self, version: str) -> int | None:
        self._rpt.execute(
            "MERGE dim_release AS t USING (VALUES(?)) AS s(release_name) "
            "ON t.release_name = s.release_name "
            "WHEN NOT MATCHED THEN INSERT (release_name) VALUES (s.release_name);",
            version,
        )
        row = self._rpt.execute(
            "SELECT release_sk FROM dim_release WHERE release_name = ?", version
        ).fetchone()
        return row[0] if row else None

    def _upsert_environment(self, env_name: str) -> None:
        self._rpt.execute(_MERGE_DIM_ENVIRONMENT, env_name, None, None)

    # ── Staging cursor ─────────────────────────────────────────────────────────

    def _iter_staging(
        self,
        table: str,
        watermark: datetime | None,
    ):
        """Yield (source_key, parsed_dict) from a staging table."""
        if watermark and self._cfg.mode == "incremental":
            where = f"WHERE loaded_at > '{watermark.isoformat()}'"
        else:
            where = ""

        sql = _SELECT_ISSUES.format(table=table, where=where)
        cursor = self._stg.execute(sql)

        for row in cursor:
            source_key: str = row[0]
            try:
                payload: dict[str, Any] = json.loads(row[1])
            except (json.JSONDecodeError, TypeError) as exc:
                log.warning("transformer.bad_json", table=table, source_key=source_key, error=str(exc))
                continue
            yield source_key, payload


# ── Utility ────────────────────────────────────────────────────────────────────

def _account(value: Any) -> str | None:
    """Extract display name from a Jira user object or plain string."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("displayName") or value.get("accountId")
    return str(value)


def _parse_ts(value: Any) -> datetime | None:
    """Parse an ISO timestamp string; return None on failure."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _parse_date(value: Any):
    """Parse a date string (YYYY-MM-DD) to a Python date; return None on failure."""
    if not value:
        return None
    try:
        from datetime import date
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _date_to_sk(d: Any) -> int | None:
    """Convert a date to an YYYYMMDD integer surrogate key."""
    if d is None:
        return None
    try:
        from datetime import date
        if isinstance(d, datetime):
            d = d.date()
        if isinstance(d, date):
            return int(d.strftime("%Y%m%d"))
    except (ValueError, AttributeError):
        pass
    return None


def _nested_key(payload: dict[str, Any], path: list[str]) -> str | None:
    """Safely walk a nested dict and return the value or None."""
    node: Any = payload
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return str(node) if node is not None else None


def _nested_dict(payload: dict[str, Any], path: list[str]) -> dict | None:
    """Safely walk a nested dict and return the dict node or None."""
    node: Any = payload
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, dict) else None


def _first_component(components: Any) -> str | None:
    """Return the name of the first Jira component, or None."""
    if not components or not isinstance(components, list):
        return None
    first = components[0]
    return first.get("name") if isinstance(first, dict) else str(first)


def _extract_select(field: Any) -> str | None:
    """Extract the value from a Jira select-type custom field object."""
    if field is None:
        return None
    if isinstance(field, dict):
        return field.get("value") or field.get("name")
    return str(field)


def _extract_custom_field(payload: dict[str, Any], logical_name: str) -> str | None:
    """Look for a named custom field in the payload's customFields array (Xray Cloud)."""
    for cf in payload.get("customFields") or []:
        if isinstance(cf, dict) and cf.get("name", "").lower() == logical_name.lower():
            v = cf.get("value")
            return str(v) if v is not None else None
    return None
