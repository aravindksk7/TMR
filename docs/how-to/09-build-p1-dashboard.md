# How-to: Build P1 Dashboard (CXO Quality)

Build the P1 page in Power BI Desktop using the MCP-prepared semantic model.

---

## Scope

This guide builds page P1 only:
- Executive KPI cards
- Pass rate gauge
- Release/status distribution chart
- Pass-rate trend
- Release summary table

---

## Required fields and measures

Tables:
- dim_release
- dim_squad
- dim_date
- fact_test_run
- dim_defect

Measures:
- Total Runs
- Passed Runs
- Failed Runs
- Blocked Runs
- Pass Rate %
- Pass Rate (formatted)
- Open Defects
- Critical Defects
- P1 Target Pass Rate %
- Pass Rate % Prior Month
- Pass Rate % Change
- Pass Rate % Change (formatted)
- P1 Pass Rate Status

---

## Step 1: Create page and slicers

1. Add a new report page.
2. Rename it to P1 - CXO Quality.
3. Add top slicers:
- Release: dim_release[release_name] (Dropdown, multi-select on)
- Squad: dim_squad[squad_name] (Dropdown)
- Date: dim_date[full_date] (Between)

---

## Step 2: Add KPI cards

Add card visuals for:
- Total Runs -> Total Runs
- Passed Runs -> Passed Runs
- Failed Runs -> Failed Runs
- Blocked Runs -> Blocked Runs
- Open Defects -> Open Defects
- Critical Defects -> Critical Defects
- Pass Rate (formatted) -> Pass Rate (formatted)
- Pass Rate % Change (formatted) -> Pass Rate % Change (formatted)
- P1 Pass Rate Status -> P1 Pass Rate Status

Suggested conditional formatting:
- P1 Pass Rate Status: green for On Track, red for At Risk
- Failed Runs and Critical Defects: red accent if > 0

---

## Step 3: Add pass-rate gauge

1. Insert Gauge visual.
2. Value: Pass Rate %
3. Minimum: 0
4. Maximum: 100
5. Target value: P1 Target Pass Rate %

Recommended thresholds:
- 0-59 red
- 60-79 amber
- 80-100 green

---

## Step 4: Add release/status distribution

1. Insert Stacked bar chart.
2. Y-axis: dim_release[release_name]
3. Values: Total Runs
4. Legend: fact_test_run[run_status]

Recommended status colors:
- PASS: #107C10
- FAIL: #D13438
- BLOCKED: #FF8C00
- EXECUTING: #0078D4
- TODO: #797775
- ABORTED: #605E5C

---

## Step 5: Add pass-rate trend

1. Insert Line chart.
2. X-axis: dim_date[full_date]
3. Y-axis: Pass Rate %
4. Add analytics reference line at 80.

Optional:
- Add a second series (column or line) with Total Runs.

---

## Step 6: Add release summary table

1. Insert Table visual.
2. Columns:
- dim_release[release_name]
- Total Runs
- Passed Runs
- Failed Runs
- Pass Rate (formatted)
- Open Defects
- Critical Defects
3. Sort by dim_release[release_name] descending.

---

## Step 7: Validate interactions

1. Select one Release and confirm all visuals update.
2. Change Date range and verify trend + KPIs update.
3. Filter by Squad and verify defect and pass metrics recalculate.
4. Ensure no visual shows blank due to missing relationships.

---

## Publish readiness checklist

- Page title: P1 - CXO Quality
- Slicer labels are clear and aligned
- Gauge target line visible
- Status colors consistent with legend
- Tooltips enabled on charts
- Card units/decimal formatting reviewed
