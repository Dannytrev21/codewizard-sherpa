# Story S1-08 — `@register_probe(heaviness=, runs_last=)` + coordinator sort-order edit

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Done (GREEN 2026-05-15) — all 17 ACs verified; see `_attempts/S1-08.md`
**Effort:** M
**Depends on:** S1-05
**ADRs honored:** 02-ADR-0003

## Evidence — GREEN on attempt #1 (2026-05-15)

- **Code:** `src/codegenie/probes/registry.py` (`Heaviness`, `_HEAVINESS_RANK`, `ProbeRegEntry`, `Registry.sorted_for_dispatch`, `Registry.sorted_for_task`, `Registry.decorator`, dual-shape `register_probe`), `src/codegenie/coordinator/coordinator.py` (`gather(..., *, runs_last_names)` partition + per-wave `coordinator.dispatch.order` log), `src/codegenie/cli.py` (`_seam_registry_for_task` → `sorted_for_dispatch`; new sibling `_seam_runs_last_names`).
- **Tests added:** `tests/unit/probes/test_registry_heaviness.py` (16 tests, incl. Hypothesis property-based AC-15), `tests/unit/coordinator/test_coordinator_sort_order.py` (4 tests, incl. AC-13 cross-wave hoist + AC-10 per-wave log + AC-6b single semaphore), `tests/unit/test_cli_seam_sorted_dispatch.py` (3 tests, AC-6a).
- **Gates green:** `ruff check` + `ruff format --check` clean on touched files; `mypy --strict src/` → "Success: no issues found in 67 source files"; full suite → 1790 passed / 3 deselected / 2 xfailed (the 2 xfailed are pre-existing tracked S4-02 / ADR-0006 limitations); `pre-commit run --all-files` passes every hook.
- **AC-by-AC coverage:** see `_attempts/S1-08.md` §"AC coverage map".
- **Phase 0 contract freeze:** `tests/unit/test_probe_contract.py` continues green — `Probe` ABC and `ProbeContext` untouched.

## Validation notes (2026-05-15, phase-story-validator)

The story was HARDENED after a four-critic pass. Summary of changes:

- **Consistency (block)** — Coordinator integration was under-specified. The actual coordinator at `src/codegenie/coordinator/coordinator.py` does **not** call `Registry.sorted_for_task()`; it receives a pre-resolved `probes: Sequence[Probe]` list from `_seam_registry_for_task()` at `src/codegenie/cli.py:239–258`, which currently calls `default_registry.all_probes()`. The integration point for sort-order is the **CLI seam**, not the coordinator's internals. Files-to-touch updated to include `src/codegenie/cli.py`. AC-6 split into AC-6a (seam reads sorted order) + AC-6b (coordinator preserves single Semaphore, no per-tier semaphores).
- **Consistency (block)** — The coordinator partitions probes into a prelude wave (`tier == "base"`) and a Wave-2 rest. `phase-arch-design.md §"Component design" #1` annotates `IndexHealthProbe.tier = "base"`. Naïvely, that would dispatch B2 in Wave 1, **before** any heavy SCIP/SBOM probe — defeating the entire `runs_last` semantic. Added AC-13 making the cross-wave invariant explicit and verifiable: a `runs_last=True` probe **must** dispatch after every non-`runs_last` probe regardless of its declared `tier`. The seam (or coordinator) hoists `runs_last=True` probes out of Wave 1 into the tail of Wave 2.
- **Coverage (harden)** — Missing edge-case ACs added: empty registry (AC-14a), single `runs_last=True` only (AC-14b), all-same-heaviness preserves registration order (AC-14c). The "two `runs_last=True` probes" case in AC-4 conflicts with 02-ADR-0003 Tradeoffs row 4 ("one probe per gather may set it"). The story's intent is *the sort is well-defined for ≥1 runs_last*, not that the design endorses multiple — AC-4 reworded to say so, and an explicit ADR-amendment-deferred note added to `Notes for the implementer`.
- **Test-Quality (harden)** — `test_module_level_decorator_backward_compatible_no_parens` was mutation-thin (only asserted `returned is cls`). Rewritten to (a) use a sub-registry so default_registry isn't polluted across tests, (b) assert the entry **actually appears** in `sorted_for_dispatch()` with defaults `("light", False)`. Now fails if the decorator silently drops kwargs OR fails to register.
- **Test-Quality (harden)** — `test_coordinator_sort_order.py` was a `...` sketch. Replaced with a concrete test that captures dispatch-entry timestamps via a `_FakeRecorder` probe and asserts the observed order matches `sorted_for_dispatch()`. The test would fail if `sorted_for_dispatch` were stubbed to return `self._entries` unchanged (no-op).
- **Test-Quality (harden + property-based)** — Added AC-15 + a property-based test (Hypothesis) over the four sort invariants: (1) every `runs_last=True` entry appears after every `runs_last=False` entry; (2) within each partition, heaviness rank is non-decreasing; (3) ties within (partition, heaviness) preserve registration order; (4) `len(output) == len(input)` and the output is a permutation of the input. Property-based shrinking will surface any off-by-one in the heaviness rank dict.
- **Coverage (harden)** — AC-10 only specified one `coordinator.dispatch.order` event. The coordinator has two waves. AC-10 reworded: emit `coordinator.dispatch.order` **once per wave** with the wave-1 / wave-2 ordered probe-name lists, OR a single event carrying both lists keyed by wave. Test must verify both wave-1 and wave-2 orderings observable from logs.
- **Coverage (harden)** — AC-8 was unverified ("Phase 0/1 probes continue to register without per-probe edits"). Added AC-8 test: import `codegenie.probes` (triggers every concrete `@register_probe` decoration) and assert `default_registry.sorted_for_dispatch()` contains every Phase 0/1 probe with `heaviness="light", runs_last=False`. This is the real backward-compat guarantee.
- **Coverage (harden)** — Added AC-16: `_filter` lru_cache compatibility. The current module-level `_filter(probes_tuple, task, languages)` returns `tuple[type[Probe], ...]`. The story's `sorted_for_task` must either (a) preserve the same cache surface (filter-then-sort), or (b) introduce a new cache aligned with the new return shape. Whichever path, a test must verify cache invalidation across two different registries does not leak.
- **Design-Patterns (note, not AC)** — `codegenie.probes.registry` is the **1st** of three registries in this phase (probes / indices / depgraph — see `src/codegenie/indices/registry.py:26–29` docstring naming the rule-of-three trigger queued for S1-10). Added implementer note: keep `ProbeRegEntry` shape compatible with a future `KernelRegistryEntry[K, V]` extract (frozen dataclass, generic-friendly field names). **Do not** introduce the kernel here — Rule 2: three similar lines is better than premature abstraction; S1-10 will be the third precedent and the right moment.
- **Design-Patterns (harden)** — `Heaviness` is a `Literal["light","medium","heavy"]`. The `_HEAVINESS_RANK: dict[Heaviness, int]` is the only place ordering is encoded. Added an AC-17 mypy-level invariant: `_HEAVINESS_RANK`'s key set must equal the `Heaviness` `Literal` arms. A unit test uses `typing.get_args(Heaviness)` to assert exhaustive coverage — surfaces drift loud at CI time if a 4th tier is ever added.

Critic priority resolution applied (`Consistency > Coverage > Test-Quality > Design-Patterns`):

- Consistency-block on tier-partition vs runs_last is honored by AC-13 (the cross-wave invariant); design-patterns critic's suggestion to "make the prelude/Wave-2 split itself a strategy plugin" was rejected as premature (Rule 2; no rule-of-three trigger yet).
- Coverage critic wanted an AC asserting "multiple `runs_last=True` probes raise a warning". Resolved against by 02-ADR-0003 Tradeoffs row 4 ("`runs_last` is a global ordering primitive (one probe per gather may set it)") — the design admits but does not police; sort is well-defined either way. Warning behaviour deferred to a future ADR amendment if drift surfaces.

Verdict: **HARDENED** — story now binds the implementer to the load-bearing invariant (`runs_last` overrides tier-partition) and gives the validator pass concrete, mutation-resistant tests to verify against.

## Context

`IndexHealthProbe` (B2) must run *after* every sibling that produces a freshness signal, and `RuntimeTraceProbe` / `ScipIndexProbe` (heavy) should *start first* under the single `Semaphore(min(cpu_count(), 8))` so total wall-clock minimizes. The architect's choice (02-ADR-0003) is *not* to edit the `Probe` ABC (`localv2.md §4` is frozen) but to ride scheduling concerns on the registry decorator: `@register_probe(heaviness="heavy", runs_last=True)`. This story extends the registry and the coordinator's sort logic without touching the ABC.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #1 — IndexHealthProbe` — `runs_last=True` is the load-bearing annotation on B2.
  - `../phase-arch-design.md §"Logical view"` + `§"Process view"` — coordinator reads `heaviness` from the registry; heavy first; `runs_last` reserved for the tail.
  - `../phase-arch-design.md §"Design patterns applied"` row 4 — registry + decorator-data over ABC fields; refuses `cost_tier: Literal[0..3]` on the ABC.
  - `../phase-arch-design.md §"Tradeoffs (consolidated)"` row "Registry annotations instead of ABC fields" — preserves contract freeze.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-coordinator-heaviness-sort-annotation.md` — 02-ADR-0003 — the decision and its consequences; `Probe` ABC is **not** edited.
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0007-probe-contract-freeze.md` (Phase 0 ADR-0007) — the Phase 0 contract-freeze snapshot test continues to pass.
- **Source design:**
  - `../final-design.md §13 — Registry annotations instead of ABC fields` — the deliberate scope.
- **Existing code:**
  - `src/codegenie/probes/registry.py` — Phase 0/1 `Registry` class; `register_probe` is currently a bare decorator (no kwargs). Extend in place.
  - `src/codegenie/coordinator/coordinator.py` — Phase 0/1 dispatch path; the sort-order edit lives here.
  - `src/codegenie/probes/base.py` — **NOT touched** (Phase 0 contract freeze).
- **External docs (only if directly relevant):**
  - None.

## Goal

Extend `src/codegenie/probes/registry.py` to accept `@register_probe(heaviness: Literal["light","medium","heavy"]="light", runs_last: bool=False)`, store both kwargs alongside each registered probe class, expose `Registry.sorted_for_dispatch() -> tuple[ProbeRegEntry, ...]` returning heavy → medium → light → `runs_last=True` order; extend `src/codegenie/coordinator/coordinator.py` to read that order under the existing single `Semaphore(min(cpu_count(), 8))`. The `Probe` ABC is **not** edited.

## Acceptance criteria

- [ ] **AC-1.** `register_probe` is now a decorator-factory: `register_probe(*, heaviness: Literal["light","medium","heavy"]="light", runs_last: bool=False) -> Callable[[type[Probe]], type[Probe]]`. The old positional call site `@register_probe` (no parens) still works — backward-compatible with Phase 0/1 probes (defaults `heaviness="light"`, `runs_last=False`). The dual-shape decorator pattern is the canonical approach (handle both `register_probe(cls)` and `register_probe(...)(cls)`).
- [ ] **AC-2.** `Registry.register` accepts `(cls, *, heaviness, runs_last)` and stores a `ProbeRegEntry(cls, heaviness, runs_last)` (frozen dataclass). Existing duplicate-name detection is preserved.
- [ ] **AC-3.** `Registry.sorted_for_dispatch() -> tuple[ProbeRegEntry, ...]` returns:
  - First: every entry with `runs_last=False`, ordered `heavy` → `medium` → `light`, ties broken by registration order (stable).
  - Last: every entry with `runs_last=True`, ordered `heavy` → `medium` → `light`, ties broken by registration order.
  Result: a `runs_last=True` light probe still runs after a `runs_last=False` heavy probe — `runs_last` dominates `heaviness`.
- [ ] **AC-4.** A synthetic mixed registry test (light+light, medium+medium, heavy+heavy, one `runs_last=True heaviness="light"`, one `runs_last=True heaviness="heavy"`) dispatches in the asserted exact order. The sort is well-defined for ≥1 `runs_last=True` entries (the design admits but does not police multiple — see 02-ADR-0003 Tradeoffs row 4 + `Notes for the implementer`). Parametrized.
- [ ] **AC-5.** `Registry.for_task(...)` (Phase 0 method) preserves filter semantics; `sorted_for_dispatch` is layered on top — `Registry.sorted_for_task(task, languages) -> tuple[ProbeRegEntry, ...]` combines both (filter, then sort).
- [ ] **AC-6a.** `src/codegenie/cli.py:_seam_registry_for_task()` (the call site that resolves the probes list passed to `coordinator.gather`) is updated to consume `default_registry.sorted_for_dispatch()` (or `sorted_for_task` once Phase 2 widens to non-`*` task filters) instead of `default_registry.all_probes()`. The order the coordinator receives **is** the sorted order. The seam preserves the current "instantiate each class" step (`[cls() for cls in ...]`).
- [ ] **AC-6b.** `src/codegenie/coordinator/coordinator.py` continues to dispatch under the **existing** single `Semaphore(min(cpu_count(), 8))`. No per-tier semaphores. No `pytest-xdist`. (02-ADR-0009 + 02-ADR-0003 §Consequences.) The coordinator does **not** re-sort what it receives — preserves "trust the seam" + minimizes the ~15 LOC edit budget the architect specified.
- [ ] **AC-7.** The Phase 0 contract-freeze snapshot test (`tests/unit/test_probe_contract.py`) stays green — `Probe` ABC unchanged (`base.py` not edited in this story).
- [ ] **AC-8.** Phase 0/1 existing probes (`LanguageDetectionProbe`, `NodeBuildSystemProbe`, `NodeManifestProbe`, `CIProbe`, `DeploymentProbe`, `TestInventoryProbe`, parser probes) continue to register without per-probe edits. **Verified by a test** that imports `codegenie.probes` (triggering every `@register_probe` decoration) and asserts every Phase 0/1 probe appears in `default_registry.sorted_for_dispatch()` with `heaviness="light", runs_last=False`. Failure mode caught: a misimplemented dual-shape decorator that silently dropped Phase 0/1 registrations on import.
- [ ] **AC-9.** Dispatch-order test under a coordinator-like environment: synthetic probes record a monotonic `time.perf_counter_ns()` on entry; the order observed matches `sorted_for_dispatch`'s declared order modulo the semaphore-induced parallelism for ties (assert: for any two probes of *different* heaviness tier and same `runs_last`, the heavier probe's entry timestamp is strictly less than the lighter probe's). Mutation-resistant: would fail if `sorted_for_dispatch` were stubbed to return `self._entries` unchanged.
- [ ] **AC-10.** Structured log emission: the dispatch path emits `coordinator.dispatch.order` **per wave** — one event with `wave="prelude"` carrying the wave-1 ordered probe-name list, and one event with `wave="rest"` carrying the wave-2 ordered list. Verified by structlog capture in one test that asserts both lists are present AND that any `runs_last=True` probe appears at the end of the `wave="rest"` list (never in `wave="prelude"`). Audit anchor.
- [ ] **AC-11.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-12.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/probes/` + `tests/unit/coordinator/` + `tests/unit/test_cli.py` (the seam-touched files) all pass on the touched files.
- [ ] **AC-13. (cross-wave `runs_last` invariant — load-bearing for IndexHealthProbe.)** A `runs_last=True` probe dispatches **after every non-`runs_last` probe regardless of declared `tier`**. The coordinator currently partitions by `tier == "base"` (prelude) vs other (Wave 2). `phase-arch-design.md §"Component design" #1` annotates `IndexHealthProbe.tier = "base"`. The seam or coordinator MUST hoist `runs_last=True` probes out of the prelude partition and into the tail of Wave 2 — never dispatch them in Wave 1. Verified by a test: a `tier="base"` + `runs_last=True` probe's entry timestamp is strictly greater than every `tier != "base"` non-`runs_last` probe's entry timestamp.
- [ ] **AC-14a.** Empty registry: `Registry().sorted_for_dispatch()` returns `()` without raising.
- [ ] **AC-14b.** All entries `runs_last=True`: `sorted_for_dispatch` returns them in `heavy → medium → light` order with registration-order tie-breaks; no entry is dropped.
- [ ] **AC-14c.** All entries same heaviness, all `runs_last=False`: `sorted_for_dispatch` preserves registration order exactly (stable-sort guarantee is observable).
- [ ] **AC-15. (property-based.)** Hypothesis-based test over the four sort invariants holds for arbitrary registry shapes: (1) every `runs_last=True` entry appears after every `runs_last=False` entry; (2) within each partition (runs_last True/False), heaviness rank is non-decreasing per `_HEAVINESS_RANK`; (3) ties within (partition, heaviness) preserve `registration_index` order; (4) `len(output) == len(input)` and the output is a permutation of the input (no duplicates, no drops). Failure surfaces via Hypothesis shrinker → minimal counter-example.
- [ ] **AC-16. (cache correctness.)** Two independent `Registry()` instances do not cross-pollute. `r1.sorted_for_dispatch()` followed by `r2.sorted_for_dispatch()` returns r1's entries and r2's entries respectively. If the implementation chooses to `lru_cache` either `sorted_for_dispatch` or the underlying filter, the cache MUST be keyed such that two different `Registry` instances are not aliased (the Phase 0 `_filter` lives at module scope and takes `probes_tuple` precisely so the cache doesn't leak `self`; preserve that property).
- [ ] **AC-17. (`Heaviness` exhaustiveness.)** A unit test uses `typing.get_args(Heaviness)` to assert `set(_HEAVINESS_RANK.keys()) == set(typing.get_args(Heaviness))`. If a 4th tier is ever added to `Heaviness`, CI fails loud at this assertion rather than silently mis-sorting at runtime. (Make-illegal-states-unrepresentable invariant for the registry.)

## Implementation outline

1. In `src/codegenie/probes/registry.py`:
   - Add `ProbeRegEntry` frozen dataclass: `cls: type[Probe]`, `heaviness: Literal["light","medium","heavy"]`, `runs_last: bool`.
   - Change `Registry._probes` from `list[type[Probe]]` to `list[ProbeRegEntry]`. Maintain `all_probes()` for back-compat returning `tuple[type[Probe], ...]` (Phase 0/1 callers use this).
   - Add `Registry.sorted_for_dispatch()` and `Registry.sorted_for_task()`.
   - Rewrite `register_probe` as a dual-shape decorator: if the first arg is a `type` (Phase 0/1 style), treat as `@register_probe` (no parens); else treat as `@register_probe(...)`.
2. In `src/codegenie/coordinator/coordinator.py`:
   - Replace the Phase 0/1 dispatch iteration with `sorted_for_task` results.
   - Preserve the `Semaphore(min(cpu_count(), 8))` (one semaphore; do not split into per-tier).
   - Emit `coordinator.dispatch.order` log event.
3. Red tests → impl → refactor.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/test_registry_heaviness.py`

```python
from __future__ import annotations

import pytest

from codegenie.probes.base import Probe
from codegenie.probes.registry import (
    ProbeRegEntry,
    Registry,
    register_probe,
)


def _make_probe(name_: str) -> type[Probe]:
    class _P(Probe):
        name = name_
        layer = "B"
        tier = "base"
        applies_to_tasks = ["*"]
        applies_to_languages = ["*"]
        requires: list[str] = []
        declared_inputs: list[str] = []
        async def run(self, repo, ctx):  # type: ignore[no-untyped-def]
            raise NotImplementedError
    _P.__name__ = name_
    return _P


def test_sorted_dispatch_order_heavy_then_medium_then_light_then_runs_last() -> None:
    reg = Registry()
    a_light = reg.register(_make_probe("a_light"))
    b_medium = reg.register(_make_probe("b_medium"), heaviness="medium")
    c_heavy = reg.register(_make_probe("c_heavy"), heaviness="heavy")
    d_runs_last_light = reg.register(_make_probe("d_index_health"), runs_last=True)
    e_runs_last_heavy = reg.register(_make_probe("e_runs_last_heavy"), heaviness="heavy", runs_last=True)
    f_light = reg.register(_make_probe("f_light"))

    order = [e.cls.name for e in reg.sorted_for_dispatch()]
    # Non-runs_last first: heavy → medium → light; ties by registration order.
    # Runs_last last: heavy → medium → light.
    assert order == [
        "c_heavy",
        "b_medium",
        "a_light", "f_light",
        "e_runs_last_heavy",
        "d_index_health",
    ]


def test_default_heaviness_is_light_and_runs_last_false() -> None:
    reg = Registry()
    reg.register(_make_probe("x"))
    entries = reg.sorted_for_dispatch()
    assert len(entries) == 1
    assert entries[0].heaviness == "light"
    assert entries[0].runs_last is False


def test_decorator_factory_shape() -> None:
    reg = Registry()

    @reg.decorator(heaviness="heavy", runs_last=True)
    class P1(Probe):
        name = "p1"; layer = "B"; tier = "base"
        applies_to_tasks = ["*"]; applies_to_languages = ["*"]
        requires: list[str] = []; declared_inputs: list[str] = []
        async def run(self, repo, ctx): ...  # type: ignore[no-untyped-def]

    entries = reg.sorted_for_dispatch()
    assert entries[0].cls is P1
    assert entries[0].heaviness == "heavy"
    assert entries[0].runs_last is True


def test_module_level_decorator_backward_compatible_no_parens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Phase 0/1 probe decorated with bare @register_probe (no parens) still
    registers AND lands in the registry with defaults.

    Mutation-resistance: a buggy dual-shape decorator that returns ``cls``
    unchanged but never calls ``register()`` would pass the old assertion
    ``returned is cls``. This test fails that buggy implementation by also
    asserting the entry appears in ``sorted_for_dispatch()`` with defaults.
    """
    from codegenie.probes import registry as registry_mod

    fresh = Registry()
    monkeypatch.setattr(registry_mod, "default_registry", fresh)

    cls = _make_probe("legacy_phase0_probe")
    returned = register_probe(cls)  # treats first positional arg as the class

    assert returned is cls
    entries = fresh.sorted_for_dispatch()
    assert len(entries) == 1, "decorator must actually register, not just return cls"
    assert entries[0].cls is cls
    assert entries[0].heaviness == "light"
    assert entries[0].runs_last is False


def test_phase_0_1_probes_register_unedited() -> None:
    """AC-8: importing ``codegenie.probes`` triggers every Phase 0/1
    ``@register_probe`` decoration; all of them must land with defaults.

    This is the real backward-compat guarantee: ``LanguageDetectionProbe``,
    ``NodeBuildSystemProbe``, ``NodeManifestProbe``, ``CIProbe``,
    ``DeploymentProbe``, ``TestInventoryProbe``, plus the parser probes are
    not edited in this story; they must still appear in the default registry
    with ``heaviness="light", runs_last=False``.
    """
    import importlib

    import codegenie.probes  # noqa: F401 — import side effect

    importlib.import_module("codegenie.probes")
    from codegenie.probes.registry import default_registry

    entries = default_registry.sorted_for_dispatch()
    by_name = {e.cls.name: e for e in entries}
    expected_phase01 = {
        "language_detection",
        "node_build_system",
        "node_manifest",
        "ci",
        "deployment",
        "test_inventory",
    }
    missing = expected_phase01 - set(by_name.keys())
    assert not missing, f"Phase 0/1 probes dropped on import: {missing}"
    for name in expected_phase01:
        assert by_name[name].heaviness == "light", name
        assert by_name[name].runs_last is False, name


def test_empty_registry_sorted_dispatch_is_empty_tuple() -> None:
    """AC-14a."""
    assert Registry().sorted_for_dispatch() == ()


def test_all_runs_last_partition_orders_by_heaviness_then_registration() -> None:
    """AC-14b: every entry has runs_last=True; heavy → medium → light, then
    registration order within tier."""
    reg = Registry()
    reg.register(_make_probe("a"), heaviness="light", runs_last=True)
    reg.register(_make_probe("b"), heaviness="heavy", runs_last=True)
    reg.register(_make_probe("c"), heaviness="medium", runs_last=True)
    reg.register(_make_probe("d"), heaviness="heavy", runs_last=True)
    order = [e.cls.name for e in reg.sorted_for_dispatch()]
    assert order == ["b", "d", "c", "a"]


def test_heaviness_literal_arms_exhaustively_ranked() -> None:
    """AC-17: ``_HEAVINESS_RANK`` keys must equal ``Heaviness`` Literal arms.

    If a 4th tier is added to ``Heaviness`` but ``_HEAVINESS_RANK`` is not
    updated, this fails loud at CI rather than silently mis-sorting.
    """
    import typing

    from codegenie.probes.registry import _HEAVINESS_RANK, Heaviness

    assert set(_HEAVINESS_RANK.keys()) == set(typing.get_args(Heaviness))


# Property-based — AC-15.
from hypothesis import given, strategies as st

_heaviness_st = st.sampled_from(["light", "medium", "heavy"])
_runs_last_st = st.booleans()
_entry_specs_st = st.lists(st.tuples(_heaviness_st, _runs_last_st), min_size=0, max_size=20)


@given(specs=_entry_specs_st)
def test_sort_invariants_hold_for_arbitrary_registries(
    specs: list[tuple[str, bool]],
) -> None:
    """AC-15: four sort invariants hold for any list of (heaviness, runs_last)
    pairs.

    Mutation-resistance: shrinking will surface off-by-one rank-dict bugs,
    flipped runs_last partition, or non-stable tie-breaks.
    """
    from codegenie.probes.registry import _HEAVINESS_RANK

    reg = Registry()
    for i, (h, rl) in enumerate(specs):
        reg.register(_make_probe(f"p{i}"), heaviness=h, runs_last=rl)
    out = reg.sorted_for_dispatch()

    # (4) permutation of input — no drops, no dupes, same length.
    assert len(out) == len(specs)
    assert {e.cls.name for e in out} == {f"p{i}" for i in range(len(specs))}

    # (1) every runs_last=True after every runs_last=False.
    seen_runs_last = False
    for e in out:
        if e.runs_last:
            seen_runs_last = True
        else:
            assert not seen_runs_last, "runs_last=False after runs_last=True"

    # (2) within each partition, heaviness rank non-decreasing.
    for partition in (False, True):
        ranks = [_HEAVINESS_RANK[e.heaviness] for e in out if e.runs_last is partition]
        assert ranks == sorted(ranks), f"heaviness rank non-monotonic in {partition=}"

    # (3) ties within (partition, heaviness) preserve registration order.
    for partition in (False, True):
        for h in ("heavy", "medium", "light"):
            idxs = [e.registration_index for e in out if e.runs_last is partition and e.heaviness == h]
            assert idxs == sorted(idxs), f"tie-break unstable in {partition=}, {h=}"


def test_two_registries_do_not_cross_pollute() -> None:
    """AC-16: independent ``Registry()`` instances stay isolated.

    The Phase 0 ``_filter`` cache lives at module scope and takes the
    probes-tuple as a key; this test fails any implementation that aliases
    instances via a cache keyed on something less specific.
    """
    r1 = Registry()
    r2 = Registry()
    r1.register(_make_probe("only_in_r1"))
    r2.register(_make_probe("only_in_r2"))
    names_r1 = {e.cls.name for e in r1.sorted_for_dispatch()}
    names_r2 = {e.cls.name for e in r2.sorted_for_dispatch()}
    assert names_r1 == {"only_in_r1"}
    assert names_r2 == {"only_in_r2"}


def test_iter_order_is_stable_within_tier() -> None:
    """Ties are broken by registration order — load-bearing for cache key
    sensitivity and golden-file stability."""
    reg = Registry()
    for n in ["x1", "x2", "x3"]:
        reg.register(_make_probe(n))
    order = [e.cls.name for e in reg.sorted_for_dispatch()]
    assert order == ["x1", "x2", "x3"]


def test_phase_0_ABC_unchanged() -> None:
    """02-ADR-0003 §Decision — `Probe` ABC is not edited. Spot-check that
    `heaviness` and `runs_last` are NOT attributes on the ABC class."""
    assert not hasattr(Probe, "heaviness")
    assert not hasattr(Probe, "runs_last")
```

Test file path: `tests/unit/coordinator/test_coordinator_sort_order.py`

```python
from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from typing import Any

import pytest
import structlog
from structlog.testing import LogCapture

from codegenie.coordinator.coordinator import gather
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput
from codegenie.probes.registry import Registry


def _make_recorder_probe(
    name_: str,
    *,
    tier_: str = "task_specific",
    timeline: list[tuple[str, int]],
) -> type[Probe]:
    """A synthetic probe that records (name, perf_counter_ns) on entry to
    ``run`` and returns a trivial slice.

    ``timeline`` is a shared list the test threads receive entries into;
    after gather() returns, the order of the list reveals the actual
    dispatch order (modulo semaphore-induced parallelism for ties)."""

    class _P(Probe):
        name = name_
        layer = "B"
        tier = tier_
        applies_to_tasks = ["*"]
        applies_to_languages = ["*"]
        requires: list[str] = []
        declared_inputs: list[str] = []
        cache_strategy = "none"
        timeout_seconds = 5

        async def run(self, ctx: ProbeContext) -> ProbeOutput:  # type: ignore[no-untyped-def]
            timeline.append((name_, time.perf_counter_ns()))
            await asyncio.sleep(0.005)  # small yield so semaphore-bound ties surface
            return ProbeOutput(schema_slice={}, errors=[], warnings=[])

    _P.__name__ = name_
    return _P


def _seam_to_probes(reg: Registry) -> list[Probe]:
    """Mirror ``cli._seam_registry_for_task`` post-S1-08 behaviour:
    consume ``sorted_for_dispatch`` and instantiate."""
    return [e.cls() for e in reg.sorted_for_dispatch()]


@pytest.mark.asyncio
async def test_dispatch_order_under_single_semaphore(
    log_output: LogCapture,
    cache_force_miss: Any,
    fake_snapshot: Any,
    fake_task: Any,
    fake_config_max_8: Any,
    fake_sanitizer: Any,
) -> None:
    """AC-9 + AC-13: registry-declared order survives the single
    ``Semaphore(min(cpu_count(), 8))`` and ``runs_last=True`` dispatches after
    every non-runs_last sibling — including across the prelude/Wave-2
    partition.

    Mutation-resistance: would fail if ``sorted_for_dispatch`` were stubbed
    to return ``self._entries`` unchanged OR if the coordinator/seam ignored
    ``runs_last`` for ``tier="base"`` probes.
    """
    timeline: list[tuple[str, int]] = []
    reg = Registry()
    reg.register(_make_recorder_probe("a_light",   tier_="task_specific", timeline=timeline))
    reg.register(_make_recorder_probe("b_medium", tier_="task_specific", timeline=timeline), heaviness="medium")
    reg.register(_make_recorder_probe("c_heavy",  tier_="task_specific", timeline=timeline), heaviness="heavy")
    # The load-bearing case: tier="base" + runs_last=True — IndexHealth shape.
    reg.register(
        _make_recorder_probe("d_index_health", tier_="base", timeline=timeline),
        runs_last=True,
    )
    # A non-runs_last tier="base" probe — should still run in the prelude.
    reg.register(_make_recorder_probe("e_base_prelude", tier_="base", timeline=timeline))

    probes = _seam_to_probes(reg)
    await gather(fake_snapshot, fake_task, probes, fake_config_max_8, cache_force_miss, fake_sanitizer)

    order = [name for name, _ in timeline]

    # AC-13: d_index_health (runs_last=True) is strictly last, despite tier="base".
    assert order[-1] == "d_index_health"
    # Non-runs_last prelude probe runs before any non-prelude Wave-2 probe.
    assert order.index("e_base_prelude") < order.index("a_light")
    assert order.index("e_base_prelude") < order.index("b_medium")
    assert order.index("e_base_prelude") < order.index("c_heavy")
    # Within Wave 2 non-runs_last: heavy < medium < light by entry-timestamp.
    assert order.index("c_heavy") < order.index("b_medium")
    assert order.index("b_medium") < order.index("a_light")


@pytest.mark.asyncio
async def test_coordinator_dispatch_order_log_emitted_per_wave(
    log_output: LogCapture,
    cache_force_miss: Any,
    fake_snapshot: Any,
    fake_task: Any,
    fake_config_max_8: Any,
    fake_sanitizer: Any,
) -> None:
    """AC-10: ``coordinator.dispatch.order`` emitted once per wave; any
    ``runs_last=True`` probe appears at the tail of the rest-wave list, never
    in the prelude-wave list."""
    timeline: list[tuple[str, int]] = []
    reg = Registry()
    reg.register(_make_recorder_probe("base_a",   tier_="base", timeline=timeline))
    reg.register(_make_recorder_probe("rest_a",   tier_="task_specific", timeline=timeline), heaviness="heavy")
    reg.register(
        _make_recorder_probe("runs_last_x", tier_="base", timeline=timeline),
        runs_last=True,
    )
    probes = _seam_to_probes(reg)
    await gather(fake_snapshot, fake_task, probes, fake_config_max_8, cache_force_miss, fake_sanitizer)

    events = [r for r in log_output.entries if r.get("event") == "coordinator.dispatch.order"]
    waves = {e["wave"]: e["probe_order"] for e in events}
    assert set(waves.keys()) == {"prelude", "rest"}
    assert "runs_last_x" not in waves["prelude"]
    assert waves["rest"][-1] == "runs_last_x"
```

Notes on the test harness above: `log_output`, `cache_force_miss`, `fake_snapshot`, `fake_task`, `fake_config_max_8`, and `fake_sanitizer` are pytest fixtures the existing `tests/unit/coordinator/conftest.py` already provides (mirror their shape; the implementer reads that conftest and reuses or extends as needed — Rule 11, match the codebase's conventions). If a fixture doesn't yet exist, add it to the same conftest rather than inlining bespoke setup in this test file.

Run — confirm `ImportError`/`TypeError` on the new decorator-factory signature. Commit.

### Green — make it pass

In `src/codegenie/probes/registry.py`:

```python
from __future__ import annotations
import functools
from dataclasses import dataclass
from typing import Callable, Literal, Union, overload

from codegenie.errors import ProbeError
from codegenie.probes.base import Probe

__all__ = [
    "ProbeRegEntry", "Registry", "default_registry", "register_probe",
]

Heaviness = Literal["light", "medium", "heavy"]
_HEAVINESS_RANK: dict[Heaviness, int] = {"heavy": 0, "medium": 1, "light": 2}


@dataclass(frozen=True)
class ProbeRegEntry:
    cls: type[Probe]
    heaviness: Heaviness
    runs_last: bool
    registration_index: int  # tie-breaker for stable sort


class Registry:
    def __init__(self) -> None:
        self._entries: list[ProbeRegEntry] = []
        self._counter: int = 0

    def register(
        self,
        cls: type[Probe],
        *,
        heaviness: Heaviness = "light",
        runs_last: bool = False,
    ) -> type[Probe]:
        for e in self._entries:
            if e.cls.name == cls.name:
                raise ProbeError(
                    f"duplicate probe name {cls.name!r}: "
                    f"{e.cls.__module__}.{e.cls.__qualname__} and "
                    f"{cls.__module__}.{cls.__qualname__}"
                )
        self._entries.append(ProbeRegEntry(cls, heaviness, runs_last, self._counter))
        self._counter += 1
        return cls

    def decorator(
        self,
        *,
        heaviness: Heaviness = "light",
        runs_last: bool = False,
    ) -> Callable[[type[Probe]], type[Probe]]:
        def _wrap(cls: type[Probe]) -> type[Probe]:
            return self.register(cls, heaviness=heaviness, runs_last=runs_last)
        return _wrap

    def sorted_for_dispatch(self) -> tuple[ProbeRegEntry, ...]:
        non_last = sorted(
            (e for e in self._entries if not e.runs_last),
            key=lambda e: (_HEAVINESS_RANK[e.heaviness], e.registration_index),
        )
        last = sorted(
            (e for e in self._entries if e.runs_last),
            key=lambda e: (_HEAVINESS_RANK[e.heaviness], e.registration_index),
        )
        return tuple(non_last + last)

    def sorted_for_task(self, task: str, languages: frozenset[str]) -> tuple[ProbeRegEntry, ...]:
        # Filter then sort. Preserve Phase 0 _filter semantics.
        ...  # adapt from existing for_task implementation

    def all_probes(self) -> tuple[type[Probe], ...]:
        return tuple(e.cls for e in self._entries)

    def for_task(self, task: str, languages: frozenset[str]) -> tuple[type[Probe], ...]:
        # Phase 0/1 callers — unchanged signature
        return tuple(e.cls for e in self.sorted_for_task(task, languages))


default_registry = Registry()


# Dual-shape decorator: @register_probe (Phase 0/1, no parens) AND
# @register_probe(heaviness="heavy", runs_last=True) (Phase 2).
@overload
def register_probe(cls: type[Probe], /) -> type[Probe]: ...
@overload
def register_probe(*, heaviness: Heaviness = "light", runs_last: bool = False) -> Callable[[type[Probe]], type[Probe]]: ...
def register_probe(
    cls: type[Probe] | None = None,
    *,
    heaviness: Heaviness = "light",
    runs_last: bool = False,
) -> Union[type[Probe], Callable[[type[Probe]], type[Probe]]]:
    if cls is not None:
        # @register_probe  (no parens; Phase 0/1)
        return default_registry.register(cls)
    # @register_probe(heaviness=..., runs_last=...)  (Phase 2)
    return default_registry.decorator(heaviness=heaviness, runs_last=runs_last)
```

In `src/codegenie/coordinator/coordinator.py`:

- Locate the existing dispatch path (gather function).
- Replace the existing `registry.for_task(...)` iteration with `registry.sorted_for_task(...)` (or equivalent) so entries arrive in heaviness/runs-last order. Preserve the single `Semaphore(min(cpu_count(), 8))`.
- Emit `coordinator.dispatch.order` structlog event with the ordered list of probe names.

### Refactor — clean up

- Module docstring on `registry.py`: name 02-ADR-0003 (decorator-data, not ABC fields) and the runs_last invariant (`IndexHealthProbe` is the canonical user).
- The legacy `@register_probe` (no parens) backward-compat must be tested. Phase 0/1 probes are not edited.
- `Probe` ABC remains unchanged (`base.py` is not in this story's "Files to touch").
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/probes/registry.py src/codegenie/coordinator/coordinator.py tests/unit/probes/test_registry_heaviness.py tests/unit/coordinator/test_coordinator_sort_order.py`, `pytest tests/unit/probes/ tests/unit/coordinator/ -v`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/registry.py` | Add `ProbeRegEntry`, `_HEAVINESS_RANK`, `sorted_for_dispatch`, `sorted_for_task`, `Registry.decorator(...)`, dual-shape module-level `register_probe`. |
| `src/codegenie/cli.py` | (AC-6a) `_seam_registry_for_task()` switches from `default_registry.all_probes()` to `default_registry.sorted_for_dispatch()` (consumed via `[e.cls() for e in ...]`). Surgical — one method body. |
| `src/codegenie/coordinator/coordinator.py` | (AC-6b + AC-13) Trust the seam's order. The only edit is to (a) ensure the prelude/Wave-2 partition hoists `runs_last=True` probes out of `base` into the tail of `rest`, and (b) emit `coordinator.dispatch.order` once per wave with the ordered probe-name list. Preserves single `Semaphore(min(cpu_count(), 8))`. ~15 LOC per the architect's budget. |
| `tests/unit/probes/test_registry_heaviness.py` | Heaviness/runs_last ordering (AC-3, AC-4), decorator factory (AC-1), backward-compat including post-import default-registry contents (AC-8), ABC-unchanged (AC-7 spot-check), edge cases (AC-14a/b/c), `Heaviness` exhaustiveness (AC-17), property-based invariants (AC-15), cache isolation (AC-16). |
| `tests/unit/coordinator/test_coordinator_sort_order.py` | Coordinator honors registry order under single semaphore (AC-9), cross-wave `runs_last` invariant (AC-13), per-wave `coordinator.dispatch.order` log emission (AC-10). |
| `tests/unit/test_cli.py` *(if exists, else `tests/unit/test_cli_seam.py`)* | (AC-6a) The seam returns instances of every registered probe in `sorted_for_dispatch()` order. |

## Out of scope

- **`Probe` ABC edits** — explicitly forbidden by 02-ADR-0003 §Decision. Editing `src/codegenie/probes/base.py` here makes the Phase 0 contract-freeze snapshot test fail and breaks 02-ADR-0003's commitment.
- **Per-tier semaphores** — explicitly rejected by 02-ADR-0009 (`pytest-xdist` veto preserved) and architect's `cpu_count()=2` analysis (`../phase-arch-design.md §"Gap 2"`). Single `Semaphore(min(cpu_count(), 8))` only.
- **`pytest-xdist` reversal** — 02-ADR-0009.
- **`ProbeContext.image_digest_resolver`** — handled by S1-09 (the next story); this story does not edit `base.py`.
- **`IndexHealthProbe` itself** — S4-01; this story only ensures the registry has the `runs_last` annotation slot it will use.
- **Probe scheduling with `requires:` topological ordering** — Phase 0/1 already implements `requires`; this story does not change that. `runs_last` is a *layer* over `requires`; topo sort first, then within-batch heaviness sort.

## Notes for the implementer

- **Cross-wave `runs_last` is the load-bearing invariant** (AC-13). The architect's annotation `IndexHealthProbe.tier = "base"` plus `runs_last=True` is a deliberate stress on the prelude/Wave-2 partition: a naïve coordinator would dispatch B2 first (in the prelude), not last. The fix lives in the coordinator's partition step: split into `base = [p for p in probes if tier=="base" and not _runs_last(p)]` and append `runs_last=True` probes to the *end* of `rest`, regardless of declared tier. Resolve the "is this probe runs_last?" predicate via a coordinator-side helper that reads from the registry by probe `name` (or via a `ProbeMeta` lookup): the coordinator does NOT learn `runs_last` from the probe instance itself — that would re-introduce the ABC contract change 02-ADR-0003 rejected. One clean shape: `_seam_registry_for_task()` returns `list[tuple[Probe, ProbeMeta]]` (or pairs the seam emits) so the coordinator partitions on the metadata without touching `Probe`. Pick the shape that minimizes the coordinator's LOC delta.
- **`tier` semantic check with the architect (out-of-band).** The fact that `IndexHealthProbe.tier = "base"` is on the same probe that must run last is friction-inducing. If during implementation it becomes clear the cleaner shape is `IndexHealthProbe.tier = "task_specific"`, raise the question via an ADR amendment on 02-ADR-0003 or a follow-up story rather than silently re-tier'ing the probe — that decision is not in this story's scope (S4-01 owns `IndexHealthProbe` itself). For S1-08, treat AC-13 as the contract and make it work with `tier="base"`.
- **Rule-of-three kernel-extract is queued, not in scope.** `codegenie.probes.registry` is the **1st** of three decorator-registries in this phase (probes, then `codegenie.indices.registry` already shipped at S1-02, then `codegenie.depgraph.registry` at S1-10). `src/codegenie/indices/registry.py:26–29` already names the rule-of-three trigger. Keep `ProbeRegEntry` a frozen dataclass with field names that would survive a future generic `KernelRegistryEntry[K, V]` extract (`cls`, `registration_index`, and per-registry metadata fields). **Do not** introduce the kernel base in this story — Rule 2: three similar lines is better than premature abstraction; S1-10 is the right moment.
- **Dual-shape decorator is the canonical idiom.** The `cls=None` + overload pattern is in Python textbooks; ensure mypy is happy by using `@overload` properly. Test backward-compat explicitly — Phase 0/1 probes use `@register_probe` with no parens and must continue to work.
- **`Probe` ABC is not edited.** The Phase 0 contract-freeze snapshot test (`tests/unit/test_probe_contract.py`) is the structural defense. If that test fails after this story, the change is wrong — back out and route via the registry annotation instead.
- **Stable sort is load-bearing.** Cache keys and golden files depend on deterministic dispatch order; ties between probes of the same heaviness/runs_last MUST be broken by registration order (the `registration_index` field). `sorted()` in Python is stable; using the rank-tuple key preserves the registration-index tie-break.
- **`runs_last` dominates `heaviness`.** A `runs_last=True heaviness="light"` probe still runs after a `runs_last=False heaviness="heavy"` probe. The architect's intent is: `runs_last` means *truly last*, not "last within its heaviness tier."
- **Coordinator integration is surgical.** The existing `coordinator.gather` already iterates registered probes; the change is *which iteration order it reads*. Do not rewrite the dispatch loop, the semaphore, or the cache lookup. The synthesis explicitly says "~15 LOC sort-order edit to Phase 0 coordinator" (`../phase-arch-design.md §"Tradeoffs (consolidated)"` row 2).
- **`requires:` interactions.** Phase 0's coordinator runs `requires` as topological ordering (each probe waits for its dependencies' slices). `runs_last=True` is *separate* — it's an entire-batch postponement, not a dependency. If `IndexHealthProbe` has `requires=[]` (the architect's spec — B2 reads sibling slices "via the coordinator-provided slice map, not via topological ordering") then `runs_last=True` is what enforces the after-everyone-else ordering. Verify: this story's tests use `requires=[]` and rely on `runs_last` alone for ordering — the integration with topo-sort `requires` is tested in S4-01.
- **Default heaviness "light" is the right default.** Most Phase 0/1 probes are I/O-light marker probes; the architect's heaviness assignment table reserves "heavy" for `SCIPIndexProbe` and `RuntimeTraceProbe` only.
- **`coordinator.dispatch.order` log field.** This is the audit-anchor diagnostic for "why did probes run in that order?" — verifiable by a Phase 0 audit-anchor reviewer without re-running.
