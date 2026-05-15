# Validation report — S1-08 `@register_probe(heaviness=, runs_last=)` + coordinator sort-order edit

**Date:** 2026-05-15
**Validator:** phase-story-validator (scheduled run)
**Verdict:** **HARDENED**
**Story:** `../S1-08-registry-heaviness-runs-last.md`

## Inputs read

- Story `S1-08-registry-heaviness-runs-last.md`
- Phase ADR `0003-coordinator-heaviness-sort-annotation.md`
- `phase-arch-design.md` (Component design #1, Process view, Tradeoffs, ADR table)
- `src/codegenie/probes/registry.py` (current Phase 0/1 implementation)
- `src/codegenie/coordinator/coordinator.py` (lines 440–540, gather + partition path)
- `src/codegenie/cli.py:_seam_registry_for_task` (lines 239–258, the actual integration point)
- `src/codegenie/indices/registry.py` (sibling registry — rule-of-three context)

## Critic findings (collapsed into one pass)

### Consistency — 2 BLOCK findings

1. **B1 — integration point mis-identified.** AC-6 said "coordinator reads `sorted_for_task`". But `coordinator.gather` receives `probes: Sequence[Probe]` from `_seam_registry_for_task()`, which currently calls `default_registry.all_probes()`. The seam in `cli.py` is the actual integration point. Without editing it, the new `sorted_for_dispatch` would never reach the coordinator and AC-9/AC-13 would be vacuously false in production.
   - Resolution: AC-6 split into AC-6a (seam reads sorted order) and AC-6b (coordinator preserves Semaphore). Files-to-touch now includes `src/codegenie/cli.py`.

2. **B2 — cross-wave `runs_last` invariant undefined.** `phase-arch-design.md §"Component design" #1` declares `IndexHealthProbe.tier = "base"`. The current coordinator partitions `[base | rest]` by `tier == "base"` and dispatches `base` first. So a naïve implementation would run B2 in Wave 1, **before** every SCIP/SBOM/runtime-trace probe — exactly the failure mode `runs_last` exists to prevent. The story's tests only covered same-wave ordering.
   - Resolution: New AC-13 makes the cross-wave invariant explicit and testable. The coordinator must hoist `runs_last=True` probes into the tail of Wave 2 regardless of declared tier. Implementer-note added: solve via metadata-paired-with-instance at the seam so 02-ADR-0003's "no ABC change" commitment stays intact.

### Coverage — 4 HARDEN findings

- **C1 — edge cases.** Empty registry, all-runs_last partition, all-same-heaviness preservation. Three new ACs (AC-14a/b/c) + tests.
- **C2 — backward-compat unverified.** AC-8 claimed Phase 0/1 probes still register, but no test actually checked. New `test_phase_0_1_probes_register_unedited` imports `codegenie.probes` and asserts the expected six probes appear in `default_registry.sorted_for_dispatch()` with defaults.
- **C3 — multiple-`runs_last` semantic.** Story's mixed-registry test included TWO `runs_last=True` entries; 02-ADR-0003 Tradeoffs row 4 says "one probe per gather may set it". Resolved by clarifying AC-4 wording: the sort is well-defined for ≥1; the design admits but does not police multiple. Implementer-note flags this for a future ADR amendment if drift surfaces.
- **C4 — `coordinator.dispatch.order` per-wave.** Coordinator has two waves; AC-10 specified one log event. Now: one event per wave with `wave` field; test asserts both AND that no `runs_last=True` probe appears in the prelude-wave list.

### Test-Quality — 3 HARDEN findings

- **T1 — mutation-thin backward-compat test.** `test_module_level_decorator_backward_compatible_no_parens` only checked `returned is cls`. Rewritten to monkeypatch `default_registry` to a fresh `Registry()`, then assert the entry **actually appears in** `sorted_for_dispatch()` with defaults. Catches a buggy decorator that returns the class but never calls `register()`.
- **T2 — coordinator test was a sketch.** `test_runs_last_dispatched_after_every_sibling` had a `...` body. Rewritten as two concrete tests using `_make_recorder_probe` + `time.perf_counter_ns()` + the actual `gather()` call. Both tests verify cross-wave hoisting (AC-13) and per-wave log emission (AC-10) under the real semaphore.
- **T3 — property-based added.** Sort function has four invariants easily expressible via Hypothesis (`@given(specs=…)`). New AC-15 + property test surfaces off-by-one heaviness rank, flipped partition, or unstable tie-breaks via shrinker.

### Design-Patterns — 1 HARDEN, 1 NOTE

- **D1 — `Heaviness` exhaustiveness invariant (HARDEN).** `_HEAVINESS_RANK` and the `Heaviness` Literal must stay in sync. New AC-17 + `typing.get_args(Heaviness)` assertion. Make-illegal-states-unrepresentable: if a 4th tier is ever added without updating the rank dict, CI fails loud.
- **D2 — Rule-of-three kernel-extract is queued, NOT in scope (NOTE).** `codegenie.indices.registry.py:26–29` already names the trigger queued for S1-10. Implementer note added: keep `ProbeRegEntry` shape compatible with a future `KernelRegistryEntry[K, V]` extract; **do not** introduce the kernel here (Rule 2). The third precedent at S1-10 is the right moment.

## Conflicts resolved by priority

- Design-patterns critic considered proposing "make the prelude/Wave-2 partition itself a plugin/strategy" (so `runs_last` is one strategy among many). Rejected by Consistency + Rule 2: there's no rule-of-three trigger; one named `runs_last` use-case (B2) does not warrant an abstraction. The opportunity is recorded as a Notes-for-implementer paragraph, not as an AC.
- Coverage wanted "warn on multiple `runs_last=True` probes". 02-ADR-0003 Tradeoffs row 4 admits but does not police multiple. Consistency wins → no AC; flagged for future ADR amendment.

## Stage 3 (research) — skipped

No critic finding tagged `NEEDS RESEARCH`. Property-based testing pattern is canonical (Hypothesis docs + already used in this repo per `tests/` precedents); no arXiv lookup needed.

## Edits applied to the story

- Header: `Status: Ready (HARDENED 2026-05-15)` + new `Validation notes` block summarizing every change with rationale.
- Acceptance criteria: AC-4 reworded; AC-6 split into AC-6a / AC-6b; added AC-13 (cross-wave), AC-14a/b/c (edge cases), AC-15 (property-based), AC-16 (cache isolation), AC-17 (`Heaviness` exhaustiveness). AC-8 reworded with concrete verification path. AC-10 reworded with per-wave emission.
- TDD plan red tests: rewrote `test_module_level_decorator_backward_compatible_no_parens` (mutation-resistant); added `test_phase_0_1_probes_register_unedited`, `test_empty_registry_sorted_dispatch_is_empty_tuple`, `test_all_runs_last_partition_orders_by_heaviness_then_registration`, `test_heaviness_literal_arms_exhaustively_ranked`, `test_sort_invariants_hold_for_arbitrary_registries` (Hypothesis), `test_two_registries_do_not_cross_pollute`.
- TDD plan coordinator file: replaced `...` sketch with two concrete tests covering AC-9, AC-13, AC-10.
- Files to touch: added `src/codegenie/cli.py`, added test seam file. Reworded existing rows for accuracy.
- Notes for the implementer: added cross-wave invariant guidance (top), tier-semantic-check guidance (out-of-band ADR amendment, not silent re-tier), and rule-of-three kernel-extract note.

## What the story now guarantees the executor

- The implementer cannot land code that violates the cross-wave `runs_last` invariant (AC-13 + its dedicated test).
- The implementer cannot ship a registry whose `_HEAVINESS_RANK` drifts from the `Heaviness` Literal (AC-17).
- The implementer cannot ship a buggy dual-shape decorator that silently drops registrations (AC-8 + hardened backward-compat test).
- Property-based shrinking will surface any sort bug that produces a "looks right on these examples" implementation (AC-15).
- The seam-coordinator integration is explicit (AC-6a + AC-6b + files-to-touch).

## Files modified

- `docs/phases/02-context-gather-layers-b-g/stories/S1-08-registry-heaviness-runs-last.md` — header, ACs, TDD plan, Files-to-touch, Notes-for-implementer.
- `docs/phases/02-context-gather-layers-b-g/stories/_validation/S1-08-registry-heaviness-runs-last.md` — this report.
