# Team Poster: Jira/Xray Guardrails for Reliable QA Metrics

Use this as a one-page working agreement for all squads.

---

## 1) Non-Negotiables

- Use approved values only (no custom spellings).
- Fill required fields before status transitions.
- Keep Requirement -> Test -> Execution -> Defect links complete.
- Update execution status in real time.
- Do not close work with missing traceability unless waived.

---

## 2) Required Fields by Artifact

### Requirement/User Story

Before Ready for QA:
- Squad
- Program
- Application
- Release/Fix Version
- Priority
- At least 1 linked Xray test

### Xray Test

Before execution:
- Test Type (Manual, Cucumber, Generic)
- Owning Squad/Program aligned to requirement
- Test steps or executable definition present
- Linked requirement(s)

### Xray Test Execution

During run:
- Environment set
- Assignee/Executed By set
- Status uses only: TODO, EXECUTING, PASS, FAIL, BLOCKED, ABORTED
- PASS/FAIL only after actual execution

### Defect

Before closure:
- Severity set
- Root cause set from approved taxonomy
- Resolution set
- Linked failed run/execution
- Verification rerun completed (or approved exception)

---

## 3) Approved Value Standards

Run Status:
- PASS
- FAIL
- BLOCKED
- TODO
- EXECUTING
- ABORTED

Defect Severity (recommended):
- Critical
- High
- Medium
- Low

Never use mixed aliases like Passed/Failed/In Progress/Sev1 unless centrally mapped.

---

## 4) Pre-Release Data Quality Gate

- Requirements without tests = 0 or justified.
- Failed runs without defects = near 0 and justified exceptions only.
- Closed defects with blank severity/root cause = 0.
- Active items with blank Squad/Program/Application = 0.

If any check fails, fix Jira/Xray fields first, then review dashboard trends.

---

## 5) Daily Squad Checklist (2-Minute)

- New requirements linked to tests.
- No stale EXECUTING runs.
- FAIL runs linked to defects or waiver.
- BLOCKED runs have blocker reason.
- Defects being closed have root cause and resolution.

---

## 6) Ownership

- Practitioners: accurate and timely updates.
- QA Lead: enforce value standards and checklist compliance.
- Jira Admin + BI Owner: maintain field options and pipeline mappings.

---

## 7) Exceptions (Waiver Process)

When a rule cannot be met:
1. Record waiver reason.
2. Tag release/sprint.
3. Notify QA Lead and BI Owner before reporting cutoff.

No silent exceptions.

---

## 8) Where to Go Next

- Full guide: docs/how-to/13-jira-xray-field-guardrails.md
- Field mapping updates: docs/how-to/02-map-custom-fields.md
- Metric definitions: docs/reference/quality-metric-catalog.md
