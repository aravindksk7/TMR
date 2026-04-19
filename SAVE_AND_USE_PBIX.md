# How to Save and Use Your QA Pipeline Power BI Model

## Current Status ✓

Your **semantic model is fully loaded and active** in Power BI Desktop right now:
- All 14 tables imported
- All 12 relationships configured
- All 22 measures defined
- Ready for report canvas creation

---

## STEP 1: Save Your PBIX File

### Manual Save (Recommended)

1. **Look at Power BI Desktop window** on your screen (titled "Untitled - Power BI Desktop")
2. **Click the File menu** (or press Ctrl+S)
3. **Select "Save As"** (or press Ctrl+Shift+S)
4. **Enter filename:** `QA-Pipeline-Report`
5. **Choose location:** `c:\TM_PBI\qa_pipeline\`
6. **File type:** Power BI Report (*.pbix)
7. **Click Save**

Your file will be saved as:
```
c:\TM_PBI\qa_pipeline\QA-Pipeline-Report.pbix
```

### Keyboard Shortcut (Quick)
- Press **Ctrl+Shift+S** to open Save As dialog immediately

---

## STEP 2: Refresh Data (Optional)

If you want to populate the model with data from your SQL Server:

1. **Go to Home tab** in Power BI Desktop
2. **Click Refresh** (or Ctrl+R)
3. **Wait** for data to load from Reporting_DB
4. **Save again** (Ctrl+S) to persist the data

---

## STEP 3: Create Report Pages

Your model has:
- **14 dimension tables** (for filtering and attributes)
- **3 fact tables** (for analytics and measures)
- **22 DAX measures** (for metrics)

### Recommended Pages (P1-P6)

Start building these pages one by one:

#### P1: QA Health by Release
**Purpose:** Executive summary of test quality by release  
**Key Visuals:**
- Card: Current overall pass rate
- Matrix: Pass rate by release and squad
- KPI: Progress toward 95% target

**Filters:** Release, Squad, Date range

---

#### P2: Defect Density
**Purpose:** Correlate test volume with defect metrics  
**Key Visuals:**
- Scatter plot: # of test runs vs. defect count (per release)
- Stacked bar: Defects by severity
- Table: Defect details with assignee

**Filters:** Program, Squad, Severity, Status

---

#### P3: Requirement Coverage
**Purpose:** Track test coverage of requirements  
**Key Visuals:**
- Gauge: Overall coverage %
- Table: Covered vs. Uncovered requirements
- Card: Total requirements and covered count

**Filters:** Release, Program, Squad

---

#### P4: Execution Trend
**Purpose:** Visualize test execution and pass rate over time  
**Key Visuals:**
- Line chart: Pass rate % by week/month
- Area chart: Cumulative passed/failed/blocked runs
- Card: Average test duration

**Filters:** Date range, Squad, Test type

---

#### P5: Test Type Breakdown
**Purpose:** Understand test distribution across types  
**Key Visuals:**
- Pie/Donut: % of Manual, Cucumber, Generic tests
- Clustered bar: Pass rate by test type
- Card: Total tests per type

**Filters:** Release, Squad

---

#### P6: Test Run Drill-Through
**Purpose:** Detailed view of individual test runs  
**Key Visuals:**
- Table: All test runs with columns:
  - Release, Test name, Status, Duration, Assignee
  - Defect count, Executed by
- Drill-through: Click a row → see test step results

**Filters:** Release, Test type, Status, Date range

---

## STEP 4: Add Filters and Interactivity

**Slicers to add:**
1. Release (dropdown or list)
2. Squad (dropdown)
3. Date range (date picker)
4. Test type (checkboxes)
5. Status (Manual filter)

**Cross-filtering:** Configure visual interactions so that selecting one visual filters others on the same page.

---

## STEP 5: Format and Polish

1. **Table renaming** (Model view):
   - dim_test → "Test"
   - dim_release → "Release"
   - fact_test_run → "Test Runs"
   - etc.

2. **Hide FK columns** (Model view → Column properties):
   - Hide: `_sk` columns (e.g., release_sk, test_sk)
   - These are for relationships, not user display

3. **Add measures to Power BI visuals:**
   - Use Pass Rate %, Total Runs, Defect counts in cards/gauges
   - Create KPIs with target thresholds

4. **Apply branding:**
   - Corporate color palette
   - Font: Segoe UI or corporate standard
   - Logo on title page

---

## STEP 6: Publish (Optional)

Once happy with your report:

1. **File → Publish**
2. **Select workspace** (Power BI Service or Report Server)
3. **Choose dataset publishing:**
   - Use existing dataset (if shared)
   - Create new dataset
4. **Configure refresh schedule** (if using Service)
5. **Set up RLS** (if using bridge_squad_user)

---

## Available Measures by Table

### In fact_test_run:
```
Total Runs, Passed Runs, Failed Runs, Blocked Runs
Pass Rate %, Avg Duration (seconds), Avg Duration (minutes)
Total Test Time (hours), Pass Rate (formatted)
P1 Target Pass Rate %, Pass Rate % Prior Month
Pass Rate % Change, Pass Rate % Change (formatted)
P1 Pass Rate Status
```

### In dim_defect:
```
Total Defects, Open Defects, Critical Defects
Open + Critical Defects
```

### In fact_requirement_coverage:
```
Total Requirements, Covered Requirements
Coverage %, Uncovered Requirements
```

---

## Common Formulas (DAX Reference)

If you need to create custom measures, here are common patterns:

```DAX
-- Count with filter
Measure = CALCULATE(COUNTA(fact_test_run[test_run_id]), 
           fact_test_run[run_status] = "Passed")

-- Percentage
Pass Rate = DIVIDE([Passed Runs], [Total Runs]) * 100

-- Prior period comparison
Prior Month = CALCULATE([Pass Rate], 
              DATEADD(dim_date[full_date], -1, MONTH))
```

See Power BI DAX docs for advanced scenarios.

---

## Troubleshooting

### Data not loading after refresh?
1. Check SQL Server connection: File → Options → Data load
2. Verify database accessibility: `telnet 127.0.0.1 1433`
3. Check Reporting_DB exists on server

### Measures showing "blank" or error?
1. Right-click measure → Edit
2. Check DAX syntax in formula bar
3. Verify table/column names are correct
4. Look for circular dependencies

### Report looks wrong / relationships broken?
1. Go to Model view (View → Model)
2. Check that 12 relationships are visible and active
3. Verify cardinality (Many-to-One)
4. Note: `rel_req_coverage_release` should be INACTIVE

### How do I add more measures?
1. Model view → Select a dimension table
2. New Measure
3. Enter DAX formula
4. Name it and press Enter
5. Use in visuals

---

## Next: Manual Canvas Creation Guide

See the **[Report Pages Quick Guide](../docs/how-to/05-add-powerbi-page.md)** for step-by-step visual creation.

---

**Questions?** Refer to:
- Full Design Guide: `docs/powerbi-design-guide.md`
- Model Reference: `QA_PIPELINE_MODEL_REFERENCE.md`
- Repository: `README.md`

