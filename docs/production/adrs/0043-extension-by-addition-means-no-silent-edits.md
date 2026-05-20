# ADR-0043: Extension by addition means "no silent edits"

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** architecture · extension-by-addition · fences · contracts · migrations
**Related:** ADR-0007, ADR-0028, ADR-0031, ADR-0033, ADR-0039

## Context

"Extension by addition" is a load-bearing commitment ([design.md §2](../design.md), commitment 5): adding a new language, task type, or tool must not require edits to existing plugins or stable existing behaviour. In practice the rule conflates three different things under one word — *contracts* (interfaces many components depend on), *invariants* (properties that must hold), and *components/implementations* (code that does work). Freezing the first two is correct; freezing the third is not, and taking "no edits" literally has produced three problems:

1. **Per-phase byte-edit allowlists do not scale.** Phase 7 ([Phase 7 ADR-0009](../../phases/07-migration-task-class/ADRs/0009-phase-7-byte-edit-allowlist-fence.md)) enumerates ten sanctioned byte-edits to "locked" Phase 0–6.5 files, policed by a phase-specific fence. Phase 7.5 would add its own list; by Phase 16 there are 100+ allowlist rows across a dozen fence tests and no one can reason about what is actually protected. An exception list that grows every phase is a sign the rule is mis-stated.
2. **Some edits are loud and compiler-policed — and those are not the danger.** Adding a member to a closed `Literal`, a field to a frozen struct, or an import line to a collection point is a *textual* edit but a *semantic* addition: the compiler (`mypy --strict`) or a fence forces every consumer to confront it. The failure mode the commitment exists to prevent is the *silent*, behaviour-changing edit — a changed function body, a flipped default, a loosened validation — that forces re-verification of everything downstream.
3. **There is no sanctioned path for legitimate horizontal change.** Some cross-cutting changes are necessary and correct — a security fix touching every probe, a logging-format migration, a new required confidence sub-field. The literal rule has no concept of a loud, reviewed, all-at-once sweep distinct from a silent edit, so such work either fights the rule or is avoided — producing parallel near-duplicate components instead of one refactor.

## Options considered

- **Option A — status quo.** Keep "no edits" literal; keep enumerating per-phase byte-edit allowlists. Rejected: does not scale (problem 1) and still has no horizontal-change path (problem 3).
- **Option B — relax the discipline.** Allow edits to existing code with ordinary review. Rejected: destroys the property that makes a green regression suite *mean something* — if existing code can be silently edited, "Phase 3 tests still pass" is weak evidence, and the parallel/agentic execution model (`phase-story-executor`) loses its near-zero-merge-conflict guarantee.
- **Option C — reframe to "no silent edits" + category-based fence + sanctioned migration.** Keep the freeze where it earns its rent (contracts, invariants, security boundaries); name the edit *categories* that are always safe; police the category, not a hand-counted list; give horizontal change an explicit, conformance-gated path. Chosen.

## Decision

Extension by addition means **no *silent* edits**, not "no edits." Three concrete changes:

1. **Restate the rule.** An edit is a violation only when it changes existing behaviour *silently*. Edits the compiler or a fence fully polices — adding a `Literal`/`Enum` member, adding a field to a frozen struct, adding an import line to a collection point, adding a schema `$ref` — are the enforcement mechanism, not violations. They are loud, bounded, and reviewable.
2. **Replace per-phase enumerated allowlists with one category-based fence.** A single repo-wide fence (`tests/fence/test_no_silent_edits.py`) defines the always-safe edit *categories* once and checks a diff against the category, not against a per-phase list of specific files. Phase 7's ten-row allowlist is folded into the category fence; future phases add no allowlist rows.
3. **Add a sanctioned "migration" concept.** A *migration* is a loud, reviewed, all-at-once horizontal sweep across existing code — explicitly labelled, with the conformance suite and golden files as the safety net. It is the legitimate path for cross-cutting change and is distinct, by construction and by review treatment, from a silent edit.

This refines [ADR-0039](0039-extension-by-addition-allows-bounded-core-primitives.md); 0039's bounded-additive-primitive carve-out stands unchanged. ADR-0043 governs *what counts as an edit*.

## Tradeoffs

| Gain | Cost |
|---|---|
| Per-phase allowlist accretion stops — one fence, defined once | The category fence must be carefully specified; an over-broad category silently re-admits dangerous edits |
| Loud compiler/fence-policed edits are no longer mislabelled as violations — the discipline matches reality | "No silent edits" requires judgement ("is this edit silent?") where "no edits" was mechanical |
| Horizontal change has a real, conformance-gated path instead of fighting the rule | A "migration" is a heavier review artefact than an addition — intentionally |
| Green regression suite keeps meaning what it means (Option B's loss is avoided) | Existing docs that say "never edit existing code" must be reworded (design.md §2.5, CLAUDE.md, contributing.md) |

## Consequences

- Phase 7.5 ships the category-based fence; Phase 7's per-phase allowlist is folded into it and no future phase adds allowlist rows.
- The `LanguagePack` contract (Phase 7.5) is the model case: adding a language is pure addition; growing the `LanguagePack` type itself is a sanctioned, compiler-policed edit.
- Closed `Literal`s (`PackageManager`, `SupportedLanguage`) may be edited to add members without a bespoke ADR — the edit is a recognised category and is compiler-policed.
- A new review artefact — the *migration* — is defined in `contributing.md` with its checklist (conformance green, goldens regenerated deliberately, one reviewed sweep).
- `design.md §2`, `CLAUDE.md`, and `contributing.md` are updated to the "no silent edits" wording.
- The discipline now requires judgement at the margin; the category fence is the backstop that keeps the judgement honest.

## Reversibility

**Medium.** The reframe is wording plus one fence; reverting to literal "no edits" is cheap textually. But once Phase 7.5+ stop maintaining per-phase allowlists and the category fence becomes the single source of truth, reverting means reconstructing per-phase lists — increasingly costly as phases accumulate. Reverse early or not at all.

## Evidence / sources

- `../design.md §2` commitment 5 — the extension-by-addition commitment this ADR refines.
- [ADR-0039](0039-extension-by-addition-allows-bounded-core-primitives.md) — bounded additive core primitives; ADR-0043 refines the definition of "edit" that 0039 assumes.
- [Phase 7 ADR-0009](../../phases/07-migration-task-class/ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — the per-phase byte-edit allowlist whose non-scaling motivated this ADR.
- [ADR-0033](0033-domain-modeling-discipline.md) — closed sum types; compiler-policed `Literal` growth is the canonical "loud edit".
- `docs/roadmap.md §"Phase 7.5"` — the phase that lands the category fence and the conformance suite.
