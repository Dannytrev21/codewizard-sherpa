# Validation report — S2-04 `assemble_provenance(...)` free function + `match`/`assert_never` composition

**Story:** [`S2-04-assemble-provenance-function.md`](../S2-04-assemble-provenance-function.md)
**Verdict:** **STRONG (retrospective)** — story shipped `Done` on 2026-05-19 in a single attempt (commit pending human merge); four-critic pass finds every AC (AC-1..AC-15) already anchored to a shipped-and-green test, one accepted implementation deviation from the outline (class-pattern arms + `Provenance | None` locals in place of `AppKind | None` / `BaseKind | None`) that lands more robust than the outline, and three coverage / design-pattern observations that carry over to S2-05 or Phase 8 stories as `Validation notes` — not new ACs (Rule 2 + Rule 3).
**Validator run:** 2026-07-26
**Depth:** default (Stage 3 research not fired — no `NEEDS RESEARCH` findings; the composition surface is one ≤80-LOC function + a five-arm `match` block backed by a `Provenance` seven-variant discriminated union already frozen by S1-03).

## Why retrospective

The scheduled `story-validation-corrector` job selects the lowest-numbered story lacking a `_validation/{ID}.md` report. S2-04 was implemented and merged before the validator ran on it; the shipped tree (`src/codegenie/primitives/vuln_provenance/assembly.py`, `tests/unit/primitives/vuln_provenance/test_assembly.py`, `tests/unit/primitives/vuln_provenance/test_assemble_match_exhaustive.py`) is the authoritative artifact. This report exercises the four critics against the story-as-written and the shipped code, then applies edits that preserve every checked-off AC (Rule 12 — shipped evidence is authoritative).

## Critics — findings

### Coverage — STRONG (all ACs anchored; one deferred-scenario note)

Every one of the fifteen ACs traces 1:1 to a shipped green test. AC-6 anchors two tests (`test_first_non_unknown_adapter_in_layer_wins` + `test_ecosystem_sort_order_decides_winner_not_registration_order`), both intended by the AC's two-sentence "then reverse" wording. AC-9 anchors two tests in `test_assemble_match_exhaustive.py` (`test_match_has_four_composition_arms_plus_assert_never_guard` + `test_match_guard_arm_is_wildcard_calling_assert_never`), both intended by the AC's "asserts it has exactly four case arms plus the `assert_never` guard" wording. AC-14's TDD-red test is the AC-5 identity check. AC-15 is a static-gate AC proven by `make check`.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| C-1 | note | The mixed scenario "APP adapter raises `ProvenanceError` AND BASE_IMAGE adapter returns a real `BaseImage`" is not pinned by any AC. Shipped behavior: `adapter_error_seen=True`, the `(None, base)` arm returns the `BaseImage`, and the flag is silently discarded. This is arguably the correct "real answer wins over partial failure" reading of AC-7, but neither the AC nor a test locks it. | Carried in `Validation notes` for S2-05's Hypothesis property test to sweep (raises/Unknown/real × APP/BASE_IMAGE); no new AC (the story explicitly defers cross-layer property tests to S2-05). |
| C-2 | note | The mixed scenario "APP returns `Unknown` (real, not raising) AND BASE_IMAGE returns real `BaseImage`" is untested — the `(None, base)` arm handles it and `adapter_error_seen` stays `False`, so the final result is the base — but no test pins that the reason-tracking flag remains `False` here. Same S2-05 disposition. | Same disposition as C-1. |
| C-3 | nit | No AC covers what happens if a `RUNTIME` adapter is registered (a Phase 8+ event). Shipped code walks the `(Layer.RUNTIME,)` row but has no `elif` branch to stash the result — a real `RuntimeBundled` result would `break` without being captured. Phase 7 ships no RUNTIME adapter (explicit in story `Out of scope` + arch §5), so this is a "waiting for the first RUNTIME story" reserved gap, not a shipped bug. | Note carried for the future story that ships the first `RUNTIME` adapter (JRE-bundled per ADR-0006 §Consequences); no AC change here (Rule 2 — the row is a reserved slot, and the extension story will add both the branch and its AC). |
| C-4 | nit | AC-13's test asserts `provenance is assemble_provenance` (identity). No test asserts `inspect.signature(provenance) == inspect.signature(assemble_provenance)` — but identity implies signature parity trivially (same object). AC's "OR" wording is honored by the stronger form. | No action. |

### Test Quality — STRONG

Every high-value mutant is already closed:

1. **"Re-wrap the adapter's result into a new instance"** — closed by AC-3, AC-4, AC-5 all using `is` (identity), not `==`. A `copy.deepcopy` mutant would flip identity to inequality and fail three tests.
2. **"Iterate `dict.items()` instead of `Ecosystem`-sorted"** — closed by `test_ecosystem_sort_order_decides_winner_not_registration_order` (registration order YARN_BERRY-first, NPM-second, but NPM wins). This is the BP-1 closure carried end-to-end from S2-03's helper into S2-04's composition.
3. **"Catch `Exception` instead of `ProvenanceError`"** — closed by AC-8 (`test_runtime_error_propagates_and_is_not_swallowed`). This is the Rule 12 discipline made mechanical.
4. **"Return `Both` when only APP resolves"** — closed by AC-3's `isinstance(result, AppDirect)` + `is` check; a wrongly-`Both`-wrapping mutant would fail the `isinstance`.
5. **"Preinstantiate all adapters at decoration time"** — closed by AC-11's class-level `construct_count` counter that would flip to `0` under a `Both(...)` short-circuit or to `>1` under a bug that re-invokes the factory.
6. **"Silently drop `adapter_error` reason under (None, None)"** — closed by AC-7's `result.reason == "adapter_error"`; a mutant that always emits `"no_adapter_resolved"` would fail.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| TQ-1 | note | No property/metamorphic test on `assemble_provenance` itself — 50-permutation registration invariance, `Both` no-recursion under permutation, mixed-scenario idempotence. Explicitly deferred to S2-05 (`Out of scope` in the story). | No action; correctly scoped. |
| TQ-2 | note | No test that a **second** call to `assemble_provenance` with the same registry returns an **equal** (not just structurally equal) result — a stateful-cache mutant would survive locally, though it would fail S2-05's idempotence property test. | Note carried for S2-05; no action here (the story's `Out of scope` explicitly forbids caching per Phase 7 ADR-0008). |
| TQ-3 | nit | AC-1's signature test asserts parameter kinds but not annotations. A refactor that widens `image_ref: ImageRef \| None` to `image_ref: object \| None` would not fail AC-1. Given `mypy --strict` under `make check` guards annotations globally, the direct test would be redundant. | No action — the static-gate coverage is real. |
| TQ-4 | nit | AC-11's `_CountingAdapter.construct_count` uses a class-level counter reset only by the class definition inside the test function — if pytest orders the test differently or reruns via `--collect-only`, the counter still resets because the class is re-created each call. Robust as-is. | No action. |

### Consistency — STRONG (one accepted-deviation to document)

Story faithfully implements Phase-7 ADR-0006 §Decision (dispatch order is explicit `Final` tuple; `match`/`assert_never` composition; BP-4 closure), ADR-0007 §Consequences (construct via `AdapterFactory`; `ProvenanceError` folds to `Unknown`), ADR-0001 (`Both` is typed evidence — no coordinator), ADR-0004 (primitive home). Production ADR-0038 cited as the deferred-question resolution. Cross-consistency with S2-01 (registry), S2-02 (factory), S2-03 (dispatch order tuple + iteration helper) all holds.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| CN-1 | harden | The **Implementation outline** at story lines 74–126 shows locals typed `AppKind \| None` / `BaseKind \| None` with plain-capture match arms (`case (app, None):`, `case (None, base):`). The **shipped** code (`assembly.py:160-204`) types locals as `Provenance \| None` and uses **class-pattern narrowing** (`case (AppDirect() \| AppTransitive() \| AppVendored() as app, None):`) with `cast("AppKind", app)` / `cast("BaseKind", base)` in the `Both(...)` construction. This is a design refinement — the class-pattern arms + `Both(...)`'s Pydantic discriminated-union validation catch a misbehaving adapter that smuggles a wrong-layer variant (fail-loud per Rule 12), whereas the plain-capture outline would silently trust the adapter's layer contract. The shipped choice is more robust; the outline text was not updated. | Documented in `Validation notes` as an accepted deviation. The Implementation outline is not surgically edited (Rule 3 — outlines are suggestions; the ACs and shipped code are the contract). |
| CN-2 | nit | The Evidence line references `_attempts/S2-04-assemble-provenance-function.md` — file exists (single attempt confirmed). No drift. | No action. |
| CN-3 | nit | Story's TDD-plan `Red` fixture uses `AppDirect(cve_id=..., package_id=..., chain_length=1)` but shipped `AppDirect` (S1-03) has fields `manifest_path`, `package`, `confidence`. Also `ImageDigest.parse_or_raise("sha256:...")` in the story vs shipped `parse_image_digest("sha256:...").unwrap()`. TDD-plan snippets are illustrative — they were written before S1-01/S1-02/S1-03 finalized, and the shipped tests use the correct parsers/fields. | No action — TDD-plan text is illustrative; shipped tests are the source of truth. |
| CN-4 | nit | Story's Implementation-outline snippet does not import `cast` in its "Import:" list, but the shipped module imports it. Consistent with CN-1's refinement disposition. | No action. |

### Design Patterns — STRONG (one positive precedent worth surfacing)

Registry (S2-01) + `Final`-tuple marker catalog (S2-03) + Factory (S2-02) + Ports-and-adapters (S1-04) + Sum-type / discriminated union (S1-03) + `match`/`assert_never` exhaustiveness (this story) compose into a clean Open/Closed shape: extending `Ecosystem` is free, extending `Layer` is ADR-gated, adding an eighth `Provenance` variant would fail `mypy --strict` at the `assert_never(...)` line and force explicit AC growth here. Functional-core-with-imperative-shell (pure `_ECOSYSTEM_SORT_KEY` precompute + `iter_adapters_for_layer_set` sort + local mutable-state `adapter_error_seen`/`app_result`/`base_result` loop) is well-balanced for the ≤80-LOC budget.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| DP-1 | note | **Class-pattern arms `(AppDirect() \| AppTransitive() \| AppVendored() as app, None):`** — a valuable "pattern-matching-as-validation" idiom shipped over the outline's plain-capture arms. It makes the composition self-validating: a misbehaving adapter that returns a `BaseImage` for a `Layer.APP` registration falls through to the irrefutable `(app, base)` arm and is caught by `Both(...)`'s Pydantic discriminated-union validator (`app_record: AppKind`, `base_record: BaseKind`). Sibling story S3-01 and later Phase 8+ provenance stories should copy this idiom instead of trusting layer-tag correlation. | Carried in `Validation notes` as a positive precedent for downstream provenance stories; no AC change (the pattern is behavioral, not contractual). |
| DP-2 | note | `adapter_error_seen: bool` is a small piece of local mutable state in an otherwise-pure composition. A `Result[Provenance, AdapterErrorSet]`-monad shape would express "any-adapter-error poisons the (None, None) reason" more explicitly, but at the cost of a new type + a `Result`-vocabulary rollout. Rule 2 acceptable; note for the day a second global-error-tracking flag appears. | No action (Rule 2 — three-similar-lines beats premature abstraction). |
| DP-3 | note | The `if layer_set == (Layer.APP,): ...; elif layer_set == (Layer.BASE_IMAGE,): ...; break` branches implicitly encode a `Layer → slot` map. If a fourth layer ever ships without ADR-gating the RUNTIME slot's activation, the mapping should be extracted into a small `_LAYER_TO_SLOT_SETTER: Mapping[tuple[Layer, ...], Callable[[Provenance], None]]` dict — but today the three-branch structure is `Rule 2`-appropriate and the RUNTIME row is deliberately no-op. | No action; note carried for the first RUNTIME-adapter story (mirrors C-3's disposition). |
| DP-4 | note | `cast("AppKind", app)` / `cast("BaseKind", base)` in the `Both(...)` construction is the mypy-required bridge between the `Provenance \| None` locals and `Both`'s narrowed field types. An alternative shape ("stash into typed locals from the start") would eliminate the casts but re-adopts the outline's less-defensive layer-tag-only correlation. The shipped choice trades two `cast` calls for a Pydantic-guarded fail-loud path — a good trade. | No action. |

## Edits applied to the story

All surgical (Rule 3):

1. **Status line** — appended `(HARDENED retroactively 2026-07-26)`.
2. **`Validation notes` block** — appended under the story documenting the retrospective review: verdict, the CN-1 accepted-deviation (class-pattern arms + `Provenance | None` locals over the outline's `AppKind | None` / `BaseKind | None`), the DP-1 pattern-matching-as-validation positive precedent for downstream stories, the C-1 / C-2 / C-3 mixed-scenario and RUNTIME notes deferred to S2-05 / the first RUNTIME-adapter story, and the coverage tally showing all fifteen ACs anchored.

**Not edited:** every checked-off AC-1..AC-15 (Rule 12 — shipped evidence is authoritative), the Goal, the Scope reminder, the References, the Implementation outline (Rule 3 — outlines are suggestions; the CN-1 deviation is documented in `Validation notes`, not rewritten inline), the TDD plan (illustrative snippets predating S1-01/S1-02/S1-03 finalization; shipped tests are the source of truth), the Files-to-touch table, the Out-of-scope list, the existing Notes-for-the-implementer bullets.

## Verdict rationale

- No critic returned a `block`-severity finding.
- The single `harden` finding (CN-1) is a shipped implementation refinement that the outline did not anticipate; per Rule 3 (surgical edits), the outline is not rewritten — the deviation is documented explicitly in `Validation notes` so future readers understand why the shipped `match` has more sophisticated class-pattern arms than the story's illustrative snippet.
- All other findings are `note` or `nit` — either Rule-2-appropriate (three-similar-lines beats premature abstraction), correctly deferred to S2-05 (property tests) / a future RUNTIME-adapter story, or covered indirectly by an adjacent static gate (`mypy --strict`).
- Every one of the fifteen ACs is anchored to a shipped-and-green test. No new AC needed.
- Shipped implementation is a clean instantiation of Registry + `Final`-tuple marker catalog + Factory + Ports-and-adapters + Sum-type + `match`/`assert_never` exhaustiveness, faithful to ADR-0006, ADR-0007, ADR-0001, ADR-0004, and production ADR-0038.

**STRONG.** No re-execution needed. Notes are seeded for S2-05 (property tests over the mixed-scenario matrix) and the first RUNTIME-adapter story (activating the reserved slot per ADR-0006).
