# How-to: Troubleshoot the Pipeline

Diagnose and fix the most common pipeline failures.

---

## Step 1 — Check the run log first

```sql
USE Staging_DB;

SELECT TOP 10
    job_name, status,
    FORMAT(started_at,  'yyyy-MM-dd HH:mm') AS started,
    FORMAT(finished_at, 'yyyy-MM-dd HH:mm') AS finished,
    records_extracted,
    rows_upserted,
    LEFT(ISNULL(error_message, ''), 400) AS error
FROM pipeline_run_log
ORDER BY started_at DESC;
```

The `error_message` column usually identifies the root cause.

---

## Common failures and fixes

### Delta run extracts 0 records

**Symptoms:** `records_extracted = 0`, status = success, but data in Jira changed.

**Diagnose:**
```sql
SELECT job_name, last_success_ts FROM Staging_DB.dbo.pipeline_watermarks;
```

| Finding | Fix |
|---------|-----|
| Watermark is in the future | Reset to a past date — see [How-to: Reset Watermark](04-reset-watermark.md) |
| Watermark is correct but Jira has no updates | Normal — no records to extract |
| Watermark is from weeks ago but 0 records extracted | Jira auth may be failing silently — check logs for 401/403 |

---

### `httpx.HTTPStatusError: 401 Unauthorized`

The `JIRA_AUTH_TOKEN` in `.env` is invalid or expired.

**For Jira Server/DC (Basic auth):**
1. Re-generate the token: re-encode `username:password` in Base64.
   ```powershell
   [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("qa-pipeline-svc:NewPassword"))
   ```
2. Update `JIRA_AUTH_TOKEN=Basic <new-token>` in `.env`.
3. Restart the scheduler service.

**For Jira Cloud (Bearer token):**
1. Go to **Account Settings → Security → API Tokens → Revoke and create new**.
2. Update `JIRA_AUTH_TOKEN=Bearer <new-token>` in `.env`.

---

### `httpx.HTTPStatusError: 403 Forbidden`

The service account lacks permission on a project.

```
Check: Jira → project → Project settings → People → confirm qa-pipeline-svc has Browse Projects
```

---

### `pyodbc.OperationalError: ('08001', ...)` — cannot connect to SQL Server

Check in order:
1. SQL Server is running: `services.msc → SQL Server (MSSQLSERVER)`.
2. TCP/IP is enabled: SQL Server Configuration Manager → Protocols for MSSQLSERVER → TCP/IP = Enabled.
3. Port 1433 is open: `Test-NetConnection -ComputerName SQLSRV01 -Port 1433`.
4. DSN in `.env` uses the correct server name (use `HOST\INSTANCE` for named instances).

---

### `pyodbc.ProgrammingError` — login failed

The SQL login password may have changed:
```sql
ALTER LOGIN qa_pipeline_svc WITH PASSWORD = 'NewPassword';
```
Update `STAGING_DB_DSN` and `REPORTING_DB_DSN` in `.env`.

---

### `pydantic_core.ValidationError` on startup

A required environment variable is missing from `.env`.

```cmd
python -c "from qa_pipeline.settings import PipelineSettings; s = PipelineSettings()"
```

The error output names the missing field. Add it to `.env`.

---

### Transformer writes 0 rows

The transformer only processes staging rows not yet seen. Check:

```sql
-- Is staging populated?
SELECT COUNT(*) FROM Staging_DB.dbo.stg_jira_issues;
SELECT COUNT(*) FROM Staging_DB.dbo.stg_xray_tests;
```

- If staging is empty → the extractor failed. Check `pipeline_run_log` for extractor errors.
- If staging has rows but transformer writes 0 → reset the transformer watermark:

```sql
UPDATE Staging_DB.dbo.pipeline_watermarks
SET last_success_ts = DATEADD(day, -1, SYSUTCDATETIME())
WHERE job_name = 'transformer';
```

Then run `qa-delta` (or `qa-full-load` to reprocess everything).

---

### `ModuleNotFoundError: No module named 'qa_pipeline'`

The package is not installed in the active virtual environment:

```cmd
cd C:\Services\qa-pipeline
.venv\Scripts\activate
pip install -e .
```

---

### `WinError 10060` — Connection timed out (TCP)

**Symptom:** The pipeline exits immediately with an error like:
```
httpx.ConnectError: [WinError 10060] A connection attempt failed because the connected
party did not properly respond after a period of time
```

This means the pipeline server cannot reach Atlassian or Xray Cloud directly and a corporate proxy is required.

**Fix:**

1. Ask your network team for the proxy address and port (e.g. `http://proxy.corp.com:8080`).
2. Add to `.env`:
   ```ini
   HTTP_PROXY=http://proxy.corp.com:8080
   HTTPS_PROXY=http://proxy.corp.com:8080
   # Hosts that should NOT go through the proxy (comma-separated):
   NO_PROXY=localhost,127.0.0.1,sqlsrv01,.corp.com
   ```
3. If the proxy performs TLS inspection, also add the corporate CA bundle:
   ```ini
   SSL_CA_BUNDLE=C:\certs\corporate-ca-bundle.pem
   ```
4. Verify with: `qa-check-connectivity`

> **Important:** Setting `HTTP_PROXY` in Windows System Environment Variables or via `$env:HTTPS_PROXY` in PowerShell is **not sufficient** — the pipeline reads proxy settings from `.env` and applies them explicitly to every HTTP call. Only `.env` is authoritative.

---

### SSL / TLS errors (`SSL Provider`, `certificate verify failed`)

Add `TrustServerCertificate=yes` to the DSN in `.env`:

```ini
STAGING_DB_DSN=DRIVER={ODBC Driver 18 for SQL Server};SERVER=SQLSRV01;...;TrustServerCertificate=yes
```

---

### Scheduler stops triggering jobs

If the `qa-scheduler` Windows Service (NSSM) shows as running but no jobs fire:

1. Check the scheduler log:
   ```cmd
   type C:\Services\qa-pipeline\logs\scheduler-err.log
   ```
2. Check APScheduler's job store in `Staging_DB` — if the `apscheduler_jobs` table is corrupted, drop and recreate:
   ```sql
   USE Staging_DB;
   DROP TABLE IF EXISTS apscheduler_jobs;
   ```
   Then restart the service. APScheduler recreates the table and reschedules jobs from `.env` cron settings.
3. Verify the system clock is correct — APScheduler uses UTC.

---

### Xray Cloud GraphQL returns zero test runs or HTTP 400/422

**Symptoms:** `records_extracted = 0` for `xray_test_run`, or the log shows:
```
xray_cloud.extract_test_runs_failed error="... 400 Bad Request ..."
```

**Likely causes and fixes:**

| Symptom | Cause | Fix |
|---------|-------|-----|
| All Xray entities return 0, not just test runs | Wrong `XRAY_BASE_URL` — the path `/api/v2` must **not** be included in the base URL | Set `XRAY_BASE_URL=https://xray.cloud.getxray.app` (host only, no path suffix) |
| GraphQL error "Unknown argument `projectKey`" | Your Xray version uses `projectId` as the argument name (standard for Xray DC and current SaaS) | Already the default in this pipeline — confirm `src/qa_pipeline/extractor/xray.py` queries use `projectId:` |
| GraphQL error "Unknown argument `testExecIssueId`" | API expects the plural array form `testExecIssueIds` | Already the default — confirm `_GQL_TEST_RUNS` uses `testExecIssueIds: [$testExecIssueId]` |
| Auth error `401` on GraphQL calls only | JWT has expired mid-run | Pipeline auto-refreshes tokens; if the error is persistent, verify `XRAY_CLIENT_ID` / `XRAY_CLIENT_SECRET` are current |

**Quick verification** — run the connectivity check to confirm Xray auth and a basic GraphQL ping succeed before a full load:

```cmd
qa-check-connectivity
```

---

## Escalation checklist

If none of the above resolves the issue, collect the following before escalating:

1. Last 5 rows from `pipeline_run_log` (full `error_message`).
2. Current watermarks from `pipeline_watermarks`.
3. Output of `pip show qa-pipeline` (version).
4. The last 100 lines from the scheduler log.
5. SQL Server error log: SSMS → Management → SQL Server Logs → Current.
