# Story S8-04 — Plugin-resolution integration test + `tccm.yaml` `derived_queries:` content

**Step:** Step 8 — `DistrolessMigrationPlugin` manifest + TCCM `derived_queries:` band + plugin loader wiring
**Status:** Ready
**Effort:** M
**Depends on:** S8-03 (the loader + resolver + `api.py` shape must exist; this story exercises the full path end-to-end)
**ADRs honored:** Phase 7 ADR-0016 (TCCM `derived_queries:` band — primary; this story is the end-to-end proof), Phase 7 ADR-0001 (no multi-plugin coordinator; `Both` resolution yields `PendingCoordination`, NOT a coordinator pick), Phase 7 ADR-0009 (no new byte-edits to locked files; the YAML is a new file under the plugin tree), production ADR-0031 (resolver behavior — `(task, language, build_system)` triple drives plugin selection), production ADR-0029 (TCCM bands; `must_read` is evidence, `derived_queries` is computation)

## Context

S8-01 added the manifest, S8-02 added the schema for `derived_queries:`, S8-03 added the loader explicit-import line + the `compute:` resolver + `api.py`. This story closes Step 8 with the **content** — the actual `tccm.yaml` body for the distroless plugin — and the **integration test** that proves the resolver picks the right plugin for the right CVE provenance.

The TCCM YAML for `distroless-migration--node--npm/tccm.yaml` carries:

```yaml
must_read:
  - dockerfile           # evidence: the Dockerfile slice from BaseImageProbe
  - base_image           # evidence: BaseImageProbe's structured output
  - sbom                 # evidence: SyftSbom (Layer F, gathered upstream)

should_read:
  - shell_invocation_trace   # nice-to-have: ShellInvocationTraceProbe's output (S7-02)
  - node_build_system        # nice-to-have: Phase 1 NodeBuildSystem probe output

derived_queries:
  - name: provenance
    compute: vuln.provenance
    args:
      cve_id: $workflow.cve
      package_id: $workflow.package
      image_ref: $repo.base_image
```

**Important YAML-vs-schema-shape gap:** the existing `TCCM` Pydantic model in `src/codegenie/plugins/tccm.py` uses `must_read: list[ContextQuery]`, where each `ContextQuery` is the five-primitive shape (`scip.refs`, `import_graph.reverse_lookup`, etc.). The README + ADR-0016 use prose shorthand `must_read: [dockerfile, base_image, sbom]` — bare strings. These do not parse against `ContextQuery`'s schema.

The resolution: the migration plugin's TCCM does **not** load through the Phase 3 `TCCM` Pydantic model directly. Either (a) a Phase 7 `MigrationTCCM` model exists alongside Phase 3's (Phase 3 ADR-0004 explicitly allows multiple TCCM shapes per plugin family), OR (b) the `must_read` / `should_read` entries are wrapped in a thin `ContextQuery` shape that names the probe output as an evidence reference. The implementer picks ONE convention and pins it in the AC tests. The simplest path consistent with ADR-0016's prose: introduce a thin `EvidenceRef(name: str)` model and switch the migration plugin's TCCM type to `MigrationTccm(must_read: list[EvidenceRef], should_read: list[EvidenceRef] = [], derived_queries: list[DerivedQuery] = [])`. Surface the choice in the implementer notes; do not silently average.

**The resolution integration test is the gate that proves task-class routing works** (the prompt names this explicitly). Three cases must pass:

1. **Base-image-only CVE** (CVE attributed to `base_image` layer per `assemble_provenance`) → resolver picks `distroless-migration--node--npm`.
2. **App-only CVE** (CVE attributed to `app` layer) → resolver picks `vulnerability-remediation--node--npm`.
3. **`Both` workflow** (CVE attributed to BOTH layers — provenance returns `Both(app_record, base_record)`) → resolver returns `PendingCoordination` (typed; risk #4 mitigation per Phase 7 final-design.md). NOT a coordinator pick; NOT a precedence-based tiebreaker.

The `Both` case is the load-bearing test — Phase 7 ADR-0001 says "no multi-plugin coordinator in Phase 7"; the resolver must surface `Both` as a *typed deferred decision*, not silently pick one plugin.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §Process view`](../phase-arch-design.md) — resolver sequence; `Both` → `PendingCoordination`.
  - [`../phase-arch-design.md §Component design §11 (DistrolessMigrationPlugin) / §13 (TCCM band) / §14 (Resolver)`](../phase-arch-design.md) — resolver shape.
  - [`../phase-arch-design.md §Edge cases / Failure modes`](../phase-arch-design.md) — `Both` provenance + resolver behavior.
- **Phase ADRs:**
  - [`../ADRs/0016-tccm-derived-queries-band.md`](../ADRs/0016-tccm-derived-queries-band.md) — **primary**; §Consequences row 4 names this plugin's TCCM `derived_queries:` content verbatim.
  - [`../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md`](../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md) — **primary** for the `Both` case; coordinator deferred to Phase 8 (per production ADR-0042).
  - [`../ADRs/0009-phase-7-byte-edit-allowlist-fence.md`](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — no locked-file edits in this story.
- **Production ADRs:**
  - [`../../../production/adrs/0031-plugin-architecture.md`](../../../production/adrs/0031-plugin-architecture.md) — resolver `(task, language, build_system)` triple.
  - [`../../../production/adrs/0029-task-class-context-manifests.md`](../../../production/adrs/0029-task-class-context-manifests.md) — TCCM bands.
- **High-level impl:**
  - [`../High-level-impl.md §Step 8`](../High-level-impl.md) — Done criteria bullets 1–3.
  - [`../High-level-impl.md §Risks specific to this phase #4`](../High-level-impl.md) — "Plugin resolver ambiguity on `Both` workflows ... resolver must surface `PendingCoordination`."
- **Source:**
  - [`src/codegenie/plugins/resolver.py`](../../../../src/codegenie/plugins/resolver.py) (or `resolution.py` — check the existing module structure). Read the existing resolver end-to-end before writing the test.
  - [`src/codegenie/primitives/vuln_provenance/assembly.py`](../../../../src/codegenie/primitives/vuln_provenance/assembly.py) — `assemble_provenance(...)` (from S2-04). The test calls this to compute the typed `Provenance` for each fixture.

## Goal

Land three things:

1. **`plugins/distroless-migration--node--npm/tccm.yaml`** — the YAML body with `must_read`, `should_read`, and one `derived_queries:` entry as named above.
2. **`tests/integration/test_plugin_resolution_phase7.py`** — three test cases (base-only, app-only, `Both`) proving the resolver's task-class routing.
3. **`tests/integration/test_tccm_distroless_derived_queries_loads.py`** — the TCCM YAML loads cleanly; the `compute:` resolves to the imported `vuln.provenance` callable via S8-03's resolver; template-arg strings carry forward verbatim (not substituted at load time).

The CVE-to-image catalog YAML (Step 9) and the actual Dockerfile transform (Step 10) are out of scope.

## Acceptance criteria

### A. `tccm.yaml` content

- [ ] `plugins/distroless-migration--node--npm/tccm.yaml` exists.
- [ ] `must_read:` contains exactly `[dockerfile, base_image, sbom]` (or the equivalent `EvidenceRef`-wrapped shape — see Implementer Notes; pin the chosen convention with a comment at the top of the YAML).
- [ ] `should_read:` contains exactly `[shell_invocation_trace, node_build_system]`.
- [ ] `derived_queries:` contains exactly one entry: `{name: provenance, compute: vuln.provenance, args: {cve_id: $workflow.cve, package_id: $workflow.package, image_ref: $repo.base_image}}`.
- [ ] No other top-level keys (`provides:`, `requires:` are optional and default to empty per S8-02's schema; do not ship them unless the migration plugin actually declares them).
- [ ] The YAML is < 30 lines (small, scannable; the migration plugin's TCCM is intentionally compact).

### B. TCCM YAML loads via the schema

- [ ] `tests/integration/test_tccm_distroless_derived_queries_loads.py` exists.
- [ ] The test loads `plugins/distroless-migration--node--npm/tccm.yaml` via the project's TCCM YAML loader (whichever entry point Phase 3's `tccm.py` + safe-yaml chokepoint exposes; if the project uses `Tccm.from_yaml(...)`, use that — confirm the existing convention).
- [ ] `tccm.derived_queries` is a list of length 1.
- [ ] `tccm.derived_queries[0].name == "provenance"`.
- [ ] `tccm.derived_queries[0].compute == "vuln.provenance"`.
- [ ] `tccm.derived_queries[0].args == {"cve_id": "$workflow.cve", "package_id": "$workflow.package", "image_ref": "$repo.base_image"}`.
- [ ] `resolve_derived_queries(tccm.derived_queries, vocabulary=_PHASE7_VOCABULARY)` returns `Ok([resolved])` with `resolved.callable is codegenie.primitives.vuln_provenance.provenance`.
- [ ] A test mutates the YAML to use `compute: vuln.provence` (typo) and asserts the resolver returns `Err(UnknownDerivedCompute)`. (This may be a separate `tmp_path`-scoped test that copies the YAML and edits it.)

### C. Resolution integration — three cases

- [ ] `tests/integration/test_plugin_resolution_phase7.py` exists.
- [ ] **Case 1 — base-image-only CVE.** Given a workflow context where `assemble_provenance(cve_id, package_id, image_ref, sbom)` returns `BaseImage(image_digest=..., layer_digest=..., distro_pkg=..., stage=...)` (a single-variant `Provenance` rooted in `BaseImage`), the resolver picks `distroless-migration--node--npm` from the two plugins registered for `(task=*, language=node, build=npm)`.
  - The fixture provides: a Dockerfile (e.g., `FROM alpine:3.18 ... RUN apk add openssl`), a `package.json` with no vulnerable npm deps, an SBOM whose vulnerable artifact's `layerID` matches the base image. `assemble_provenance` returns `BaseImage(...)`.
  - The resolver call returns a `ResolvedPlugin` (or whatever the existing resolver's success type is named) with `plugin_id == PluginId("distroless-migration--node--npm")`.
- [ ] **Case 2 — app-only CVE.** Given a workflow context where `assemble_provenance(...)` returns `AppDirect(...)` or `AppTransitive(...)`, the resolver picks `vulnerability-remediation--node--npm`.
  - The fixture: a Dockerfile with a healthy base, a `package.json` with one vulnerable direct dep, an SBOM whose vulnerable artifact's `layerID` matches the app layer.
- [ ] **Case 3 — `Both` workflow.** Given a workflow context where `assemble_provenance(...)` returns `Both(app_record, base_record)`, the resolver returns a typed `PendingCoordination` value (NOT a `ResolvedPlugin`, NOT a precedence-based pick). The typed `PendingCoordination` carries the workflow id + the `Both` value for downstream (Step 11's coordination writer).
  - The fixture: a Dockerfile + `package.json` where CVE is present in BOTH the base image layer and an app dep.
  - The test asserts the return type is `PendingCoordination` (use `isinstance` or a `match` with `assert_never`).
  - The test asserts neither `distroless-migration--node--npm` nor `vulnerability-remediation--node--npm` is silently picked.

### D. Resolver wiring — no edits to existing resolver behavior

- [ ] The resolver's existing behavior for single-variant `Provenance` (App/BaseImage/Unknown) routes to the matching plugin via the `(task, language, build_system)` triple. This story does NOT add new branching to the resolver; it provides the second registered plugin for `(distroless-migration, node, npm)` and proves it gets picked.
- [ ] If the resolver does not already understand `Both` → `PendingCoordination` as of Phase 6.5, this story adds that branch. The branch is a typed `match` arm in the resolver, not a new module. Surface this in the implementer notes — if it's new code, name it as a deliberate addition; if it's already there, exercise it.
- [ ] No `if plugin_id == "distroless-migration..."` style special-casing — the resolver routes via data (scope triple + precedence + provenance variant), not branching on plugin id.

### E. Backward-compat + lint

- [ ] All existing plugin-resolution tests continue to pass; this story is a strict superset of resolver behavior.
- [ ] `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py` green; no locked-file edits in this story.
- [ ] `mypy --strict tests/integration/test_plugin_resolution_phase7.py tests/integration/test_tccm_distroless_derived_queries_loads.py plugins/distroless-migration--node--npm/tccm.yaml` (or however the project applies mypy to test + plugin trees) — clean.
- [ ] `make check` green.
- [ ] **Phase 3–6.5 regression suite green; `bench/vuln-remediation/` cassette replay byte-equal (ε ≤ $0.01).**

## Implementation outline

1. **Read `src/codegenie/plugins/resolver.py` (or `resolution.py`) end-to-end.** Confirm: (a) the resolver's input shape — does it take a `Provenance` value, or does it derive scope from a workflow context that then queries provenance? (b) the resolver's output shape — `ResolvedPlugin | PendingCoordination`, an `Optional[ResolvedPlugin]`, a `Result[...]`? Pin against the existing convention.
2. **Decide TCCM-shape convention.** If the migration plugin's TCCM should load through the existing `TCCM` Pydantic model in `src/codegenie/plugins/tccm.py`, the `must_read` entries need to be `ContextQuery`-shaped (which they aren't — `dockerfile` is not one of the five `_KNOWN_PRIMITIVES`). Two paths:
   - **Path A:** introduce a sibling `MigrationTccm` Pydantic model (or generalize the existing model) — this is an additive schema change, **not** covered by allowlist row #6 (row #6 was consumed by S8-02). Surface the choice as an explicit ADR amendment if needed.
   - **Path B:** extend the existing `TCCM` model with `EvidenceRef(name: str)` and switch `must_read` / `should_read` from `list[ContextQuery]` to `list[ContextQuery | EvidenceRef]`. This is a richer schema change and again may need an ADR.
   - **Path C (simplest):** ship the migration plugin's TCCM as a parallel YAML format read via a new loader in `plugins/distroless-migration--node--npm/tccm_loader.py`, mirroring Phase 3's pattern but scoped to the migration plugin. This is the most explicit "additive new file under the plugin tree" path.
   - **Recommendation:** Path C, scoped to the plugin tree. Surface the decision in the YAML's top comment and the test fixture's docstring. Do not silently average (Rule 7).
3. **Write `plugins/distroless-migration--node--npm/tccm.yaml`** with the body named in AC-A. Include a top-of-file comment naming Phase 7 ADR-0016 and the chosen TCCM-shape convention.
4. **Write `tests/integration/test_tccm_distroless_derived_queries_loads.py`** — see TDD plan.
5. **Write the three resolution-case test fixtures** under `tests/fixtures/portfolio/` (S12-01 will eventually own the broader portfolio; this story bootstraps three of them so resolution can be tested before S12-01 lands):
   - `node-vulnerable-base-only/` — Dockerfile + package.json + SBOM where CVE lives in base layer only.
   - `node-vulnerable-app-only/` — CVE lives in app layer only.
   - `node-vulnerable-alpine/` — CVE in both layers (`Both`).
   Each fixture tree carries pinned `image-digest:` for deterministic resolution.
6. **Write `tests/integration/test_plugin_resolution_phase7.py`** — three test cases per AC-C.
7. **If the resolver lacks `Both` → `PendingCoordination` branching, add it.** Likely a one-`match`-arm change in the existing resolver. Surface in the Notes.
8. **Run `make check`** — green.

## TDD plan (red → green → refactor)

### Red — write `tests/integration/test_plugin_resolution_phase7.py` first

```python
"""S8-04 — resolver routes (task, language, build) + Provenance variant to plugin."""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.plugins.resolver import (
    PendingCoordination,
    ResolvedPlugin,
    resolve_plugin,  # exact name TBD — match existing
)
from codegenie.primitives.vuln_provenance import (
    AppDirect,
    BaseImage,
    Both,
    assemble_provenance,
)
from codegenie.types.identifiers import (
    CveId,
    ImageRef,
    PackageId,
    PluginId,
)

FIXTURES = Path("tests/fixtures/portfolio")


class TestBaseImageOnly:
    def test_routes_to_distroless_migration(self) -> None:
        fixture = FIXTURES / "node-vulnerable-base-only"
        # Build the workflow context per the existing convention (this
        # mirrors what an orchestrator does upstream).
        ctx = _make_workflow_ctx(fixture)
        prov = assemble_provenance(
            ctx.cve_id, ctx.package_id, ctx.image_ref, ctx.sbom
        )
        assert isinstance(prov, BaseImage)
        resolved = resolve_plugin(
            task="distroless-migration", language="node", build="npm",
            provenance=prov,
        )
        assert isinstance(resolved, ResolvedPlugin)
        assert resolved.plugin_id == PluginId("distroless-migration--node--npm")


class TestAppOnly:
    def test_routes_to_vulnerability_remediation(self) -> None:
        fixture = FIXTURES / "node-vulnerable-app-only"
        ctx = _make_workflow_ctx(fixture)
        prov = assemble_provenance(
            ctx.cve_id, ctx.package_id, ctx.image_ref, ctx.sbom
        )
        assert isinstance(prov, (AppDirect,))  # or AppTransitive
        resolved = resolve_plugin(
            task="vulnerability-remediation", language="node", build="npm",
            provenance=prov,
        )
        assert isinstance(resolved, ResolvedPlugin)
        assert resolved.plugin_id == PluginId("vulnerability-remediation--node--npm")


class TestBothEmitsPendingCoordination:
    """The load-bearing case — Phase 7 ADR-0001 §"no multi-plugin coordinator"."""

    def test_both_provenance_yields_pending_coordination(self) -> None:
        fixture = FIXTURES / "node-vulnerable-alpine"
        ctx = _make_workflow_ctx(fixture)
        prov = assemble_provenance(
            ctx.cve_id, ctx.package_id, ctx.image_ref, ctx.sbom
        )
        assert isinstance(prov, Both)
        resolved = resolve_plugin(
            task="vulnerability-remediation", language="node", build="npm",
            provenance=prov,
        )
        # Pending coordination is a typed sentinel — NOT a silent plugin pick.
        assert isinstance(resolved, PendingCoordination)

    def test_both_does_not_silently_pick_distroless(self) -> None:
        fixture = FIXTURES / "node-vulnerable-alpine"
        ctx = _make_workflow_ctx(fixture)
        prov = assemble_provenance(
            ctx.cve_id, ctx.package_id, ctx.image_ref, ctx.sbom
        )
        resolved = resolve_plugin(
            task="distroless-migration", language="node", build="npm",
            provenance=prov,
        )
        assert not isinstance(resolved, ResolvedPlugin) or resolved.plugin_id != PluginId(
            "distroless-migration--node--npm"
        )
```

Run — fails because the fixtures, the YAML, and (if needed) the `PendingCoordination` branch don't exist. That's red.

### Green — minimum implementation

Land the three fixtures, the `tccm.yaml`, and (if missing) the resolver's `Both` branch. Re-run; all tests pass.

### Refactor

- Confirm the fixtures are minimal — Dockerfile + package.json + SBOM + image-digest pin; no extra build artifacts.
- Confirm `_make_workflow_ctx` (test helper) loads the fixture deterministically and matches the existing convention for workflow-context construction in Phase 3's tests.
- Confirm `PendingCoordination` is exported from `codegenie.plugins.resolver` (or wherever the resolver lives); if you had to add it, surface the addition as a typed sentinel (frozen Pydantic model with `workflow_id`, `both: Both` fields, mirroring S11-01's typed event shape).

## Files to touch

- `plugins/distroless-migration--node--npm/tccm.yaml` — new file (the TCCM body).
- `tests/integration/test_plugin_resolution_phase7.py` — new integration test (three cases).
- `tests/integration/test_tccm_distroless_derived_queries_loads.py` — new integration test (YAML loads + resolves).
- `tests/fixtures/portfolio/node-vulnerable-base-only/` — new fixture tree (Dockerfile + package.json + sbom.json + manifest pin).
- `tests/fixtures/portfolio/node-vulnerable-app-only/` — new fixture tree.
- `tests/fixtures/portfolio/node-vulnerable-alpine/` — new fixture tree (the `Both` case).
- `src/codegenie/plugins/resolver.py` (or wherever) — possibly one new `match` arm for `Both` → `PendingCoordination` IF the resolver doesn't already have it. **NOT** a byte-edit allowlist row — this is a new branch in a Phase-7-owned-or-already-modified file. If the resolver is a Phase 3 locked file, surface the conflict (Rule 7) and defer to an explicit ADR amendment.

## Out of scope

- The S12-01 full fixture portfolio (already-distroless, multi-stage, poisoned-sbom) — this story ships only the three needed for resolution.
- The actual Dockerfile transforms + gates — Step 10.
- The CVE-to-image catalog — Step 9.
- The `coordination-summary.yaml` writer + spanning-log event emission — Step 11 (S11-02).
- The `codegenie list-coordination-candidates` CLI — Step 11 (S11-03).
- Exit code 8 wiring at the orchestrator level — Step 11 (S11-04).
- Property tests covering invariants like "every `Both` workflow has exactly one coordination event" — Step 12 (S12-03).

## Notes for the implementer

- **TCCM-shape convention (load-bearing decision):** the existing `TCCM` Pydantic model in `src/codegenie/plugins/tccm.py` uses `list[ContextQuery]` for `must_read` — incompatible with the prose YAML in ADR-0016 and the High-level-impl Step 8 features bullet. You must pick a path (A/B/C in the Implementation outline) and pin it. **Recommended: Path C** — a parallel migration-plugin-local TCCM loader. This keeps the existing `TCCM` model byte-clean and avoids consuming another allowlist row mid-story. Surface the choice in a comment at the top of `tccm.yaml` and in this story's Notes upon completion.
- **`PendingCoordination` type — where it lives:** mirrors S11-01's `RequiresMultiPluginCoordination` event but is the *typed sentinel* the resolver returns (the event is written downstream when the orchestrator translates `PendingCoordination` to spanning-log evidence). Frozen Pydantic; `extra="forbid"`; fields `workflow_id: WorkflowId`, `both: Both`. If S11-01 hasn't landed yet, this story may need to ship a thin version of the sentinel and let S11-01/S11-02 extend it — surface in Notes.
- **`assemble_provenance(...)` arity:** Phase 7 S2-04 ships the function as `assemble_provenance(cve_id, package_id, image_ref, sbom, *, registry=None, adapter_factory=None) -> Provenance`. The test fixtures must produce these four arguments; the `_make_workflow_ctx(fixture)` helper loads them from disk and pins the workflow context shape.
- **Resolver `Both` arm — is it new code?** Phase 6.5's resolver likely returns `ResolvedPlugin | None` for the existing single-variant flow. Adding a third return type (`PendingCoordination`) is a typed-surface widening. Check the existing return annotation; if it's `ResolvedPlugin | None`, this story widens to `ResolvedPlugin | PendingCoordination | None`. Use `match` + `assert_never` at the callsites to catch unhandled returns. If the widening touches a Phase 0–6.5 locked file, surface as an ADR amendment — the resolver may not yet exist as a Phase 0–6.5 surface (S2/S3 may have only stubbed it), in which case the addition is "additive new behavior in Phase 7-owned code" and no fence row is needed.
- **Fixture realism:** the three fixtures should be small but realistic. The `node-vulnerable-alpine` fixture is the headline `Both` case used by S12-01's portfolio — coordinate the file layout so S12-01 can extend it. Use a synthetic CVE id (e.g., `CVE-2024-99999`) and a stable Chainguard digest pinned in `image-digest:`. The SBOM should be a minimal Syft JSON with at most 5 artifacts.
- **Resolver picks via `(task, language, build)` triple, NOT plugin name:** the test must not assert "plugin X is picked because of its name" — it must assert "plugin X is picked because its `scope` matches." A regression test that hard-codes the name would pass even if the resolver started picking by string-comparison. Surface this in the test docstring (Rule 9 — tests verify intent).
- **Why is `Both` resolution a precedence-tiebreaker risk?** Both plugins overlap on `(language=node, build=npm)`. The Phase 3 plugin's scope is `task=vulnerability-remediation`; the migration plugin's is `task=distroless-migration`. They are NOT direct ties on the triple — the `task` axis disambiguates. The risk is at the *workflow* level: the orchestrator receives a CVE, calls `assemble_provenance(...)`, gets `Both`, and now has to decide which plugin to invoke. The resolver's `PendingCoordination` return is the answer: defer to S11's coordination event, do not pick.
- **`PLUGINS.lock` precondition:** S5-04 lands the lock entry. Until it's green the loader rejects this plugin. If the integration test exercises `load_plugins(...)` end-to-end, it must run after S5-04. If it only exercises the resolver in isolation (with a hand-built `_REGISTRY`), it can run independently. Pick whichever is feasible at the time of execution.
- **Backward compat with Phase 3:** the resolver must still pick `vulnerability-remediation--node--npm` for the app-only case. If introducing the migration plugin changes Phase 3's routing for any existing test, that's a regression — surface immediately.
- **Cross-reference for S12-03:** the `Both`-emits-coordination property test (S12-03) builds on this story's `Both` fixture. Keep the fixture layout stable across stories.
