# Story S2-05 — Property tests: dispatch-order invariance + idempotence

**Step:** Step 2 — Registry kernel, `_ADAPTER_DISPATCH_ORDER`, `assemble_provenance` free function
**Status:** Ready
**Effort:** S
**Depends on:** S2-04 (`assemble_provenance` callable + four-arm `match` composition); transitively: S2-01 (`Layer`, `Ecosystem`, `_REGISTRY`, `@register_provenance_adapter`), S2-03 (`_ADAPTER_DISPATCH_ORDER`, `iter_adapters_for_layer_set`)
**ADRs honored:** Phase 7 ADR-0006 (dispatch-order discipline — this story's 50-permutation property test is the load-bearing locking mechanism), Phase 7 ADR-0007 (registry stores classes — property tests use class-substitution for adapter behavior fixtures), Phase 7 ADR-0001 (no `MultiPluginCoordinator` — `Both` is evidence, this story pins `Both` no-recursion invariant), Phase 7 ADR-0008 (no vuln.provenance cache — idempotence holds without caching).

## Context

S2-01..S2-04 ship the **mechanism**. S2-05 ships the **proof** — Hypothesis-driven property tests that lock the discipline against silent regressions:

- **50-permutation registration-order invariance** (BP-1 closure at the property level): no matter what order adapters are registered, `assemble_provenance` returns byte-identical results. Phase 7 ADR-0006 §Tradeoffs row 3 names this as a load-bearing property test on the roadmap-coherence path.
- **Idempotence**: calling `assemble_provenance` twice with identical inputs returns equal `Provenance` instances (per `High-level-impl.md §Step 2 done-criteria` line 82 + Phase 7 ADR-0008 — no cache exists, but the function is deterministic by construction).
- **`Both` no-recursion invariant**: for any registered `(AppKind, BaseKind)` pair where both layers resolve non-`Unknown`, `assemble_provenance` returns `Both(app_record=app, base_record=base)` where neither field is itself a `Both` (S1-03's nested `Both` guard). Per ADR-0006 §Consequences last bullet.
- **`Layer.RUNTIME` reserved-slot under permutation**: the empty `RUNTIME` layer behaves correctly across all permutations (per ADR-0006 §Consequences row 2 + open question §4).

The `provenance_registry_reset` conftest fixture (introduced in S2-01) isolates `_REGISTRY` per test; this story's Hypothesis tests rely on it heavily — every example must start from an empty registry. Without it, parameters bleed across examples and the property test gives false confidence.

**Scope reminder.** S2-05 ships ONLY property tests + (optionally) a small Hypothesis strategy module. No production code changes. The `tests/property/vuln_provenance/` directory is new and may need an `__init__.py` marker.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy §Property tests (Hypothesis)` — names the four required property tests: 50-permutation invariance, idempotence, `Both` no-recursion, SBOM tampering (the last is S4-04's). This story owns the first three.
  - `../phase-arch-design.md §Component design §6` "Failure behavior" — `ProvenanceError` → `Unknown`; pure function; deterministic.
  - `../phase-arch-design.md §Harness engineering §Determinism vs probabilism` — assembly is deterministic; cache-free; same inputs → same output.
- **Phase ADRs:**
  - `../ADRs/0006-adapter-dispatch-explicit-final-tuple.md §Tradeoffs row 3` — "A property test … shuffles registration order across 50 permutations and asserts `assemble_provenance` result is byte-identical — locks the discipline at the property level." THIS STORY.
  - `../ADRs/0006-adapter-dispatch-explicit-final-tuple.md §Consequences last bullet` — `test_both_invariant.py` asserts for any non-`Unknown` `(AppKind, BaseKind)` pair, `assemble_provenance` returns `Both(...)` with no recursion.
  - `../ADRs/0008-no-vuln-provenance-cache-in-phase-7.md` — no cache exists; idempotence holds by construction.
- **Source design:** `../final-design.md §Synthesis ledger row 13` (the property tests are part of the row-13 / score-15-of-15 dispatch-as-data answer).
- **Existing code (precedent to mirror):**
  - `tests/property/` Phase 2 examples (e.g., `tests/property/test_index_health.py` if shipped) — canonical idioms for Hypothesis strategies + autouse registry-reset fixtures.
  - `tests/conftest.py` and `tests/unit/primitives/vuln_provenance/conftest.py` (S2-01) — the `provenance_registry_reset` fixture this story leans on.
  - `hypothesis` is a dev dep already pinned in `pyproject.toml`.

## Goal

Ship `tests/property/vuln_provenance/test_dispatch_order_invariant.py`, `tests/property/vuln_provenance/test_idempotence.py`, and `tests/property/vuln_provenance/test_both_invariant.py` (the latter overlapping S12-03's `test_both_invariant.py` — that story consumes the same file; story-writing pins it here once and S12-03 cross-references). The 50-permutation test fails loud if `assemble_provenance` ever silently depends on registration order; the idempotence test fails if a future PR introduces hidden state (e.g., a cache); the `Both` no-recursion test fails if S1-03's nested-`Both` guard ever weakens.

## Acceptance criteria

- [ ] **AC-1 — 50-permutation registration-order invariance (BP-1 lock).** `tests/property/vuln_provenance/test_dispatch_order_invariant.py::test_assemble_invariant_under_50_registration_order_permutations` registers a fixed set of adapters (one APP returning `AppDirect`, two BASE_IMAGE returning `BaseImage` with distinct `image_digest`s) and runs Hypothesis with `@given(st.permutations(adapter_specs))` (or equivalent), `@settings(max_examples=50, deadline=None)`. For every permutation, the function calls `assemble_provenance` with identical inputs; asserts the result is `==` equal across permutations (using `Provenance` value equality from S1-03). Permutation seed N=0 establishes the "reference" result; permutations 1..49 are compared against it.
- [ ] **AC-2 — Idempotence: same inputs, same output.** `tests/property/vuln_provenance/test_idempotence.py::test_assemble_provenance_is_idempotent` registers an arbitrary adapter set and inputs (Hypothesis-generated); calls `assemble_provenance(...)` twice with **byte-identical inputs**; asserts the two results are `==` equal. Per Phase 7 ADR-0008: no cache exists, so idempotence holds by determinism alone. `@settings(max_examples=30, deadline=None)`.
- [ ] **AC-3 — `Both` no-recursion invariant.** `tests/property/vuln_provenance/test_both_invariant.py::test_both_app_record_is_appkind_base_record_is_basekind_never_both` registers exactly one APP adapter returning a non-`Unknown` `AppKind` AND one BASE_IMAGE adapter returning a non-`Unknown` `BaseKind` (Hypothesis-generated values from the appropriate seven-variant union). Calls `assemble_provenance`; asserts `isinstance(result, Both) AND isinstance(result.app_record, (AppDirect, AppTransitive, AppVendored)) AND isinstance(result.base_record, (BaseImage, RuntimeBundled)) AND not isinstance(result.app_record, Both) AND not isinstance(result.base_record, Both)`. `@settings(max_examples=30, deadline=None)`. **Cross-references S12-03** — the headline e2e story will import/extend this property test.
- [ ] **AC-4 — `Layer.RUNTIME` reserved-slot under permutation.** `tests/property/vuln_provenance/test_dispatch_order_invariant.py::test_runtime_layer_remains_empty_under_permutations` registers ONLY APP + BASE_IMAGE adapters across 20 permutations; asserts `assemble_provenance` NEVER returns a `RuntimeBundled` variant (because no `RUNTIME` adapter is registered). Closes Phase 7 ADR-0006 §Consequences row 2 + open question §4.
- [ ] **AC-5 — Adapter classes for Hypothesis fixtures live in `tests/property/vuln_provenance/_strategies.py`** (or inline if simpler). Each strategy yields a closure-captured concrete return value the test then registers via dynamic class creation:
  ```python
  def _make_app_direct_adapter(expected: AppDirect) -> type:
      class _A:
          def __init__(self) -> None: ...
          def attribute(self, *a, **kw) -> Provenance: return expected
          def confidence(self) -> str: return "high"
      return _A
  ```
  Adapter classes are constructed per-example; the `provenance_registry_reset` fixture clears `_REGISTRY` between examples. Test asserts the fixture is autouse and effective (a sanity test that runs two examples in sequence and confirms isolation).
- [ ] **AC-6 — All property tests use the `provenance_registry_reset` autouse fixture.** Verified by: the new test files import nothing from `conftest.py` directly (the autouse fixture activates implicitly); a sanity assertion `assert _registry_mod._REGISTRY == {}` at the START of each `@given`-decorated function body proves the registry was reset between examples.
- [ ] **AC-7 — Property test failure messages name the failing invariant.** Hypothesis's `note(...)` calls inside the body print the permutation seed and the offending result + reference result on shrinkage. Engineers debugging a regression read the message and immediately know which permutation broke.
- [ ] **AC-8 — `tests/property/vuln_provenance/__init__.py`** exists (test package marker; new directory needs it).
- [ ] **AC-9 — `pytest tests/property/vuln_provenance/` runs in CI under the default `make check` invocation.** No new `-m` marker required (Hypothesis tests live in the standard pytest collection). If a `phase07_property` marker is added in future story-writing, it's additive — for now, the property tests run with everything else.
- [ ] **AC-10 — TDD red test exists, committed, green.** `tests/property/vuln_provenance/test_dispatch_order_invariant.py::test_assemble_invariant_under_50_registration_order_permutations` was the first failing test (initially: `assemble_provenance` returns different results because dispatch consults registration order). After S2-03 + S2-04 are in place, the property holds. If S2-04's implementation silently re-introduced `dict.items()` dispatch (mutation regression), this test fails on permutation N≥2 within seconds.
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on the three test files + `_strategies.py`. `make lint-imports` green.

## Implementation outline

1. Create `tests/property/vuln_provenance/__init__.py` (empty marker).
2. Create `tests/property/vuln_provenance/_strategies.py`:
   - Helper factories that close over a concrete `Provenance` return value and yield an adapter `type`:
     ```python
     def adapter_returning(expected: Provenance) -> type:
         class _Adapter:
             def __init__(self) -> None: ...
             def attribute(self, *a, **kw): return expected
             def confidence(self): return "high"
         return _Adapter
     ```
   - Hypothesis strategies for the seven-variant `Provenance` types (composing S1-01's identifier strategies if they exist; otherwise smart-constructed values inline).
3. Create `tests/property/vuln_provenance/test_dispatch_order_invariant.py`:
   - The 50-permutation test (AC-1).
   - The RUNTIME reserved-slot test (AC-4).
4. Create `tests/property/vuln_provenance/test_idempotence.py`:
   - The idempotence test (AC-2).
5. Create `tests/property/vuln_provenance/test_both_invariant.py`:
   - The `Both` no-recursion test (AC-3).
6. Confirm the `provenance_registry_reset` autouse fixture from `tests/unit/primitives/vuln_provenance/conftest.py` (S2-01) propagates to `tests/property/vuln_provenance/`. **Likely needed:** either move the fixture to `tests/conftest.py` (the top-level conftest applies to both `tests/unit/...` and `tests/property/...`) OR duplicate the fixture into `tests/property/vuln_provenance/conftest.py`. Pick **move-to-top-level** for DRY; coordinate via S2-01's attempt log if it currently lives in the lower conftest.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/property/vuln_provenance/test_dispatch_order_invariant.py`

```python
from __future__ import annotations

from hypothesis import given, settings, strategies as st, note

from codegenie.primitives.vuln_provenance import (
    assemble_provenance,
    Ecosystem,
    Layer,
    register_provenance_adapter,
)
from codegenie.primitives.vuln_provenance.types import AppDirect, BaseImage
from tests.property.vuln_provenance._strategies import adapter_returning


def _adapter_specs():
    """Three (layer, ecosystem, expected_result) tuples — fixed set."""
    return [
        (Layer.APP, Ecosystem.NPM, AppDirect(...)),                  # fill in
        (Layer.BASE_IMAGE, Ecosystem.APK, BaseImage(...)),           # fill in
        (Layer.BASE_IMAGE, Ecosystem.DPKG, BaseImage(...)),          # fill in (different image_digest)
    ]


@settings(max_examples=50, deadline=None)
@given(st.permutations(_adapter_specs()))
def test_assemble_invariant_under_50_registration_order_permutations(
    perm: list[tuple[Layer, Ecosystem, object]],
) -> None:
    """Phase 7 ADR-0006 §Tradeoffs row 3: shuffle registration order across 50
    permutations; assemble_provenance returns BYTE-IDENTICAL results.
    Closes critic BP-1 at the property level. Registration order is NOT
    load-bearing."""

    for layer, eco, expected in perm:
        cls = adapter_returning(expected)
        register_provenance_adapter(layer=layer, ecosystem=eco)(cls)

    cve_id = ...   # fixture
    pkg_id = ...
    img_ref = ...
    sbom = ...

    result = assemble_provenance(cve_id, pkg_id, img_ref, sbom)

    note(f"permutation: {[(l.value, e.value) for l, e, _ in perm]}")
    note(f"result: {result!r}")

    # Reference result is computed once (Hypothesis seed N=0); use a module-level
    # cache or compute on the first example. For simplicity:
    expected_ref = _reference_result()  # computed once by walking adapter_specs in
                                        # _ADAPTER_DISPATCH_ORDER × Ecosystem-sort
                                        # order — the canonical result.
    assert result == expected_ref, f"result diverged on permutation {perm}: {result} vs {expected_ref}"
```

Why it fails (red): until S2-03 + S2-04 land, `assemble_provenance` may walk `dict.items()` order — permutations N≥2 produce different results. The property test fails fast on the first divergence.

(In practice: S2-03 + S2-04 will already be GREEN when this story runs, so this "red" reads as a regression check rather than a literal failing test. The discipline still holds: write the test BEFORE assuming S2-04 honors the dispatch policy; let the property test confirm it does.)

### Green

Tests pass once `assemble_provenance` correctly walks `_ADAPTER_DISPATCH_ORDER` per S2-03 + S2-04. If they don't pass, the bug is in S2-04 (not S2-05); S2-05's job is to surface it.

### Required follow-on tests

```python
# test_idempotence.py
from hypothesis import given, settings, strategies as st

@settings(max_examples=30, deadline=None)
@given(...)  # registration + inputs strategies
def test_assemble_provenance_is_idempotent(...) -> None:
    """Phase 7 ADR-0008: no cache; idempotence holds by determinism alone."""
    # ... register adapters ...
    a = assemble_provenance(cve_id, pkg_id, img_ref, sbom)
    b = assemble_provenance(cve_id, pkg_id, img_ref, sbom)
    assert a == b, f"non-idempotent: {a} != {b}"


# test_both_invariant.py
@settings(max_examples=30, deadline=None)
@given(
    app_value=app_kind_strategy(),         # AppDirect | AppTransitive | AppVendored
    base_value=base_kind_strategy(),       # BaseImage | RuntimeBundled
)
def test_both_app_record_is_appkind_base_record_is_basekind_never_both(
    app_value: AppKind, base_value: BaseKind,
) -> None:
    """Phase 7 ADR-0006 §Consequences last bullet: for any non-Unknown
    (AppKind, BaseKind) pair, result is Both(app_record=app, base_record=base)
    with no recursion. S1-03's nested-Both guard MUST hold end-to-end."""
    register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)(adapter_returning(app_value))
    register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)(adapter_returning(base_value))

    result = assemble_provenance(...)

    assert isinstance(result, Both)
    assert not isinstance(result.app_record, Both)
    assert not isinstance(result.base_record, Both)
    assert isinstance(result.app_record, (AppDirect, AppTransitive, AppVendored))
    assert isinstance(result.base_record, (BaseImage, RuntimeBundled))


# test_dispatch_order_invariant.py (continued)
def test_runtime_layer_remains_empty_under_permutations() -> None:
    """AC-4 — no RUNTIME adapter registered; result never contains RuntimeBundled."""
    # Register only APP + BASE_IMAGE adapters; assert across 20 permutations
    # that result is never `isinstance(..., RuntimeBundled)`.
    ...
```

### Refactor

- Hoist common adapter-spec fixtures into `_strategies.py`; tests import them.
- Add `@example(...)` decorators on the property tests with hand-crafted edge cases (e.g., reverse-order permutation, single-adapter degenerate case) so shrinkage is fast.
- Module docstring on each test file cites the specific ADR + arch reference (ADR-0006 §Tradeoffs row 3 for invariance, ADR-0008 for idempotence, ADR-0006 §Consequences last bullet for `Both` no-recursion).
- Inline `note(...)` calls per Hypothesis convention — failure output shows the offending permutation + values.

## Files to touch

| Path | Why |
|---|---|
| `tests/property/vuln_provenance/__init__.py` | Test package marker (new directory). |
| `tests/property/vuln_provenance/_strategies.py` | Hypothesis strategies + `adapter_returning` factory. |
| `tests/property/vuln_provenance/test_dispatch_order_invariant.py` | 50-permutation invariance (AC-1) + RUNTIME reserved-slot (AC-4). |
| `tests/property/vuln_provenance/test_idempotence.py` | Idempotence property (AC-2). |
| `tests/property/vuln_provenance/test_both_invariant.py` | `Both` no-recursion property (AC-3). Cross-referenced by S12-03. |
| `tests/conftest.py` (extend) OR `tests/property/vuln_provenance/conftest.py` (new) | Ensure `provenance_registry_reset` autouse fixture applies to property tests. Coordinate with S2-01. |

## Out of scope

- **SBOM-tampering Hypothesis property test** — owned by **S4-04** (`tests/property/vuln_provenance/test_sbom_tampering.py`).
- **`Both` always emits coordination event property test** — owned by **S12-03** (`test_both_always_emits_coordination.py`). S2-05's `test_both_invariant.py` covers the function-level invariant; S12-03 extends to end-to-end event emission.
- **Adversarial tests (poisoned SBOM, poisoned catalog YAML, Dockerfile prompt-injection)** — owned by **S12-04**.
- **Performance property tests (p99 ≤ 50 ms)** — owned by **S12-05** (`tests/perf/test_assemble_provenance_uncached.py`).
- **Real Phase 3 / Phase 7 plugin adapters (`NpmVulnProvenanceAdapter`, `AlpineVulnProvenanceAdapter`, `DistrolessVulnProvenanceAdapter`)** — owned by S3 + S4. This story uses dynamic test-only adapter classes via `adapter_returning(...)`.
- **Hypothesis strategies for the full `Provenance` seven-variant union** — partial scope; S2-05 needs only `AppKind`-and-`BaseKind`-generating strategies. Full union strategies live in `_strategies.py` and may be extended by S12-03 / S4-04.

## Notes for the implementer

- **Reference result computation is the subtle bit.** Across 50 permutations, the "expected" result is the SAME — it's whatever `assemble_provenance` returns when registration order matches `_ADAPTER_DISPATCH_ORDER` × `Ecosystem`-declaration order. Compute the reference ONCE per test invocation (outside the Hypothesis `@given`) or use Hypothesis's `@example(permutation=canonical)` to pin the reference. If two permutations diverge from each other, the test fails — that's the signal regardless of which is "right".
- **`max_examples=50` matches ADR-0006 §Tradeoffs row 3 exactly.** Don't increase to 100 "because more is better" — 50 is the discipline. If a regression slips through 50 permutations, it'll slip through 500. Don't decrease to 30 either; the property is high-signal.
- **Hypothesis `deadline=None`** is correct because each example registers an adapter, runs assembly, and asserts — variable cost depending on adapter count. The 50-permutation test is bound by 50 × ~10 ms ≈ 500 ms wall time, fast enough for CI.
- **The `provenance_registry_reset` fixture must propagate.** If it's only registered in `tests/unit/primitives/vuln_provenance/conftest.py`, the property tests in `tests/property/...` won't see it. **Two options:**
  - **Recommended:** move the fixture to `tests/conftest.py` (top-level) so it applies broadly.
  - Alternative: duplicate the fixture into `tests/property/vuln_provenance/conftest.py`. Less DRY but more localized.
  Coordinate the choice with the S2-01 attempt log — pick the same approach.
- **Property test failure shrinkage** is the real value-add of Hypothesis. When a permutation breaks the invariance, Hypothesis shrinks to the minimal-counter-example permutation — usually a single swap. Engineers debug in seconds because the `note(...)` output names the offending permutation.
- **`AppKind` / `BaseKind` strategies** need to construct valid instances of `AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled` — each carrying smart-constructed identifiers (S1-01) and `DistroPackage` (S1-02). If S1-01 / S1-02 ship Hypothesis strategies for their newtypes, compose them; if not, hand-write small strategies in `_strategies.py` and refactor later when a sibling story adds them.
- **Don't add an `@pytest.mark.phase07_property` marker yet.** Property tests run in default collection; if performance becomes an issue (it won't at 50 examples × 3 properties), a marker can be added then. CLAUDE.md §pytest config notes the `bench` marker is for perf-only tests; property tests are not perf-bound.
- **The "TDD red test" framing (AC-10) is partly retrospective.** By the time S2-05 runs, S2-04 has already implemented the dispatch correctly — so the red property test might pass on first run. The discipline is still: write the property test BEFORE assuming S2-04 honors the dispatch; if it had failed, you'd know S2-04 cut a corner. Future regressions (e.g., someone refactors `iter_adapters_for_layer_set` to use `dict.items()`) will be caught by this test, not by a unit test.
