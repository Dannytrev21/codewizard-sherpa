# Story S3-01 — `TCCM` + `ContextQuery` Pydantic models (Phase 3 plugin-private capability shape)

**Step:** Step 3 — TCCM, BundleBuilder, VulnIndex, content-addressed cache
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-04, S2-01
**ADRs honored:** Phase 3 ADR-0004 (plugin-private capabilities live on TCCM `provides`/`requires`, NOT on the kernel `Plugin` Protocol), Phase 3 ADR-0010 (tagged-union / Literal discipline for closed state sets), production ADR-0029 (Task-Class Context Manifests), production ADR-0030 (graph-aware context queries — fixed primitive set), production ADR-0033 (domain-modeling discipline; smart constructors at external boundaries)

## Validation notes (2026-05-18)

Hardened by `/phase-story-validator`. Findings recorded in `_validation/S3-01-tccm-context-query-models.md`. Changes applied here:

- **`PrimitiveName` smart-constructor gap with S1-01.** ADR-0030's primitive names contain dots (`scip.refs`, `import_graph.reverse_lookup`); S1-01's HARDENED `parse_primitive_name` regex (`^[a-z][a-z0-9_]*$`) does *not* accept dots. Resolved by pinning `_KNOWN_PRIMITIVES` membership as the sole boundary check for `ContextQuery.primitive` and direct-wrapping `PrimitiveName(s)` after the check — explicit AC + Notes entry. `parse_primitive_name` is intentionally *not* called from `ContextQuery.create`. (Consistency BLOCK F1.)
- **`TCCMParseError` shape conflict with markers-only `CodegenieError`.** The TDD plan reads `.reason` as a typed attribute, but `codegenie.errors` is markers-only (no `__init__`, no class state). Resolved by making `TCCMParseError` a frozen Pydantic `BaseModel` (S1-01 `ParseError` precedent under `codegenie.types.errors`), **not** a `CodegenieError` subclass. `reason` is typed `Literal["unknown_primitive", "negative_max_files"]` — closes the set at compile time per ADR-0010. (Consistency HARDEN; Design-Patterns 1.)
- **Hashability claim contradicts `args: dict` field.** Pydantic v2 frozen models hash by field values; dicts are unhashable → `hash(ContextQuery)` raises `TypeError`. Notes claim corrected: cache key derivation uses `model_dump_json(by_alias=False, exclude_defaults=False)`; an explicit AC + test pins the canonical-JSON cache-key path and asserts `hash()` raises (the test documents the constraint, not a wished-for behavior). (Coverage F7; Consistency NIT; Design-Patterns 3.)
- **Fence assertion grammar tightened.** Old fence (`_NAMESPACE_RE.match(p.split(".")[0])`) accepted both `scip` (no dot) and `scip.refs.deep` (two dots). Replaced with `_PRIMITIVE_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")` matching exactly one dot-separated `namespace.name` shape; assertion uses `fullmatch`. (Coverage F4.)
- **`_KNOWN_PRIMITIVES` exact-set pin.** Cardinality + set-equality test added — a developer adding a 6th primitive must edit the pin, forcing a paired ADR-0030 amendment review. (Coverage F2; Design-Patterns 5.)
- **Helper extraction at rule-of-three elevated to AC.** Day 1 has two consumers of namespace-map walking (`provides` outer + `requires` outer keys). S1-01 AC-18 precedent applies — mandatory, not "refactor advisory." (Design-Patterns 2.)
- **Test parametrization mutation-hardened.** Negative tests on `_NAMESPACE_RE`, `_IMPORT_PATH_RE`, `max_files`, and `args` value union widened to parametrized rejection corpora; positive parametrization added for happy import paths and shallow/deep fallback chains. Property test imports fixed (`re`, `pytest`, `ValidationError` were missing). Second property test added covering import-path grammar drift. (Test-Quality block + harden.)
- **AST source-scan test added to TDD plan + `re` added to import allowlist** (was missing from old AC). (Coverage F8.)
- **Forward-ref approach pinned** to `from __future__ import annotations` + explicit `ContextQuery.model_rebuild()`; matches Phase-2 `tccm/model.py` convention. (Design-Patterns 4; Rule 11.)
- **Deferred design opportunities** captured in Notes (capability-namespace newtypes for S2-02; per-primitive args sum type for S3-04 BundleBuilder) — neither crosses rule-of-three today.

## Context

Phase 3's plugin model needs a richer TCCM shape than the Phase 02 `src/codegenie/tccm/model.py` ships: it must carry `must_read` / `should_read` / `may_read` priority bands of typed `ContextQuery` items (ADR-0029) AND a `provides` / `requires` capability namespace (ADR-0004 — task-class-specific knowledge such as `vuln_index_capabilities: {nvd_parser: api:NvdParser, ...}` is declared here so the kernel `Plugin` Protocol stays at four methods and is closed for modification). The Phase 02 `TCCM` is a different concern (probe-set declaration) and stays unchanged — Phase 3's lives under `src/codegenie/plugins/tccm.py` as a fresh model, ADR-0004 §Consequences "kernel knows about neither namespace" being the load-bearing invariant.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C7` — `BundleBuilder.build(resolution, ...)` consumes `resolution.composed_tccm` to dispatch queries.
  - `../phase-arch-design.md §Data model` (lines ~759–773) — `TCCM` Pydantic shape: `must_read`, `should_read`, `may_read`, `provides: dict[str, dict[str, str]]`, `requires: dict[str, list[str]]`.
  - `../phase-arch-design.md §C2` — `Plugin` Protocol surface is exactly four methods; per-task-class knowledge MUST land in TCCM `provides`.
- **Phase ADRs:**
  - `../ADRs/0004-plugin-private-capabilities-via-tccm.md §Decision + §Consequences` — `provides.{capability_namespace}` is the extension seam; vuln plugin declares `provides.vuln_index_capabilities`; Phase 7 distroless will declare `provides.dockerfile_capabilities` with zero kernel edits.
- **Production ADRs:**
  - `../../../production/adrs/0029-task-class-context-manifests.md §must/should/may_read` — three priority bands and their semantics.
  - `../../../production/adrs/0030-graph-aware-context-queries.md §Initial query primitives` — fixed primitive set (`scip.refs`, `import_graph.reverse_lookup`, `import_graph.transitive_callers`, `dep_graph.consumers`, `test_inventory.tests_exercising`).
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Plugin Protocol surface"` — ADR-0004 origin.
- **Existing code:**
  - `src/codegenie/tccm/model.py` — Phase 02 TCCM (do NOT edit); Phase 3 ships a *new* model under `src/codegenie/plugins/tccm.py`. Surface the conflict if any naming clash is awkward.
  - `src/codegenie/types/identifiers.py` (S1-01) — `PluginId`, `PrimitiveName`, `RecipeId` etc.; Phase 3 imports `PrimitiveName` here.
  - `src/codegenie/result.py` — `Result[T, E]` return convention used by smart constructors.

## Goal

`codegenie.plugins.tccm` exposes `ContextQuery` and `TCCM` Pydantic models with `frozen=True`, `extra="forbid"`, validated `PrimitiveName` strings on `ContextQuery.primitive`, and typed `provides` / `requires` capability namespace maps — so Phase 3's `BundleBuilder` can iterate `must_read`/`should_read`/`may_read` and the vuln plugin can declare `provides.vuln_index_capabilities` without any kernel edit.

## Acceptance criteria

### Module surface

- [ ] AC-1 — New module `src/codegenie/plugins/tccm.py` exports `ContextQuery`, `TCCM`, `TCCMParseError`. `__all__` pins exactly these three names (set-equality, not `⊇`).
- [ ] AC-2 — `ContextQuery` is a Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields: `primitive: PrimitiveName`, `args: dict[str, str | int | bool | list[str]]` (primitives only — NO `Any`), `fallback: ContextQuery | None = None` (the ADR-0008 declared-fallback seam — fires *only* on `AdapterConfidence.Degraded | Unavailable`), `max_files: int | None = None` (ADR-0030 bound).
- [ ] AC-3 — `TCCM` is a Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields: `must_read: list[ContextQuery]` (**required, no default**), `should_read: list[ContextQuery] = []`, `may_read: list[ContextQuery] = []`, `provides: dict[str, dict[str, str]] = {}`, `requires: dict[str, list[str]] = {}`.

### Error model (markers-only conflict resolved per Validation notes)

- [ ] AC-4 — `TCCMParseError` is a **frozen Pydantic `BaseModel`** (not a `CodegenieError` subclass — see Validation notes; mirrors S1-01's `ParseError` precedent in `codegenie.types.errors`). `model_config = ConfigDict(frozen=True, extra="forbid")`. Fields: `reason: Literal["unknown_primitive", "negative_max_files"]` (closed set; additions require ADR amendment) and `details: dict[str, str | int] = {}` (carries the offending value, e.g. `{"primitive": "grep.adhoc"}` or `{"max_files": -1}`). `mypy --strict` rejects construction with any other `reason` string at the call site.

### Primitive set + grammar (ADR-0030)

- [ ] AC-5 — `_KNOWN_PRIMITIVES: Final[frozenset[PrimitiveName]]` is a module-level constant. Test pins **exact set equality**: `_KNOWN_PRIMITIVES == frozenset({"scip.refs", "import_graph.reverse_lookup", "import_graph.transitive_callers", "dep_graph.consumers", "test_inventory.tests_exercising"})` AND `len(_KNOWN_PRIMITIVES) == 5`. A 6th primitive added without editing this test (and therefore without prompting an ADR-0030 amendment review) fails CI.
- [ ] AC-6 — `_PRIMITIVE_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")` (exactly one dot-separated `namespace.name` shape). Module-import fence: `if not all(_PRIMITIVE_RE.fullmatch(p) for p in _KNOWN_PRIMITIVES): raise AssertionError("primitive grammar drift in _KNOWN_PRIMITIVES")` (using `raise AssertionError(...)` form per the `forbidden-patterns` hook; bare `assert` is banned).
- [ ] AC-7 — **`PrimitiveName` direct-wrap discipline.** `ContextQuery.create` does **NOT** call `parse_primitive_name` (S1-01's regex `^[a-z][a-z0-9_]*$` rejects dots; ADR-0030 primitives contain dots). The membership check against `_KNOWN_PRIMITIVES` *is* the boundary validation; the constructor wraps `PrimitiveName(s)` directly after the check. A code comment cites this gap with file/line back to S1-01 AC. (See Notes for the implementer; a follow-up amendment to S1-01's `parse_primitive_name` may relax the regex to a dotted-snake shape, but is **out of scope here**.)

### Smart constructor — `ContextQuery.create`

- [ ] AC-8 — `ContextQuery.create(primitive: str, args: dict[str, str | int | bool | list[str]], *, fallback: ContextQuery | None = None, max_files: int | None = None) -> Result[ContextQuery, TCCMParseError]`:
  - Returns `Err(TCCMParseError(reason="unknown_primitive", details={"primitive": primitive}))` when `primitive not in _KNOWN_PRIMITIVES`.
  - Returns `Err(TCCMParseError(reason="negative_max_files", details={"max_files": max_files}))` when `max_files is not None and max_files <= 0`.
  - Otherwise returns `Ok(ContextQuery(primitive=PrimitiveName(primitive), args=args, fallback=fallback, max_files=max_files))`.
  - Any `pydantic.ValidationError` raised by direct construction (e.g., from a malformed `args` value type, or `extra="forbid"` rejection) is **NOT swallowed** — `create` is the smart-constructor surface for the two enumerated `TCCMParseError` reasons only; other errors propagate to the caller. Test pins this contract.

### `args` value-type rejection (parametrized)

- [ ] AC-9 — `ContextQuery.model_validate({"primitive": "scip.refs", "args": X})` raises `pydantic.ValidationError` for **each** of the following payloads (parametrized): `X = {"k": None}`, `{"k": 3.14}`, `{"k": {"nested": "dict"}}`, `{"k": [1, 2]}` (list of non-str), `{"k": (1, 2)}` (tuple), `{"k": object()}`. A dev relaxing the union to `dict[str, Any]` fails ≥ 5 of these.
- [ ] AC-10 — `ContextQuery.create("scip.refs", args={})` returns `Ok(...)` (empty args dict is intentionally valid; primitive-specific arg-key requirements live in the adapter contract, not in this schema).

### `provides` validation (multi-namespace + import-path corpus)

- [ ] AC-11 — `provides` outer-key grammar `^[a-z][a-z0-9_]*$` (namespace), inner-key grammar `^[a-z][a-z0-9_]*$` (capability name), inner-value grammar `^[a-zA-Z_][a-zA-Z0-9_.]*:[A-Z][a-zA-Z0-9_]*$` (`module.path:ClassName`). On violation, `ValidationError` is raised with `loc` pointing at the offending key path. **Parametrized rejection corpus:**
  - Bad namespace: `["1vuln", "Vuln", "vuln-index", "vuln.index", "Vuln-Index", "", " spaces ", "_leading_underscore"]`.
  - Bad import-path: `[":NoModule", "mod:lowercase", "1mod:Class", "mod:1Class", "mod:", "mod::Class", "no_colon_here", ""]`.
  - **Happy import-path corpus:** `["a:B", "codegenie.x.y:NvdParser", "_mod:Cls", "pkg.sub_pkg.mod:ClassName"]` — all accepted.
- [ ] AC-12 — **Multi-namespace iteration coverage.** `TCCM.model_validate(...)` with `provides = {"valid_ns": {"ok": "a:B"}, "Bad-NS": {"x": "a:B"}}` raises `ValidationError` with `loc` reaching the second-position invalid `"Bad-NS"` (i.e., validator iterates ALL outer keys, not just the first). Mirror for `requires`.
- [ ] AC-13 — **Multi-namespace round-trip.** A `TCCM` instance with `provides` containing **two** namespaces side-by-side (e.g., `vuln_index_capabilities` AND `telemetry_capabilities`) round-trips via `model_dump()` → `TCCM.model_validate(...)` to an equal instance; both namespaces are preserved.

### `requires` validation

- [ ] AC-14 — `requires` outer-key and every list-element match `^[a-z][a-z0-9_]*$`. Empty inner list is **explicitly allowed** (positive test): `TCCM.model_validate({"must_read": [...], "requires": {"valid_ns": []}})` succeeds. A future tightening that disallows empty lists would fail this AC.

### `ContextQuery` round-trip (recursive forward-ref)

- [ ] AC-15 — A `ContextQuery` with **non-None** `fallback` round-trips via `model_dump()` → `ContextQuery.model_validate(...)` to an equal instance. A **3-level-deep** fallback chain (primary → fallback → fallback) also round-trips; `primary.fallback.fallback.primitive` survives intact. Pins that the forward-ref recursion (`model_rebuild()`) works at depth > 1.

### Cache-key strategy + hashability honesty (illegal-state-representable fix)

- [ ] AC-16 — `ContextQuery` is **NOT hashable** (because `args: dict[...]` is unhashable). Explicit test pins this: `with pytest.raises(TypeError): hash(some_ctx_query)`. The cache-key surface for downstream consumers (e.g., BundleBuilder per ADR-0008) is `ContextQuery.model_dump_json()` — deterministic across two instances constructed identically; an explicit test asserts byte-equal JSON output for the same inputs. This replaces the misleading "frozen ⇒ hashable" claim previously in Notes.

### Helper extraction at rule-of-three (S1-01 AC-18 precedent)

- [ ] AC-17 — A single module-private helper validates the namespace-key shape across `provides` (outer keys) and `requires` (outer keys + list elements). Signature: `_validate_namespace_keys(value: Mapping[str, object], *, where: str) -> None` (raises `ValueError` → Pydantic converts to `ValidationError`). **AST observable:** the substring `_NAMESPACE_RE.fullmatch(` (or `.match(`) appears at most ONCE in `src/codegenie/plugins/tccm.py` outside the helper body (i.e., only inside the helper). Adding a third consumer requires zero edits to the helper. Mirrors S1-01 AC-18 discipline.

### Property tests (Hypothesis)

- [ ] AC-18 — Property test 1: any `provides` outer namespace key drawn from `st.text(min_size=1).filter(lambda s: not re.fullmatch(r"[a-z][a-z0-9_]*", s))` is rejected by `TCCM.model_validate(...)`.
- [ ] AC-19 — Property test 2: any `provides` inner value (import path) drawn from `st.text(min_size=1).filter(lambda s: not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.]*:[A-Z][a-zA-Z0-9_]*", s))` is rejected by `TCCM.model_validate(...)`.

### Boundary parametrization for `max_files`

- [ ] AC-20 — `ContextQuery.create(..., max_files=X)` returns `Err(reason="negative_max_files", ...)` for **each** `X ∈ {0, -1, -(2**31)}`; returns `Ok(...)` for `X ∈ {1, 1024, None}`.

### Module purity (AST source-scan)

- [ ] AC-21 — `tests/unit/plugins/test_tccm_module_purity.py` AST-walks `src/codegenie/plugins/tccm.py`; asserts the union of all `ast.Import` / `ast.ImportFrom` module names is **a subset of** `{"__future__", "re", "typing", "pydantic", "codegenie.types.identifiers", "codegenie.types.errors", "codegenie.result"}`. No logger, no I/O, no sibling Phase-3 modules. Note: `re` and `__future__` are in the allowlist (previously omitted from AC); `codegenie.errors` is **removed** because `TCCMParseError` is no longer a `CodegenieError` subclass.

### Gates

- [ ] AC-22 — TDD red test exists, committed, then green.
- [ ] AC-23 — `ruff format --check`, `ruff check`, `mypy --strict src/codegenie/plugins/` clean.

## Implementation outline

1. Create `src/codegenie/plugins/__init__.py` (empty module docstring; Phase 3 plugins package home).
2. Create `src/codegenie/plugins/tccm.py`. Start with `from __future__ import annotations` (matches Phase-2 `src/codegenie/tccm/model.py:33` convention; pinned for forward-ref recursion).
3. Imports — restricted to the AC-21 allowlist:
   - `re`, `typing.Final`, `typing.Literal`, `typing.Mapping`
   - `pydantic.BaseModel`, `pydantic.ConfigDict`, `pydantic.field_validator`
   - `codegenie.types.identifiers.PrimitiveName`
   - `codegenie.types.errors.ParseError` is **not** reused — `TCCMParseError` is a distinct closed model (see AC-4 / Validation notes); but the pattern (frozen Pydantic `BaseModel` as the `Err` value) is the same.
   - `codegenie.result.{Result, Ok, Err}`
4. Module constants (`Final`):
   - `_KNOWN_PRIMITIVES: Final[frozenset[PrimitiveName]]` with the 5 ADR-0030 primitives (AC-5).
   - `_NAMESPACE_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")`.
   - `_IMPORT_PATH_RE: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*:[A-Z][a-zA-Z0-9_]*$")`.
   - `_PRIMITIVE_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")` (used by the fence, AC-6).
5. Fence assertion at module-import time (AC-6): walk `_KNOWN_PRIMITIVES`; on first miss, `raise AssertionError("primitive grammar drift in _KNOWN_PRIMITIVES: <bad>")`. Use `raise AssertionError(...)` form (bare `assert` is banned by the `forbidden-patterns` pre-commit hook).
6. Define `class TCCMParseError(BaseModel)` (NOT a `CodegenieError` subclass — see Validation notes; S1-01 `ParseError` precedent):
   ```python
   class TCCMParseError(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       reason: Literal["unknown_primitive", "negative_max_files"]
       details: dict[str, str | int] = {}
   ```
7. Define `class ContextQuery(BaseModel)`:
   - `model_config = ConfigDict(frozen=True, extra="forbid")`.
   - Field set per AC-2.
   - `@field_validator("primitive")` — `_KNOWN_PRIMITIVES` membership; raises `ValueError(f"unknown primitive: {v!r}")`.
   - `@field_validator("max_files")` — rejects `<= 0` when not None.
   - Classmethod `create(...) -> Result[ContextQuery, TCCMParseError]` returning the two enumerated reasons explicitly (AC-8); does **not** wrap arbitrary `ValidationError` (those propagate to caller).
8. Define module-private `_validate_namespace_keys(value: Mapping[str, object], *, where: str) -> None` helper (AC-17). Reused by both `provides` and `requires` validators. Single place that calls `_NAMESPACE_RE.fullmatch`.
9. Define `class TCCM(BaseModel)`:
   - Field set per AC-3.
   - `@field_validator("provides")` — iterates outer keys → calls `_validate_namespace_keys`; iterates inner items → checks inner key against `_NAMESPACE_RE` and inner value against `_IMPORT_PATH_RE`. Loops over the **full** dict (no early return) so the second offending namespace is also surfaced (AC-12).
   - `@field_validator("requires")` — iterates outer keys → `_validate_namespace_keys`; iterates list elements → `_NAMESPACE_RE`. Empty inner list allowed (AC-14).
10. Trailing `ContextQuery.model_rebuild()` (resolves the forward-ref `fallback: ContextQuery | None`).
11. `__all__ = ("ContextQuery", "TCCM", "TCCMParseError")` (sorted; AC-1).

## TDD plan — red / green / refactor

### Red

Three test files. Imports shown in full (the previous draft's property test was missing `re`, `pytest`, and `ValidationError` imports — fixed below).

**File 1: `tests/unit/plugins/test_tccm_models.py`** — unit + parametrized negatives.

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from codegenie.plugins.tccm import (
    ContextQuery, TCCM, TCCMParseError,
    _IMPORT_PATH_RE, _KNOWN_PRIMITIVES, _NAMESPACE_RE, _PRIMITIVE_RE,
)


# --- ContextQuery ---

class TestContextQuery:
    def test_known_primitive_accepted(self):
        result = ContextQuery.create(primitive="scip.refs", args={"symbol": "express.urlencoded"})
        assert result.is_ok()
        assert result.unwrap().primitive == "scip.refs"

    def test_unknown_primitive_rejected(self):
        result = ContextQuery.create(primitive="grep.adhoc", args={})
        assert result.is_err()
        err = result.unwrap_err()
        assert err.reason == "unknown_primitive"
        assert err.details == {"primitive": "grep.adhoc"}

    @pytest.mark.parametrize("bad", [0, -1, -(2**31)])
    def test_negative_max_files_rejected(self, bad):
        # AC-20 boundary parametrization
        r = ContextQuery.create(primitive="scip.refs", args={}, max_files=bad)
        assert r.is_err()
        assert r.unwrap_err().reason == "negative_max_files"
        assert r.unwrap_err().details == {"max_files": bad}

    @pytest.mark.parametrize("good", [1, 1024, None])
    def test_valid_max_files_accepted(self, good):
        # AC-20 happy-path parametrization
        assert ContextQuery.create(primitive="scip.refs", args={}, max_files=good).is_ok()

    def test_fallback_round_trip_depth_3(self):
        # AC-15: three-deep fallback chain survives dump/validate
        deep = ContextQuery.create(primitive="dep_graph.consumers", args={"pkg": "x"}).unwrap()
        mid = ContextQuery.create(primitive="import_graph.reverse_lookup", args={"module": "x"}, fallback=deep).unwrap()
        primary = ContextQuery.create(primitive="scip.refs", args={"symbol": "x"}, fallback=mid).unwrap()
        assert primary.fallback.fallback.primitive == "dep_graph.consumers"
        rt = ContextQuery.model_validate(primary.model_dump())
        assert rt == primary
        assert rt.fallback.fallback.primitive == "dep_graph.consumers"

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            ContextQuery.model_validate({"primitive": "scip.refs", "args": {}, "rogue": "x"})

    def test_empty_args_accepted(self):
        # AC-10
        assert ContextQuery.create(primitive="scip.refs", args={}).is_ok()

    @pytest.mark.parametrize("bad_args", [
        {"k": None},
        {"k": 3.14},
        {"k": {"nested": "dict"}},
        {"k": [1, 2]},      # list of non-str
        {"k": (1, 2)},      # tuple
    ])
    def test_args_rejects_non_primitive_values(self, bad_args):
        # AC-9 — relaxing the union to dict[str, Any] would silently regress
        with pytest.raises(ValidationError):
            ContextQuery.model_validate({"primitive": "scip.refs", "args": bad_args})

    def test_create_does_not_swallow_unrelated_validation_errors(self):
        # AC-8 last bullet: malformed args propagates, not wrapped in TCCMParseError
        with pytest.raises(ValidationError):
            ContextQuery.create(primitive="scip.refs", args={"k": {"nested": "x"}})  # type: ignore[dict-item]


# --- TCCMParseError shape ---

def test_tccm_parse_error_is_frozen_pydantic_with_literal_reason():
    # AC-4: NOT a CodegenieError subclass — frozen Pydantic with closed reason set
    from codegenie.errors import CodegenieError
    assert not issubclass(TCCMParseError, CodegenieError)
    err = TCCMParseError(reason="unknown_primitive", details={"primitive": "x"})
    assert err.reason == "unknown_primitive"
    with pytest.raises(ValidationError):
        TCCMParseError(reason="totally_made_up", details={})        # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        TCCMParseError(reason="unknown_primitive", details={"x": 3.14})  # float not in str|int union


# --- _KNOWN_PRIMITIVES discipline ---

def test_known_primitives_exact_set():
    # AC-5: exact set equality + cardinality; a 6th primitive must edit this test
    assert _KNOWN_PRIMITIVES == frozenset({
        "scip.refs",
        "import_graph.reverse_lookup",
        "import_graph.transitive_callers",
        "dep_graph.consumers",
        "test_inventory.tests_exercising",
    })
    assert len(_KNOWN_PRIMITIVES) == 5


def test_primitive_grammar_fence_matches_known_primitives():
    # AC-6: every known primitive matches _PRIMITIVE_RE.fullmatch
    for p in _KNOWN_PRIMITIVES:
        assert _PRIMITIVE_RE.fullmatch(p), p


def test_primitive_re_rejects_drift():
    # AC-6 mutation pin: a missing dot or two-dot variant must NOT match
    assert _PRIMITIVE_RE.fullmatch("scip") is None
    assert _PRIMITIVE_RE.fullmatch("scip.refs.deep") is None
    assert _PRIMITIVE_RE.fullmatch("Scip.refs") is None


# --- TCCM ---

class TestTCCM:
    BASE_MUST = [{"primitive": "scip.refs", "args": {}}]

    @pytest.mark.parametrize("bad_ns", [
        "1vuln", "Vuln", "vuln-index", "vuln.index",
        "Vuln-Index", "", " spaces ", "_leading_underscore",
    ])
    def test_provides_namespace_grammar_rejects_bad(self, bad_ns):
        # AC-11 negative corpus for namespace
        with pytest.raises(ValidationError):
            TCCM.model_validate({
                "must_read": self.BASE_MUST,
                "provides": {bad_ns: {"nvd_parser": "x:Y"}},
            })

    @pytest.mark.parametrize("bad_path", [
        ":NoModule", "mod:lowercase", "1mod:Class", "mod:1Class",
        "mod:", "mod::Class", "no_colon_here", "",
    ])
    def test_provides_import_path_rejects_bad(self, bad_path):
        # AC-11 negative corpus for import path
        with pytest.raises(ValidationError):
            TCCM.model_validate({
                "must_read": self.BASE_MUST,
                "provides": {"vuln_index_capabilities": {"nvd_parser": bad_path}},
            })

    @pytest.mark.parametrize("good_path", [
        "a:B",
        "codegenie.x.y:NvdParser",
        "_mod:Cls",
        "pkg.sub_pkg.mod:ClassName",
    ])
    def test_provides_import_path_accepts_happy_corpus(self, good_path):
        # AC-11 positive corpus
        m = TCCM.model_validate({
            "must_read": self.BASE_MUST,
            "provides": {"vuln_index_capabilities": {"nvd_parser": good_path}},
        })
        assert m.provides["vuln_index_capabilities"]["nvd_parser"] == good_path

    def test_provides_multi_namespace_second_invalid_caught(self):
        # AC-12: validator iterates ALL outer keys (mutation: early-return after first would survive single-NS tests)
        with pytest.raises(ValidationError) as ei:
            TCCM.model_validate({
                "must_read": self.BASE_MUST,
                "provides": {
                    "valid_ns": {"ok": "a:B"},
                    "Bad-NS": {"x": "a:B"},
                },
            })
        # surface the loc — Pydantic reports the offending path
        joined = str(ei.value)
        assert "Bad-NS" in joined or "provides" in joined

    def test_provides_two_namespaces_round_trip(self):
        # AC-13: two namespaces side-by-side both validate AND round-trip
        original = TCCM.model_validate({
            "must_read": [{"primitive": "dep_graph.consumers", "args": {"pkg": "express"}}],
            "should_read": [{"primitive": "test_inventory.tests_exercising", "args": {"symbol": "urlencoded"}}],
            "may_read": [],
            "provides": {
                "vuln_index_capabilities": {
                    "nvd_parser": "codegenie.vuln_index.parsers:NvdParser",
                    "ghsa_parser": "codegenie.vuln_index.parsers:GhsaParser",
                },
                "telemetry_capabilities": {
                    "emitter": "codegenie.telemetry:Emitter",
                },
            },
            "requires": {},
        })
        rt = TCCM.model_validate(original.model_dump())
        assert rt == original
        assert set(rt.provides) == {"vuln_index_capabilities", "telemetry_capabilities"}

    @pytest.mark.parametrize("bad_inner", ["BadName", "1foo", "with-hyphen", "with.dot"])
    def test_requires_inner_grammar_rejects_bad(self, bad_inner):
        with pytest.raises(ValidationError):
            TCCM.model_validate({
                "must_read": self.BASE_MUST,
                "requires": {"valid_ns": [bad_inner]},
            })

    def test_requires_empty_list_allowed(self):
        # AC-14 positive — namespace declared without specific names
        m = TCCM.model_validate({"must_read": self.BASE_MUST, "requires": {"valid_ns": []}})
        assert m.requires == {"valid_ns": []}

    def test_must_read_required_and_loc_pinned(self):
        # AC-3: must_read has no default
        with pytest.raises(ValidationError) as ei:
            TCCM.model_validate({"should_read": []})
        locs = [tuple(e["loc"]) for e in ei.value.errors()]
        assert ("must_read",) in locs


# --- Cache-key + hashability honesty (AC-16) ---

def test_context_query_is_not_hashable_due_to_dict_args():
    cq = ContextQuery.create(primitive="scip.refs", args={"k": "v"}).unwrap()
    with pytest.raises(TypeError):
        hash(cq)


def test_context_query_model_dump_json_is_deterministic_for_cache_key():
    # The actual cache-key surface (ADR-0008)
    cq_a = ContextQuery.create(primitive="scip.refs", args={"symbol": "x"}).unwrap()
    cq_b = ContextQuery.create(primitive="scip.refs", args={"symbol": "x"}).unwrap()
    assert cq_a.model_dump_json() == cq_b.model_dump_json()
```

**File 2: `tests/property/plugins/test_tccm_namespace_grammar.py`** — Hypothesis (AC-18 + AC-19).

```python
from __future__ import annotations

import re

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from codegenie.plugins.tccm import TCCM

_BASE_MUST = [{"primitive": "scip.refs", "args": {}}]
_NS_RE = r"[a-z][a-z0-9_]*"
_IMPORT_RE = r"[a-zA-Z_][a-zA-Z0-9_.]*:[A-Z][a-zA-Z0-9_]*"


@given(bad_ns=st.text(min_size=1).filter(lambda s: not re.fullmatch(_NS_RE, s)))
def test_invalid_namespace_always_rejected(bad_ns):
    # AC-18
    with pytest.raises(ValidationError):
        TCCM.model_validate({
            "must_read": _BASE_MUST,
            "provides": {bad_ns: {"nvd_parser": "x:Y"}},
        })


@given(bad_path=st.text(min_size=1).filter(lambda s: not re.fullmatch(_IMPORT_RE, s)))
def test_invalid_import_path_always_rejected(bad_path):
    # AC-19
    with pytest.raises(ValidationError):
        TCCM.model_validate({
            "must_read": _BASE_MUST,
            "provides": {"vuln_index_capabilities": {"nvd_parser": bad_path}},
        })
```

**File 3: `tests/unit/plugins/test_tccm_module_purity.py`** — AST source-scan (AC-17 + AC-21).

```python
from __future__ import annotations

import ast
from pathlib import Path

import codegenie.plugins.tccm as _tccm_mod

_ALLOWED_MODULES = {
    "__future__", "re", "typing",
    "pydantic",
    "codegenie.types.identifiers",
    "codegenie.result",
}
# Note: codegenie.errors is intentionally NOT in the allowlist; TCCMParseError
# is a Pydantic BaseModel, not a CodegenieError subclass (AC-4).


def _imports_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
    return out


def test_tccm_module_imports_subset_of_allowlist():
    # AC-21
    src = Path(_tccm_mod.__file__)
    assert _imports_in(src) <= _ALLOWED_MODULES


def test_namespace_re_fullmatch_appears_only_in_helper():
    # AC-17: the dict-walking helper is the SOLE caller of _NAMESPACE_RE.fullmatch
    src_text = Path(_tccm_mod.__file__).read_text(encoding="utf-8")
    # Tolerant search: count occurrences of either `_NAMESPACE_RE.fullmatch(` or `.match(`
    n = src_text.count("_NAMESPACE_RE.fullmatch(") + src_text.count("_NAMESPACE_RE.match(")
    assert n == 1, (
        f"Expected exactly one call site for _NAMESPACE_RE; found {n}. "
        "All namespace-key validation must route through _validate_namespace_keys (AC-17)."
    )
```

### Green

Smallest impl: §Implementation outline; ~140 lines including the helper and parametrized validators.

### Refactor

- Promote docstrings to cite ADR-0004 §Consequences for `provides`, ADR-0030 §Initial query primitives for `_KNOWN_PRIMITIVES`, and ADR-0010 for the closed `Literal` reason set on `TCCMParseError`.
- If the `provides` inner-key + leaf-value walking grows a third consumer (S2-02's manifest loader will probably need to validate the same shapes when ingesting `tccm.yaml`), elevate that helper too — but only at rule-of-three. Today's two consumers (`provides` outer + `requires` outer) share `_validate_namespace_keys` (AC-17).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/__init__.py` | New package — Phase 3 plugins module home (empty file with module docstring) |
| `src/codegenie/plugins/tccm.py` | New module — `ContextQuery`, `TCCM`, `TCCMParseError` (frozen Pydantic; not a `CodegenieError` subclass) |
| `tests/unit/plugins/test_tccm_models.py` | Unit + parametrized negatives + cache-key honesty tests (AC-1..AC-16, AC-20) |
| `tests/property/plugins/test_tccm_namespace_grammar.py` | Hypothesis property tests over namespace + import-path grammars (AC-18, AC-19) |
| `tests/unit/plugins/test_tccm_module_purity.py` | AST source-scan for import allowlist + helper-extraction discipline (AC-17, AC-21) |
| `tests/unit/plugins/__init__.py` + `tests/property/plugins/__init__.py` | Empty package markers if not present |

## Out of scope

- **Plugin manifest YAML loading** — S2-02's job; this story ships the runtime types only.
- **TCCM composition under `extends`** — `PluginRegistry`/resolver concern, S2-04.
- **Actual query dispatch** — `BundleBuilder` (S3-04) consumes `ContextQuery` and routes via Phase 2 search adapters; this story only defines the type.
- **`AdapterConfidence` re-definition** — Phase 02 owns it; import as-needed (ADR-0008 mentions it; not part of this story's surface).
- **Editing `src/codegenie/tccm/model.py`** — Phase 02 TCCM stays; this is a separate Phase 3 model. Do NOT unify; the shapes serve different consumers.

## Notes for the implementer

- **Naming clash with Phase 02 `codegenie.tccm`.** Phase 02 owns `codegenie.tccm` (probe-set TCCM). Phase 3 lands under `codegenie.plugins.tccm` — different namespace, different shape, different consumer. If reviewers ask about unification, defer to ADR-0004 — the two TCCMs are intentionally distinct.
- **`provides` value parsing is a soft contract.** Per ADR-0004 §Tradeoffs, the import-path strings are validated for *shape* here, not *importability* — the loader (S2-02 / S2-03) resolves `module:Class` at plugin load time and surfaces `PluginRejected(import_error)` on miss. Keep this story's validation grammatical only.
- **`_KNOWN_PRIMITIVES` is closed by design.** Adding a primitive is an ADR amendment to production ADR-0030 + one line here. The AC-5 exact-set pin makes this enforceable: a 6th primitive added without editing both the set and the test forces a review. Do NOT add wildcards or `*`-matching; that defeats the "small, stable DSL" commitment.
- **`PrimitiveName` smart-constructor gap (S1-01 conflict).** S1-01's `parse_primitive_name` regex is `^[a-z][a-z0-9_]*$` (no dots). ADR-0030 primitives like `scip.refs` contain dots and would be **rejected** by that parser. This story therefore does **NOT** call `parse_primitive_name` from `ContextQuery.create` — the `_KNOWN_PRIMITIVES` membership check IS the boundary validation, and the constructor wraps `PrimitiveName(s)` directly after the check (`NewType` is identity at runtime). Leave a comment at the call site pointing at this Note + AC-7. A future story may amend S1-01 to relax `parse_primitive_name` to a dotted-snake regex; until then, the discipline lives here.
- **Forward references — pinned to `from __future__ import annotations`.** Matches Phase-2 `src/codegenie/tccm/model.py:33`. Add an explicit `ContextQuery.model_rebuild()` call after the class block to resolve the recursive `fallback: ContextQuery | None`.
- **`args: dict[str, str | int | bool | list[str]]`** — primitives only, no nested dicts, matching the discipline used for `TrustSignal.details` (phase-arch-design §Data model). Reject `Any`; reviewers will hold the line. AC-9 pins the rejection corpus.
- **Cache-key strategy is `model_dump_json()`, not `hash()`.** `args: dict[...]` makes `ContextQuery` unhashable (the previous draft of this story incorrectly claimed otherwise). Downstream consumers in BundleBuilder (S3-04 / ADR-0008) should derive content-addressed keys from `model_dump_json(by_alias=False, exclude_defaults=False)`. AC-16 pins both the negative (`hash()` raises `TypeError`) and the positive (`model_dump_json()` is deterministic).
- **`TCCMParseError` is a frozen Pydantic `BaseModel`, NOT a `CodegenieError` subclass.** The TDD plan reads `.reason` as a typed attribute; markers-only error classes (per `src/codegenie/errors.py` discipline) carry no fields and so cannot serve this role. Mirrors S1-01's `ParseError` precedent in `codegenie.types.errors`. The `reason: Literal[...]` set is closed by ADR-0010; extending it requires an ADR amendment.
- **Deferred design opportunities (do not address in S3-01):**
  - *Capability-namespace newtypes* — `provides: dict[str, dict[str, str]]` is semantically `dict[CapabilityNamespace, dict[CapabilityName, ImportPath]]`. Rule-of-three not yet crossed (2 callers Day 1). When S2-02 (manifest loader) lands as the 3rd consumer of the namespace grammar, evaluate adding `CapabilityNamespace`, `CapabilityName`, `ImportPath` to `codegenie.types.identifiers`.
  - *Per-primitive args sum type* — `args: dict[str, str | int | bool | list[str]]` is anaemic; a `ScipRefsArgs(symbol: str) | DepGraphConsumersArgs(pkg: str) | ...` discriminated union would let S3-04 BundleBuilder `match` on args shape. Today the 5 primitives' arg schemas are not formalized; the union is intentionally anaemic per Rule 2. Revisit at S3-04.
- **Do NOT register `TCCM` with anything yet** — this story is types only. S2-02 loads from YAML; S3-04 consumes for query dispatch.
