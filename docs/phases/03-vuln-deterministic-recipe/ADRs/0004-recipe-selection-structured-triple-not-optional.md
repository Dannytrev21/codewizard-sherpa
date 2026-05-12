# ADR-0004: `RecipeSelection` is a structured `(recipe, reason, diagnostics)` triple — not `Optional[Recipe]`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** contract · phase-4-handoff · diagnostic-signal · synthesizer-departure
**Related:** ADR-0001, ADR-0003, [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md), [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md)

## Context

The selector maps `(advisory, repo_context, skills) → recipe_or_no_match`. Best-practices proposed `selector.select(...) → Optional[Recipe]` — a binary return. Performance-first emitted `skipped: no_recipe` as a single output field. Neither captured **why** a recipe didn't match.

The critic flagged this as best-practices' hidden assumption #1 (`critique.md §"Attacks on best-practices" §"Hidden assumptions" #1`): Phase 4's RAG → LLM-fallback chain (`production ADR-0011`) needs more than "no recipe matched" — it needs the *signals* that say *why* no recipe matched (was the package outside the catalog? was the semver range untranslatable? was the lockfile dialect unsupported? was the requested engine unavailable?). A binary return forces Phase 4 to either expand the selector's return type (editing Phase 3 code, violating extension-by-addition) or duplicate the diagnostic logic in Phase 4 (smell).

The synthesis returns a closed-enum `reason` plus a free-form `diagnostics` dict (`final-design.md §"Goals" §"Contract goals"` row 5; `§"Departures from all three inputs"` #2). The reason enum is the public contract Phase 4 reads.

## Options considered

- **`Optional[Recipe]` [B].** Cheapest. Phase 4 has no signal beyond null/non-null. Forces Phase 4 to re-derive the no-match reason.
- **`Optional[Recipe]` + per-call diagnostic side-effects (audit log) [implicit].** Diagnostics in audit chain, not in return type. Phase 4 must parse audit events to drive its decision — wrong layer.
- **`Recipe | NoMatch(reason, diagnostics)` sum type [variant].** Pythonic via dataclass union. Forces Phase 4 to pattern-match; reason is at the top level. Considered but the unified `RecipeSelection` triple makes the contract simpler to mock and snapshot.
- **`RecipeSelection(recipe: Recipe | None, reason: Literal[...], diagnostics: dict)` triple [synth].** One return type for both match and no-match. `reason="matched"` when `recipe is not None`. Phase 4 reads `reason` to route.

## Decision

**Selector returns a `RecipeSelection` Pydantic model:**

```python
class RecipeSelection(BaseModel):
    recipe: Recipe | None
    reason: Literal[
        "matched",
        "no_engine",          # the recipe's engine is unavailable (e.g., java missing for OpenRewrite stub)
        "range_break",        # the patched version is outside the recipe's semver-translatable range
        "peer_dep_conflict",  # repo's peer-dep graph blocks the bump
        "unsupported_dialect", # lockfile dialect (npm 9 → 10 churn, pnpm workspace, yarn classic) not yet supported
        "catalog_miss",       # no recipe in the catalog matches (advisory.package, ecosystem)
    ]
    diagnostics: dict[str, Any]
```

- `reason="matched"` ↔ `recipe is not None`. Other values ↔ `recipe is None`.
- The **`reason` enum is the public contract**. Phase 4 reads it to decide RAG vs. LLM fallback (`production ADR-0011`).
- `diagnostics` is free-form (probe outputs, engine-availability snapshot, semver attempts). Phase 4 may pass it as few-shot context to the LLM; Phase 5 may aggregate it across retries.
- The enum is **closed at v0.3.0**. Adding a new reason value requires an ADR amendment and a coordinated update to Phase 4's router.
- Phase 4 wraps the selector by calling it and branching on `reason`; never edits the selector itself.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 4's RAG → LLM-fallback chain reads `reason` to route — no audit-log parsing, no re-derivation | The enum is closed; adding a new "why no match" reason requires an ADR amendment + Phase-4 router update — coordination tax |
| `diagnostics` dict is open — implementer can record richer context (semver attempts, peer-dep graph slices) without contract churn | `diagnostics` is free-form; Phase 4 cannot rely on specific keys without a per-key contract (deferred to Phase 4 ADRs) |
| Property test `test_selector_is_total.py` (Hypothesis) asserts any `(advisory, repo_ctx, skills)` returns `RecipeSelection` without raising — total function | Total-function discipline forces every "weird input" to map to a `reason` value; the implementer must classify edge cases |
| One return type for both match and no-match — easier to mock, snapshot, and unit-test | Slightly heavier than a bare `Optional[Recipe]`; callers must read `.recipe` and `.reason` |
| `reason="no_engine"` makes ADR-0003's engine-availability filter visible in the contract — Phase 4 routes around missing JVM without re-checking | Engine availability is captured once per run (`phase-arch-design.md §"Gap 6"`); selector reads the snapshot, not by re-calling `available()` |
| Exit code 4 (`no_recipe`) is the operator-facing surface; orchestrator treats every `reason != "matched"` as exit 4 in Phase 3 — Phase 4 splits by reason | Operators see one exit code for all no-match cases; the audit event carries the specific reason — operator must read the log for diagnosis |

## Consequences

- `src/codegenie/recipes/models.py` defines `RecipeSelection`, `Recipe`, `RecipeApplication`.
- `src/codegenie/recipes/selector.py` returns `RecipeSelection`; no raising on no-match.
- `tests/unit/test_selector_reason_enum.py` asserts ≥ 14 cases — one per reason × matched/unmatched paths × engine-availability filter (`final-design.md §"Test plan" §"Unit tests"`).
- `tests/property/test_selector_is_total.py` asserts totality.
- Audit event `recipe.selected` includes `reason` and `diagnostics`.
- Orchestrator's Stage 3 exits with code 4 when `reason != "matched"`; the `TransformOutput(skipped=True, errors=[reason])` carries the reason for Phase 4 to read.
- Phase 4's planning coordinator reads `reason` and `diagnostics` from the audit chain (or in-process when wrapping the orchestrator directly); routes:
  - `catalog_miss` → solved-example RAG → LLM fallback
  - `range_break` → LLM (parameter widening)
  - `peer_dep_conflict` → LLM (peer-dep-aware planning)
  - `unsupported_dialect` → human escalation
  - `no_engine` → operator-fix (install JVM) or skip
- The `Optional[Recipe]` shape from `design-best-practices.md` is explicitly rejected; this ADR documents why.

## Reversibility

**Medium.** Collapsing back to `Optional[Recipe]` would break Phase 4's router (high cost — Phase 4 already reads `reason`). Adding a new reason value to the enum is **low cost in code** but **medium cost in coordination** — Phase 4 must learn the new value, and any solved-example store keyed on `reason` may need re-indexing. Adding a structured-`errors` field to `TransformOutput` (replacing the `list[str]`) is the natural Phase-4 evolution; deferred per `phase-arch-design.md §"Gap 1"`.

## Evidence / sources

- `../final-design.md §"Goals" §"Contract goals"` row 5 — structured-return commitment
- `../final-design.md §"Components" #3 "`recipes` selector + catalog"`
- `../final-design.md §"Departures from all three inputs"` #2
- `../final-design.md §"Synthesis ledger"` — closes "best-practices hidden assumption #1"
- `../phase-arch-design.md §"Component design" #3 "Recipe, RecipeSelector, catalog"`
- `../phase-arch-design.md §"Integration with Phase 4 (next phase)"`
- `../critique.md §"Attacks on best-practices" §"Hidden assumptions" #1` — the dismantling
- [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) — Recipe → RAG → LLM-fallback chain
- [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) — objective signals only
