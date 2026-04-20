# How-to: Jira/Xray Field Guardrails for Reliable Dashboard Metrics

This guide defines the minimum data-entry guardrails for test practitioners so Power BI metrics remain accurate, comparable, and audit-friendly.

Audience:
- QA Engineers
- Test Leads
- Defect Triage Owners
- Release Coordinators

---

## Why this matters

Dashboard pages P1-P8 and governance metrics depend on consistent field usage in Jira and Xray. Inconsistent values, missing links, or late updates cause metric drift such as:
- pass rate spikes/drops that are not real
- requirements shown as uncovered when tests exist
- failed runs without linked defects
- incorrect defect severity or root-cause trends

Use this document as the operational Definition of Done for issue updates.

---

## 1. Golden rules (apply to every ticket)

1. Use approved values only. Do not create ad-hoc spellings or synonyms.
2. Never leave required fields blank at workflow transition points.
3. Link artifacts before closing work (Requirement <-> Test <-> Execution <-> Defect).
4. Update status in real time. Do not batch-update at day end.
5. If a value does not fit, raise a process request; do not repurpose another field.

---

## 2. Field guardrails by object

### 2.1 Requirement/User Story (Jira issue)

Required before moving to Ready for QA:
- Issue key: system-generated, unchanged
- Summary: clear, testable statement
- Squad: required, exactly one squad
- Program: required
- Application: required
- Priority: required
- Release/Fix Version: required

Required before Done:
- Linked test cases in Xray: at least one for testable requirements
- Requirement status aligned to actual delivery state

Guardrails:
- One requirement belongs to one primary squad.
- Do not use free-text in squad/program fields if select lists are configured.
- Do not close requirement while all linked tests are TODO unless explicitly waived.

Metric impact:
- Requirement Coverage %, Requirements Without Tests %, release-level summary tables.

### 2.2 Xray Test (test case issue)

Required at creation:
- Test type: Manual, Cucumber, or Generic
- Squad and Program: must match owning requirement
- Repository path/component: required for discoverability

Required before execution:
- At least one step or executable definition (manual steps, gherkin, or generic definition)
- Linked requirement(s)

Guardrails:
- Test type is immutable after first execution unless approved by test lead.
- Avoid duplicate test cases for same acceptance criterion; extend existing test when possible.

Metric impact:
- Test Type Breakdown, automation ratio, coverage rollups.

### 2.3 Xray Test Execution

Required at creation:
- Release version
- Test environment (e.g., SIT, UAT, PROD-like)
- Test plan link (if your process uses plans)
- Assignee/executed by

Required while execution is in progress:
- Run status set accurately: TODO, EXECUTING, PASS, FAIL, BLOCKED, ABORTED
- Start/end timestamps recorded by tool or workflow automation

Guardrails:
- Never mark PASS/FAIL without an executed timestamp.
- Use BLOCKED only when external dependency prevents completion.
- Use ABORTED only for interrupted/invalid runs.

Metric impact:
- P1 pass rate, run status distributions, trend lines, duration and throughput charts.

### 2.4 Defect (Jira bug)

Required at creation from failed run:
- Severity (approved list only)
- Status
- Root cause (if known; mandatory before closure)
- Linked failed test run and/or test execution
- Linked requirement (directly or via failing test)

Required before Done/Closed:
- Resolution value set
- Root cause set to approved taxonomy value
- Reopen reason captured when defect was reopened

Guardrails:
- Every failed critical-path run should have a linked defect or explicit waiver reason.
- Do not use custom statuses without mapping approval.
- Do not mark defect resolved if linked rerun still fails.

Metric impact:
- Defect density, open/closed trends, defect resolution metrics, failed-runs-without-defect metric.

---

## 3. Approved value standards

Use controlled vocabularies from Jira/Xray admin. If your board currently allows free text, align values to the standards below.

### 3.1 Run status (Xray)

Allowed:
- PASS
- FAIL
- BLOCKED
- TODO
- EXECUTING
- ABORTED

Not allowed examples:
- Passed
- Failed
- In Progress
- NA

### 3.2 Defect severity

Recommended canonical values:
- Critical
- High
- Medium
- Low

Not allowed examples:
- Sev1, S1, P1 mixed without mapping
- blocker/critical used interchangeably

### 3.3 Root cause taxonomy

Define and use one controlled list, for example:
- Requirement gap
- Test data issue
- Environment issue
- Code regression
- Configuration issue
- Third-party dependency
- Automation script defect

If the list changes, update both Jira configuration and the pipeline mapping before rollout.

---

## 4. Linkage guardrails (traceability chain)

Minimum expected links:
- Requirement -> one or more Xray Tests
- Xray Test -> one or more Test Executions
- Failed Test Run -> Defect (or documented waiver)
- Defect -> related Requirement (directly or via linked test)

Release readiness traceability check:
1. Top-priority requirements have linked tests.
2. Executed tests have final statuses.
3. All FAIL runs have linked defects or approved waivers.
4. Closed defects map to a root cause.

---

## 5. Timing guardrails (when to update fields)

- Requirement fields (Squad, Program, Release): set before sprint execution starts.
- Test type and ownership: set at test creation, not during execution week.
- Run status: update immediately when execution outcome is known.
- Defect severity/root cause: severity at creation, root cause before closure.

Late data entry causes historical trend distortion.

---

## 6. Practitioner checklists

### 6.1 Before moving a Requirement to Ready for QA

- Squad populated and valid
- Program populated and valid
- Application populated and valid
- Release/Fix Version set
- At least one linked Xray test exists

### 6.2 Before marking a Test Execution cycle complete

- No test run remains in EXECUTING unless actively running
- FAIL runs linked to defects or waiver
- BLOCKED runs include blocker comment
- Environment field populated for every run

### 6.3 Before closing a Defect

- Severity set
- Root cause set from approved taxonomy
- Resolution set
- Verification rerun status is PASS (or approved exception)

---

## 7. Anti-patterns to avoid

- Updating statuses in bulk days later.
- Using comments to store structured data instead of fields.
- Renaming status values without BI/pipeline alignment.
- Reusing one field for different purposes across squads.
- Closing requirements with no linked tests and no waiver.

---

## 8. Data quality SLA and ownership

Suggested operating model:
- Daily: squad QA lead reviews missing required fields.
- Weekly: program QA manager reviews cross-squad traceability gaps.
- Per release: governance review validates metric readiness before sign-off.

Ownership:
- Practitioners: accurate and timely field updates.
- QA lead: value standard enforcement.
- Jira admin/BI owner: mapping and schema alignment.

---

## 9. Exception handling

If process requires a non-standard value or missing link:
1. Record waiver reason in a dedicated field/comment template.
2. Tag with release identifier.
3. Notify QA lead and BI owner before release reporting cutoff.

Do not silently bypass required fields.

---

## 10. Alignment with pipeline configuration

Field mappings used by the pipeline are maintained in:
- config/custom_field_map.json

When Jira/Xray field IDs or option values change:
1. Update Jira/Xray configuration.
2. Update mapping in config/custom_field_map.json.
3. Run a validation load in non-production.
4. Confirm dashboard metrics before production release.

---

## 11. Quick metric reliability checks

Use these checks during release week:
- Failed runs without defects should trend near zero.
- Requirements without tests should be reviewed and justified.
- Unknown/blank severity should be zero for closed defects.
- Unknown/blank squad/program/application should be zero for active requirements.

If any check fails, fix source field quality first before interpreting dashboard trends.

---

## Related docs

- docs/how-to/02-map-custom-fields.md
- docs/how-to/03-run-pipeline-manually.md
- docs/how-to/07-troubleshoot-pipeline.md
- docs/reference/quality-metric-catalog.md
- docs/reference/powerbi-design-guide.md
