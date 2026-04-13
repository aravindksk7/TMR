# How-to: Map Custom Jira Fields

Tell the pipeline how to extract a Jira custom field (e.g. "Squad", "Program", "Test Environment") and which reporting column to store it in.

---

## 1. Find the field ID in your Jira instance

Custom field IDs (`customfield_XXXXX`) are instance-specific. Use the Jira REST API to list them:

**PowerShell:**
```powershell
$headers = @{ Authorization = "Basic <your-base64-token>" }
Invoke-RestMethod `
    -Uri "https://jira.yourcompany.com/rest/api/3/field" `
    -Headers $headers |
Where-Object { $_.custom -eq $true } |
Select-Object id, name |
Format-Table -AutoSize
```

**curl:**
```bash
curl -s -H "Authorization: Basic <token>" \
     https://jira.yourcompany.com/rest/api/3/field \
  | python3 -c "
import sys, json
for f in json.load(sys.stdin):
    if f.get('custom'): print(f['id'], '\t', f['name'])
"
```

Look for your field name in the output and note its ID (e.g. `customfield_10200`).

---

## 2. Choose the correct field_type

| `field_type` | When to use | Example Jira payload |
|-------------|-------------|---------------------|
| `string` | Plain text or number | `"Platform Alpha"` |
| `select_value` | Single-select list | `{"value": "Manual", "id": "10001"}` |
| `array` | Multi-select or labels | `[{"value": "Staging"}, {"value": "Prod"}]` |
| `issue_key` | Linked issue reference | `{"key": "PROJ-42", "id": "10042"}` |
| `json` | Structured blob (test steps) | `[{"step": "...", "result": "..."}]` |

To check what your field actually returns, call the Jira issue API and inspect the payload:

```powershell
Invoke-RestMethod `
    -Uri "https://jira.yourcompany.com/rest/api/3/issue/PROJ-1?fields=customfield_10200" `
    -Headers @{ Authorization = "Basic <token>" } |
ConvertTo-Json -Depth 5
```

---

## 3. Add the mapping to custom_field_map.json

Open `config/custom_field_map.json` and add an entry to the `mappings` array:

```jsonc
{
  "source_field_id": "customfield_10200",
  "logical_name":    "program_name",
  "target_table":    "dim_program",
  "target_column":   "program_name",
  "entity_type":     "jira_issue",
  "field_type":      "string"
}
```

**entity_type** options:
- `jira_issue` — fields on Jira issues (stories, bugs, epics)
- `xray_test` — fields on Xray test issues
- `xray_execution` — fields on Xray test execution issues

---

## 4. Add the column to the database (if new)

If the target column does not yet exist in `Reporting_DB`, add it:

```sql
USE Reporting_DB;
ALTER TABLE dim_program ADD program_name NVARCHAR(255) NULL;
```

Do **not** re-run the full DDL — just add the new column.

---

## 5. Test the mapping

Run a single-project full load with verbose logging and inspect the output:

```cmd
qa-full-load --projects QA --log-level DEBUG 2>&1 | findstr "customfield_10200"
```

Then query the result:

```sql
USE Reporting_DB;
SELECT TOP 5 program_name FROM dim_program ORDER BY program_sk DESC;
```

---

## Common mistakes

| Problem | Cause | Fix |
|---------|-------|-----|
| Column always NULL | Wrong `field_type` | Check the raw Jira payload — use `select_value` not `string` for dropdowns |
| `KeyError: customfield_XXXXX` in logs | Field doesn't exist on some issue types | Set `"required": false` in the mapping entry |
| Mapping silently ignored | `entity_type` mismatch | Confirm the field lives on `jira_issue` vs `xray_test` |
