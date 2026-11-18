# AI PR Review Guide

Use this guide to review a concrete PR or commit diff. AI supplies findings;
the human reviewer retains approval, risk acceptance and merge authority.
Follow `CLAUDE.md` as the shared rule source and `AGENTS.md` as its Codex adapter.
This guide does not authorize test execution, edits, commits or external actions.

## Establish the review boundary

- Record base/head commits, branch, changed files and working-tree state. Read
  the complete diff, including new tests, and enough related code to trace behavior.
- Locate applicable intent/spec/plan. Record their revision and approval status;
  do not silently substitute a Draft or infer approval from implemented code.
  Use documents belonging to the reviewed revision when checkouts differ.
- Separate code evidence, observed runtime results and unverified assumptions.
  A test's existence, a comment or an agent's success statement is not a passing run.
- Review without changing files or auto-fixing findings. Run checks only when
  authorized; never execute untrusted PR code with credentials or real user data.

## Pass 1 — Bugs

- Trace inputs, outputs and state through changed code and its callers. Check
  failure propagation, return types, exceptions, ordering and compatibility.
- Cover boundaries, empty/invalid input, `None`, partial failure and recovery
  where relevant. Check for regressions in existing interfaces and data formats.
- Assess whether tests exercise real behavior with independent expectations.
  Check fault-injection bindings, cleanup and actual process exit codes where
  required. Distinguish assertion failures from collection/setup/environment errors.
- Anchor findings to a reachable trigger and an observable consequence. Record
  pre-existing defects separately unless the patch introduces or worsens them.

## Pass 2 — Security

- Inspect changed trust boundaries, path handling, subprocess arguments, network
  access, authentication, permissions and log/artifact output where applicable.
- Check secret exposure and unsafe use of user configuration. Do not open `.env`,
  credentials, tokens or API keys; cite relevant code/metadata without secret values.
- Check for destructive writes/deletes, unsafe rollback and lost source/canonical
  text or media provenance. Preserve unrelated uncommitted work and real data.
- Treat comments claiming isolation as claims. Trace actual read/write permissions,
  credential paths and network controls; state the limits of verified protection.

## Pass 3 — Compliance

- Map changed behavior and tests to approved requirements, design and acceptance
  criteria. Check allowlisted files, constraints, scope and applicable project rules.
- Flag unauthorized scope changes, missing acceptance coverage or contradictions;
  cite both the implementation and the governing requirement.
- Check documentation against implemented behavior and validation limits. Historical
  pass counts do not prove the current patch; missing runtime evidence stays explicit.
- If documents are absent, Draft, stale or conflicting, record the gap and required
  owner decision. Do not invent requirements or approve a design change yourself.

## Findings and severity

| Severity | Meaning | Integration handling |
| --- | --- | --- |
| Critical | A serious defect such as reachable secret exposure, data loss or a broken essential contract. | Block integration until resolved. |
| Major | A significant functional, security or approved-requirement defect. | Requires resolution or an explicit human disposition before merge. |
| Minor | A small improvement with limited impact. | Usually non-blocking; report at most 5. |

For every finding, include:

- ID, severity, review pass and concise title.
- File and exact line(s) at the reviewed head; reference the governing document
  and requirement ID when applicable.
- Trigger and evidence: actual code path, diff or authorized command/result.
  Label static reasoning; do not describe an unexecuted reproduction as observed.
- Impact and a focused proposed remedy; state whether it blocks integration.

Deduplicate findings across passes and order them by impact. Do not report
formatting issues already checked by CI, repeat unrelated historical defects or
fill a severity bucket with unsupported concerns. Zero findings is valid.

## Report and handoff

Report the reviewed base/head, scope, document revisions, findings by severity,
missing evidence and authorized checks actually run (or explicitly not run).
Identify required fixes and owner decisions separately from optional suggestions.

- **CHANGES REQUIRED:** unresolved Critical/Major defects or a demonstrated
  requirement violation need action or human disposition.
- **READY FOR HUMAN REVIEW:** no such blocker was found within the inspected
  scope. List remaining validation gaps; this is not test acceptance, proof of
  security, human approval or permission to merge.

Stop at the report. Do not auto-fix, approve, commit, push or merge.
