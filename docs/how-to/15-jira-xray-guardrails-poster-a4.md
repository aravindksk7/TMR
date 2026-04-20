# A4 Team Poster: Jira/Xray Guardrails for Reliable QA Metrics

Print target: A4 portrait, single page.

Print settings (recommended):
- Paper: A4
- Orientation: Portrait
- Scale: 90%
- Margins: Narrow

---

## Non-Negotiables

- Use approved values only.
- Complete required fields before moving status.
- Maintain full links: Requirement -> Test -> Execution -> Defect.
- Update run outcomes in real time.
- No silent exceptions.

---

## Required Fields (Minimum)

Requirement/User Story (before Ready for QA)
- Squad, Program, Application
- Release/Fix Version, Priority
- At least 1 linked Xray test

Xray Test (before execution)
- Test Type: Manual, Cucumber, Generic
- Linked requirement(s)
- Steps/definition present

Xray Execution (during cycle)
- Environment
- Assignee/Executed By
- Status from allowed list only

Defect (before closure)
- Severity
- Root cause
- Resolution
- Linked failed run/execution

---

## Allowed Values

Run Status:
- TODO
- EXECUTING
- PASS
- FAIL
- BLOCKED
- ABORTED

Severity:
- Critical
- High
- Medium
- Low

Do not use aliases like Passed, Failed, In Progress, Sev1 unless centrally mapped.

---

## Pre-Release Data Quality Gate

- Requirements without tests: 0 or justified.
- Failed runs without defects: near 0 (exceptions documented).
- Closed defects with blank severity/root cause: 0.
- Active records with blank Squad/Program/Application: 0.

---

## Daily 2-Minute QA Check

- New requirements linked to tests.
- No stale EXECUTING runs.
- FAIL runs linked to defects or waiver.
- BLOCKED runs include blocker reason.
- Defects being closed include root cause + resolution.

---

## Waiver Process

1. Record waiver reason.
2. Tag release/sprint.
3. Notify QA Lead and BI Owner before reporting cutoff.

---

## Ownership

- Practitioners: complete and timely updates.
- QA Lead: enforce standards.
- Jira Admin + BI Owner: keep field config and mappings aligned.

---

## References

- Full guardrails: docs/how-to/13-jira-xray-field-guardrails.md
- Team poster: docs/how-to/14-jira-xray-metrics-guardrails-poster.md
- Field mapping: docs/how-to/02-map-custom-fields.md
- Metric catalog: docs/reference/quality-metric-catalog.md
