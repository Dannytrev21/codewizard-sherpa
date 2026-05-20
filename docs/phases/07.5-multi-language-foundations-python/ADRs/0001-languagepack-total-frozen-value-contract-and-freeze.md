# ADR-0001: `LanguagePack` — a total, frozen-value capability contract, frozen provisionally

**Status:** Provisional Accepted
**Date:** 2026-05-20
**Tags:** Make illegal states unrepresentable · Value object · Contract + snapshot test · contract · domain-modeling
**Related:** [ADR-0002](0002-register-language-validate-all-then-commit-no-unregister.md), [ADR-0003](0003-grammars-modeled-one-to-many-relation.md), [ADR-0012](0012-languagepack-contract-snapshot-fence-not-byte-edit-allowlist.md), [production ADR-0010](../../../production/adrs/0010-seven-stage-pipeline-shape.md), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)
**Review trigger:** the third `LanguagePack` lands — i.e. the first non-isomorphic language (Java/Maven is the named candidate, per [phase-arch-design.md §Non-goals](../phase-arch-design.md#non-goals) and ADR-0032's running example). Until then the contract is provisional.

## Context

Phase 7.5 introduces the language axis: a second target language (Python) added by addition, the mirror of Phase 7's second task class. The roadmap mandates that the second language land "as a `LanguagePack` value with no edits to the first" ([`roadmap.md` §"Phase 7.5"](../../../roadmap.md)). That makes the *shape* of `LanguagePack` the central artifact of the phase — it is the seam every Phase 8+ target language registers through.

The three lens designs disagreed on the type (CONFLICT CR-1 in [final-design.md §Synthesis ledger](../final-design.md#synthesis-ledger)): performance punted ("immaterial"), security wavered between dataclass and Pydantic, best-practices was definite on a frozen Pydantic model with `extra="forbid"`. The critic's design-pattern review flagged a deeper problem ([critique.md §Pattern claims that don't survive scrutiny](../critique.md)): best-practices claimed "make illegal states unrepresentable" but used a raw `grammar_name: str` — leaving the most error-prone field fully representable when invalid. The roadmap-level critique additionally flagged that freezing a six-field contract on two near-isomorphic ecosystems (TypeScript and Python are both gradually-typed, lockfile-based, single-file-module) is the "freeze-too-early" judgement error [ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) explicitly names.

This ADR resolves both: the *type* (a total frozen Pydantic value) and the *freeze posture* (provisional, narrow, with an explicit early-freeze justification).

## Options considered

- **Option A — frozen Pydantic model, every capability a required field.** A `LanguagePack(...)` with a field missing is a `mypy --strict` error at the construction site; an unknown field is a `pydantic.ValidationError` (`extra="forbid"`). **Pattern:** Make illegal states unrepresentable + Value object — a partial language is a real bug the compiler forbids for free.
- **Option B — a `LanguagePackBuilder`.** Construct the pack incrementally, `.build()` at the end. **Pattern:** Builder — and an anti-pattern here: it reintroduces exactly the partial-pack state the total value exists to forbid.
- **Option C — a frozen dataclass.** Same totality, but no `extra="forbid"`, and it is not the project's contract idiom. **Pattern:** Value object without the project's sanctioned validation framework.
- **Option D — defer the freeze; ship `LanguagePack` as an un-pinned type.** No snapshot test, grow it freely. **Pattern:** none — and it abandons a roadmap-mandated deliverable.

## Decision

`LanguagePack` is a **frozen Pydantic v2 model** (`model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`) carrying exactly the six roadmap-named capabilities as required fields — `language`, `grammars`, `project_detector`, `layer_a_probes`, `dep_graph_strategies`, `search_adapter_module` — plus one typed retrofit discriminator (`probes_self_registered: bool`, see [ADR-0006](0006-typescript-retrofit-by-reference-probes-self-registered.md)). A partial language is unrepresentable: an incomplete construction is a compile-time error. The pattern is **Make illegal states unrepresentable + Value object**. The contract ships **`Provisional Accepted`** with the third-language review trigger above — the early freeze is justified because the roadmap *mandates* the contract land this phase, exactly the escape hatch [ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) commitment 5 permits ("or state plainly why an early freeze is necessary").

## Tradeoffs

| Gain | Cost |
|---|---|
| A half-registered language cannot exist — totality is a `mypy --strict` error before any test runs | A *broad* six-field contract where ADR-0043 prefers *narrow* ones — justified only because the six are the irreducible roadmap-named set |
| `extra="forbid"` makes a typo'd capability a loud `ValidationError`, not a silently-ignored field | `arbitrary_types_allowed=True` is required for the `type[Probe]` / callable fields — a documented but non-default Pydantic mode |
| `LanguagePack` *is* the project's contract idiom (`ProbeOutput`, manifests, events all use frozen Pydantic) — zero new framework | The contract is frozen on two near-isomorphic examples; Java/Maven (classpath, compiled artifacts, POM inheritance) will likely force a field-add |
| Authoring a total pack is deliberately more work than a partial one — the human cost buys "a half-registered language cannot exist" | Authoring friction is real and intentional; there is no incremental-construction convenience path |
| `Provisional Accepted` + `Review trigger` is ADR-0043's exact sanctioned mechanism for an honest early freeze | The contract *will* break on its first non-isomorphic use — though that breakage is loud and expected, not silent |

## Pattern fit

This is **Make illegal states unrepresentable** (toolkit §Structural / typing patterns) applied to a capability bundle: the six fields are the irreducible set the roadmap names, and a language missing any one of them is not a degraded language — it is a bug. Modeling the bundle as a total frozen **Value object** pushes that bug to the construction site where `mypy` catches it for free. The tempting alternative pattern — **Builder** — is an anti-pattern here: a `LanguagePackBuilder` exists precisely to allow partial intermediate state, which is the state this design exists to forbid. The critic correctly noted (and the best-practices design correctly rejected) a builder for the *pack value*; this ADR keeps that rejection. A staging mechanism for the *registration act* is a different object and is covered by [ADR-0002](0002-register-language-validate-all-then-commit-no-unregister.md).

## Consequences

- Every Phase 8+ target language registers by constructing one `LanguagePack` — the seam is fixed and minimal.
- A new capability *category* (a seventh field) is a `LanguagePack` field-add — a loud, compiler- and snapshot-policed edit, caught by the [ADR-0012](0012-languagepack-contract-snapshot-fence-not-byte-edit-allowlist.md) contract-snapshot fence. ADR-0043 calls this growth "exactly the desired behaviour."
- `package_managers` is **not** a field — it is a derived `@property` over `dep_graph_strategies.keys()` ([final-design.md §Departures](../final-design.md#departures-from-all-three-inputs) item 5); a second field would be a drift-prone duplicate source of truth.
- The `tests/conformance/` tier ([ADR-0010](0010-conformance-tier-parameterized-over-live-registry.md)) parameterizes over registered packs — every language auto-enrolls because the pack value *is* the enrollment unit.
- Phase 8 must plan for a near-certain `LanguagePack` field-add when Java/Maven lands; the field-add is expected and loud, not a surprise — the contract-snapshot fence will go red and the review trigger will fire.
- The freeze is provisional: the third pack either promotes this ADR to `Accepted` (the six fields held) or supersedes it with a widened contract (and a new ADR per the [production ADRs README](../../../production/adrs/README.md) conventions).

## Reversibility

**Medium.** The *type choice* (frozen Pydantic) is cheap to keep — it is the project idiom. The *freeze* is the reversible-cost surface: un-freezing means deleting the snapshot test, and widening means a reviewed field-add plus a snapshot bump. Because the freeze ships `Provisional Accepted` with a named trigger, growing the contract is a sanctioned, anticipated act rather than a contract violation — the reversibility cost is bounded by design. Collapsing `LanguagePack` entirely (inlining its six fields at call sites) would lose the conformance auto-enrollment and the single-seam property, and is not a realistic reversal.

## Evidence / sources

- [final-design.md §Components — `LanguagePack`](../final-design.md#components), §Synthesis ledger CR-1, §Departures item 5, §Risks #1
- [phase-arch-design.md §Component design — `LanguagePack`](../phase-arch-design.md#component-design), §Data model
- [critique.md](../critique.md) — best-practices "Make illegal states unrepresentable" partial claim; roadmap-level critique on freeze-too-early
- [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) commitment 5 (freeze discipline: narrow / earned / provisional) and the "model case" callout
- [production ADR-0010](../../../production/adrs/0010-seven-stage-pipeline-shape.md), [ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) — Pydantic contract idiom, domain-modeling discipline
- [`roadmap.md` §"Phase 7.5"](../../../roadmap.md) — the contract is mandated this phase
