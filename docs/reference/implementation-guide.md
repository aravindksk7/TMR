# QA Pipeline — On-Premises Implementation Guide

**Audience:** IT Administrator / DevOps Engineer responsible for installing, configuring, and maintaining the QA metrics pipeline in an on-premises environment.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [SQL Server Setup](#3-sql-server-setup)
4. [Python Environment Setup](#4-python-environment-setup)
5. [Pipeline Installation](#5-pipeline-installation)
6. [Configuration](#6-configuration)
7. [Custom Field Mapping](#7-custom-field-mapping)
8. [Database Initialisation](#8-database-initialisation)
9. [First Run — Full Load](#9-first-run--full-load)
10. [Scheduling — Incremental Runs](#10-scheduling--incremental-runs)
11. [Alerting Setup](#11-alerting-setup)
12. [Monitoring and Observability](#12-monitoring-and-observability)
13. [Upgrading](#13-upgrading)
14. [Troubleshooting Reference](#14-troubleshooting-reference)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  On-Premises Network                                                │
│                                                                     │
│  ┌──────────────┐   HTTPS   ┌──────────────────┐                  │
│  │  Jira Server │◄─────────►│                  │                  │
│  │  (or Cloud)  │           │  qa-pipeline      │                  │
│  └──────────────┘           │  Python 3.11      │                  │
│                             │  Windows Service  │                  │
│  ┌──────────────┐   HTTPS   │  or Task Scheduler│                  │
│  │  Xray Plugin │◄─────────►│                  │                  │
│  │  (Server/DC) │           └────────┬─────────┘                  │
│  └──────────────┘                    │ pyodbc                      │
│                                      ▼                             │
│                         ┌────────────────────────┐                 │
│                         │     SQL Server 2019+   │                 │
│                         │  ┌──────────────────┐  │                 │
│                         │  │   Staging_DB     │  │                 │
│                         │  │   (raw JSON)     │  │                 │
│                         │  └──────────────────┘  │                 │
│                         │  ┌──────────────────┐  │                 │
│                         │  │  Reporting_DB    │  │◄── Power BI     │
│                         │  │  (star schema)   │  │    Desktop /    │
│                         │  └──────────────────┘  │    Report Server│
│                         └────────────────────────┘                 │
└──────────────────────────────────────────────────────────���──────────┘
```

**Data flow:**
1. Pipeline extracts Jira issues and Xray test data via REST API (or GraphQL for Xray Cloud).
2. Raw JSON is written to `Staging_DB` staging tables (`stg_*`).
3. Transformer reads staging data and upserts normalised records into `Reporting_DB` dimension and fact tables.
4. Power BI connects to `Reporting_DB` views for dashboard rendering.

**Run schedule (default):**
- **Delta run** every 4 hours — extracts records updated since the last watermark.
- **Full load** nightly at 01:00 UTC — re-processes all records to catch corrections and deletes.

---

## 2. Prerequisites

### 2.1 Server requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Windows Server 2019 | Windows Server 2022 |
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB free | 100 GB (for staging JSON growth) |
| .NET Runtime | 4.8 | 4.8 |

The pipeline server can be the same machine as SQL Server for small installations, or a separate application server.

### 2.2 Software requirements

| Software | Version | Download |
|----------|---------|----------|
| Python | 3.11 or 3.12 | python.org |
| Microsoft ODBC Driver for SQL Server | 18 | Microsoft Download Center |
| SQL Server | 2019 or 2022 | Microsoft |
| SQL Server Management Studio (SSMS) | 19+ | Microsoft Download Center |
| Git (optional) | Latest | git-scm.com |
| Power BI Desktop | Latest | Microsoft Store / Download Center |
| Power BI Report Server | Latest | Microsoft Download Center |

### 2.3 Network requirements

The pipeline server must be able to reach:
- Jira instance: HTTPS port 443 (or custom port)
- Xray REST endpoints: same host as Jira (Server/DC) or `xray.cloud.getxray.app` (Cloud)
- SQL Server: TCP port 1433 (or custom instance port)

Firewall rules needed (outbound from pipeline server):

```
Destination: <jira-host>        Port: 443    Protocol: TCP
Destination: <sql-server-host>  Port: 1433   Protocol: TCP
```

### 2.4 Jira / Xray API credentials

Create a dedicated service account in Jira:

1. In Jira: **Settings → User Management → Create User**
   - Username: `qa-pipeline-svc`
   - Role: **Browse Projects** on all QA-related projects (read-only is sufficient)
2. Generate an API token (Jira Cloud) or use username/password (Jira Server):
   - Cloud: **Account Settings → Security → API Tokens → Create**
   - Server/DC: Use HTTP Basic auth — encode `username:password` in Base64

Keep the token secure. You will need it for the `.env` file in Section 6.

---

## 3. SQL Server Setup

### 3.1 Create the databases

Open SSMS and connect to your SQL Server instance. Run the following:

```sql
-- Create the two pipeline databases
CREATE DATABASE Staging_DB
    COLLATE SQL_Latin1_General_CP1_CI_AS;
GO

CREATE DATABASE Reporting_DB
    COLLATE SQL_Latin1_General_CP1_CI_AS;
GO
```

> **Tip:** Use the same collation as your Jira database if you plan to cross-query.

### 3.2 Create a dedicated SQL login

```sql
-- Create a login with a strong password
CREATE LOGIN qa_pipeline_svc
    WITH PASSWORD = 'StrongP@ssw0rd!',
         DEFAULT_DATABASE = Staging_DB,
         CHECK_POLICY = ON,
         CHECK_EXPIRATION = OFF;  -- disable expiry for service accounts
GO

-- Staging_DB: needs read + write access
USE Staging_DB;
CREATE USER qa_pipeline_svc FOR LOGIN qa_pipeline_svc;
ALTER ROLE db_datareader ADD MEMBER qa_pipeline_svc;
ALTER ROLE db_datawriter  ADD MEMBER qa_pipeline_svc;
-- MERGE requires ALTER TABLE permission on target
GRANT ALTER ON SCHEMA::dbo TO qa_pipeline_svc;
GO

-- Reporting_DB: read + write for transformer
USE Reporting_DB;
CREATE USER qa_pipeline_svc FOR LOGIN qa_pipeline_svc;
ALTER ROLE db_datareader ADD MEMBER qa_pipeline_svc;
ALTER ROLE db_datawriter  ADD MEMBER qa_pipeline_svc;
GRANT ALTER ON SCHEMA::dbo TO qa_pipeline_svc;
GO
```

### 3.3 Create a Power BI read-only login

```sql
-- Separate login for Power BI Report Server (read-only)
CREATE LOGIN powerbi_svc
    WITH PASSWORD = 'PBIRead@Only1',
         CHECK_POLICY = ON,
         CHECK_EXPIRATION = OFF;
GO

USE Reporting_DB;
CREATE USER powerbi_svc FOR LOGIN powerbi_svc;
ALTER ROLE db_datareader ADD MEMBER powerbi_svc;
GO
```

### 3.4 Enable TCP/IP in SQL Server Configuration Manager

1. Open **SQL Server Configuration Manager**.
2. Expand **SQL Server Network Configuration → Protocols for MSSQLSERVER**.
3. Right-click **TCP/IP → Enable**.
4. Under **IP Addresses**, set **TCP Port** to `1433` in the `IPAll` section.
5. Restart the SQL Server service.

### 3.5 (Optional) Enable SQL Server Agent for scheduled jobs

If you prefer SQL Server Agent over Windows Task Scheduler:

```sql
-- Enable SQL Server Agent
EXEC sp_configure 'show advanced options', 1;
RECONFIGURE;
EXEC sp_configure 'Agent XPs', 1;
RECONFIGURE;
```

---

## 4. Python Environment Setup

### 4.1 Install Python 3.11

1. Download Python 3.11 installer from [python.org](https://www.python.org/downloads/).
2. Run installer — check **"Add Python to PATH"** and **"Install for all users"**.
3. Verify:

```cmd
python --version
# Python 3.11.x
```

### 4.2 Install Microsoft ODBC Driver 18

Download **Microsoft ODBC Driver 18 for SQL Server** from the Microsoft Download Center and install. Verify:

```cmd
python -c "import pyodbc; print(pyodbc.drivers())"
# Should list: ['ODBC Driver 18 for SQL Server', ...]
```

### 4.3 Create a virtual environment

Use a dedicated service directory. Example: `C:\Services\qa-pipeline\`

```cmd
mkdir C:\Services\qa-pipeline
cd C:\Services\qa-pipeline

python -m venv .venv
.venv\Scripts\activate
```

---

## 5. Pipeline Installation

### 5.1 Copy files to the service directory

Copy the entire `qa_pipeline` project folder to `C:\Services\qa-pipeline\`:

```
C:\Services\qa-pipeline\
  .venv\
  src\
  config\
  scripts\
  tests\
  docs\
  pyproject.toml
  .env          ← you create this from .env.example
```

### 5.2 Install Python dependencies

With the virtual environment activated:

```cmd
cd C:\Services\qa-pipeline
.venv\Scripts\activate
pip install -e .
```

Verify the CLI scripts installed:

```cmd
qa-full-load --help
qa-delta --help
qa-seed-dates --help
```

---

## 6. Configuration

### 6.1 Create the `.env` file

Copy `.env.example` to `.env` and fill in all values:

```cmd
copy .env.example .env
notepad .env
```

Complete `.env` reference:

```ini
# ── Jira / Xray ─────────────────────────────────────────────────────��─────────
# Your Jira base URL (no trailing slash)
JIRA_BASE_URL=https://jira.yourcompany.com

# Xray base URL — same as Jira for Server/DC
XRAY_BASE_URL=https://jira.yourcompany.com

# Auth token:
#   Jira Server/DC: Basic <base64(username:password)>
#     e.g. Basic cWEtcGlwZWxpbmU6bXlwYXNzd29yZA==
#   Jira Cloud:     Bearer <api-token>
JIRA_AUTH_TOKEN=Basic cWEtcGlwZWxpbmU6bXlwYXNzd29yZA==

# "server" for Xray Server/DC, "cloud" for Xray Cloud
XRAY_VARIANT=server

# Comma-separated list of Jira project keys to include
JIRA_PROJECT_KEYS=QA,PROJ,PLATFORM

# ── SQL Server ────────────────────────────────────────────────────────────────
STAGING_DB_DSN=DRIVER={ODBC Driver 18 for SQL Server};SERVER=SQLSRV01\MSSQLSERVER;DATABASE=Staging_DB;UID=qa_pipeline_svc;PWD=StrongP@ssw0rd!;TrustServerCertificate=yes
REPORTING_DB_DSN=DRIVER={ODBC Driver 18 for SQL Server};SERVER=SQLSRV01\MSSQLSERVER;DATABASE=Reporting_DB;UID=qa_pipeline_svc;PWD=StrongP@ssw0rd!;TrustServerCertificate=yes
SCHEDULER_DB_URL=mssql+pyodbc://qa_pipeline_svc:StrongP%40ssw0rd!@SQLSRV01\MSSQLSERVER/Staging_DB?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes

# ── Extraction tuning ─────────────────────────────────────────────────────────
MAX_RESULTS_PER_PAGE=100
RATE_LIMIT_RETRY_MAX=5
RATE_LIMIT_BACKOFF_BASE_MS=1000

# Comma-separated project keys (duplicates JIRA_PROJECT_KEYS — keep consistent)
JIRA_PROJECT_KEYS=QA,PROJ,PLATFORM

# ── Custom field map path ─────────────────────────────────────────────────────
CUSTOM_FIELD_MAP_PATH=config/custom_field_map.json

# ── Scheduler cron ───────────────────────────��────────────────────────────────
EXTRACTOR_CRON_HOUR=*/4      # delta run every 4 hours
FULL_LOAD_CRON_HOUR=1        # full load at 01:00 UTC nightly

# ── Alerting (optional — leave blank to disable) ──────────────────────────────
# Teams webhook:
# ALERT_WEBHOOK_URL=https://yourorg.webhook.office.com/webhookb2/...

# SMTP email:
# ALERT_SMTP_HOST=smtp.yourcompany.com
# ALERT_SMTP_PORT=587
# ALERT_SMTP_USER=pipeline@yourcompany.com
# ALERT_SMTP_PASSWORD=smtppassword
# ALERT_SMTP_FROM=pipeline@yourcompany.com
# ALERT_SMTP_TO=qa-team@yourcompany.com,manager@yourcompany.com
```

> **Security note:** Restrict permissions on `.env` so only the service account can read it:
> ```cmd
> icacls .env /inheritance:r /grant "DOMAIN\qa-pipeline-svc:(R)"
> ```

### 6.2 How to generate a Base64 token (Jira Server/DC)

In PowerShell:

```powershell
$cred = "qa-pipeline-svc:MyPassword123"
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($cred))
# Output: cWEtcGlwZWxpbmUtc3ZjOk15UGFzc3dvcmQxMjM=
```

Then set: `JIRA_AUTH_TOKEN=Basic cWEtcGlwZWxpbmUtc3ZjOk15UGFzc3dvcmQxMjM=`

### 6.3 Verify the connection string

Test the SQL Server connection manually:

```cmd
python -c "
import pyodbc, os
dsn = 'DRIVER={ODBC Driver 18 for SQL Server};SERVER=SQLSRV01;DATABASE=Staging_DB;UID=qa_pipeline_svc;PWD=StrongP@ssw0rd!;TrustServerCertificate=yes'
conn = pyodbc.connect(dsn)
print('Connected:', conn.getinfo(pyodbc.SQL_SERVER_NAME))
conn.close()
"
```

---

## 7. Custom Field Mapping

### 7.1 Discover your Jira custom field IDs

Jira custom field IDs (e.g. `customfield_10200`) are **instance-specific**. You must discover them for your Jira instance before the pipeline can extract program names, squad names, and Xray-specific fields.

**Option A — REST API:**

```powershell
$headers = @{ Authorization = "Basic <your-base64-token>" }
$response = Invoke-RestMethod `
    -Uri "https://jira.yourcompany.com/rest/api/3/field" `
    -Headers $headers
$response | Where-Object { $_.custom -eq $true } |
    Select-Object id, name | Format-Table -AutoSize
```

This returns a table like:

```
id                   name
--                   ----
customfield_10100    Test Type
customfield_10101    Test Repository Path
customfield_10200    Program Name
customfield_10201    Squad/Team
customfield_10300    Test Environments
customfield_10301    Test Plan
customfield_10302    Revision
```

**Option B — Jira UI:**
1. Open a test issue in Jira.
2. Press **F12 → Network** and filter for `issue/`.
3. Find your field in the JSON response — the key is the `customfield_XXXXX` ID.

### 7.2 Update `config/custom_field_map.json`

Edit `config/custom_field_map.json` and replace the placeholder IDs with your real ones:

```jsonc
{
  "_comment": "Map Jira custom field IDs to reporting schema columns.",
  "mappings": [
    {
      "source_field_id": "customfield_10200",   // ← replace with your Program Name field ID
      "logical_name":    "program_name",
      "target_table":    "dim_program",
      "target_column":   "program_name",
      "entity_type":     "jira_issue",
      "field_type":      "string"
    },
    {
      "source_field_id": "customfield_10201",   // ← replace with your Squad/Team field ID
      "logical_name":    "squad_name",
      "target_table":    "dim_squad",
      "target_column":   "squad_name",
      "entity_type":     "jira_issue",
      "field_type":      "string"
    },
    {
      "source_field_id": "customfield_10100",   // ← Xray Test Type (select)
      "logical_name":    "test_type",
      "target_table":    "dim_test",
      "target_column":   "test_type_sk",
      "entity_type":     "xray_test",
      "field_type":      "select_value"
    }
    // ... other mappings
  ]
}
```

**Field type reference:**

| `field_type` | What it extracts | Example Jira payload |
|-------------|-----------------|----------------------|
| `string` | Plain text value | `"Platform Alpha"` |
| `select_value` | `.value` from single-select | `{"value": "Manual", "id": "10001"}` |
| `array` | JSON array of values | `[{"value": "Staging"}, {"value": "Prod"}]` |
| `json` | Full JSON blob (e.g. test steps) | `[{"step": "...", "result": "..."}]` |
| `issue_key` | `.key` from issue link | `{"key": "PROJ-42", "id": "10042"}` |

---

## 8. Database Initialisation

Run the DDL scripts once against each database. From the project root:

```cmd
cd C:\Services\qa-pipeline

REM Staging_DB — watermarks, run log, and all stg_* tables
sqlcmd -S SQLSRV01 -U qa_pipeline_svc -P "StrongP@ssw0rd!" ^
       -d Staging_DB -i scripts\init_staging_db.sql -b

REM Reporting_DB — dimension tables, fact tables, views
sqlcmd -S SQLSRV01 -U qa_pipeline_svc -P "StrongP@ssw0rd!" ^
       -d Reporting_DB -i scripts\init_reporting_db.sql -b
```

Verify in SSMS that tables appear under each database.

### 8.1 Seed the dim_date table

```cmd
.venv\Scripts\activate
qa-seed-dates --start 2015-01-01 --end 2035-12-31
```

This inserts one row per calendar day (~7,305 rows). Re-running is safe (MERGE skips existing rows).

### 8.2 Populate bridge_squad_user (for Row-Level Security)

The RLS bridge table controls which Power BI users can see which squads. Populate it from SSMS:

```sql
USE Reporting_DB;
GO

-- Example: assign users to squads
-- Get squad_sk values first
SELECT squad_sk, squad_name FROM dim_squad;

-- Then insert user memberships
INSERT INTO bridge_squad_user (squad_sk, user_email, role)
VALUES
    (1, 'alice@yourcompany.com',   'Squad_Member'),
    (1, 'bob@yourcompany.com',     'Squad_Member'),
    (2, 'charlie@yourcompany.com', 'Squad_Member'),
    (3, 'manager@yourcompany.com', 'Program_Manager'),
    (4, 'director@yourcompany.com','CXO');
GO
```

> Run this after the first full load so `dim_squad` is populated.

---

## 9. First Run — Full Load

The initial run extracts all data from Jira and Xray (no watermark filter).
This may take 30–120 minutes depending on your data volume.

```cmd
cd C:\Services\qa-pipeline
.venv\Scripts\activate

REM Optional: test connectivity first (no DB writes)
qa-full-load --dry-run

REM Actual full load
qa-full-load
```

**What happens:**
1. Connects to Jira and extracts all issues (stories, bugs, epics) for configured projects.
2. Connects to Xray and extracts all tests, test executions, test runs, step results, test sets, and preconditions.
3. Writes raw JSON to all `stg_*` tables in `Staging_DB`.
4. Transforms staging data into dimension and fact tables in `Reporting_DB`.
5. Records run metadata in `pipeline_run_log`.

**Monitor progress:**

The pipeline logs structured JSON to stdout. You can redirect to a file:

```cmd
qa-full-load > logs\full-load-%DATE%.log 2>&1
```

Or watch in real time — each log line is a JSON object with `event`, `timestamp`, and context fields.

**Verify success:**

```sql
-- Check run log
USE Staging_DB;
SELECT TOP 5 job_name, status, started_at, finished_at,
             records_extracted, rows_upserted, error_message
FROM pipeline_run_log
ORDER BY started_at DESC;

-- Check reporting data
USE Reporting_DB;
SELECT COUNT(*) AS test_runs FROM fact_test_run;
SELECT COUNT(*) AS tests      FROM dim_test;
SELECT COUNT(*) AS releases   FROM dim_release;
```

---

## 10. Scheduling — Incremental Runs

Choose **one** of the following scheduling methods.

### Option A — Windows Task Scheduler (recommended for simplicity)

Create two scheduled tasks: delta every 4 hours, full load nightly.

**Task 1 — Delta extraction:**

1. Open **Task Scheduler → Create Task**.
2. **General tab:**
   - Name: `QA Pipeline — Delta`
   - Run whether user is logged on or not
   - Run with highest privileges
   - Configure for: Windows Server 2019/2022
3. **Triggers tab → New:**
   - Daily, starting 00:00
   - Repeat every: 4 hours, for a duration of: 1 day
4. **Actions tab → New:**
   - Program: `C:\Services\qa-pipeline\.venv\Scripts\qa-delta.exe`
   - Start in: `C:\Services\qa-pipeline`
5. **Settings:** Stop if runs longer than 2 hours; do not start new instance if already running.

**Task 2 — Nightly full load:**

Same steps, but:
- Name: `QA Pipeline — Full Load`
- Trigger: Daily at 01:00 (UTC) — no repeat
- Program: `C:\Services\qa-pipeline\.venv\Scripts\qa-full-load.exe`
- Stop if runs longer than 4 hours

**PowerShell equivalent (run as Administrator):**

```powershell
$delta = New-ScheduledTaskAction `
    -Execute "C:\Services\qa-pipeline\.venv\Scripts\qa-delta.exe" `
    -WorkingDirectory "C:\Services\qa-pipeline"

$deltaTriger = New-ScheduledTaskTrigger `
    -RepetitionInterval (New-TimeSpan -Hours 4) `
    -RepetitionDuration (New-TimeSpan -Days 365) `
    -Once -At "00:00"

Register-ScheduledTask `
    -TaskName "QA Pipeline - Delta" `
    -Action $delta `
    -Trigger $deltaTriger `
    -RunLevel Highest `
    -User "DOMAIN\qa-pipeline-svc" `
    -Password "ServiceAcctPassword"

$full = New-ScheduledTaskAction `
    -Execute "C:\Services\qa-pipeline\.venv\Scripts\qa-full-load.exe" `
    -WorkingDirectory "C:\Services\qa-pipeline"

$fullTrigger = New-ScheduledTaskTrigger -Daily -At "01:00"

Register-ScheduledTask `
    -TaskName "QA Pipeline - Full Load" `
    -Action $full `
    -Trigger $fullTrigger `
    -RunLevel Highest `
    -User "DOMAIN\qa-pipeline-svc" `
    -Password "ServiceAcctPassword"
```

### Option B — APScheduler daemon (in-process, persistent job store)

Run the built-in scheduler as a long-running process. Suitable when you want the scheduler to survive reboots via a Windows Service wrapper.

```cmd
qa-scheduler
```

**Wrap as a Windows Service using NSSM:**

1. Download [NSSM](https://nssm.cc/) and copy `nssm.exe` to `C:\Tools\`.
2. Install the service:

```cmd
C:\Tools\nssm.exe install "QA-Pipeline-Scheduler" ^
    "C:\Services\qa-pipeline\.venv\Scripts\qa-scheduler.exe"

C:\Tools\nssm.exe set "QA-Pipeline-Scheduler" AppDirectory ^
    "C:\Services\qa-pipeline"

C:\Tools\nssm.exe set "QA-Pipeline-Scheduler" AppStdout ^
    "C:\Services\qa-pipeline\logs\scheduler.log"

C:\Tools\nssm.exe set "QA-Pipeline-Scheduler" AppStderr ^
    "C:\Services\qa-pipeline\logs\scheduler-err.log"

C:\Tools\nssm.exe set "QA-Pipeline-Scheduler" Start SERVICE_AUTO_START

net start "QA-Pipeline-Scheduler"
```

---

## 11. Alerting Setup

### 11.1 Microsoft Teams webhook

1. In Teams: open the channel → **… → Connectors → Incoming Webhook → Configure**.
2. Give it a name (e.g. "QA Pipeline Alerts") and copy the URL.
3. Add to `.env`:

```ini
ALERT_WEBHOOK_URL=https://yourorg.webhook.office.com/webhookb2/...
```

### 11.2 SMTP email

Add to `.env`:

```ini
ALERT_SMTP_HOST=smtp.yourcompany.com
ALERT_SMTP_PORT=587
ALERT_SMTP_USER=pipeline-alerts@yourcompany.com
ALERT_SMTP_PASSWORD=SmtpPassword
ALERT_SMTP_FROM=pipeline-alerts@yourcompany.com
ALERT_SMTP_TO=qa-lead@yourcompany.com,ops@yourcompany.com
```

Alerts fire when any pipeline job finishes with `status = 'failed'`. The Teams card includes the job name, run ID, records extracted, and first 800 characters of the error.

---

## 12. Monitoring and Observability

### 12.1 Pipeline run log

Query the run log from SSMS at any time:

```sql
USE Staging_DB;

-- Last 10 runs with status
SELECT TOP 10
    job_name,
    status,
    FORMAT(started_at,  'yyyy-MM-dd HH:mm') AS started,
    FORMAT(finished_at, 'yyyy-MM-dd HH:mm') AS finished,
    records_extracted,
    rows_upserted,
    LEFT(ISNULL(error_message, ''), 200) AS error
FROM pipeline_run_log
ORDER BY started_at DESC;

-- Failed runs in last 7 days
SELECT *
FROM pipeline_run_log
WHERE status = 'failed'
  AND started_at >= DATEADD(day, -7, SYSUTCDATETIME())
ORDER BY started_at DESC;
```

### 12.2 Watermarks

```sql
USE Staging_DB;
SELECT job_name, last_success_ts, updated_at
FROM pipeline_watermarks;
```

If the watermark is stale (older than 8 hours for delta), the job is probably failing or not scheduled.

### 12.3 Log files

If you redirected output to files (Task Scheduler or NSSM), logs are at:
```
C:\Services\qa-pipeline\logs\
```

Each log line is JSON — parse with PowerShell:

```powershell
Get-Content .\logs\scheduler.log |
    ForEach-Object { $_ | ConvertFrom-Json } |
    Where-Object { $_.level -eq 'error' } |
    Select-Object timestamp, event, error |
    Format-Table -AutoSize
```

### 12.4 Data quality checks

Run weekly from SSMS to catch drift:

```sql
USE Reporting_DB;

-- Tests with no test runs in last 30 days
SELECT t.test_key, t.summary, t.updated_at
FROM dim_test t
WHERE NOT EXISTS (
    SELECT 1 FROM fact_test_run tr WHERE tr.test_sk = t.test_sk
    AND tr.started_at >= DATEADD(day, -30, SYSUTCDATETIME())
)
ORDER BY t.updated_at DESC;

-- Releases with 0% pass rate (potential data issue)
SELECT * FROM vw_p1_qa_health_by_release
WHERE total_runs > 0 AND pass_rate_pct = 0
ORDER BY release_name;
```

---

## 13. Upgrading

### 13.1 Update Python package

```cmd
cd C:\Services\qa-pipeline
git pull                           # if using git
.venv\Scripts\activate
pip install -e . --upgrade
```

### 13.2 Apply schema changes

If a new version adds database columns:

1. Review the `scripts/init_staging_db.sql` and `scripts/init_reporting_db.sql` changelogs.
2. Apply only the new `ALTER TABLE` statements in SSMS — do **not** re-run the full DDL (it uses `IF NOT EXISTS` guards but `CREATE OR ALTER VIEW` will recreate views).
3. Run a full load after schema changes: `qa-full-load`.

### 13.3 Rolling restart

Since the pipeline is stateless between runs (watermark in DB, no in-memory state), you can:
1. Stop the scheduler service / Task Scheduler tasks.
2. Replace the source files.
3. Restart.

No drain period needed — the next scheduled run picks up from the last watermark.

---

## 14. Troubleshooting Reference

### Error: `ModuleNotFoundError: No module named 'qa_pipeline'`

The package is not installed in the active virtual environment.

```cmd
cd C:\Services\qa-pipeline
.venv\Scripts\activate
pip install -e .
```

### Error: `pyodbc.Error: ('01000', "[01000] [Microsoft][ODBC Driver 18 ...] ...SSL Provider"`

SSL certificate validation failing. Add `TrustServerCertificate=yes` to the DSN in `.env`.

### Error: `pyodbc.OperationalError: ('08001', ...)`

Cannot reach SQL Server. Check:
1. Firewall — TCP 1433 is open between pipeline server and SQL Server.
2. SQL Server Browser service is running (for named instances).
3. TCP/IP protocol is enabled in SQL Server Configuration Manager.
4. Server name in DSN is correct (use `HOST\INSTANCE` for named instances, `HOST,PORT` for non-default ports).

### Error: `httpx.ConnectError` or `httpx.HTTPStatusError: 401`

- `ConnectError`: Jira host unreachable. Check `JIRA_BASE_URL` and network/firewall.
- `401 Unauthorized`: Check `JIRA_AUTH_TOKEN`. Re-generate the API token or verify Base64 encoding.
- `403 Forbidden`: The service account lacks **Browse Projects** permission on one or more projects.

### Error: `pydantic_core.ValidationError` on startup

A required environment variable is missing. Check the `.env` file — all non-optional fields (`JIRA_BASE_URL`, `XRAY_BASE_URL`, `JIRA_AUTH_TOKEN`, `STAGING_DB_DSN`, `REPORTING_DB_DSN`, `SCHEDULER_DB_URL`) must be set.

### Delta run extracting zero records

1. Check the watermark: `SELECT * FROM Staging_DB.dbo.pipeline_watermarks;`
2. If the watermark is in the future, reset it:
   ```sql
   UPDATE Staging_DB.dbo.pipeline_watermarks
   SET last_success_ts = DATEADD(day, -7, SYSUTCDATETIME())
   WHERE job_name = 'delta_extractor';
   ```
3. Run `qa-delta --since 2024-01-01T00:00:00Z` to override for one run.

### Transformer writes 0 rows

The transformer reads from `stg_*` tables. If staging is empty:
1. Verify `qa-full-load` or `qa-delta` completed successfully (`pipeline_run_log`).
2. Check staging counts: `SELECT COUNT(*) FROM Staging_DB.dbo.stg_jira_issues;`
3. If staging has data but transformer writes 0, check the `transformer_watermark` — it may be filtering everything.

### Watermark not advancing

The watermark is only updated on a **fully successful** run. If any step fails (extraction error or transformation error), the watermark stays at its previous value so the next run retries the same window. Check `pipeline_run_log` for the error.

### Power BI shows stale data

1. Check whether the last scheduled refresh succeeded in Power BI Report Server.
2. Verify `pipeline_run_log` shows recent successful runs.
3. If using Import mode, force a manual refresh in Power BI Report Server: **Manage → Refresh History → Refresh Now**.
