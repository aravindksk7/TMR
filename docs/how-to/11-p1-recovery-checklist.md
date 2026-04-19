# P1 Recovery Checklist (15-Minute Rebuild)

Use this checklist when PBIX is broken and you need P1 back quickly.

---

## 0. Prerequisites

- SQL source is reachable on 127.0.0.1,1433.
- Reporting_DB is populated.
- Power BI Desktop is open.

---

## 1. Create clean recovery file

1. New blank report.
2. Save as: tmr-recovered-p1.pbix.

---

## 2. Fix data source first

1. Data source settings -> clear old localhost entries.
2. Add source:
- Server: 127.0.0.1,1433
- Database: Reporting_DB
3. Credential type: Database
- Username: powerbi_svc
- Password: PBIRead@Only1

Pass condition:
- Refresh does not fail with SSPI or credential errors.

---

## 3. Load minimum P1 tables

Load these tables:
- dim_release
- dim_squad
- dim_date
- fact_test_run
- dim_defect

Optional for expansion later:
- dim_program

---

## 4. Validate minimum relationships

Create/verify:
- fact_test_run[release_sk] -> dim_release[release_sk]

Optional but useful:
- fact_test_run[test_sk] -> dim_test[test_sk]
- fact_test_run[execution_sk] -> dim_test_execution[execution_sk]

---

## 5. Create or verify P1 measures

Required:
- Total Runs
- Passed Runs
- Failed Runs
- Blocked Runs
- Pass Rate %
- Pass Rate (formatted)
- Open Defects
- Critical Defects
- P1 Target Pass Rate %
- P1 Pass Rate Status

Reference:
- docs/how-to/09-build-p1-dashboard.md

---

## 6. Build P1 visuals only

Add in this order:

1. Slicers:
- Release (dim_release[release_name])
- Squad (dim_squad[squad_name])
- Date (dim_date[full_date])

2. KPI cards:
- Total Runs
- Passed Runs
- Failed Runs
- Blocked Runs
- Open Defects
- Critical Defects
- Pass Rate (formatted)

3. Gauge:
- Value: Pass Rate %
- Target: P1 Target Pass Rate %

4. Stacked bar:
- Axis: dim_release[release_name]
- Legend: fact_test_run[run_status]
- Values: Total Runs

5. Trend line:
- Axis: dim_date[full_date]
- Values: Pass Rate %

6. Release summary table:
- dim_release[release_name]
- Total Runs
- Passed Runs
- Failed Runs
- Pass Rate (formatted)
- Open Defects
- Critical Defects

---

## 7. Smoke test before saving

1. Pick one release -> all visuals must update.
2. Adjust date range -> trend and KPIs must change.
3. Verify pass rate in card matches gauge value.
4. Ensure no visual shows missing field errors.

---

## 8. Save and checkpoint

1. Save PBIX.
2. Create backup copy with date suffix.
3. Continue to P2-P6 only after P1 is stable.

---

## Escalation if still failing

If refresh still fails:
1. Re-open docs/how-to/10-recover-corrupt-pbix.md
2. Reconfirm source uses 127.0.0.1, not localhost
3. Re-enter database credentials
4. Restart Desktop and retry refresh
