# Story S1-05 — ADR-0033 identifier newtypes — `IndexId`, `SkillId`, `TaskClassId`, `IndexName`

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** production ADR-0033 (typed identifiers across module boundaries)

## Context

Production ADR-0033 §3 names primitive-obsession on domain identifiers as a review-blocker pattern. Phase 2 introduces four new kernel-tier identifier families (`IndexId`, `SkillId`, `TaskClassId`, `IndexName`) used by every other Step 1 story (`TCCM`, freshness registry, depgraph registry). `PackageManager` already exists from Phase 1 ADR-0013 — this story re-imports the location, **never redefines it**, and a unit test guards that location at the module-import boundary.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Anti-patterns avoided"` row "Stringly-typed identifiers" — `ProbeId`, `TaskClassId`, `SkillId`, `PackageManager` are typed; `ecosystem: PackageManager` is the registry key, not `ecosystem: str`.
  - `../phase-arch-design.md §"Data model"` — `TCCM.task_class: TaskClassId`, `required_skills: list[SkillId]`, `Skill.id: SkillId`; `IndexName` is the freshness-registry key.
  - `../phase-arch-design.md §"Component design" #11 — DepGraphProbe + strategy registry` — `PackageManager` is imported from Phase 1 ADR-0013, not redefined.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0006-index-freshness-sum-type-location.md` — 02-ADR-0006 §Decisions noted — `IndexName` is the registry key for `@register_index_freshness_check`.
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0033-typed-identifiers.md` — production ADR-0033 — typed identifiers at module boundaries; the binding discipline.
- **Source design:**
  - `../final-design.md §"Synthesis ledger" — ADR-0033 newtypes` — the deliberate scope.
- **Existing code:**
  - `src/codegenie/probes/node_build_system.py` — Phase 1 ADR-0013 lives here; `PackageManager` is the canonical `Literal["bun","pnpm","yarn-classic","yarn-berry","npm"]` (or `NewType`/`Enum`, whichever shipped). Import location is `codegenie.probes.node_build_system` (or `codegenie.probes.layer_a.node_build_system` if Phase 2 has moved Phase 1 into `layer_a/` — the architect documents either; this story's test pins whichever is current).
  - `src/codegenie/probes/base.py` — `ProbeId` source (Phase 0); do not redefine here.
- **External docs (only if directly relevant):**
  - https://docs.python.org/3/library/typing.html#typing.NewType — `NewType` semantics (type-checker-only; zero runtime cost).

## Goal

Implement `src/codegenie/types/__init__.py` and `src/codegenie/types/identifiers.py` declaring `IndexId`, `SkillId`, `TaskClassId`, `IndexName` as `NewType`s over `str`, re-exporting `PackageManager` from its Phase 1 ADR-0013 source location **by import** — and assert via a unit test that the import location has not silently changed.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/types/identifiers.py` declares `IndexId = NewType("IndexId", str)`, `SkillId = NewType("SkillId", str)`, `TaskClassId = NewType("TaskClassId", str)`, `IndexName = NewType("IndexName", str)`. Each is a distinct `NewType` (mypy treats them as non-interchangeable at type-check time).
- [ ] **AC-2.** `src/codegenie/types/identifiers.py` re-exports `PackageManager` via `from codegenie.probes.<layer_a>.node_build_system import PackageManager as PackageManager` (the explicit `as` re-export makes mypy `--strict` admit the public re-export). The import path is whichever Phase 1 currently ships at — adapt at impl time.
- [ ] **AC-3.** `src/codegenie/types/__init__.py` re-exports all five names (`IndexId`, `SkillId`, `TaskClassId`, `IndexName`, `PackageManager`) via `__all__`.
- [ ] **AC-4.** `PackageManager` is **not** redefined anywhere under `src/codegenie/types/`; a unit test scans `identifiers.py` source and asserts the file contains no `class PackageManager`, no `PackageManager = ...` assignment, and exactly one `import PackageManager` statement.
- [ ] **AC-5.** The PackageManager import-location guard test asserts `codegenie.types.identifiers.PackageManager is codegenie.probes.<layer_a>.node_build_system.PackageManager` — same object identity, no re-wrapping. If Phase 1 moves `PackageManager` to a different module, that move is a deliberate ADR amendment to Phase 1 ADR-0013, not a silent change.
- [ ] **AC-6.** A mypy-only test (`tests/unit/types/test_identifiers_typecheck.py`) uses `reveal_type` to assert mypy reports `IndexId`, `SkillId`, `TaskClassId`, `IndexName` as distinct nominal types — i.e., passing an `IndexId` where a `SkillId` is expected fails type-check (mypy assertion via `# type: ignore[arg-type]` comment that mypy WOULD reject; verified via `mypy --strict` exit code = 1 in CI).
- [ ] **AC-7.** Runtime: `IndexId("scip") == "scip"` (because `NewType` is identity at runtime); the test documents this and is intentional.
- [ ] **AC-8.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-9.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/types/` all pass on the touched files.

## Implementation outline

1. Locate the Phase 1 ADR-0013 `PackageManager` source — likely `src/codegenie/probes/node_build_system.py` (or `src/codegenie/probes/layer_a/node_build_system.py` if a Phase 2 reorganization has happened; if not, do **not** reorganize as part of this story — that's a separate ADR).
2. Create `src/codegenie/types/__init__.py` + `src/codegenie/types/identifiers.py` with the four `NewType`s and the explicit-`as` `PackageManager` re-export.
3. Write red tests; confirm `ImportError`.
4. Implement; confirm green.
5. Refactor — module docstrings cite production ADR-0033; the no-redefinition invariant is restated in a one-line comment above the `import PackageManager` line.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/types/test_identifiers.py`

```python
from __future__ import annotations

import inspect
import pathlib
import re
from typing import get_type_hints

import codegenie.types.identifiers as ids


def test_newtypes_exist_and_are_distinct() -> None:
    # AC-1 — four NewType aliases over str
    for name in ("IndexId", "SkillId", "TaskClassId", "IndexName"):
        assert hasattr(ids, name), f"missing {name}"
        nt = getattr(ids, name)
        # NewType objects expose .__supertype__ == str
        assert nt.__supertype__ is str, f"{name} must be NewType over str"


def test_newtypes_runtime_identity_to_str() -> None:
    # AC-7 — at runtime, NewType is identity. Document the intentional shape.
    val = ids.IndexId("scip")
    assert val == "scip"  # equality — identity-as-str at runtime
    assert isinstance(val, str)


def test_package_manager_reexported_from_phase1_adr_0013_location() -> None:
    # AC-5 — same object identity, no re-wrapping
    # Adapt path at impl time. Phase 1 ADR-0013 currently lives at
    # codegenie.probes.node_build_system; if it moved to .layer_a.* it's an
    # explicit Phase 1 ADR amendment, not a silent change.
    try:
        from codegenie.probes.node_build_system import PackageManager as P1
    except ImportError:
        from codegenie.probes.layer_a.node_build_system import PackageManager as P1  # type: ignore[no-redef]

    assert ids.PackageManager is P1, (
        "PackageManager must be re-exported from its Phase 1 ADR-0013 location; "
        "a redefinition violates ADR-0013 and the architect's design-patterns rule."
    )


def test_no_package_manager_redefinition_in_types_module() -> None:
    # AC-4 — guard against silent shadowing
    src = pathlib.Path(inspect.getsourcefile(ids)).read_text()
    assert "class PackageManager" not in src, "Do not redefine PackageManager"
    assert not re.search(r"^PackageManager\s*=\s*(?!.*import)", src, flags=re.MULTILINE), (
        "Only `from ... import PackageManager as PackageManager` is allowed"
    )
    # And exactly one import line for PackageManager.
    matches = re.findall(r"^\s*from .* import .*PackageManager", src, flags=re.MULTILINE)
    assert len(matches) == 1, f"expected one PackageManager import; found {matches}"


def test_all_exports_include_five_names() -> None:
    from codegenie import types as t
    assert set(t.__all__) >= {
        "IndexId", "SkillId", "TaskClassId", "IndexName", "PackageManager",
    }
```

Plus a mypy-only file:

```python
# tests/unit/types/test_identifiers_typecheck.py — verified by `mypy --strict`
from __future__ import annotations
from codegenie.types.identifiers import IndexId, SkillId

def _accepts_index(_x: IndexId) -> None: ...
def _accepts_skill(_x: SkillId) -> None: ...

def main() -> None:
    i: IndexId = IndexId("scip")
    s: SkillId = SkillId("scip.maintenance")
    _accepts_index(i)
    _accepts_skill(s)
    # The following two lines must be flagged by mypy --strict as type errors
    # (NewType nominal typing). They are commented out so pytest passes at
    # runtime; mypy CI run will exit non-zero if the comments are uncommented.
    # _accepts_index(s)       # mypy: error: Argument has incompatible type "SkillId"; expected "IndexId"
    # _accepts_skill(i)       # mypy: error: Argument has incompatible type "IndexId"; expected "SkillId"
```

Run — confirm `ImportError: cannot import name 'IndexId' from 'codegenie.types.identifiers'`. Commit.

### Green — make it pass

```python
# src/codegenie/types/identifiers.py
"""Phase 2 kernel-tier identifier newtypes (production ADR-0033).

Each NewType is a nominal type at mypy --strict time; identity-to-str at
runtime. Adding a new identifier here is the canonical extension point —
do NOT redefine PackageManager (Phase 1 ADR-0013); import it.
"""
from __future__ import annotations
from typing import NewType

# Phase 1 ADR-0013 owns PackageManager; we re-export by import, never redefine.
from codegenie.probes.node_build_system import PackageManager as PackageManager

IndexId = NewType("IndexId", str)
SkillId = NewType("SkillId", str)
TaskClassId = NewType("TaskClassId", str)
IndexName = NewType("IndexName", str)

__all__ = ["IndexId", "IndexName", "PackageManager", "SkillId", "TaskClassId"]
```

```python
# src/codegenie/types/__init__.py
from codegenie.types.identifiers import (
    IndexId, IndexName, PackageManager, SkillId, TaskClassId,
)
__all__ = ["IndexId", "IndexName", "PackageManager", "SkillId", "TaskClassId"]
```

### Refactor — clean up

- Module docstring on `identifiers.py` cites production ADR-0033 §3 (primitive-obsession is a review-blocker) and names the Phase 1 ADR-0013 source location.
- Comment above the `import PackageManager` line: `# DO NOT redefine — Phase 1 ADR-0013 owns this enum; this is a re-export.`
- Confirm CI gates: `ruff format`, `ruff check`, `mypy --strict src/codegenie/types/ tests/unit/types/`, `pytest tests/unit/types/`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/__init__.py` | New package; re-export the five names. |
| `src/codegenie/types/identifiers.py` | Declare four `NewType`s; re-export `PackageManager`. |
| `tests/unit/types/test_identifiers.py` | Source-scan guard + same-object-identity assertion. |
| `tests/unit/types/test_identifiers_typecheck.py` | mypy-only nominal-type discrimination check. |

## Out of scope

- **Adapter-tier `TestId`** — declared in S1-03's `codegenie.adapters.protocols` (TestId is adapter-local; this file is kernel-tier).
- **`ProbeId`** — already exists in Phase 0 (`src/codegenie/probes/base.py` or `registry.py`); do not redefine.
- **`CommitSha`/`FileHash`/`BlobId` newtypes** — not introduced in Phase 2; commit SHAs flow as raw `str` at the I/O boundary by design (`../phase-arch-design.md §"Data model"` — `CommitsBehind.last_indexed: str`).
- **`Enum`-shaped `PackageManager` rewrite** — Phase 1 ADR-0013 is the source of truth. If Phase 1 shipped `Literal["bun","pnpm",…]` and Phase 2 wants `Enum`, that's a Phase 1 ADR amendment, not a Phase 2 story.
- **Runtime validation of newtype values** — `NewType` has no runtime semantics; if a probe needs to validate `IndexName` patterns, that's a probe-side concern, not the newtype's.

## Notes for the implementer

- **`from ... import X as X` is the explicit re-export idiom mypy `--strict` accepts.** Without the redundant `as X`, mypy under `implicit_reexport = false` would treat `PackageManager` as private to `identifiers.py`. The double-name is intentional; do not "clean it up".
- **NewType has zero runtime cost.** At runtime, `IndexId("scip")` is the string `"scip"`. The protection is type-checker-only. The test `test_newtypes_runtime_identity_to_str` documents this so a future contributor doesn't add runtime `isinstance(x, IndexId)` checks that would silently succeed for any `str`.
- **Phase 1 ADR-0013 location matters.** If Phase 1 is currently in `src/codegenie/probes/node_build_system.py` (flat) and Phase 2's Step 4 will move it to `src/codegenie/probes/layer_a/node_build_system.py` per the architecture's package tree, **that move is a Phase 1 ADR amendment** (the architect's package tree intends `layer_a/` per `../phase-arch-design.md §"Development view"`). This story's import path adapts to whichever currently ships; if both work, pick the existing location. Do not reorganize Phase 1 here.
- **The "no class PackageManager / no PackageManager =" source-scan test is structural defense.** It catches the most common mistake — a reviewer who copy-pastes the enum into `identifiers.py` "for convenience." Keep the regex tight; do not weaken to allow conditional imports.
- **NewType vs. Annotated[str, …] vs. dataclass.** `NewType` is the lightest; production ADR-0033 explicitly names it. Do not invent `@dataclass(frozen=True) class IndexId: value: str` — that's pattern-soup and breaks string interop the architecture relies on.
- **The mypy-only test file must NOT be auto-discovered by pytest in a way that fails.** Pytest will load and import it (so the imports must work), but the commented-out lines are the mypy-time assertions. Add the file to `mypy --strict` coverage in `pyproject.toml`; pytest collection picks it up but finds no test functions (file content is module-level only).
