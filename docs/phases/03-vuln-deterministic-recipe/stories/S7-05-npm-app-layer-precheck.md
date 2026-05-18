# Story S7-05 — npm plugin app-layer precheck (refuse-mode for non-app-layer CVEs)

**Step:** Step 7 — First production plugin, universal HITL fallback plugin, synthetic third plugin
**Status:** Ready
**Effort:** S
**Depends on:** S7-01 (plugin scaffold + `build_subgraph` seam exists), S6-03 (`SubgraphNode` Protocol + `NodeTransition` tagged union), S5-01 (`RecipeOutcome.NotApplicable.reason` enum lives in the recipe registry surface), S6-04 (orchestrator runs the plugin's `build_subgraph` output)
**ADRs honored:** [production ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md) (refuse-mode for non-app-layer CVEs — Phase 3's Phase-7-precursor commitment), [ADR-0003](../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md) (the matched plugin is not silently substituted when it cannot act — the workflow exits with an evidence-bearing outcome that the orchestrator routes to HITL), [ADR-0010](../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md) (new `RecipeOutcome.NotApplicable.reason = CVE_NOT_IN_APP_LAYER` variant follows the existing tagged-union + `assert_never` exhaustiveness discipline)

## Context

Phase 3 ships the `vulnerability-remediation--node--npm` plugin scoped to `(vulnerability-remediation, node, npm)`. Today the plugin's `build_subgraph` produces the five-node pipeline `ingest_cve → match_recipe → apply_recipe → stage6_validate → write_branch` (S6-04). When the resolver routes a CVE to this plugin, every recipe's `Applies(plan)` check is iterated; if none match, the recipe engine short-circuits with `RecipeOutcome.NotApplicable(reason=ALL_RECIPES_NOT_APPLICABLE)` (S5-01) and the orchestrator emits a generic-reason outcome.

That behavior is correct but **insufficiently honest** for the specific failure mode this story addresses: a CVE whose affected package is *not in the app's resolved npm dep graph at all* because the package actually lives in the base container image (glibc CVE on an Alpine base), the JRE (a JVM-bundled `xerces` CVE), a vendored copy in source (a `vendor/` directory), or a runtime that bundles the package independently. The resolver matches the plugin (the repo *is* node+npm), every npm recipe correctly returns `NotApplies`, the engine reports `ALL_RECIPES_NOT_APPLICABLE` — but the reviewer reading the HITL escalation cannot tell whether (a) the plugin's recipes are buggy / incomplete or (b) the CVE is genuinely outside this plugin's remit. The two cases need different reviewer actions; today they produce identical outcomes.

[ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md) §Decision §Phase-3-scope and §Consequences §Phase-3 commit to a small, surgical refuse-mode in Phase 3 — explicitly **not** the full `vuln.provenance` primitive (which lands in Phase 7) — that gives reviewers an evidence-bearing distinct outcome when the CVE is not addressable by editing npm dependencies. The fix is implementable today using only the npm dep graph the existing Phase 2/3 probes already gather: lookup the CVE's affected package in the resolved npm dep tree; if the lookup is empty, short-circuit before any recipe is iterated. The new specific reason `CVE_NOT_IN_APP_LAYER` makes the failure mode actionable.

This story is the **precursor to Phase 7's full `vuln.provenance` adapter** — the npm-side precheck implemented here is exactly the shape `NpmVulnProvenanceAdapter` will be promoted to when Phase 7 introduces the multi-adapter chain (one app-layer adapter + one base-image adapter per `Provenance` lookup). Implementing it in Phase 3 prevents an embarrassing silent-wrong-fix failure mode and seeds the adapter shape Phase 7 inherits.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals` — the cardinal failure mode this story closes (silent-wrong-fix when CVE is outside scope).
  - `../phase-arch-design.md §Component design — RemediationOrchestrator` — the orchestrator runs whatever `build_subgraph` the plugin returns; this story's new node is inserted into the npm plugin's subgraph, not the orchestrator.
  - `../phase-arch-design.md §Edge cases` — the "CVE for unrelated package" row (the failure mode this story addresses head-on).
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

Insert a `verify_cve_in_app_layer` node at the head of the `vulnerability-remediation--node--npm` plugin's subgraph that returns `ShortCircuit(RemediationOutcome.NotApplicable(reason=CVE_NOT_IN_APP_LAYER))` when the CVE's affected npm package is not present in the resolved `package-lock.json` dep graph, and `Advance(state)` otherwise.

## Acceptance criteria

- [ ] A new `RecipeOutcome.NotApplicable.reason` enum variant `CVE_NOT_IN_APP_LAYER` exists (literal `"cve_not_in_app_layer"` for serialization), and every `match`-on-reason site updates to handle it exhaustively (`assert_never` keeps the discipline).
- [ ] A new `SubgraphNode` implementation `VerifyCveInAppLayerNode` lives under `plugins/vulnerability-remediation--node--npm/subgraph/verify_app_layer.py`; it reads `state.cve_record` + `state.npm_dep_graph` (the resolved tree from `state.bundle.slices["node_manifest"]`) and returns `Advance(state)` if the CVE's `affected.packages[*].name` intersects the resolved tree, else `ShortCircuit(RemediationOutcome.NotApplicable(reason=CVE_NOT_IN_APP_LAYER, evidence=AppLayerAbsenceEvidence(...)))`.
- [ ] The plugin's `build_subgraph` returns a six-node subgraph `verify_cve_in_app_layer → ingest_cve → match_recipe → apply_recipe → stage6_validate → write_branch` — the new node is the head; orchestrator code is unchanged (S6-04 stays at one `match` over `NodeTransition`).
- [ ] `AppLayerAbsenceEvidence` is a Pydantic model (`extra="forbid"`, `frozen=True`) carrying `cve_id: CveId`, `affected_package_names: list[PackageName]`, `resolved_npm_packages_searched: int`, `npm_dep_graph_digest: BlobDigest` so reviewers can reproduce the lookup; serialized into the `remediation-report.yaml` `outcome.evidence` field.
- [ ] The new node emits one `WorkflowInternalEvent` per invocation — `AppLayerPrecheckCompleted(workflow_id, cve_id, present_in_app_layer: bool, dep_graph_digest)` — on the workflow-internal stream (S6-01); no spanning-stream emission.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff format`, `ruff check`, `mypy --strict`, and `pytest` all pass on touched files.

## Implementation outline

1. Extend the `RecipeOutcome.NotApplicable.reason` enum with `CVE_NOT_IN_APP_LAYER`; update every `match` over `reason` (S5-01 engine short-circuit site, S6-04 orchestrator finalize site, the `remediation-report.yaml` writer in S5-05) with the new variant. `assert_never` flips red until every site is updated.
2. Define `AppLayerAbsenceEvidence` Pydantic model under the plugin's `subgraph/evidence.py` (or wherever the plugin's typed evidence shapes live).
3. Define `VerifyCveInAppLayerNode` implementing `SubgraphNode` (S6-03 Protocol). The node's `run(state)` does one read against the `node_manifest` slice and returns `Advance(state)` or `ShortCircuit(...)`. The slice access goes through the same `read_raw_slices(raw_dir(snapshot.root))` kernel S5-04 established (no per-plugin disk-IO duplication).
4. Update the plugin's `build_subgraph` to prepend `VerifyCveInAppLayerNode` to the existing five-node sequence.
5. Add the new event variant `AppLayerPrecheckCompleted` to `WorkflowInternalEvent` (S6-01's discriminated union) and emit it from the node.
6. Wire the new evidence type into the `remediation-report.yaml` writer (S5-05) — `outcome.evidence` becomes a discriminated union over `AppLayerAbsenceEvidence | …existing variants…`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Two red tests anchor this story (the positive and negative paths, each load-bearing):

Test file path: `tests/integration/plugins/vulnerability_remediation_node_npm/test_app_layer_precheck.py`

```python
# tests/integration/plugins/vulnerability_remediation_node_npm/test_app_layer_precheck.py

async def test_cve_for_unrelated_package_short_circuits_with_specific_reason():
    # arrange — Express-fixture repo + a CVE whose affected.packages.name is "glibc"
    #          (deliberately outside the resolved npm dep graph)
    plan = await _build_plan(
        repo_fixture="express-cve-2024-21501",
        cve_record=_cve_for_package("glibc"),
    )
    plugin = default_registry.resolve(PluginScope.parse("vulnerability-remediation--node--npm")).plugin
    subgraph = plugin.build_subgraph()

    # act — run the subgraph head-to-tail
    outcome = await _run_subgraph(subgraph, plan)

    # assert — short-circuit at the first node with the new specific reason
    match outcome:
        case RemediationOutcome.NotApplicable(reason=NotApplicableReason.CVE_NOT_IN_APP_LAYER, evidence=ev):
            assert isinstance(ev, AppLayerAbsenceEvidence)
            assert ev.cve_id == CveId("CVE-FIXTURE-GLIBC")
            assert "glibc" in ev.affected_package_names
            assert ev.resolved_npm_packages_searched > 0  # the graph was searched, not skipped
        case _:
            pytest.fail(f"expected NotApplicable(CVE_NOT_IN_APP_LAYER), got {outcome}")


async def test_cve_for_express_package_advances_to_match_recipe():
    # arrange — same Express fixture, but a CVE whose affected.packages.name is "express"
    plan = await _build_plan(
        repo_fixture="express-cve-2024-21501",
        cve_record=_cve_for_package("express"),
    )
    plugin = default_registry.resolve(PluginScope.parse("vulnerability-remediation--node--npm")).plugin
    subgraph = plugin.build_subgraph()

    # act
    outcome = await _run_subgraph(subgraph, plan)

    # assert — precheck passes; downstream nodes run; outcome is not the precheck refuse
    assert not _is_precheck_refuse(outcome), \
        f"express CVE should pass the precheck; got {outcome}"
```

These fail today because `CVE_NOT_IN_APP_LAYER` doesn't exist as a variant (`AttributeError`), `VerifyCveInAppLayerNode` doesn't exist (`ImportError`), and the plugin's `build_subgraph` still returns five nodes (so the precheck never runs and the outcome reason will be `ALL_RECIPES_NOT_APPLICABLE` instead of the new specific one).

A third, smaller red test anchors the event-emission discipline:

Test file path: `tests/integration/plugins/vulnerability_remediation_node_npm/test_app_layer_precheck_events.py`

```python
async def test_app_layer_precheck_emits_one_workflow_internal_event_no_spanning():
    plan = await _build_plan(repo_fixture="express-cve-2024-21501",
                              cve_record=_cve_for_package("glibc"))
    event_log_spy = _spy_event_log()
    # act
    await _run_subgraph(plan_for(plan), event_log_spy=event_log_spy)
    # assert
    internal_events = [e for e in event_log_spy.internal if isinstance(e, AppLayerPrecheckCompleted)]
    assert len(internal_events) == 1
    assert internal_events[0].present_in_app_layer is False
    assert event_log_spy.spanning_count_of(AppLayerPrecheckCompleted) == 0  # internal stream only
```

### Green — minimal pass

1. Add `CVE_NOT_IN_APP_LAYER = "cve_not_in_app_layer"` to the `NotApplicableReason` enum. Update every `match` site exhaustively until `mypy --strict` is clean and `assert_never` discipline holds.
2. Add `AppLayerAbsenceEvidence` Pydantic model (`extra="forbid"`, `frozen=True`) with the five fields above.
3. Add `AppLayerPrecheckCompleted` to `WorkflowInternalEvent`'s discriminated union (S6-01).
4. Add `plugins/vulnerability-remediation--node--npm/subgraph/verify_app_layer.py` with `class VerifyCveInAppLayerNode(SubgraphNode)`; `run(state)` reads `state.bundle.slices["node_manifest"]`, walks the resolved tree once, and returns the discriminated outcome.
5. Update the plugin's `build_subgraph` to prepend the new node.
6. Update `S5-05`'s `RemediationReport` writer to handle the new `evidence` variant in serialization.

### Refactor

- Confirm `NpmDepGraphSearchHelper` (or its analogue) is shared with anything Phase 7 will lift into `NpmVulnProvenanceAdapter` — the precheck *is* the npm half of the future provenance adapter; the lookup logic should be a pure helper that the future adapter can wrap without duplication.
- Add a docstring on `VerifyCveInAppLayerNode` explicitly stating this is the Phase-7-precursor for `NpmVulnProvenanceAdapter`, with the ADR-0038 link, so the future implementer finds the right starting point.
- Confirm the `outcome.evidence` discriminated union has `extra="forbid"` at every nested variant; the new `AppLayerAbsenceEvidence` joins the union without breaking serialization.
- Add `_WARNING_IDS: Final[frozenset[str]] = frozenset(["app_layer_precheck.cve_not_in_app_layer"])` per the project's warning-ID discipline.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/types/outcomes.py` (or wherever S1-03's outcome types live) | Add `CVE_NOT_IN_APP_LAYER` variant to `NotApplicableReason`. |
| `src/codegenie/transforms/types/evidence.py` (or wherever Phase 3 evidence types live) | New `AppLayerAbsenceEvidence` Pydantic model. |
| `src/codegenie/events/workflow_internal.py` (or the S6-01 event discriminated-union module) | Add `AppLayerPrecheckCompleted` event variant. |
| `plugins/vulnerability-remediation--node--npm/subgraph/verify_app_layer.py` | New `VerifyCveInAppLayerNode`. |
| `plugins/vulnerability-remediation--node--npm/api.py` | Update `build_subgraph` to prepend the new node. |
| `src/codegenie/output/remediation_report.py` (or wherever S5-05's writer lives) | Update serialization for the new evidence variant. |
| `tests/integration/plugins/vulnerability_remediation_node_npm/test_app_layer_precheck.py` | New — the two TDD red tests. |
| `tests/integration/plugins/vulnerability_remediation_node_npm/test_app_layer_precheck_events.py` | New — the event-emission red test. |
| `plugins/PLUGINS.lock` | Re-hash the plugin tree (new files change the tree sha256). |

## Out of scope

- **Full `vuln.provenance` primitive + multi-adapter chain.** Phase 7 territory per [ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md). This story only handles the npm-side precheck; base-image / runtime-bundled / vendored detection is not introduced here.
- **`NpmVulnProvenanceAdapter` class wrapping the lookup as the canonical Phase-7 adapter.** Phase 7 promotes the helper this story ships; this story does not pre-introduce the adapter shape (premature pluggability per the phase's pattern catalog).
- **The `BaseImage`, `RuntimeBundled`, `AppVendored`, `Both`, `Unknown` provenance variants** — every CVE that fails this precheck is reported via the simple `CVE_NOT_IN_APP_LAYER` reason; the seven-variant sum type from ADR-0038 does not land in Phase 3.
- **Updating the universal HITL fallback (S7-03) to specially format `CVE_NOT_IN_APP_LAYER` outcomes** — Phase 3's universal fallback handles the new outcome via its existing generic markdown sanitizer; richer routing decisions are Phase 8 Planner territory.
- **Bench cases that exercise the precheck.** Phase 6.5's `bench/vuln-remediation/` may add a `cve-not-in-app-layer` case as a follow-up, but Phase 3 does not introduce one (the cardinal bench cases are already the lockfile-bump happy-path scenarios).

## Notes for the implementer

- **The new node sits BEFORE `ingest_cve`, not inside it.** `ingest_cve` parses the CVE record into the workflow state; `verify_cve_in_app_layer` then reads the parsed CVE + the gather-time npm dep graph. Reversing the order means the precheck has no CVE to check against. Put the new node first in `build_subgraph`'s sequence.
- **Watch the exhaustiveness discipline.** Adding a `NotApplicableReason` variant flips every `match` over `reason` red until the new branch is added with `assert_never` discipline. This is a feature: it forces every consumer to acknowledge the new variant. Do not silently catch-all.
- **The lookup is a pure function over gather-time slices.** No `SubprocessJail` calls, no network, no LSP, no SCIP — just a dict walk against the parsed `package-lock.json` mirror. This is what makes the story "S" effort and what keeps the precheck out of the per-workflow latency budget.
- **Honest confidence reporting.** The precheck is *not* full provenance — a CVE for `lodash` might pass the precheck (lodash IS in the npm graph) and still fail the actual recipe iteration (e.g., the affected version range doesn't intersect the resolved version). The `Advance(state)` outcome means "the CVE's package is at least nominally in scope," not "the recipe will succeed." Document this in the node's module docstring so future readers don't over-trust the precheck.
- **Multi-package CVE handling.** A CVE may list multiple affected packages (e.g., a transitive vulnerability affecting both `parent` and `child`). The precheck passes if ANY affected package is in the npm dep graph (logical OR, not AND). Document this in the lookup helper; add a parametrized test case if it isn't obvious from the integration test.
- **The `dep_graph_digest` evidence field is load-bearing for reproducibility.** A reviewer reading the `remediation-report.yaml` six months from now needs to be able to verify the precheck against the same gather snapshot — pin the digest, not a path.
- **This story is the Phase-7-precursor for `NpmVulnProvenanceAdapter` — keep the lookup logic in a pure helper module the future adapter can wrap.** Per [ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md) §Consequences first bullet, "the Phase 3 `NpmVulnProvenanceAdapter` is promoted from its refuse-mode shape" — making the helper a clean module-level function (not buried in the node class) saves Phase 7 a refactor.
