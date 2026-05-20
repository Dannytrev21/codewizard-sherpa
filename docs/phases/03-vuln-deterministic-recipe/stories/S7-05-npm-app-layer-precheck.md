# Story S7-05 — npm plugin app-layer precheck (refuse-mode for non-app-layer CVEs)

**Step:** Step 7 — First production plugin, universal HITL fallback plugin, synthetic third plugin
**Status:** HARDENED (validated 2026-05-20 — see [`_validation/S7-05-npm-app-layer-precheck.md`](_validation/S7-05-npm-app-layer-precheck.md))
**Effort:** S–M (raised from S — the story was drafted against an imagined API surface; hardening pins it to the shipped `SubgraphState` / `outcomes.py` / `events.py` contracts and adds the additive model + event-taxonomy widenings the goal actually requires)
**Depends on:** S7-01 (plugin scaffold + `build_subgraph` seam — shipped as a `NotImplementedError` stub this story first implements), S6-03 (`SubgraphNode` Protocol + `SubgraphState` + `NodeTransition` tagged union), S5-01 (the shared `NotApplicableReason` `Literal` lives at the recipe-engine surface), S6-04 (orchestrator runs the plugin's `build_subgraph` output), S6-01 (`WorkflowInternalEvent` event module the new variant joins), S6-06 (Phase-5 contract snapshot — must be regenerated when the additive widenings land)
**ADRs honored:** [production ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md) (refuse-mode for non-app-layer CVEs — Phase 3's Phase-7-precursor commitment), [ADR-0003](../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md) (the matched plugin is not silently substituted when it cannot act — the workflow exits with an evidence-bearing outcome that the orchestrator routes to HITL), [ADR-0010](../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md) (new `NotApplicableReason` `Literal` member `"CVE_NOT_IN_APP_LAYER"` follows the existing taxonomy + `assert_never` exhaustiveness discipline)

## Validation notes (2026-05-20)

Hardened by `phase-story-validator`. Full audit: [`_validation/S7-05-npm-app-layer-precheck.md`](_validation/S7-05-npm-app-layer-precheck.md). The story's goal is sound and traces cleanly to ADR-0038; the ACs/TDD plan were rewritten against the **shipped** sibling contracts. Block-tier closures:

- **`NotApplicableReason` is a `typing.Literal`, not an enum** (`src/codegenie/transforms/outcomes.py:84`). The new member is the UPPER_SNAKE string `"CVE_NOT_IN_APP_LAYER"` (matching `ALL_RECIPES_NOT_APPLICABLE` et al.) — not the lowercase value the draft prescribed, and not enum attribute access.
- **The outcome class is `RemediationNotApplicable`** (`outcomes.py:284`), not `RemediationOutcome.NotApplicable`. It has only `kind` + `reason` and is `frozen, extra="forbid"` — the `evidence` field must be **added additively** (precedent: `RecipeNotApplicable.considered`, S5-01).
- **`SubgraphState` (S6-03) has `cve: CveId` + `bundle: Bundle | None`** and **no** `cve_record`, `npm_dep_graph`, or `snapshot` field. AC-4 / the data-access steps were rewritten to read only real fields; the contradictory `read_raw_slices(raw_dir(snapshot.root))` path was removed.
- **`AppLayerAbsenceEvidence` lives in core `src/codegenie/transforms/`**, not the plugin directory — a core type (`RemediationNotApplicable`) references it, so a plugin-dir placement would invert the dependency direction and break `make lint-imports`.
- **`AppLayerPrecheckCompleted`** is an additive `WorkflowInternalEvent` variant in `src/codegenie/plugins/events.py` (S6-01) — the "S3-05 additive" precedent.
- Added ACs for degenerate inputs (zero-affected CVE, missing `node_manifest` slice → `Escalate`, not a misleading `CVE_NOT_IN_APP_LAYER`), multi-package logical-OR, digest determinism, the pure lookup helper as a Phase-7 seam, and the positive-path event. Test fixtures made story-local (no forward dependency on S8-01).

## Context

Phase 3 ships the `vulnerability-remediation--node--npm` plugin scoped to `(vulnerability-remediation, node, npm)`. Today the plugin's `build_subgraph` produces the five-node pipeline `ingest_cve → match_recipe → apply_recipe → stage6_validate → write_branch` (S6-04). When the resolver routes a CVE to this plugin, every recipe's `Applies(plan)` check is iterated; if none match, the recipe engine short-circuits with `RecipeOutcome.NotApplicable(reason=ALL_RECIPES_NOT_APPLICABLE)` (S5-01) and the orchestrator emits a generic-reason outcome.

That behavior is correct but **insufficiently honest** for the specific failure mode this story addresses: a CVE whose affected package is *not in the app's resolved npm dep graph at all* because the package actually lives in the base container image (glibc CVE on an Alpine base), the JRE (a JVM-bundled `xerces` CVE), a vendored copy in source (a `vendor/` directory), or a runtime that bundles the package independently. The resolver matches the plugin (the repo *is* node+npm), every npm recipe correctly returns `NotApplies`, the engine reports `ALL_RECIPES_NOT_APPLICABLE` — but the reviewer reading the HITL escalation cannot tell whether (a) the plugin's recipes are buggy / incomplete or (b) the CVE is genuinely outside this plugin's remit. The two cases need different reviewer actions; today they produce identical outcomes.

[ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md) §Decision §Phase-3-scope and §Consequences §Phase-3 commit to a small, surgical refuse-mode in Phase 3 — explicitly **not** the full `vuln.provenance` primitive (which lands in Phase 7) — that gives reviewers an evidence-bearing distinct outcome when the CVE is not addressable by editing npm dependencies. The fix is implementable today using only the npm dep graph the existing Phase 2/3 probes already gather: lookup the CVE's affected package in the resolved npm dep tree; if the lookup is empty, short-circuit before any recipe is iterated. The new specific reason `CVE_NOT_IN_APP_LAYER` makes the failure mode actionable.

This story is the **precursor to Phase 7's full `vuln.provenance` adapter** — the npm-side precheck implemented here is exactly the shape `NpmVulnProvenanceAdapter` will be promoted to when Phase 7 introduces the multi-adapter chain (one app-layer adapter + one base-image adapter per `Provenance` lookup). Implementing it in Phase 3 prevents an embarrassing silent-wrong-fix failure mode and seeds the adapter shape Phase 7 inherits.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals` — the cardinal failure mode this story closes (silent-wrong-fix when CVE is outside scope).
  - `../phase-arch-design.md §Component design — RemediationOrchestrator` — the orchestrator runs whatever `build_subgraph` the plugin returns; this story's new node is inserted into the npm plugin's subgraph, not the orchestrator.
  - `../phase-arch-design.md §Edge cases` — adjacent rows E2 (yarn-berry repo mis-routed to the npm plugin → universal fallback) and E5 (transitive-only vuln). There is **no** dedicated "CVE not in the dep graph" row in the E1–E20 table today; this story's failure mode is specified by ADR-0038 §Context, not the arch §Edge cases table. (A follow-up arch edit could add an E21 row — out of scope for this story.)
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md` — ADR-0003 — the matched plugin must produce an evidence-bearing outcome, not silently no-op; the orchestrator routes the typed outcome.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — ADR-0010 — new reason variant follows the existing tagged-union + `assert_never` exhaustiveness pattern; no stringly-typed status fields.
- **Production ADRs (the rules this story implements):**
  - `../../../production/adrs/0038-vulnerability-provenance-attribution.md` — ADR-0038 §Decision §Phase-3-scope, §Consequences first bullet, §Tradeoffs first row — the Phase-3 refuse-mode this story implements verbatim; the Phase-7-promotion path the precheck seeds.
- **Sibling stories:**
  - `S6-03-subgraph-node-protocol.md` — the `SubgraphNode` Protocol + `NodeTransition = Advance | ShortCircuit | Escalate` sum type this node returns.
  - `S6-04-remediation-orchestrator.md` — the orchestrator's outer `match` over `NodeTransition` (no orchestrator changes needed; ShortCircuit propagates the outcome).
  - `S5-01-recipe-registry.md` — where `RecipeOutcome.NotApplicable.reason` is enumerated; the new `CVE_NOT_IN_APP_LAYER` variant joins `ALL_RECIPES_NOT_APPLICABLE`.
  - `S7-01-vuln-node-npm-plugin-scaffold.md` — the plugin's `build_subgraph` seam where this story's new node is inserted.
  - `S7-04-example-noop-plugin-bake-test.md` — the 3-plugin contract bake test that should exercise the new outcome.
- **Existing code (after Phase 2 lands):**
  - `src/codegenie/probes/layer_a/node_manifest.py` (Phase 2 NodeManifestProbe — the resolved npm dep graph slice).
  - Phase 2 `<raw_dir>/package-lock.json` mirror — the source of truth for the resolved tree.

## Goal

Insert a `verify_cve_in_app_layer` node at the head of the `vulnerability-remediation--node--npm` plugin's subgraph that returns `ShortCircuit(RemediationNotApplicable(reason="CVE_NOT_IN_APP_LAYER", evidence=AppLayerAbsenceEvidence(...)))` when the CVE's affected npm package is not present in the resolved `package-lock.json` dep graph, `Advance(state)` when it is, and `Escalate(...)` when the precheck cannot honestly run at all (no dep-graph slice, degenerate CVE record).

## Acceptance criteria

> **Validator note.** The original ACs were drafted against an imagined API surface. The list below is pinned to the **shipped** contracts: `NotApplicableReason` is a `typing.Literal` (not an enum) at `src/codegenie/transforms/outcomes.py:84`; the outcome class is `RemediationNotApplicable` (not `RemediationOutcome.NotApplicable`); `SubgraphState` (S6-03) carries `cve: CveId` + `bundle: Bundle | None` and **no** `cve_record` / `npm_dep_graph` field.

- [ ] **AC-1 — new `NotApplicableReason` Literal member.** A new member `"CVE_NOT_IN_APP_LAYER"` is added to the `NotApplicableReason` `Literal` alias at its single declaration site `src/codegenie/transforms/outcomes.py`. It is UPPER_SNAKE with value == name, matching the six existing members (`PEER_DEP_CONFLICT` … `NO_RECIPES_REGISTERED`) — it is a `Literal` member, **not** an enum variant (no `.value`, no attribute access; the bare string `"CVE_NOT_IN_APP_LAYER"` is the value). Every `match` over a `NotApplicableReason`-typed value — the S5-01 recipe-engine short-circuit, the S6-04 orchestrator finalize, the S5-05 `remediation-report.yaml` writer — gains a `case "CVE_NOT_IN_APP_LAYER":` arm, with `assert_never` on the fall-through keeping `mypy --strict` exhaustiveness.

- [ ] **AC-2 — short-circuit path (CVE not in app layer).** Given a CVE whose affected npm package(s) are **absent** from the resolved `package-lock.json` dep graph, `VerifyCveInAppLayerNode.run(state)` returns `ShortCircuit(RemediationNotApplicable(reason="CVE_NOT_IN_APP_LAYER", evidence=AppLayerAbsenceEvidence(...)))`; downstream subgraph nodes do **not** run and no recipe is iterated. (`ShortCircuit` carries a `RemediationOutcome`; the concrete class is `RemediationNotApplicable` — `outcomes.py:284`.)

- [ ] **AC-3 — advance path (CVE nominally in app layer).** Given a CVE whose affected npm package(s) are **present** in the resolved dep graph, `VerifyCveInAppLayerNode.run(state)` returns `Advance(state)` and the subgraph proceeds to `ingest_cve`. `Advance` means "the affected package is at least nominally in scope" — **not** "the recipe will succeed" (see Notes).

- [ ] **AC-4 — the node reads only real `SubgraphState` fields.** `VerifyCveInAppLayerNode` reads **only** fields that exist on `SubgraphState` (S6-03): `state.cve` (the `CveId`, for the evidence's `cve_id`) and `state.bundle` (the gather-slice `Bundle`, populated before the subgraph runs — arch C1 "resolve → bundle → [subgraph]"). The resolved npm dep graph is the `node_manifest` slice reached via the `Bundle` slice-access API established by S3-04. The CVE's affected-package identifiers come from the bundle's per-CVE resolution context (the BundleBuilder substitutes the affected package into the npm plugin's TCCM `must_read` `dep_graph.consumers` query — S7-01). The node does **no** disk I/O, **no** subprocess, **no** network. There is no `state.cve_record`, no `state.npm_dep_graph`, no `snapshot.root`, no `read_raw_slices` call. *(Executor precondition: bind these two reads to the real `Bundle` (S3-04) / TCCM (S7-01) API as the first implementation step; if the affected-package set is genuinely unreachable from `state.bundle` / `state.cve`, **stop and surface a BLOCKED-PARTIAL** — do not invent a `SubgraphState` field silently, as that is an S6-03 / ADR-0010 contract change.)*

- [ ] **AC-5 — six-node subgraph; orchestrator unchanged.** This story provides the first real implementation of the npm plugin's `build_subgraph(self, registry)` (S7-01 shipped it as a `raise NotImplementedError` stub). `build_subgraph(registry)` returns the six-node sequence `verify_cve_in_app_layer → ingest_cve → match_recipe → apply_recipe → stage6_validate → write_branch` — `VerifyCveInAppLayerNode` prepended at index 0 to the orchestrator's default five nodes. The customization is npm-plugin-local: the universal-fallback and synthetic noop plugins are unaffected. Orchestrator code is unchanged (S6-04 stays at one `match` over `NodeTransition`; `ShortCircuit` / `Escalate` propagate the outcome). `VerifyCveInAppLayerNode` lives under `plugins/vulnerability-remediation--node--npm/subgraph/verify_app_layer.py` and conforms structurally to the S6-03 `SubgraphNode` Protocol (`async def run(self, state: SubgraphState) -> NodeTransition`).

- [ ] **AC-6 — `AppLayerAbsenceEvidence` model in core `transforms/`.** `AppLayerAbsenceEvidence` is a Pydantic model (`model_config = ConfigDict(frozen=True, extra="forbid")`) living in **core** `src/codegenie/transforms/` (a new `evidence.py`, or appended to `outcomes.py`) — **not** the plugin directory, because the core type `RemediationNotApplicable` references it (a plugin-dir placement would make `transforms/` import from `plugins/` and break `make lint-imports`). Fields: `cve_id: CveId`, `affected_packages: list[PackageId]`, `resolved_npm_packages_searched: int`, `npm_dep_graph_digest: BlobDigest`. `PackageId` is the established Phase-3 newtype (`phase-arch-design.md §Data model`; the type `VulnIndex` already keys on) — construct via `PackageId.parse` at the boundary. There is **no** new `PackageName` type.

- [ ] **AC-7 — additive `evidence` field on `RemediationNotApplicable`.** `RemediationNotApplicable` (`src/codegenie/transforms/outcomes.py:284`) gains `evidence: AppLayerAbsenceEvidence | None = None` — added **additively** with a `None` default so the six existing `NotApplicableReason` reasons and every current `RemediationNotApplicable(...)` construction site keep working unchanged (precedent: `RecipeNotApplicable.considered`, added additively by S5-01 — see `outcomes.py:218-224`). It is a plain optional field, **not** a discriminated union — there is exactly one evidence variant in Phase 3. The S5-05 `remediation-report.yaml` writer serializes `outcome.evidence` when present.

- [ ] **AC-8 — `npm_dep_graph_digest` is deterministic.** `npm_dep_graph_digest` is a `BlobDigest` computed over a **canonical** (sorted-key, fixed-separator) serialization of the resolved dep graph: the same `node_manifest` slice yields a byte-identical digest across runs and regardless of dict/key iteration order. (Phase 3's determinism commitment — G4 — is veto-strength.) The digest carried on the `AppLayerPrecheckCompleted` event (AC-10) is the *same* value computed over the *same* canonical bytes.

- [ ] **AC-9 — normalized matching; multi-package is logical-OR.** Matching normalizes both the CVE's affected package names and the resolved dep-graph keys to lowercase before intersection, and matches scoped names (`@scope/name`) by their full normalized form. A CVE listing multiple affected packages **advances** if **any** one is in the dep graph (logical OR — not AND, not first-only); it short-circuits only when **none** are present, and `evidence.affected_packages` then lists all of them.

- [ ] **AC-10 — `AppLayerPrecheckCompleted` event: one per invocation, both paths.** The node emits exactly one `AppLayerPrecheckCompleted` event on the **workflow-internal** stream (S6-01, `src/codegenie/plugins/events.py`) per invocation — on the Advance path (`present_in_app_layer=True`) and the ShortCircuit path (`present_in_app_layer=False`) alike; zero spanning-stream emissions. The variant is added to `WorkflowInternalEvent` **additively** (precedent: `cache_gc_completed`, the "S3-05 additive" extension at arch line 872; arch lines 872/1080 authorize additive event-taxonomy extension); discriminator value `event_type="app_layer_precheck_completed"` (lowercase snake, matching the events convention). Payload: `event_id`, `workflow_id`, `cve_id`, `present_in_app_layer: bool`, `dep_graph_digest`.

- [ ] **AC-11 — degenerate inputs `Escalate`, never a misleading `CVE_NOT_IN_APP_LAYER`.** Absence-of-data must not masquerade as absence-of-package (CLAUDE.md "Facts, not judgments"; ADR-0003 evidence-bearing outcomes). (a) A missing `node_manifest` slice / `state.bundle is None` returns `Escalate(...)` — the node could not search. (b) A CVE record with **zero** affected packages returns `Escalate(...)` — the record is degenerate, not "out of app-layer scope". (c) A genuinely **empty but present** dep graph (a real zero-dependency repo) short-circuits with `CVE_NOT_IN_APP_LAYER` and `resolved_npm_packages_searched == 0` — that is an honest negative.

- [ ] **AC-12 — the lookup is a separately-testable pure function.** The CVE-package-in-dep-graph decision (intersection + digest + evidence construction) is a module-level **pure function** — no I/O, no event emission, no `SubgraphState` argument — over structured data, callable directly from a fast unit test. `VerifyCveInAppLayerNode.run` is the imperative shell: it reads the slice from `state.bundle`, calls the pure helper, emits the event, and maps the result to `Advance` / `ShortCircuit` / `Escalate`. (Load-bearing: Phase 7's `NpmVulnProvenanceAdapter` must wrap this helper without a refactor — the story's stated precursor purpose.)

- [ ] **AC-13 — the TDD red tests exist, are committed, and are green** (all tests in the TDD plan below, including the pure-helper unit tests and the determinism property test).

- [ ] **AC-14 — full gate green.** The full `make check` gate passes — `ruff format`, `ruff check`, `mypy --strict`, and the **whole `pytest -q` suite** (not just touched files — the changed `NotApplicableReason` Literal and `WorkflowInternalEvent` union are consumed by S5-01 / S6-04 / S5-05 and the event-taxonomy tests, which must stay green). `make lint-imports` stays green — no `src/codegenie/transforms/` module imports from `plugins/`. The S6-06 Phase-5 contract snapshot is regenerated to reflect the three additive widenings.

## Implementation outline

1. Add the `"CVE_NOT_IN_APP_LAYER"` member to the `NotApplicableReason` `Literal` at `src/codegenie/transforms/outcomes.py` (single declaration site). Add a `case "CVE_NOT_IN_APP_LAYER":` arm to every `match` over a `NotApplicableReason` value — the S5-01 recipe-engine short-circuit, the S6-04 orchestrator finalize, the S5-05 `remediation-report.yaml` writer. `assert_never` flips `mypy --strict` red until every site is updated.
2. Add `AppLayerAbsenceEvidence` (Pydantic, `frozen=True, extra="forbid"`) in **core** `src/codegenie/transforms/` — a new `evidence.py`, or appended to `outcomes.py`. It must be importable from `transforms/` because step 3 puts it on `RemediationNotApplicable`. Add `evidence: AppLayerAbsenceEvidence | None = None` to `RemediationNotApplicable` additively (mirror the `RecipeNotApplicable.considered` precedent — `None` default, existing callers untouched). Plain optional field — no discriminated-union machinery for one variant.
3. Write the **pure lookup helper** (a module-level function over `list[PackageId]` + the resolved tree — no I/O, no `SubgraphState`, no event emission) that does the normalized intersection, computes the canonical `npm_dep_graph_digest`, and returns the decision + `AppLayerAbsenceEvidence`. This is the surface Phase 7 wraps (AC-12).
4. Define `VerifyCveInAppLayerNode` implementing the S6-03 `SubgraphNode` Protocol (`async def run(self, state: SubgraphState) -> NodeTransition`). `run` is the imperative shell: read the `node_manifest` slice + affected-package set from `state.bundle`, call the pure helper, emit the event, and return `Advance` / `ShortCircuit` / `Escalate` (AC-11 degenerate-input handling). Bind the two `state.bundle` reads to the real S3-04 `Bundle` / S7-01 TCCM API.
5. Implement the npm plugin's `build_subgraph(self, registry)` — replacing S7-01's `NotImplementedError` stub — to return the six-node subgraph with `VerifyCveInAppLayerNode` prepended to the orchestrator's default five nodes (imported from S6-04). Confirm S6-04 exports the default subgraph in a composable form.
6. Add the `AppLayerPrecheckCompleted` variant to `WorkflowInternalEvent` in `src/codegenie/plugins/events.py` (additive — match whatever shape S6-01 shipped: a per-variant class appended to the `Annotated[…, Field(discriminator="event_type")]` union, with `event_type: Literal["app_layer_precheck_completed"]`). Emit it from `VerifyCveInAppLayerNode.run` on both paths.
7. Update the S5-05 `remediation-report.yaml` writer to serialize `outcome.evidence` when present.
8. Regenerate the S6-06 Phase-5 contract snapshot (`tests/integration/test_phase5_contract_snapshot.py` baseline) — the `NotApplicableReason` widening, the `RemediationNotApplicable.evidence` field, and the `WorkflowInternalEvent` variant all change the contract surface. Record the regeneration in the attempt log.

## TDD plan — red / green / refactor

> All pseudocode is pinned to the shipped APIs: `match` on the class `RemediationNotApplicable` (not `RemediationOutcome.NotApplicable`); `reason` is the bare string `"CVE_NOT_IN_APP_LAYER"` (a `Literal`, not an enum member — no attribute access); `build_subgraph` takes the `registry`; `PluginScope.parse` returns a `Result` and must be `.unwrap()`-ed.

### Test fixtures — story-local, no S8-01 dependency

This story does **not** depend on S8-01's `express-cve-2024-21501` portfolio fixture (S8-01 runs *after* S7-05 in sprint order — depending on it would be a dependency cliff). It ships a minimal self-contained fixture under `tests/integration/plugins/vulnerability_remediation_node_npm/fixtures/` — a hand-written tiny `package-lock.json` mirror resolving `express` (+ one transitive dep) — and synthetic CVE records. A `conftest.py` in the test directory defines the helpers used below, **one signature each**:

- `_build_plan(*, package_lock, cve_record) -> Plan` — `package_lock=None` simulates a missing `node_manifest` slice (AC-11a).
- `_run_subgraph(subgraph, plan, *, event_log_spy=None) -> RemediationOutcome` — single canonical signature.
- `_cve_for_package(name: str) -> CveRecord` / `_cve_for_packages(names: list[str]) -> CveRecord`.
- `_event_log_spy() -> EventLogSpy` — exposes `.internal: list` and `.spanning_count_of(cls) -> int`.

### Red — write the failing tests first

Integration tests — `tests/integration/plugins/vulnerability_remediation_node_npm/test_app_layer_precheck.py`:

```python
async def test_cve_for_unrelated_package_short_circuits_with_specific_reason():
    # CVE whose affected package is "glibc" — deliberately outside the npm dep graph
    plan = _build_plan(package_lock=MINIMAL_EXPRESS_LOCK, cve_record=_cve_for_package("glibc"))
    scope = PluginScope.parse("vulnerability-remediation--node--npm").unwrap()
    plugin = default_registry.resolve(scope).plugin
    subgraph = plugin.build_subgraph(default_registry)

    spy = _event_log_spy()
    outcome = await _run_subgraph(subgraph, plan, event_log_spy=spy)

    match outcome:
        case RemediationNotApplicable(reason="CVE_NOT_IN_APP_LAYER", evidence=ev):
            assert isinstance(ev, AppLayerAbsenceEvidence)
            assert ev.cve_id == CveId("CVE-FIXTURE-GLIBC")
            assert PackageId("glibc") in ev.affected_packages
            assert ev.resolved_npm_packages_searched > 0          # the graph WAS searched
        case _:
            pytest.fail(f"expected RemediationNotApplicable(CVE_NOT_IN_APP_LAYER), got {outcome}")
    # short-circuited at the HEAD — no recipe was iterated (kills the "node placed last" mutant)
    assert not any(e.event_type == "recipe_matched" for e in spy.internal)


async def test_cve_for_express_package_advances_and_precheck_actually_ran():
    plan = _build_plan(package_lock=MINIMAL_EXPRESS_LOCK, cve_record=_cve_for_package("express"))
    scope = PluginScope.parse("vulnerability-remediation--node--npm").unwrap()
    plugin = default_registry.resolve(scope).plugin
    subgraph = plugin.build_subgraph(default_registry)

    spy = _event_log_spy()
    outcome = await _run_subgraph(subgraph, plan, event_log_spy=spy)

    assert not (isinstance(outcome, RemediationNotApplicable)
                and outcome.reason == "CVE_NOT_IN_APP_LAYER")
    # the precheck actually RAN (not a no-op pass-through): it emitted its positive event
    precheck = [e for e in spy.internal if isinstance(e, AppLayerPrecheckCompleted)]
    assert len(precheck) == 1 and precheck[0].present_in_app_layer is True


async def test_build_subgraph_prepends_precheck_at_index_zero():
    scope = PluginScope.parse("vulnerability-remediation--node--npm").unwrap()
    plugin = default_registry.resolve(scope).plugin
    subgraph = plugin.build_subgraph(default_registry)
    assert isinstance(subgraph[0], VerifyCveInAppLayerNode)
    assert len(subgraph) == 6


async def test_multi_package_cve_advances_when_any_package_in_graph():
    # affected = ["glibc", "express"] — express IS in-graph and is NOT first → OR, not AND, not first-only
    plan = _build_plan(package_lock=MINIMAL_EXPRESS_LOCK,
                       cve_record=_cve_for_packages(["glibc", "express"]))
    outcome = await _run_subgraph(_subgraph(), plan)
    assert not (isinstance(outcome, RemediationNotApplicable)
                and outcome.reason == "CVE_NOT_IN_APP_LAYER")


async def test_multi_package_cve_short_circuits_when_none_in_graph():
    plan = _build_plan(package_lock=MINIMAL_EXPRESS_LOCK,
                       cve_record=_cve_for_packages(["glibc", "openssl"]))
    outcome = await _run_subgraph(_subgraph(), plan)
    match outcome:
        case RemediationNotApplicable(reason="CVE_NOT_IN_APP_LAYER", evidence=ev):
            assert set(ev.affected_packages) == {PackageId("glibc"), PackageId("openssl")}
        case _:
            pytest.fail(f"expected CVE_NOT_IN_APP_LAYER, got {outcome}")


async def test_missing_node_manifest_slice_escalates_not_short_circuits():
    plan = _build_plan(package_lock=None, cve_record=_cve_for_package("glibc"))
    outcome = await _run_subgraph(_subgraph(), plan)
    # absence-of-data must NOT masquerade as absence-of-package
    assert not (isinstance(outcome, RemediationNotApplicable)
                and outcome.reason == "CVE_NOT_IN_APP_LAYER")
    assert _is_escalation(outcome)


async def test_zero_affected_packages_cve_escalates():
    plan = _build_plan(package_lock=MINIMAL_EXPRESS_LOCK, cve_record=_cve_for_packages([]))
    outcome = await _run_subgraph(_subgraph(), plan)
    assert _is_escalation(outcome)   # degenerate CVE record, NOT CVE_NOT_IN_APP_LAYER
```

Event-discipline test — `test_app_layer_precheck_events.py`:

```python
async def test_app_layer_precheck_emits_one_internal_event_no_spanning():
    plan = _build_plan(package_lock=MINIMAL_EXPRESS_LOCK, cve_record=_cve_for_package("glibc"))
    spy = _event_log_spy()
    await _run_subgraph(_subgraph(), plan, event_log_spy=spy)
    internal = [e for e in spy.internal if isinstance(e, AppLayerPrecheckCompleted)]
    assert len(internal) == 1
    assert internal[0].present_in_app_layer is False
    assert internal[0].cve_id == CveId("CVE-FIXTURE-GLIBC")
    assert internal[0].dep_graph_digest                              # non-empty
    assert spy.spanning_count_of(AppLayerPrecheckCompleted) == 0     # internal stream only
```

Pure-helper unit tests — `tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_dep_graph_search.py` (fast, table-driven — the primary mutation-resistance anchor for the matching logic):

```python
def test_helper_hit_returns_no_evidence(): ...          # package present  -> Advance signal
def test_helper_miss_returns_evidence(): ...            # package absent   -> evidence built
def test_helper_multi_package_logical_or(): ...         # any-in-graph     -> hit  (kills the AND mutant)
def test_helper_normalizes_case_and_scoped_names(): ... # "@Babel/Core" matches "@babel/core"
def test_helper_empty_present_graph_is_honest_miss(): ...# zero-dep repo -> miss, searched == 0

# determinism — property-based via hypothesis (already a dev dep)
@given(dep_graph=st.dictionaries(st.text(), st.text()))
def test_dep_graph_digest_is_deterministic(dep_graph):
    assert digest(dep_graph) == digest(dep_graph)                       # idempotent
    assert digest(dep_graph) == digest(_shuffle_keys(dep_graph))        # canonical — order-independent
```

These fail today because `"CVE_NOT_IN_APP_LAYER"` is not yet a `NotApplicableReason` member, `VerifyCveInAppLayerNode` / `AppLayerAbsenceEvidence` / `AppLayerPrecheckCompleted` do not exist (`ImportError`), and `build_subgraph` still raises `NotImplementedError` (S7-01 stub).

### Green — minimal pass

Implementation outline steps 1–8. Keep the matching + digest logic in the pure helper (AC-12); `VerifyCveInAppLayerNode.run` stays a thin imperative shell.

### Refactor

- Confirm the pure helper is the exact surface Phase 7's `NpmVulnProvenanceAdapter` will wrap — a module-level function over `list[PackageId]` + the resolved tree, no `SubgraphState`, no I/O, no event emission. Phase 7 must wrap it with **zero** refactor (the story's stated precursor purpose).
- Add a module docstring on `VerifyCveInAppLayerNode` stating it is the Phase-7 precursor for `NpmVulnProvenanceAdapter` (with the ADR-0038 link), and that `Advance` means "nominally in scope", not "the recipe will succeed".
- Keep `RemediationNotApplicable.evidence` a plain `AppLayerAbsenceEvidence | None` field — **no** discriminated union for one variant. Note in the implementer notes that Phase 7 (multiple evidence shapes) is the rule-of-three moment to promote it.
- Confirm `make lint-imports` is green — `AppLayerAbsenceEvidence` in core `transforms/`, no `transforms/ → plugins/` import.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/outcomes.py` | Add `"CVE_NOT_IN_APP_LAYER"` to the `NotApplicableReason` `Literal`; add the additive `evidence: AppLayerAbsenceEvidence \| None = None` field to `RemediationNotApplicable`. (Verified path — there is no `transforms/types/` subdir.) |
| `src/codegenie/transforms/evidence.py` | New — `AppLayerAbsenceEvidence` Pydantic model. **Core** location is mandatory (a core type references it); may instead be appended to `outcomes.py`. |
| `src/codegenie/plugins/events.py` | Add the `AppLayerPrecheckCompleted` variant to `WorkflowInternalEvent` (S6-01's event module — verified path; there is no `src/codegenie/events/` directory). |
| `src/codegenie/transforms/recipe_engine.py` + the S6-04 orchestrator finalize site | Add the `case "CVE_NOT_IN_APP_LAYER":` arm to each `match`-over-reason site. |
| `plugins/vulnerability-remediation--node--npm/subgraph/verify_app_layer.py` | New — `VerifyCveInAppLayerNode` (imperative shell) + the pure lookup helper. |
| `plugins/vulnerability-remediation--node--npm/api.py` | Implement `build_subgraph(self, registry)` — replace S7-01's `NotImplementedError` stub; prepend the new node. |
| `src/codegenie/output/remediation_report.py` (or wherever S5-05's writer lives) | Serialize `outcome.evidence` when present. |
| `tests/integration/plugins/vulnerability_remediation_node_npm/conftest.py` | New — story-local test helpers (single signature each). |
| `tests/integration/plugins/vulnerability_remediation_node_npm/fixtures/` | New — minimal `package-lock.json` mirror + synthetic CVE records (no S8-01 dependency). |
| `tests/integration/plugins/vulnerability_remediation_node_npm/test_app_layer_precheck.py` | New — short-circuit / advance / ordering / multi-package / degenerate-input tests. |
| `tests/integration/plugins/vulnerability_remediation_node_npm/test_app_layer_precheck_events.py` | New — event-emission discipline test. |
| `tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_dep_graph_search.py` | New — pure-helper unit tests + the digest-determinism property test. |
| `tests/integration/test_phase5_contract_snapshot.py` (S6-06 baseline) | Regenerate — the `NotApplicableReason` widening, `RemediationNotApplicable.evidence`, and the `WorkflowInternalEvent` variant all change the contract surface. |
| `plugins/PLUGINS.lock` | Re-hash the plugin tree (new files change the tree sha256). |

## Out of scope

- **Full `vuln.provenance` primitive + multi-adapter chain.** Phase 7 territory per [ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md). This story only handles the npm-side precheck; base-image / runtime-bundled / vendored detection is not introduced here.
- **`NpmVulnProvenanceAdapter` class wrapping the lookup as the canonical Phase-7 adapter.** Phase 7 promotes the helper this story ships; this story does not pre-introduce the adapter shape (premature pluggability per the phase's pattern catalog).
- **The `BaseImage`, `RuntimeBundled`, `AppVendored`, `Both`, `Unknown` provenance variants** — every CVE that fails this precheck is reported via the simple `CVE_NOT_IN_APP_LAYER` reason; the seven-variant sum type from ADR-0038 does not land in Phase 3.
- **Updating the universal HITL fallback (S7-03) to specially format `CVE_NOT_IN_APP_LAYER` outcomes** — Phase 3's universal fallback handles the new outcome via its existing generic markdown sanitizer; richer routing decisions are Phase 8 Planner territory.
- **Bench cases that exercise the precheck.** Phase 6.5's `bench/vuln-remediation/` may add a `cve-not-in-app-layer` case as a follow-up, but Phase 3 does not introduce one (the cardinal bench cases are already the lockfile-bump happy-path scenarios).

## Notes for the implementer

- **The node is the HEAD of the subgraph** — it runs before `ingest_cve`. By the time the subgraph runs, the orchestrator has already resolved the plugin and built the `Bundle` (arch C1: "resolve → bundle → [subgraph]"), so `state.bundle` is populated for the head node. Read both inputs (resolved dep graph, affected-package set) from `state.bundle` — that is the only `SubgraphState` field carrying gather evidence. The node needs no parsed CVE *record* on the state; `state.cve` (the `CveId`) supplies the evidence's `cve_id`.
- **Bind the two reads to real APIs as the first step.** `SubgraphState` (S6-03) has `cve: CveId` and `bundle: Bundle | None` — and **no** `cve_record` / `npm_dep_graph` / `snapshot`. Confirm against S3-04 the `Bundle` slice-access API (`node_manifest` slice) and against S7-01 how the affected-package set rides in the bundle (the TCCM `dep_graph.consumers` query has the affected `package` substituted by the BundleBuilder). If the affected-package set is genuinely unreachable from `state.bundle` / `state.cve`, **stop and surface a BLOCKED-PARTIAL** — do not invent a `SubgraphState` field; an additive widening of that frozen state model is an S6-03 / ADR-0010 contract change needing its own story or ADR amendment.
- **Watch the exhaustiveness discipline.** Adding a `NotApplicableReason` member flips every `match` over `reason` red until the `case "CVE_NOT_IN_APP_LAYER":` arm is added with `assert_never` on the fall-through. This is a feature — it forces every consumer (S5-01, S6-04, S5-05) to acknowledge the new member. Do not catch-all.
- **The lookup is a pure function over gather-time slices.** No `SubprocessJail`, no network, no LSP, no SCIP — a normalized dict walk against the parsed `package-lock.json` mirror. Keep it a module-level pure function (AC-12), not buried in the node class — that is what keeps the story small and keeps the precheck out of the per-workflow latency budget. The event is emitted by `VerifyCveInAppLayerNode.run` (the imperative shell), constructed from the pure helper's return value — `present_in_app_layer` and `dep_graph_digest` are *outputs* of the lookup, not side effects of it.
- **Absence of data ≠ absence of package.** A missing `node_manifest` slice, `bundle is None`, or a zero-affected-packages CVE record must `Escalate` — never `CVE_NOT_IN_APP_LAYER`. Reporting "not in app layer" when the node could not actually search would be a dishonest fact (CLAUDE.md "Facts, not judgments"; ADR-0003). Only a genuinely empty-but-present dep graph short-circuits, with `resolved_npm_packages_searched == 0`.
- **Honest confidence reporting.** The precheck is *not* full provenance — a CVE for `lodash` may pass the precheck (lodash IS in the npm graph) and still fail recipe iteration (the affected version range doesn't intersect the resolved version). `Advance(state)` means "nominally in scope," not "the recipe will succeed." Document this in the node's module docstring.
- **Multi-package CVEs are logical-OR.** A CVE may list several affected packages; the precheck advances if ANY one is in the graph. Implement in the pure helper; the parametrized multi-package tests (AC-9) are mandatory, not optional.
- **`npm_dep_graph_digest` is load-bearing for reproducibility — and must be deterministic.** Compute it over a canonical (sorted-key) serialization so a reviewer six months on can reproduce the lookup against the same gather snapshot. Pin the digest, not a path. The same value rides on the `AppLayerPrecheckCompleted` event.
- **Use `PackageId`, not a new `PackageName`.** `PackageId` (with its `.parse` smart constructor) is the established Phase-3 npm-package identifier and the type `VulnIndex` already keys on. Construct via `PackageId.parse` at the CVE-record boundary — never raw `str` for the domain ID (CLAUDE.md "Newtype identifiers"; ADR-0010).
- **`evidence` stays a plain optional field in Phase 3.** One variant, no discriminated union. When Phase 7 adds `BaseImage` / `RuntimeBundled` / `AppVendored` evidence shapes, *that* is the rule-of-three moment to promote `RemediationNotApplicable.evidence` to a discriminated union with a `kind` discriminator — not now (Rule 2; consistent with this story's own Out-of-scope framing).
- **This story is the Phase-7 precursor for `NpmVulnProvenanceAdapter`.** Per [ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md) §Consequences first bullet, the Phase-3 refuse-mode helper is *promoted* into the Phase-7 adapter — so the pure lookup helper (AC-12) must be a clean module-level function the adapter can wrap with zero refactor. This is why AC-12 is an AC, not a suggestion.
