# Story S1-01 — Errors extension for parser + catalog typed markers

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready (hardened by phase-story-validator)
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0007

## Validation notes (phase-story-validator, 2026-05-13)

This story was hardened by the validator from its initial draft. Key changes:

- **Markers-only invariant preserved.** Original draft proposed custom `__init__(self, *, path, cap)` on every new subclass — that directly violated Phase 0's `test_subclasses_are_markers_only` invariant in `tests/unit/test_errors.py` (`cls.__init__ is e.CodegenieError.__init__`, no class attributes). The hardened story keeps the six new subclasses as **markers** (Phase 0 module-docstring contract). Path / cap / detail are encoded in the **formatted message string** the raise site passes positionally to `CodegenieError.__init__` (which inherits `Exception.__init__` → `.args[0]`). Probes that catch translate to a `WarningId` at catch time (arch §"Error escalation" — *"each is caught by the calling probe into `ProbeOutput.errors` with a structured WarningId"*), so machine-recoverable attributes are not required on the exception instance.
- **Phase 0 inventory corrected from 9 → 11 subclasses.** Original draft listed nine Phase 0 subclasses (`ConfigError`, `ToolMissingError`, `ProbeError`, `ProbeTimeoutError`, `CacheError`, `SchemaValidationError`, `SecretLikelyFieldNameError`, `DisallowedSubprocessError`, `SymlinkRefusedError`). Phase 0 actually ships **eleven** (adds `ProbeBudgetExceeded` from S3-05 and `AllProbesFailedError` from S4-02). The hardened `EXPECTED_SUBCLASSES` totals **17** (11 Phase 0 + 6 new).
- **`DOCUMENTED_MODULE_SLUGS` extended.** Phase 0's slug allowlist (`exec`, `cache`, `sanitizer`, `validator`, `writer`, `coordinator`, `config`, `tool_check`, `schema`) does not cover the new raise sites in `parsers/` and `catalogs/`. The hardened story extends the set to add `parsers` and `catalogs` and asserts every new subclass docstring names its slug.
- **ADR-0008 citation dropped.** Phase 0 ADR-0008 is the *output sanitizer two-pass chokepoint* ADR — it governs `output/sanitizer.py`, not `errors.py`. The honored ADR is ADR-0007 only.
- **Tests strengthened against six concrete mutations.** Parametrized construction for all six new subclasses (Malformed{YAML,Lockfile} were untested in the draft); explicit `pytest.raises(TypeError)` for any kwargs-only positional misuse is **dropped** (markers don't enforce kwargs); `caught.args[0]` recovery test added; root-`CodegenieError.__init__` untouched test added; negative-attribute test (`hasattr(..., "warning_id") is False`) added; `CatalogLoadError` carries a docstring fatality marker per arch §Edge cases #9.

Full report: `_validation/S1-01-errors-extension.md`.

## Context

Every Phase 1 parser and the catalog loader raise the same closed set of typed **marker** exceptions so probes catch into `ProbeOutput(confidence="low", errors=[<warning_id>])` deterministically. Phase 0 already ships `CodegenieError` plus **eleven** subclasses (markers only — no `__init__`, no class attributes; see `src/codegenie/errors.py` module docstring and `tests/unit/test_errors.py::test_subclasses_are_markers_only`); Phase 1 extends that hierarchy with six new marker subclasses without weakening the markers-only invariant. This story is the prerequisite for every other Step 1 story — parsers, memo, catalogs, raw-artifact-budget code all import these names.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Agentic best practices" → "Error escalation"` — full list of the six new subclasses and the rule that `SymlinkRefusedError` is the Phase-0 type that `O_NOFOLLOW` raises (extended raise site, not duplicated class).
  - `../phase-arch-design.md §"Component design" #8` — names which parser raises which typed exception.
  - `../phase-arch-design.md §"Edge cases"` rows 1, 2, 3, 9 — the failure paths each exception encodes. Row 9 (`CatalogLoadError` at module import) is a **hard-fail at CLI startup**, not a soft-fail into `ProbeOutput.errors`.
- **Phase ADRs:**
  - `../ADRs/0007-warnings-id-pattern.md` — ADR-0007 — exception **catch sites** (not the exception class itself) produce `WarningId` IDs matching `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. The exception type does **not** embed a WarningId.
- **Production ADRs:**
  - `../../../production/adrs/` — none directly; this story is local plumbing.
- **Source design:**
  - `../final-design.md §"Failure modes & recovery"` — pairs each failure with its typed marker.
- **Existing code (Phase 0 contract — DO NOT WEAKEN):**
  - `src/codegenie/errors.py` — Phase 0 hierarchy. Module docstring: *"Subclasses carry no `__init__`, no `__str__`, no class attributes — they are markers only. Adding behavior is a separate decision (Rule 2, Rule 3)."*
  - `tests/unit/test_errors.py` (Phase 0 S2-01) — load-bearing tests this story extends without weakening: `test_codegenie_error_root_is_distinct_subclass_of_exception`, `test_all_closure_pins_public_surface`, `test_every_subclass_directly_inherits_codegenie_error`, `test_every_subclass_has_raise_site_docstring`, `test_subclasses_are_markers_only`.

## Goal

Extend `src/codegenie/errors.py` with **six new marker subclasses** of `CodegenieError` — `SizeCapExceeded`, `DepthCapExceeded`, `MalformedJSONError`, `MalformedYAMLError`, `MalformedLockfileError`, `CatalogLoadError` — so every parser, lockfile parser, catalog loader, and raw-artifact-budget enforcer can `raise <Marker>(f"{path}: cap={cap}")` (or `: detail={detail}`) without ad-hoc string-typed `Exception`s. The new subclasses are markers (no `__init__`, no class attributes) — identical shape to the eleven Phase 0 subclasses. The path/cap/detail are encoded in the `args[0]` message string passed positionally to `CodegenieError.__init__`; probes recover semantics from the **catch context**, not from instance attributes.

## Acceptance criteria

- [ ] **AC-1 (six new names, in `__all__`, inherit `CodegenieError` directly).** `src/codegenie/errors.py` exports `SizeCapExceeded`, `DepthCapExceeded`, `MalformedJSONError`, `MalformedYAMLError`, `MalformedLockfileError`, `CatalogLoadError`. Each is listed in `errors.__all__`. Each `cls.__mro__[1] is CodegenieError` (direct child, asserted by `test_every_subclass_directly_inherits_codegenie_error`).
- [ ] **AC-2 (markers-only invariant preserved across all 17 subclasses).** Each new subclass satisfies `cls.__init__ is CodegenieError.__init__` AND `set(cls.__dict__.keys()) <= MARKER_ALLOWED_DICT_KEYS`. The full `EXPECTED_SUBCLASSES` set in `tests/unit/test_errors.py` enumerates **all 17** names (11 Phase 0 + 6 Phase 1) and continues to pass `test_subclasses_are_markers_only` unchanged.
- [ ] **AC-3 (Phase 0 `EXPECTED_SUBCLASSES` count corrected).** The `EXPECTED_SUBCLASSES` set in `tests/unit/test_errors.py` includes `ProbeBudgetExceeded` and `AllProbesFailedError` (already in Phase 0's `__all__`) — i.e., the test now lists all 11 Phase 0 names, not the stale "nine" the original story draft assumed. `test_all_closure_pins_public_surface` continues to pass.
- [ ] **AC-4 (`DOCUMENTED_MODULE_SLUGS` extended additively).** `DOCUMENTED_MODULE_SLUGS` in `tests/unit/test_errors.py` is extended by union with `{"parsers", "catalogs"}` (no Phase 0 slug removed). Each new subclass docstring contains its slug (`parsers` for the five parser/lockfile types; `catalogs` for `CatalogLoadError`). `test_every_subclass_has_raise_site_docstring` continues to pass for all 17 subclasses.
- [ ] **AC-5 (raise-site documentation in each docstring).** Each new subclass declares a `>= 10`-char docstring naming the raise site verbatim from arch design — e.g., `SizeCapExceeded.__doc__` mentions *"parsers"* and the pre-parse size cap; `MalformedJSONError.__doc__` mentions *"parsers"* and `safe_json.load`; `CatalogLoadError.__doc__` mentions *"catalogs"* and the words *"hard fail at CLI startup"* (arch §Edge cases row 9 — load-bearing-invariant).
- [ ] **AC-6 (no instance state; `args[0]` carries the message).** Construction with a single positional message arg works (`SizeCapExceeded(f"{path}: cap={cap}")`); `caught.args[0]` recovers the message verbatim; instance has **no** `.path`, `.cap`, `.detail`, or `.warning_id` attribute (`hasattr` returns `False`). Asserted parametrically across all six new types.
- [ ] **AC-7 (root `CodegenieError` unchanged).** `CodegenieError.__init__ is Exception.__init__`; no new class attributes on the root; `test_codegenie_error_root_is_distinct_subclass_of_exception` continues to pass.
- [ ] **AC-8 (`SymlinkRefusedError` class identity preserved).** `SymlinkRefusedError` is **not** redefined, renamed, or shadowed in `errors.py`; the Phase 0 class object remains the one referenced via `errors.SymlinkRefusedError`; `id(errors.SymlinkRefusedError)` matches the class declared in Phase 0's module (asserted by class-source-line check). Out of scope: any test that the parser actually raises it on `O_NOFOLLOW` — that's S1-02's contract.
- [ ] **AC-9 (red → green → refactor evidence).** A failing test commit exists naming the six new subclasses before the source file is touched; `git log` shows the red commit precedes the green commit; both reference S1-01.
- [ ] **AC-10 (toolchain clean on touched files only).** `ruff check`, `ruff format --check`, `mypy --strict` pass on `src/codegenie/errors.py` and `tests/unit/test_errors.py`; `pytest tests/unit/test_errors.py` is green (all 17 subclasses verified by every parametrized test).

## Implementation outline

1. **Red.** Extend `tests/unit/test_errors.py` first:
   - Add `ProbeBudgetExceeded` and `AllProbesFailedError` to `EXPECTED_SUBCLASSES` (correct Phase 0 inventory).
   - Add the six new names: `SizeCapExceeded`, `DepthCapExceeded`, `MalformedJSONError`, `MalformedYAMLError`, `MalformedLockfileError`, `CatalogLoadError`.
   - Extend `DOCUMENTED_MODULE_SLUGS` by union with `{"parsers", "catalogs"}` (do not remove Phase 0 slugs).
   - Add a parametrized construction test (`test_phase1_subclasses_accept_message_arg_and_expose_args0`) over the six new types that constructs each with a single positional message, asserts `args[0]` round-trip, and asserts `hasattr(exc, "path") is False` and `hasattr(exc, "cap") is False` and `hasattr(exc, "detail") is False` and `hasattr(exc, "warning_id") is False`.
   - Add a `test_caught_exception_message_recoverable_via_args0` that `try: raise SizeCapExceeded("…"); except CodegenieError as caught: assert caught.args[0] == "…"`.
   - Add `test_symlink_refused_class_identity_preserved` asserting `errors.SymlinkRefusedError.__module__ == "codegenie.errors"` and that the class is the same `id()` as `errors.__dict__["SymlinkRefusedError"]` (guards against accidental shadow imports).
   - Add `test_catalog_load_error_doc_marks_hard_fail` asserting the substring *"hard fail"* appears in `CatalogLoadError.__doc__` (case-insensitive).
   - Run; confirm `AttributeError` on the six new names. Commit as red marker (AC-9).
2. **Green.** Append the six classes to `src/codegenie/errors.py`, each as a bare marker:
   ```python
   class SizeCapExceeded(CodegenieError):
       """Raised by parsers (safe_json / safe_yaml) when the pre-parse file size exceeds the configured cap."""
   ```
   Same shape for the other five: `DepthCapExceeded`, `MalformedJSONError`, `MalformedYAMLError`, `MalformedLockfileError`, `CatalogLoadError`. Each docstring names its slug (`parsers` or `catalogs`) plus the raise site verbatim from arch design. `CatalogLoadError.__doc__` includes *"hard fail at CLI startup"*.
3. Append all six names to `__all__`.
4. **Refactor.**
   - Confirm no `__init__`, no `__str__`, no class attributes — `cls.__dict__` should contain only `__module__`, `__qualname__`, `__doc__` (plus Python 3.13's compiler-injected entries already in `MARKER_ALLOWED_DICT_KEYS`).
   - Module-level docstring: append a one-line note that Phase 1 added six marker subclasses for `parsers/` and `catalogs/` raise sites, paired via ADR-0007's `WarningId` pattern **at catch sites** (not on the class).
5. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/errors.py tests/unit/test_errors.py`, `pytest tests/unit/test_errors.py -v` (AC-10).

## TDD plan — red / green / refactor

### Red — failing tests first

Test file: `tests/unit/test_errors.py` (extend the existing module from Phase 0 S2-01; do not weaken any existing assertion).

```python
# tests/unit/test_errors.py — extension
from __future__ import annotations

import pytest
import codegenie.errors as e

# AC-2, AC-3 — full 17-name inventory (11 Phase 0 + 6 Phase 1)
EXPECTED_SUBCLASSES = {
    # Phase 0 — eleven (corrected count; the prior draft of this story listed 9)
    "ConfigError", "ToolMissingError", "ProbeError", "ProbeTimeoutError",
    "ProbeBudgetExceeded", "CacheError", "SchemaValidationError",
    "SecretLikelyFieldNameError", "DisallowedSubprocessError",
    "SymlinkRefusedError", "AllProbesFailedError",
    # Phase 1 — six new markers (this story)
    "SizeCapExceeded", "DepthCapExceeded",
    "MalformedJSONError", "MalformedYAMLError", "MalformedLockfileError",
    "CatalogLoadError",
}

# AC-4 — extended additively; Phase 0 entries unchanged
DOCUMENTED_MODULE_SLUGS = {
    "exec", "cache", "sanitizer", "validator", "writer", "coordinator",
    "config", "tool_check", "schema",
    "parsers", "catalogs",   # Phase 1 additions
}

PHASE1_NEW = {
    "SizeCapExceeded", "DepthCapExceeded",
    "MalformedJSONError", "MalformedYAMLError", "MalformedLockfileError",
    "CatalogLoadError",
}


# AC-6 — every Phase-1 marker accepts a single positional message string,
# round-trips it via .args[0], and exposes NO instance attributes (markers only).
@pytest.mark.parametrize("name", sorted(PHASE1_NEW))
def test_phase1_subclasses_accept_message_arg_and_expose_args0(name: str) -> None:
    cls = getattr(e, name)
    msg = f"/repo/file.ext: cap=64 detail=for {name}"
    exc = cls(msg)
    # message round-trips via Exception.args (Phase 0 inherited shape)
    assert exc.args == (msg,)
    assert exc.args[0] == msg
    assert str(exc) == msg  # Exception.__str__ delegates to args[0] when len==1
    # Markers expose NO instance state — these are deliberate negatives
    for forbidden_attr in ("path", "cap", "detail", "warning_id"):
        assert not hasattr(exc, forbidden_attr), (
            f"{name} must remain a marker; instance must not carry "
            f"{forbidden_attr!r}. Path/cap/detail live in the message."
        )


# AC-6 — caught instance still exposes args[0]; semantics live in catch context.
def test_caught_phase1_exception_recovers_via_args0() -> None:
    with pytest.raises(e.CodegenieError) as exc_info:
        raise e.SizeCapExceeded("/r/package.json: cap=5242880")
    assert exc_info.value.args[0] == "/r/package.json: cap=5242880"
    assert isinstance(exc_info.value, e.SizeCapExceeded)
    assert isinstance(exc_info.value, e.CodegenieError)


# AC-7 — root unchanged
def test_codegenie_error_root_init_unchanged() -> None:
    assert e.CodegenieError.__init__ is Exception.__init__


# AC-8 — class identity preserved (no shadow, no rename)
def test_symlink_refused_class_identity_preserved() -> None:
    assert e.SymlinkRefusedError.__module__ == "codegenie.errors"
    assert e.SymlinkRefusedError is e.__dict__["SymlinkRefusedError"]
    assert issubclass(e.SymlinkRefusedError, e.CodegenieError)


# AC-5 — CatalogLoadError docstring records the hard-fail semantics (arch §Edge cases row 9)
def test_catalog_load_error_doc_marks_hard_fail() -> None:
    doc = (e.CatalogLoadError.__doc__ or "").lower()
    assert "hard fail" in doc, (
        "CatalogLoadError docstring must mark the hard-fail-at-CLI-startup invariant "
        "per arch §Edge cases row 9; downstream catches must not soft-degrade it."
    )


# AC-1, AC-2 — new subclasses inherit DIRECTLY from CodegenieError (not transitively)
@pytest.mark.parametrize("name", sorted(PHASE1_NEW))
def test_phase1_subclasses_inherit_codegenie_error_directly(name: str) -> None:
    cls = getattr(e, name)
    assert cls.__mro__[1] is e.CodegenieError
    assert issubclass(cls, e.CodegenieError)
    assert name in e.__all__
```

Run; confirm `AttributeError: module 'codegenie.errors' has no attribute 'SizeCapExceeded'` (and the five siblings). Commit as the red marker per AC-9.

### Green — minimal impl

Append to `src/codegenie/errors.py` (after the Phase 0 subclasses, before/at `__all__` update). Each is a bare marker — no `__init__`, no class attributes:

```python
class SizeCapExceeded(CodegenieError):
    """Raised by parsers (safe_json.load / safe_yaml.load) when the file's pre-parse size exceeds the configured cap (e.g., package.json > 5 MB, lockfile > 50 MB)."""


class DepthCapExceeded(CodegenieError):
    """Raised by parsers (safe_json / safe_yaml) when the post-parse depth walker observes a structure exceeding the configured max_depth (e.g., billion-laughs)."""


class MalformedJSONError(CodegenieError):
    """Raised by parsers (safe_json.load) when the file fails JSON decode (delegates to stdlib json.JSONDecodeError detail)."""


class MalformedYAMLError(CodegenieError):
    """Raised by parsers (safe_yaml.load) when CSafeLoader refuses the bytes (e.g., !!python/object tag) or the load itself raises."""


class MalformedLockfileError(CodegenieError):
    """Raised by parsers (lockfile parsers: pnpm, npm, yarn) when the file fails structural validation."""


class CatalogLoadError(CodegenieError):
    """Raised by catalogs at module import time when the catalog YAML fails self-schema validation or contains a duplicate name. This is a load-bearing-invariant violation — hard fail at CLI startup; operator must fix the catalog before any gather runs."""
```

Update `__all__` to include the six new names (alphabetically grouped with existing entries is fine; the closure test does not constrain order). Do not edit any Phase 0 subclass.

### Refactor — clean up

- Confirm each new class body is **exactly one docstring line** plus nothing else — no `pass`, no `__init__`, no `__str__`, no class variables. `cls.__dict__` must contain only `{__module__, __qualname__, __doc__}` plus Python 3.13's compiler-injected `__firstlineno__` / `__static_attributes__` (already in `MARKER_ALLOWED_DICT_KEYS`).
- Append a one-line note to the module docstring: *"Phase 1 (Layer A) adds six marker subclasses for `parsers/` and `catalogs/` raise sites. The structured `WarningId` per ADR-0007 is constructed by the **catch site** (the calling probe), not embedded on the exception class."*
- Re-run the full Phase 0 test file (`pytest tests/unit/test_errors.py -v`) — all 17 subclasses now flow through every Phase 0 parametrized test (`test_every_subclass_directly_inherits_codegenie_error`, `test_every_subclass_has_raise_site_docstring`, `test_subclasses_are_markers_only`).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/errors.py` | Append six marker subclasses; extend `__all__`; one-line module-docstring note |
| `tests/unit/test_errors.py` | Extend `EXPECTED_SUBCLASSES` to 17; extend `DOCUMENTED_MODULE_SLUGS` by `{parsers, catalogs}`; add six parametrized tests (construction + args[0] round-trip + negative attribute checks + caught recovery + class identity + CatalogLoadError hard-fail docstring) |

## Out of scope

- **Raising these markers from parsers / catalog / coordinator** — those raise sites land in S1-02, S1-03, S1-04, S1-05, S1-09 respectively. This story is the type definitions only.
- **Mapping each exception to a `WarningId` string** — that mapping lives in each parser/probe at **catch time** (S1-02 onward). The exception type does not embed the WarningId (per ADR-0007 + this story's AC-6).
- **Re-exporting from `codegenie/__init__.py`** — Phase 0 does not re-export `errors`; do not start.
- **Promoting `WarningId` to a typed enum** — deferred to Phase 2 (open question #7).
- **Carrying machine-readable `path`/`cap`/`detail` as instance attributes** — Phase 0's markers-only contract holds; semantics are recovered from the catch context (the probe knows what it was attempting). If a later phase needs introspectable structured fields, a dedicated ADR amends the marker-only invariant and re-shapes the existing 11 Phase 0 subclasses uniformly.
- **Verifying the `safe_json.load` / `safe_yaml.load` raise behavior** — those are S1-02 / S1-03 ACs. AC-8 here only guards class identity, not runtime raise behavior.

## Notes for the implementer

- **Markers only.** Phase 0's module docstring is load-bearing: *"Subclasses carry no `__init__`, no `__str__`, no class attributes — they are markers only."* Do not add an `__init__` or class attribute to any subclass. Path / cap / detail are encoded in the **message string** the raise site passes positionally: `raise SizeCapExceeded(f"{path}: cap={cap}")`. Probes recover via `caught.args[0]` if the formatted message is needed; otherwise the calling probe simply knows the context.
- **No `__init__`, no Final, no class vars.** mypy --strict has no friction since there is no signature to constrain. `cls.__dict__` keys must remain inside `MARKER_ALLOWED_DICT_KEYS` (the Phase 0 test enforces this).
- **`SymlinkRefusedError` is a Phase 0 type.** Do not duplicate it under `parsers/`. The depth+size walker in `safe_json.load` (S1-02) re-raises it from `os.open(..., O_NOFOLLOW)`. S1-02 may extend the Phase 0 docstring of `SymlinkRefusedError` to mention the parser walker; this story does not touch that docstring.
- **`DOCUMENTED_MODULE_SLUGS` is additive.** Do not remove `exec`, `cache`, etc. — those still constrain Phase 0 subclasses. The Phase 1 union adds `parsers` and `catalogs` only.
- **Phase 0 EXPECTED_SUBCLASSES correction is part of this story.** The original Phase 0 S2-01 test enumerated 11 names; the original draft of this Phase 1 story listed 9 (stale). The hardened story re-establishes the 11-name baseline as part of the Red step so the closure test continues to pass.
- **`CatalogLoadError` docstring is load-bearing.** Arch §Edge cases row 9 says this exception is the *"hard fail at CLI startup"* signal — distinguishable from the soft-fail `Malformed*` siblings that flow into `ProbeOutput.errors`. The docstring carries that semantic for downstream readers; AC-5 + the dedicated docstring test pin it.
- **No `WarningId` import in `errors.py`.** ADR-0007 says the structured ID is produced at **catch time** by the calling probe, not on the exception class. AC-6's negative-attribute test (`hasattr(exc, "warning_id") is False`) enforces this.
- **CODEOWNERS posture.** `errors.py` is not in `CODEOWNERS`-routed paths the way `probes/base.py` is — `errors.py` grows by addition; future contributors can add a new marker subclass without an ADR, as long as they (a) keep it as a marker, (b) declare a raise-site docstring naming a documented slug, and (c) extend `DOCUMENTED_MODULE_SLUGS` if a brand-new module slug is needed. The Phase-0 contract that's frozen is `Probe` (ADR-0007 in Phase 0), not `CodegenieError`.
