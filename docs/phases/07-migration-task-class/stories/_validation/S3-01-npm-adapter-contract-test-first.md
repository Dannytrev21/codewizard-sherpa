# Validation report: S3-01 — `test_provenance_assembly_via_plugins.py` contract test (red-first)

**Story:** [`../S3-01-npm-adapter-contract-test-first.md`](../S3-01-npm-adapter-contract-test-first.md)
**Validator run:** 2026-08-14 (scheduled-task `story-validation-corrector`)
**Verdict:** **HARDENED — story-text reconciled against landed reality; one carry-forward fixture defect surfaced as a follow-up (owned by S3-02)**

## Summary

S3-01 shipped GREEN on 2026-05-20 in one attempt. The attempt log documents three story-vs-reality deviations the executor absorbed at ship-time:

1. **AC-8** referenced a non-existent `ImageRef.parse(...).unwrap()` smart constructor (`ImageRef` is a bare `NewType[str]` in `codegenie.types.identifiers` — no `Result` monad).
2. **AC-1** prescribed `@pytest.mark.integration`, but `--strict-markers` is on and `integration` is not registered; the existing `tests/integration/` suite carries no module marker.
3. **AC-10** was internally contradictory: prose said the red-state canary `test_red_state_when_no_npm_adapter_registered` was `xfail(strict=True)`, but that test PASSES today (asserting the very `Unknown(no_adapter_resolved)` outcome the red state produces). `xfail(strict=True)` on a passing test XPASSes → CI red — which directly contradicts AC-9 ("CI does not block on the red") and the TDD plan.

A fourth deviation is subtler and was NOT surfaced at ship-time — but WAS surfaced by the downstream S3-02 validation (Blocker F, 2026-08-14): the pinned SBOM fixture (`npm_lodash_app.json`) has both `lodash` and `express` at depth 1 in `node_modules/`. In the RED state (no adapter registered) this is invisible — every scenario resolves to `Unknown(no_adapter_resolved)` regardless of fixture shape, so the three positive-path tests all xfail cleanly. But when S3-02 removes the `xfail` markers, the transitive test will HARD-FAIL because the landed classifier will read `lodash` at depth 1 and produce `AppDirect`, not `AppTransitive`. The fixture defect is a load-bearing precondition for S3-02's un-xfail step.

This validation is retrospective — the executor and the shipped code are correct. The story text has been reconciled against landed reality (AC-1, AC-8, AC-10 rewritten in place), the fixture-depth invariant has been promoted to an explicit AC with a "known gap" callout, autouse-fixture scope has been pinned as a new AC, and the fixture defect + cassette absence + ADR-0009 contradiction have been documented under a "Notes for follow-up" block.

**No shipped code was touched.** No re-implementation. The validator's job on a GREEN story is to bring the story text up to the standard of the shipped reality, so future readers (and the executors of S4-02 / S4-03 sibling contract tests) can rely on the story as an accurate template.

## Context Brief

**Story snapshot:**
- **Goal:** Land red-first integration contract test pinning `plugin-load → @register_provenance_adapter → assemble_provenance → typed Provenance` for the npm app-layer adapter.
- **Non-goals:** Implement `NpmVulnProvenanceAdapter` (S3-02); wire `api.py` import (S3-03); base-image coverage (S4-02, S4-03); property tests on `assemble_provenance` (S2-05).
- **Effort:** S. Effort matched — 1 attempt, 3 files, single-day ship.

**Landed reality (from `tests/integration/test_provenance_assembly_via_plugins.py`, verified 2026-08-14):**
- 4 test scenarios: 3 positive-path decorated `@pytest.mark.xfail(strict=True, reason=_GREEN_WHEN)`; 1 red-state canary that passes.
- `_GREEN_WHEN` is a module-level constant — DRY seam for the S3-02 handoff (single grep removes all three markers).
- `_assemble(package_id)` helper drives `load_plugins(_PLUGIN_ROOT, _PLUGIN_LOCK)` + `assemble_provenance(...)` for all 4 tests. Zero direct `_REGISTRY` access. Zero direct adapter class import.
- Runtime today: `1 passed, 3 xfailed`.
- `tests/integration/conftest.py` provides autouse `provenance_registry_reset` (snapshot-clear-restore) at function scope.
- Fixture: `_fixtures/syft_sboms/npm_lodash_app.json` — two artifacts, `lodash@4.17.20` at `node_modules/lodash/…` and `express@4.18.2` at `node_modules/express/…`. **Both depth 1.**

**Phase / arch constraints honored:**
- **ADR-0004** (primitive home): test imports from `codegenie.primitives.vuln_provenance` — public surface only.
- **ADR-0006** (`_ADAPTER_DISPATCH_ORDER` `Final` tuple): test exercises the `_ADAPTER_DISPATCH_ORDER` walk via `assemble_provenance`; never `dict.items()`; never `sorted(...)` of the registry.
- **ADR-0007** (registry stores classes): test invokes plugin-loader import side effect; never `_REGISTRY[key] = cls()`; never construction at decorator time.
- **ADR-0009** (10-row byte-edit allowlist): story adds ZERO Phase 0–6.5 file edits (only new files under `tests/integration/`). Allowlist rows are consumed by S3-02 (`npm_provenance.py`) and S3-03 (`api.py` / `tccm.yaml`).

## Findings by critic lens

Consolidated + de-duplicated across four inline critics (Coverage, Test-Quality, Consistency, Design-Patterns).
Severity: **block** = story-vs-reality contradiction the executor absorbed at ship-time; **harden** = story ships correctly but weakens future maintenance; **nit** = cleanup.

### F1 (Consistency, AC-8) — `ImageRef.parse(...).unwrap()` does not exist [block, resolved by rewrite]

`grep -n 'class ImageRef\|ImageRef =' src/codegenie/types/identifiers.py` → `ImageRef = NewType("ImageRef", str)` at line 149. No `.parse()`, no `.unwrap()`, no smart constructor. The executor constructed directly (`ImageRef("alpine:3.18@sha256:" + "0" * 64)`) and carried an explanatory comment.

**Fix (applied 2026-08-14):** rewrote AC-8 to specify the direct-construct form and named the intent ("test uses an Alpine ref only because the assembly seam forwards it to registered adapters"). Docstring `_IMAGE_REF` in the landed test already carries this rationale.

### F2 (Consistency, AC-1) — `@pytest.mark.integration` is unregistered [block, resolved by rewrite]

`pyproject.toml [tool.pytest.ini_options]` sets `addopts` including `--strict-markers`; `markers = ["bench", "adv", "phase02_adv"]` does NOT include `integration`. The AC's "or whichever marker the existing integration suite uses — match conventions" escape clause was the load-bearing half; the primary "with `@pytest.mark.integration`" is the misleading half.

**Fix (applied 2026-08-14):** rewrote AC-1 to primarily assert *no* module-level marker (matches shipped file) and named the convention (the directory itself is the marker).

### F3 (Consistency, AC-10) — Red-state canary xfail contradiction [block, resolved by rewrite]

Original AC-10: "The test asserts `Unknown(reason="no_adapter_resolved")` in a `test_red_state_when_no_npm_adapter_registered` scenario that is marked `xfail(strict=True, reason=...)` — so CI does not block on the red, but a passing red would fail strict."

This is self-contradictory. In the RED state, the canary PASSES (asserts the outcome the empty-registry state produces). `xfail(strict=True)` on a passing test XPASSes → strict → CI red. That directly contradicts AC-9 ("At commit time of this story's PR, the test is RED" but "CI does not block on the red") and the TDD plan's Green section ("the one `test_red_state_when_no_npm_adapter_registered` test passes").

The self-consistent reading is: the strict-xfail discipline lives on the **three positive-path scenarios** (they fail RED under empty registry, will pass GREEN under S3-02, and xfail-strict catches "passing for the wrong reason" during handoff). The **red-state canary** is a plain passing test — no marker.

**Fix (applied 2026-08-14):** rewrote AC-10 to explicitly separate the three xfail-marked positive scenarios from the unmarked red-state canary, name `_GREEN_WHEN` as the DRY seam, and describe the mechanical S3-02+S3-03 handoff (S3-02 removes the three markers; S3-03 deletes/inverts the canary once registration actually fires via `load_plugins`).

### F4 (Consistency + Coverage, AC-13) — `bench/vuln-remediation/` cassette does not exist [block-then-harden]

Original AC-13: "**Phase 3–6.5 regression suite green** (`make check` excluding the `xfail` line counts as green per the pre-merge gate; the cassette replay is byte-equal)."

`ls bench/vuln-remediation/` → No such file or directory. The cassette-replay clause is aspirational — Phase 3 owes the cassette; Phase 7 does not synthesize one. Same finding as S3-02 validation Blocker B.

For S3-01 specifically the impact is trivial: S3-01 ships only new files (`tests/integration/*` and `tests/integration/_fixtures/*` — none on the allowlist surface), so cassette-byte-equivalence is preserved by construction (nothing under `plugins/` or `src/codegenie/` changed).

**Fix (applied 2026-08-14):** removed the "cassette replay is byte-equal" clause from AC-13; documented why S3-01 preserves cassette-equivalence trivially; added the cassette absence as a follow-up bullet cross-referenced to S3-02 Blocker B.

### F5 (Coverage — carry-forward fixture defect) — SBOM fixture masks depth-invariant gap [block, deferred to S3-02]

The three positive-path scenarios semantically require distinct fixture shapes:

- `test_npm_adapter_returns_app_direct_for_root_dependency`: `PackageId("lodash")` at `node_modules/lodash/…` (depth 1) → `AppDirect`.
- `test_npm_adapter_returns_app_transitive_for_deep_dependency`: `PackageId("lodash")` at `node_modules/express/node_modules/lodash/…` (depth ≥ 2) → `AppTransitive` with `chain[0] == PackageId("express")`.
- `test_npm_adapter_returns_unknown_when_package_absent`: `PackageId("not-in-this-repo")` absent → `Unknown(sbom_layer_attribution_absent)`.

The shipped fixture has BOTH `lodash` AND `express` at depth 1. The direct + absent scenarios are satisfied; the transitive scenario is NOT satisfied (there is no deeper `lodash` path in the fixture, and both direct tests currently query the same `PackageId("lodash")`).

**Today (RED state):** invisible. No adapter is registered → assembly returns `Unknown(no_adapter_resolved)` for all three scenarios → all three xfail with the "wrong variant" `pytest.fail(...)` arm → CI green.

**When S3-02 lands and removes the three xfail markers:**
- `test_..._app_direct_for_root_dependency` passes (`lodash` at depth 1 → `AppDirect(package=PackageId("lodash"))`).
- `test_..._app_transitive_for_deep_dependency` FAILS — `lodash` at depth 1 → `AppDirect`, not `AppTransitive`. The `case AppTransitive() as app:` arm never matches; `case _:` falls through to `pytest.fail(f"expected AppTransitive, got: {result!r}")`.
- `test_..._unknown_when_package_absent` passes (`not-in-this-repo` absent → `Unknown(sbom_layer_attribution_absent)`).

The executor's attempt-log surfaced this obliquely under "Deviations": *"In the RED phase no adapter runs, so fixture contents do not affect behavior — all three xfail tests compose to `Unknown(no_adapter_resolved)` regardless. Shipped the one file AC-7 names (lodash + express artifacts). S3-02, which owns the adapter discrimination logic, will add scenario-specific fixtures."* That framing punted the discrimination-fixture design to S3-02 — but S3-02's validation surfaced the same defect as Blocker F ("Move `lodash` under `node_modules/express/node_modules/`; repoint the S3-01 direct test at `express`").

**Fix (applied 2026-08-14):** added a new AC pinning the three depth invariants each scenario requires, explicitly documenting the shipped gap ("Known gap at 2026-08-14 …") and naming the un-xfail-precondition role of the AC. Added a Notes-for-follow-up bullet cross-referencing S3-02 Blocker F. NO fixture edit was made (the fix crosses story boundaries: it either belongs to S3-02's un-xfail PR or to an assigned S3-01 fixture-owner). This preserves the validator's "no unilateral cross-story edits" discipline.

### F6 (Design-Patterns) — `_GREEN_WHEN` module constant is an intentional DRY seam [harden, notes-only]

The landed test defines `_GREEN_WHEN = "goes green when Phase 7 S3-02 lands NpmVulnProvenanceAdapter"` and uses it as the `reason=` for all three `xfail(strict=True)` markers. This is the DRY seam that makes the mechanical S3-02+S3-03 handoff a single grep. It is not surfaced in the story's Notes-for-implementer as an intentional pattern, so a future contract-test-first story (S4-02, S4-03) might invent its own reason-string convention.

**Fix (applied 2026-08-14):** added a Notes-for-implementer paragraph naming the `_GREEN_WHEN` pattern and marking it as a rule-of-three candidate for lift-into-a-shared-helper once sibling contract tests land.

### F7 (Test-Quality) — Autouse fixture scope was not pinned [harden, elevated to AC]

The story's AC-6 named `provenance_registry_reset` but never pinned function-scope. Default `pytest.fixture` scope IS function, so the landed conftest is correct — but a future refactor toward `scope="module"` or `scope="session"` would silently allow adapter registrations to leak between tests, invalidating the strict-xfail contract (a leftover registered adapter from another test's `load_plugins(...)` would satisfy the positive tests for the wrong reason).

**Fix (applied 2026-08-14):** added an explicit AC pinning per-function scope + the snapshot-clear-restore semantics, and named the load-bearing role (leak = wrong-reason strict-xfail pass = silent contract violation).

### F8 (Design-Patterns) — Anti-instructions to preserve Rule 2 simplicity [harden, notes-only]

Three preemptive-abstraction traps are latent in this story's shape and would tempt a future re-writer:

1. Parametrizing the three positive-path scenarios into one `pytest.mark.parametrize` block — trades intent (Rule 9 test names) for LOC economy.
2. Extracting `_assemble(package_id)` to a module-level utility before S4-02 or S4-03 demonstrate the second concrete consumer — premature per Rule 2.
3. Inventing a helper class `ProvenanceContractTest` as a shared base — Protocol IS the seam; the test file IS the deliverable; base-classing test files is the classic hidden-inheritance smell.

**Fix (applied 2026-08-14):** added three Notes-for-implementer bullets explicitly forbidding these. Pattern advice belongs in Notes, not ACs.

### F9 (Consistency, ADR-0009 vs High-level-impl.md) — 10-row allowlist contradiction [inherited from S3-02/S3-03]

Same contradiction the S3-02 and S3-03 validations flagged: ADR-0009 lists `pyproject.toml` as row #9; High-level-impl.md Step 5 lists `api.py` as row #9 (and `pyproject.toml` is absent). S3-01 does NOT trigger this — it adds zero allowlist rows — but the contradiction blocks S3-03's `api.py` byte-edit downstream.

**Fix (applied 2026-08-14):** added a Notes-for-follow-up bullet cross-referencing the S3-02 and S3-03 validation recommendations. No unilateral ADR amendment (belongs to a `phase-architect` amendment pass).

## Findings NOT made (and why)

- **No new AC for property-based testing of dispatch invariants.** S2-05 owns `test_dispatch_order_invariant.py` (Hypothesis, 50 permutations). S3-01's job is contract-pinning, not invariant-testing.
- **No new AC forbidding `_REGISTRY` inspection.** Already covered by AC-3 ("triggers plugin loading via the canonical loader API") + AC-4 ("invokes `assemble_provenance(...)` — the public seam") + the Context paragraph ("The test must read **only the public surface** — no `_REGISTRY` peeking, no direct adapter import"). Adding a fourth AC would be redundant.
- **No unilateral fixture edit.** F5 is a cross-story defect; the fix belongs to S3-02's un-xfail PR (or an assigned S3-01 fixture owner). The validator surfaces, does not act.
- **No unilateral cassette synthesis.** F4 is a Phase-3 obligation, not a Phase-7 synthesis target.
- **No unilateral ADR amendment.** F9 belongs to a `phase-architect` pass.
- **No re-typing of the Goal.** The Goal (red-first contract test for the plugin-load → registration → assembly path) is sound and the shipped test file honors it faithfully.
- **No removal of the shipped `_assemble(package_id)` helper or the `_GREEN_WHEN` constant.** Both are Rule-2-compliant DRY seams (4 call sites, 3 call sites) that shipped correctly; the validator elevates them to Notes-for-implementer as intentional patterns, not as ACs.

## Recommendations to the user (out-of-scope for this validation)

1. **Fix F5 — restructure `npm_lodash_app.json`.** Move `lodash` under `node_modules/express/node_modules/lodash/…`; keep `express` at `node_modules/express/…`; keep `PackageId("not-in-this-repo")` absent. This unblocks S3-02's un-xfail step for the transitive scenario. Assign to a Phase-7 owner (S3-02 implementer or S3-01 fixture owner). Cross-reference: [`_validation/S3-02-npm-vuln-provenance-adapter.md`](S3-02-npm-vuln-provenance-adapter.md) Blocker F.
2. **Fix F4 — synthesize `bench/vuln-remediation/`.** Phase-3 obligation. Blocks S3-02 AC-Full-Check + Phase-7 Step-3 done-criterion #3.
3. **Reconcile F9 — amend ADR-0009 or High-level-impl.md.** Blocks S3-03's `api.py` byte-edit. `phase-architect` pass.

## What "good" looks like for this story post-validation

The story now (with the shipped code unchanged) gives future readers and sibling-story implementers:

- 12 acceptance criteria, each individually verifiable, each reconciled against landed reality.
- Explicit callout of the three known ship-time deviations, each with a hardening rewrite that names the deviation, the landed pattern, and the rationale.
- A new AC pinning autouse-fixture scope (`function` + snapshot-clear-restore) as the load-bearing test-isolation invariant.
- A new AC pinning the SBOM-fixture depth invariants each scenario requires, with an explicit "Known gap at 2026-08-14" callout that names the un-xfail precondition.
- Three anti-instruction bullets in Notes-for-implementer forbidding preemptive-abstraction traps (`parametrize`, extract-`_assemble`, base-class-`ProvenanceContractTest`).
- A Notes-for-follow-up block enumerating three carry-forward gaps (fixture depth, cassette absence, ADR-0009 contradiction), each cross-referenced to the downstream validation that surfaced it.

## Mark of completion

The story file has been edited in place. This validation report has been written. The story header now carries a `**Validator status:** HARDENED (2026-08-14)` line linking back here. Shipped code is untouched; verdict is retrospective HARDENED.
