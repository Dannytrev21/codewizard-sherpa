# Story S1-05 — ADR-0033 identifier newtypes — `IndexId`, `SkillId`, `TaskClassId`, `IndexName`, `ProbeId`

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Done (GREEN 2026-05-15, all 9 original ACs) — **HARDENED 2026-05-15 (validator); AC-1b/3a/3b/4a/5b/6a/7a/8a/9a remediation required** — see "Hardening remediation" below; attempt log: [`_attempts/S1-05.md`](_attempts/S1-05.md)
**Effort:** S (+XS remediation)
**Depends on:** —
**Hard requirement of:** S1-04 (which imports `ProbeId` from `codegenie.types.identifiers`)
**ADRs honored:** production ADR-0033 (typed identifiers across module boundaries)

## Validation notes (2026-05-15)

Hardened by `phase-story-validator` (scheduled task: `story-validation-corrector`). Full audit at [`_validation/S1-05-identifiers-newtypes.md`](_validation/S1-05-identifiers-newtypes.md). Verdict: **HARDENED with remediation queue.**

Findings the original draft AND the GREEN merge both missed (all routed to remediation ACs below — none retroactively invalidate the 9 original ACs):

- **Block-tier — `ProbeId` is missing.** S1-04 (hardened on 2026-05-15) imports `ProbeId` from `codegenie.types.identifiers` (S1-04 lines 51, 78, 656). `grep -rn "ProbeId" src/` returns zero hits at validation time. When S1-04 runs, `ImportError`. The Out-of-scope section of the original story falsely claimed `ProbeId` already existed in Phase 0 — it does not. Add `ProbeId = NewType("ProbeId", str)` to `identifiers.py`, the package `__init__.py` `__all__`, and the test suite (AC-1b below).
- **Block-tier — AC-6 mypy nominal-discrimination is unverified by automation.** The original test file (`test_identifiers_typecheck.py`) keeps the swap lines commented out. **No CI step uncomments them.** A future contributor who edits the comment in (or out) gets no feedback. The single load-bearing property of the whole story — that mypy `--strict` rejects cross-NewType assignment — is asserted by *prose*, not by code. Add a subprocess meta-test (AC-6a below).
- **Harden — `__all__` checked with ⊇ not ==.** The GREEN tests use `set(t.__all__) >= {...}` — stowaway exports slip past. Sibling stories S1-01 / S1-03 / S1-04 all closed with `==`. Family symmetric discipline (AC-3a/3b below).
- **Harden — `try/except ImportError` masks layout drift.** AC-5's test allows both `codegenie.probes.node_build_system` and `codegenie.probes.layer_a.node_build_system`. A half-done Phase 1 reorg (both files present, one stale) passes silently. Commit to the verified-current flat path; future move is a Phase 1 ADR-0013 amendment. (AC-5b below.)
- **Harden — Source-scan uses regex, not AST.** Multi-line `from x import (\n  PackageManager,\n)` style breaks the single-line regex; annotation-form rebindings (`PackageManager: TypeAlias = Literal[...]`) slip past the assignment regex's lookahead. AST is durable; regex is fragile. (AC-4a below.)
- **Harden — Module-purity invariant missing.** Sibling stories S1-01 / S1-03 / S1-04 each carry one. The kernel-tier `identifiers.py` is the single most-imported module in Phase 2; any future contributor adding `from codegenie.probes.registry import _REGISTRY` to "see what probes are registered" silently pulls the probe registry into kernel-import order. (AC-9a below.)
- **Harden — `isinstance(x, IndexId)` runtime-error undocumented.** `NewType` is not a class; `isinstance` raises `TypeError`. The footgun is named in Notes but not enforced by a test; a future reader who writes `isinstance(x, IndexId)` for "validation" gets a runtime crash, not a silent always-true. Add a `pytest.raises(TypeError)` test. (AC-8a below.)
- **Harden — `type(val) is str` stricter than `isinstance(val, str)`.** A wrong impl `IndexId = lambda s: FancyStr(s)` (`FancyStr(str)`) passes `isinstance(val, str)` but breaks `type(val) is str`. (AC-7a below.)
- **Harden — `__name__` of each NewType unpinned.** A typo `NewType("Indeex_id", str)` assigned to `IndexId` still type-checks correctly (mypy uses the variable binding), but every mypy error message lies (`"Indeex_id" vs ...`). Pin `nt.__name__ == name`. (AC-1b below.)
- **Harden — Pairwise distinctness unasserted.** `IndexId = SkillId = NewType("Id", str)` (one NewType, four names) passes the GREEN test set; mypy would catch swaps **between** them only if they're distinct objects. (AC-1b below.)
- **Harden — Identity passthrough through `__init__` unasserted for the four NewTypes.** AC-5's `is` check covers `PackageManager` only; a typo in `__init__.py` (`from .identifiers import IndexId as IndexName`) is undetectable. (AC-5b below.)
- **Harden — AC-9 conflates four tools into one.** Failure attribution is impossible. Split per-tool (AC-9 → 9a/9b/9c/9d).
- **Nit — Production ADR-0033 §1 names `TaskClass` (no `Id` suffix).** Phase 2 settled on `TaskClassId` for naming symmetry with `ProbeId`/`SkillId`/`IndexId`/`IndexName`. Deviation is deliberate; documented in Notes (no AC change).
- **Nit — `as X` + `__all__` complementarity** clarified in Notes. Both are needed (mypy strict ⇒ implicit_reexport=false ⇒ `as X` for the type-checker contract; `__all__` for the runtime `from x import *` contract).

The 9 original ACs all PASS as merged. The 9 remediation ACs (1b, 3a, 3b, 4a, 5b, 6a, 7a, 8a, 9a/9b/9c/9d) are additive — they tighten the bar to family discipline without overturning anything that landed.

## Hardening remediation (queued for a follow-up surgical commit)

These ACs are queued because the original ACs all GREEN'd; the gaps named above did not block merge. Treat the remediation as a single XS follow-up:

- [ ] **AC-1b.** `identifiers.py` declares **five** NewTypes (add `ProbeId = NewType("ProbeId", str)`). For each NewType `NT`: `NT.__supertype__ is str`, `NT.__name__ == "<var name>"`, and the five are **pairwise distinct objects** (`id(IndexId) != id(SkillId)` etc., tested over all 10 pairs).
- [ ] **AC-3a.** `set(codegenie.types.identifiers.__all__) == {"IndexId", "IndexName", "PackageManager", "ProbeId", "SkillId", "TaskClassId"}` — exact equality, no stowaways.
- [ ] **AC-3b.** `set(codegenie.types.__all__) == {"IndexId", "IndexName", "PackageManager", "ProbeId", "SkillId", "TaskClassId"}` — exact equality.
- [ ] **AC-4a.** Replace the regex source-scan with an AST walk (`ast.parse` + `ast.walk`): zero `ast.ClassDef` named `PackageManager`; zero `ast.Assign`/`ast.AnnAssign` targeting `PackageManager`; exactly one `ast.ImportFrom` carrying a `PackageManager` alias, and that alias has `asname == "PackageManager"` (the redundant-`as` idiom mypy strict requires).
- [ ] **AC-5b.** Remove the `try/except ImportError` fallback from `test_package_manager_reexported_from_phase1_adr_0013_location`; commit to the single verified-current path (`codegenie.probes.node_build_system`). **Plus:** identity passthrough through `__init__` — for every name in `{IndexId, IndexName, PackageManager, ProbeId, SkillId, TaskClassId}`, `getattr(codegenie.types, name) is getattr(codegenie.types.identifiers, name)`.
- [ ] **AC-6a.** New test file `tests/unit/types/test_identifiers_mypy_negative.py` writes a temp file with the cross-type swap (`_accepts_index(s)` where `s: SkillId`) **executable, not commented**, subprocess-invokes `python -m mypy --strict <tmpfile>`, asserts `returncode != 0`, and asserts the combined stdout/stderr contains substrings `incompatible type "SkillId"` AND `expected "IndexId"`. This is the load-bearing CI gate for the whole story; without it AC-6 is decorative.
- [ ] **AC-7a.** `test_newtypes_runtime_identity_to_str` asserts `type(NT("scip")) is str` (strict — catches str subclasses) in addition to `isinstance(val, str)`. Run over all five NewTypes.
- [ ] **AC-8a.** A test asserts `with pytest.raises(TypeError): isinstance("scip", ids.IndexId)` — pins the documented footgun (`NewType` is not a class) as enforced behavior.
- [ ] **AC-9a.** `ruff check src/codegenie/types/ tests/unit/types/` exits 0.
- [ ] **AC-9b.** `ruff format --check src/codegenie/types/ tests/unit/types/` exits 0.
- [ ] **AC-9c.** `mypy --strict src/codegenie/types/ tests/unit/types/` exits 0 on the positive-path code.
- [ ] **AC-9d.** `pytest tests/unit/types/` passes (now includes AC-6a's subprocess negative-mypy meta-test + AC-1b/4a/5b/7a/8a/9a additions).

The new test file is `tests/unit/types/test_identifiers_mypy_negative.py`; the existing `test_identifiers.py` and `test_identifiers_typecheck.py` are edited surgically (no rename).

## Evidence (S1-05 — original 9 ACs)

- **AC-1, AC-7** — `tests/unit/types/test_identifiers.py::test_newtypes_exist_and_are_distinct` + `::test_newtypes_runtime_identity_to_str` (NewType objects expose `__supertype__ is str`; `IndexId("scip") == "scip"`).
- **AC-1 (distinct identities)** — `tests/unit/types/test_identifiers.py::test_newtype_objects_are_distinct_identities`.
- **AC-2** — Re-export at [`src/codegenie/types/identifiers.py:18`](../../../../src/codegenie/types/identifiers.py) (`from codegenie.probes.node_build_system import PackageManager as PackageManager`).
- **AC-3** — `__all__` in [`src/codegenie/types/__init__.py`](../../../../src/codegenie/types/__init__.py) and `identifiers.py`; pinned by `test_all_exports_include_five_names` and `test_identifiers_module_all_lists_five_names`.
- **AC-4** — Source-scan guard `test_no_package_manager_redefinition_in_types_module` (no `class PackageManager`, no reassignment, exactly one import line). **Hardening note:** regex-based; remediation AC-4a moves to AST.
- **AC-5** — `test_package_manager_reexported_from_phase1_adr_0013_location` asserts `ids.PackageManager is P1`. **Hardening note:** uses `try/except ImportError`; remediation AC-5b removes the fallback.
- **AC-6** — [`tests/unit/types/test_identifiers_typecheck.py`](../../../../tests/unit/types/test_identifiers_typecheck.py) — `mypy --strict` PASS over file; commented lines pin nominal-type discrimination **as prose, not as automation**. Remediation AC-6a adds the subprocess meta-test that is the actual CI gate.
- **AC-8** — RED commit ran with `ModuleNotFoundError: No module named 'codegenie.types.identifiers'`; GREEN commit makes 7 tests pass.
- **AC-9** — `ruff check src/ tests/` clean, `ruff format --check` clean, `mypy --strict src/codegenie/types/ tests/unit/types/` clean, `pytest tests/unit/types/` → 7 passed; full suite 1605 passed. **Hardening note:** four tools conflated; remediation AC-9a/9b/9c/9d splits per-tool.

## Precondition note (S1-05)

`PackageManager` did not previously exist as a typed alias in `codegenie.probes.node_build_system`; the field was typed `str | None`. AC-2/AC-5 require importing it. Surgical minimal fix: a `PackageManager: TypeAlias = Literal["bun","pnpm","yarn-classic","yarn-berry","npm"]` constant was added to [`src/codegenie/probes/node_build_system.py`](../../../../src/codegenie/probes/node_build_system.py) (matches the schema enum at `src/codegenie/schema/probes/node_build_system.schema.json` line 29). Existing signatures (`str | None`) were left untouched — `Literal | None` is a structural subtype of `str | None`, so no downstream signature drift. Consistent with Phase 1 ADR-0013's enumeration of variants and the story's Notes §"Phase 1 ADR-0013 location matters" allowance.

## Context

Production ADR-0033 §3 names primitive-obsession on domain identifiers as a review-blocker pattern. Phase 2 introduces five new kernel-tier identifier families (`IndexId`, `SkillId`, `TaskClassId`, `IndexName`, `ProbeId`) used by every other Step 1 story (`TCCM`, freshness registry, depgraph registry, probe registry). `PackageManager` already exists from Phase 1 ADR-0013 — this story re-imports the location, **never redefines it**, and unit tests guard that location at the module-import boundary.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Anti-patterns avoided"` row "Stringly-typed identifiers" — `ProbeId`, `TaskClassId`, `SkillId`, `PackageManager` are typed; `ecosystem: PackageManager` is the registry key, not `ecosystem: str`.
  - `../phase-arch-design.md §"Data model"` — `TCCM.task_class: TaskClassId`, `required_skills: list[SkillId]`, `required_probes: list[ProbeId]`, `Skill.id: SkillId`; `IndexName` is the freshness-registry key.
  - `../phase-arch-design.md §"Component design" #11 — DepGraphProbe + strategy registry` — `PackageManager` is imported from Phase 1 ADR-0013, not redefined.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0006-index-freshness-sum-type-location.md` — 02-ADR-0006 §Decisions noted — `IndexName` is the registry key for `@register_index_freshness_check`.
- **Production ADRs:**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — production ADR-0033 §1 — typed identifiers at module boundaries; the binding discipline. **Naming note:** production ADR-0033 §1 names `TaskClass` (no `Id` suffix). Phase 2's `TaskClassId` is a deliberate naming-symmetry choice with `ProbeId`/`SkillId`/`IndexId`; see Notes-for-implementer.
- **Sibling-story cross-dependencies:**
  - `S1-04-tccm-model-loader.md §References` + lines 51 / 78 / 656 — S1-04 imports `ProbeId, SkillId, TaskClassId` from `codegenie.types.identifiers`. **S1-04 hard-routed `ProbeId` through this story.** If `ProbeId` is missing from `identifiers.py`, S1-04 `ImportError`s at green-stage time. Remediation AC-1b closes this.
- **Source design:**
  - `../final-design.md §"Synthesis ledger" — ADR-0033 newtypes` — the deliberate scope.
- **Existing code (verified at validation time 2026-05-15):**
  - `src/codegenie/probes/node_build_system.py:115` — Phase 1 ADR-0013 ships `PackageManager = Literal["bun", "pnpm", "yarn-classic", "yarn-berry", "npm"]` (flat path; no `layer_a/` subpackage exists). The story commits to this import path and treats any future move to `probes/layer_a/` as a Phase 1 ADR-0013 amendment, not an in-story branch.
  - `src/codegenie/probes/base.py`, `src/codegenie/probes/registry.py` — `ProbeId` does **not** exist anywhere under `src/codegenie/` (grep verified 2026-05-15). S1-04's routing comment treats S1-05 as the home; remediation AC-1b honors that.
  - `pyproject.toml [tool.mypy]` — `strict = true`, `warn_unreachable = true`. `strict` implies `implicit_reexport = false`, which is why the redundant `as X` re-export idiom is required.
- **External docs (only if directly relevant):**
  - https://docs.python.org/3/library/typing.html#typing.NewType — `NewType` semantics (type-checker-only; zero runtime cost; `__supertype__` exposes the runtime supertype; `__name__` is the nominal-type name mypy prints in errors).

## Goal

Implement `src/codegenie/types/__init__.py` and `src/codegenie/types/identifiers.py` declaring `IndexId`, `SkillId`, `TaskClassId`, `IndexName`, `ProbeId` as `NewType`s over `str`, re-exporting `PackageManager` from its Phase 1 ADR-0013 source location **by import** — and assert via unit tests that (a) the import location has not silently changed, (b) the five NewTypes are pairwise distinct, (c) `mypy --strict` rejects cross-type assignment (executed in CI, not asserted in prose), and (d) the `identifiers.py` module is import-pure (no I/O, no logger, no probe-registry pull-in).

## Acceptance criteria (original — all GREEN as merged)

- [x] **AC-1.** `src/codegenie/types/identifiers.py` declares `IndexId = NewType("IndexId", str)`, `SkillId = NewType("SkillId", str)`, `TaskClassId = NewType("TaskClassId", str)`, `IndexName = NewType("IndexName", str)`. Each is a distinct `NewType` (mypy treats them as non-interchangeable at type-check time).
- [x] **AC-2.** `src/codegenie/types/identifiers.py` re-exports `PackageManager` via `from codegenie.probes.node_build_system import PackageManager as PackageManager` (the explicit `as` re-export makes mypy `--strict` admit the public re-export).
- [x] **AC-3.** `src/codegenie/types/__init__.py` re-exports all five names (`IndexId`, `SkillId`, `TaskClassId`, `IndexName`, `PackageManager`) via `__all__` (⊇; remediation AC-3a/3b tightens to ==).
- [x] **AC-4.** `PackageManager` is **not** redefined anywhere under `src/codegenie/types/`; a unit test scans `identifiers.py` source via regex (remediation AC-4a moves to AST).
- [x] **AC-5.** `codegenie.types.identifiers.PackageManager is codegenie.probes.node_build_system.PackageManager` — same object identity, no re-wrapping (with `try/except ImportError` fallback; remediation AC-5b removes the fallback).
- [x] **AC-6.** A mypy-only test (`tests/unit/types/test_identifiers_typecheck.py`) keeps commented-out swap lines as prose-documentation (remediation AC-6a adds the subprocess meta-test that is the actual CI gate).
- [x] **AC-7.** Runtime: `IndexId("scip") == "scip"` (because `NewType` is identity at runtime); the test documents this and is intentional (remediation AC-7a tightens to `type(val) is str`).
- [x] **AC-8.** The TDD plan's red test exists, was committed, and is green.
- [x] **AC-9.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/types/` all pass on the touched files (remediation AC-9a/9b/9c/9d splits per-tool).

(See "Hardening remediation" section above for the additive AC-1b / 3a / 3b / 4a / 5b / 6a / 7a / 8a / 9a / 9b / 9c / 9d that bring the story to family-discipline parity with S1-01 / S1-03 / S1-04.)

## Implementation outline

1. Locate the Phase 1 ADR-0013 `PackageManager` source — at validation time it ships at `src/codegenie/probes/node_build_system.py` (flat). Use that path. A future move to `probes/layer_a/` is a Phase 1 ADR-0013 amendment that updates the single import line in `identifiers.py`.
2. Create `src/codegenie/types/__init__.py` + `src/codegenie/types/identifiers.py` with the **five** `NewType`s (`IndexId`, `SkillId`, `TaskClassId`, `IndexName`, `ProbeId`) and the explicit-`as` `PackageManager` re-export.
3. Write red tests; confirm `ImportError` on `ProbeId` and on the new module path.
4. Implement; confirm green.
5. Refactor — module docstrings cite production ADR-0033; the no-redefinition invariant is restated in a one-line comment above the `import PackageManager` line.
6. **Remediation pass (post-GREEN, surgical follow-up):** add `ProbeId`, swap regex→AST source-scan, swap ⊇→== for `__all__`, remove `try/except` from the AC-5 test, add the subprocess negative-mypy meta-test (new file `test_identifiers_mypy_negative.py`), add `type(val) is str`, add `pytest.raises(TypeError)` for `isinstance`, add module-purity AST scan, split AC-9 per-tool.

## TDD plan — red / green / refactor

(Original TDD plan retained for historical context; the **remediation TDD plan** below is what AC-1b/3a/3b/4a/5b/6a/7a/8a/9a–d require.)

### Red — write the failing test first (original)

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
    try:
        from codegenie.probes.node_build_system import PackageManager as P1
    except ImportError:
        from codegenie.probes.layer_a.node_build_system import PackageManager as P1  # type: ignore[no-redef]

    assert ids.PackageManager is P1


def test_no_package_manager_redefinition_in_types_module() -> None:
    # AC-4 — guard against silent shadowing
    src = pathlib.Path(inspect.getsourcefile(ids)).read_text()
    assert "class PackageManager" not in src
    assert not re.search(r"^PackageManager\s*=\s*(?!.*import)", src, flags=re.MULTILINE)
    matches = re.findall(r"^\s*from .* import .*PackageManager", src, flags=re.MULTILINE)
    assert len(matches) == 1


def test_all_exports_include_five_names() -> None:
    from codegenie import types as t
    assert set(t.__all__) >= {"IndexId", "SkillId", "TaskClassId", "IndexName", "PackageManager"}
```

### Remediation tests (AC-1b / 3a / 3b / 4a / 5b / 7a / 8a / 9a)

Edit `tests/unit/types/test_identifiers.py` to add these (and tighten the existing) — preserves the existing pass-set and adds the family-discipline closure:

```python
from __future__ import annotations

import ast
import itertools
import pathlib

import pytest

import codegenie.types as types_pkg
import codegenie.types.identifiers as ids


_FIVE_NEWTYPES = ("IndexId", "SkillId", "TaskClassId", "IndexName", "ProbeId")
_EXPECTED_ALL = {*_FIVE_NEWTYPES, "PackageManager"}


def test_five_newtypes_supertype_and_name_pinned() -> None:
    # AC-1b — five (incl. ProbeId); __name__ pinned to variable name.
    for name in _FIVE_NEWTYPES:
        assert hasattr(ids, name), f"missing {name}"
        nt = getattr(ids, name)
        assert nt.__supertype__ is str
        assert nt.__name__ == name, (
            f"{name} NewType __name__ is {nt.__name__!r}; mypy prints this in errors."
        )


def test_newtypes_pairwise_distinct() -> None:
    # AC-1b — guards against IndexId = SkillId = NewType("Id", str) aliasing.
    nts = [getattr(ids, n) for n in _FIVE_NEWTYPES]
    for a, b in itertools.combinations(nts, 2):
        assert a is not b, f"{a.__name__} and {b.__name__} are the same object"


def test_runtime_value_type_is_exactly_str() -> None:
    # AC-7a — type(...) is str (stricter than isinstance; catches str subclasses).
    for name in _FIVE_NEWTYPES:
        val = getattr(ids, name)("scip")
        assert val == "scip"
        assert type(val) is str


def test_isinstance_against_newtype_raises_typeerror() -> None:
    # AC-8a — NewType is not a class. Footgun pinned as enforced behavior.
    with pytest.raises(TypeError):
        isinstance("scip", ids.IndexId)  # type: ignore[arg-type]


def test_package_manager_reexported_hard_path() -> None:
    # AC-5b — no try/except fallback. Layout drift fails loud.
    from codegenie.probes.node_build_system import PackageManager as P1
    assert ids.PackageManager is P1


def test_identity_passthrough_through_init() -> None:
    # AC-5b — codegenie.types.X is codegenie.types.identifiers.X for all six.
    for name in _EXPECTED_ALL:
        assert getattr(types_pkg, name) is getattr(ids, name)


def test_all_exact_six_names() -> None:
    # AC-3a / AC-3b — exact equality, no stowaways.
    assert set(ids.__all__) == _EXPECTED_ALL
    assert set(types_pkg.__all__) == _EXPECTED_ALL


def _identifiers_ast() -> ast.Module:
    return ast.parse(pathlib.Path(ids.__file__).read_text())


def test_no_package_manager_redefinition_ast() -> None:
    # AC-4a — AST-based; tolerates multi-line imports, catches annotation-form.
    tree = _identifiers_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PackageManager":
            pytest.fail("Do not redefine PackageManager via class")
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "PackageManager":
                    pytest.fail("PackageManager rebound via assignment")
        if isinstance(node, ast.AnnAssign):
            t = node.target
            if isinstance(t, ast.Name) and t.id == "PackageManager":
                pytest.fail("PackageManager rebound via annotation-form assignment")
    imports = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
        and any(a.name == "PackageManager" for a in n.names)
    ]
    assert len(imports) == 1
    alias = next(a for a in imports[0].names if a.name == "PackageManager")
    assert alias.asname == "PackageManager", (
        "PackageManager must be re-exported with `as PackageManager` (mypy strict)."
    )


def test_identifiers_module_is_pure() -> None:
    # AC-9a (module-purity invariant) — family symmetric discipline.
    tree = _identifiers_ast()
    ALLOWED_FROM = {"__future__", "typing", "codegenie.probes.node_build_system"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module in ALLOWED_FROM, (
                f"identifiers.py imports from {node.module!r}; allowed: {ALLOWED_FROM}"
            )
        elif isinstance(node, ast.Import):
            pytest.fail(f"bare import in identifiers.py: {[a.name for a in node.names]}")
```

### New file — subprocess negative-mypy meta-test (AC-6a)

```python
# tests/unit/types/test_identifiers_mypy_negative.py
"""AC-6a — mypy --strict MUST reject cross-NewType assignment.

The whole point of NewType is mypy-time nominal discrimination. The original
draft commented out the bad lines and called it "verified" — no automation ran
them. This test executes mypy against a file with the swap uncommented and
asserts non-zero exit + the expected error substring.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


_NEGATIVE = textwrap.dedent('''
    from __future__ import annotations
    from codegenie.types.identifiers import IndexId, SkillId

    def _accepts_index(_x: IndexId) -> None: ...
    def _accepts_skill(_x: SkillId) -> None: ...

    def main() -> None:
        i: IndexId = IndexId("scip")
        s: SkillId = SkillId("scip.maintenance")
        _accepts_index(s)  # mypy MUST flag: SkillId where IndexId expected
        _accepts_skill(i)  # mypy MUST flag: IndexId where SkillId expected
''')


def test_mypy_strict_rejects_cross_newtype_assignment(tmp_path: Path) -> None:
    target = tmp_path / "negative_swap.py"
    target.write_text(_NEGATIVE)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(target)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0, (
        f"mypy --strict accepted cross-NewType assignment; NewType discipline is broken.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert 'incompatible type "SkillId"' in combined, combined
    assert 'expected "IndexId"' in combined, combined
```

### Green — make it pass (post-remediation shape)

```python
# src/codegenie/types/identifiers.py
"""Phase 2 kernel-tier identifier newtypes (production ADR-0033).

Each NewType is a nominal type at mypy --strict time; identity-to-str at
runtime. Adding a new identifier here is the canonical extension point —
do NOT redefine PackageManager (Phase 1 ADR-0013); import it.
"""
from __future__ import annotations
from typing import NewType

# DO NOT redefine — Phase 1 ADR-0013 owns this enum; this is a re-export.
from codegenie.probes.node_build_system import PackageManager as PackageManager

IndexId     = NewType("IndexId", str)
SkillId     = NewType("SkillId", str)
TaskClassId = NewType("TaskClassId", str)
IndexName   = NewType("IndexName", str)
ProbeId     = NewType("ProbeId", str)

__all__ = ["IndexId", "IndexName", "PackageManager", "ProbeId", "SkillId", "TaskClassId"]
```

```python
# src/codegenie/types/__init__.py
from codegenie.types.identifiers import (
    IndexId, IndexName, PackageManager, ProbeId, SkillId, TaskClassId,
)
__all__ = ["IndexId", "IndexName", "PackageManager", "ProbeId", "SkillId", "TaskClassId"]
```

### Refactor — clean up

- Module docstring on `identifiers.py` cites production ADR-0033 §3 (primitive-obsession is a review-blocker) and names the Phase 1 ADR-0013 source location.
- Comment above the `import PackageManager` line: `# DO NOT redefine — Phase 1 ADR-0013 owns this enum; this is a re-export.`
- Confirm CI gates per AC-9a/b/c/d:
  - `ruff format src/codegenie/types/ tests/unit/types/`
  - `ruff check src/codegenie/types/ tests/unit/types/`
  - `mypy --strict src/codegenie/types/ tests/unit/types/`
  - `pytest tests/unit/types/`

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/__init__.py` | New package; re-export the six names exactly. |
| `src/codegenie/types/identifiers.py` | Declare five `NewType`s (add `ProbeId`); re-export `PackageManager`. |
| `tests/unit/types/test_identifiers.py` | AST source-scan, pairwise distinctness, identity passthrough, `__all__` exact-set, runtime-identity-is-exactly-str, `isinstance` footgun, module-purity. |
| `tests/unit/types/test_identifiers_typecheck.py` | Positive-path mypy file — every NewType used at its declared site type-checks. |
| `tests/unit/types/test_identifiers_mypy_negative.py` | **New (AC-6a)** — subprocess-invokes `mypy --strict` on a file with the cross-type swap uncommented; asserts non-zero exit + expected error substring. The single load-bearing CI gate for NewType discipline. |

## Out of scope

- **Adapter-tier `TestId`** — declared in S1-03's `codegenie.adapters.protocols` (TestId is adapter-local; this file is kernel-tier).
- **Phase 3+ identifiers (`AdapterId`, `RecipeId`, `BundleId`, `AttemptId`, `WorkflowId`, `RepoId`, `EventId`, `SymbolId`, `SignalKind`, `Language`, `BuildSystem`)** — production ADR-0033 §1 lists ~15 newtypes for the whole codebase; Phase 2 ships only the five it actively consumes. Extension is by addition: subsequent phases add new `NewType("X", str)` lines to this same `identifiers.py` (no new files, no decorators, no registry — Rule 2). The exact-set `__all__` test in AC-3a/3b means each addition is a one-line story change, but it IS a story-change (no silent additions).
- **`CommitSha`/`FileHash`/`BlobId` newtypes** — not introduced in Phase 2; commit SHAs flow as raw `str` at the I/O boundary by design (`../phase-arch-design.md §"Data model"` — `CommitsBehind.last_indexed: str`).
- **`Enum`-shaped `PackageManager` rewrite** — Phase 1 ADR-0013 is the source of truth. If Phase 1 shipped `Literal["bun","pnpm",…]` and Phase 2 wants `Enum`, that's a Phase 1 ADR amendment, not a Phase 2 story.
- **Runtime validation of newtype values** — `NewType` has no runtime semantics; if a probe needs to validate `IndexName` patterns, that's a probe-side concern (and likely a smart-constructor at the parser boundary per ADR-0033 §2), not the newtype's.
- **Closing `IndexName` / `SkillId` / `TaskClassId` / `ProbeId` to a `Literal[...]`** — these are open by design (registry keys for `@register_index_freshness_check`, `@register_skill`, `@register_task_class`, `@register_probe`). A closed `Literal` would violate Phase 2 Extension-by-Addition. See Notes-for-implementer.

## Notes for the implementer

- **`from ... import X as X` is the explicit re-export idiom mypy `--strict` accepts.** Under `implicit_reexport = false` (which `strict = true` implies — verified in `pyproject.toml [tool.mypy]`), `from x import Y` makes `Y` *private* to the importing module. The redundant `as Y` is the public-re-export contract. `__all__` is the *runtime* contract (`from x import *` honors it); both are needed. The story uses both correctly; do not "clean up" the redundancy.
- **NewType has zero runtime cost.** At runtime, `IndexId("scip")` is the string `"scip"`. The protection is type-checker-only. `test_isinstance_against_newtype_raises_typeerror` (AC-8a) documents this so a future contributor doesn't add runtime `isinstance(x, IndexId)` checks — `NewType` is not a class; `isinstance` raises `TypeError`, not a silent always-true.
- **Open `NewType` vs closed `Literal` — `IndexName`, `SkillId`, `TaskClassId`, `ProbeId` are open on purpose.** Each is a registry key: `IndexName` for `@register_index_freshness_check` (S1-01 / ADR-0006), `SkillId` for skill registration, `TaskClassId` for the TCCM `task_class` field, `ProbeId` for `@register_probe`. Phase 3+ extends the registries by **new file + new decorator** — Extension by Addition. A closed `Literal["scip","ctags","tree-sitter","semgrep"]` would freeze the set and require editing the kernel for every new index source / skill / task class / probe. A reviewer who proposes "tightening" these to `Literal[...]` is reaching for false safety. `PackageManager` is the **exception** — it's `Literal[...]` because Phase 1 ADR-0013 explicitly closed the package-manager taxonomy; extension is by ADR amendment, not by user-data.
- **Phase 1 ADR-0013 location at validation time: flat (`src/codegenie/probes/node_build_system.py`).** The architect's package tree intends a future `layer_a/` reorganization (per `../phase-arch-design.md §"Development view"`). When that move happens it's a Phase 1 ADR-0013 amendment and updates the single import line in `identifiers.py`. **Do not** branch in the story or test code on `try/except ImportError` — that hides drift. Fail loud, then update the one line. The remediation pass removes the `try/except`.
- **Production ADR-0033 §1 names `TaskClass` (no `Id` suffix).** Phase 2 chose `TaskClassId` for naming symmetry with `ProbeId`/`SkillId`/`IndexId`/`IndexName`; the phase-arch design and all Phase 2 stories settled on this spelling. The deviation from production ADR-0033 is deliberate — a future production-ADR amendment may reconcile (`TaskClass` → `TaskClassId`), but Phase 2 doesn't wait. Do not redeclare or alias the two names.
- **The AST source-scan tests are structural defense, not paranoia.** They catch the most common mistakes: a reviewer who copy-pastes the enum into `identifiers.py` "for convenience" (AC-4a); a contributor who adds `from codegenie.probes.registry import _REGISTRY` to `identifiers.py` to "see what probes are registered" (AC-9a) and silently pulls the probe registry into kernel-import order. Keep the AST scans; do not weaken to allow conditional imports or platform-specific bare imports — there are no platform-specific identifiers in this file.
- **The subprocess mypy meta-test (AC-6a) is the load-bearing CI gate.** Without it, AC-6's "verified via mypy" claim is theatre — the commented-out swap lines never run against mypy. If the meta-test is flaky in CI (e.g., mypy not on `$PATH`), fix the CI environment; do not weaken the assertion. Sibling story S1-03 uses the same shape for compile-fail tests; mirror it.
- **NewType vs. Annotated[str, …] vs. dataclass.** `NewType` is the lightest; production ADR-0033 explicitly names it. Do not invent `@dataclass(frozen=True) class IndexId: value: str` — that's pattern-soup, breaks string interop the architecture relies on, and re-creates the runtime-validation surface this file deliberately rejects.
- **`types/` is the kernel-tier package.** ADR-0006's "new top-level packages" list (`indices/, adapters/, tccm/, skills/, conventions/, depgraph/, report/`) enumerated *domain* packages only; `types/` joins the kernel peer group alongside `errors/`, `cache/`, `coordinator/`, etc. No new arch decision is required.
- **Hypothesis (property-based) is NOT warranted here.** The mutation space is categorical (alias vs distinct, supertype right vs wrong, `__name__` right vs wrong), not value-space. The remediation unit tests + the subprocess meta-test exhaust the failure modes. Adding Hypothesis would be ceremony without coverage gain.
- **Cross-story dependency: `ProbeId` is consumed by S1-04.** S1-04 lines 51, 78, 656 import `ProbeId` from `codegenie.types.identifiers`. The original S1-05 merge did NOT ship `ProbeId`; the remediation pass closes this gap. The correct serialization is S1-05 (remediation) before S1-04 execution. If S1-04 runs against the pre-remediation tree, it `ImportError`s — that's the loud failure mode we want, not a workaround in S1-04.
