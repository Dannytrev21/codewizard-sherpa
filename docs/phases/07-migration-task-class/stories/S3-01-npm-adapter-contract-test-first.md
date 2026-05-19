# Story S3-01 — `test_provenance_assembly_via_plugins.py` contract test (red-first)

**Step:** Step 3 — `NpmVulnProvenanceAdapter` in Phase 3 plugin as additive new file (first byte-edit territory)
**Status:** Ready
**Effort:** S
**Depends on:** S2-04 (`assemble_provenance(...)` free function lands with `match`/`assert_never` composition), S1-05 (`SyftSbom` Pydantic reader exists so the test can construct a typed SBOM fixture)
**ADRs honored:** [ADR-0007](../ADRs/0007-provenance-adapter-registry-stores-classes.md) (the registry stores adapter **classes**, so the integration test asserts class registration + dispatch-time construction — never instance registration); [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) (this story does NOT touch any Phase 0–6.5 file — it only adds `tests/integration/test_provenance_assembly_via_plugins.py`; the fence cost is paid by S3-02 + S3-03); [ADR-0004](../ADRs/0004-vuln-provenance-primitive-home.md) (the primitive's `attribute(...) -> Provenance` surface is what the test pins); [ADR-0006](../ADRs/0006-adapter-dispatch-explicit-final-tuple.md) (the test exercises `_ADAPTER_DISPATCH_ORDER` walking — the result must be reachable through the canonical dispatch path, not by importing the adapter class directly)

## Context

`High-level-impl.md §"Step 3 — Risks specific to this step"` names the single highest-leverage mitigation for the entire step:

> Adapter contract incompatibility with the promoted-from-Phase-3 refuse-mode shape could force editing Phase 3 plugin code beyond the allowed two files — **mitigate by writing the contract test (`test_provenance_assembly_via_plugins.py`) first**, before the adapter body lands, so the contract is the green-light.

This is a red-phase TDD story: write the integration test that pins the contract surface BEFORE the adapter body in S3-02 lands. The test must FAIL until S3-02 ships, then go green when S3-02 lands the adapter and S3-03 wires the explicit import.

The contract this story pins is the cross-component invariant: full plugin-load → `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)` fires at import time → `assemble_provenance(cve_id, package_id, image_ref, sbom)` walks `_ADAPTER_DISPATCH_ORDER`, **the registry produces the NPM adapter class for `(Layer.APP, Ecosystem.NPM)`**, the `AdapterFactory` constructs it with the well-known DI kwargs `{sbom_reader, logger, image_manifest_cache}`, `.attribute(...)` runs, and the function returns a typed `Provenance` variant. The test must read **only the public surface** — no peeking into `_REGISTRY`, no direct adapter import, no `NpmVulnProvenanceAdapter.attribute(...)` call bypassing the assembly seam. If the test passes by importing the adapter class directly, the contract has not been pinned — it has been side-stepped.

The Phase 3 plugin shipped under Phase 3 a "refuse-mode shape" for several recipes (`NpmMajorBumpRefuseRecipe`, etc.) that emits `RecipeOutcome.NotApplicable(reason=MAJOR_BUMP_REFUSE)`. The S3-02 adapter is promoted from that shape — same dep-tree reading discipline, same lockfile readers — and the risk is that the existing Phase 3 internal helpers don't quite satisfy the read needs of `VulnProvenanceAdapter.attribute(...)`. Locking the test FIRST surfaces that mismatch as a fixture failure in this story, not as a "while I'm here let me refactor `plugins/vulnerability-remediation--node--npm/recipes/_lockfile_walk.py`" temptation in S3-02 — Phase 3 internal code is off-limits to byte-edits per Phase 7 ADR-0009.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design §1 VulnProvenancePrimitive"` — the `attribute(...) -> Provenance` callable surface (lines ~520–610).
  - `../phase-arch-design.md §"Component design §7a NpmVulnProvenanceAdapter"` (lines 742–750) — the canonical adapter spec the contract test pins.
  - `../phase-arch-design.md §"Scenario A — App-only CVE"` (sequence diagram, ~line 370) — the happy-path the test reproduces step-by-step.
  - `../phase-arch-design.md §"Scenario C — Both-app-and-base CVE"` (sequence diagram, ~line 460) — the test does NOT exercise this (S4-04 / S12-03 own it), but the test fixture's `image_ref` must be one that would NOT trigger a base-image adapter so the result is unambiguous app-side.
  - `../phase-arch-design.md §"Integration tests"` line 1268 — exact filename `tests/integration/test_provenance_assembly_via_plugins.py` and the exact contract (plugin-load → registration → `assemble_provenance` → typed result).
- **Phase 7 ADRs:**
  - [ADR-0004](../ADRs/0004-vuln-provenance-primitive-home.md) — primitive home + the seven-variant `Provenance` union.
  - [ADR-0006](../ADRs/0006-adapter-dispatch-explicit-final-tuple.md) — `_ADAPTER_DISPATCH_ORDER` is the only entry path; the test must not bypass.
  - [ADR-0007](../ADRs/0007-provenance-adapter-registry-stores-classes.md) — registry stores **classes**; `AdapterFactory.__call__(...)` does construction with DI kwargs at dispatch time.
  - [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — this story adds a new test file (off the allowlist surface — adding test files is unconstrained); S3-02 / S3-03 consume the allowlist rows.
- **High-level impl:** `../High-level-impl.md §"Step 3 — Features delivered"` bullet 4 (the `tccm.yaml` decision is deferred to S3-03 + S8-02 — this story does NOT need TCCM to be wired for the integration test to be meaningful).
- **Phase 3 precedent for promoted-from-refuse shape:**
  - `plugins/vulnerability-remediation--node--npm/recipes/` (existing) — read-only reference for how Phase 3 walks `package-lock.json`. The S3-02 adapter must NOT depend on private Phase 3 helpers.
  - `docs/phases/03-vuln-deterministic-recipe/stories/S7-02-npm-recipes-and-adapters.md` — context for the recipes that already exist in the plugin (do not edit).
- **Existing primitive surface (assumed shipped by S1-S2):**
  - `src/codegenie/primitives/vuln_provenance/__init__.py` — public exports (`assemble_provenance`, `AppDirect`, `AppTransitive`, `Unknown`, `Layer`, `Ecosystem`, `register_provenance_adapter`).
  - `src/codegenie/primitives/vuln_provenance/assembly.py` — `assemble_provenance(...)` free function.
  - `src/codegenie/primitives/vuln_provenance/registry.py` — `_REGISTRY` + decorator.
  - `src/codegenie/primitives/vuln_provenance/protocols.py` — `VulnProvenanceAdapter` Protocol + `AdapterFactory` Protocol.
  - `src/codegenie/primitives/vuln_provenance/syft_reader.py` — `SyftSbom` Pydantic model used in the fixture.

## Goal

Land `tests/integration/test_provenance_assembly_via_plugins.py` as a failing red test that pins the cross-component contract `Plugin import → `@register_provenance_adapter` side-effect → `assemble_provenance(...)` dispatch → typed `Provenance` return` for the npm app-layer adapter. The test goes red on this branch (no adapter implementation yet), goes green when S3-02 + S3-03 land. The test reads ONLY the public surface — no `_REGISTRY` peeking, no direct adapter import, no Phase 3 plugin internal access.

## Acceptance criteria

- [ ] `tests/integration/test_provenance_assembly_via_plugins.py` exists with `@pytest.mark.integration` (or whichever marker the existing integration suite uses — match conventions).
- [ ] The test has at least three scenarios, named for clarity:
  - `test_npm_adapter_returns_app_direct_for_root_dependency` — `package.json` declares `lodash@4.17.20` directly; `package-lock.json` resolves it at depth 1; `assemble_provenance(cve_id=CveId("CVE-2021-23337"), package_id=PackageId("lodash"), image_ref=..., sbom=...)` returns `AppDirect(...)` with `package_id == PackageId("lodash")`.
  - `test_npm_adapter_returns_app_transitive_for_deep_dependency` — `package.json` declares `express`; `lodash` appears at depth ≥ 2 via the resolved tree; assembly returns `AppTransitive(...)` whose `chain` field has `len(chain) >= 2` and the head is `express`.
  - `test_npm_adapter_returns_unknown_when_package_absent` — `package.json` + `package-lock.json` do not contain the queried package; assembly returns `Unknown(reason="sbom_layer_attribution_absent")` (NOT `no_adapter_resolved` — the adapter ran and observed absence; that's the typed reason).
- [ ] The test triggers plugin loading via the canonical loader API (e.g., `from codegenie.plugins.loader import load_plugins; load_plugins(...)` — match the existing Phase 3 integration test pattern). It does NOT do `from plugins.vulnerability_remediation__node__npm.adapters import npm_provenance` directly — that would side-step the registration discipline ADR-0007 protects.
- [ ] After loader runs, the test invokes `assemble_provenance(...)` from `codegenie.primitives.vuln_provenance` — the public seam — to produce the typed result.
- [ ] The result is asserted via `match` exhaustiveness on `Provenance`, NOT `isinstance`:
  ```python
  match result:
      case AppDirect() as app: ...
      case AppTransitive() as app: ...
      case Unknown(reason="sbom_layer_attribution_absent"): ...
      case _: pytest.fail(f"unexpected variant: {result!r}")
  ```
- [ ] A `conftest.py` fixture under `tests/integration/` (or extension of existing) provides the `provenance_registry_reset` isolation per S2-05 — the test must not bleed adapter registrations into other integration tests.
- [ ] A minimal `SyftSbom` fixture is constructed via the typed reader (`SyftSbom(artifacts=[SyftArtifact(name="lodash", version="4.17.20", locations=[SyftLocation(layerID="sha256:...")])])`) — pinned in `tests/integration/_fixtures/syft_sboms/npm_lodash_app.json` and loaded via `SyftSbom.model_validate_json(...)`. The fixture's `layerID` is a non-base-image layer so the base-image adapters return `Unknown` and the assembly composes to a clean app-only result.
- [ ] An `ImageRef` fixture is constructed via the smart constructor from S1-01 (`ImageRef.parse("alpine:3.18@sha256:...").unwrap()`) — the test uses an Alpine ref **only because** the loader needs a non-empty ref; the test does NOT exercise the alpine adapter (it's not yet registered in this story's run).
- [ ] **At commit time of this story's PR, the test is RED.** The commit message includes the literal substring "RED" and the test failure is the absence of any adapter for `(Layer.APP, Ecosystem.NPM)` in `_REGISTRY` — surfacing as `Unknown(reason="no_adapter_resolved")` from `assemble_provenance(...)`. This is the canonical TDD red phase the story locks in.
- [ ] The test asserts `Unknown(reason="no_adapter_resolved")` in a `test_red_state_when_no_npm_adapter_registered` scenario that is marked `xfail(strict=True, reason="goes green when S3-02 lands NpmVulnProvenanceAdapter")` — so CI does not block on the red, but a passing red would fail strict. **Once S3-02 lands**, the implementer of S3-02 removes the `xfail` marker (this is the green-phase handoff).
- [ ] `ruff format`, `ruff check`, `mypy --strict tests/integration/test_provenance_assembly_via_plugins.py` clean.
- [ ] `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` — N/A for this story (no Phase 0–6.5 file edits); `make check` green except for the documented `xfail`.
- [ ] **Phase 3–6.5 regression suite green** (`make check` excluding the `xfail` line counts as green per the pre-merge gate; the cassette replay is byte-equal).

## Implementation outline

1. Create `tests/integration/test_provenance_assembly_via_plugins.py`. Import surface:
   ```python
   import pytest
   from codegenie.primitives.vuln_provenance import (
       assemble_provenance, AppDirect, AppTransitive, Unknown, Layer, Ecosystem,
   )
   from codegenie.primitives.vuln_provenance.syft_reader import SyftSbom
   from codegenie.types.identifiers import CveId, PackageId, ImageRef
   from codegenie.plugins.loader import load_plugins  # match existing API
   ```
2. Add a `conftest.py` extension (or new file) under `tests/integration/` that calls the S2-05 `provenance_registry_reset` fixture as `autouse=True` for this module's tests, ensuring registry isolation.
3. Construct the SBOM fixture file `tests/integration/_fixtures/syft_sboms/npm_lodash_app.json` (raw JSON; loaded via `SyftSbom.model_validate_json(Path(...).read_bytes())`).
4. Write three positive-path tests (`AppDirect`, `AppTransitive`, `Unknown` for absence) that depend on S3-02 landing. Mark them `xfail(strict=True)` at story-commit time with the documented `reason`.
5. Write the red-state test (`test_red_state_when_no_npm_adapter_registered`) — calls `assemble_provenance(...)` against the fixture and asserts `Unknown(reason="no_adapter_resolved")` (the assembly's "no adapter resolved" reason, per S2-04's composition table). This is the canary that detects the adapter has indeed not yet shipped.
6. Confirm the failure shape matches the expected red:
   ```bash
   .venv/bin/pytest tests/integration/test_provenance_assembly_via_plugins.py -v --no-cov
   # Expect: 1 passed (the red-state test), 3 xfailed (strict)
   ```
7. Commit with message containing "RED" (per CLAUDE.md Rule 12 fail-loud — the commit message names the test phase).

## Test-driven development plan

**Red.** The four-test file lands. The three `xfail(strict=True)` tests fail with `Unknown(reason="no_adapter_resolved")` (because no adapter is registered for `(Layer.APP, Ecosystem.NPM)`), which is the strict-xfail-pass signal. The one `test_red_state_when_no_npm_adapter_registered` test passes (it asserts the very same `no_adapter_resolved` outcome). CI is green; the contract is pinned.

**Green.** S3-02 (next story) lands `NpmVulnProvenanceAdapter`. S3-03 lands the explicit import line. As part of S3-03's PR, the three `xfail` markers are removed; the three positive-path tests now pass; the red-state test now fails (the adapter IS registered) — so S3-03 also deletes the red-state test (or inverts it to a "registry contains expected key" assertion). The hand-off is mechanical and traceable.

**Refactor.** None in this story — the test file IS the deliverable. Future stories may extract the SBOM fixture loader into a shared `tests/integration/_fixtures/conftest.py` helper if S4-02 / S4-03 / S12-02 reuse it.

## Files to touch

- `tests/integration/test_provenance_assembly_via_plugins.py` (new).
- `tests/integration/_fixtures/syft_sboms/npm_lodash_app.json` (new — pinned SBOM fixture).
- `tests/integration/conftest.py` (extend if it exists; otherwise create) — autouse registry-reset fixture inclusion.

## Out of scope

- Implementing `NpmVulnProvenanceAdapter` — S3-02 owns that body.
- Editing `plugins/vulnerability-remediation--node--npm/api.py` (the import wiring) — S3-03 owns that byte-edit allowlist row.
- Adding to `plugins/vulnerability-remediation--node--npm/tccm.yaml` — S3-03 owns; pinned against S8-02 schema.
- Any base-image adapter coverage — S4-02 + S4-03 own the `BaseImage` side and the `Both` composition is S12-03's e2e responsibility.
- Property tests over `assemble_provenance` (`test_idempotence`, `test_dispatch_order_invariant`) — S2-05 owns these at the unit/property level.

## Notes for the implementer

- The headline mitigation pattern in this story (write the integration test first, in a red state, with `xfail(strict=True)` so CI is green but the contract is locked) is the **risk #1 mitigation** named in `High-level-impl.md §"Step 3 — Risks specific to this step"`. If you find yourself wanting to skip ahead to S3-02, stop — the value of this story is precisely the pressure it puts on S3-02 to satisfy a contract that was written before any line of adapter code.
- Do NOT peek into `_REGISTRY` directly. If `assemble_provenance(...)` returns the wrong variant, the public-surface output is what you fix — not your test fixture's access to private state.
- Do NOT call `NpmVulnProvenanceAdapter.attribute(...)` directly. The whole point of the contract test is that the adapter is reached **only** through `assemble_provenance` walking `_ADAPTER_DISPATCH_ORDER`. A test that imports the adapter directly is a unit test, not a contract test — and the unit test is S3-02's job.
- The `xfail(strict=True)` discipline is load-bearing: it means a regression that accidentally makes the test pass (e.g., a leftover registered adapter from another test) BREAKS CI. Strict-xfail catches "the contract is silently satisfied for the wrong reason."
- If the existing `tests/integration/conftest.py` doesn't yet have the `provenance_registry_reset` fixture, you may need to coordinate: S2-05 promises to land it. If S2-05 hasn't shipped, mark this story BLOCKED-PARTIAL and surface in `_attempts/S3-01-npm-adapter-contract-test-first.md`. Do NOT write your own ad-hoc registry-reset — the canonical fixture lives with the primitive.
