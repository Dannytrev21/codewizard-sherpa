# Story S3-01 — `_pnpm` lockfile parser

**Step:** Step 3 — Ship `NodeManifestProbe` and the three lockfile parsers
**Status:** Ready (HARDENED)
**Effort:** S
**Depends on:** S1-03 (`safe_yaml.load`), S1-01 (Phase 1 marker exceptions)
**ADRs honored:** ADR-0008 (in-process caps, not per-probe sandbox), ADR-0009 (no new C-extension parser deps), ADR-0007 (`WarningId` constructed at catch site)
**Phase-0 invariant honored:** `tests/unit/test_errors.py::test_subclasses_are_markers_only` and `::test_phase1_subclasses_accept_message_arg_and_expose_args0` — marker exceptions accept a single positional message string and expose **no** instance state.

## Validation notes (2026-05-14 — phase-story-validator HARDENED)

Two **block-level** corrections applied (see `_validation/S3-01-pnpm-lockfile-parser.md` for full audit):

1. **Marker exception construction.** The draft prescribed `MalformedLockfileError(path=path, cause=e)` (kwargs) and a test assertion `exc.value.path == lockfile`. Phase 0's `test_subclasses_are_markers_only` and S1-01's `test_phase1_subclasses_accept_message_arg_and_expose_args0` parametrize **every Phase-1 marker** (including `MalformedLockfileError`) as positional-only — `hasattr(exc, "path")` is an asserted **negative**. Construction must be `MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}") from cause`. The implementer-notes hedge ("if `__init__` doesn't accept `path` + `cause`, surface as a blocker") was rewritten as a settled fact — the marker contract is frozen, the path lives in `args[0]`, the original lives on `__cause__`.
2. **Implementation outline step 4 deleted.** "Confirm `MalformedLockfileError` carries `path`; add constructor argument if missing" is wrong on both counts (it doesn't, and adding one would break Phase 0). Replaced with the positional-format directive.

Twelve harden-tier additions: depth-cap test uses YAML alias amplification (matches arch §"Edge cases" row 1 + S1-03's canonical alias-bomb fixture, not the draft's bracket-nesting which surfaces as `MalformedYAMLError`-from-`ScannerError`); size-cap test monkey-patches `os.fstat` rather than writing 60 MB to tmpfs; `__cause__` chain pinned; symlink passthrough test added; all four typed exceptions parametrized across one test; `total=False` semantics pinned via a v6-shape fixture and a v9-shape fixture; non-mapping-top-level translation (`MalformedYAMLError` → `MalformedLockfileError`) made explicit; `_lockfiles/__init__.py` content concretized; module constants typed `Final`; dead `FIXTURE_DIR` reference removed; `__all__` declared on the module; extension-by-addition AC pinned ("adding `_bun.py` must require zero edits to `_pnpm.py`" — load-bearing per CLAUDE.md "Extension by addition").

Design-pattern opportunities recorded in Notes for the implementer (rule-of-three deferral: no shared `_translate(path)` helper extracted yet — that's S3-03's call after all three sibling parsers exist). No `NEEDS RESEARCH` findings; Stage 3 skipped.

## Context

`pnpm-lock.yaml` is the most common modern Node lockfile and is the parse-cost hot spot of `NodeManifestProbe` (~250 ms p50 on a typical 5 MB file). This story ships the thinnest possible adapter on top of `safe_yaml.load`: read the lockfile under the 50 MB + depth 64 caps that arch §"Component design" #9 pins, return a typed dict, and translate exactly one exception class (`MalformedYAMLError` → `MalformedLockfileError`) so the probe error catalog stays clean. **No interpretation of fields, no flattening of the `packages:` tree** — that is `NodeManifestProbe`'s job in S3-05.

This is the smallest of the three lockfile parsers — straight `safe_yaml.load` + a `TypedDict` cast + a single exception-translation pass. It exists separately because pnpm/npm/yarn have format-specific *callers* in `NodeManifestProbe`, even though the parse layer is one-liner-thin. The three sibling files compose the parser plugin family — adding a fourth (`_bun.py`) is a new file with zero edits to the existing three (load-bearing extension-by-addition commitment per CLAUDE.md).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #9 Lockfile parsers` — interface, `safe_yaml.load` wrapper, ~250 ms p50 budget.
  - `../phase-arch-design.md §"Component design" #4 NodeManifestProbe` — the caller; lockfile is in `declared_inputs`.
  - `../phase-arch-design.md §"Edge cases"` row 1 — billion-laughs `pnpm-lock.yaml` → `DepthCapExceeded` (the YAML-alias-amplification path; **not** straight bracket-nesting which surfaces as `MalformedYAMLError`).
  - `../phase-arch-design.md §"Component design" #8 Safe-parse helpers` — the load contract `safe_yaml.load(path, *, max_bytes, max_depth=64)` and the exception map.
  - `../phase-arch-design.md §"Scenarios" #3` — billion-laughs end-to-end flow under `safe_yaml`'s `id()`-memoized walker (the depth violation the alias-amplification test exercises).
- **Phase ADRs:**
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — why the size+depth caps are the parser's job, not a sandbox's.
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — `pyyaml.CSafeLoader` only; no `ruamel.yaml`.
  - `../ADRs/0007-warnings-id-pattern.md` — `WarningId` is constructed at the catch site (in `NodeManifestProbe`) from the marker's `args[0]`, not embedded on the exception.
- **Source design:**
  - `../final-design.md §"Components" #4` — three sibling parsers under `_lockfiles/`.
  - `../High-level-impl.md §"Step 3"` — first deliverable bullet.
- **Existing code (Phase 0 + Step 1):**
  - `src/codegenie/parsers/safe_yaml.py` — `load(path, *, max_bytes, max_depth=64)` from S1-03; raises `SizeCapExceeded`, `DepthCapExceeded`, `MalformedYAMLError`, `SymlinkRefusedError`.
  - `src/codegenie/errors.py` — Phase 1 markers are `class X(CodegenieError): """..."""` with **no `__init__`** override (Phase 0 invariant: `cls.__init__ is CodegenieError.__init__`).
  - `tests/unit/test_errors.py::test_phase1_subclasses_accept_message_arg_and_expose_args0` — parametrizes every Phase 1 marker (incl. `MalformedLockfileError`) for positional construction and asserts `not hasattr(exc, "path" | "cap" | "detail" | "warning_id")`.
- **Validation precedents (the marker discipline already settled):**
  - `_validation/S1-02-safe-json-parser.md` — first kwargs-on-markers correction.
  - `_validation/S1-03-safe-yaml-parser.md` — second; introduced positional `f"{path}: {type(cause).__name__}: {cause}"` and `raise ... from cause` as the canonical translation form.

## Goal

Implement `src/codegenie/probes/_lockfiles/_pnpm.py` as a thin `safe_yaml.load` wrapper returning a `PnpmLock` `TypedDict`, so `NodeManifestProbe` can call `_pnpm.parse(path)` and receive a parsed-and-capped dict — or one of five typed exceptions (`SizeCapExceeded`, `DepthCapExceeded`, `SymlinkRefusedError` re-raised unchanged from `safe_yaml`; `MalformedLockfileError` translated from `MalformedYAMLError` with `__cause__` preserved; `FileNotFoundError` propagated from the OS open). All marker exceptions remain positional-message-only per Phase 0's marker invariant.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

- [ ] **AC-1.** `src/codegenie/probes/_lockfiles/__init__.py` exists with the literal content: a module docstring referencing the package's role plus `__all__: list[str] = []` (re-exports are added incrementally by S3-02 / S3-03; S3-01 keeps the file inert so import order is unsurprising).
- [ ] **AC-2.** `src/codegenie/probes/_lockfiles/_pnpm.py` exports exactly `__all__ = ["PnpmLock", "parse"]`.
- [ ] **AC-3.** `parse(path: Path) -> PnpmLock` calls `safe_yaml.load(path, max_bytes=PNPM_LOCKFILE_MAX_BYTES, max_depth=PNPM_LOCKFILE_MAX_DEPTH)` with `PNPM_LOCKFILE_MAX_BYTES: Final[int] = 50 * 1024 * 1024` and `PNPM_LOCKFILE_MAX_DEPTH: Final[int] = 64` declared at module scope (matches arch §"Component design" #9 cap).
- [ ] **AC-4.** `parse(path)` **re-raises unchanged** any `SizeCapExceeded`, `DepthCapExceeded`, or `SymlinkRefusedError` raised by `safe_yaml.load`. No re-wrapping, no swallowing.
- [ ] **AC-5.** `parse(path)` translates `MalformedYAMLError` raised by `safe_yaml.load` into `MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}")` raised `from cause`, so the original `MalformedYAMLError` is preserved on `__cause__` (per S1-03 precedent; Rule 12 — fail loud with the chain).
- [ ] **AC-6.** **Marker contract preserved.** The raised `MalformedLockfileError` carries its message in `args[0]` only; `hasattr(exc, "path")` and `hasattr(exc, "cause")` are both **False**. The Phase 0 invariant `tests/unit/test_errors.py::test_subclasses_are_markers_only` is unaffected by S3-01 code.
- [ ] **AC-7.** **`__cause__` chain.** For the malformed-YAML path, `exc.__cause__` is the original `MalformedYAMLError` instance (`isinstance(exc.__cause__, MalformedYAMLError)` holds; the test pins the class, not the message).
- [ ] **AC-8.** **Path observability via message, not attribute.** The raised `MalformedLockfileError`'s `args[0]` contains `str(path)` as a substring (so downstream `WarningId` construction in `NodeManifestProbe` can recover it from the message without instance state).
- [ ] **AC-9.** **`PnpmLock` `TypedDict` declared `total=False`** with at minimum `lockfileVersion: str | float`, `packages: dict[str, Any]`, `importers: dict[str, Any]`, `snapshots: dict[str, Any]` (pnpm v6 has the first three; v9 adds `snapshots`). The `total=False` flag is **load-bearing** — versions disagree on which fields are present; defaulting at the parser layer is forbidden (consumer-side concern per Note #1).
- [ ] **AC-10.** **Top-level non-mapping** (list / scalar / `None` document) raises `MalformedLockfileError` via the `MalformedYAMLError` translation path (`safe_yaml.load` raises `MalformedYAMLError` for non-mapping top-level; `parse()` catches it like any other malformed-YAML and re-raises as `MalformedLockfileError`). Asserts the typed exception, not a `TypeError`.
- [ ] **AC-11.** **Single-document only.** `parse()` calls `safe_yaml.load`, not `safe_yaml.load_all`; a multi-document `pnpm-lock.yaml` (`---\nlockfileVersion: '9.0'\n---\n...`) raises `MalformedYAMLError` from CSafeLoader's single-doc parser and is translated to `MalformedLockfileError` per AC-5.
- [ ] **AC-12.** **Extension-by-addition.** Adding a future sibling parser (e.g., `_bun.py` for `bun.lockb`) requires **zero edits** to `_pnpm.py`. Pinned via an architectural test that asserts `_pnpm.py`'s module text contains no string occurrences of `"_npm"`, `"_yarn"`, or `"_bun"` (sibling parsers don't import each other; the kernel they share is `parsers/safe_yaml.py` + `codegenie.errors`).
- [ ] **AC-13.** **Module hygiene.** `ruff format --check`, `ruff check`, `mypy --strict src/codegenie/probes/_lockfiles/_pnpm.py`, and the unit-test module pass. The cast `cast(PnpmLock, raw)` is the **only** runtime-no-op present; no schema validation, no field defaulting, no key reshaping.
- [ ] **AC-14.** **TDD discipline.** The red marker commit lands first (`ModuleNotFoundError: codegenie.probes._lockfiles._pnpm`); each failure-path test asserts the **specific** typed exception class (not just `CodegenieError`); the happy-path test asserts dict-shape, not value-equality of nested structures (that's `NodeManifestProbe`'s concern).
- [ ] **AC-15.** **Marker-attribute negative.** A parametrized test asserts that for every typed exception this module *can* raise (`SizeCapExceeded`, `DepthCapExceeded`, `SymlinkRefusedError`, `MalformedLockfileError`), the caught instance has `args == (some_str,)` and `not hasattr(exc, "path")` / `not hasattr(exc, "cap")` — pins the marker discipline against silent regressions.

## Implementation outline

1. Create `src/codegenie/probes/_lockfiles/__init__.py` with a docstring + `__all__: list[str] = []` (no re-exports yet).
2. Create `src/codegenie/probes/_lockfiles/_pnpm.py`:
   - Module docstring naming arch §"Component design" #9 and ADR-0008/0009.
   - `__all__ = ["PnpmLock", "parse"]`.
   - Module constants: `PNPM_LOCKFILE_MAX_BYTES: Final[int] = 50 * 1024 * 1024`, `PNPM_LOCKFILE_MAX_DEPTH: Final[int] = 64`.
   - `class PnpmLock(TypedDict, total=False):` with `lockfileVersion`, `packages`, `importers`, `snapshots`.
   - `def parse(path: Path) -> PnpmLock:` that calls `safe_yaml.load(path, max_bytes=PNPM_LOCKFILE_MAX_BYTES, max_depth=PNPM_LOCKFILE_MAX_DEPTH)`, lets `SizeCapExceeded`/`DepthCapExceeded`/`SymlinkRefusedError` propagate, catches `MalformedYAMLError as cause` and raises `MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}") from cause`, then `return cast(PnpmLock, raw)`.
3. Create `tests/unit/probes/_lockfiles/__init__.py` (empty package marker).
4. Write the unit-test module per the TDD plan below — eight named tests, all keyed to ACs.

**No constructor extension of `MalformedLockfileError`.** The marker contract is frozen per Phase 0 invariant + S1-01 parametrized tests. Path lives in `args[0]`; cause lives on `__cause__` via `raise ... from cause`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/_lockfiles/test_pnpm.py`. Each test is annotated with its AC and the mutation it catches.

```python
# tests/unit/probes/_lockfiles/test_pnpm.py
"""Unit tests for ``codegenie.probes._lockfiles._pnpm``.

Each test is keyed to an AC in S3-01 and names the mutation it catches in
its docstring (mutation-resistance per Rule 9 — tests verify intent).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from codegenie.errors import (
    DepthCapExceeded,
    MalformedLockfileError,
    MalformedYAMLError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.probes._lockfiles import _pnpm


# --- AC-2, AC-3, AC-9, AC-14 ---------------------------------------------------


def test_parse_happy_path_v9_returns_typed_dict_shape(tmp_path: Path) -> None:
    """AC-3, AC-9. Mutation caught: dropping ``total=False`` (v9 fixture has
    ``snapshots`` which v6 omits; total=True would require all 4 keys
    present in every PnpmLock instance — pnpm v6 callers would TypeError)."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text(
        "lockfileVersion: '9.0'\n"
        "importers:\n"
        "  .:\n"
        "    dependencies: {}\n"
        "packages: {}\n"
        "snapshots: {}\n"
    )
    result = _pnpm.parse(lockfile)
    assert result["lockfileVersion"] == "9.0"
    assert result["packages"] == {}
    assert result["snapshots"] == {}
    # Shape only — value-equality of nested structure is NodeManifestProbe's job.


def test_parse_happy_path_v6_missing_snapshots_still_parses(tmp_path: Path) -> None:
    """AC-9. Mutation caught: TypedDict ``total=True`` would still parse at
    runtime (TypedDict is unenforced at runtime) but mypy --strict on the
    consumer side would flag missing ``snapshots`` — assertion is the
    runtime no-op, the load-bearing check is the mypy invocation in AC-13."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("lockfileVersion: '6.0'\npackages: {}\nimporters: {}\n")
    result = _pnpm.parse(lockfile)
    assert "snapshots" not in result  # v6 shape — packages-only.
    assert result["lockfileVersion"] == "6.0"


# --- AC-4 — size cap (re-raised unchanged) -------------------------------------


def test_parse_oversized_file_reraises_size_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-4. Mutation caught: swallowing SizeCapExceeded into MalformedLockfileError.

    Uses ``os.fstat`` monkey-patch instead of writing 60 MB to tmpfs (Rule 2 —
    smallest test that proves the contract; matches the S1-03 precedent for
    deterministic, fast size-cap assertions).
    """
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("lockfileVersion: '9.0'\npackages: {}\n")

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
        _pnpm.parse(lockfile)


# --- AC-4 — depth cap, exercising the YAML alias-amplification path ------------


def test_parse_yaml_alias_amplification_reraises_depth_cap(tmp_path: Path) -> None:
    """AC-4, arch §Edge cases row 1, arch §Scenarios #3.

    The canonical billion-laughs vector for ``pnpm-lock.yaml``: a chain of
    YAML anchors / aliases produces O(k) physical nodes but exponential
    logical visits. ``safe_yaml.load``'s ``id()``-memoized walker raises
    ``DepthCapExceeded`` once the logical depth exceeds 64.

    Mutation caught: any depth-cap path that uses a non-memoizing walker
    (which would hang instead of raising) — the test asserts the typed
    exception under a pytest timeout shorter than the hang would take.
    """
    lockfile = tmp_path / "pnpm-lock.yaml"
    # Anchor chain: each level references the prior anchor. Depth at expansion >> 64.
    lines = ["a0: &a0 {x: 1}"]
    for i in range(1, 70):
        lines.append(f"a{i}: &a{i} {{x: *a{i - 1}, y: *a{i - 1}}}")
    lockfile.write_text("\n".join(lines) + "\n")
    with pytest.raises(DepthCapExceeded):
        _pnpm.parse(lockfile)


# --- AC-4 — symlink refusal (re-raised unchanged) ------------------------------


def test_parse_symlink_at_final_component_reraises_symlink_refused(tmp_path: Path) -> None:
    """AC-4. Mutation caught: any path that follows the symlink instead of
    refusing it (e.g., dropping ``O_NOFOLLOW`` in a hypothetical re-impl;
    here, the wrapper inherits the defense and must let the exception
    propagate unchanged)."""
    real = tmp_path / "real.yaml"
    real.write_text("lockfileVersion: '9.0'\npackages: {}\n")
    link = tmp_path / "pnpm-lock.yaml"
    link.symlink_to(real)
    with pytest.raises(SymlinkRefusedError):
        _pnpm.parse(link)


# --- AC-5, AC-7, AC-8, AC-10 — malformed-YAML translation ----------------------


def test_parse_malformed_yaml_raises_malformed_lockfile_with_cause_chain(tmp_path: Path) -> None:
    """AC-5, AC-7. Mutation caught: dropping ``from cause`` (loses
    ``__cause__``); catching ``Exception`` (would absorb unrelated types);
    translating to a different marker class."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("packages: {unclosed\n")
    with pytest.raises(MalformedLockfileError) as exc:
        _pnpm.parse(lockfile)
    # AC-7: ``__cause__`` is the original MalformedYAMLError.
    assert isinstance(exc.value.__cause__, MalformedYAMLError)


def test_parse_malformed_yaml_message_contains_path(tmp_path: Path) -> None:
    """AC-8. Mutation caught: building the message without the path (e.g.,
    ``MalformedLockfileError(str(cause))``) — downstream WarningId
    construction in NodeManifestProbe recovers the path from ``args[0]``."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text(": :\n")  # CSafeLoader rejects (ParserError).
    with pytest.raises(MalformedLockfileError) as exc:
        _pnpm.parse(lockfile)
    assert str(lockfile) in exc.value.args[0]


def test_parse_top_level_non_mapping_raises_malformed_lockfile(tmp_path: Path) -> None:
    """AC-10. Mutation caught: returning the non-mapping object (the cast
    would silently widen ``list`` to ``PnpmLock``); the translation pass
    re-uses the same MalformedYAMLError→MalformedLockfileError handler."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("- a\n- b\n")  # top-level YAML list, not a mapping.
    with pytest.raises(MalformedLockfileError):
        _pnpm.parse(lockfile)


# --- AC-6, AC-15 — marker discipline ------------------------------------------


@pytest.mark.parametrize(
    "trigger",
    [
        "malformed",
        # SizeCapExceeded/DepthCapExceeded/SymlinkRefusedError are exercised in
        # their own typed tests above; this parametrize specifically guards
        # MalformedLockfileError — the one we *construct* in _pnpm.py.
    ],
)
def test_raised_marker_has_no_instance_attributes(tmp_path: Path, trigger: str) -> None:
    """AC-6, AC-15. Mutation caught: a future "convenience" override of
    ``MalformedLockfileError.__init__(self, *, path, cause)`` would be
    flagged immediately. The Phase-0 invariant
    ``test_subclasses_are_markers_only`` already guards the class-level
    contract; this test guards the construction site in _pnpm.py."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("packages: {unclosed\n")
    with pytest.raises(MalformedLockfileError) as exc:
        _pnpm.parse(lockfile)
    # Marker invariant: args is a single positional message string.
    assert len(exc.value.args) == 1
    assert isinstance(exc.value.args[0], str)
    # Negatives — no instance attributes smuggled in.
    for forbidden in ("path", "cap", "detail", "cause", "warning_id"):
        assert not hasattr(exc.value, forbidden), (
            f"MalformedLockfileError must remain a marker; instance must not "
            f"carry {forbidden!r}. Path lives in args[0]; cause lives on __cause__."
        )


# --- AC-11 — single-document only ---------------------------------------------


def test_parse_multi_document_yaml_translates_to_malformed_lockfile(tmp_path: Path) -> None:
    """AC-11. Mutation caught: swapping ``safe_yaml.load`` for
    ``safe_yaml.load_all`` and returning the first document — would
    silently accept multi-doc lockfiles. Real pnpm-lock.yaml is
    single-document by spec; multi-doc is a malformed artifact."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text(
        "lockfileVersion: '9.0'\npackages: {}\n---\nlockfileVersion: '6.0'\npackages: {}\n"
    )
    with pytest.raises(MalformedLockfileError):
        _pnpm.parse(lockfile)


# --- AC-12 — extension-by-addition (architectural test) -----------------------


def test_pnpm_module_does_not_reference_sibling_parsers() -> None:
    """AC-12, CLAUDE.md "Extension by addition". Mutation caught: a future
    edit that imports ``_npm`` / ``_yarn`` / ``_bun`` into ``_pnpm`` —
    sibling parsers must be free to evolve independently. The shared
    kernel is ``parsers/safe_yaml`` + ``codegenie.errors``, not other
    sibling modules."""
    import inspect

    src = inspect.getsource(_pnpm)
    for forbidden in ("_npm", "_yarn", "_bun"):
        assert forbidden not in src, (
            f"_pnpm.py must not reference sibling parser {forbidden!r}; "
            f"adding a new lockfile format is a new file, not an edit here."
        )
```

Run `pytest tests/unit/probes/_lockfiles/test_pnpm.py` — fails with `ModuleNotFoundError`. Commit the red marker.

### Green — make it pass

```python
# src/codegenie/probes/_lockfiles/_pnpm.py
"""pnpm-lock.yaml parser — thin ``safe_yaml.load`` wrapper.

The parser shapes nothing and validates no fields — its job is to
translate exactly one exception class (:class:`MalformedYAMLError` ->
:class:`MalformedLockfileError`) while preserving the original on
``__cause__`` so the catch site in :class:`NodeManifestProbe` (S3-05)
constructs the structured ``WarningId`` per ADR-0007 from
``exc.args[0]``.

All other typed exceptions raised by :func:`safe_yaml.load` propagate
unchanged (:class:`SizeCapExceeded`, :class:`DepthCapExceeded`,
:class:`SymlinkRefusedError`). ``FileNotFoundError`` and other
``OSError`` subclasses propagate from the underlying open.

Sources:

- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #9 — interface and ~250 ms p50 budget.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0008-in-process-parse-caps-not-per-probe-sandbox.md`` (ADR-0008)
  ratifies the in-process caps; ``0009-no-new-c-extension-parser-dependencies.md``
  (ADR-0009) pins ``CSafeLoader`` as the only allowed YAML loader.

Phase-0 marker invariant: :class:`MalformedLockfileError` accepts a
single positional message string; the path lives in ``args[0]``, the
cause lives on ``__cause__`` via ``raise ... from cause``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final, TypedDict, cast

from codegenie.errors import MalformedLockfileError, MalformedYAMLError
from codegenie.parsers import safe_yaml

__all__ = ["PnpmLock", "parse"]

PNPM_LOCKFILE_MAX_BYTES: Final[int] = 50 * 1024 * 1024
PNPM_LOCKFILE_MAX_DEPTH: Final[int] = 64


class PnpmLock(TypedDict, total=False):
    """``pnpm-lock.yaml`` shape — ``total=False`` is load-bearing.

    pnpm v6 ships ``lockfileVersion``, ``packages``, ``importers``;
    pnpm v9 adds ``snapshots``. The parser does NOT default missing
    keys — version reconciliation is :class:`NodeManifestProbe`'s job.
    """

    lockfileVersion: str | float
    packages: dict[str, Any]
    importers: dict[str, Any]
    snapshots: dict[str, Any]


def parse(path: Path) -> PnpmLock:
    """Parse a ``pnpm-lock.yaml`` under the 50 MB / depth 64 caps.

    Raises:
        SizeCapExceeded: re-raised unchanged from ``safe_yaml.load``.
        DepthCapExceeded: re-raised unchanged from ``safe_yaml.load``.
        SymlinkRefusedError: re-raised unchanged from ``safe_yaml.load``.
        MalformedLockfileError: translated from ``MalformedYAMLError``;
            the original is preserved on ``__cause__``. The message in
            ``args[0]`` includes ``str(path)`` so downstream
            ``WarningId`` construction can recover the path.
        FileNotFoundError: propagated from the underlying open.
    """
    try:
        raw = safe_yaml.load(
            path,
            max_bytes=PNPM_LOCKFILE_MAX_BYTES,
            max_depth=PNPM_LOCKFILE_MAX_DEPTH,
        )
    except MalformedYAMLError as cause:
        raise MalformedLockfileError(
            f"{path}: {type(cause).__name__}: {cause}"
        ) from cause
    return cast(PnpmLock, raw)
```

```python
# src/codegenie/probes/_lockfiles/__init__.py
"""Lockfile parser family — pnpm, npm, yarn siblings.

Each file in this package is a thin ``safe_*.load`` wrapper that
returns a format-specific TypedDict and translates exactly one
exception class to :class:`MalformedLockfileError`. Sibling parsers do
not import each other; the kernel they share is
:mod:`codegenie.parsers` + :mod:`codegenie.errors`. Adding a new
format (e.g. ``bun.lockb``) is a new file with zero edits to
existing siblings (CLAUDE.md "Extension by addition").

S3-01 ships ``_pnpm``; S3-02 ships ``_npm``; S3-03 ships ``_yarn``.
``__all__`` stays empty here — each sibling exports from its own
module to keep import order unsurprising.
"""

from __future__ import annotations

__all__: list[str] = []
```

### Refactor

- Module constants stay per-file. They are identical across pnpm/npm/yarn (50 MB / depth 64), but Rule 2 ("three similar lines is better than premature abstraction") + CLAUDE.md "Extension by addition" both argue for keeping the constants local: lifting them to `_lockfiles/__init__.py` would create a backward-edge that S3-02/S3-03 inherit silently. The decision to lift is **S3-03's call** once all three are visible (see Notes for the implementer).
- The cast to `PnpmLock` is a runtime no-op. If a future change adds a structural validator, it lives in `NodeManifestProbe`, not here (Note #1).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/_lockfiles/__init__.py` | New file — package marker; module docstring + `__all__: list[str] = []`. |
| `src/codegenie/probes/_lockfiles/_pnpm.py` | New file — `PnpmLock` `TypedDict` + `parse()` wrapper + module constants. |
| `tests/unit/probes/_lockfiles/__init__.py` | New file — test package marker (empty). |
| `tests/unit/probes/_lockfiles/test_pnpm.py` | New file — eight tests, each keyed to one or more ACs. |

## Out of scope

- **`_npm.py` and `_yarn.py`** — separate stories (S3-02, S3-03). S3-03 is the rule-of-three trigger: at that point, evaluate extracting a shared `_translate(path, *, cause)` helper across the three.
- **Native-module catalog cross-reference** — S3-05 (`NodeManifestProbe`).
- **Reshaping `packages` keys (e.g., `/sharp/0.32.5` → `("sharp", "0.32.5")`)** — `NodeManifestProbe` does this; the parser is format-agnostic.
- **Multi-document YAML** — `pnpm-lock.yaml` is single-document; use `safe_yaml.load`, not `load_all`. Multi-doc input is treated as malformed (AC-11).
- **Fixtures with real `bcrypt` / `sharp` entries** — those live in S3-06's `node_pnpm_native/` fixture.
- **Schema validation of `PnpmLock`** — the wrapper is intentionally lenient. Phase 0's `_ProbeOutputValidator` handles output validation; lockfile *input* shape is `NodeManifestProbe`'s concern.

## Notes for the implementer

1. **Don't validate the lockfile schema here.** The thin wrapper exists so `NodeManifestProbe` (S3-05) decides what "valid enough" means per consumer (recipe planner vs. distroless build vs. SBOM). Adding a validator is a one-way ratchet.
2. **`safe_yaml.load` from S1-03 already handles `O_NOFOLLOW`, size pre-check, depth post-walk (id()-memoized).** This module adds zero defense-in-depth — its only job is to translate `MalformedYAMLError` into `MalformedLockfileError` so the probe error catalog stays clean and `NodeManifestProbe` can match one class to one warning ID per ADR-0007.
3. **Marker construction is positional-only.** Phase 0's `test_subclasses_are_markers_only` and S1-01's `test_phase1_subclasses_accept_message_arg_and_expose_args0` parametrize `MalformedLockfileError` and assert `not hasattr(exc, "path")`. Do **not** add a `MalformedLockfileError.__init__(self, *, path, cause)`. The path goes in `args[0]`; the cause goes on `__cause__` via `raise ... from cause`. This is the same pattern S1-02 and S1-03 already settled.
4. **The 60 MB size-cap test uses `os.fstat` monkey-patching, not a 60 MB write.** Writing 60 MB to tmpfs is wasteful and CI-flaky; the cap fires on `os.fstat(fd).st_size > max_bytes` (S1-03 docstring) so monkey-patching `os.fstat` is the load-bearing assertion.
5. **The depth-cap test uses YAML alias amplification, not deep bracket-nesting.** Bracket-nesting (`[[[[...]]]]`) parses to `ScannerError` from pyyaml's tokenizer before the post-parse depth walker ever runs — that surfaces as `MalformedYAMLError`, not `DepthCapExceeded`. The canonical billion-laughs vector is an anchor chain (`&a0`, `&a1 [*a0, *a0]`, …) — the `id()`-memoized walker in `safe_yaml` raises `DepthCapExceeded` on logical depth, which is what arch §"Edge cases" row 1 means by "billion-laughs `pnpm-lock.yaml` → `DepthCapExceeded`."
6. **pnpm version variance**: v6 omits `snapshots`; v9 includes it. `total=False` is the load-bearing choice — defaulting any key here would mask version skew downstream.
7. **Rule of three (deferred extraction).** All three lockfile parsers will share the shape `try: safe_X.load(...) except MalformedXError as cause: raise MalformedLockfileError(f"{path}: ...") from cause`. **Do NOT extract a shared `_translate(path, *, cause)` helper in S3-01.** Wait until S3-03 lands — the third concrete instance is the rule-of-three threshold. At that point, the helper lives in `_lockfiles/__init__.py` or `parsers/_lockfile_io.py`. Premature extraction creates a kernel that S3-02 inherits silently. Reference: CLAUDE.md Rule 2.
8. **Open/Closed at the family level.** Adding a `_bun.py` later must require zero edits to `_pnpm.py`. AC-12's source-introspection test pins this — the test fires immediately if a future implementer adds a sibling-import.
9. **Why `cast(PnpmLock, raw)` and not a runtime validator.** TypedDict is a static-only construct; the cast is a no-op at runtime. If `safe_yaml.load` returned the wrong shape, the failure surfaces at the first key access in `NodeManifestProbe`, not here. This is the deliberate functional-core / imperative-shell split: parse is I/O + translation only; validation is interpretation, which lives with the consumer.
10. **`__all__ = ["PnpmLock", "parse"]`** is intentional — module constants (`PNPM_LOCKFILE_MAX_BYTES`, `PNPM_LOCKFILE_MAX_DEPTH`) are not exported. They are tunable internals; downstream callers that need to know the cap should read it from the module docstring, not import the constant.
