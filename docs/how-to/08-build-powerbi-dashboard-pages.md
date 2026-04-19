# How-to: Build Power BI Dashboard Pages (P1–P8)

Build all eight dashboard pages after the PBIT has been opened in Power BI Desktop,
credentials entered, and the model refresh completed without errors.

---

## Before you start

### Confirm the model loaded cleanly

In the **Fields** pane verify all 29 tables are present with no yellow warning triangles:

| Group | Tables |
|---|---|
| **Dimensions** | dim_date, dim_program, dim_application, dim_squad, dim_release, dim_test_type, dim_issue, dim_defect, dim_test, dim_test_plan, dim_test_execution, dim_environment, dim_tester, dim_status, dim_root_cause |
| **Facts** | fact_test_run, fact_test_step_result, fact_requirement_coverage, fact_defect_link, fact_cycle_snapshot |
| **Views** | vw_p1_qa_health_by_release, vw_p2_defect_density, vw_p3_requirement_coverage, vw_p4_execution_trend, vw_p5_test_type_breakdown, vw_p6_test_run_detail, vw_p7_environment_health, vw_p8_release_snapshot |
| **Bridge** | bridge_squad_user |

### Confirm key measures exist

| Table | Measures |
|---|---|
| fact_test_run | Total Runs, Passed Runs, Failed Runs, Blocked Runs, Automated Runs, Pass Rate %, Automation Rate %, Pass Rate % Change, P1 Pass Rate Status, Avg Duration (minutes), Total Test Time (hours) |
| fact_requirement_coverage | Total Requirements, Covered Requirements, Uncovered Requirements, Coverage % |
| dim_defect | Total Defects, Open Defects, Critical Defects, Open Critical Defects |
| fact_defect_link | Total Defect Links, Open Defects Linked, Unique Defects, Impacted Test Runs |
| fact_cycle_snapshot | Snapshot Pass Rate %, Snapshot Coverage %, Snapshot Automation Rate %, Snapshot Open Critical Defects |
| vw_p1_qa_health_by_release | P1 Total Runs, P1 Passed, P1 Failed, P1 Blocked, P1 Pass Rate %, P1 Automation Rate % |

### Confirm active relationships in Model view

These must be **active** (solid line):

```
fact_test_run        → dim_release           (release_sk)
fact_test_run        → dim_test              (test_sk)
fact_test_run        → dim_test_execution    (execution_sk)
fact_test_run        → dim_environment       (environment_sk)
fact_test_run        → dim_tester            (tester_sk)
fact_test_run        → dim_status            (status_sk)
fact_test_run        → dim_root_cause        (root_cause_sk)
fact_test_run        → dim_date              (date_sk)
fact_test_step_result → fact_test_run        (test_run_id)
fact_requirement_coverage → dim_issue        (issue_sk)
fact_requirement_coverage → dim_release      (release_sk)
fact_defect_link     → dim_release           (release_sk)
fact_defect_link     → dim_defect            (defect_sk)
fact_cycle_snapshot  → dim_release           (release_sk)
fact_cycle_snapshot  → dim_squad             (squad_sk)
dim_test             → dim_test_type         (test_type_sk)
dim_squad            → dim_program           (program_sk)
dim_application      → dim_program           (program_sk)
bridge_squad_user    → dim_squad             (squad_sk)
```

These must be **inactive** (dashed line — available via USERELATIONSHIP in DAX):

```
fact_requirement_coverage → dim_date         (latest_execution_date_sk)
fact_cycle_snapshot       → dim_date         (snapshot_date_sk)
dim_test                  → dim_squad        (squad_sk)
dim_defect                → dim_squad        (squad_sk)
dim_defect                → dim_application  (application_sk)
dim_issue                 → dim_squad        (squad_sk)
dim_squad                 → dim_application  (application_sk)
dim_release               → dim_date         (release_date_sk)
```

---

## Colour palette

Use these hex values consistently across all pages so visuals match the Xray TestMetrics design language:

| Meaning | Hex | Use |
|---|---|---|
| Pass / Green | `#4ec77a` | Pass bars, positive KPIs, pass rate gauges |
| Fail / Red | `#e05c5c` | Fail bars, at-risk KPIs |
| Blocked / Amber | `#f0a030` | Blocked bars, warning states |
| Executing / Blue | `#0078d4` | Automation rate, active runs |
| Pending / Grey | `#8a8a8a` | Todo/not-run bars |
| Header background | `#1a1f2e` | Page header, card header |
| Card background | `#1e2530` | Visual card fill |
| Base background | `#141923` | Canvas background |

Set the canvas background via **View → Page background → Custom colour → `#141923`** on every page.

---

## Global slicers (build once on P1, then copy to all pages)

Place a slim slicer bar across the top of every page:

| # | Slicer | Field | Style |
|---|---|---|---|
| 1 | Release | `dim_release[release_name]` | Dropdown |
| 2 | Squad | `dim_squad[squad_name]` | Dropdown |
| 3 | Program | `dim_program[program_name]` | Dropdown |
| 4 | Date range | `dim_date[full_date]` | Between |
| 5 | Environment | `dim_environment[environment_name]` | Dropdown |

Turn off the slicer header, set border radius 4 px, font size 10 pt, dark background `#1e2530`.

---

## P1 — QA Health Overview (CXO)

**Purpose:** Release-level pass rate, automation rate, and critical defect summary for executives.
**Primary view:** `vw_p1_qa_health_by_release` + `fact_test_run` measures.

### KPI card strip (5 cards, top row)

| Card | Measure | Colour accent |
|---|---|---|
| Total Runs | `[Total Runs]` | `#0078d4` |
| Pass Rate % | `[P1 Pass Rate %]` | `#4ec77a` |
| Automation Rate % | `[P1 Automation Rate %]` | `#0078d4` |
| Open Critical Defects | `[Open Critical Defects]` | `#e05c5c` |
| P1 Status | `[P1 Pass Rate Status]` | Conditional: "On Track" = `#4ec77a`, "At Risk" = `#e05c5c` |

### Pass rate gauge

- Visual: Gauge
- Value: `[P1 Pass Rate %]`
- Minimum: 0, Maximum: 100
- Target: `[P1 Target Pass Rate %]` (default 80)
- Fill colour: Conditional — green ≥ 80, amber 60–79, red < 60

### Stacked bar — runs by release and status

- Visual: Stacked bar chart
- X-axis: `vw_p1_qa_health_by_release[release_name]`
- Values: `[P1 Passed]` (#4ec77a), `[P1 Failed]` (#e05c5c), `[P1 Blocked]` (#f0a030)
- Sort: Release date descending

### Pass rate trend line

- Visual: Line chart
- X-axis: `dim_date[full_date]` — Month level
- Line 1: `[Pass Rate %]` (#4ec77a)
- Line 2: `[P1 Target Pass Rate %]` (#e05c5c, dashed reference line)
- Enable data labels on the current month point

### MoM change card

- Visual: Card
- Value: `[Pass Rate % Change (formatted)]`
- Subtitle: "vs prior month"

---

## P2 — Defect Density

**Purpose:** Where are defects being introduced? Density by squad, severity, and release.
**Primary view:** `vw_p2_defect_density` + `fact_defect_link` measures.

### KPI card strip (4 cards)

| Card | Measure | Colour accent |
|---|---|---|
| Total Defects | `[Total Defect Links]` | `#e05c5c` |
| Open Defects | `[Open Defects Linked]` | `#f0a030` |
| Critical Defects | `[Critical Defects]` | `#e05c5c` |
| Impacted Test Runs | `[Impacted Test Runs]` | `#0078d4` |

### Defect density matrix (main visual)

- Visual: Matrix
- Rows: `dim_squad[squad_name]`
- Columns: `vw_p2_defect_density[defect_status]`
- Values: `vw_p2_defect_density[total_defects]`
- Conditional formatting: cell background — red for highest density, white for zero

### Severity breakdown bar

- Visual: Stacked bar chart
- X-axis: `vw_p2_defect_density[squad_name]`
- Legend: `vw_p2_defect_density[severity]`
- Values: `vw_p2_defect_density[total_defects]`
- Colours: Critical = `#e05c5c`, High = `#f0a030`, Medium = `#f2c94c`, Low = `#8a8a8a`

### Open vs closed donut

- Visual: Donut chart
- Legend: open/closed (derive from `open_flag` = 1 / 0)
- Values: `vw_p2_defect_density[open_defects]` vs `vw_p2_defect_density[total_defects]`
- Open slice: `#e05c5c`, Closed: `#4ec77a`

### Defect detail table

- Visual: Table
- Columns: `dim_defect[defect_key]`, `dim_defect[summary]`, `dim_defect[severity]`,
  `dim_defect[priority]`, `dim_defect[status]`, `dim_defect[assignee]`
- Filter: `dim_defect[critical_flag]` = TRUE for default view
- Enable drill-through to P6 on `dim_defect[defect_key]`

---

## P3 — Requirement Coverage

**Purpose:** Which requirements are tested, partially covered, or completely uncovered?
**Primary view:** `vw_p3_requirement_coverage` + `fact_requirement_coverage` measures.

### KPI card strip (4 cards)

| Card | Measure | Colour accent |
|---|---|---|
| Total Requirements | `[Total Requirements]` | `#0078d4` |
| Covered | `[Covered Requirements]` | `#4ec77a` |
| Uncovered | `[Uncovered Requirements]` | `#e05c5c` |
| Coverage % | `[Coverage %]` | `#4ec77a` or `#e05c5c` (conditional) |

### Coverage gauge

- Visual: Gauge
- Value: `[Coverage %]`
- Target: 80 (or use a What-If parameter "Coverage Target")
- Fill: green ≥ 80, amber 60–79, red < 60

### Coverage status donut

- Visual: Donut chart
- Legend: `vw_p3_requirement_coverage[coverage_status]`
- Values: count of requirements per status
- Colours: Covered = `#4ec77a`, Partial = `#f0a030`, Failed = `#e05c5c`, No Coverage = `#8a8a8a`

### Requirements matrix

- Visual: Matrix
- Rows: `vw_p3_requirement_coverage[requirement_summary]`, `[issue_key]`
- Columns: `vw_p3_requirement_coverage[release_name]`
- Values: `[Coverage %]`
- Conditional formatting on values: green = 100, amber = 1–99, red = 0

### Uncovered requirements table

- Visual: Table
- Source: `vw_p3_requirement_coverage`
- Columns: `issue_key`, `requirement_summary`, `priority`, `squad_name`, `is_critical_requirement`
- Filter: `is_covered` = FALSE
- Sort: `is_critical_requirement` descending, then `priority`

### Coverage by squad bar

- Visual: Clustered bar chart
- X-axis: `vw_p3_requirement_coverage[squad_name]`
- Values: `[Covered Requirements]` (#4ec77a), `[Uncovered Requirements]` (#e05c5c)

---

## P4 — Execution Trend

**Purpose:** Daily/weekly execution velocity, automation rate trend, environment breakdown.
**Primary view:** `vw_p4_execution_trend`.

### KPI card strip (4 cards)

| Card | Measure | Source |
|---|---|---|
| Total Runs (period) | `[Total Runs]` | fact_test_run |
| Automated Runs | `[Automated Runs]` | fact_test_run |
| Automation Rate % | `[Automation Rate %]` | fact_test_run |
| Avg Duration (min) | `[Avg Duration (minutes)]` | fact_test_run |

### Execution trend — combo chart

- Visual: Line and stacked column chart
- X-axis: `vw_p4_execution_trend[run_date]` — Week or Month grain
- Column values: `vw_p4_execution_trend[passed]` (#4ec77a), `[failed]` (#e05c5c), `[blocked]` (#f0a030)
- Line value: `[Automation Rate %]` — secondary Y-axis, `#0078d4`

### Runs by environment bar

- Visual: Clustered bar chart
- X-axis: `vw_p4_execution_trend[environment_name]`
- Values: `[Total Runs]` (colour by run status)
- Sort: Total Runs descending

### Weekly pass rate by squad — small multiples

- Visual: Line chart with small multiples
- X-axis: `vw_p4_execution_trend[run_date]` — Week level
- Values: `vw_p4_execution_trend[passed]` / `vw_p4_execution_trend[total_runs]` (quick measure ratio)
- Small multiples: `vw_p4_execution_trend[squad_name]`

---

## P5 — Test Type Breakdown

**Purpose:** Manual vs automated vs regression split, pass rates by type, squad performance.
**Primary view:** `vw_p5_test_type_breakdown`.

### KPI cards (4 cards, match P1 style)

| Card | Value |
|---|---|
| Total Runs | `[Total Runs]` |
| Pass Rate % | `[Pass Rate %]` |
| Automated Runs | `[Automated Runs]` |
| Automation Rate % | `[Automation Rate %]` |

### Test type donut

- Visual: Donut chart
- Legend: `dim_test_type[test_type_name]`
- Values: `[Total Runs]`
- Assign a distinct colour per test type

### Pass rate by test type bar

- Visual: Clustered bar chart
- X-axis: `vw_p5_test_type_breakdown[test_type_name]`
- Values: `vw_p5_test_type_breakdown[pass_rate_pct]`
- Reference line at 80 (target)
- Conditional colour: ≥ 80 = `#4ec77a`, < 80 = `#e05c5c`

### Squad × test type matrix

- Visual: Matrix
- Rows: `vw_p5_test_type_breakdown[squad_name]`
- Columns: `vw_p5_test_type_breakdown[test_type_name]`
- Values: `vw_p5_test_type_breakdown[total_runs]`
- Conditional formatting: highest = dark blue, zero = grey

### Slowest tests table

- Visual: Table
- Source: fact_test_run + dim_test
- Columns: `dim_test[test_key]`, `dim_test[summary]`, `dim_test_type[test_type_name]`, `[Avg Duration (minutes)]`, `[Total Runs]`
- Sort: Avg Duration descending, top 20

---

## P6 — Test Run Detail (Drill-through)

**Purpose:** Row-level investigation for a specific release, squad, or test.
**Primary view:** `vw_p6_test_run_detail`.

### Drill-through setup

In **Format → Drill through**, add these as drill-through fields:
- `dim_release[release_name]`
- `dim_squad[squad_name]`
- `dim_test[test_key]`
- `dim_environment[environment_name]`

Add a **Back button** (Insert → Buttons → Back) top-left.

### Header summary cards (4 small cards)

| Card | Value |
|---|---|
| Release | `dim_release[release_name]` (current filter context) |
| Environment | `dim_environment[environment_name]` |
| Pass Rate % | `[Pass Rate %]` |
| Total Runs | `[Total Runs]` |

### Run detail table (main visual)

- Visual: Table
- Source: `vw_p6_test_run_detail`
- Columns: `test_run_id`, `test_key`, `test_summary`, `test_type_name`, `execution_key`,
  `environment_name`, `release_name`, `squad_name`, `run_status`, `status_category`,
  `run_sequence`, `is_automated`, `is_blocked`, `block_reason`, `started_at`,
  `finished_at`, `duration_s`, `tester_name`, `executed_by`, `defect_count`,
  `root_cause_name`, `comment`
- Conditional formatting on `run_status`: PASS = `#4ec77a`, FAIL = `#e05c5c`, BLOCKED = `#f0a030`
- Enable word wrap on `test_summary` and `comment`

### Status distribution donut

- Visual: Donut chart
- Legend: `vw_p6_test_run_detail[run_status]`
- Values: count of rows
- Colours: PASS = `#4ec77a`, FAIL = `#e05c5c`, BLOCKED = `#f0a030`, others = `#8a8a8a`

### Step results table

- Visual: Table
- Source: `fact_test_step_result`
- Filter context: linked from selected row in run detail table via `test_run_id`
  (use **Edit interactions** to connect the two tables)
- Columns: `step_order`, `step_status`, `actual_result`, `comment`
- Conditional formatting on `step_status`

---

## P7 — Environment Health

**Purpose:** Which environments are most unstable? Block/fail rates by environment and root cause.
**Primary view:** `vw_p7_environment_health`.

### KPI card strip (4 cards)

| Card | Measure | Accent |
|---|---|---|
| Environments Monitored | DISTINCTCOUNT of `environment_name` | `#0078d4` |
| Avg Pass Rate % | `[Pass Rate %]` across environments | `#4ec77a` or `#e05c5c` |
| Total Failed Runs | SUM of `vw_p7_environment_health[failed_runs]` | `#e05c5c` |
| Total Blocked Runs | SUM of `vw_p7_environment_health[blocked_runs]` | `#f0a030` |

### Environment health scorecard (main visual)

Replicate the Xray TestMetrics program×environment heatmap:

- Visual: Matrix
- Rows: `vw_p7_environment_health[environment_name]`
- Columns: `vw_p7_environment_health[squad_name]`
- Values: `vw_p7_environment_health[pass_rate_pct]`
- Conditional background formatting:
  - ≥ 80 → `#1e2a20` text `#4ec77a` (green cell)
  - 60–79 → `#2a2218` text `#f0a030` (amber cell)
  - < 60 → `#2a1e1e` text `#e05c5c` (red cell)

### Blocked runs trend by environment

- Visual: Line chart
- X-axis: `vw_p7_environment_health[execution_date]` — Week grain
- Lines: one per `environment_name` (use Legend field)
- Values: `vw_p7_environment_health[blocked_runs]`
- Colour: use `ENV_COLORS` pattern — DEV `#4ec77a`, SIT `#e05c5c`, UAT `#f0a030`, PROD `#c77ae0`

### Root cause breakdown bar

- Visual: Clustered bar chart
- X-axis: `vw_p7_environment_health[root_cause_category]`
- Legend: `vw_p7_environment_health[environment_name]`
- Values: SUM of `failed_runs` + `blocked_runs`

### Environment detail table

- Visual: Table
- Columns: `environment_name`, `environment_type`, `criticality`, `squad_name`,
  `total_runs`, `failed_runs`, `blocked_runs`, `pass_rate_pct`
- Sort: `pass_rate_pct` ascending (worst first)
- Conditional formatting on `pass_rate_pct` column

---

## P8 — Release Snapshot (Executive)

**Purpose:** Pre-aggregated executive snapshot using `fact_cycle_snapshot`. Shows how each release
is tracking over time without expensive cross-filtering of large fact tables.
**Primary view:** `vw_p8_release_snapshot`.

### KPI card strip (4 cards)

| Card | Measure | Accent |
|---|---|---|
| Snapshot Pass Rate % | `[Snapshot Pass Rate %]` | conditional |
| Snapshot Coverage % | `[Snapshot Coverage %]` | conditional |
| Snapshot Automation Rate % | `[Snapshot Automation Rate %]` | `#0078d4` |
| Open Critical Defects | `[Snapshot Open Critical Defects]` | `#e05c5c` |

### Release Readiness Index (RRI) card per release

Inspired by the Xray TestMetrics RRI formula. Create a DAX measure:

```dax
RRI Score =
VAR PassW  = [Snapshot Pass Rate %]     * 0.40
VAR CovW   = [Snapshot Coverage %]      * 0.30
VAR FailW  = (100 - [Snapshot Pass Rate %]  + [Snapshot Pass Rate %]
              - CALCULATE(SUM(vw_p8_release_snapshot[pass_rate_pct]),
                          vw_p8_release_snapshot[pass_rate_pct] <> BLANK()))
             * 0
VAR AutoW  = [Snapshot Automation Rate %] * 0.10
RETURN
    ROUND(PassW + CovW + AutoW, 1)
```

Simplified version — add directly to the snapshot card:
- Card title: Release name
- Body: `pass_rate_pct`, `coverage_rate_pct`, `automation_rate_pct`, `open_critical_defects`
- Colour border: ≥ 80 = `#4ec77a`, 60–79 = `#f0a030`, < 60 = `#e05c5c`

### Snapshot trend — stacked area chart

- Visual: Area chart
- X-axis: `vw_p8_release_snapshot[snapshot_date]`
- Legend: `vw_p8_release_snapshot[release_name]`
- Values: `vw_p8_release_snapshot[pass_rate_pct]`

### Release comparison table

- Visual: Table
- Columns: `release_name`, `release_date`, `release_status`, `squad_name`,
  `total_tests`, `executed_tests`, `passed_tests`, `failed_tests`, `blocked_tests`,
  `pass_rate_pct`, `coverage_rate_pct`, `automation_rate_pct`, `open_critical_defects`
- Sort: `snapshot_date` descending (most recent snapshot per release)
- Conditional formatting: `pass_rate_pct` and `coverage_rate_pct` columns

### Not-run tests gauge

- Visual: Gauge
- Value: SUM of `vw_p8_release_snapshot[not_run_tests]`
- Max: SUM of `vw_p8_release_snapshot[total_tests]`
- Target: 0 (all tests should be run by release)

---

## Cross-page drill-through map

| From page | Drill-through field | Lands on |
|---|---|---|
| P1 (by release) | `dim_release[release_name]` | P8 Release Snapshot |
| P2 (by squad) | `dim_squad[squad_name]` | P6 Drill-through |
| P2 (by defect) | `dim_defect[defect_key]` | P6 Drill-through |
| P3 (uncovered req) | `dim_release[release_name]` | P6 Drill-through |
| P4 (by environment) | `dim_environment[environment_name]` | P7 Environment Health |
| P7 (by environment) | `dim_environment[environment_name]` | P6 Drill-through |

---

## Final validation checklist

- [ ] All 8 pages exist: P1–P8
- [ ] Canvas background is `#141923` on every page
- [ ] Global slicers (Release, Squad, Program, Date, Environment) copy across all pages and cross-filter correctly
- [ ] P1 Pass Rate gauge changes when Release slicer changes
- [ ] P2 defect matrix shows squad × status breakdown
- [ ] P3 uncovered requirements table filters to `is_covered = FALSE`
- [ ] P4 trend chart shows week-over-week execution volumes
- [ ] P5 automation rate changes by test type filter
- [ ] P6 drill-through back button returns to source page
- [ ] P6 step results table responds to row selection in run detail table
- [ ] P7 environment heatmap cells colour green/amber/red by pass rate
- [ ] P8 snapshot trend shows distinct lines per release
- [ ] No visual shows "Can't display this visual" or blank field errors
- [ ] Save as `.pbix` (File → Save As) once all pages validate
