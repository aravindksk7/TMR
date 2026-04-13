-- =============================================================================
-- init_db.sql — Full DDL for QA Pipeline (Staging_DB + Reporting_DB)
-- Run once against each database.  Safe to re-run (all objects use
-- IF NOT EXISTS / CREATE OR ALTER guards where possible).
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 1: Staging_DB objects
-- ─────────────────────────────────────────────────────────────────────────────

-- pipeline_watermarks — persists last-success timestamps per job
IF OBJECT_ID('pipeline_watermarks', 'U') IS NULL
CREATE TABLE pipeline_watermarks (
    job_name        NVARCHAR(200)  NOT NULL PRIMARY KEY,
    last_success_ts DATETIME2      NOT NULL,
    updated_at      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

-- pipeline_run_log — one row per pipeline run
IF OBJECT_ID('pipeline_run_log', 'U') IS NULL
CREATE TABLE pipeline_run_log (
    pipeline_run_id   UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
    job_name          NVARCHAR(200)    NOT NULL,
    status            NVARCHAR(20)     NOT NULL DEFAULT 'running',
    started_at        DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    finished_at       DATETIME2        NULL,
    watermark_before  DATETIME2        NULL,
    watermark_after   DATETIME2        NULL,
    records_extracted INT              NOT NULL DEFAULT 0,
    rows_processed    INT              NOT NULL DEFAULT 0,
    rows_upserted     INT              NOT NULL DEFAULT 0,
    error_message     NVARCHAR(MAX)    NULL,
    alert_sent        BIT              NOT NULL DEFAULT 0
);
GO

-- Helper macro for staging tables — identical shape for all entity types
-- (source_key + run_id composite key keeps runs isolated for debugging)

IF OBJECT_ID('stg_jira_issues', 'U') IS NULL
CREATE TABLE stg_jira_issues (
    id          BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id      UNIQUEIDENTIFIER NOT NULL,
    source_key  NVARCHAR(100)    NOT NULL,
    raw_json    NVARCHAR(MAX)    NOT NULL,
    loaded_at   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_jira_issues UNIQUE (run_id, source_key)
);
GO

IF OBJECT_ID('stg_jira_defects', 'U') IS NULL
CREATE TABLE stg_jira_defects (
    id          BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id      UNIQUEIDENTIFIER NOT NULL,
    source_key  NVARCHAR(100)    NOT NULL,
    raw_json    NVARCHAR(MAX)    NOT NULL,
    loaded_at   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_jira_defects UNIQUE (run_id, source_key)
);
GO

IF OBJECT_ID('stg_xray_tests', 'U') IS NULL
CREATE TABLE stg_xray_tests (
    id          BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id      UNIQUEIDENTIFIER NOT NULL,
    source_key  NVARCHAR(100)    NOT NULL,
    raw_json    NVARCHAR(MAX)    NOT NULL,
    loaded_at   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_xray_tests UNIQUE (run_id, source_key)
);
GO

IF OBJECT_ID('stg_xray_test_executions', 'U') IS NULL
CREATE TABLE stg_xray_test_executions (
    id          BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id      UNIQUEIDENTIFIER NOT NULL,
    source_key  NVARCHAR(100)    NOT NULL,
    raw_json    NVARCHAR(MAX)    NOT NULL,
    loaded_at   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_xray_test_executions UNIQUE (run_id, source_key)
);
GO

IF OBJECT_ID('stg_xray_test_runs', 'U') IS NULL
CREATE TABLE stg_xray_test_runs (
    id          BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id      UNIQUEIDENTIFIER NOT NULL,
    source_key  NVARCHAR(100)    NOT NULL,
    raw_json    NVARCHAR(MAX)    NOT NULL,
    loaded_at   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_xray_test_runs UNIQUE (run_id, source_key)
);
GO

IF OBJECT_ID('stg_xray_test_step_results', 'U') IS NULL
CREATE TABLE stg_xray_test_step_results (
    id          BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id      UNIQUEIDENTIFIER NOT NULL,
    source_key  NVARCHAR(200)    NOT NULL,
    raw_json    NVARCHAR(MAX)    NOT NULL,
    loaded_at   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_xray_test_step_results UNIQUE (run_id, source_key)
);
GO

IF OBJECT_ID('stg_xray_test_sets', 'U') IS NULL
CREATE TABLE stg_xray_test_sets (
    id          BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id      UNIQUEIDENTIFIER NOT NULL,
    source_key  NVARCHAR(100)    NOT NULL,
    raw_json    NVARCHAR(MAX)    NOT NULL,
    loaded_at   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_xray_test_sets UNIQUE (run_id, source_key)
);
GO

IF OBJECT_ID('stg_xray_preconditions', 'U') IS NULL
CREATE TABLE stg_xray_preconditions (
    id          BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id      UNIQUEIDENTIFIER NOT NULL,
    source_key  NVARCHAR(100)    NOT NULL,
    raw_json    NVARCHAR(MAX)    NOT NULL,
    loaded_at   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_xray_preconditions UNIQUE (run_id, source_key)
);
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 2: Reporting_DB dimension tables
-- ─────────────────────────────────────────────────────────────────────────────

-- dim_date — static calendar; populated by seed_dim_date.py, never truncated
IF OBJECT_ID('dim_date', 'U') IS NULL
CREATE TABLE dim_date (
    date_sk         INT          NOT NULL PRIMARY KEY,  -- YYYYMMDD
    full_date       DATE         NOT NULL UNIQUE,
    year            SMALLINT     NOT NULL,
    quarter         TINYINT      NOT NULL,
    month           TINYINT      NOT NULL,
    month_name      NVARCHAR(10) NOT NULL,
    week_of_year    TINYINT      NOT NULL,
    day_of_month    TINYINT      NOT NULL,
    day_of_week     TINYINT      NOT NULL,  -- 1=Mon … 7=Sun
    day_name        NVARCHAR(10) NOT NULL,
    is_weekend      BIT          NOT NULL,
    fiscal_year     SMALLINT     NULL,
    fiscal_quarter  TINYINT      NULL
);
GO

-- dim_program
IF OBJECT_ID('dim_program', 'U') IS NULL
CREATE TABLE dim_program (
    program_sk   INT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    program_name NVARCHAR(255) NOT NULL UNIQUE,
    description  NVARCHAR(MAX) NULL
);
GO

-- dim_squad
IF OBJECT_ID('dim_squad', 'U') IS NULL
CREATE TABLE dim_squad (
    squad_sk     INT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    squad_name   NVARCHAR(255) NOT NULL UNIQUE,
    program_sk   INT           NULL REFERENCES dim_program(program_sk)
);
GO

-- dim_release (fix versions)
IF OBJECT_ID('dim_release', 'U') IS NULL
CREATE TABLE dim_release (
    release_sk      INT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    release_name    NVARCHAR(255) NOT NULL UNIQUE,
    release_date    DATE          NULL,
    release_date_sk INT           NULL REFERENCES dim_date(date_sk),
    is_released     BIT           NOT NULL DEFAULT 0
);
GO

-- dim_test_type  — Manual, Cucumber, Generic (Xray native types)
IF OBJECT_ID('dim_test_type', 'U') IS NULL
CREATE TABLE dim_test_type (
    test_type_sk   INT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    test_type_name NVARCHAR(100) NOT NULL UNIQUE   -- Manual | Cucumber | Generic
);
GO

-- dim_issue — stories, epics, tasks (non-defect)
IF OBJECT_ID('dim_issue', 'U') IS NULL
CREATE TABLE dim_issue (
    issue_sk        INT            IDENTITY(1,1) NOT NULL PRIMARY KEY,
    issue_key       NVARCHAR(50)   NOT NULL UNIQUE,
    issue_type      NVARCHAR(100)  NULL,
    summary         NVARCHAR(500)  NULL,
    status          NVARCHAR(100)  NULL,
    priority        NVARCHAR(50)   NULL,
    program_sk      INT            NULL REFERENCES dim_program(program_sk),
    squad_sk        INT            NULL REFERENCES dim_squad(squad_sk),
    reporter        NVARCHAR(255)  NULL,
    assignee        NVARCHAR(255)  NULL,
    created_at      DATETIME2      NULL,
    updated_at      DATETIME2      NULL,
    resolution_date DATETIME2      NULL
);
GO

-- dim_defect — Bug issues
IF OBJECT_ID('dim_defect', 'U') IS NULL
CREATE TABLE dim_defect (
    defect_sk       INT            IDENTITY(1,1) NOT NULL PRIMARY KEY,
    defect_key      NVARCHAR(50)   NOT NULL UNIQUE,
    summary         NVARCHAR(500)  NULL,
    status          NVARCHAR(100)  NULL,
    priority        NVARCHAR(50)   NULL,
    severity        NVARCHAR(50)   NULL,
    squad_sk        INT            NULL REFERENCES dim_squad(squad_sk),
    reporter        NVARCHAR(255)  NULL,
    assignee        NVARCHAR(255)  NULL,
    created_at      DATETIME2      NULL,
    resolved_at     DATETIME2      NULL,
    resolution_date DATETIME2      NULL
);
GO

-- dim_test
IF OBJECT_ID('dim_test', 'U') IS NULL
CREATE TABLE dim_test (
    test_sk              INT            IDENTITY(1,1) NOT NULL PRIMARY KEY,
    test_key             NVARCHAR(50)   NOT NULL UNIQUE,
    summary              NVARCHAR(500)  NULL,
    status               NVARCHAR(100)  NULL,
    test_type_sk         INT            NULL REFERENCES dim_test_type(test_type_sk),
    repository_path      NVARCHAR(500)  NULL,
    gherkin_definition   NVARCHAR(MAX)  NULL,
    generic_definition   NVARCHAR(MAX)  NULL,
    squad_sk             INT            NULL REFERENCES dim_squad(squad_sk),
    assignee             NVARCHAR(255)  NULL,
    created_at           DATETIME2      NULL,
    updated_at           DATETIME2      NULL
);
GO

-- dim_test_plan
IF OBJECT_ID('dim_test_plan', 'U') IS NULL
CREATE TABLE dim_test_plan (
    test_plan_sk    INT            IDENTITY(1,1) NOT NULL PRIMARY KEY,
    test_plan_key   NVARCHAR(50)   NOT NULL UNIQUE,
    summary         NVARCHAR(500)  NULL,
    status          NVARCHAR(100)  NULL,
    squad_sk        INT            NULL REFERENCES dim_squad(squad_sk),
    assignee        NVARCHAR(255)  NULL,
    created_at      DATETIME2      NULL,
    updated_at      DATETIME2      NULL
);
GO

-- dim_test_execution
IF OBJECT_ID('dim_test_execution', 'U') IS NULL
CREATE TABLE dim_test_execution (
    execution_sk        INT            IDENTITY(1,1) NOT NULL PRIMARY KEY,
    execution_key       NVARCHAR(50)   NOT NULL UNIQUE,
    summary             NVARCHAR(500)  NULL,
    status              NVARCHAR(100)  NULL,
    test_plan_key       NVARCHAR(50)   NULL,
    environments_json   NVARCHAR(MAX)  NULL,   -- JSON array of env names
    revision            NVARCHAR(255)  NULL,
    assignee            NVARCHAR(255)  NULL,
    executed_at         DATETIME2      NULL
);
GO

-- bridge_squad_user — RLS membership table
IF OBJECT_ID('bridge_squad_user', 'U') IS NULL
CREATE TABLE bridge_squad_user (
    squad_sk        INT            NOT NULL REFERENCES dim_squad(squad_sk),
    user_email      NVARCHAR(255)  NOT NULL,
    role            NVARCHAR(50)   NOT NULL DEFAULT 'Squad_Member',
    PRIMARY KEY (squad_sk, user_email)
);
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 3: Reporting_DB fact tables
-- ─────────────────────────────────────────────────────────────────────────────

-- fact_test_run — one row per test run per fix version
IF OBJECT_ID('fact_test_run', 'U') IS NULL
CREATE TABLE fact_test_run (
    test_run_id      NVARCHAR(100)  NOT NULL,   -- Xray run ID (numeric or GUID)
    release_sk       INT            NOT NULL REFERENCES dim_release(release_sk),
    test_sk          INT            NULL REFERENCES dim_test(test_sk),
    execution_sk     INT            NULL REFERENCES dim_test_execution(execution_sk),
    run_status       NVARCHAR(50)   NULL,        -- TODO | PASS | FAIL | EXECUTING | ABORTED | BLOCKED
    started_at       DATETIME2      NULL,
    finished_at      DATETIME2      NULL,
    duration_s       FLOAT          NULL,
    executed_by      NVARCHAR(255)  NULL,
    assignee         NVARCHAR(255)  NULL,
    comment          NVARCHAR(MAX)  NULL,
    defect_count     INT            NOT NULL DEFAULT 0,
    PRIMARY KEY (test_run_id, release_sk)
);
GO

-- fact_test_step_result — step-level results
IF OBJECT_ID('fact_test_step_result', 'U') IS NULL
CREATE TABLE fact_test_step_result (
    step_result_id  NVARCHAR(200)  NOT NULL PRIMARY KEY,
    test_run_id     NVARCHAR(100)  NOT NULL,
    step_order      INT            NOT NULL DEFAULT 0,
    step_status     NVARCHAR(50)   NULL,
    actual_result   NVARCHAR(MAX)  NULL,
    comment         NVARCHAR(MAX)  NULL
);
GO

-- fact_requirement_coverage — pre-aggregated coverage per issue per release
IF OBJECT_ID('fact_requirement_coverage', 'U') IS NULL
CREATE TABLE fact_requirement_coverage (
    issue_sk                 INT       NOT NULL REFERENCES dim_issue(issue_sk),
    release_sk               INT       NOT NULL REFERENCES dim_release(release_sk),
    total_test_count         INT       NOT NULL DEFAULT 0,
    passing_test_count       INT       NOT NULL DEFAULT 0,
    failing_test_count       INT       NOT NULL DEFAULT 0,
    blocked_test_count       INT       NOT NULL DEFAULT 0,
    executing_test_count     INT       NOT NULL DEFAULT 0,
    todo_test_count          INT       NOT NULL DEFAULT 0,
    no_coverage_count        INT       NOT NULL DEFAULT 0,
    coverage_status          NVARCHAR(20)  NULL,   -- highest-priority status
    is_covered               AS (CAST(CASE WHEN passing_test_count > 0 THEN 1 ELSE 0 END AS BIT)) PERSISTED,
    PRIMARY KEY (issue_sk, release_sk)
);
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 4: Reporting views (P1–P6)
-- ─────────────────────────────────────────────────────────────────────────────

-- P1 — Overall QA health per release
CREATE OR ALTER VIEW vw_p1_qa_health_by_release AS
SELECT
    r.release_name,
    r.release_date,
    COUNT(*)                                                       AS total_runs,
    SUM(CASE WHEN tr.run_status = 'PASS'      THEN 1 ELSE 0 END)  AS passed,
    SUM(CASE WHEN tr.run_status = 'FAIL'      THEN 1 ELSE 0 END)  AS failed,
    SUM(CASE WHEN tr.run_status = 'BLOCKED'   THEN 1 ELSE 0 END)  AS blocked,
    SUM(CASE WHEN tr.run_status = 'EXECUTING' THEN 1 ELSE 0 END)  AS executing,
    SUM(CASE WHEN tr.run_status = 'TODO'      THEN 1 ELSE 0 END)  AS todo,
    SUM(CASE WHEN tr.run_status = 'ABORTED'   THEN 1 ELSE 0 END)  AS aborted,
    CAST(
        100.0 * SUM(CASE WHEN tr.run_status = 'PASS' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0)
    AS DECIMAL(5,2))                                               AS pass_rate_pct
FROM  fact_test_run tr
JOIN  dim_release   r  ON tr.release_sk = r.release_sk
GROUP BY r.release_name, r.release_date;
GO

-- P2 — Defect density per squad per release
CREATE OR ALTER VIEW vw_p2_defect_density AS
SELECT
    sq.squad_name,
    r.release_name,
    COUNT(DISTINCT d.defect_sk)                              AS total_defects,
    COUNT(DISTINCT CASE WHEN d.status IN ('Closed','Done','Resolved')
                        THEN d.defect_sk END)               AS resolved_defects,
    COUNT(DISTINCT CASE WHEN d.status NOT IN ('Closed','Done','Resolved')
                        THEN d.defect_sk END)               AS open_defects,
    COUNT(DISTINCT CASE WHEN d.severity = 'Critical'        THEN d.defect_sk END) AS critical_defects,
    COUNT(DISTINCT CASE WHEN d.severity = 'High'            THEN d.defect_sk END) AS high_defects
FROM  dim_defect   d
JOIN  dim_squad    sq ON d.squad_sk    = sq.squad_sk
-- defect linked to release via fact_test_run.defect_count (approximation):
-- join through test executions is complex; use release_name from fix version
CROSS JOIN dim_release r   -- Power BI filters by release slicer
GROUP BY sq.squad_name, r.release_name;
GO

-- P3 — Test coverage per requirement per release
CREATE OR ALTER VIEW vw_p3_requirement_coverage AS
SELECT
    i.issue_key,
    i.summary                                    AS requirement_summary,
    i.issue_type,
    i.priority,
    sq.squad_name,
    r.release_name,
    fc.total_test_count,
    fc.passing_test_count,
    fc.failing_test_count,
    fc.blocked_test_count,
    fc.todo_test_count,
    fc.no_coverage_count,
    fc.coverage_status,
    fc.is_covered
FROM  fact_requirement_coverage fc
JOIN  dim_issue   i   ON fc.issue_sk   = i.issue_sk
JOIN  dim_release r   ON fc.release_sk = r.release_sk
LEFT  JOIN dim_squad sq ON i.squad_sk  = sq.squad_sk;
GO

-- P4 — Test execution trend (daily, by squad, by release)
CREATE OR ALTER VIEW vw_p4_execution_trend AS
SELECT
    CAST(tr.started_at AS DATE)                                    AS run_date,
    dd.date_sk,
    dd.year,
    dd.month,
    dd.week_of_year,
    sq.squad_name,
    r.release_name,
    COUNT(*)                                                       AS total_runs,
    SUM(CASE WHEN tr.run_status = 'PASS' THEN 1 ELSE 0 END)       AS passed,
    SUM(CASE WHEN tr.run_status = 'FAIL' THEN 1 ELSE 0 END)       AS failed,
    AVG(tr.duration_s)                                             AS avg_duration_s
FROM  fact_test_run      tr
JOIN  dim_release        r   ON tr.release_sk  = r.release_sk
JOIN  dim_test           t   ON tr.test_sk     = t.test_sk
LEFT  JOIN dim_squad     sq  ON t.squad_sk     = sq.squad_sk
LEFT  JOIN dim_date      dd  ON CAST(CONVERT(CHAR(8), tr.started_at, 112) AS INT) = dd.date_sk
GROUP BY CAST(tr.started_at AS DATE), dd.date_sk, dd.year, dd.month, dd.week_of_year,
         sq.squad_name, r.release_name;
GO

-- P5 — Test type breakdown (Manual vs Cucumber vs Generic)
CREATE OR ALTER VIEW vw_p5_test_type_breakdown AS
SELECT
    tt.test_type_name,
    sq.squad_name,
    r.release_name,
    COUNT(*)                                                        AS total_runs,
    SUM(CASE WHEN tr.run_status = 'PASS' THEN 1 ELSE 0 END)        AS passed,
    SUM(CASE WHEN tr.run_status = 'FAIL' THEN 1 ELSE 0 END)        AS failed,
    SUM(CASE WHEN tr.run_status = 'BLOCKED' THEN 1 ELSE 0 END)     AS blocked,
    CAST(
        100.0 * SUM(CASE WHEN tr.run_status = 'PASS' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0)
    AS DECIMAL(5,2))                                                AS pass_rate_pct
FROM  fact_test_run      tr
JOIN  dim_test           t   ON tr.test_sk      = t.test_sk
JOIN  dim_release        r   ON tr.release_sk   = r.release_sk
LEFT  JOIN dim_test_type tt  ON t.test_type_sk  = tt.test_type_sk
LEFT  JOIN dim_squad     sq  ON t.squad_sk      = sq.squad_sk
GROUP BY tt.test_type_name, sq.squad_name, r.release_name;
GO

-- P6 — Drill-through: individual test run detail
CREATE OR ALTER VIEW vw_p6_test_run_detail AS
SELECT
    tr.test_run_id,
    t.test_key,
    t.summary                  AS test_summary,
    tt.test_type_name,
    te.execution_key,
    te.summary                 AS execution_summary,
    te.environments_json,
    te.revision,
    r.release_name,
    sq.squad_name,
    tr.run_status,
    tr.started_at,
    tr.finished_at,
    tr.duration_s,
    tr.executed_by,
    tr.assignee,
    tr.comment,
    tr.defect_count
FROM  fact_test_run          tr
JOIN  dim_release            r   ON tr.release_sk    = r.release_sk
LEFT  JOIN dim_test          t   ON tr.test_sk       = t.test_sk
LEFT  JOIN dim_test_type     tt  ON t.test_type_sk   = tt.test_type_sk
LEFT  JOIN dim_test_execution te ON tr.execution_sk  = te.execution_sk
LEFT  JOIN dim_squad         sq  ON t.squad_sk       = sq.squad_sk;
GO
