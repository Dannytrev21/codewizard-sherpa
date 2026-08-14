# Story S2-05 — Property tests: dispatch-order invariance + idempotence

**Step:** Step 2 — Registry kernel, `_ADAPTER_DISPATCH_ORDER`, `assemble_provenance` free function
**Status:** GREEN (shipped 2026-05-20; HARDENED retrospective 2026-08-14 — see `_attempts/S2-05-assemble-property-tests.md` and `_validation/S2-05-assemble-property-tests.md`)
**Effort:** S
**Depends on:** S2-04 (`assemble_provenance` callable + four-arm `match` composition); transitively: S2-01 (`Layer`, `Ecosystem`, `_REGISTRY`, `@register_provenance_adapter`), S2-03 (`_ADAPTER_DISPATCH_ORDER`, `iter_adapters_for_layer_set`)
**ADRs honored:** Phase 7 ADR-0006 (dispatch-order discipline — this story's 50-permutation property test is the load-bearing locking mechanism), Phase 7 ADR-0007 (registry stores classes — property tests use class-substitution for adapter behavior fixtures), Phase 7 ADR-0001 (no `MultiPluginCoordinator` — `Both` is evidence, this story pins `Both` no-recursion invariant), Phase 7 ADR-0008 (no vuln.provenance cache — idempotence holds without caching).

## Validation notes (2026-08-14)

Retrospective phase-story-validator pass on already-shipped GREEN code. Four critics ran (coverage, test-quality, consistency, design-patterns). Priority order Consistency > Coverage > Test-Quality > Design-Patterns. Story edited to close spec gaps that the shipped tests do not currently exercise; the code side of these gaps is tracked separately (see `_validation/S2-05-assemble-property-tests.md § Follow-up implementation work`). Changes summarised:

- **AC-1 tightened** — reference is now an *inline hardcoded* `_EXPECTED` value (not a self-computed SUT call), and equality is asserted BOTH via `==` and via `model_dump_json()` byte-equality so the arch design's "byte-identical" promise (phase-arch §22, §1260, §1407) is enforced, not paraphrased. The shipped `_reference_result()` helper partially mitigates the tautology (uses an explicit `registry=` kwarg with dict-order-independent traversal), but a mutation to `_ADAPTER_DISPATCH_ORDER` layer-walk order is still not observable because `Both(app, base)` composition is layer-set-agnostic — a walk-order spy AC (new AC-3c below) closes that gap.
- **AC-2 tightened** — idempotence now requires (a) an interleaved `f(x); f(y); f(x)` sequence (catches hidden state accumulators that AC-2's back-to-back call misses) and (b) a **call-count spy** on the adapter's `attribute()` method that asserts each call re-runs the adapter chain (the stated ADR-0008 intent — "no cache" — cannot be verified by same-inputs-same-output alone, since a cache also returns same-outputs-same-inputs).
- **AC-3 clarified** — S2-05 remains the initial author of `test_both_invariant.py` (the file shipped here); S12-03 EXTENDS this file with its own strategies + a negative `pydantic.ValidationError` test. S12-03's story text (Part B) needs a companion validator pass to align its ownership language with this pin.
- **AC-3b (new)** — composition quadrant coverage: `(Unknown, BaseKind)` returns bare `BaseKind` (never `Both`); `(AppKind, Unknown)` returns bare `AppKind` (never `Both`); `(Unknown, Unknown)` returns `Unknown`. These `match`/`assert_never` arms are property-level dispatch invariants NOT owned by S4-04 (SBOM tampering) or S12-03 (event emission); S2-05 is the only property-level home.
- **AC-3c (new)** — dispatch walk-order spy: a `SpyAdapter` records the sequence of `attribute()` calls; assert the sequence equals the declared `_ADAPTER_DISPATCH_ORDER × Ecosystem`-sorted order. This is the only assertion that catches a reversed `_ADAPTER_DISPATCH_ORDER` mutation (`Both(app, base)` composition is direction-invariant, so AC-1 as-written cannot detect it).
- **AC-3d (new)** — within-layer `Ecosystem`-enum-sorted iteration observable: registering ≥2 adapters in the same layer and asserting the spy sequence follows `Ecosystem` declaration order regardless of registration permutation. Closes ADR-0006 §Consequences row 3 at the property level.
- **AC-5 tightened** — the `_AdapterSpec` shape is elevated to a shared `NamedTuple` in `_strategies.py` (rule-of-three: dispatch, idempotence, and future S4-04 all consume it); the `adapter_returning` factory pins a static-conformance sentinel (`_type_check: type[VulnProvenanceAdapter] = _ReturningAdapter`) so Protocol drift fails at import.
- **AC-9 tightened** — property tests contribute to the ≥ 85% coverage floor (CLAUDE.md `--cov-fail-under=85`); `pytest --no-cov` is NOT used.
- **AC-10 reframed** — this AC always was retrospective; it now reads as an explicit **regression-lock** artifact requirement (temporarily mutate `iter_adapters_for_layer_set` to `dict.items()` order, capture the failing permutation output in `_attempts/`, revert) rather than a hollow "red-test" claim.
- **AC-12 (new)** — metamorphic invariance under `Unknown`-returning adapter injection: adding an `Unknown`-returning adapter for a previously-empty `(Layer, Ecosystem)` slot MUST NOT change the assembled result. Catches a mutation that flips `if isinstance(r, Unknown): continue` to `break`.
- **AC-13 (new)** — Hypothesis seeds pinned via `derandomize=True` on every `@settings(...)` in this directory, per S12-03 §Notes-for-implementer line 158 ("`derandomize=True` is the safest; `@seed(<int>)` is fine if explicit; never unpinned").
- **AC-14 (new)** — pinned `@example(...)` decorators on AC-1 for the reverse permutation and the identity permutation, so failures on a fresh CI runner surface the canonical adversarial cases without relying on the local `.hypothesis/` cache.
- **Implementation-outline step 6 corrected** — recommend the **localized-duplicate conftest** (matches shipped choice; the top-level-move alternative would fire an autouse fixture across ~5500 tests and violates Rule 3 surgical-changes on an already-shipped sibling).
- **Notes for the implementer extended** — extension-by-addition policy for real Phase-3/7 adapters (do NOT edit `_ADAPTER_SPECS`; add sibling `test_<layer>_real_adapter_invariance.py` files); S1-03 variant-invariant drift caveat (strategy `min_size=2` mirrors `Field(min_length=2)` — pin via a `_types_invariants_pinned` assertion so future widening fails loud); `max_examples=30`/`20` are justified vs the CI budget rather than left arbitrary; and the reference computation is a `scope="module"` fixture (or a hardcoded literal) so import-time SUT calls do not couple test collection to production behavior.

Verdict: **HARDENED**. Story spec closes previously-latent gaps that make future regressions detectable; the shipped code lands partway toward this bar and the remaining code work (walk-order spy, call-count spy, composition quadrants, metamorphic Unknown-inert, `derandomize=True`, hardcoded reference, `@example` seeds) is queued as follow-up implementation. Full audit in `_validation/S2-05-assemble-property-tests.md`.

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

- [ ] **AC-1 — 50-permutation registration-order invariance (BP-1 lock), against a hardcoded reference.** `tests/property/vuln_provenance/test_dispatch_order_invariant.py::test_assemble_invariant_under_50_registration_order_permutations` registers a fixed set of adapters (one APP returning `AppDirect`, two BASE_IMAGE returning `BaseImage` with distinct `image_digest`s) and runs Hypothesis with `@given(perm=st.permutations(_ADAPTER_SPECS))`, `@settings(max_examples=50, deadline=None, derandomize=True)`. For every permutation the function calls `assemble_provenance` with identical inputs; the reference is a **hardcoded literal** at the top of the module — `_EXPECTED: Final[Provenance] = Both(app_record=an_app_direct(), base_record=a_base_image("a"))` — NOT a self-computed SUT call (self-computation is tautological under a `_ADAPTER_DISPATCH_ORDER` mutation, since both sides walk in the mutated order). Assert equality via BOTH `result == _EXPECTED` AND `result.model_dump_json() == _EXPECTED.model_dump_json()` so the arch design's "byte-identical output" promise (phase-arch §22, §1260, §1407) is enforced, not paraphrased through Pydantic `==`.
- [ ] **AC-2 — Interleaved idempotence + call-count spy (no-cache lock).** `tests/property/vuln_provenance/test_idempotence.py::test_assemble_provenance_is_idempotent_and_uncached` registers a Hypothesis-generated adapter set that swaps `adapter_returning` for `counting_adapter_returning(expected)` (a factory whose `attribute()` increments a `nonlocal calls` counter). Call sequence: `a = assemble_provenance(x); b = assemble_provenance(y); c = assemble_provenance(x)`. Assert (i) `a == c` (interleaved-call idempotence — catches hidden state accumulators that back-to-back-call idempotence misses), and (ii) `calls == 3` for the adapters exercised by `x` (each call re-runs the chain — this is the assertion that actually catches a cache; same-inputs-same-output alone cannot distinguish "deterministic recomputation" from "cache hit"). Per Phase 7 ADR-0008: no cache. `@settings(max_examples=30, deadline=None, derandomize=True)`.
- [ ] **AC-3 — `Both` no-recursion invariant (S2-05 initial authorship).** `tests/property/vuln_provenance/test_both_invariant.py::test_both_app_record_is_appkind_base_record_is_basekind_never_both` registers exactly one APP adapter returning a non-`Unknown` `AppKind` AND one BASE_IMAGE adapter returning a non-`Unknown` `BaseKind` (Hypothesis-generated values from `app_kind_strategy()` / `base_kind_strategy()` in `_strategies.py`). Calls `assemble_provenance`; asserts `isinstance(result, Both) AND isinstance(result.app_record, (AppDirect, AppTransitive, AppVendored)) AND isinstance(result.base_record, (BaseImage, RuntimeBundled)) AND not isinstance(result.app_record, Both) AND not isinstance(result.base_record, Both)`. `@settings(max_examples=30, deadline=None, derandomize=True)`. **S2-05 authors the initial file; S12-03 Part B EXTENDS it** with additional strategies and a negative `pydantic.ValidationError` test (S12-03's story text must be aligned in its own validator pass — do NOT re-author the file there).
- [ ] **AC-3b — Composition quadrant coverage (`match`/`assert_never` arms).** `tests/property/vuln_provenance/test_dispatch_order_invariant.py::test_composition_match_arms_cover_full_product` sweeps the four `(app_result, base_result)` quadrants with Hypothesis:
  - `(Unknown, BaseKind)` → assert `isinstance(result, (BaseImage, RuntimeBundled))` AND `not isinstance(result, Both)`.
  - `(AppKind, Unknown)` → assert `isinstance(result, (AppDirect, AppTransitive, AppVendored))` AND `not isinstance(result, Both)`.
  - `(Unknown, Unknown)` → assert `isinstance(result, Unknown)` AND `result.reason == "no_adapter_resolved"` (or the exact reason string from ADR-0006 §Component design §6 — pin the string to catch a silent reason-drift regression).
  `@settings(max_examples=30, deadline=None, derandomize=True)`. These are property-level dispatch invariants NOT owned by S4-04 (SBOM tampering) or S12-03 (event emission); S2-05 is the only property-level home. Closes Coverage-critic FIND (block).
- [ ] **AC-3c — Dispatch walk-order spy (catches a reversed `_ADAPTER_DISPATCH_ORDER` mutation).** `tests/property/vuln_provenance/test_dispatch_order_invariant.py::test_walk_order_matches_declared_dispatch_order` registers spy adapters that append `(layer, ecosystem)` to a module-local `_SPY_CALLS: list[tuple[Layer, Ecosystem]]` on every `attribute()` invocation. After `assemble_provenance` returns, assert `_SPY_CALLS` equals the declared expected sequence: `[(APP, NPM), (BASE_IMAGE, APK), (BASE_IMAGE, DPKG)]` for `_ADAPTER_SPECS` (APP layer first per `_ADAPTER_DISPATCH_ORDER`; within BASE_IMAGE, APK before DPKG per `Ecosystem` declaration order). **This is the only assertion in this story that would fail if `_ADAPTER_DISPATCH_ORDER = ((BASE_IMAGE,), (APP,), (RUNTIME,))` were mutated in** — AC-1's `Both(app, base)` composition is layer-set-agnostic and cannot detect layer-walk reordering. `@settings(max_examples=20, deadline=None, derandomize=True)`.
- [ ] **AC-3d — Within-layer `Ecosystem`-enum-sorted iteration observable.** Add a Hypothesis-driven variant of the walk-order spy: register three BASE_IMAGE adapters (APK, DPKG, RPM) across all `3! = 6` permutations of registration order; assert `_SPY_CALLS` within the BASE_IMAGE layer is always `[APK, DPKG, RPM]` (the `Ecosystem`-enum declaration order). Closes ADR-0006 §Consequences row 3 ("Within a layer, `Ecosystem`-enum-sorted order is deterministic") at the property level.
- [ ] **AC-4 — `Layer.RUNTIME` reserved-slot under permutation.** `tests/property/vuln_provenance/test_dispatch_order_invariant.py::test_runtime_layer_remains_empty_under_permutations` registers ONLY APP + BASE_IMAGE adapters across 20 permutations; asserts `assemble_provenance` NEVER returns a `RuntimeBundled` variant, nor a `Both` whose `base_record` is `RuntimeBundled` (belt-and-suspenders). `@settings(max_examples=20, deadline=None, derandomize=True)`. Closes Phase 7 ADR-0006 §Consequences row 2 + open question §4.
- [ ] **AC-5 — Shared `AdapterSpec` NamedTuple + Protocol-conformance sentinel in `_strategies.py`.** The rule-of-three fires now (dispatch test, idempotence test, upcoming S4-04 test all consume the same 3-tuple shape). Elevate the shape to a public `NamedTuple` and pin the adapter-factory's Protocol conformance statically:
  ```python
  class AdapterSpec(NamedTuple):
      layer: Layer
      ecosystem: Ecosystem
      expected: Provenance

  def adapter_returning(expected: Provenance) -> type[VulnProvenanceAdapter]:
      class _ReturningAdapter:
          def attribute(self, *a, **kw) -> Provenance: return expected
          def confidence(self) -> AdapterConfidence: return AdapterConfidence.HIGH
      _type_check: type[VulnProvenanceAdapter] = _ReturningAdapter  # static conformance sentinel
      return _ReturningAdapter
  ```
  No sibling property-test file re-declares the tuple shape; the sentinel guarantees a future extension of the `VulnProvenanceAdapter` Protocol fails at import time rather than silently duck-typing.
- [ ] **AC-6 — All property tests use the `provenance_registry_reset` autouse fixture.** Verified by: the new test files import nothing from `conftest.py` directly (the autouse fixture activates implicitly); a sanity assertion `assert _registry_mod._REGISTRY == {}` at the START of each `@given`-decorated function body proves the registry was reset between examples. AC-5's separate isolation-sanity test (`test_autouse_fixture_isolates_registry_across_examples`) remains valuable as a *diagnostic* test — kept, but the primary invariant lives at AC-6's per-example entry assertion.
- [ ] **AC-7 — Property test failure messages name the failing invariant.** Hypothesis's `note(...)` calls inside the body print the permutation and the offending result + reference result on shrinkage. Engineers debugging a regression read the message and immediately know which permutation broke.
- [ ] **AC-8 — `tests/property/vuln_provenance/__init__.py`** exists (test package marker; new directory needs it).
- [ ] **AC-9 — `pytest tests/property/vuln_provenance/` runs in CI under the default `make check` invocation AND contributes to the ≥ 85% coverage floor.** No new `-m` marker required. `pytest --no-cov` is NOT used for this directory; these property tests exercise `assemble_provenance` end-to-end and count toward CLAUDE.md's `--cov-fail-under=85` gate. If a `phase07_property` marker is added in future story-writing, it's additive.
- [ ] **AC-10 — Regression-lock artifact (executor discipline, not a hollow red test).** By the time S2-05 runs, S2-03 + S2-04 are already GREEN, so a literal "red test" isn't achievable. The executor MUST instead capture a **regression-lock artifact** in `_attempts/S2-05-*.md`: temporarily mutate `iter_adapters_for_layer_set` to iterate `dict.items()` order (or reverse `_ADAPTER_DISPATCH_ORDER`), run the new AC-1 + AC-3c tests, paste the failing Hypothesis output (naming the offending permutation and the walk-order divergence) into the attempt log, then revert. Evidence proves the property tests *would* catch the regression they claim to catch.
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on the three test files + `_strategies.py`. `make lint-imports` green.
- [ ] **AC-12 — Metamorphic: `Unknown`-returning adapter injection is inert.** `tests/property/vuln_provenance/test_dispatch_order_invariant.py::test_unknown_returning_adapter_does_not_change_result` — Hypothesis-generate a "base" adapter plan; compute `r1 = assemble_provenance(...)`; then register an additional `Unknown`-returning adapter on a previously-empty `(Layer, Ecosystem)` slot; compute `r2`; assert `r1 == r2`. Catches a mutation flipping `if isinstance(result, Unknown): continue` to `... break` (kills the "keep walking for a non-`Unknown`" semantic). `@settings(max_examples=30, deadline=None, derandomize=True)`.
- [ ] **AC-13 — Hypothesis seeds pinned via `derandomize=True` on every `@settings(...)` in this directory.** Aligns with S12-03 §Notes-for-implementer line 158 ("`derandomize=True` is the safest; `@seed(<int>)` is fine if explicit; never unpinned"). Flaky property tests destroy trust in the gate; deterministic runs make CI failures reproducible on a fresh runner without relying on `.hypothesis/` cache carry-over.
- [ ] **AC-14 — Pinned `@example(...)` decorators on AC-1 for canonical adversarial cases.** At minimum: `@example(perm=list(_ADAPTER_SPECS))` (identity permutation — a passing baseline) and `@example(perm=list(reversed(_ADAPTER_SPECS)))` (the reverse permutation — the highest-signal adversarial case). Hypothesis runs pinned examples first on every run; if either fails, engineers see the exact offending permutation in the failure output instead of a stochastic shrink.

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
6. **Duplicate** the `provenance_registry_reset` autouse fixture into `tests/property/vuln_provenance/conftest.py` (matches the shipped choice; do NOT consolidate to `tests/conftest.py`). A top-level autouse fixture would fire for the entire ~5500-test suite, a non-surgical change (Rule 3) for a 10-line fixture, and the repo ships no `tests/conftest.py` today. The localized duplicate mirrors S2-01's package-scoped placement in `tests/unit/primitives/vuln_provenance/conftest.py`; the two conftests carry a docstring explaining the deliberate duplication so future readers do not "correct" it.

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
| `tests/property/vuln_provenance/_strategies.py` | Hypothesis strategies + shared `AdapterSpec` NamedTuple + `adapter_returning` factory (with Protocol-conformance sentinel) + `counting_adapter_returning` (call-count spy for AC-2). |
| `tests/property/vuln_provenance/test_dispatch_order_invariant.py` | Hardcoded-reference 50-permutation invariance (AC-1) + RUNTIME reserved-slot (AC-4) + composition-quadrant coverage (AC-3b) + dispatch walk-order spy (AC-3c) + within-layer sorted order spy (AC-3d) + metamorphic Unknown-inert (AC-12) + pinned `@example(...)` seeds (AC-14). |
| `tests/property/vuln_provenance/test_idempotence.py` | Interleaved idempotence + call-count spy (AC-2). |
| `tests/property/vuln_provenance/test_both_invariant.py` | `Both` no-recursion property (AC-3). **S2-05 authors initially; S12-03 extends.** |
| `_attempts/S2-05-assemble-property-tests.md` | Regression-lock artifact for AC-10 (failing + passing Hypothesis output under a temporary `dict.items()` mutation, then reverted). |
| `tests/property/vuln_provenance/conftest.py` (new) | Localized-duplicate `provenance_registry_reset` autouse fixture (do NOT consolidate to `tests/conftest.py`; see Implementation-outline step 6). |

## Out of scope

- **SBOM-tampering Hypothesis property test** — owned by **S4-04** (`tests/property/vuln_provenance/test_sbom_tampering.py`).
- **`Both` always emits coordination event property test** — owned by **S12-03** (`test_both_always_emits_coordination.py`). S2-05's `test_both_invariant.py` covers the function-level invariant; S12-03 extends to end-to-end event emission.
- **Adversarial tests (poisoned SBOM, poisoned catalog YAML, Dockerfile prompt-injection)** — owned by **S12-04**.
- **Performance property tests (p99 ≤ 50 ms)** — owned by **S12-05** (`tests/perf/test_assemble_provenance_uncached.py`).
- **Real Phase 3 / Phase 7 plugin adapters (`NpmVulnProvenanceAdapter`, `AlpineVulnProvenanceAdapter`, `DistrolessVulnProvenanceAdapter`)** — owned by S3 + S4. This story uses dynamic test-only adapter classes via `adapter_returning(...)`.
- **Hypothesis strategies for the full `Provenance` seven-variant union** — partial scope; S2-05 needs only `AppKind`-and-`BaseKind`-generating strategies. Full union strategies live in `_strategies.py` and may be extended by S12-03 / S4-04.

## Notes for the implementer

- **Reference-result computation MUST NOT be a self-computed SUT call.** The tautology-avoidance rule: if the reference is `assemble_provenance(...)` against any registry (module-level or an explicit `registry=fresh_dict` kwarg), a mutation to `_ADAPTER_DISPATCH_ORDER` walk order is invisible — both reference and permutation apply the same mutated order, and `Both(app, base)` composition is layer-set-agnostic so the outputs still compare equal. **Prefer** a **hardcoded literal** at the top of `test_dispatch_order_invariant.py`:
  ```python
  _EXPECTED: Final[Provenance] = Both(
      app_record=an_app_direct(),
      base_record=a_base_image("a"),   # APK sorts before DPKG in Ecosystem enum order
  )
  ```
  If a fixture is preferred over a literal, use `@pytest.fixture(scope="module")` so the reference computation is not run at import (import-time SUT calls couple test collection to production behavior; a raise makes the whole property-test package uncollectable). **AC-3c's walk-order spy** is the complementary invariant that catches the mutation the hardcoded reference alone cannot see.
- **`max_examples=50` matches ADR-0006 §Tradeoffs row 3 exactly.** Don't increase to 100 "because more is better" — 50 is the discipline. `max_examples=30` on AC-2/AC-3/AC-3b/AC-12 and `20` on AC-4/AC-3c reflect a per-test wall-time budget: 30 examples × ~10 ms adapter + assembly ≈ 300 ms; 20 × ~15 ms (spy overhead) ≈ 300 ms. Total directory-level Hypothesis wall time stays under 3 s, fitting the `make check` pyramid budget.
- **Hypothesis `deadline=None`** is correct because each example registers an adapter, runs assembly, and asserts — variable cost depending on adapter count. **`derandomize=True`** (AC-13) is mandatory: a stochastic seed under Hypothesis default settings produces different examples per run, and a flaky property test would be indistinguishable from a real regression.
- **Extension policy for real Phase-3/7 adapters (`NpmVulnProvenanceAdapter`, `AlpineVulnProvenanceAdapter`, `DistrolessVulnProvenanceAdapter`) — extension by addition, no edits to `_ADAPTER_SPECS`.** When S3-02, S4-02, S4-03 ship real adapter classes, do NOT modify the shipped `_ADAPTER_SPECS` list or any of the S2-05 test files. Add sibling `test_<layer>_real_adapter_invariance.py` files that register the real class directly (the property-test module gains a new file per real adapter, mirroring the "extension by addition" load-bearing commitment in CLAUDE.md). The stub `adapter_returning` factory stays test-only; real-adapter tests use the real class.
- **`AdapterSpec` NamedTuple lives in `_strategies.py`** (AC-5). Both property modules and future S4-04 import the same shape. Do NOT re-declare the 3-tuple as a private `_AdapterSpec` alias in individual test files (rule-of-three fires: dispatch, idempotence, S4-04). The static conformance sentinel (`_type_check: type[VulnProvenanceAdapter] = _ReturningAdapter`) inside `adapter_returning` MUST be committed — otherwise a future extension of the `VulnProvenanceAdapter` Protocol drifts silently.
- **`AppKind` / `BaseKind` strategies** need to construct valid instances of `AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled` — each carrying smart-constructed identifiers (S1-01) and `DistroPackage` (S1-02). The `AppTransitive.chain` strategy uses `min_size=2` to mirror S1-03's `Field(min_length=2)` — this coupling is silent tribal knowledge and drifts if S1-03 widens the invariant. Land a `_types_invariants_pinned` unit assertion (e.g., `assert AppTransitive.model_fields["chain"].metadata[0].min_length == 2`) alongside the strategy so a Pydantic-schema widening fails loud rather than silently under-generating.
- **`provenance_registry_reset` fixture must live in the local package conftest, NOT `tests/conftest.py`.** Shipped choice per Implementation-outline step 6 above. The two conftests (`tests/unit/primitives/vuln_provenance/conftest.py` from S2-01 and `tests/property/vuln_provenance/conftest.py` from this story) MUST both carry a docstring explaining the deliberate duplication so future readers do not consolidate them.
- **Don't add an `@pytest.mark.phase07_property` marker yet.** Property tests run in default collection; if performance becomes an issue (it won't at 50 examples × N properties), a marker can be added then. CLAUDE.md §pytest config notes the `bench` marker is for perf-only tests; property tests are not perf-bound and DO count toward the coverage floor (AC-9).
- **AC-10 is a regression-lock artifact, NOT a red test.** By the time S2-05 runs, S2-04 is already GREEN, so no genuine red is possible. The executor MUST paste a two-part artifact into `_attempts/S2-05-*.md`: (a) the failing Hypothesis output when `iter_adapters_for_layer_set` is temporarily mutated to `dict.items()` order (naming the offending permutation and the walk-order divergence), and (b) the passing output after reverting. Without the artifact, the story's regression-catching claim is unfalsifiable.
- **Property test failure shrinkage** is the real value-add of Hypothesis. When a permutation breaks the invariance, Hypothesis shrinks to the minimal-counter-example permutation — usually a single swap. Engineers debug in seconds because the `note(...)` output names the offending permutation. Pinned `@example(...)` decorators (AC-14) run first, so the highest-signal adversarial cases (identity + reversed permutation) surface before Hypothesis begins shrinking.
