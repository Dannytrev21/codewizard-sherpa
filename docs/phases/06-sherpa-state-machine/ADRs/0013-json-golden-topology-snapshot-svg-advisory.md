# ADR-0013: JSON-form golden-graph topology is the CI gate; SVG is committed for review only

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** testing · golden-files · langgraph-cli
**Related:** [ADR-0001](0001-lazy-singleton-build-vuln-loop-factory.md)

## Context

Catching unintended topology changes (a stray edge, a renamed node, a mis-wired conditional branch) is one of the cheapest and highest-value tests Phase 6 can ship — the topology is small, deterministic, and central. Best-practices proposed a *both-formats* golden: render the graph to both JSON and SVG via `langgraph-cli`, commit both, diff both at CI time.

`critique.md best-practices-hidden-1` killed the SVG-as-gate idea: `langgraph-cli` rendering is not a documented stable contract. SVG output includes node coordinates that depend on the layout algorithm version — every `langgraph-cli` upgrade re-flows the SVG. A Renovate PR that bumps `langgraph-cli` from `0.0.x → 0.0.y` would flip the CI gate red on every dependency update.

`critique.md best-practices-hidden-2` raised the same concern about JSON output, but more weakly: `graph.get_graph().to_json()` is the LangGraph API surface and its key set is more likely to be stable than SVG layout. With a canonical key sort, the JSON form is a viable stable contract.

The synthesizer's choice (`final-design.md §Goals row 17` + `final-design.md §Component 8`): **JSON-only as the CI gate; SVG committed for human review but not a CI failure on drift.**

## Options considered

- **Both SVG and JSON as CI gates (best-practices' original).** Catches more drift; flips on every `langgraph-cli` version bump; high false-positive rate.
- **SVG only.** Same false-positive issue; harder to diff machine-readably.
- **No topology gate.** Re-wiring the graph is a load-bearing change; nothing catches it as long as the predicate tests still pass.
- **JSON-only as gate; SVG committed for review.** Stable contract for the gate; visual review for humans at PR time without the false-positive churn.

## Decision

`tests/graph/test_topology_golden.py` exports `build_vuln_loop(checkpointer=InMemorySaver()).get_graph().to_json()`, recursively sorts dict keys, serializes with `separators=(",", ":")`, and diffs against `tests/golden/vuln_loop_topology.json`. **The JSON diff is the CI gate.** A separate command `codegenie loop render --out tests/golden/vuln_loop_topology.svg` writes both `.json` (CI gate) and `.svg` (committed at `docs/phases/06-sherpa-state-machine/vuln_loop.svg` for human review). The SVG is committed, but **a diff in the SVG does not fail CI.** Updating either golden is a deliberate `pytest --update-golden` invocation, not casual.

## Tradeoffs

| Gain | Cost |
|---|---|
| The CI gate is stable across `langgraph-cli` version bumps — Renovate PRs don't flip the gate red | The SVG can drift unnoticed between renders — reviewers may glance at a stale SVG when reviewing a topology change |
| A topology change requires an explicit `--update-golden` step, forcing the author to look at the diff and explain it in PR review | Two artifacts to keep in sync — JSON for the gate, SVG for the eye; humans must remember to re-render the SVG when they bump the JSON |
| `graph.get_graph().to_json()` is a documented LangGraph API; canonical key sort makes the output reproducible | If a future LangGraph version *does* change the `to_json()` schema, the gate flips; we accept this and update the golden as a deliberate step |
| `codegenie loop render` is the operator-facing topology dump tool — `langgraph-cli` is treated as a dev-time renderer, not a production primitive | Renaming a node still requires an `--update-golden`; the test catches accidental renames but not malicious ones |

## Consequences

- **`tests/golden/vuln_loop_topology.json`** is the CI gate file. Format: canonical key-sorted JSON, `separators=(",", ":")`, UTF-8, no trailing newline.
- **`docs/phases/06-sherpa-state-machine/vuln_loop.svg`** is the committed SVG for human review. Not a CI gate.
- A new `--update-golden` flag is added to the test runner; running it requires intent and the resulting diff appears in the PR — the author must justify.
- Phase 7's `tests/golden/distroless_loop_topology.json` is a *new file*, not an edit to the vuln topology; Phase 7's introduction adds a sibling without touching this golden.
- `codegenie loop render` is the operator dump command; it's idempotent and is the single integration point with `langgraph-cli`. Phase 9 may replace `langgraph-cli` (`temporal-ui` or analog); Phase 6 does not pre-design that swap.
- The `to_json()` dependency is recorded under Phase 6's design Open Questions; the LangGraph version is pinned (`>= 0.2.x`) in `pyproject.toml` to bound the surface.

## Reversibility

**High.** Adding the SVG to the CI gate is one test addition; the runtime cost is low (a render per CI run). Removing the JSON gate altogether is a one-line delete; would lose the topology safety net but be easy to undo. The committed-SVG-for-review shape is the durable compromise.

## Evidence / sources

- [`../final-design.md` §Goals row 17 "langgraph-cli posture"](../final-design.md)
- [`../final-design.md` §Synthesis ledger row 11 "Golden topology test"](../final-design.md)
- [`../final-design.md` §Component 8 "Golden-graph topology snapshot"](../final-design.md)
- [`../phase-arch-design.md` §Component 10 "Golden-graph topology snapshot"](../phase-arch-design.md)
- [`../phase-arch-design.md` §Edge cases #11](../phase-arch-design.md)
- [`../critique.md` §best-practices-hidden-1 + §best-practices-hidden-2](../critique.md)
