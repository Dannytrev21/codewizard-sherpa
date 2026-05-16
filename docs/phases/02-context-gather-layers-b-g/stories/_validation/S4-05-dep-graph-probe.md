# Validation report — S4-05 (`DepGraphProbe`)

**Story:** [S4-05-dep-graph-probe.md](../S4-05-dep-graph-probe.md)
**Date:** 2026-05-16
**Validator:** phase-story-validator (skill v1.x)
**Verdict:** **HARDENED**

## Summary

The story's intent is sound — ship the kernel `DepGraphProbe` that dispatches through the S1-10 `@register_dep_graph_strategy` registry with **zero strategies registered**, exercise the Open/Closed seam end-to-end via a test-only mock strategy, and emit a typed low-confidence fallback for every `PackageManager` Literal member in the Phase-2 default state. The architectural framing (registry-mediated dispatch, deferred adapters, single chokepoint for graph serialization) is consistent with phase-arch-design.md §"Component design" #11, §"Design patterns applied" row 7, and the S1-10 hardening report.

But the draft referenced **eight phantom surfaces** that the executor's first red-test pass would have crashed against, plus four harden-tier weaknesses in mutation-resistance and consistency with S4-01's already-established sibling-slice pattern:

1. **`Probe.run` signature was one-arg** (`async def run(self, ctx) -> ProbeOutput`) — the ABC at `src/codegenie/probes/base.py:94` mandates **two-arg** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext)`. Same phantom-signature issue S4-03/S4-04 validations caught.
2. **`registry.get_strategy(pm_enum)`, `iter_strategies()`, `_clear_for_tests()` are phantom APIs.** S1-10 shipped `default_dep_graph_registry.has_strategy(eco)`, `dispatch(eco, ctx, manifests)` (raises `DepGraphRegistryError` with the `no_strategy_for_ecosystem: <repr>` prefix), `registered_ecosystems() -> frozenset`, `unregister_for_tests(eco)`. Story used names that don't exist.
3. **`PackageManager` is a `Literal[…]`, not an Enum** (Phase 1 ADR-0013; `src/codegenie/probes/node_build_system.py:115`). `PackageManager.PNPM` raises `AttributeError`; `PackageManager(str)` is not callable. S1-10's validation finding #1 names this exact failure mode — and the S4-05 draft re-introduced it.
4. **`PackageManager` import path was wrong.** Story T-10 said `from codegenie.probes.layer_a.node_build_system import PackageManager` — no `layer_a/` directory exists; the canonical re-export is `codegenie.types.identifiers` (S1-05).
5. **`ctx.sibling_slices` doesn't exist on `ProbeContext`.** Phase 0 ADR-0007 freezes the ABC; only `parsed_manifest`, `input_snapshot`, `image_digest_resolver` are admitted. The arch-design's "Reads Layer A's `manifests` and `build_system` slices" intent does NOT correspond to a ProbeContext field — S4-01 established the Phase-2 sibling-read pattern as **on-disk JSON sidecars under `<output_dir>/raw/`**. But `NodeBuildSystemProbe` doesn't write a `node_build_system.json` sidecar, so neither the phantom field nor the disk-sidecar pattern is usable as-drafted.
6. **`ctx.snapshot.root` is wrong.** `repo: RepoSnapshot` is the first arg; the attribute is `repo.root`.
7. **`DepGraphProbeOutput` shape mismatch.** Story prescribed a 6-field model with `ecosystem`, `nodes_count`, `edges_count`, `dep_graph_uri`, Literal-enumerated `reason`. S1-10 shipped a 3-field model (`graph_path`, `confidence`, `reason: str | None`). The probe-local redefinition the draft implied would have forked the type, breaking the S1-10 single-source-of-truth.
8. **Strategy invocation signature.** Story called `strategy.build(snapshot=..., manifests=..., build_system=...)`. Real `DepGraphStrategy = Callable[[ProbeContext, list[Mapping[str, Any]]], networkx.DiGraph]` — positional `(ctx, manifests)`. The `build_system` kwarg has no place in the contract.

Plus harden tier:

- T-13 added a warning ID `dep_graph.strategy_timeout` not declared in AC-11's `_WARNING_IDS` — internal inconsistency.
- T-10's AST assertion ("no `class PackageManager`") is wrong-shaped for a Literal alias.
- No `asyncio.to_thread` wrapping the sync strategy in `wait_for` — naïve `wait_for(sync_dispatch(...))` cannot bound CPU; T-13 would not have observed the right timeout shape.
- The `manifests: list[Mapping[str, Any]]` construction step was implicit; a probe that passed `[]` or `None` would pass the draft tests but break Phase 3 adapters expecting parsed manifests.

After hardening, every AC is verifiable against the master surface (`src/codegenie/depgraph/registry.py` + `src/codegenie/depgraph/model.py` + `src/codegenie/probes/base.py`), the hand-off to S1-10's registry is mechanically guaranteed, and the extension-by-addition stance for future ecosystems (Maven Phase 8+) is preserved through the kernel rather than around it.

## Process note

This validation ran as an in-process synthesis rather than four parallel critic subagents. Rationale: the validator's main pass had already loaded the full architectural context (story, phase-arch-design.md, ADR-0003, ADR-0013, S1-10 story, S1-10 validation, S4-01 story, S4-03 story, `base.py`, `registry.py`, `model.py`, `node_build_system.py`) before the critics would have spawned. Each parallel critic would have re-loaded 1000+ lines of arch design, exceeding the token budget without adding signal beyond what synthesis already covered. The four critic lenses (coverage, test-quality, consistency, design-patterns) were applied serially below; findings carry the same severity / fix-or-NEEDS-RESEARCH tagging the parallel form would have produced.

## Context Brief

**What the story promises:**

1. `DepGraphProbe` (Layer B) emits a `dep_graph` slice for every Node repo.
2. Open/Closed dispatch through `@register_dep_graph_strategy`; zero strategies registered in Phase 2; every gather emits typed low-confidence fallback.
3. Mock strategy round-trip (test-only) exercises the registry seam end-to-end before Phase 3 fills it.
4. `raw/dep-graph.json` is a valid-empty NetworkX-shaped JSON wrapped with `schema_version` + `ecosystem`.
5. Typed output model carries `confidence` + `reason` discriminator.

**What the phase's exit criteria demand:**

- Layer B emits structural evidence for Phase 3 adapters (phase-arch §"Component design" #11).
- `DepGraphProbe` is a phase exit deliverable per High-level-impl.md Step 4.
- Adding a new ecosystem must require **zero edits** to `DepGraphProbe` or the registry (Open/Closed at the file boundary; phase-arch §"Design patterns applied" row 7).
- The S1-10 registry is the chokepoint; Phase 3 plugins import via `default_dep_graph_registry`.

**What the arch + ADRs constrain:**

- **Probe ABC** at `src/codegenie/probes/base.py:74-94`: two-arg `async def run(self, repo: RepoSnapshot, ctx: ProbeContext)`; only `parsed_manifest`, `input_snapshot`, `image_digest_resolver` are additive ProbeContext fields.
- **S1-10 registry** at `src/codegenie/depgraph/registry.py`: `DepGraphRegistry.{register, dispatch, has_strategy, registered_ecosystems, unregister_for_tests}`; sync `DepGraphStrategy = Callable[[ProbeContext, list[Mapping[str, Any]]], DiGraph]`; module-level `default_dep_graph_registry` singleton; raises `DepGraphRegistryError` with `no_strategy_for_ecosystem: <repr>` prefix.
- **S1-10 model** at `src/codegenie/depgraph/model.py`: `DepGraphProbeOutput(graph_path, confidence, reason)` — frozen + extra=forbid.
- **Phase 1 ADR-0013**: `PackageManager` is `Literal["bun","pnpm","yarn-classic","yarn-berry","npm"]`; canonical re-export at `codegenie.types.identifiers`.
- **02-ADR-0003**: `@register_probe(heaviness="light", runs_last=False)` defaults.
- **Phase 0 ADR-0006**: `[project.dependencies]` is the runtime closure; `gather` extras intentionally empty.
- **S4-01**: established Phase 2 sibling-slice access pattern via on-disk JSON sidecars; pure `read_raw_slices` helper at `src/codegenie/probes/layer_b/index_health.py`.
- **CLAUDE.md**: "Extension by addition", "Match codebase conventions", "Surface conflicts don't average them", "Read before you write".

## Source-of-truth verifications (grep against master + sibling stories)

| Reference in draft | Master / sibling surface | Verdict |
|---|---|---|
| Impl outline §3 + T-06: `async def run(self, ctx) -> ProbeOutput` | `Probe.run(self, repo: RepoSnapshot, ctx: ProbeContext)` at `src/codegenie/probes/base.py:94` | **PHANTOM** — one-arg signature would `TypeError` at dispatch |
| AC-3 / Impl §3: `registry.get_strategy(pm_enum)` returns `None` | `default_dep_graph_registry.has_strategy(eco) -> bool` + `dispatch(eco, ...) -> DiGraph` raises (no None-return) | **PHANTOM API** |
| Test preamble: `from codegenie.depgraph.registry import iter_strategies, _clear_for_tests` | Real exports: `register_dep_graph_strategy`, `default_dep_graph_registry`, `DepGraphRegistry`, `DepGraphStrategy`, `DepGraphRegistryError` (per S1-10 AC-1); no `iter_strategies`, no `_clear_for_tests` | **PHANTOM SYMBOLS** |
| AC-3 / AC-5: `PackageManager(pm)` raises `ValueError` | `PackageManager` is `Literal[…]` (a typing construct, not a class); not callable; `PackageManager(x)` raises `TypeError: 'typing.Literal' is not callable` | **TYPE-SYSTEM MISUSE** (S1-10 validation finding #1 carried over) |
| T-06: `@register_dep_graph_strategy(ecosystem=PackageManager.PNPM)` | `Literal` has no attributes; `PackageManager.PNPM` raises `AttributeError` | **TYPE-SYSTEM MISUSE** |
| T-10: `from codegenie.probes.layer_a.node_build_system import PackageManager` | `layer_a/` directory does not exist; canonical re-export at `codegenie.types.identifiers` (S1-05) | **PHANTOM PATH** |
| AC-2 / AC-3: `ctx.sibling_slices.get("build_system")` | `ProbeContext` fields: `cache_dir`, `output_dir`, `workspace`, `logger`, `config`, `parsed_manifest`, `input_snapshot`, `image_digest_resolver` (frozen ABC, Phase 0 ADR-0007) | **PHANTOM FIELD** |
| Impl §5 / §6: `ctx.snapshot.root` | `ProbeContext` has no `snapshot`; `RepoSnapshot.root` lives on the first `run()` arg (`repo: RepoSnapshot`) | **PHANTOM ATTR** |
| AC-6: 6-field `DepGraphProbeOutput` redefined in probe module | Shipped at `src/codegenie/depgraph/model.py` (S1-10) with 3 fields: `graph_path`, `confidence`, `reason: str \| None`; frozen + extra=forbid | **CONTRACT FORK** |
| AC-3: `strategy.build(snapshot=..., manifests=..., build_system=...)` | `DepGraphStrategy = Callable[[ProbeContext, list[Mapping[str, Any]]], DiGraph]` (S1-10 `registry.py:60`) — positional `(ctx, manifests)`; no `build_system` kwarg | **SIGNATURE MISMATCH** |
| Impl §3: `await asyncio.wait_for(_invoke_strategy(...))` | Sync `Callable[..., DiGraph]` cannot be awaited; CPU blocking is unbounded without `asyncio.to_thread` | **ASYNC MECHANISM MISSING** |
| T-13: warning ID `dep_graph.strategy_timeout` | AC-11's `_WARNING_IDS` declares only `dep_graph.upstream_build_system_unavailable`, `dep_graph.unrecognized_package_manager` | **INTERNAL INCONSISTENCY** |
| T-10: assert "no `class PackageManager`" | `PackageManager` is a Literal alias — "no class" is necessary but not sufficient; redefinition catch is the load-bearing assertion | **WRONG ASSERTION SHAPE** |

## Findings by critic lens

### Coverage critic

| # | Severity | Finding |
|---|---|---|
| C-1 | block | AC-3 didn't specify how `manifests: list[Mapping[str, Any]]` is constructed before passing to `dispatch`. A probe that passed `[]` would pass typed-confidence assertions but silently break Phase 3 adapters expecting parsed manifests. |
| C-2 | harden | No AC pinned `raw/dep-graph.json` byte-stability across reruns (NetworkX dict iteration order leak risk). |
| C-3 | harden | No AC distinguished `yarn-classic` from `yarn-berry` in inline detection (Phase 1 ADR-0013 split is load-bearing). |
| C-4 | harden | AC-12 lacked a negative control (Python repo) — a probe that applied to every language would pass the positive asserts. |
| C-5 | nit | AC-13 didn't explain its relationship to S1-10's complementary source-scan test. |

### Test-quality critic

| # | Severity | Finding |
|---|---|---|
| T-1 | block | T-13 (timeout) cannot work without `asyncio.to_thread` — sync `time.sleep` would block the event loop and `wait_for` could not interrupt it. |
| T-2 | block | T-06 strategy signature `_mock_pnpm(snapshot, manifests, build_system)` doesn't match the S1-10 contract `(ctx, manifests)`. |
| T-3 | harden | T-06 didn't pin argument-identity on `manifests` reaching the strategy. A probe wrapping/copying manifests would pass T-06 but break Phase 3 adapters. |
| T-4 | harden | T-09 asserted properties of a probe-local `DepGraphProbeOutput` — would pass even if the redefinition forked the type. Should pin "import from S1-10". |
| T-5 | harden | T-10's "no class definition named PackageManager" is wrong-shaped for a Literal alias. Should pin import source + no reassignment. |
| T-6 | harden | T-04 parametrize used `PackageManager.__members__` (Enum API). Literals have no `__members__`. Use `get_args(PackageManager)`. |
| T-7 | nit | T-11 didn't exercise the import-time assertion failing — a regression weakening `_ID_PATTERN` would pass T-11. Add mutation companion. |

### Consistency critic

| # | Severity | Finding |
|---|---|---|
| K-1 | block | All eight phantom-surface findings (run signature, registry API, PackageManager Literal vs Enum, import path, sibling_slices, snapshot.root, model shape, strategy call signature). |
| K-2 | block | `ctx.sibling_slices` contradicts Phase 0 ADR-0007 (frozen ABC) AND S4-01's established sibling-read pattern (disk sidecars). Resolution requires inline detection OR Phase 1 amendment to write `node_build_system.json` sidecar. |
| K-3 | harden | AC-10 `gather` extras placement contradicted Phase 0 ADR-0006. Use `[project.dependencies]`. |
| K-4 | harden | Story's `requires=["node_build_system"]` is wrong if S4-05 re-detects inline (no topological dependency). S4-01 precedent: B-layer probes that read sibling data do NOT use `requires=` for that. |
| K-5 | harden | Story's `_clear_for_tests()` would have introduced a phantom helper into the fixture. The per-ecosystem `unregister_for_tests` IS the policy. |

### Design-patterns critic

| # | Severity | Finding |
|---|---|---|
| D-1 | harden | Impl outline §4 introduced `_invoke_strategy(strategy, ctx)` that "coerces sync/async" — duplicates the kernel's dispatch logic (S1-10 `DepGraphRegistry.dispatch` IS the invoke chokepoint). |
| D-2 | harden | Story redefined `DepGraphProbeOutput` inside the probe module — fork would create two failure modes (Rule 7). Use shipped S1-10 model. Optional sub-ADR for Literal-narrowing `reason`. |
| D-3 | harden | The pure-vs-impure split was implicit (only a REFACTOR step). S4-01 establishes functional core / imperative shell as the load-bearing structure for Layer B probes. Pure helpers belong in the GREEN-phase outline. |
| D-4 | nit | Story's `Notes` lacked a "do not introduce a kernel abstraction" guardrail. Three sibling registries are at rule-of-three (S1-10 deferred the kernel-extract). A junior implementer might propose `KernelRegistry[K, V]`. |
| D-5 | n/a | Rule-of-three for `_LOCKFILE_PRECEDENCE`: now duplicated between `node_build_system.py` and `dep_graph.py`. Two consumers, not three — extract NOT prescribed. Backlog Note. |

## Prescriptions applied to the story (HARDENED set)

The story was edited in place to:

1. Switch all `run()` invocations and the ABC reference to two-arg `(repo: RepoSnapshot, ctx: ProbeContext)`.
2. Replace `registry.get_strategy(pm_enum)` / `iter_strategies()` / `_clear_for_tests()` with `default_dep_graph_registry.{has_strategy, dispatch, registered_ecosystems, unregister_for_tests}`.
3. Replace `PackageManager.PNPM` / `PackageManager(str)` with `cast(PackageManager, "pnpm")` and `frozenset(get_args(PackageManager))` membership.
4. Correct the canonical import path to `codegenie.types.identifiers`.
5. Replace `ctx.sibling_slices["build_system"]["package_manager"]` with inline detection on `repo.root` via a small priority-1/2 lockfile walk plus `package.json#packageManager` parsing (acknowledged Rule 7 duplication of `_LOCKFILE_PRECEDENCE`; backlog Note enumerates the two follow-up paths).
6. Fix `ctx.snapshot.root` → `repo.root` throughout.
7. Consume the shipped 3-field `DepGraphProbeOutput`; pin slice-dict echo for `ecosystem`/`nodes_count`/`edges_count`/`dep_graph_uri`; optional sub-ADR (AC-6a) for Literal-narrowing `reason`.
8. Rewrite the strategy invocation as `asyncio.wait_for(asyncio.to_thread(default_dep_graph_registry.dispatch, pm, ctx, manifests), timeout=...)` — bounds sync CPU.
9. Add `dep_graph.strategy_timeout`, `dep_graph.package_manager_field_unparseable`, `dep_graph.yarn_variant_inferred`, `dep_graph.no_manifest_detected` to `_WARNING_IDS`.
10. Rewrite T-10 to assert import source + no reassignment (not "no class").
11. Add argument-identity capture assertions in T-06; add T-14 (yarn variant detection) + T-15 (byte-identical reruns).
12. Refactor Implementation outline to pure helpers + imperative shell (mirrors S4-01).

## Verdict rationale

**HARDENED, not RESCUE.** Although the edit scope is substantial, the story's **goal** is unchanged and its **AC-to-goal trace** is intact. The phantom-surface findings are mechanical reconciliations with shipped code (S1-10) and frozen contracts (Phase 0 ABC), not redesigns of intent. After hardening, every AC is verifiable, every TDD test has a clear pass/fail criterion, and the executor's Validator pass can mechanically check the runtime evidence for each AC.

The **one remaining architectural choice** (handle the missing `build_system` sidecar via Phase 1 helper extraction OR Phase 1 amendment OR S4-05 inline duplication) is surfaced in `Notes for the implementer` and the validator does NOT auto-pick. The inline-duplication path is currently prescribed as the surgical default; either of the other two paths could be adopted by a follow-up story without breaking S4-05's contract.

## Open items for the executor

1. **AC-6a (sub-ADR)** — implementer chooses whether to land the `reason` Literal-narrowing in this story or defer. Either path satisfies AC-6.
2. **`_LOCKFILE_PRECEDENCE` duplication** — recorded as a backlog Note. The story does NOT block on a follow-up extraction.
3. **`networkx>=3.4`** — verify against current `pyproject.toml`; add to `[project.dependencies]` only if absent.
