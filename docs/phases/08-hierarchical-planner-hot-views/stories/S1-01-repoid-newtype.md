# Story S1-01 — Add the RepoId newtype to the identifiers module

**Step:** Step 1 — Land the contract primitives and the runtime substrate
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0010

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
- [ ] `from codegenie.types.identifiers import RepoId` succeeds; `RepoId` is a `NewType` over `str`.
- [ ] `"RepoId"` is present in `codegenie.types.identifiers.__all__` (alphabetically placed).
- [ ] `"RepoId"` has an entry in `_NEWTYPE_REGISTRY` whose value names ADR-0010 and the Phase-8 consumers.
- [ ] A `mypy --strict` check confirms passing a `WorkflowId` where a `RepoId` is expected is a type error (negative type assertion documented in the test).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Add a Phase-8 catalog comment block to `src/codegenie/types/identifiers.py` after the Phase-7 catalog, with `RepoId = NewType("RepoId", str)` and a one-line comment naming the four Phase-8 consumers and Open Question 7 (grammar deferred to Phase 10).
2. Insert `"RepoId"` into `__all__` in alphabetical position (between `"RegistryUrl"` and `"RuntimeId"`).
3. Add a `"RepoId"` entry to `_NEWTYPE_REGISTRY` naming ADR-0010 and the Phase-8 consumers.
4. Run `mypy --strict src/` to confirm the additive edit type-checks clean.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/types/test_identifiers_phase8.py`
One red test per behavior. Initially red because `RepoId` does not exist.

```python
def test_repoid_is_importable_newtype() -> None:
    # Intent: Phase-8 signatures depend on this name existing (Gap 3).
    from codegenie.types.identifiers import RepoId
    # arrange/act: construct a RepoId from a str
    rid = RepoId("acme/api")
    # assert: it is identity-to-str at runtime, distinct nominal type for mypy
    assert rid == "acme/api"

def test_repoid_in_all_and_registry() -> None:
    # Intent: __all__ + _NEWTYPE_REGISTRY must not drift (mirrors the
    # Phase-3 test_newtype_registry_matches_all guard).
    from codegenie.types import identifiers
    assert "RepoId" in identifiers.__all__
    assert "RepoId" in identifiers._NEWTYPE_REGISTRY
    # the registry value documents ADR-0010 traceability
    assert "ADR-0010" in identifiers._NEWTYPE_REGISTRY["RepoId"]
```

### Green — make it pass
Add the `RepoId = NewType("RepoId", str)` line plus the `__all__` and `_NEWTYPE_REGISTRY` entries — three additive edits, no logic.

### Refactor — clean up
Confirm the comment block matches the catalog's existing comment style (Phase reference + consumer + ADR). Confirm `__all__` stays alphabetically sorted (the file's existing convention). No docstring change beyond the inline comment. No edge cases touch this code — a bare `NewType` carries no validation (deliberate, per ADR-0010 / Open Question 7).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Add the `RepoId` newtype, the `__all__` entry, the `_NEWTYPE_REGISTRY` entry. |
| `tests/unit/types/test_identifiers_phase8.py` | New test file — the red test for the newtype, `__all__`, and registry. |

## Out of scope
- An `owner/name` grammar and a smart-constructor lift for `RepoId` — deferred to Phase 10 Discovery (Open Question 7); the bare `NewType` is the additive seam where that grammar lands later.
- Any consumer of `RepoId` (Supervisor, HotView, MCP models) — those are Steps 2–8.

## Notes for the implementer
- The `__all__` list in `identifiers.py` is alphabetically sorted — keep it sorted or the file's own convention check will surface drift.
- `_NEWTYPE_REGISTRY` is load-bearing: `tests/unit/types/test_identifiers_phase3.py::test_newtype_registry_matches_all` asserts every `__all__` name has a registry entry. Omitting the registry entry will break an existing test — that is the fence working, not a regression to silence.
- This is a free `NewType`, deliberately — do not add a Pydantic smart constructor or regex now (that would be the "premature" Option C ADR-0010 rejected).
- A `NewType` over `str` is identity-at-runtime and zero-overhead; the nominal-type guard exists only under `mypy --strict`.
