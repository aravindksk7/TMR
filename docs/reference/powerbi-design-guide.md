# QA Pipeline — Power BI Design Guide

**Audience:** BI Developer / Report Author responsible for building and publishing the QA metrics dashboards in Power BI Desktop and Power BI Report Server (on-premises).

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Connecting to SQL Server](#2-connecting-to-sql-server)
3. [Data Model — Star Schema](#3-data-model--star-schema)
4. [Core DAX Measures](#4-core-dax-measures)
5. [Report P1 — QA Health by Release](#5-report-p1--qa-health-by-release)
6. [Report P2 — Defect Density](#6-report-p2--defect-density)
7. [Report P3 — Requirement Coverage](#7-report-p3--requirement-coverage)
8. [Report P4 — Execution Trend](#8-report-p4--execution-trend)
9. [Report P5 — Test Type Breakdown](#9-report-p5--test-type-breakdown)
10. [Report P6 — Test Run Drill-Through](#10-report-p6--test-run-drill-through)
11. [Row-Level Security](#11-row-level-security)
12. [Publishing to Power BI Report Server](#12-publishing-to-power-bi-report-server)
13. [Scheduled Refresh](#13-scheduled-refresh)
14. [Troubleshooting](#14-troubleshooting)
15. [Industry-Aligned Quality Metrics](#15-industry-aligned-quality-metrics)

---

## 1. Prerequisites

| Requirement | Notes |
|-------------|-------|
| Power BI Desktop (Report Server version) | Must match your Report Server version — download from the Report Server portal |
| Power BI Report Server | On-premises, licensed via SQL Server Enterprise or Power BI Premium |
| SQL Server access | Use the `powerbi_svc` read-only login created in the Implementation Guide |
| Reporting_DB populated | At least one successful `qa-full-load` run must have completed |

> **Important:** Use the **Power BI Desktop for Power BI Report Server** build, not the regular Desktop. They have different release cadences and the `.pbix` file may be incompatible if you mix them.

---

## 2. Connecting to SQL Server

### 2.1 Create a new Power BI Desktop file

1. Open Power BI Desktop → **Get Data → SQL Server**.
2. Enter connection details:
   - **Server:** `SQLSRV01` (or `SQLSRV01\INSTANCENAME` for named instances)
   - **Database:** `Reporting_DB`
   - **Data Connectivity mode:** `Import` (recommended for all reports up to ~10M rows)
3. Click **Advanced options** and enter:
   ```sql
   -- Leave blank; tables/views are selected in the next step
   ```
4. Click **OK**.

### 2.2 Select tables and views

In the Navigator, select all of the following and click **Load**:

**Dimension tables:**
- `dim_date`
- `dim_program`
- `dim_squad`
- `dim_release`
- `dim_test_type`
- `dim_issue`
- `dim_defect`
- `dim_test`
- `dim_test_plan`
- `dim_test_execution`
- `bridge_squad_user`

**Fact tables:**
- `fact_test_run`
- `fact_test_step_result`
- `fact_requirement_coverage`

**Views (pre-aggregated — use for each specific report page):**
- `vw_p1_qa_health_by_release`
- `vw_p2_defect_density`
- `vw_p3_requirement_coverage`
- `vw_p4_execution_trend`
- `vw_p5_test_type_breakdown`
- `vw_p6_test_run_detail`
- `vw_p7_environment_health`
- `vw_p8_release_snapshot`
- `vw_qm_quality_effectiveness` (governance scorecard)

> **Tip:** Load both the base tables and the views. Base tables power cross-page slicers (Release, Squad, Date). Views power the individual report visuals — they are already aggregated and optimise query performance.

### 2.3 Credential configuration

When prompted for credentials:
- Authentication method: **Database**
- Username: `powerbi_svc`
- Password: `PBIRead@Only1` (or the password set in the Implementation Guide)
- Privacy level: **Organisational**

---

## 3. Data Model — Star Schema

### 3.1 Define relationships

After loading, open **Model view** and create the following relationships. All are single-direction (→) unless noted.

| From table | From column | To table | To column | Cardinality |
|------------|-------------|----------|-----------|-------------|
| `fact_test_run` | `test_sk` | `dim_test` | `test_sk` | Many → One |
| `fact_test_run` | `execution_sk` | `dim_test_execution` | `execution_sk` | Many → One |
| `fact_test_run` | `release_sk` | `dim_release` | `release_sk` | Many → One |
| `fact_test_step_result` | `test_run_id` | `fact_test_run` | `test_run_id` | Many → One |
| `fact_requirement_coverage` | `issue_sk` | `dim_issue` | `issue_sk` | Many → One |
| `fact_requirement_coverage` | `release_sk` | `dim_release` | `release_sk` | Many → One |
| `dim_test` | `test_type_sk` | `dim_test_type` | `test_type_sk` | Many → One |
| `dim_test` | `squad_sk` | `dim_squad` | `squad_sk` | Many → One |
| `dim_issue` | `squad_sk` | `dim_squad` | `squad_sk` | Many → One |
| `dim_issue` | `program_sk` | `dim_program` | `program_sk` | Many → One |
| `dim_squad` | `program_sk` | `dim_program` | `program_sk` | Many → One |
| `bridge_squad_user` | `squad_sk` | `dim_squad` | `squad_sk` | Many → One |
| `dim_date` | `date_sk` | `dim_release` | `release_date_sk` | One → Many |

**Date table relationship for fact_test_run:**
In Model view, right-click `fact_test_run` and add a calculated column:

```dax
fact_test_run[started_date_sk] =
    IF(
        NOT ISBLANK(fact_test_run[started_at]),
        INT(FORMAT(fact_test_run[started_at], "YYYYMMDD")),
        BLANK()
    )
```

Then add relationship:
`fact_test_run[started_date_sk]` → `dim_date[date_sk]` (Many → One)

### 3.2 Mark dim_date as a Date Table

1. Select `dim_date` in Model view.
2. **Table tools → Mark as date table → Mark as date table**.
3. Set the date column to `full_date`.

This enables Power BI time intelligence functions.

### 3.3 Rename tables for readability

In Model view, rename tables to user-friendly names:

| Original | Display name |
|----------|-------------|
| `dim_date` | Date |
| `dim_program` | Program |
| `dim_squad` | Squad |
| `dim_release` | Release |
| `dim_test_type` | Test Type |
| `dim_issue` | Requirement |
| `dim_defect` | Defect |
| `dim_test` | Test |
| `dim_test_execution` | Test Execution |
| `fact_test_run` | Test Runs |
| `fact_requirement_coverage` | Coverage |

### 3.4 Hide foreign key columns from report view

Select each fact table and mark the following columns as hidden (right-click → Hide):
- `test_sk`, `execution_sk`, `release_sk`, `test_type_sk`, `squad_sk`, `program_sk`, `issue_sk`

---

## 4. Core DAX Measures

Create a dedicated **Measures** table (blank table) to organise all measures.

**Create the measures table:**
- **Modeling → New table** → `Measures = ROW("placeholder", 1)` → then delete the "placeholder" column.

### 4.1 Fundamental test run counts

```dax
Total Runs =
COUNTROWS('Test Runs')

Passed Runs =
CALCULATE(
    COUNTROWS('Test Runs'),
    'Test Runs'[run_status] = "PASS"
)

Failed Runs =
CALCULATE(
    COUNTROWS('Test Runs'),
    'Test Runs'[run_status] = "FAIL"
)

Blocked Runs =
CALCULATE(
    COUNTROWS('Test Runs'),
    'Test Runs'[run_status] = "BLOCKED"
)

Todo Runs =
CALCULATE(
    COUNTROWS('Test Runs'),
    'Test Runs'[run_status] = "TODO"
)

Executing Runs =
CALCULATE(
    COUNTROWS('Test Runs'),
    'Test Runs'[run_status] = "EXECUTING"
)

Aborted Runs =
CALCULATE(
    COUNTROWS('Test Runs'),
    'Test Runs'[run_status] = "ABORTED"
)
```

### 4.2 Pass rate

```dax
Pass Rate % =
DIVIDE([Passed Runs], [Total Runs], 0) * 100

Pass Rate (formatted) =
FORMAT([Pass Rate %], "0.0") & "%"
```

### 4.3 Coverage metrics

```dax
Total Requirements =
DISTINCTCOUNT(Coverage[issue_sk])

Covered Requirements =
CALCULATE(
    DISTINCTCOUNT(Coverage[issue_sk]),
    Coverage[is_covered] = 1
)

Coverage % =
DIVIDE([Covered Requirements], [Total Requirements], 0) * 100

Uncovered Requirements =
[Total Requirements] - [Covered Requirements]
```

### 4.4 Defect metrics

```dax
Total Defects =
COUNTROWS(Defect)

Open Defects =
CALCULATE(
    COUNTROWS(Defect),
    NOT Defect[status] IN {"Closed", "Done", "Resolved", "Won't Fix"}
)

Critical Defects =
CALCULATE(
    COUNTROWS(Defect),
    Defect[severity] = "Critical"
)

Defect Resolution Rate % =
DIVIDE(
    CALCULATE(COUNTROWS(Defect), Defect[status] IN {"Closed", "Done", "Resolved"}),
    COUNTROWS(Defect),
    0
) * 100
```

### 4.5 Execution time

```dax
Avg Duration (seconds) =
AVERAGE('Test Runs'[duration_s])

Avg Duration (minutes) =
DIVIDE([Avg Duration (seconds)], 60, BLANK())

Total Test Time (hours) =
DIVIDE(SUMX('Test Runs', 'Test Runs'[duration_s]), 3600, 0)
```

### 4.6 Period-over-period comparison

```dax
Pass Rate % Prior Period =
CALCULATE(
    [Pass Rate %],
    DATEADD('Date'[full_date], -1, MONTH)
)

Pass Rate % Change =
[Pass Rate %] - [Pass Rate % Prior Period]

Pass Rate % Change (formatted) =
VAR delta = [Pass Rate % Change]
RETURN
    IF(
        ISBLANK(delta), "—",
        IF(delta >= 0, "▲ " & FORMAT(delta, "0.0") & "%",
                       "▼ " & FORMAT(ABS(delta), "0.0") & "%")
    )
```

### 4.7 RLS user context (for Row-Level Security)

```dax
Current User Squad =
LOOKUPVALUE(
    'Squad'[squad_name],
    bridge_squad_user[user_email], USERPRINCIPALNAME()
)

Current User Role =
LOOKUPVALUE(
    bridge_squad_user[role],
    bridge_squad_user[user_email], USERPRINCIPALNAME()
)
```

---

## 5. Report P1 — QA Health by Release

**Purpose:** Executive overview. Answers "What is the current test pass rate and how has it changed?"

**Page layout:**

```
┌─────────────────────────────────────────────────────────────┐
│  [Release slicer]  [Squad slicer]  [Date range slicer]      │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│  TOTAL   │  PASSED  │  FAILED  │  BLOCKED │  PASS RATE %    │
│  RUNS    │          │          │          │   (gauge)       │
│  KPI card│  KPI card│  KPI card│  KPI card│                 │
├──────────┴──────────┴──────────┴──────────┴─────────────────┤
│                                                              │
│   Stacked bar chart: Runs by status per Release             │
│                                                              │
├──────────────────────────┬──────────────────────────────────┤
│  Line chart:             │  Table: Release summary          │
│  Pass rate % over time   │  Release | Runs | Pass% | Defects│
└──────────────────────────┴──────────────────────────────────┘
```

### 5.1 Slicers

Add three slicers at the top of the page:

1. **Release slicer**
   - Field: `Release[release_name]`
   - Style: Dropdown
   - Selection: Multi-select enabled

2. **Squad slicer**
   - Field: `Squad[squad_name]`
   - Style: Dropdown

3. **Date range slicer**
   - Field: `Date[full_date]`
   - Style: Between (date picker)

### 5.2 KPI cards

For each KPI, add a **Card** visual:

| Card | Measure | Conditional formatting |
|------|---------|----------------------|
| Total Runs | `[Total Runs]` | None |
| Passed | `[Passed Runs]` | Green if > 0 |
| Failed | `[Failed Runs]` | Red background if > 0 |
| Blocked | `[Blocked Runs]` | Amber if > 0 |
| Pass Rate % | `[Pass Rate (formatted)]` | — use gauge instead |

**Pass Rate gauge:**
1. Add a **Gauge** visual.
2. Value: `[Pass Rate %]`
3. Minimum: `0`, Maximum: `100`, Target: `80` (configurable)
4. Color rules: Red 0–59, Amber 60–79, Green 80–100

### 5.3 Stacked bar chart — Runs by status per release

1. Add a **Stacked bar chart**.
2. **Y-axis:** `Release[release_name]`
3. **X-axis (values):** `[Total Runs]`
4. **Legend:** `Test Runs[run_status]`
5. **Custom colors:**
   - PASS → `#107C10` (green)
   - FAIL → `#D13438` (red)
   - BLOCKED → `#FF8C00` (amber)
   - EXECUTING → `#0078D4` (blue)
   - TODO → `#797775` (grey)
   - ABORTED → `#605E5C` (dark grey)
6. Sort by `release_name` ascending.

### 5.4 Line chart — Pass rate trend over time

1. Add a **Line chart**.
2. **X-axis:** `Date[full_date]` → set hierarchy to Month
3. **Y-axis:** `[Pass Rate %]`
4. **Secondary Y-axis:** `[Total Runs]` (bar chart overlay)
5. Add a **reference line** at Y=80 (target pass rate)
6. Add **data labels** for the last point.

### 5.5 Release summary table

1. Add a **Table** visual.
2. Columns (in order):

| Column | Source |
|--------|--------|
| Release | `Release[release_name]` |
| Release Date | `Release[release_date]` (format: Short date) |
| Total Runs | `[Total Runs]` |
| Passed | `[Passed Runs]` |
| Failed | `[Failed Runs]` |
| Pass Rate | `[Pass Rate (formatted)]` |
| Defects | `[Total Defects]` |

3. Sort by `Release Date` descending.
4. Add conditional formatting on **Pass Rate**: data bar (green = high, red = low).

---

## 6. Report P2 — Defect Density

**Purpose:** Shows defect volume, severity, and resolution trends per squad and release.

### 6.1 Visuals

**Defect status matrix:**
1. Add a **Matrix** visual.
2. Rows: `Squad[squad_name]`
3. Columns: `Defect[status]`
4. Values: `COUNTROWS(Defect)`
5. Enable **Stepped layout** = Off (flat matrix).
6. Add conditional formatting (background colour, white-to-red scale) on values.

**Defect severity clustered bar:**
1. Add a **Clustered bar chart**.
2. Y-axis: `Squad[squad_name]`
3. Values:
   - Critical: `[Critical Defects]`
   - Others: use CALCULATE with appropriate severity filters
4. Sort descending by total.

**Defect age scatter chart:**
Shows how long defects have been open.

```dax
Defect Age Days =
DATEDIFF(Defect[created_at], TODAY(), DAY)
```

1. Add a **Scatter chart**.
2. X-axis: `Defect[created_at]`
3. Y-axis: `[Defect Age Days]`
4. Size: `1` (uniform dots)
5. Legend: `Defect[priority]`
6. Tooltip: `Defect[defect_key]`, `Defect[summary]`, `Defect[assignee]`

**Defect trend line chart:**

```dax
New Defects This Month =
CALCULATE(
    COUNTROWS(Defect),
    DATESMTD('Date'[full_date])
)
```

1. X-axis: `Date[month_name]` + `Date[year]`
2. Y-axis: `[Total Defects]`
3. Add a second line for `[Open Defects]`

---

## 7. Report P3 — Requirement Coverage

**Purpose:** Shows which user stories/requirements have passing tests and which are uncovered.

### 7.1 Coverage status matrix

```dax
Coverage Status Label =
SWITCH(
    MAX(Coverage[coverage_status]),
    "PASS",      "✓ Covered",
    "FAIL",      "✗ Failing",
    "BLOCKED",   "⚠ Blocked",
    "TODO",      "○ Planned",
    "EXECUTING", "↻ Executing",
    "NO_COVERAGE","— Not Covered",
    "— Not Covered"
)
```

1. Add a **Matrix** visual.
2. Rows: `Requirement[issue_key]`, `Requirement[summary]`
3. Columns: `Release[release_name]`
4. Values: `[Coverage Status Label]`
5. Enable **Conditional formatting → Background colour**:
   - Rule on field `Coverage[coverage_status]`:
     - `PASS` → `#DFF6DD` (light green)
     - `FAIL` → `#FDE7E9` (light red)
     - `BLOCKED` → `#FFF4CE` (light amber)
     - `NO_COVERAGE` → `#F3F2F1` (light grey)

### 7.2 Coverage treemap

Shows test coverage distribution by squad.

1. Add a **Treemap** visual.
2. **Category:** `Squad[squad_name]`
3. **Details:** `Requirement[issue_key]`
4. **Values:** `[Total Requirements]`
5. **Tooltips:** `[Covered Requirements]`, `[Coverage %]`
6. Color by: `Coverage %` — gradient from red (0%) to green (100%).

### 7.3 Coverage KPI cards

| Card | Measure |
|------|---------|
| Total Requirements | `[Total Requirements]` |
| Covered | `[Covered Requirements]` |
| Coverage % | `FORMAT([Coverage %], "0.0") & "%"` |
| Uncovered | `[Uncovered Requirements]` |

### 7.4 Uncovered requirements table

```dax
Is Uncovered =
IF(Coverage[passing_test_count] = 0, "Yes", "No")
```

1. Add a **Table** visual filtered where `Is Uncovered = "Yes"`.
2. Columns: Issue Key, Summary, Priority, Squad, Release, Total Tests.
3. Sort by Priority (Critical first).

---

## 8. Report P4 — Execution Trend

**Purpose:** Shows how test execution volume and quality trends over time (weekly/monthly).

### 8.1 Execution trend area chart

1. Add an **Area chart**.
2. **X-axis:** `Date[full_date]` — set hierarchy to Week then Day.
3. **Y-axis (series):**
   - `[Passed Runs]` — green fill
   - `[Failed Runs]` — red fill
   - `[Blocked Runs]` — amber fill
4. Enable **Constant Line** at a target (e.g. 50 runs/week).
5. In **Analytics pane**, add a **Trend line** for Passed Runs.

### 8.2 Weekly heatmap

```dax
Runs This Week =
CALCULATE(
    [Total Runs],
    DATESINTHISPERIOD('Date'[full_date], LASTDATE('Date'[full_date]), -7, DAY)
)
```

1. Add a **Matrix** visual.
2. Rows: `Date[year]`, `Date[week_of_year]`
3. Columns: `Date[day_name]` (sorted Mon→Sun using `Date[day_of_week]`)
4. Values: `[Total Runs]`
5. Apply background colour conditional formatting (white = 0, dark blue = max).

### 8.3 Duration trend

1. Add a **Line and clustered column chart**.
2. Shared axis: `Date[full_date]` (Month)
3. Column values: `[Total Runs]`
4. Line values: `[Avg Duration (minutes)]`
5. This shows whether tests are getting slower as volume grows.

### 8.4 Top slowest tests table

```dax
Max Duration (seconds) =
MAXX('Test Runs', 'Test Runs'[duration_s])
```

1. Add a **Table** visual.
2. Columns: Test Key, Summary, Test Type, Squad, Max Duration (s), Avg Duration (s), Run Count.
3. Sort by `Max Duration (s)` descending.
4. Top N filter: show top 20.

---

## 9. Report P5 — Test Type Breakdown

**Purpose:** Compares automation coverage (Manual vs Cucumber/BDD vs Generic) across squads and releases.

### 9.1 Test type donut chart

1. Add a **Donut chart**.
2. **Legend:** `Test Type[test_type_name]`
3. **Values:** `[Total Runs]`
4. Custom colors:
   - Manual → `#0078D4` (blue)
   - Cucumber → `#107C10` (green)
   - Generic → `#8764B8` (purple)
5. **Detail labels:** show percentage and count.

### 9.2 Automation ratio gauge

```dax
Automated Runs =
CALCULATE(
    [Total Runs],
    Test[test_type_sk] <> LOOKUPVALUE(
        'Test Type'[test_type_sk],
        'Test Type'[test_type_name], "Manual"
    )
)

Automation Ratio % =
DIVIDE([Automated Runs], [Total Runs], 0) * 100
```

1. Add a **Gauge** visual.
2. Value: `[Automation Ratio %]`
3. Target: `60` (organisation target for automation coverage)
4. Min: 0, Max: 100.

### 9.3 Stacked column chart — By squad

1. Add a **Stacked column chart**.
2. **X-axis:** `Squad[squad_name]`
3. **Y-axis:** `[Total Runs]`
4. **Legend:** `Test Type[test_type_name]`
5. Sort by total descending.
6. Add data labels showing percentage.

### 9.4 Pass rate by test type table

1. Add a **Table** visual.
2. Columns:

| Column | DAX |
|--------|-----|
| Test Type | `Test Type[test_type_name]` |
| Total Runs | `[Total Runs]` |
| Passed | `[Passed Runs]` |
| Failed | `[Failed Runs]` |
| Pass Rate | `[Pass Rate (formatted)]` |
| Avg Duration (min) | `[Avg Duration (minutes)]` |

3. Conditional formatting on Pass Rate (data bar).

---

## 10. Report P6 — Test Run Drill-Through

**Purpose:** Individual test run details. This page is accessed via drill-through from P1–P5, not directly.

### 10.1 Configure drill-through

1. Create a new report page named **"Test Run Detail"**.
2. In the **Visualizations pane → Build visual → Drill through**:
   - Add `Release[release_name]` as a drill-through field.
   - Add `Squad[squad_name]` as a drill-through field.
   - Add `Test[test_key]` as a drill-through field (optional — for single-test drill).
3. Power BI will automatically add a **Back button**.

Users drill through by right-clicking a data point on any P1–P5 chart → **Drill through → Test Run Detail**.

### 10.2 Visuals

**Run status breakdown (for this drill context):**
1. Add a **Clustered bar chart**.
2. Y-axis: `Test Runs[run_status]`
3. X-axis: `[Total Runs]`
4. Apply status colours (same as P1).

**Test run table:**
1. Add a **Table** visual using `vw_p6_test_run_detail`.
2. Columns:

| Column | Display Name |
|--------|-------------|
| `test_run_id` | Run ID |
| `test_key` | Test Key |
| `test_summary` | Test Summary |
| `test_type_name` | Type |
| `execution_key` | Execution |
| `release_name` | Release |
| `squad_name` | Squad |
| `run_status` | Status |
| `started_at` | Started (format: `dd/MM/yyyy HH:mm`) |
| `duration_s` | Duration (s) |
| `executed_by` | Executed By |
| `defect_count` | Defects |
| `comment` | Comment |

3. Conditional formatting on `run_status`:
   - PASS → green text
   - FAIL → red text
   - BLOCKED → amber text

4. Enable **row sorting** on all columns.
5. Set **page filters** to show only the drilled context (auto-populated by drill-through).

### 10.3 Step results expandable table (optional)

If step-level detail is needed:

1. Add a second **Table** for `fact_test_step_result`.
2. Columns: `step_order`, `step_status`, `actual_result`, `comment`.
3. Add a page-level filter: `fact_test_step_result[test_run_id]` = selected run ID.
4. Use a **Slicer** on `Test Runs[test_run_id]` so the user can select a specific run to see its steps.

---

## 11. Row-Level Security

RLS ensures that Squad Members only see their own squad's data, while Program Managers and CXOs see all data.

### 11.1 Define RLS roles in Power BI Desktop

Go to **Modeling → Manage Roles → Create**.

**Role: Squad_Member**

Add the following filter to the `bridge_squad_user` table:

```dax
[user_email] = USERPRINCIPALNAME()
```

Then add a filter on `Squad`:

```dax
[squad_sk] IN
    SELECTCOLUMNS(
        FILTER(
            bridge_squad_user,
            bridge_squad_user[user_email] = USERPRINCIPALNAME()
        ),
        "squad_sk", bridge_squad_user[squad_sk]
    )
```

**Role: Program_Manager**

Add a filter on `bridge_squad_user`:

```dax
[user_email] = USERPRINCIPALNAME() &&
[role] IN {"Program_Manager", "CXO"}
```

When a Program Manager is filtered in, they automatically see all squads under their program (no squad filter needed — the relationship propagates through `dim_program`).

**Role: CXO**

No filters — CXO sees all data. Create the role but leave all filters blank. This allows explicit assignment without data restriction.

### 11.2 Test RLS in Power BI Desktop

1. **Modeling → View as → Other user**.
2. Enter a team member's email (e.g. `alice@yourcompany.com`).
3. Select role: `Squad_Member`.
4. Verify that P1–P5 only shows data for Alice's squad.

### 11.3 Assign users to roles in Power BI Report Server

After publishing, roles are assigned in the Report Server portal:

1. Open the Report Server web portal.
2. Navigate to the `.pbix` report → **Manage → Security**.
3. Under **Row-Level Security**:
   - `Squad_Member` role → add all squad member email addresses
   - `Program_Manager` role → add program manager emails
   - `CXO` role → add executive emails
4. Users not in any role will see no data (secure by default).

> **Note:** For Active Directory integration, you can use AD groups instead of individual emails. The `USERPRINCIPALNAME()` function returns the UPN of the authenticated user.

---

## 12. Publishing to Power BI Report Server

### 12.1 Save the .pbix file

In Power BI Desktop:
- **File → Save** → `QA_Metrics_Dashboard.pbix`
- Keep a local backup copy before publishing.

### 12.2 Publish to Report Server

1. **File → Publish → Publish to Power BI Report Server**.
2. Enter your Report Server URL: `http://REPORTSRV01/ReportServer`
3. Select or create a folder: e.g. `/QA Metrics/`
4. Click **Publish**.

### 12.3 Configure the data source connection

After publishing, the embedded connection string must be updated to use the server-side credentials:

1. Open the Report Server web portal.
2. Navigate to your published report.
3. Click **...** → **Manage → Data sources**.
4. Under connection type, select **Use the following credentials**:
   - Username: `powerbi_svc`
   - Password: `PBIRead@Only1`
5. Click **Test connection** → should return "Connection created successfully".
6. Click **Apply**.

---

## 13. Scheduled Refresh

### 13.1 Configure refresh in Report Server portal

1. Navigate to the report → **Manage → Subscriptions → New Subscription**.

   Or use **Manage → Cached Data Plans → New Cached Data Plan**.

2. For Import mode reports, set up a **cached data plan**:
   - Frequency: Every 4 hours (to match the delta pipeline run)
   - Start time: 30 minutes after the scheduled delta run (e.g. if delta runs at 00:00, 04:00, 08:00 → set refresh at 00:30, 04:30, 08:30)
   - This gives the pipeline time to complete before Power BI refreshes.

3. Alternatively, trigger refresh from the pipeline after a successful run. Add this to `run_delta.py` or `run_full_load.py` post-success:

```python
# Optional: trigger Report Server cache invalidation via REST
import httpx
report_server_url = "http://REPORTSRV01/ReportServer/api/v2.0"
report_path = "/QA Metrics/QA_Metrics_Dashboard"
resp = httpx.post(
    f"{report_server_url}/CacheRefreshPlans({plan_id})/Model.Execute",
    auth=("domain\\report-svc", "password"),
)
```

### 13.2 Recommended refresh schedule

| Report type | Recommended refresh | Rationale |
|-------------|-------------------|-----------|
| P1 (Health) | Every 4 hours | Matches delta run cadence |
| P2 (Defects) | Every 4 hours | Defects can be raised frequently |
| P3 (Coverage) | Daily at 02:00 | Coverage rarely changes intra-day |
| P4 (Trend) | Every 4 hours | Trend data is time-sensitive |
| P5 (Type breakdown) | Daily at 02:00 | Stable metric |
| P6 (Drill-through) | Every 4 hours | Users expect current run data |

---

## 14. Troubleshooting

---

## 15. Industry-Aligned Quality Metrics

This section introduces an implementation-ready governance layer aligned to commonly used enterprise QA benchmarks (test effectiveness, traceability completeness, and defect containment quality).

For KPI definitions, ownership, and threshold baselines, use the companion reference: [Quality Metric Catalog](quality-metric-catalog.md).

### 15.1 Load the supporting governance view

In Navigator, load:

- `vw_qm_quality_effectiveness`

This view is built for release-level quality governance and should be used for scorecards/management pages.

### 15.2 Recommended KPIs (from vw_qm_quality_effectiveness)

| KPI | Source Column | Interpretation |
|-----|---------------|----------------|
| Defect Resolution Rate % | `defect_resolution_rate_pct` | Share of defects resolved out of total identified defects |
| Defect Reopen Rate % | `defect_reopen_rate_pct` | Share of reopened defects out of resolved defects |
| Defect Leakage Rate % | `defect_leakage_rate_pct` | Share of leakage-flagged defects out of total defects |
| Defect Removal Efficiency % | `defect_removal_efficiency_pct` | Percentage of defects removed before leakage |
| Requirement Coverage % | `requirement_coverage_pct` | Covered requirements over total requirements |
| Requirements Without Tests % | `requirements_without_tests_pct` | Uncovered-by-test requirements ratio |
| Failed Runs Without Defect % | `failed_runs_without_defect_pct` | Potential traceability gap indicator |
| Avg Resolution Hours | `avg_resolution_hours` | Mean time to defect resolution |

### 15.3 Optional DAX wrappers for scorecards

If you prefer all report visuals to use DAX measures rather than direct numeric columns, create these measures:

```dax
Defect Leakage Rate % =
AVERAGE('vw_qm_quality_effectiveness'[defect_leakage_rate_pct])

Defect Removal Efficiency % =
AVERAGE('vw_qm_quality_effectiveness'[defect_removal_efficiency_pct])

Requirements Without Tests % =
AVERAGE('vw_qm_quality_effectiveness'[requirements_without_tests_pct])

Failed Runs Without Defect % =
AVERAGE('vw_qm_quality_effectiveness'[failed_runs_without_defect_pct])

Avg Resolution Hours =
AVERAGE('vw_qm_quality_effectiveness'[avg_resolution_hours])
```

### 15.4 Recommended governance page layout

Create a page called **P9 - Quality Effectiveness** with:

1. KPI cards:
    - Defect Leakage Rate %
    - Defect Removal Efficiency %
    - Requirements Without Tests %
    - Avg Resolution Hours
2. Clustered column chart by `release_name`:
    - `defect_resolution_rate_pct`
    - `defect_reopen_rate_pct`
3. Table by `release_name`:
    - total_defects
    - leakage_defects
    - total_requirements
    - requirements_without_tests
    - failed_runs_without_defect
4. Conditional formatting rules:
    - Leakage Rate: Green <= 5, Amber 5-10, Red > 10
    - Reopen Rate: Green <= 8, Amber 8-15, Red > 15
    - Requirements Without Tests %: Green <= 3, Amber 3-8, Red > 8

### 15.5 Governance rollout notes

- Start by publishing P9 as an internal QA leadership page.
- Confirm leakage and reopen status values are populated consistently by source systems.
- Calibrate thresholds per program/release train after 2-3 monthly cycles.

### "Data source credentials are invalid"

The `powerbi_svc` SQL login password may have expired or been changed.
1. Reset the password in SQL Server:
   ```sql
   ALTER LOGIN powerbi_svc WITH PASSWORD = 'NewPBIRead@Only2';
   ```
2. Update the credentials in the Report Server data source settings (Section 12.3).

### Report shows no data after first publish

1. Verify the data source connection test passes (Section 12.3).
2. In Power BI Desktop, refresh the report manually — **Home → Refresh**.
3. If desktop refresh fails, check the DSN in the `.pbix` query settings matches the actual server name.
4. Query the SQL view directly from SSMS to confirm it returns data:
   ```sql
   SELECT TOP 10 * FROM Reporting_DB.dbo.vw_p1_qa_health_by_release;
   ```

### RLS not working — users see all data

1. Verify the role was defined in Power BI Desktop (not just in Report Server).
2. Check that `bridge_squad_user` has rows for the test user's UPN.
3. Use **View as** in Desktop to simulate the user and confirm filters apply.
4. Verify `USERPRINCIPALNAME()` returns the expected value — add a Card visual with this measure for debugging:
   ```dax
   Debug UPN = USERPRINCIPALNAME()
   ```

### RLS not working — users see no data

1. The user's UPN may not match what is stored in `bridge_squad_user`. Check:
   ```sql
   SELECT * FROM Reporting_DB.dbo.bridge_squad_user
   WHERE user_email = 'alice@yourcompany.com';
   ```
2. If using Active Directory, ensure the UPN matches the AD UPN (not SAMAccountName).

### Drill-through not available on a chart

Drill-through requires the drill-through fields on the source page to match the fields defined on the detail page (Section 10.1).
1. Confirm the visual on P1–P5 has `Release[release_name]` or `Squad[squad_name]` in its visual fields.
2. Right-click a data point — drill-through option will only appear if there is a matching context.

### Scheduled refresh fails with "Query timeout"

Large datasets may exceed the default 30-second query timeout.
1. In Power BI Desktop: **File → Options → Data load → Query timeout → increase to 120 seconds**.
2. In SQL Server, increase the `remote query timeout`:
   ```sql
   EXEC sp_configure 'remote query timeout', 300;
   RECONFIGURE;
   ```
3. Consider switching the slow report page to **DirectQuery** mode (right-click the view in the data pane → Storage mode).

### Gauge target line not visible

The gauge minimum/maximum/target must all be set explicitly. Check:
1. Select the gauge → **Format visual → Gauge axis**.
2. Set Min: `0`, Max: `100`, Target value: `80`.
3. If these are bound to measures, ensure the measure returns a scalar value, not a table.

---

## Appendix A — Colour palette reference

| Status / Category | Hex | Usage |
|-------------------|-----|-------|
| PASS | `#107C10` | Green — passing tests |
| FAIL | `#D13438` | Red — failing tests |
| BLOCKED | `#FF8C00` | Amber — blocked tests |
| EXECUTING | `#0078D4` | Blue — in-progress |
| TODO | `#797775` | Grey — not started |
| ABORTED | `#605E5C` | Dark grey — aborted |
| Manual (test type) | `#0078D4` | Blue |
| Cucumber/BDD | `#107C10` | Green |
| Generic | `#8764B8` | Purple |
| Covered | `#DFF6DD` | Light green background |
| Uncovered | `#FDE7E9` | Light red background |

## Appendix B — Recommended report page order

| Page | Name | Primary audience |
|------|------|-----------------|
| P1 | QA Health Overview | CXO, Program Manager |
| P2 | Defect Analysis | QA Lead, Squad Lead |
| P3 | Requirement Coverage | Business Analyst, Product Owner |
| P4 | Execution Trend | QA Manager, Squad Lead |
| P5 | Test Type Breakdown | QA Architect, Test Manager |
| P6 | Test Run Detail | QA Engineer (drill-through only) |

## Appendix C — DAX quick reference

| Measure | Formula sketch |
|---------|---------------|
| Pass rate | `DIVIDE(CALCULATE([Total Runs], status="PASS"), [Total Runs], 0) * 100` |
| Coverage % | `DIVIDE([Covered Requirements], [Total Requirements], 0) * 100` |
| Automation % | `DIVIDE([Automated Runs], [Total Runs], 0) * 100` |
| Defect density | `DIVIDE([Total Defects], [Total Requirements], 0)` |
| Period change | `[Metric] - CALCULATE([Metric], DATEADD(Date[full_date], -1, MONTH))` |
| Current user squad | `LOOKUPVALUE(Squad[squad_name], bridge_squad_user[user_email], USERPRINCIPALNAME())` |
