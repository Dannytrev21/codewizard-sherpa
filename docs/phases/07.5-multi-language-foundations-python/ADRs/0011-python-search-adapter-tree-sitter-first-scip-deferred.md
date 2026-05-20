# ADR-0011: The Python search adapter ships tree-sitter-first; `scip-python` is deferred, `ALLOWED_BINARIES` untouched

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** Adapter pattern · Structural typing (Protocol) · scope-minimization · YAGNI · security
**Related:** [ADR-0008](0008-python-depgraph-pure-parsing-no-resolution.md), [ADR-0010](0010-conformance-tier-parameterized-over-live-registry.md), [production ADR-0032](../../../production/adrs/0032-language-search-adapters.md), [production ADR-0037](../../../production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)

## Context

[ADR-0032](../../../production/adrs/0032-language-search-adapters.md) defines language search adapters — `ImportGraphAdapter` (mandatory), `DepGraphAdapter`, `TestInventoryAdapter`, and an optional `ScipAdapter` — as the bridge from generic context queries to language-specific indexers. Python needs adapters wired through the `vulnerability-remediation--python--pip` plugin's `contributes.adapters` map.

The three lens designs disagreed (CONFLICT CR-6 in [final-design.md §Synthesis ledger](../final-design.md#synthesis-ledger)). The performance lens wanted `scip-python` *in*, as the precision rung of a SCIP→tree-sitter ladder. The security lens *recommended deferring* `scip-python` (its Open-Q3) — yet built a full TB-4 jail, env-scrub, degrade-ladder, and cgroup-memory-cap proposal around it anyway. The critic flagged the self-contradiction ([critique.md §Attacks on the security-first design, problem 4](../critique.md)): "half the security architecture defends a component the design recommends deferring."

`scip-python` is a large, pyright-based, network-capable binary. Shipping it means a new `ALLOWED_BINARIES` entry, a subprocess jail, a supply-chain surface, and a memory-cap question — substantial machinery. The security lens *also* asserted an "ADR-0033 amendment to ADR-0032" changing `confidence() -> float` to a sum type; the critic showed no such amendment exists, and inventing one would be a cross-cutting silent edit to the Protocol every shipped adapter implements ([critique.md §Attacks on the security-first design, problem 1](../critique.md)).

## Options considered

- **Option A — ship `scip-python` in Phase 7.5** as the precision rung, jailed via `run_external_cli`. **Pattern:** Adapter + the SCIP/tree-sitter Strategy ladder — but it adds a binary, a jail, and a supply-chain surface for a precision tier the phase does not need to prove the language axis.
- **Option B — ship `scip-python` *and* change `confidence()` to a sum type** via an asserted ADR-0032 amendment. **Pattern:** none — the amendment does not exist; changing the float-returning Protocol every shipped adapter implements is a silent edit to frozen pre-Phase-7 surface.
- **Option C — ship a tree-sitter-backed `ImportGraphAdapter` (+ `DepGraphAdapter` / `TestInventoryAdapter`); defer `scip-python` to a fast-follow; keep `confidence() -> float` as ADR-0032 specifies.** **Pattern:** Adapter + Structural typing (Protocol) + scope-minimization.

## Decision

The Phase 7.5 Python search adapter is **tree-sitter-backed** — an `ImportGraphAdapter` (mandatory under ADR-0032) plus `DepGraphAdapter` and `TestInventoryAdapter`, all always-fresh, in-process, no external binary. `scip-python` and its `ScipAdapter` are **deferred to a fast-follow** (ADR-0032 explicitly makes `ScipAdapter` optional; the minimum adapter surface is `ImportGraphAdapter` + `TestInventoryAdapter`). `confidence()` stays the **ADR-0032-as-written `-> float`** — the synthesis does **not** invent an "ADR-0033 amendment to ADR-0032." `ALLOWED_BINARIES` is **untouched** — `scip-python` is not added; a closed-set regression test asserts this. The `scip-python` fast-follow, when scheduled, will need its own `ALLOWED_BINARIES` amendment under the Phase 2 omnibus ADR-0001.

## Tradeoffs

| Gain | Cost |
|---|---|
| `ALLOWED_BINARIES` is untouched — no new jail surface, no subprocess, no supply-chain entry, no cgroup-memory-cap question | Python loses symbol-precise `scip.refs` until the fast-follow lands — tree-sitter is the always-fresh floor, not the precision ceiling |
| The Python adapter is always-fresh and in-process — no staleness, no external-binary failure mode | tree-sitter import-graph resolution is shallower than SCIP's symbol-precise references — acceptable; ADR-0032's *minimum* surface excludes `ScipAdapter` |
| `confidence() -> float` stays as ADR-0032 specifies — no cross-cutting silent edit to the Protocol every shipped adapter implements | The float confidence is coarser than a sum type would be — but changing it is a Phase-pre-7 frozen-surface migration, not a Phase 7.5 license |
| The phase's job — prove the language axis extends by addition — is fully served by tree-sitter; SCIP precision is a Phase-8-Planner concern | A precision-sensitive Python workflow must wait for the fast-follow; Phase 7.5 ships the floor, not parity with Node's SCIP-backed search |
| Deferring drops an entire security apparatus (jail, env-scrub, degrade-ladder, memory-cap) that would otherwise be built for a component not in the phase | The deferral is a scheduling debt — the fast-follow (closeout story or Phase 8 preamble) must actually be scheduled |

## Pattern fit

The Python adapter is the toolkit's **Adapter pattern** done correctly — it *translates* generic query primitives (`import_graph.reverse_lookup`, `dep_graph.consumers`) into Python-specific tree-sitter walks; it is not a forwarder. It is wired as a **Structural typing (Protocol)** implementation of ADR-0032's adapter Protocols — no inheritance. The load-bearing decision, though, is the *anti-decision*: **not** building the `scip-python` apparatus. The tempting pattern was the performance lens's SCIP→tree-sitter **Strategy + Chain-of-responsibility ladder** — a real future want, but the toolkit's **premature pluggability** warning applies precisely here: building a multi-rung precision ladder, plus a jail for the rung you recommend deferring, is machinery ahead of need. The critic's sharpest finding was the security lens building "an elaborate TB-4 jail … for a component the same design recommends deferring out of the phase." Deferring `scip-python` is YAGNI applied honestly: ship the always-fresh floor, schedule the precision rung when a workflow needs it.

## Consequences

- `ALLOWED_BINARIES` stays a closed set with `scip-python` absent — a closed-set regression test asserts this; the `fence` job confirms no `FORBIDDEN_LLM_SDK` rode in.
- No subprocess jail, env-scrub, or memory-cap machinery is built this phase — the entire `scip-python` security apparatus is unnecessary.
- `confidence()` stays `-> float`; ADR-0032's degradation logic (a low float drives the Bundle Builder's declared-fallback) works unchanged — no Protocol every shipped adapter implements is touched.
- The `scip-python` fast-follow is a scheduling debt with a known shape: a new `ScipAdapter`, an `ALLOWED_BINARIES` amendment under Phase 2 ADR-0001, and a subprocess jail — sequencing (Phase 7.5 closeout vs. Phase 8 preamble) is left to the story-writer (open question 4).
- Python's tree-sitter adapter is registered through the existing plugin `contributes.adapters` mechanism — unchanged.

## Reversibility

**High.** Deferring `scip-python` is the absence of code — there is nothing to unwind. Adding the `ScipAdapter` later is a pure addition: a new adapter class, a new `ALLOWED_BINARIES` row (a sanctioned amendment), a new plugin `contributes.adapters` entry. The tree-sitter adapter stays as the always-fresh floor even after SCIP lands — ADR-0032's ladder *expects* both rungs. The one thing that would be costly to reverse is the rejected security-lens move — inventing an ADR-0032 `confidence()` amendment — and that is rejected precisely because it is a hard-to-reverse cross-cutting change to frozen surface.

## Evidence / sources

- [final-design.md §Components — Python search adapter](../final-design.md#components), §Synthesis ledger CR-6, §Departures item 4, §Path to production end state (deferred ADRs)
- [phase-arch-design.md §Component design — Python search adapter](../phase-arch-design.md#component-design), §Goals G8, §Non-goals (`scip-python` deferred)
- [critique.md §Attacks on the security-first design](../critique.md) — problem 1 (invented ADR-0032 amendment), problem 4 (jail for a deferred component)
- [production ADR-0032](../../../production/adrs/0032-language-search-adapters.md) — adapter Protocols; `ScipAdapter` optional; `confidence() -> float`
- [production ADR-0037](../../../production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md) — SCIP's role in the analysis funnel; Phase 2 omnibus ADR-0001 — the `ALLOWED_BINARIES` amendment path
