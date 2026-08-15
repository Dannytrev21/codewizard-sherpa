# Validation report — S2-03 `_ADAPTER_DISPATCH_ORDER` `Final` tuple + `Ecosystem`-sorted intra-layer iteration

**Story:** [`S2-03-adapter-dispatch-order-tuple.md`](../S2-03-adapter-dispatch-order-tuple.md)
**Verdict:** **HARDENED (retrospective)** — story shipped `Done` on 2026-05-19 in a single attempt (commit `ecbb0a0`); four-critic pass finds no blockers, one missing-AC anchor for an already-shipped-and-green test (AC-10), and three design-pattern observations that carry as `Notes for the implementer` / `Validation notes` — not new ACs (Rule 2).
**Validator run:** 2026-07-26
**Depth:** default (Stage 3 research not fired — no `NEEDS RESEARCH` findings; the surface is a `Final` tuple + one 8-line iteration helper).

## Why retrospective

The scheduled `story-validation-corrector` job selects the lowest-numbered story lacking a `_validation/{ID}.md` report. S2-03 was implemented and merged (`ecbb0a0 — feat(phase7/S2-03): GREEN — _ADAPTER_DISPATCH_ORDER Final tuple + Ecosystem-sorted iteration`) before the validator ran on it. This report exercises the four critics against the story-as-written and the shipped code, then applies edits that preserve every checked-off AC (Rule 12: shipped evidence is authoritative).

## Critics — findings

### Coverage — HARDENED (one missing AC anchor for a shipped test)

Every subgoal of the Goal statement traces to an AC; the load-bearing intra-layer ordering discipline (BP-1 closure) is pinned by AC-4 at the helper level. The one gap: the shipped test suite includes `test_iter_adapters_for_layer_set_is_reexported_from_package` — a real green test — with no numbered AC in the story to trace it to. Without an AC anchor, a future refactor pruning `__all__` would fail only the stray test, not the story's acceptance gate.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| C-1 | harden | The shipped test `test_iter_adapters_for_layer_set_is_reexported_from_package` (line 123 of `test_assembly_dispatch_order.py`) asserts `pkg.iter_adapters_for_layer_set is iter_adapters_for_layer_set` AND `"iter_adapters_for_layer_set" in pkg.__all__`, but no numbered AC pins it. Impl outline step 2 does say "extend `__init__.py` to re-export", but re-exports are process, not spec — an AC would trace the test to acceptance. | **Edited:** added **AC-10 — `iter_adapters_for_layer_set` re-exported from the package** with an explicit HARDENED-retroactively note. |
| C-2 | nit | Empty layer-set `iter_adapters_for_layer_set((), registry)` yields nothing (trivially — the outer `for layer in layer_set:` skips). Uncovered by any test. `_ADAPTER_DISPATCH_ORDER` never constructs `()`; adding an AC for a shape the tuple can't produce is Rule-2 overreach. | Carried in `Validation notes` as a note for `S2-05`'s property test if a future ADR extends `_ADAPTER_DISPATCH_ORDER` with multi-element rows; no AC change. |
| C-3 | nit | Duplicate-layer layer-set `(APP, APP)` would yield each APP adapter twice. Uncovered. Same reason as C-2 — Phase 7's tuple never produces this shape. | Same disposition as C-2. |
| C-4 | nit | The helper's return type `Iterator[...]` (laziness) is enforced by the `mypy --strict` type hint plus `yield`-style body; no runtime test pins that it is a generator, not a materialized list. Callers `list(...)` the result today — lazy-vs-eager is not observable. | No action (Rule 2). |

### Test Quality — STRONG

Two high-value mutants are already closed:
1. **"Iterate `dict.items()` instead of `Ecosystem`-sorted"** — `test_intra_layer_iteration_is_ecosystem_sorted_not_registration_sorted` registers DPKG before APK and asserts APK first. This is the exact BP-1 closure the story sets out to lock at the helper level.
2. **"Yield everything ignoring layer"** — `test_iter_filters_by_layer` closes.

`test_iter_returns_classes_not_instances` cross-checks ADR-0007 (registry stores classes, not instances) via identity + `isinstance(cls, type)` — high-signal, catches an "accidentally instantiate" mutant.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| TQ-1 | nit | `_ECOSYSTEM_SORT_KEY: Final[Mapping[Ecosystem, int]] = {eco: i for i, eco in enumerate(Ecosystem)}` — the sort key derivation itself has no direct test (only observed through helper output). An enum-reordering mutant would fail `test_intra_layer_iteration_is_ecosystem_sorted_not_registration_sorted` because APK/DPKG's relative order would flip, so the mutant is caught indirectly. | No action — the indirect coverage is real. |
| TQ-2 | nit | No Hypothesis property test on `iter_adapters_for_layer_set` itself. Deferred to S2-05 by story design (Out-of-scope explicit). | No action; correctly scoped. |

### Consistency — STRONG

Story faithfully implements Phase-7 ADR-0006 §Decision (dispatch order is explicit `Final` tuple) + §Consequences row 3 (intra-layer `Ecosystem`-sorted). Cross-checks ADR-0007 (registry-stores-classes) via `test_iter_returns_classes_not_instances`. Primitive placement matches ADR-0004 (`vuln.provenance` primitive home). Sibling `Final`-tuple precedents cited (`_GENERATOR_HEADER_MARKERS`, `_REFLECTION_QUERIES`, `_LOCKFILE_PRECEDENCE`) match shipped codebase conventions.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| CN-1 | — | Evidence block references `_attempts/S2-03-adapter-dispatch-order-tuple.md` — file exists (single attempt). No drift. | No action. |
| CN-2 | — | Shipped module docstring cites ADR-0006 §Decision + §Consequences + BP-1 closure exactly as the story says it should. Docstring includes the ADR-0007 cross-check + Strategy-via-data + Final-tuple-marker-catalog claims. | No action. |
| CN-3 | nit | `_ADAPTER_DISPATCH_ORDER` is module-private by leading underscore; the story notes re-export via the module path `from codegenie.primitives.vuln_provenance import assembly as _assembly_mod`. `__init__.py` currently re-exports it in `__all__` under the *public* name via the assembly module reference — the convention matches `_REGISTRY` (S2-01), so intentional. | No action. |

### Design Patterns — STRONG

Registry (S2-01) + `Final`-tuple marker catalog (this story) + Strategy-via-data + Ports-and-adapters (S1-04) compose into an Open/Closed shape: extending `Ecosystem` is free (adds a row to `_ECOSYSTEM_SORT_KEY` implicitly at import time), extending `Layer` is ADR-gated (the tuple is the operator-facing contract). The `_ECOSYSTEM_SORT_KEY: Final[Mapping[Ecosystem, int]]` precompute is a small but exemplary "sort key as data" Strategy touch — `tuple(Ecosystem).index(...)` per item would be O(n) and hidden.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| DP-1 | note | `_ECOSYSTEM_SORT_KEY` O(1) precompute is a load-bearing sibling pattern future adapter-registry-style stories should copy. | Carried in `Validation notes` as a positive precedent; already flagged in existing `Notes for the implementer`. |
| DP-2 | note | The helper accepts `Mapping[ProvenanceAdapterId, type[VulnProvenanceAdapter]]` (not `dict`) — proper Dependency Inversion. Tests pass fixture dicts; production passes `_REGISTRY`. AC-7 pins the type. | No action — good as-is. |
| DP-3 | note | `iter_adapters_for_layer_set` yields `(key, cls)` tuples (not just `cls`) — carrying the `(Layer, Ecosystem)` tuple lets S2-04's `assemble_provenance` audit-log which adapter ran first without a reverse-lookup. Small choice, high downstream leverage. | No action — good as-is. |
| DP-4 | nit | Helper is a `def` returning `Iterator`, not `def ... -> Iterable` with `list` body. Lazy iteration is the right default for a filter-then-sort pipeline; matters if a future consumer streams without materializing. | No action. |

## Edits applied to the story

All surgical (Rule 3):

1. **Added AC-10** — package re-export. Text: `**AC-10 — iter_adapters_for_layer_set re-exported from the package.** codegenie.primitives.vuln_provenance re-exports the helper (present in __all__ and importable as pkg.iter_adapters_for_layer_set) so S2-04's assemble_provenance and future package consumers do not depend on the internal module path .assembly. Test asserts identity (pkg.iter_adapters_for_layer_set is iter_adapters_for_layer_set) AND "iter_adapters_for_layer_set" in pkg.__all__. (HARDENED 2026-07-26 — the test was already shipped as test_iter_adapters_for_layer_set_is_reexported_from_package; the AC anchor was missing.)`
2. **Status line** — appended `(HARDENED retroactively 2026-07-26)`.
3. **`Validation notes` block** — appended under the story documenting the retrospective review, the C-2 / C-3 empty-and-duplicate-layer-set observations (deferred as notes for S2-05's property test extension), the DP-1 `_ECOSYSTEM_SORT_KEY` positive precedent, and the coverage tally after edit.

**Not edited:** every checked-off AC-1..AC-9 (Rule 12 — shipped evidence is authoritative), the Goal, the Scope reminder, the References, the Implementation outline, the TDD plan (red / green / follow-on tests), the Files-to-touch table, the Out-of-scope list, the existing Notes-for-the-implementer bullets.

## Verdict rationale

- No critic returned a `block`-severity finding.
- The single `harden` finding (C-1) was a missing AC anchor for an already-shipped-and-green test; adding AC-10 preserves the test, gives it a numbered home, and closes the "future refactor could silently regress the re-export" gap without invalidating any shipped work (Rule 12).
- All other findings are `nit` or `note` — either Rule-2-appropriate (three-similar-lines beats premature abstraction) or already-covered indirectly (TQ-1's enum-reordering mutant is caught by the ordering test).
- Shipped implementation is a clean instantiation of `Final`-tuple marker catalog + Strategy-via-data + Registry + Ports-and-adapters, faithful to ADR-0006 and cross-consistent with ADR-0007 and ADR-0004.

**HARDENED.** No re-execution needed. S2-05 will pick up the C-2 / C-3 empty-and-duplicate-layer observations when its property test is next hardened.
