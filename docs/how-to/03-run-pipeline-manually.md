# How-to: Run the Pipeline Manually

Trigger a pipeline run outside of the normal schedule — for testing, backfill, or recovery.

---

## Prerequisites

```cmd
cd C:\Services\qa-pipeline
.venv\Scripts\activate
```

---

## Full load

Re-extracts and reprocesses **all records** for all configured projects. Use this after a schema change, a new project addition, or when you suspect data drift.

```cmd
qa-full-load
```

**With a dry run first** (connects and validates, but writes nothing to the database):

```cmd
qa-full-load --dry-run
```

**Restrict to specific projects:**

```cmd
qa-full-load --projects QA,PROJ
```

**Redirect logs to a file:**

```cmd
qa-full-load > logs\manual-full-%DATE%.log 2>&1
```

---

## Delta run

Extracts only records updated since the last successful watermark. Runs faster than a full load.

```cmd
qa-delta
```

**Override the start timestamp** (useful for backfilling a missed window):

```cmd
qa-delta --since 2024-06-01T00:00:00Z
```

**Override the end timestamp** (extract up to a specific point in time, not now):

```cmd
qa-delta --since 2024-06-01T00:00:00Z --until 2024-06-30T23:59:59Z
```

> Note: `--since`/`--until` do **not** update the watermark. The watermark only advances on a run completed without `--since`.

---

## Seed the date dimension

Run once after initial database setup, or to extend the date range:

```cmd
qa-seed-dates --start 2015-01-01 --end 2035-12-31
```

Re-running is safe (MERGE skips existing dates).

---

## Watch progress

Each log line is a JSON object. Pipe through `python` to pretty-print in real time:

```cmd
qa-full-load 2>&1 | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line)
        print(d.get('timestamp',''), d.get('level',''), d.get('event',''), d.get('message',''))
    except:
        print(line, end='')
"
```

Or use the raw log and search for errors after the fact:

```cmd
qa-full-load > logs\run.log 2>&1
findstr /i "error" logs\run.log
```

---

## Verify the run completed

```sql
USE Staging_DB;
SELECT TOP 1
    job_name, status,
    FORMAT(started_at,  'yyyy-MM-dd HH:mm') AS started,
    FORMAT(finished_at, 'yyyy-MM-dd HH:mm') AS finished,
    records_extracted,
    rows_upserted,
    LEFT(ISNULL(error_message, 'OK'), 200) AS result
FROM pipeline_run_log
ORDER BY started_at DESC;
```

`status = 'success'` means the watermark was also advanced.
