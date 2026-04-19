-- =============================================================================
-- upgrade_reporting_db.sql  — adds every object missing from Reporting_DB
-- Run against Reporting_DB in SSMS.  Safe to re-run (idempotent).
-- =============================================================================

USE Reporting_DB;
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

-- ── 1. New dimension tables ────────────────────────────────────────────────────

IF OBJECT_ID('dim_application','U') IS NULL
CREATE TABLE dim_application (
    application_sk   INT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    application_name NVARCHAR(255) NOT NULL UNIQUE,
    platform         NVARCHAR(100) NULL,
    program_sk       INT           NULL REFERENCES dim_program(program_sk),
    is_active        BIT           NOT NULL DEFAULT 1
);
GO

IF OBJECT_ID('dim_status','U') IS NULL
CREATE TABLE dim_status (
    status_sk       INT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    status_name     NVARCHAR(50)  NOT NULL UNIQUE,
    status_category NVARCHAR(20)  NOT NULL,
    sort_order      TINYINT       NOT NULL DEFAULT 99
);
GO

IF OBJECT_ID('dim_root_cause','U') IS NULL
CREATE TABLE dim_root_cause (
    root_cause_sk       INT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    root_cause_name     NVARCHAR(100) NOT NULL UNIQUE,
    root_cause_category NVARCHAR(50)  NULL
);
GO

IF OBJECT_ID('dim_environment','U') IS NULL
CREATE TABLE dim_environment (
    environment_sk   INT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    environment_name NVARCHAR(255) NOT NULL UNIQUE,
    environment_type NVARCHAR(50)  NULL,
    criticality      NVARCHAR(10)  NULL
);
GO

IF OBJECT_ID('dim_tester','U') IS NULL
CREATE TABLE dim_tester (
    tester_sk   INT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    tester_id   NVARCHAR(255) NOT NULL UNIQUE,
    tester_name NVARCHAR(255) NULL,
    email       NVARCHAR(255) NULL,
    team_name   NVARCHAR(255) NULL,
    is_active   BIT           NOT NULL DEFAULT 1
);
GO

-- ── 2. Seed reference data ────────────────────────────────────────────────────

MERGE dim_status AS tgt
USING (VALUES
    ('PASS',      'Pass',    1),
    ('FAIL',      'Fail',    2),
    ('BLOCKED',   'Blocked', 3),
    ('EXECUTING', 'Active',  4),
    ('TODO',      'Pending', 5),
    ('ABORTED',   'Skipped', 6)
) AS src (status_name, status_category, sort_order)
ON tgt.status_name = src.status_name
WHEN NOT MATCHED THEN
    INSERT (status_name, status_category, sort_order)
    VALUES (src.status_name, src.status_category, src.sort_order);
GO

MERGE dim_root_cause AS tgt
USING (VALUES
    ('Environment Outage', 'Infra'),
    ('Environment Config', 'Infra'),
    ('Test Data Missing',  'Data'),
    ('Test Data Corrupt',  'Data'),
    ('Application Bug',    'App'),
    ('Application Config', 'Config'),
    ('Network Timeout',    'Network'),
    ('Build Failure',      'Process'),
    ('Not Applicable',     'N/A')
) AS src (root_cause_name, root_cause_category)
ON tgt.root_cause_name = src.root_cause_name
WHEN NOT MATCHED THEN
    INSERT (root_cause_name, root_cause_category)
    VALUES (src.root_cause_name, src.root_cause_category);
GO

-- ── 3. New fact tables ────────────────────────────────────────────────────────

IF OBJECT_ID('fact_defect_link','U') IS NULL
CREATE TABLE fact_defect_link (
    defect_link_sk BIGINT        IDENTITY(1,1) NOT NULL PRIMARY KEY,
    defect_key     NVARCHAR(50)  NOT NULL,
    defect_sk      INT           NULL REFERENCES dim_defect(defect_sk),
    test_run_id    NVARCHAR(100) NOT NULL,
    release_sk     INT           NOT NULL REFERENCES dim_release(release_sk),
    link_type      NVARCHAR(30)  NULL,
    open_flag      BIT           NOT NULL DEFAULT 1,
    linked_at      DATETIME2     NULL
);
GO

IF OBJECT_ID('fact_cycle_snapshot','U') IS NULL
CREATE TABLE fact_cycle_snapshot (
    snapshot_sk           BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    snapshot_date_sk      INT    NOT NULL REFERENCES dim_date(date_sk),
    release_sk            INT    NOT NULL REFERENCES dim_release(release_sk),
    squad_sk              INT    NULL     REFERENCES dim_squad(squad_sk),
    total_tests           INT    NOT NULL DEFAULT 0,
    executed_tests        INT    NOT NULL DEFAULT 0,
    passed_tests          INT    NOT NULL DEFAULT 0,
    failed_tests          INT    NOT NULL DEFAULT 0,
    blocked_tests         INT    NOT NULL DEFAULT 0,
    not_run_tests         INT    NOT NULL DEFAULT 0,
    automated_executions  INT    NOT NULL DEFAULT 0,
    covered_requirements  INT    NOT NULL DEFAULT 0,
    total_requirements    INT    NOT NULL DEFAULT 0,
    open_critical_defects INT    NOT NULL DEFAULT 0,
    avg_duration_s        FLOAT  NULL,
    UNIQUE (snapshot_date_sk, release_sk, squad_sk)
);
GO

-- ── 4. ALTER existing tables — add missing columns ────────────────────────────

-- dim_squad
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dim_squad') AND name='application_sk')
    ALTER TABLE dim_squad ADD application_sk INT NULL REFERENCES dim_application(application_sk);
GO

-- dim_release
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dim_release') AND name='release_train')
    ALTER TABLE dim_release ADD release_train NVARCHAR(100) NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dim_release') AND name='planned_start_date')
    ALTER TABLE dim_release ADD planned_start_date DATE NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dim_release') AND name='planned_end_date')
    ALTER TABLE dim_release ADD planned_end_date DATE NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dim_release') AND name='release_status')
    ALTER TABLE dim_release ADD release_status NVARCHAR(30) NULL;
GO

-- dim_defect
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dim_defect') AND name='application_sk')
    ALTER TABLE dim_defect ADD application_sk INT NULL REFERENCES dim_application(application_sk);
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dim_defect') AND name='leakage_flag')
    ALTER TABLE dim_defect ADD leakage_flag BIT NOT NULL DEFAULT 0;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dim_defect') AND name='severity')
    ALTER TABLE dim_defect ADD severity NVARCHAR(50) NULL;
GO

-- dim_issue
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dim_issue') AND name='critical_flag')
    ALTER TABLE dim_issue ADD critical_flag BIT NOT NULL DEFAULT 0;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dim_issue') AND name='business_area')
    ALTER TABLE dim_issue ADD business_area NVARCHAR(255) NULL;
GO

-- fact_test_run
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('fact_test_run') AND name='environment_sk')
    ALTER TABLE fact_test_run ADD environment_sk INT NULL REFERENCES dim_environment(environment_sk);
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('fact_test_run') AND name='tester_sk')
    ALTER TABLE fact_test_run ADD tester_sk INT NULL REFERENCES dim_tester(tester_sk);
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('fact_test_run') AND name='status_sk')
    ALTER TABLE fact_test_run ADD status_sk INT NULL REFERENCES dim_status(status_sk);
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('fact_test_run') AND name='root_cause_sk')
    ALTER TABLE fact_test_run ADD root_cause_sk INT NULL REFERENCES dim_root_cause(root_cause_sk);
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('fact_test_run') AND name='date_sk')
    ALTER TABLE fact_test_run ADD date_sk INT NULL REFERENCES dim_date(date_sk);
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('fact_test_run') AND name='run_sequence')
    ALTER TABLE fact_test_run ADD run_sequence TINYINT NOT NULL DEFAULT 1;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('fact_test_run') AND name='is_automated')
    ALTER TABLE fact_test_run ADD is_automated BIT NOT NULL DEFAULT 0;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('fact_test_run') AND name='block_reason')
    ALTER TABLE fact_test_run ADD block_reason NVARCHAR(500) NULL;
GO

-- fact_requirement_coverage
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('fact_requirement_coverage') AND name='partial_coverage_flag')
    ALTER TABLE fact_requirement_coverage ADD partial_coverage_flag BIT NOT NULL DEFAULT 0;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('fact_requirement_coverage') AND name='failed_coverage_flag')
    ALTER TABLE fact_requirement_coverage ADD failed_coverage_flag BIT NOT NULL DEFAULT 0;
GO
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('fact_requirement_coverage') AND name='latest_execution_date_sk')
    ALTER TABLE fact_requirement_coverage ADD latest_execution_date_sk INT NULL REFERENCES dim_date(date_sk);
GO

-- ── 5. Recreate all views (CREATE OR ALTER is idempotent) ─────────────────────

CREATE OR ALTER VIEW vw_p1_qa_health_by_release AS
SELECT
    r.release_name,
    r.release_date,
    r.release_status,
    COUNT(*)                                                       AS total_runs,
    SUM(CASE WHEN tr.run_status = 'PASS'      THEN 1 ELSE 0 END)  AS passed,
    SUM(CASE WHEN tr.run_status = 'FAIL'      THEN 1 ELSE 0 END)  AS failed,
    SUM(CASE WHEN tr.run_status = 'BLOCKED'   THEN 1 ELSE 0 END)  AS blocked,
    SUM(CASE WHEN tr.run_status = 'EXECUTING' THEN 1 ELSE 0 END)  AS executing,
    SUM(CASE WHEN tr.run_status = 'TODO'      THEN 1 ELSE 0 END)  AS todo,
    SUM(CASE WHEN tr.run_status = 'ABORTED'   THEN 1 ELSE 0 END)  AS aborted,
    SUM(CASE WHEN tr.is_automated = 1         THEN 1 ELSE 0 END)  AS automated_runs,
    CAST(100.0 * SUM(CASE WHEN tr.run_status = 'PASS' THEN 1 ELSE 0 END)
         / NULLIF(COUNT(*), 0) AS DECIMAL(5,2))                    AS pass_rate_pct
FROM  fact_test_run tr
JOIN  dim_release   r  ON tr.release_sk = r.release_sk
GROUP BY r.release_name, r.release_date, r.release_status;
GO

CREATE OR ALTER VIEW vw_p2_defect_density AS
SELECT
    r.release_name,
    sq.squad_name,
    d.severity,
    d.priority,
    d.status                                  AS defect_status,
    COUNT(DISTINCT fdl.defect_key)            AS total_defects,
    SUM(CAST(fdl.open_flag AS INT))           AS open_defects,
    SUM(CAST(ISNULL(d.critical_flag, 0) AS INT)) AS critical_defects,
    COUNT(DISTINCT fdl.test_run_id)           AS impacted_runs
FROM  fact_defect_link  fdl
JOIN  dim_release       r   ON fdl.release_sk = r.release_sk
LEFT  JOIN dim_defect   d   ON fdl.defect_sk  = d.defect_sk
LEFT  JOIN dim_squad    sq  ON d.squad_sk     = sq.squad_sk
GROUP BY r.release_name, sq.squad_name, d.severity, d.priority, d.status;
GO

CREATE OR ALTER VIEW vw_qm_quality_effectiveness AS
WITH defects AS (
    SELECT
        r.release_sk,
        r.release_name,
        COUNT(DISTINCT d.defect_key) AS total_defects,
        SUM(CASE WHEN d.status IN ('Closed', 'Done', 'Resolved', 'Won''t Fix') THEN 1 ELSE 0 END) AS resolved_defects,
        SUM(CASE WHEN d.status = 'Reopened' THEN 1 ELSE 0 END) AS reopened_defects,
        SUM(CASE WHEN d.leakage_flag = 1 THEN 1 ELSE 0 END) AS leakage_defects,
        SUM(CASE WHEN d.critical_flag = 1 THEN 1 ELSE 0 END) AS critical_defects,
        AVG(CASE
                WHEN d.created_at IS NOT NULL AND COALESCE(d.resolved_at, d.resolution_date) IS NOT NULL
                THEN CAST(DATEDIFF(MINUTE, d.created_at, COALESCE(d.resolved_at, d.resolution_date)) / 60.0 AS FLOAT)
                ELSE NULL
            END) AS avg_resolution_hours
    FROM dim_release r
    LEFT JOIN fact_defect_link fdl ON fdl.release_sk = r.release_sk
    LEFT JOIN dim_defect d ON d.defect_sk = fdl.defect_sk
    GROUP BY r.release_sk, r.release_name
),
coverage AS (
    SELECT
        r.release_sk,
        SUM(fc.total_test_count) AS coverage_total_tests,
        SUM(CASE WHEN fc.total_test_count = 0 THEN 1 ELSE 0 END) AS requirements_without_tests,
        SUM(CASE WHEN fc.is_covered = 1 THEN 1 ELSE 0 END) AS covered_requirements,
        COUNT(*) AS total_requirements
    FROM dim_release r
    LEFT JOIN fact_requirement_coverage fc ON fc.release_sk = r.release_sk
    GROUP BY r.release_sk
),
runs AS (
    SELECT
        r.release_sk,
        COUNT(*) AS total_runs,
        SUM(CASE WHEN tr.run_status = 'FAIL' THEN 1 ELSE 0 END) AS failed_runs,
        SUM(CASE WHEN tr.run_status = 'FAIL' AND ISNULL(tr.defect_count, 0) = 0 THEN 1 ELSE 0 END) AS failed_runs_without_defect
    FROM dim_release r
    LEFT JOIN fact_test_run tr ON tr.release_sk = r.release_sk
    GROUP BY r.release_sk
)
SELECT
    d.release_name,
    ISNULL(d.total_defects, 0) AS total_defects,
    ISNULL(d.resolved_defects, 0) AS resolved_defects,
    ISNULL(d.reopened_defects, 0) AS reopened_defects,
    ISNULL(d.leakage_defects, 0) AS leakage_defects,
    ISNULL(d.critical_defects, 0) AS critical_defects,
    CAST(ISNULL(d.avg_resolution_hours, 0) AS DECIMAL(10,2)) AS avg_resolution_hours,
    ISNULL(c.total_requirements, 0) AS total_requirements,
    ISNULL(c.covered_requirements, 0) AS covered_requirements,
    ISNULL(c.requirements_without_tests, 0) AS requirements_without_tests,
    ISNULL(r.total_runs, 0) AS total_runs,
    ISNULL(r.failed_runs, 0) AS failed_runs,
    ISNULL(r.failed_runs_without_defect, 0) AS failed_runs_without_defect,
    CAST(100.0 * ISNULL(d.resolved_defects, 0) / NULLIF(ISNULL(d.total_defects, 0), 0) AS DECIMAL(5,2)) AS defect_resolution_rate_pct,
    CAST(100.0 * ISNULL(d.reopened_defects, 0) / NULLIF(ISNULL(d.resolved_defects, 0), 0) AS DECIMAL(5,2)) AS defect_reopen_rate_pct,
    CAST(100.0 * ISNULL(d.leakage_defects, 0) / NULLIF(ISNULL(d.total_defects, 0), 0) AS DECIMAL(5,2)) AS defect_leakage_rate_pct,
    CAST(100.0 * (ISNULL(d.total_defects, 0) - ISNULL(d.leakage_defects, 0)) / NULLIF(ISNULL(d.total_defects, 0), 0) AS DECIMAL(5,2)) AS defect_removal_efficiency_pct,
    CAST(100.0 * ISNULL(c.covered_requirements, 0) / NULLIF(ISNULL(c.total_requirements, 0), 0) AS DECIMAL(5,2)) AS requirement_coverage_pct,
    CAST(100.0 * ISNULL(c.requirements_without_tests, 0) / NULLIF(ISNULL(c.total_requirements, 0), 0) AS DECIMAL(5,2)) AS requirements_without_tests_pct,
    CAST(100.0 * ISNULL(r.failed_runs_without_defect, 0) / NULLIF(ISNULL(r.failed_runs, 0), 0) AS DECIMAL(5,2)) AS failed_runs_without_defect_pct
FROM defects d
LEFT JOIN coverage c ON c.release_sk = d.release_sk
LEFT JOIN runs r ON r.release_sk = d.release_sk;
GO

CREATE OR ALTER VIEW vw_p3_requirement_coverage AS
SELECT
    i.issue_key,
    i.summary                  AS requirement_summary,
    i.issue_type,
    i.priority,
    i.critical_flag            AS is_critical_requirement,
    i.business_area,
    sq.squad_name,
    r.release_name,
    fc.total_test_count,
    fc.passing_test_count,
    fc.failing_test_count,
    fc.blocked_test_count,
    fc.todo_test_count,
    fc.no_coverage_count,
    fc.coverage_status,
    fc.is_covered,
    fc.partial_coverage_flag,
    fc.failed_coverage_flag
FROM  fact_requirement_coverage fc
JOIN  dim_issue   i   ON fc.issue_sk   = i.issue_sk
JOIN  dim_release r   ON fc.release_sk = r.release_sk
LEFT  JOIN dim_squad sq ON i.squad_sk  = sq.squad_sk;
GO

CREATE OR ALTER VIEW vw_p4_execution_trend AS
SELECT
    CAST(tr.started_at AS DATE)                                    AS run_date,
    dd.date_sk,
    dd.year,
    dd.month,
    dd.week_of_year,
    sq.squad_name,
    e.environment_name,
    r.release_name,
    COUNT(*)                                                       AS total_runs,
    SUM(CASE WHEN tr.run_status = 'PASS'    THEN 1 ELSE 0 END)    AS passed,
    SUM(CASE WHEN tr.run_status = 'FAIL'    THEN 1 ELSE 0 END)    AS failed,
    SUM(CASE WHEN tr.run_status = 'BLOCKED' THEN 1 ELSE 0 END)    AS blocked,
    SUM(CASE WHEN tr.is_automated = 1       THEN 1 ELSE 0 END)    AS automated_runs,
    AVG(tr.duration_s)                                             AS avg_duration_s
FROM  fact_test_run      tr
JOIN  dim_release        r   ON tr.release_sk     = r.release_sk
JOIN  dim_test           t   ON tr.test_sk        = t.test_sk
LEFT  JOIN dim_squad     sq  ON t.squad_sk        = sq.squad_sk
LEFT  JOIN dim_environment e ON tr.environment_sk = e.environment_sk
LEFT  JOIN dim_date      dd  ON tr.date_sk        = dd.date_sk
GROUP BY CAST(tr.started_at AS DATE), dd.date_sk, dd.year, dd.month,
         dd.week_of_year, sq.squad_name, e.environment_name, r.release_name;
GO

CREATE OR ALTER VIEW vw_p5_test_type_breakdown AS
SELECT
    tt.test_type_name,
    sq.squad_name,
    r.release_name,
    COUNT(*)                                                       AS total_runs,
    SUM(CASE WHEN tr.run_status = 'PASS'    THEN 1 ELSE 0 END)    AS passed,
    SUM(CASE WHEN tr.run_status = 'FAIL'    THEN 1 ELSE 0 END)    AS failed,
    SUM(CASE WHEN tr.run_status = 'BLOCKED' THEN 1 ELSE 0 END)    AS blocked,
    CAST(100.0 * SUM(CASE WHEN tr.run_status = 'PASS' THEN 1 ELSE 0 END)
         / NULLIF(COUNT(*), 0) AS DECIMAL(5,2))                    AS pass_rate_pct
FROM  fact_test_run      tr
JOIN  dim_test           t   ON tr.test_sk     = t.test_sk
JOIN  dim_release        r   ON tr.release_sk  = r.release_sk
LEFT  JOIN dim_test_type tt  ON t.test_type_sk = tt.test_type_sk
LEFT  JOIN dim_squad     sq  ON t.squad_sk     = sq.squad_sk
GROUP BY tt.test_type_name, sq.squad_name, r.release_name;
GO

CREATE OR ALTER VIEW vw_p6_test_run_detail AS
SELECT
    tr.test_run_id,
    t.test_key,
    t.summary              AS test_summary,
    tt.test_type_name,
    te.execution_key,
    te.summary             AS execution_summary,
    te.revision,
    e.environment_name,
    e.environment_type,
    r.release_name,
    r.release_status,
    sq.squad_name,
    tr.run_status,
    ds.status_category,
    tr.run_sequence,
    tr.is_automated,
    CAST(CASE WHEN tr.run_status = 'BLOCKED' THEN 1 ELSE 0 END AS BIT) AS is_blocked,
    tr.block_reason,
    tr.started_at,
    tr.finished_at,
    tr.duration_s,
    tstr.tester_name,
    tstr.team_name,
    tr.executed_by,
    tr.comment,
    tr.defect_count,
    rc.root_cause_name,
    rc.root_cause_category
FROM  fact_test_run          tr
JOIN  dim_release            r    ON tr.release_sk     = r.release_sk
LEFT  JOIN dim_test          t    ON tr.test_sk        = t.test_sk
LEFT  JOIN dim_test_type     tt   ON t.test_type_sk    = tt.test_type_sk
LEFT  JOIN dim_test_execution te  ON tr.execution_sk   = te.execution_sk
LEFT  JOIN dim_squad         sq   ON t.squad_sk        = sq.squad_sk
LEFT  JOIN dim_environment   e    ON tr.environment_sk = e.environment_sk
LEFT  JOIN dim_tester        tstr ON tr.tester_sk      = tstr.tester_sk
LEFT  JOIN dim_status        ds   ON tr.status_sk      = ds.status_sk
LEFT  JOIN dim_root_cause    rc   ON tr.root_cause_sk  = rc.root_cause_sk;
GO

CREATE OR ALTER VIEW vw_p7_environment_health AS
SELECT
    e.environment_name,
    e.environment_type,
    e.criticality,
    r.release_name,
    sq.squad_name,
    rc.root_cause_name,
    rc.root_cause_category,
    CAST(tr.started_at AS DATE)                                    AS execution_date,
    COUNT(*)                                                       AS total_runs,
    SUM(CASE WHEN tr.run_status = 'FAIL'    THEN 1 ELSE 0 END)    AS failed_runs,
    SUM(CASE WHEN tr.run_status = 'BLOCKED' THEN 1 ELSE 0 END)    AS blocked_runs,
    CAST(100.0 * SUM(CASE WHEN tr.run_status = 'PASS' THEN 1 ELSE 0 END)
         / NULLIF(COUNT(*), 0) AS DECIMAL(5,2))                    AS pass_rate_pct
FROM  fact_test_run   tr
JOIN  dim_release     r    ON tr.release_sk     = r.release_sk
LEFT  JOIN dim_environment e  ON tr.environment_sk = e.environment_sk
LEFT  JOIN dim_test   t    ON tr.test_sk        = t.test_sk
LEFT  JOIN dim_squad  sq   ON t.squad_sk        = sq.squad_sk
LEFT  JOIN dim_root_cause rc ON tr.root_cause_sk = rc.root_cause_sk
GROUP BY e.environment_name, e.environment_type, e.criticality,
         r.release_name, sq.squad_name, rc.root_cause_name,
         rc.root_cause_category, CAST(tr.started_at AS DATE);
GO

CREATE OR ALTER VIEW vw_p8_release_snapshot AS
SELECT
    dd.full_date               AS snapshot_date,
    dd.year,
    dd.month,
    r.release_name,
    r.release_date,
    r.release_status,
    sq.squad_name,
    fcs.total_tests,
    fcs.executed_tests,
    fcs.passed_tests,
    fcs.failed_tests,
    fcs.blocked_tests,
    fcs.not_run_tests,
    fcs.automated_executions,
    fcs.covered_requirements,
    fcs.total_requirements,
    fcs.open_critical_defects,
    fcs.avg_duration_s,
    CAST(100.0 * fcs.passed_tests / NULLIF(fcs.executed_tests, 0)
         AS DECIMAL(5,2))      AS pass_rate_pct,
    CAST(100.0 * fcs.covered_requirements / NULLIF(fcs.total_requirements, 0)
         AS DECIMAL(5,2))      AS coverage_rate_pct,
    CAST(100.0 * fcs.automated_executions / NULLIF(fcs.executed_tests, 0)
         AS DECIMAL(5,2))      AS automation_rate_pct
FROM  fact_cycle_snapshot  fcs
JOIN  dim_date             dd  ON fcs.snapshot_date_sk = dd.date_sk
JOIN  dim_release          r   ON fcs.release_sk       = r.release_sk
LEFT  JOIN dim_squad       sq  ON fcs.squad_sk         = sq.squad_sk;
GO

-- ── Verify ────────────────────────────────────────────────────────────────────
SELECT name, type_desc FROM sys.objects
WHERE name IN (
    'dim_application','dim_status','dim_root_cause','dim_environment','dim_tester',
    'fact_defect_link','fact_cycle_snapshot',
    'vw_p2_defect_density','vw_p7_environment_health','vw_p8_release_snapshot',
    'vw_qm_quality_effectiveness'
)
AND type_desc IN ('USER_TABLE','VIEW')
ORDER BY type_desc, name;
GO
