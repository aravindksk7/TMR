"""
staging/writer.py — StagingWriter.

Writes StagingRecord objects into the Staging_DB stg_* tables using
pyodbc MERGE statements (idempotent — safe to re-run on duplicate data).

Each entity type maps to a dedicated staging table:
  jira_issue            → stg_jira_issues
  jira_defect           → stg_jira_defects
  xray_test             → stg_xray_tests
  xray_test_execution   → stg_xray_test_executions
  xray_test_run         → stg_xray_test_runs
  xray_test_step_result → stg_xray_test_step_results
  xray_test_set         → stg_xray_test_sets
  xray_precondition     → stg_xray_preconditions
"""
from __future__ import annotations

from typing import Sequence

import pyodbc
import structlog

from qa_pipeline.models.staging import EntityType, StagingRecord

log = structlog.get_logger(__name__)

# ── Table routing ──────────────────────────────────────────────────────────────

_TABLE_MAP: dict[str, str] = {
    "jira_issue":             "stg_jira_issues",
    "jira_defect":            "stg_jira_defects",
    "xray_test":              "stg_xray_tests",
    "xray_test_execution":    "stg_xray_test_executions",
    "xray_test_run":          "stg_xray_test_runs",
    "xray_test_step_result":  "stg_xray_test_step_results",
    "xray_test_set":          "stg_xray_test_sets",
    "xray_precondition":      "stg_xray_preconditions",
}

# MERGE template — same shape for every staging table.
# Primary key is (source_key, run_id) so multiple runs stay isolated.
_MERGE_TMPL = """
MERGE {table} AS tgt
USING (VALUES (CAST(? AS UNIQUEIDENTIFIER), ?, ?, SYSUTCDATETIME())) AS src
      (run_id, source_key, raw_json, loaded_at)
ON  tgt.source_key = src.source_key
AND tgt.run_id     = src.run_id
WHEN MATCHED THEN
    UPDATE SET raw_json  = src.raw_json,
               loaded_at = src.loaded_at
WHEN NOT MATCHED THEN
    INSERT (run_id, source_key, raw_json, loaded_at)
    VALUES (src.run_id, src.source_key, src.raw_json, src.loaded_at);
"""


class StagingWriter:
    """
    Write StagingRecord objects to the appropriate stg_* table.

    Usage::

        with StagingWriter(conn) as writer:
            writer.write_batch(records)
            # commit happens automatically on __exit__
    """

    def __init__(self, conn: pyodbc.Connection, batch_size: int = 500) -> None:
        self._conn = conn
        self._batch_size = batch_size

    def __enter__(self) -> StagingWriter:
        return self

    def __exit__(self, exc_type: object, *_: object) -> None:
        if exc_type is None:
            self._conn.commit()
            log.debug("staging_writer.committed")
        else:
            self._conn.rollback()
            log.warning("staging_writer.rolled_back")

    # ── Public API ─────────────────────────────────────────────────────────────

    def write_batch(self, records: Sequence[StagingRecord]) -> int:
        """
        Upsert all records.  Returns the count of rows written.
        Records with unknown entity_type are skipped with a warning.
        """
        if not records:
            return 0

        # Group by entity_type to execute one MERGE statement per table
        by_type: dict[str, list[StagingRecord]] = {}
        for rec in records:
            by_type.setdefault(rec.entity_type, []).append(rec)

        total_written = 0
        for entity_type, batch in by_type.items():
            table = _TABLE_MAP.get(entity_type)
            if table is None:
                log.warning("staging_writer.unknown_entity_type", entity_type=entity_type,
                            count=len(batch))
                continue
            total_written += self._write_to_table(table, batch)

        return total_written

    # ── Private helpers ────────────────────────────────────────────────────────

    def _write_to_table(self, table: str, records: list[StagingRecord]) -> int:
        sql = _MERGE_TMPL.format(table=table)
        written = 0

        # Process in sub-batches to avoid huge parameter lists
        for i in range(0, len(records), self._batch_size):
            chunk = records[i : i + self._batch_size]
            params = [
                (str(r.run_id), r.source_key, r.raw_json)
                for r in chunk
            ]
            cursor = self._conn.cursor()
            cursor.executemany(sql, params)
            written += len(chunk)

        log.info("staging_writer.wrote", table=table, rows=written)
        return written
