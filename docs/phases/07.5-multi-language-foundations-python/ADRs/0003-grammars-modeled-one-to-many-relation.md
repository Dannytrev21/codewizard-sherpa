# ADR-0003: `LanguagePack.grammars` is a modeled one-to-many relation; `language` reuses the existing `Language` newtype

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** Modeled relation · Newtype · closed sum type · domain-modeling · anti-primitive-obsession
**Related:** [ADR-0001](0001-languagepack-total-frozen-value-contract-and-freeze.md), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)

## Context

All three lens designs quietly agreed on a conflation the critic flagged as a **shared blind spot** ([critique.md §Where do all three quietly agree](../critique.md), item 1; [final-design.md §Shared blind spots](../final-design.md#shared-blind-spots-considered)): they treated "TypeScript/JavaScript" as one language. The grammar kernel does not. `src/codegenie/grammars/lock.py` declares `SupportedLanguage = Literal["typescript", "tsx", "javascript"]` — *three* Node-side grammar keys, and no `"node"` member. The performance design went further and silently invented a fourth identifier ("node" the ecosystem), typing its detection pre-pass against `frozenset[SupportedLanguage]` containing a `{node, python}` set that is not a subset of `SupportedLanguage`.

Two distinct things were tangled: the **ecosystem axis** ("this is a Python repo" / "this is a TypeScript repo") and the **grammar key** (which tree-sitter grammar parses a given file). One ecosystem maps to *many* grammar keys. The best-practices design's `grammar_name: str` made it worse — a raw `str` keying into a closed `Literal`-typed kernel, so a typo (`"pyhton"`) passes `mypy` and surfaces only at runtime registration. The critic named this primitive obsession, in the design whose headline was domain-modeling discipline ([critique.md §Anti-patterns from the toolkit's "flag on sight" list](../critique.md)).

## Options considered

- **Option A — `grammar_name: str`, one raw string per pack.** **Pattern:** primitive obsession on a domain ID that keys into a closed `Literal` — the anti-pattern the toolkit flags on sight. A typo type-checks.
- **Option B — `grammar: SupportedLanguage`, one grammar key per pack.** Typed, but models a one-to-one relation that is false: "TypeScript" is three grammar keys. Forces either three TypeScript packs or a lie. **Pattern:** Newtype/closed-Literal but wrong cardinality.
- **Option C — invent a `"node"` / ecosystem `Literal` distinct from both `Language` and `SupportedLanguage`.** A fourth identifier. **Pattern:** none — adds an identifier the codebase does not have and the critic flagged as a silent invention.
- **Option D — `language: Language` (the existing newtype, reused) + `grammars: tuple[SupportedLanguage, ...]` (a modeled one-to-many relation).** **Pattern:** Modeled relation + Newtype + closed sum type.

## Decision

`LanguagePack` carries **two** distinct, correctly-typed identifier fields. `language: Language` reuses the **existing** `Language` newtype from `codegenie.types.identifiers` — no duplicate `LanguageId`, no invented `"node"` member. `grammars: tuple[SupportedLanguage, ...]` models the **one-language-to-many-grammars relation explicitly** as a tuple of the closed `SupportedLanguage` `Literal`. The TypeScript pack carries `grammars=("typescript", "tsx", "javascript")`; the Python pack carries `grammars=("python",)`. The no-shadow and grammar-wired checks in `validate_pack` operate *per grammar key*.

## Tradeoffs

| Gain | Cost |
|---|---|
| The one-to-many ecosystem-to-grammar relation is a typed field, not a conflation — "TypeScript is three grammars" is now expressible | `LanguagePack` carries two identifier fields where a naive reading expects one — a small conceptual cost paid once |
| Reusing the existing `Language` newtype avoids a duplicate-by-addition identifier ([ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) flags duplicate newtypes) | The two axes (`Language` ecosystem, `SupportedLanguage` grammar key) must be kept conceptually distinct by every reader and reviewer |
| A typo'd grammar key is a `mypy --strict` error at the construction site — the closed `Literal` catches it before runtime | Adding a grammar requires a `SupportedLanguage` `Literal` `+1` and a `_DISPATCH` `+1` row — loud, compiler-policed edits (correct per ADR-0043, but not free) |
| No invented "node" identifier — the codebase's identifier set stays minimal and grep-able | The TypeScript pack's three-grammar tuple must be exercised by a fixture, or the relation is a paper claim (open question 2) |

## Pattern fit

This is the toolkit's **Newtype pattern** plus **closed sum type** plus an explicitly **modeled relation**. The toolkit flags "stringly-typed identifiers" as an attack-on-sight anti-pattern: a raw `str` for a domain ID keying into a closed `Literal` defeats the type checker exactly where it is most needed. `grammars: tuple[SupportedLanguage, ...]` uses the closed `Literal` directly, so the type system polices grammar-key validity. The "modeled relation" framing is the critic's named *missed* structural pattern — none of the three designs modeled one-language-to-many-grammars; representing it as a tuple field (not a hidden assumption, not a raw string) makes the cardinality a first-class, type-checked fact. Reusing `Language` rather than minting `LanguageId` honors ADR-0043's caution against duplicate-by-addition identifiers.

## Consequences

- The TypeScript pack is one pack covering three grammar keys — not three packs — and `validate_pack`'s grammar-wired check verifies all three are in `supported_languages()`.
- The no-shadow check operates per grammar key — a future pack claiming a grammar key already wired to another language is a loud `LanguageRegistryError`.
- Adding a future grammar (Phase 8+ Java) is a `SupportedLanguage` `Literal` `+1` and a `_DISPATCH` `+1` row — the loud, compiler-policed edits ADR-0043 sanctions; `register_language` never writes `_DISPATCH`.
- The conformance fixture spec should require the TypeScript fixture to exercise at least `typescript` and one of `tsx`/`javascript` (open question 2, [phase-arch-design.md §Gap analysis Gap 2](../phase-arch-design.md#gap-analysis--improvements)) so the three-grammar tuple is a tested claim.
- No `"node"` ecosystem identifier exists — code that needs "the TypeScript ecosystem" uses `Language("typescript")`; the grammar keys are an internal detail of the pack.

## Reversibility

**High.** `grammars` is an in-memory field of a Pydantic model; changing its type or cardinality is a localized edit plus a contract-snapshot bump ([ADR-0012](0012-languagepack-contract-snapshot-fence-not-byte-edit-allowlist.md)). Because `LanguagePack` is `Provisional Accepted`, the field is explicitly open to revision. Reverting to a one-to-one `grammar` field would only be correct if a future language were genuinely single-grammar *and* the TypeScript three-grammar fact were removed — which it cannot be. The modeled-relation choice is durable because the underlying fact (one ecosystem, many grammars) is durable.

## Evidence / sources

- [final-design.md §Components — `LanguagePack`](../final-design.md#components), §Synthesis ledger CR-7, §Shared blind spots item 1, §Departures item 1, §Pattern reconciliation
- [phase-arch-design.md §Component design — `LanguagePack`](../phase-arch-design.md#component-design), §Design patterns applied
- [critique.md](../critique.md) — "Missed patterns" (the one-to-many relation); "Anti-patterns from the toolkit's flag-on-sight list" (primitive obsession); shared-blind-spot 1
- [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) — newtype + closed sum type discipline
- `src/codegenie/grammars/lock.py` — `SupportedLanguage` Literal; `codegenie.types.identifiers` — the `Language` newtype
