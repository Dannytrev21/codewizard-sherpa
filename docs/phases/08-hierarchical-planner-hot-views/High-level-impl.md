# Phase 08 — Hierarchical Planner + pre-rendered hot views: High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-21
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [docs/roadmap.md](../../roadmap.md) §"Phase 8"

## Executive summary

Phase 8 builds four new flat packages — `codegenie.supervisor`, `codegenie.planner`, `codegenie.hotviews`, `codegenie.mcp` — plus two additive, fence-enumerated edits to shipped files (`RepoId` in `types/identifiers.py`, `RouteDecided`/`RouteDescended` in `plugins/events.py`). The work is sequenced contracts-first: every newtype, tagged union, `Protocol`, and frozen Pydantic model lands before any consumer, so `mypy --strict` is a real gate from Step 2 onward. Two architect-surfaced gaps are sequencing constraints baked into the plan — the `RepoId` newtype lands in Step 1 because every later signature uses it, and the `ConcreteResolution → BundleResolution` adapter (Step 4) gates Bundle building and must fail loud (`ResolverTccmPlaceholder`) if the resolver's S3-01 TCCM substitution has not shipped. The two exit criteria — a logged routing decision on every workflow, and `<50 ms p95` hot-view serving — are closed by Steps 5–7 and proven by a `phase08_e2e` latency test and a static append-before-transition AST test.

## Order of operations

The sequence is dictated by dependency direction and by the design patterns the architect committed to. Contracts come first: newtypes, tagged unions, `Protocol`s, and `StrEnum`s are pure declarations every consumer imports, so they land in Steps 1–3 before any package that uses them. Within the four packages, `codegenie.hotviews` and `codegenie.planner` are leaves (the planner reads the hot-view store; nothing reads the planner except the supervisor), so they precede `codegenie.supervisor`, which composes both. The `ConcreteResolution → BundleResolution` adapter (C2) is its own step before the supervisor graph because it is a hard gate — without it the `build_bundle` node either fails to type-check or silently builds an empty Bundle. `codegenie.mcp` is fully independent of the other three and is sequenced late so it does not block the exit-criteria path. Infrastructure (Redis container, deps) lands in Step 1 because the perf-bearing tests need a real `redis:7-alpine` from the first hot-view step.

### Pattern-driven sequencing

- **Newtypes + smart constructors Step 1.** `RepoId` (and `SkillId` regex guard) are domain primitives in 50+ call sites; per the toolkit they must exist before any signature uses them, or consumers fall back to stringly-typed `str`. Step 1 lands `RepoId` in `types/identifiers.py` with `__all__` updated and `mypy --strict` clean.
- **Tagged unions before the state machine.** `SupervisorDecision`, `TriggerProvenance`, `PlanningRoute`, `HotViewSliceName`, and the two new event variants are declared as frozen Pydantic discriminated unions / `StrEnum`s in Steps 2–3 — before `decide()` and `route()`, which `match` over them with `assert_never`. A state machine built before its state union is un-typecheckable.
- **Ports before adapters.** `RecipeMatchPort`, `SolvedExampleRagPort`, `LeafLlmPort`, `ColdStoreReader` are `Protocol`s declared in Step 3 before `PlannerNode` (Step 5) and before `NullRagPort` — the hexagonal boundary is fixed before either side is filled.
- **No registry for the routing tiers.** The architect explicitly rejected `@register_planning_step` — three fixed steps are an ordered `tuple`, not a registry. There is no registry-kernel step here; the only registry consumed (`PluginRegistry`) already ships.
- **Type-strict from day one.** `mypy --strict src/` and `ruff` (`C901` ≤ 8) are in every step's done-criteria, not deferred to a cleanup step.

## Step 1 — Land the contract primitives and the runtime substrate

**Goal:** Add the `RepoId` newtype, stand up Redis + the two new dependencies, and wire the Phase-8 fence allowlist so every later step builds on a typed, fenced foundation.

**Features delivered:**
- `RepoId = NewType("RepoId", str)` added to `src/codegenie/types/identifiers.py`, exported in `__all__` (Gap 3). Free `NewType` for now; the `owner/name` smart-constructor lift is deferred to Phase 10 (Open Question 7).
- `redis:7-alpine` service in `docker-compose.yml` (`:6379`, no AOF, no replication).
- `redis>=5` (client) and a version-pinned `mcp` SDK row added to `pyproject.toml` (Open Question 8 — pin a specific `mcp` version).
- `import-linter` contract group: `codegenie.hotviews`, `codegenie.mcp`, `codegenie.supervisor`, `codegenie.planner.routing` may not import any LLM SDK.
- A `tests/fence/` entry enumerating the Phase-8 wiring allowlist (four package imports, the `docker-compose.yml` redis line, the `pyproject.toml` `redis`/`mcp` rows) + a fence test confirming the four new packages stay outside the `test_pyproject_fence.py` gather-runtime closure.

**Done criteria:**
- [ ] `from codegenie.types.identifiers import RepoId` succeeds; `mypy --strict src/` clean.
- [ ] `docker compose up redis` starts `redis:7-alpine` on `:6379`; a `redis-py` ping from a throwaway script succeeds.
- [ ] `make lint-imports` green with the new LLM-SDK contract group.
- [ ] `make fence` green — Phase-8 packages confirmed outside the gather closure; `pyproject.toml` `redis`/`mcp` rows present in the allowlist.
- [ ] `make check` green (no behavior added yet — this step is substrate only).

**Depends on:** none (external prerequisite: Docker available locally for `redis:7-alpine`).
**Effort:** S — additive edits to four existing files plus one fence test; no new logic.
**Risks specific to this step:** the `mcp` SDK is young (Open Question 8) — pin a concrete version and confirm it installs cleanly under Python 3.11 and 3.12 before proceeding.

## Step 2 — Declare the hot-view data model and the Supervisor/routing sum types

**Goal:** Land every frozen Pydantic contract — hot-view slices, `SupervisorDecision`, `TriggerProvenance`, `PlanningRoute`, `RouteDecision` — as pure declarations before any consumer.

**Features delivered:**
- `codegenie/hotviews/model.py` — `HotViewSliceName` `Literal`, `HotViewKey` (with `redis_key()`), `HotViewSlice` (`gather_id`- and `slice_schema_version`-stamped), the four per-slice payload models, `RenderReport`.
- `codegenie/planner/model.py` — `PlanningRoute` `StrEnum`, `RouteDecision` frozen model.
- `codegenie/supervisor/state.py` — `SupervisorState`, `PluginWorkItem`, the `Dispatched | MultiPluginDispatch | EscalatedToHITL` discriminated `SupervisorDecision` union, `SingleTaskTrigger | BothProvenanceTrigger` `TriggerProvenance` union with the `>= 2` `field_validator` on both `BothProvenanceTrigger.implicated_task_classes` and `MultiPluginDispatch.work_items`.
- All models `frozen=True`, `extra="forbid"`; discriminated unions use `Field(discriminator="kind")`.

**Done criteria:**
- [ ] `mypy --strict src/` clean across the three new model modules.
- [ ] A contract-snapshot test pins the `SupervisorDecision` and `TriggerProvenance` JSON shapes; `match` over `SupervisorDecision` with `assert_never` type-checks.
- [ ] A `BothProvenanceTrigger` with one task class raises `ValidationError` (edge case 14); a `MultiPluginDispatch` with one work item raises `ValidationError`.
- [ ] `HotViewKey.redis_key()` returns `hotview:{repo}:{slice}:v{n}` — unit-tested over all four slice names.
- [ ] `ruff` clean; no public name beyond the bounded surface budget (≤ 24 across the four packages — tracked from here).

**Depends on:** Step 1 (`RepoId`).
**Effort:** S — pure model declarations, no behavior; the validators are a few lines each.

## Step 3 — Declare the planner ports and extend the event union

**Goal:** Land the hexagonal `Protocol` boundary and the two additive routing-event variants so the planner and store have their seams fixed before any logic.

**Features delivered:**
- `codegenie/planner/ports.py` — `RecipeMatchPort`, `SolvedExampleRagPort`, `LeafLlmPort` `Protocol`s; `RecipeMatch` / `RagHit` result models.
- `codegenie/hotviews/store.py` (interface only) — the `ColdStoreReader` `Protocol`.
- `codegenie/planner/null_rag.py` — `NullRagPort` (the Phase-8 concrete `SolvedExampleRagPort`; KG arrives Phase 11).
- Additive edit to `src/codegenie/plugins/events.py` — `RouteDecided` and `RouteDescended` `Literal`-tagged variants added to the `WorkflowInternalEvent` union, to `_INTERNAL_CLASSES`, and to `__all__` (Gap 4 — workflow-scoped, internal stream, not the BLAKE3-chained spanning stream).
- Each new package declares its module-level `_WARNING_IDS: Final[frozenset[str]]` validated at import via `raise AssertionError(...)`.

**Done criteria:**
- [ ] `mypy --strict src/` clean; `NullRagPort` structurally satisfies `SolvedExampleRagPort` (a `Protocol` assignment test confirms).
- [ ] `RouteDecided`/`RouteDescended` round-trip through `EventLog.emit_internal` / `EventLog.replay` in an `InMemorySink` test.
- [ ] A test confirms `RouteDecided` is in `WorkflowInternalEvent` and **not** in `WorkflowSpanningEvent` — it pays no `fcntl.flock` per routing decision.
- [ ] Warning-ID regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` validated at import for all four packages.
- [ ] `make check` green.

**Depends on:** Steps 1–2.
**Effort:** S — `Protocol` declarations plus a three-line additive union edit; the precedent (`PluginResolved`) shows the exact placement.

## Step 4 — Build the `ConcreteResolution → BundleResolution` adapter (C2)

**Goal:** Bridge the resolver's output type to `BundleBuilder.build`'s input Protocol, failing loud if the resolver still hands the `ComposedTccm` placeholder.

**Features delivered:**
- `codegenie/supervisor/bundle_resolution.py` — `ResolvedBundleInput` (satisfies the shipped `codegenie.plugins.bundle.BundleResolution` Protocol) and the pure `to_bundle_resolution(resolution: ConcreteResolution) -> ResolvedBundleInput`.
- Maps each per-primitive `Adapter` object in `ConcreteResolution.composed_adapters` to its `AdapterDispatch` callable for `composed_dispatch`.
- A typed `ResolverTccmPlaceholder` error raised when `composed_tccm` is still the placeholder (empty `provides`/`requires`, no `must_read` band) — naming S3-01 as the prerequisite (edge case 2, D5).

**Done criteria:**
- [ ] **Gating prerequisite resolved (Open Question 1 / Gap 2):** the implementer has verified against `src/codegenie/plugins/resolver.py` whether `resolver.resolve` hands the real `codegenie.plugins.tccm.TCCM` or the `ComposedTccm` placeholder — and, if the placeholder, has routed the S3-01 substitution loudly into the story plan as an explicit Phase-8 prerequisite. This verification result is recorded in the step's attempt log.
- [ ] `to_bundle_resolution` over a `ConcreteResolution` fixture produces a `ResolvedBundleInput` that structurally satisfies `BundleResolution` (`mypy --strict` confirms; a runtime `isinstance`-against-`Protocol` test confirms).
- [ ] A `ConcreteResolution` with a placeholder `composed_tccm` raises `ResolverTccmPlaceholder` — never builds an empty Bundle.
- [ ] The adapter imports no I/O module (functional-core purity AST test).
- [ ] `make check` green.

**Depends on:** Steps 1–3.
**Effort:** M — the mapping itself is pure and small, but the gating verification against `resolver.py` may surface S3-01 as a real prerequisite that expands scope.
**Risks specific to this step:** if S3-01 has not shipped, the `build_bundle` node cannot do anything real until it does — this is the single biggest schedule risk in the phase. Surface it before Step 6, not during.

## Step 5 — Implement the HotViewStore, renderer, and PlannerNode routing core

**Goal:** Build the warm-path read path (store + renderer) and the fixed three-step routing pipeline — the two leaf packages the supervisor will compose.

**Features delivered:**
- `codegenie/hotviews/store.py` — `HotViewStore` with `get` / `get_all` (one pipelined Redis round-trip of four `GET`s), `(repo, slice, gather_id, slice_schema_version)` integrity verification, fail-closed `ColdStoreReader` fallback on miss / `ConnectionError`. `get` always returns a `HotViewSlice`, never `None` (branchless warm path).
- `codegenie/hotviews/renderer.py` — pure `render_hot_views` (derives the four slices from `RepoContext` + the union of `must_read` queries across `active_tccms`), pure `invalidates` matcher, shell `write_hot_views` (one atomic `HSET` per slice → `RenderReport`).
- `codegenie/planner/routing.py` — `PlannerNode` with the fixed `tuple[(PlanningRoute, port-callable), ...]` recipe→RAG→LLM pipeline; first hit wins, fallthrough is `LLM`. `route()` reads `HotViewStore.get_all` and appends `RouteDecided` via `emit_internal` **before** returning the `RouteDecision`.
- The gather-tail detached-task callback that fires `render_hot_views` (a thin callback so the renderer package stays outside the gather closure).

**Done criteria:**
- [ ] `mypy --strict src/` clean; `make lint-imports` green (`codegenie.planner.routing` LLM-SDK-fenced).
- [ ] `PlannerNode.route` selection: 100 % branch coverage over recipe-hit / RAG-hit (fake port) / LLM-fallthrough; `invalidates` 100 % branch coverage.
- [ ] `HotViewStore` integrity check unit-tested over matching / stale `gather_id` / tampered / `slice_schema_version`-drift values — all four resolve to a cold read (edge cases 4, 5, 6).
- [ ] `render_hot_views` and `invalidates` import no I/O module (functional-core purity AST test); `render_hot_views` golden-tested (`tests/golden/hotviews/{repo}/`) for byte-identical re-render.
- [ ] A property test: `invalidates` is monotone (adding a probe never removes a slice).
- [ ] `make check` green.

**Depends on:** Steps 1–3 (models, ports, event variant). Independent of Step 4.
**Effort:** L — two packages, the renderer's TCCM-aggregation logic, the redis-py shell, golden fixtures, and the gather-tail callback wiring.
**Risks specific to this step:** the cold-storage read must hit the *same* `RepoContext` artifact the renderer rendered from (Open Question 6) or warm/cold equivalence fails — confirm the `ColdStoreReader` artifact identity before writing the property test in Step 7.

## Step 6 — Assemble the Supervisor graph and the pure `decide()` core

**Goal:** Wire the three-node `resolve → build_bundle → route` Supervisor and the pure `decide()` function that maps `(provenance, resolution, bundle, route)` to a `SupervisorDecision`.

**Features delivered:**
- `codegenie/supervisor/decide.py` — the pure `decide()` core: maps to `Dispatched` (single `ConcreteResolution`), `MultiPluginDispatch` (`BothProvenanceTrigger`, one `PluginWorkItem` per resolved task class), or `EscalatedToHITL` (`UniversalFallbackResolution`). `match` + `assert_never`.
- `codegenie/supervisor/graph.py` — `build_supervisor_graph` and `run_supervisor`; `SupervisorGraph` bound to a plain async pipeline of three functions sharing a frozen `SupervisorState` advanced by `model_copy(update=...)` (08-ADR-0001 Option B — keeps the new-dep count at two; the node boundary is the Phase-9 Temporal-Activity seam either way).
- `resolve_node` (calls `resolver.resolve`, emits `PluginResolved`), `build_bundle_node` (calls `to_bundle_resolution` then `BundleBuilder.build`, emits `BundleBuilt`), `route_node` (calls `PlannerNode.route`).
- The `BothProvenanceTrigger` branch: resolve each implicated task class, build a `Bundle` + `RouteDecision` per resolution.
- Dispatch of the `Dispatched` payload into the Phase-6 SHERPA subgraph's initial `SubgraphState` (`bundle` / `resolution` accumulator fields).

**Done criteria:**
- [ ] `mypy --strict src/` clean; `make lint-imports` green (`codegenie.supervisor` LLM-SDK-fenced).
- [ ] `decide()` exhaustively unit-tested over all three `SupervisorDecision` variants × both `TriggerProvenance` variants, zero mocks; a property test confirms `decide()` is total over all `(provenance, resolution-variant)` pairs.
- [ ] `decide()` imports no I/O module (functional-core purity AST test).
- [ ] An integration test runs the full graph against an in-memory `EventLog` (`InMemorySink`) and a real local Redis: a fixture vuln-remediation workflow produces a `Dispatched`; a `cobol` repo produces `EscalatedToHITL`; a `Both` trigger produces `MultiPluginDispatch` (edge cases 1, 3).
- [ ] A static AST test asserts no routing edge in `route_node` is reachable on a code path that skips the `RouteDecided` append (exit criterion 1, by construction).
- [ ] `make check` green.

**Depends on:** Steps 4 and 5.
**Effort:** M — `decide()` is pure and small; the graph is ~30 lines of plain async wiring; the `Both` branch and subgraph handoff carry most of the integration-test surface.

## Step 7 — Close the exit criteria: latency, decision-log completeness, and adversarial gates

**Goal:** Prove both exit criteria with measured tests and lock the security/audit properties.

**Features delivered:**
- `@pytest.mark.bench` canary — `HotViewStore.get_all` against a real `redis:7-alpine`, asserting `p95 < 50 ms`; a second bench asserts warm-path Supervisor overhead `p95 < 5 ms`.
- Two `@pytest.mark.phase08_e2e` tests — a fixture vuln-remediation workflow through the full Supervisor → Planner path asserting the `RouteDecided` event is in the internal stream; a latency e2e running 200 sequential `get_all` calls after a real render, asserting `p95 < 50 ms`.
- Property test — warm/cold equivalence (Hypothesis): a hot-view-served read and a cold-storage read produce byte-identical planner context.
- Adversarial tests — Redis-tamper / fail-closed (wrong `gather_id` discarded, cold fallback, mismatch signal emitted; attacker bytes for `risk_flags` yield byte-identical context to the no-tamper run); decision-log completeness (N fixture workflows → exactly N `RouteDecided` events in the internal stream).
- `RouteDescended` emission wired where Phase 4's `FallbackTier` descends (edge case 8) so misprediction rate is a measured number.

**Done criteria:**
- [ ] `HotViewStore.get_all` p95 `< 50 ms` measured against a real Redis (exit criterion 2 — measured, not asserted-by-faith).
- [ ] The `phase08_e2e` latency test passes; the `phase08_e2e` routing test confirms `RouteDecided` is logged on every workflow (exit criterion 1).
- [ ] Warm/cold-equivalence property test green — the cache never changes the answer, only the latency.
- [ ] Redis-tamper adversarial test green — fail-closed to cold storage, mismatch signal logged.
- [ ] Decision-log completeness adversarial test green — exactly N `RouteDecided` events for N workflows.
- [ ] `make check` green; `@pytest.mark.bench` advisory gate green with no `> 20 %` regression.

**Depends on:** Steps 5 and 6.
**Effort:** M — the tests are the work; a real-Redis perf harness and the Hypothesis equivalence test carry the weight.

## Step 8 — Ship the MCP Skills server

**Goal:** Serve Skill manifests to the planner over an `mcp` SDK stdio process with a snapshot-pinned tool surface.

**Features delivered:**
- `codegenie/mcp/server.py` — transport-agnostic `SkillsMcpServer` core: `start()` builds the in-memory index once (calls the shipped `SkillsLoader.load_all()`, indexes `Skill`s by `(task_class, language)`); `list_skills` / `get_skill` are dict lookups returning `SkillManifest`s (id, frontmatter, `body_offset`/`body_size`/`body_blake3` — never inlined bodies, progressive disclosure).
- `codegenie/mcp/stdio.py` — `serve_skills_stdio` on an `mcp` SDK `Server` with stdio transport; exactly two read-only tools (`list_skills`, `get_skill`); no write / exec / filesystem-path tool.
- `codegenie/mcp/contract.py` — `MCP_SKILLS_CONTRACT: Final[McpServerContract]`, the pinned tool surface.
- `SkillId` newtype hardened with a regex smart constructor — a traversal-shaped ID (`../../etc/passwd`) fails the constructor before any filesystem touch (edge case 12).

**Done criteria:**
- [ ] `mypy --strict src/` clean; `make lint-imports` green (`codegenie.mcp` LLM-SDK-fenced).
- [ ] A contract-snapshot test (`tests/golden/mcp/`) asserts the live server's advertised tools byte-match `MCP_SKILLS_CONTRACT` — drift fails CI.
- [ ] One integration test exercises a real MCP stdio roundtrip (`list_skills` + `get_skill`).
- [ ] `get_skill("../../etc/passwd")` is rejected by the `SkillId` smart constructor with a typed error before any filesystem touch.
- [ ] `SkillsMcpServer` builds its index in `start()`, not at import — no side effects in the constructor.
- [ ] `make check` green; the full Phase-8 fence allowlist (Step 1) still green.

**Depends on:** Step 1 (deps, fence). Independent of Steps 4–7.
**Effort:** M — the core is dict lookups, but the `mcp` SDK stdio transport, the contract snapshot, and the real-roundtrip integration test carry real integration risk against a young SDK.
**Risks specific to this step:** the `mcp` SDK's stdio transport and tool-advertisement API may not match `MCP_SKILLS_CONTRACT`'s assumptions (Open Question 8) — confirm against the pinned version before writing the snapshot.

## Exit-criteria mapping

| Exit criterion (verbatim or close) | Step(s) |
|---|---|
| "The planner makes the recipe/RAG/LLM decision and the chosen path is logged on every workflow." | Step 3 (event variants), Step 5 (`PlannerNode.route` + append-before-transition), Step 6 (static AST test — no routing edge skips the append), Step 7 (`phase08_e2e` routing test + decision-log completeness adversarial test) |
| "Hot views serve agent context in <50ms p95." | Step 1 (Redis substrate), Step 2 (slice models), Step 5 (`HotViewStore.get_all` one pipelined round-trip), Step 7 (`@pytest.mark.bench` canary + `phase08_e2e` latency test — measured `p95 < 50 ms`) |

Steps 4 and 8 do not directly close an exit criterion: Step 4 unblocks the Bundle-building path that Step 6 (and therefore exit criterion 1) depends on; Step 8 delivers the MCP Skills server scoped by `roadmap.md` §Phase 8 ("the Skills server runs as a local MCP stdio process") — required for phase completeness even though it is not in the two exit-criteria sentences.

## Implementation-level risks

1. **The resolver TCCM placeholder is still in place (Gap 2 / Open Question 1).** If `resolver.resolve` still hands `ComposedTccm`, the `build_bundle` node cannot produce a real Bundle and Step 6 is blocked. *Signal:* Step 4's gating verification finds no `must_read` band on the resolved `composed_tccm`. *Action:* surface S3-01 as an explicit Phase-8 prerequisite in the story plan before Step 6 begins; do not work around it with an empty Bundle — `ResolverTccmPlaceholder` must fire.
2. **The `mcp` SDK is young and the API may not match the pinned contract (Open Question 8).** *Signal:* Step 8's stdio roundtrip or contract snapshot fails against the pinned version. *Action:* pin a concrete `mcp` version in Step 1, validate the stdio transport and tool-advertisement API against `MCP_SKILLS_CONTRACT`'s assumptions before writing the snapshot; if the API diverges, adjust `MCP_SKILLS_CONTRACT` to the SDK's real shape rather than forcing the SDK.
3. **The `<50 ms p95` perf test is flaky in CI (shared-runner jitter).** *Signal:* the `phase08_e2e` latency test passes locally but fails intermittently on `ubuntu-24.04`. *Action:* the bench is advisory and CI-tracked; the e2e is the gate — run it against a co-located `redis:7-alpine` over a local socket (the design's measured headroom is ~25×, so true regressions are large); investigate any failure as a real regression, not by widening the threshold.
4. **Warm/cold divergence — the `ColdStoreReader` reads a different artifact than the renderer (Open Question 6).** *Signal:* the warm/cold-equivalence property test fails byte-comparison. *Action:* confirm in Step 5 that the `ColdStoreReader` adapter reads the exact `RepoContext` artifact `render_hot_views` rendered from before writing the Step 7 property test.
5. **The bounded public surface (≤ 24 exported names) is exceeded.** *Signal:* the surface count, tracked from Step 2, drifts past 24. *Action:* keep package internals (`store.py` redis-py calls, `decide.py` helpers) behind the package `__all__`; if 24 is genuinely too tight, surface it as a deliberate decision in the attempt log — do not silently widen.
6. **A new package accidentally lands inside the gather-runtime closure (edge case 16).** *Signal:* the Step 1 fence test fails after Step 5 wires the gather-tail callback. *Action:* the gather pipeline must reference the renderer only through a thin detached-task callback — never an `import codegenie.hotviews` in the gather closure; the fence test catches it on every PR.

## What's next — handoff to Phase 9

- **The three-node Supervisor graph is the Temporal-Activity seam.** Phase 9 wraps each node (`resolve_node`, `build_bundle_node`, `route_node`) in a Temporal Activity; `decide()` stays pure and Activity-wrappable. Because Phase 8 ships the plain async pipeline (08-ADR-0001 Option B), Phase 9 wraps three plain functions — no LangGraph migration required.
- **The routing events are emitted in the shape ADR-0034 adopts.** `RouteDecided` / `RouteDescended` ride the existing `WorkflowInternalEvent` stream; Phase 9 re-points `codegenie.plugins.events` as a projection of the canonical Postgres event log — a re-pointing, not a re-build.
- **`SupervisorDecision` and `MultiPluginDispatch` are stable contracts.** Phase 9's Temporal parent/child workflow model maps directly onto `MultiPluginDispatch(parent_workflow_id, work_items)`; Phase 10 (the first real `Both` producer) is an additive consumer.
- **The `LeafLlmPort` and `SolvedExampleRagPort` seams are ready.** Phase 9 attaches the per-workflow budget cap (ADR-0024/0025) at `LeafLlmPort`; Phase 11 swaps `NullRagPort` for the KG-backed adapter with zero routing-code change.
- **New on disk / new CI gates.** Redis hot views (`hotview:{repo}:{slice}:v{n}`) populated by the gather tail; the MCP Skills stdio server as a worked example for ADR-0023's topology decision; a new `import-linter` LLM-SDK contract group and the Phase-8 fence allowlist that every later phase inherits.
- **`RepoId` is the seam for Phase 10's GitHub repo identity.** Phase 10 Discovery can lift `RepoId` to a smart-constructed `owner/name` grammar additively — the newtype is already the single place that change lands.
