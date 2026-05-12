# Story S3-02 — `_npm` lockfile parser

**Step:** Step 3 — Ship `NodeManifestProbe` and the three lockfile parsers
**Status:** Ready
**Effort:** S
**Depends on:** S1-02 (`safe_json`), S1-03 (`safe_yaml` — for symmetry with the sibling parsers' shared error-translation pattern)
**ADRs honored:** ADR-0008 (in-process caps), ADR-0009 (no new C-extension parser deps — stdlib `json` only)

## Context

`package-lock.json` is npm's lockfile and the second of three sibling parsers feeding `NodeManifestProbe`. The shape mirrors `_pnpm.py` exactly — a thin `safe_json.load` wrapper returning a `TypedDict`, with the same size + depth caps (50 MB / depth 64) and the same exception-translation pattern (`MalformedJSONError` → `MalformedLockfileError`). The only structural difference vs. S3-01 is the parser entry point (`safe_json.load` instead of `safe_yaml.load`).

npm's lockfile has had three on-disk shapes (`lockfileVersion` 1, 2, 3); v2+ is much larger than pnpm equivalents because npm stores both `packages` (modern flat tree) and `dependencies` (legacy nested tree) for backward compatibility. That's why the 50 MB cap matters even more here than for pnpm.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #9 Lockfile parsers` — interface, `safe_json.load` wrapper, ~100 ms p50 budget.
  - `../phase-arch-design.md §"Component design" #4 NodeManifestProbe` — caller; `package-lock.json` is in `declared_inputs`.
  - `../phase-arch-design.md §"Component design" #8 Safe-parse helpers` — `safe_json.load(path, *, max_bytes, max_depth=64)`.
- **Phase ADRs:**
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — caps live in the parser; this module is one line of integration.
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — stdlib `json` only; no `orjson`.
- **Source design:**
  - `../final-design.md §"Components" #4` — three sibling parsers under `_lockfiles/`.
  - `../High-level-impl.md §"Step 3"` — `_npm.py` deliverable.
- **Existing code:**
  - `src/codegenie/parsers/safe_json.py` — from S1-02.
  - `src/codegenie/errors.py` — `SizeCapExceeded`, `DepthCapExceeded`, `MalformedJSONError`, `MalformedLockfileError`, `SymlinkRefusedError`.
  - `src/codegenie/probes/_lockfiles/_pnpm.py` — already on disk from S3-01; **mirror the structure**.

## Goal

Implement `src/codegenie/probes/_lockfiles/_npm.py` as a thin `safe_json.load` wrapper returning an `NpmLock` `TypedDict`, structurally identical to `_pnpm.py` except for the parser entry point.

## Acceptance criteria

- [ ] `src/codegenie/probes/_lockfiles/_npm.py` exports `parse(path: Path) -> NpmLock` and an `NpmLock` `TypedDict`.
- [ ] `parse(path)` calls `safe_json.load(path, max_bytes=50 * 1024 * 1024, max_depth=64)`.
- [ ] `parse(path)` re-raises `SizeCapExceeded`, `DepthCapExceeded`, `SymlinkRefusedError` unchanged; catches `MalformedJSONError` and re-raises as `MalformedLockfileError(path=path, cause=e)`.
- [ ] `NpmLock` `TypedDict` declares (at minimum, `total=False`): `name: str`, `version: str`, `lockfileVersion: int`, `requires: bool`, `packages: dict[str, Any]`, `dependencies: dict[str, Any]` — covering lockfileVersion 1/2/3 fields.
- [ ] TDD red test exists, was committed red, now green; happy path + the three failure paths (size cap, depth cap, malformed) each assert the **specific** typed exception class.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict`, and the unit test all pass.
- [ ] `src/codegenie/probes/_lockfiles/__init__.py` re-exports `NpmLock` (additive — don't break S3-01's `PnpmLock` re-export).

## Implementation outline

1. Mirror `_pnpm.py`'s structure verbatim — same constants, same exception-translation, same `cast`-only return path. Substitute `safe_json` for `safe_yaml` and `MalformedJSONError` for `MalformedYAMLError`.
2. Define `NpmLock(TypedDict, total=False)` with the lockfileVersion 1/2/3 union of fields (`name`, `version`, `lockfileVersion`, `requires`, `packages`, `dependencies`).
3. Update `src/codegenie/probes/_lockfiles/__init__.py` to additively re-export `NpmLock` (alongside S3-01's `PnpmLock`).
4. Write the four-path unit test mirroring `test_pnpm.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/_lockfiles/test_npm.py`.

```python
# tests/unit/probes/_lockfiles/test_npm.py
from pathlib import Path
import pytest
from codegenie.errors import (
    SizeCapExceeded, DepthCapExceeded, MalformedLockfileError, SymlinkRefusedError,
)
from codegenie.probes._lockfiles import _npm

def test_parse_happy_path_returns_typed_dict(tmp_path: Path):
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text(
        '{"name":"x","version":"1.0.0","lockfileVersion":3,"packages":{"":{}}}'
    )
    result = _npm.parse(lockfile)
    assert result["lockfileVersion"] == 3
    assert result["name"] == "x"

def test_parse_oversized_file_raises_size_cap(tmp_path: Path):
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_bytes(b'{"x":"' + b"a" * (60 * 1024 * 1024) + b'"}')
    with pytest.raises(SizeCapExceeded) as exc:
        _npm.parse(lockfile)
    assert exc.value.path == lockfile

def test_parse_deep_nesting_raises_depth_cap(tmp_path: Path):
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text("{" + '"a":{' * 70 + "}" * 71)
    with pytest.raises(DepthCapExceeded):
        _npm.parse(lockfile)

def test_parse_malformed_json_raises_malformed_lockfile(tmp_path: Path):
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"unterminated')
    with pytest.raises(MalformedLockfileError) as exc:
        _npm.parse(lockfile)
    assert exc.value.path == lockfile
```

Confirm `ModuleNotFoundError`. Commit red.

### Green — make it pass

```python
# src/codegenie/probes/_lockfiles/_npm.py
from pathlib import Path
from typing import Any, TypedDict, cast

from codegenie.errors import MalformedJSONError, MalformedLockfileError
from codegenie.parsers import safe_json

NPM_LOCKFILE_MAX_BYTES = 50 * 1024 * 1024
NPM_LOCKFILE_MAX_DEPTH = 64


class NpmLock(TypedDict, total=False):
    name: str
    version: str
    lockfileVersion: int
    requires: bool
    packages: dict[str, Any]
    dependencies: dict[str, Any]


def parse(path: Path) -> NpmLock:
    try:
        raw = safe_json.load(
            path, max_bytes=NPM_LOCKFILE_MAX_BYTES, max_depth=NPM_LOCKFILE_MAX_DEPTH
        )
    except MalformedJSONError as e:
        raise MalformedLockfileError(path=path, cause=e) from e
    return cast(NpmLock, raw)
```

### Refactor

- If `_pnpm.py` and `_npm.py` share the constants `50 * 1024 * 1024` and `64` literally, consider extracting them to `src/codegenie/probes/_lockfiles/__init__.py` as `LOCKFILE_MAX_BYTES` / `LOCKFILE_MAX_DEPTH` constants. **Only do this** if S3-03's `_yarn.py` also uses identical values (it does — same cap policy) AND the consolidation is genuinely a one-time edit. Otherwise leave the per-file constants — duplication of two integers beats premature sharing.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/_lockfiles/_npm.py` | New file — `NpmLock` `TypedDict` + `parse()` wrapper. |
| `src/codegenie/probes/_lockfiles/__init__.py` | Edit — additive `NpmLock` re-export. |
| `tests/unit/probes/_lockfiles/test_npm.py` | New file — four-path test mirroring `test_pnpm.py`. |

## Out of scope

- **`_yarn.py`** — S3-03 (the ADR-0003 land-time decision lives there, not here).
- **lockfileVersion 1 ↔ 3 normalization** — `NodeManifestProbe` reconciles; the parser is shape-faithful.
- **Resolving the `node_modules/` paths inside `packages:`** — S3-05 (probe).
- **Validating `lockfileVersion` is one of {1, 2, 3}** — defer to S3-05 (probe records `confidence: low` on unknown versions; the parser is permissive).
- **Fixtures with real native modules** — S3-06.

## Notes for the implementer

- The depth-cap test fixture uses 70 levels of `{"a":{...}}` nesting — verify locally that 70 exceeds the default depth 64 cap from `safe_json.load`. If 70 is too close to the boundary for any reason (e.g., depth-walker counts differently than the test author expects), bump to 100. Surface the chosen value in PR body.
- The size-cap test uses a 60 MB byte payload — verify the pre-parse size check on the fd fires before `_json.c` allocates. The whole point of S1-02's pre-parse check is to never `json.loads()` a 60 MB string; if the test passes only because `_json.c` blows up cleanly, that's a bug in `safe_json`, not this module.
- `MalformedJSONError` from S1-01 carries `path` + `cause` per the typed-exception extension contract; if the constructor signature drifted, surface in PR body.
- **Do not** add a `lockfileVersion` switch here. lockfileVersion 1 puts `dependencies` at the top; v2 has both `dependencies` and `packages`; v3 drops `dependencies`. `NodeManifestProbe` reads whichever is present — the parser doesn't gate.
- The `cast(NpmLock, raw)` is a type-system convenience only; mypy gets `NpmLock` semantics, runtime gets raw dict. That's the whole TypedDict contract.
- Symmetry with `_pnpm.py` is load-bearing for reviewability — if you diverge from the structure (e.g., adding a private `_translate_exception` helper here but not in `_pnpm.py`), back-port or revert. Three parsers should diff like three lines.
