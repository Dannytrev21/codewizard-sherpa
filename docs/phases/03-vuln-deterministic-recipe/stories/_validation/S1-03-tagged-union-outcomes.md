# Validation report — S1-03 Tagged-union outcome types

**Story:** [`../S1-03-tagged-union-outcomes.md`](../S1-03-tagged-union-outcomes.md)
**Validated:** 2026-05-18
**Validator:** phase-story-validator (scheduled task: `story-validation-corrector`)
**Verdict:** **HARDENED**

## Summary

S1-03 lands the five Pydantic discriminated unions (`RecipeOutcome`, `RemediationOutcome`, `NodeTransition`, `AdapterConfidence`, `Applicability`) that every later Phase 3 module (`PluginRegistry`, recipe engines, `RemediationOrchestrator`, `SubgraphNode`, `BundleBuilder`) dispatches on. These are the **Phase-5-wrap surface** that ADR-0001 freezes by name — renames or shape changes after S6-02 lands break the contract-snapshot test. The story carries dense detail and is mostly right; validation found two block-tier consistency issues, several test-quality gaps the executor would not have caught, and a design-patterns opportunity to consolidate reason taxonomies.

- **Two block-tier consistency issues** (story drifts from `phase-arch-design.md §C4 line 530` and `§Data model line 825`):
  - **`RemediationOutcome.Validated` field set diverges from arch:** story (line 36) ships `Validated(transform_id, trust_outcome_passed, failing)`. Arch §Data model line 827 ships `Validated(branch: BranchName, report_path: SandboxedPath, trust_outcome: TrustOutcome)`. The drift forces Phase 5's `GateRunner` and the `remediation-report.yaml` writer to read fields the contract didn't promise — exactly the failure mode ADR-0001's contract-snapshot test exists to prevent. Resolution: keep the flat `passed: bool, failing: list[SignalKind]` denormalization (justified because `TrustOutcome` ships in S6-02, not here — Out of scope §2 line 156) but **add `branch: BranchName` and `report_path: str`** (the latter as a `str` placeholder; S4-01 widens to `SandboxedPath`). Document the S6-02 amendment path in Notes.
  - **`RemediationOutcome.Failed` missing `partial_report_path`** (arch line 830, line 452 "the orchestrator writes a partial `remediation-report.yaml` with `outcome.kind = "failed"` and re-raises"). Resolution: add `partial_report_path: str | None = None` (None when failure occurs before the report path is allocated). Fenced by AC.
- **Two block-tier test-quality gaps** that mirror the freshness-precedent harden-tier closures established by Phase 2 S1-01 / S1-02:
  - **Discriminator strings not pinned exactly.** Round-trip alone is symmetric — `Applied.kind = "failed"` + `Failed.kind = "applied"` swap passes round-trip but breaks every Phase-5 consumer that switches on `kind`. Promoted to AC + a `test_discriminator_strings_are_exactly_pinned` test enumerating all 19 variant strings ({applied, skipped, not_applicable, failed} × 2 unions + {validated, requires_human_review, not_applicable, failed} + {advance, short_circuit, escalate} + {trusted, degraded, unavailable} + {applies, not_applies}).
  - **JSON-shape pinning missing.** A symmetric `kind` → `tag` rename across every variant + every consumer is also round-trip-stable. Promoted to AC + `test_json_shape_pinned` — `Applied(...).model_dump(mode="json")["kind"] == "applied"` per variant.
- **Test-quality harden-tier closures**:
  - **`extra="forbid"` and `frozen=True` parametrized over every variant** (story tests only `NotApplicable` and `Applied`). 17 variants × 2 assertions; a parametrize loop is the natural shape.
  - **Top-level-discriminator rejects bogus `kind`** for each of the five unions (`TypeAdapter(U).validate_python({"kind": "bogus"})` raises `ValidationError`) — story tests reason-literal rejection but not top-level discriminator rejection.
  - **Nested-discriminator preservation on `NodeTransition.ShortCircuit.outcome: RemediationOutcome`** — round-trip on `ShortCircuit(outcome=Validated(...))` must preserve `Validated` (not collapse to `RequiresHumanReview` via discriminator drift). Mirrors the `Stale.reason: StaleReason` nested precedent in `tests/unit/indices/test_freshness.py:46-52`.
  - **`Validated.passed == (failing == [])` invariant** — without a `model_validator(mode="after")` guard, `Validated(passed=True, failing=[SignalKind("tests")])` is constructable: "make illegal states unrepresentable" (ADR-0010 §Pattern fit) is not enforced. The arch's `TrustOutcome.passed` and `TrustOutcome.failing` carry the same invariant implicitly — S6-02 will inherit it. Pin it here.
  - **`NodeTransition.Advance.state` primitives-only rejection** — story Notes §line 167 says "no list[str]" but no AC. `state={"x": [1, 2]}` must raise `ValidationError`. Mutation-resistance test.
- **Test-quality property-based opportunities**:
  - **Every-variant round-trip preserves the concrete type** — `type(decoded) is type(instance)` over a parametrized fixture of all 17 variants (mirrors `test_index_freshness_roundtrip_identity` at `tests/unit/indices/test_freshness.py:40`).
- **Design-patterns / consistency**:
  - **`NotApplicableReason` shared between `RecipeOutcome.NotApplicable` and `RemediationOutcome.NotApplicable`** — Notes line 165 says so but no AC asserts a single source-of-truth Literal alias. Without it, the executor could redefine the literal in two places (drift in Phase 4 when a new reason lands). AC pins identity: `from codegenie.transforms.outcomes import NotApplicableReason` is the *only* import path for both.
  - **`kind: Literal["..."] = "..."` default-value form** — repo convention (`freshness.py:45`, `scanner_outcome.py:117`, `scenario_result.py`) sets the default; story signature `kind: Literal["applied"]` (no default) forces every construction to pass `kind="applied"` redundantly. Pin the default-value form.
  - **`Annotated[A | B | C, Field(discriminator="kind")]`** is the repo's idiomatic discriminator syntax (every existing union: `freshness.py:84,110`; `scanner_outcome.py:130`; `scenario_result.py:105,135,180`; `_cve_models.py:70`). Story line 49 mentions `Discriminator("kind")` — a *different* Pydantic v2 API (callable-discriminator). Pin `Field(discriminator="kind")` for consistency.
  - **`assert_never` enforcement is type-time, not runtime** — story Refactor §line 140 acknowledges this but ships no executable mypy-negative fence. Without it, a future contributor adds a 5th `RecipeOutcome` variant without updating consumer `match` blocks and CI is silent. Promoted to AC + a subprocess-mypy meta-test (`test_exhaustiveness_mypy_negative`) that asserts `mypy --strict` returns non-zero on a fixture with a missing `case` arm + the `assert_never` line. Same shape as Phase 2 S1-05 fence.
  - **`__all__` exact-set pinning** — ADR-0001 §Consequences pins the re-export list. Promoted from "re-export" prose to AC: `set(outcomes.__all__) == EXPECTED_NAMES` (17 variant classes + 5 union aliases + 6 reason aliases + 2 error models = 30 names).
  - **Module-purity / fence** — `outcomes.py` is contract-surface kernel; imports limited to `{__future__, typing, pydantic, codegenie.types.identifiers, codegenie.types.errors}`. Mirrors S1-01 / S1-02 module-purity closure.
- **Out-of-scope clarifications** to prevent executor scope creep:
  - `Skipped` semantics — clarified: a plugin's `pre_applies()` (Phase 4+ surface) explicitly declines to evaluate (vs `NotApplicable` which is `applies()` returning False). Phase 3 may not reach `Skipped` in normal flow; the variant is reserved for Phase 4+ additive extension. Pinned in Notes.
  - `Applied.transform: Transform` (arch line 534) vs story's `Applied.transform_id: TransformId` — justified by build-order (S1-04 ships `Transform` ABC). Notes documents the S1-04 amendment.

Stage 3 research **skipped** — every closure is answerable from arch + ADR-0010 + ADR-0001 + Phase-2 S1-01 (`freshness.py`) precedent + verified repo state.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim):** Land `src/codegenie/transforms/outcomes.py` with five Pydantic discriminated unions (`RecipeOutcome`, `RemediationOutcome`, `NodeTransition`, `AdapterConfidence`, `Applicability`), each `frozen=True` + `extra="forbid"`, with a `Discriminator("kind")` and one exhaustiveness test per union using `match` + `assert_never`.
- **Non-goals (from Out of scope):** `Transform` ABC + `ApplyContext` + `AttemptSummary` (S1-04); `TrustOutcome` + `TrustSignal` (S6-02); `JailedSubprocessResult` (S4-01 `sandbox_jail.py`); `PluginResolution` (S2-04 `resolution.py`); `WorkflowInternalEvent` / `WorkflowSpanningEvent` (S6-01).

### Goal-to-AC trace (pre-hardening)

- AC-1 (package marker) → goal: YES
- AC-2 (five unions, discriminator, frozen, extra=forbid) → goal: YES
- AC-3 (RecipeOutcome variants + `NotApplicableReason` literals) → goal: PARTIAL — `Skipped`'s `SkipReason` taxonomy not enumerated; `Applied.transform: Transform` arch-shape replaced with `transform_id` without explicit justification
- AC-4 (RemediationOutcome variants) → goal: WEAK — **drifts from arch** on `Validated` fields (no `branch`, no `report_path`); `Failed` missing `partial_report_path`
- AC-5 (NodeTransition variants) → goal: YES (Gap 1 fix per arch line 1154 §Gap analysis)
- AC-6 (AdapterConfidence variants) → goal: PARTIAL — `DegradationReason` / `UnavailabilityReason` taxonomies named but literal sets not pinned
- AC-7 (Applicability variants) → goal: PARTIAL — `ApplicationPlan` placeholder shape not pinned
- AC-8 (`test_outcomes.py` covers construct + extra-reject + frozen + JSON round-trip) → goal: PARTIAL — round-trip tested on one variant; not parametrized; discriminator-string rename + JSON-shape rename regressions slip past
- AC-9 (exhaustiveness one test per union) → goal: PARTIAL — example shown only for `RecipeOutcome`; no executable mypy-negative fence
- AC-10 / AC-11 / AC-12 (mypy strict / ruff / TDD red-test) → goal: bar-ACs

### Phase / arch constraints

- **ADR-0010 §Decision §3** — names every union and variant; `extra="forbid"` + `frozen=True` mandatory; `match` + `assert_never` at every dispatch site.
- **ADR-0001 §Consequences** — `RemediationOutcome` and `RecipeOutcome` re-exported from `codegenie.transforms.__init__`; contract-snapshot test (`tests/integration/test_phase5_contract_snapshot.py`, lands in Step 6/9) byte-snapshots the surface — renames break it.
- **ADR-0001 line 40** — public re-export list: `RemediationOrchestrator, TrustScorer, Transform, ApplyContext, RecipeEngine, RemediationOutcome, TrustOutcome`. Plus the variant classes (for `isinstance`/`match` at call sites).
- **`phase-arch-design.md §C4` line 516–538** — `RecipeOutcome` variants pseudo-code; `Applied(transform: Transform, …)`.
- **`phase-arch-design.md §Data model` line 817–830** — load-bearing pseudo-code with `Validated(branch, report_path, trust_outcome)` + `Failed(error, partial_report_path)`.
- **`phase-arch-design.md §C8` line 605** — `AdapterConfidence ∈ {Degraded, Unavailable}` triggers serial fallback.
- **`phase-arch-design.md §Gap analysis Gap 1` line 1154** — `NodeTransition = Advance(state) | ShortCircuit(outcome: RecipeOutcome) | Escalate(reason)`. Note: arch says `ShortCircuit(outcome: RecipeOutcome)` but story line 38 says `ShortCircuit(outcome: RemediationOutcome)`. Investigated: arch §Edge cases line 899–904 shows nodes short-circuit with `RemediationOutcome.Failed/NotApplicable` (the *orchestrator-level* outcome, not the per-recipe outcome). The story's `RemediationOutcome` choice matches the orchestrator-outer-loop wrap target — `RemediationOutcome` is correct. Document the arch-typo in Notes.
- **`phase-arch-design.md §Edge cases E4/E6/E10` line 978–984** — pins `PEER_DEP_CONFLICT`, `MAJOR_BUMP_REFUSE`, `NoConcreteMatch` reason literals.
- **`phase-arch-design.md §Patterns` line 944** — Tagged-union sum types pattern row: `PluginResolution, RecipeOutcome, RemediationOutcome, TrustOutcome, AdapterConfidence, JailedSubprocessResult, Applicability, ScopeDim`.
- **`phase-arch-design.md §line 876`** — "The **discriminator-on-`kind`** pattern is uniform across `RecipeOutcome, RemediationOutcome, PluginResolution, Applicability, JailedSubprocessResult, AdapterConfidence`."
- **`phase-arch-design.md §line 1166`** — `RecipeOutcome.NotApplicable(reason=ALL_RECIPES_NOT_APPLICABLE)` for first-Applies-wins fallthrough (justifies story's addition beyond arch line 1075's 4 reasons).
- **CLAUDE.md "Extension by addition"** — `match` + `assert_never` is the structural enforcement against silent `Union` widening when a new variant lands (Phase 4 `LLMFallback` / Phase 7 `DistrolessMigration`).
- **CLAUDE.md "No LLM anywhere in the gather pipeline" + `import-linter`** — `transforms/` is Phase 3 contract surface; the `fence` test in Step 1 covers `src/codegenie/{plugins,transforms}/`; module-purity invariant applies.

### Phase 3 Step-1 exit criteria the story must contribute to

(from `High-level-impl.md §Step 1 Done criteria` lines 36–42)
- [ ] `Every sum-type module is consumed by at least one match statement with assert_never (verified by tests/unit/transforms/test_exhaustiveness.py).` ← S1-03 ships `test_exhaustiveness.py`.
- [ ] `mypy --strict src/codegenie/plugins src/codegenie/transforms` clean — S1-03 contributes `transforms/outcomes.py`.
- [ ] `tests/fence/test_no_any_in_plugin_surface.py` — S1-03 must not introduce `dict[str, Any]`.

### Sibling-family lineage (Design-Patterns critic)

- **This is the 3rd Pydantic-discriminated-union family** in the repo (after `IndexFreshness` Phase 2 S1-01 → `ScannerOutcome` Phase 2 S5-01 → `ScenarioResult` Phase 2 S5-01 multiple). Rule-of-three ALREADY-REACHED — the convention (`kind: Literal["..."] = "..."`; `Annotated[A | B | C, Field(discriminator="kind")]`; `model_config = ConfigDict(frozen=True, extra="forbid")`; `match` + `assert_never` in consumers) is set.
- **Kernel-extract opportunity?** No: Pydantic discriminated unions are not a kernel that wants extraction — the language already provides the abstraction. The Open/Closed seam for new variants is *additive imports* in `outcomes.py` + a fence test (`test_exhaustiveness_mypy_negative`) that ensures every consumer's `match` covers the new variant. **Promoted to AC.**
- **Closest precedent for *this* story:** `src/codegenie/indices/freshness.py` (Phase 2 S1-01) and its tests `tests/unit/indices/test_freshness.py`. Mirror the patterns exactly:
  - `kind: Literal["..."] = "..."` (default value)
  - `Annotated[Fresh | Stale, Field(discriminator="kind")]`
  - Nested discriminator preservation in round-trip tests
  - `match` + `assert_never` consumer test
  - Discriminator-string pin test
  - JSON-shape pin test
  - Module-purity fence (no `model_construct`)

### Open ambiguities resolved before Stage 2

- **`Discriminator("kind")` vs `Field(discriminator="kind")` API.** Repo convention (5 files) uses `Field(discriminator="kind")`. Pin this form.
- **`SkipReason` literals.** Arch is silent. Resolution: Phase 3 has no `Skipped` producer in normal flow (Phase 4+ adds them). Pin `SkipReason = Literal["plugin_disabled", "registry_skipped"]` as a minimal extensible set; Phase 4 adds additively.
- **`EscalationReason` literals.** Arch is silent; story names the alias. Resolution: pin to `Literal["plugin_extends_cycle", "manifest_rejected", "capability_missing"]` aligning with `PluginRejected` / `PluginExtendsCycle` errors in S2-01 and `CapabilityBundle` checks in S2-04.
- **`HumanReviewReason` literals.** Arch §line 1075 + E10 names `NoConcreteMatch`. Pin `Literal["no_concrete_match", "trust_outcome_failed", "policy_violation_unrecoverable"]` — minimal extensible.
- **`DegradationReason` / `UnavailabilityReason` literals.** Arch §C7 line 605 + §line 936 (logging) name `adapter_degraded`. Pin `DegradationReason = Literal["timeout", "partial_results", "rate_limited"]`; `UnavailabilityReason = Literal["binary_missing", "io_error", "unsupported_version"]`.
- **`Applied.transform: Transform` vs `Applied.transform_id: TransformId`.** Build-order: S1-04 ships `Transform` ABC. S1-03 cannot import `Transform` (circular: `outcomes.py` would import from `transform.py` which would import `RecipeOutcome` from `outcomes.py`). Resolution: ship `transform_id: TransformId` now; S1-04's `Transform` ABC carries `transform_id` field, so consumer code can lookup the `Transform` by id without a direct reference. Document the rationale in Notes; S1-04's AC closes the loop.
- **`branch: BranchName` placeholder for `SandboxedPath` field-type.** `SandboxedPath` ships in S4-01. S1-03 cannot type `report_path: SandboxedPath` without a forward-ref. Resolution: ship `report_path: str` now; S4-01 widens via a Pydantic `field_validator` to convert at construction time. Document.
- **`ApplicationPlan` placeholder.** Story Notes line 168 names "one optional `summary: str` field is enough"; S5-01 widens. Pin: `class ApplicationPlan(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid"); summary: str | None = None`. Phase 5 recipe engines widen additively.

### Adjacent test / production code

- `src/codegenie/indices/freshness.py` — closest precedent (Pydantic discriminated union family). Mirror imports, `kind` defaults, `Annotated[... Field(discriminator="kind")]` form.
- `tests/unit/indices/test_freshness.py` — closest test precedent. Mirror: round-trip identity over all variants; discriminator-string pin; JSON-shape pin; top-level rejection; nested-discriminator preservation; `match` + `assert_never` exhaustiveness; `__all__` subset; module-purity source-scan.
- `src/codegenie/probes/_shared/scanner_outcome.py` — second precedent (`ScannerOutcome = Annotated[ScannerRan | ScannerSkipped | ScannerFailed, Field(discriminator="kind")]`). Identical pattern.
- `tests/unit/probes/_shared/test_scanner_outcome.py` — `TypeAdapter[ScannerOutcome]` round-trip + adversarial bytes-cap pattern.
- `src/codegenie/probes/layer_c/scenario_result.py` — third precedent (3 discriminated unions in one module). Mirror multi-union-per-module structure.

## Stage 2 — critic reports

### Coverage critic (verdict: COVERAGE-HARDEN — 9 findings, 2 block)

| ID | Sev | Finding | Closure |
|---|---|---|---|
| C-F1 | **block** | `RemediationOutcome.Validated` story-field-set `(transform_id, trust_outcome_passed, failing)` drifts from arch line 827 `(branch, report_path, trust_outcome)`. Phase 5 GateRunner reads `branch` and `report_path`; without them, the executor ships a `Validated` that doesn't carry the data the contract requires. | Add AC pinning `Validated(kind, branch: BranchName, report_path: str, passed: bool, failing: list[SignalKind])`. Document S4-01 / S6-02 widening path. |
| C-F2 | **block** | `RemediationOutcome.Failed` missing `partial_report_path: str \| None` (arch line 452 / line 830). | Add AC + test for the field; default `None` for failures before report-path allocation. |
| C-F3 | harden | `SkipReason`, `EscalationReason`, `HumanReviewReason`, `DegradationReason`, `UnavailabilityReason` taxonomies named in Implementation outline §3 but no AC pins their `Literal[...]` sets. A wrong implementation could ship `SkipReason = Literal["any_string"]`. | Add AC pinning the exact literal members for each taxonomy. |
| C-F4 | harden | `NotApplicableReason` shared between two outcome types but no AC pins single source-of-truth. | Add AC: `from codegenie.transforms.outcomes import NotApplicableReason as A; from <RecipeOutcome's module> import NotApplicableReason as B; assert A is B`. |
| C-F5 | harden | `Validated.passed == (failing == [])` invariant unenforced. `Validated(passed=True, failing=[SignalKind("tests")])` constructable. | Add AC + `model_validator(mode="after")` + test. |
| C-F6 | harden | `NodeTransition.Advance.state: dict[str, str \| int \| bool \| float]` — story Notes §line 167 says "no list[str]" but no AC asserts rejection of `state={"x": [1, 2]}`. | Add AC + parametrized rejection test. |
| C-F7 | harden | `ApplicationPlan` placeholder shape not pinned. | AC: `class ApplicationPlan(BaseModel): ...; summary: str \| None = None`. |
| C-F8 | nit | `Skipped` semantics under-specified — when does a recipe engine emit `Skipped` vs `NotApplicable`? | Pin in Notes-for-implementer (no AC needed; Phase 4 surface). |
| C-F9 | nit | Arch line 1154 says `NodeTransition.ShortCircuit(outcome: RecipeOutcome)` but story says `RemediationOutcome`. | Story is correct per orchestrator-outer-loop semantics; document arch-typo in Notes. |

### Test-quality critic (verdict: TEST-HARDEN — 8 findings, 2 block)

| ID | Sev | Finding | Closure |
|---|---|---|---|
| T-F1 | **block** | Discriminator strings not pinned exactly. Round-trip is symmetric under string-rename. Mutation: `Applied.kind = "failed"; Failed.kind = "applied"` passes round-trip; breaks every Phase-5 consumer. | New AC + `test_discriminator_strings_are_exactly_pinned` enumerating all 19 variant strings. |
| T-F2 | **block** | JSON-shape not pinned. Mutation: `kind` → `tag` rename across every variant + every consumer is also round-trip-stable. | New AC + `test_json_shape_pinned` — `Applied(...).model_dump(mode="json")["kind"] == "applied"` per variant. |
| T-F3 | harden | `extra="forbid"` and `frozen=True` tested only on one variant each (`NotApplicable`, `Applied`). | Parametrize over every variant of every union (17 variants). |
| T-F4 | harden | Top-level-discriminator rejection (`TypeAdapter(U).validate_python({"kind": "bogus"}) raises ValidationError`) not tested. | New AC + test per union. |
| T-F5 | harden | Nested-discriminator preservation on `NodeTransition.ShortCircuit.outcome` not tested. Mirror `Stale.reason: StaleReason` precedent. | New AC + parametrized round-trip preserving inner concrete type. |
| T-F6 | harden | Exhaustiveness test shown only for `RecipeOutcome` in TDD plan. AC-9 says "one per union" but no parametrized fixture or per-union test enumeration. | Restate AC: explicit five tests `test_exhaustiveness_<union>` with named arms. |
| T-F7 | harden | `assert_never` enforcement is type-time. Story Refactor §line 140 admits this. No executable mypy-negative fence. | New AC + subprocess-mypy meta-test (`test_exhaustiveness_mypy_negative`) that asserts `mypy --strict` returns non-zero on a fixture with a missing `case` arm. |
| T-F8 | nit | TDD red-test code (`Applied(...)`) uses ellipsis for fixture args — would fail at runtime, but the red→green transition requires the test be valid Python first. | Use concrete fixture constructors in TDD plan. |

### Consistency critic (verdict: CONSISTENCY-HARDEN — 5 findings, 0 block (2 already promoted by Coverage))

| ID | Sev | Finding | Closure |
|---|---|---|---|
| X-F1 | (Coverage C-F1) | Already covered — `Validated` field drift. | Same closure. |
| X-F2 | (Coverage C-F2) | Already covered — `Failed.partial_report_path` missing. | Same closure. |
| X-F3 | harden | `Discriminator("kind")` (Pydantic v2 callable-discriminator) vs `Field(discriminator="kind")` (tag-string) — story line 49 mentions the former; repo convention is the latter (5 files). | Pin AC on `Annotated[A \| B \| C, Field(discriminator="kind")]`. |
| X-F4 | harden | `kind: Literal["..."] = "..."` (default-value form) is the repo convention. Story signature `kind: Literal["applied"]` (no default) forces redundant `kind="applied"` at every call site. | Pin AC on default-value form. |
| X-F5 | harden | `__all__` exact-set not pinned. ADR-0001 §Consequences requires re-export discipline. | Pin AC: 30 names enumerated (variants + unions + reason aliases + error models). |

### Design-patterns critic (verdict: DP-HARDEN — 4 findings, 0 block)

| ID | Sev | Finding | Closure |
|---|---|---|---|
| D-F1 | harden | Module-purity invariant unasserted — `outcomes.py` is contract-surface kernel; imports must be limited to `{__future__, typing, pydantic, codegenie.types.identifiers, codegenie.types.errors}`. Same closure as S1-01 / S1-02. | Add AC + AST source-scan test. |
| D-F2 | harden | `model_construct` (bypass-validation) discipline unasserted. | Add AC + source-scan: `model_construct` absent from `outcomes.py`. |
| D-F3 | harden | `Open/Closed for new variants` — when Phase 4 lands `LLMFallback`, no fence detects an un-updated `match` site. Type-time `assert_never` is the enforcement; promoted to AC via subprocess-mypy negative (already in T-F7). | Covered by T-F7. |
| D-F4 | nit | `Applied.transform_id: TransformId` (story) vs `Applied.transform: Transform` (arch) — build-order forces the denormalization. Capture in Notes; S1-04 closes the loop. | Notes update. |

## Stage 4 — synthesis & edits applied

The story has the right scope and the right intent, but ships ACs that:
1. Drift from arch on two load-bearing fields (`Validated.branch`, `Validated.report_path`, `Failed.partial_report_path`) — block-tier.
2. Underspecify the literal taxonomies for 5 of 6 reason types — harden-tier.
3. Underspecify the test plan in ways that admit symmetric-mutation regressions (discriminator-string rename, `kind` → `tag` rename) — block-tier under Rule 9 ("Tests verify intent, not just behavior").
4. Miss the repo-uniform conventions for Pydantic discriminated unions (default-value `kind`, `Field(discriminator)` form, parametrized `frozen`/`extra=forbid`, module-purity, `model_construct` absent) — harden-tier.

**Edits applied to the story file** (see `git diff` for the authoritative record):

- **Status:** `Ready` → `HARDENED`.
- **Validation notes block** added under the header naming this report.
- **Acceptance criteria** rewritten:
  - AC-3 (`RecipeOutcome` variants) — `Applied.transform_id: TransformId` rationale added; `kind: Literal["applied"] = "applied"` form; pin `Skipped(reason: SkipReason)` taxonomy.
  - AC-4 (`RemediationOutcome` variants) — **block fix**: `Validated(kind, branch, report_path, passed, failing)` + `Failed(kind, error, partial_report_path)`; document S4-01 / S6-02 widening path.
  - AC-5 (`NodeTransition`) — pin `Advance.state` primitive-only rejection; document arch line 1154 typo (story is correct).
  - AC-6 (`AdapterConfidence`) — pin `DegradationReason` / `UnavailabilityReason` literal sets.
  - AC-7 (`Applicability`) — pin `ApplicationPlan(summary: str \| None = None)`.
  - New AC-7a — every `kind` field uses the default-value form `Literal["..."] = "..."`.
  - New AC-7b — every union uses `Annotated[A \| B \| C, Field(discriminator="kind")]`.
  - New AC-7c — `NotApplicableReason` exported from one source-of-truth path.
  - New AC-7d — `SkipReason`, `EscalationReason`, `HumanReviewReason` literal sets pinned.
  - New AC-7e — `Validated` model_validator: `passed == (failing == [])` invariant enforced.
  - AC-8 (test file) split into AC-8a (construct + frozen + extra + JSON round-trip parametrized over all 17 variants), AC-8b (discriminator-strings pinned), AC-8c (JSON-shape pinned), AC-8d (top-level discriminator rejects bogus kind), AC-8e (nested-discriminator preservation on `NodeTransition.ShortCircuit.outcome`).
  - AC-9 (exhaustiveness) — pin five named tests (one per union); add new AC-9a for subprocess-mypy negative meta-test.
  - New AC-10a — `__all__` exact-set pinned.
  - New AC-10b — module-purity AST scan (imports limited to allowed set).
  - New AC-10c — `model_construct` absent (source-scan).
- **Implementation outline** updated to reflect the corrected `Validated` / `Failed` shape, the default-value `kind` form, and the literal-taxonomy enumeration.
- **TDD plan** — red-test rewritten to use concrete fixture constructors (not `...` ellipsis); explicit five exhaustiveness tests named; subprocess-mypy fixture mentioned.
- **Files to touch** — added `tests/unit/transforms/test_outcomes_mypy_negative_fixture.py` and the test_exhaustiveness fixture import.
- **Notes for the implementer** — added paragraphs on: build-order rationale for `transform_id` (S1-04 closes the loop); `branch` / `report_path` placeholder typing (S4-01 closes); S6-02 widening path for `Validated`; arch-typo on `NodeTransition.ShortCircuit.outcome`; freshness-precedent test patterns to mirror.

**Final verdict: HARDENED.** Story is ready for the executor with two block-tier consistency issues closed, eight test-quality regressions pinned, and the repo-uniform discriminated-union conventions fenced.
