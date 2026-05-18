# Story S2-01 — PluginRegistry kernel + Plugin/Adapter/RecipeEngine Protocols

**Step:** Step 2 — Plugin Registry kernel, manifest schema, loader, resolver
**Status:** Ready
**Effort:** M
**Depends on:** S1-01, S1-02
**ADRs honored:** ADR-0002, ADR-0004, ADR-0010, ADR-0011 (framing only — `PLUGINS.lock` rejection raised by loader in S2-03), production ADR-0031

## Context

Step 2 lands the closed-for-modification ADR-0031 kernel that every Phase 3+ plugin slots into. This story is the kernel's split: the **Protocols plugins implement** (`Plugin`, `Adapter`, `RecipeEngine`) live in `src/codegenie/plugins/protocols.py`, and the **kernel that holds them** (`PluginRegistry` + module-level `default_registry` + `@register_plugin` decorator) lives in `src/codegenie/plugins/registry.py`. Mirrors Phase 6.5's `TaskClassRegistry` shape and the existing `codegenie.probes.registry.Registry` precedent (ADR-0002 Option C). The four-method `Plugin` surface (`manifest`, `build_subgraph`, `adapters`, `transforms`) is the load-bearing freeze that lets ADR-0004 push task-class-specific knowledge onto TCCM `provides`/`requires` rather than the kernel.

This story only ships the registry **kernel** — manifest parsing (S2-02), integrity-checked filesystem loading (S2-03), and the resolver/extends/fallback algorithm (S2-04) all sit downstream. `PluginRegistry.resolve(scope)` is therefore stubbed here to a `NotImplementedError` (S2-04 lands it); `register`, `get`, and `all` are fully functional so S2-02/S2-03 have something to register against.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C2` — exact public interface for `Plugin`, `PluginRegistry`, `default_registry`, `register_plugin`; failure modes (`PluginAlreadyRegistered`, exit code 4); "Two-arg `run` only" discipline.
  - `../phase-arch-design.md §Design patterns applied row 1` — Registry pattern; per-test fresh-instance isolation.
  - `../phase-arch-design.md §Patterns considered and deliberately rejected` — "No DI container"; "No module-level mutable singleton".
- **Phase ADRs:**
  - `../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md` — ADR-0002 — Option C is the decision; `default_registry` is a module-level `PluginRegistry` *instance*, not a `dict`; `@register_plugin(plugin, *, registry=None)` is the helper shape; tests pass fresh `PluginRegistry()` instances.
  - `../ADRs/0004-plugin-private-capabilities-via-tccm.md` — ADR-0004 — the `Plugin` Protocol surface is **exactly four** methods (`manifest`, `build_subgraph`, `adapters`, `transforms`); no `cve_feed_parsers()`. Fence test asserts the method count.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — ADR-0010 — `PluginId` from S1-01; no raw `str` for domain IDs.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` §Plugin manifest, §Discovery and resolution — the umbrella commitment this kernel implements.
- **Existing code (precedent to mirror):**
  - `src/codegenie/probes/registry.py` — class shape, decorator shape, `default_registry` placement, fresh-instance fixture pattern. **Mirror its API discipline**; do not re-invent.
  - `src/codegenie/result.py` — `Result[T, E]` used by the manifest loader (S2-02 consumer) — referenced here only so `Plugin.manifest` type aligns once S2-02 lands.
  - `src/codegenie/types/identifiers.py` — `PluginId` is added in S1-01; import it.
  - `src/codegenie/probes/base.py` — Protocol/ABC pattern for the "contract is frozen" discipline.

## Goal

Ship the Phase 3 plugin kernel: three `Protocol`s (`Plugin`, `Adapter`, `RecipeEngine`) in `protocols.py`; one `PluginRegistry` class + `default_registry` instance + `@register_plugin` decorator in `registry.py`; typed exceptions for collision and lookup failure; per-test fixture isolation that does not touch `default_registry`.

## Acceptance criteria

- [ ] `src/codegenie/plugins/protocols.py` exports exactly three `Protocol`s: `Plugin` (with `manifest: PluginManifest`, `build_subgraph`, `adapters`, `transforms`), `Adapter`, `RecipeEngine`. `Plugin` has **exactly four** member references (one attribute, three methods); a fence test asserts the count.
- [ ] `src/codegenie/plugins/registry.py` exports `PluginRegistry`, `default_registry`, and `register_plugin`. `PluginRegistry` instances have `register(plugin) -> Plugin`, `get(name: PluginId) -> Plugin`, `all() -> tuple[Plugin, ...]`, `resolve(scope: PluginScope) -> PluginResolution`. `resolve` raises `NotImplementedError("resolved in S2-04")` for now; the other three are real.
- [ ] `register_plugin(plugin, *, registry: PluginRegistry | None = None) -> Plugin` mutates the passed registry (or `default_registry` if `None`), returns the plugin unchanged so it composes as a decorator-style helper. Duplicate `plugin.manifest.name` raises `PluginAlreadyRegistered(name)`.
- [ ] `PluginRegistry.get(unknown_id)` raises `PluginNotRegistered(name)`. `PluginRegistry.all()` returns plugins in registration order (deterministic).
- [ ] `tests/unit/plugins/test_registry.py` covers: register one / register two / collision raises `PluginAlreadyRegistered`; `get` returns the registered plugin; `get(unknown)` raises `PluginNotRegistered`; `all()` returns registration order; **fresh `PluginRegistry()` in fixture A does not appear in fixture B** (per-test isolation explicitly asserted via a cross-test pollution check).
- [ ] `tests/fence/test_plugin_protocol_frozen.py` introspects `Plugin.__abstractmethods__` / `dir(Plugin)` and asserts the four-member surface (ADR-0004 enforcement).
- [ ] `conftest.py` (test-level) ships a `plugin_registry` fixture returning a fresh `PluginRegistry()` per test — no `monkeypatch` of `default_registry`.
- [ ] TDD red test (`test_collision_raises`) committed and green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/plugins/{protocols,registry,errors}.py` and the new tests.

## Implementation outline

1. Create `src/codegenie/plugins/__init__.py` (empty, namespace marker).
2. Create `src/codegenie/plugins/errors.py` with `PluginAlreadyRegistered`, `PluginNotRegistered`, and the placeholder `PluginExtendsCycle` / `PluginRejected` (raised by later stories — S2-03/S2-04 — but live here so the exception hierarchy is one file).
3. Create `src/codegenie/plugins/protocols.py`:
   - `class Adapter(Protocol)`: minimal surface (`primitive: PrimitiveName`; one or two methods reflecting ADR-0032 language search adapters — keep the surface tight; full bodies are S7 work).
   - `class RecipeEngine(Protocol)`: `kind: TransformKind`; `def applies(...) -> Applicability`; `async def apply(...) -> RecipeOutcome`. Stubbed shape — Step 5 consumers fill detail.
   - `class Plugin(Protocol)`: `manifest: PluginManifest` (forward-ref placeholder until S2-02 lands the model — type-only import behind `TYPE_CHECKING`); `def build_subgraph(self, registry: "PluginRegistry") -> "PluginSubgraph"`; `def adapters(self) -> dict[PrimitiveName, Adapter]`; `def transforms(self) -> dict[TransformKind, RecipeEngine]`.
   - All three Protocols are `@runtime_checkable` so test fixtures can `isinstance(obj, Plugin)`; rejected if perf becomes an issue.
4. Create `src/codegenie/plugins/registry.py`:
   - `class PluginRegistry`: private `self._plugins: dict[PluginId, Plugin]`; insertion-ordered registration list (Python dict order suffices; preserve registration index for tie-break parity with `probes/registry.py`).
   - `register(plugin)`: collision raises `PluginAlreadyRegistered(plugin.manifest.name)`.
   - `get(name)` / `all()` / `resolve(scope)` per AC.
   - `default_registry: Final[PluginRegistry] = PluginRegistry()` module-level.
   - `def register_plugin(plugin, *, registry=None) -> Plugin`: thin helper; returns plugin unchanged.
5. Write the red test (collision raises), watch it fail, implement, watch it pass.
6. Add fence test for the four-member `Plugin` surface (ADR-0004).
7. Add `conftest.py` fixture for fresh `PluginRegistry()` and a separate test that proves cross-test isolation (register into fixture A; assert fresh `PluginRegistry()` in fixture B is empty).

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/unit/plugins/test_registry.py`

```python
import pytest

from codegenie.plugins.errors import PluginAlreadyRegistered
from codegenie.plugins.registry import PluginRegistry, register_plugin
from tests.fixtures.plugins.fake_plugin import make_fake_plugin


def test_collision_raises():
    """Re-registering a plugin name into the same registry is an exit-4
    failure mode (ADR-0002 §Consequences). The kernel must refuse, loudly."""
    registry = PluginRegistry()
    plugin = make_fake_plugin(name="vulnerability-remediation--node--npm")
    register_plugin(plugin, registry=registry)

    duplicate = make_fake_plugin(name="vulnerability-remediation--node--npm")
    with pytest.raises(PluginAlreadyRegistered) as exc_info:
        register_plugin(duplicate, registry=registry)
    assert "vulnerability-remediation--node--npm" in str(exc_info.value)
```

Why it fails: `codegenie.plugins` doesn't exist yet — `ImportError` on the test's first line.

### Green — minimal pass

- Create the package, `errors.py`, `protocols.py`, `registry.py`.
- `PluginRegistry.register` checks `if plugin.manifest.name in self._plugins: raise PluginAlreadyRegistered(...)`.
- `register_plugin(plugin, *, registry=None)` delegates to `(registry or default_registry).register(plugin)`.

Resist the urge to wire `resolve` here — `NotImplementedError("resolved in S2-04")` is correct.

### Refactor

- Module docstrings mirroring `probes/registry.py`'s precedent rationale.
- `PluginRegistry` is `__slots__`-able but keep it a plain class unless `mypy --strict` complains.
- `@runtime_checkable` Protocol decorators on all three; document why (test fixtures use `isinstance`).
- The `Plugin.manifest` forward reference: `from __future__ import annotations` + a `TYPE_CHECKING` import to avoid the S2-02 cycle. Add a `# S2-02 lands the concrete model` comment.
- Cross-test isolation test (`test_default_registry_not_polluted_by_fixtures`) is the load-bearing assertion ADR-0002 §Consequences names.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/__init__.py` | Namespace marker (empty). |
| `src/codegenie/plugins/errors.py` | `PluginAlreadyRegistered`, `PluginNotRegistered`, placeholders for `PluginExtendsCycle`/`PluginRejected` consumed by S2-03/S2-04. |
| `src/codegenie/plugins/protocols.py` | The three Protocols plugins implement; four-member `Plugin` surface (ADR-0004). |
| `src/codegenie/plugins/registry.py` | `PluginRegistry`, `default_registry`, `register_plugin`. |
| `tests/unit/plugins/__init__.py` | Test package marker. |
| `tests/unit/plugins/test_registry.py` | TDD red test + register/get/all/collision/isolation tests. |
| `tests/unit/plugins/conftest.py` | `plugin_registry` fresh-instance fixture. |
| `tests/fence/test_plugin_protocol_frozen.py` | Four-member `Plugin` surface assertion (ADR-0004). |
| `tests/fixtures/plugins/fake_plugin.py` | `make_fake_plugin(name=...)` helper used by all Step-2 tests. |

## Out of scope

- **`PluginManifest` Pydantic model** — handled by S2-02. This story uses a minimal forward-referenced placeholder so `Plugin.manifest` is type-shaped.
- **Filesystem walk / `PLUGINS.lock` integrity check** — handled by S2-03.
- **Resolution algorithm (specificity, precedence, extends walk, universal fallback)** — handled by S2-04. `resolve()` raises `NotImplementedError` here on purpose.
- **TCCM composition / `provides`/`requires`** — Step 3.
- **`@register_signal_kind`, `@register_recipe`** — different kernels; Steps 5/6.

## Notes for the implementer

- The **kernel must stay tiny**. ADR-0002 explicitly carries the toolkit's "Stay that simple. … no eager validation, no side effects at registration." Resist the urge to add logging, metrics, or import-time validation here. Validation belongs in `resolve()` (S2-04) and the loader (S2-03).
- **Mirror `src/codegenie/probes/registry.py` deliberately**. Same docstring shape, same `default_registry` placement, same fresh-instance fixture story. Reviewers shouldn't have to context-switch between two registry idioms.
- The `@register_plugin` shape is **not** the dual-shape (bare-or-parens) decorator that `register_probe` uses. ADR-0002's interface in arch-design §C2 shows `register_plugin(plugin, *, registry=None)` — i.e., a function call, not a class decorator. Plugins call `register_plugin(MyPlugin(), registry=local_registry)` from their `api.py`. Don't over-engineer.
- The fence test for the four-member `Plugin` surface is the structural enforcement ADR-0004 §Consequences names. Use `inspect.getmembers(Plugin, predicate=callable)` + the `manifest` attribute introspection — be explicit; reviewers will read this test as the canonical "the kernel is closed" assertion.
- Cross-test pollution (`default_registry` leaking) is the *exact* failure mode ADR-0002 §Tradeoffs warns about. The cross-test assertion is not optional belt-and-suspenders; it's an ADR consequence.
- `PluginId` comes from S1-01 (`codegenie.types.identifiers.PluginId`). Never `str` — that's an ADR-0010 violation a reviewer will catch immediately.
