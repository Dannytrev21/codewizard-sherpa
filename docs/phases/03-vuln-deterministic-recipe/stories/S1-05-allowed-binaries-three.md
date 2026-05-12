# Story S1-05 — `ALLOWED_BINARIES` extension for `npm`, `ncu`, `java`

**Step:** Step 1 — Plant the two ABCs, the four Phase 0/1/2 additive edits, and the foundations every Phase 3 component consumes
**Status:** Ready
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0014

## Context

Phase 2 ADR-0005 added six binaries to `ALLOWED_BINARIES` (`scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks`, `docker`) under the Phase-1 per-binary-named precedent. Phase 3 introduces three new external CLIs: `npm` (lockfile resolution, install, test), `ncu` (npm-check-updates, used by the default `NcuRecipeEngine`), and `java` (used only when `--engine=openrewrite` is passed — opt-in). ADR-0014 captures the per-binary justification, pin granularity (`npm` minor / `ncu` patch / `java` major), and tool-readiness expectations.

This story is the surgical edit: extend `ALLOWED_BINARIES` to include the three new names and pin the credential-strip discipline unchanged. The actual per-tool wrapper modules (`tools/npm.py`, `tools/ncu.py`, `tools/openrewrite.py`) ship in Step 3 + Step 6 respectively; the readiness check that fails CLI startup loud lives in Step 5 (CLI body) and Step 6 (OpenRewrite). This story plants only the allowlist gate.

## References — where to look

- **Architecture:** `../phase-arch-design.md §"Component design" #4 (NpmPackageUpgradeTransform)`, `#5 (LockfileResolver)`, `#11 (ValidationGate)` — every npm-shell raise site.
- **Architecture:** `../phase-arch-design.md §"Development view — module tree"` — `Exec → exec.py (Phase 1 — ALLOWED_BINARIES extends)`.
- **Phase ADRs:** `../ADRs/0014-allowed-binaries-additions-npm-ncu-java.md` — ADR-0014 — per-binary purpose, pin granularity, sandbox profile, tool-readiness check, opt-in posture for `java`.
- **Phase ADRs:** `../ADRs/0003-recipe-engine-ncu-default-openrewrite-stub-registered.md` — ADR-0003 — `available()` returns `False` when `java` is missing (`no_engine` path); this story does **not** introduce the `available()` logic, only the allowlist.
- **Production ADRs:** `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — POC-to-service tool discipline.
- **Source design:** `../final-design.md §"Components" #6 LockfileResolver`, `§"Components" #7 ValidationGate` — npm/ncu/java raise sites.
- **Existing code:** `src/codegenie/exec.py` — `ALLOWED_BINARIES` set; Phase 1's initial set + Phase 2 ADR-0005's six additions.

## Goal

Extend `src/codegenie/exec.py`'s `ALLOWED_BINARIES` to include `npm`, `ncu`, `java`, preserve the existing credential-strip discipline byte-for-byte, and pin the three new entries with a unit test that asserts membership + credential-strip invariance.

## Acceptance criteria

- [ ] `src/codegenie/exec.py` `ALLOWED_BINARIES` includes `npm`, `ncu`, `java` in addition to the Phase 1 + Phase 2 entries; the existing entries are not edited or reordered (append-only).
- [ ] The credential-strip environment list (the env vars stripped before subprocess invocation, established in Phase 1/2) is unchanged — no edits to that list in this story.
- [ ] `tests/unit/exec/test_allowed_binaries_phase3.py` asserts (a) `"npm" in ALLOWED_BINARIES`, `"ncu" in ALLOWED_BINARIES`, `"java" in ALLOWED_BINARIES`; (b) all Phase 1 + Phase 2 entries remain in `ALLOWED_BINARIES` (regression guard); (c) the credential-strip env list matches a checked-in canonical list (regression guard) — the canonical list is captured from `git show HEAD:src/codegenie/exec.py` and pinned in the test as a literal.
- [ ] The test fails loud (Rule 12) if any prior binary was silently removed.
- [ ] No edits to `run_in_sandbox`, no new keyword arguments, no behavior change other than the allowlist membership. (The `test_execution=True` overlay edit is **S1-06**, a separate story.)
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/exec.py tests/unit/exec/test_allowed_binaries_phase3.py` pass.
- [ ] All Phase 0/1/2 tests for `exec.py` continue green (no regression).

## Implementation outline

1. Read `src/codegenie/exec.py` top-to-bottom — Rule 8. Identify the `ALLOWED_BINARIES` definition site and the credential-strip env list site.
2. Write `tests/unit/exec/test_allowed_binaries_phase3.py` red — asserts the three new names are present and that the full set + credential-strip env are exactly as captured.
3. Run the test once with the *current* `exec.py` to capture (via debug print or a one-off `python -c`) the full pre-edit `ALLOWED_BINARIES` set and the credential-strip env list. Bake those captures into the test as canonical pinned constants (`EXPECTED_PRE_PHASE3_BINARIES`, `EXPECTED_CRED_STRIP_ENV`). The test then asserts: post-edit `ALLOWED_BINARIES == EXPECTED_PRE_PHASE3_BINARIES | {"npm","ncu","java"}` and the env list unchanged.
4. Append the three new names to `ALLOWED_BINARIES`. Use the same data-structure style Phase 2 ADR-0005 used (likely a `frozenset[str]`; mirror exactly).
5. Run `pytest tests/unit/exec/test_allowed_binaries_phase3.py` and the Phase 1/2 `exec.py` tests; all green.
6. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/exec.py`.

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/unit/exec/test_allowed_binaries_phase3.py`.

```python
from codegenie.exec import ALLOWED_BINARIES, _CREDENTIAL_STRIP_ENV  # symbol may differ; match the actual name

# Captured from Phase 2 head — pinned to assert no Phase 0/1/2 regression
EXPECTED_PRE_PHASE3_BINARIES = frozenset({
    # Phase 1 set:
    "git", "node", ...,
    # Phase 2 set:
    "scip-typescript", "semgrep", "syft", "grype", "gitleaks", "docker",
})

EXPECTED_CRED_STRIP_ENV = (
    # captured verbatim from Phase 1/2 head — extends nothing in this story
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", ...
)

def test_phase3_adds_npm_ncu_java_only():
    expected = EXPECTED_PRE_PHASE3_BINARIES | {"npm", "ncu", "java"}
    assert ALLOWED_BINARIES == expected  # exact equality — no silent drift

def test_phase3_does_not_remove_prior_binaries():
    # Rule 12: fail loud if any prior binary was silently removed
    assert EXPECTED_PRE_PHASE3_BINARIES <= ALLOWED_BINARIES

def test_credential_strip_env_list_unchanged_in_phase3():
    # The credential-strip discipline does not change in this story
    assert tuple(_CREDENTIAL_STRIP_ENV) == EXPECTED_CRED_STRIP_ENV
```

Run; confirm `AssertionError` on the first test (the three new names are missing).

### Green — make it pass

- Append `"npm"`, `"ncu"`, `"java"` to `ALLOWED_BINARIES`. Match the existing data-structure type and ordering convention (alphabetical or insertion-order — match what is already there).
- Do not touch the credential-strip env list. Do not touch `run_in_sandbox`. Do not add wrapper code.
- Run the test; green.

### Refactor — clean up

- One inline comment beside each new entry: `# Phase 3 — ADR-0014` so a future reader sees the per-binary justification immediately.
- Confirm the Phase 1/2 tests for `exec.py` are still green.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/exec.py` | Append `npm`, `ncu`, `java` to `ALLOWED_BINARIES` |
| `tests/unit/exec/test_allowed_binaries_phase3.py` | New test pinning the three new entries + regression guard for prior entries + credential-strip env |

## Out of scope

- **`run_in_sandbox` `test_execution=True` overlay flag** — S1-06 (separate story).
- **Per-tool wrapper modules** (`tools/npm.py`, `tools/ncu.py`, `tools/openrewrite.py`) — Step 3 (npm + ncu) and Step 6 (openrewrite).
- **Tool-readiness check at CLI startup** — wires into the `codegenie remediate` body in Step 5; `java` readiness wires into `--engine=openrewrite` only in Step 6.
- **`tools/digests.yaml` extension** — extends in Step 3 (npm minor + ncu patch) and Step 6 (java major + openrewrite jar) with per-binary digest pins.
- **`NpmScriptsEnabled` raise site** — lives in `tools/npm.py` (Step 3); this story plants only the allowlist.

## Notes for the implementer

- This is the smallest, most surgical Step-1 edit. Resist the urge to add wrapper modules, readiness checks, or per-binary justification comments beyond the one-line `# Phase 3 — ADR-0014` marker. Rule 3 (surgical changes) and the splitting threshold in `High-level-impl.md` Step 1 both favor minimal diff here.
- **The credential-strip env list is verbatim from Phase 2.** Capture it as a literal in the test; do not import a constant if the constant happens to be re-exported (the test pinning is what catches a future silent removal). This is the same posture Phase 2 used for the Phase-1 binary set: the test embeds the canonical list as a tuple literal.
- **Frozenset vs set.** `ALLOWED_BINARIES` in Phase 1/2 is a `frozenset[str]`. Keep it frozenset — Rule 11. If a future implementer needs to add a binary at runtime, they file an ADR and amend the source; the frozenset prevents accidental mutation.
- **Alphabetical vs insertion order.** Phase 2 ADR-0005's six additions appear in insertion order in `ALLOWED_BINARIES`. Match that — append `"npm"`, `"ncu"`, `"java"` in that order at the bottom. The test asserts membership, not ordering, so the ordering decision is for readability only.
- **`java` is opt-in, but its allowlist membership is unconditional.** A developer running `codegenie remediate --engine=ncu` (the default) never invokes `java` — the readiness check skips it. But if a malicious recipe somehow declared `engine: java` in its YAML and the selector emitted it, `run_in_sandbox` must accept the invocation. The opt-in is at the readiness check + selector layer, not the allowlist.
- The test file's location (`tests/unit/exec/`) mirrors Phase 2's S1-03 organization. Create the directory if it does not yet exist; add `tests/unit/exec/__init__.py` if needed.
- Do not skip the "all Phase 0/1/2 tests still green" CI run — silent removal of an allowlist entry would compile fine but break a downstream gather; the regression test catches it.
