# Story S1-01 — Add the RepoId newtype to the identifiers module

**Step:** Step 1 — Land the contract primitives and the runtime substrate
**Status:** HARDENED
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0010

## Validation notes (2026-05-26 — phase-story-validator)
Story hardened in place. Original draft was importable-name + registry-entry + one mypy assertion. Findings:
- **Critical (block):** the additive edit ripples into the *existing* fence `tests/unit/types/test_identifiers_phase3.py::test_all_is_exact_set` — that test asserts `set(ids.__all__) == PHASE2 ∪ PHASE3 ∪ PHASE3_LITERAL ∪ PHASE7_NEWTYPE ∪ PHASE7_TYPE_ALIAS ∪ PHASE4 ∪ PHASE6_NEWTYPE`. Adding `RepoId` to `__all__` without extending that union breaks the suite. Phase 6 (`PHASE6_NEWTYPE_NAMES = {...}`) and Phase 7 (`PHASE7_NEWTYPE_NAMES = {...}`) are the precedent: each phase added its set to the union. AC-7 below promotes this from an implementer-discovers-at-test-time surprise into a story-level commitment.
- **High (harden):** the original AC bundle was missing intent-verifying assertions that every prior phase enforces (`__name__` pinning, `__supertype__ is str`, `isinstance` raises `TypeError`, pairwise distinctness from every other newtype). Mutation-resistance was weak — the `assert rid == "acme/api"` test passes for *any* `NewType("X", str)`, so a `RepoId = NewType("RepoId", int)` typo would have slipped through.
- **High (harden):** the mypy-negative AC named no concrete swap pair. Phase 3's `test_identifiers_phase3_mypy_negative.py::SWAP_PAIRS` is the canonical subprocess-mypy harness; reuse-by-extension (add `("RepoId", "WorkflowId")` row) honours rule-of-three and avoids forking a new mypy harness for one pair.
- **Medium (harden):** the "free NewType, no grammar" decision (ADR-0010 / Open Question 7) was named in the Notes but not affirmatively asserted by a test. AC-8 adds a positive test that a *malformed* repo string (with no grammar) is accepted — proving the smart-constructor lift was *not* silently introduced.
- **Design-pattern observation (nit):** the new `tests/unit/types/test_identifiers_phase8.py` file is the rule-of-three trigger (Phase 6, Phase 7, Phase 8 each ship one). The Notes-for-implementer surface this — not as an AC — and explicitly defer extraction (Rule 2: three similar files are still better than premature abstraction; the rule-of-three threshold is *met* but the abstraction would touch every prior phase's test file, a Rule 3 violation).

Full critic reports and edit log: `_validation/S1-01-repoid-newtype.md`.

## Context
Every Phase-8 package threads a repository identifier through its public surface — `SupervisorState.repo_id`, `HotViewKey.repo_id`, `HotViewStore.get(repo, ...)`, `HotViewStore.get_all(repo)`, `SkillsMcpServer.list_skills(repo)`. The synthesis (`final-design.md`) assumed `RepoId` already lived in `codegenie.types.identifiers`; it does not (arch Gap 3). This is the foundational first story of the phase: every later Step-1+ signature imports this name, so it must land before any consumer or those consumers fall back to the stringly-typed-`str` anti-pattern.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Gap analysis & improvements §Gap 3` — `RepoId` does not exist; the synthesis uses it pervasively.
  - `../phase-arch-design.md §Data model` — the `RepoId = NewType("RepoId", str)` declaration line and the comment "does NOT exist today (Gap 3)".
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0010-repoid-newtype-in-the-identifiers-module.md` — ADR-0010 — Decision: add `RepoId = NewType("RepoId", str)` to `codegenie/types/identifiers.py` with the name in `__all__`; a free `NewType` (no `owner/name` grammar — Open Question 7 defers that to Phase 10).
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — newtype-for-domain-IDs discipline; never raw `str` for an identifier.
  - `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — a new newtype in the identifiers module is a sanctioned loud additive edit.
- **Existing code (if any):**
  - `src/codegenie/types/identifiers.py` — the kernel-tier `NewType` catalog; note the Phase-3 catalog block, the `__all__` list (alphabetically sorted), and the `_NEWTYPE_REGISTRY: Final[Mapping[str, str]]` docstring registry that every public name must appear in.
  - `tests/unit/types/test_identifiers_phase3.py` — `test_newtype_registry_matches_all` fences `__all__` against `_NEWTYPE_REGISTRY` for drift; the new name must be wired into both.

## Goal
Add `RepoId = NewType("RepoId", str)` to `codegenie/types/identifiers.py`, exported in `__all__` and registered in `_NEWTYPE_REGISTRY`, so every Phase-8 signature can type a repository identifier without falling back to raw `str`.

## Acceptance criteria
- [ ] **AC-1 — Importable + correct shape.** `from codegenie.types.identifiers import RepoId` succeeds and `RepoId.__supertype__ is str` and `RepoId.__name__ == "RepoId"` (mirrors Phase-3 `test_phase3_newtypes_are_newtype_over_correct_supertype` + Phase-3 AC-9 `test_newtype_names_pinned`). A bare `assert rid == "acme/api"` is *not* sufficient — any `NewType("X", str)` passes it; the `__supertype__` + `__name__` assertions are what catch a `NewType("RepoId", int)` typo or a name-mismatch refactor.
- [ ] **AC-2 — Alphabetical placement.** `"RepoId"` is present in `codegenie.types.identifiers.__all__` AND `ids.__all__ == sorted(ids.__all__)` (file convention — Phase-3 `test_all_is_exact_set` already enforces global sort; this AC names it as the touched-file invariant).
- [ ] **AC-3 — Registry entry with ADR-0010 citation.** `"RepoId"` has an entry in `_NEWTYPE_REGISTRY` whose value contains the literal `"ADR-0010"` (Phase-3 `else` branch of `test_newtype_registry_matches_all` covers this for *any* phase whose names aren't in the phase-specific sets) AND names ≥ 2 of the four Phase-8 consumers (`SupervisorState`, `HotViewKey`, `HotViewStore`, `SkillsMcpServer`) so the docstring is grep-traceable.
- [ ] **AC-4 — mypy --strict cross-newtype swap is a type error.** The Phase-3 subprocess-mypy harness `tests/unit/types/test_identifiers_phase3_mypy_negative.py::SWAP_PAIRS` gains a `("RepoId", "WorkflowId")` row (both are `NewType` over `str` — the swap must be a `mypy --strict` error). Reuse the existing harness; do NOT fork a Phase-8-specific subprocess-mypy file (rule-of-three: the harness IS the shared kernel for this assertion class).
- [ ] **AC-5 — `isinstance` raises `TypeError`.** `isinstance("foo", RepoId)` raises `TypeError` at runtime (`NewType` is not a class — Phase-3 AC-13 precedent).
- [ ] **AC-6 — Pairwise distinct.** `RepoId` is `is`-distinct from every other Phase-2 / Phase-3 / Phase-4 / Phase-6 / Phase-7 `NewType` in `codegenie.types.identifiers` (the Phase-6 `test_phase6_newtypes_pairwise_distinct` is the precedent — a tiny phase-local pairwise test, not a global one).
- [ ] **AC-7 — Central exact-set fence updated.** `tests/unit/types/test_identifiers_phase3.py` gains a `PHASE8_NEWTYPE_NAMES = {"RepoId"}` constant and the `test_all_is_exact_set` assertion is extended with `| PHASE8_NEWTYPE_NAMES`. This is the rippling additive edit the original story plan omitted; without it the existing fence trips and the *appearance* of a regression hides the real change. The change must show up in the diff (no silent edit to a fence — Rule 12: fail loud).
- [ ] **AC-8 — Free NewType, no validation (ADR-0010 / Open Question 7).** A positive test asserts that a syntactically malformed repo string (e.g., `"not even a slash separated thing"`, `""`, `"UPPER/CASE"`) is *accepted* by `RepoId(...)` at runtime — proof that no smart-constructor lift was silently introduced. When Phase 10 lands the `owner/name` grammar, this test changes shape; until then it pins the deliberate "no grammar" decision.
- [ ] **AC-9 — Process gate.** `ruff check`, `ruff format --check`, `mypy --strict src/`, and the full `pytest -q` suite all pass — including the touched `test_identifiers_phase3.py` fence and the new `test_identifiers_phase8.py` and `test_identifiers_phase3_mypy_negative.py` rows. The Phase-3 fence MUST be observed green *after* the AC-7 edit, not before — running it before would obscure whether the edit actually fixed the rippling break.

## Implementation outline
1. Add a Phase-8 catalog comment block to `src/codegenie/types/identifiers.py` after the Phase-7 catalog, with `RepoId = NewType("RepoId", str)` and a one-line comment naming the four Phase-8 consumers and Open Question 7 (grammar deferred to Phase 10).
2. Insert `"RepoId"` into `__all__` in alphabetical position (between `"RegistryUrl"` and `"RuntimeId"`).
3. Add a `"RepoId"` entry to `_NEWTYPE_REGISTRY` naming ADR-0010 and ≥ 2 of the four Phase-8 consumers (`SupervisorState`, `HotViewKey`, `HotViewStore`, `SkillsMcpServer`).
4. **Update the central exact-set fence (AC-7):** add `PHASE8_NEWTYPE_NAMES = {"RepoId"}` to `tests/unit/types/test_identifiers_phase3.py` and extend `test_all_is_exact_set`'s union with `| PHASE8_NEWTYPE_NAMES`. This is a *required* rippling additive edit (the same pattern Phase 6 / Phase 7 followed) — without it the fence trips and the new red test masquerades as the failure source.
5. **Extend the central mypy-negative swap matrix (AC-4):** add `("RepoId", "WorkflowId")` to `tests/unit/types/test_identifiers_phase3_mypy_negative.py::SWAP_PAIRS`. The subprocess-mypy harness is engine-shared across phases; do not fork a Phase-8 mirror.
6. Run `mypy --strict src/` and the full `pytest -q` suite to confirm the additive edit type-checks clean *and* every touched fence is green.

## TDD plan — red / green / refactor
### Red — write the failing tests first
Test file path: `tests/unit/types/test_identifiers_phase8.py` (mirrors the Phase-6 / Phase-7 per-phase file convention). Each test traces back to a single AC. All initially red because `RepoId` does not exist.

```python
"""Phase 8 S1-01 — RepoId newtype catalog fence.

AC-1, AC-2, AC-3, AC-5, AC-6, AC-8 from
docs/phases/08-hierarchical-planner-hot-views/stories/S1-01-repoid-newtype.md.

AC-4 (mypy --strict cross-newtype swap) lives in
test_identifiers_phase3_mypy_negative.py (extended SWAP_PAIRS row).
AC-7 (central exact-set fence) lives in test_identifiers_phase3.py
(extended PHASE8_NEWTYPE_NAMES constant + assertion union).
"""

from __future__ import annotations

import pytest

PHASE8_NEWTYPE_NAMES = {"RepoId"}


# --- AC-1 — Importable + correct shape ----------------------------------
def test_repoid_supertype_is_str_and_name_pinned() -> None:
    """AC-1 — supertype + __name__ pinning catch typos a bare equality misses.

    Intent: a NewType("RepoId", int) typo or a copy-paste mismatch
    (NewType("WorkflowId", str) re-exported as RepoId) would pass a bare
    `assert rid == "acme/api"` — these two assertions wouldn't.
    """
    from codegenie.types.identifiers import RepoId

    assert RepoId.__supertype__ is str
    assert RepoId.__name__ == "RepoId"


# --- AC-2 — Alphabetical placement --------------------------------------
def test_all_is_sorted_after_repoid_added() -> None:
    """AC-2 — touched-file invariant: __all__ stays alphabetically sorted."""
    import codegenie.types.identifiers as ids

    assert "RepoId" in ids.__all__
    assert ids.__all__ == sorted(ids.__all__)


# --- AC-3 — Registry entry + Phase-8 consumer trace ---------------------
def test_repoid_registry_entry_cites_adr_and_consumers() -> None:
    """AC-3 — registry value must be grep-traceable to ADR-0010 + consumers.

    A docstring of just "Phase-8 repo id." would pass a bare presence check
    but lose the grep-traceability the registry exists for.
    """
    from codegenie.types.identifiers import _NEWTYPE_REGISTRY

    assert "RepoId" in _NEWTYPE_REGISTRY
    doc = _NEWTYPE_REGISTRY["RepoId"]
    assert "ADR-0010" in doc
    consumers = ("SupervisorState", "HotViewKey", "HotViewStore", "SkillsMcpServer")
    hits = sum(c in doc for c in consumers)
    assert hits >= 2, f"RepoId docstring names {hits} Phase-8 consumers; need ≥ 2 — got: {doc!r}"


# --- AC-5 — isinstance raises TypeError (NewType is not a class) --------
def test_repoid_isinstance_raises_typeerror() -> None:
    """AC-5 — Phase-3 AC-13 precedent: NewType is not a class."""
    from codegenie.types.identifiers import RepoId

    with pytest.raises(TypeError):
        isinstance("acme/api", RepoId)  # type: ignore[arg-type]


# --- AC-6 — Pairwise distinct from every prior newtype ------------------
def test_repoid_is_distinct_from_every_other_newtype() -> None:
    """AC-6 — RepoId must be `is`-distinct from every other catalog member.

    A copy-paste accident (`RepoId = WorkflowId`) would pass everything
    above; this catches it. Mirrors the Phase-6
    test_phase6_newtypes_pairwise_distinct precedent.
    """
    import codegenie.types.identifiers as ids

    from tests.unit.types.test_identifiers_phase3 import (
        PHASE2_NAMES,
        PHASE3_NAMES,
        PHASE4_NAMES,
        PHASE6_NEWTYPE_NAMES,
        PHASE7_NEWTYPE_NAMES,
    )

    # Literals + TypeAlias rows are not NewType objects — exclude them.
    other_newtype_names = sorted(
        (PHASE2_NAMES | PHASE3_NAMES | PHASE4_NAMES | PHASE6_NEWTYPE_NAMES | PHASE7_NEWTYPE_NAMES)
        - {"PackageManager"}
    )
    repo_id = ids.RepoId
    for name in other_newtype_names:
        other = getattr(ids, name)
        assert repo_id is not other, f"RepoId is the same object as {name} — copy-paste accident"


# --- AC-8 — Free NewType, no smart-constructor lift (ADR-0010, OQ-7) ----
@pytest.mark.parametrize(
    "raw",
    [
        "",
        "UPPER/CASE",
        "not even slash-separated",
        "owner/repo/extra",   # too many slashes — would fail an owner/name grammar
        "owner​/repo",   # zero-width space — would fail an NFKC parser
    ],
)
def test_repoid_accepts_any_str_today(raw: str) -> None:
    """AC-8 — pins the deliberate "no grammar" decision (OQ-7 → Phase 10).

    If a future change silently lifts RepoId to a Pydantic smart constructor,
    THIS test must fail loudly — flipping the assertion is the intentional
    Phase-10 follow-up, not a regression.
    """
    from codegenie.types.identifiers import RepoId

    rid = RepoId(raw)
    assert rid == raw  # runtime identity-to-str
```

The AC-4 and AC-7 edits also start red:

```python
# tests/unit/types/test_identifiers_phase3.py — AC-7 edit
PHASE8_NEWTYPE_NAMES = {"RepoId"}

def test_all_is_exact_set() -> None:  # extended assertion
    ...
    assert (
        set(ids.__all__)
        == PHASE2_NAMES | PHASE3_NAMES | PHASE3_LITERAL_NAMES
        | PHASE7_NEWTYPE_NAMES | PHASE7_TYPE_ALIAS_NAMES
        | PHASE4_NAMES | PHASE6_NEWTYPE_NAMES
        | PHASE8_NEWTYPE_NAMES   # <-- new
    )

# tests/unit/types/test_identifiers_phase3_mypy_negative.py — AC-4 edit
SWAP_PAIRS: list[tuple[str, str]] = [
    ...,
    ("RepoId", "WorkflowId"),   # <-- new
]
```

### Green — make it pass
Four additive edits, no logic:
1. `RepoId = NewType("RepoId", str)` in `identifiers.py` after the Phase-7 block.
2. `"RepoId"` in `__all__` (alphabetical position between `"RegistryUrl"` and `"RuntimeId"`).
3. `"RepoId"` entry in `_NEWTYPE_REGISTRY` naming ADR-0010 + ≥ 2 consumers.
4. The two fence updates from AC-4 + AC-7 in their respective test files.

### Refactor — clean up
Confirm the comment block matches the catalog's existing per-phase comment style (Phase reference + consumer + ADR). Confirm `__all__` stayed alphabetically sorted. No docstring change beyond the inline comment. **Do not** introduce a smart constructor / regex — a bare `NewType` is the deliberate decision (ADR-0010 / Open Question 7); AC-8 guards against accidental lift.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Add the `RepoId` newtype, the `__all__` entry, the `_NEWTYPE_REGISTRY` entry. |
| `tests/unit/types/test_identifiers_phase8.py` | New test file — AC-1, AC-2, AC-3, AC-5, AC-6, AC-8 (importable shape, alphabetical, registry trace, isinstance, pairwise distinct, no-grammar). |
| `tests/unit/types/test_identifiers_phase3.py` | **Required rippling edit (AC-7):** add `PHASE8_NEWTYPE_NAMES = {"RepoId"}` and extend `test_all_is_exact_set`'s assertion union. Without this, the existing fence trips and the new red tests look like the cause. |
| `tests/unit/types/test_identifiers_phase3_mypy_negative.py` | **Required rippling edit (AC-4):** add `("RepoId", "WorkflowId")` to `SWAP_PAIRS`. The subprocess-mypy harness is shared across phases — extend, don't fork. |

## Out of scope
- An `owner/name` grammar and a smart-constructor lift for `RepoId` — deferred to Phase 10 Discovery (Open Question 7); the bare `NewType` is the additive seam where that grammar lands later.
- Any consumer of `RepoId` (Supervisor, HotView, MCP models) — those are Steps 2–8.

## Notes for the implementer
- **The order of red-then-green matters here.** Write all six new tests in `test_identifiers_phase8.py` plus the AC-4 and AC-7 fence updates *before* touching `identifiers.py`. Run them; confirm they fail for the right reason (`ImportError: cannot import name 'RepoId'` — not a SyntaxError, not a wrong-AssertionError). Only then add the four green edits.
- **The AC-7 ripple is the single non-obvious step.** The existing `test_all_is_exact_set` assertion is a closed union — adding `"RepoId"` to `__all__` breaks it unless `PHASE8_NEWTYPE_NAMES` is added to the union. This pattern was established by Phase 6 (`PHASE6_NEWTYPE_NAMES`) and Phase 7 (`PHASE7_NEWTYPE_NAMES`). Failing to do this and then silencing the fence by relaxing it (e.g., changing `==` to `<=`) is a Rule 12 violation — surface the rippling test edit in the diff.
- **`_NEWTYPE_REGISTRY` is load-bearing:** `test_newtype_registry_matches_all` asserts every `__all__` name has a registry entry. Phase 8's `RepoId` falls into the `else: assert "ADR-0010" in doc` branch (line 381–382 of `test_identifiers_phase3.py`) — that branch passes automatically as long as the docstring contains the literal `"ADR-0010"`. No phase-specific branch needs to be added.
- **This is a free `NewType`, deliberately.** Do not add a Pydantic smart constructor, regex, or `owner/name` parser now — that is the "premature" Option C ADR-0010 explicitly rejected, deferred to Phase 10 Discovery (Open Question 7). AC-8 is the test that catches an accidental lift.
- A `NewType` over `str` is identity-at-runtime and zero-overhead; the nominal-type guard exists only under `mypy --strict`. The cross-newtype swap (`RepoId` → `WorkflowId`) does NOT raise at runtime — that is exactly why the subprocess-mypy meta-test exists.
- **Open-Closed / extension-by-addition observation (design-patterns critic):** the per-phase test-file convention (`test_identifiers_phase3.py`, `test_identifiers_phase6.py`, `test_identifiers_phase7.py`, now `test_identifiers_phase8.py`) is the rule-of-three threshold for "extract a shared helper". The validator deliberately did NOT lift this — the per-phase files are tiny, the assertions are slightly phase-specific (e.g., Phase 6 requires `"ADR-0001"`, Phase 8 doesn't), and the extraction would force a Rule 3 cross-cutting edit to every prior phase's test file. The pattern *is* extension-by-addition as it stands; flagging it here for the historical record.
- **Out-of-scope cross-check:** do not re-export `RepoId` from `codegenie/types/__init__.py` in this story. That package-level re-export was *not* extended for Phase 6 (`VulnCaseId`, `RepoFixtureRef`, `SutDigest` are absent from `types/__init__.py::__all__`), so Phase 8 stays consistent with the prevailing convention — `from codegenie.types.identifiers import RepoId` is the supported import path. If Phase 8 consumers later need `from codegenie.types import RepoId`, that is a separate (additive, fence-policed) change.
