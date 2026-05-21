# Story S8-03 — Loader explicit-import + `compute:` resolver + `api.py` side-effect registration

**Step:** Step 8 — `DistrolessMigrationPlugin` manifest + TCCM `derived_queries:` band + plugin loader wiring
**Status:** Ready
**Effort:** M
**Depends on:** S8-02 (the `DerivedQuery` schema must exist before the loader can resolve `compute:` strings against it)
**ADRs honored:** Phase 7 ADR-0016 (TCCM `derived_queries:` band — primary; resolver half of the ADR's load-bearing commitment), Phase 7 ADR-0009 row #7 (the one new explicit-import line in `src/codegenie/plugins/loader.py` is the enumerated byte-edit), Phase 7 ADR-0001 (single-task-class plugin), Phase 7 ADR-0005 (probes and adapters under the plugin tree register via decorator side-effects from `api.py`), Phase 7 ADR-0004 (typed `compute:` resolution surface — fail loud on unknown), production ADR-0031 (plugin loader contract — `register_plugin(...)` side-effect at import time)

> **⚠ Amendment A sequencing note (2026-05-20).** Phase 7 Amendment A ([`../final-design.md` §Amendment A](../final-design.md)) adds six gather probes (Steps 13–15) whose `api.py` side-effect registration the loader must also collect. Coordinate with [S13-03](S13-03-amendment-a-schemas-and-fence.md) and the Step 15 probe stories. See [`README.md` §"Stories — Amendment A"](README.md).

## Context

S8-02 added the `DerivedQuery` Pydantic shape; it validates the *string* shape of `compute:` but does not resolve it to a callable. This story closes the loop:

1. **Loader explicit-import line** in `src/codegenie/plugins/loader.py` — Phase 7 ADR-0009 row #7. The existing loader does dynamic `importlib.import_module(f"plugins.{slug}.api")` walks; the additive change is an explicit `import plugins.distroless_migration__node__npm.api as _distroless_migration_api  # noqa: F401` (exact module path TBD by the project's `plugins/` package layout convention) — or, if the project uses `importlib`-only style, the byte-edit is the registration of the migration plugin's slug in a tuple of known plugins. Read the existing loader end-to-end first to pin which convention applies.
2. **`compute:` resolver** — when the loader loads a plugin's `tccm.yaml` and the YAML carries `derived_queries:` entries, resolve each `compute:` dotted string to an imported Python callable at plugin-load time. Unknown reference → loader fails fast with file/line diagnostic and the Supervisor refuses to start.
3. **`plugins/distroless-migration--node--npm/api.py`** — declares the plugin instance and imports adapters + probes + recipes for side-effect registration (`@register_provenance_adapter`, `@register_probe`, `@register_signal_kind` decorators fire). This mirrors the Phase 3 plugin's `api.py` pattern.

The `compute:` vocabulary in Phase 7 is closed-by-design at exactly one entry: `vuln.provenance` → `codegenie.primitives.vuln_provenance.provenance` (the thin-wrapper callable established by Step 1's High-level-impl line 75). Future task classes adding `compute:` vocabulary words (Phase 8's `dep_chain.distance`, etc.) is an additive event with its own ADR per ADR-0016 §Consequences row 6.

**Why fail loud on unknown `compute:`:** if `compute: vuln.provence` (typo) silently resolved to `None` and the dispatch path quietly skipped the derived query, the migration plugin's TCCM would index zero provenance evidence — the Planner would route blind. ADR-0016 §Consequences row 3 names this: "Unknown reference → load-time failure with file/line diagnostic; Supervisor refuses to start."

**Why side-effect registration in `api.py`:** Phase 3 ADR-0005 plus production ADR-0031 commit to "plugins register via decorator side-effects from `import plugins.{slug}.api`." The plugin's adapters, probes, and recipes all carry decorators; importing `api.py` fires them in one explicit hop. Phase 7 ADR-0005 inherits this convention.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §Component design §11 (DistrolessMigrationPlugin) / §13 (TCCM band)`](../phase-arch-design.md) — `api.py` shape + `compute:` resolver.
  - [`../phase-arch-design.md §Process view`](../phase-arch-design.md) — sequence: plugin-load → `compute:` resolver → register decorators fire.
- **Phase ADRs:**
  - [`../ADRs/0016-tccm-derived-queries-band.md`](../ADRs/0016-tccm-derived-queries-band.md) — **primary**; §Consequences rows 3–5 pin the resolver behavior.
  - [`../ADRs/0009-phase-7-byte-edit-allowlist-fence.md`](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — row #7 (loader explicit-import).
  - [`../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md`](../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md) — single-task-class.
  - [`../ADRs/0005-probes-live-under-plugin-not-core-tree.md`](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) — `api.py` is where the decorator side-effects fire.
- **Production ADRs:**
  - [`../../../production/adrs/0031-plugin-architecture.md`](../../../production/adrs/0031-plugin-architecture.md) — `register_plugin(...)` + `importlib.import_module("plugins.{slug}.api")`.
- **High-level impl:**
  - [`../High-level-impl.md §Step 8`](../High-level-impl.md) — Features delivered bullets 4–6.
- **Source:**
  - [`src/codegenie/plugins/loader.py`](../../../../src/codegenie/plugins/loader.py) — existing loader. The `importlib.import_module(f"plugins.{slug}.api")` line is the load-bearing seam (line 291).
  - [`src/codegenie/plugins/tccm.py`](../../../../src/codegenie/plugins/tccm.py) — post-S8-02 with `DerivedQuery` + `derived_queries:` band.
  - Phase 3 plugin `api.py` precedent (if it has landed yet) — match its shape.

## Goal

Ship three things — exactly:

1. **Allowlist row #7 byte-edit** to `src/codegenie/plugins/loader.py`: add an explicit `import plugins.distroless_migration__node__npm.api  # noqa: F401` (or the equivalent project-canonical form — see Notes). The dynamic `importlib.import_module(f"plugins.{slug}.api")` line in `_register_plugins()` continues to drive the general loader path; the explicit import is the fence-enumerated "wiring" that Phase 7 ADR-0009 row #7 authorizes.
2. **`compute:` resolver** — a new function in `src/codegenie/plugins/tccm.py` (or a sibling module under `src/codegenie/plugins/`) that takes a loaded `Tccm.derived_queries` list plus a closed-set vocabulary mapping (Phase 7 ships `{"vuln.provenance": codegenie.primitives.vuln_provenance.provenance}`) and resolves each entry's `compute:` to the imported callable. Unknown `compute:` → `Err(UnknownDerivedCompute(...))` (a new typed error variant alongside the existing `TCCMParseError`). Loader translates this to `PluginRejected` so the Supervisor refuses to start.
3. **`plugins/distroless-migration--node--npm/api.py`** — module that:
   - Declares the plugin instance (`PLUGIN_ID = PluginId("distroless-migration--node--npm")`).
   - Imports `from . import adapters, probes, recipes  # noqa: F401` so the `@register_provenance_adapter` / `@register_probe` / `@register_signal_kind` decorators fire.
   - Defines `register_plugin(registry)` if the Phase 3 precedent uses that shape; otherwise the import side-effect alone is sufficient (read the Phase 3 plugin's `api.py` and mirror).

The TCCM YAML content + the resolution integration test belong to **S8-04**. This story proves the loader + resolver + api.py shape work in isolation against an in-test-tree TCCM fixture; S8-04 proves it works end-to-end against the real plugin tree.

## Acceptance criteria

### A. Loader explicit-import line lands

- [ ] `src/codegenie/plugins/loader.py` has exactly one new line: an explicit `import plugins.distroless_migration__node__npm.api  # noqa: F401` (or the equivalent project-canonical form — confirm naming convention against any Phase 3 precedent or the explicit-import patterns in `src/codegenie/probes/__init__.py`).
- [ ] The new line is placed alongside any existing per-plugin explicit imports (matching the file's convention); if no precedent exists yet, place it after the imports block, before the first function/class definition, with a `# Phase 7 ADR-0009 row #7` inline comment.
- [ ] No other byte-edits to `loader.py` — the existing dynamic `importlib.import_module(f"plugins.{slug}.api")` line at line ~291 is byte-unchanged.

### B. `compute:` resolver behavior

- [ ] A new function `resolve_derived_queries(queries: list[DerivedQuery], *, vocabulary: Mapping[str, Callable[..., Any]]) -> Result[list[ResolvedDerivedQuery], UnknownDerivedCompute]` (exact name + signature pinned in the test) exists in `src/codegenie/plugins/tccm.py` (or a sibling). The exact location is the implementer's call as long as the public surface is `from codegenie.plugins.tccm import resolve_derived_queries`.
- [ ] `ResolvedDerivedQuery` is a frozen Pydantic model with fields `name: str`, `callable: Callable[..., Any]` (typed via `Callable[..., Any]` — the in-band callable shape is dynamic by design), `args: dict[str, str]`. `model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)` (callable is not a Pydantic-known type).
- [ ] `UnknownDerivedCompute` is a frozen Pydantic model `BaseModel` (mirrors `TCCMParseError` precedent) with fields `compute: str`, `name: str` (the `derived_queries[].name` for diagnostics), `known_vocabulary: tuple[str, ...]`. NOT a `CodegenieError` subclass.
- [ ] Resolving an entry whose `compute:` is in `vocabulary` returns `Ok([ResolvedDerivedQuery(...)])` with `callable is vocabulary[compute]`.
- [ ] Resolving an entry whose `compute:` is NOT in `vocabulary` returns `Err(UnknownDerivedCompute(compute=..., name=..., known_vocabulary=tuple(sorted(vocabulary.keys()))))`.
- [ ] Resolving an empty list returns `Ok([])` (the `derived_queries: []` case).
- [ ] The resolver does NOT execute the callable; it only resolves the reference.
- [ ] The resolver does NOT substitute the template tokens (`$workflow.cve`); template substitution is dispatch-time, not load-time.

### C. Phase 7 vocabulary seed

- [ ] A module-level `Final[dict[str, Callable[..., Any]]] _PHASE7_VOCABULARY` exists somewhere (`src/codegenie/plugins/tccm.py` or `src/codegenie/plugins/derived_queries.py` — implementer's call; pin the import path in tests).
- [ ] The vocabulary has exactly one entry: `"vuln.provenance"` → `codegenie.primitives.vuln_provenance.provenance` (the thin-wrapper callable established by Step 1 — High-level-impl line 75).
- [ ] A unit test asserts `_PHASE7_VOCABULARY["vuln.provenance"] is codegenie.primitives.vuln_provenance.provenance`.
- [ ] A unit test asserts `len(_PHASE7_VOCABULARY) == 1` — cardinality pin so a future stealth fourth entry fails CI.

### D. Loader wiring — `register_plugin` calls resolver

- [ ] The loader's plugin-load path (`load_plugins(...)` or the post-import `register_plugin(...)` hook) calls `resolve_derived_queries(tccm.derived_queries, vocabulary=_PHASE7_VOCABULARY)` for each plugin's TCCM. (The exact integration point depends on how the existing loader composes; the test fixture in S8-04 will exercise the full path.)
- [ ] An integration test (or a focused unit test with a minimal plugin tree fixture under `tests/fixtures/`) covers: (i) plugin with valid `compute:` → loader returns `Ok(LoadReport(...))` and resolver state shows the callable; (ii) plugin with unknown `compute:` → loader returns `Err(PluginRejected(...))` whose message names the file path, `derived_queries[].name`, and the unknown `compute:` string.
- [ ] The Supervisor (or whatever top-level callsite the project uses) propagates the `Err(...)` and exits non-zero. If the Supervisor wiring is owned by a later story, this AC degrades to "the loader returns `Err(...)` cleanly; an integration test in S8-04 asserts Supervisor refusal."

### E. `plugins/distroless-migration--node--npm/api.py` exists

- [ ] `plugins/distroless-migration--node--npm/api.py` exists.
- [ ] The module is importable (`importlib.import_module("plugins.distroless_migration__node__npm.api")` — exact path matches the project's `plugins/` package layout convention).
- [ ] The module imports `from . import probes  # noqa: F401` (or the equivalent for whichever subpackages exist post-S4-02, S4-03, S7-01, S7-02). The decorators fire on import.
- [ ] The module exports `PLUGIN_ID: Final[PluginId]` with value `PluginId("distroless-migration--node--npm")`.
- [ ] If Phase 3's `api.py` precedent defines a `register_plugin(registry)` function, this module mirrors that shape. If the convention is import-side-effect-only, do not invent a function.

### F. Backward-compat — no Phase 0–6.5 regression

- [ ] Existing plugins (Phase 3's `vulnerability-remediation--node--npm`, etc.) continue to load. The dynamic `importlib.import_module(f"plugins.{slug}.api")` path is unchanged.
- [ ] TCCMs without `derived_queries:` (or with empty `derived_queries: []`) load without invoking the resolver path (or invoke it as a no-op).
- [ ] **Phase 3–6.5 regression suite green; `bench/vuln-remediation/` cassette replay byte-equal (ε ≤ $0.01).**

### G. Lint + fence gates

- [ ] `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py` passes; row #7 (`src/codegenie/plugins/loader.py`) increments by exactly one allowed line.
- [ ] A deliberately-planted second edit to `loader.py` (e.g., an unrelated whitespace change) fails the fence.
- [ ] `mypy --strict src/codegenie/plugins/ plugins/distroless-migration--node--npm/` clean.
- [ ] `ruff check` + `ruff format --check` clean.
- [ ] `make lint-imports` green — the primitive imports cleanly; the plugin imports only from the primitive surface, never the other way.
- [ ] `make check` green.

## Implementation outline

1. **Read `src/codegenie/plugins/loader.py` end-to-end.** Confirm the `_register_plugins(...)` shape, the `importlib.import_module` line at ~291, and any existing per-plugin explicit imports. If Phase 3's plugin has an explicit-import precedent, mirror its style; otherwise pick a stable insertion point.
2. **Read `src/codegenie/plugins/tccm.py`** (post-S8-02). Decide whether the resolver lives in the same module or a sibling `derived_queries.py`. The Phase 3 precedent for `loader.py` (single big file) suggests keeping it adjacent — implementer's call.
3. **Add `class UnknownDerivedCompute(BaseModel)`** to `tccm.py` (mirroring `TCCMParseError`). `frozen=True, extra="forbid"`.
4. **Add `class ResolvedDerivedQuery(BaseModel)`** — `frozen=True, extra="forbid", arbitrary_types_allowed=True`.
5. **Add `_PHASE7_VOCABULARY: Final[Mapping[str, Callable[..., Any]]]`** with the one entry. Place at module level.
6. **Add `resolve_derived_queries(...)`** — pure function; walks the list, looks up each `compute:` in `vocabulary`, returns `Result[list[ResolvedDerivedQuery], UnknownDerivedCompute]` (first failure short-circuits per Rule 12 — fail loud; the diagnostic names the first bad entry).
7. **Wire the resolver into `loader.py`'s plugin-load path.** Where TCCM is loaded today (or where Phase 3 plans to load it), call `resolve_derived_queries(...)` and translate `Err` to `PluginRejected(...)`.
8. **Add the explicit-import line** to `loader.py`. Allowlist row #7. ONE line.
9. **Create `plugins/distroless-migration--node--npm/api.py`** — declare `PLUGIN_ID`, import the subpackages for side-effect registration.
10. **Write the test files** — see TDD plan.
11. **Run `make check`** — green.

## TDD plan (red → green → refactor)

### Red — write `tests/unit/plugins/test_derived_queries_resolver.py` first

```python
"""S8-03 — resolve_derived_queries + Phase 7 vocabulary + unknown-compute failure."""

from __future__ import annotations

import pytest

from codegenie.plugins.tccm import (
    DerivedQuery,
    ResolvedDerivedQuery,
    UnknownDerivedCompute,
    _PHASE7_VOCABULARY,
    resolve_derived_queries,
)
from codegenie.primitives.vuln_provenance import provenance as _provenance_callable


class TestPhase7Vocabulary:
    def test_vocabulary_size_pinned(self) -> None:
        assert len(_PHASE7_VOCABULARY) == 1

    def test_vuln_provenance_points_to_primitive(self) -> None:
        assert _PHASE7_VOCABULARY["vuln.provenance"] is _provenance_callable


class TestResolverHappyPath:
    def test_empty_list_returns_ok_empty(self) -> None:
        out = resolve_derived_queries([], vocabulary=_PHASE7_VOCABULARY).unwrap()
        assert out == []

    def test_single_known_compute_resolves(self) -> None:
        dq = DerivedQuery(
            name="provenance",
            compute="vuln.provenance",
            args={"cve_id": "$workflow.cve"},
        )
        out = resolve_derived_queries([dq], vocabulary=_PHASE7_VOCABULARY).unwrap()
        assert len(out) == 1
        resolved = out[0]
        assert isinstance(resolved, ResolvedDerivedQuery)
        assert resolved.name == "provenance"
        assert resolved.callable is _provenance_callable
        assert resolved.args == {"cve_id": "$workflow.cve"}

    def test_resolver_does_not_invoke_callable(self) -> None:
        # Pinning the boundary: resolver resolves references; dispatch
        # invokes. A regression that eagerly calls would explode here.
        dq = DerivedQuery(name="x", compute="vuln.provenance", args={})
        resolve_derived_queries([dq], vocabulary=_PHASE7_VOCABULARY).unwrap()


class TestResolverFailFast:
    def test_unknown_compute_yields_err(self) -> None:
        dq = DerivedQuery(name="provence", compute="vuln.provence", args={})  # typo
        result = resolve_derived_queries([dq], vocabulary=_PHASE7_VOCABULARY)
        assert result.is_err()
        err = result.error
        assert isinstance(err, UnknownDerivedCompute)
        assert err.compute == "vuln.provence"
        assert err.name == "provence"
        assert "vuln.provenance" in err.known_vocabulary

    def test_first_unknown_short_circuits(self) -> None:
        good = DerivedQuery(name="good", compute="vuln.provenance", args={})
        bad = DerivedQuery(name="bad", compute="vuln.nope", args={})
        result = resolve_derived_queries([good, bad], vocabulary=_PHASE7_VOCABULARY)
        # Either: ok first, fail second; OR: short-circuit and fail with
        # bad's name. The spec says fail-loud at first unknown.
        assert result.is_err()
        assert result.error.name == "bad"


class TestUnknownDerivedComputeShape:
    def test_frozen(self) -> None:
        err = UnknownDerivedCompute(
            compute="x.y", name="n", known_vocabulary=("a.b",)
        )
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            err.compute = "z.w"  # type: ignore[misc]
```

And `tests/unit/plugins/distroless_migration_node_npm/test_api_module_loads.py`:

```python
"""S8-03 — plugins/distroless-migration--node--npm/api.py is importable."""

from __future__ import annotations

import importlib

from codegenie.types.identifiers import PluginId


def test_api_module_importable() -> None:
    # The exact module path follows the project's plugins/ package layout.
    mod = importlib.import_module("plugins.distroless_migration__node__npm.api")
    assert mod.PLUGIN_ID == PluginId("distroless-migration--node--npm")
```

Run — fails because `resolve_derived_queries`, `_PHASE7_VOCABULARY`, `api.py` don't exist. That's red.

### Green — minimum implementation

Add the resolver, the vocabulary constant, the loader explicit-import line, and `plugins/distroless-migration--node--npm/api.py`. Re-run; all tests pass.

### Refactor

- Confirm `resolve_derived_queries` is < 30 LOC; pure function; no I/O.
- Confirm `_PHASE7_VOCABULARY` is `Final` and frozen at module load.
- Confirm `api.py` is < 20 LOC — declare `PLUGIN_ID`, import subpackages for side-effects, done.
- Re-read `loader.py`'s new explicit-import line; confirm exactly ONE line was added.

## Files to touch

- `src/codegenie/plugins/tccm.py` — additive: `_PHASE7_VOCABULARY`, `UnknownDerivedCompute`, `ResolvedDerivedQuery`, `resolve_derived_queries(...)`. NOT a byte-edit-allowlist row — these are new symbols, the existing fields are byte-unchanged. (S8-02 already consumed row #6's edit; this story's additions are part of the same "one additive band" event.)
- `src/codegenie/plugins/loader.py` — exactly one new explicit-import line (allowlist row #7). Plus, where the TCCM is loaded, call `resolve_derived_queries(...)` and translate `Err` to `PluginRejected`.
- `plugins/distroless-migration--node--npm/api.py` — new file.
- `plugins/distroless-migration--node--npm/__init__.py` — new (empty) package marker if not present.
- `tests/unit/plugins/test_derived_queries_resolver.py` — new test file.
- `tests/unit/plugins/distroless_migration_node_npm/test_api_module_loads.py` — new test file.

## Out of scope

- The `plugins/distroless-migration--node--npm/tccm.yaml` content — **S8-04**.
- The `tests/integration/test_plugin_resolution_phase7.py` end-to-end resolution test — **S8-04**.
- Substituting template tokens (`$workflow.cve` → concrete CVE id) at dispatch time — a Phase 7 orchestrator concern; the substitution callable lives near `assemble_provenance(...)` (S2-04) or in a thin Phase 7 dispatch helper (out of scope for this story).
- Adding `vuln.provenance` to Phase 3's `plugins/vulnerability-remediation--node--npm/tccm.yaml` — allowlist row #2; separate story.
- Editing `src/codegenie/plugins/manifest.py` — schema unchanged.
- Sigstore-bundled callable signing / verification — Phase 11 (production ADR-0036 deferred).

## Notes for the implementer

- **Module path naming:** the directory is `plugins/distroless-migration--node--npm/` (hyphens), but Python module paths cannot use hyphens. The conventional translation is `plugins.distroless_migration__node__npm` (hyphens → underscores; double-hyphens → double-underscores). Read the existing loader at line 291 (`f"plugins.{slug}.api"`) — `slug` is the directory name; the project may either do a hyphen-to-underscore mapping in the loader or use a `setup.py`-style package-name override. Match whatever the Phase 3 plugin's `api.py` path uses. If unsure, ask before guessing (Rule 1).
- **`PLUGINS.lock` precondition:** S5-04 lands the lock entry for this plugin. Until that's green, the loader's `Verify` gate (loader.py line ~17) rejects the plugin as `UnlockedPlugin`. This story's tests should either (a) bypass the lock check by calling `resolve_derived_queries(...)` directly on a hand-built `DerivedQuery` list, or (b) gate the integration-style test on S5-04's completion. S8-04's integration test is the natural place for the full load + resolve path.
- **`UnknownDerivedCompute` vs `PluginRejected`:** the resolver returns the *typed* `UnknownDerivedCompute` (mirrors `TCCMParseError`'s precedent — a Pydantic value error, not a `CodegenieError` exception). The loader translates that at its boundary into `PluginRejected(...)` (the existing `codegenie.plugins.errors` variant). Keep the two layers separate; do not raise from inside `resolve_derived_queries`.
- **Why `Callable[..., Any]`:** the vocabulary holds heterogeneous callables (Phase 8 will add more); typing them precisely would force a Protocol that grows with every new entry. ADR-0016 §Tradeoffs row 4 accepts the dynamic shape; the AST fence in `tests/fence/test_no_any_in_provenance_surface.py` (S1-06) covers the *primitive* surface, not the plugin-loader surface, so this is consistent.
- **Side-effect ordering in `api.py`:** import `adapters` first (registers provenance adapters into `_REGISTRY`), then `probes` (registers probes), then `recipes` (registers gates + transforms). Order matters only if one decorator depends on another's registration; if not, alphabetical is fine. Phase 3 precedent governs.
- **Read `src/codegenie/probes/__init__.py` for the explicit-import style.** CLAUDE.md (Architecture → "Registry-dispatched coordinator") names that file as the canonical explicit-import collection point — `loader.py`'s new line should mirror its style.
- **Failing loud:** if the explicit-import in `loader.py` raises at module import (e.g., the plugin's `api.py` has a typo), `from codegenie.plugins.loader import load_plugins` itself will fail. That's the desired behavior — ADR-0016 §Consequences row 3 ("Supervisor refuses to start") is satisfied by Python's import-time error propagation; the loader does not need to swallow.
- **Do not pre-substitute template tokens in the resolver.** A future implementer may be tempted to substitute `$workflow.cve` at resolve time using a stub workflow context. Resist: template tokens may reference values that exist only at dispatch time. The resolver's contract is "lookup the callable + carry the args dict forward unchanged." Add an explicit AC assertion (`args == {"cve_id": "$workflow.cve"}`) as a regression pin.
