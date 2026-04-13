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

_MERGE_DIM_SQUAD = """
MERGE dim_squad AS tgt
USING (VALUES (?, ?)) AS src (squad_name, program_sk)
ON tgt.squad_name = src.squad_name
WHEN MATCHED THEN
    UPDATE SET program_sk = src.program_sk
WHEN NOT MATCHED THEN
    INSERT (squad_name, program_sk) VALUES (src.squad_name, src.program_sk);
"""

_MERGE_DIM_ISSUE = """
MERGE dim_issue AS tgt
USING (VALUES (?,?,?,?,?,?,?,?,?,?,?,?)) AS src
      (issue_key,issue_type,summary,status,priority,
       program_sk,squad_sk,reporter,assignee,
       created_at,updated_at,resolution_date)
ON tgt.issue_key = src.issue_key
WHEN MATCHED THEN
    UPDATE SET issue_type=src.issue_type, summary=src.summary,
               status=src.status, priority=src.priority,
               program_sk=src.program_sk, squad_sk=src.squad_sk,
               reporter=src.reporter, assignee=src.assignee,
               created_at=src.created_at, updated_at=src.updated_at,
               resolution_date=src.resolution_date
WHEN NOT MATCHED THEN
    INSERT (issue_key,issue_type,summary,status,priority,
            program_sk,squad_sk,reporter,assignee,
            created_at,updated_at,resolution_date)
    VALUES (src.issue_key,src.issue_type,src.summary,src.status,src.priority,
            src.program_sk,src.squad_sk,src.reporter,src.assignee,
            src.created_at,src.updated_at,src.resolution_date);
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
USING (VALUES (?,?,?,?,?,?,?,?,?,?,?,?)) AS src
      (test_run_id,test_sk,execution_sk,release_sk,
       run_status,started_at,finished_at,duration_s,
       executed_by,assignee,comment,defect_count)
ON  tgt.test_run_id = src.test_run_id
AND tgt.release_sk  = src.release_sk
WHEN MATCHED THEN
    UPDATE SET test_sk=src.test_sk, execution_sk=src.execution_sk,
               run_status=src.run_status, started_at=src.started_at,
               finished_at=src.finished_at, duration_s=src.duration_s,
               executed_by=src.executed_by, assignee=src.assignee,
               comment=src.comment, defect_count=src.defect_count
WHEN NOT MATCHED THEN
    INSERT (test_run_id,test_sk,execution_sk,release_sk,
            run_status,started_at,finished_at,duration_s,
            executed_by,assignee,comment,defect_count)
    VALUES (src.test_run_id,src.test_sk,src.execution_sk,src.release_sk,
            src.run_status,src.started_at,src.finished_at,src.duration_s,
            src.executed_by,src.assignee,src.comment,src.defect_count);
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

_LOOKUP_SK = "SELECT {sk_col} FROM {table} WHERE {key_col} = ?"


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

        # 1. Jira issues → dim_program, dim_squad, dim_issue
        for key, payload in self._iter_staging("stg_jira_issues", wm):
            self._handle_jira_issue(key, payload, "jira_issue")
            processed += 1
            upserted  += 1

        # 2. Jira defects → dim_issue (reuse same handler, different entity_type)
        for key, payload in self._iter_staging("stg_jira_defects", wm):
            self._handle_jira_issue(key, payload, "jira_defect")
            processed += 1
            upserted  += 1

        # 3. Xray tests → dim_test
        for key, payload in self._iter_staging("stg_xray_tests", wm):
            self._handle_xray_test(key, payload)
            processed += 1
            upserted  += 1

        # 4. Xray test executions → dim_test_execution
        for key, payload in self._iter_staging("stg_xray_test_executions", wm):
            self._handle_xray_test_execution(key, payload)
            processed += 1
            upserted  += 1

        # 5. Xray test runs → fact_test_run
        for key, payload in self._iter_staging("stg_xray_test_runs", wm):
            self._handle_xray_test_run(key, payload)
            processed += 1
            upserted  += 1

        # 6. Step results → fact_test_step_result
        for key, payload in self._iter_staging("stg_xray_test_step_results", wm):
            self._handle_step_result(key, payload)
            processed += 1
            upserted  += 1

        return processed, upserted

    # ── Per-entity handlers ────────────────────────────────────────────────────

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

        # Ensure dim_squad row exists
        squad_name: str | None = cf.get("squad_name")
        squad_sk: int | None = None
        if squad_name:
            self._rpt.execute(_MERGE_DIM_SQUAD, squad_name, program_sk)
            row = self._rpt.execute(
                _LOOKUP_SK.format(sk_col="squad_sk", table="dim_squad", key_col="squad_name"),
                squad_name,
            ).fetchone()
            squad_sk = row[0] if row else None

        self._rpt.execute(
            _MERGE_DIM_ISSUE,
            source_key,
            fields.get("issuetype", {}).get("name"),
            fields.get("summary"),
            fields.get("status", {}).get("name"),
            fields.get("priority", {}).get("name"),
            program_sk,
            squad_sk,
            _account(fields.get("reporter")),
            _account(fields.get("assignee")),
            _parse_ts(fields.get("created")),
            _parse_ts(fields.get("updated")),
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

        # test_type_sk — look up or insert into dim_test_type
        test_type_name: str | None = cf.get("test_type")
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
            cf.get("gherkin_definition"),
            cf.get("generic_definition"),
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

        self._rpt.execute(
            _MERGE_DIM_TEST_EXECUTION,
            source_key,
            fields.get("summary"),
            fields.get("status", {}).get("name") if isinstance(fields.get("status"), dict) else fields.get("status"),
            cf.get("test_plan_key"),
            cf.get("test_environments"),
            cf.get("revision"),
            _account(fields.get("assignee")),
            _parse_ts(fields.get("updated")),
        )

    def _handle_xray_test_run(
        self,
        source_key: str,
        payload: dict[str, Any],
    ) -> None:
        # Resolve FKs
        test_key = _nested_key(payload, ["test", "key"]) or _nested_key(payload, ["test", "jira", "key"])
        exec_key = payload.get("_execution_key") or payload.get("_execution_issue_id", "")

        test_sk      = self._lookup_test(test_key)
        execution_sk = self._lookup_execution(exec_key)

        # Fix versions → fan-out one row per release
        fix_versions: list[str] = payload.get("fixVersions") or []
        if not fix_versions:
            fix_versions = ["UNVERSIONED"]

        started_at  = _parse_ts(payload.get("startedOn") or payload.get("started_at"))
        finished_at = _parse_ts(payload.get("finishedOn") or payload.get("finished_at"))
        duration_s: float | None = None
        if started_at and finished_at:
            duration_s = (finished_at - started_at).total_seconds()

        defect_count = len(payload.get("defects") or [])
        run_status   = (payload.get("status") or {}).get("name") if isinstance(payload.get("status"), dict) else payload.get("status")
        executed_by  = _account(payload.get("assignee"))
        comment      = payload.get("comment")

        for version in fix_versions:
            release_sk = self._lookup_or_create_release(version)
            self._rpt.execute(
                _MERGE_FACT_TEST_RUN,
                source_key,
                test_sk,
                execution_sk,
                release_sk,
                run_status,
                started_at,
                finished_at,
                duration_s,
                executed_by,
                None,       # assignee not in test run payload directly
                comment,
                defect_count,
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


def _nested_key(payload: dict[str, Any], path: list[str]) -> str | None:
    """Safely walk a nested dict and return the value or None."""
    node: Any = payload
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return str(node) if node is not None else None
