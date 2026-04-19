# Manual PBIX Creation Guide - QA Pipeline Semantic Model

## Status

✅ **Semantic model is 100% complete and backed up**
- Location: `c:\TM_PBI\qa_pipeline\powerbi\semantic-model-pbix-backup\definition\`
- Contains: All 14 tables, 12 relationships, 22 measures
- TMDL files verified and present

❌ **Challenge:** UI automation for saving PBIX via Power BI Desktop's keyboard shortcuts has proven unreliable due to dialog timing issues.

**Solution:** Use manual steps below (takes 2-3 minutes)

---

## Manual Steps to Create PBIX File

### Step 1: Open Power BI Desktop
1. Launch Power BI Desktop
2. Wait for it to fully load (blank report should appear)

### Step 2: Create a New PBIX and Save It
1. **File → Save As**
2. **Location:** `c:\TM_PBI\qa_pipeline\`
3. **Filename:** `QA-Pipeline-Report`
4. **Format:** Power BI Report (*.pbix)
5. **Click Save**

The file will be created as an empty PBIX.

### Step 3: Import the Semantic Model
Now we'll populate this PBIX with the complete model using Power BI Desktop's folder import feature.

**Manual approach:**
1. In Power BI Desktop, go to **File → Open**
2. Navigate to: `c:\TM_PBI\qa_pipeline\powerbi\semantic-model-pbix-backup\definition\`
3. Select the folder
4. Power BI should detect it as a model definition and import it

**If that doesn't work, alternative:**
1. Go to **Model view** (left panel)
2. **New Source → More → Blank Query**
3. Or use **Get Data → Other Sources → Folder**  
4. Point to the backup definition folder

### Step 4: Save the PBIX with Model
1. **File → Save** (Ctrl+S)
2. Wait for the save to complete

---

##Alternative: Direct TMDL Import via MCP (Automated)

If you want to try the automated approach again:

```powershell
# 1. Connect to local Power BI instance
# 2. Import TMDL directly
Invoke-RestMethod -Uri "http://localhost:9000/Model/Import" -Method Post -Body @{
    tmdlPath = "c:\TM_PBI\qa_pipeline\powerbi\semantic-model-pbix-backup\definition"
}
# 3. Save via File menu
```

---

## File Structure Reference

Your complete model exists at:
```
c:\TM_PBI\qa_pipeline\powerbi\semantic-model-pbix-backup\definition\
├── database.tmdl                    # Database metadata
├── model.tmdl                       # Model configuration
├── relationships.tmdl               # All 12 relationships
├── tables/                          # 14 table definitions
│   ├── dim_program.tmdl
│   ├── dim_date.tmdl
│   ├── dim_squad.tmdl
│   ├── dim_release.tmdl
│   ├── dim_test_type.tmdl
│   ├── dim_issue.tmdl
│   ├── dim_defect.tmdl
│   ├── dim_test.tmdl
│   ├── dim_test_plan.tmdl
│   ├── dim_test_execution.tmdl
│   ├── bridge_squad_user.tmdl
│   ├── fact_test_run.tmdl
│   ├── fact_test_step_result.tmdl
│   └── fact_requirement_coverage.tmdl
└── cultures/en-US.tmdl              # Localization
```

---

## Model Verification

The model in this TMDL backup contains:

| Component | Count | Status |
|-----------|-------|--------|
| Dimension Tables | 11 | ✓ |
| Fact Tables | 3 | ✓ |
| Relationships | 12 | ✓ (11 active, 1 inactive) |
| Measures | 22 | ✓ |
| Total Columns | ~120 | ✓ |

---

## Quick Reference: What's in Each Table

### Dimensions (for filtering and grouping)
- `dim_program` - Programs (3 cols)
- `dim_date` - Calendar (13 cols)
- `dim_squad` - Squad names (3 cols)
- `dim_release` - Releases/fix versions (5 cols)
- `dim_test_type` - Manual/Cucumber/Generic (2 cols)
- `dim_test` - Test definitions (12 cols)
- `dim_test_plan` - Test plans (8 cols)
- `dim_test_execution` - Xray executions (9 cols)
- `dim_issue` - Requirements (13 cols)
- `dim_defect` - Defects (12 cols + 4 measures)
- `bridge_squad_user` - Squad-user mappings (3 cols)

### Facts (for metrics)
- `fact_test_run` - Test runs (12 cols + 14 measures)
- `fact_test_step_result` - Test step details (6 cols)
- `fact_requirement_coverage` - Requirement coverage (11 cols + 4 measures)

---

## Measures Available

### Test Run Metrics (14 total)
Total Runs, Passed Runs, Failed Runs, Blocked Runs
Pass Rate %, Pass Rate (formatted)
Avg Duration (seconds/minutes), Total Test Time (hours)
P1 Target Pass Rate %, Pass Rate % Prior Month
Pass Rate % Change, Pass Rate % Change (formatted)
P1 Pass Rate Status

### Defect Metrics (4 total)
Total Defects, Open Defects, Critical Defects
Open + Critical Defects

### Coverage Metrics (4 total)
Total Requirements, Covered Requirements
Coverage %, Uncovered Requirements

---

## Next Steps After PBIX Creation

1. **Refresh data** (optional): Home → Refresh
   - Requires SQL Server Reporting_DB to be accessible
   - Tables will populate with data

2. **Build report pages** P1-P6 using the guide in `SAVE_AND_USE_PBIX.md`

3. **Configure visuals** with the 22 available measures

4. **Publish** to Power BI Service or Report Server

---

## Support

- Model Reference: [QA_PIPELINE_MODEL_REFERENCE.md](QA_PIPELINE_MODEL_REFERENCE.md)
- Usage Guide: [SAVE_AND_USE_PBIX.md](SAVE_AND_USE_PBIX.md)
- Design Guide: [`docs/powerbi-design-guide.md`](docs/powerbi-design-guide.md)

