# ADR-0004: Python detection is a `tier="base"` probe reusing the coordinator prelude — no `LanguageDetectionPrepass`

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** Open/Closed Principle · Registry · functional-core-imperative-shell · coordinator-reuse · anti-temporal-bug
**Related:** [ADR-0005](0005-projectdetector-protocol-shared-marker-catalog.md), [ADR-0007](0007-python-probes-hardened-parse-only-no-exec.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)

## Context

A polyglot or Python repo must have its Python probes *admitted* to the coordinator's dispatch waves, and a Node-only repo must have them *filtered out* at no cost. The performance lens design proposed a new `LanguageDetectionPrepass` component that would run *before the coordinator builds its waves*, returning the set of detected languages so the wave could be filtered.

The critic killed it ([critique.md §Attacks on the performance-first design, problem 3](../critique.md); [final-design.md §Departures item 2](../final-design.md#departures-from-all-three-inputs)): the pre-pass claimed to read `RepoSnapshot.detected_languages` — a field populated by the Phase 0/1 `LanguageDetection` *probe*, whose output lands in `ProbeOutput.schema_slice` *only after the wave runs*. A pre-pass that runs *before wave construction* cannot read a probe output that does not exist yet. The pre-pass had a **temporal-ordering bug**: it wanted probe-derived data at a lifecycle point before any probe had run. The only ways to satisfy it were to duplicate the marker walk (contradicting the pre-pass's own "no second filesystem walk" claim) or reorder the coordinator — an [ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)-forbidden silent edit to shipped Phase 0–2 code.

The codebase already has the right mechanism: the coordinator runs a `tier="base"` **prelude wave** first; `LanguageDetectionProbe` runs there and enriches `RepoSnapshot.detected_languages`; the `tier="task_specific"` rest wave is filtered by the existing `language_filter._admits_languages` predicate.

## Options considered

- **Option A — a new `LanguageDetectionPrepass` component that runs before wave construction.** **Pattern:** the design tagged it "Specification pattern" — pattern-name inflation (a one-shot marker-glob is not a composable predicate object), and it carries a temporal-ordering bug.
- **Option B — reorder the coordinator so detection runs before wave construction.** A silent edit to shipped Phase 0–2 coordinator code. **Pattern:** none — ADR-0043-forbidden.
- **Option C — `PythonProjectProbe` declared `tier="base"`, registered like any probe, running in the existing prelude wave.** Detection becomes a probe, not a pre-pass; the existing `language_filter` does the filtering. **Pattern:** Open/Closed Principle + Registry — a new probe is new files plus one import line, zero new dispatch code.

## Decision

Python project detection is a **`tier="base"` probe** — `PythonProjectProbe` — registered through the normal `@register_probe` mechanism (fanned out by `register_language`). It runs in the coordinator's **existing prelude wave** alongside `LanguageDetectionProbe`, enriching `RepoSnapshot.detected_languages`. The `tier="task_specific"` Python probes are admitted or filtered by the **existing** `language_filter._admits_languages` predicate. **No `LanguageDetectionPrepass` is introduced**; **no coordinator code is reordered or edited**. The temporal-ordering bug cannot occur because detection *is* a probe in the wave, not a pre-pass before it.

## Tradeoffs

| Gain | Cost |
|---|---|
| Zero new dispatch code — the coordinator, prelude wave, and `language_filter` are reused verbatim | Detection is bounded to the prelude wave's lifecycle — it cannot influence anything that runs *before* the prelude (acceptable; nothing needs to) |
| The temporal-ordering bug is structurally impossible — a probe cannot read its own output before it runs because detection *is* the probe | `PythonProjectProbe` runs on every gather, including Node-only repos — but a `tier="base"` marker-glob is cheap, and it is the price of correctness |
| `language_filter` already filters Python probes out of a Node-only repo's rest wave — "negligible cost on language-#1 repos" is achieved by reuse, not new code | The honest claim is *negligible*, not *zero* — the prelude wave does run one more probe; the performance lens's "free" framing is dropped |
| A future language's detector is just another `tier="base"` probe — the pattern scales by addition | Detection cannot be a single fast pre-flight check; it pays the per-probe dispatch overhead (negligible, but real) |

## Pattern fit

This is **Open/Closed Principle** and the **Registry pattern** working exactly as the toolkit prescribes: "a new feature should not require editing existing code" — `PythonProjectProbe` is new files plus one import line, and the coordinator never learns the word "Python." The performance design's "Specification pattern" label for the pre-pass was pattern-name inflation (the critic flagged it): a Specification is a composable boolean predicate object, not a one-shot marker-glob returning a frozenset. The deeper lesson is the toolkit's **functional core / imperative shell** discipline applied to *lifecycle*: detection is not a special pre-pipeline phase, it is ordinary work the existing pipeline already sequences correctly via the prelude/rest-wave partition. Inventing a pre-pass to do what a `tier="base"` probe already does is machinery ahead of need — and in this case machinery with a correctness bug.

## Consequences

- The coordinator, the prelude/rest-wave partition, and `language_filter._admits_languages` are reused unchanged — no Phase 0–2 edit, the regression suite keeps meaning what it means.
- A Node-only gather never imports `tree_sitter_python`: `language_filter` filters Python `tier="task_specific"` probes out before any `language_for("python")` call (verified by a `sys.modules` fence, G11).
- `PythonProjectProbe` returns `Detected(confidence="high")` only on a real Python manifest and `Detected(confidence="low")` for a bare `*.py` tree — see [ADR-0005](0005-projectdetector-protocol-shared-marker-catalog.md).
- A conformance assertion (`test_language_probes_actually_dispatched`, [phase-arch-design.md §Gap analysis Gap 3](../phase-arch-design.md#gap-analysis--improvements)) asserts every `pack.layer_a_probes` probe appears in the coordinator's `coordinator.dispatch.order` audit event — closing the registered-but-never-dispatched hole the isolated capability assertions miss.
- A future language's detection is added the same way — a new `tier="base"` probe — with no new pre-pass per language.

## Reversibility

**High.** Detection-as-a-probe is the codebase's existing idiom; there is nothing bespoke to unwind. If a future need genuinely required pre-wave language knowledge, that would be a coordinator change (a sanctioned migration with its own ADR), not a casual revert. The decision is durable because it is the *absence* of a new component — there is no `LanguageDetectionPrepass` to remove.

## Evidence / sources

- [final-design.md §Components — Python Layer A/B probes](../final-design.md#components), §Synthesis ledger CR-5, §Departures item 2, §Pattern reconciliation (Specification rejected with the component)
- [phase-arch-design.md §Process view, §Control flow, §Gap analysis Gap 3](../phase-arch-design.md)
- [critique.md §Attacks on the performance-first design](../critique.md) — problem 3 (temporal-ordering bug); "Specification pattern" pattern-name inflation
- [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) — the probe contract reused unchanged; [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) — reordering the coordinator would be a silent edit
