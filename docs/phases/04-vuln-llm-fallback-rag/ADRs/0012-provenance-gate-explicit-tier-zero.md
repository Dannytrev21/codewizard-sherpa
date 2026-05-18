# ADR-0012: `ProvenanceGate` as an explicit tier-0 gate — refuse non-app-layer CVEs before any LLM tokens are spent

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** specification-pattern · refuse-mode · tier-zero · cost-discipline · adr-0038
**Related:** [production ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md) · ADR-0010 (this phase)

## Context

[Production ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md) introduces `vuln.provenance` as a query-time join over gather-time SBOMs, with `Unknown` triggering refuse-mode (no remediation attempted). Phase 3 ships the npm-side refuse-mode for the recipe path. Phase 4 must decide where in the dispatch order the provenance check fires.

The three design lenses split: performance never mentioned provenance (the LLM tier would happily spend tokens on a base-image CVE that should never have reached it); security shipped an explicit gate before any LLM call; best-practices inherited the Phase 3 `applies_to` short-circuit implicitly. The critic was clear: "both security and best-practices call out that ADR-0038's `vuln.provenance == Unknown` must refuse *before* any LLM call" (`critique.md §"Things this design missed"` on performance).

The honest framing is that provenance is *tier-0* — it runs before recipe, RAG, or LLM. Implicit inheritance from Phase 3 (best-practices) makes the gate's existence dependent on Phase 3's refuse-mode firing first, which couples Phase 4's spend-protection to Phase 3's recipe path. An explicit gate as the first step in `FallbackTier.run` decouples them.

Phase 7 owns the full multi-adapter provenance primitive (base-image adapters that turn `Unknown` into structured provenance). Phase 4 must ship *something* that uses what Phase 3 has (`NpmVulnProvenanceAdapter`) without forking the primitive.

## Options considered

- **Implicit inheritance from Phase 3's `applies_to` short-circuit** (best-practices lens). Phase 3 returns `NotApplicable` for base-image CVEs; Phase 4 sees nothing to do. **Pattern:** Implicit gate via existing return path. Couples Phase 4 spend-protection to Phase 3 logic; the gate's existence is invisible in Phase 4 code.
- **No provenance check** (performance lens). Trust upstream. **Pattern:** No gate. The LLM spends tokens on out-of-scope CVEs.
- **Explicit tier-0 `ProvenanceGate.classify(...)` at the top of `FallbackTier.run`** (security lens). Calls Phase 3's `NpmVulnProvenanceAdapter`; refuses with `Refused(PROVENANCE_NOT_APP_LAYER)` for any provenance not in `{AppDirect, AppTransitive, AppVendored, Both}`. **Pattern:** Specification pattern (named gate rule) + Tier-zero short-circuit.
- **Provenance-aware retrieval / planning** (alternative). Provenance flows as a typed field through the dispatch; each tier checks. **Pattern:** Cross-cutting concern. More spread; harder to assert "no LLM tokens on base-image" as a single test.

## Decision

`ProvenanceGate` runs as **tier-0** in `FallbackTier.run`, before recipe, RAG, or LLM. It delegates to the plugin's `NpmVulnProvenanceAdapter` (Phase 3 generalised). Anything not in `{AppDirect, AppTransitive, AppVendored, Both}` returns `RecipeApplication.Refused(reason=PROVENANCE_NOT_APP_LAYER)` immediately — **no LLM tokens spent, no RAG queried, no recipe matched**. Phase 7 will ship the base-image adapters that turn `Unknown`/`BaseImage` into actionable provenance; Phase 4 ships a Phase-4-scoped consumer that refuses on anything non-app-layer. **Pattern:** Specification pattern (named rule: `is_app_layer ⇔ provenance ∈ {AppDirect, AppTransitive, AppVendored, Both}`) + Tier-zero short-circuit. Asserted by event-absence: `tests/integration/test_phase4_provenance_short_circuits.py` mocks `LeafLlm` with a `pytest.fail` side-effect and asserts a base-image CVE refuses without firing it.

## Tradeoffs

| Gain | Cost |
|---|---|
| Zero LLM tokens spent on out-of-scope CVEs — the most expensive failure mode is structurally impossible | Phase 7's full multi-adapter primitive is needed to *resolve* `Unknown` to actionable provenance; Phase 4 refuses anything Phase 3's npm adapter can't classify as app-layer |
| The gate is explicit in `FallbackTier.run` — readers see the check; it's not buried in Phase 3 conditional return paths | Slight duplication: Phase 3 also refuses base-image CVEs; both layers have the check. Acceptable: defense-in-depth at the cost boundary |
| Audit event `ProvenanceClassified(kind)` always fires — operator-portal sees the classification regardless of outcome | `Refused(reason=PROVENANCE_NOT_APP_LAYER)` requires HITL escalation via Phase 3's universal fallback — operator workload grows for the BaseImage CVE class |
| The Phase-4-scoped `_AppLayerOnlyProvenance` consumer is a small, named adapter; Phase 7's full primitive replaces it without changing `FallbackTier` | Phase 7 must respect the same `Provenance` sum type; widening the sum is a Phase-7-amendment ADR |
| `tests/integration/test_phase4_provenance_short_circuits.py` proves the gate by event-absence — *the* primary test that the cost protection holds | Event-absence tests are coupled to event names; renaming `LeafInvoked` to `LeafCalled` would silently make the test pass — mitigated by enforced event-kind allowlist in `tests/fence/test_event_kinds_complete.py` |

## Pattern fit

The toolkit's Specification pattern fits: `is_app_layer` is a named, testable, composable rule over `Provenance` sum-type variants. The classification logic is one place; the consumer (`FallbackTier.run`) just calls `is_app_layer(provenance)` (or its inlined equivalent).

The Tier-zero short-circuit is the structural commitment: provenance check is the *first* step, not the third. In tagged-union dispatch terms, the `Refused(PROVENANCE_NOT_APP_LAYER)` arm exists before the recipe/RAG/LLM dispatch even begins.

## Consequences

- `FallbackTier.run` begins with `provenance = self.provenance.classify(advisory, repo_ctx)`. The match on `Provenance` is the first decision.
- Audit emissions: `ProvenanceClassified(kind)` always; `Refused(reason=PROVENANCE_NOT_APP_LAYER, provenance_kind=...)` on non-app-layer.
- The integration test `tests/integration/test_phase4_provenance_short_circuits.py` mocks the `LeafLlm` adapter with `pytest.fail` and asserts the test passes on a base-image CVE input (the leaf was never invoked).
- Phase 7's distroless plugin adds base-image adapters (`DockerfileBaseImageAdapter`, etc.) registered against the `VulnProvenanceAdapter` Protocol; Phase 4's `ProvenanceGate` consumes whichever adapters the resolved plugin provides — no Phase 4 code change.
- `Provenance` sum type variants (`AppDirect | AppTransitive | AppVendored | BaseImage | RuntimeBundled | Both | Unknown`) are stable per [ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md); Phase 7 may add variants (additive sum-type widening at *that* phase's local sum, not Phase 3's `RecipeOutcome`).
- The Phase-4-scoped `_AppLayerOnlyProvenance` consumer is a documented constant inside `provenance_gate.py` named `_APP_LAYER_PROVENANCE_KINDS: Final[frozenset[ProvenanceKind]] = frozenset({"AppDirect", "AppTransitive", "AppVendored", "Both"})`; Phase 7 may expand by registering its own consumer (or by phase-amending the constant).
- Performance envelope: `ProvenanceGate.classify` is ≤ 5 ms (file reads cached by Phase 3); negligible vs leaf-call cost.

## Reversibility

**Low.** Removing the gate is a code edit but reintroduces the "LLM tokens spent on base-image CVE" failure mode — a load-bearing cost commitment break. Moving the gate later in the dispatch (e.g., after RAG) is a Phase-4 amendment ADR; risks the same failure mode at smaller scale. Phase 7's broadening of `_APP_LAYER_PROVENANCE_KINDS` (e.g., admitting `BaseImage` for distroless migrations) is a phase-amendment ADR with explicit reasoning.

## Evidence / sources

- `../final-design.md §Component 6 — ProvenanceGate`
- `../final-design.md §Goal "Allowed network egress"` + `§"Audit completeness"`
- `../phase-arch-design.md §Component 6 — ProvenanceGate`
- `../phase-arch-design.md §Goals — G7`
- `../phase-arch-design.md §Scenarios — Scenario 3` (Provenance gate refuses)
- `../critique.md §"Things this design missed"` (performance missed provenance refuse-mode)
- [production ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md) (the primitive Phase 7 will complete)
