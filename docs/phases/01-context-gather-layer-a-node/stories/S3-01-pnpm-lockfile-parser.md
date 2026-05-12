# Story S3-01 — `_pnpm` lockfile parser

**Step:** Step 3 — Ship `NodeManifestProbe` and the three lockfile parsers
**Status:** Ready
**Effort:** S
**Depends on:** S1-05 (catalogs + `safe_yaml` already loaded by it transitively)
**ADRs honored:** ADR-0008 (in-process caps, not per-probe sandbox), ADR-0009 (no new C-extension parser deps)

## Context

`pnpm-lock.yaml` is the most common modern Node lockfile and is the parse-cost hot spot of `NodeManifestProbe` (~250 ms p50 on a typical 5 MB file). This story ships the thinnest possible adapter on top of `safe_yaml.load`: read the lockfile under the standard 50 MB + depth 64 caps, return a typed dict, surface the typed exception set unchanged. No interpretation of fields, no flattening of the `packages:` tree — that's `NodeManifestProbe`'s job in S3-05. Keeping this module thin is the whole point: every lockfile format gets the same defensive parse, and the catalog cross-reference logic stays in one place.

This is the smallest of the three lockfile parsers — straight `safe_yaml.load` + a `TypedDict` cast. It exists separately because pnpm/npm/yarn have format-specific *callers* in `NodeManifestProbe`, even though the parse layer is one-liner-thin.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #9 Lockfile parsers` — interface, `safe_yaml.load` wrapper, ~250 ms p50 budget.
  - `../phase-arch-design.md §"Component design" #4 NodeManifestProbe` — the caller; lockfile is in `declared_inputs`.
  - `../phase-arch-design.md §"Edge cases"` row 1 — billion-laughs `pnpm-lock.yaml` → `DepthCapExceeded`.
  - `../phase-arch-design.md §"Component design" #8 Safe-parse helpers` — the load contract `safe_yaml.load(path, *, max_bytes, max_depth=64)` raises.
- **Phase ADRs:**
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — why the size+depth caps are the parser's job, not a sandbox's.
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — `pyyaml.CSafeLoader` only; no `ruamel.yaml`.
- **Source design:**
  - `../final-design.md §"Components" #4` — three sibling parsers under `_lockfiles/`.
  - `../High-level-impl.md §"Step 3"` — first deliverable bullet.
- **Existing code (Phase 0 + Step 1):**
  - `src/codegenie/parsers/safe_yaml.py` — `load(path, *, max_bytes, max_depth=64)` from S1-03.
  - `src/codegenie/errors.py` — `SizeCapExceeded`, `DepthCapExceeded`, `MalformedYAMLError`, `MalformedLockfileError`, `SymlinkRefusedError` from S1-01.

## Goal

Implement `src/codegenie/probes/_lockfiles/_pnpm.py` as a thin `safe_yaml.load` wrapper returning a `PnpmLock` `TypedDict`, so `NodeManifestProbe` can call `_pnpm.parse(path)` and receive a parsed-and-capped dict or a typed exception.

## Acceptance criteria

- [ ] `src/codegenie/probes/_lockfiles/__init__.py` exists (may be empty or re-export `PnpmLock`, `NpmLock`, `YarnLock` once the siblings land — see Out of scope).
- [ ] `src/codegenie/probes/_lockfiles/_pnpm.py` exports `parse(path: Path) -> PnpmLock` and a `PnpmLock` `TypedDict`.
- [ ] `parse(path)` calls `safe_yaml.load(path, max_bytes=50 * 1024 * 1024, max_depth=64)` (50 MB cap, depth 64 per `phase-arch-design.md §"Component design" #9`).
- [ ] `parse(path)` re-raises `SizeCapExceeded`, `DepthCapExceeded`, `SymlinkRefusedError` unchanged; catches `MalformedYAMLError` and re-raises as `MalformedLockfileError` with the file path attached.
- [ ] `PnpmLock` `TypedDict` declares at minimum `lockfileVersion: str | float`, `packages: dict[str, Any]`, `importers: dict[str, Any]` as `total=False` (real pnpm lockfiles have all three at the top level for `lockfileVersion: '6.0'+`).
- [ ] TDD red test exists, was committed red, now green; all four failure-path tests assert the **specific** typed exception class.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict src/codegenie/probes/_lockfiles/_pnpm.py`, and the unit test all pass.

## Implementation outline

1. Create `src/codegenie/probes/_lockfiles/__init__.py` (empty package marker).
2. Create `src/codegenie/probes/_lockfiles/_pnpm.py`:
   - Define `PnpmLock(TypedDict, total=False)` with `lockfileVersion`, `packages`, `importers`, `snapshots` (pnpm v9).
   - Define module constants: `PNPM_LOCKFILE_MAX_BYTES = 50 * 1024 * 1024`, `PNPM_LOCKFILE_MAX_DEPTH = 64`.
   - Implement `parse(path: Path) -> PnpmLock` that calls `safe_yaml.load(path, max_bytes=PNPM_LOCKFILE_MAX_BYTES, max_depth=PNPM_LOCKFILE_MAX_DEPTH)`, catches `MalformedYAMLError`, re-raises as `MalformedLockfileError(path=path, cause=e)`.
   - Cast the returned dict to `PnpmLock` via `cast(PnpmLock, ...)` (no runtime validation — that's `NodeManifestProbe`'s job).
3. Write the four unit tests (see TDD plan).
4. Confirm `MalformedLockfileError` carries `path` per S1-01's error-extension contract; add the constructor argument if missing (surface in PR body if so).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/_lockfiles/test_pnpm.py`.

```python
# tests/unit/probes/_lockfiles/test_pnpm.py
from pathlib import Path
import pytest
from codegenie.errors import (
    SizeCapExceeded, DepthCapExceeded, MalformedLockfileError, SymlinkRefusedError,
)
from codegenie.probes._lockfiles import _pnpm

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "_pnpm"

def test_parse_happy_path_returns_typed_dict(tmp_path: Path):
    # arrange: minimal valid pnpm-lock.yaml
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("lockfileVersion: '9.0'\npackages: {}\nimporters: {}\n")
    # act
    result = _pnpm.parse(lockfile)
    # assert: shape (not value-equality — that's NodeManifestProbe's job)
    assert result["lockfileVersion"] == "9.0"
    assert result["packages"] == {}

def test_parse_oversized_file_raises_size_cap(tmp_path: Path):
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_bytes(b"a: b\n" * (60 * 1024 * 1024 // 5))  # ~60 MB
    with pytest.raises(SizeCapExceeded) as exc:
        _pnpm.parse(lockfile)
    assert exc.value.path == lockfile

def test_parse_billion_laughs_raises_depth_cap(tmp_path: Path):
    lockfile = tmp_path / "pnpm-lock.yaml"
    # 70 levels of nesting via YAML anchors would exceed depth 64
    lockfile.write_text("a: " + "[" * 70 + "1" + "]" * 70 + "\n")
    with pytest.raises(DepthCapExceeded):
        _pnpm.parse(lockfile)

def test_parse_malformed_yaml_raises_malformed_lockfile(tmp_path: Path):
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("packages: {unclosed\n")
    with pytest.raises(MalformedLockfileError) as exc:
        _pnpm.parse(lockfile)
    assert exc.value.path == lockfile
```

Run `pytest tests/unit/probes/_lockfiles/test_pnpm.py` — fails with `ModuleNotFoundError`. Commit the red marker.

### Green — make it pass

```python
# src/codegenie/probes/_lockfiles/_pnpm.py
from pathlib import Path
from typing import Any, TypedDict, cast

from codegenie.errors import MalformedYAMLError, MalformedLockfileError
from codegenie.parsers import safe_yaml

PNPM_LOCKFILE_MAX_BYTES = 50 * 1024 * 1024
PNPM_LOCKFILE_MAX_DEPTH = 64


class PnpmLock(TypedDict, total=False):
    lockfileVersion: str | float
    packages: dict[str, Any]
    importers: dict[str, Any]
    snapshots: dict[str, Any]


def parse(path: Path) -> PnpmLock:
    try:
        raw = safe_yaml.load(
            path, max_bytes=PNPM_LOCKFILE_MAX_BYTES, max_depth=PNPM_LOCKFILE_MAX_DEPTH
        )
    except MalformedYAMLError as e:
        raise MalformedLockfileError(path=path, cause=e) from e
    return cast(PnpmLock, raw)
```

### Refactor

- Move the two cap constants into `src/codegenie/probes/_lockfiles/__init__.py` only if S3-02 and S3-03 share identical values (they do — 50 MB / depth 64) AND share imports cleanly. Otherwise leave them per-file; premature sharing is worse than duplication.
- The `total=False` on `PnpmLock` is deliberate — pnpm v6 vs v9 disagree on which fields are present; the probe defensive-checks.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/_lockfiles/__init__.py` | New file — package marker; re-exports added incrementally by S3-02, S3-03. |
| `src/codegenie/probes/_lockfiles/_pnpm.py` | New file — `PnpmLock` `TypedDict` + `parse()` wrapper. |
| `tests/unit/probes/_lockfiles/__init__.py` | New file — test package marker. |
| `tests/unit/probes/_lockfiles/test_pnpm.py` | New file — four-path test (happy + 3 typed failures). |

## Out of scope

- **`_npm.py` and `_yarn.py`** — separate stories (S3-02, S3-03).
- **Native-module catalog cross-reference** — S3-05 (`NodeManifestProbe`).
- **Reshaping `packages` keys (e.g., `/sharp/0.32.5` → `("sharp", "0.32.5")`)** — `NodeManifestProbe` does this; the parser is format-agnostic.
- **Multi-document YAML** — `pnpm-lock.yaml` is single-document; use `safe_yaml.load`, not `load_all`.
- **Fixtures with real `bcrypt` / `sharp` entries** — those live in S3-06's `node_pnpm_native/` fixture.

## Notes for the implementer

- Don't validate the lockfile schema here. The point of the thin wrapper is that `NodeManifestProbe` (S3-05) gets to decide what "valid enough" means per consumer use case — recipe planner vs. distroless build vs. SBOM.
- `safe_yaml.load` from S1-03 already handles `O_NOFOLLOW`, size pre-check, depth post-walk; this module adds zero defense-in-depth — its job is to translate one exception (`MalformedYAMLError`) into a more specific one (`MalformedLockfileError`) so the probe error catalog stays clean.
- If `MalformedLockfileError.__init__` doesn't accept `path` + `cause` keyword args per S1-01's contract, surface that as a blocker in this PR — don't paper over it locally.
- The 60 MB size-cap test uses bytes (not parsed structure) so it triggers the pre-parse size check on the fd, not the post-parse depth walker; that's the correct failure path for an oversized real-world lockfile.
- Do not add a `validate_pnpm_lock(d)` schema-validator function here even as a convenience — Phase 0's `_ProbeOutputValidator` handles output validation; lockfile *input* shape is the probe's concern.
- pnpm v6 changed `dependencies`/`devDependencies` key shapes inside `packages:`; v9 introduced `snapshots:`. Don't try to normalize across versions in this module — the probe handles it.
