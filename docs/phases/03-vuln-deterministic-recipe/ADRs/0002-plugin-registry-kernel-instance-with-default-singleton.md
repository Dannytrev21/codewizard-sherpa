# ADR-0002: Plugin / Registry kernel — instance-based with `default_registry` + fixture isolation

**Status:** Accepted
**Date:** 2026-05-17
**Tags:** plugin-architecture · registry · kernel · open-closed · phase-7-bake-test
**Related:** [0003](0003-plugin-resolution-and-universal-fallback-semantics.md), [0004](0004-plugin-private-capabilities-via-tccm.md), [0013](0013-synthetic-third-plugin-for-contract-bake-test.md), [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md), [production ADR-0028](../../../production/adrs/0028-task-class-introduction-order.md)

## Context

Production ADR-0031 commits the system to a plugin architecture where each `(task × language × build-tool)` tuple is a plugin and where Phase 7's distroless work must land "extension by addition" — zero edits to existing plugins or the kernel. Phase 3 is the **first** instantiation of that contract: it ships `vulnerability-remediation--node--npm` and the `universal--*--*` fallback, and its kernel becomes the closed-for-modification anchor that every later phase composes against (`phase-arch-design.md §Component design C2`, `final-design.md §Synthesis ledger row 6`).

The performance-first lens design proposed a **module-level mutable singleton** (`_REGISTRY: dict = {}` populated by `@register_plugin` at import time). Best-practices proposed an **instance + `default_registry` + fixture-isolation** pattern matching Phase 6.5's already-merged `TaskClassRegistry`. Security was silent on the registry shape. The critic's pattern review and `critique.md §Pattern claims that don't survive scrutiny` flagged the module-level mutable dict as the toolkit's "side effects at module import time" anti-pattern.

## Options considered

- **Option A — Module-level mutable singleton.** `_REGISTRY: dict[PluginId, Plugin] = {}`; `@register_plugin` mutates it on import. **Pattern:** Registry, but applied as the toolkit's flagged anti-shape. Test isolation is impossible without `monkeypatch` of module globals — fragile, leaks across test sessions.
- **Option B — Pure DI: every consumer constructs and passes its own `PluginRegistry`.** No default singleton; every call site explicitly threads the registry. **Pattern:** Dependency inversion taken to a literal extreme. Eliminates global state but adds 5–10 lines of plumbing at every call site for zero capability the CLI needs.
- **Option C — Instance with `default_registry` module-level instance + `@register_plugin(registry=...)` parameter for fixture isolation.** Production code uses the default; tests pass a fresh `PluginRegistry()` instance. **Pattern:** Registry pattern as written in the toolkit — same shape as Phase 6.5's `TaskClassRegistry`. Mirrors `pytest`'s plugin model.

## Decision

Adopt **Option C.** Ship `class PluginRegistry` in `src/codegenie/plugins/registry.py` with `register(plugin)`, `get(id)`, `resolve(scope)`, `all()`. Ship one module-level `default_registry: PluginRegistry` instance and a `def register_plugin(plugin, *, registry: PluginRegistry | None = None)` helper that mutates the passed registry (or `default_registry` if `None`). Tests pass fresh `PluginRegistry()` instances; production code uses the default.

## Tradeoffs

| Gain | Cost |
|---|---|
| Matches Phase 6.5's `TaskClassRegistry` shape exactly — one less thing reviewers must hold in their head | Two ways to register (with vs without explicit registry param); discoverability cost |
| Test isolation is a one-line fixture (`registry = PluginRegistry()`); no `monkeypatch` of module globals | The `default_registry` is still global state; a misbehaving test that forgets to use a fresh registry can pollute later tests |
| `@register_plugin` decorator is the toolkit's textbook Registry shape — no eager validation, no side effects at registration | Validation happens at `resolve()` time; a malformed plugin only surfaces at first dispatch |
| Adding a new plugin = new directory + decorator call; zero edits to `registry.py` or any existing plugin (ADR-0031's "extension by addition" honored) | The `@register_plugin` call must be at module-import time, which couples plugin loading to Python import order |
| Phase 7's distroless plugin slots in mechanically; the registry has no hardcoded plugin names to add to | The kernel's `resolve()` algorithm becomes a hot path — must stay O(plugins) and avoid eager work |

## Pattern fit

Implements **Registry pattern** (toolkit §Run-shape patterns) exactly as the toolkit prescribes: "a registry is a dict; the decorator is `def register(name): def wrap(cls): registry[name] = cls; return cls; return wrap`. Stay that simple." Avoids the anti-pattern called out in the same section ("a registry that does more than registration — eager validation, side effects, cross-references at registration time. Keep it dumb; validate on use"). Also instantiates **Open/Closed Principle** at the file boundary — the kernel never imports plugins; plugins register on import (toolkit §Composition / coupling patterns).

## Consequences

- `src/codegenie/plugins/registry.py` is closed for modification once Phase 3 ships. Phase 7 distroless adds `plugins/distroless-migration--node--npm/` and a decorator call; zero edits here.
- `default_registry` is a `Final` module-level instance constructed once; replacement requires explicit DI (tests do this).
- `tests/fence/test_kernel_frozen.py` git-diffs the kernel file list against an ADR-anchored allowlist; any unauthorized edit fails CI.
- `PluginAlreadyRegistered` on collision; `PluginExtendsCycle(chain)` on cyclic `extends`; `PluginRejected(integrity_mismatch)` on `PLUGINS.lock` mismatch — every failure mode is a typed exception with exit code 4.
- Resolution stays O(plugins) per workflow — 30 μs against 3 plugins per the architecture spec. Linear scaling is fine at the projected Phase-10 plugin count (~15).
- Phase 6.5's `TaskClassRegistry` is the precedent; this ADR locks the precedent for every future plugin-shaped registry (signal kinds, dep-graph strategies, etc.).
- Tests must use `registry = PluginRegistry()` fixtures explicitly — a `conftest.py` fixture is provided.

## Reversibility

**Medium.** Moving from instance-based to pure-DI (Option B) is a mechanical refactor — replace every `register_plugin(p)` with `register_plugin(p, registry=cli_registry)` and pass `cli_registry` through the orchestrator's `__init__`. Moving to Option A (module-level mutable singleton) is also possible but loses test isolation and re-introduces the anti-pattern. The chosen shape is the *most* reversible because it carries both DI and singleton affordances simultaneously.

## Evidence / sources

- `../phase-arch-design.md §Component design C2`, §Design patterns applied row 1, §Patterns considered and deliberately rejected ("No DI container")
- `../final-design.md §Synthesis ledger row 6` (score 15/15) and §Pattern reconciliation row "Plugin / Registry"
- `../critique.md §Pattern claims that don't survive scrutiny` (module-level singleton flagged)
- Phase 6.5's `src/codegenie/eval/task_class_registry.py` — the precedent this ADR matches
- [production ADR-0031 — plugin architecture](../../../production/adrs/0031-plugin-architecture.md) (the umbrella commitment)
- [production ADR-0028 — task class introduction order](../../../production/adrs/0028-task-class-introduction-order.md)
- design-patterns-toolkit.md §Registry pattern, §Open/Closed Principle
