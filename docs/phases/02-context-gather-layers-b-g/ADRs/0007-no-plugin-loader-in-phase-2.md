# ADR-0007: No Plugin Loader in Phase 2 — Protocols + TCCMLoader skeleton only; Phase 3 ships loader + first plugin + adapters together

**Status:** Accepted
**Date:** 2026-05-14
**Tags:** roadmap-fidelity · plugin-architecture · scope · phase-boundary · premature-pluggability
**Related:** 02-ADR-0006, [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md), [production ADR-0032](../../../production/adrs/0032-language-search-adapters.md), [production ADR-0029](../../../production/adrs/0029-task-class-context-manifests.md)

## Context

[Production ADR-0031](../../../production/adrs/0031-plugin-architecture.md) defines the plugin architecture: granular `(task × language × build-tool)` plugins under `plugins/{slug}/` with `plugin.yaml`, `tccm.yaml`, `probes/`, `adapters/`, `subgraph/`, `skills/`, `recipes/`. Its §Consequences §1 is explicit: **"Phase 3 of the roadmap (first vuln remediation, deterministic recipe path) becomes 'author `vulnerability-remediation--node--npm`.' The first plugin doubles as the proof that the plugin loader works."** The plugin loader, the universal `(*, *, *)` fallback plugin, the first concrete plugin, the four [ADR-0032](../../../production/adrs/0032-language-search-adapters.md) adapter implementations, the [ADR-0029](../../../production/adrs/0029-task-class-context-manifests.md) TCCM in-tree, the Skills, and the OpenRewrite recipes all ship together in Phase 3, by ADR design.

The performance lens proposed shipping the plugin loader + a universal-fallback plugin (`plugins/universal--*--*/plugin.yaml`) in Phase 2 "to make the kernel-side seam exist." Its own §Risks §4 admitted "shipping infrastructure on speculation." The critic ([critique.md §"Attacks on the performance-first design" #1](../critique.md)) and §"Cross-design observations" §"Which disagreement matters most" attacked this verbatim: pulling the loader forward hollows Phase 3's exit criterion — "the first plugin doubles as the proof" requires the loader and the plugin to land together. A loader without a plugin to test it (or with a synthetic universal-fallback whose `contributes.adapters: {}` is empty) is premature pluggability dressed as scaffolding.

Best-practices lens proposed the opposite: ship **only** kernel-side scaffolding (adapter `Protocol`s, `TCCMLoader`, `Skill` loader, `IndexFreshness`) and let Phase 3 own the loader + first plugin together. The synthesizer (`final-design.md §"Conflict-resolution table" row 1, §"Departures from all three inputs" §"Kernel scaffolding"`) picked this path verbatim. The risk it accepts is **adapter Protocol drift** — Phase 3's first adapter may discover the Protocol shape is wrong (e.g., `consumers(self, pkg: str)` should be `consumers(self, pkg: PackageId, *, transitively: bool = False)`). Gap 1 improvement (an integration test that lands skipped in Phase 2 and enables at Phase 3 land time) makes the contract-violation discoverable at PR review.

This ADR records the decision and the boundary discipline: Phase 2 ships `Protocol` types + loaders + sum types; Phase 3 ships the runtime mechanism that turns those types into a plugin system.

## Options considered

- **Option A — Ship plugin loader + universal-fallback plugin + `plugin.yaml` parser in Phase 2.** **Pattern:** Plugin architecture, prematurely. Performance lens's pick. Hollows Phase 3's exit criterion; "the first plugin doubles as the proof" loses its meaning when the proof already exists with no plugin to test it. Critic finding #1.
- **Option B — Ship nothing plugin-related in Phase 2.** Defer all of ADR-0031/0032/0029 to Phase 3. Wrong: roadmap names ADR-0029 (TCCMs), ADR-0030 (graph-aware queries), ADR-0031, ADR-0032 as load-bearing inputs for Phase 2; Phase 3 cannot land both the kernel-side typing surface AND the first concrete consumer in a single phase without inheriting *something* from Phase 2.
- **Option C — Ship kernel-side scaffolding only: four adapter `Protocol`s (zero implementations) at `codegenie/adapters/protocols.py`, `TCCMLoader` + `TCCM` Pydantic model + `DerivedQuery` discriminated union at `codegenie/tccm/`, `SkillsLoader` at `codegenie/skills/`, `IndexFreshness` at `codegenie/indices/freshness.py` (02-ADR-0006). NO plugin loader. NO `plugin.yaml` parser. NO `plugins/universal--*--*/` directory. NO adapter implementations.** **Pattern:** Documentation as code + Protocol-as-contract. Synthesis pick. Phase 3 inherits typed surfaces on day 1; the plugin loader and first plugin ship together as ADR-0031 §Consequences §1 prescribes.

## Decision

Adopt **Option C**. Phase 2 ships:
- `codegenie/adapters/protocols.py` — four `Protocol` classes (`DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`) with `@runtime_checkable` decorators. Zero implementations. ~80 LOC total, stdlib + `typing` only.
- `codegenie/adapters/confidence.py` — `AdapterConfidence = Trusted | Degraded(reason) | Unavailable(reason)` placeholder (variant set owned by Phase 3 per 02-ADR-0006).
- `codegenie/tccm/` — `TCCMLoader.load(path) -> Result[TCCM, TCCMLoadError]`. `TCCM`, `DerivedQuery` Pydantic models. The five-variant `DerivedQuery` discriminated union covers ADR-0030's five primitives; no `Unknown` variant — ADR-amend on a sixth.
- `codegenie/skills/` — `SkillsLoader(search_paths).load_all() -> Result[list[Skill], SkillsLoadError]`. Three-tier merge (user > repo-local > org-shared); `O_NOFOLLOW` at file open; reuses Phase 1 `safe_yaml.load` chokepoint.

Phase 2 ships **NO**:
- Plugin loader (no `PluginLoader`, no plugin-registry, no `plugin.yaml` parser).
- Universal `(*, *, *)` fallback plugin.
- `plugins/` directory in the source tree (in Phase 2's land, that directory does not exist).
- Adapter implementations (no `DepGraphNpmAdapter`, no `ScipNodeAdapter`, no `NullAdapter` stubs).

The reference TCCM that exercises every `DerivedQuery` primitive (`docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml`) lives under `docs/`, not under `plugins/` — deliberately outside the plugin namespace Phase 3 owns. **Pattern: Phase boundary discipline + documentation-as-code + Protocol-as-contract.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 3's exit criterion ("first plugin doubles as proof the loader works") survives intact — the loader and the plugin land together, as ADR-0031 §Consequences §1 prescribes | Phase 2 ships four `Protocol` classes with **zero implementations**; the contract-correctness question is answered by Phase 3's first concrete adapter, which may discover the Protocol shape is wrong. Critic-acknowledged risk |
| Phase 3 inherits day-1 typed surfaces — `DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`, `IndexFreshness`, `TCCM`, `DerivedQuery`, `Skill` — and writes its first plugin against them without guessing shapes | Phase 3 may need to amend a Phase 2 module (e.g., add a fifth `DerivedQuery` primitive), which ripples through any Phase 3 plugin code that prototyped against the wrong shape. Gap 1 improvement: `tests/integration/adapters/test_phase3_handoff_smoke.py` lands skipped in Phase 2 and unskips at Phase 3 land time — the test makes the contract violation discoverable at PR review |
| Premature-pluggability anti-pattern (`design-patterns-toolkit.md`'s flag-on-sight list) is avoided — no "pluggable" architecture with zero plugins; no `NullAdapter` fixtures validating schemas that validate themselves | The reference TCCM is **deliberately outside** `plugins/` (lives at `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml`); the integration test (`tests/integration/tccm/test_reference_tccm_roundtrips.py`) loads it from `docs/`, which is unusual. Documented in the test docstring; the alternative (synthetic plugin under `tests/fixtures/plugins/`) was refused as implying pluggability Phase 3 owns |
| `codegenie/adapters/protocols.py` is documentation-as-code — the Protocols *are* the spec Phase 3's first adapter implements against; "the Protocol is correct" is testable via Phase 3's exit | The risk that Phase 2 ships a Protocol shape that turns out wrong is real but bounded — the Phase 3 exit criterion includes "the first adapter implements the Phase 2 Protocols *unchanged*" — any drift requires an explicit ADR amendment to 02-ADR-0006 / this ADR |
| `TCCMLoader` is exercised by one Phase 2 consumer (`tests/integration/tccm/test_reference_tccm_roundtrips.py`) loading the reference TCCM — closes the schema-without-consumer gap the critic flagged | The reference TCCM is a deliberately-minimal manifest for an `index-health-self-check` task class; it does not exercise real Phase 3+ workflows; its purpose is to round-trip every field, not to prove the TCCM model is correct under load. Phase 3's first real `tccm.yaml` is the production validation |
| The "what's a plugin vs. what's kernel" boundary is now visibly documented — kernel-side files live under `src/codegenie/{adapters,tccm,skills,conventions,depgraph,indices}/`, plugin-side will live under `plugins/{slug}/{adapters,probes,skills,recipes,subgraph}/` | The directory taxonomy ratchets — Phase 3+ contributors must learn which side a new module belongs to. Mitigation: ADR-0031 §"Plugin directory layout" + this ADR are the canonical references |
| `AdapterConfidence` ships as a placeholder; Phase 3 owns the eventual variant set when the first adapter ships | A Phase 3 author may want to layer `AdapterConfidence` over `IndexFreshness` (e.g., "adapter Degraded because underlying SCIP index is Stale"); Phase 2 does not pre-decide that layering |

## Pattern fit

Pattern: **Phase boundary discipline + documentation-as-code + Protocol-as-contract** (`design-patterns-toolkit.md §"Plugin architecture / Pluggable systems"` failure mode and `§"Anti-patterns to flag explicitly" → Premature pluggability`). The toolkit's failure mode for plugin architecture — "a 'pluggable' design where the kernel still has a hardcoded list of plugin names, or where adding a plugin requires editing a central dispatch table" — applies symmetrically: a pluggable design where the loader exists without any plugin is the inverse anti-pattern. The synthesis picks documentation-as-code via Protocols: Phase 3's first adapter is the proof. Composes with **Open/Closed at the Phase boundary** — Phase 3 adds the loader + first plugin together as new files under `plugins/`, never edits Phase 2's `codegenie/adapters/protocols.py` Protocols (the Protocols are the contract; their consumers extend by addition). The "premature pluggability" anti-pattern the toolkit flags on sight is the load-bearing observation: a Protocol with zero implementations is documentation; a Protocol with a `NullAdapter` fixture validates itself; a Protocol with Phase 3's first real adapter as its exit gate is the synthesis pick.

## Consequences

- Phase 2's source tree contains **no `plugins/` directory**. The `tests/fixtures/plugins/` directory also does not exist (the synthetic plugin fixture proposed by [B] was refused as implying pluggability Phase 3 owns).
- `src/codegenie/adapters/protocols.py` is ~80 LOC of `@runtime_checkable` Protocols. `src/codegenie/adapters/confidence.py` is the `AdapterConfidence` placeholder.
- `src/codegenie/tccm/{loader.py, model.py, queries.py}` ships the `TCCMLoader` + `TCCM` Pydantic model + 5-variant `DerivedQuery`. No Bundle Builder (Phase 8). No plugin-resolution logic.
- `src/codegenie/skills/{loader.py, model.py}` ships `SkillsLoader` over the three-tier search path. Body byte-offset only (progressive disclosure); reuses Phase 1 `safe_yaml.load`.
- `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml` is the in-tree reference manifest; it lives under `docs/` and is loaded by `tests/integration/tccm/test_reference_tccm_roundtrips.py`. Documentation, not infrastructure.
- `tests/integration/adapters/test_phase3_handoff_smoke.py` lands in Phase 2 as **skipped** with `@pytest.mark.skip(reason="enabled when Phase 3 plugin lands")`. The test, when unskipped at Phase 3, MUST import the Phase 2 Protocols *unchanged* and pass against `plugins/vulnerability-remediation--node--npm/adapters/`. Drift requires an ADR amendment to this one and/or 02-ADR-0006.
- Phase 3 ships, **together** (per ADR-0031 §Consequences §1):
  1. The plugin loader (`PluginLoader` + `plugin.yaml` Pydantic parser).
  2. The universal `(*, *, *)` fallback plugin under `plugins/universal--*--*/`.
  3. The first concrete plugin: `plugins/vulnerability-remediation--node--npm/` with `plugin.yaml`, `tccm.yaml`, `probes/`, `adapters/` (implementing all four Phase 2 Protocols), `subgraph/`, `skills/`, `recipes/`.
  4. Supervisor-side plugin resolution (most-specific + `precedence` tiebreak + `extends` walk).
- A Phase 3 attempt to land "loader without first plugin" or "first plugin without loader" fails the Phase 3 exit criterion explicitly.

## Reversibility

**Medium-low.** "Pulling forward" the plugin loader into a Phase 2 patch later (e.g., if Phase 3's first plugin is delayed) is feasible — the loader is a `plugin.yaml` Pydantic parser + a registry walk + a Supervisor dispatch. But the "first plugin doubles as the proof" property is one-way: once you ship the loader without a real plugin, the proof relationship is lost forever, and the universal-fallback-only configuration becomes the de-facto Phase 2 deliverable (with `contributes.adapters: {}` empty). The reverse direction (adopting plugins later) is well-trodden; the forward direction (un-doing premature pluggability) is the structural one-way the toolkit's flag-on-sight list warns against.

## Evidence / sources

- `../final-design.md §"Goals"` (plugin scaffolding shipped is kernel-only)
- `../final-design.md §"Conflict-resolution table" row 1` — plugin loader in Phase 2 resolution
- `../final-design.md §"Components" #7, #8, #9` — Adapter Protocols, `TCCMLoader`, `SkillsLoader` scope
- `../final-design.md §"Patterns considered and deliberately rejected" #1` — explicit refusal
- `../phase-arch-design.md §"Non-goals"` (Plugin Loader, universal fallback, `plugin.yaml` parser, adapter implementations)
- `../phase-arch-design.md §"Component design" #7, #8, #9` — Phase 2 scaffolding details
- `../phase-arch-design.md §"Integration with Phase 3 (next phase)"` — what Phase 3 inherits day-1
- `../phase-arch-design.md §"Gap analysis & improvements" Gap 1` — Phase 3 handoff smoke test (skipped in Phase 2)
- `../critique.md §"Attacks on the performance-first design" #1` — premature pluggability framing
- `../critique.md §"Cross-design observations" §"Which disagreement matters most"` — the dispositive observation
- [Production ADR-0031](../../../production/adrs/0031-plugin-architecture.md) §Consequences §1 — "first plugin doubles as proof"
- [Production ADR-0032](../../../production/adrs/0032-language-search-adapters.md) — adapter contract that the Protocols anticipate
- [Production ADR-0029](../../../production/adrs/0029-task-class-context-manifests.md) — TCCM model that `TCCMLoader` parses
