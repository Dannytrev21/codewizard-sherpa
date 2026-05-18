# Story S2-01 — PluginRegistry kernel + Plugin/Adapter/RecipeEngine Protocols

**Step:** Step 2 — Plugin Registry kernel, manifest schema, loader, resolver
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-01 (`PluginId`, `PluginScope`), S1-02 (`PluginScope.parse`)
**ADRs honored:** ADR-0002, ADR-0004, ADR-0010, ADR-0011 (framing only — `PLUGINS.lock` rejection raised by loader in S2-03), production ADR-0031

## Validation notes (2026-05-18)

Hardened by `phase-story-validator` (see `_validation/S2-01-plugin-registry-kernel.md` for full audit). Key changes:

- Closed the `PluginResolution` symbol gap (S2-04 owns the sum type) by shipping a minimal placeholder `src/codegenie/plugins/resolution.py` here so `mypy --strict` resolves the `resolve()` return annotation today (Consistency F1).
- Pinned the fence-test introspection mechanism — `Protocol` doesn't populate `__abstractmethods__`; AC-7 now uses `dir(Plugin) - dunders` + `__annotations__` (Test-Quality F10 / Consistency F6).
- Made every previously prose-only test concrete with named identities, mutation-resistant assertions, and explicit fixture cleanup (Test-Quality F1–F6, F10).
- Mandated typed `.name: PluginId` attributes on `PluginAlreadyRegistered` / `PluginNotRegistered` so loader S2-03 and exit-code-4 formatters consume a structured field, not an `args[0]` string (Coverage F6, Test-Quality F4/F6).
- Specified the `make_fake_plugin` fixture shape inline so the executor doesn't improvise; the single `PluginId(str)` boundary lift lives in the fixture (Test-Quality F8, Consistency F9).
- Reduced `Adapter` Protocol to one attribute (no methods this story); freezing deferred to S7 (Design F3, Coverage F8, Consistency F8).
- Added the 4th-registry rule-of-three observation as a `Notes` paragraph + module docstring, mirroring `depgraph/registry.py:30-38` so the kernel-extract opportunity survives (Design F1).
- Added `tests/fence/__init__.py` to Files-to-touch — S2-01 is the first story to populate `tests/fence/` (Consistency F5).

## Context

Step 2 lands the closed-for-modification ADR-0031 kernel that every Phase 3+ plugin slots into. This story is the **kernel split**: the **Protocols plugins implement** (`Plugin`, `Adapter`, `RecipeEngine`) live in `src/codegenie/plugins/protocols.py`, and the **kernel that holds them** (`PluginRegistry` + module-level `default_registry` + `register_plugin` helper) lives in `src/codegenie/plugins/registry.py`. Mirrors the three existing decorator-registry precedents in this codebase (`src/codegenie/probes/registry.py`, `src/codegenie/indices/registry.py`, `src/codegenie/depgraph/registry.py`) — same `default_registry` placement, same fresh-instance fixture story, same typed collision exception. The four-method `Plugin` surface (`manifest`, `build_subgraph`, `adapters`, `transforms`) is the load-bearing freeze ADR-0004 names; the fence test in this story is the structural enforcement.

This story ships **only the kernel** — `register`, `get`, `all` are real; `resolve` ships as a typed stub that raises `NotImplementedError("resolved in S2-04")`. Manifest parsing (S2-02), integrity-checked filesystem loading (S2-03), and the resolver/extends/fallback algorithm (S2-04) all sit downstream. `src/codegenie/plugins/resolution.py` ships here with a minimal placeholder `class PluginResolution: ...` so the `resolve()` return-type annotation resolves under `mypy --strict` today; S2-04 expands the placeholder into the `ConcreteResolution | UniversalFallbackResolution` sum type per `S1-03-tagged-union-outcomes.md:378`.

**Scope reminder.** `High-level-impl.md` Step 2's done-criteria are the **union** of S2-01..S2-04. S2-01 owns: register/get/all + Protocol declarations + collision/isolation tests + Plugin fence test. Resolver / loader / `PLUGINS.lock` / property-tested resolution totality belong to S2-03 / S2-04.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C2` — public interface for `Plugin`, `PluginRegistry`, `default_registry`, `register_plugin`; failure modes (`PluginAlreadyRegistered`, exit code 4). NOTE: arch line 466 declares `register(self, plugin: Plugin) -> None`; this story tightens to `-> Plugin` per the `probes/registry.py:139` precedent (and to make `register_plugin`'s `return plugin` natural) — Notes §3 captures the divergence.
  - `../phase-arch-design.md §Design patterns applied row 1` — Registry pattern; per-test fresh-instance isolation.
  - `../phase-arch-design.md §Patterns considered and deliberately rejected` — "No DI container"; "No module-level mutable singleton".
  - `../phase-arch-design.md §Anti-patterns avoided` rows — "Side effects in constructors / module import time"; "Stringly-typed identifiers".
- **Phase ADRs:**
  - `../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md` — Option C is the decision; `default_registry` is a module-level `PluginRegistry` *instance*, not a `dict`; `@register_plugin(plugin, *, registry=None)` is the helper shape; tests pass fresh `PluginRegistry()` instances.
  - `../ADRs/0004-plugin-private-capabilities-via-tccm.md` — the `Plugin` Protocol surface is **exactly four** members (`manifest`, `build_subgraph`, `adapters`, `transforms`); no `cve_feed_parsers()`. Fence test asserts the count.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — `PluginId` from S1-01; no raw `str` for domain IDs; typed exception payloads.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — framing only (loader S2-03 owns the integrity-check exception).
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` §Plugin manifest, §Discovery and resolution — the umbrella commitment this kernel implements.
- **Existing code (precedent to mirror):**
  - `src/codegenie/probes/registry.py` — class shape, decorator shape, `default_registry` placement, fresh-instance fixture pattern, dual-error message naming both colliding `module.qualname`s (line 154-158). **Mirror its API discipline** verbatim except where the story explicitly notes a divergence (Notes §3).
  - `src/codegenie/indices/registry.py:26-31` — sibling explicit-deferral docstring for the rule-of-three kernel-extract; this story's `registry.py` carries the same paragraph updated to N=4.
  - `src/codegenie/depgraph/registry.py:30-38` — same precedent applied a second time; mirrors verbatim.
  - `tests/unit/test_registry.py` (probes) and `tests/unit/depgraph/test_registry.py` — the canonical test idioms (identity-tuple `all()` assertion, `restore_default_registry` autouse fixture, dual-name collision message).
  - `src/codegenie/result.py` — `Result[T, E]` used by the manifest loader (S2-02 consumer) — referenced here only so `Plugin.manifest` type aligns once S2-02 lands.
  - `src/codegenie/types/identifiers.py` — `PluginId` is added in S1-01; import it.
  - `src/codegenie/probes/base.py` — Protocol/ABC pattern for the "contract is frozen" discipline.
- **Sibling validation framings:**
  - `docs/phases/02-context-gather-layers-b-g/stories/_validation/S1-02-freshness-check-registry.md`, `S1-08-registry-heaviness-runs-last.md`, `S1-10-depgraph-strategy-registry.md` — the established hardening conventions for decorator-registries in this codebase.

## Goal

Ship the Phase 3 plugin kernel: three `Protocol`s (`Plugin`, `Adapter`, `RecipeEngine`) in `protocols.py` (`Plugin`'s surface is fence-frozen here per ADR-0004; `Adapter` and `RecipeEngine` are shipped with the minimum surface this story needs — freezing them is deferred to S5 / S7); one `PluginRegistry` class + `default_registry` instance + `register_plugin` helper in `registry.py`; typed exceptions for collision and lookup failure carrying `.name: PluginId` attributes; per-test fixture isolation enforced by an autouse `default_registry`-snapshot guard.

## Acceptance criteria

- [ ] **AC-1 — Protocol declarations.** `src/codegenie/plugins/protocols.py` exports three `@runtime_checkable` `Protocol`s:
    - `Plugin`: **exactly four** non-dunder member names — `manifest` (attribute, annotated `PluginManifest` behind a `TYPE_CHECKING` forward reference until S2-02 lands the model), `build_subgraph(self, registry: "PluginRegistry") -> "PluginSubgraph"`, `adapters(self) -> dict[PrimitiveName, Adapter]`, `transforms(self) -> dict[TransformKind, RecipeEngine]`. No `cve_feed_parsers`. No other public attributes/methods.
    - `Adapter`: a single attribute `primitive: PrimitiveName`. No methods declared in this story (full surface lands in S7 per ADR-0032). Surface explicitly NOT frozen — Out-of-scope names the deferral.
    - `RecipeEngine`: `kind: TransformKind`; `def applies(self, cve: "CveRecord", bundle: "Bundle") -> "Applicability"`; `async def apply(self, plan: "RecipePlan", ctx: "ApplyContext") -> "RecipeOutcome"`. Bodies stubbed via `...`; full surface fence lands in Step 5.
- [ ] **AC-2 — `PluginRegistry` public surface.** `src/codegenie/plugins/registry.py` exports a `PluginRegistry` class with exactly four public methods:
    - `register(self, plugin: Plugin) -> Plugin` — registers and returns the plugin unchanged. Duplicate `plugin.manifest.name` raises `PluginAlreadyRegistered(name)`.
    - `get(self, name: PluginId) -> Plugin` — returns the registered plugin or raises `PluginNotRegistered(name)`.
    - `all(self) -> tuple[Plugin, ...]` — returns plugins in registration order, as an immutable tuple.
    - `resolve(self, scope: "PluginScope") -> "PluginResolution"` — raises `NotImplementedError`; `"S2-04"` MUST appear in `str(exc)` (this is the forward-reference contract S2-04's executor will grep on).
- [ ] **AC-3 — `register_plugin` helper.** `register_plugin(plugin: Plugin, *, registry: PluginRegistry | None = None) -> Plugin`:
    - Returns the **same** `plugin` instance (`assert register_plugin(p, registry=r) is p`).
    - With `registry=None`, mutates `default_registry`; with `registry=<instance>`, mutates that instance. (Equivalent to `(registry or default_registry).register(plugin)`.)
    - Used as a function call from each plugin's `api.py` (e.g., `PLUGIN = register_plugin(MyPlugin())`); NOT as a class decorator (plugins are instances, not classes — see Notes §3).
- [ ] **AC-4 — Typed exception payloads.** `src/codegenie/plugins/errors.py` defines:
    - `PluginAlreadyRegistered(Exception)` with a typed `name: PluginId` attribute; `__init__` accepts `name: PluginId`, the *existing* registration's `module.qualname`, and the *new* registration's `module.qualname`; the formatted message names both — mirrors `probes/registry.py:154-158`.
    - `PluginNotRegistered(Exception)` with a typed `name: PluginId` attribute; message includes the missing name.
    - Placeholders `PluginExtendsCycle(Exception)` and `PluginRejected(Exception)` (raised by S2-03 / S2-04; live here so the exception hierarchy is one file).
    - Tests assert `exc_info.value.name == PluginId("...")`, NOT `"..." in str(exc_info.value)` alone.
- [ ] **AC-5 — `all()` preserves registration order.** Registering three plugins with names `vulnerability-remediation--node--zeta`, `vulnerability-remediation--node--alpha`, `vulnerability-remediation--node--mu` in that order, `registry.all()` returns them as the identity tuple `(zeta_plugin, alpha_plugin, mu_plugin)` — NOT alphabetic, NOT a set, NOT a list. Names chosen so alphabetic ≠ insertion order.
- [ ] **AC-6 — Cross-test isolation (both controls).** Two assertions, both required:
    - **Positive control:** in a test using fresh `PluginRegistry()` instance `reg_a`, `register_plugin(p, registry=reg_a)` then `assert reg_a.all() == (p,)`.
    - **Negative control:** a separate test using fresh `PluginRegistry()` instance `reg_b` (constructed independently) asserts `reg_b.all() == ()` AND `p not in reg_b.all()`.
    - An autouse **session-scoped** fixture in `tests/unit/plugins/conftest.py` snapshots `default_registry.all()` at session start and re-asserts byte-identical equality at session end. Any test that omits the `registry=` kwarg pollutes the default and fails the assertion (ADR-0002 §Consequences row 7). Function-scoped restoration handled by a separate `restore_default_registry` fixture (mirror `tests/unit/test_registry.py:20-40` precedent).
- [ ] **AC-7 — `Plugin` Protocol surface fence test.** `tests/fence/test_plugin_protocol_frozen.py` asserts ALL of:
    - `{n for n in dir(Plugin) if not n.startswith("_")} == {"manifest", "build_subgraph", "adapters", "transforms"}` (exact-set equality).
    - `"manifest" in Plugin.__annotations__`.
    - `inspect.isfunction(Plugin.build_subgraph)` (likewise for `adapters`, `transforms`).
    - Test does NOT use `Plugin.__abstractmethods__` — `Protocol` (especially `@runtime_checkable`) populates that differently than ABCs; relying on it would either fail outright or pass trivially.
- [ ] **AC-8 — Runtime-checkable smoke.** A test asserts `isinstance(make_fake_plugin(name="example--noop--*"), Plugin) is True` AND `isinstance(object(), Plugin) is False`. Sufficient evidence the `@runtime_checkable` decoration is in place; downstream tests / fixtures rely on this.
- [ ] **AC-9 — `PluginResolution` placeholder.** `src/codegenie/plugins/resolution.py` ships with a single declaration: `class PluginResolution: ...` (or equivalent type alias placeholder). A one-line module docstring states "Placeholder; S2-04 expands to `ConcreteResolution | UniversalFallbackResolution` sum type." `mypy --strict` resolves the `resolve()` return annotation against this symbol.
- [ ] **AC-10 — Default-singleton smoke.** A test calls `register_plugin(plugin)` with NO `registry=` kwarg and asserts `plugin in default_registry.all()`. Cleanup is guaranteed via a function-scoped autouse `restore_default_registry` fixture in `tests/unit/plugins/conftest.py` (snapshot pre-test, restore post-test). This exercises the `registry or default_registry` fallback that AC-3 names; without this test, the singleton branch is dead-code-covered.
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/plugins/{__init__,protocols,registry,resolution,errors}.py`, `tests/unit/plugins/{__init__,conftest,test_registry,test_protocols}.py`, `tests/fence/{__init__,test_plugin_protocol_frozen}.py`, and `tests/fixtures/plugins/{__init__,fake_plugin}.py`.

## Implementation outline

1. **Test fixture spec (write first — every other test depends on it).** Create `tests/fixtures/plugins/__init__.py` (empty) and `tests/fixtures/plugins/fake_plugin.py`:
    ```python
    from __future__ import annotations
    from dataclasses import dataclass
    from typing import TYPE_CHECKING
    from codegenie.types.identifiers import PluginId

    if TYPE_CHECKING:
        from codegenie.plugins.protocols import Adapter, Plugin, RecipeEngine
        from codegenie.plugins.registry import PluginRegistry

    @dataclass(frozen=True)
    class _FakeManifest:
        name: PluginId

    @dataclass(frozen=True)
    class _FakePlugin:
        manifest: _FakeManifest

        def build_subgraph(self, registry: "PluginRegistry") -> object:
            raise NotImplementedError("test fake")

        def adapters(self) -> dict[object, "Adapter"]:
            return {}

        def transforms(self) -> dict[object, "RecipeEngine"]:
            return {}

    def make_fake_plugin(*, name: str) -> "Plugin":
        # Single PluginId(str) boundary lift lives here. Callers pass raw str
        # for convenience; PluginId discipline (ADR-0010) preserved.
        return _FakePlugin(manifest=_FakeManifest(name=PluginId(name)))  # type: ignore[return-value]
    ```
    The `# type: ignore[return-value]` is acceptable here because the fixture is a test-time stand-in for the not-yet-shipped `PluginManifest` Pydantic model (S2-02). When S2-02 lands, this fixture upgrades to satisfy the full `PluginManifest` shape and the ignore can come off.
2. Create `src/codegenie/plugins/__init__.py` (empty, namespace marker) and `src/codegenie/plugins/resolution.py` (placeholder per AC-9). Document the placeholder is a forward-reference target only.
3. Create `src/codegenie/plugins/errors.py` per AC-4. `PluginAlreadyRegistered.__init__` takes `(name: PluginId, existing: str, duplicate: str)` and stores `self.name = name`; message: `f"duplicate plugin name {name!r}: {existing} and {duplicate}"`. `PluginNotRegistered.__init__` takes `(name: PluginId)`; stores `self.name = name`.
4. Create `src/codegenie/plugins/protocols.py`:
    - All three Protocols `@runtime_checkable` (perf cost is paid at test-fixture time, not the hot path; this is the same trade-off `runtime_checkable` Protocols carry across the codebase).
    - Use `from __future__ import annotations`; forward-ref `PluginManifest`, `PluginScope`, `PluginResolution`, `Adapter`, `RecipeEngine`, `PluginSubgraph`, `CveRecord`, `Bundle`, `Applicability`, `RecipePlan`, `ApplyContext`, `RecipeOutcome` under `TYPE_CHECKING`.
    - `Plugin.manifest: PluginManifest` is the attribute; the other three are method signatures. Resist the urge to add any fifth member — AC-7's fence test will fail loud if you do.
5. Create `src/codegenie/plugins/registry.py`:
    - Module docstring mirrors `src/codegenie/depgraph/registry.py:30-38` verbatim, updated to "this is the 4th registry of the decorator-registry family" (see Notes §6). The opportunity is recorded; the extract is NOT done here.
    - `class PluginRegistry`: private `self._plugins: dict[PluginId, Plugin] = {}` (dict-of-`PluginId` → `Plugin`; CPython 3.7+ insertion-order preservation is the order contract).
    - `register(plugin)`: collision check by `plugin.manifest.name in self._plugins`; raises `PluginAlreadyRegistered(name, existing_qualname, duplicate_qualname)` with both `module.qualname`s formatted into the message — mirror `probes/registry.py:154-158`.
    - `get(name)` / `all()` / `resolve(scope)` per AC-2. `resolve` raises `NotImplementedError("resolve() lands in S2-04; the universal-fallback algorithm is not yet implemented")`.
    - `default_registry: Final[PluginRegistry] = PluginRegistry()` module-level. `Final` is intentional per ADR-0002 §Consequences (tightening of `probes/registry.py:238` precedent; see Notes §2).
    - `def register_plugin(plugin: Plugin, *, registry: PluginRegistry | None = None) -> Plugin`: `(registry or default_registry).register(plugin); return plugin`. Thin wrapper; no validation here.
6. Create `tests/fence/__init__.py` (empty marker — **S2-01 is the first story to populate `tests/fence/`**) and `tests/fence/test_plugin_protocol_frozen.py` per AC-7.
7. Create `tests/unit/plugins/__init__.py` (empty marker). Create `tests/unit/plugins/conftest.py` with TWO fixtures:
    - `plugin_registry` (function-scoped): returns `PluginRegistry()`.
    - `restore_default_registry` (function-scoped, autouse): snapshot `default_registry._plugins.copy()` pre-test, restore post-test. Used to make AC-10's default-singleton test safe under repeated runs.
    - Optionally: a `_default_registry_session_guard` (session-scoped, autouse) that asserts `default_registry.all() == ()` at session start and session end — the load-bearing ADR-0002 §Consequences row 7 assertion (Notes §4).
8. Write the red test (`test_collision_raises`), watch it fail (import-error on `codegenie.plugins`), implement, watch it pass. Then add the rest of the TDD plan's tests in order.

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/unit/plugins/test_registry.py`

```python
import pytest

from codegenie.plugins.errors import PluginAlreadyRegistered
from codegenie.plugins.registry import PluginRegistry, register_plugin
from codegenie.types.identifiers import PluginId
from tests.fixtures.plugins.fake_plugin import make_fake_plugin


def test_collision_raises():
    """Re-registering a plugin name into the same registry is an exit-4
    failure mode (ADR-0002 §Consequences). The kernel must refuse, loudly —
    AND name both colliding registrations' module.qualname in the message
    (mirrors probes/registry.py:154-158)."""
    registry = PluginRegistry()
    plugin = make_fake_plugin(name="vulnerability-remediation--node--npm")
    register_plugin(plugin, registry=registry)

    duplicate = make_fake_plugin(name="vulnerability-remediation--node--npm")
    with pytest.raises(PluginAlreadyRegistered) as exc_info:
        register_plugin(duplicate, registry=registry)

    assert exc_info.value.name == PluginId("vulnerability-remediation--node--npm")
    # Both colliding qualified names appear in the message:
    assert "_FakePlugin" in str(exc_info.value)  # appears twice — existing + duplicate
    assert str(exc_info.value).count("_FakePlugin") == 2
```

Why it fails: `codegenie.plugins` doesn't exist yet — `ImportError` on the test's first line.

### Green — minimal pass

- Create the package, `errors.py`, `protocols.py`, `registry.py`, `resolution.py`.
- `PluginRegistry.register` checks `if plugin.manifest.name in self._plugins: raise PluginAlreadyRegistered(...)`.
- `register_plugin(plugin, *, registry=None)` delegates to `(registry or default_registry).register(plugin)` and returns `plugin`.

Resist the urge to wire `resolve` here — `raise NotImplementedError("resolve() lands in S2-04; ...")` is correct.

### Required follow-on tests (one per AC; pin each with the named identity)

```python
def test_all_returns_registration_order(plugin_registry: PluginRegistry) -> None:
    """AC-5 — identity tuple ordering (catches return (), set, sort mutants)."""
    a = make_fake_plugin(name="vulnerability-remediation--node--zeta")
    b = make_fake_plugin(name="vulnerability-remediation--node--alpha")
    c = make_fake_plugin(name="vulnerability-remediation--node--mu")
    register_plugin(a, registry=plugin_registry)
    register_plugin(b, registry=plugin_registry)
    register_plugin(c, registry=plugin_registry)
    assert plugin_registry.all() == (a, b, c)


def test_register_plugin_returns_plugin_unchanged(plugin_registry: PluginRegistry) -> None:
    """AC-3 — return identity (catches `return None` mutant)."""
    p = make_fake_plugin(name="vulnerability-remediation--node--npm")
    assert register_plugin(p, registry=plugin_registry) is p


def test_register_plugin_default_singleton_path(restore_default_registry: None) -> None:
    """AC-10 — `register_plugin(plugin)` with no kwarg mutates default_registry.
    The restore_default_registry autouse fixture handles cleanup."""
    from codegenie.plugins.registry import default_registry
    p = make_fake_plugin(name="vulnerability-remediation--node--npm")
    register_plugin(p)  # no registry= kwarg
    assert p in default_registry.all()


def test_get_returns_registered_plugin(plugin_registry: PluginRegistry) -> None:
    """AC-2 — get round-trip."""
    p = make_fake_plugin(name="vulnerability-remediation--node--npm")
    register_plugin(p, registry=plugin_registry)
    assert plugin_registry.get(PluginId("vulnerability-remediation--node--npm")) is p


def test_get_unknown_raises_plugin_not_registered_with_typed_name(
    plugin_registry: PluginRegistry,
) -> None:
    """AC-4 — typed exception payload, not just stringified message."""
    from codegenie.plugins.errors import PluginNotRegistered
    with pytest.raises(PluginNotRegistered) as exc_info:
        plugin_registry.get(PluginId("vulnerability-remediation--node--npm"))
    assert exc_info.value.name == PluginId("vulnerability-remediation--node--npm")


def test_resolve_stub_names_s2_04(plugin_registry: PluginRegistry) -> None:
    """AC-2 — forward-reference contract; S2-04 will grep for this substring."""
    with pytest.raises(NotImplementedError, match="S2-04"):
        plugin_registry.resolve(scope=None)  # type: ignore[arg-type]


def test_runtime_checkable_protocols_match_fakes() -> None:
    """AC-8 — @runtime_checkable smoke; downstream fixtures rely on isinstance."""
    from codegenie.plugins.protocols import Plugin
    p = make_fake_plugin(name="example--noop--*")
    assert isinstance(p, Plugin) is True
    assert isinstance(object(), Plugin) is False


def test_fresh_registries_are_isolated() -> None:
    """AC-6 — both positive AND negative control (catches `all() == ()`-always mutant)."""
    reg_a = PluginRegistry()
    reg_b = PluginRegistry()
    p = make_fake_plugin(name="vulnerability-remediation--node--npm")
    register_plugin(p, registry=reg_a)
    assert reg_a.all() == (p,)        # positive — A has it
    assert reg_b.all() == ()           # negative — fresh B is empty
    assert p not in reg_b.all()        # belt and suspenders
```

Fence test (`tests/fence/test_plugin_protocol_frozen.py`) per AC-7:

```python
import inspect

from codegenie.plugins.protocols import Plugin


def test_plugin_protocol_has_exactly_four_members() -> None:
    """ADR-0004 §Consequences: Plugin Protocol surface is exactly four members.
    Adding a fifth or removing one fails this assertion. Do NOT rely on
    Plugin.__abstractmethods__ — Protocol does not populate it like ABCs do."""
    members = {n for n in dir(Plugin) if not n.startswith("_")}
    assert members == {"manifest", "build_subgraph", "adapters", "transforms"}, (
        f"Plugin Protocol surface drifted from ADR-0004 freeze: {members}"
    )
    assert "manifest" in Plugin.__annotations__
    assert inspect.isfunction(Plugin.build_subgraph)
    assert inspect.isfunction(Plugin.adapters)
    assert inspect.isfunction(Plugin.transforms)
```

### Refactor

- Module docstrings: `protocols.py` cites ADR-0004's four-member freeze and names the fence test; `registry.py` mirrors `depgraph/registry.py:30-38` updated to N=4 (Notes §6); `errors.py` documents the structured `.name` attribute as the loader-S2-03 contract.
- `@runtime_checkable` decorators on all three Protocols; the `Plugin` decorator carries an inline `# AC-8 — see test_runtime_checkable_protocols_match_fakes` comment so reviewers can grep.
- `PluginRegistry` is `__slots__`-able but **keep it a plain class** unless `mypy --strict` complains — precedent `probes/registry.py` doesn't use `__slots__` (Notes §8).
- `from __future__ import annotations` everywhere in the new modules + `TYPE_CHECKING` imports for cross-S1-* / cross-S2-* forward references.

### Optional property test (only if executor has budget)

`hypothesis` is a dev dep. The strongest hardening of AC-5's order contract is a property test that generates N≥2 distinct plugin names, registers them, asserts `reg.all()` returns the identical tuple. Three sibling registries skipped this; AC-5's three-element identity-tuple test catches the dominant mutants. Add only if cheap.

## Files to touch

| Path                                                | Why                                                                                                            |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `src/codegenie/plugins/__init__.py`                 | Namespace marker (empty).                                                                                       |
| `src/codegenie/plugins/errors.py`                   | `PluginAlreadyRegistered`, `PluginNotRegistered` with typed `.name: PluginId`; placeholders `PluginExtendsCycle` / `PluginRejected`. |
| `src/codegenie/plugins/protocols.py`                | Three `@runtime_checkable` Protocols; four-member `Plugin` surface (ADR-0004).                                  |
| `src/codegenie/plugins/registry.py`                 | `PluginRegistry`, `default_registry: Final[PluginRegistry]`, `register_plugin` helper. Module docstring carries 4th-registry rule-of-three observation (Notes §6). |
| `src/codegenie/plugins/resolution.py`               | Placeholder `class PluginResolution: ...` so the `resolve()` return annotation resolves under `mypy --strict` today. S2-04 expands. |
| `tests/fixtures/plugins/__init__.py`                | Test fixture package marker.                                                                                    |
| `tests/fixtures/plugins/fake_plugin.py`             | `make_fake_plugin(name=str)` helper; single `PluginId(str)` boundary lift.                                      |
| `tests/unit/plugins/__init__.py`                    | Test package marker.                                                                                            |
| `tests/unit/plugins/test_registry.py`               | TDD red test + named follow-on tests (one per AC).                                                              |
| `tests/unit/plugins/conftest.py`                    | `plugin_registry` fresh-instance fixture + `restore_default_registry` autouse fixture + optional session-scoped `default_registry`-snapshot guard. |
| `tests/fence/__init__.py`                           | **First population of `tests/fence/`** — empty marker.                                                          |
| `tests/fence/test_plugin_protocol_frozen.py`        | Four-member `Plugin` surface assertion (ADR-0004); explicit non-use of `__abstractmethods__`.                   |

## Out of scope

- **`PluginManifest` Pydantic model** — handled by S2-02. This story uses a minimal forward-referenced placeholder so `Plugin.manifest` is type-shaped. The `make_fake_plugin` fixture uses a `_FakeManifest` frozen dataclass with a `name: PluginId` field; S2-02 will upgrade the fixture to satisfy the full model.
- **`Adapter` Protocol surface freeze** — only the `primitive: PrimitiveName` attribute ships here. Methods land in **S7** with the first concrete `Adapter` implementation (ADR-0032 language-search adapters). No fence test for `Adapter` in this story — by intent, the surface is not yet stable enough to freeze.
- **`RecipeEngine` Protocol surface freeze** — the method signatures `applies` / `apply` ship here for Step 5 consumers, but the surface is not fence-frozen. Step 5 owns the freeze.
- **`PluginResolution` sum-type expansion** — `src/codegenie/plugins/resolution.py` ships a placeholder; S2-04 expands to `ConcreteResolution | UniversalFallbackResolution` per ADR-0003.
- **Filesystem walk / `PLUGINS.lock` integrity check** — handled by S2-03.
- **Resolution algorithm (specificity, precedence, extends walk, universal fallback)** — handled by S2-04. `resolve()` raises `NotImplementedError("S2-04")` here on purpose.
- **TCCM composition / `provides`/`requires`** — Step 3.
- **`@register_signal_kind`, `@register_recipe`** — different kernels; Steps 5 / 6.
- **Concurrent registration from multiple threads / coroutines** — registration is import-time and single-threaded by construction (mirrors `probes/registry.py`). No threading lock; no async semantics. If a future story needs it, an ADR amendment is the path.
- **Module-reload semantics** — `importlib.reload()`-ing a plugin module that calls `register_plugin` MUST raise `PluginAlreadyRegistered` (the desired behavior — reload is a developer-only operation and a duplicate registration is correctly an error). No special-casing.
- **Kernel-extract across the four registries** — `probes/registry.py`, `indices/registry.py`, `depgraph/registry.py`, and this `plugins/registry.py` all implement related-but-divergent dispatch. The shared surface (`register` / `get` / `all` / typed-collision-error) is a kernel-extract candidate (rule-of-three threshold crossed at N=3, now N=4). Still deferred (`resolve()` machinery dominates LOC; Rule 2 — three similar lines is better than premature abstraction). See Notes §6.

## Notes for the implementer

### §1 — Kernel must stay tiny

ADR-0002 explicitly carries the toolkit's "Stay that simple. … no eager validation, no side effects at registration." Resist the urge to add logging, metrics, or import-time validation here. Validation belongs in `resolve()` (S2-04) and the loader (S2-03). The `register()` method does ONE thing: collision-check then append. The `register_plugin()` helper does ONE thing: pick the registry then delegate then return.

### §2 — Mirror `probes/registry.py` deliberately

Same docstring shape, same `default_registry` placement, same fresh-instance fixture story, same dual-name collision message (line 154-158 of the precedent). Reviewers shouldn't have to context-switch between two registry idioms.

`default_registry: Final[PluginRegistry] = PluginRegistry()` is intentionally tighter than the precedent (`probes/registry.py:238`'s `default_registry = Registry()`). ADR-0002 §Consequences row 2 names `Final` as the intended posture — production code uses the singleton; replacement requires explicit DI through `register_plugin(..., registry=...)`. The precedent is loose; this story tightens it.

### §3 — `@register_plugin` is a function call, NOT a class decorator

Three existing registries use a class-decorator shape (`@register_probe`, `@register_index_freshness_check(name)`, `@register_dep_graph_strategy(eco)`). This story uses `register_plugin(plugin, *, registry=None)` — a function call from each plugin's `api.py` (`PLUGIN = register_plugin(MyPlugin())`).

**Why the asymmetry is intentional, not oversight:** plugins are *instances* that carry a manifest + composed state, not classes / functions. A class decorator would need to instantiate the class at module-import time with no arguments, breaking the manifest-carrying contract. ADR-0002 §Decision pins this shape. Do NOT add a `@register_plugin` dual-shape wrapper to chase symmetry — the asymmetry is a feature.

**Return-type divergence from arch:** `phase-arch-design.md §Component design C2` line 466 declares `register(self, plugin: Plugin) -> None` and line 469 `all(self) -> list[Plugin]`. This story tightens to `-> Plugin` (per `probes/registry.py:139` precedent and to make `register_plugin`'s `return plugin` natural) and `-> tuple[Plugin, ...]` (per `probes/registry.py:189` precedent + immutability convention). File a follow-up cleanup to update arch C2.

### §4 — Cross-test isolation mechanism

The load-bearing assertion ADR-0002 §Consequences row 7 names is: after the unit-tests run, `default_registry.all() == ()`. Implement as TWO fixtures in `tests/unit/plugins/conftest.py`:

- **Function-scoped autouse `restore_default_registry`:** snapshot `default_registry._plugins.copy()` pre-test; restore post-test. Mirror `tests/unit/test_registry.py:20-40`. Needed because AC-10's test deliberately calls `register_plugin(plugin)` without a registry kwarg.
- **Session-scoped autouse `_default_registry_session_guard`:** capture `default_registry.all()` at session start and re-assert byte-identical equality at session end. This catches *any* test that escaped the function-scoped restore (e.g., crashed mid-cleanup).

Do NOT add an `unregister_for_tests()` method to `PluginRegistry`. The sibling `indices/registry.py:198-208` ships that explicitly because production code registers into `default_registry`; in this phase, the first production registration is S2-03's loader, not anything in S2-01's scope. When S2-03 lands, reconsider — but not here.

### §5 — `PluginId` newtype boundary

The single boundary lift from `str` to `PluginId` lives inside `make_fake_plugin`. Tests pass `name="..."` (raw str for convenience); the fixture wraps with `PluginId(name)` exactly once. Production code (`PluginManifest.from_yaml`, S2-02) will do its own typed parse. Never construct a `Plugin` whose `manifest.name` is a raw `str` — that's an ADR-0010 violation any reviewer will catch.

### §6 — Rule-of-three observation: NOW four registries

This is the **4th** decorator-registry in the codebase:

1. `src/codegenie/probes/registry.py` (Phase 0 + Phase 2 ADR-0003 amendments) — `for_task` filter + LRU + `sorted_for_dispatch` (heaviness, runs_last).
2. `src/codegenie/indices/registry.py` (Phase 2 S1-02) — total dispatch via `dispatch_all`.
3. `src/codegenie/depgraph/registry.py` (Phase 2 S1-10) — single dispatch + `has_strategy` query.
4. `src/codegenie/plugins/registry.py` (this story) — `register` / `get` / `all` + `resolve(scope)` + `extends`-walk (in S2-04).

Both `indices/registry.py:26-31` and `depgraph/registry.py:30-38` explicitly document the rule-of-three threshold and *defer* the kernel-extract because dispatch shapes diverge. **The deferral still holds at N=4** — `resolve()`'s specificity / precedence / extends-walk logic dominates this kernel's LOC; the shared surface (`register` / `get` / `all` / typed-collision-error) is a small fraction. Pure-Rule-2 application.

**Mirror the deferral pattern.** Add a module-docstring paragraph to `plugins/registry.py` that:
- Names all four precedents and their dispatch divergences.
- Pins the extract trigger: "lift a shared `KernelRegistry[K, V]` base when N=5 OR when a new registry needs only the common surface (`register` / `get` / `all` / typed-collision-error)."
- Cites this story file as the audit anchor.

The paragraph IS the deferral — without it, the next registry's author won't see the prior three's reasoning and will either (a) re-derive the extract argument from scratch or (b) silently re-implement a 5th copy.

### §7 — Step 2 done-criteria is the union of S2-01..S2-04

`High-level-impl.md §Step 2 done-criteria` (lines 64-70) names: resolver tests (`extends` cycle, depth 4 / 5), loader tests, `PLUGINS.lock` mismatch, property-tested resolution totality, fresh-fixture isolation, `mypy --strict` clean. S2-01 owns ONLY: register / get / all / collision / cross-test isolation / `Plugin` fence test / `mypy --strict` for the kernel modules. Resolver and loader done-criteria belong to S2-03 / S2-04. A reader who treats Step 2 done-criteria as a single-story checklist will think this story is under-scoped; it isn't.

### §8 — Deliberately not adopted

These are correct YAGNI applications, listed so future PRs don't second-guess:

- **`__slots__` on `PluginRegistry`** — not adopted; precedent `probes/registry.py` doesn't use it. Hot-path cost is zero (registration is import-time); footprint cost is one entry per registry per process. Add only if profiling shows a real cost.
- **Dual-shape decorator for `register_plugin`** — not adopted; rationale in §3 above.
- **DI container (`punq`, `dependency-injector`)** — explicitly rejected in `phase-arch-design.md §Patterns considered and deliberately rejected`. Plugin loading is one filesystem walk + `importlib.import_module`; a DI container is 5× the indirection for zero capability.
- **Module-level mutable `_REGISTRY: dict = {}`** — the toolkit's "side effects at module import time" anti-pattern. ADR-0002 explicitly rejects this in favor of an instance-with-`default_registry` shape.

The fence test (AC-7) is the structural enforcement ADR-0004 §Consequences names. Use the exact-set-equality + `__annotations__` shape from the TDD plan — be explicit; reviewers will read this test as the canonical "the kernel is closed" assertion.

Cross-test pollution (`default_registry` leaking) is the *exact* failure mode ADR-0002 §Tradeoffs warns about. The cross-test assertion is not optional belt-and-suspenders; it's an ADR consequence.
