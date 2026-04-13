# How-to: Add a New Power BI Report Page

Add a custom report page to the QA metrics `.pbix` file alongside the standard P1–P6 pages.

---

## Before you start

- Open `QA_Metrics_Dashboard.pbix` in **Power BI Desktop for Report Server** (not regular Desktop).
- Confirm at least one successful pipeline run has populated `Reporting_DB`.
- The data model (tables, relationships, DAX measures) is already set up — see the [Power BI Design Guide](../reference/powerbi-design-guide.md) if you need to rebuild it.

---

## Step 1 — Add a new page

Right-click the page tab bar at the bottom → **New page**.

Rename the page: right-click the tab → **Rename** → e.g. `P7 - Sprint Velocity`.

---

## Step 2 — Add slicers (recommended)

Copy the Release, Squad, and Date slicers from P1 so users get consistent cross-page filtering:

1. Go to page P1.
2. Select all three slicers (Ctrl+click each).
3. **Ctrl+C** → navigate to the new page → **Ctrl+V**.
4. Reposition as needed.

---

## Step 3 — Add visuals

Drag fields from the **Data pane** onto the canvas, or select a visual type first and then assign fields.

**Commonly used combinations:**

| Visual type | Good for |
|-------------|---------|
| Card | Single KPI (Total Runs, Pass Rate %) |
| Stacked bar | Distribution by category (status per squad) |
| Line chart | Trends over time (weekly pass rate) |
| Matrix | Cross-tab (squad × release) |
| Table | Row-level detail |
| Gauge | Target vs actual (pass rate goal) |
| Donut | Composition (test type breakdown) |

---

## Step 4 — Write a new DAX measure (if needed)

If no existing measure covers your metric, add one to the **Measures** table:

1. Select the **Measures** table in the Data pane.
2. **Modeling → New measure**.
3. Enter the DAX formula, e.g.:

```dax
Sprint Pass Rate % =
DIVIDE(
    CALCULATE([Total Runs], 'Test Runs'[run_status] = "PASS",
              DATESINPERIOD('Date'[full_date], LASTDATE('Date'[full_date]), -14, DAY)),
    CALCULATE([Total Runs],
              DATESINPERIOD('Date'[full_date], LASTDATE('Date'[full_date]), -14, DAY)),
    0
) * 100
```

See [DAX quick reference](../reference/powerbi-design-guide.md#appendix-c--dax-quick-reference) for common patterns.

---

## Step 5 — Configure drill-through (optional)

If users should be able to drill into this page from another page:

1. Open the new page → **Visualizations pane → Build visual → Drill through**.
2. Drag the context field (e.g. `Squad[squad_name]`) into the **Add drill-through fields here** well.
3. Power BI automatically adds a **Back** button.

Users right-click any data point on P1–P5 → **Drill through → P7 - Sprint Velocity**.

---

## Step 6 — Set page-level filters (optional)

To restrict this page to specific data (e.g. only automated tests):

1. Open the **Filters pane**.
2. Under **Filters on this page**, drag the field in.
3. Set the filter value and click **Apply filter**.

Page-level filters do not appear as slicers — they are always active.

---

## Step 7 — Test and publish

1. In the slicers, try a few combinations to confirm the visuals respond correctly.
2. Use **View → Mobile layout** if you need a mobile-optimised version.
3. **File → Save** to save the `.pbix`.
4. **File → Publish → Publish to Power BI Report Server** to deploy.
5. After publishing, verify the new page is visible in the Report Server portal.

---

## Tips

- Keep the page title and tab name consistent (add a title text box matching the tab name).
- Use the same colour palette as P1–P5 — see [colour reference](../reference/powerbi-design-guide.md#appendix-a--colour-palette-reference).
- If a visual is slow, switch its source from the base fact tables to a pre-aggregated SQL view, or add a new view to `Reporting_DB`.
