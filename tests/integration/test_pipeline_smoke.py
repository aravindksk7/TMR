"""
tests/integration/test_pipeline_smoke.py — Live smoke tests.

These tests require real database connections and (optionally) real API
credentials.  They are marked with the `integration` pytest marker and
excluded from normal CI via:

    pytest -m "not integration"

To run integration tests set the environment variables in .env and use:

    pytest -m integration -v

Environment variables required:
  STAGING_DB_DSN, REPORTING_DB_DSN — must point to real SQL Server DBs
  JIRA_BASE_URL, XRAY_BASE_URL, JIRA_AUTH_TOKEN — Jira/Xray instance
"""
from __future__ import annotations

import pytest


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def settings():
    """Load real settings — fails fast if .env is missing required vars."""
    from qa_pipeline.settings import PipelineSettings
    return PipelineSettings()


@pytest.fixture(scope="module")
def staging_conn(settings):
    from qa_pipeline.db.connection import build_connection
    conn = build_connection(settings.staging_db_dsn.get_secret_value())
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def reporting_conn(settings):
    from qa_pipeline.db.connection import build_connection
    conn = build_connection(settings.reporting_db_dsn.get_secret_value())
    yield conn
    conn.close()


# ── Staging DB Tests ───────────────────────────────────────────────────────────

@pytest.mark.integration
def test_staging_db_connection(staging_conn):
    """Verify Staging_DB is reachable and pipeline_watermarks exists."""
    row = staging_conn.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_NAME = 'pipeline_watermarks'"
    ).fetchone()
    assert row[0] == 1, "pipeline_watermarks not found — run init_staging_db.sql"


@pytest.mark.integration
def test_staging_tables_exist(staging_conn):
    """All ten stg_* tables must exist."""
    for tbl in [
        'stg_jira_issues',
        'stg_jira_defects',
        'stg_jira_versions',
        'stg_xray_tests',
        'stg_xray_test_executions',
        'stg_xray_test_runs',
        'stg_xray_test_step_results',
        'stg_xray_test_sets',
        'stg_xray_preconditions',
        'stg_xray_test_plans',
    ]:
        row = staging_conn.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", tbl
        ).fetchone()
        assert row[0] == 1, f"Staging table '{tbl}' not found"


@pytest.mark.integration
def test_watermark_roundtrip(staging_conn):
    """Write and read back a watermark."""
    from datetime import datetime, timezone
    from qa_pipeline.db.connection import get_watermark, set_watermark

    ts = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    set_watermark(staging_conn, "_test_smoke_job", ts)
    retrieved = get_watermark(staging_conn, "_test_smoke_job")
    assert retrieved is not None
    assert retrieved.year == 2024 and retrieved.month == 6 and retrieved.day == 15

    staging_conn.execute(
        "DELETE FROM pipeline_watermarks WHERE job_name = ?", "_test_smoke_job"
    )
    staging_conn.commit()


@pytest.mark.integration
def test_staging_writer_roundtrip(staging_conn):
    """Write a record to stg_jira_issues and read it back."""
    import json
    import uuid
    from qa_pipeline.models.staging import StagingRecord
    from qa_pipeline.staging.writer import StagingWriter

    run_id = uuid.uuid4()
    payload = {"key": "SMOKE-1", "fields": {"summary": "Smoke test issue"}}
    record = StagingRecord(
        run_id=run_id,
        source_key="SMOKE-1",
        entity_type="jira_issue",
        raw_json=payload,
    )

    with StagingWriter(staging_conn) as writer:
        count = writer.write_batch([record])

    assert count == 1

    row = staging_conn.execute(
        "SELECT source_key, raw_json FROM stg_jira_issues "
        "WHERE run_id = ? AND source_key = ?",
        str(run_id), "SMOKE-1",
    ).fetchone()
    assert row is not None
    assert row[0] == "SMOKE-1"
    parsed = json.loads(row[1])
    assert parsed["key"] == "SMOKE-1"

    staging_conn.execute(
        "DELETE FROM stg_jira_issues WHERE run_id = ?", str(run_id)
    )
    staging_conn.commit()


@pytest.mark.integration
def test_staging_jira_version_writer_roundtrip(staging_conn):
    """Write a jira_version record to stg_jira_versions and read it back."""
    import json
    import uuid
    from qa_pipeline.models.staging import StagingRecord
    from qa_pipeline.staging.writer import StagingWriter

    run_id = uuid.uuid4()
    payload = {"id": "10001", "name": "v1.0", "released": False, "_project_key": "PROJ"}
    record = StagingRecord(
        run_id=run_id,
        source_key="10001",
        entity_type="jira_version",
        raw_json=payload,
    )

    with StagingWriter(staging_conn) as writer:
        count = writer.write_batch([record])

    assert count == 1

    row = staging_conn.execute(
        "SELECT source_key FROM stg_jira_versions WHERE run_id = ? AND source_key = ?",
        str(run_id), "10001",
    ).fetchone()
    assert row is not None

    staging_conn.execute(
        "DELETE FROM stg_jira_versions WHERE run_id = ?", str(run_id)
    )
    staging_conn.commit()


# ── Reporting DB Tests ─────────────────────────────────────────────────────────

@pytest.mark.integration
def test_reporting_db_connection(reporting_conn):
    """Verify Reporting_DB is reachable and dim_date exists."""
    row = reporting_conn.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_NAME = 'dim_date'"
    ).fetchone()
    assert row[0] == 1, "dim_date not found — run init_reporting_db.sql"


@pytest.mark.integration
def test_reporting_dimension_tables_exist(reporting_conn):
    """All dimension tables must exist."""
    for tbl in [
        'dim_date',
        'dim_program',
        'dim_application',
        'dim_squad',
        'dim_release',
        'dim_test',
        'dim_test_type',
        'dim_test_execution',
        'dim_issue',
        'dim_defect',
        'dim_environment',
        'dim_tester',
        'dim_status',
        'dim_root_cause',
    ]:
        row = reporting_conn.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", tbl
        ).fetchone()
        assert row[0] == 1, f"Dimension table '{tbl}' not found"


@pytest.mark.integration
def test_reporting_fact_tables_exist(reporting_conn):
    """All fact tables must exist."""
    for tbl in [
        'fact_test_run',
        'fact_test_step_result',
        'fact_requirement_coverage',
        'fact_defect_link',
        'fact_cycle_snapshot',
    ]:
        row = reporting_conn.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", tbl
        ).fetchone()
        assert row[0] == 1, f"Fact table '{tbl}' not found"


@pytest.mark.integration
def test_reporting_views_exist(reporting_conn):
    """All eight Power BI reporting views (P1–P8) must exist."""
    for view in [
        'vw_p1_qa_health_by_release',
        'vw_p2_defect_density',
        'vw_p3_requirement_coverage',
        'vw_p4_execution_trend',
        'vw_p5_test_type_breakdown',
        'vw_p6_test_run_detail',
        'vw_p7_environment_health',
        'vw_p8_release_snapshot',
    ]:
        row = reporting_conn.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.VIEWS WHERE TABLE_NAME = ?", view
        ).fetchone()
        assert row[0] == 1, f"View '{view}' not found"


@pytest.mark.integration
def test_dim_date_seeded(reporting_conn):
    """Verify that dim_date has been seeded (at least 365 rows)."""
    row = reporting_conn.execute("SELECT COUNT(*) FROM dim_date").fetchone()
    assert row[0] >= 365, "dim_date appears empty — run qa-seed-dates"


@pytest.mark.integration
def test_dim_status_seeded(reporting_conn):
    """dim_status must have all canonical Xray statuses seeded."""
    expected = {"PASS", "FAIL", "BLOCKED", "EXECUTING", "TODO", "ABORTED"}
    rows = reporting_conn.execute("SELECT status_name FROM dim_status").fetchall()
    found = {r[0] for r in rows}
    missing = expected - found
    assert not missing, f"dim_status missing seeds: {missing}"


@pytest.mark.integration
def test_dim_root_cause_seeded(reporting_conn):
    """dim_root_cause must have at least one seeded row."""
    row = reporting_conn.execute("SELECT COUNT(*) FROM dim_root_cause").fetchone()
    assert row[0] >= 1, "dim_root_cause appears empty — run init_reporting_db.sql"


@pytest.mark.integration
def test_fact_test_run_schema(reporting_conn):
    """fact_test_run must have new columns added in the model update."""
    expected_cols = {
        'test_run_id', 'release_sk', 'test_sk', 'execution_sk', 'run_status',
        'environment_sk', 'tester_sk', 'status_sk', 'root_cause_sk', 'date_sk',
        'is_automated', 'is_blocked', 'block_reason', 'run_sequence',
    }
    rows = reporting_conn.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME = 'fact_test_run'"
    ).fetchall()
    found = {r[0] for r in rows}
    missing = expected_cols - found
    assert not missing, f"fact_test_run missing columns: {missing}"


@pytest.mark.integration
def test_fact_requirement_coverage_schema(reporting_conn):
    """fact_requirement_coverage must have the coverage flag columns."""
    expected_cols = {'partial_coverage_flag', 'failed_coverage_flag', 'latest_execution_date_sk'}
    rows = reporting_conn.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME = 'fact_requirement_coverage'"
    ).fetchall()
    found = {r[0] for r in rows}
    missing = expected_cols - found
    assert not missing, f"fact_requirement_coverage missing columns: {missing}"


@pytest.mark.integration
def test_dim_defect_schema(reporting_conn):
    """dim_defect must have application_sk and flag columns."""
    expected_cols = {'application_sk', 'critical_flag', 'leakage_flag'}
    rows = reporting_conn.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME = 'dim_defect'"
    ).fetchall()
    found = {r[0] for r in rows}
    missing = expected_cols - found
    assert not missing, f"dim_defect missing columns: {missing}"


# ── API Reachability Tests ─────────────────────────────────────────────────────

@pytest.mark.integration
def test_jira_api_reachable(settings):
    """Verify the Jira API responds to a basic field list request.
    Skipped when JIRA_BASE_URL points to a stub hostname."""
    import httpx
    import pytest as _pytest

    base = str(settings.jira_base_url)
    if "example.com" in base or "localhost" in base:
        _pytest.skip("Stub JIRA_BASE_URL — set real credentials to enable this test")

    resp = httpx.get(
        f"{base}/rest/api/3/field",
        headers={"Authorization": settings.jira_auth_token.get_secret_value()},
        timeout=10.0,
    )
    assert resp.status_code == 200, f"Jira API returned {resp.status_code}"
    assert isinstance(resp.json(), list)
