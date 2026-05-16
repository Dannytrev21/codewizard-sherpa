# Story S4-05 — `DepGraphProbe` consuming `@register_dep_graph_strategy` registry

**Step:** Step 4 — Ship `IndexHealthProbe` (B2) + Layer B structural probes
**Status:** Ready (HARDENED 2026-05-16 — see Validation notes)
**Effort:** M
**Depends on:** S1-10 (`@register_dep_graph_strategy(ecosystem: PackageManager)` decorator-registry on disk at `src/codegenie/depgraph/registry.py`; `PackageManager` is a `Literal[…]` re-exported from `codegenie.types.identifiers` — never redefined), S4-01 (`IndexHealthProbe` registered so this probe's slice can flow through B2 if a depgraph-freshness check is later added — not a hard runtime dep, but ordering rationale in the manifest)
**ADRs honored:** [`02-ADR-0003`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) (`heaviness` defaults to `"light"` — depgraph is fast O(N) graph construction; no `runs_last`), [phase-arch-design.md §"Design patterns applied"](../phase-arch-design.md) row 7 — Open/Closed via `@register_dep_graph_strategy(ecosystem: PackageManager)` (the Phase 3 seam — **zero strategies registered in Phase 2**), Phase 1 ADR-0013 (`PackageManager` Literal source of truth — `bun | pnpm | yarn-classic | yarn-berry | npm`; imported, not redefined), Phase 1 ADR-0004 (sub-schema lands in S4-07), Phase 1 ADR-0007 (warning ID pattern), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) (typed discriminated-union output, no stringly-typed fallback)

## Validation notes (2026-05-16, phase-story-validator)

**Verdict:** HARDENED. The story's intent — exercise the Phase 3 Open/Closed seam (`@register_dep_graph_strategy`) with zero strategies registered while shipping the kernel probe that dispatches through it — is sound and traces cleanly to phase-arch-design §"Component design" #11. But the draft referenced **eight phantom surfaces** the executor's first red-test pass would have crashed against, plus four harden-tier weaknesses in mutation-resistance and consistency with S4-01's already-established sibling-slice pattern. The implementer MUST treat the prescriptions below as overriding the body of the original story when they conflict; the body is left intact only for traceability of the audit. Full audit at [`_validation/S4-05-dep-graph-probe.md`](_validation/S4-05-dep-graph-probe.md).

### Prescribed corrections (override the original ACs / Impl outline / TDD plan on conflict)

1. **`Probe.run` is two-arg** per `src/codegenie/probes/base.py:94`: `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`. All draft references to `run(ctx)`, `DepGraphProbe().run(ctx)`, and tests calling the probe with a single arg are wrong — use two args. (Same phantom-signature S4-03/S4-04 validations caught.)
2. **Registry surface (the only valid spelling).** Real S1-10 surface — `default_dep_graph_registry.has_strategy(eco) -> bool`, `dispatch(eco, ctx, manifests) -> networkx.DiGraph` (raises `DepGraphRegistryError` whose `args[0]` starts with `no_strategy_for_ecosystem: `), `registered_ecosystems() -> frozenset[PackageManager]`, `unregister_for_tests(eco)`. The draft's `registry.get_strategy(pm_enum)`, `iter_strategies()`, `_clear_for_tests()` **do not exist** — substitute the real names throughout.
3. **`PackageManager` is a `Literal[…]`, not an Enum** (Phase 1 ADR-0013; `src/codegenie/probes/node_build_system.py:115`). No `.PNPM` attribute access; no `PackageManager(str)` constructor. Validate strings via `frozenset(get_args(PackageManager))` membership; narrow via `cast(PackageManager, pm_str)`. T-06's `@register_dep_graph_strategy(ecosystem=PackageManager.PNPM)` MUST be `default_dep_graph_registry.register(cast(PackageManager, "pnpm"))`. AC-5's `PackageManager(pm)` raising `ValueError` is wrong — `Literal` is not callable.
4. **`PackageManager` import path** is `from codegenie.types.identifiers import PackageManager` (S1-05 re-export). The draft's `codegenie.probes.layer_a.node_build_system` is phantom — no `layer_a/` directory exists.
5. **`ctx.sibling_slices` is not on `ProbeContext`** (`src/codegenie/probes/base.py:51-62`; Phase 0 ADR-0007 freezes the ABC). S4-01 established the Phase-2 sibling-read pattern as on-disk JSON sidecars under `<output_dir>/raw/`, but `NodeBuildSystemProbe` does not currently write a `node_build_system.json` sidecar. **S4-05 must re-detect `package_manager` inline on `repo.root`**, reusing the priority-1/2 lockfile-precedence logic from `src/codegenie/probes/node_build_system.py`: priority-1 = `package.json#packageManager` field (parsed via `ctx.parsed_manifest`) matching `^bun@`, `^pnpm@`, `^npm@`, `^yarn@1\.`, `^yarn@(2|3|4|\d+)\.`; priority-2 = lockfile presence (`bun.lockb` → bun; `pnpm-lock.yaml` → pnpm; `package-lock.json` → npm; `yarn.lock` + `.yarnrc.yml` or `.yarn/` → yarn-berry, else yarn-classic with `dep_graph.yarn_variant_inferred` warning). The duplication of `_LOCKFILE_PRECEDENCE` is acknowledged (Rule 7) and surfaced as a backlog Note (two follow-up paths: promote to a shared helper module, OR amend Phase 1 to emit `node_build_system.json` sidecar). The validator does NOT auto-pick; the inline-duplication is the surgical default.
6. **`ctx.snapshot.root` is wrong.** `repo: RepoSnapshot` is the first `run()` arg; the attribute is `repo.root`. Fix throughout the Impl outline + tests.
7. **`DepGraphProbeOutput` is shipped at `src/codegenie/depgraph/model.py`** (S1-10) with 3 fields: `graph_path: Path | None`, `confidence: Literal["high","medium","low"]`, `reason: str | None`; frozen + extra=forbid. **Do NOT redefine** in the probe module — fork would create two failure modes (Rule 7). The draft's 6-field model with `ecosystem`/`nodes_count`/`edges_count`/`dep_graph_uri` is wrong: those fields belong in the **slice-dict echo** under `ProbeOutput.schema_slice["dep_graph"]` alongside the typed model's `model_dump`. S4-07's sub-schema (`dep_graph.schema.json`) will pin the slice-dict shape. Optionally land a sub-ADR (`ADRs/0011-dep-graph-probe-output-reason-literal.md`) narrowing `reason: str | None` to a Literal-enumerated discriminator (`Literal["ok", "no_strategy_for_ecosystem", "unrecognized_package_manager", "upstream_build_system_unavailable", "strategy_timeout", "package_manager_field_unparseable"] | None`) — this is a **strict superset** of the current free-form `str`; every S1-10 GREEN test continues to pass. Implementer choice.
8. **Strategy invocation signature.** `DepGraphStrategy = Callable[[ProbeContext, list[Mapping[str, Any]]], networkx.DiGraph]` per S1-10 (`src/codegenie/depgraph/registry.py:60`) — **positional `(ctx, manifests)`**, sync, returns the exact `networkx.DiGraph` (identity-preserving — S1-10 AC-11). The draft's `strategy.build(snapshot=..., manifests=..., build_system=...)` is wrong on every dimension (method call vs Callable; kwargs vs positional; extra `build_system` parameter). Invoke via `default_dep_graph_registry.dispatch(pm, ctx, manifests)`.
9. **Async wrapper.** The strategy is sync. `await wait_for(default_dep_graph_registry.dispatch(...))` would not bound CPU. Use: `graph = await asyncio.wait_for(asyncio.to_thread(default_dep_graph_registry.dispatch, pm, ctx, manifests), timeout=self.timeout_seconds)`. T-13's timeout assertion requires this mechanism; a naïve `wait_for` would fail to interrupt the strategy.
10. **`manifests` construction.** Pure helper `_construct_manifests(repo_root, parsed_manifest) -> list[Mapping[str, Any]]` enumerates detected manifest paths (`package.json` + `pnpm-workspace.yaml`) and calls `ctx.parsed_manifest(p)` for each, filtering `None`. The probe MUST pass real parsed manifests to the strategy — a probe that passed `[]` would silently break Phase 3 adapters.
11. **`_WARNING_IDS` set MUST include** `dep_graph.upstream_build_system_unavailable`, `dep_graph.unrecognized_package_manager`, `dep_graph.strategy_timeout`, `dep_graph.package_manager_field_unparseable`, `dep_graph.yarn_variant_inferred`, `dep_graph.no_manifest_detected`. Import-time validation uses `raise AssertionError(...)` (S4-01 precedent — not bare `assert`, which `-O` would strip).
12. **T-10 AST assertion** must be (a) "import source is exactly `codegenie.types.identifiers`" and (b) "no module-level reassignment / TypeAlias redefinition of `PackageManager`." The draft's "no `class PackageManager`" is wrong-shaped for a Literal alias.
13. **`requires=[]`** — the probe re-detects `package_manager` inline, so no topological dependency on `node_build_system`. Mirrors S4-01's stance ("reads sibling artifacts but does not topologically require them").
14. **`networkx>=3.4`** belongs in `[project.dependencies]` per Phase 0 ADR-0006 (S4-04 hardening precedent). Do NOT add to `[project.optional-dependencies] gather` (which is intentionally empty).
15. **Deterministic JSON serialization.** `raw/dep-graph.json` is written via `json.dumps(networkx.node_link_data(graph, edges="edges"), sort_keys=True, indent=2).encode("utf-8")` then `Path.write_bytes`. Both reruns and across-version output must be byte-identical (T-15) — Phase 3 cache stability depends on it.
16. **Pure-helper / imperative-shell split** (mirrors S4-01). Module-level pure functions: `_detect_package_manager`, `_construct_manifests`, `_serialize_graph`, `_empty_graph_json`, `_emit_low_confidence`, `_emit_high_confidence`. `run()` is the only impure code — composes the helpers and calls `Path.write_bytes` + `asyncio.to_thread + wait_for`.
17. **Mutation-resistance additions to the TDD plan:** (a) T-06 captures `(ctx, manifests)` actuals via a sentinel dict and asserts `captured["ctx"] is ctx` plus manifest list-identity; (b) T-09 asserts `set(DepGraphProbeOutput.model_fields) == {"graph_path", "confidence", "reason"}` to pin single-source-of-truth on the shipped model; (c) T-14 splits yarn-classic vs yarn-berry detection; (d) T-15 asserts byte-identical reruns; (e) T-12 adds a Python negative-control to `for_task`.
18. **Do NOT introduce a kernel `KernelRegistry[K, V]` abstraction.** Three sibling registries (`probes/registry.py`, `indices/registry.py`, `depgraph/registry.py`) reach rule-of-three with S1-10, but the three dispatch shapes diverge non-trivially (`for_task` filter, `dispatch_all` total, single-`dispatch(key)`) — S1-10's validation deliberately deferred the kernel-extract per Rule 2. Honor the deferral; consume `default_dep_graph_registry` as-is.

### Notes on parallelism vs in-process synthesis

This validation ran as an in-process synthesis rather than four parallel critic subagents — the main pass had already loaded the relevant 1000+ lines of arch design + ADRs + sibling stories. Spawning four parallel critics would have re-read the same context, exceeding the token budget without adding signal. The four critic lenses (coverage, test-quality, consistency, design-patterns) were applied serially; findings carry the same severity tagging the parallel form would have produced. See `_validation/S4-05-dep-graph-probe.md` for the full audit.

## Context

`DepGraphProbe` builds a `networkx.DiGraph` of the repo's internal package dependencies (monorepo modules + cross-references). Ecosystem-specific resolution — "given pnpm-workspaces, compute the cross-package edges" — lives in **Phase 3** plugin adapters; Phase 2 ships the **kernel skeleton + strategy registry seam**.

[Phase-arch-design.md §"Component design" #11](../phase-arch-design.md) and [final-design §"Components"](../final-design.md) are emphatic: **zero strategies are registered in Phase 2.** The `@register_dep_graph_strategy` decorator-registry (planted in S1-10 at `src/codegenie/depgraph/registry.py`) is the Open/Closed seam Phase 3 fills with `build_npm`, `build_pnpm`, `build_yarn`, `build_bun` in `plugins/vulnerability-remediation--node--npm/adapters/dep_graph_npm.py` and friends. This story exercises the registry *path* — confirms the dispatch is wired, asserts the unknown-ecosystem fallback emits typed `DepGraphProbeOutput(confidence="low", reason="no_strategy_for_ecosystem")` — but does NOT register any strategy. Adding Maven (Phase 8+) is a new file + new decorator + an ADR amendment to Phase 1 ADR-0013 (to extend the `PackageManager` enum); never an edit to `DepGraphProbe`.

The probe reads Phase 1's already-parsed `manifests` and `build_system` slices (via the coordinator-provided slice map; same shape B2 uses). It does NOT re-parse `package.json`/`pnpm-workspace.yaml` — Phase 1's parser closure (S1-02/S1-03/S1-04) already did that work. The Phase-2 probe's job is to dispatch to the registered strategy for the detected `package_manager`, OR emit the typed low-confidence fallback.

The slice is intentionally minimal in Phase 2 — `dep_graph_uri` (relative path to `raw/dep-graph.json` artifact), `nodes_count`, `edges_count`, `ecosystem` (from `build_system.package_manager`), `confidence`. The artifact `raw/dep-graph.json` is empty (`{"schema_version": 1, "nodes": [], "edges": []}`) in Phase 2 since no strategy emits edges. Phase 3 adapter populates it. A test in this story exercises the registry with a **mock strategy** that emits a fake graph — this is the only place in Phase 2 where the strategy path is exercised end-to-end (and the mock is test-only, not registered in production).

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §"Component design" #11`](../phase-arch-design.md) — full internal structure; the registry dispatch.
  - [`../phase-arch-design.md §"Design patterns applied"`](../phase-arch-design.md) row 7 — Open/Closed via `@register_dep_graph_strategy`.
  - [`../phase-arch-design.md §"Conflict-resolution table" row 2 / §"Components" #13`](../phase-arch-design.md) — the registry-decorator pattern symmetry with `@register_probe` and `@register_index_freshness_check`.
  - [`../phase-arch-design.md §"Logical view"`](../phase-arch-design.md) — `DepGraphProbe` class card showing dispatch to `DepGraphStrategy`.
- **Phase 1 ADRs:**
  - [`docs/phases/01-context-gather-layer-a-node/ADRs/0013-package-manager-enum-split.md`](../../01-context-gather-layer-a-node/ADRs/0013-package-manager-enum-split.md) (or equivalent — the `yarn` → `yarn-classic`/`yarn-berry` split; `PackageManager` is the enum to consume).
- **Source design:**
  - [`docs/localv2.md §5.2 B5`](../../../localv2.md) — `BuildGraphProbe` shape (depgraph is the structural cousin); workspace-level metadata.
- **Existing code:**
  - `src/codegenie/depgraph/registry.py` (from S1-10) — `@register_dep_graph_strategy` decorator + `iter_strategies()` / `get_strategy(pm)` accessors.
  - `src/codegenie/depgraph/model.py` (from S1-10) — `DepGraphStrategy` Protocol and any shared types.
  - `src/codegenie/probes/base.py` (frozen).
  - Phase 1 `NodeBuildSystemProbe` slice (`build_system.package_manager: str | None`) — read via the coordinator slice map.

## Goal

Running `codegenie gather` against any Phase-1-detected Node repo (pnpm, npm, yarn-classic, yarn-berry, bun, or unknown) produces a `dep_graph` slice. With zero strategies registered (the Phase 2 reality), every analyzed repo gets `DepGraphProbeOutput(confidence="low", reason="no_strategy_for_ecosystem")`. The probe emits the typed low-confidence slice WITHOUT raising. With a mock strategy registered at test time, the probe dispatches to it, receives a `networkx.DiGraph` (or equivalent), serializes to `raw/dep-graph.json`, and emits `confidence="high"`. The registry dispatch is the load-bearing Open/Closed test (T-04, T-05).

## Acceptance criteria

- [ ] **AC-1 — Probe contract attributes.** `src/codegenie/probes/layer_b/dep_graph.py` defines `class DepGraphProbe(Probe)` with `list[str]` class attributes: `name="dep_graph"`, `version="0.1.0"`, `layer="B"`, `tier="base"`, `applies_to_languages=["javascript","typescript"]`, `applies_to_tasks=["*"]`, `requires=["node_build_system"]`, `timeout_seconds=60`. `declared_inputs` includes `["package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "pnpm-workspace.yaml"]` PLUS the special token `dep_graph_strategy_set:<resolved>` where `<resolved>` is the sorted comma-joined list of `PackageManager` enum members that have a registered strategy (computed at probe init via `iter_strategies()`). Cache-key sensitivity: a Phase-3 PR registering a new strategy changes `<resolved>` and invalidates caches AS EXPECTED. The decorator is `@register_probe` (no kwargs — defaults to `heaviness="light", runs_last=False`).

- [ ] **AC-2 — Reads the `build_system` slice; no re-parsing.** The probe reads `ctx.sibling_slices["build_system"]["package_manager"]` (the result of S2-02's `NodeBuildSystemProbe`). It does NOT call any parser directly — `safe_json`, `safe_yaml`, `jsonc`, `pyarn` are all forbidden by the AST-walk discipline (T-03). If `ctx.sibling_slices.get("build_system")` is `None` (Phase 1 probe failed or did not run), the probe emits `confidence="low"`, `warnings=["dep_graph.upstream_build_system_unavailable"]`, and an empty slice — does NOT raise.

- [ ] **AC-3 — Strategy registry dispatch.** Given `pm = ctx.sibling_slices["build_system"]["package_manager"]` (a string like `"pnpm"` or `"yarn-classic"`), the probe:
  1. Parses the string to a `PackageManager` enum member via `PackageManager(pm)` (will raise `ValueError` if the string is unknown — caught and mapped to AC-5).
  2. Calls `registry.get_strategy(pm_enum)` — returns `None` if no strategy is registered.
  3. If `None`: emits the typed fallback per AC-4 — this is the **Phase-2 default path**.
  4. If a strategy: invokes `strategy.build(snapshot=ctx.snapshot, manifests=ctx.sibling_slices.get("manifests"), build_system=ctx.sibling_slices["build_system"]) -> networkx.DiGraph` (or returns a typed `DepGraphProbeOutput`-shaped object — the precise return type is on the `DepGraphStrategy` Protocol defined in S1-10; this story's job is to invoke and serialize, not redesign the Protocol). Serializes the graph to `raw/dep-graph.json`; emits `confidence="high"`, `nodes_count`, `edges_count`, `dep_graph_uri`.

- [ ] **AC-4 — Unknown ecosystem → typed low-confidence fallback (Phase 2 default).** When `registry.get_strategy(pm_enum)` returns `None`, the slice is:
  ```yaml
  dep_graph:
    ecosystem: "pnpm"               # echoes the detected package_manager
    confidence: low
    reason: no_strategy_for_ecosystem
    nodes_count: 0
    edges_count: 0
    dep_graph_uri: ".codegenie/context/raw/dep-graph.json"
  ```
  The `raw/dep-graph.json` artifact is written with `{"schema_version": 1, "ecosystem": "pnpm", "nodes": [], "edges": []}` — a valid, empty graph that Phase 3 plugins can read uniformly (don't force consumers to handle "file absent" AND "file empty" as two separate paths). T-04 asserts this fallback for every `PackageManager` enum member.

- [ ] **AC-5 — Unparseable `package_manager` string → typed low-confidence.** If `PackageManager(pm)` raises `ValueError` (e.g., Phase 1 emitted `package_manager: "deno"` from a future detection path, but the enum doesn't include it yet), the probe catches and emits `confidence="low"`, `reason: "unrecognized_package_manager"`, `warnings=["dep_graph.unrecognized_package_manager"]`, `ecosystem=pm` (echo verbatim). No `ValueError` escapes. T-05 exercises this.

- [ ] **AC-6 — `dep_graph` slice shape (Pydantic-validated typed output).** A Pydantic model `DepGraphProbeOutput` in `src/codegenie/probes/layer_b/dep_graph.py` (or `codegenie/depgraph/model.py` if S1-10 lands it there — implementer choice; if S1-10 owns the Protocol, the output model can live alongside the probe):
  ```python
  class DepGraphProbeOutput(BaseModel, frozen=True, extra="forbid"):
      ecosystem: str | None       # echoes detected package_manager; None on AC-2 path
      confidence: Literal["high", "medium", "low"]
      reason: Literal["ok", "no_strategy_for_ecosystem", "unrecognized_package_manager",
                      "upstream_build_system_unavailable"] | None = None
      nodes_count: int = 0
      edges_count: int = 0
      dep_graph_uri: str = ".codegenie/context/raw/dep-graph.json"
  ```
  The discriminator is `reason` for the failure shapes; `confidence="high"` requires `reason=None` or `reason="ok"` (implementer picks one and documents — recommend `None` for clean shape). The output is serialized to the slice via `model_dump(mode="json")`.

- [ ] **AC-7 — Mock strategy round-trip (the Open/Closed exercise).** A test (T-06) registers a mock strategy:
  ```python
  @register_dep_graph_strategy(ecosystem=PackageManager.PNPM)
  def _mock_pnpm(snapshot, manifests, build_system):
      g = networkx.DiGraph()
      g.add_edge("payments-api", "shared-models")
      g.add_edge("payments-api", "payments-core")
      return g
  ```
  invokes the probe against a fixture with `build_system.package_manager == "pnpm"`, asserts the slice has `nodes_count=3`, `edges_count=2`, `confidence="high"`, AND `raw/dep-graph.json` is well-formed (parseable as `{"schema_version": 1, "ecosystem": "pnpm", "nodes": [...], "edges": [...]}`). The mock is unregistered in test teardown (uses `_clear_for_tests()` helper from S1-10). **This is the only place in Phase 2 where the strategy path is exercised end-to-end** — proves the seam works before Phase 3 fills it.

- [ ] **AC-8 — Per-PackageManager-variant parametrization.** T-04 parametrizes over **every** `PackageManager` enum member (`bun`, `pnpm`, `yarn-classic`, `yarn-berry`, `npm`); for each, asserts the no-strategy-fallback emits the typed low-confidence output. **A future contributor adding a new `PackageManager` variant in Phase 1 ADR-0013 (or amendment) will see this parametrize generate a failing test** — the test enumerates `PackageManager.__members__` at collection time, so a forgotten ADR-amend on the enum becomes visible (this is the kind of structural test the manifest's risk callout for S2-02a illustrated: registry dispatch is total over the enum).

- [ ] **AC-9 — `raw/dep-graph.json` schema_version + path.** The artifact is JSON-serialized from `networkx.DiGraph` via `networkx.node_link_data(g)` (NetworkX's standard JSON shape — Phase 3's `DepGraphAdapter` reads `nodes` + `links`/`edges` directly). Top-level: `{"schema_version": 1, "ecosystem": <pm_str>, "nodes": [...], "edges": [...]}` (the wrapper adds `schema_version` and `ecosystem` around NetworkX's native shape so Phase 3 can dispatch on `ecosystem` without re-reading the slice). Path is `<snapshot.root>/.codegenie/context/raw/dep-graph.json` (mirrors S4-03's blob path convention).

- [ ] **AC-10 — `networkx` is a Phase-0 dep (already on disk).** A unit test asserts `import networkx` succeeds; no new entry in `pyproject.toml`. If networkx is NOT already a Phase 0 dep (verify against Phase 0 ADR — likely is, per the localv2 spec mentioning `networkx.DiGraph`), add to the `gather` extras with a documented entry. **Do NOT add it speculatively — if it's already there, skip this AC.**

- [ ] **AC-11 — Warning + error ID frozenset + import-time assertion.** All warning IDs (`dep_graph.upstream_build_system_unavailable`, `dep_graph.unrecognized_package_manager`) declared in `_WARNING_IDS: frozenset[str]`. Import-time assert verifies ADR-0007 regex.

- [ ] **AC-12 — Registry membership + `for_task` filter.** `src/codegenie/probes/__init__.py` imports `DepGraphProbe` via additive import. `default_registry.all_probes()` includes it. `for_task("*", frozenset({"typescript"}))` and `for_task("*", frozenset({"javascript"}))` include it.

- [ ] **AC-13 — Zero strategies registered in production.** A unit test (`test_no_strategies_registered_in_phase_2`) asserts that after a clean import of `src/codegenie/probes/__init__.py` (forcing all module-level decorator runs), `iter_strategies()` returns an **empty** iterator. **A Phase 3 PR will register strategies; this test will fail and be deleted in that PR** — that's the explicit narrative gate for Phase 3 ([phase-arch-design.md §"Path to production end state"](../phase-arch-design.md)).

- [ ] **AC-14 — Tooling green.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/probes/layer_b/dep_graph.py`, `pytest tests/unit/probes/layer_b/test_dep_graph.py`. All green.

## Implementation outline

1. **Create `src/codegenie/probes/layer_b/dep_graph.py`** with class per AC-1.

2. **Module-level constants.** `_WARNING_IDS` (AC-11), `_ID_PATTERN` regex, import-time assertion.

3. **`async def run(self, ctx) -> ProbeOutput`** — the dispatcher (~50 LOC):
   ```python
   build_system_slice = ctx.sibling_slices.get("build_system")
   if build_system_slice is None:
       return _emit_upstream_unavailable()

   pm_str = build_system_slice.get("package_manager")
   if pm_str is None:
       return _emit_upstream_unavailable()   # absent field → treat as unavailable

   try:
       pm_enum = PackageManager(pm_str)
   except ValueError:
       return _emit_unrecognized(pm_str)

   strategy = registry.get_strategy(pm_enum)
   if strategy is None:
       _write_empty_graph(ctx.snapshot.root, pm_str)
       return _emit_no_strategy(pm_str)

   try:
       graph = await asyncio.wait_for(_invoke_strategy(strategy, ctx), timeout=self.timeout_seconds)
   except asyncio.TimeoutError:
       return _emit_strategy_timeout(pm_str)

   _serialize_graph(ctx.snapshot.root, pm_str, graph)
   return _emit_ok(pm_str, graph)
   ```

4. **`_invoke_strategy(strategy, ctx) -> networkx.DiGraph`.** Calls the strategy's `build` (or `__call__` — the Protocol shape lives in S1-10). May be sync or async; the wrapper coerces. Returns a `DiGraph`.

5. **`_serialize_graph(root, ecosystem, graph)`.** Wraps `networkx.node_link_data(graph)` with `{"schema_version": 1, "ecosystem": ecosystem, ...}`; writes to `raw/dep-graph.json` via `Path.write_text(json.dumps(...))`.

6. **`_write_empty_graph(root, ecosystem)`.** Writes the empty-but-well-formed `{"schema_version": 1, "ecosystem": ecosystem, "nodes": [], "edges": []}` for the no-strategy path (AC-4).

7. **`_emit_*` builders** — one per failure mode; each returns a `ProbeOutput` with the typed `DepGraphProbeOutput` serialized into the slice.

8. **Register the probe** via `src/codegenie/probes/__init__.py` additive import.

## TDD plan — red / green / refactor

### Test helpers preamble

```python
# tests/unit/probes/layer_b/test_dep_graph.py
from __future__ import annotations
import asyncio, ast, json
from pathlib import Path
import pytest
import networkx
from codegenie.depgraph.registry import register_dep_graph_strategy, iter_strategies, _clear_for_tests
from codegenie.probes.layer_a.node_build_system import PackageManager  # ADR-0013 source
from codegenie.probes.layer_b.dep_graph import DepGraphProbe, DepGraphProbeOutput

@pytest.fixture
def clean_dep_graph_registry():
    _clear_for_tests()
    yield
    _clear_for_tests()
```

### RED

- **T-01** `test_probe_contract_attributes` — AC-1.
- **T-02** `test_no_parser_imports` — AC-2; AST-walk module; assert no import of `safe_json`/`safe_yaml`/`jsonc`/`pyarn` directly (the probe consumes Phase 1's parsed output, not the parsers).
- **T-03** `test_upstream_build_system_missing_emits_low_confidence` (AC-2): `ctx.sibling_slices = {}` (no build_system); assert `confidence="low"`, `warnings == ["dep_graph.upstream_build_system_unavailable"]`; no exception escapes.
- **T-04** `test_no_strategy_registered_per_package_manager_variant` (AC-4, AC-8): parametrize over every `PackageManager.__members__` value; sibling slice `build_system.package_manager` set per variant; assert `confidence="low"`, `reason="no_strategy_for_ecosystem"`, `ecosystem=<variant_value>`, `raw/dep-graph.json` is well-formed empty graph.
- **T-05** `test_unparseable_package_manager_emits_typed_warning` (AC-5): sibling slice `build_system.package_manager = "deno"` (not in enum); assert `confidence="low"`, `reason="unrecognized_package_manager"`, `warnings == ["dep_graph.unrecognized_package_manager"]`.
- **T-06** `test_mock_strategy_round_trip` (AC-7, the Open/Closed exercise):
  ```python
  def test_mock_strategy_round_trip(tmp_path, clean_dep_graph_registry):
      @register_dep_graph_strategy(ecosystem=PackageManager.PNPM)
      def _mock_pnpm(snapshot, manifests, build_system):
          g = networkx.DiGraph()
          g.add_edge("payments-api", "shared-models")
          g.add_edge("payments-api", "payments-core")
          return g
      ctx = build_probe_context(snapshot_root=tmp_path,
                                sibling_slices={"build_system": {"package_manager": "pnpm"}})
      out = asyncio.run(DepGraphProbe().run(ctx))
      assert out.schema_slice["dep_graph"]["nodes_count"] == 3
      assert out.schema_slice["dep_graph"]["edges_count"] == 2
      assert out.schema_slice["dep_graph"]["confidence"] == "high"
      raw = json.loads((tmp_path / ".codegenie/context/raw/dep-graph.json").read_text())
      assert raw["schema_version"] == 1
      assert raw["ecosystem"] == "pnpm"
      assert {"payments-api", "shared-models", "payments-core"} == {n["id"] for n in raw["nodes"]}
  ```
- **T-07** `test_no_strategies_registered_in_phase_2` (AC-13): force-import `codegenie.probes.__init__`; assert `list(iter_strategies()) == []`. **This test fails in Phase 3** — that's the explicit gate; delete on the Phase-3 PR.
- **T-08** `test_raw_dep_graph_json_well_formed_on_no_strategy` (AC-4, AC-9): no strategy registered; sibling slice has `package_manager="npm"`; run probe; assert `raw/dep-graph.json` exists AND is `{"schema_version": 1, "ecosystem": "npm", "nodes": [], "edges": []}`.
- **T-09** `test_dep_graph_probe_output_model_strict` (AC-6): construct `DepGraphProbeOutput(extra_field="x")` raises `pydantic.ValidationError` (`extra="forbid"`); `model_dump_json` → `model_validate_json` round-trips identity-equal.
- **T-10** `test_package_manager_enum_imported_not_redefined` (Phase 1 ADR-0013): AST-walk the module; assert `PackageManager` is imported from `codegenie.probes.layer_a.node_build_system` (or wherever Phase 1 places it); assert no class definition named `PackageManager` in this module.
- **T-11** `test_warning_ids_match_adr_0007` (AC-11).
- **T-12** `test_registry_membership_and_for_task_filter` (AC-12).
- **T-13** `test_strategy_timeout_path` (AC-3 timeout arm): register a mock strategy that `await asyncio.sleep(10)`; `timeout_seconds=1`; assert `confidence="low"`, `warnings` contains `"dep_graph.strategy_timeout"` (add this ID to `_WARNING_IDS` if not present).

### GREEN

Implement per outline. Confirm `networkx` is on disk (Phase 0). Implement `_serialize_graph` using `networkx.node_link_data(graph, edges="edges")` — NetworkX's modern API uses `edges` key (older versions used `links`); pin to a version where `edges` is standard.

### REFACTOR

- Extract `_emit_*` builders to module-level pure functions; each returns `ProbeOutput`.
- Consider extracting `DepGraphProbeOutput` to `src/codegenie/depgraph/model.py` if S1-10 lands the Protocol there — co-locate output model with strategy contract.
- Confirm `mypy --strict` passes; `networkx` may need `# type: ignore[import-untyped]` (Rule 12 — loud, with a TODO).

## Files to touch

**Create:**
- `src/codegenie/probes/layer_b/dep_graph.py`
- `tests/unit/probes/layer_b/test_dep_graph.py`

**Edit (additive):**
- `src/codegenie/probes/__init__.py` — additive import.

**Possibly edit (S1-10 may have already landed these):**
- `src/codegenie/depgraph/model.py` — `DepGraphProbeOutput` Pydantic model (if it doesn't belong with the Protocol).

## Out of scope

- **Any concrete depgraph strategy.** Phase 3 plugin (`vulnerability-remediation--node--npm/adapters/dep_graph_npm.py`) ships `build_npm`, `build_pnpm`, etc. **Zero strategies in Phase 2** — AC-13 is the explicit gate.
- **Reverse / consumer queries.** `DepGraphAdapter.consumers(pkg)` / `producers(pkg)` is Phase 3. Phase 2 emits the graph; the adapter queries it.
- **Cross-language depgraphs.** Phase 2 is Node-only via the existing Phase 1 `PackageManager` enum. Phase 8+ adds Maven (ADR-amend on the enum).
- **Workspace-level metadata** (per `localv2.md §5.2 B5` `BuildGraphProbe` shape — that's a separate Phase 2 probe per the localv2 spec; this Phase-2 plan synthesizes "BuildGraphProbe" into the `DepGraphProbe` here because the design treats them as the same concern — see [phase-arch-design.md §"Component design" #11](../phase-arch-design.md)). The minimal Phase 2 slice is `ecosystem + nodes_count + edges_count + uri + confidence`.
- **Sub-schema for `dep_graph`.** S4-07 lands the sub-schema.
- **Reverse-index in the artifact.** Phase 3's `DepGraphAdapter` builds reverse adjacency. Forward only here.

## Notes for the implementer

- **Zero strategies is the load-bearing test.** AC-13 / T-07 will look like a useless test today (`list(iter_strategies()) == []` is trivially true) — but it is the structural gate that makes the Phase 3 transition observable. When Phase 3 lands and registers the first strategy, T-07 fails, which is the loud "Phase 3 is making the transition" signal. That PR deletes T-07 and adds new tests for the concrete strategies. Document this in the test docstring and in the Phase 3 plan's "tests to remove" list.
- **Don't redefine `PackageManager`.** [Phase 1 ADR-0013](../../01-context-gather-layer-a-node/ADRs/) is the source of truth. T-10 enforces. A second enum would create two failure modes ("Phase 1 says pnpm, Phase 2 says PNPM") that Rule 7 forbids.
- **Mock strategy in tests is test-only.** T-06 registers a mock via `@register_dep_graph_strategy(ecosystem=PackageManager.PNPM)`, but the registration happens inside the test function scope AND `_clear_for_tests()` runs in teardown (the fixture handles this). The mock is NEVER visible to production gather. A future contributor who runs the test suite and sees `iter_strategies()` return entries is looking at test pollution — `_clear_for_tests` is the discipline.
- **NetworkX is a heavy dep but Phase 0 already accepts it.** [localv2.md](../../../localv2.md) mentions `networkx.DiGraph`; the Phase 0 baseline tracks this. If networkx is NOT on disk after Phase 0/1, AC-10 needs ADR amendment — surface that conflict (Rule 7) before adding it.
- **Why not parse manifests directly?** [phase-arch-design.md §"Component design" #11](../phase-arch-design.md) — "Reads Layer A's `manifests` and `build_system` slices." The Phase 1 parsers already did the work; re-parsing would duplicate the parse-and-cap discipline of Phase 1 ADR-0008 / ADR-0009 — Rule 3 (surgical changes) forbids that drift.
- **`asyncio.wait_for` on strategy invocation.** The strategy itself is owned by Phase 3 and may be CPU-bound. Wrapping in `wait_for` means a runaway strategy can't hang the gather; the probe's `timeout_seconds=60` is the upper bound. T-13 verifies the timeout path emits a typed slice rather than propagating.
- **Empty-graph artifact is intentional.** AC-4's `raw/dep-graph.json` containing an empty graph is "valid empty," not "file absent." Phase 3 consumers can read it uniformly (one parse path, not "file absent → empty list" branching). This is a small Rule 2 (simplicity for the consumer) win — the producer pays slightly more (one `write_text` call), but every downstream avoids a branch.
- **Rule 9 — tests verify intent.** T-04 (per-variant parametrize) encodes the WHY of the registry — dispatch is total over the enum. T-06 (mock strategy round-trip) encodes the WHY of the Open/Closed seam — adding a strategy is one new file + one decorator; the probe body never changes. T-07 (zero strategies in Phase 2) encodes the WHY of the Phase-3 boundary — the test failing is the signal of the transition.
