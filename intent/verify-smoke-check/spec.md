# Spec: Make smoke-check failures observable

**Project:** novel-pipeline-v2

**Status:** Approved

**Source:** Approved intent at `intent/verify-smoke-check/intent.md`

**Decision status:** Q1–Q5 resolved; full spec approved by the project owner

**Baseline inspected:** HEAD `1f1d969` and the related working-tree files

**Evidence status:** Static inspection only — no acceptance or regression tests executed

**Implementation status:** Not started

## 1. Purpose and scope

Make a mismatch in the Chinese-numeral smoke check in `verify.py` observable in
the check result, summary and process exit code. The summary must describe smoke
checks without claiming that the whole application has been validated.

### In scope

- Correct the success/failure signal of the numeral smoke check.
- Preserve the existing aggregation, exception handling and exit-code contract.
- Clarify the summary messages.
- Add regression tests for the helper, `main()` and the real script entry point.
- Add a minimal verification explanation to `INSTALL.md`.

### Out of scope

- Changing Chinese-numeral conversion rules or implementation.
- Fixing the chunking smoke check or other unrelated defects in `verify.py`.
- Changing React/PyQt6, application APIs, media processing, AI, TTS or YouTube.
- Establishing CI/CD or standardizing test runners across the repository.
- Rewriting historical verification reports.

Fixing the numeral signal does not establish correctness of all other checks.

## 2. Evidence and assumptions

Line references below describe the inspected baseline and must be rechecked if
the implementation checkout differs. Repository paths are relative to its root.

| ID | Verified by static inspection | Evidence |
| --- | --- | --- |
| E1 | The source intent is approved and restricts the change to the numeral signal and summary. | `intent/verify-smoke-check/intent.md:4`, `:67`, `:121` |
| E2 | `test_chinese_numerals()` has five cases, prints a comparison result, then returns `True` even when a comparison differs. | `verify.py:22`, `:27`, `:35`, `:40` |
| E3 | The converter import is inside `test_chinese_numerals()`, not at module scope. | `verify.py:25` |
| E4 | `main()` runs four checks, counts their returned results, treats caught `Exception` instances as failures, and returns `0` or `1`. | `verify.py:95`, `:103`, `:113`, `:117` |
| E5 | The actual script entry point calls `sys.exit(main())`. | `verify.py:124` |
| E6 | The success output says “Application is ready”; the chunking check also returns `True` without validating its printed results. | `verify.py:71`, `:87`, `:118` |
| E7 | `chinese_to_int` is exported from `chapters`; `None` denotes rejected malformed input. Separate tests exercise the converter. | `chapters/__init__.py:3`, `chapters/numerals.py:62`, `tests/test_chapter_normalization.py:30` |
| E8 | Tests use both pytest-style classes/fixtures and `unittest.TestCase`. Documentation contains both runner commands. | `tests/test_chapter_normalization.py:330`, `tests/test_headless_service.py:15`, `INSTALL.md:84`, `FINAL_SUMMARY.md:28` |
| E9 | `INSTALL.md` documents pytest/build; STATUS, FINAL_SUMMARY and MANIFEST contain `python verify.py`. | `INSTALL.md:84`, `STATUS.md:82`, `FINAL_SUMMARY.md:28`, `MANIFEST.md:81` |
| E10 | Architecture documentation describes a shared Python core with CLI/FastAPI and React/PyQt6 interfaces. This change concerns a separate verification script. | `README.md:163`, `pipeline/service.py:1`, `pipeline/document.py:1` |

### Not verified

- Whether the converter currently produces any incorrect result on this checkout.
- Current runtime pass/fail results, coverage or external-service parity.
- Which dependencies and optional test runners are installed in the execution environment.
- Whether downstream automation currently relies on the script's exit code.
- Runtime behavior of the proposed test harness, including child-process execution.

Requirements describe required future behavior. Design details are specified for
review; they are not claims that implementation or validation has happened.

## 3. Owner review decisions

| Decision | Recorded resolution |
| --- | --- |
| Q1 — Messages | Accept the three English messages specified in D3, explicitly limited to smoke checks. |
| Q2 — Documentation | Update `INSTALL.md` minimally; do not edit historical reports. R8 is enabled. |
| Q3 — Test runner | Add `tests/test_verify.py` using `unittest.TestCase` and standard-library utilities. Use pytest additionally if the environment supports it. |
| Q4 — Fault injection | Keep the actual checker; replace only the converter at the location it is looked up. The inspected function-local import means that location is currently `chapters.chinese_to_int`. |
| Q5 — Verification | Cover the helper, `main()`, actual process exit code and an appropriate regression suite. |

These decisions answer the open questions carried by the source intent. The
intent file itself is not modified by this specification task.

## 4. Functional requirements

| ID | Requirement | Source |
| --- | --- | --- |
| R1 | A numeral case succeeds when actual output equals its expected output. Actual `None` with expected `None` is a success. | Intent §2; E2, E7 |
| R2 | Without an exception, the numeral checker returns `True` only if all five existing cases match. Any mismatch makes its result `False`; later successes cannot clear an earlier failure. | Intent §2, §6 |
| R3 | Preserve diagnostics identifying the input, actual output and expected output. A normal mismatch must not prevent evaluation of later cases. | Intent §5; E2 |
| R4 | If the numeral checker fails while the other three checks succeed, `main()` and the process must report failure with the existing exit code `1`. | Intent §2, §6; E4, E5 |
| R5 | Keep the four existing checks and their order. All reported successes produce exit code `0`; any returned `False` or caught `Exception` produces `1`. Count checks, not individual numeral cases. Preserve continuation of the outer check loop after a caught exception. | Intent §4–§6; E4 |
| R6 | Emit the success, failure and count messages in D3. Do not claim the whole application is ready or validated. | Intent §2, §6; Q1 |
| R7 | Regression tests must exercise the real numeral checker, real aggregation and real `__main__` exit path. Record a regression failing because of the false-positive behavior before the patch and succeeding afterward. | Intent §6; Q4, Q5 |
| R8 | Add minimal documentation in `INSTALL.md`: how to run the script, meanings of exit codes `0`/`1`, and the limits of smoke-check validation. Leave historical reports unchanged. | Intent §3, §7; Q2 |

“Caught exception” means the current `Exception` boundary in `main()`. This spec
does not introduce handling for `BaseException`, `KeyboardInterrupt` or
`SystemExit` inside that loop.

## 5. Non-functional requirements

| ID | Requirement |
| --- | --- |
| N1 — Offline/privacy | New tests use fixed or synthetic input and synthetic exceptions. They must not call online providers, read secrets or use real accounts/novel data. |
| N2 — Isolation/determinism | Restore patched dependencies after each test. Use isolated configuration paths and bounded subprocess lifetimes; clean up child processes and temporary test resources. Do not depend on test execution order. |
| N3 — Compatibility/scope | Keep current callable interfaces and script entry point. Use `unittest.TestCase` and the standard library for new tests, without adding dependencies. Preserve the documented Python 3.11+ floor. Do not change converter/chunker/UI/API behavior. |
| N4 — Evidence/reviewability | Record exact validation commands, checkout identity, working-tree state, results and failure reasons. Keep the patch focused and independently reviewable/revertible. |

No new performance benchmark or coverage-percentage target is required.

## 6. Technical design

### D1 — Numeral-check aggregation

Keep the five fixtures and the existing equality comparison. Maintain an
aggregate result whose failure state cannot be reset by later matches. Evaluate
all cases when there are only mismatches; preserve the existing exception path
through `main()` rather than introducing a new swallowing/retry mechanism.

| Input | Expected |
| --- | --- |
| `九十八` | `98` |
| `一百零五` | `105` |
| `两万三千` | `23000` |
| `一二` | `None` |
| `十十` | `None` |

No new result class, enum, production test hook or public parameter is required.

### D2 — Existing runner and exit code

Feed the corrected boolean result into the existing `main()` aggregation.
Preserve the four checks, exception handling, check-level counts and
`sys.exit(main())`. Do not redesign the runner.

### D3 — Approved summary messages

Use these exact message texts; counts are interpolated at runtime:

- Success: `Smoke checks reported success. Full application validation was not performed.`
- Failure: `One or more smoke checks failed. Review the results above.`
- Count: `Smoke checks reporting success: {passed}/{total}`

Keep the existing individual-case diagnostics. Test output behavior; do not add
tests that merely search production source text or freeze unrelated decoration.

### D4 — Helper and main regression tests

Create `tests/test_verify.py` with `unittest.TestCase` and standard-library
utilities such as `unittest.mock`, `contextlib`, `io`, `subprocess` and `tempfile`.

Keep `test_chinese_numerals()` real. For mismatch cases, substitute the converter
with a controlled response for a selected input; use independently defined
literal expectations. Do not derive expectations from the production checker.

#### Patch where lookup actually happens

The inspected code imports `chinese_to_int` locally inside the checker:

- Each checker invocation performs `from chapters import chinese_to_int`.
- Patch `chapters.chinese_to_int` before calling the checker and keep the patch
  active during that call. This still applies if the `verify` module has already
  been imported, because no module-level `verify.chinese_to_int` was bound by
  that import.
- Do not patch `verify.chinese_to_int` with `create=True`: an unused artificial
  attribute would not affect the function-local import and could make fault
  injection ineffective.
- If an implementation checkout instead has a module-level
  `from chapters import chinese_to_int`, the corresponding lookup is
  `verify.chinese_to_int`. Reinspect the actual lookup before choosing a target.
  Moving imports is not a required production change in this spec.

Fault injection must be observable in the real checker's actual-result
diagnostic and failure result. Asserting only that a mock was called does not
prove the checker detects the fault.

For isolated `main()` tests, unrelated checks may return controlled success or
failure results. When testing propagation of a numeral mismatch, keep the
numeral checker and `main()` real; do not replace either with a predetermined
failure result.

### D5 — Real entry-point/process verification

Use `subprocess` with the same interpreter as the test runner and the actual
`verify.py` file. Capture stdout, stderr and `CompletedProcess.returncode`.

AT8 has two real child-process paths:

1. **Success:** execute the actual file as a script, with the repository root as
   the working directory. Observe the process's natural exit code.
2. **Injected mismatch:** a test-only child launcher installs a controlled patch
   on `chapters.chinese_to_int` inside that child, then executes the actual file
   through `runpy.run_path` with `run_name="__main__"`. The file's own guard must
   invoke its real `main()` and `sys.exit(main())`.

The injected path must not call an imported `verify.main()` and fabricate its
own `sys.exit` in place of running the file's entry point. Do not stub `main()`,
patch `sys.exit`, suppress `SystemExit`, rewrite the file or add production fault
switches. A patch in the parent process alone is not the child's fault injection.

Use synthetic converter output only; keep the other script checks real in AT8.
If those checks fail independently, report their cause rather than claiming AT8
proved a numeral-specific result or expanding scope to fix them.

If the actual `__main__` guard no longer runs, or the script stops propagating a
failure to the process exit code, AT8 must fail. Capture alone is not acceptance:
assert the expected runtime diagnostics, summary counts and process return code.

Child setup must use isolated application configuration, avoid real credentials,
and ensure termination on timeout. Encoding and timeout details are test-harness
decisions for the subsequent plan; they do not change production behavior.

### D6 — Minimal documentation

Update only the relevant verification section of `INSTALL.md` to include:

- `python verify.py` from the repository root.
- `0`: the configured smoke checks reported success.
- `1`: a check reported failure or raised a caught exception.
- These checks do not establish complete application validation or external
  TTS/YouTube parity; this change corrects the numeral signal only.

Do not update historical pass counts or historical production-readiness reports.

### Data and state flow

```text
Five input/expected pairs
        ↓
Current converter → actual output
        ↓
Equality comparison + case diagnostic
        ↓
Sticky aggregate numeral result: True / False
        ↓
main(): combine with the three other checks
        ↓
Check-level success count + approved summary message
        ↓
main() returns 0 / 1
        ↓
Actual __main__ guard → sys.exit(main()) → process return code
```

| Event | Numeral state | Runner state |
| --- | --- | --- |
| Case matches | Preserve prior aggregate state. | Not yet aggregated by `main()`. |
| Case mismatches | Mark failure; later matches cannot clear it. | Checker eventually returns `False`. |
| Converter raises `Exception` | Preserve the existing propagation path. | `main()` records failure and continues its outer loop. |
| Four checks report success | — | Return `0`. |
| At least one check fails | — | Return `1`. |

## 7. Acceptance tests and reviews

**All items below are Not executed.** Expected outcomes are requirements, not
observed test results.

| ID | Scenario | Expected outcome |
| --- | --- | --- |
| AT1 | Actual numeral checker and converter on the five existing fixtures. | `True` when all match; expected `None` results count as success. |
| AT2 | Parameterized mismatch at each of the five positions, with the others matching. Include wrong numeric output and incorrect acceptance of an input expected to yield `None`. | Real checker returns `False`; diagnostic shows the injected actual output/input/expectation; later cases remain evaluated and cannot clear failure. |
| AT3 | Real numeral checker with a controlled mismatch; the other three checks report success. | Real `main()` returns `1`; summary reports `3/4`. This regression catches the original false positive. |
| AT4 | Numeral cases match; the other three checks report success. | `main()` returns `0`; summary reports `4/4`, not an expanded count of internal cases. |
| AT5 | Each other check separately returns `False` or raises `Exception`, with remaining checks reporting success. | Return `1`; count that check as failed; subsequent checks still run. |
| AT6 | Converter raises a synthetic exception. | Existing `main()` handling records failure and returns `1`; success output does not hide it. |
| AT7 | Runtime summary output on success and failure. | Approved D3 messages and correct counts; no whole-application-readiness assertion. Inspect emitted output, not source strings. |
| AT8 | Execute D5's actual script-success path and its injected-mismatch child path. | With the other checks succeeding: natural process return code `0` and `4/4` for success; `1`, numeral mismatch diagnostic and `3/4` for failure. The actual file runs as `__main__`; no simulated entry-point exit substitutes for it. |
| AT9 | Controlled tests in isolated configuration with network access unavailable; repeat controlled scenarios and restore resources. | No real data/account/secrets dependency; stable semantic results, no leaked patch or live child process. |
| AR1 | Review patch scope, interfaces and fixtures. | Only `verify.py`, `tests/test_verify.py` and minimal `INSTALL.md` changes; all four checks and five fixtures retained; no converter/chunker/UI/API/dependency changes. |
| AR2 | Review before/after evidence. | A numeral mismatch regression fails before the patch because the checker/main/process reports success, and succeeds afterward. Record commands, checkout and reasons. |
| AR3 | Review documentation. | Correct command, exit codes and limits in `INSTALL.md`; historical reports untouched. No prose-only automated test is required. |

AT1 and preservation tests may already succeed on the baseline. Red/green proof
must concern a regression that exposes this false positive, such as AT2, AT3 or
the failure path of AT8, rather than an unrelated import/environment error.

## 8. Requirements traceability matrix

| Requirement | Design | Acceptance |
| --- | --- | --- |
| R1 — equality and expected `None` | D1 | AT1, AT2 |
| R2 — aggregate failure cannot be cleared | D1 | AT2 |
| R3 — diagnostics and continued case evaluation | D1, D3 | AT2 |
| R4 — numeral failure reaches exit code | D1, D2, D5 | AT3, AT8 |
| R5 — preserve checks, exceptions and counts | D2 | AT4, AT5, AT6, AR1 |
| R6 — scoped summary messages | D3 | AT7, AT8 |
| R7 — regression and actual entry-point proof | D4, D5 | AT2, AT3, AT8, AR2 |
| R8 — minimal installation documentation | D6 | AR3 |
| N1 — offline/privacy | D4, D5 | AT9, AR1 |
| N2 — isolation/determinism | D4, D5 | AT9 |
| N3 — compatibility/scope | D1, D2, D4, D5 | AT1, AT5, AT6, AT8, AR1 |
| N4 — evidence/reviewability | D4, D5, D6 | AR1, AR2, AR3 |

## 9. Intent constraint audit

This table states the planned means of satisfying each constraint. Compliance
has not been established by implementation or runtime validation.

| Intent constraint | Design response | Verification |
| --- | --- | --- |
| Preserve conversion behavior. | Only aggregate checker outcomes; do not edit the converter. | AT1, AR1 |
| Offline regression with fixed/synthetic data. | Preserve five fixtures; inject controlled faults solely in test utilities. | AT2, AT9 |
| No real data, secrets or service accounts. | Isolated configuration and synthetic exceptions; no provider calls. | AT9, AR1 |
| Do not remove checks or cases. | Preserve four checks, five cases and existing exception continuation. | AT2, AT4–AT6, AR1 |
| Focused, reviewable, revertible change. | Limit deliverables to script, dedicated tests and minimal INSTALL explanation. | AR1 |
| Intent did not decide aggregation, injection, file organization or runner. | Q3–Q5 and D1–D5 make those choices explicit in the reviewed spec; do not imply they existed in the source intent. | Final Technical Lead spec review |

## 10. Policies/Skills and areas of concern

No repository-local `AGENTS.md`, `CLAUDE.md` or `SKILL.md` was found in the
repository inventory inspected for this task and the preceding assessment.
Repo-local Skills therefore remain **not found**; installed Skills outside the
repository do exist. Their installed paths are environment-specific, not files
to add to this patch.

Relevant installed Skills reviewed:

Inspected Skill root:
`/home/thienphuc/.codex/plugins/cache/openai-curated-remote/superpowers/6.4.2/skills`.
Paths in this list are relative to that installed root:

- `brainstorming/SKILL.md` (`superpowers:brainstorming`): understand intent and review design before implementation.
- `writing-plans/SKILL.md` (`superpowers:writing-plans`): applies to the later planning task, not permission to create a plan now.
- `test-driven-development/SKILL.md` and `test-driven-development/writing-good-tests.md`: exercise real behavior, use independent expectations and verify a meaningful failing regression.
- `verification-before-completion/SKILL.md`: no runtime pass claims without fresh evidence.
- `receiving-code-review/SKILL.md`: check reviewer feedback against the actual code before changing the design.
- `using-superpowers/SKILL.md`: direct user instructions take precedence over default Skill workflows.

P1 concerns require attention before implementing or accepting affected behavior.
P2 concerns are recorded without expanding the patch to resolve the whole system.

| ID | Priority | Concern/evidence | Required handling | Proposed owner |
| --- | --- | --- | --- | --- |
| A1 | P1 | Patch namespace depends on import placement; the actual import is function-local. E3. | Use D4's current lookup rule; do not assume `verify.chinese_to_int` exists or silently create it. Reinspect if the checkout changes. | Technical Lead |
| A2 | P1 | Mocking a checker to fail would not prove detection of a wrong conversion. TDD/test guidance prioritizes real code. | Keep checker/main real; inject only converter behavior; assert real diagnostics and outcomes. | Technical Lead |
| A3 | P1 | Returning `1` from a simulated helper does not prove the script entry point. E5. | AT8 must execute the actual file as `__main__`, preserve its `SystemExit` and inspect child return code. | Technical Lead / QA |
| A4 | P1 | Environment, optional pytest and full regression availability are unverified. E8. | Use standard-library new tests first; select supported offline regression commands, report missing dependencies/failures/skips and never claim an unavailable suite passed. | Technical Lead / QA |
| A5 | P2 | BUILD_PROMPT forbids web/React while README and code use them. `BUILD_PROMPT.md:7`, `README.md:3`, `frontend/src/App.tsx:2`. | Record the documentation conflict; do not change architecture in this patch. | Software Architect / documentation owner |
| A6 | P2 | Historical production-readiness claims are not evidence for the current checkout. `VERIFICATION_REPORT.md:363`; E1. | Use AR2's new evidence; preserve historical reports as required by Q2. | QA / Technical Lead |
| A7 | P2 | Chunking remains outside scope despite its weak success signal. E6. | Use approved scoped output; do not imply chunking validation was fixed. | Product Owner |
| A8 | P2 | Default Skill workflows may include writing/committing docs, plans or running tests; these stages have separate authorization. | This task creates only this spec. No plan, product code, test execution or commit follows automatically. | SDLC coordinator |
| A9 | P1 at acceptance | TDD requires meaningful red/green proof and project-suite verification; verification Skills reject unsupported success claims. | Record focused regression and appropriate project-suite results after implementation authorization; report unrelated failures without silently fixing them. | Technical Lead / QA |

## 11. Validation strategy for the subsequent implementation

The commands below are prescribed future validation, not commands executed while
creating this spec. They do not authorize dependency installation.

- New test module: `python -m unittest tests.test_verify -v`.
- Optional additional runner, if already supported:
  `python -m pytest tests/test_verify.py -q`.
- Related converter/normalization regression, when pytest is supported:
  `python -m pytest tests/test_chapter_normalization.py -q`.
- Broader Python regression using the documented suite command, when its
  dependencies are available and offline behavior has been checked:
  `QT_QPA_PLATFORM=offscreen python -m pytest -q`.

Broader suite availability and the appropriate offline regression set must be
documented in the subsequent plan. Do not present unittest discovery alone as
proof that pytest-style classes/fixtures were collected. Do not silently skip
required tests because a runner or Qt dependency is missing.

Record commands, interpreter/environment, checkout/working-tree state,
before/after output, failures, skips and limitations. Do not expand the patch to
fix unrelated failures or require live TTS/YouTube checks.

## 12. Approval record and planning follow-up

Q1–Q5 are recorded as resolved by owner review in §3. The patch location correction
is established from the inspected import scope; the real-entry-point requirement
is explicit in D5/AT8.

Approval record and remaining planning item:

| ID | Priority | Item | Owner | Status |
| --- | --- | --- | --- | --- |
| O1 | P1 | Final approval of this revised spec, including the import-scope explanation and D5's entry-point harness. | Project owner | Approved |
| O2 | P1 for validation planning | Identify the supported offline regression set and available environment; record concrete subprocess cleanup/timeout choices in the later plan. | Technical Lead / QA | Pending planning |

The next Coding Agent can plan from R1–R8, D1–D6, acceptance criteria and the RTM
without chat history. It must verify the source intent and this spec's approval
status, recheck lookup placement on its checkout and preserve the scope boundary.

No implementation plan, implementation code, test results or Git commit is
produced by the act of creating this specification.
