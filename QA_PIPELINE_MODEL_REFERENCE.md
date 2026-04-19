# QA Pipeline Power BI Semantic Model Reference

**Status:** ✓ Model loaded in Power BI Desktop (Ready for canvas creation)  
**Location:** Power BI Desktop instance running on port 31168  
**Model ID:** a5c5b035-97c4-4ec1-a61a-7591741ba450  
**Compatibility Level:** 1600  
**Generated:** 2026-04-18

---

## Overview

Your semantic model is **fully loaded and ready** in Power BI Desktop. All tables, relationships, and measures have been imported from the TMDL definition. You can now create report pages and visuals manually using this model.

### Quick Save Instructions

1. **In Power BI Desktop**, go to **File → Save As**
2. **Choose location:** `c:\TM_PBI\qa_pipeline\`
3. **Filename:** `QA-Pipeline-Report` (or your preferred name)
4. **File type:** Power BI Report (*.pbix)
5. **Click Save**

---

## Model Inventory

### Tables: 14 Total

#### **Dimension Tables** (User-facing filters/attributes)

| Table | Columns | Purpose |
|-------|---------|---------|
| **dim_date** | 13 | Calendar table with year, quarter, month, week, day attributes |
| **dim_program** | 3 | Program names and descriptions |
| **dim_squad** | 3 | Squad names with program association |
| **dim_release** | 5 | Release/fix versions with dates |
| **dim_test_type** | 2 | Test classification (Manual, Cucumber, Generic) |
| **dim_test** | 12 | Test definitions with squad/type associations |
| **dim_test_plan** | 8 | Test plan metadata |
| **dim_test_execution** | 9 | Xray execution records |
| **dim_issue** | 13 | Requirements (Jira issues) with program/squad |
| **dim_defect** | 12 | Defect records with severity/priority/status |
| **bridge_squad_user** | 3 | Squad-to-user role mappings (for RLS) |

#### **Fact Tables** (Transactional/Aggregate data)

| Table | Columns | Measures | Purpose |
|-------|---------|----------|---------|
| **fact_test_run** | 12 | 14 | Individual test execution runs per release |
| **fact_test_step_result** | 6 | — | Test step-level results (drill-through detail) |
| **fact_requirement_coverage** | 11 | 4 | Requirement coverage metrics by release |

---

## Relationships: 12 Total

All relationships use **Many-to-One (M:1)** cardinality with **One-Direction** cross-filtering.

### Fact-to-Dimension

| From | To | Active | Name |
|------|----|----|------|
| `fact_test_run.release_sk` | `dim_release.release_sk` | ✓ | `rel_fact_run_release` |
| `fact_test_run.test_sk` | `dim_test.test_sk` | ✓ | `rel_fact_run_test` |
| `fact_test_run.execution_sk` | `dim_test_execution.execution_sk` | ✓ | `rel_fact_run_execution` |
| `fact_test_step_result.test_run_id` | `fact_test_run.test_run_id` | ✓ | `rel_step_result_run` |
| `fact_requirement_coverage.issue_sk` | `dim_issue.issue_sk` | ✓ | `rel_req_coverage_issue` |
| `fact_requirement_coverage.release_sk` | `dim_release.release_sk` | ✗ | `rel_req_coverage_release` (INACTIVE) |

### Dimension-to-Dimension

| From | To | Active | Name |
|------|----|----|------|
| `dim_test.test_type_sk` | `dim_test_type.test_type_sk` | ✓ | `rel_test_test_type` |
| `dim_test.squad_sk` | `dim_squad.squad_sk` | ✓ | `rel_test_squad` |
| `dim_defect.squad_sk` | `dim_squad.squad_sk` | ✓ | `rel_defect_squad` |
| `dim_issue.squad_sk` | `dim_squad.squad_sk` | ✓ | `rel_issue_squad` |
| `dim_squad.program_sk` | `dim_program.program_sk` | ✓ | `rel_squad_program` |
| `bridge_squad_user.squad_sk` | `dim_squad.squad_sk` | ✓ | `rel_bridge_squad` |

**Note:** `rel_req_coverage_release` is **inactive** to avoid ambiguous paths in requirement coverage analysis.

---

## Measures: 22 Total

All measures are DAX calculations spanning three tables.

### Defect Metrics (dim_defect)
- **Total Defects** — Count of all defects
- **Open Defects** — Count where status ≠ Closed/Resolved
- **Critical Defects** — Count where severity = Critical OR priority = P0/P1
- **Open + Critical Defects** — Sum of Open + Critical (without double-count)

### Test Run Counts (fact_test_run)
- **Total Runs** — Count of all test runs
- **Passed Runs** — Count where run_status = 'Passed'
- **Failed Runs** — Count where run_status = 'Failed'
- **Blocked Runs** — Count where run_status = 'Blocked'

### Pass Rate & Performance (fact_test_run)
- **Pass Rate %** — (Passed Runs / Total Runs) × 100
- **Pass Rate (formatted)** — Pass Rate % with 2 decimal places + "%"
- **Avg Duration (seconds)** — Average of duration_s
- **Avg Duration (minutes)** — Avg Duration (seconds) / 60
- **Total Test Time (hours)** — Sum(duration_s) / 3600

### Period-over-Period (fact_test_run)
- **P1 Target Pass Rate %** — Hard-coded target (typically 95%)
- **Pass Rate % Prior Month** — Pass Rate for previous month's test runs
- **Pass Rate % Change** — (Current Pass Rate - Prior Month) 
- **Pass Rate % Change (formatted)** — Pass Rate % Change with +/- prefix & 1 decimal place
- **P1 Pass Rate Status** — "On Track" / "At Risk" / "Critical" based on target vs. actual

### Coverage Metrics (fact_requirement_coverage)
- **Total Requirements** — Distinct count of issues in coverage fact
- **Covered Requirements** — Count where coverage_status = 'Covered'
- **Coverage %** — (Covered / Total) × 100
- **Uncovered Requirements** — Total - Covered

---

## Recommended Report Pages (P1–P6)

Based on your design guide, create these canvas pages:

1. **P1: QA Health by Release**
   - Use: `dim_release`, `fact_test_run` measures (Pass Rate, Total Runs)
   - Visuals: Card (current pass rate), Matrix (by release/squad), KPI

2. **P2: Defect Density**
   - Use: `dim_release`, `dim_squad`, defect measures
   - Visuals: Scatter (test runs vs. defects), Bar (defect severity)

3. **P3: Requirement Coverage**
   - Use: `dim_release`, `dim_issue`, `fact_requirement_coverage`
   - Visuals: Gauge (coverage %), Table (covered vs. uncovered)

4. **P4: Execution Trend**
   - Use: `dim_date`, `fact_test_run` (time-series)
   - Visuals: Line (runs over time), Area (pass rate trend)

5. **P5: Test Type Breakdown**
   - Use: `dim_test_type`, test run measures
   - Visuals: Pie/Donut (test type distribution), Clustered bar

6. **P6: Test Run Drill-Through**
   - Use: `fact_test_run`, `fact_test_step_result` (detail rows)
   - Visuals: Table (test runs with drill-through to steps)

---

## Data Connection

**Source Database:** SQL Server (Reporting_DB)  
**Server:** 127.0.0.1, 1433  
**Import Mode:** All tables use Import mode (Power Query)

All tables pull from `Reporting_DB` using Power Query expressions. The model is currently in **Unprocessed** state—refresh will populate data once you connect to the live database.

---

## Key Configuration Notes

1. **dim_date is marked as a Date Table** — Enables Power BI time intelligence functions
2. **Display Names:** Consider renaming tables for user-friendly report labels
3. **Hidden Columns:** Foreign keys (e.g., `_sk` columns) should be hidden from report view
4. **RLS Ready:** `bridge_squad_user` table is present for Row-Level Security by squad

---

## Next Steps

1. **Save the PBIX file** (File → Save As)
2. **Refresh the model** (Home → Refresh) to populate data from Reporting_DB
3. **Create report pages** using the measures and dimensions listed above
4. **Configure RLS** using `bridge_squad_user` if needed
5. **Publish** to Power BI Report Server or Power BI Service

---

## Troubleshooting

- **Data not appearing?** Ensure Reporting_DB is accessible from your machine
- **Relationship conflicts?** Check that `rel_req_coverage_release` remains INACTIVE
- **Measures showing errors?** Verify table schema matches the TMDL definition
- **RLS setup?** Use `bridge_squad_user` with email filter on squad membership

---

## Files Reference

- **TMDL Definition:** `powerbi/semantic-model/definition/`
- **Generated Export:** `powerbi/semantic-model-generated/definition/`
- **This Reference:** `QA_PIPELINE_MODEL_REFERENCE.md`

For further details, see:
- `docs/powerbi-design-guide.md` — Full implementation guide
- `docs/how-to/05-add-powerbi-page.md` — Page creation walkthrough

