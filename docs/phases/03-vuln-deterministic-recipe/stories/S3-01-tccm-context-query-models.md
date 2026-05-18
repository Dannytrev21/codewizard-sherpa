# Story S3-01 — `TCCM` + `ContextQuery` Pydantic models (Phase 3 plugin-private capability shape)

**Step:** Step 3 — TCCM, BundleBuilder, VulnIndex, content-addressed cache
**Status:** Ready
**Effort:** S
**Depends on:** S1-04, S2-01
**ADRs honored:** Phase 3 ADR-0004 (plugin-private capabilities live on TCCM `provides`/`requires`, NOT on the kernel `Plugin` Protocol), production ADR-0029 (Task-Class Context Manifests), production ADR-0030 (graph-aware context queries — fixed primitive set)

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

- [ ] New module `src/codegenie/plugins/tccm.py` exports `ContextQuery`, `TCCM`, `TCCMParseError`. `__all__` pins exactly these three names.
- [ ] `ContextQuery` is a Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields: `primitive: PrimitiveName`, `args: dict[str, str | int | bool | list[str]]` (primitives only — NO `Any`), `fallback: ContextQuery | None = None` (the ADR-0008 declared-fallback seam — fires *only* on `AdapterConfidence.Degraded | Unavailable`), `max_files: int | None = None` (ADR-0030 bound).
- [ ] `ContextQuery.primitive` validation: smart-constructor `ContextQuery.create(primitive: str, args: dict, ...) -> Result[ContextQuery, TCCMParseError]` rejects any `primitive` not in the **fixed** ADR-0030 set: `{"scip.refs", "import_graph.reverse_lookup", "import_graph.transitive_callers", "dep_graph.consumers", "test_inventory.tests_exercising"}`. The set lives in a module-level `Final[frozenset[PrimitiveName]]` named `_KNOWN_PRIMITIVES` so future adapter ADRs grow it by addition, not by edit.
- [ ] `TCCM` is a Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields: `must_read: list[ContextQuery]` (required, no default), `should_read: list[ContextQuery] = []`, `may_read: list[ContextQuery] = []`, `provides: dict[str, dict[str, str]] = {}`, `requires: dict[str, list[str]] = {}`.
- [ ] `provides` value-shape validation: every key in the outer map matches `^[a-z][a-z0-9_]*$` (capability namespace; e.g. `vuln_index_capabilities`); every key in the inner map matches `^[a-z][a-z0-9_]*$` (capability name; e.g. `nvd_parser`); every value matches `^[a-zA-Z_][a-zA-Z0-9_.]*:[A-Z][a-zA-Z0-9_]*$` (`module.path:ClassName` import-path shape, per ADR-0004 §Consequences "broken imports surface at plugin load time"). On any violation, `TCCM.model_validate(...)` raises `pydantic.ValidationError` with `loc` pointing at the offending key path.
- [ ] `requires` value-shape validation: every outer key and every list element match `^[a-z][a-z0-9_]*$` (same namespace grammar). Empty lists are allowed (a namespace can declare "I require *this* namespace but no specific names yet").
- [ ] `ContextQuery.create(...)` returns `Result.err(TCCMParseError(reason="unknown_primitive", primitive=...))` on a primitive miss; `Result.err(TCCMParseError(reason="negative_max_files", max_files=...))` when `max_files is not None and max_files <= 0`. `TCCMParseError` extends `CodegenieError` (markers-only per repo discipline).
- [ ] Round-trip: a hand-built `TCCM` instance serializes via `model_dump()` to a dict and `TCCM.model_validate(...)` returns an equal instance (frozen-equal); deeply nested `provides` / `requires` survive.
- [ ] Property test: any `provides` namespace key NOT matching `^[a-z][a-z0-9_]*$` (Hypothesis strategy over invalid chars + leading-digit + uppercase) is rejected.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean. AST source-scan: `codegenie.plugins.tccm` imports from `pydantic`, `typing`, `codegenie.types.identifiers`, `codegenie.result`, `codegenie.errors` ONLY — no other Phase 3 module, no I/O, no logger.

## Implementation outline

1. Create `src/codegenie/plugins/__init__.py` (empty; Phase 3 plugins package home).
2. Create `src/codegenie/plugins/tccm.py`:
   - Import `PrimitiveName`, `PluginId` from `codegenie.types.identifiers`.
   - Define module-level `_KNOWN_PRIMITIVES: Final[frozenset[PrimitiveName]]` with the 5 ADR-0030 primitives.
   - Define `_NAMESPACE_RE = re.compile(r"^[a-z][a-z0-9_]*$")` and `_IMPORT_PATH_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*:[A-Z][a-zA-Z0-9_]*$")`.
   - Define `class TCCMParseError(CodegenieError)` markers-only (carry `reason: str` and `**details` in message).
   - Define `class ContextQuery(BaseModel)` with the field set above. Add a `@field_validator("primitive")` that calls `_KNOWN_PRIMITIVES` membership check (raises `ValueError` → Pydantic converts to `ValidationError`). Add a `@field_validator("max_files")` that rejects `<= 0`.
   - Add classmethod `ContextQuery.create(...) -> Result[ContextQuery, TCCMParseError]` that catches `ValidationError` and maps to `Result.err`.
   - Define `class TCCM(BaseModel)` with `@field_validator("provides")` walking the nested dict against `_NAMESPACE_RE` + `_IMPORT_PATH_RE`, `@field_validator("requires")` walking outer/inner keys against `_NAMESPACE_RE`.
3. Add a fence assertion at module import: `assert all(_NAMESPACE_RE.match(p.split(".")[0]) for p in _KNOWN_PRIMITIVES), "primitive grammar drift"`. Use `raise AssertionError(...)` form (bare `assert` is banned by the forbidden-patterns hook).
4. `__all__ = ("ContextQuery", "TCCM", "TCCMParseError")`.

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/plugins/test_tccm_models.py`

```python
import pytest
from pydantic import ValidationError
from codegenie.plugins.tccm import ContextQuery, TCCM, TCCMParseError
from codegenie.types.identifiers import PrimitiveName

class TestContextQuery:
    def test_known_primitive_accepted(self):
        # Arrange: ADR-0030's `scip.refs` is a known primitive
        # Act
        result = ContextQuery.create(primitive="scip.refs", args={"symbol": "express.urlencoded"})
        # Assert: smart ctor returns Ok with the typed instance
        assert result.is_ok()
        assert result.unwrap().primitive == "scip.refs"

    def test_unknown_primitive_rejected(self):
        # Arrange: ADR-0030 set is closed; rogue primitive is a parse error
        result = ContextQuery.create(primitive="grep.adhoc", args={})
        assert result.is_err()
        assert result.unwrap_err().reason == "unknown_primitive"

    def test_negative_max_files_rejected(self):
        result = ContextQuery.create(primitive="scip.refs", args={}, max_files=0)
        assert result.is_err() and result.unwrap_err().reason == "negative_max_files"

    def test_fallback_is_recursive_context_query(self):
        # The fallback chain (ADR-0008 declared serial fallback) is typed all the way down
        primary = ContextQuery.create(
            primitive="scip.refs", args={"symbol": "x"},
            fallback=ContextQuery.create(primitive="dep_graph.consumers", args={"pkg": "x"}).unwrap(),
        ).unwrap()
        assert primary.fallback is not None
        assert primary.fallback.primitive == "dep_graph.consumers"

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            ContextQuery.model_validate({"primitive": "scip.refs", "args": {}, "rogue": "x"})

class TestTCCM:
    def test_provides_namespace_grammar_enforced(self):
        # Capability namespace must be ^[a-z][a-z0-9_]*$ per ADR-0004 §Consequences
        with pytest.raises(ValidationError):
            TCCM.model_validate({
                "must_read": [{"primitive": "scip.refs", "args": {}}],
                "provides": {"Vuln-Index": {"nvd": "api:NvdParser"}},   # uppercase + hyphen — invalid
            })

    def test_provides_import_path_grammar_enforced(self):
        # Value must match module:ClassName per ADR-0004 (broken imports fail fast at plugin load)
        with pytest.raises(ValidationError):
            TCCM.model_validate({
                "must_read": [{"primitive": "scip.refs", "args": {}}],
                "provides": {"vuln_index_capabilities": {"nvd_parser": "no_colon_here"}},
            })

    def test_requires_namespace_grammar_enforced(self):
        with pytest.raises(ValidationError):
            TCCM.model_validate({
                "must_read": [{"primitive": "scip.refs", "args": {}}],
                "requires": {"valid_ns": ["BadName"]},
            })

    def test_vuln_plugin_shape_round_trips(self):
        # ADR-0004 §Consequences example: vuln plugin declares vuln_index_capabilities
        original = TCCM.model_validate({
            "must_read": [{"primitive": "dep_graph.consumers", "args": {"pkg": "express"}}],
            "should_read": [{"primitive": "test_inventory.tests_exercising", "args": {"symbol": "urlencoded"}}],
            "may_read": [],
            "provides": {"vuln_index_capabilities": {
                "nvd_parser": "codegenie.vuln_index.parsers:NvdParser",
                "ghsa_parser": "codegenie.vuln_index.parsers:GhsaParser",
                "osv_parser": "codegenie.vuln_index.parsers:OsvParser",
            }},
            "requires": {},
        })
        assert TCCM.model_validate(original.model_dump()) == original

    def test_must_read_required(self):
        # must_read has no default; missing it is an error (ADR-0029 priority bands)
        with pytest.raises(ValidationError):
            TCCM.model_validate({"should_read": []})
```

Property test (`tests/property/plugins/test_tccm_namespace_grammar.py`):

```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1).filter(lambda s: not re.fullmatch(r"[a-z][a-z0-9_]*", s)))
def test_invalid_namespace_always_rejected(bad_ns):
    with pytest.raises(ValidationError):
        TCCM.model_validate({
            "must_read": [{"primitive": "scip.refs", "args": {}}],
            "provides": {bad_ns: {"nvd_parser": "x:Y"}},
        })
```

### Green

Smallest impl: §Implementation outline; ~110 lines.

### Refactor

- Lift `_NAMESPACE_RE` and `_IMPORT_PATH_RE` to module-level `Final[re.Pattern[str]]`; tests assert their compilation at import time (`assert _NAMESPACE_RE.pattern == "^[a-z][a-z0-9_]*$"`).
- Add docstrings citing ADR-0004 §Consequences for `provides` and ADR-0030 §Initial query primitives for `_KNOWN_PRIMITIVES`.
- Consider lifting the dict-walking validator to a small `_validate_nested_str_map(value, key_re, leaf_re) -> dict[...]` helper; reused for `provides` and `requires`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/__init__.py` | New package — Phase 3 plugins module home (empty file with module docstring) |
| `src/codegenie/plugins/tccm.py` | New module — `ContextQuery`, `TCCM`, `TCCMParseError` |
| `tests/unit/plugins/test_tccm_models.py` | Red tests covering all ACs |
| `tests/property/plugins/test_tccm_namespace_grammar.py` | Hypothesis property over namespace grammar |
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
- **`_KNOWN_PRIMITIVES` is closed by design.** Adding a primitive is an ADR amendment to production ADR-0030 + one line here. Do NOT add wildcards or `*`-matching; that defeats the "small, stable DSL" commitment.
- **`fallback: ContextQuery | None`** — Pydantic supports forward references; if you hit `NameError`, use `from __future__ import annotations` + `model_rebuild()` (or wrap the type as `"ContextQuery"`). Either is fine; pick one and stay consistent.
- **`args: dict[str, str | int | bool | list[str]]`** — primitives only, no nested dicts, matching the discipline used for `TrustSignal.details` (phase-arch-design §Data model). Reject `Any`; reviewers will hold the line.
- **`frozen=True`** matters — `ContextQuery` instances will live in cache keys; hashability matters. Verify `hash(ContextQuery.create(...).unwrap())` works (Pydantic v2 frozen models are hashable by field values).
- **Do NOT register `TCCM` with anything yet** — this story is types only. S2-02 loads from YAML; S3-04 consumes for query dispatch.
