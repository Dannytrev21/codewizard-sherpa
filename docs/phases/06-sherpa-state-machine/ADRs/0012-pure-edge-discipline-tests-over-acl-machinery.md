# ADR-0012: `@pure_edge` for routing + per-node unit tests — no field-ACL or docstring-AST machinery

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** routing · testing · determinism
**Related:** [ADR-0002](0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md)

## Context

Two of the three lens designs shipped machinery to enforce "nodes read what they declare and write what they declare":

- **Best-practices** required every node to declare a docstring `Reads:` and `Writes:` block, then ran an AST validator at CI time to walk the node body and assert the declared accesses match. `critique.md best-practices.2` killed it: the AST walker is ~80 LOC of hand-rolled dataflow that doesn't know about `getattr(state, name)`, chained access, tuple destructuring; a passing-but-wrong docstring is unfalsifiable. Worse — the test verifies *syntactic appearance*, not behavior, exactly the kind of "lint that becomes truth" CLAUDE.md Rule 9 warns against.
- **Security** shipped per-field `read_acl` / `write_acl` with both runtime + AST enforcement. `critique.md security.3` killed it: the ACL machinery requires every node to return `ReducerCall(...)` instead of `VulnLedger`, breaking LangGraph's idiom and `langgraph-cli` introspection.

Both designs were trying to solve a real problem: nodes that mutate state outside their declared scope are a vector for replay non-determinism and silent state corruption. But both solutions verified *appearance*, not *behavior*. The synthesizer's response (`final-design.md §Goal 19` + `final-design.md §Conflict-resolution row 13`):

1. **Conditional-edge purity** is enforced — the `@pure_edge` decorator AST-walks the function body at import time and rejects imports of `random | time | os | datetime` (whitelist: `datetime.fromisoformat`). This catches the only structurally-detectable purity violation (importing a non-deterministic module).
2. **Routing-decision dependency on state projections** is verified by *per-predicate unit tests* that mutate non-consumed fields and assert label invariance — verifying behavior, not syntax (closes `critique.md security-attack-4`).
3. **Per-node behavior** is verified by *per-node unit tests* that construct an input `VulnLedger`, mock the upstream Phase 3/4/5 engine at the import boundary, invoke the node, and assert the returned ledger's fields. This is the "tests verify intent, not syntax" replacement (CLAUDE.md Rule 9).

The runtime in-place-mutation hook (ADR-0002) is the complementary safety net — it catches a class of violation that no static test can.

## Options considered

- **Field-ACL with runtime + AST enforcement.** Security's pick. Heavy machinery; fights LangGraph idiom; ~150 LOC.
- **Docstring `Reads:`/`Writes:` with AST validator.** Best-practices' pick. Encodes intent in docs; AST walker is fragile; verifies appearance.
- **No declared access at all.** Implicit; relies on review discipline; no automated check.
- **`@pure_edge` for edges + per-node unit tests + runtime mutation hook.** Combines a small static AST check (edges only — the smallest case) with behavior-verifying unit tests at the node level and a runtime safety net for the mutation case the static checks can't catch.

## Decision

The discipline ships in three layers:

1. **`@pure_edge` decorator** (`src/codegenie/graph/edges.py`): every conditional-edge predicate is decorated. At import time, the decorator AST-walks the function body and raises `ImpureEdge` if it sees an import of `random | time | os | datetime` (whitelist: `datetime.fromisoformat` for ISO 8601 parsing). It does *not* try to verify "depends only on a state projection" via AST — that's too brittle.
2. **Per-predicate unit tests** (`tests/graph/test_edge_label_depends_only_on_projection.py`): for each predicate, the test mutates non-consumed fields (e.g., `AttemptSummary.created_at`, `events[].at`) and asserts the label is invariant. Closes `critique.md security-attack-4` (synthetic-state property tests vs production timestamp-bearing states).
3. **Per-node unit tests** (`tests/graph/test_nodes/test_<node>.py` — one file per node): construct an input `VulnLedger`, mock the upstream Phase 3/4/5 engine at the import boundary, invoke the node, assert the returned ledger's fields.

No docstring-`Reads:`/`Writes:` AST validator. No field-level `read_acl` / `write_acl` machinery. The data-model file does record `Reads:` and `Writes:` annotations as **prose comments only** (`phase-arch-design.md §Data model`); they are documentation, not enforcement.

## Tradeoffs

| Gain | Cost |
|---|---|
| Tests verify behavior (what the node returns from a known input), not syntactic appearance (what fields are mentioned in source) — honors CLAUDE.md Rule 9 | A node that reads a state field but produces an output that doesn't visibly depend on it is not caught by behavior tests — only by the mutation hook (ADR-0002) |
| ~80 LOC of AST-walker machinery saved; one decorator that does the bare minimum static check on edges | The `@pure_edge` AST check is conservative (it only catches imports); a function that calls `time.time` indirectly through a helper passes the static check |
| Per-node mocking is small and focused — each test file is ~30–60 LOC and trivially extensible by future node authors | One test file per node is N test files (currently 10); the discipline must be enforced by directory layout and a CI lint that asserts the file exists |
| The runtime mutation hook (ADR-0002) catches the dataflow case the static checks can't — `state.events.append(...)` raises loudly | Three safety layers (decorator + per-predicate test + per-node test + mutation hook) is more moving parts than a single mechanism; reviewers must understand which catches what |

## Consequences

- The Layer 0 static checks (`phase-arch-design.md §Testing strategy`) ship the small static checks: topology golden, fence-CI, no-cross-node-imports, no-anthropic-in-graph, no-Any-in-state, no-self-confidence-field. None of them try to verify "this function reads X."
- The Hypothesis property test (`test_edges_determinism.py`) runs 10k synthetic `VulnLedger` instances against each predicate to verify referential transparency — orthogonal to the projection test.
- The Layer 1 per-node unit tests are ~60% of test LOC — the workhorse layer.
- A reviewer who adds a node with no test file fails the directory-layout lint immediately.
- The data-model `Reads:`/`Writes:` annotations remain as prose for human reading but are *not* enforced — clarifying that they are documentation, not a contract, is part of the implementer-notes block in story files.

## Reversibility

**High.** Adding back a field-ACL or docstring validator is mechanical (the precedent designs are still in the lens-design docs); none of the production code depends on the absence of those mechanisms. Removing the `@pure_edge` decorator would silently re-open the non-determinism gap and would be caught by Hypothesis property tests within one CI run.

## Evidence / sources

- [`../final-design.md` §Goals row 19 "Tests verify intent, not syntax"](../final-design.md)
- [`../final-design.md` §Synthesis ledger row 13 "Field-ACL machinery"](../final-design.md)
- [`../final-design.md` §Component 4 "@pure_edge"](../final-design.md)
- [`../phase-arch-design.md` §Component 4 "@pure_edge predicates"](../phase-arch-design.md)
- [`../phase-arch-design.md` §Testing strategy](../phase-arch-design.md)
- [`../critique.md` §best-practices.2 + §security.3](../critique.md) — the two "verify appearance, not behavior" critiques that this ADR closes
- CLAUDE.md global rule §9 — "Tests verify intent, not just behavior"
