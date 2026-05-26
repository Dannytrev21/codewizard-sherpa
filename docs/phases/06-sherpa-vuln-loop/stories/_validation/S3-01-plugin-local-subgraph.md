# Validation report — S3-01 (Plugin-local subgraph)

**Date:** 2026-05-25
**Validator:** phase-story-validator (four parallel critic agents — Coverage, Test-Quality, Consistency, Design-Patterns — followed by in-context synthesis; no Stage-3 research needed — every plausible `NEEDS RESEARCH` flag was resolved by another critic's finding or by an explicit defer-to-next-story judgment).
**Verdict:** **HARDENED**
**Story path:** [`docs/phases/06-sherpa-vuln-loop/stories/S3-01-plugin-local-subgraph.md`](../S3-01-plugin-local-subgraph.md)

## Why HARDENED (not STRONG, not RESCUE)

The story's *architectural intent* matches every authoritative source: it wires the plugin-local LangGraph subgraph that composes Phase-3/4/5 ports under the path ADR-0002 + final-design.md item 1 pin verbatim. But the pre-validation file was a 17-line stub: one-sentence Goal, three vague bullet ACs (using `-` not `- [ ]`, so AC count was technically zero), three-sentence TDD plan, no References / Files-to-touch / Out-of-scope / Notes / Anti-refactor. Worst single failure mode: the story did NOT address that `langgraph` is currently in `pyproject.toml`'s closure-wide `forbidden_modules` list, AND the existing pyproject comment referenced an ADR-0003 §Consequences anchor that does NOT contain the admission decision. Without an explicit ADR amendment + path-scoped fence, the story is structurally unshippable — `make fence` breaks the moment `builder.py` imports `langgraph`.

Specific weaknesses found:

1. **AC count was 0.** Three bullets with `-`, not `- [ ]` — no checkbox-shaped, no individually-verifiable ACs.
2. **No path pinning.** "Graph package lives under the plugin" — ADR-0002 + final-design.md item 1 pin `plugins/vulnerability-remediation--node--npm/subgraph/` byte-equal. The vague AC let an executor land it anywhere.
3. **`langgraph` admission entirely unaddressed.** The pyproject anchor (`"see ADR-0003 §Consequences"`) is a forward-reference placeholder; ADR-0003 §Consequences contains only the chain-head verification consequences. This story must land the new Phase-6 ADR-0004 + the path-scoped fence BEFORE any production code can import `langgraph`.
4. **No five-node topology pinning.** The canonical sequence (`ingest_cve → match_recipe → apply_recipe → stage6_validate → write_branch`) is documented at multiple sites but the story did not enumerate; an executor could ship a 3-node skeleton that satisfies "graph package exists."
5. **No "edges own control flow" enforcement.** final-design.md item 4 verbatim ("No node directly calls another node") + arch §"Failure modes" row 2 ("node attempts direct peer call | AST test | CI failure") + High-level-impl.md §Step 3 ("Add static tests forbidding direct node-to-node calls") triple-pin this; the story's vague "import-boundary test" didn't name a file, an AST predicate, or an allowlist.
6. **No `SubgraphNode` Protocol-reuse pinning.** The Protocol already lives at `src/codegenie/plugins/subgraph.py` (Phase-3 S6-03 ship). Without an explicit "implementers, not redefiners" AC, an executor could redefine the Protocol locally — exactly the "no duplicate domain logic" failure the story's third bullet gestured at.
7. **No `Plugin.build_subgraph` reachability.** The Plugin Protocol's four-member kernel includes `build_subgraph`; the new plugin must satisfy it. Without the AC, the subgraph code exists on disk but `PluginRegistry.resolve()` can't reach it.
8. **No DI mechanism pinning.** "Injected ports" — through what shape? Constructor? Factory? `SubgraphDeps` god-object? Three Phase-3/5/6 precedents earn the rule-of-three for constructor injection; the story didn't claim the pattern.
9. **No compiled-vs-uncompiled `StateGraph` discipline.** LangGraph's `StateGraph.compile(checkpointer=...)` is the seam where the SUT adapter (S5-01) injects the checkpointer; compiling inside `build_subgraph` closes the seam. Without the AC, S5-01 has to rebuild from scratch.
10. **No failure-routing matrix.** final-design.md §"Main workflow" step 6 lists four routing paths (pass / retry / escalate / fail); none are tested. A graph that always routes to `Completed` would pass the existing ACs.
11. **No bounded-retry cap.** LangGraph cycles via conditional edges; a graph with no `MAX_RETRIES` infinite-loops in production.
12. **No entry-edge `hydrate_or_fail` wiring.** S2-02's `hydrate_or_fail` is the SOLE site of integrity decision; the subgraph's entry edge must call it before any node runs. Without the AC, a tampered chain silently resumes — the most catastrophic failure mode the entire phase-6 design defends against.
13. **No node exception wrapping.** arch §"Failure modes" row 5: "planner/gate exception | node outcome wrapper | typed failed state, not traceback escape." Without the AC, a planner `RuntimeError` propagates out of `graph.ainvoke()` and the Phase-6.5 bench sees an untyped exception.
14. **No trust-bypass AST fence.** final-design.md item 6 ("No new trust bypass") needs structural enforcement; an executor calling `subprocess.run(["npm", "install"])` directly bypasses Phase-5 sandbox gates.
15. **No cross-plugin isolation fence.** ADR-0002 §Consequences ("Existing plugin behavior remains isolated from future task classes") needs structural enforcement; Phase-7's plugin could silently import from Phase-6's.
16. **No `__all__` discipline.** S1-01 / S1-02 / S2-01 / S2-02 all enforce the 14-name `codegenie.workflows.__all__` allowlist sentinel; this story adds plugin-side code (correctly), but the no-leak property needs explicit assertion per Phase-6.5's "may not depend on" constraint.
17. **No contract snapshot extension.** Every prior Phase-6 story extends `test_phase6_sut_contract_snapshot.py`; this story's subgraph surface (builder signature, deps schema, node set) needs the same defense.
18. **No file naming convention.** Per-node-file is the Open/Closed substrate (rule-of-three earned across `vuln_*`, `transforms/engines/*`, `_indices/*`); a collapsed `subgraph/nodes.py` makes every node addition a kernel edit.
19. **No HITL deferral statement.** final-design.md item 5 (typed-interruption discriminated union) belongs to S4-01 but the story should explicitly defer or it's ambiguous which scope owns the work.
20. **"Refactor: extract pure reducers" was undefined.** "Reducers" in LangGraph terms are `Annotated[T, reducer_fn]` accumulator merges; the story didn't name what state field needs one or what shape they take. Without pinning, the executor invents an abstraction with no concrete consumer.

All in-place fixable; none requires re-running `phase-story-writer`. The story's structure (one-paragraph goal, ACs, TDD plan) survives — three bullets grew to 16 numbered ACs, the TDD plan was reordered with the anti-refactor block, and References / Files-to-touch / Out-of-scope / Notes-for-implementer / Anti-refactor were added. Verdict: **HARDENED**.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (post-edit):** ship the plugin-local LangGraph subgraph at `plugins/vulnerability-remediation--node--npm/subgraph/` (per-node module Open/Closed substrate), wire entry-edge `hydrate_or_fail`, route through four canonical failure paths via existing `Advance | ShortCircuit | Escalate` tagged union (no new arms), enforce "edges own control flow" via AST fences, land Phase-6 ADR-0004 path-scoped `langgraph` admission (closure-deny + path-admit mirroring Phase-4 anthropic precedent), expose via `Plugin.build_subgraph(registry) -> StateGraph` (uncompiled — S5-01 adapter compiles with injected checkpointer).
- **Status pre-validation:** `Ready` — never executed; never validated.
- **Status post-validation:** `HARDENED`.

### Authoritative sources

- **ADR-0002** pins the plugin path verbatim + the `src/codegenie/` ports-location rule.
- **final-design.md §"Decisions of record"** items 1, 4, 5, 6 — plugin-local topology, edges-own-control-flow, typed-interruption discriminated union, no-new-trust-bypass.
- **phase-arch-design.md §"Logical view"** — the topology (SUT → adapter → graph → {ports, ledger}).
- **phase-arch-design.md §"Failure modes"** rows 2 + 5 — node-peer-call AST test + node-exception-wrapper typed return.
- **High-level-impl.md §"Step 3"** — three bullets: plugin path + port wiring + static tests.
- **Phase-3 S6-03 (already shipped)** — `SubgraphNode` Protocol + `SubgraphState` + `Advance | ShortCircuit | Escalate` tagged union. Phase-6 nodes IMPLEMENT, never REDEFINE.
- **Phase-3 `Plugin` Protocol (`src/codegenie/plugins/protocols.py`)** — four-member kernel (`manifest`, `build_subgraph`, `adapters`, `transforms`). New plugin satisfies the Protocol; no kernel amendment.
- **Phase-4 path-scoped fence precedent** (`tests/fence/test_pyproject_fence_phase4.py`) — canonical "closure-wide deny + path-scoped admit" pattern AC-14's new Phase-6 fence mirrors.

### Hardest design tension resolved

**Verifier-as-Protocol vs free function** was already resolved in S2-02. The parallel tension here is **`build_subgraph` returns compiled vs uncompiled `StateGraph`** (DP-5). The Plugin Protocol's existing `build_subgraph` return type is `PluginSubgraph` (a wrapper); the implementer choice is whether to compile inside or outside. Resolution: uncompiled — the SUT adapter (S5-01) compiles with the injected checkpointer per Phase-6's substrate-portability story (Phase-9 Postgres swap is a one-line constructor change). Compiling inside would close the checkpointer-injection seam.

## Stage 2 — Critic findings (summary)

Four critics ran in parallel; findings consolidated below.

### Coverage (`COV-*`) — 20 findings (7 block, 9 harden, 4 nit)

| Disposition |
|---|
| All 7 block findings adopted as ACs (path pinning, ports + injection, no-duplicate-logic, LangGraph fence, 5-node topology, edges-own-control-flow, Protocol conformance). |
| All 9 harden findings adopted (checkpoint emission, entry-hydration, routing matrix, exception wrapping, trust closure, TCCM manifest, error-id namespace, EventLog wiring, contract snapshot). |
| 3 nits adopted (typecheck, idempotent re-entry deferred to S4-01, HITL placeholder); 1 nit (cassette pinning) deferred to S6-01 closeout. |

### Test Quality (`TQ-*`) — 13 findings (8 block, 4 harden, 1 nit)

| Disposition |
|---|
| All 8 block findings adopted — concrete fence file names (TQ-1), node-order test (TQ-2), uncompiled-StateGraph type assertion (TQ-3), routing matrix per-arm (TQ-4), exception-wrapping integration test (TQ-5), `hydrate_or_fail` short-circuit test with spy-Mock (TQ-6), boundary-only TransitionEvent emission (TQ-7), per-node `isinstance(SubgraphNode)` + `iscoroutinefunction` check (TQ-8). |
| 4 harden adopted (frozen-state AST guard, replay-determinism property — DEFERRED to S6-01, port-shape mock assertions, "extract pure reducers" rewrite). |
| 1 nit (cassette test) deferred to S6-01. |

### Consistency (`CON-*`) — 24 findings (9 block, 12 harden, 3 nit)

| Disposition |
|---|
| All 9 block adopted — including the **load-bearing CON-6** discovery that the existing pyproject anchor (`"see ADR-0003 §Consequences"`) references an ADR section that does NOT contain the admission decision. Resolution: new ADR-0004 + new fence + rewrite the pyproject comment to reference ADR-0004. |
| All 12 harden adopted (CON-4 trust closure, CON-5 HITL defer, CON-9 test-file naming, CON-13 boundary-only emission, CON-15 plugin manifest in-scope, CON-16 error-id namespace, CON-17 cross-story integration scoping, CON-18 `__all__` defense, CON-19 workflow-determinism deferred to S6-01, CON-20 subprocess discipline, CON-22 cross-plugin isolation, CON-24 fence-file list). |
| 3 nits adopted (CON-8 status flip, CON-21 forbidden-patterns note, CON-23 Phase-7 reuse-by-imitation). |

### Design Patterns (`DP-*`) — 14 findings (1 block, 11 harden, 2 nit)

| Disposition |
|---|
| DP-1 block (composition over inheritance) → Anti-refactor #1. |
| 11 harden adopted: DP-2 per-node-file (AC-1), DP-3 constructor DI (AC-3 + Anti-refactor #7 `Services` god-object), DP-4 free-function builder (AC-2 + Anti-refactor #2), DP-5 uncompiled `StateGraph` (AC-2), DP-6 functional core inside nodes (AC-7 routing purity), DP-7 `Annotated`-reducer hygiene (AC-8), DP-8 no `SubgraphRegistry` (Anti-refactor #3), DP-9 replay-safe nodes (Notes), DP-10 newtype discipline (Notes — covered by existing CLAUDE.md rule), DP-14 imperative topology (Anti-refactor #5). |
| 2 nits adopted: DP-11 (`EscalationReason` additive amendment guidance — Notes), DP-12 (`NodeTransition` arity confirmation — AC-9 + Anti-refactor #6 explicit "no new arm"), DP-13 (`SubgraphState` vs `VulnLedgerState` separation — Notes). |

## Conflict resolution (priority: Consistency > Coverage > Test-Quality > Design-Patterns)

1. **`langgraph` admission path** (CON-6 vs no other voice). **Resolution:** new ADR-0004 mirroring the Phase-4 anthropic precedent. The pyproject comment's existing "see ADR-0003 §Consequences" reference is fixed in this story (AC-14 part 3) — the prior reference was a forward-reference placeholder that never resolved.

2. **`build_subgraph` return type — compiled vs uncompiled** (DP-5 vs no opposition; CON-11 names the Plugin Protocol returns `PluginSubgraph`). **Resolution:** the type signature in AC-2 returns `StateGraph[SubgraphState]` (LangGraph's StateGraph). The plugin's `build_subgraph(registry)` (Plugin Protocol) wraps or returns this. The SUT adapter compiles with the injected checkpointer. This honors both DP-5's seam-preservation and CON-11's Plugin-Protocol-reachability.

3. **HITL ownership** (CON-5 vs COV-19 both defer to S4-01). **Resolution:** explicit Out-of-scope + a Notes line + a placeholder `Escalate(reason="awaiting_human_review")` emitted by AC-9 routing matrix path #3. S4-01 lands the typed interrupt payload + resume validator additively.

4. **Workflow-replay-determinism property ownership** (CON-19 + TQ-10 both defer to S6-01). **Resolution:** S6-01 closeout owns; this story provides the substrate (the wired graph) the property exercises.

5. **Cassette pinning** (TQ-13 nit). **Resolution:** deferred to S6-01 / S5-01 end-to-end golden; this story uses `Mock(spec=...)` for the Planner port, no live Anthropic calls.

6. **Per-node module vs collapsed `nodes.py`** (DP-2 + COV-no-collision). **Resolution:** per-node module is canonical (Open/Closed at the file boundary). Anti-refactor #9 explicitly rejects `subgraph/nodes.py` single-file collection.

No `NEEDS RESEARCH` flag remained after critic synthesis.

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` flag from any critic remained unresolved after Stage-2 synthesis.

## Stage 4 — Edits applied

### Pre-validation story (17 lines)

```markdown
# S3-01 — Plugin-local subgraph

**Status:** Ready
**Goal:** Wire the vuln remediation graph under the plugin directory and compose existing Phase 3–5 ports.

## Acceptance criteria

- Graph package lives under the plugin.
- Planner, transform, and gate services are injected ports.
- No duplicate domain logic is introduced.

## TDD plan

Red: import-boundary test.
Green: add graph builder and node wiring.
Refactor: extract pure reducers.
```

### Post-validation story (HARDENED — see file)

| Section | Before | After |
|---|---|---|
| Status line | `Ready` | `HARDENED` + `Validated:` line + `Depends on:` (six explicit cross-story deps) |
| Goal | 1 sentence | 1 paragraph + 1 deferral note naming the path, ports, four-routing matrix, ADR-0004 amendment, S5-01 hand-off |
| References | absent | 14-entry block citing final-design.md / phase-arch-design.md / ADRs/0002 / new ADR-0004 / High-level-impl.md / sibling stories S2-02, S2-01, S1-02, S1-01 / Phase-3 SubgraphNode Protocol / Phase-3 tagged union / Phase-3 Plugin Protocol / Phase-4 fence precedent / Phase-7 forward dep |
| Acceptance criteria | 3 bullets (0 checkboxes) | 16 numbered checkbox ACs across 7 labeled sub-sections (plugin shape, node implementations, edges-own-control-flow, routing matrix, entry-edge hydration, exception wrapping, trust closure, `langgraph` admission, `__all__` + isolation, closeout gates) |
| Files to touch | absent | 30-line list — plugin source files + ADR-0004 + 6 fence files + 8 unit/integration test files + 2 contract-snapshot modifications + 1 mypy-files modification |
| TDD plan | 3 sentences | Red phase (16-step sequence; ADR-0004 lands at step 2 BEFORE any production import) + Green (concrete impl list) + Refactor (4-item cleanup list) + Anti-refactor (9 items) |
| Out of scope | absent | 8-item list — HITL (S4-01), SUT adapter (S5-01), end-to-end (S5-01+S6-01), workflow-determinism property (S6-01), Phase-9 Postgres, second plugin (Phase-7), richer TCCM, anti-pattern abstractions |
| Notes for implementer | absent | 11-paragraph block — ADR-0004-first rationale, uncompiled-StateGraph rationale, per-node-file Open/Closed, constructor-injection rule-of-three, `_wrap_node_exceptions` decorator rationale, entry-pseudo-node rationale, four-path mapping to existing arms, sole-site fence ownership, all-plugin-pairs isolation, Phase-7 reuse-by-imitation, Phase-9 checkpointer-agnostic, workflow-determinism-deferred |

## Verdict

**HARDENED** — every Stage-2 critic finding either landed as an AC, an Anti-refactor item, or an Out-of-scope / Notes-for-implementer entry. All conflicts resolved with explicit priority-order rationale. No `NEEDS RESEARCH` flag remained open. The story is ready for `phase-story-executor`.
