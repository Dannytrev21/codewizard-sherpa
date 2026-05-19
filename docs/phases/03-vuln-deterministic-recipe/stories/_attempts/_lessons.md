# Phase 3 — cross-story lessons (executor)

Append-only journal of reusable takeaways discovered during
phase-story-executor runs in this phase. New entries at the bottom.

## Lessons

1. **`@runtime_checkable` Protocols do not populate `__abstractmethods__`
   the way `abc.ABC` does** (S2-01). Fence tests that assert a
   Protocol's "exactly N members" must enumerate via the union of
   `dir(Cls)` and `Cls.__annotations__.keys()` — `dir()` alone omits
   attribute-only annotations on every Python version we've tested.

2. **Module-docstring strings are grep-able by Phase 2 fences** (S2-01).
   `test_zero_strategies_registered_in_phase2` does a literal substring
   search for `@register_dep_graph_strategy`. Referencing a sibling
   registry's decorator with the `@` prefix inside narrative prose trips
   it even when the reference is purely informational. Drop the `@` or
   use sufficiently distinct phrasing in cross-registry docstrings.

3. **`TYPE_CHECKING`-only forward-ref stubs still need typed fields**
   when production code reads attributes through them under `mypy
   --strict` (S2-01). A bare `class PluginManifest: ...` stub fails
   `[attr-defined]` on `plugin.manifest.name`. Add the minimal field
   set the kernel actually reads; the downstream story expands the
   stub to the full Pydantic model.
