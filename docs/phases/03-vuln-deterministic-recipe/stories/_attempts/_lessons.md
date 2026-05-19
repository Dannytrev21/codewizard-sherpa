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
   stub to the full Pydantic model. **2026-05-19 update (S2-04):** as
   the consuming surface widens past `.name`, replace the stub with
   `if TYPE_CHECKING: from codegenie.plugins.manifest import
   PluginManifest as PluginManifest`. The real Pydantic model is
   only loaded at type-check time, so the kernel stays cold-start
   clean while every documented field is type-known.

4. **Avoid lazy intra-package imports if a fence test pops your
   package mid-session** (S2-04). `tests/fence/test_no_llm_in_transforms.py`
   does `for k in sys.modules: if k.startswith("codegenie.plugins."):
   sys.modules.pop(k)` and re-walks. A method that does
   `from codegenie.plugins import resolver as _resolver` inside its
   body fetches the new (C2) module after the pop, while the test's
   already-bound names hold the old (C1). The `_resolver._unpack`'s
   `case Concrete(...)` then sees a C1 instance of Concrete and trips
   `assert_never`. Bind the symbol at module load instead — the value
   is frozen at registry-load time and stays consistent with the
   test's globals. If you legitimately need a lazy import to break a
   real cycle, the lazy site is also the place a future test's
   module-reload will introduce class-identity drift; surface the
   trade-off.

5. **Pydantic v2 BaseModel with `arbitrary_types_allowed=True` still
   runtime-checks Protocol fields** (S2-04). A field typed as a
   `runtime_checkable` Protocol (e.g.
   `composed_adapters: dict[PrimitiveName, Adapter]`) rejects
   `object()` instances at `model_validate` time because the
   Protocol implements `__instancecheck__`. Test fakes for adapter
   maps need at least the Protocol's attribute set (here,
   `primitive: PrimitiveName`).

6. **Test fakes can — and often should — bypass production
   validators** (S2-04). The S2-02 `PluginManifest.name` validator
   rejects names like `a-plugin` (regex requires three `--`-segments)
   and the literal `universal--*--*` (regex rejects `*`). Resolver
   tests need both: `a-plugin` for sort tie-breakers,
   `universal--*--*` for the fallback fixture. Use
   `PluginManifest.model_construct(...)` in test fixtures; the
   manifest loader's own tests cover the production regex. Coupling
   resolver tests to the production name format would mean every
   sort-tie test ships with three nonsense `--`-segments.
