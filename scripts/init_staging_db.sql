-- =============================================================================
-- init_staging_db.sql — DDL for Staging_DB
-- Run against Staging_DB only.
-- =============================================================================

-- pipeline_watermarks
IF OBJECT_ID('pipeline_watermarks', 'U') IS NULL
CREATE TABLE pipeline_watermarks (
    job_name        NVARCHAR(200) NOT NULL PRIMARY KEY,
    last_success_ts DATETIME2     NOT NULL,
    updated_at      DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

-- pipeline_run_log
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

-- Staging tables (one per entity type)

IF OBJECT_ID('stg_jira_issues', 'U') IS NULL
CREATE TABLE stg_jira_issues (
    id         BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id     UNIQUEIDENTIFIER NOT NULL,
    source_key NVARCHAR(100)    NOT NULL,
    raw_json   NVARCHAR(MAX)    NOT NULL,
    loaded_at  DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_jira_issues UNIQUE (run_id, source_key)
);
GO

IF OBJECT_ID('stg_jira_defects', 'U') IS NULL
CREATE TABLE stg_jira_defects (
    id         BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id     UNIQUEIDENTIFIER NOT NULL,
    source_key NVARCHAR(100)    NOT NULL,
    raw_json   NVARCHAR(MAX)    NOT NULL,
    loaded_at  DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_jira_defects UNIQUE (run_id, source_key)
);
GO

IF OBJECT_ID('stg_xray_tests', 'U') IS NULL
CREATE TABLE stg_xray_tests (
    id         BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id     UNIQUEIDENTIFIER NOT NULL,
    source_key NVARCHAR(100)    NOT NULL,
    raw_json   NVARCHAR(MAX)    NOT NULL,
    loaded_at  DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_xray_tests UNIQUE (run_id, source_key)
);
GO

IF OBJECT_ID('stg_xray_test_executions', 'U') IS NULL
CREATE TABLE stg_xray_test_executions (
    id         BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id     UNIQUEIDENTIFIER NOT NULL,
    source_key NVARCHAR(100)    NOT NULL,
    raw_json   NVARCHAR(MAX)    NOT NULL,
    loaded_at  DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_xray_test_executions UNIQUE (run_id, source_key)
);
GO

IF OBJECT_ID('stg_xray_test_runs', 'U') IS NULL
CREATE TABLE stg_xray_test_runs (
    id         BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id     UNIQUEIDENTIFIER NOT NULL,
    source_key NVARCHAR(100)    NOT NULL,
    raw_json   NVARCHAR(MAX)    NOT NULL,
    loaded_at  DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_xray_test_runs UNIQUE (run_id, source_key)
);
GO

IF OBJECT_ID('stg_xray_test_step_results', 'U') IS NULL
CREATE TABLE stg_xray_test_step_results (
    id         BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id     UNIQUEIDENTIFIER NOT NULL,
    source_key NVARCHAR(200)    NOT NULL,
    raw_json   NVARCHAR(MAX)    NOT NULL,
    loaded_at  DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_xray_test_step_results UNIQUE (run_id, source_key)
);
GO

IF OBJECT_ID('stg_xray_test_sets', 'U') IS NULL
CREATE TABLE stg_xray_test_sets (
    id         BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id     UNIQUEIDENTIFIER NOT NULL,
    source_key NVARCHAR(100)    NOT NULL,
    raw_json   NVARCHAR(MAX)    NOT NULL,
    loaded_at  DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_xray_test_sets UNIQUE (run_id, source_key)
);
GO

IF OBJECT_ID('stg_xray_preconditions', 'U') IS NULL
CREATE TABLE stg_xray_preconditions (
    id         BIGINT           IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id     UNIQUEIDENTIFIER NOT NULL,
    source_key NVARCHAR(100)    NOT NULL,
    raw_json   NVARCHAR(MAX)    NOT NULL,
    loaded_at  DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_stg_xray_preconditions UNIQUE (run_id, source_key)
);
GO
