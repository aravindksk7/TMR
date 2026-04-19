# Canvas Build Guide - QA Pipeline Dashboard (P1-P8)

Use this guide to build the full Power BI dashboard canvas using the latest semantic model views.

**Template:** `QA-Pipeline-Report.pbit`  
**Saved report:** `QA-Pipeline-Report.pbix`  
**Pages:** P1 QA Health, P2 Defect Density, P3 Requirement Coverage, P4 Execution Trend, P5 Test Type Breakdown, P6 Drill-through Detail, P7 Environment Health, P8 Release Snapshot

---

## 0 - Prerequisites and Setup

### 0.1 Open and connect

1. Open `QA-Pipeline-Report.pbit` from `c:\TM_PBI\qa_pipeline\`.
2. In the SQL credential prompt use:
   - Server: `127.0.0.1,1433`
   - Database: `Reporting_DB`
   - Authentication: Database
3. Complete login and wait for refresh to complete.

### 0.2 Save immediately as PBIX

1. File -> Save As.
2. Save as `QA-Pipeline-Report.pbix` in `c:\TM_PBI\qa_pipeline\`.

### 0.3 Verify latest views are present

In the Fields pane, confirm all page views exist:

- `vw_p1_qa_health_by_release`
- `vw_p2_defect_density`
- `vw_p3_requirement_coverage`
- `vw_p4_execution_trend`
- `vw_p5_test_type_breakdown`
- `vw_p6_test_run_detail`
- `vw_p7_environment_health`
- `vw_p8_release_snapshot`

If any view is missing, refresh metadata before building pages.

---

## 1 - Shared Canvas Pattern (Repeat for Each Page)

Use the same build sequence on every page (similar build cadence as the Xray-style implementation flow):

1. Create and rename page.
2. Paste global slicers.
3. Build KPI strip first.
4. Build main chart(s).
5. Add detail matrix/table.
6. Configure interactions.
7. Validate filters and totals.
8. Save.

### 1.1 Build global slicers once (copy to all non-drillthrough pages)

Create these slicers on P1 and group as `_Global Slicers`:

- Release: `dim_release[release_name]` (Dropdown)
- Squad: `dim_squad[squad_name]` (Dropdown)
- Program: `dim_program[program_name]` (Dropdown)
- Date Range: `dim_date[full_date]` (Between)
- Environment: `dim_environment[environment_name]` (Dropdown)

Formatting baseline:

- Font size: 10
- Slicer title: On
- Slicer background: `#1e2530`

Copy this group to P1-P5, P7, P8.

---

## 2 - P1 QA Health Overview

**Primary view:** `vw_p1_qa_health_by_release`  
**Purpose:** Executive release-level quality health

### 2.1 Create page

1. Add new page.
2. Rename to `P1 - QA Health`.
3. Paste `_Global Slicers`.

### 2.2 Build KPI row

Add cards:

- `vw_p1_qa_health_by_release[P1 Total Runs]`
- `vw_p1_qa_health_by_release[P1 Passed]`
- `vw_p1_qa_health_by_release[P1 Failed]`
- `vw_p1_qa_health_by_release[P1 Blocked]`
- `vw_p1_qa_health_by_release[P1 Pass Rate %]`
- `vw_p1_qa_health_by_release[P1 Automation Rate %]`

### 2.3 Build visuals

1. Stacked column chart:
   - Axis: `vw_p1_qa_health_by_release[release_name]`
   - Values: `P1 Passed`, `P1 Failed`, `P1 Blocked`
2. Pass-rate trend line:
   - Axis: `dim_date[full_date]` (Month)
   - Value: `fact_test_run[Pass Rate %]`
3. Gauge:
   - Value: `vw_p1_qa_health_by_release[P1 Pass Rate %]`
   - Target: `fact_test_run[P1 Target Pass Rate %]`
4. Release summary table:
   - `release_name`, `total_runs`, `passed`, `failed`, `blocked`, `pass_rate_pct`

### 2.4 Validate

- Release and Date slicers update all visuals.
- Pass rate gauge and trend values remain consistent.

---

## 3 - P2 Defect Density

**Primary view:** `vw_p2_defect_density`  
**Purpose:** Defect concentration by status/severity/squad

### 3.1 Create page

1. Add page `P2 - Defect Density`.
2. Paste `_Global Slicers`.

### 3.2 Build KPI row

Add cards:

- `vw_p2_defect_density[P2 Total Defects]`
- `vw_p2_defect_density[P2 Open Defects]`
- `vw_p2_defect_density[P2 Critical Defects]`
- `vw_p2_defect_density[P2 Impacted Runs]`

### 3.3 Build visuals

1. Matrix:
   - Rows: `vw_p2_defect_density[squad_name]`
   - Columns: `vw_p2_defect_density[defect_status]`
   - Values: `vw_p2_defect_density[total_defects]`
2. Severity stacked bar:
   - Axis: `vw_p2_defect_density[squad_name]`
   - Legend: `vw_p2_defect_density[severity]`
   - Values: `vw_p2_defect_density[total_defects]`
3. Priority breakdown chart:
   - Axis: `vw_p2_defect_density[priority]`
   - Value: `vw_p2_defect_density[total_defects]`
4. Defect detail table:
   - `release_name`, `squad_name`, `severity`, `priority`, `defect_status`, `open_defects`, `critical_defects`

### 3.4 Validate

- Squad slicer filters matrix and bars.
- KPI totals match matrix totals.

---

## 4 - P3 Requirement Coverage

**Primary view:** `vw_p3_requirement_coverage`  
**Purpose:** Coverage and requirement gap tracking

### 4.1 Create page

1. Add page `P3 - Requirement Coverage`.
2. Paste `_Global Slicers`.

### 4.2 Build KPI row

Add cards:

- `vw_p3_requirement_coverage[P3 Total Requirements]`
- `vw_p3_requirement_coverage[P3 Covered Requirements]`
- `vw_p3_requirement_coverage[P3 Coverage %]`
- Additional card using column aggregate: `no_coverage_count` (Sum)

### 4.3 Build visuals

1. Coverage status donut:
   - Legend: `vw_p3_requirement_coverage[coverage_status]`
   - Values: Count of `issue_key`
2. Requirement matrix:
   - Rows: `requirement_summary`, `issue_key`
   - Columns: `release_name`
   - Values: `total_test_count`, `passing_test_count`, `failing_test_count`, `blocked_test_count`
3. Squad coverage chart:
   - Axis: `squad_name`
   - Values: `P3 Covered Requirements`, `P3 Total Requirements`
4. Uncovered table (visual filter):
   - Filter `is_covered = FALSE`
   - Show `issue_key`, `requirement_summary`, `priority`, `squad_name`, `release_name`

### 4.4 Validate

- `P3 Coverage %` agrees with table-level covered vs total counts.
- Uncovered table only shows `is_covered = FALSE`.

---

## 5 - P4 Execution Trend

**Primary view:** `vw_p4_execution_trend`  
**Purpose:** Throughput and execution trend performance

### 5.1 Create page

1. Add page `P4 - Execution Trend`.
2. Paste `_Global Slicers`.

### 5.2 Build KPI row

Add cards:

- `vw_p4_execution_trend[P4 Total Runs]`
- `vw_p4_execution_trend[P4 Passed]`
- `vw_p4_execution_trend[P4 Failed]`
- `vw_p4_execution_trend[P4 Avg Duration (s)]`

### 5.3 Build visuals

1. Combo chart:
   - Axis: `run_date`
   - Column values: `passed`, `failed`
   - Optional line: average of `avg_duration_s`
2. Weekly trend chart:
   - Axis: `week_of_year`
   - Values: `total_runs`
3. Release trend chart:
   - Axis: `release_name`
   - Values: `total_runs`, `passed`, `failed`
4. Detailed trend table:
   - `run_date`, `squad_name`, `release_name`, `total_runs`, `passed`, `failed`, `avg_duration_s`

### 5.4 Validate

- Weekly/monthly slicing does not break trend continuity.
- KPI values match aggregated chart totals.

---

## 6 - P5 Test Type Breakdown

**Primary view:** `vw_p5_test_type_breakdown`  
**Purpose:** Quality comparison by test type and squad

### 6.1 Create page

1. Add page `P5 - Test Type Breakdown`.
2. Paste `_Global Slicers`.

### 6.2 Build KPI row

Add cards:

- `vw_p5_test_type_breakdown[P5 Total Runs]`
- `vw_p5_test_type_breakdown[P5 Passed]`
- `vw_p5_test_type_breakdown[P5 Failed]`
- `vw_p5_test_type_breakdown[P5 Pass Rate %]`

### 6.3 Build visuals

1. Pass rate by test type:
   - Axis: `test_type_name`
   - Values: `pass_rate_pct`
2. Squad x test type matrix:
   - Rows: `squad_name`
   - Columns: `test_type_name`
   - Values: `total_runs`, `passed`, `failed`, `blocked`
3. Release comparison chart:
   - Axis: `release_name`
   - Legend: `test_type_name`
   - Values: `total_runs`
4. Detail table:
   - `test_type_name`, `squad_name`, `release_name`, `total_runs`, `passed`, `failed`, `blocked`, `pass_rate_pct`

### 6.4 Validate

- `P5 Pass Rate %` aligns with ratio from `passed/total_runs` at same filter grain.

---

## 7 - P6 Drill-through Detail

**Primary view:** `vw_p6_test_run_detail`  
**Purpose:** Row-level diagnostic drill-through

### 7.1 Create page

1. Add page `P6 - Drill-through Detail`.
2. Do not paste global slicers.
3. Insert Back button.

### 7.2 Configure drill-through fields

Add to Drill-through pane:

- `dim_release[release_name]`
- `dim_squad[squad_name]`
- `dim_test[test_key]`
- Optional: `dim_defect[defect_key]`

### 7.3 Build visuals

1. Context multi-row card:
   - release_name, squad_name, test_key
2. Main detail table from `vw_p6_test_run_detail` columns:
   - `test_run_id`, `test_key`, `test_summary`, `test_type_name`, `execution_key`, `execution_summary`, `environments_json`, `revision`, `release_name`, `squad_name`, `run_status`, `started_at`, `finished_at`, `duration_s`, `executed_by`, `assignee`, `comment`, `defect_count`
3. Status chart:
   - Legend: `run_status`
   - Value: Count of `test_run_id`
4. Step details table from `fact_test_step_result`:
   - `step_order`, `step_status`, `actual_result`, `comment`

### 7.4 Interaction

Set interaction so selecting a run in the main table filters step details.

### 7.5 Validate

- Drill-through opens with expected context.
- Back button returns to source page.

---

## 8 - P7 Environment Health

**Primary view:** `vw_p7_environment_health`  
**Purpose:** Environment reliability and root-cause tracking

### 8.1 Create page

1. Add page `P7 - Environment Health`.
2. Paste `_Global Slicers`.

### 8.2 Build KPI row

Add cards:

- `vw_p7_environment_health[P7 Total Runs]`
- `vw_p7_environment_health[P7 Failed Runs]`
- `vw_p7_environment_health[P7 Blocked Runs]`
- `vw_p7_environment_health[P7 Pass Rate %]`

### 8.3 Build visuals

1. Environment x squad matrix:
   - Rows: `environment_name`
   - Columns: `squad_name`
   - Values: `pass_rate_pct`
2. Weekly blocked trend:
   - Axis: `execution_date`
   - Values: `blocked_runs`
3. Root cause chart:
   - Axis: `root_cause_category`
   - Legend: `environment_name`
   - Values: `failed_runs`
4. Health detail table:
   - `environment_name`, `environment_type`, `criticality`, `release_name`, `squad_name`, `root_cause_name`, `root_cause_category`, `execution_date`, `total_runs`, `failed_runs`, `blocked_runs`, `pass_rate_pct`

### 8.4 Validate

- Environment filter slices matrix and root-cause visuals correctly.
- `P7 Pass Rate %` behaves correctly with low-volume filters.

---

## 9 - P8 Release Snapshot

**Primary view:** `vw_p8_release_snapshot`  
**Purpose:** Snapshot-based release readiness tracking

### 9.1 Create page

1. Add page `P8 - Release Snapshot`.
2. Paste `_Global Slicers`.

### 9.2 Build KPI row

Add cards:

- `vw_p8_release_snapshot[P8 Pass Rate %]`
- `vw_p8_release_snapshot[P8 Coverage Rate %]`
- `vw_p8_release_snapshot[P8 Automation Rate %]`
- `vw_p8_release_snapshot[P8 Open Critical Defects]`

### 9.3 Build visuals

1. Snapshot pass-rate trend:
   - Axis: `snapshot_date`
   - Legend: `release_name`
   - Values: `pass_rate_pct`
2. Execution composition stacked chart:
   - Axis: `release_name`
   - Values: `executed_tests`, `failed_tests`, `blocked_tests`, `not_run_tests`
3. Coverage/automation combo:
   - Axis: `snapshot_date`
   - Values: `covered_requirements`, `total_requirements`, `automated_executions`
4. Snapshot detail table:
   - `snapshot_date`, `release_name`, `release_status`, `squad_name`, `total_tests`, `executed_tests`, `passed_tests`, `failed_tests`, `blocked_tests`, `not_run_tests`, `automated_executions`, `covered_requirements`, `total_requirements`, `open_critical_defects`, `avg_duration_s`

### 9.4 Validate

- Latest snapshot row in table agrees with KPI cards.
- Date slicing keeps rates and raw totals coherent.

---

## 10 - Recommended Visual Theme and Color Mapping

Use consistent colors across all pages:

- Pass: `#4ec77a`
- Fail: `#e05c5c`
- Blocked: `#f0a030`
- Active/Info: `#0078d4`
- Neutral: `#8a8a8a`
- Page background: `#141923`
- Visual card background: `#1e2530`

---

## 11 - Final Validation Checklist

### Model checks

- [ ] All 8 `vw_p*` page views exist in Fields pane.
- [ ] No visual contains unresolved fields.
- [ ] No measure returns unexpected blanks at default filter context.

### Page checks

- [ ] P1 through P8 created and named.
- [ ] P6 drill-through works from at least one source visual.
- [ ] P7 and P8 visuals use the current environment/snapshot columns.

### Interaction checks

- [ ] Global slicers filter all target pages.
- [ ] Edit Interactions reviewed for all complex visuals.
- [ ] Date hierarchy level is intentionally configured per chart.

### Save and publish

1. Save PBIX.
2. Export PDF for review if required.
3. Publish to target workspace/report server.

---

## 12 - Troubleshooting

### Missing view fields after model update

- Reopen the PBIX.
- Refresh model metadata.
- Rebind affected visual fields.

### Slicer does not affect a visual

- Format -> Edit interactions.
- Set slicer interaction to Filter for the target visual.

### Drill-through not visible

- Confirm drill-through fields are in the P6 drill-through bucket.
- Confirm source visual contains at least one matching field.

---

*Guide updated: 2026-04-19*  
*Build helper script: `./build_pbix.ps1`*
