# QA Pipeline — Implementation Guide

Jira Cloud + Xray Cloud → SQL Server → Power BI

---

## Overview

The pipeline extracts QA data from Jira Cloud and Xray Cloud, loads it into a SQL Server
staging layer, transforms it into a dimensional reporting model, and serves it to a Power BI
dashboard. It runs on a schedule (delta every 4 hours, full reload nightly) or on demand.

```
Jira Cloud ──┐
              ├─► Extractor ─► Staging_DB (stg_*) ─► Transformer ─► Reporting_DB ─► Power BI
Xray Cloud ──┘
```

---

## Prerequisites

| Requirement | Minimum version | Notes |
|---|---|---|
| Python | 3.11 | Standard library used for JWT decode, base64, json |
| SQL Server | 2019 or Azure SQL | ODBC Driver 18 required on the host |
| ODBC Driver 18 for SQL Server | 18.x | Microsoft download |
| Jira Cloud | — | Admin access to create an API token |
| Xray Cloud | — | Admin access to create an API Key (client_id + client_secret) |
| Power BI Desktop | — | For report authoring |
| Power BI Service | — | For scheduled refresh and sharing (optional) |

---

## Step 1 — Collect credentials

### 1.1 Jira Cloud API token

1. Log in to Jira Cloud as the service account that will run the pipeline.
2. Go to **Account Settings → Security → API tokens → Create API token**.
3. Give it a descriptive name (e.g. `qa-pipeline`), copy the token value.
4. Base64-encode `email@company.com:api_token_value`:

   **PowerShell:**
   ```powershell
   [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("email@company.com:api_token_value"))
   ```

   **bash / Git Bash:**
   ```bash
   echo -n "email@company.com:api_token_value" | base64
   ```

5. Save the resulting base64 string — this becomes `JIRA_AUTH_TOKEN`.

### 1.2 Xray Cloud API Key

1. Log in to Xray Cloud (https://xray.cloud.getxray.app) with a Jira Cloud admin account.
2. Go to **Xray Settings → API Keys → Create API Key**.
3. Copy both the **Client ID** and the **Client Secret** — they are shown only once.
4. Save as `XRAY_CLIENT_ID` and `XRAY_CLIENT_SECRET`.

### 1.3 Identify Jira project keys

Note the keys for every Jira project containing test-related issues
(e.g. `QA`, `INFRA`, `MOBILE`). These become `JIRA_PROJECT_KEYS`.

---

## Step 2 — Discover Jira custom field IDs

Xray Cloud custom fields have instance-specific IDs. The default config uses placeholder
IDs (`customfield_10200` etc.) that must be updated for your tenant.

Run the following against your Jira Cloud instance:

```
GET https://your-org.atlassian.net/rest/api/3/field
Authorization: Basic <JIRA_AUTH_TOKEN>
```

Or via curl:

```bash
curl -s -u "email@company.com:api_token_value" \
  "https://your-org.atlassian.net/rest/api/3/field" \
  | python -m json.tool | grep -i "program\|squad\|application\|severity\|root"
```

Find the `id` values for:

| Logical name | What to look for in the field name |
|---|---|
| `program_name` | "Program", "Portfolio", "Initiative" |
| `squad_name` | "Squad", "Team", "Feature Team" |
| `application_name` | "Application", "Component Group", "System" |
| `root_cause` | "Root Cause", "Failure Reason" |
| `severity` | "Severity" |
| `business_area` | "Business Area", "Domain" |

Update [config/custom_field_map.json](config/custom_field_map.json) with the correct
`source_field_id` values for each mapping entry.

---

## Step 3 — Set up SQL Server databases

Two databases are required: `Staging_DB` (raw JSON) and `Reporting_DB` (dimensional model).

### 3.1 Create the databases

Run in SSMS or sqlcmd:

```sql
CREATE DATABASE Staging_DB   COLLATE SQL_Latin1_General_CP1_CI_AS;
CREATE DATABASE Reporting_DB COLLATE SQL_Latin1_General_CP1_CI_AS;
```

### 3.2 Initialise Staging_DB

```
sqlcmd -S <server> -d Staging_DB -i scripts/init_staging_db.sql
```

Creates:
- `pipeline_watermarks` — tracks last successful extraction timestamp per job
- `pipeline_run_log` — execution history and error log
- `stg_jira_issues`, `stg_jira_defects`, `stg_jira_versions`
- `stg_xray_tests`, `stg_xray_test_executions`, `stg_xray_test_plans`
- `stg_xray_test_runs`, `stg_xray_test_step_results`, `stg_xray_test_sets`, `stg_xray_preconditions`

### 3.3 Initialise Reporting_DB

```
sqlcmd -S <server> -d Reporting_DB -i scripts/init_reporting_db.sql
```

Creates all dimension and fact tables plus 8 reporting views (P1–P8):

| Table/View | Purpose |
|---|---|
| `dim_date` | Calendar dimension, seeded separately |
| `dim_program` / `dim_application` / `dim_squad` | Organisational hierarchy |
| `dim_release` | Jira versions mapped to releases |
| `dim_test` / `dim_test_type` / `dim_test_execution` | Xray test metadata |
| `dim_tester` / `dim_status` / `dim_root_cause` / `dim_environment` | Lookup dimensions |
| `dim_defect` / `dim_issue` | Defect and requirement tracking |
| `fact_test_run` | Grain: one row per test run per release |
| `fact_test_step_result` | Step-level results |
| `fact_requirement_coverage` | Requirements × releases |
| `fact_defect_link` | Defect ↔ test run bridge |
| `fact_cycle_snapshot` | Nightly aggregated snapshot |
| `vw_p1_qa_health_by_release` through `vw_p8_release_snapshot` | Pre-built report views |

### 3.4 Upgrade existing Reporting_DB (if updating an existing installation)

```
sqlcmd -S <server> -d Reporting_DB -i scripts/upgrade_reporting_db.sql
```

This script is idempotent and safe to re-run. It adds any columns and tables
introduced after the initial install.

### 3.5 Seed dim_date

```bash
qa-seed-dates --start 2018-01-01 --end 2035-12-31
```

Populates `dim_date` with one row per calendar day. English month and day names
are hardcoded in the script regardless of system locale. Re-running will also
correct any rows where `month_name` or `day_name` were stored in a non-English format.

---

## Step 4 — Install the Python package

### 4.1 Create a virtual environment

```bash
cd qa_pipeline
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
```

### 4.2 Install

```bash
pip install -e .
# For development (tests, linting, type checking)
pip install -e ".[dev]"
```

This registers the following CLI commands:

| Command | Purpose |
|---|---|
| `qa-check-connectivity` | Validate credentials and network before first run |
| `qa-full-load` | Full extraction + transformation (use for initial load) |
| `qa-delta` | Incremental extraction + transformation |
| `qa-seed-dates` | Populate or repair dim_date |
| `qa-scheduler` | Start the background scheduler (runs both jobs on a cron) |

---

## Step 5 — Configure the environment

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```ini
# Jira Cloud
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_AUTH_TOKEN=<base64 of email:api_token>  # from Step 1.1
JIRA_API_VERSION=3
JIRA_PROJECT_KEYS=QA,INFRA,MOBILE            # comma-separated, no spaces

# Xray Cloud
XRAY_BASE_URL=https://xray.cloud.getxray.app
XRAY_VARIANT=cloud
XRAY_CLIENT_ID=<client_id>                   # from Step 1.2
XRAY_CLIENT_SECRET=<client_secret>           # from Step 1.2

# SQL Server
STAGING_DB_DSN=DRIVER={ODBC Driver 18 for SQL Server};SERVER=<host>;DATABASE=Staging_DB;AutoCommit=True;
REPORTING_DB_DSN=DRIVER={ODBC Driver 18 for SQL Server};SERVER=<host>;DATABASE=Reporting_DB;AutoCommit=True;
SCHEDULER_DB_URL=mssql+pyodbc://<host>/Staging_DB?driver=ODBC+Driver+18+for+SQL+Server

# Schedule
EXTRACTOR_CRON_HOUR=*/4    # delta run every 4 hours
FULL_LOAD_CRON_HOUR=1      # full reload at 01:00 UTC
```

**Windows authentication (no SQL login):** append `Trusted_Connection=yes;` to the DSN strings
and omit `UID`/`PWD`.

**SQL login:** append `UID=<login>;PWD=<password>;` to the DSN strings.

---

## Step 6 — Verify connectivity

Before running the pipeline, confirm all three endpoints are reachable:

```bash
qa-check-connectivity
```

Expected output:

```
--- Jira Cloud ---
  [PASS] Jira Cloud authenticated as: Service Account Name

--- Xray Cloud authentication ---
  [PASS] Xray Cloud auth: JWT obtained, expires in 23.9h

--- Xray Cloud GraphQL ---
  [PASS] Xray Cloud GraphQL: reachable and responding

All connectivity checks passed.
```

**Common failures:**

| Error | Cause | Fix |
|---|---|---|
| HTTP 401 Jira | Wrong base64 encoding or expired token | Re-encode `email:token`, regenerate the Jira API token |
| HTTP 401 Xray | Wrong client_id or client_secret | Regenerate the Xray Cloud API Key |
| HTTP 403 Jira | Service account lacks project permission | Add the account to the Jira project(s) |
| Connection refused / timeout | Firewall blocking outbound HTTPS | Allow outbound 443 to `*.atlassian.net` and `xray.cloud.getxray.app` |
| SSL error | Corporate proxy intercepting TLS | Set `SSL_CERT_FILE=C:/certs/corporate-ca-bundle.pem` in `.env` |

---

## Step 7 — Run the initial full load

```bash
qa-full-load
```

This performs, in order:

1. **Jira extraction** — fetches all issues (stories, epics, bugs) from all configured projects
2. **Xray extraction** — fetches tests, test executions, test plans, and test runs (including step results) via GraphQL
3. **Staging write** — upserts raw JSON into `stg_*` tables in `Staging_DB`
4. **Transformation** — maps staging JSON into dimension/fact tables in `Reporting_DB`
5. **Cycle snapshot** — builds today's aggregate row in `fact_cycle_snapshot`

Typical runtime: 5–30 minutes depending on data volume.

To extract and stage only (skip transformation), use:

```bash
qa-full-load --dry-run
```

---

## Step 8 — Verify the data load

Run in SSMS against `Reporting_DB`:

```sql
-- Row counts across key tables
SELECT 'dim_date'           AS tbl, COUNT(*) AS rows FROM dim_date
UNION ALL
SELECT 'dim_release',              COUNT(*) FROM dim_release
UNION ALL
SELECT 'dim_test',                 COUNT(*) FROM dim_test
UNION ALL
SELECT 'fact_test_run',            COUNT(*) FROM fact_test_run
UNION ALL
SELECT 'fact_requirement_coverage',COUNT(*) FROM fact_requirement_coverage
UNION ALL
SELECT 'dim_defect',               COUNT(*) FROM dim_defect;

-- Check month/day names are English
SELECT TOP 5 full_date, month_name, day_name FROM dim_date ORDER BY 1;

-- Check application names contain no dates
SELECT TOP 20 application_name FROM dim_application ORDER BY 1;

-- Check pipeline run log
SELECT TOP 5 job_name, status, records_extracted, rows_upserted,
             started_at, finished_at, error_message
FROM   pipeline_run_log
ORDER  BY started_at DESC;
```

---

## Step 9 — Start the scheduler

For ongoing incremental updates, start the background scheduler:

```bash
qa-scheduler
```

The scheduler runs two jobs:
- **delta_job** — every 4 hours (configurable via `EXTRACTOR_CRON_HOUR`); extracts only records
  updated since the last successful watermark
- **full_load_job** — daily at 01:00 UTC (configurable via `FULL_LOAD_CRON_HOUR`); full refresh
  to catch any records missed by the delta

Job state is persisted in `Staging_DB` so the scheduler resumes correctly after a restart.

**Run as a Windows Service** (recommended for production):

```powershell
# Install NSSM (Non-Sucking Service Manager) then:
nssm install QAPipelineScheduler "C:\path\to\.venv\Scripts\qa-scheduler.exe"
nssm set QAPipelineScheduler AppDirectory "C:\path\to\qa_pipeline"
nssm set QAPipelineScheduler AppEnvironmentExtra "PYTHONPATH=src"
nssm start QAPipelineScheduler
```

**Run via Docker:**

```bash
docker compose up -d scheduler
```

---

## Step 10 — Connect Power BI

### 10.1 SQL Server connection

1. Open Power BI Desktop.
2. **Get Data → SQL Server**.
3. Server: `<host>`, Database: `Reporting_DB`.
4. Import mode (recommended) or DirectQuery.
5. Select all `vw_p*` views plus `dim_date` for the date table.

### 10.2 Set dim_date as the date table

1. Select the `dim_date` table in the model view.
2. Right-click → **Mark as date table** → choose `full_date`.

### 10.3 Relationships to verify

| From | To | Cardinality |
|---|---|---|
| `fact_test_run.date_sk` | `dim_date.date_sk` | Many→One |
| `fact_test_run.release_sk` | `dim_release.release_sk` | Many→One |
| `fact_test_run.test_sk` | `dim_test.test_sk` | Many→One |
| `fact_test_run.environment_sk` | `dim_environment.environment_sk` | Many→One |
| `fact_test_run.tester_sk` | `dim_tester.tester_sk` | Many→One |
| `fact_test_run.status_sk` | `dim_status.status_sk` | Many→One |
| `fact_test_run.root_cause_sk` | `dim_root_cause.root_cause_sk` | Many→One |
| `fact_defect_link.release_sk` | `dim_release.release_sk` | Many→One |
| `fact_defect_link.defect_sk` | `dim_defect.defect_sk` | Many→One |
| `fact_requirement_coverage.issue_sk` | `dim_issue.issue_sk` | Many→One |
| `fact_requirement_coverage.release_sk` | `dim_release.release_sk` | Many→One |
| `fact_cycle_snapshot.snapshot_date_sk` | `dim_date.date_sk` | Many→One |
| `fact_cycle_snapshot.release_sk` | `dim_release.release_sk` | Many→One |
| `dim_squad.application_sk` | `dim_application.application_sk` | Many→One |
| `dim_squad.program_sk` | `dim_program.program_sk` | Many→One |
| `dim_application.program_sk` | `dim_program.program_sk` | Many→One |

### 10.4 Dashboard pages (P1–P8)

| Page | Source view | Key visuals |
|---|---|---|
| P1 — QA Health by Release | `vw_p1_qa_health_by_release` | KPI cards (Total/Pass/Fail/Blocked), Pass Rate gauge, runs-by-status bar chart, pass rate trend line |
| P2 — Defect Density | `vw_p2_defect_density` | Defects by severity/priority, open vs closed, critical defect count |
| P3 — Requirement Coverage | `vw_p3_requirement_coverage` | Coverage % by squad/release, uncovered requirements list |
| P4 — Execution Trend | `vw_p4_execution_trend` | Daily run volume, pass rate over time, automated vs manual |
| P5 — Test Type Breakdown | `vw_p5_test_type_breakdown` | Manual vs automated vs BDD split |
| P6 — Test Run Detail | `vw_p6_test_run_detail` | Drill-through table, block reason, duration, tester |
| P7 — Environment Health | `vw_p7_environment_health` | Blocked/failed by environment, root cause breakdown |
| P8 — Release Snapshot | `vw_p8_release_snapshot` | Executive summary: coverage rate, automation rate, open critical defects |

### 10.5 Configure scheduled refresh (Power BI Service)

1. Publish the report to a Power BI workspace.
2. Go to the dataset settings → **Gateway and cloud connections**.
3. Set up a Data Gateway (on-premises) pointing to the SQL Server, or use a cloud connection
   if SQL Server is Azure SQL.
4. Configure **Scheduled refresh** to run shortly after the pipeline's nightly full load
   (e.g. 02:00 UTC if the pipeline runs at 01:00 UTC).

---

## Step 11 — Update custom field mappings

If Xray custom field IDs change (e.g. after a tenant migration), update
[config/custom_field_map.json](config/custom_field_map.json) and restart the scheduler.
No code changes are required.

The fields currently mapped:

| `source_field_id` | `logical_name` | Target |
|---|---|---|
| `customfield_10200` | `program_name` | `dim_program.program_name` |
| `customfield_10201` | `squad_name` | `dim_squad.squad_name` |
| `customfield_10202` | `application_name` | `dim_application.application_name` |
| `customfield_10203` | `root_cause` | `dim_root_cause.root_cause_name` |
| `customfield_10204` | `severity` | `dim_defect.severity` |
| `customfield_10205` | `business_area` | `dim_issue.business_area` |
| `customfield_10100` | `test_type` | `dim_test_type.test_type_name` |
| `customfield_10101` | `test_repository_path` | `dim_test.repository_path` |
| `customfield_10300` | `test_environments` | `dim_environment.environment_name` |
| `customfield_10301` | `test_plan_key` | `stg_xray_test_executions.test_plan_key` |
| `customfield_10302` | `revision` | `stg_xray_test_executions.revision` |

---

## Step 12 — Operational runbook

### Force a delta run immediately

```bash
qa-delta
```

### Re-extract from a specific date (override watermark)

```bash
qa-delta --since 2024-06-01T00:00:00Z
```

### Run a dry-run (extract and stage only, no transformation)

```bash
qa-full-load --dry-run
```

### Repair dim_date (re-run to fix any non-English month/day names)

```bash
qa-seed-dates --start 2018-01-01 --end 2035-12-31
```

### Monitor pipeline runs

```sql
SELECT TOP 20
    job_name,
    status,
    records_extracted,
    rows_upserted,
    DATEDIFF(SECOND, started_at, finished_at) AS duration_s,
    error_message,
    started_at
FROM pipeline_run_log
ORDER BY started_at DESC;
```

### Check watermarks

```sql
SELECT job_name, last_success_ts, updated_at
FROM   pipeline_watermarks;
```

### Reset watermark (forces next delta to act as a full re-extract)

```sql
DELETE FROM pipeline_watermarks WHERE job_name = 'delta_extractor';
```

---

## Architecture reference

```
┌──────────────────────────────────────────────────────────────────────┐
│  Extraction layer (extractor/)                                        │
│                                                                       │
│  JiraExtractor                 XrayCloudExtractor                    │
│  ├── GET /rest/api/3/search    ├── POST /api/v2/authenticate          │
│  │   (JQL, cursor pagination)  │   (client_id + client_secret → JWT)  │
│  └── GET /rest/api/3/project/  ├── POST /api/v2/graphql               │
│       {key}/versions           │   getTests, getTestExecutions,        │
│                                │   getTestRuns, getTestPlans           │
│                                └── JWT auto-refresh (60s before exp)  │
└──────────────────────────────────────────────────────────────────────┘
              │
              ▼ StagingRecord (run_id, source_key, entity_type, raw_json)
┌──────────────────────────────────────────────────────────────────────┐
│  Staging layer (staging/)                                             │
│  StagingWriter → MERGE into stg_* tables in Staging_DB               │
│  One table per entity type; keyed on (run_id, source_key)            │
└──────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Transformation layer (transformer/)                                  │
│  Transformer.run()                                                    │
│  ├── stg_jira_versions   → dim_release                               │
│  ├── stg_jira_issues     → dim_program, dim_application,             │
│  │                          dim_squad, dim_issue                      │
│  ├── stg_jira_defects    → dim_defect                                │
│  ├── stg_xray_tests      → dim_test, dim_test_type                   │
│  ├── stg_xray_test_executions → dim_test_execution, dim_environment  │
│  ├── stg_xray_test_runs  → fact_test_run, fact_defect_link,          │
│  │                          dim_tester, dim_status                    │
│  ├── stg_xray_test_step_results → fact_test_step_result              │
│  └── (nightly) → fact_cycle_snapshot                                 │
└──────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Reporting_DB (SQL Server)                                            │
│  vw_p1 … vw_p8  +  vw_qm_quality_effectiveness                      │
└──────────────────────────────────────────────────────────────────────┘
              │
              ▼
      Power BI Desktop / Service
```

---

## Key files reference

| File | Purpose |
|---|---|
| [src/qa_pipeline/extractor/xray.py](src/qa_pipeline/extractor/xray.py) | Xray Cloud GraphQL extractor with JWT auth and auto-refresh |
| [src/qa_pipeline/extractor/jira.py](src/qa_pipeline/extractor/jira.py) | Jira Cloud REST extractor |
| [src/qa_pipeline/extractor/client.py](src/qa_pipeline/extractor/client.py) | Shared HTTP client (retry, pagination, auth) |
| [src/qa_pipeline/transformer/transformer.py](src/qa_pipeline/transformer/transformer.py) | Staging → Reporting transformation logic |
| [src/qa_pipeline/transformer/cf_mapper.py](src/qa_pipeline/transformer/cf_mapper.py) | Custom field ID → logical name mapping |
| [src/qa_pipeline/staging/writer.py](src/qa_pipeline/staging/writer.py) | Upserts raw JSON into stg_* tables |
| [src/qa_pipeline/scripts/check_connectivity.py](src/qa_pipeline/scripts/check_connectivity.py) | Pre-flight connectivity and credential check |
| [src/qa_pipeline/scripts/run_full_load.py](src/qa_pipeline/scripts/run_full_load.py) | Full extraction + transformation entry point |
| [src/qa_pipeline/scripts/run_delta.py](src/qa_pipeline/scripts/run_delta.py) | Incremental extraction + transformation entry point |
| [src/qa_pipeline/scripts/seed_dim_date.py](src/qa_pipeline/scripts/seed_dim_date.py) | Populate / repair dim_date |
| [src/qa_pipeline/scheduler/scheduler.py](src/qa_pipeline/scheduler/scheduler.py) | APScheduler cron setup (delta + full load) |
| [src/qa_pipeline/settings.py](src/qa_pipeline/settings.py) | All configuration via environment variables |
| [config/custom_field_map.json](config/custom_field_map.json) | Jira custom field ID → reporting column mappings |
| [scripts/init_staging_db.sql](scripts/init_staging_db.sql) | Staging_DB DDL |
| [scripts/init_reporting_db.sql](scripts/init_reporting_db.sql) | Reporting_DB DDL + seed data + P1–P8 views |
| [scripts/upgrade_reporting_db.sql](scripts/upgrade_reporting_db.sql) | Idempotent schema upgrade for existing installations |
| [.env.example](.env.example) | Environment variable template |
