# ADR-0006: TypeScript is retrofitted as `LanguagePack` #1 by reference — `probes_self_registered` discriminator

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** Tagged union / typed discriminator · Registry · Open/Closed Principle · retrofit · extension-by-addition
**Related:** [ADR-0001](0001-languagepack-total-frozen-value-contract-and-freeze.md), [ADR-0002](0002-register-language-validate-all-then-commit-no-unregister.md), [ADR-0010](0010-conformance-tier-parameterized-over-live-registry.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)

## Context

The phase's headline claim is "Python is `LanguagePack` #2, which validates the abstraction." That requires a `LanguagePack` #1 — TypeScript — to exist. But TypeScript's probes are *already registered*: the Phase 1 Node probe modules fired `@register_probe` at their own import, long before `codegenie.languages` existed. This is the **retrofit seam** the best-practices design named "the single most important decision in the phase" and then left unresolved ([critique.md §Attacks on the best-practices design, problem 1](../critique.md)).

The naive `register_language` body — `for probe_cls in pack.layer_a_probes: register_probe(probe_cls)` — *crashes on its own first input*: re-registering an already-registered Phase 1 probe raises `ProbeError` ([critique.md §Attacks on the best-practices design, problem 2](../critique.md)). The two ways out each have a cost: route Phase 1 probe registration *through* `register_language` (a silent edit to the shipped `codegenie/probes/__init__.py` collection point — [ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)-forbidden), or keep probes self-registering and have the pack merely *reference* them (an asymmetry with Python, which fans its probes out). The security design's no-shadow check would, additionally, mis-fire on the TypeScript pack itself if the retrofit re-registered Phase 1 probes ([critique.md §Things this design missed](../critique.md)).

## Options considered

- **Option A — route Phase 1 probe registration through `register_language`.** Symmetric, but requires editing the shipped `probes/__init__.py` collection point. **Pattern:** none — an ADR-0043-forbidden silent edit to shipped code.
- **Option B — flat fan-out, no discriminator.** `register_language(TS_PACK)` re-registers Phase 1 probes and crashes. **Pattern:** none — known-broken on its primary input.
- **Option C — `probes_self_registered: bool` typed field on the pack; the fan-out skips probe registration when `True`.** TypeScript is retrofitted *by reference* — its pack records the probe class references but `register_language` does not re-register them. **Pattern:** typed discriminator on a value (a degenerate tagged union) + Open/Closed.

## Decision

`LanguagePack` carries a typed field `probes_self_registered: bool` (default `False`). `register_language` **skips the probe fan-out** when it is `True`. The TypeScript pack ships `probes_self_registered=True`: it is a `LanguagePack` #1 retrofitted **by reference** — its `layer_a_probes` tuple records the Phase 1 Layer-A probe classes for conformance to consume, but `register_language` does not re-register them (they self-registered at Phase 1 import). The Python pack ships `probes_self_registered=False`: its probes *are* fanned out. The asymmetry is **typed and explicit**, not a call-site flag and not papered over. The no-shadow probe-name check in `validate_pack` runs **only for `probes_self_registered=False` packs** (a retrofit pack's probes are, by definition, the registry's existing content — comparing them to themselves is meaningless; see [phase-arch-design.md §Gap analysis Gap 1](../phase-arch-design.md#gap-analysis--improvements)).

## Tradeoffs

| Gain | Cost |
|---|---|
| `register_language` is a *pure addition* — no double-registration, no edit to the shipped `probes/__init__.py` | The retrofit is genuinely *asymmetric*: TS probes self-register, Python's fan out — the two packs have different registration histories |
| The asymmetry is a *typed field on the pack value*, not a hidden behavior or a call-site boolean flag — it is honest and greppable | `probes_self_registered` is, narrowly, a boolean — but it is a typed field, not a method flag, so the toolkit's "boolean-flag soup" anti-pattern does not apply |
| The no-shadow check does not mis-fire on the retrofit's own probes — the retrofit is by reference, its probes belong to Phase 1, not to a colliding pack | The "Python validates the abstraction" proof rests on conformance consuming *both* packs identically as inputs — the *contract* is symmetric even though registration history is not |
| Conformance treats `TS_PACK` and `PYTHON_PACK` identically — both are `LanguagePack` values it iterates; the proof is the symmetric *contract*, not symmetric *history* | `TS_PACK` must be enumerated completely (all six fields) as a concrete deliverable — "retrofit by reference" cannot leave `layer_a_probes` / `project_detector` unspecified (Gap 2) |

## Pattern fit

`probes_self_registered` is a **typed discriminator on a value** — a degenerate tagged union (a two-state discriminator). The toolkit flags "boolean flags on public methods" as an anti-pattern because each flag doubles a *method's* behavioral surface; this is different — it is a *field on an immutable value*, set once at pack construction, describing a durable property of that pack (its probes were or were not pre-registered). The honest framing the critic forced is **Registry + Open/Closed**, not "Facade": a facade *simplifies access without changing semantics*, but a `register_language` that double-registers on its own first input is "a leaky re-registrar, not a facade." The discriminator makes the retrofit a *pure addition* — the Open/Closed property holds because no shipped code is edited. The drift risk (Risk #2) is contained by a unit test asserting the live probe registry contains *at least* the union of all packs' `layer_a_probes` (not equality — Phase 2–7 added Layer B–G probes belonging to no pack).

## Consequences

- `register_language` never edits the shipped `probes/__init__.py` — TypeScript's probes are referenced, not re-registered; the Open/Closed property of the phase holds.
- `TS_PACK` must be enumerated completely as a Phase 7.5 deliverable (the first story): `layer_a_probes` is exactly the Phase 1 Layer-A probe classes; `project_detector` is a *genuine new* `ProjectDetector` object (Phase 1 had no detector — detection was a probe); `grammars=("typescript", "tsx", "javascript")`. See [phase-arch-design.md §Gap analysis Gap 2](../phase-arch-design.md#gap-analysis--improvements).
- The Risk #2 drift test asserts the probe registry contains *at least* the union of all packs' `layer_a_probes` — strict equality is wrong (Layer B–G probes belong to no pack).
- The no-shadow probe-name check runs only for `probes_self_registered=False` packs; the `PackageManager`-key no-shadow check runs for every pack (a retrofit's strategies are not auto-pre-registered the way `@register_probe` probes are — verify per open question 6).
- Future *new* languages ship `probes_self_registered=False` — the retrofit path is a one-time accommodation for the already-shipped Node probes, not a general mode.

## Reversibility

**Medium.** `probes_self_registered` is a `LanguagePack` field; removing it would require either retrofitting Phase 1 probe registration through `register_language` (a sanctioned migration touching shipped code) or accepting the double-registration crash. Because `LanguagePack` is `Provisional Accepted`, the field is open to revision — but the underlying asymmetry (Node probes shipped before the language axis existed) is a permanent historical fact, so some accommodation will always be needed. The discriminator is the lowest-cost honest accommodation; reversing it does not remove the fact it describes.

## Evidence / sources

- [final-design.md §Components — `register_language()`](../final-design.md#components), §Synthesis ledger CR-2, §Risks #2, §Shared blind spots item 2, §Pattern reconciliation (Facade reframed as Registry + retrofit discriminator)
- [phase-arch-design.md §Process view, §Control flow, §Gap analysis Gap 1 and Gap 2, §Edge cases #16](../phase-arch-design.md)
- [critique.md §Attacks on the best-practices design](../critique.md) — problems 1 and 2 (the unresolved retrofit seam; the flat fan-out crash); §Things this design missed (no-shadow mis-fire on the retrofit)
- [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) — the probe contract; [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) — editing `probes/__init__.py` to route Phase 1 registration would be a silent edit
