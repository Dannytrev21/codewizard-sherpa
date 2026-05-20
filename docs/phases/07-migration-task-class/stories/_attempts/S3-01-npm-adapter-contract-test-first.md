# Attempt log: S3-01 — `test_provenance_assembly_via_plugins.py` contract test (red-first)

## Attempt 1 — 2026-05-20 — SUCCESS

**Approach:** Red-first TDD. The test file IS the deliverable — S3-01 pins the
cross-component contract (plugin-load → `@register_provenance_adapter` side
effect → `assemble_provenance` dispatch → typed `Provenance`) BEFORE the npm
adapter body lands in S3-02. Shipped three positive-path scenarios as
`xfail(strict=True)` plus one passing red-state canary, the conftest
registry-isolation fixture, and the pinned SBOM fixture.

**Files shipped (all new — no Phase 0–6.5 byte-edits; ADR-0009 fence N/A):**
- `tests/integration/test_provenance_assembly_via_plugins.py`
- `tests/integration/conftest.py` (autouse `provenance_registry_reset`)
- `tests/integration/_fixtures/syft_sboms/npm_lodash_app.json`

**Runtime evidence:**
`pytest tests/integration/test_provenance_assembly_via_plugins.py -v --no-cov`
→ `1 passed, 3 xfailed` — exactly the Implementation-outline step-6
expectation. The red-state canary asserts `Unknown(reason="no_adapter_resolved")`
(the `(None, None)` arm of `assembly.py` — no `(Layer.APP, Ecosystem.NPM)`
adapter is registered); the three positive-path scenarios fail against that
same outcome and are therefore strict-xfailed.

**Environment defect found + fixed (NOT a code defect, NOT caused by S3-01):**
The venv's editable `codegenie` install pointed at a stale git worktree
(`.claude/worktrees/thirsty-cray-9765a4/src/codegenie`) left by an in-flight
PR, not the main repo's `src/codegenie`. That worktree predates master's
`8acdb98` / `bcb46ae` (types↔probes cold-start cycle fix), so the first
`make check` reported 29 failures — all in `tests/fence/`, `tests/golden/`,
`tests/unit/types/`, none in S3-01's files. Diagnosed via
`python -c "import codegenie; print(codegenie.__file__)"`; re-pointed with
`pip install -e . --no-deps` from the main repo root; all 29 cleared.
Recorded in `_lessons.md`.

**Deviations from the story spec (surfaced for human review):**
- **AC-8 — `ImageRef.parse(...).unwrap()` does not exist.** `ImageRef` is a
  bare `NewType` over `str` (`codegenie/types/identifiers.py:149`); S1-01
  shipped it as a `NewType`, not a smart-constructor class. Constructed
  directly as `ImageRef("alpine:3.18@sha256:" + "0" * 64)`. The AC's *intent*
  (a non-empty Alpine ref the test does not exercise) is satisfied; the code
  carries an explanatory comment.
- **AC-1 — no `@pytest.mark.integration` marker.** `--strict-markers` is on
  and `integration` is not a registered marker; the existing `tests/integration/`
  suite uses no module-level marker. Took AC-1's "or whichever marker the
  existing integration suite uses — match conventions" escape clause → no
  marker.
- **AC-10 is internally contradictory; followed the self-consistent reading.**
  AC-10's prose says `test_red_state_when_no_npm_adapter_registered` is marked
  `xfail(strict=True)`. That is impossible: the red-state test PASSES today, so
  `xfail(strict=True)` on it would XPASS → strict failure → CI red immediately,
  contradicting AC-9 ("CI does not block on the red"), Implementation-outline
  step 6 ("Expect: 1 passed, 3 xfailed"), and the TDD plan ("the one red-state
  test passes"). The `xfail(strict=True)` discipline belongs to the THREE
  positive-path scenarios. Shipped that reading — runtime confirms
  `1 passed, 3 xfailed`.
- **Single SBOM fixture for three scenarios.** AC-7 names one file
  (`npm_lodash_app.json`); AC-2's three scenarios conceptually need different
  repo states (lodash-direct vs express→lodash-transitive vs absent). In the
  RED phase no adapter runs, so fixture contents do not affect behavior — all
  three xfail tests compose to `Unknown(no_adapter_resolved)` regardless.
  Shipped the one file AC-7 names (lodash + express artifacts). S3-02, which
  owns the adapter discrimination logic, will add scenario-specific fixtures.

**Refactor decisions:**
- `_assemble(package_id)` helper — a small DRY seam used by all 4 tests; not a
  premature abstraction (4 call sites).
- Domain values use the `CveId` / `PackageId` / `ImageRef` newtypes throughout;
  the result is inspected by `match` / `case` over the `Provenance` sum type,
  never `isinstance` (ADR-0006 discipline).
- `conftest.py` mirrors the established `provenance_registry_reset`
  snapshot/clear/restore fixture (the unit + property copies) — reinforces the
  existing pattern rather than inventing a new one.
- The test exercises the public Ports & Adapters seam only (`load_plugins`,
  `assemble_provenance`) — never an adapter class directly. That is the story's
  whole point, not a discretionary refactor.

**Follow-ups surfaced this attempt:**
- Green-phase handoff is mechanical: S3-02 removes the three `xfail` markers;
  S3-03 deletes / inverts `test_red_state_when_no_npm_adapter_registered`. The
  shared `_GREEN_WHEN` reason string makes the xfail removal a single grep.
- Module-import caching: once the npm plugin exists, `load_plugins` imports
  `api.py` once per process, while the autouse registry-reset clears `_REGISTRY`
  between tests. S3-03 must ensure registration survives (or re-fires) per
  test. Flagged for S3-03; out of S3-01's scope (no plugin exists yet).

**Validator report (Stage 3):** All 13 ACs verified against runtime behavior
(see story-file evidence block). Cross-cutting gates — `ruff format --check`,
`ruff check`, `mypy --strict` on both new `.py` files, and the full `make check`
regression suite (lint → typecheck → test → fence) — all green once the venv
editable install was re-pointed at the main repo. New file contributes
`1 passed, 3 xfailed`; no existing test disabled or weakened.
