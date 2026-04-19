# QA Pipeline — Quality Metric Catalog

This catalog defines the governance metrics introduced for industry-aligned QA reporting. It is intended to be the operational reference for BI authors, QA leads, and release governance stakeholders.

---

## Scope

These metrics complement the existing P1-P8 reporting suite. They do not replace delivery pages; they provide a governance layer for quality effectiveness, traceability, and defect containment.

Primary source object:
- `dbo.vw_qm_quality_effectiveness`

---

## Metric Catalog

| Metric | SQL Column | Formula | Primary Owner | Suggested Thresholds | Rollout Page |
|--------|------------|---------|---------------|----------------------|--------------|
| Defect Resolution Rate % | `defect_resolution_rate_pct` | resolved defects / total defects x 100 | QA Lead + Defect Manager | Green >= 90, Amber 75-89, Red < 75 | P9 |
| Defect Reopen Rate % | `defect_reopen_rate_pct` | reopened defects / resolved defects x 100 | QA Lead | Green <= 8, Amber 8-15, Red > 15 | P9 |
| Defect Leakage Rate % | `defect_leakage_rate_pct` | leakage defects / total defects x 100 | Test Manager | Green <= 5, Amber 5-10, Red > 10 | P9 |
| Defect Removal Efficiency % | `defect_removal_efficiency_pct` | (total defects - leakage defects) / total defects x 100 | Test Manager | Green >= 95, Amber 90-94, Red < 90 | P9 |
| Requirement Coverage % | `requirement_coverage_pct` | covered requirements / total requirements x 100 | QA Lead + BA | Green >= 97, Amber 92-96, Red < 92 | P3 / P9 |
| Requirements Without Tests % | `requirements_without_tests_pct` | requirements without tests / total requirements x 100 | QA Lead + BA | Green <= 3, Amber 3-8, Red > 8 | P9 |
| Failed Runs Without Defect % | `failed_runs_without_defect_pct` | failed runs with no linked defect / failed runs x 100 | Test Execution Lead | Green <= 5, Amber 5-12, Red > 12 | P6 / P9 |
| Avg Resolution Hours | `avg_resolution_hours` | average hours between defect creation and resolution | Defect Manager | Green <= 48, Amber 48-96, Red > 96 | P9 |

---

## Operational Notes

| Area | Guidance |
|------|----------|
| Leakage flag quality | Leakage metrics are only meaningful if `dim_defect.leakage_flag` is maintained consistently in source systems or transformation rules. |
| Reopen status quality | Reopen rate assumes defects use a standard `Reopened` status value. Normalise variants before executive use. |
| Traceability gaps | `failed_runs_without_defect_pct` is a process-quality indicator. High values usually signal missing defect linkage rather than product quality alone. |
| Coverage completeness | `requirements_without_tests_pct` should be reviewed together with requirement criticality and business area, not in isolation. |

---

## Rollout Sequence

1. Enable the SQL view in Reporting_DB.
2. Refresh semantic model imports and confirm the `vw_qm_quality_effectiveness` table loads successfully.
3. Build P9 as an internal governance page first.
4. Review thresholds after 2-3 release cycles and calibrate by program.
5. Only after threshold stabilization, use these metrics in automated alerts or release gates.

---

## Release Governance Use

Recommended minimum governance scorecard:
- Defect Leakage Rate %
- Defect Removal Efficiency %
- Requirements Without Tests %
- Failed Runs Without Defect %
- Avg Resolution Hours

Recommended interpretation:
- Use P1-P8 to understand delivery status and execution details.
- Use P9 governance metrics to judge whether testing is effective, traceable, and sufficiently preventive.
