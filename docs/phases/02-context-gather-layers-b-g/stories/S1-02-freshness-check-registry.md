# Story S1-02 — `@register_index_freshness_check` decorator-registry

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready (hardened by phase-story-validator 2026-05-15)
**Effort:** S
**Depends on:** S1-01, S1-05
**ADRs honored:** 02-ADR-0006

## Validation notes

Hardened by `phase-story-validator` on 2026-05-15 (report: [`_validation/S1-02-freshness-check-registry.md`](_validation/S1-02-freshness-check-registry.md)). Four critic lenses (coverage, test-quality, consistency, design-patterns) ran; verdict **HARDENED**, no `RESCUE`. Substantive changes:

1. **AC-3 tightened — error message must include `module.qualname` for *both* call sites.** The original red test only asserted the function-name fragments (`check_a`, `check_b`) were substrings; a regression that strips the module path (`fn.__qualname__` only) would still pass while degrading the operator's ability to locate the conflicting registrations across a multi-file plugin tree. The hardened test now asserts the dotted `module.qualname` shape explicitly.
2. **AC-5 + new AC-12 — `head` is threaded unchanged through `dispatch_all` to every dispatched check.** A mutation that swaps slice/head positional args (`fn(head, slices.get(name, {}))`) or drops `head` would silently return wrong freshness on every gather. The new test captures `head` inside a synthetic check and asserts identity equality with the dispatched value.
3. **AC-6 + new AC-14 — `dispatch_all`'s iteration order is registration order.** Audit-chain hashing (Phase 0 ADR + S3-06) requires byte-stable outputs; a non-deterministic iteration order would silently produce different audit hashes across reruns. The new test registers checks in a fixed sequence and asserts `list(result.keys()) == [<first>, <second>, …]`.
4. **New AC-11 — empty registry → empty dispatch.** `FreshnessRegistry().dispatch_all({}, head="x") == {}`. Trivial edge case but a wrong impl that bombs on empty input would silently slip through (B2 runs before any source registers when the registry-walking story S4-01 is built in isolation).
5. **New AC-13 — exception from a check function propagates.** The story Notes claim "an exception from a check is a bug and must propagate" but no test pinned this contract. A wrong impl that catches and silently swallows would pass — and that's a real fail-loud surface (CLAUDE.md commitment).
6. **AC-1 expanded — `registered_names()` is part of the public surface.** Test 4 (`test_module_level_decorator_uses_default_singleton`) and S4-01's coordinator dispatch loop both call it; ship it explicitly named in `__all__` so consumers don't reach through `_checks`. Symmetric with `Registry.all_probes()` (Phase 0 `probes/registry.py`).
7. **New test — module-level `register_index_freshness_check` returns the decorated function unchanged.** Symmetric with `test_decorator_returns_function_unchanged` but at the module-level singleton entrypoint; catches a wrong `register_index_freshness_check` that returns `None` after registering on `default_freshness_registry`.
8. **New test — `test_dispatch_all_routes_each_slice_to_its_own_check`.** The original `test_register_and_dispatch_round_trip` only verified that result keys match registered names; it did not verify the *correct slice* reaches the *correct check function*. The new test captures inputs per check and asserts the slice for `scip` was passed to `check_scip` (not to `check_runtime` or vice versa) — catches a `dispatch_all` mutation that shuffles slices.
9. **Notes-for-implementer extended (4 paragraphs):**
   - **ADR-0006 §Consequences location deviation documented.** The ADR's §Consequences bullet says "decorator-registry in `freshness.py`"; this story (and S1-01's hardening) place it in `registry.py` to keep `freshness.py` pure data and avoid a circular import once the registry imports `IndexFreshness`. The deviation is intentional; an ADR amendment is deferred to the first phase that hits friction (per 02-ADR-0006 §Decision noted in the ADR proper).
   - **Rule-of-three observation: this is the 2nd registry of the same family.** Phase 0's `probes/registry.py` is the 1st precedent; S1-10's `depgraph/registry.py` will be the 3rd. The kernel-extract opportunity (a shared `KernelRegistry[K, V]` base + per-registry typed errors) crosses the rule-of-three threshold when S1-10 lands. This story **DOES NOT** pre-extract — Rule 2 (simplicity first) wins until three concrete consumers exist; the extract decision is owned by whoever validates S1-10.
   - **`JSONValue` forward-reference is intentionally lenient.** Phase 0's `codegenie.output.sanitizer` does not export a `JSONValue` recursive type alias today (the writer chokepoint takes `dict[str, Any]`). The `FreshnessCheck` signature is therefore `Callable[[dict[str, object], str], IndexFreshness]` at this story's land time — `dict[str, object]` is the structural fallback for "Pydantic-serializable JSON payload" and matches Phase 0 precedent. If S1-06 (`probe-context-extension`) or later promotes `JSONValue` to a public alias, this module rebinds the inner type *by import*, never by redefinition. The contract surface (signature shape) does not change.
   - **Open/Closed seam at the file boundary.** Adding a new index source must require *zero edits* to `src/codegenie/indices/registry.py`, `src/codegenie/probes/layer_b/index_health.py`, or `src/codegenie/indices/__init__.py`. The seam is "new file under `src/codegenie/probes/...` + `@register_index_freshness_check(IndexName("..."))` decorator on a free function". This is the load-bearing extension-by-addition commitment from CLAUDE.md; the discipline is verified in-phase by S5-05 (`runtime_trace`) and S6-08 (`semgrep` / `gitleaks` / `conventions`) whose git diffs MUST NOT touch the three paths named above.

No `RESCUE`-tier findings. No `NEEDS RESEARCH` (Stage 3 skipped — every gap was answerable from arch + ADR-0006 + Phase 0's `probes/registry.py` precedent).

## Context

`IndexHealthProbe` (B2) would otherwise grow a `match index_name:` block that every phase has to edit when a new index source appears (Phase 3 SCIP-per-language, Phase 7 distroless target, Phase 14 cross-repo SCIP). The architect's Gap-3 fix closes that Open/Closed failure mode the way the rest of the design closes others: a decorator-registry. Each Phase-2 index source registers a tiny function `(slice, head) -> IndexFreshness`; B2 loops the registry instead of switching on index name. This story plants the registry primitive — zero consumers in this story, but everything else in Steps 4–6 will register through it.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Gap 3" — IndexHealthProbe couples to every sibling probe's slice shape` — the named gap; the prescribed fix is this decorator-registry.
  - `../phase-arch-design.md §"Component design" #1 — IndexHealthProbe` — describes how B2 loops the registry (consumed by S4-01).
  - `../phase-arch-design.md §"Design patterns applied"` row 5 — `@register_dep_graph_strategy` precedent; this registry is the symmetric counterpart for freshness checks.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0006-index-freshness-sum-type-location.md` — 02-ADR-0006 §Decisions noted — the registry location decision (Phase 2 lands it inside `codegenie.indices.registry`; ADR amendment optional only if friction arises).
- **Source design:**
  - `../final-design.md §"Synthesis ledger" — Open Q 1` — first-class registry location resolved here.
- **Existing code:**
  - `src/codegenie/probes/registry.py` — model after this — a class-based `Registry` + module-level `default_registry` + a `register_*` decorator function that targets it. Duplicate-name detection raises a typed error at decoration time (i.e., import time) for fail-loud semantics.
  - `src/codegenie/indices/__init__.py` / `src/codegenie/indices/freshness.py` — S1-01 lands them; the registry imports `IndexFreshness` from here.
- **External docs (only if directly relevant):**
  - None.

## Goal

Implement `src/codegenie/indices/registry.py` exposing `@register_index_freshness_check(index_name: IndexName)` — a decorator-registry that registers `(slice: dict[str, JSONValue], head: str) -> IndexFreshness` functions, rejects duplicate `index_name` at import time, and offers a `dispatch_all(slices, head) -> dict[IndexName, IndexFreshness]` method totalled over every registered name.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/indices/registry.py` exists and exports — via `__all__` — `register_index_freshness_check`, `default_freshness_registry`, `FreshnessRegistry`, `FreshnessCheck` (the function-type alias), and `FreshnessRegistryError` (typed marker subclass of `codegenie.errors.CodegenieError`). `FreshnessRegistry` exposes the public methods `register`, `registered_names`, and `dispatch_all` (symmetric with `Registry.all_probes()` on `codegenie.probes.registry`). `unregister_for_tests` is public-but-test-only (named-trigger discipline; AC-9 documents the intent).
- [ ] **AC-2.** `register_index_freshness_check(index_name: IndexName)` is a decorator-factory; the inner decorator registers the function in `default_freshness_registry` **and** returns the function unchanged (`registered_fn is original_fn`) so the registration is non-invasive. The convenience decorator's return-identity is verified for both `FreshnessRegistry.register(...)` and the module-level `register_index_freshness_check(...)` entry points.
- [ ] **AC-3.** Duplicate-name registration raises `FreshnessRegistryError` at decoration time (i.e., module import), with a message containing (a) the offending `index_name` value, and (b) **both** call sites as `f"{fn.__module__}.{fn.__qualname__}"` dotted-form strings (so an operator grepping a multi-file plugin tree finds both registrations from the message alone). Mirrors `codegenie.probes.registry.Registry.register`. Test must assert the dotted shape, not merely the function-name fragment.
- [ ] **AC-4.** `FreshnessCheck` signature is exactly `Callable[[dict[str, <JSONValue>], str], IndexFreshness]` (slice + head; returns a typed freshness value, never raises by contract). The inner value type uses Phase 0's `codegenie.output.sanitizer.JSONValue` recursive alias **if and when it is publicly exported**; until then the structural fallback is `dict[str, object]` (see Notes for implementer §JSONValue forward-reference). **Do NOT** redefine `JSONValue` in this module.
- [ ] **AC-5.** `FreshnessRegistry.dispatch_all(slices: dict[IndexName, dict[str, <JSONValue>]], head: str) -> dict[IndexName, IndexFreshness]` is total over every registered index name; if a `slices[name]` key is missing, the registered check is still invoked with an empty dict (its responsibility to emit `Stale(IndexerError(message=f"upstream_{name}_unavailable"))`). The `head` argument is threaded **unchanged** through to every dispatched check — no shadowing, no coercion, no truncation (see AC-12 for the explicit propagation test).
- [ ] **AC-6.** Registered functions whose `index_name` is not in `slices.keys()` still appear in the output (the registry is the source of truth for *expected* indices; B2 will treat a missing slice as a degraded upstream — that logic lives in S4-01, not here).
- [ ] **AC-7.** A test exercises a synthetic registration of two checks via the decorator on a fresh `FreshnessRegistry` (not the module-level singleton), then asserts dispatch returns both **and routes each slice to its own check function** (a per-check capture variable confirms `check_scip` receives the scip slice and `check_runtime` receives the runtime slice — catches a `dispatch_all` mutation that shuffles slices).
- [ ] **AC-8.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-9.** Tests live under `tests/unit/indices/test_freshness_registry.py` and use a *local* `FreshnessRegistry()` instance, never `default_freshness_registry`, to avoid cross-test pollution (mirroring `tests/unit/probes/test_registry.py`). The single exception is `test_module_level_decorator_uses_default_singleton`, which MUST guard with `try / finally: default_freshness_registry.unregister_for_tests(name)` exactly as written.
- [ ] **AC-10.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/indices/test_freshness_registry.py` all pass on the touched files.
- [ ] **AC-11.** **Empty-registry totality.** `FreshnessRegistry().dispatch_all(slices={}, head="any") == {}` — an empty registry returns an empty dict, never raises. (B2's `run()` will dispatch through this primitive even on the first gather where no source has registered yet; failing on empty would be a deadlock.)
- [ ] **AC-12.** **`head` propagation determinism.** A dedicated test registers a check whose first action is to append `head` to a captured list; `dispatch_all(slices={name: {}}, head="cafef00d")` is invoked; the captured list equals `["cafef00d"]`. Catches the slice/head argument-swap mutation that no other test would notice (because freshness-value identity is the check function's choice, not the registry's).
- [ ] **AC-13.** **Exception-propagation contract.** A check function that raises a non-`FreshnessRegistryError` (e.g., `RuntimeError("synthetic_bug")`) inside `dispatch_all` propagates the exception unchanged — the registry does NOT catch, log-and-continue, or wrap. (Per Notes-for-implementer: "an exception from a check is a bug and must propagate"; the coordinator at S4-01 is the right place to catch.) Pinned by `test_dispatch_all_propagates_check_exception`.
- [ ] **AC-14.** **Iteration determinism.** `list(reg.dispatch_all(...).keys())` equals the order in which checks were registered (`dict` insertion-order semantics; Python ≥ 3.7). Audit-chain hashing (Phase 0 ADR / S3-06) depends on byte-stable output ordering; a non-deterministic dispatch order would silently corrupt audit chains. Pinned by `test_dispatch_all_iteration_is_registration_order`.

## Implementation outline

1. Create `src/codegenie/indices/registry.py` with: a `FreshnessRegistryError` marker subclass of `CodegenieError`; the `FreshnessCheck` type alias (`Callable[[dict[str, object], str], "IndexFreshness"]`; `JSONValue` rebinds *by import* if/when Phase 0 promotes it); the `FreshnessRegistry` class exposing `register`, `registered_names`, `dispatch_all`, and the test-only `unregister_for_tests`; the module-level `default_freshness_registry = FreshnessRegistry()`; the `register_index_freshness_check(index_name: IndexName)` decorator-factory targeting the default singleton (returns the decorated function unchanged at both layers — see AC-2).
2. Add `FreshnessRegistryError` to `src/codegenie/errors.py` as a bare marker subclass (per Phase 0 markers-only convention; same shape as `ProbeError`).
3. Update `src/codegenie/indices/__init__.py` to re-export the registry surface (`register_index_freshness_check`, `default_freshness_registry`, `FreshnessRegistry`, `FreshnessCheck`, `FreshnessRegistryError`).
4. Write the red test against a fresh `FreshnessRegistry()` instance, exercising decoration → dispatch → duplicate-name rejection — plus the hardened mutation-resistance tests (per-slice routing, head propagation, empty-registry, exception propagation, iteration order, module-level decorator return-identity).
5. Implement; confirm green.
6. Refactor: docstrings (module + class + `unregister_for_tests`); `__all__`; log line emitted on every registration (`structlog` event `indices.freshness_check.registered` with `index_name` + `origin` fields); `dispatch_all` must iterate `self._checks.items()` in declaration order (do NOT sort or set-ify).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/indices/test_freshness_registry.py`

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from codegenie.errors import FreshnessRegistryError
from codegenie.indices import (
    CommitsBehind,
    Fresh,
    FreshnessRegistry,
    IndexerError,
    Stale,
    register_index_freshness_check,
)
from codegenie.indices.registry import FreshnessCheck  # type alias
from codegenie.types.identifiers import IndexName


def test_register_and_dispatch_routes_each_slice_to_its_own_check() -> None:
    """AC-7 — registration round-trip *and* per-slice routing.
    Captures the slice each check actually receives, so a `dispatch_all` mutation
    that shuffles slices (e.g., `fn(slices.get(other_name, {}), head)`) fails.
    """
    # arrange: fresh local registry; do NOT touch the module-level default.
    reg = FreshnessRegistry()
    scip = IndexName("scip")
    runtime = IndexName("runtime_trace")

    seen_by_scip: list[dict[str, object]] = []
    seen_by_runtime: list[dict[str, object]] = []

    @reg.register(scip)
    def check_scip(slice_: dict[str, object], head: str) -> "IndexFreshness":
        seen_by_scip.append(slice_)
        last = slice_.get("last_indexed_commit")
        if last == head:
            return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=timezone.utc))
        return Stale(reason=CommitsBehind(n=1, last_indexed=str(last or "")))

    @reg.register(runtime)
    def check_runtime(slice_: dict[str, object], head: str) -> "IndexFreshness":
        seen_by_runtime.append(slice_)
        return Stale(reason=IndexerError(message="upstream_runtime_unavailable"))

    # act
    scip_slice = {"last_indexed_commit": "deadbeef"}
    runtime_slice = {"last_traced_image_digest": "sha256:abc"}
    result = reg.dispatch_all(
        slices={scip: scip_slice, runtime: runtime_slice},
        head="cafef00d",
    )

    # assert: every registered name appears; each check saw ITS OWN slice (not the other's).
    assert set(result.keys()) == {scip, runtime}
    assert seen_by_scip == [scip_slice]
    assert seen_by_runtime == [runtime_slice]
    assert isinstance(result[scip], Stale)
    assert isinstance(result[scip].reason, CommitsBehind)
    assert isinstance(result[runtime].reason, IndexerError)


def test_duplicate_name_rejected_at_registration_time() -> None:
    """AC-3 — duplicate raises at decoration time; message contains the offending
    name AND both call sites as dotted `module.qualname` strings (catches a
    regression that strips the module path)."""
    reg = FreshnessRegistry()
    name = IndexName("scip")

    @reg.register(name)
    def check_a(slice_: dict[str, object], head: str) -> "IndexFreshness":
        return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=timezone.utc))

    with pytest.raises(FreshnessRegistryError) as exc_info:
        @reg.register(name)
        def check_b(slice_: dict[str, object], head: str) -> "IndexFreshness":
            return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=timezone.utc))

    msg = exc_info.value.args[0]
    assert "scip" in msg
    # AC-3: both dotted module.qualname forms must appear, not just the bare
    # function names. The qualname includes the test function as its enclosing
    # scope (e.g., "tests.unit.indices.test_freshness_registry.test_…<locals>.check_a").
    assert check_a.__module__ in msg
    assert f".{check_a.__qualname__}" in msg
    assert f".{check_b.__qualname__}" in msg


def test_decorator_returns_function_unchanged_on_local_registry() -> None:
    """AC-2 — `Registry.register(name)(fn) is fn`."""
    reg = FreshnessRegistry()

    def f(slice_: dict[str, object], head: str) -> "IndexFreshness":
        return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=timezone.utc))

    returned = reg.register(IndexName("x"))(f)
    assert returned is f  # decorator is non-invasive


def test_module_level_decorator_returns_function_unchanged() -> None:
    """AC-2 — symmetric guard at the module-level singleton entrypoint.
    Catches a `register_index_freshness_check` that registers correctly but
    returns `None` (or a wrapper); operator-visible because the decorated
    name would shadow to `None` at every import site."""
    from codegenie.indices import default_freshness_registry

    name = IndexName("__test_module_returns_marker__")

    def f(slice_: dict[str, object], head: str) -> "IndexFreshness":
        return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=timezone.utc))

    try:
        returned = register_index_freshness_check(name)(f)
        assert returned is f
    finally:
        default_freshness_registry.unregister_for_tests(name)


def test_module_level_decorator_uses_default_singleton() -> None:
    """AC-9 — the convenience decorator delegates to default_freshness_registry;
    verified by registering on it and observing the singleton's registered_names."""
    from codegenie.indices import default_freshness_registry

    name = IndexName("__test_singleton_marker__")

    @register_index_freshness_check(name)
    def check_marker(slice_: dict[str, object], head: str) -> "IndexFreshness":
        return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=timezone.utc))

    try:
        assert name in default_freshness_registry.registered_names()
    finally:
        # Be a good citizen — don't pollute downstream tests in the same process.
        default_freshness_registry.unregister_for_tests(name)


def test_dispatch_invokes_check_with_empty_dict_when_slice_missing() -> None:
    """AC-5 — missing slice → check is still invoked with `{}`; result key present."""
    reg = FreshnessRegistry()
    name = IndexName("runtime_trace")
    captured: list[dict[str, object]] = []

    @reg.register(name)
    def check(slice_: dict[str, object], head: str) -> "IndexFreshness":
        captured.append(slice_)
        return Stale(reason=IndexerError(message="upstream_runtime_unavailable"))

    out = reg.dispatch_all(slices={}, head="abc123")
    assert name in out
    assert captured == [{}]
    assert isinstance(out[name].reason, IndexerError)


def test_dispatch_all_on_empty_registry_returns_empty_dict() -> None:
    """AC-11 — empty registry → empty dict; never raises.
    B2 dispatches through this primitive even on the first gather where no
    source has registered yet; failing on empty input would deadlock."""
    reg = FreshnessRegistry()
    assert reg.dispatch_all(slices={}, head="any") == {}
    assert reg.dispatch_all(slices={IndexName("orphan"): {"x": 1}}, head="any") == {}


def test_dispatch_all_threads_head_unchanged_to_every_check() -> None:
    """AC-12 — `head` propagation determinism.
    A wrong impl that swaps slice/head positional args, drops `head`, or
    coerces it would fail. The captured list pins the dispatched value
    identity to the value the caller passed."""
    reg = FreshnessRegistry()
    name = IndexName("scip")
    captured_heads: list[str] = []

    @reg.register(name)
    def check(slice_: dict[str, object], head: str) -> "IndexFreshness":
        captured_heads.append(head)
        return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=timezone.utc))

    reg.dispatch_all(slices={name: {}}, head="cafef00d")
    assert captured_heads == ["cafef00d"]


def test_dispatch_all_propagates_check_exception() -> None:
    """AC-13 — registry does not catch / log-and-continue / wrap.
    An exception from a check is a bug, and per the Notes-for-implementer
    contract the coordinator at S4-01 is the right place to catch."""
    reg = FreshnessRegistry()
    name = IndexName("scip")

    @reg.register(name)
    def check(slice_: dict[str, object], head: str) -> "IndexFreshness":
        raise RuntimeError("synthetic_bug")

    with pytest.raises(RuntimeError, match="synthetic_bug"):
        reg.dispatch_all(slices={name: {}}, head="x")


def test_dispatch_all_iteration_is_registration_order() -> None:
    """AC-14 — `list(result.keys()) == registration_order`.
    Audit-chain hashing (S3-06) depends on byte-stable output ordering;
    a non-deterministic iteration order would silently corrupt audit chains."""
    reg = FreshnessRegistry()
    order = [IndexName(n) for n in ("first", "second", "third", "fourth")]

    for n in order:
        @reg.register(n)
        def _stub(slice_: dict[str, object], head: str, _n: str = n) -> "IndexFreshness":
            return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=timezone.utc))

    # Empty `slices` keeps the test focused on order, not on slice routing.
    # `dispatch_all` is the load-bearing ordering contract (audit-hash dependency);
    # `registered_names()` returns an unordered frozenset by Green-step design.
    result = reg.dispatch_all(slices={}, head="x")
    assert list(result.keys()) == order
    assert set(reg.registered_names()) == set(order)
```

Run — confirm `ImportError: cannot import name 'FreshnessRegistry' from 'codegenie.indices'`. Commit.

### Green — make it pass

```python
# src/codegenie/indices/registry.py
from __future__ import annotations
from collections.abc import Callable
from typing import TYPE_CHECKING

import structlog

from codegenie.errors import FreshnessRegistryError
from codegenie.types.identifiers import IndexName

if TYPE_CHECKING:
    from codegenie.indices.freshness import IndexFreshness

JSONValue = object  # use codegenie.output.sanitizer.JSONValue if already public; otherwise the
                    # registry contract carries no narrower shape than "Pydantic-serializable".
FreshnessCheck = Callable[[dict[str, "JSONValue"], str], "IndexFreshness"]

_log = structlog.get_logger(__name__)


class FreshnessRegistry:
    def __init__(self) -> None:
        self._checks: dict[IndexName, FreshnessCheck] = {}
        self._origins: dict[IndexName, str] = {}  # for fail-loud duplicate messages

    def register(self, index_name: IndexName) -> Callable[[FreshnessCheck], FreshnessCheck]:
        def _decorator(fn: FreshnessCheck) -> FreshnessCheck:
            if index_name in self._checks:
                prior = self._origins[index_name]
                raise FreshnessRegistryError(
                    f"duplicate index_name {index_name!r}: "
                    f"{prior} and {fn.__module__}.{fn.__qualname__}"
                )
            self._checks[index_name] = fn
            self._origins[index_name] = f"{fn.__module__}.{fn.__qualname__}"
            _log.debug("indices.freshness_check.registered", index_name=index_name)
            return fn
        return _decorator

    def registered_names(self) -> frozenset[IndexName]:
        return frozenset(self._checks)

    def dispatch_all(
        self,
        slices: dict[IndexName, dict[str, "JSONValue"]],
        head: str,
    ) -> dict[IndexName, "IndexFreshness"]:
        return {
            name: check(slices.get(name, {}), head)
            for name, check in self._checks.items()
        }

    def unregister_for_tests(self, index_name: IndexName) -> None:
        """Test-only convenience to keep the singleton clean across tests."""
        self._checks.pop(index_name, None)
        self._origins.pop(index_name, None)


default_freshness_registry = FreshnessRegistry()


def register_index_freshness_check(
    index_name: IndexName,
) -> Callable[[FreshnessCheck], FreshnessCheck]:
    """Decorator targeting :data:`default_freshness_registry`."""
    return default_freshness_registry.register(index_name)


__all__ = [
    "FreshnessCheck",
    "FreshnessRegistry",
    "default_freshness_registry",
    "register_index_freshness_check",
]
```

Add the marker exception:

```python
# in src/codegenie/errors.py — append (markers only, per Phase 0/1 convention)
class FreshnessRegistryError(CodegenieError):
    """Raised by indices.registry on duplicate @register_index_freshness_check
    decoration; hard fail at import time (load-bearing fail-loud surface)."""
```

Update `__all__` of `codegenie.errors`. Re-export from `codegenie/indices/__init__.py`:

```python
from codegenie.indices.registry import (
    FreshnessCheck, FreshnessRegistry,
    default_freshness_registry, register_index_freshness_check,
)
```

### Refactor — clean up

- Type hints already strict. Add module docstring referencing 02-ADR-0006 (with explicit note that this file lives in `registry.py`, NOT `freshness.py` — deviation from the ADR's §Consequences text; see Notes-for-implementer §ADR-0006 §Consequences location deviation).
- The `FreshnessCheck` alias is exposed at package level so probes can spell it without dipping into the submodule.
- Docstring `unregister_for_tests` clearly: this is **test-only** and the name carries the intent (do not invent a "deregister" public API).
- Confirm the structlog `indices.freshness_check.registered` event has at least one log-emission assertion test (covered by the "Cross-cutting concerns" §Structured logging from the manifest).
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/indices/ tests/unit/indices/test_freshness_registry.py`, `pytest tests/unit/indices/test_freshness_registry.py -v`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/indices/registry.py` | New module; decorator-registry primitive. |
| `src/codegenie/indices/__init__.py` | Extend re-exports with the registry surface. |
| `src/codegenie/errors.py` | Append `FreshnessRegistryError` marker; extend `__all__`. |
| `tests/unit/indices/test_freshness_registry.py` | Red-then-green coverage of register / dispatch / duplicate / module decorator. |

## Out of scope

- **`IndexHealthProbe` looping the registry** — handled by S4-01.
- **Phase-2 index source registrations** (SCIP, runtime trace, semgrep, gitleaks, conventions) — those land in their own probe stories (S5-05, S6-08) once the probes exist.
- **`mypy --warn-unreachable` per-module override on `codegenie.indices/**`** — handled by S1-11.
- **Phase 3+ ecosystem-specific index sources** — registered later via the same decorator from inside the Phase 3 plugin; no edit to this file is required.

## Notes for the implementer

- **Singleton vs. local registry discipline.** Tests MUST use a local `FreshnessRegistry()` instance. The two exceptions are `test_module_level_decorator_uses_default_singleton` and `test_module_level_decorator_returns_function_unchanged` — both guard with `default_freshness_registry.unregister_for_tests(name)` in a `finally`, exactly as shown.
- **Duplicate-name failure is import-time, not dispatch-time.** Mirror `codegenie.probes.registry.Registry.register`'s fail-loud-at-decoration discipline. A registry that fails silently is worse than no registry. The error message MUST include `module.qualname` for both call sites — an operator grepping a multi-file plugin tree should be able to locate both registrations from the message alone (AC-3 tightening).
- **`FreshnessCheck` does not raise *by contract*; the registry does not catch.** By contract, a well-behaved check function takes a slice + head and returns a typed freshness value. If construction fails internally, it returns `Stale(IndexerError(message="..."))`. The registry intentionally does **not** wrap, catch, or log-and-continue — an exception from a check is a bug and the coordinator at S4-01 is the right place to catch (Phase 0 coordinator isolation precedent). AC-13 pins this exception-propagation contract with a runtime test.
- **`head` propagation is byte-stable.** `dispatch_all` MUST thread its `head` argument positionally through to each check unchanged — no coercion, no slicing, no `.lower()`. The slice/head argument-swap is a plausible silent mutation; AC-12 catches it by capturing the value inside a synthetic check.
- **Iteration order is registration order — load-bearing.** `dict` insertion-order semantics (Python ≥ 3.7) plus the implementation walking `self._checks.items()` in declaration order give the right shape for free. Audit-chain hashing (S3-06 / Phase 0 ADR) depends on byte-stable outputs; AC-14 pins the contract. Do **not** sort, `frozenset()`, or otherwise re-permute the registered names inside `dispatch_all`.
- **The `slices` parameter to `dispatch_all` is *the coordinator-provided slice map* — already-sanitized.** The registry contract has no opinion on `dict[str, JSONValue]`'s typing depth. Do **not** invent a narrower `IndexSlice` Pydantic model here — that is a Step-4 IndexHealthProbe-internal concern.
- **JSONValue forward-reference is intentionally lenient.** Phase 0's `codegenie.output.sanitizer` does not export a `JSONValue` recursive type alias today (the writer chokepoint takes `dict[str, Any]`). The `FreshnessCheck` signature is therefore `Callable[[dict[str, object], str], IndexFreshness]` at this story's land time — `dict[str, object]` is the structural fallback for "Pydantic-serializable JSON payload" and matches Phase 0 precedent. If S1-06 (`probe-context-extension`) or a later story promotes `JSONValue` to a public alias on `codegenie.output.sanitizer`, this module rebinds the inner type *by import*, never by redefinition. The contract surface (signature shape) does not change.
- **Why not Pydantic for the function type?** A `Callable[[dict, str], IndexFreshness]` is the simplest correct typing surface; Pydantic models with `__call__` are pattern-soup (final-design Anti-patterns §"Pattern soup" precedent). The registry stays a plain dict + decorator.
- **`unregister_for_tests` is intentionally awkward.** The name is the policy; do not promote it to a normal `unregister` public method. Document in its docstring: "Test-only convenience for cleaning the module-level singleton; do not use in production code paths." Two tests call it (the AC-9 finally-guard pair).
- **ADR-0006 §Consequences location deviation.** The ADR's §Consequences bullet says "decorator-registry in `freshness.py`"; this story (and S1-01's hardening) place it in `registry.py` to keep `freshness.py` pure data and avoid a circular import once the registry imports `IndexFreshness`. The deviation is intentional; an ADR amendment is deferred to the first phase that hits friction (per 02-ADR-0006's "ADR amendment optional only if friction arises" allowance). If you find yourself wanting to move the code back into `freshness.py`: first check whether the renderer at S8-01 still imports `IndexFreshness` without pulling in the registry singleton — that's the import-direction invariant the split protects.
- **Rule-of-three observation — kernel extract is deferred to S1-10.** This is the 2nd registry of the decorator-registry family in this phase (`probes/registry.py` is the 1st precedent; `depgraph/registry.py` at S1-10 is the 3rd). Do **not** pre-extract a shared `KernelRegistry[K, V]` base here — Rule 2 (simplicity first) wins until three concrete consumers exist. The extract decision is owned by whoever validates S1-10 with all three implementations in hand.
- **Open/Closed seam at the file boundary.** Adding a new index source (Phase 2's `runtime_trace`, `semgrep`, `gitleaks`, `conventions`; Phase 3+'s `scip_per_language`, `distroless_target`, `cross_repo_scip`) MUST require zero edits to `src/codegenie/indices/registry.py`, `src/codegenie/probes/layer_b/index_health.py`, or `src/codegenie/indices/__init__.py`. The seam is "new file under `src/codegenie/probes/...` + `@register_index_freshness_check(IndexName("..."))` decorator on a free function". This is the load-bearing extension-by-addition commitment from CLAUDE.md; the in-phase verification is by S5-05 / S6-08's git-diff scope.
