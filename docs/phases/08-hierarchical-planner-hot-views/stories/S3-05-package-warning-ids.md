# Story S3-05 — Declare per-package warning IDs validated at import

**Step:** Step 3 — Declare the planner ports and extend the event union
**Status:** Ready
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0007 (Phase 1)

## Context
Every component in the codebase logs through `structlog` with regex-validated warning/error IDs — and each module declares a module-level `_WARNING_IDS: Final[frozenset[str]]` validated at import time so a typo'd ID refuses to load the module rather than slipping silently into a slice. Phase 8's four new packages must conform. This is cross-cutting hygiene work: it makes the later integrity-miss, Redis-fallback, and `RouteDescended` log calls draw from a compile-time-checked vocabulary (Rule 12 — never silent).

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Harness engineering` — "each package declares a module-level `_WARNING_IDS: Final[frozenset[str]]` validated at import via `raise AssertionError(...)`"; warning IDs match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
  - `../README.md §Cross-cutting concerns` — "`structlog` logging with regex-validated IDs … hot-view integrity misses, Redis fallbacks, `RouteDescended` events, and MCP-process death all log explicitly — never silent."
- **Production ADRs (if applicable):**
  - Phase 1 ADR-0007 — the warning-ID regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`; per-module `_WARNING_IDS` validated at import.
- **Existing code (if any):**
  - `src/codegenie/probes/ci.py` (lines ~160–187) — the canonical precedent: `_WARNING_IDS: Final[frozenset[str]]`, an `_ID_PATTERN` regex compiled once, and a module-bottom `for _id in _WARNING_IDS: assert _ID_PATTERN.match(_id), ...` loop. Note: bare `assert` is forbidden by the `forbidden-patterns` hook in `src/` — use `raise AssertionError(...)`.
  - `src/codegenie/probes/deployment.py`, `src/codegenie/probes/test_inventory.py` — two more precedents.

## Goal
Each of the four new packages (`codegenie.supervisor`, `codegenie.planner`, `codegenie.hotviews`, `codegenie.mcp`) declares a module-level `_WARNING_IDS: Final[frozenset[str]]` validated at import against the ADR-0007 regex.

## Acceptance criteria
- [ ] Each of the four new packages declares a module-level `_WARNING_IDS: Final[frozenset[str]]` — in the package `__init__.py` or a dedicated `_warnings.py` module, whichever the package's structure makes natural.
- [ ] Each `_WARNING_IDS` contains the warning IDs that package will actually log (e.g. `hotviews`: `hotview.integrity_miss`, `hotview.redis_unreachable`; `planner`: `planner.route_descended`, `planner.leaf_llm_unavailable`; `supervisor`: `supervisor.universal_fallback`; `mcp`: `mcp.process_death`) — exact IDs are the implementer's call but each must name a real, anticipated log event, not a placeholder.
- [ ] Every ID in every `_WARNING_IDS` matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`, validated at import via a module-bottom `for _id in _WARNING_IDS: ... raise AssertionError(...)` loop — **never a bare `assert`** (forbidden in `src/`).
- [ ] A test confirms that importing each new package succeeds (the at-import validation passes) and that a deliberately malformed ID (e.g. `"Hotview.Bad-Id"`) fed to the shared validator raises `AssertionError`.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. For each new package, decide where `_WARNING_IDS` lives (`__init__.py` for small packages, a `_warnings.py` for ones that grow) — match the `probes/ci.py` precedent's placement.
2. Compile an `_ID_PATTERN` regex once per module (or import one shared compiled pattern if the codebase exposes one — check `codegenie.types` first).
3. Declare each `_WARNING_IDS` frozenset with the anticipated IDs and a module-bottom validation loop using `raise AssertionError(...)`.
4. Write the import-success + malformed-ID-rejection test.
5. Run `mypy --strict` and the `forbidden-patterns` pre-commit hook (it bans bare `assert` in `src/`).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/test_phase08_warning_ids.py`
Assert each package's `_WARNING_IDS` exists, is valid, and that a bad ID is rejected.
```python
import re
import pytest

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

@pytest.mark.parametrize("module", [
    "codegenie.supervisor", "codegenie.planner",
    "codegenie.hotviews", "codegenie.mcp",
])
def test_package_warning_ids_match_adr_0007_regex(module: str) -> None:
    # arrange: import the package and read its _WARNING_IDS frozenset
    # act:    iterate every id
    # assert: every id matches _ID_PATTERN; _WARNING_IDS is a non-empty frozenset

def test_malformed_warning_id_is_rejected_at_import() -> None:
    # arrange: a malformed id "Hotview.Bad-Id"
    # act:    run it through the same validation the modules use
    # assert: the validation raises AssertionError — a typo refuses to load
```
### Green — make it pass
Add `_WARNING_IDS` + the at-import validation loop to each of the four packages.
### Refactor — clean up
Confirm each ID names a *real* anticipated log event tied to a §Edge cases entry (integrity miss → edge case 5; Redis unreachable → edge case 4; `RouteDescended` → edge case 8; MCP death → edge case 11). Add a one-line module comment naming Phase 1 ADR-0007. Verify the `forbidden-patterns` hook is satisfied (no bare `assert`).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/supervisor/__init__.py` (or `_warnings.py`) | Declare `_WARNING_IDS` + at-import validation. |
| `src/codegenie/planner/__init__.py` (or `_warnings.py`) | Declare `_WARNING_IDS` + at-import validation. |
| `src/codegenie/hotviews/__init__.py` (or `_warnings.py`) | Declare `_WARNING_IDS` + at-import validation. |
| `src/codegenie/mcp/__init__.py` (or `_warnings.py`) | Declare `_WARNING_IDS` + at-import validation. |
| `tests/unit/test_phase08_warning_ids.py` | Red test — per-package regex conformance + malformed-ID rejection. |

## Out of scope
- The actual `structlog` log calls that *use* these IDs — they land with their owning logic (integrity miss in S5-02, `RouteDescended` in S7-05, MCP death in S8-02).
- New package source files beyond `__init__.py` / `_warnings.py` — created by their owning stories (S3-01 already creates `planner/__init__.py`; S3-02 creates `hotviews/__init__.py`).

## Notes for the implementer
- `_WARNING_IDS` is a frozenset, declared `Final`, validated at the **bottom of the module** so import fails loudly on a typo — this is the Rule 12 "fail loud" discipline, not decoration.
- Use `raise AssertionError(...)`, never a bare `assert` — the `forbidden-patterns` pre-commit hook bans `assert(` in `src/`. The `probes/ci.py` precedent uses bare `assert`; that predates the hook for that file — match the *current* convention (`raise AssertionError`), not the older file.
- Each ID must name a *real* anticipated log event — do not pad the frozensets with placeholder IDs to look complete. An empty-ish but honest set is correct; the owning stories add IDs as they add log calls. If a package has no anticipated warning yet, declare an empty frozenset and note it in the attempt log rather than inventing IDs.
- Some new package `__init__.py` files are created by sibling stories (S3-01, S3-02). Coordinate: this story *adds to* those files if they already exist, or creates `_warnings.py` if cleaner. Do not duplicate or clobber a sibling story's `__all__`.
- The regex is `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` — exactly one dot, lowercase, no hyphens, no colons (colon-suffixed IDs violate ADR-0007 per the `ci.py` docstring's CN-1 note).
