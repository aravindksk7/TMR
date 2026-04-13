# How-to: Reset the Watermark

The pipeline stores a high-water mark for each job so delta runs only extract new/changed records. If a run fails repeatedly, or you need to re-extract a time window, reset the watermark manually.

---

## When to reset

- Delta run reports **0 records extracted** but you know data has changed in Jira.
- The watermark timestamp is in the **future** (clock skew or accidental override).
- You want to **re-extract the last N days** after a transformer bug was fixed.
- A **schema migration** changed how data is stored and old records need reprocessing.

---

## View current watermarks

```sql
USE Staging_DB;

SELECT job_name, last_success_ts, updated_at
FROM pipeline_watermarks
ORDER BY job_name;
```

---

## Reset to a specific point in time

```sql
USE Staging_DB;

-- Reset the delta extractor watermark to 7 days ago
UPDATE pipeline_watermarks
SET last_success_ts = DATEADD(day, -7, SYSUTCDATETIME()),
    updated_at      = SYSUTCDATETIME()
WHERE job_name = 'delta_extractor';
```

Common reset values:

```sql
-- Re-extract last 24 hours
SET last_success_ts = DATEADD(hour, -24, SYSUTCDATETIME())

-- Re-extract last 30 days
SET last_success_ts = DATEADD(day, -30, SYSUTCDATETIME())

-- Re-extract from a specific date
SET last_success_ts = '2024-01-01T00:00:00'
```

---

## Reset for a full re-extraction (all time)

```sql
-- Set watermark to epoch — extracts everything on the next run
UPDATE pipeline_watermarks
SET last_success_ts = '2000-01-01T00:00:00',
    updated_at      = SYSUTCDATETIME()
WHERE job_name = 'delta_extractor';
```

> For a true full re-extraction, use `qa-full-load` instead. The `delta_extractor` watermark
> reset achieves the same result but uses the delta code path (may be slower for very large datasets).

---

## Reset the transformer watermark separately

The transformer has its own watermark that tracks which staging records it has already processed.
If staging has data but `Reporting_DB` is empty or stale:

```sql
UPDATE pipeline_watermarks
SET last_success_ts = DATEADD(day, -7, SYSUTCDATETIME()),
    updated_at      = SYSUTCDATETIME()
WHERE job_name = 'transformer';
```

---

## After resetting

Run the pipeline manually to pick up the reset window:

```cmd
cd C:\Services\qa-pipeline
.venv\Scripts\activate
qa-delta
```

Or trigger a full load if you reset to a very early date:

```cmd
qa-full-load
```

Verify the watermark advanced after a successful run:

```sql
SELECT job_name, last_success_ts FROM Staging_DB.dbo.pipeline_watermarks;
```

---

## Important notes

- The watermark only advances when a run **completes without errors**. If the next run also fails, the watermark stays at the reset value — you will not lose the window.
- Resetting does **not** delete existing data from `Reporting_DB`. Re-extracted records are upserted (existing rows updated, no duplicates created).
