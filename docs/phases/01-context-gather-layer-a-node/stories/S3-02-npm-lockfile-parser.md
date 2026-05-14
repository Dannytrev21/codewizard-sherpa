# Story S3-02 — `_npm` lockfile parser

**Step:** Step 3 — Ship `NodeManifestProbe` and the three lockfile parsers
**Status:** Ready (HARDENED)
**Effort:** S
**Depends on:** S3-01 (`_pnpm.py` + `_lockfiles/__init__.py` — the family kernel landed there), S1-02 (`safe_json.load`), S1-01 (Phase 1 marker exceptions)
**ADRs honored:** ADR-0008 (in-process caps, not per-probe sandbox), ADR-0009 (no new C-extension parser deps), ADR-0007 (`WarningId` constructed at catch site)
**Phase-0 invariant honored:** `tests/unit/test_errors.py::test_subclasses_are_markers_only` and `::test_phase1_subclasses_accept_message_arg_and_expose_args0` — marker exceptions accept a single positional message string and expose **no** instance state.

## Validation notes (2026-05-14 — phase-story-validator HARDENED)

Three **block-level** corrections applied (see `_validation/S3-02-npm-lockfile-parser.md` for full audit):

1. **Marker exception construction.** The draft prescribed `MalformedLockfileError(path=path, cause=e)` (kwargs) and a test assertion `exc.value.path == lockfile`. Phase 0's `test_subclasses_are_markers_only` and S1-01's `test_phase1_subclasses_accept_message_arg_and_expose_args0` parametrize **every Phase-1 marker** (including `MalformedLockfileError`) as positional-only — `hasattr(exc, "path")` is an asserted **negative**. Construction must be `MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}") from cause`. Same defect S1-02 / S1-03 / S3-01 hardenings already corrected.
2. **No re-export from `_lockfiles/__init__.py`.** Draft AC-7 + Implementation-outline step 3 prescribed "additively re-export `NpmLock`". This contradicts S3-01's settled form (`__all__: list[str] = []`, docstring stating "S3-01 ships `_pnpm`; S3-02 ships `_npm`; S3-03 ships `_yarn`. `__all__` stays empty here — each sibling exports from its own module"). Consumers import siblings directly. S3-02 must **not** touch `_lockfiles/__init__.py`; this is now AC-1 (non-edit guarantee with a regression test).
3. **`Depends on` corrected.** Draft listed S1-03 (`safe_yaml`) "for symmetry" — irrelevant to JSON parsing. The real dependencies are S3-01 (family kernel), S1-02 (`safe_json`), and S1-01 (markers).

Twelve harden-tier additions mirroring S3-01's hardened shape with npm-specific deltas: explicit AC for the `__cause__` chain (`isinstance(exc.__cause__, MalformedJSONError)`); explicit AC for `str(path) in exc.args[0]` (downstream `WarningId` recovery per ADR-0007); parametrized markers-only-negative test; size-cap test rewritten to monkey-patch `os.fstat` (no 60 MB write); symlink-passthrough test added; top-level non-mapping translation (`MalformedJSONError("expected JSON object at top level")` → `MalformedLockfileError`) made explicit; empty-file translation (`MalformedJSONError("empty file")` → `MalformedLockfileError`) added; `total=False` semantics pinned by a v1-shape fixture (no `packages`) and a v3-shape fixture (no `dependencies`); module constants typed `Final[int]`; `__all__ = ["NpmLock", "parse"]` declared; architectural test `test_npm_module_does_not_reference_sibling_parsers`; non-edit `_lockfiles/__init__.py` pinned by `test_lockfiles_init_remains_inert`.

Design-pattern opportunities recorded in Notes for the implementer (rule-of-three deferral: still no shared `_translate(path)` helper — S3-02 is the **second** concrete consumer; threshold is the third, S3-03). No `NEEDS RESEARCH` findings; Stage 3 skipped.

## Context

`package-lock.json` is npm's lockfile and the second of three sibling parsers feeding `NodeManifestProbe`. The shape mirrors S3-01's `_pnpm.py` exactly — a thin `safe_json.load` wrapper returning a `TypedDict`, with the same size + depth caps (50 MB / depth 64) and the same exception-translation pattern (`MalformedJSONError` → `MalformedLockfileError`, with the original preserved on `__cause__`). The structural difference vs. S3-01 is the parser entry point (`safe_json.load`) and the translated source exception class (`MalformedJSONError`). All other invariants — positional marker construction, `total=False` `TypedDict`, no schema validation, no sibling imports, inert `_lockfiles/__init__.py` — are inherited unchanged.

npm's lockfile has had three on-disk shapes (`lockfileVersion` 1, 2, 3). v1 (npm 5/6) stores only a nested `dependencies` tree; v2 (npm 7+) stores **both** the modern flat `packages` tree **and** the legacy nested `dependencies` for backward compatibility; v3 (npm 9+) drops `dependencies`, keeping `packages`. v2's dual representation is why `package-lock.json` is typically larger than the pnpm/yarn equivalents — the 50 MB cap matters here. The `total=False` `TypedDict` is **load-bearing** for this variance: defaulting any key at the parser layer would mask version skew that `NodeManifestProbe` (S3-05) needs to see.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #9 Lockfile parsers` — interface, ~100 ms p50 budget.
  - `../phase-arch-design.md §"Component design" #4 NodeManifestProbe` — caller; `package-lock.json` is in `declared_inputs`.
  - `../phase-arch-design.md` line 517 — `_npm.py: parsers.safe_json.load (50 MB cap, depth 64)`.
  - `../phase-arch-design.md §"Component design" #8 Safe-parse helpers` — `safe_json.load(path, *, max_bytes, max_depth=64)`.
- **Phase ADRs:**
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — caps live in the parser.
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — stdlib `json` only; no `orjson`.
  - `../ADRs/0007-warnings-id-pattern.md` — `WarningId` is constructed at the catch site (in `NodeManifestProbe`) from the marker's `args[0]`, not embedded on the exception.
- **Source design:**
  - `../final-design.md §"Components" #4` — three sibling parsers under `_lockfiles/`.
  - `../High-level-impl.md §"Step 3"` — `_npm.py` deliverable.
- **Existing code (Phase 0 + Step 1 + S3-01):**
  - `src/codegenie/parsers/safe_json.py` — from S1-02. Raises `SizeCapExceeded`, `DepthCapExceeded`, `SymlinkRefusedError`, `MalformedJSONError` (positional-only). `safe_json._decode` enforces top-level-dict (`if not isinstance(obj, dict): raise MalformedJSONError(f"{path}: expected JSON object at top level")`) and empty-file (`if not data: raise MalformedJSONError(f"{path}: empty file")`).
  - `src/codegenie/errors.py` — `MalformedLockfileError` is a marker subclass with no `__init__` (Phase 0 invariant).
  - `tests/unit/test_errors.py::test_phase1_subclasses_accept_message_arg_and_expose_args0` — parametrizes every Phase 1 marker (incl. `MalformedLockfileError`) for positional construction; asserts `not hasattr(exc, "path" | "cap" | "detail" | "warning_id")`.
  - `src/codegenie/probes/_lockfiles/_pnpm.py` — from S3-01; **mirror the structure verbatim**, substituting `safe_json` for `safe_yaml` and `MalformedJSONError` for `MalformedYAMLError`.
  - `src/codegenie/probes/_lockfiles/__init__.py` — from S3-01; `__all__: list[str] = []`. **S3-02 must not edit this file.**
- **Validation precedents (the marker discipline already settled):**
  - `_validation/S1-02-safe-json-parser.md` — first kwargs-on-markers correction; established `f"{path}: {detail}"` format.
  - `_validation/S1-03-safe-yaml-parser.md` — added `from cause` chaining.
  - `_validation/S3-01-pnpm-lockfile-parser.md` — settled the lockfile-parser shape S3-02 mirrors; pinned `_lockfiles/__init__.py` as inert.

## Goal

Implement `src/codegenie/probes/_lockfiles/_npm.py` as a thin `safe_json.load` wrapper returning an `NpmLock` `TypedDict`, so `NodeManifestProbe` can call `_npm.parse(path)` and receive a parsed-and-capped dict — or one of five typed exceptions (`SizeCapExceeded`, `DepthCapExceeded`, `SymlinkRefusedError` re-raised unchanged from `safe_json`; `MalformedLockfileError` translated from `MalformedJSONError` with `__cause__` preserved; `FileNotFoundError` propagated from the OS open). All marker exceptions remain positional-message-only per Phase 0's marker invariant. S3-02 adds **one new file** to `src/` and **does not edit** `_lockfiles/__init__.py` (CLAUDE.md "Extension by addition").

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

- [ ] **AC-1.** `src/codegenie/probes/_lockfiles/__init__.py` is **not edited** by S3-02. The file content as committed by S3-01 remains byte-for-byte unchanged. Pinned by an architectural test that snapshots the file's content (excluding trailing newline normalization) and compares against the S3-01 baseline (`__all__: list[str] = []` plus the docstring). Extension-by-addition: S3-02 adds **one** new file to `src/`, period.
- [ ] **AC-2.** `src/codegenie/probes/_lockfiles/_npm.py` exports exactly `__all__ = ["NpmLock", "parse"]`.
- [ ] **AC-3.** `parse(path: Path) -> NpmLock` calls `safe_json.load(path, max_bytes=NPM_LOCKFILE_MAX_BYTES, max_depth=NPM_LOCKFILE_MAX_DEPTH)` with `NPM_LOCKFILE_MAX_BYTES: Final[int] = 50 * 1024 * 1024` and `NPM_LOCKFILE_MAX_DEPTH: Final[int] = 64` declared at module scope (matches arch §"Component design" #9 cap).
- [ ] **AC-4.** `parse(path)` **re-raises unchanged** any `SizeCapExceeded`, `DepthCapExceeded`, or `SymlinkRefusedError` raised by `safe_json.load`. No re-wrapping, no swallowing.
- [ ] **AC-5.** `parse(path)` translates `MalformedJSONError` raised by `safe_json.load` into `MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}")` raised `from cause`, so the original `MalformedJSONError` is preserved on `__cause__` (per S1-02 / S3-01 precedent; Rule 12 — fail loud with the chain). The translation covers **all three** `safe_json` paths that raise `MalformedJSONError`: JSON-decode error, empty file, and top-level non-mapping.
- [ ] **AC-6.** **Marker contract preserved.** The raised `MalformedLockfileError` carries its message in `args[0]` only; `hasattr(exc, "path")` and `hasattr(exc, "cause")` are both **False**. The Phase 0 invariant `tests/unit/test_errors.py::test_subclasses_are_markers_only` is unaffected by S3-02 code.
- [ ] **AC-7.** **`__cause__` chain.** For the malformed-JSON path, `exc.__cause__` is the original `MalformedJSONError` instance (`isinstance(exc.__cause__, MalformedJSONError)` holds; the test pins the class, not the message).
- [ ] **AC-8.** **Path observability via message, not attribute.** The raised `MalformedLockfileError`'s `args[0]` contains `str(path)` as a substring (so downstream `WarningId` construction in `NodeManifestProbe` can recover it from the message without instance state).
- [ ] **AC-9.** **`NpmLock` `TypedDict` declared `total=False`** with at minimum `name: str`, `version: str`, `lockfileVersion: int`, `requires: bool`, `packages: dict[str, Any]`, `dependencies: dict[str, Any]` — covering lockfileVersion 1/2/3 fields. The `total=False` flag is **load-bearing** — v1 lacks `packages`, v3 lacks `dependencies`; defaulting at the parser layer is forbidden (consumer-side concern per Note #1).
- [ ] **AC-10.** **Top-level non-mapping** (JSON list / scalar / `null` document) raises `MalformedLockfileError` via the `MalformedJSONError` translation path (`safe_json._decode` raises `MalformedJSONError("expected JSON object at top level")` for non-dict top-level; `parse()` catches it like any other malformed-JSON and re-raises as `MalformedLockfileError`). Asserts the typed exception, not a `TypeError`.
- [ ] **AC-11.** **Empty file** raises `MalformedLockfileError` via the same translation path (`safe_json._decode` raises `MalformedJSONError("empty file")` for zero-byte input; translates to `MalformedLockfileError` per AC-5).
- [ ] **AC-12.** **Extension-by-addition.** Adding a future sibling parser (e.g., `_bun.py` for `bun.lockb`) requires **zero edits** to `_npm.py`. Pinned via an architectural test that asserts `_npm.py`'s module text contains no string occurrences of `"_pnpm"`, `"_yarn"`, or `"_bun"` (sibling parsers don't import each other; the kernel they share is `parsers/safe_json.py` + `codegenie.errors`).
- [ ] **AC-13.** **Module hygiene.** `ruff format --check`, `ruff check`, `mypy --strict src/codegenie/probes/_lockfiles/_npm.py`, and the unit-test module pass. The cast `cast(NpmLock, raw)` is the **only** runtime-no-op present; no schema validation, no field defaulting, no key reshaping.
- [ ] **AC-14.** **TDD discipline.** The red marker commit lands first (`ModuleNotFoundError: codegenie.probes._lockfiles._npm`); each failure-path test asserts the **specific** typed exception class (not just `CodegenieError`); the happy-path test asserts dict-shape, not value-equality of nested structures (that's `NodeManifestProbe`'s concern).
- [ ] **AC-15.** **Marker-attribute negative.** A parametrized test asserts that for the `MalformedLockfileError` this module constructs, the caught instance has `args == (some_str,)` and `not hasattr(exc, "path" | "cap" | "detail" | "cause" | "warning_id")` — pins the marker discipline against silent regressions.

## Implementation outline

1. Create `src/codegenie/probes/_lockfiles/_npm.py`:
   - Module docstring naming arch §"Component design" #9 and ADR-0008/0009 (mirror `_pnpm.py`'s docstring shape).
   - `__all__ = ["NpmLock", "parse"]`.
   - Module constants: `NPM_LOCKFILE_MAX_BYTES: Final[int] = 50 * 1024 * 1024`, `NPM_LOCKFILE_MAX_DEPTH: Final[int] = 64`.
   - `class NpmLock(TypedDict, total=False):` with `name`, `version`, `lockfileVersion`, `requires`, `packages`, `dependencies`.
   - `def parse(path: Path) -> NpmLock:` that calls `safe_json.load(path, max_bytes=NPM_LOCKFILE_MAX_BYTES, max_depth=NPM_LOCKFILE_MAX_DEPTH)`, lets `SizeCapExceeded`/`DepthCapExceeded`/`SymlinkRefusedError` propagate, catches `MalformedJSONError as cause` and raises `MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}") from cause`, then `return cast(NpmLock, raw)`.
2. **Do NOT edit `src/codegenie/probes/_lockfiles/__init__.py`.** S3-01 settled it as `__all__: list[str] = []` plus a docstring; S3-02 inherits and adds **one** new file. (Architectural test in AC-1 pins this.)
3. Write the unit-test module per the TDD plan below — twelve named tests, each keyed to ACs. `tests/unit/probes/_lockfiles/__init__.py` already exists from S3-01; do not recreate.

**No constructor extension of `MalformedLockfileError`.** The marker contract is frozen per Phase 0 invariant + S1-01 parametrized tests. Path lives in `args[0]`; cause lives on `__cause__` via `raise ... from cause`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/_lockfiles/test_npm.py`. Each test is annotated with its AC and the mutation it catches.

```python
# tests/unit/probes/_lockfiles/test_npm.py
"""Unit tests for ``codegenie.probes._lockfiles._npm``.

Each test is keyed to an AC in S3-02 and names the mutation it catches in
its docstring (mutation-resistance per Rule 9 — tests verify intent).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from codegenie.errors import (
    DepthCapExceeded,
    MalformedJSONError,
    MalformedLockfileError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.probes._lockfiles import _npm


# --- AC-2, AC-3, AC-9, AC-14 ---------------------------------------------------


def test_parse_happy_path_v3_returns_typed_dict_shape(tmp_path: Path) -> None:
    """AC-3, AC-9. Mutation caught: dropping ``total=False`` (v1 fixture has
    ``dependencies`` only, v3 has ``packages`` only — total=True would
    require all six keys present in every NpmLock instance)."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text(
        '{"name":"x","version":"1.0.0","lockfileVersion":3,'
        '"packages":{"":{"name":"x","version":"1.0.0"}}}'
    )
    result = _npm.parse(lockfile)
    assert result["lockfileVersion"] == 3
    assert result["name"] == "x"
    assert result["packages"] == {"": {"name": "x", "version": "1.0.0"}}
    # Shape only — value-equality of nested structure is NodeManifestProbe's job.


def test_parse_happy_path_v1_missing_packages_still_parses(tmp_path: Path) -> None:
    """AC-9. Mutation caught: TypedDict ``total=True`` would still parse at
    runtime (TypedDict is unenforced at runtime) but mypy --strict on the
    consumer side would flag missing ``packages`` for v1 fixtures —
    assertion is the runtime no-op, the load-bearing check is the mypy
    invocation in AC-13. v1 ships ``dependencies`` (nested tree) only."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text(
        '{"name":"x","version":"1.0.0","lockfileVersion":1,"requires":true,'
        '"dependencies":{"lodash":{"version":"4.17.21"}}}'
    )
    result = _npm.parse(lockfile)
    assert "packages" not in result  # v1 shape — no flat tree.
    assert result["lockfileVersion"] == 1
    assert result["dependencies"] == {"lodash": {"version": "4.17.21"}}


# --- AC-4 — size cap (re-raised unchanged) -------------------------------------


def test_parse_oversized_file_reraises_size_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4. Mutation caught: swallowing SizeCapExceeded into MalformedLockfileError.

    Uses ``os.fstat`` monkey-patch instead of writing 60 MB to tmpfs (Rule 2 —
    smallest test that proves the contract; mirrors S3-01 / S1-02 precedents
    for deterministic, fast size-cap assertions).
    """
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"name":"x","lockfileVersion":3,"packages":{}}')

    real_fstat = os.fstat

    class FakeStat:
        def __init__(self, st: os.stat_result) -> None:
            self._st = st

        # Pretend the file is 60 MB on disk; pre-parse cap fires before any read.
        st_size = 60 * 1024 * 1024
        st_mode = property(lambda self: self._st.st_mode)  # type: ignore[no-redef]

    def fake_fstat(fd: int) -> Any:  # noqa: ANN401 — stub mirrors stdlib
        return FakeStat(real_fstat(fd))

    monkeypatch.setattr(os, "fstat", fake_fstat)
    with pytest.raises(SizeCapExceeded):
        _npm.parse(lockfile)


# --- AC-4 — depth cap (re-raised unchanged) ------------------------------------


def test_parse_deep_nesting_reraises_depth_cap(tmp_path: Path) -> None:
    """AC-4. Mutation caught: swallowing DepthCapExceeded into MalformedLockfileError.

    JSON has no aliases (unlike YAML), so bracket-nesting is the canonical
    depth-cap vector — ``json.loads`` parses the deeply-nested object fine
    (stdlib C extension iterates within `sys.getrecursionlimit()`), then
    the post-parse depth walker raises ``DepthCapExceeded`` at depth 65.
    70 levels of ``{"a": {...}}`` produces depth 70 > max_depth 64 → fires.
    """
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text("{" + '"a":{' * 70 + "}" * 71)
    with pytest.raises(DepthCapExceeded):
        _npm.parse(lockfile)


# --- AC-4 — symlink refusal (re-raised unchanged) ------------------------------


def test_parse_symlink_at_final_component_reraises_symlink_refused(
    tmp_path: Path,
) -> None:
    """AC-4. Mutation caught: any path that follows the symlink instead of
    refusing it (e.g., dropping ``O_NOFOLLOW`` in a hypothetical re-impl;
    here, the wrapper inherits the defense and must let the exception
    propagate unchanged)."""
    real = tmp_path / "real.json"
    real.write_text('{"name":"x","lockfileVersion":3,"packages":{}}')
    link = tmp_path / "package-lock.json"
    link.symlink_to(real)
    with pytest.raises(SymlinkRefusedError):
        _npm.parse(link)


# --- AC-5, AC-7, AC-8, AC-10, AC-11 — malformed-JSON translation ---------------


def test_parse_malformed_json_raises_malformed_lockfile_with_cause_chain(
    tmp_path: Path,
) -> None:
    """AC-5, AC-7. Mutation caught: dropping ``from cause`` (loses
    ``__cause__``); catching ``Exception`` (would absorb unrelated types);
    translating to a different marker class."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"unterminated')  # JSONDecodeError path.
    with pytest.raises(MalformedLockfileError) as exc:
        _npm.parse(lockfile)
    # AC-7: ``__cause__`` is the original MalformedJSONError.
    assert isinstance(exc.value.__cause__, MalformedJSONError)


def test_parse_malformed_json_message_contains_path(tmp_path: Path) -> None:
    """AC-8. Mutation caught: building the message without the path (e.g.,
    ``MalformedLockfileError(str(cause))``) — downstream WarningId
    construction in NodeManifestProbe recovers the path from ``args[0]``."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text("not valid json at all")
    with pytest.raises(MalformedLockfileError) as exc:
        _npm.parse(lockfile)
    assert str(lockfile) in exc.value.args[0]


def test_parse_top_level_non_mapping_raises_malformed_lockfile(tmp_path: Path) -> None:
    """AC-10. Mutation caught: returning the non-mapping object (the cast
    would silently widen ``list`` to ``NpmLock``); the translation pass
    re-uses the same MalformedJSONError→MalformedLockfileError handler.
    ``safe_json._decode`` raises ``MalformedJSONError("expected JSON object
    at top level")`` for any top-level non-dict — we translate it like any
    other malformed-JSON cause."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('["a","b"]')  # top-level JSON array, not a mapping.
    with pytest.raises(MalformedLockfileError):
        _npm.parse(lockfile)


def test_parse_empty_file_raises_malformed_lockfile(tmp_path: Path) -> None:
    """AC-11. Mutation caught: only translating the JSONDecodeError path
    (e.g., ``except json.JSONDecodeError: ...``) would miss the empty-file
    branch — ``safe_json._decode`` raises ``MalformedJSONError("empty
    file")`` *before* ``json.loads`` runs. We catch ``MalformedJSONError``
    as the class, so empty files surface as ``MalformedLockfileError``."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_bytes(b"")
    with pytest.raises(MalformedLockfileError):
        _npm.parse(lockfile)


# --- AC-6, AC-15 — marker discipline ------------------------------------------


def test_raised_marker_has_no_instance_attributes(tmp_path: Path) -> None:
    """AC-6, AC-15. Mutation caught: a future "convenience" override of
    ``MalformedLockfileError.__init__(self, *, path, cause)`` would be
    flagged immediately. The Phase-0 invariant
    ``test_subclasses_are_markers_only`` already guards the class-level
    contract; this test guards the construction site in _npm.py."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"unterminated')
    with pytest.raises(MalformedLockfileError) as exc:
        _npm.parse(lockfile)
    # Marker invariant: args is a single positional message string.
    assert len(exc.value.args) == 1
    assert isinstance(exc.value.args[0], str)
    # Negatives — no instance attributes smuggled in.
    for forbidden in ("path", "cap", "detail", "cause", "warning_id"):
        assert not hasattr(exc.value, forbidden), (
            f"MalformedLockfileError must remain a marker; instance must not "
            f"carry {forbidden!r}. Path lives in args[0]; cause lives on __cause__."
        )


# --- AC-12 — extension-by-addition (architectural test) -----------------------


def test_npm_module_does_not_reference_sibling_parsers() -> None:
    """AC-12, CLAUDE.md "Extension by addition". Mutation caught: a future
    edit that imports ``_pnpm`` / ``_yarn`` / ``_bun`` into ``_npm`` —
    sibling parsers must be free to evolve independently. The shared
    kernel is ``parsers/safe_json`` + ``codegenie.errors``, not other
    sibling modules."""
    import inspect

    src = inspect.getsource(_npm)
    for forbidden in ("_pnpm", "_yarn", "_bun"):
        assert forbidden not in src, (
            f"_npm.py must not reference sibling parser {forbidden!r}; "
            f"adding a new lockfile format is a new file, not an edit here."
        )


# --- AC-1 — _lockfiles/__init__.py stays inert (S3-02 doesn't edit it) --------


def test_lockfiles_init_remains_inert() -> None:
    """AC-1, CLAUDE.md "Extension by addition". Mutation caught: an
    implementer adding ``from . import _npm`` or ``NpmLock`` to the
    package ``__init__`` — S3-01 settled this file as inert and S3-02
    must not touch it. The contract: ``__all__: list[str] = []`` and
    sibling parsers export from their own modules."""
    from codegenie.probes import _lockfiles

    assert getattr(_lockfiles, "__all__", None) == [], (
        "_lockfiles/__init__.py is settled as inert by S3-01 — S3-02 must "
        "not re-export NpmLock through it. Consumers import siblings directly."
    )
    # Negative: no NpmLock attribute leaked through the package.
    assert not hasattr(_lockfiles, "NpmLock"), (
        "NpmLock must be imported from codegenie.probes._lockfiles._npm, "
        "not the package __init__. S3-03 may revisit if extracting a shared "
        "_translate helper (rule of three)."
    )
```

Run `pytest tests/unit/probes/_lockfiles/test_npm.py` — fails with `ModuleNotFoundError: codegenie.probes._lockfiles._npm`. Commit the red marker.

### Green — make it pass

```python
# src/codegenie/probes/_lockfiles/_npm.py
"""package-lock.json parser — thin ``safe_json.load`` wrapper.

The parser shapes nothing and validates no fields — its job is to
translate exactly one exception class (:class:`MalformedJSONError` ->
:class:`MalformedLockfileError`) while preserving the original on
``__cause__`` so the catch site in :class:`NodeManifestProbe` (S3-05)
constructs the structured ``WarningId`` per ADR-0007 from
``exc.args[0]``.

All other typed exceptions raised by :func:`safe_json.load` propagate
unchanged (:class:`SizeCapExceeded`, :class:`DepthCapExceeded`,
:class:`SymlinkRefusedError`). ``FileNotFoundError`` and other
``OSError`` subclasses propagate from the underlying open.

npm's lockfile has three on-disk shapes:

- ``lockfileVersion`` 1 (npm 5/6): legacy nested ``dependencies`` only.
- ``lockfileVersion`` 2 (npm 7+): both flat ``packages`` and nested
  ``dependencies`` (for backward compatibility — why this format is
  larger than pnpm/yarn equivalents and why the 50 MB cap matters).
- ``lockfileVersion`` 3 (npm 9+): flat ``packages`` only.

``NpmLock`` is ``total=False`` to admit all three shapes without
defaulting at the parser layer — version reconciliation is
:class:`NodeManifestProbe`'s job.

Sources:

- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #9 — interface and ~100 ms p50 budget.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0008-in-process-parse-caps-not-per-probe-sandbox.md`` (ADR-0008)
  ratifies the in-process caps; ``0009-no-new-c-extension-parser-dependencies.md``
  (ADR-0009) pins stdlib ``json`` as the only allowed JSON parser.

Phase-0 marker invariant: :class:`MalformedLockfileError` accepts a
single positional message string; the path lives in ``args[0]``, the
cause lives on ``__cause__`` via ``raise ... from cause``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final, TypedDict, cast

from codegenie.errors import MalformedJSONError, MalformedLockfileError
from codegenie.parsers import safe_json

__all__ = ["NpmLock", "parse"]

NPM_LOCKFILE_MAX_BYTES: Final[int] = 50 * 1024 * 1024
NPM_LOCKFILE_MAX_DEPTH: Final[int] = 64


class NpmLock(TypedDict, total=False):
    """``package-lock.json`` shape — ``total=False`` is load-bearing.

    npm v1 ships ``dependencies`` only; v2 ships both ``packages`` and
    ``dependencies``; v3 ships ``packages`` only. The parser does NOT
    default missing keys — version reconciliation is
    :class:`NodeManifestProbe`'s job.
    """

    name: str
    version: str
    lockfileVersion: int
    requires: bool
    packages: dict[str, Any]
    dependencies: dict[str, Any]


def parse(path: Path) -> NpmLock:
    """Parse a ``package-lock.json`` under the 50 MB / depth 64 caps.

    Raises:
        SizeCapExceeded: re-raised unchanged from ``safe_json.load``.
        DepthCapExceeded: re-raised unchanged from ``safe_json.load``.
        SymlinkRefusedError: re-raised unchanged from ``safe_json.load``.
        MalformedLockfileError: translated from ``MalformedJSONError``;
            the original is preserved on ``__cause__``. The message in
            ``args[0]`` includes ``str(path)`` so downstream
            ``WarningId`` construction can recover the path. Covers all
            three ``safe_json`` malformed-JSON paths: decode error, empty
            file, and top-level non-mapping.
        FileNotFoundError: propagated from the underlying open.
    """
    try:
        raw = safe_json.load(
            path,
            max_bytes=NPM_LOCKFILE_MAX_BYTES,
            max_depth=NPM_LOCKFILE_MAX_DEPTH,
        )
    except MalformedJSONError as cause:
        raise MalformedLockfileError(
            f"{path}: {type(cause).__name__}: {cause}"
        ) from cause
    return cast(NpmLock, raw)
```

### Refactor

- Module constants stay per-file. They are identical across pnpm/npm/yarn (50 MB / depth 64). Rule 2 ("three similar lines is better than premature abstraction") + S3-01's settled deferral push the lift-to-shared-constants decision to **S3-03's land time** (rule of three). S3-02 is the second; do not pre-emptively extract.
- Likewise, the `try/except MalformedXError as cause: raise MalformedLockfileError(...) from cause` block is now duplicated across `_pnpm.py` and `_npm.py`. **Do not extract a shared `_translate(path, *, cause)` helper yet.** Premature extraction in S3-02 would create a kernel that S3-03 inherits silently and bias the trio's API toward a shape the third consumer might disprefer. The extraction decision is S3-03's, after the third concrete shape is visible.
- The cast to `NpmLock` is a runtime no-op. If a future change adds a structural validator, it lives in `NodeManifestProbe`, not here.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/_lockfiles/_npm.py` | New file — `NpmLock` `TypedDict` + `parse()` wrapper + module constants. |
| `tests/unit/probes/_lockfiles/test_npm.py` | New file — twelve tests, each keyed to one or more ACs. |

**Explicitly NOT touched:** `src/codegenie/probes/_lockfiles/__init__.py` (S3-01's settled inert form; pinned by AC-1) and `tests/unit/probes/_lockfiles/__init__.py` (already exists from S3-01).

## Out of scope

- **`_yarn.py`** — S3-03 (ADR-0003 land-time decision lives there, not here). S3-03 is the rule-of-three trigger: at that point, evaluate extracting `_translate(path, *, cause)` and/or shared cap constants.
- **lockfileVersion 1 ↔ 3 normalization** — `NodeManifestProbe` (S3-05) reconciles; the parser is shape-faithful.
- **Resolving the `node_modules/` paths inside `packages:`** — S3-05 (probe).
- **Validating `lockfileVersion` is one of {1, 2, 3}** — defer to S3-05 (probe records `confidence: low` on unknown versions; the parser is permissive).
- **Fixtures with real native modules** — S3-06's `node_pnpm_native/` portfolio.
- **Schema validation of `NpmLock`** — the wrapper is intentionally lenient. Phase 0's `_ProbeOutputValidator` handles output validation; lockfile *input* shape is `NodeManifestProbe`'s concern.
- **Editing `_lockfiles/__init__.py`** — S3-01 settled it; AC-1 pins the non-edit.

## Notes for the implementer

1. **Don't validate the lockfile schema here.** The thin wrapper exists so `NodeManifestProbe` (S3-05) decides what "valid enough" means per consumer (recipe planner vs. distroless build vs. SBOM). Adding a validator is a one-way ratchet.
2. **`safe_json.load` from S1-02 already handles `O_NOFOLLOW`, pre-parse `os.fstat` size check, top-level-dict assertion, empty-file guard, and the post-parse depth walker.** This module adds zero defense-in-depth — its only job is to translate `MalformedJSONError` into `MalformedLockfileError` so the probe error catalog stays clean and `NodeManifestProbe` can match one class to one warning ID per ADR-0007. All three `safe_json` paths that raise `MalformedJSONError` — decode error, empty file, top-level non-mapping — must be covered by the single `except MalformedJSONError as cause` handler. The class is caught, not the message; that is why all three paths translate uniformly.
3. **Marker construction is positional-only.** Phase 0's `test_subclasses_are_markers_only` and S1-01's `test_phase1_subclasses_accept_message_arg_and_expose_args0` parametrize `MalformedLockfileError` and assert `not hasattr(exc, "path")`. Do **not** add a `MalformedLockfileError.__init__(self, *, path, cause)`. The path goes in `args[0]`; the cause goes on `__cause__` via `raise ... from cause`. This is the same pattern S1-02, S1-03, and S3-01 already settled.
4. **The 60 MB size-cap test uses `os.fstat` monkey-patching, not a 60 MB write.** Writing 60 MB to tmpfs is wasteful and CI-flaky; the cap fires on `os.fstat(fd).st_size > max_bytes` (S1-02 docstring) so monkey-patching `os.fstat` is the load-bearing assertion. Mirrors S3-01.
5. **JSON has no aliases — bracket-nesting is the canonical depth-cap vector.** Unlike YAML (where `[[[[...]]]]` surfaces as `ScannerError`, requiring the alias-amplification vector for the depth path to fire), `json.loads` parses ``{"a":{"a":...}}`` 70-deep in C-extension iteration without hitting Python recursion (stdlib `_json.c` is iterative for object/array bodies). The post-parse depth walker (`parsers/_depth.assert_max_depth`) then raises `DepthCapExceeded` at depth 65. The `id()`-memoization in the walker is non-load-bearing for JSON (JSON produces trees, not DAGs) but harmless. 70 levels is well above the 64 cap; if you change the literal, surface in PR body why.
6. **npm version variance**: v1 ships `dependencies` only; v3 ships `packages` only; v2 ships both. `total=False` is the load-bearing choice — defaulting any key here would mask version skew downstream. Do not add a `lockfileVersion` switch in `parse()`; `NodeManifestProbe` reads whichever tree is present.
7. **Rule of three (deferred extraction).** All three lockfile parsers share the shape `try: safe_X.load(...) except MalformedXError as cause: raise MalformedLockfileError(f"{path}: ...") from cause`. **Do NOT extract a shared `_translate(path, *, cause)` helper in S3-02.** S3-02 is the second concrete instance — rule of three is the third. The extraction decision (and the question of whether to lift it into `_lockfiles/__init__.py` versus `parsers/_lockfile_io.py`) is S3-03's at land time. Premature extraction creates a kernel S3-03 inherits silently. Reference: CLAUDE.md Rule 2, `_validation/S3-01-pnpm-lockfile-parser.md` "Follow-up obligations."
8. **Open/Closed at the family level.** Adding a `_bun.py` later must require zero edits to `_npm.py`. AC-12's source-introspection test fires immediately if a future implementer adds a sibling-import. The shared kernel for the family is `parsers/safe_json` + `codegenie.errors`, not other sibling modules.
9. **Why `cast(NpmLock, raw)` and not a runtime validator.** TypedDict is a static-only construct; the cast is a no-op at runtime. If `safe_json.load` returned the wrong shape (it won't — it asserts top-level-dict in `_decode`), the failure surfaces at the first key access in `NodeManifestProbe`, not here. This is the deliberate functional-core / imperative-shell split: parse is I/O + translation only; validation is interpretation, which lives with the consumer.
10. **`__all__ = ["NpmLock", "parse"]`** is intentional — module constants (`NPM_LOCKFILE_MAX_BYTES`, `NPM_LOCKFILE_MAX_DEPTH`) are not exported. They are tunable internals; downstream callers that need to know the cap should read it from the module docstring, not import the constant. Mirrors S3-01.
11. **`_lockfiles/__init__.py` is settled — do not touch it.** S3-01 committed it as `__all__: list[str] = []` plus a docstring declaring "S3-01 ships `_pnpm`; S3-02 ships `_npm`; S3-03 ships `_yarn`. `__all__` stays empty here — each sibling exports from its own module." Consumers import siblings directly (`from codegenie.probes._lockfiles import _npm`), which works because `_npm` is a submodule of the package. AC-1's test pins the non-edit. If S3-03 decides to extract a shared helper into the package `__init__`, *that* is when the file may grow — and only by S3-03's hand.
