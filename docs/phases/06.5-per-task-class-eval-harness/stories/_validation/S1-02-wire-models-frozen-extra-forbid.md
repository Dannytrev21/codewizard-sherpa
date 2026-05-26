# Validation report: S1-02 — Wire models with frozen + extra=forbid

**Validated:** 2026-05-26
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S1-02 plants `src/codegenie/eval/models.py` — five frozen Pydantic v2 wire types that the entire rest of Phase 6.5 (and Phases 11/13/16 downstream) reads and writes. The story is well-referenced (every field shape traces to `phase-arch-design.md §Data model`, every constraint cites a phase ADR), the goal is small and singular, and the "no validators except `case_digest`" doctrine correctly defers structural defense to the runner per ADR-0008 / ADR-0004. But the TDD plan as written tests only a *sampling* of the discipline, and several load-bearing structural invariants live in prose or in the Notes for implementer rather than in ACs.

Five categories of weakness slipped past the writer:

1. **`frozen=True, extra="forbid"` is verified for two of five wire types.** The parameterized red test `test_every_wire_type_is_frozen_and_forbids_extra` enumerates `[FailureMode, BenchScore]` only. AC-2 says "Every wire type" — a regression dropping `frozen=True` from `BenchCase`, `BenchRunReport`, or `PromotionVerdict` would silently pass. The right shape is structural walk over `inspect.getmembers(models, inspect.isclass)` filtered to `BaseModel` subclasses, mirroring the precedent in `tests/unit/workflows/test_vuln_ledger_shape.py:65` and the Phase 5 ADR-0014 `test_objective_signals_static.py` discipline this story explicitly cites in its References block. Hardened AC-2 to require introspective coverage + introduced a module-level `_FROZEN_WIRE_TYPES: Final[frozenset[type[BaseModel]]]` catalog so new wire types in future stories are extension-by-addition (one new class — no test edit).

2. **Bounded-field constraints (the load-bearing structural defense for ADR-0002) are tested for `BenchScore.score` only.** AC-6 names `Field(ge=0.0, le=1.0)` on `lower_bound_95` and `mean_score`, `Field(ge=0.0)` on `score_stddev`/`total_cost_usd`, and `Field(ge=0)` on `passed_count` — but the TDD plan has zero tests covering them. A regression dropping the constraint from `lower_bound_95` *cannot be detected* by the current suite, even though ADR-0002 makes this the *only* statistic the promotion gate consumes. Added AC-6a (BenchRunReport bound coverage) + AC-3a (boundary inclusivity — `0.0` and `1.0` must accept; a regression to `gt`/`lt` would otherwise slip).

3. **Literal-typed Pydantic fields are tested by example, not by introspection — symmetric-widening regressions slip.** `test_failure_mode_severity_literal_is_exactly_three_values_adr_0004` asserts `"block"/"warn"/"info"` accept and `"fatal"` rejects. A regression `Literal["block","warn","info","trace"]` would pass (all three accepted values still work). Same shape on `isolation_class`: the test asserts default + that `"firecracker"` rejects, but does NOT positively pin `"microvm"` as the second member. And the BenchCase Literal fields (`disposition`, `difficulty`, `source`, `curation_class`) are untested entirely — a lazy impl with raw `str` would pass every test. Tightened AC-4 (severity), AC-5 (isolation_class), and added AC-12 (BenchCase Literal exactness) — every Literal now pinned via `typing.get_args(model.model_fields[name].annotation) == expected_set` introspection, matching the codebase precedent in `tests/unit/probes/layer_c/test_runtime_trace.py:211` and `tests/unit/probes/test_registry_heaviness.py:256`.

4. **Three load-bearing structural invariants live only in `Notes for implementer`.**
   (a) `PromotionVerdict.requires_human_approval: Literal[True]` is documented as "no default; force every constructor to write it explicitly" — but no AC pins this, and no test exists. A regression giving it a default of `True` silently undoes the structural-marker discipline. Added AC-7a + matching tests (omission raises; `=False` raises).
   (b) `per_case: tuple[tuple[str, BenchScore], ...]` is documented as deliberately tuple-not-list ("Pydantic v2 with `frozen=True` will still permit mutation of inner `list` fields; using `tuple` closes that hole") — no AC, no test. A regression to `list[tuple[str, BenchScore]]` would pass every test but allow `report.per_case.append(...)`. Added AC-11 + introspection test pinning the annotation.
   (c) Tier fields' `str`-not-`Literal` discipline (ADR-0003) is tested only by assignment (`target_tier="emerald"`) — a regression to `Literal["bronze","silver","gold","platinum","emerald"]` would still pass. Added AC-13 — annotation introspection pins `is str`.

5. **AC enumeration omits two `Field`-constrained attributes on `BenchRunReport`.** Arch line 791-792 specifies `passed_count: int = Field(ge=0)` and `total_cost_usd: float = Field(ge=0.0)`. The story's AC-6 enumerated `lower_bound_95`, `mean_score`, `score_stddev`, and `block_severity_failure_modes` but skipped these two. Rolled into AC-6a. `FailureMode.detail: str | None = None` default was similarly unpinned — added AC-4a.

Sixth, smaller: the `case_digest` validator test has only two negative cases (wrong prefix + 63 hex). Uppercase hex, length+1, prefix-only, and missing prefix are the obvious mutation slips. Hardened AC-9 to enumerate negatives + added a hypothesis property test guarding "any string not matching the regex must reject" — the regex is small enough that hypothesis can cover the negative space exhaustively in seconds (cf. project precedent — hypothesis is in `pyproject.toml` `dev` deps and used by `test_freshness.py` siblings).

Design-pattern review: the story correctly avoids a `FrozenStrict(BaseModel)` base class — `Rule 11` (match codebase conventions) makes the per-class `model_config = ConfigDict(frozen=True, extra="forbid")` line the established style (`indices/freshness.py:44, 55, 67, 78, 95, 105`; `probes/layer_g/ripgrep_curated.py:52, 60`; many more). Rule-of-three (one new module declaring this pattern in this phase) has not been crossed. NOT a finding to act on, but a Notes-for-implementer paragraph captures the convention rationale + the trigger condition for a future kernel-extract. Similarly, `complete: bool` is sum-type-ready but YAGNI — flagged as `Notes for implementer` for the Phase 16 widening trigger (a third state like `"crashed"` or `"superseded"`), not promoted to a Literal today.

Consistency review: all referenced ADRs (0002, 0003, 0004, 0008, 0010) and Phase 5 ADR-0014 exist; arch sections cited are present. One info-level observation: the story's Refactor step says "Module docstring cites `../phase-arch-design.md §Data model` and the four phase ADRs honored" — but the ADRs honored are *five* (0002, 0003, 0004, 0008, 0010 — the story header is correct), and Phase 5 ADR-0014 is the discipline this entire story mirrors. Tightened the Refactor instructions to enumerate all six in the docstring + cite the precedent.

Verdict: **HARDENED**. Three blocks (F-COV-1/F-TQ-1/F-DP-2 converged; F-COV-2; F-TQ-2). Eight hardens. Three nits. No `NEEDS RESEARCH` — every pattern is precedented in `tests/unit/workflows/test_vuln_ledger_shape.py`, `tests/unit/probes/test_registry_heaviness.py`, and Phase 5 `test_objective_signals_static.py`.

## Findings by critic

### Coverage critic

#### F-COV-1: `frozen=True, extra="forbid"` is tested for 2 of 5 wire types only
- **Severity:** block
- **Type:** thin AC + missing test
- **Where:** AC-2; TDD test `test_every_wire_type_is_frozen_and_forbids_extra`
- **Why it matters:** AC-2 reads "Every wire type" but the test loops only `[FailureMode, BenchScore]`. A future PR that drops `frozen=True` from `BenchCase`, `BenchRunReport`, or `PromotionVerdict` silently passes. Phase 5 ADR-0014 (referenced by this story) is the precedent — it walks the *whole* type tree, not a hand-rolled list. The codebase has the matching shape in `tests/unit/workflows/test_vuln_ledger_shape.py:65`.
- **Proposed fix:** Rewrite AC-2 to require structural verification: every `BaseModel` subclass declared in `codegenie.eval.models` has `model_config["frozen"] is True` and `model_config["extra"] == "forbid"`. The red test uses `inspect.getmembers(models, inspect.isclass)` filtered to `BaseModel` subclasses (and `obj.__module__ == models.__name__` to exclude transitive imports). Publish the collected set as a module-level `_FROZEN_WIRE_TYPES: Final[frozenset[type[BaseModel]]]` for downstream tests (S1-05's substring-ban test, future per-task-class tests).
- **Resolution:** Applied — AC-2 rewritten; test renamed to `test_every_wire_type_in_models_module_is_frozen_and_forbids_extra`; `_FROZEN_WIRE_TYPES` catalog promoted to module-scope `Final[frozenset[...]]`.

#### F-COV-2: BenchRunReport's `Field(ge=...)`-constrained attributes are tested for 0 of 5 attributes
- **Severity:** block
- **Type:** missing AC + missing tests
- **Where:** AC-6; TDD plan has no Test covering BenchRunReport bounds
- **Why it matters:** AC-6 enumerates `lower_bound_95` and `mean_score` constraints (and the `block_severity_failure_modes` shape) but no test enforces them. Arch lines 788-793 specify five bounded fields: `mean_score ∈ [0,1]`, `score_stddev ≥ 0`, `lower_bound_95 ∈ [0,1]`, `passed_count ≥ 0`, `total_cost_usd ≥ 0`. A regression dropping the `Field(...)` constraint from any of these silently passes. ADR-0002 makes `lower_bound_95` the load-bearing input to the promotion gate; an unbounded `lower_bound_95` of `2.5` would pass to `evaluate(...)` and produce wrong verdicts.
- **Proposed fix:** Add AC-6a enumerating each bounded BenchRunReport attribute; add tests `test_bench_run_report_lower_bound_95_bounded`, `test_bench_run_report_mean_score_bounded`, `test_bench_run_report_score_stddev_nonneg`, `test_bench_run_report_passed_count_nonneg`, `test_bench_run_report_total_cost_usd_nonneg`. Each test verifies both directions (above-bound rejects, below-bound rejects) and inclusive boundary (`0.0`/`1.0` accept where applicable).
- **Resolution:** Applied — AC-6a added; five red tests added.

#### F-COV-3: `FailureMode.detail` default is unpinned
- **Severity:** harden
- **Type:** missing AC
- **Where:** AC list (no entry); ADR-0004 specifies `detail: str | None = None`
- **Why it matters:** Without an AC pinning the default, a regression to `detail: str` (required) breaks every consumer's construction call (e.g., `_ok_failure_mode` in the red tests). The default is part of the wire contract — ADR-0004 names it explicitly.
- **Proposed fix:** Add AC-4a: `FailureMode.detail: str | None = None` — the default permits omission; introspect via `FailureMode.model_fields["detail"].default is None` and `is_required() is False`.
- **Resolution:** Applied — AC-4a + matching test.

#### F-COV-4: `PromotionVerdict.requires_human_approval` no-default discipline lives only in Notes
- **Severity:** harden (load-bearing prose)
- **Type:** missing AC for stated invariant
- **Where:** Notes for implementer; AC list (missing)
- **Why it matters:** Notes say "Do not give it a default; force every constructor to write `requires_human_approval=True` explicitly." This is a structural marker — the gate-is-always-advisory contract per ADR-0009 / phase-arch §Components → promotion.py. A regression giving it `= True` default silently makes every construction site valid without the explicit acknowledgement; the structural marker becomes invisible. "Load-bearing prose" is not a contract (Phase 0 S2-01 / S1-01 precedent).
- **Proposed fix:** Add AC-7a: `PromotionVerdict.requires_human_approval` is required (no default); omission raises; passing `False` raises. Test introspects `model_fields["requires_human_approval"].is_required() is True` AND constructs without the field (expect `ValidationError`) AND constructs with `=False` (expect `ValidationError`).
- **Resolution:** Applied — AC-7a + matching test.

#### F-COV-5: BenchCase Literal-typed fields are untested
- **Severity:** harden
- **Type:** missing AC + missing tests
- **Where:** AC list (no entry); arch lines 762-765 specify four Literal fields
- **Why it matters:** `disposition: Literal["positive", "negative", "ambiguous"]`, `difficulty: Literal["easy", "medium", "hard"]`, `source: Literal["curated", "outcome-ledger-derived", "regression-converted"]`, `curation_class: Literal["rag-corpus-derived", "held-out"]`. A regression to raw `str` for any of them passes every test, but quietly accepts `disposition="invalid"` — the loader (S2-02) is the next defense, but per the "model is permissive, runner is strict" doctrine, the *taxonomy* (Literal closure) is the model's responsibility; only *cross-field rules* (e.g., `commit_sha` conditional) are loader-side.
- **Proposed fix:** Add AC-12 pinning each Literal's exact value set via `typing.get_args(BenchCase.model_fields[name].annotation)`. Tests: each Literal's accept-set works; one rejection per field; introspection pin.
- **Resolution:** Applied — AC-12 + four parameterized tests.

#### F-COV-6: `per_case` tuple-not-list discipline lives only in Notes
- **Severity:** harden
- **Type:** missing AC for load-bearing invariant
- **Where:** Notes for implementer (last paragraph); AC list (missing)
- **Why it matters:** Notes correctly identify the hole: "Pydantic v2 with `frozen=True` will still permit mutation of inner `list` fields; using `tuple` closes that hole." A regression `per_case: list[tuple[str, BenchScore]]` (innocuous-looking refactor) defeats the entire frozen contract — `report.per_case.append(...)` silently works. The annotation type IS the contract.
- **Proposed fix:** Add AC-11 — `BenchRunReport.per_case` annotation is `tuple[tuple[str, BenchScore], ...]` and `BenchScore.failure_modes` is `tuple[FailureMode, ...]` (same hole). Test introspects field annotations against `typing.get_origin(...) is tuple` and `typing.get_args(...)` matching expected.
- **Resolution:** Applied — AC-11 + test.

#### F-COV-7: BenchCase `cassette_canary_pin` format is unpinned at the model boundary
- **Severity:** nit
- **Type:** scope-deferral surface
- **Where:** AC list / Out-of-scope
- **Why it matters:** Arch line 772: `cassette_canary_pin: str  # 32 hex; pinned per case`. The model types it `str`. A typed validator (parallel to `case_digest`'s blake3 regex) would close the smuggling hole structurally. The story's "one validator only" doctrine defers this — but it should be *explicitly* deferred (to S2-02 or S5-07 cassette-seed-shim) in Out-of-scope.
- **Proposed fix:** Add to Out-of-scope a bullet naming the deferral target. The model carries `cassette_canary_pin: str` (required, no default); the format validator lives in the loader / cassette adapter.
- **Resolution:** Applied — Out-of-scope last bullet added.

### Test-Quality critic

#### F-TQ-1: `test_every_wire_type_is_frozen_and_forbids_extra` parameterization gap (dup with F-COV-1 / F-DP-2)
- **Severity:** block
- **Type:** thin test
- **Mutation that slips:** drop `frozen=True` from `BenchCase`; current test loops only `FailureMode` and `BenchScore`. Test passes; immutability claim silently violated.
- **Proposed fix:** Walk `inspect.getmembers(models, inspect.isclass)` filtered to `issubclass(BaseModel) and obj.__module__ == models.__name__`. Assert `model_config["frozen"] is True` and `model_config["extra"] == "forbid"` for every member. Publish the catalog as `_FROZEN_WIRE_TYPES: Final[frozenset[type[BaseModel]]]` so a later story can reuse.
- **Resolution:** Applied (merged with F-COV-1).

#### F-TQ-2: `test_bench_run_report_isolation_class_defaults_subprocess_adr_0010` doesn't pin the exact two-value Literal
- **Severity:** harden
- **Type:** asymmetric test
- **Mutation that slips:** `Literal["subprocess"]` (one value); test still passes (default works, `"firecracker"` still rejects). The arch invariant "exactly two values" silently lost.
- **Proposed fix:** Positively assert `_make_report(isolation_class="microvm").isolation_class == "microvm"` (the other accepted value). Additionally, introspect: `typing.get_args(BenchRunReport.model_fields["isolation_class"].annotation) == ("subprocess", "microvm")` — pins the set exactly.
- **Resolution:** Applied — test extended; introspection added.

#### F-TQ-3: Boundary inclusivity untested on bounded fields
- **Severity:** harden
- **Type:** missing edge-case test
- **Mutation that slips:** `Field(gt=0.0, lt=1.0)` (strict bounds); existing test only asserts `1.5` and `-0.01` fail; both still fail under strict, so test passes. But a rubric emitting a perfect score `1.0` is now rejected.
- **Proposed fix:** Add AC-3a — explicit boundary inclusivity (`score=0.0` accepts; `score=1.0` accepts; `cost_usd=0.0` accepts; `wall_clock_ms=0` accepts). Mirror for BenchRunReport bounded fields in AC-6a.
- **Resolution:** Applied — AC-3a + tests.

#### F-TQ-4: `test_failure_mode_severity_literal_is_exactly_three_values_adr_0004` — exhaustive check via introspection missing
- **Severity:** harden
- **Type:** asymmetric test
- **Mutation that slips:** `Literal["block","warn","info","trace"]`; existing test still passes (all three accepted values work). ADR-0004 §Consequences makes the three-value closure load-bearing.
- **Proposed fix:** Pin via introspection: `typing.get_args(FailureMode.model_fields["severity"].annotation) == ("block", "warn", "info")`.
- **Resolution:** Applied — test extended with introspection assertion.

#### F-TQ-5: `test_promotion_verdict_tier_fields_are_str_not_literal_adr_0003` — only asserts value, not type
- **Severity:** harden
- **Type:** weak test
- **Mutation that slips:** `Literal["bronze","silver","gold","platinum","emerald"]`; existing test (`target_tier="emerald"`) still passes — emerald is in the set. ADR-0003's "tier names are `str`, not `Literal`" silently lost.
- **Proposed fix:** Add AC-13 — `PromotionVerdict.model_fields["current_tier"].annotation is str` and same for `target_tier`. Test introspects the annotation directly (not the value).
- **Resolution:** Applied — AC-13 + introspection test.

#### F-TQ-6: `test_bench_case_digest_must_match_blake3_64_hex` — only two negative cases
- **Severity:** harden
- **Type:** under-mutated negative space
- **Mutation that slips:** `re.fullmatch(r"^blake3:[0-9a-fA-F]{64}$", ...)` (case-insensitive); test passes (lowercase still works) but the contract intent (digest canonicality) is lost. Also slips: 65-char hex, prefix-only, missing prefix, leading/trailing whitespace.
- **Proposed fix:** Enumerate negative cases in AC-9 (uppercase, 65 chars, prefix-only, no prefix, whitespace). Add a hypothesis property test: `@given(st.text())` — any text not matching the regex must reject; any text matching must accept. The regex is small enough for hypothesis to span the negative space in seconds.
- **Resolution:** Applied — AC-9 strengthened; hypothesis test added.

#### F-TQ-7: No test for `complete=False` round-trip
- **Severity:** nit
- **Type:** missing serialization test
- **Mutation that slips:** A defensive `field_serializer` on `complete` that drops `False` values silently. The next story (audit chain extension, S2-04) would emit JSON that omits the field, and Phase 11/13 consumers reading the artifact would see `complete=True` (default) on partial runs. Failure is silent.
- **Proposed fix:** `assert "complete" in BenchRunReport(complete=False, ...).model_dump()`; AND `assert BenchRunReport.model_validate_json(report.model_dump_json()).complete is False`.
- **Resolution:** Applied — round-trip serialization test added.

#### F-TQ-8: No test for module export discipline
- **Severity:** nit
- **Type:** scope-deferral surface
- **Where:** AC-1 / S1-05
- **Why it matters:** AC-1 verifies the five names import. It does NOT verify no *other* names leak (e.g., that the module doesn't accidentally export a helper class or a sixth model). S1-05 owns the `eval/__init__.py` closure — but `models.py`'s own surface is per-story.
- **Proposed fix:** Add a `_FROZEN_WIRE_TYPES` catalog test (same vehicle as F-COV-1) — assert exactly five frozen wire types, by name. New types fail the test loudly and force ADR amendment.
- **Resolution:** Applied via F-COV-1's catalog — `_FROZEN_WIRE_TYPES` cardinality is also asserted.

### Consistency critic

#### F-CON-1: AC-6 enumeration is incomplete (`passed_count`, `total_cost_usd` skipped)
- **Severity:** harden
- **Type:** doc-internal inconsistency
- **Where:** AC-6 vs arch lines 791-792
- **Why it matters:** AC-6 names `lower_bound_95`, `mean_score`, `score_stddev` and `block_severity_failure_modes` — but the arch's wire shape includes `passed_count: int = Field(ge=0)` and `total_cost_usd: float = Field(ge=0.0)` on the same model. Skipping them in the AC list is a documentation contradiction; the implementer is the only defense and the test suite cannot back them up. Resolved by F-COV-2's AC-6a.
- **Resolution:** Applied via AC-6a.

#### F-CON-2: Refactor step undercounts ADRs honored in the module docstring
- **Severity:** nit
- **Where:** Refactor step bullet 1: "Module docstring cites … and the four phase ADRs honored"
- **Why it matters:** Story header lists *five* phase ADRs (0001, 0002, 0003, 0004, 0008, 0010 = six counting Phase 5 ADR-0014) — saying "four" is a stale number, likely from an earlier draft before Gap #1/#4 added ADR-0010 + the Notes-elevated Phase 5 precedent. Implementer following the Refactor step writes a docstring that's a count-of-record short.
- **Proposed fix:** Update Refactor step to "the six honored ADRs (ADR-0002, ADR-0003, ADR-0004, ADR-0008, ADR-0010, Phase 5 ADR-0014)" + cite each by anchor.
- **Resolution:** Applied — Refactor step bullet 1 expanded.

#### F-CON-3: Story references all check out
- **Severity:** info
- **Where:** References block
- **Verdict:** All five phase ADRs (0002, 0003, 0004, 0008, 0010) exist; Phase 5 ADR-0014 exists; production ADR-0008 exists; arch sections cited (§Data model, §Component design → models.py, §Edge cases #10/#12/#15/#21, §Harness engineering — Typed state contracts) all exist. No stale refs.

#### F-CON-4: Out-of-scope correctly defers cross-cutting concerns
- **Severity:** info
- **Where:** Out-of-scope (5 bullets)
- **Verdict:** S1-03 (TaskClass), S1-04 (Rubric), S1-05 (__init__ re-export + substring-ban), S3-04 (runner validation), S2-02 (loader validators) — all correctly deferred. One small addition recommended: explicitly defer `cassette_canary_pin` format validation (F-COV-7) and the schema-export-to-disk question (whether eval models get a JSON Schema artifact like `repo_context.schema.json` — Phase 6.5 may not need one but the silence invites a future surprise PR).
- **Resolution:** Applied — Out-of-scope two bullets added.

#### F-CON-5: ADR-0008 typed-at-the-edge alignment confirmed
- **Severity:** info
- **Where:** AC-3 (`breakdown` permissive at the model) + Notes for implementer
- **Verdict:** Aligned. Story correctly says model is permissive; runner is strict (S3-04). Substring-ban defense lives in S1-05 (PR-time AST walk) + S3-04 (runtime). No edit.

#### F-CON-6: CLAUDE.md commitments respected
- **Severity:** info
- **Verdict:** "Facts, not judgments" → preserved (model is structural; the rubric is the judgment). "Extension by addition" → `breakdown_keys` per-task-class, `failure_modes` per-task-class, tier slugs in YAML, `isolation_class` Literal-widenable. "Honest confidence" → `lower_bound_95` (ADR-0002) is the gate input. "Make illegal states unrepresentable" → tagged-union-like discipline (Literal closures). Aligned.

### Design-Patterns critic

#### F-DP-1: Per-class `model_config` line is the codebase convention (Rule 11 — no edit)
- **Severity:** info
- **Verdict:** `indices/freshness.py` declares the same `model_config = ConfigDict(frozen=True, extra="forbid")` line on six classes (lines 44, 55, 67, 78, 95, 105) without extracting a base. Same pattern in `probes/layer_g/ripgrep_curated.py`, `probes/layer_g/test_coverage_mapping.py`, `plugins/vulnerability-remediation--node--npm/config.py`. The convention is per-class config. Rule-of-three (third project location with 5+ models in this exact pattern) is now arguably met if we count `models.py` as the fourth — but extracting a `FrozenStrict(BaseModel)` base now would diverge from the established style without a discussed migration. NOT a finding to act on; add to Notes for implementer as the trigger condition for a future kernel-extract (when a *fifth* such location appears with 5+ wire models, propose a shared base via ADR amendment).
- **Resolution:** Added to Notes for implementer as a deferred-extract opportunity (Rule 2 YAGNI guard).

#### F-DP-2: Structural test over the wire-type catalog (dup with F-COV-1 / F-TQ-1)
- **Severity:** harden
- **Smell:** Implicit registry; Open/Closed at the test boundary
- **What's wrong:** TDD's `test_every_wire_type_is_frozen_and_forbids_extra` enumerates `[FailureMode, BenchScore]`. Adding a new wire type requires editing the test (extension by editing, not addition). The Phase 5 precedent (`test_objective_signals_static.py`) and the codebase precedent (`tests/unit/workflows/test_vuln_ledger_shape.py:65`) walk via `inspect.getmembers`. New wire type ⇒ test passes for free (or fails loudly if it forgets the discipline).
- **Proposed fix:** Walk the module. Publish the collected set as `_FROZEN_WIRE_TYPES: Final[frozenset[type[BaseModel]]]` at test-module scope — extension by addition for downstream tests in S1-05, S3-04, S7-01.
- **Resolution:** Applied (merged with F-COV-1).

#### F-DP-3: `complete: bool` vs `Literal["complete","partial"]` — YAGNI guard holds (no edit)
- **Severity:** info
- **Verdict:** A boolean models the binary "complete vs not." A third state (e.g., `"crashed"`, `"superseded"`, `"externally-cancelled"`) would force a `Literal` widening + ADR amendment. Rule of three (one new state vs two prior — complete/partial) is not crossed; bool is correct today. Notes for implementer captures the trigger condition.
- **Resolution:** Added to Notes for implementer.

#### F-DP-4: `isolation_class` Literal-widening path is explicit (no edit)
- **Severity:** info
- **Verdict:** ADR-0010 §Reversibility names the path: widening to a third class (gVisor / bare-metal) is a `Literal` edit + ADR amendment + a transition contract. Extension by addition is anticipated. No edit.

#### F-DP-5: `breakdown: dict[str, float]` typed-at-the-edge (no edit)
- **Severity:** info
- **Verdict:** ADR-0008 makes the model intentionally permissive — extension by addition for future task classes. Defense lives elsewhere (S1-05 fence + S3-04 runner). Notes for implementer already cite this. No edit.

#### F-DP-6: `BenchScore` shape — `passed: bool + score + failure_modes` vs sum-type (no edit)
- **Severity:** info
- **Verdict:** `BenchScore(passed=False, score=0.97, failure_modes=())` is allowed per arch §Edge case #10 ("the rubric chooses"). A pure `Passed | Failed` tagged union would forbid this combination but contradicts ADR-0004's rubric-autonomy doctrine. The bool+score+failures shape is correct; making `passed` derived from `failure_modes` would couple the rubric's judgment to the runner's taxonomy — the wrong direction.

#### F-DP-7: Functional core / imperative shell — models are pure data (no edit)
- **Severity:** info
- **Verdict:** No I/O, no side effects. The one `field_validator` on `case_digest` is a pure regex check. Correct shape.

#### F-DP-8: Make illegal states unrepresentable — `requires_human_approval: Literal[True]` (already-correct + needs AC)
- **Severity:** harden (dup with F-COV-4)
- **Smell:** Structural marker as type-system contract
- **Verdict:** The Literal[True] discipline IS the right pattern. The validator's job here: pin the *no-default* aspect via AC + test so a future "tidy-up" PR adding `= True` default doesn't silently make the structural marker invisible.
- **Resolution:** Applied via F-COV-4.

#### F-DP-9: Tuple-vs-list as immutability-honouring shape (dup with F-COV-6)
- **Severity:** harden
- **Smell:** Hidden-mutability hole
- **Verdict:** Right pattern, missing AC. Resolved via F-COV-6.

## Conflict resolution

| Conflict | Resolution |
|---|---|
| Coverage F-COV-1 + Test-Quality F-TQ-1 + Design-Patterns F-DP-2 all propose the same structural-walk fix. | Merged into single AC-2 hardening + single test + single catalog. Design-Patterns framing (Open/Closed at the test boundary) cited in the validation report; the AC itself reads as an observable contract ("every BaseModel subclass declared in `models` has frozen+extra=forbid"), not a pattern name. |
| Design-Patterns F-DP-1 (extract `FrozenStrict` base) vs Rule 11 + Rule 2 (match codebase convention; YAGNI) | Rule 2 / Consistency wins. Don't introduce a shared base — codebase precedent is per-class config (`indices/freshness.py` + others). Surface the trigger-for-future-extract in Notes for implementer only. |
| Design-Patterns F-DP-3 (Literal for `complete`) vs Rule 2 (YAGNI) | Rule 2 wins. Bool is fine for binary today. Notes for implementer documents the widening trigger. |
| No critic-to-critic conflicts otherwise. | — |

## Edits applied

Story file edited in place. New `Validation notes` block under the story header. ACs renumbered: was 10 unnumbered checkbox items; now 16 explicit AC-N entries (AC-1 through AC-13 + AC-3a/AC-4a/AC-6a/AC-7a inserted in-line to keep semantic grouping). Implementation outline, TDD plan, Out-of-scope, Notes for implementer, Refactor all touched in line with the new ACs.

Pre/post diff summary:

| Section | Before | After |
|---|---|---|
| Status | `Ready` | `HARDENED` |
| ACs | 10 unnumbered checkboxes | 16 numbered (AC-1..AC-13 + AC-3a/AC-4a/AC-6a/AC-7a) |
| TDD plan red tests | 8 tests | 14 tests (added: structural walk, severity introspection, isolation introspection + microvm positive, tier-annotation introspection, BenchCase Literal exactness, per_case tuple introspection, BenchRunReport bounded coverage × 5, FailureMode default-None, requires_human_approval no-default, case_digest hypothesis property, complete round-trip serialization, _FROZEN_WIRE_TYPES cardinality) |
| Out-of-scope items | 6 bullets | 8 bullets (added: `cassette_canary_pin` format validator deferral; JSON Schema artifact deferral) |
| Notes for implementer | 6 bullets | 9 bullets (added: structural-walk-test discipline + `_FROZEN_WIRE_TYPES` catalog rationale; per-class `model_config` Rule 11 convention + future-extract trigger; `complete` bool ↔ Literal widening trigger) |
| Refactor step bullets | 4 | 4 (bullet 1 expanded: cite all 6 honored ADRs + Phase 5 ADR-0014 precedent) |

## Verdict rationale

**HARDENED.** Three blocks (F-COV-1 / F-TQ-1 / F-DP-2 converged; F-COV-2; F-TQ-2 — all in-place-fixable with precedented patterns). Eight hardens. Three nits. No `NEEDS RESEARCH` — every introspection pattern is precedented in this repo (`tests/unit/workflows/test_vuln_ledger_shape.py:65`; `tests/unit/probes/test_registry_heaviness.py:256`; `tests/unit/probes/layer_c/test_runtime_trace.py:211`) and the Phase 5 `test_objective_signals_static.py` reference cited by the story itself. The mutation set the hardened test suite resists: dropping `frozen=True` from any of the five types; dropping `Field(...)` constraints from any of the five BenchRunReport bounded fields; widening the severity / isolation_class / BenchCase Literals symmetrically; widening tier fields to a Literal (defeating ADR-0003 extension-by-addition); changing `per_case` from tuple to list (defeating frozen immutability); giving `requires_human_approval` a default (defeating the structural-marker discipline); accepting uppercase / wrong-length / no-prefix hex in `case_digest` (defeating canonicality); silently elide `complete` from JSON dumps.

Design-pattern posture: validator explicitly endorses the per-class `model_config` Rule-11 conformance (no shared base); endorses bool-for-`complete` and dict-for-`breakdown` YAGNI; cites the kernel-extract trigger conditions in Notes for implementer for the next story-writer's reference.

## Recommended next step

`phase-story-executor` to implement. Story is ready: every AC is individually verifiable; the AC set collectively guarantees the goal (five frozen wire types with structural discipline pinned, not merely sampled); every test in the TDD plan would fail under a wrong implementation; no design-pattern anti-pattern is locked in.
