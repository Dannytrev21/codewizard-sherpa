# S2-05 Validation Report — `assemble_provenance` property tests

**Date:** 2026-08-14
**Validator:** phase-story-validator (retrospective — story shipped GREEN 2026-05-20)
**Verdict:** **HARDENED** (spec-side; code-side follow-up queued below)

## Scope

Retrospective validation of `docs/phases/07-migration-task-class/stories/S2-05-assemble-property-tests.md`. The story shipped GREEN on 2026-05-20 with tests at `tests/property/vuln_provenance/{test_dispatch_order_invariant.py,test_idempotence.py,test_both_invariant.py,_strategies.py,conftest.py}`. Story text still needed hardening — several ACs were tautological, ambiguous, or silently contradicted a sibling story. This pass fixes the story so the executor's regression-catching claim is falsifiable and so a future contributor extending the property-test package inherits the pattern discipline the shipped code assumes.

## Context brief

- **Story goal.** Lock the dispatch-order / idempotence / `Both`-composition / RUNTIME-reserved invariants of `assemble_provenance` at the Hypothesis property-test level, so silent regressions (a refactor that re-introduces implicit `dict.items()` iteration, adds a hidden cache, weakens the nested-`Both` guard, or seeds RUNTIME accidentally) fail loud.
- **Load-bearing ADRs.** Phase 7 ADR-0006 (explicit `_ADAPTER_DISPATCH_ORDER` tuple + `Ecosystem`-sorted intra-layer iteration), ADR-0007 (registry stores classes), ADR-0008 (no vuln.provenance cache — Phase 7 only), ADR-0001 (no `MultiPluginCoordinator`; `Both` is evidence).
- **Cross-story coupling.** S12-03 Part B ships `test_both_always_emits_coordination.py` AND *also claims* to author `test_both_invariant.py` (Part B line 78-95). S2-05 already shipped `test_both_invariant.py`. Consistency-critic FIND-1 surfaced the conflict; resolution: S2-05 authors initially, S12-03 extends. S12-03 story needs a companion validator pass.
- **Sibling shipped precedents consulted.** `tests/property/test_dep_graph_strategy_dispatch.py` (Phase 2 property-test idiom), `tests/unit/primitives/vuln_provenance/conftest.py` (S2-01 fixture placement).

## Critic reports

Four critics ran in parallel (agents `aeccf6fd` coverage, `aaf2eb4b` test-quality, `a12615d3` consistency, `a411601d` design-patterns). Full transcripts in the harness task outputs; distilled findings below.

### Coverage critic (severity ranked)

| Sev | Target | Finding | Disposition |
|---|---|---|---|
| block | AC-3 | Coverage gap — `match`/`assert_never` product's other three quadrants (`Unknown×BaseKind`, `AppKind×Unknown`, `Unknown×Unknown`) are property-level dispatch invariants not owned by S4-04 or S12-03. | **Applied — new AC-3b.** |
| harden | AC-1 | Ambiguous-reference — "permutation seed N=0" is not something Hypothesis guarantees; the reference must be computed out-of-band. | **Applied — see Test-Quality CRITICAL; converged on hardcoded literal.** |
| harden | AC-1 / AC-4 | Coverage gap — within-layer `Ecosystem`-sorted iteration order is only implicitly tested; silent `dict.items()` intra-layer regression passes. | **Applied — new AC-3d.** |
| harden | ACs (missing) | Missing edge cases: single-adapter degenerate, adapter-that-raises, duplicate `(Layer, Ecosystem)` registration. | **Partial — single-adapter covered via `@example` (AC-14). Adapter-that-raises deferred to S1-04 error-path unit test (out of scope for S2-05 property level). Duplicate registration deferred to S2-01 (registry-side).** |
| harden | AC-2 | Idempotence too narrow ("call twice back-to-back") — misses hidden state on interleaved calls. | **Applied — AC-2 rewritten as `f(x); f(y); f(x)` sequence.** |
| nit | AC-5 / AC-6 | Redundant "sanity test" claim. | **Kept the diagnostic test; clarified AC-6 owns the primary invariant.** |
| nit | AC-2..AC-4 | `max_examples` counts arbitrary; no wall-time justification. | **Applied — Notes for implementer now justify each count vs CI budget.** |

### Test-Quality critic (severity ranked)

| Sev | Target | Finding | Disposition |
|---|---|---|---|
| CRITICAL | AC-1 / `_reference_result()` | Self-computed reference is tautological — `_ADAPTER_DISPATCH_ORDER` reversed produces the same reference AND the same permutation result. Story's own Notes endorsed this pattern. | **Applied — AC-1 now mandates a hardcoded `_EXPECTED: Final[Provenance]` literal + `model_dump_json()` byte-check.** |
| HIGH | AC-2 | Cache-detection intent unenforced — same-inputs-same-output cannot distinguish deterministic recomputation from cache hit. | **Applied — AC-2 now mandates a call-count spy (`counting_adapter_returning`) asserting `calls == N`.** |
| HIGH | all three tests | Reverse-layer mutation (`_ADAPTER_DISPATCH_ORDER = ((BASE,), (APP,), (RUNTIME,))`) is invisible; `Both(app, base)` composition is layer-set-agnostic. | **Applied — new AC-3c dispatch walk-order spy.** |
| MEDIUM | `test_both_invariant.py` | Nested-`Both` invariant is dead-code-tested — `app_kind_strategy()` cannot generate `Both`. | **Noted; keep the runtime check as belt-and-suspenders. A stronger negative test (constructing an intentional nested `Both` via `.model_construct()`) is deferred to S12-03 Part B extension; this is where the primary responsibility naturally lives per the consistency resolution.** |
| MEDIUM | ACs (missing) | Missing metamorphic property — adding an `Unknown`-returning adapter should be inert. | **Applied — new AC-12.** |
| MEDIUM | all three files | Missing `@example(...)` seed pinning; regression reproducibility relies on `.hypothesis/` cache. | **Applied — new AC-14 (identity + reversed permutation `@example`s).** |
| LOW | AC-1 | `id(cls)` sort mutation caught only accidentally. | **Subsumed by AC-1 hardcoded reference + AC-3c walk-order spy.** |
| LOW | shipped conftest | Deviates from story's recommended fixture location (localized duplicate, not top-level move). | **Aligned with consistency FIND-2 below.** |

### Consistency critic (severity ranked)

| Sev | Target | Finding | Disposition |
|---|---|---|---|
| HIGH | AC-3 + Files-to-touch | S12-03 Part B also claims ownership of `test_both_invariant.py` with a different function name (`test_both_record_pair_produces_both_variant_no_recursion` vs S2-05's `test_both_app_record_is_appkind_base_record_is_basekind_never_both`). Two-hand-write risk. | **Applied — AC-3 pins S2-05 as initial author; noted S12-03 needs a companion validator pass to align its story text to "extends" rather than "authors".** |
| HIGH | Impl-outline step 6 | Story recommends move-to-top-level; shipped code did localized-duplicate; recommendation contradicts sibling S2-01 shipped placement. | **Applied — step 6 rewritten to prescribe localized duplicate.** |
| MEDIUM | AC-1 | "byte-identical" arch language (§22, §1260, §1407) vs `==` (Pydantic value equality). | **Applied — AC-1 now requires BOTH `==` and `model_dump_json()` equality.** |
| MEDIUM | AC-1, AC-2, AC-3 | Unpinned Hypothesis seeds contradict S12-03 §Notes line 158 mandate for `derandomize=True`. | **Applied — new AC-13, plus `derandomize=True` written into AC-1..AC-4, AC-3b/c/d, AC-12.** |
| LOW | story-wide | Silence on coverage floor. | **Applied — AC-9 extended.** |
| LOW | AC-10 | "Partly retrospective" red-test claim undermines executor's TDD discipline. | **Applied — AC-10 reframed as regression-lock artifact requirement.** |

**Consistent (no finding).** `max_examples=50` matches ADR-0006 exactly. `hypothesis` pinned at `pyproject.toml:123` dev dep. `asyncio_mode = "auto"` — no conflict. ADR-0001 / ADR-0007 / ADR-0008 honored.

### Design-Patterns critic (severity ranked)

| Sev | Target | Finding | Disposition |
|---|---|---|---|
| medium | AC-5 | Primitive obsession / rule-of-three — `_AdapterSpec` re-declared in both property-test modules; upcoming S4-04 will re-declare a third time. | **Applied — AC-5 elevates `AdapterSpec` to a public `NamedTuple` in `_strategies.py`.** |
| low | Notes | `adapter_returning` return type unverified against Protocol; silent drift risk. | **Applied — AC-5 pins `_type_check: type[VulnProvenanceAdapter] = _ReturningAdapter` sentinel.** |
| low | Notes | Import-time `_reference_result()` couples pytest collection to production behavior. | **Applied — Notes now recommend hardcoded literal or `scope="module"` fixture.** |
| low | Impl-outline step 6 | Conftest duplication contradicts story recommendation. | **Applied — see consistency FIND-2 above (aligned).** |
| low | Notes | No extension-by-addition policy for real Phase-3/7 adapters. | **Applied — Notes now specify sibling `test_<layer>_real_adapter_invariance.py` files.** |
| low | Notes | `AppTransitive.chain` `min_size=2` mirrors `Field(min_length=2)` invariant silently. | **Applied — Notes now call out the coupling + recommend a `_types_invariants_pinned` assertion.** |

## Conflict resolutions (priority: Consistency > Coverage > Test-Quality > Design-Patterns)

1. **Consistency FIND-1 vs Coverage AC-3 disposition.** Consistency says two stories fight over `test_both_invariant.py`; Coverage wants a stronger `Both` invariant. Resolution: keep AC-3 in S2-05 (S2-05 already shipped the file); pin S12-03 as "extends, does not re-author"; queue a companion validator pass for S12-03. The stronger negative-recursion invariant (constructing intentional nested `Both` via `.model_construct()`) is deferred to S12-03's extension so the responsibility doesn't split.
2. **Test-Quality CRITICAL vs shipped `_reference_result()` design.** The shipped code uses `registry=<fresh dict>` — a partial mitigation, but not sufficient for layer-walk-order mutations. Resolution: AC-1 now mandates a hardcoded `_EXPECTED` literal AND AC-3c introduces a walk-order spy. The shipped `_reference_result()` helper can remain as a diagnostic sanity check but is no longer the sole reference.
3. **Consistency FIND-2 vs Design-Patterns F4 (both aligned).** Both critics converged on "the shipped localized-duplicate is correct; the story's move-to-top-level recommendation is wrong". Resolution unambiguous — updated in place.
4. **Coverage "adapter-that-raises" edge case vs story scope.** The critic wants a property test for `ProvenanceError → Unknown`. Deferred to S1-04's error-path unit tests (that story owns the adapter Protocol including the error contract); adding this at the property level in S2-05 would blur ownership. Noted in Notes for implementer.
5. **Rule 2 (Simplicity First) check on `AdapterSpec` NamedTuple elevation.** Design-Patterns wants a NamedTuple; Rule 2 says "three similar lines is better than premature abstraction". The rule-of-three fires (dispatch, idempotence, S4-04 upcoming) — abstraction is justified. Elevated to AC-5.

## Edits applied

All edits made to the story file in place; before/after summary:

| Section | Before (compressed) | After (compressed) |
|---|---|---|
| **Status line** | `GREEN (shipped 2026-05-20)` | `GREEN (shipped 2026-05-20; HARDENED retrospective 2026-08-14)` |
| **New: Validation notes block** | (absent) | 15-item summary block explaining every AC change and its rationale |
| **AC-1** | `==` equality against permutation-N=0 self-computed reference | Hardcoded `_EXPECTED` literal + `==` AND `model_dump_json()` + `derandomize=True` |
| **AC-2** | Same-inputs-same-output back-to-back | Interleaved `f(x); f(y); f(x)` + call-count spy asserting `calls == 3` |
| **AC-3** | "Cross-referenced by S12-03" | "**S2-05 authors the initial file; S12-03 Part B EXTENDS it**" + `derandomize=True` |
| **AC-3b (new)** | (absent) | Composition quadrant coverage — three non-Both quadrants |
| **AC-3c (new)** | (absent) | Dispatch walk-order spy — catches reversed `_ADAPTER_DISPATCH_ORDER` |
| **AC-3d (new)** | (absent) | Within-layer `Ecosystem`-sorted iteration observable |
| **AC-4** | 20 permutations, no seed | Same + `derandomize=True` + belt-and-suspenders `Both.base_record` check |
| **AC-5** | Inline `_A` class in each file, ad-hoc | Shared `AdapterSpec` NamedTuple + `_type_check` Protocol-conformance sentinel |
| **AC-6** | Sanity test + entry-assertion (redundant) | Entry assertion is primary; diagnostic test kept |
| **AC-9** | Runs in CI | Runs in CI + contributes to `--cov-fail-under=85` |
| **AC-10** | "Partly retrospective red" | **Regression-lock artifact** — executor mutates + captures failing output + reverts |
| **AC-12 (new)** | (absent) | Metamorphic — `Unknown`-returning adapter is inert |
| **AC-13 (new)** | (absent) | `derandomize=True` on every `@settings` (per S12-03 Notes) |
| **AC-14 (new)** | (absent) | Pinned `@example(...)` on AC-1 for identity + reversed permutations |
| **Impl-outline step 6** | "Recommended: move to `tests/conftest.py`" | "Duplicate into `tests/property/vuln_provenance/conftest.py` — do NOT consolidate" |
| **Files to touch** | Conftest options ambiguous | Localized-duplicate conftest pinned; `_attempts/` regression-lock artifact added |
| **Notes for implementer** | 8 bullets | Rewritten — hardcoded-reference discipline, extension-by-addition for real adapters, `AdapterSpec` NamedTuple, `min_length=2` drift guard, `derandomize=True` mandate, regression-lock artifact framing |

## Follow-up implementation work (queued)

The story spec now describes a higher bar than the shipped code hits. To close the code-side gap:

1. **`test_dispatch_order_invariant.py`** — add hardcoded `_EXPECTED` literal for AC-1 (replace `_REFERENCE_RESULT: Provenance = _reference_result()` at line 85); add `@example(...)` decorators for identity + reversed permutations (AC-14); add walk-order spy test (AC-3c); add within-layer `Ecosystem`-sorted test (AC-3d); add composition-quadrant test (AC-3b); add metamorphic `Unknown`-inert test (AC-12); add `derandomize=True` to every `@settings(...)` (AC-13).
2. **`test_idempotence.py`** — rewrite as interleaved `f(x); f(y); f(x)` + `counting_adapter_returning` factory in `_strategies.py` (AC-2, AC-13).
3. **`_strategies.py`** — elevate `_AdapterSpec` to public `AdapterSpec` NamedTuple; add `_type_check: type[VulnProvenanceAdapter] = _ReturningAdapter` sentinel inside `adapter_returning`; add `counting_adapter_returning`; add `_types_invariants_pinned` assertion for `AppTransitive.chain` min-length coupling.
4. **`_attempts/S2-05-*.md`** — capture the AC-10 regression-lock artifact (temporarily mutate `iter_adapters_for_layer_set` → `dict.items()` order, paste failing Hypothesis output, revert).
5. **Companion validator pass on `S12-03`** — align its Part B ownership language to "extends `test_both_invariant.py` authored by S2-05" and rename its planned test function to avoid the naming conflict.

These are queued as separate implementation work; not touched in this validation pass.

## Verdict

**HARDENED.** Story spec now closes previously-latent gaps that would let regressions slip past (tautological reference, cache-detection blind, walk-order blind, unpinned seeds, silent quadrant coverage gaps, ownership conflict with S12-03, primitive-obsession in fixtures). Executor has a concrete, falsifiable target for the code-side follow-up; a future contributor extending the property-test package inherits the pattern discipline explicitly rather than by tribal knowledge.

No RESCUE-tier issues surfaced. No `NEEDS RESEARCH` findings surfaced (all critic recommendations mapped to established Hypothesis patterns already used in the codebase or in canonical Hypothesis docs).
