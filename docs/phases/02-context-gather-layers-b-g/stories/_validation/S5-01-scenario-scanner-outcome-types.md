# Validation report — S5-01 `ScenarioResult` + `ScannerOutcome` shared discriminated unions

**Story:** [`../S5-01-scenario-scanner-outcome-types.md`](../S5-01-scenario-scanner-outcome-types.md)
**Validated:** 2026-05-16
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The story plants two pure-typing modules: `src/codegenie/probes/layer_c/scenario_result.py` (`ScenarioResult = TraceScenarioCompleted | TraceScenarioFailed | TraceScenarioSkipped`) and `src/codegenie/probes/_shared/scanner_outcome.py` (`ScannerOutcome = ScannerRan | ScannerSkipped | ScannerFailed`). The goal, scope, references, and pattern choice (Sum type + Make-illegal-states-unrepresentable + schema-paired-with-consumer) all trace cleanly to `02-ADR-0006`, `phase-arch-design.md §"Component design"` #5 / #6 / §"Data model", and `High-level-impl.md` Step 5 §171–172.

This is the **2nd canonical sum-type story in Phase 2** — S1-01 (`IndexFreshness`) was the 1st. The HARDENED precedent set there (discriminator-string pinning; nested-type roundtrip; JSON-shape pinning; exhaustive `match` at every level of the sum; Hypothesis property test; source-scan against `model_construct`; literal `__all__` pinning) applies symmetrically here. The draft was structurally sound — no `RESCUE`-tier findings — but missed the same five mutation-resistance gaps S1-01's draft had, PLUS two consistency findings unique to this story (a stale per-module mypy override that S1-11 made redundant, and a hedged `forbidden-patterns` extension that inspection showed was actually required, not optional).

Twelve hardening edits were applied in place; the story is now ready for `phase-story-executor`. No `NEEDS RESEARCH` findings — every gap was answerable from `02-ADR-0006`, S1-01's HARDENED report, the existing `IndexFreshness` implementation pattern, the existing `JSONValue` alias, the current state of `pyproject.toml` line 141, the current state of `scripts/check_forbidden_patterns.py`, and the existing S1-11 validation report.

## Context Brief (Stage 1)

- **Goal as written:** Land two pure-typing modules exporting Pydantic discriminated unions with `kind` discriminators, JSON round-trip identity, and exhaustive `match` enforced at the type level for downstream consumers (zero probes consume them this story).
- **Phase 2 exit criteria touched:** Schema-with-consumer discipline (consumers are S5-02 / S5-04 / S6-06 / S6-07 / S6-08 — declared in module docstring per ADR-0006 precedent); G4 / G9 (kernel scaffolding ships before consumers).
- **Load-bearing commitments touched:**
  - `production/design.md §2.3` — honest confidence / typed surface.
  - `02-ADR-0006 §Consequences` — sum-type discipline, ADR-amendment-gated variant extension, Hypothesis property test deliverable.
  - `phase-arch-design.md §"Data model"` — Pydantic shape (frozen, extra=forbid, Literal["..."], `Annotated[Union[...], Field(discriminator="kind")]`).
  - `phase-arch-design.md §"Anti-patterns avoided"` row 12 — `model_construct()` bypass; `forbidden-patterns` extension closes the loop.
  - `CLAUDE.md` "Extension by addition" — but variant-set extension is **deliberately** NOT Open/Closed for this family.
- **Open/Closed boundaries:**
  - New consumer of `ScannerOutcome` / `ScenarioResult` → import (zero edits to these modules).
  - New variant → **ADR-amendment-gated**, NOT registry-by-addition. `assert_never` on every consumer enforces.
  - The Open/Closed seam for *new scanner kinds* (a 7th probe wrapping a 5th external CLI) lives at the probe level via `@register_probe`, not at the type level.
- **Sibling-family lineage:** 2nd canonical sum-type story; S1-01 (`IndexFreshness`) was the 1st. The validator-hardened S1-01 is the precedent template.
- **Existing kernels to consume:** `codegenie.parsers.JSONValue` (recursive alias at `src/codegenie/parsers/__init__.py:34`); Pydantic discriminated unions; `typing.assert_never`; `pytest`, `hypothesis` (both already in `pyproject.toml`).
- **Existing files that may be edited:** `pyproject.toml` `[tool.mypy]` — `warn_unreachable = true` already repo-wide since Phase 0 S1-02 (`pyproject.toml` line 141); per-module overrides would be redundant. `scripts/check_forbidden_patterns.py` — `_is_under_phase2_banned_package` currently covers `{indices, tccm, skills, conventions, adapters, depgraph, output}`; does NOT cover `probes/_shared/` or `probes/layer_c/`, so the extension IS needed.
- **Arch tension to flag:** `phase-arch-design.md §"Data model"` line 731 still pins `[internal] codegenie/probes/layer_g/scanner_outcome.py`; the story + High-level-impl.md §172 evolve to `_shared/` — surface as documentation-debt in `Notes for implementer`, do NOT edit the arch (Rule 3 — surgical).

## Stage 2 — critic reports

### Coverage critic (verdict: COVERAGE-HARDEN)

- **CF1 (harden).** AC-5 (round-trip identity) asserts `parse(dump(v)) == v` byte-for-byte but does NOT require **nested type preservation** for sum-of-sum cases. A regression that drops `Field(discriminator="kind")` from `TraceFailureReason`'s `Annotated` wrapper would deserialize `TraceScenarioFailed.reason` as a plain `dict`; `TraceScenarioFailed`-level equality could still pass. Same regression S1-01 F1 / mutation #3 caught. **Fix:** tighten AC-5 + Test 3 parametrization to assert `type(decoded.reason) is type(instance.reason)` for every `TraceScenarioFailed` / `TraceScenarioSkipped` case and `[type(f) for f in decoded.findings] == [type(f) for f in instance.findings]` for `ScannerRan`.
- **CF2 (harden).** **No AC pins the discriminator string values.** AC-3 says each variant has *a* unique `kind: Literal["..."]`, but a symmetric swap (`ScannerRan.kind = "failed"` + `ScannerFailed.kind = "ran"`) would round-trip cleanly while breaking every downstream consumer + every cross-doc reference. Same as S1-01 F2 / mutation #4. **Fix:** add an AC + `test_discriminator_strings_are_exactly_pinned` (new AC-12).
- **CF3 (harden).** **No JSON-shape pin.** Round-trip identity tolerates a symmetric rename of the discriminator field (`kind → tag` on every variant). Same as S1-01 F5 / mutation #7. **Fix:** add an AC + `test_json_shape_pinned` (new AC-13).
- **CF4 (harden).** **Hypothesis property test absent.** S1-01's HARDENED template adds `tests/property/test_index_freshness_roundtrip.py` per ADR-0006 §Consequences pattern; S7-05's "property and portfolio integration" story explicitly cites property-tests per type as established by the per-type story. Symmetry argument is load-bearing — the 2nd sum type without the property test would erode the precedent. **Fix:** add AC + `tests/property/test_sum_types_roundtrip.py` (new AC-15).
- **CF5 (harden).** **Top-level "unknown discriminator" rejection unspecified.** Without an explicit assertion, a future contributor could relax the discriminator (`Union` without `Field(discriminator=)`) and silently lose the exhaustiveness guarantee. **Fix:** add AC + `test_unknown_discriminator_is_rejected` parametrized over all four unions (new AC-14).
- **CF6 (harden).** **Exhaustive `match` only over top-level unions.** The inner sum types (`TraceFailureReason`, `TraceSkipReason`) exist precisely *because* consumers (S5-05, S8-01) must `match` on `reason` — the discipline should be rehearsed at every level. **Fix:** add AC-6a — `_describe_failure_reason` and `_describe_skip_reason` consumer helpers each `match` with `assert_never`.
- **CF7 (harden).** **`Finding` shape not anchored to a roundtrip test.** A regression that drops `JSONValue`'s recursive constraint (`metadata: dict[str, JSONValue]` → `metadata: dict[str, Any]`) round-trips primitives cleanly but loses the typed JSON-tree constraint. **Fix:** add AC + `test_finding_metadata_jsonvalue_roundtrip` constructing a deeply-nested `metadata` payload (new AC-16).
- **CF8 (nit).** **`stderr_tail` cap is duplicated** between the field_validator, the docstring, and the test. **Fix:** require `STDERR_TAIL_CAP_BYTES: Final[int] = 4096` as a module-level constant; both validator and tests import it.

### Test-Quality critic (verdict: TESTS-HARDEN)

Mutation analysis (12 plausible wrong implementations):

| # | Wrong implementation | Caught by draft TDD? | Severity |
|---|---|---|---|
| 1 | Drop `frozen=True` from `model_config` | **No** — story has no frozen-attempt test | harden |
| 2 | Drop `extra="forbid"` from `model_config` | **No** — same gap | harden |
| 3 | Drop `Field(discriminator="kind")` wrapper from inner `TraceFailureReason` | **No** — see CF1 | harden |
| 4 | Symmetric swap of two variants' `kind` strings | **No** — see CF2 | harden |
| 5 | Use `model_construct` to bypass validation | **Partial** — story's draft Test 8 ran `pre-commit run`; but `_shared/` and `layer_c/` are NOT in the current banned set (verified via `scripts/check_forbidden_patterns.py`). Without the extension, `pre-commit` would pass silently. | block→harden |
| 6 | Symmetric rename discriminator `kind → tag` | **No** — see CF3 | harden |
| 7 | Add a fifth variant without extending the `Annotated[Union[...]]` alias | Yes at mypy-time once consumers exist; accepted at runtime today | accepted |
| 8 | `ScannerFailed(stderr_tail=…)` cap raised silently from 4096 to 8192 | Yes — Test 6 asserts `len == 4096`; off-by-one boundary additionally pinned via CF8 + boundary test (TF-B) | hardened |
| 9 | `ScannerSkipped.reason` becomes `str` instead of `Literal[...]` | Yes — original Test 7 (extended to formal parametrized closure test) | hardened |
| 10 | `Finding.metadata` regressed to `dict[str, Any]` (loses recursive `JSONValue`) | **No** — see CF7 | harden |
| 11 | `Finding.severity` regressed from `Literal[...]` to `str` | **No** — story spec has it as Literal but no test asserts strings outside the closed set are rejected | harden |
| 12 | `kind: Literal["..."]` default value dropped (forces callers to pass) | Partial — fixtures construct without `kind=`; would fail at construction | acceptable |

Other test-quality concerns:

- **TF-A (harden).** No `test_models_are_frozen_and_forbid_extra` covering (a) `inst.kind = "other"` raises `ValidationError`; (b) `Model(..., extra_field=1)` raises `ValidationError`. The two cheapest cross-cut mutation-resistance tests. Mirrors S1-01. → new AC-17, Test 13.
- **TF-B (harden).** Test 6 `test_scanner_failed_stderr_tail_truncates` doesn't cover the boundary triple at exactly cap. Off-by-one in `[: cap]` slicing undetected. → boundary parametrization in Test 7 over `{0, 1, 4095, 4096, 4097, 8192}`.
- **TF-C (harden).** Test 5 `test_strace_unavailable_is_typed` only covers ONE inner variant. Outline change hard-coding a single inner type undetected. → parametrize Test 3 over every (failure-reason × `TraceScenarioFailed`) and (skip-reason × `TraceScenarioSkipped`).
- **TF-D (nit).** Test 8's `pre-commit run` shell-out is the wrong signal: it'd be a no-op if the extension didn't land. Replace with a source-scan over the new module files (Test 16) + the proper forbidden-patterns parametrized extension test (Test 17).
- **TF-E (harden).** No test pins `__all__` exports literally — silent export drift undetected. → new AC-18, Test 14.

### Consistency critic (verdict: CONSISTENCY-HARDEN with 2 corrections)

- **NF-A (harden).** **`phase-arch-design.md §"Data model"` line 731 prescribes `[internal] codegenie/probes/layer_g/scanner_outcome.py`** — the story relocates to `_shared/`. High-level-impl.md §172 agrees with `_shared/`. The relocation is **right** (it serves both Layer C S5-04 and Layer G S6-06/07/08); the arch is stale. **Fix:** add a `Notes for implementer` paragraph acknowledging arch-doc drift; point implementer to leave the arch unchanged (Rule 3 — surgical) since High-level-impl.md is the authoritative impl plan.
- **NF-B (block→harden).** AC-10 prescribed "`mypy --warn-unreachable` per-module override (from S1-11) is configured for ..." but S1-11 validation established that `warn_unreachable = true` is **already repo-wide** since Phase 0 S1-02 (`pyproject.toml` line 141). Adding per-module overrides would be redundant noise — matches S1-11's "honored-broader-than-arch" framing. **Fix:** rewrite AC-10 to assert the repo-wide flag is present and unmodified (new Test 18); document in `Notes`.
- **NF-C (harden).** AC-11 hedged ("if not already covered"). Inspection of `scripts/check_forbidden_patterns.py` confirms `_is_under_phase2_banned_package` covers `{indices, tccm, skills, conventions, adapters, depgraph, output}` — does NOT cover `probes/_shared/` or `probes/layer_c/`. The hedge was therefore false; the extension IS required. **Fix:** rewrite AC-11 to drop the hedge, explicitly require the script extension + a dedicated test (mirroring S1-11 AC-2/AC-3 parametrization). Test 17.
- **NF-D (clean).** Module location `_shared/` consistent with ADR-0006 posture ("schema-paired-with-consumer; consumer imports without pulling registry"). Pure-data discipline consistent with `codegenie/indices/freshness.py` precedent. ✓
- **NF-E (clean).** `Finding` placeholder with `metadata: dict[str, JSONValue]` consumes Phase 1's existing `JSONValue` (verified at `src/codegenie/parsers/__init__.py:34`) — no duplication. ✓
- **NF-F (clean).** Story does not edit `Probe` ABC / `ProbeContext` — Phase 2 contract-freeze invariant honored. ✓
- **NF-G (clean).** No `model_construct` in prescribed code; aligns with `phase-arch-design.md §"Anti-patterns avoided"`. ✓

### Design-Patterns critic (verdict: DESIGN-HARDEN — 2 patterns surfaced, 0 mandated)

The story IS the canonical 2nd consumer of **Sum type + Make-illegal-states-unrepresentable + schema-paired-with-consumer**. Patterns are largely correct as written. Two improvements surface in `Notes for implementer`; no new AC mandates a pattern name:

- **DF-1 (harden).** Variant-set extension is deliberately NON-Open/Closed (mirrors S1-01 / ADR-0006). The proliferation of `@register_*` decorators in Phase 2 must NOT be misread as license to make these unions pluggable. **Fix:** explicit `Notes for implementer` paragraph naming the discipline + the ADR-amendment trigger.
- **DF-2 (harden).** Smart constructor at the cap boundary (`stderr_tail`). Surface pattern name in `Notes for implementer`; mandate `STDERR_TAIL_CAP_BYTES: Final[int] = 4096` module constant (per CF8 — observable AC, not pattern name).
- **DF-3 (clean).** Composition over inheritance: every variant inherits only `BaseModel`. ✓
- **DF-4 (clean).** Functional core / imperative shell: both modules are pure data; no I/O, no logger. ✓
- **DF-5 (harden, deferred).** `scenario_name: str` newtype opportunity crosses ≥ 2 boundaries; S1-05 is the canonical newtype story. **Fix:** `Notes for implementer` paragraph naming the deferral — Rule 2 / Rule 3 protect against scope creep here.
- **DF-6 (clean).** Premature pluggability avoided: no registry over variant set; no factory; no `NullScannerOutcome`. ✓
- **DF-7 (harden).** Producer/consumer `assert_never` ladder discipline (mirrors `IndexFreshness` ↔ `confidence_section.py`). **Fix:** module docstring (TDD plan Refactor §2) names all 5 consumers + the discipline.

No `block`-tier design findings. No `NEEDS RESEARCH` findings.

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings. Every gap is answerable from:

- `02-ADR-0006` (sum-type discipline + ADR-amendment-gating);
- `_validation/S1-01-index-freshness-sum-type.md` (HARDENED precedent — verbatim template);
- `src/codegenie/indices/freshness.py` (existing implementation pattern);
- `src/codegenie/parsers/__init__.py:34` (existing `JSONValue` alias);
- `pyproject.toml` line 141 (verified repo-wide `warn_unreachable`);
- `scripts/check_forbidden_patterns.py` (verified `_is_under_phase2_banned_package` set);
- `_validation/S1-11-forbidden-patterns-mypy-adrs.md` (verified "honored-broader-than-arch" mypy framing).

## Stage 4 — Synthesizer resolution

### Conflict resolution

No critic-vs-critic conflicts. Reinforcement crosswalk:

| Coverage | Test-Quality | Consistency | Design-Patterns |
|---|---|---|---|
| CF1 | mutation #3 | — | — |
| CF2 | mutation #4 | — | — |
| CF3 | mutation #6 | — | — |
| CF4 | — | — | precedent symmetry (S1-01) |
| CF5 | — | — | — |
| CF6 | TF-C parametrization | — | DF-7 ladder |
| CF7 | mutation #10 | NF-E (JSONValue source) | — |
| CF8 | TF-B boundary | — | DF-2 smart-constructor constant |
| — | mutation #5 | NF-C (script extension required) | — |
| — | — | NF-B (mypy redundancy) | — |
| — | — | NF-A (arch drift) | DF-7 (producer/consumer note) |

All findings hardened in place; no Consistency veto needed (NF-B is a `block` reclassified to `harden` because the AC was redundant, not contradictory).

### Edits applied to the story

| Section | Before | After |
|---|---|---|
| Status | `Ready` | `Ready (hardened by phase-story-validator 2026-05-16)` |
| New `Validation notes` block | absent | 12-point summary of structural changes + report link |
| AC-5 | "round-trip identity, parametrized" — top-level type only | + "MUST additionally preserve nested discriminated-union types: `type(decoded.reason) is type(instance.reason)` AND element-type lists for `ScannerRan.findings`" + explanation of the discriminator-wrapper regression it guards against |
| AC-10 | Per-module `mypy --warn-unreachable` overrides for two new modules | Rewritten — asserts repo-wide `warn_unreachable = true` is present and unmodified; no per-module override added; documents S1-11's "honored-broader-than-arch" framing |
| AC-11 | Hedged "if not already covered" | Rewritten — hedge dropped; explicitly requires `scripts/check_forbidden_patterns.py` extension + parametrized 8-positive + 2+ negative test; `applies_when` discipline (path-scoped predicate inside script, NOT in `.pre-commit-config.yaml`) per S1-11 AC-1 |
| AC-12 (new) | — | Discriminator strings exactly pinned per `phase-arch-design.md §"Component design"` #5/#6 |
| AC-13 (new) | — | JSON-shape pin: literal `model_dump(mode="json")` snapshot for one ScannerOutcome + one ScenarioResult variant |
| AC-14 (new) | — | Unknown-discriminator rejection for all four unions |
| AC-6a (new) | — | Exhaustive `match` over inner `TraceFailureReason` + `TraceSkipReason` with `assert_never` |
| AC-15 (new) | — | Hypothesis property test under `tests/property/test_sum_types_roundtrip.py` |
| AC-16 (new) | — | `Finding.metadata` JSONValue round-trip |
| AC-17 (new) | — | Frozen + extra=forbid mutation-resistance, parametrized over every variant |
| AC-18 (new) | — | Literal `__all__` pin per module |
| AC stderr-tail-cap-constant (new) | — | `STDERR_TAIL_CAP_BYTES: Final[int] = 4096` module constant |
| AC stderr-tail-boundary (new) | — | Off-by-one boundary triple {0,1,4095,4096,4097,8192} → {0,1,4095,4096,4096,4096} |
| AC scanner-skipped-closure (new) | — | Parametrized successes + failures for `ScannerSkipped.reason` Literal |
| AC finding-severity-closure (new) | — | Parametrized successes + failures for `Finding.severity` Literal |
| AC source-scan (new) | — | Source-scan over module bytes for `model_construct` substring |
| TDD plan — red tests | 8 tests | 19 tests + 1 property test file; added: nested-type roundtrip parametrization, inner-union exhaustive matches, discriminator-string pinning, JSON-shape pin, unknown-discriminator rejection, frozen/extra-forbid mutation resistance, `__all__` pin, Finding.metadata JSONValue roundtrip, source-scan, forbidden-patterns extension test, mypy repo-wide test, Hypothesis property test |
| Implementation outline | 10 steps | (unchanged in step count) + Refactor §4 added: `STDERR_TAIL_CAP_BYTES` module constant |
| Files to touch | 4 new files + 2 new tests + 2 "possibly extend" | 4 new modules + 6 new test files (incl. property + __init__) + 2 required extends (script + S1-11 test) + 1 NO-EDIT note (pyproject.toml mypy) |
| Notes for implementer | 6 paragraphs | + 5 paragraphs: 2nd canonical sum-type story (precedent template); variant-set extension is ADR-amendment-gated; producer/consumer `assert_never` ladder; arch-doc drift acknowledgement; smart-constructor module constant; `scenario_name` newtype deferral to S1-05 |

### Mutation-resistance crosswalk after edits

| # | Wrong implementation | Caught by hardened TDD? |
|---|---|---|
| 1 | Drop `frozen=True` | **Yes** — `test_models_are_frozen_and_forbid_extra` |
| 2 | Drop `extra="forbid"` | **Yes** — same test |
| 3 | Drop `Field(discriminator="kind")` from inner `TraceFailureReason` | **Yes** — parametrized roundtrip asserts `type(decoded.reason) is type(instance.reason)`; property test confirms over Hypothesis-generated inputs |
| 4 | Symmetric swap of two `kind` strings | **Yes** — `test_discriminator_strings_are_exactly_pinned` |
| 5 | Use `model_construct` inside new modules | **Yes** — `test_modules_have_no_model_construct` source-scan + extended `forbidden-patterns` script + parametrized 8-positive test |
| 6 | Symmetric rename `kind → tag` | **Yes** — `test_json_shape_pinned` asserts literal JSON containing `"kind"` |
| 7 | Add 5th variant without extending `Annotated[Union[...]]` alias | Yes at mypy time once S5-02/S5-04 consumers land; accepted runtime-side today |
| 8 | Raise stderr_tail cap silently | **Yes** — boundary parametrization + `STDERR_TAIL_CAP_BYTES` constant test |
| 9 | `ScannerSkipped.reason: str` instead of Literal | **Yes** — closure test on `{"", "ad_hoc", "TOOL_MISSING"}` |
| 10 | `Finding.metadata: dict[str, Any]` regression | **Yes** — `test_finding_metadata_jsonvalue_roundtrip` exercises deep nested payload + Hypothesis property test bounds depth |
| 11 | `Finding.severity: str` instead of Literal | **Yes** — closure test on `{"unknown", "INFO", ""}` |
| 12 | Drop `kind` default value | **Yes** — fixtures construct without `kind=` |
| 13 (new) | Add a hypothetical 4th top-level `ScannerOutcome` variant without extending consumer match | Yes at mypy-time once consumers exist; `test_unknown_discriminator_is_rejected` documents runtime side |
| 14 (new) | Drop `__all__` entry for a variant | **Yes** — `test_all_exports_are_pinned` |

### Design-pattern crosswalk after edits

| Concern | Pattern applied | Where documented |
|---|---|---|
| Make illegal states unrepresentable | Pydantic discriminated union; `Literal["..."]` on every variant; `extra="forbid"` + `frozen=True`; closure tests on Literal fields | AC-3, AC-12, AC-13, AC-14, AC-17; phase-arch-design §"Data model" |
| Sum type for state | `ScannerOutcome`, `ScenarioResult`, `TraceFailureReason`, `TraceSkipReason` | Goal; AC-3, AC-4 |
| Smart constructor | Pydantic ctor + `Literal["..."]` default + `extra="forbid"`; `field_validator` for `stderr_tail` cap; module constant `STDERR_TAIL_CAP_BYTES` | AC-3, AC-9, AC stderr-tail-cap-constant; Notes (DF-2) |
| Schema paired with consumer | Consumers = S5-02 / S5-04 / S6-06 / S6-07 / S6-08; module docstring names them; story does NOT ship them | Context; Out of scope; Notes (DF-7); Refactor §2 |
| Open/Closed (consumer-side) | New consumer → import (zero edits) | Goal; Out of scope |
| Variant-set stability (intentional NON-Open/Closed) | ADR-amendment-gated; `assert_never` enforcement on every consumer match | Notes (DF-1); AC-6, AC-6a, AC-14 |
| Producer/consumer `assert_never` ladder | This module is producer; consumers match exhaustively; mypy --warn-unreachable enforces | Notes (DF-7); Refactor §2 |
| Functional core / imperative shell | Modules are pure data; no I/O, no logger, no decorator | Implementation outline; Notes |
| Composition over inheritance | All variants inherit only `BaseModel`; no shared marker | Implementation outline |
| Avoid primitive obsession | Closed sets typed via `Literal[...]`; `scenario_name: str` deferred to S1-05 newtype scope (DF-5) | Notes (DF-5) |
| Premature pluggability avoided | No registry over variant set; no factory; no Null variants | Notes (DF-1); phase-arch-design §"Anti-patterns avoided" |

## Verdict

**HARDENED.** Story now satisfies the validator's "STRONG" bar:

- Every AC is individually verifiable (binary pass/fail).
- AC set collectively guarantees the goal — round-trip identity is end-to-end-typed (top-level AND nested); discriminator strings pinned at both Python and JSON layers; exhaustive `match` rehearsed at every level of the sum; smart-constructor cap exposed as a module constant; `__all__` literally pinned; Hypothesis property test exhausts the input space.
- Every AC has at least one mutation-resistant test in the TDD plan.
- No tautologies, no "no exception thrown" checks, no qualitative-only assertions.
- No contradictions with arch / 02-ADR-0006 / production design / CLAUDE.md commitments. Two consistency corrections applied (mypy override redundancy; forbidden-patterns extension required, not hedged).
- Edge cases covered: unknown discriminator at every level; frozen mutation; extra-field rejection; off-by-one stderr_tail boundary; Literal closure for `reason` / `severity`; recursive JSONValue payload; source-scan for `model_construct`; literal `__all__`; cross-doc discriminator string contract.
- Implementation consumes existing kernels (Pydantic, stdlib, `typing.assert_never`, `JSONValue` from `codegenie.parsers`); introduces no premature abstraction; leaves variant-set extension deliberately ADR-amendment-gated and documents this discipline as a Notes paragraph so the executor doesn't misread the prevalence of `@register_*` patterns in Phase 2 as license to make these unions pluggable.
- Domain identifiers typed (`Literal["..."]` discriminators; `Literal[...]` closed-set fields; sum-of-sums for nested reasons); illegal combinations unrepresentable.

Ready for `phase-story-executor`.
