# TMR — Test Metrics Repository

QA metrics pipeline that extracts data from **Jira + Xray** into **SQL Server** and surfaces it through **Power BI** dashboards.

```
Jira / Xray  ──►  qa-pipeline (Python)  ──►  SQL Server  ──►  Power BI
               extract → stage → transform        Staging_DB + Reporting_DB
```

---

## Quick links

| I want to… | Go to |
|-----------|-------|
| Install the pipeline from scratch | [Implementation Guide](docs/reference/implementation-guide.md) |
| Build the Power BI dashboards | [Power BI Design Guide](docs/reference/powerbi-design-guide.md) |
| Review governance KPI definitions | [Quality Metric Catalog](docs/reference/quality-metric-catalog.md) |
| Add a Jira project to the pipeline | [How-to: Add a Jira Project](docs/how-to/01-add-jira-project.md) |
| Map custom Jira fields | [How-to: Map Custom Fields](docs/how-to/02-map-custom-fields.md) |
| Run the pipeline manually | [How-to: Run Pipeline Manually](docs/how-to/03-run-pipeline-manually.md) |
| Reset the watermark after a failure | [How-to: Reset Watermark](docs/how-to/04-reset-watermark.md) |
| Add a new report page to Power BI | [How-to: Add Power BI Report Page](docs/how-to/05-add-powerbi-page.md) |
| Add or remove a Power BI user / RLS role | [How-to: Manage RLS Users](docs/how-to/06-manage-rls-users.md) |
| Diagnose a broken pipeline run | [How-to: Troubleshoot the Pipeline](docs/how-to/07-troubleshoot-pipeline.md) |

---

## Architecture at a glance

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Source | Jira Server / DC / Cloud + Xray | Issues, tests, executions, results |
| Pipeline | Python 3.11, httpx, pyodbc, APScheduler | Extract → Stage → Transform |
| Storage | SQL Server 2019+ | `Staging_DB` (raw JSON) + `Reporting_DB` (star schema) |
| Reporting | Power BI Desktop + Report Server | 8 dashboard pages (P1–P8) |

**Default schedule:**
- Delta run every **4 hours** — incremental, watermark-based
- Full load nightly at **01:00 UTC** — re-processes all records

---

## CLI commands

```cmd
qa-full-load       # full extraction + transformation (first run or nightly)
qa-delta           # incremental extraction + transformation
qa-scheduler       # start APScheduler daemon
qa-seed-dates      # seed dim_date table (run once after DB init)
```

---

## Repository layout

```
docs/
  how-to/          ← task-focused guides for day-to-day operations
  reference/       ← full implementation and design guides
src/
  qa_pipeline/
    extractor/     ← Jira + Xray API clients
    staging/       ← staging table writer
    transformer/   ← star-schema upserts
    alerting/      ← Teams webhook + SMTP
    scheduler/     ← APScheduler daemon
    scripts/       ← CLI entry points
config/
  custom_field_map.json   ← Jira custom field → column mappings
scripts/
  init_db.sql      ← full DDL for both databases
tests/             ← unit + integration tests
```
