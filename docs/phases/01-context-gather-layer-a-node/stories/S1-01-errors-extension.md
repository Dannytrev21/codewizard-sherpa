# Story S1-01 — Errors extension for parser + catalog typed exceptions

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0007, ADR-0008 (Phase 0 ADR-0008 chokepoint preservation)

## Context

Every Phase 1 parser and the catalog loader raise the same closed set of typed exceptions so probes catch into `ProbeOutput(confidence="low", errors=[<warning_id>])` deterministically. Phase 0 already ships `CodegenieError` plus nine subclasses including `SymlinkRefusedError`; Phase 1 extends that hierarchy with six new subclasses without editing or weakening any Phase 0 type. This story is the prerequisite for every other Step 1 story — parsers, memo, catalogs, raw-artifact-budget code all import these names.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Agentic best practices" → "Error escalation"` — full list of the six new subclasses and the rule that `SymlinkRefusedError` is the Phase-0 type that `O_NOFOLLOW` raises (extended, not duplicated).
  - `../phase-arch-design.md §"Component design" #8` — names which parser raises which typed exception.
  - `../phase-arch-design.md §"Edge cases"` rows 1, 2, 3, 9 — the failure paths each exception encodes.
- **Phase ADRs:**
  - `../ADRs/0007-warnings-id-pattern.md` — ADR-0007 — exception names are paired with `WarningId` IDs (e.g., `package_json.size_cap_exceeded`) that match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
- **Production ADRs:**
  - `../../../production/adrs/` — none directly; this story is local plumbing.
- **Source design:**
  - `../final-design.md §"Failure modes & recovery"` — the row that names `SymlinkRefusedError` as Phase 0's existing type.
- **Existing code:**
  - `src/codegenie/errors.py` — Phase 0 hierarchy; this story extends `__all__` and appends six classes.
  - `tests/unit/test_errors.py` (Phase 0 S2-01) — extended to enumerate the new subclasses in `EXPECTED_SUBCLASSES`.

## Goal

Extend `src/codegenie/errors.py` with six new `CodegenieError` subclasses that carry a violated-cap path and a typed-id, so every parser, lockfile parser, catalog loader, and raw-artifact-budget enforcer can `raise` one without ad-hoc string exceptions.

## Acceptance criteria

- [ ] `src/codegenie/errors.py` exports `SizeCapExceeded`, `DepthCapExceeded`, `MalformedJSONError`, `MalformedYAMLError`, `MalformedLockfileError`, `CatalogLoadError`; each inherits from `CodegenieError`; each is listed in `errors.__all__`.
- [ ] Each new subclass `__init__` accepts `path: Path` and the relevant cap value (or, for `Malformed*` and `CatalogLoadError`, a `detail: str`); the values are stored as attributes (`self.path`, `self.cap`/`self.detail`) and recoverable from the caught instance.
- [ ] `SymlinkRefusedError` (Phase 0) is asserted to be the typed exception `O_NOFOLLOW` raises (no rename, no duplicate; the test pins the contract).
- [ ] `tests/unit/test_errors.py` extends `EXPECTED_SUBCLASSES` to enumerate the six new names; asserts each is in `__all__`; asserts each subclass constructor signature accepts the documented kwargs and stores attributes.
- [ ] Test asserts no behavior on `CodegenieError` itself changed (only an additive extension).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/test_errors.py` all pass on touched files.
- [ ] TDD red test exists, committed, green.

## Implementation outline

1. Extend `tests/unit/test_errors.py` first (red) — add the six names to `EXPECTED_SUBCLASSES`; add a new test that asserts each subclass instance carries the expected attributes after construction.
2. Append the six subclasses to `src/codegenie/errors.py`. Each subclass has a one-line docstring naming the raise site (e.g., `"""Raised by safe_json.load when the file exceeds max_bytes."""`).
3. Each `__init__` is explicit; no inheritance of `Exception.__init__` shortcuts — store the typed attributes, then call `super().__init__(f"{path}: cap={cap}")` (or `: detail`) so `str(exc)` is informative for logging.
4. Append all six names to `__all__`.
5. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/errors.py tests/unit/test_errors.py`, `pytest tests/unit/test_errors.py`.

## TDD plan — red / green / refactor

### Red — failing test first

Test file: `tests/unit/test_errors.py` (extend the existing module from Phase 0 S2-01).

```python
# tests/unit/test_errors.py — extension
from pathlib import Path

import codegenie.errors as e

EXPECTED_SUBCLASSES = {
    # Phase 0
    "ConfigError", "ToolMissingError", "ProbeError", "ProbeTimeoutError",
    "CacheError", "SchemaValidationError", "SecretLikelyFieldNameError",
    "DisallowedSubprocessError", "SymlinkRefusedError",
    # Phase 1 — this story
    "SizeCapExceeded", "DepthCapExceeded",
    "MalformedJSONError", "MalformedYAMLError", "MalformedLockfileError",
    "CatalogLoadError",
}

def test_phase1_subclasses_carry_path_and_cap_attrs():
    # arrange/act: construct each cap-bearing subclass with documented kwargs
    sc = e.SizeCapExceeded(path=Path("/r/package.json"), cap=5_242_880)
    dc = e.DepthCapExceeded(path=Path("/r/pnpm-lock.yaml"), cap=64)
    # assert: attributes are recoverable from the caught exception
    assert sc.path == Path("/r/package.json")
    assert sc.cap == 5_242_880
    assert dc.cap == 64
    # assert: str(exc) carries enough context for structlog
    assert "package.json" in str(sc)

def test_phase1_malformed_subclasses_carry_path_and_detail():
    mj = e.MalformedJSONError(path=Path("/r/package.json"), detail="unterminated string at line 1")
    cl = e.CatalogLoadError(path=Path("/p/catalogs/native_modules.yaml"), detail="duplicate name: bcrypt")
    assert mj.path.name == "package.json"
    assert "duplicate" in cl.detail

def test_symlink_refused_is_phase0_type_unchanged():
    # ADR contract: O_NOFOLLOW raises the existing Phase 0 type; no rename.
    assert e.SymlinkRefusedError.__module__ == "codegenie.errors"
    assert issubclass(e.SymlinkRefusedError, e.CodegenieError)
```

Run; confirm `AttributeError` on the new names. Commit as red marker.

### Green — minimal impl

Append to `src/codegenie/errors.py` (after the Phase 0 subclasses, before `__all__` update):

- `class SizeCapExceeded(CodegenieError)` with `__init__(self, *, path: Path, cap: int)` storing `self.path`, `self.cap`.
- `class DepthCapExceeded(CodegenieError)` — same shape.
- `class MalformedJSONError(CodegenieError)` with `__init__(self, *, path: Path, detail: str)` storing `self.path`, `self.detail`.
- `class MalformedYAMLError(CodegenieError)` — same shape.
- `class MalformedLockfileError(CodegenieError)` — same shape.
- `class CatalogLoadError(CodegenieError)` — same shape.

Update `__all__` to include the six new names. Do not edit any Phase 0 subclass.

### Refactor — clean up

- Each `__init__` builds a single-line `super().__init__(...)` message including path + cap/detail for the logged form.
- Module-level docstring already references `phase-arch-design.md §"Agentic best practices"`; append a short note that Phase 1 added six subclasses with ADR-0007's WarningId pairing convention.
- Confirm `Final` is not needed (these are classes, not constants).
- Confirm `mypy --strict` is clean — the `__init__` signature is keyword-only (`*`); attributes are typed.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/errors.py` | Append six subclasses; extend `__all__` |
| `tests/unit/test_errors.py` | Extend `EXPECTED_SUBCLASSES`; add attribute-shape tests |

## Out of scope

- **Raising these exceptions from parsers / catalog / coordinator** — those raise sites land in S1-02, S1-03, S1-04, S1-05, S1-09 respectively. This story is the type definitions only.
- **Mapping each exception to a `WarningId` string** — that mapping lives in each parser/probe at catch time (S1-02 onward). The exception type does not embed the WarningId.
- **Re-exporting from `codegenie/__init__.py`** — Phase 0 does not re-export `errors`; do not start.
- **Promoting `WarningId` to a typed enum** — deferred to Phase 2 (open question #7).

## Notes for the implementer

- Keep the subclass bodies near-empty: one-line docstring + `__init__` storing typed attributes + `super().__init__(formatted_message)`. Do not add `__str__` overrides — the formatted message in `super().__init__` carries the str() form.
- Keyword-only `__init__` (`def __init__(self, *, path, cap)`) makes call sites explicit at every raise site. Phase 0's `ConfigError` etc. did not enforce this; per Rule 11 (match conventions), prefer keyword-only here because the new types carry **multiple** related fields and positional ordering would drift.
- Do **not** subclass `ValueError` or `OSError`; everything is `CodegenieError` so the CLI's top-level catch (S4-02 from Phase 0) treats them uniformly.
- The `SymlinkRefusedError` is a *Phase 0* type. Do not duplicate it under `parsers/`. The depth+size walker in `safe_json.load` (S1-02) re-raises it from `os.open(..., O_NOFOLLOW)`.
- The cap value stored on `SizeCapExceeded` / `DepthCapExceeded` is the **violated** cap, not the **observed** size/depth. Storing the violated cap makes the exception's structlog rendering match the configuration that caused the failure (useful in Phase 14 when caps become per-probe overridable).
- This file is **not** in `CODEOWNERS`-routed paths the way `probes/base.py` is — `errors.py` is allowed to grow by addition; future contributors should not need an ADR to add a new subclass. The Phase-0 contract that's frozen is `Probe`, not `CodegenieError`.
