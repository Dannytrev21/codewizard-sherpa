# Validation report — S1-01 `IndexFreshness` sum type

**Story:** [`../S1-01-index-freshness-sum-type.md`](../S1-01-index-freshness-sum-type.md)
**Validated:** 2026-05-15
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The story implements `IndexFreshness = Fresh | Stale(reason: StaleReason)` at `src/codegenie/indices/freshness.py` as a Pydantic discriminated-union sum type. The goal, scope, references, and pattern choice (Sum type + Make-illegal-states-unrepresentable + schema-paired-with-consumer) all trace cleanly to `02-ADR-0006`, `phase-arch-design.md §"Component design" #2` / §"Data model", and `High-level-impl.md` Step 1. The draft was structurally sound — no `RESCUE`-tier findings — but had five harden-tier gaps in AC coverage and TDD mutation-resistance that would have let an obviously wrong implementation slip through the executor's Validator pass.

Five hardening edits were applied in place; the story is now ready for `phase-story-executor`. No `NEEDS RESEARCH` findings (Stage 3 skipped — every gap was answerable from arch + ADR-0006 + the existing Pydantic discriminated-union docs the story already cites).

## Context Brief (Stage 1)

- **Goal as written:** Implement `src/codegenie/indices/{__init__.py, freshness.py}` as a Pydantic discriminated-union sum type — `IndexFreshness = Fresh | Stale(reason: StaleReason)` with `StaleReason = CommitsBehind | DigestMismatch | CoverageGap | IndexerError` — that round-trips identity through `model_dump_json` / `model_validate_json` and is exhaustively matchable with `assert_never`.
- **Phase 2 exit criteria touched:** G4 ("Single name, single module, single Phase-2 consumer for the freshness sum type"), G9 (kernel scaffolding ships before Phase 3), G2 (the load-bearing stale-scip case asserts an exact typed `IndexFreshness.Stale(reason=CommitsBehind(...))`).
- **Load-bearing commitments touched:**
  - CLAUDE.md §"Honest confidence" — `IndexFreshness` IS the typed surface for the worst-failure-mode probe in the system.
  - `production/design.md §2.3` — silent index staleness; the typed sum is the structural fix.
  - `02-ADR-0006 §Consequences` — names `tests/property/test_index_freshness_roundtrip.py` as a deliverable.
  - `phase-arch-design.md §"Data model"` — pins exact Pydantic shape (frozen, extra=forbid, Literal["..."] discriminators, `Annotated[Union[...], Field(discriminator="kind")]`).
- **Open/Closed boundaries:**
  - New consumer of `IndexFreshness` → import (zero edits to `freshness.py`).
  - New *index source* freshness check → S1-02's `@register_index_freshness_check` decorator-registry in `registry.py` (new file + decorator; never edit `freshness.py` or `index_health.py`'s `run()`).
  - New `StaleReason` variant → **deliberately ADR-amendment-gated**, not Open/Closed. The `assert_never` arms enforce.
- **Phase 1 prior art consulted:** `src/codegenie/parsers/safe_yaml.py` (frozen+extra=forbid discipline; module-docstring citation; stdlib + chokepoint deps); errors-extension validation report (S1-01 phase 01) for the validator's prior pattern of markers-only invariants.

## Stage 2 — critic reports

### Coverage (verdict: COVERAGE-HARDEN)

- **F1 (harden).** AC-4 (round-trip identity) only verifies `type(decoded) is type(instance)` at the top level. For `Stale` instances, `type(decoded.reason) is type(instance.reason)` is unasserted. A regression that drops `Field(discriminator="kind")` from `StaleReason`'s `Annotated` wrapper would leave `Stale.reason` deserialized as a plain `dict`, yet `Stale` itself would still round-trip equal — AC-4 passes; real consumers break. **Fix:** tighten AC-4 + parametrized test to assert nested type preservation for every `Stale` case.
- **F2 (harden).** No AC pins the **discriminator string values** (`"fresh"`, `"stale"`, …). A symmetric swap (`CommitsBehind.kind = "digest_mismatch"` + `DigestMismatch.kind = "commits_behind"`) would round-trip cleanly while breaking every cross-ADR consumer (rendered Markdown, golden files, downstream Phase 3 plugins). **Fix:** add an AC requiring exact-string pinning and a dedicated test (`test_discriminator_strings_are_exactly_pinned`).
- **F3 (harden).** Exhaustive `match` test (AC-6) covers `StaleReason` (4 variants) but NOT the top-level `IndexFreshness` (Fresh | Stale). The renderer at S8-01 must `match` at both layers; the discipline should be rehearsed symmetrically. **Fix:** add AC-6a + `test_match_is_exhaustive_over_index_freshness_top_level`.
- **F4 (harden).** `02-ADR-0006 §Consequences` explicitly enumerates `tests/property/test_index_freshness_roundtrip.py` (Hypothesis) as a deliverable. `High-level-impl.md` Step 7 line 247 references it as *"already may exist from Step 1's freshness tests"* — i.e., Step 1 owns the scaffold. Story omits it. **Fix:** add AC-11 + a full Hypothesis-based property test.
- **F5 (nit).** No JSON-shape pin — round-trip identity tolerates a symmetric `kind → tag` rename of the discriminator field. A single golden-shape assertion catches this and pins the cross-ADR contract at the JSON boundary, not just the Python-object boundary. **Fix:** add AC-10 + `test_json_shape_pinned`.

### Test quality (verdict: TESTS-HARDEN)

Mutation analysis (10 plausible wrong implementations):

| # | Wrong implementation | Caught by draft TDD? | Severity |
|---|---|---|---|
| 1 | Drop `frozen=True` from `model_config` | Yes — `test_models_are_frozen_and_forbid_extra` does `inst.n = 2` | — |
| 2 | Drop `extra="forbid"` from `model_config` | Yes — same test | — |
| 3 | Drop `Field(discriminator="kind")` wrapper from `StaleReason` | **No** — round-trip would deserialize `Stale.reason` as a plain dict; `type(decoded) is type(instance)` (Stale) holds; nested type unchecked | harden |
| 4 | Symmetric swap of `CommitsBehind.kind` and `DigestMismatch.kind` | **No** — both sides emit the same wrong string; round-trip equal | harden |
| 5 | Drop `kind` default value on a variant (force callers to pass it explicitly) | Yes — fixture constructs `CommitsBehind(n=3, last_indexed="abc1234")` without `kind=` and would fail | — |
| 6 | Add a fifth `StaleReason` variant but forget to extend `StaleReason = Union[...]` | Yes at *type-check* time (mypy `--warn-unreachable` post-S1-11); documented in test docstring as runtime-undetectable today | accepted |
| 7 | Rename discriminator field `kind` → `tag` symmetrically on every variant | **No** — round-trip identity still passes; only a JSON-shape pin or external golden detects | nit |
| 8 | Implement `Fresh` with no fields (drop `indexed_at`) | Yes — fixture constructs `Fresh(indexed_at=…)` and would fail in green | — |
| 9 | Make a class a `dataclass` instead of `BaseModel` | Yes — `TypeAdapter` validation fails | — |
| 10 | Use `model_construct` inside `freshness.py` for "performance" | **No** — story Notes prohibit but no test scans source | harden |

Mutations 3, 4, 7, 10 motivate AC-4 tightening, AC-2 tightening, AC-10, and a `test_freshness_module_has_no_model_construct` source-scan respectively.

Other test-quality concerns:
- The `test_match_is_exhaustive_over_stale_reason` test's docstring correctly documents that runtime detection of a missed arm requires the S1-11 mypy override. This is good intent-versus-behavior discipline (Rule 9).
- `STALE_REASONS: list[StaleReason]` uses the type alias as a runtime annotation under `from __future__ import annotations`; deferred evaluation makes this safe. No fix needed.

### Consistency (verdict: CONSISTENCY-CLEAN with one ADR-deliverable miss)

- Frozen + `extra="forbid"` + `Literal["..."]` discriminator + `Annotated[Union[...], Field(discriminator="kind")]` — exact match to `phase-arch-design.md §"Data model"`. ✓
- Module location `src/codegenie/indices/freshness.py` matches `02-ADR-0006 §Decision`. ✓
- `__all__` set of eight names matches arch §"Component design" #2 and ADR-0006 verbatim. ✓
- `last_indexed: str` raw at I/O boundary (no `CommitSha` newtype) — matches story's Notes-for-implementer and S1-05's scope. ✓
- `assert_never` from `typing` (Python 3.11+) — Phase 0 baseline. ✓
- No `model_construct` — aligns with `phase-arch-design.md §"Anti-patterns avoided"` row `model_construct() bypass`. ✓ (test added by Coverage F-mutation #10)
- `Stale.reason: StaleReason` typed (not `dict` / `Optional[str]`) — matches `phase-arch-design.md §"Design patterns applied"` row 1 ("Null Object — loses the *reason*; `Optional[str]` — stringly-typed" rejected). ✓
- **Miss:** `02-ADR-0006 §Consequences` names `tests/property/test_index_freshness_roundtrip.py` (Hypothesis) as a deliverable. Story does not include it. Treated as harden by Coverage F4; no conflict — additive.

No `RESCUE`-tier findings.

### Design patterns (verdict: DESIGN-CLEAN, one Notes-for-implementer extension)

The story IS the canonical Sum type + Make-illegal-states-unrepresentable + schema-paired-with-consumer implementation. The patterns are correct as written. Considerations:

- **Variant-set extension is deliberately not Open/Closed.** Adding a fifth `StaleReason` is an ADR amendment to `02-ADR-0006`, not a registry-by-addition. `assert_never` is the enforcement. The story's draft Notes mention this implicitly via the S1-11 reference; explicit framing in a Notes paragraph prevents an implementer from misreading the prevalence of `@register_*` decorators in this phase as "ergo every variant set must be pluggable."
- **Open/Closed seam for new *index sources* lives in S1-02, not here.** `freshness.py` must remain pure data so `registry.py` can layer the `@register_index_freshness_check` decorator-registry without circular imports. The draft does not explicitly forbid pre-stubbing the registry; this is a future-proofing nit worth documenting.
- **No new patterns wanted.** Strategy / Plugin / Capability would all over-engineer the variant set; the toolkit's "premature pluggability" anti-pattern (`phase-arch-design.md §"Anti-patterns avoided"`) applies. Rule 2 ("simplicity first") and Rule 3 ("surgical changes") protect the boring shape.
- **Smart constructor** = the Pydantic ctor with `extra="forbid"` + `Literal["..."]` default. No additional helper function needed; the Pydantic constructor IS the smart constructor (per ADR-0006 §"Pattern fit").
- **Composition over inheritance** is honored: every class inherits *only* `BaseModel`; no shared marker base in `freshness.py` beyond Pydantic itself.
- **Functional core / imperative shell** is honored trivially: `freshness.py` is pure data; no I/O, no logger. The renderer (S8-01) is the imperative shell.

Outcome: extend Notes-for-implementer with two paragraphs (Open/Closed seam handoff, variant-set extension is ADR-gated).

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings. Every gap is answerable from `02-ADR-0006`, `phase-arch-design.md`, `High-level-impl.md`, and Pydantic's discriminated-union docs the story already cites.

## Stage 4 — Synthesizer resolution

### Conflict resolution

No critic-vs-critic conflicts. Coverage F1 (typed nested reason) and Test-Quality mutation #3 reinforce each other; Coverage F2 and Test-Quality mutation #4 reinforce each other; Coverage F4 and Consistency's ADR-deliverable miss reinforce each other. All harden-tier; no Consistency veto needed.

### Edits applied to the story

| Section | Before | After |
|---|---|---|
| Status | `Ready` | `Ready (hardened by phase-story-validator 2026-05-15)` |
| New `Validation notes` block | absent | 7-point summary of structural changes + report link |
| AC-2 | "unique discriminator string (`"fresh"`, `"stale"`, ...)" | + "**exact** discriminator string named in 02-ADR-0006 §Decision / phase-arch-design.md §"Data model"" with per-variant `cls.kind == "..."` pinning; framing as cross-ADR contract |
| AC-4 | "round-trip identity, parametrized" — top-level type only | + "For every `Stale(reason=R)` instance the round-trip additionally preserves the nested typed reason: `type(decoded.reason) is type(instance.reason)`" + explanation of the discriminator-wrapper regression it guards against |
| AC-5 | Unknown-reason rejection only | + top-level unknown-kind rejection via `TypeAdapter(IndexFreshness).validate_python({"kind": "bogus_freshness"})` |
| AC-6a (new) | — | Exhaustive `match` over top-level `IndexFreshness` (Fresh \| Stale) with `assert_never`; symmetric with AC-6 |
| AC-9 | pytest path = `tests/unit/indices/test_freshness.py` | + `tests/property/test_index_freshness_roundtrip.py` |
| AC-10 (new) | — | JSON-shape pin: literal `model_dump(mode="json")` snapshot for one Fresh + one Stale-with-CommitsBehind |
| AC-11 (new) | — | Hypothesis property test deliverable per `02-ADR-0006 §Consequences` |
| TDD plan — red tests | 5 tests | 9 tests + 1 property test file; added: `test_index_freshness_roundtrip_identity` extended for nested type, `test_discriminator_strings_are_exactly_pinned`, `test_json_shape_pinned`, `test_top_level_unknown_kind_is_rejected`, `test_match_is_exhaustive_over_index_freshness_top_level`, `test_freshness_module_has_no_model_construct`, full `tests/property/test_index_freshness_roundtrip.py` |
| Files to touch | 3 files | 5 files (+ `tests/property/__init__.py`, `tests/property/test_index_freshness_roundtrip.py`) |
| Notes for implementer | 6 paragraphs | + 4 paragraphs: Open/Closed seam handoff to S1-02; variant-set extension is ADR-amendment-gated (not Open/Closed); discriminator strings are cross-ADR contract; property test is small + additive + ADR-named |

### Mutation-resistance crosswalk after edits

| # | Wrong implementation | Caught by hardened TDD? |
|---|---|---|
| 1 | Drop `frozen=True` | Yes (unchanged from draft) |
| 2 | Drop `extra="forbid"` | Yes (unchanged from draft) |
| 3 | Drop `Field(discriminator="kind")` from `StaleReason` | **Yes** — `test_index_freshness_roundtrip_identity` now asserts `type(decoded.reason) is type(instance.reason)`; property test asserts the same on arbitrary Hypothesis-generated inputs |
| 4 | Symmetric swap of two `kind` strings | **Yes** — `test_discriminator_strings_are_exactly_pinned` asserts each `cls(...).kind == "exact_string"` |
| 5 | Drop `kind` default value | Yes (unchanged) |
| 6 | Add 5th `StaleReason` and forget `Union` extension | Yes at mypy-time (S1-11), accepted at runtime |
| 7 | Symmetric rename `kind → tag` | **Yes** — `test_json_shape_pinned` asserts literal JSON dict containing `"kind"` |
| 8 | Drop `Fresh.indexed_at` | Yes (unchanged) |
| 9 | Use `dataclass` instead of `BaseModel` | Yes (unchanged) |
| 10 | Use `model_construct` inside `freshness.py` | **Yes** — `test_freshness_module_has_no_model_construct` source-scans the module |
| 11 (new) | Add a hypothetical third top-level variant (`Unknown`) without extending the renderer's match | **Yes** at mypy-time on the renderer (S8-01 + S1-11); `test_match_is_exhaustive_over_index_freshness_top_level` documents the discipline runtime-side |

### Design-pattern crosswalk after edits

| Concern | Pattern applied | Where documented |
|---|---|---|
| Make illegal states unrepresentable | Pydantic discriminated union (`Annotated[Union[...], Field(discriminator="kind")]`); `Literal["..."]` on every variant; `extra="forbid"` + `frozen=True` | AC-2, AC-3; `phase-arch-design.md §"Data model"` |
| Sum type for state | `IndexFreshness = Fresh \| Stale`; `StaleReason = CommitsBehind \| DigestMismatch \| CoverageGap \| IndexerError` | Goal; AC-3 |
| Smart constructor | Pydantic ctor + `Literal["..."]` default + `extra="forbid"` | AC-2; ADR-0006 §"Pattern fit" |
| Schema paired with consumer | Consumer = `report/confidence_section.py` (S8-01); story documents the dependency, does NOT ship it | Context; Out of scope; Notes |
| Open/Closed (new index sources) | `@register_index_freshness_check(index_name: IndexName)` in S1-02's `registry.py`; this module remains pure data | Notes for implementer (new paragraph) |
| Variant-set stability (intentional NON-Open/Closed) | ADR-amendment-gated; `assert_never` enforcement on every consumer | Notes for implementer (new paragraph); AC-6, AC-6a |
| Functional core / imperative shell | `freshness.py` is pure data; no I/O, no logger, no decorator | Notes; AC-8 (no `model_construct`) + source-scan |
| Composition over inheritance | All variants inherit only `BaseModel`; no shared marker | (implicit in Implementation outline) |
| Avoid primitive obsession | Variants typed via Pydantic; `last_indexed: str` is the I/O-boundary exception (commit SHA from git raw) | Notes for implementer (existing paragraph) |
| Premature pluggability avoided | No registry over variant set; no factory; no `NullFreshness` | Notes for implementer (new paragraph); `phase-arch-design.md §"Anti-patterns avoided"` |

## Verdict

**HARDENED.** Story now satisfies the validator's "STRONG" bar:

- Every AC is individually verifiable (binary pass/fail).
- AC set collectively guarantees the goal — round-trip identity is now end-to-end-typed; discriminator strings are pinned at both the Python and JSON layers; exhaustive `match` is rehearsed at both levels of the sum.
- Every AC has at least one mutation-resistant test in the TDD plan.
- No tautologies, no "no exception thrown" checks, no qualitative-only assertions.
- No contradictions with arch / ADR-0006 / production design / CLAUDE.md commitments.
- Edge cases covered: unknown discriminator at both levels, frozen mutation attempt, extra-field attempt, source-scan for `model_construct`, JSON-shape stability, Hypothesis-generated arbitrary input round-trip.
- Implementation consumes existing kernels (Pydantic, stdlib, `typing.assert_never`); introduces no premature abstraction; leaves the S1-02 Open/Closed seam open by remaining pure data.
- Domain identifiers are typed (`Literal["..."]` discriminators; `StaleReason`/`IndexFreshness` as `Annotated[Union[...], Field(discriminator=...)]` aliases); illegal combinations (untyped `Stale.reason`, unknown discriminators, extra fields, mutation) are unrepresentable.

Ready for `phase-story-executor`.
