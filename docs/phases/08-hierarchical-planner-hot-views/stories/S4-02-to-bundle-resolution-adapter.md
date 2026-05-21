# Story S4-02 — Build the to_bundle_resolution adapter

**Step:** Step 4 — Build the `ConcreteResolution → BundleResolution` adapter (C2)
**Status:** Ready
**Effort:** M
**Depends on:** S4-01
**ADRs honored:** ADR-0009, ADR-0010

## Context
The Supervisor's `build_bundle` node must turn a resolved plugin into a Context Bundle, but the shipped `resolver.resolve` and the shipped `BundleBuilder.build` do not structurally line up — the resolver returns `ConcreteResolution` (with `composed_adapters: dict[PrimitiveName, Adapter]`, *objects*) and the builder expects a `BundleResolution` Protocol (`composed_dispatch: Mapping[PrimitiveName, AdapterDispatch]`, *async callables*). This story builds Component C2: the first-class `ConcreteResolution → BundleResolution` Adapter that translates the mismatch — `ResolvedBundleInput` plus the pure `to_bundle_resolution` function — so the shipped `BundleBuilder` is reused unchanged, never forked. This is foundational work that unblocks the Step 6 `build_bundle_node`.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C2 — ConcreteResolution → BundleResolution adapter` — the public interface (`ResolvedBundleInput`, `to_bundle_resolution`), internal structure, dependencies
  - `../phase-arch-design.md §Gap 2` — the three concrete mismatches the adapter must translate
  - `../phase-arch-design.md §Control flow` — step 3 (`build_bundle_node` calls `to_bundle_resolution` then `BundleBuilder.build`)
  - `../phase-arch-design.md §Design patterns applied` — "Adapter genuinely translates, is not a forwarder"
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0009-concrete-resolution-to-bundle-resolution-adapter.md` — ADR-0009 — the Adapter pattern decision; `to_bundle_resolution` must *translate* (objects→callables; placeholder→real), not re-export; reuse the shipped `BundleBuilder` unchanged
  - `../ADRs/0010-repoid-newtype-in-the-identifiers-module.md` — ADR-0010 — domain IDs are newtypes; use `PluginId`, `PrimitiveName`, never raw `str`
- **Existing code (consume these, do not fork):**
  - `src/codegenie/plugins/bundle.py` — `BundleResolution` Protocol (line ~276 — `composed_tccm: TCCM`, `composed_dispatch: Mapping[PrimitiveName, AdapterDispatch]`, `plugin_id: PluginId`); `AdapterDispatch = Callable[[ContextQuery], Awaitable[AdapterResult]]` (line ~202)
  - `src/codegenie/plugins/resolver.py` — `ConcreteResolution` (line ~137 — `plugin: Plugin`, `composed_tccm: ComposedTccm`, `composed_adapters: dict[PrimitiveName, Adapter]`)
  - `src/codegenie/plugins/protocols.py` — `Adapter` Protocol (line ~56 — currently `primitive: PrimitiveName`; the method surface lands later)
  - `src/codegenie/plugins/tccm.py` — the real `TCCM` (line ~226)
- **Attempt log:**
  - `../_attempts/S4-01.md` — read first; tells you whether `composed_tccm` is the placeholder or the real `TCCM`

## Goal
A pure `to_bundle_resolution(ConcreteResolution) -> ResolvedBundleInput` exists whose output structurally satisfies the shipped `BundleResolution` Protocol, mapping each `Adapter` object to its `AdapterDispatch` callable.

## Acceptance criteria
- [ ] `codegenie/supervisor/bundle_resolution.py` exports `ResolvedBundleInput` (a frozen Pydantic model with `composed_tccm`, `composed_dispatch`, `plugin_id`) and the pure `to_bundle_resolution` function.
- [ ] A `ResolvedBundleInput` instance built from a `ConcreteResolution` fixture structurally satisfies `codegenie.plugins.bundle.BundleResolution` — confirmed by `mypy --strict` (a typed assignment to a `BundleResolution`-annotated name) **and** a runtime `isinstance`-against-`Protocol` check.
- [ ] `to_bundle_resolution` maps every entry of `ConcreteResolution.composed_adapters` (`Adapter` objects) into a `composed_dispatch` `Mapping[PrimitiveName, AdapterDispatch]` of callables — no `Adapter` object survives into the output.
- [ ] `to_bundle_resolution` imports no I/O module — proven by a functional-core purity AST test mirroring `tests/unit/plugins/test_resolver_purity.py`.
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files; `make lint-imports` stays green (`codegenie.supervisor` LLM-SDK-fenced).

## Implementation outline
1. Read `../_attempts/S4-01.md` to know whether `composed_tccm` is the placeholder or the real `TCCM`.
2. Declare `ResolvedBundleInput` — a frozen Pydantic model (`ConfigDict(frozen=True, arbitrary_types_allowed=True)`) with `composed_tccm: TCCM`, `composed_dispatch: Mapping[PrimitiveName, AdapterDispatch]`, `plugin_id: PluginId` — matching the `BundleResolution` Protocol property-by-property.
3. Write the pure `to_bundle_resolution(resolution: ConcreteResolution) -> ResolvedBundleInput`: bind each `Adapter` object's primitive-method to an `AdapterDispatch` callable for `composed_dispatch`; carry `composed_tccm` through as the rich `TCCM`; derive `plugin_id` from `resolution.plugin`.
4. Leave the placeholder-detection / `ResolverTccmPlaceholder`-raising to S4-02's sibling S4-03 — but structure `to_bundle_resolution` so S4-03 can insert the guard at the function's head without a re-shape.
5. Wire `bundle_resolution` into `codegenie/supervisor/__init__.py`'s `__all__` only for the names the public surface needs (mind the ≤24-name budget).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/supervisor/test_bundle_resolution_adapter.py`

One red test per behavior:

```python
def test_to_bundle_resolution_output_satisfies_bundle_resolution_protocol() -> None:
    # arrange: a ConcreteResolution fixture with a real (or fixture) TCCM and
    # one composed_adapters entry.
    resolution = make_concrete_resolution_fixture()
    # act: run the adapter.
    result = to_bundle_resolution(resolution)
    # assert: the output structurally satisfies the shipped BundleResolution
    # Protocol — the type-checker proves it; isinstance proves it at runtime.
    from codegenie.plugins.bundle import BundleResolution
    accepted: BundleResolution = result          # mypy --strict must accept this
    assert isinstance(result, BundleResolution)  # runtime_checkable Protocol

def test_to_bundle_resolution_maps_adapter_objects_to_dispatch_callables() -> None:
    # arrange: a ConcreteResolution whose composed_adapters has a known primitive.
    resolution = make_concrete_resolution_fixture()
    # act
    result = to_bundle_resolution(resolution)
    # assert: every composed_dispatch value is a callable (AdapterDispatch),
    # never the Adapter object — the adapter genuinely translates (ADR-0009).
    assert set(result.composed_dispatch) == set(resolution.composed_adapters)
    assert all(callable(v) for v in result.composed_dispatch.values())
```

A second test file for the purity fence:

```python
# tests/unit/supervisor/test_bundle_resolution_purity.py
def test_to_bundle_resolution_imports_no_io_module() -> None:
    # AST source-scan of bundle_resolution.py asserting no import of asyncio
    # I/O, redis, pathlib-write, subprocess, etc. — functional-core fence.
    ...
```

### Green — make it pass
Declare `ResolvedBundleInput` and implement `to_bundle_resolution` as a pure transform: a dict-comprehension binding each `Adapter`'s primitive-method into an `AdapterDispatch`, carry `composed_tccm` through, set `plugin_id`. The smallest code that makes both behaviors and the purity scan pass.

### Refactor — clean up
Type hints on all signatures; a module docstring naming this as Component C2 and citing ADR-0009; a function docstring on `to_bundle_resolution` describing the three translations. Honor the ≤24-name public surface (only export what `build_bundle_node` needs). Confirm `make lint-imports` LLM-SDK fence stays green.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/supervisor/__init__.py` | New (or extend) — package marker; export the C2 public names within budget |
| `src/codegenie/supervisor/bundle_resolution.py` | New — `ResolvedBundleInput` model + pure `to_bundle_resolution` (Component C2) |
| `tests/unit/supervisor/test_bundle_resolution_adapter.py` | New — Protocol-satisfaction and object→callable mapping tests |
| `tests/unit/supervisor/test_bundle_resolution_purity.py` | New — functional-core purity AST fence |

## Out of scope
- The `ResolverTccmPlaceholder` typed error and the fail-loud guard on the placeholder `composed_tccm` — S4-03.
- The `build_bundle_node` that calls `to_bundle_resolution` then `BundleBuilder.build` — Step 6 (S6-02).
- The `SupervisorState` / `SupervisorDecision` models — Step 2.

## Notes for the implementer
- `to_bundle_resolution` must *translate*, not forward (ADR-0009 §Pattern fit) — `Adapter` objects become `AdapterDispatch` callables, the field name changes (`composed_adapters` → `composed_dispatch`). A pass-through re-export would be the rejected anti-pattern.
- Reuse the shipped `BundleBuilder` and `BundleResolution` Protocol unchanged — never fork them (ADR-0009; commitment §5; Rule 11).
- The `Adapter` Protocol currently exposes only `primitive`; its method surface lands later. Bind whatever callable surface the shipped `Adapter` actually exposes — read `protocols.py` at execution time and adapt to its real shape; do not assume a method name.
- `ResolvedBundleInput` needs `arbitrary_types_allowed=True` (the `BundleResolution` Protocol carries non-Pydantic callables in `composed_dispatch`) — mirror the C2 interface in `phase-arch-design.md §C2`.
- Keep the function pure — no Redis, no disk, no event log. The impure surface (`resolver.resolve`, `BundleBuilder.build`) is the `build_bundle_node`'s job in Step 6.
- Watch the ≤24-name public-surface budget across the four new packages — `bundle_resolution` should export at most two names.
