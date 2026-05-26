# Validation report — S3-02 (Transition table tests)

**Date:** 2026-05-26
**Validator:** phase-story-validator (inline four-lens analysis — Coverage, Test-Quality, Consistency, Design-Patterns — applied directly after Stage 1's Context Brief, mirroring the precedent set by the S1-02 and S3-01 validations in this phase. The story is small enough that spawning four parallel critic agents would have burned tokens without changing the verdict.)
**Verdict:** **HARDENED**
**Story path:** [`docs/phases/06-sherpa-vuln-loop/stories/S3-02-transition-table-tests.md`](../S3-02-transition-table-tests.md)

## Why HARDENED (not STRONG, not RESCUE)

The story's *architectural intent* matches the design — `phase-arch-design.md §"Testing strategy"` lists "Reducer unit tests: exhaustive transition matrix" and "Static tests: graph nodes may import ports, not each other directly" as canonical Phase-6 testing concerns; `final-design.md §"Decisions of record"` item 4 (edges own control flow) plus `High-level-impl.md §"Step 3"` third bullet ("Add static tests forbidding direct node-to-node calls") triple-pin the AST fence concern. But the pre-validation file was a 17-line stub identical in shape to S3-01 pre-validation (one-sentence goal, three vague `-` bullets, three-sentence TDD plan, no References / Files-to-touch / Out-of-scope / Notes / Anti-refactor), and the substantive failure modes were sharper than S3-01's because S3-02 sits *on top of S3-01*: it must (i) avoid duplicating S3-01 surface, (ii) explicitly distinguish import-side vs call-side AST fences (S3-01 AC-6 covers imports; "direct node-to-node calls" needs the call-side complement), (iii) name a concrete *table* the tests parametrize over (the original Refactor step "table-drive the routing rules" is a hint, not a substrate), and (iv) tie the routing-table coverage to the *ledger transition table* `_LEGAL_TRANSITIONS` already shipped by S1-02 — otherwise the two tables silently drift.

Specific weaknesses found:

1. **AC count was 0 (`-` bullets, not `- [ ]` checkboxes).** Three bullets gave the executor no individually-verifiable assertion; the Validator pass downstream could not binary-pass-fail.
2. **No table substrate named.** "Pin every conditional edge" — every conditional edge of what shape? The story did not introduce the declarative `_ROUTING_TABLE` the tests parametrize over; without the table, "every valid edge has a test" can be satisfied by a thin parametrize over the four S3-01 AC-9 paths.
3. **Import-side vs call-side AST fence unresolved.** S3-01 AC-6 already lands "AST fence: no direct node-to-node imports"; the original S3-02 bullet "AST test rejects direct peer-node calls" overlaps but is broader (`Call` AST nodes, not `ImportFrom`). Without distinguishing the two fences explicitly, an executor would either duplicate S3-01 AC-6 (no value) or write a fence that catches calls but not imports (regression).
4. **No cross-table consistency.** Two transition tables exist in Phase 6 — the *ledger* transition table (`_LEGAL_TRANSITIONS` from S1-02) and the *routing* transition table (introduced here). Without a cross-table invariant, a future ledger amendment that adds a transition silently fails to expose it through the routing layer (soft-lock), and a routing amendment that emits an unsupported transition fails only at runtime via the model_validator.
5. **No exclusion-set discipline for HITL / entry-edge edges.** `awaiting_human_review → plan_ready` and the related HITL ledger transitions are owned by S4-01, not by the subgraph router. Without explicit `_HITL_LEDGER_EDGES` / `_ENTRY_LEDGER_EDGES` exclusion sets, the cross-table backward-consistency test would trip on every HITL edge and force the executor to wrongly include them in the routing table.
6. **No `MAX_RETRIES` exact-value pin.** S3-01 AC-10 asserts boundedness (no infinite loop); without an exact-value pin here, mutating `MAX_RETRIES = 3` to `MAX_RETRIES = 2` silently shortens the retry loop and passes S3-01 AC-10. The off-by-one comparison-operator drift (`==` instead of `>=`) is a second mutation class equally invisible at the S3-01 layer.
7. **No mutation-resistance encoding.** Every original AC was satisfiable by a trivial implementation: a routing layer that always returns `"completed"` would pass "every valid edge has a test" if the test parametrize is over the four happy-path edges only; a fence that walks for `ImportFrom` would pass "AST test rejects direct peer-node calls" without ever catching a `Call`. The new ACs encode the specific mutation classes (wrong cap, off-by-one, single-arm coverage, import-laundered call) so mutants die loud.
8. **No negative coverage.** "Invalid edges fail predictably" was vague — the test could assert one invalid pair and pass. Hypothesis-driven negative coverage over the closed `(SourceNode × PredicateName)` universe is the canonical "make the gap loud" discipline (S1-02 AC-5 negative property is the in-phase precedent).
9. **No projection from canonical four-path matrix.** S3-01 AC-9 ships the four-path matrix; without an explicit projection assertion, the matrix and the routing table can diverge silently (a path that runs end-to-end via direct dispatch but bypasses the routing table is silently OK from the matrix view).
10. **No closeout / contract-snapshot extension.** Every Phase-6 story so far extends `test_phase6_sut_contract_snapshot.py`; this story adds a routing-table shape (new public-ish contract between the subgraph and the SUT adapter) that needs the same defense.
11. **No isolation fence (kernel → plugin direction).** ADR-0002's "plugin behavior remains isolated" needs structural enforcement; without a fence walking `src/codegenie/` for imports of the plugin's routing module, a future kernel module could silently consume the table and break the plugin-local-topology decision.
12. **No generality discipline on the new AST fence.** Writing the fence with a hardcoded `plugins/vulnerability-remediation--node--npm/subgraph/nodes/` path makes Phase-7's plugin require a fence amendment. The glob-discovery pattern (S3-01 AC-15 precedent) makes Phase-7 inherit the protection by addition.
13. **Refactor step "table-drive the routing rules" was undefined.** Table-drive into *what*? A `dict`? A `Mapping`? A `frozenset` of triples? Without naming the substrate AND the read-only enforcement (`MappingProxyType`), the executor invents a shape with no concrete coverage handle and no read-only defense — the table becomes silently mutable at runtime.
14. **No `mypy --strict` closeout.** The closed `SourceNode` / `PredicateName` Literals are the load-bearing typecheck: a `dict[str, list[dict]]` slip would bypass narrowing and re-admit anaemic dicts at the routing layer (CLAUDE.md "newtype identifiers — never raw `str` for domain IDs" reduced to Literal-narrowing for in-module enums).
15. **No anti-refactor list.** The "make it pluggable" reflex was unguarded: an executor under deadline pressure could ship a `RoutingTableRegistry` or `@register_routing_row` decorator and earn no rule-of-three justification. The Phase-3 / S1-02 / S3-01 anti-refactor precedents are explicit; this story needs the same guard rails.

All in-place fixable, none requires re-running `phase-story-writer`. The story's structure (one-paragraph goal, ACs, TDD plan) survives — three bullets grew to 11 numbered ACs across 4 labeled sub-sections, the TDD plan was reordered with the 8-item anti-refactor block, References / Files-to-touch / Out-of-scope / Notes-for-implementer were added. Verdict: **HARDENED**.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (post-edit):** ship the **defensive coverage layer** for Phase-6 transition routing as a triple of additive concerns over S3-01 + S1-02: (1) the declarative `_ROUTING_TABLE` at the head of `routing.py` enumerating every `(source_node, predicate, dst_node, ledger_edge)` triple — table-driven dispatch, data over branching code, fourth concrete consumer of the closed-`Final`-mapping pattern (`_LEGAL_TRANSITIONS` + `_SEMANTIC_BOUNDARY_KINDS` + `_NODE_MODULES` are the prior three); (2) exhaustive mutation-resistant tests parametrizing over every table row (positive) and every Hypothesis-drawn `(source, predicate) ∉ table` pair (negative); (3) the *call-side* AST fence complementing S3-01 AC-6's *import-side* fence, with a conjunction guard asserting both are load-bearing; PLUS a cross-table consistency invariant linking `_ROUTING_TABLE` → `_LEGAL_TRANSITIONS` (forward, backward, and semantic-boundary projection) with explicit exclusion sets for HITL (S4-01-owned) and entry-edge (S2-02-owned) edges; PLUS `MAX_RETRIES = 3` exact-value + off-by-one pinning; PLUS kernel → plugin isolation fence; PLUS contract snapshot extension.
- **Status pre-validation:** `Ready` — never executed; never validated.
- **Status post-validation:** `HARDENED`.

### Authoritative sources

- **final-design.md** §"Decisions of record" item 4 (edges own control flow — the AST fence's whole reason for being); §"Main workflow" step 6 (the four-routing matrix this story projects through `_ROUTING_TABLE`); §"State model" (the seven ledger variants the cross-table consistency invariant ties to); §"Relationship to Phase 6.5" (Phase 6.5 may NOT depend on the routing topology — AC-9 isolation defense).
- **phase-arch-design.md** §"Failure modes" row 2 (node attempts direct peer call | AST test | CI failure — drives AC-3 call-side fence); §"Testing strategy" ("Reducer unit tests: exhaustive transition matrix"; "Static tests: graph nodes may import ports, not each other directly" — drives the *call-side* extension).
- **ADR-0002** §Decision (plugin-local topology — drives the file path scoping); §Consequences ("Existing plugin behavior remains isolated from future task classes" — drives AC-9 kernel → plugin direction fence + AC-10 generality).
- **ADR-0003** §Consequences (the integrity short-circuit path — `_ENTRY_LEDGER_EDGES` exclusion set documentation).
- **S3-01 hardened story** — the upstream substrate this story extends. S3-01 AC-6 (import-side fence) + AC-7 (routing purity) + AC-9 (four-path matrix) + AC-10 (bounded retry) are *consumed* here, not replaced; the table-drive refactor preserves S3-01 ACs byte-equal.
- **S1-02 hardened story** — `_LEGAL_TRANSITIONS` (the ledger-edge inventory cross-consistency consumes), the closed-`Final`-mapping precedent pattern this story mirrors.
- **S2-01 hardened story** — `_SEMANTIC_BOUNDARY_KINDS` (consumed by AC-6 semantic-boundary projection).

### Hardest design tension resolved

**`_ROUTING_TABLE` registry vs frozen closed-`Mapping`.** The Refactor hint "table-drive the routing rules" admits two readings: (i) a closed `Final[Mapping[...]]` at the head of `routing.py` (this story's choice); (ii) an open `@register_routing_row` decorator that lets future plugins extend the table. The S1-02 anti-refactor #2 + the S3-01 anti-refactor #3 + the existing precedent of `_LEGAL_TRANSITIONS` / `_SEMANTIC_BOUNDARY_KINDS` (both closed `Final` sets, not registries) plus the Phase-6 architectural decision that each plugin owns its OWN routing table (ADR-0002 plugin-local topology) makes the closed-Mapping the right shape. The rule-of-three threshold for a *registry over routing tables* would require Phase-6 + Phase-7 + Phase-8+ each shipping their own routing layer; the current state is one (Phase-6). Resolution: closed `Final[Mapping[...]]`, fourth concrete consumer of the closed-set pattern; the file path co-location (`routing.py`, not `routing_table.py`) is the Open/Closed substrate per-plugin.

**Second tension — AC-3 fence file name collision with S3-01 AC-6.** S3-01 AC-6 declares `tests/fence/test_subgraph_no_peer_calls.py` for the import-side fence. AC-3 here adds a *call-side* fence with the same logical concern (no direct node-to-node calls). The validated story names the new file `tests/fence/test_subgraph_no_peer_calls.py` AND a sibling `tests/fence/test_subgraph_no_peer_calls_callside.py` if the original is already taken — the Notes-for-implementer addresses this. The AC-4 conjunction guard pairs the two so both remain load-bearing.

**Third tension — HITL / entry-edge cross-table edges.** Without explicit exclusion sets, the cross-table backward-consistency test would force the routing table to include `awaiting_human_review → plan_ready` (owned by S4-01) and the integrity short-circuit (owned by S2-02). Resolution: declare `_HITL_LEDGER_EDGES` and `_ENTRY_LEDGER_EDGES` as `Final[frozenset[...]]` at the head of `routing.py`; the backward-consistency test takes the set difference. Adding an edge to either exclusion set is an explicit boundary amendment, not a silent fix.

## Four-lens findings (inline, no parallel subagents)

### Lens 1 — Coverage

| Finding | Severity | Resolution |
|---|---|---|
| AC-1 "every valid edge has a test" is unverifiable | block | Replaced with AC-1 (closed `_ROUTING_TABLE` with read-only enforcement + 5-key membership equality + `dst ∈ SourceNode ∪ {"__end__"}` membership) + AC-2 (table-driven dispatch test parametrized over every row). |
| Cross-table consistency absent | block | AC-6 forward + backward + semantic-boundary projection, with explicit `_HITL_LEDGER_EDGES` / `_ENTRY_LEDGER_EDGES` exclusion sets. |
| `MAX_RETRIES` exact-value unspecified | block | AC-8 exact-value + off-by-one + comparison-operator parametrization. |
| Negative coverage unspecified | block | AC-7 Hypothesis property over `(SourceNode × PredicateName)`; pair is either in `_ROUTING_TABLE` or explicitly marked `UnreachableInProduction`. |
| Four-path matrix projection unstated | block | AC-5 projection assertion: every canonical S3-01 path traces through a contiguous chain of `_ROUTING_TABLE` rows. |
| Closeout (contract snapshot + mypy) unspecified | harden | AC-11 extends `test_phase6_sut_contract_snapshot.py` with routing-shaped delta; `make typecheck` AC. |
| Public-surface allowlist unstated | harden | AC-9 part 1 — sentinel byte-equal-unchanged. |
| Kernel → plugin direction fence unspecified | harden | AC-9 part 2 — `tests/fence/test_routing_table_isolation.py` walks `src/codegenie/` for plugin imports. |
| Phase-7 generality discipline unspecified | nit | AC-10 glob-discovery fence + Notes. |

### Lens 2 — Test Quality

| Finding | Severity | Resolution |
|---|---|---|
| Import-side vs call-side fence ambiguity | block | AC-3 call-side fence (Call AST walk) + AC-4 conjunction guard. Notes-for-implementer names final-design.md item 4 verbatim. |
| Mutation-resistance encoding absent | block | Each AC includes a "Mutation thinking" note naming a specific mutation class the AC catches (wrong cap value, off-by-one operator, import-laundered call, single-arm coverage, etc.). |
| Test fixture builder shape unspecified | harden | `tests/unit/workflows/_routing_fixtures.py` is the closed-dispatch synthetic-input builder; predicate enumeration is the trampoline; AC-7 Hypothesis property requires `UnreachableInProduction` markers for gaps. |
| Single-file bundling temptation | harden | Anti-refactor #7 explicitly rejects a consolidated `test_subgraph_routing.py` covering all four ACs in one parametrize. |
| `MappingProxyType` read-only enforcement | harden | AC-1 part 1 asserts `TypeError` on mutation attempts. |
| Negative property uses closed universe (not arbitrary strings) | harden | `@given(st.sampled_from(get_args(SourceNode)), st.sampled_from(get_args(PredicateName)))` is the closed-set draw; an open `st.text()` draw would be a weaker property. |

### Lens 3 — Consistency

| Finding | Severity | Resolution |
|---|---|---|
| HITL edges silently included in cross-table test | block | `_HITL_LEDGER_EDGES` exclusion set + Out-of-scope statement + Notes-for-implementer. |
| Entry-edge integrity short-circuit silently included | block | `_ENTRY_LEDGER_EDGES` (empty but declared) + Notes; the integrity short-circuit is NOT a ledger transition. |
| Anti-refactor list absent | block | 8-item anti-refactor block — no registry, no Specification pattern, no `BaseRoutingDecision` ABC, no `RoutingResult` wrapper, no graph-topology-in-routing-table, no `__all__` leak, no consolidated test file, no fence replacement. |
| Phase-6.5 isolation directive | harden | AC-9 references final-design.md §"Relationship to Phase 6.5" verbatim. |
| Plugin path naming + Open/Closed substrate | harden | Notes for the implementer §"Why the table lives in `routing.py`" §"Why MappingProxyType". |
| Final/Literal narrowing discipline | harden | AC-11 part 2 explicit; Notes-for-implementer §"Why `RoutingDecision` is a frozen Pydantic model, not a `NamedTuple`". |

### Lens 4 — Design Patterns

| Finding | Severity | Resolution |
|---|---|---|
| "Table-drive the routing rules" Refactor undefined | block | `_ROUTING_TABLE: Final[Mapping[SourceNode, frozenset[RoutingDecision]]]` with `MappingProxyType` + `RoutingDecision` frozen Pydantic model + `Literal`-discriminated `predicate_name`. The fourth concrete consumer of the closed-`Final`-mapping pattern; mirrors `_LEGAL_TRANSITIONS` / `_SEMANTIC_BOUNDARY_KINDS` / `_NODE_MODULES`. |
| Plugin pattern temptation | harden | Anti-refactor #1 — no `RoutingTableRegistry` / `@register_routing_row` decorator. The rule-of-three threshold (per-plugin routing tables) is unmet until Phase-7 + Phase-8+. The closed-Mapping substrate is the precondition the future registry would build on. |
| Specification-pattern temptation | harden | Anti-refactor #4 — the `Literal["gate_passed", "gate_failed_retryable", ...]` PredicateName IS the specification language. Six predicates × 1-3 lines each = below Rule 2's three-similar-lines threshold. |
| `RoutingResult` wrapper temptation | nit | Anti-refactor #5 — LangGraph consumes bare `str` destinations; wrapping would force every caller to unwrap. |
| Newtype / Literal narrowing discipline | harden | Notes-for-implementer §"Why `RoutingDecision` is a frozen Pydantic model, not a `NamedTuple`" — Pydantic's discriminator + Literal machinery preserves narrowing under `mypy --strict`. |
| Composition over inheritance | harden | Anti-refactor #2 — no `BaseRoutingDecision` ABC; the `Literal`-discriminated `predicate_name` IS the variant discriminator (mirrors S1-02 sum-type discipline). |
| Functional core / imperative shell | harden | The table is data; the `_predicate_for` helper is a pure `match` with `assert_never`; the four `route_after_*` functions are one-line lookups. S3-01 AC-7 purity invariant is preserved. |

## Conflict resolution (priority: Consistency > Coverage > Test-Quality > Design-Patterns)

1. **`_ROUTING_TABLE` registry vs closed-Mapping** (Design-Patterns potential registry temptation vs Consistency reading of S1-02 / S3-01 anti-refactor precedent + ADR-0002 plugin-local). **Resolution:** closed-Mapping (Consistency wins). The rule-of-three threshold for a registry over routing tables is unmet; per-plugin routing tables live in per-plugin files per ADR-0002.

2. **Fence file name collision** (Test-Quality reading of S3-01 AC-6 naming vs Coverage need for a distinct call-side file). **Resolution:** sibling file `tests/fence/test_subgraph_no_peer_calls.py` (call-side) + retain S3-01 AC-6's filename for the import-side; if a name collision arises during execution, rename the call-side to `tests/fence/test_subgraph_no_peer_calls_callside.py`. The AC-4 conjunction guard pairs them so both remain load-bearing. Notes-for-implementer addresses the naming.

3. **HITL / entry-edge cross-table edges** (Consistency reading of S4-01 / S2-02 ownership vs Coverage backward-consistency test). **Resolution:** explicit `_HITL_LEDGER_EDGES` + `_ENTRY_LEDGER_EDGES` exclusion sets at the head of `routing.py`; backward-consistency test takes the set difference. Moving an edge across the boundary is an explicit amendment, not a silent fix (Consistency-driven).

4. **`MAX_RETRIES` pin (S3-01 AC-10 boundedness vs S3-02 exact-value)** (Test-Quality reading of complementary mutation classes). **Resolution:** S3-01 AC-10 (boundedness) + S3-02 AC-8 (exact-value + off-by-one + comparison-operator) are complementary; both remain load-bearing.

5. **Single-file consolidated test vs per-AC files** (Test-Quality reading of discoverability vs Coverage parametrize density). **Resolution:** per-AC files (Anti-refactor #7); mirrors S1-02's per-AC split pattern.

6. **Workflow-replay-determinism property ownership** (Coverage reading of S6-01 closeout). **Resolution:** S6-01 owns the property; this story owns the routing-table substrate. Out-of-scope statement is explicit.

7. **`__all__` leak temptation** (Anti-refactor #6 vs hypothetical SUT adapter convenience). **Resolution:** AC-9 part 1 — sentinel byte-equal-unchanged; the SUT adapter compiles the graph through `Plugin.build_subgraph()` and never reads `_ROUTING_TABLE` directly.

No `NEEDS RESEARCH` flag remained after critic synthesis.

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` flag from any lens remained unresolved after Stage-2 synthesis. The closed-`Final`-mapping pattern is well-established in this codebase (three precedents); the call-side AST fence is a standard mutation of the existing import-side fence pattern; Hypothesis closed-universe draws over `Literal` arguments via `get_args` are idiomatic.

## Stage 4 — Edits applied

### Pre-validation story (17 lines)

```markdown
# S3-02 — Transition table tests

**Status:** Ready
**Goal:** Pin every conditional edge and forbid direct node-to-node calls.

## Acceptance criteria

- Every valid edge has a test.
- Invalid edges fail predictably.
- AST test rejects direct peer-node calls.

## TDD plan

Red: missing-edge and direct-call tests.
Green: implement transition router.
Refactor: table-drive the routing rules.
```

### Post-validation story (HARDENED — see file)

| Section | Before | After |
|---|---|---|
| Status line | `Ready` | `HARDENED` + `Validated:` line + `Depends on:` (three explicit cross-story deps + a "This story does NOT" disambiguation) |
| Goal | 1 sentence | 1 paragraph + 1 deferral paragraph naming the table, the four cross-cutting concerns (table substrate, exhaustive coverage, call-side fence, cross-table consistency), and the explicit additive relationship with S3-01 + S1-02 |
| References | absent | 13-entry block citing final-design.md / phase-arch-design.md / ADRs/0002 / ADRs/0003 / High-level-impl.md / sibling stories S3-01, S1-02, S2-01, S1-01, S4-01, S5-01, S6-01 / closed-`Final`-mapping precedents `_LEGAL_TRANSITIONS` + `_SEMANTIC_BOUNDARY_KINDS` + `_chain.py` |
| Acceptance criteria | 3 bullets (0 checkboxes) | 11 numbered checkbox ACs across 4 labeled sub-sections (declarative routing table + dispatch, cross-table consistency, negative coverage + retry pin, generality + closeout) |
| Files to touch | absent | 13-line list — `routing.py` modify + 8 new unit/integration test files + 3 new fence files + 2 contract-snapshot modifications |
| TDD plan | 3 sentences | Red phase (12-step sequence with the substrate ACs landing before integration assertions) + Green (concrete impl list naming `_ROUTING_TABLE`, `MappingProxyType`, `_predicate_for`, the exclusion sets) + Refactor (4-item cleanup list) + Anti-refactor (8 items) |
| Out of scope | absent | 6-item list — routing functions (S3-01), HITL edges (S4-01), entry-edge integrity (S2-02), workflow-replay property (S6-01), Phase-7+ registry, sibling abstractions |
| Notes for implementer | absent | 10-paragraph block — table-file co-location, MappingProxyType rationale, Pydantic vs NamedTuple, call-side fence separability, cross-table drift hazard, Hypothesis unreachability markers, MAX_RETRIES three-mutation-class coverage, contract-snapshot inclusion of exclusion sets, Phase-7 inheritance via glob, Phase-9 checkpointer-agnosticism, implementation-order suggestion |

## Verdict

**HARDENED** — every four-lens finding either landed as an AC, an Anti-refactor item, an Out-of-scope statement, a Notes-for-implementer paragraph, or a Conflict-resolution rationale. All seven conflicts resolved with explicit priority-order reasoning. No `NEEDS RESEARCH` flag remained open. The story is ready for `phase-story-executor`.
