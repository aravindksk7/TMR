# How-to: Recover from Corrupted PBIX

Recover your report when Power BI Desktop shows:
- This file is corrupted
- Created by an unrecognized version
- Cannot be opened

This runbook rebuilds the report from the semantic model assets already in this repository.

---

## 1. Preserve the failed file first

1. Copy the broken PBIX to a safe folder.
2. Rename it with timestamp, for example:
- tmr-corrupt-2026-04-18.pbix
3. Do not overwrite it during recovery.

---

## 2. Verify the semantic model source of truth

Use the TMDL model in this repository:

- powerbi/semantic-model/definition/database.tmdl
- powerbi/semantic-model/definition/model.tmdl
- powerbi/semantic-model/definition/tables

If these files are present, you can rebuild the model even if PBIX is broken.

---

## 3. Start a new report shell

1. Open Power BI Desktop.
2. Create a new blank report.
3. Save immediately as:
- tmr-recovered.pbix

---

## 4. Reconnect using working SQL host

Important:
- Use 127.0.0.1 instead of localhost.

Connection target:
- Server: 127.0.0.1,1433
- Database: Reporting_DB

Credential mode:
- Database credentials
- Username: powerbi_svc
- Password: PBIRead@Only1

If credentials were previously cached for localhost, clear them in Data source settings and reconnect with 127.0.0.1.

---

## 5. Rebuild model tables

Load the model tables used by dashboards:

Dimensions:
- dim_date
- dim_program
- dim_application
- dim_squad
- dim_release
- dim_environment
- dim_status
- dim_root_cause
- dim_tester
- dim_test_type
- dim_issue
- dim_defect
- dim_test
- dim_test_plan
- dim_test_execution
- bridge_squad_user

Facts:
- fact_test_run
- fact_test_step_result
- fact_requirement_coverage
- fact_defect_link
- fact_cycle_snapshot

Views:
- vw_p1_qa_health_by_release
- vw_p2_defect_density
- vw_p3_requirement_coverage
- vw_p4_execution_trend
- vw_p5_test_type_breakdown
- vw_p6_test_run_detail
- vw_p7_environment_health
- vw_p8_release_snapshot
- vw_qm_quality_effectiveness

If needed, you can reconstruct from TMDL table definitions in:
- powerbi/semantic-model/definition/tables

---

## 6. Recreate relationships

Ensure these are present:

- fact_test_run[test_sk] -> dim_test[test_sk]
- fact_test_run[execution_sk] -> dim_test_execution[execution_sk]
- fact_test_run[release_sk] -> dim_release[release_sk]
- fact_test_step_result[test_run_id] -> fact_test_run[test_run_id]
- fact_requirement_coverage[issue_sk] -> dim_issue[issue_sk]
- fact_requirement_coverage[release_sk] -> dim_release[release_sk]
- dim_test[test_type_sk] -> dim_test_type[test_type_sk]
- dim_test[squad_sk] -> dim_squad[squad_sk]
- dim_issue[squad_sk] -> dim_squad[squad_sk]
- dim_issue[program_sk] -> dim_program[program_sk]
- dim_squad[program_sk] -> dim_program[program_sk]
- bridge_squad_user[squad_sk] -> dim_squad[squad_sk]

---

## 7. Restore measures

If measures are missing, recreate using these guides:

- docs/how-to/09-build-p1-dashboard.md
- docs/how-to/08-build-powerbi-dashboard-pages.md

---

## 8. Rebuild report pages

Rebuild pages in this order:

1. P1 first:
- docs/how-to/09-build-p1-dashboard.md

2. Remaining pages:
- docs/how-to/08-build-powerbi-dashboard-pages.md

---

## 9. Validate before publish

Check all items:

- Report refresh succeeds.
- Release, Squad, Date slicers affect all visuals.
- P1 KPIs and trend update with filters.
- Drill-through to P6 works.
- No visuals show broken field references.

If you see blocked queries with cyclic reference (for example dim_issue):

1. Close all open Power BI Desktop windows.
2. Open the latest regenerated template:
- QA-Pipeline-Report-fixed.pbit
3. In Data Source settings, clear permissions for both localhost and 127.0.0.1 entries.
4. Reconnect only with:
- Server: 127.0.0.1,1433
- Database: Reporting_DB
5. Refresh all queries.
6. If still blocked, regenerate template using:
- python make_pbit.py
and reopen the fixed output file.

---

## 10. Prevent future PBIX loss

1. Keep semantic model files under source control:
- powerbi/semantic-model/definition
2. Save PBIX with dated backups:
- tmr-YYYY-MM-DD.pbix
3. Avoid mixing Desktop channels (Store, MSI, Report Server) for the same PBIX.
4. Before upgrading Desktop, create a backup copy of PBIX.
