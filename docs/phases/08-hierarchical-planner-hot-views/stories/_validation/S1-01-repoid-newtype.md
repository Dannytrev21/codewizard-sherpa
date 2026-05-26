# Validation report — S1-01 Add the RepoId newtype to the identifiers module

**Date:** 2026-05-26
**Validator:** phase-story-validator (scheduled run — story-validation-corrector)
**Verdict:** **HARDENED**
**Story:** [`docs/phases/08-hierarchical-planner-hot-views/stories/S1-01-repoid-newtype.md`](../S1-01-repoid-newtype.md)
**Status transition:** `Ready` → `HARDENED`

## Context brief

- **Goal:** Add `RepoId = NewType("RepoId", str)` to `codegenie/types/identifiers.py`, exported in `__all__`, registered in `_NEWTYPE_REGISTRY` — so every Phase-8 signature (`SupervisorState.repo_id`, `HotViewKey.repo_id`, `HotViewStore.get(repo, ...)`, `SkillsMcpServer.list_skills(repo)`) can type a repository identifier without falling back to raw `str`.
- **Constraints (sourced):**
  - Phase-8 ADR-0010 — free `NewType`, no smart-constructor / grammar (Open Question 7 defers grammar to Phase 10).
  - Production ADR-0033 — newtype-for-domain-IDs discipline.
  - Production ADR-0043 — extension by addition; an additive newtype is a sanctioned loud edit.
  - CLAUDE.md "Newtype identifiers" + "Match the existing convention" — `__all__` alphabetically sorted, `_NEWTYPE_REGISTRY` mirrors `__all__`.
- **Existing kernel (read before writing):**
  - `src/codegenie/types/identifiers.py` — Phase-7 catalog block is the last existing block; `__all__` ends at `WorkflowId`.
  - `tests/unit/types/test_identifiers_phase3.py:309 test_all_is_exact_set` — closed-union exact-set fence over `PHASE2 ∪ PHASE3 ∪ PHASE3_LITERAL ∪ PHASE7_NEWTYPE ∪ PHASE7_TYPE_ALIAS ∪ PHASE4 ∪ PHASE6_NEWTYPE`. **Adding `RepoId` to `__all__` without extending this union breaks the suite.**
  - `tests/unit/types/test_identifiers_phase3.py:353 test_newtype_registry_matches_all` — `else: assert "ADR-0010" in doc` branch covers Phase 8 automatically (no new branch needed).
  - `tests/unit/types/test_identifiers_phase3_mypy_negative.py::SWAP_PAIRS` — Phase-3 subprocess-mypy harness. Reuse-by-extension is the established rule-of-three pattern (Phase 6 + Phase 7 mypy negatives also extend it).
  - `tests/unit/types/test_identifiers_phase6.py` + `tests/unit/types/test_identifiers_phase7.py` — per-phase test-file precedent (Phase 8 follows).

## Stage 2 — Critic findings

### Coverage critic

| # | Finding | Severity | Fix |
|---|---|---|---|
| C-1 | Original AC set missed `__supertype__ is str`, `__name__ == "RepoId"`, `isinstance` raises `TypeError`, pairwise distinctness. Every prior phase fences these. | harden | New AC-1 (supertype + name), AC-5 (isinstance), AC-6 (pairwise distinct). |
| C-2 | "Alphabetically placed" was a phrase in the AC body but no test verified it. Phase-3 enforces global sort; Phase-8 should name it as a touched-file invariant. | harden | New AC-2 with explicit `sorted(__all__)` assertion. |
| C-3 | Registry-entry AC only required `"ADR-0010"` literal — too lax. The registry exists to be grep-traceable to consumers; a docstring of "Phase-8 repo id." would pass. | harden | New AC-3 requires ≥ 2 of the four Phase-8 consumer names in the docstring. |
| C-4 | **CRITICAL** — story did not mention updating `tests/unit/types/test_identifiers_phase3.py::test_all_is_exact_set`. This existing fence is a closed-union check; adding `RepoId` without extending the union trips it. Phase 6 + Phase 7 followed this rippling pattern; Phase 8 must too. | block | New AC-7 — required rippling fence update with explicit instruction to make the change visible in the diff. |
| C-5 | "Free NewType, no validation" was a Note for the implementer but no test affirmed it. A future silent lift to a Pydantic smart constructor would go undetected. | harden | New AC-8 — parametrized test asserts deliberately malformed strings are accepted today. |

### Test-quality critic

| # | Finding | Severity | Fix |
|---|---|---|---|
| T-1 | Original test `assert rid == "acme/api"` is weakly mutation-resistant — any `NewType("X", str)` passes it. Would not catch `NewType("RepoId", int)`, `NewType("WorkflowId", str)` rename-typo, or a copy-paste from another newtype. | harden | Rewrote first test as `test_repoid_supertype_is_str_and_name_pinned` (AC-1) with explicit intent comment. |
| T-2 | The mypy-negative AC named no concrete swap pair and no harness; an implementer might fork a new `test_identifiers_phase8_mypy_negative.py` (anti-rule-of-three) or invent an ad-hoc inline check. | harden | AC-4 names the exact harness extension: add `("RepoId", "WorkflowId")` to the existing `SWAP_PAIRS`. |
| T-3 | TDD plan's two tests covered only two ACs, leaving four un-tested. | harden | New TDD plan covers AC-1, AC-2, AC-3, AC-5, AC-6, AC-8 with one test per AC; AC-4 + AC-7 land as fence extensions and are called out separately. |
| T-4 | AC-9 (process gate) was not differentiated from AC-5 ("red test exists, is green"). The latter is implicit in TDD discipline; the former is the ruff/mypy/pytest gate. | nit | Merged into a single AC-9 process gate. |

### Consistency critic

| # | Finding | Severity | Fix |
|---|---|---|---|
| K-1 | ADR-0010 + Open Question 7 explicitly defer the grammar/smart-constructor to Phase 10. Story honors. ✅ | — | None. |
| K-2 | Story's "alphabetical position between RegistryUrl and RuntimeId" matches `__all__` ordering. ✅ | — | None. |
| K-3 | CLAUDE.md "Match existing convention" — per-phase test-file naming (Phase 6 + Phase 7 precedent). Story honors. ✅ | — | None. |
| K-4 | Story did not address whether `codegenie/types/__init__.py` should also re-export `RepoId`. Phase 6 names (`VulnCaseId`, `RepoFixtureRef`, `SutDigest`, `TransitionId`) are *not* re-exported there (verified by reading the file); so Phase 8 staying out is consistent. | nit | Added explicit out-of-scope note in Notes-for-implementer. |
| K-5 | Test-quality finding T-2 would, if mis-handled, fork a new mypy harness file — that would violate the rule-of-three convention. | block-if-mishandled | AC-4 explicitly forbids forking. |

### Design-patterns critic

| # | Finding | Severity | Fix |
|---|---|---|---|
| D-1 | The story prescribes the textbook **Newtype pattern** — zero-overhead nominal type. Matches ADR-0010. ✅ | — | None. |
| D-2 | `_NEWTYPE_REGISTRY` is a **registry pattern** — adding `RepoId` is one row, no kernel edit. The fence `test_newtype_registry_matches_all` is the Open/Closed enforcement. ✅ | — | None. |
| D-3 | Per-phase test files are at the rule-of-three threshold (Phase 3, 6, 7, now 8). Considered extracting a shared `assert_phase_newtype_catalog(...)` helper — REJECTED. (a) Each phase has slightly different ADR-citation rules (Phase 6 requires `ADR-0001`, Phase 7 requires `ADR-0004` or `ADR-0006`, Phase 8 needs only `ADR-0010`); a generic helper would need to thread phase-specific config and become harder to read than the duplication it replaces. (b) Extracting now would force a Rule 3 cross-cutting edit to every prior phase's test file. (c) The current pattern *is* extension-by-addition for the test-file dimension — adding a phase is one new file, no edits to prior ones. | nit (informational) | Added explanatory note for posterity (Notes-for-implementer last bullet). |
| D-4 | The AC-4 "extend the shared SWAP_PAIRS list, do not fork" instruction IS the Open/Closed seam for the cross-newtype mypy harness — adding a new row is additive, no harness rewrite. ✅ | — | None. |
| D-5 | Implementation outline correctly uses `NewType` (Newtype pattern), not a tagged dataclass or Pydantic model — avoids the "primitive obsession on the *value*" trap (smart constructor) AND the "wrapper-everything" trap (anaemic class). ✅ | — | None. |

## Stage 3 — Researcher

No findings tagged `NEEDS RESEARCH`. Stage 3 skipped (token economy).

## Stage 4 — Editor — edits applied

| Section | Change |
|---|---|
| Story header — `Status:` | `Ready` → `HARDENED`. |
| **NEW** — `Validation notes` block after header | Records critical, high, medium findings and the design-pattern non-extraction observation. |
| `Acceptance criteria` | Replaced 6 ACs with 9, all carrying explicit `AC-N — <name>` prefixes that trace to the TDD plan. AC-1 (importable + correct shape), AC-2 (alphabetical placement), AC-3 (registry + consumer trace), AC-4 (mypy --strict swap — extends shared harness), AC-5 (isinstance TypeError), AC-6 (pairwise distinct), AC-7 (**central exact-set fence rippling update — was missing**), AC-8 (free NewType — no validation), AC-9 (process gate). Every AC carries WHY (intent), not just WHAT (behavior). |
| `Implementation outline` | Was 4 steps. Now 6 — adds explicit "update the central exact-set fence" step (4) and "extend the mypy swap matrix" step (5). Each step calls out the rule-of-three / additive-edit rationale inline. |
| `TDD plan — Red` | Was 2 tests (~20 lines). Now 6 tests (~80 lines) — one per AC-1, AC-2, AC-3, AC-5, AC-6, AC-8, plus the AC-4 + AC-7 fence-extension snippets. Each test carries an intent comment explaining *what mutation it catches*. The first test's intent comment explicitly names the mutation a bare `assert rid == "acme/api"` misses. |
| `TDD plan — Green` | Edits ennumerated as 4 (was 3) — adds the fence updates. |
| `TDD plan — Refactor` | Explicitly forbids introducing a smart constructor / regex; AC-8 named as the guard. |
| `Files to touch` | Was 2 rows. Now 4 — adds the two rippling fence-edit files with `**Required rippling edit**` callouts and rationale. |
| `Notes for the implementer` | Was 4 bullets. Now 6 — adds (a) order-of-red-then-green discipline, (b) AC-7 ripple explanation with explicit Rule-12 warning against silencing the fence, (c) design-pattern non-extraction explanation, (d) out-of-scope cross-check on `codegenie/types/__init__.py` package-level re-export. |
| `Out of scope` | Unchanged — original scope holds. |
| `Goal` | Unchanged — original goal is correct and trace-able. |

## Conflict resolution

- **Consistency vs Coverage on the `types/__init__.py` re-export.** Coverage was *not* asked to flag this; Consistency surfaced it as a non-finding (K-4) — Phase 6 precedent skips the package-level re-export, so Phase 8 doing the same is *consistent*. No conflict; added a Notes-for-implementer line confirming the deliberate omission.
- **Design-Patterns vs Rule 2/3 on the per-phase test-file extraction.** Design-Patterns flagged rule-of-three; Rule 2 ("three similar lines is better than premature abstraction") + Rule 3 ("don't refactor what isn't broken") win. Surfaced as an informational note, NOT an AC — the validator does not push design-pattern advice past CLAUDE.md's YAGNI threshold.

## Verdict — HARDENED

The story had one **block-severity gap** (AC-7: the existing exact-set fence's rippling update was missing — a "story passes its own tests in isolation but breaks the suite" failure mode) and several **harden-severity gaps** (mutation-weak first test, missing intent-verifying ACs, unspecified mypy swap pair, no guard against silent smart-constructor lift).

All edits applied in place; the story is now ready for `phase-story-executor`. The Goal and core scope are unchanged.

## Sources

- [`docs/phases/08-hierarchical-planner-hot-views/phase-arch-design.md`](../../phase-arch-design.md) §Gap 3, §Data model, §Open question 7
- [`docs/phases/08-hierarchical-planner-hot-views/ADRs/0010-repoid-newtype-in-the-identifiers-module.md`](../../ADRs/0010-repoid-newtype-in-the-identifiers-module.md)
- [`src/codegenie/types/identifiers.py`](../../../../../src/codegenie/types/identifiers.py)
- [`tests/unit/types/test_identifiers_phase3.py`](../../../../../tests/unit/types/test_identifiers_phase3.py) (lines 212–323, 353–382)
- [`tests/unit/types/test_identifiers_phase3_mypy_negative.py`](../../../../../tests/unit/types/test_identifiers_phase3_mypy_negative.py)
- [`tests/unit/types/test_identifiers_phase6.py`](../../../../../tests/unit/types/test_identifiers_phase6.py)
- `CLAUDE.md` — "Newtype identifiers", "Match the existing convention", "Fail loud" (Rule 12), "Don't refactor what isn't broken" (Rule 3)
