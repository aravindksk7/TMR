# How-to: Add a Jira Project to the Pipeline

Add a new Jira project so the pipeline extracts its issues, tests, and test runs.

---

## Steps

### 1. Grant the service account access

In Jira, give the `qa-pipeline-svc` service account **Browse Projects** permission on the new project:

1. Open the project → **Project settings → People**.
2. Add `qa-pipeline-svc` with the **Viewer** (or equivalent read-only) role.

### 2. Add the project key to `.env`

Open `C:\Services\qa-pipeline\.env` and append the new project key to `JIRA_PROJECT_KEYS`:

```ini
# Before
JIRA_PROJECT_KEYS=QA,PROJ

# After
JIRA_PROJECT_KEYS=QA,PROJ,NEWKEY
```

### 3. Check custom field coverage

Open `config/custom_field_map.json` and verify the field IDs are valid for the new project.
Custom field IDs are Jira-instance-wide, so if the field already maps correctly no change is needed.

If the new project uses different fields, follow [How-to: Map Custom Fields](02-map-custom-fields.md).

### 4. Run a targeted full load

Extract only the new project without re-processing everything:

```cmd
cd C:\Services\qa-pipeline
.venv\Scripts\activate
qa-full-load --projects NEWKEY
```

> The `--projects` flag overrides `JIRA_PROJECT_KEYS` for this one run only.

### 5. Verify data arrived

```sql
USE Reporting_DB;

-- Check the new project's tests loaded
SELECT COUNT(*) AS tests
FROM dim_test t
JOIN dim_squad s ON t.squad_sk = s.squad_sk
WHERE t.project_key = 'NEWKEY';

-- Check test runs
SELECT COUNT(*) AS test_runs
FROM fact_test_run tr
JOIN dim_test t ON tr.test_sk = t.test_sk
WHERE t.project_key = 'NEWKEY';
```

After the next scheduled delta run the new project will be included automatically.

---

## Rollback

To stop extracting a project, remove its key from `JIRA_PROJECT_KEYS` in `.env`.
Existing data in `Reporting_DB` is **not** deleted automatically — to purge it run:

```sql
-- Remove from staging
DELETE FROM Staging_DB.dbo.stg_jira_issues  WHERE project_key = 'NEWKEY';
DELETE FROM Staging_DB.dbo.stg_xray_tests   WHERE project_key = 'NEWKEY';

-- Cascade delete from reporting (order matters — facts first)
DELETE fr FROM Reporting_DB.dbo.fact_test_run fr
JOIN Reporting_DB.dbo.dim_test t ON fr.test_sk = t.test_sk
WHERE t.project_key = 'NEWKEY';

DELETE FROM Reporting_DB.dbo.dim_test WHERE project_key = 'NEWKEY';
```
