# Story S7-05 — Phase-2 regression hard-gate: `test_phase2_unchanged.py`

**Step:** Step 7 — Harden — ≥ 30 adversarial fixtures, determinism canary, perf canaries, Phase-2 regression hard-gate, Phase-4 handoff verification, CI gates
**Status:** Ready
**Effort:** S
**Depends on:** S7-01 (fixture portfolio — the test runs against the `nestjs/nest` pinned fixture from Phase 2 + uses the Phase-3 mirror as needed), S1-06 (the single Phase-2 chokepoint amendment: `run_in_sandbox(test_execution=True)` overlay flag — this is the Phase-2 edit that this hard-gate verifies did not regress)
**ADRs honored:** ADR-0005 (the `test_execution=True` overlay is the single additive Phase-2 amendment Phase 3 is allowed; the regression gate proves the amendment is non-breaking), Phase 2 ADR-0001 (`consumes_peer_outputs` contract not weakened), Phase 2 ADR-0003 (subprocess sandbox profile extension), Phase 2 ADR-0004 (`tools/digests.yaml` pin manifest — Phase 3 extends it without breaking the prior contract), Phase 2 ADR-0012 (audit chain BLAKE3 rolling head — Phase 3 extends event-type enum without changing the chain shape)

## Context

Phase 3 makes **exactly four** additive edits to Phase 0/1/2 code (per the cross-cutting concerns in `stories/README.md`):

1. `exec.py` — `ALLOWED_BINARIES +3` (S1-05, ADR-0014).
2. `exec.py` — `test_execution=True` overlay flag (S1-06, ADR-0005 — the **single Phase-2 chokepoint amendment**).
3. `audit_writer.py` — event-type enum extension (S1-07, ADR-0010).
4. `skills/models.py` — `applies_to.cve_patterns` additive field (S1-08, ADRs README #1).

The riskiest of these is #2 — the `test_execution=True` overlay flag amends Phase 2's `run_in_sandbox` chokepoint. Phase 2's contract is that **the gather pipeline never invokes `npm install`** (Phase 2 ADR-0013 — `node_modules` never written by gather); Phase 3's overlay carves out a single new pathway that **does** invoke npm + executes tests, but only when the caller explicitly sets `test_execution=True`. The amendment is meant to be **strictly additive** — every Phase-2 caller continues to pass `test_execution=False` (or omits the parameter via its default), and every Phase-2 invariant continues to hold.

This story is the **regression hard-gate** that verifies the amendment is actually non-breaking. It re-runs **every Phase-2 integration test verbatim** against the `nestjs/nest` pinned fixture from Phase 2 (the same fixture Phase 2's S8-02 established) and asserts every Phase-2 invariant continues to hold. This is the Phase-7 precedent from Phase 2 (where Phase 2's bench-gate re-ran Phase 1's bench), applied at Phase 3.

The test is **mechanically simple**: it imports every test under `tests/integration/` matching the pattern `test_phase2_*` (or `test_gather_*` — whatever convention Phase 2's integration suite uses) and re-runs them as a subprocess invocation of pytest. If any Phase-2 test red-fails, this story's gate red-fails, and the PR is blocked. The test does **not** re-implement Phase 2's test logic; it delegates.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" §"Integration tests"` — line `test_phase2_unchanged.py` referenced explicitly.
  - `../phase-arch-design.md §"Edge cases"` — Phase 2 regression possibility flagged.
  - `../phase-arch-design.md §"Roadmap coherence check" §"Prior phases this depends on"` — Phase 2's chokepoint pattern.
- **Phase ADRs:**
  - `../ADRs/0005-single-sandbox-profile-test-execution-overlay-signal-escalate.md` — the amendment whose non-regression this story verifies.
- **Production ADRs:** `../../../production/adrs/` — no direct dependency.
- **Source design:**
  - `../final-design.md §"Test plan" §"Integration tests"` — `test_phase2_unchanged.py` named.
  - `../High-level-impl.md §"Step 7"` — story row.
- **Phase 2 references (the contract this gate enforces):**
  - `../../02-context-gather-layers-b-g/phase-arch-design.md §"Goals"` — every Phase-2 exit criterion is what this gate keeps from regressing.
  - `../../02-context-gather-layers-b-g/ADRs/0001-peer-outputs-binding.md` through `0013-scip-node-modules-conditional-mount.md` — every Phase-2 ADR's invariant must continue to hold.
  - `../../02-context-gather-layers-b-g/stories/S8-02-*.md` (if present) — the `nestjs/nest` real-OSS fixture story.
- **Existing code:**
  - `src/codegenie/exec.py` — read after S1-06 lands to confirm the overlay is additive (default `test_execution=False`; every existing Phase-2 caller unchanged).
  - `tests/integration/test_gather_*.py` (Phase 2's integration suite) — the test list this gate re-runs.
- **Style reference:**
  - `../../02-context-gather-layers-b-g/stories/` — Phase 2's regression-related stories are the closest analog; otherwise this gate's pattern is new.

## Goal

Land `tests/integration/test_phase2_unchanged.py` that re-runs every Phase-2 integration test verbatim against the `nestjs/nest` pinned fixture, so any Phase-2 regression caused by the four Phase-3 additive edits (especially S1-06's `test_execution=True` overlay) is caught at merge time.

## Acceptance criteria

- [ ] `tests/integration/test_phase2_unchanged.py` exists and is green on `main`.
- [ ] The test enumerates **every** Phase-2 integration test file (the glob `tests/integration/test_gather_*.py` plus any phase-2 named integration tests) and re-runs them as a single pytest subprocess invocation, asserting exit code 0.
- [ ] The subprocess invocation uses the **same Phase 2 fixtures** (the `nestjs/nest` pinned fixture from Phase 2 + any other real-OSS fixtures the integration suite consumed). It does **not** consume Phase 3 fixtures from S7-01.
- [ ] The test fails loud if any Phase-2 integration test was **deleted** or **renamed** since the gate was established — the gate compares the current Phase-2 test set against a frozen list embedded in the test (or a checked-in `tests/integration/phase2_test_manifest.txt`); a missing test red-fails with a structured message ("Phase 2 integration test `test_gather_X` is missing — did a Phase-3 PR delete it? Phase-2 tests are append-only").
- [ ] The test exit code is propagated faithfully: a Phase-2 test red-fail → this gate red-fails with the originating test's name in the message.
- [ ] The test runs in **≤ 5 minutes** on the CI runner (`nestjs/nest` real-OSS gather is the largest single integration test; sub-tests run in parallel where Phase 2's suite supports it).
- [ ] The test is registered under `pytest.mark.phase2_regression`; S7-07 wires a CI job that selects it.
- [ ] A docstring at the top of the test file explains: (a) the four Phase-3 additive edits this gate guards against regressing, (b) the procedure for legitimately retiring a Phase-2 test (requires an ADR amendment), (c) the manifest's frozen-list semantics.
- [ ] If a Phase-2 test red-fails through this gate, the failure message includes a one-liner pointing at the **likely Phase-3 edit** that caused the regression (the four additive edits enumerated; the test maps Phase-2 failure modes to the most likely Phase-3 cause heuristically).
- [ ] The frozen manifest `tests/integration/phase2_test_manifest.txt` is checked in as part of this story; its initial content is `find tests/integration -name 'test_gather_*.py' -o -name 'test_phase2_*' | sort > tests/integration/phase2_test_manifest.txt` (captured at story-merge time).

## Implementation outline

1. **Establish the manifest.** Run `find tests/integration -name 'test_gather_*.py' -o -name 'test_phase2_*' | sort > tests/integration/phase2_test_manifest.txt`. The manifest is a sorted list of test-file paths. Commit it as part of this story.
2. **Write the gate test.** `test_phase2_unchanged.py` reads the manifest, then:
   - **Drift check**: enumerate `find tests/integration -name 'test_gather_*.py' -o -name 'test_phase2_*' | sort`; assert the current set is a **superset** of the manifest (additions are fine; removals are not). If a test was removed, red-fail with the missing file name.
   - **Re-run check**: invoke `pytest --tb=short <manifest contents> -m "not slow_adv"` as a subprocess; capture exit code; assert exit code is 0.
   - **Diagnostic on red**: on non-zero exit, capture the subprocess's pytest output, scan for the failing test name, look up the test against a heuristic-to-Phase-3-edit map (e.g., `test_run_in_sandbox_*` → S1-06 overlay; `test_audit_chain_*` → S1-07 enum; `test_allowed_binaries_*` → S1-05 + S6-01; `test_skills_load_*` → S1-08), and emit a structured failure message naming the likely cause.
3. **Wire the heuristic map.** A small dictionary in the test file:
   ```text
   PHASE3_EDIT_HEURISTICS = {
     "test_run_in_sandbox": "S1-06 — test_execution=True overlay flag (ADR-0005)",
     "test_audit_chain": "S1-07 — event-type enum extension (ADR-0010)",
     "test_allowed_binaries": "S1-05 or S6-01 — ALLOWED_BINARIES additions (ADR-0014)",
     "test_skills_load": "S1-08 — applies_to.cve_patterns additive field",
   }
   ```
   On red-fail, scan the failing test name against keys; emit the matching value in the failure message. If no heuristic matches, emit a generic "scan recent Phase-3 PRs touching `src/codegenie/exec.py`, `src/codegenie/audit_writer.py`, or `src/codegenie/skills/models.py`."
4. **Register the marker.** `pytest.mark.phase2_regression` in `pyproject.toml`'s `[tool.pytest.ini_options]` `markers` list.
5. **Document the legitimate-retirement procedure.** The docstring at the top of `test_phase2_unchanged.py` (and a corresponding section in `docs/runbooks/phase2-test-retirement.md`, lightweight) explains: a Phase-2 test can be retired only via an ADR amendment that documents the invariant the test pinned and how it's now redundant (e.g., subsumed by a Phase-3 test). The manifest is updated in the same PR.

## TDD plan — red / green / refactor

### Red — write the failing test first

Path: `tests/integration/test_phase2_unchanged.py`

```python
"""ADR-0005 (S1-06) + ADR-0010 (S1-07) + ADR-0014 (S1-05) + S1-08 (Skills) | Invariant: every Phase-2 integration test continues to pass verbatim after Phase-3's four additive Phase-0/1/2 edits.

The four edits this gate guards against regressing:
1. S1-05 — `ALLOWED_BINARIES += ["npm", "ncu", "java"]` (ADR-0014).
2. S1-06 — `run_in_sandbox(test_execution=True)` overlay (ADR-0005).
3. S1-07 — `AuditEvent.event_type` enum extension (ADR-0010).
4. S1-08 — `Skill.applies_to.cve_patterns` additive field.

Legitimate retirement: a Phase-2 test can be removed from the manifest only via an ADR amendment that documents the invariant the test pinned and how the invariant is now redundant.
"""

@pytest.mark.phase2_regression
def test_phase2_integration_manifest_is_superset() -> None:
    """Current tests/integration/test_gather_*.py set is a superset of the frozen manifest; missing tests red-fail."""

@pytest.mark.phase2_regression
def test_phase2_integration_suite_passes_verbatim() -> None:
    """Re-run every Phase-2 integration test as a subprocess; exit 0 expected."""

@pytest.mark.phase2_regression
def test_red_fail_surfaces_likely_phase3_edit_cause(monkeypatch) -> None:
    """If a Phase-2 test red-fails, the failure message names the likely Phase-3 edit that caused the regression."""
```

The third test exercises the diagnostic path: monkeypatch the subprocess invocation to simulate a `test_run_in_sandbox_basic_isolation` red-fail, and assert the gate's failure message contains the substring `"S1-06"` and `"test_execution=True"`.

### Green — make each one pass

Green requires three things:

1. **The manifest is correct.** Run the `find` command at story-merge time, commit the output.
2. **The subprocess pytest invocation is faithful.** It uses `sys.executable -m pytest <manifest contents>` so the same interpreter / packages / coverage harness applies. Pass `--no-cov` if the parent invocation is already collecting coverage (to avoid double-instrumentation issues).
3. **The diagnostic-on-red actually triggers.** The third test is what verifies this; without it, a future PR that drops the diagnostic is invisible until the gate actually red-fails.

The most common first failure: the subprocess pytest invocation finds the tests but red-fails because a Phase-2 fixture path is relative-to-cwd and the subprocess cwd is different. Fix by passing `cwd=repo_root` explicitly or by ensuring Phase-2 tests use `Path(__file__).parent` patterns (which Phase 2's S8-02 likely already does — verify before adding workarounds here).

### Refactor — clean up

After green:

- **Wall-clock budget.** Confirm the gate completes in ≤ 5 min on the CI runner. If the `nestjs/nest` integration is slower than that, surface as a parallelism follow-up.
- **Manifest sort order.** Use `sort -u` to dedupe + sort the manifest; future regenerations should produce a byte-identical file when the test set is unchanged.
- **Confirm `pytest.mark.phase2_regression`** is registered in `pyproject.toml`.
- **Run the gate locally** against `main` with no Phase-3 edits and assert it green-passes; then locally apply a deliberate break (e.g., comment out a line in `src/codegenie/exec.py` that S1-06 added) and assert it red-fails with the right diagnostic; revert.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase2_unchanged.py` | The regression hard-gate. |
| `tests/integration/phase2_test_manifest.txt` | Frozen list of Phase-2 integration tests; checked in. |
| `pyproject.toml` (extend) | Register `phase2_regression` pytest marker. |
| `docs/runbooks/phase2-test-retirement.md` | Lightweight runbook for the ADR-amendment-gated retirement procedure (≤ 50 lines). |

## Out of scope

- **Phase 2 source code changes.** This story does not edit Phase 2 production code; it pins the regression contract.
- **Phase 2 test changes.** This story does not edit Phase 2 tests; it re-runs them verbatim.
- **Phase 2 fixture changes.** This story does not touch `tests/fixtures/<phase-2-fixtures>/`; it consumes them as-is.
- **The determinism canary, perf canaries, adversarial corpus, Phase-4 handoff test.** S7-02, S7-03, S7-04, S7-06.
- **CI workflow wiring.** S7-07 wires the `phase2_regression` job.
- **Replacing an existing Phase-2 test.** If a Phase-2 test is genuinely obsolete, the retirement procedure (ADR amendment) is documented but the procedure itself is out of scope to exercise.
- **Cross-phase test harmonization.** Phase 2 and Phase 3 may use different test fixtures, different conftest helpers, different invocation styles; this gate accepts whatever Phase 2 ships and re-runs it as-is.

## Notes for the implementer

- **The manifest is the single source of truth for "what tests Phase 2 requires."** If a Phase-3 PR genuinely retires a Phase-2 test, the same PR must (a) update the manifest, (b) cite the ADR amendment that authorizes the retirement, (c) explain the redundancy. Without all three, the gate red-fails the PR.
- **The diagnostic-on-red is what makes the gate useful.** A raw "Phase 2 tests failed" message tells the operator nothing about which Phase-3 edit caused the regression. The heuristic map shortens debugging by ~80%; pin it with its own test (#3 in the red section).
- **`subprocess.run` invocation is load-bearing.** Direct in-process pytest invocation inherits the parent process's monkeypatches, conftest state, and fixtures, which silently bypasses some Phase-2 invariants. The subprocess invocation is what makes the gate faithful to "verbatim Phase 2."
- **Phase 2's `nestjs/nest` fixture is large (real-OSS).** It dominates the wall-clock. If the gate's budget pressure becomes load-bearing, the right response is to parallelize Phase 2's integration suite (`pytest -n auto`) rather than to skip tests.
- **Append-only is the discipline.** Phase 2's invariants are append-only; new Phase-2 tests added in a later phase are welcome (they extend the gate). Retirements require ADR amendment. This is the same discipline as Phase 2's ABC snapshot tests and Phase 1's frozen contracts.
- **Phase-2 tests using `subprocess.run`-time-flaky behavior (network, real binaries) should already be `slow_adv`-marked in Phase 2 itself.** This gate excludes `slow_adv` to keep the budget; the markers are Phase 2's responsibility. If a Phase-2 test is too slow but isn't marked, surface as a Phase-2 follow-up — do not silently exclude it from this gate.
- **The retirement runbook is intentionally lightweight.** The full discipline is in the ADR amendment process; the runbook is a navigation aid. Resist the urge to grow it past ~50 lines.
- **This gate is the only Phase-3 story that re-runs Phase-2 tests.** S7-06 (Phase-4 handoff contract) is forward-looking; S7-05 is backward-looking. Both gates together fully bracket Phase 3's adjacency to the prior + next phase.
