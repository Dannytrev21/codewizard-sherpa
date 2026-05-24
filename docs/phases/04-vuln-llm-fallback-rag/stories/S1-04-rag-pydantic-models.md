# Story S1-04 — RAG-side Pydantic models

**Step:** Step 1 — Establish Phase-4 type substrate + path-scoped fence amendment
**Status:** Done — 2026-05-24 (phase-story-executor; see [`_attempts/S1-04.md`](_attempts/S1-04.md) for the per-AC evidence table + gate log — seven Phase-4 RAG-side Pydantic v2 frozen-extra-forbid models landed across `src/codegenie/rag/models.py`, `src/codegenie/fallback/budget.py`, plus the kernel-tier `TzAwareDatetime` alias at `src/codegenie/types/datetime.py` (homed there to break a `rag.models` ↔ `fallback.budget` cycle the first green-run surfaced). 74 story-scoped tests pass — 42 in `tests/unit/rag/test_models.py`, 17 in `tests/unit/fallback/test_budget_models.py`, 2 Hypothesis properties in `tests/property/test_query_digest_determinism.py`, 1 concrete JSON round-trip in `tests/property/test_solved_example_yaml_roundtrip.py`. Story-scoped gates green: 383 fence tests, `mypy --strict src/` (213 files), `ruff check`, `ruff format --check`, `make lint-imports` (6 contracts kept). `_marker` is a Pydantic v2 `PrivateAttr` per ADR-0010 §Decision; AC-18's three checks (default, non-serialization, forged-marker rejection) pin the capability-discipline contract.)
**Effort:** S
**Depends on:** S1-01, S1-02
**ADRs honored:** ADR-0010 (`BudgetToken` is the capability; this story lands the Pydantic frozen-extra-forbid model with the ADR-0010 four-field shape + the private `_marker` discriminator), ADR-0016 (canonical YAML SolvedExample with chain-verified `RecordProvenance`), ADR-0008 (`RetrievalOutcome` is a closed three-way union — `RagHit | RagMiss | RagDegraded` — feeding the two-threshold band)

## Validation notes

Validated: 2026-05-21
Verdict: HARDENED
Findings addressed: 21 — 6 blocks, 11 hardens, 4 nits

Changes applied:
- **F1 (block)** — TDD-plan import `from codegenie.probes.node_build_system import PackageManager` corrected to `codegenie.types.identifiers` (ADR-0013 Amendment 2026-05-20 moved `PackageManager` to the kernel-tier `types` package; `probes`/`depgraph` import it FROM there).
- **F2 (block)** — `PackageManager` is a `Literal`, not an `Enum`. The `PackageManager.NPM.value` fixture idiom is invalid (a `Literal` has no `.NPM`/`.value`); fixtures use the bare string `"npm"`. AC-2 / References / Notes wording "enum" → "`Literal`".
- **F3 (block)** — AC-2's unresolved `task_class: TaskClassId` "(or `TaskClassName`)" / `language: Language` "(or `LanguageName`)" parentheticals removed. `identifiers.py` ships `TaskClassId`/`Language`/`PackageManager` and NO `*Name` variants; the canonical names win (Rule 11). The arch §Data-model `*Name` drift is flagged for doc correction in Notes.
- **F4 (block)** — `Depends on:` extended to `S1-01, S1-02` — the story imports `PlanProposal` from `codegenie.fallback.plan_proposal` and writes into the `fallback/` package, both created by S1-02.
- **F5 (block)** — AC-4 `RagHit`/`RagMiss`/`RagDegraded` conformed to ADR-0008 §Decision + arch §Component 9: `RagHit(kind, few_shot, score)`, `RagDegraded(kind, near_match, score)`, `RagMiss(kind)` **bare**. The writer's `RagMiss.reason` 4-literal enrichment was unsourced and ADR-0008 says `RagMiss` is bare (widening is a separate ADR amendment) — dropped; chain-orphan/model-mismatch observability lives in the emitted events per edge cases #14/#19.
- **F6 (block)** — AC-7 `BudgetToken` conformed to ADR-0010 §Decision + arch §Component 5: fields `precharged_tokens`, `precharged_dollars`, `issued_at`, `_marker`. The writer's `id: BudgetTokenId` field was dropped (ADR-0010's `BudgetToken` carries no id; the guard keys `outstanding_tokens` by `BudgetTokenId` externally — arch §Component 5 State).
- **F7–F13 (harden)** — TDD plan rewritten: `extra="forbid"` + `frozen` parametrized over all seven models; `Literal`-field rejection tests added (AC-16); `digest()` field-perturbation extended to all six `Query` fields; the Hypothesis property now draws all six fields; AC-12 round-trip got a concrete test body; naive-datetime enforcement parametrized over `SolvedExample` + `RecordProvenance` + `BudgetToken.issued_at`; `RagHit`/`RagDegraded` required-payload rejection tests added.
- **F14 (harden)** — AC-18 added: `_marker` is a Pydantic v2 `PrivateAttr` (leading underscore ⇒ private attribute — ADR-0010 itself says "private"); tests pin the default, its absence from `model_dump()`, and rejection of a forged `_marker=` constructor kwarg.
- **F15 (harden)** — AC-17 added: range-bounded fields reject out-of-range values (`score` outside `[-1.0, 1.0]`; `TokenCount` fields below 0) via `Annotated[..., Field(ge=..., le=...)]` — the established repo idiom (`scip_slice.py`, `sandbox_jail.py`).
- **F16 (harden)** — `tests/unit/fallback/__init__.py` added to Files-to-touch + Implementation outline.
- **F17 (harden)** — `RecordProvenance.signing_method` literal set is unsourced; Notes instruct the implementer to verify it against the Phase-3 spanning-log chain implementation before GREEN.
- **F18 (nit)** — `RetrievalOutcome` discriminator idiom corrected to `Field(discriminator="kind")` (the implemented repo convention in `transforms/outcomes.py`; S1-02/S1-03 already corrected the same `Discriminator(...)` arch-doc drift).
- **F19 (nit)** — budget-model tests homed unambiguously in `tests/unit/fallback/test_budget_models.py`; AC-10 updated to name both test files.
- **F20 (nit)** — `FailureModeTag` placement: kept rag-local; Notes document the choice + the competing `identifiers.py` precedent (Rule 7).
- **F21 (nit)** — AC-3 `digest()` wording: Pydantic v2 `model_dump_json` emits fields in definition order (stable for a frozen model), not "sorted keys" — clarified.

Full audit log: `_validation/S1-04-rag-pydantic-models.md`

## Context

Steps 2 through 7 read every RAG-side primitive landed here as a frozen Pydantic model: `SolvedExample` (the persisted record), `Query` (the typed-fields input to retrieval, no f-strings), `RecordProvenance` (chain-verify input), `RetrievalOutcome` (the closed `RagHit | RagMiss | RagDegraded` union), `BudgetSnapshot` (Phase-5-consumed projection from `LlmInvocationGuard.running_total`), `BudgetToken` (the function-signature capability gating LLM spend), and `TypecheckNodeSignal` (the Phase-3 `@register_signal_kind` `kind: Literal["typecheck.typescript"]` shape). They land *together* in Step 1 because each is a contract surface: any consumer (`SolvedExampleStore.add`, `SolvedExampleRetriever.query`, `LlmInvocationGuard.precharge`, `TrustScorer.fold`) is typed against these shapes, and the alternative — landing them lazily as each consumer arrives — produces a "fix-the-shape-and-everything-breaks" cascade that is the load-bearing risk Step 1 exists to prevent.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Data model` — every model body landed in this story (`SolvedExample`, `Query`, `BudgetSnapshot`, `BudgetToken`, `TypecheckNodeSignal`, `RecordProvenance`, `RetrievalOutcome`).
  - `../phase-arch-design.md §Component design — SolvedExampleStore (Component 7)` — `Query.digest()` is the cache key.
  - `../phase-arch-design.md §Component design — SolvedExampleRetriever (Component 9)` — `RetrievalOutcome` three-way union semantics.
  - `../phase-arch-design.md §Component design — LlmInvocationGuard + BudgetToken (Component 5)` — `BudgetToken._marker: Literal["budget_token"]`, capability discipline.
  - `../phase-arch-design.md §Component design — TypecheckTypescriptSignal (Component 11)` — `TypecheckNodeSignal.kind: Literal["typecheck.typescript"]`.
  - `../phase-arch-design.md §Edge cases` #14 (chain-orphan record), #19 (model-mismatch exclusion).
  - `../phase-arch-design.md §Goals — G2` — "Stable contract surface for Phase 5."
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0010-llm-invocation-guard-budget-token-capability.md` — `BudgetToken` shape; `BudgetSnapshot` is the name-stable projection Phase 5 consumes.
  - `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` — `SolvedExample` is the persisted YAML record; `RecordProvenance.event_chain_head` is the chain-verify anchor.
  - `../ADRs/0008-two-threshold-calibration-band.md` — `RetrievalOutcome` three-way union; `AdapterConfidence` literal set.
  - `../ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md` — `TypecheckNodeSignal` field shape mirrors Phase-3 `TrustSignal`.
- **Production ADRs:**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — frozen-extra-forbid as the default.
- **Source design:**
  - `../final-design.md §Component 8 — SolvedExample` — origin of the model shape.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/types/identifiers.py` — Phase-2/3 owns `TaskClassId`/`Language`/`CveId`/`PackageId`; Phase-4 S1-01 added `SolvedExampleId`/`StoreDigest`/`ChainHead`/`BlobDigest`/`ModelId`/`TokenCount`/`BudgetTokenId`/`EmbeddingVector`/`Similarity`. Reuse exclusively.
  - **`TaskClassName` / `LanguageName` / `BuildSystemName` / `CveId` / `FailureModeTag`** — verify which are already in `identifiers.py` and which are Phase-3-owned. If the arch §Data model names (`TaskClassName` etc.) drift from the Phase-2/3 canonical names (`TaskClassId`, `Language`), surface per Rule 7 and adopt the **existing** name.
  - `src/codegenie/plugins/protocols.py` (or wherever Phase-3's `TrustSignal` lives) — pattern for `confidence: Literal["high", "medium", "low"]` field; mirror exactly.
  - Phase-3 `RecipeOutcome` field shapes — `RecordProvenance.event_chain_head` references the Phase-3 spanning-log chain head; the link must align.

## Goal

Ship seven RAG-side Pydantic v2 frozen-extra-forbid models at `src/codegenie/rag/models.py` (and `src/codegenie/fallback/budget.py` for `BudgetSnapshot`/`BudgetToken`), so every Step 2–7 consumer is typed against the contract surface from day one.

## Acceptance criteria

### Models landed

- [x] AC-1 — `src/codegenie/rag/__init__.py` and `src/codegenie/rag/models.py` exist.
- [x] AC-2 — `SolvedExample` model in `rag/models.py` with `frozen=True, extra="forbid"` and these fields exactly:
  - `id: SolvedExampleId`
  - `task_class: TaskClassId` (validator: was "(or `TaskClassName`)" — resolved; `identifiers.py` ships `TaskClassId` and no `TaskClassName`)
  - `language: Language` (validator: was "(or `LanguageName`)" — resolved; `identifiers.py` ships `Language` and no `LanguageName`)
  - `build_system: PackageManager` (the Phase-1 ADR-0013-owned **`Literal`** — defined in `codegenie.types.identifiers`; **import, do not redefine**)
  - `cve_id: CveId`
  - `advisory_digest: BlobDigest`
  - `plan_kind: Literal["dep_bump", "override", "callsite_rewrite"]`
  - `plan_proposal: PlanProposal` (the closed union from S1-02)
  - `transform_digest: BlobDigest`
  - `trust_outcome_digest: BlobDigest`
  - `provenance: RecordProvenance`
  - `origin: Literal["llm_solved", "operator_curated", "phase11_merge_webhook"]`
  - `embedding_model: ModelId`
  - `created_at: datetime` (tz-aware; UTC; validator rejects naive datetimes).
- [x] AC-3 — `Query` model with `frozen=True, extra="forbid"`:
  - `task_class: TaskClassId`
  - `language: Language`
  - `build_system: PackageManager`
  - `cve_id: CveId`
  - `affected_package: PackageId`
  - `failure_mode: FailureModeTag` — **typed `Literal`**, not free-text. The literal set lives at module level: `FailureModeTag = Literal["build_break", "test_fail", "typecheck_fail", "lockfile_resolution_fail", "callsite_signature_drift", "policy_block"]`. Six values cover Phase-4 fixture portfolio per arch §Fixture portfolio + §Edge cases.
  - `def digest(self) -> BlobDigest:` — returns BLAKE3 hex (64 lowercase hex chars) over the model's canonical JSON serialization. Pydantic v2 `model_dump_json` emits fields in **definition order** — stable across runs for a frozen model — so the dump is deterministic without an explicit key sort. Determinism (same fields ⇒ same digest) and field-sensitivity (any field change ⇒ different digest) are the load-bearing properties; AC-11 is the guard.
- [x] AC-4 — `RetrievalOutcome` closed three-way union, each variant `frozen=True, extra="forbid"`. **Field shapes conform to ADR-0008 §Decision + arch §Component 9 verbatim** (validator: was `RagHit(kind, record, similarity)` / `RagMiss(kind, reason)` / `RagDegraded(kind, record, similarity)` — corrected):
  - `RagHit` (`kind: Literal["hit"] = "hit"`, `few_shot: SolvedExample`, `score: Similarity`) — confident hit; `score ≥ high_floor`.
  - `RagMiss` (`kind: Literal["miss"] = "miss"`) — **bare** (no payload beyond the discriminator). ADR-0008 §Decision + §Pattern-fit specify `RagMiss` carries nothing. The chain-orphan / model-mismatch observability (arch edge cases #14, #19) lives in the emitted `RagRecordChainOrphan` / `RagRecordModelMismatch` events, **not** in a `RagMiss.reason` field. Adding a `reason` field is an ADR-0008 widening amendment, out of scope for this story.
  - `RagDegraded` (`kind: Literal["degraded"] = "degraded"`, `near_match: SolvedExample`, `score: Similarity`) — near-match returned but below `high_floor` and at-or-above `degraded_floor`; fed to the LLM with a low-confidence tag.
  - `RetrievalOutcome = Annotated[RagHit | RagMiss | RagDegraded, Field(discriminator="kind")]`. (validator: `Field(discriminator="kind")`, not `Discriminator("kind")` — the implemented repo convention in `transforms/outcomes.py`; S1-02/S1-03 corrected the same arch-doc drift.)
- [x] AC-5 — `RecordProvenance` model with `frozen=True, extra="forbid"`:
  - `workflow_id: WorkflowId`
  - `event_chain_head: ChainHead` (BLAKE3 — the spanning-log head this record was witnessed at)
  - `created_at: datetime` (tz-aware UTC)
  - `signing_method: Literal["hmac_sha256_chain", "operator_attestation"]`.
- [x] AC-6 — `BudgetSnapshot` model in `src/codegenie/fallback/budget.py` with `frozen=True, extra="forbid"`:
  - `consumed_tokens: TokenCount`
  - `consumed_dollars: Decimal`
  - `outstanding_tokens: TokenCount`
  - `cap_tokens: TokenCount`
  - `cap_dollars: Decimal`.
  - **Invariants enforced via `@model_validator(mode="after")`:** `consumed_tokens + outstanding_tokens <= cap_tokens` (refused otherwise); `consumed_dollars <= cap_dollars`; `consumed_dollars >= 0`. (`TokenCount` ≥ 0 is enforced by the `parse_token_count` smart constructor at the boundary; here we re-assert the relation via Pydantic validation.)
- [x] AC-7 — `BudgetToken` model with `frozen=True, extra="forbid"`. **Field shape conforms to ADR-0010 §Decision + arch §Component 5 verbatim** (validator: was `id: BudgetTokenId` / `precharge_tokens` — corrected; ADR-0010's `BudgetToken` carries no `id`, and the field is `precharged_tokens`):
  - `precharged_tokens: TokenCount` — see AC-17 for the `≥ 0` range constraint.
  - `precharged_dollars: Decimal`
  - `issued_at: datetime` (tz-aware; UTC; the same naive-datetime validator AC-13 applies to `SolvedExample`/`RecordProvenance` covers this field).
  - `_marker: Literal["budget_token"] = "budget_token"` — the capability discriminator. ADR-0010 §Decision explicitly calls this a **private** marker; the leading underscore makes it a Pydantic v2 **`PrivateAttr`** (see AC-18). It is the identity tag S2-05's import-linter contract + AST-walk use to recognize a capability flow.
  - **No `id` field.** ADR-0010 + arch §Component 5 keep `BudgetToken` id-less; `LlmInvocationGuard` keys its `outstanding_tokens: dict[BudgetTokenId, TokenCount]` by `BudgetTokenId` externally (arch §Component 5 State). If S2-05 finds the token genuinely needs to carry its own id, that is an ADR-0010 amendment surfaced in S2-05 — not this story.
  - **No issuer logic here** — `LlmInvocationGuard.precharge` (S2-05) is where issuance happens. This story ships the shape only.
- [x] AC-8 — `TypecheckNodeSignal` model (named per arch §Data model; mirrors Phase-3 `TrustSignal` shape):
  - `kind: Literal["typecheck.typescript"] = "typecheck.typescript"`
  - `passed: bool`
  - `details: dict[str, str | int | bool]` (carries forward Phase 3 convention; no Phase-4 widening)
  - `confidence: Literal["high", "medium", "low"]`
  - **No `@register_signal_kind` call here** — S6-05 wires it; this story ships the model alone.
- [x] AC-9 — All seven models export from their package `__init__.py` and through `codegenie.rag`/`codegenie.fallback` boundary modules.

### Verification

- [x] AC-10 — Two test files together cover every model: `tests/unit/rag/test_models.py` (the five RAG-side models) and `tests/unit/fallback/test_budget_models.py` (`BudgetSnapshot`, `BudgetToken`). Coverage required:
  - Happy: each of the seven models constructs from a valid dict.
  - Sad — `extra="forbid"` rejects an unknown key. **Parametrized over all seven model classes** (`SolvedExample`, `Query`, `RecordProvenance`, `RagHit`, `RagMiss`, `RagDegraded`, `TypecheckNodeSignal`, plus `BudgetSnapshot`, `BudgetToken` in the fallback file) — not `SolvedExample` alone. (validator: hardened — the original TDD plan only tested `SolvedExample`; removing `extra="forbid"` from any other model left every test green.)
  - Sad — `frozen=True` rejects post-construction attribute assignment. **Parametrized over all seven model classes** (same set). For `BudgetToken`, assert on a public field — `precharged_tokens` — not `_marker` (see AC-18).
  - Sad — discriminator routes an unknown `kind` to `ValidationError` (`RetrievalOutcome` via `TypeAdapter`).
  - Sad — `Query.digest()` is **deterministic** across two constructions with the same field values.
  - Sad — `Query.digest()` **differs** when *any one of all six* fields changes (AC-11 is the parametrized guard).
  - Sad — `Query.digest()` length is exactly 64 lowercase hex chars (BLAKE3).
  - Sad — `Query.failure_mode` outside the six literals rejected.
  - Sad — `BudgetSnapshot` with `consumed_tokens + outstanding_tokens > cap_tokens` rejected.
  - Sad — `BudgetSnapshot` with `consumed_dollars > cap_dollars` rejected.
  - Sad — `BudgetSnapshot` with `consumed_dollars < 0` rejected.
  - Sad — `RagHit`/`RagDegraded` constructed without their required payload (`few_shot` / `near_match`) rejected. (validator: added — the story's Notes call a payload-less near-match "a model bug"; nothing tested it.)
  - Each model's full field keyset is pinned: `set(instance.model_dump().keys()) == {…}` — a silent field rename/drop is caught. (validator: added — mirrors the `test_json_shape_keysets_pinned` idiom in the adjacent `tests/unit/transforms/test_outcomes.py`.)
- [x] AC-11 — **`Query.digest()` determinism property** (`tests/property/test_query_digest_determinism.py`):
  - Hypothesis-generate `Query` field values (drawn from valid strategies). For any drawn `q`, `q.digest() == q.digest()` (purity) and `q.digest()` is 64 lowercase hex.
  - Field-perturbation: changing any single field changes the digest (parametrized over each field).
- [x] AC-12 — **`SolvedExample` JSON round-trip** (`tests/property/test_solved_example_yaml_roundtrip.py`; the full `from_yaml(to_yaml(x)) == x` Hypothesis property lands in S4-04 — this story proves the Pydantic shape is JSON-serialisable):
  - A concrete, representative valid `SolvedExample` satisfies `SolvedExample.model_validate_json(s.model_dump_json()) == s` (deep equal). (validator: was "Hypothesis-generated" — made example-based; a `st.builds(SolvedExample, …)` strategy needs a generator for the nested `PlanProposal` discriminated union, which is S1-02/S4-04 territory. A concrete round-trip still fails loudly if the shape is not serialisable. The test must have a real body — not a contentless skeleton.)
- [x] AC-13 — **`tz-aware datetime` enforcement** — parametrized test: a naive `datetime(2026, 1, 1)` → `ValidationError`; a tz-aware `datetime(2026, 1, 1, tzinfo=UTC)` → `Ok`. Applies to **all three** tz-aware datetime fields: `SolvedExample.created_at`, `RecordProvenance.created_at`, and `BudgetToken.issued_at`. (validator: hardened — `BudgetToken.issued_at` added; the original TDD plan only tested `SolvedExample`, so dropping the validator from `RecordProvenance` or `BudgetToken` left every test green.)
- [x] AC-14 — `mypy --strict src/codegenie/rag/` and `mypy --strict src/codegenie/fallback/` clean. `ruff check`, `ruff format --check` clean.
- [x] AC-15 — The TDD plan's red tests exist, are committed, and are green.
- [x] AC-16 — **Every `Literal`-typed field rejects an out-of-set value** (`pytest.raises(ValidationError)`), parametrized: `SolvedExample.plan_kind`, `SolvedExample.origin`, `RecordProvenance.signing_method`, `TypecheckNodeSignal.confidence`. (`Query.failure_mode` is already covered by AC-10; `RetrievalOutcome.kind` by the AC-10 discriminator test.) (validator: added — the original TDD plan tested only `failure_mode`; typing any of these fields as bare `str` would otherwise pass every test.)
- [x] AC-17 — **Range-bounded fields reject out-of-range values.** The float `score` on `RagHit`/`RagDegraded` is typed `Annotated[Similarity, Field(ge=-1.0, le=1.0)]` and the `TokenCount` fields on `BudgetToken` (`precharged_tokens`) and `BudgetSnapshot` (`consumed_tokens`, `outstanding_tokens`, `cap_tokens`) are typed `Annotated[TokenCount, Field(ge=0)]`. Tests: `RagHit(..., score=1.5)` → `ValidationError`; `RagHit(..., score=0.85)` (in-band) → `Ok`; `BudgetToken(..., precharged_tokens=-1)` → `ValidationError`. (validator: added — `Similarity` and `TokenCount` are `NewType`s; Pydantic v2 sees only the base `float`/`int` and does NOT re-validate the smart-constructor range. `RetrievalOutcome` is built *internally* by `SolvedExampleRetriever` from a raw ChromaDB score that never passes `parse_similarity`, so an out-of-range `RagHit` is a representable illegal state on a hot path. `Annotated[..., Field(ge=…, le=…)]` is the established repo idiom — `scip_slice.py`, `sandbox_jail.py`, `redacted_slice.py`.)
- [x] AC-18 — **`BudgetToken._marker` is a Pydantic v2 `PrivateAttr`.** A leading-underscore annotation in a Pydantic v2 model is a private attribute, not a validated field — ADR-0010 §Decision deliberately specifies a "private" marker. Declare it explicitly: `_marker: Literal["budget_token"] = PrivateAttr(default="budget_token")`. Tests pin the understood behavior: (a) `BudgetToken(precharged_tokens=…, precharged_dollars=…, issued_at=…)._marker == "budget_token"` (default present); (b) `"_marker" not in BudgetToken(...).model_dump()` (private ⇒ not serialized); (c) `BudgetToken(..., _marker="forged")` raises `ValidationError` (a forged marker cannot be injected via the constructor — `extra="forbid"` rejects the unknown `_marker` kwarg). (validator: added — the original `test_budget_token_marker` only asserted the default and would pass even if the marker provided zero capability discipline.)

## Implementation outline

1. Create `src/codegenie/rag/__init__.py` and `src/codegenie/rag/models.py`. Ensure `tests/unit/rag/__init__.py` and `tests/unit/fallback/__init__.py` exist (create whichever is absent — package-style test dirs).
2. Define `FailureModeTag = Literal[...]` (six values) at module top of `rag/models.py` per AC-3.
3. Define `RecordProvenance`, `Query`, `SolvedExample` (in order — `SolvedExample` references both), `RagHit`, `RagMiss`, `RagDegraded`, `RetrievalOutcome`. `RagHit.few_shot` / `RagDegraded.near_match` are `SolvedExample`; `RagMiss` is bare (discriminator only); `score` is `Annotated[Similarity, Field(ge=-1.0, le=1.0)]` (AC-4 + AC-17).
4. Implement `Query.digest()` using BLAKE3 over `self.model_dump_json()` (Pydantic v2 emits fields in definition order — deterministic for a frozen model; no explicit key sort needed). Hex-encode the digest to 64 lowercase chars.
5. Add the tz-aware datetime validator rejecting `v.tzinfo is None`. It applies to `SolvedExample.created_at`, `RecordProvenance.created_at`, and `BudgetToken.issued_at` — define one reusable validator helper (or an `Annotated` type) so all three fields share it rather than copying the check three times.
6. Create `src/codegenie/fallback/budget.py` containing only `BudgetSnapshot` and `BudgetToken` (issuer logic deferred to S2-05). `BudgetToken` fields per AC-7 (`precharged_tokens`, `precharged_dollars`, `issued_at`, `_marker` via `PrivateAttr` — AC-18); `TokenCount` fields are `Annotated[TokenCount, Field(ge=0)]` (AC-17). Implement the `@model_validator(mode="after")` invariants on `BudgetSnapshot`.
7. Move `TypecheckNodeSignal` to `plugins/vulnerability-remediation--node--npm/adapters/typecheck_signal_model.py` **OR** `src/codegenie/fallback/typecheck_signal.py` — pick the location S6-05 imports from. Document choice in attempt log; the model is plugin-resident vs. substrate-resident per arch §Component 11.
   - **Resolution: ship at `src/codegenie/rag/models.py` for now** (it is a Pydantic data class; the *collector* is plugin-resident in S6-05). Cross-plugin reuse is anticipated by ADR-0015.
8. Wire `src/codegenie/rag/__init__.py` re-exports.
9. Write `tests/unit/rag/__init__.py`, `tests/unit/fallback/__init__.py` (package markers, if absent), `tests/unit/rag/test_models.py`, `tests/unit/fallback/test_budget_models.py`, `tests/property/test_query_digest_determinism.py`, `tests/property/test_solved_example_yaml_roundtrip.py`.
10. Run `mypy --strict` + `make check`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/rag/test_models.py`

```python
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.rag.models import (
    Query,
    RagDegraded,
    RagHit,
    RagMiss,
    RecordProvenance,
    RetrievalOutcome,
    SolvedExample,
    TypecheckNodeSignal,
)

# `PackageManager` is a `Literal` in `codegenie.types.identifiers` (ADR-0013
# Amendment 2026-05-20). Fixtures use the bare string `"npm"` — Pydantic
# validates it against the Literal; no `PackageManager` import is needed and
# there is NO `.NPM`/`.value` member (a Literal is not an Enum).
_HEX64 = "a" * 64
_UTC_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_PROV = {
    "workflow_id": "01HXX00000000000000000000Z",
    "event_chain_head": _HEX64,
    "created_at": _UTC_NOW,
    "signing_method": "hmac_sha256_chain",
}
_PLAN_DEPBUMP = {
    "kind": "dep_bump",
    "manifest_path": "package.json",
    "package": "lodash@4.17.21",
    "target_version": "4.17.21",
    "rationale": "x",
}
_SOLVED = {
    "id": _HEX64,
    "task_class": "vuln_remediation",
    "language": "typescript",
    "build_system": "npm",
    "cve_id": "CVE-2026-1234",
    "advisory_digest": _HEX64,
    "plan_kind": "dep_bump",
    "plan_proposal": _PLAN_DEPBUMP,
    "transform_digest": _HEX64,
    "trust_outcome_digest": _HEX64,
    "provenance": _PROV,
    "origin": "llm_solved",
    "embedding_model": "bge-small-en-v1.5",
    "created_at": _UTC_NOW,
}
_QUERY = {
    "task_class": "vuln_remediation",
    "language": "typescript",
    "build_system": "npm",
    "cve_id": "CVE-2026-1234",
    "affected_package": "express@4.18.0",
    "failure_mode": "build_break",
}
_RAG_HIT = {"kind": "hit", "few_shot": _SOLVED, "score": 0.96}
_RAG_MISS = {"kind": "miss"}
_RAG_DEGRADED = {"kind": "degraded", "near_match": _SOLVED, "score": 0.70}
_TYPECHECK = {"passed": True, "details": {"errors": 0}, "confidence": "high"}

# (model_cls, valid_payload, a_field_to_probe_for_frozen) — drives the
# parametrized extra="forbid" / frozen checks over EVERY RAG-side model.
_MODEL_CASES = [
    (SolvedExample, _SOLVED, "cve_id"),
    (Query, _QUERY, "cve_id"),
    (RecordProvenance, _PROV, "signing_method"),
    (RagHit, _RAG_HIT, "score"),
    (RagMiss, _RAG_MISS, "kind"),
    (RagDegraded, _RAG_DEGRADED, "score"),
    (TypecheckNodeSignal, _TYPECHECK, "passed"),
]


# Explicit per-model expected keysets — a silent field rename/drop is caught.
_EXPECTED_KEYS = {
    SolvedExample: {
        "id", "task_class", "language", "build_system", "cve_id",
        "advisory_digest", "plan_kind", "plan_proposal", "transform_digest",
        "trust_outcome_digest", "provenance", "origin", "embedding_model",
        "created_at",
    },
    Query: {
        "task_class", "language", "build_system", "cve_id",
        "affected_package", "failure_mode",
    },
    RecordProvenance: {"workflow_id", "event_chain_head", "created_at", "signing_method"},
    RagHit: {"kind", "few_shot", "score"},
    RagMiss: {"kind"},
    RagDegraded: {"kind", "near_match", "score"},
    TypecheckNodeSignal: {"kind", "passed", "details", "confidence"},
}


def test_solved_example_happy():
    s = SolvedExample.model_validate(_SOLVED)
    assert s.id == _HEX64
    assert s.created_at == _UTC_NOW


# --- extra="forbid" / frozen / keyset — parametrized over EVERY model (AC-10) ---

@pytest.mark.parametrize("model_cls,payload,_field", _MODEL_CASES)
def test_extra_keys_rejected(model_cls, payload, _field):
    with pytest.raises(ValidationError):
        model_cls.model_validate({**payload, "shell": "rm -rf"})


@pytest.mark.parametrize("model_cls,payload,field", _MODEL_CASES)
def test_frozen_rejects_assignment(model_cls, payload, field):
    instance = model_cls.model_validate(payload)
    with pytest.raises(ValidationError):
        setattr(instance, field, getattr(instance, field))  # type: ignore[misc]


@pytest.mark.parametrize("model_cls,payload,_field", _MODEL_CASES)
def test_keyset_pinned(model_cls, payload, _field):
    dumped = model_cls.model_validate(payload).model_dump()
    assert set(dumped) == _EXPECTED_KEYS[model_cls]


# --- tz-aware datetime enforcement (AC-13; BudgetToken.issued_at in fallback file) ---

@pytest.mark.parametrize("model_cls,payload", [(SolvedExample, _SOLVED), (RecordProvenance, _PROV)])
def test_naive_datetime_rejected(model_cls, payload):
    with pytest.raises(ValidationError):
        model_cls.model_validate({**payload, "created_at": datetime(2026, 1, 1)})


@pytest.mark.parametrize("model_cls,payload", [(SolvedExample, _SOLVED), (RecordProvenance, _PROV)])
def test_tz_aware_datetime_accepted(model_cls, payload):
    assert model_cls.model_validate({**payload, "created_at": _UTC_NOW}).created_at == _UTC_NOW


# --- Literal-field rejection (AC-16) ---

@pytest.mark.parametrize(
    "model_cls,payload,field,bad",
    [
        (SolvedExample, _SOLVED, "plan_kind", "unknown_kind"),
        (SolvedExample, _SOLVED, "origin", "scraped"),
        (RecordProvenance, _PROV, "signing_method", "pgp_clearsign"),
        (TypecheckNodeSignal, _TYPECHECK, "confidence", "certain"),
        (Query, _QUERY, "failure_mode", "freeform"),
    ],
)
def test_literal_field_rejects_out_of_set(model_cls, payload, field, bad):
    with pytest.raises(ValidationError):
        model_cls.model_validate({**payload, field: bad})


# --- Query.digest() ---

def test_query_digest_is_64_hex_lowercase():
    d = Query.model_validate(_QUERY).digest()
    assert len(d) == 64
    assert all(c in "0123456789abcdef" for c in d)


def test_query_digest_deterministic():
    assert Query.model_validate(_QUERY).digest() == Query.model_validate(_QUERY).digest()


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_class", "container_migration"),
        ("language", "javascript"),
        ("build_system", "pnpm"),
        ("cve_id", "CVE-2026-9999"),
        ("affected_package", "lodash@4.17.21"),
        ("failure_mode", "test_fail"),
    ],
)
def test_query_digest_changes_with_each_field(field, value):
    # Perturbs ALL SIX fields — a digest() that canonicalizes only a subset
    # (e.g. the constant-return mutation `return "a"*64`) is killed here.
    base = Query.model_validate(_QUERY)
    perturbed = Query.model_validate({**_QUERY, field: value})
    assert base.digest() != perturbed.digest()


# --- RetrievalOutcome discriminated union ---

def test_rag_hit_happy():
    rh = RagHit.model_validate(_RAG_HIT)
    assert isinstance(rh.few_shot, SolvedExample)
    assert rh.score == 0.96


def test_rag_degraded_happy():
    rd = RagDegraded.model_validate(_RAG_DEGRADED)
    assert isinstance(rd.near_match, SolvedExample)


def test_rag_miss_is_bare():
    rm = RagMiss.model_validate(_RAG_MISS)
    assert rm.kind == "miss"
    assert set(rm.model_dump()) == {"kind"}


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "hit", "score": 0.9},        # missing few_shot
        {"kind": "degraded", "score": 0.7},   # missing near_match
    ],
)
def test_rag_hit_degraded_require_payload(payload):
    with pytest.raises(ValidationError):
        TypeAdapter(RetrievalOutcome).validate_python(payload)


def test_retrieval_outcome_routes_by_kind():
    adapter = TypeAdapter(RetrievalOutcome)
    assert isinstance(adapter.validate_python(_RAG_HIT), RagHit)
    assert isinstance(adapter.validate_python(_RAG_MISS), RagMiss)
    assert isinstance(adapter.validate_python(_RAG_DEGRADED), RagDegraded)


def test_retrieval_outcome_unknown_kind_rejected():
    with pytest.raises(ValidationError):
        TypeAdapter(RetrievalOutcome).validate_python({"kind": "exception", "trace": "..."})


# --- score range constraint (AC-17) ---

@pytest.mark.parametrize("score", [1.5, -1.5, 2.0])
def test_rag_hit_score_out_of_range_rejected(score):
    with pytest.raises(ValidationError):
        RagHit.model_validate({**_RAG_HIT, "score": score})


@pytest.mark.parametrize("score", [-1.0, 0.0, 0.85, 1.0])
def test_rag_hit_score_in_band_accepted(score):
    assert RagHit.model_validate({**_RAG_HIT, "score": score}).score == score


# --- TypecheckNodeSignal ---

def test_typecheck_signal_kind_pinned():
    assert TypecheckNodeSignal.model_validate(_TYPECHECK).kind == "typecheck.typescript"
```

Second unit file — `tests/unit/fallback/test_budget_models.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from codegenie.fallback.budget import BudgetSnapshot, BudgetToken

_UTC_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_TOKEN = {
    "precharged_tokens": 5_000,
    "precharged_dollars": Decimal("0.03"),
    "issued_at": _UTC_NOW,
}
_SNAPSHOT = {
    "consumed_tokens": 100,
    "consumed_dollars": Decimal("0.5"),
    "outstanding_tokens": 0,
    "cap_tokens": 1_000,
    "cap_dollars": Decimal("1.5"),
}


# --- extra="forbid" / frozen, parametrized over both budget models (AC-10) ---

@pytest.mark.parametrize("model_cls,payload", [(BudgetSnapshot, _SNAPSHOT), (BudgetToken, _TOKEN)])
def test_extra_keys_rejected(model_cls, payload):
    with pytest.raises(ValidationError):
        model_cls.model_validate({**payload, "shell": "rm"})


@pytest.mark.parametrize(
    "model_cls,payload,field",
    [(BudgetSnapshot, _SNAPSHOT, "consumed_tokens"), (BudgetToken, _TOKEN, "precharged_tokens")],
)
def test_frozen_rejects_assignment(model_cls, payload, field):
    instance = model_cls.model_validate(payload)
    with pytest.raises(ValidationError):
        setattr(instance, field, getattr(instance, field))  # type: ignore[misc]


# --- BudgetSnapshot invariants (AC-6 + AC-17) ---

def test_budget_snapshot_happy():
    assert BudgetSnapshot.model_validate(_SNAPSHOT).consumed_tokens == 100


def test_budget_snapshot_consumed_plus_outstanding_exceeds_cap_rejected():
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate(
            {**_SNAPSHOT, "consumed_tokens": 800, "outstanding_tokens": 300}
        )


def test_budget_snapshot_consumed_dollars_exceeds_cap_rejected():
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate({**_SNAPSHOT, "consumed_dollars": Decimal("2.0")})


def test_budget_snapshot_negative_dollars_rejected():
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate({**_SNAPSHOT, "consumed_dollars": Decimal("-0.5")})


def test_budget_snapshot_negative_tokens_rejected():  # AC-17
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate({**_SNAPSHOT, "consumed_tokens": -1})


# --- BudgetToken (AC-7 + AC-13 + AC-17 + AC-18) ---

def test_budget_token_happy():
    bt = BudgetToken.model_validate(_TOKEN)
    assert bt.precharged_tokens == 5_000
    assert bt.precharged_dollars == Decimal("0.03")


def test_budget_token_negative_precharged_tokens_rejected():  # AC-17
    with pytest.raises(ValidationError):
        BudgetToken.model_validate({**_TOKEN, "precharged_tokens": -1})


def test_budget_token_issued_at_naive_datetime_rejected():  # AC-13
    with pytest.raises(ValidationError):
        BudgetToken.model_validate({**_TOKEN, "issued_at": datetime(2026, 1, 1)})


def test_budget_token_marker_default():  # AC-18
    assert BudgetToken.model_validate(_TOKEN)._marker == "budget_token"


def test_budget_token_marker_not_serialized():  # AC-18 — PrivateAttr ⇒ not in model_dump()
    assert "_marker" not in BudgetToken.model_validate(_TOKEN).model_dump()


def test_budget_token_forged_marker_rejected():  # AC-18 — capability cannot be injected
    with pytest.raises(ValidationError):
        BudgetToken.model_validate({**_TOKEN, "_marker": "forged"})
```

The `Query.digest()` Hypothesis property (AC-11) — **all six fields are drawn from strategies**, not just `cve_id`:

```python
# tests/property/test_query_digest_determinism.py
from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from codegenie.rag.models import Query

_FAILURE_MODES = [
    "build_break", "test_fail", "typecheck_fail",
    "lockfile_resolution_fail", "callsite_signature_drift", "policy_block",
]
_BUILD_SYSTEMS = ["bun", "pnpm", "yarn-classic", "yarn-berry", "npm"]

# Every one of Query's six fields is generated — a digest() that
# canonicalizes a subset of fields is killed by the perturbation property.
_query_payload = st.builds(
    dict,
    task_class=st.sampled_from(["vuln_remediation", "container_migration"]),
    language=st.sampled_from(["typescript", "javascript"]),
    build_system=st.sampled_from(_BUILD_SYSTEMS),
    cve_id=st.from_regex(r"^CVE-\d{4}-\d{4,7}$", fullmatch=True),
    affected_package=st.from_regex(r"^[a-z][a-z0-9-]{0,20}@\d+\.\d+\.\d+$", fullmatch=True),
    failure_mode=st.sampled_from(_FAILURE_MODES),
)


@given(payload=_query_payload)
def test_query_digest_is_pure_and_64_hex(payload):
    d1 = Query.model_validate(payload).digest()
    d2 = Query.model_validate(payload).digest()
    assert d1 == d2  # purity
    assert len(d1) == 64 and all(c in "0123456789abcdef" for c in d1)


@given(payload=_query_payload, other_cve=st.from_regex(r"^CVE-\d{4}-\d{4,7}$", fullmatch=True))
def test_query_digest_sensitive_to_cve(payload, other_cve):
    # Metamorphic relation: digests are equal iff the perturbed field is equal.
    q = Query.model_validate(payload)
    perturbed = Query.model_validate({**payload, "cve_id": other_cve})
    assert (q.digest() == perturbed.digest()) == (payload["cve_id"] == other_cve)
```

The `SolvedExample` JSON round-trip (AC-12) — concrete example-based; the full
`from_yaml(to_yaml(x)) == x` Hypothesis property lands in S4-04:

```python
# tests/property/test_solved_example_yaml_roundtrip.py
from __future__ import annotations

from datetime import UTC, datetime

from codegenie.rag.models import SolvedExample

_HEX64 = "a" * 64
_SOLVED = {
    "id": _HEX64,
    "task_class": "vuln_remediation",
    "language": "typescript",
    "build_system": "npm",
    "cve_id": "CVE-2026-1234",
    "advisory_digest": _HEX64,
    "plan_kind": "dep_bump",
    "plan_proposal": {
        "kind": "dep_bump",
        "manifest_path": "package.json",
        "package": "lodash@4.17.21",
        "target_version": "4.17.21",
        "rationale": "x",
    },
    "transform_digest": _HEX64,
    "trust_outcome_digest": _HEX64,
    "provenance": {
        "workflow_id": "01HXX00000000000000000000Z",
        "event_chain_head": _HEX64,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "signing_method": "hmac_sha256_chain",
    },
    "origin": "llm_solved",
    "embedding_model": "bge-small-en-v1.5",
    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
}


def test_solved_example_json_roundtrip():
    original = SolvedExample.model_validate(_SOLVED)
    restored = SolvedExample.model_validate_json(original.model_dump_json())
    assert restored == original  # deep equal — proves the shape is serialisable
```

State why it fails: `ImportError` — `codegenie.rag.models`, `codegenie.fallback.budget` don't exist.

### Green — make it pass

- Create `rag/__init__.py`, `rag/models.py`, `fallback/budget.py`.
- Wire types, validators, and `digest()` implementation. Use `blake3` for the digest (already a project dep).
- Export from `__init__.py` modules.

### Refactor — clean up

- Lift the literal sets to module-level `Final` constants where they recur (e.g., `_FAILURE_MODE_TAGS: Final[tuple[str, ...]]`).
- Docstring each model naming the contract surface ("CONTRACT — persisted in chromadb; Phase 5 reads `.digest()`; ADR-0016.").
- The `_marker` `PrivateAttr` on `BudgetToken` carries the inline comment naming S2-05 (the issuer) and the import-linter contract; the docstring records that it is a private, non-serialized capability discriminator (ADR-0010).
- Edge cases enumerated in arch that touch this code: #14 (chain-orphan — `RecordProvenance.event_chain_head` carries the chain anchor used in S5-03 exclusion), #19 (model-mismatch — `SolvedExample.embedding_model: ModelId` is the field compared against `embedder.model_digest()` in S5-03). The chain-orphan / model-mismatch *retrieval* outcome is a bare `RagMiss` plus an emitted event (`RagRecordChainOrphan` / `RagRecordModelMismatch`) — `RagMiss` itself stays payload-less per ADR-0008.
- Naming alignment is already resolved (see Notes): use `TaskClassId`, `Language`, `PackageManager` — the existing canonical names; record the arch-doc drift in the attempt log.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/__init__.py` | NEW — package skeleton; re-exports the five RAG-side models. |
| `src/codegenie/rag/models.py` | NEW — `SolvedExample`, `Query`, `RecordProvenance`, `RetrievalOutcome` (`RagHit`/`RagMiss`/`RagDegraded`), `TypecheckNodeSignal`, `FailureModeTag`. |
| `src/codegenie/fallback/budget.py` | NEW — `BudgetSnapshot`, `BudgetToken` shapes (issuer logic deferred to S2-05). |
| `src/codegenie/fallback/__init__.py` | Add `BudgetSnapshot`/`BudgetToken` to exports (the `fallback/` package + its `__init__.py` are created by S1-02 — this story modifies it). |
| `tests/unit/rag/__init__.py` | NEW — package marker. |
| `tests/unit/fallback/__init__.py` | NEW (if absent) — package marker. `tests/unit/fallback/` does not yet exist; S1-02/S1-03 may create it first, but this story cannot assume that, so create-if-absent. |
| `tests/unit/rag/test_models.py` | NEW — happy/sad paths for the five RAG-side models; `extra="forbid"`/`frozen`/`Literal`/keyset parametrized over every model. |
| `tests/unit/fallback/test_budget_models.py` | NEW — `BudgetSnapshot` invariants; `BudgetToken` shape + range + `_marker` `PrivateAttr` behavior. |
| `tests/property/test_query_digest_determinism.py` | NEW — Hypothesis purity over all six fields + metamorphic field-sensitivity. |
| `tests/property/test_solved_example_yaml_roundtrip.py` | NEW — concrete JSON round-trip; the full YAML-roundtrip Hypothesis property lands in S4-04. |

## Out of scope

- **`SolvedExampleStore` Protocol + `ChromaPersistentStore`** — S4-03 (consumes `SolvedExample`).
- **`SolvedExampleRetriever.query`** — S5-01 (consumes `Query` + emits `RetrievalOutcome`).
- **`LlmInvocationGuard.precharge/reconcile`** — S2-05 (issues `BudgetToken`; emits `BudgetSnapshot`).
- **`RecordProvenance.verify(record, spanning_log) -> bool`** — S4-05 (this story ships only the model, not the chain-verify logic).
- **YAML serialization of `SolvedExample` to `.codegenie/rag/records/<id>.yaml`** — S4-04.
- **`TypecheckTypescriptSignal` collector** — S6-05 (this story ships the model; the collector wraps `tsc` and `@register_signal_kind`s it).
- **Path-scoped fence amendment** — S1-05 (no chromadb / fastembed import yet — this story is pure Pydantic).

## Notes for the implementer

- **Canonical field-type names are resolved (validator, Rule 7 + Rule 11).** Arch §Data model uses `TaskClassName`/`LanguageName`/`BuildSystemName`; `codegenie.types.identifiers` ships **`TaskClassId`**, **`Language`**, **`PackageManager`** and none of the `*Name` variants. The existing canonical names win — `task_class: TaskClassId`, `language: Language`, `build_system: PackageManager`. Note the arch-doc drift in the attempt log; the arch doc should be corrected separately (same drift S1-02/S1-03 already flagged for `SandboxedRelativePath`/`RecipeOutcome`).
- **`PackageManager` is a `Literal`, not an `Enum` (ADR-0013).** It is `Literal["bun", "pnpm", "yarn-classic", "yarn-berry", "npm"]`, defined in `codegenie.types.identifiers` (ADR-0013 Amendment 2026-05-20 moved it there from `probes.node_build_system`). **Import it from `codegenie.types.identifiers`**, never `probes.node_build_system`, never redefine. There is no `.NPM`/`.value` member — fixture and call-site code uses the bare string (`"npm"`). The field type `build_system: PackageManager` is correct (Pydantic validates a `Literal`).
- **`Query.digest()` must be deterministic across runs.** BLAKE3-hex over `self.model_dump_json()`. Pydantic v2 emits fields in **definition order** — stable across runs for a frozen model — so no explicit key sort is needed; do **not** assume `model_dump_json` sorts keys. The AC-11 Hypothesis purity property + the six-field perturbation parametrization are the mutation guards (they kill a constant-return or subset-canonicalizing `digest()`).
- **tz-aware datetime is mandatory on all three datetime fields.** A naive `datetime` silently breaks chain-verify across timezone-shifted CI runners. One reusable validator (a shared `@field_validator` helper or an `Annotated` datetime alias) rejecting `v.tzinfo is None` covers `SolvedExample.created_at`, `RecordProvenance.created_at`, and `BudgetToken.issued_at` — do not copy the check three times.
- **`BudgetToken` shape is ADR-0010 §Decision + arch §Component 5 verbatim.** Fields: `precharged_tokens`, `precharged_dollars`, `issued_at`, `_marker`. No `id` field — ADR-0010's token is id-less; `LlmInvocationGuard` keys `outstanding_tokens` by `BudgetTokenId` externally. Do not add fields the ADR does not have.
- **`BudgetToken._marker` is a Pydantic v2 `PrivateAttr` — this is deliberate (ADR-0010 says "private").** A leading-underscore annotation in a Pydantic v2 model is *not* a validated field: it is absent from `model_dump()`, not constructor-settable, and not protected by `frozen=True`. Declare it explicitly: `_marker: Literal["budget_token"] = PrivateAttr(default="budget_token")`. S2-05's import-linter contract is the *containment* control and its AST-walk reads source text (where the annotation is visible) — so the `PrivateAttr` choice is fine; just do not expect `_marker` in runtime `model_fields`/`model_dump()`. AC-18's tests pin this. Do not rename it to a public field — that would contradict ADR-0010 (surface per Rule 7 if you believe it should be public).
- **`RetrievalOutcome` shape is ADR-0008 §Decision + arch §Component 9 verbatim.** `RagHit(kind, few_shot, score)`, `RagDegraded(kind, near_match, score)`, `RagMiss(kind)` **bare**. The `few_shot` vs `near_match` field-name difference is intentional (ADR-0008 §Pattern-fit) — `RagHit` carries a confident few-shot, `RagDegraded` carries a near-match. Use `Field(discriminator="kind")` (not `Discriminator("kind")`) — the implemented repo convention (`transforms/outcomes.py`, whose docstring names it "the single repo convention"; S1-02/S1-03 corrected the same arch-doc drift). A `RagDegraded`/`RagHit` without its payload is a model bug — AC-10 tests it.
- **`score` / `TokenCount` range constraints (AC-17).** `Similarity` and `TokenCount` are `NewType`s; Pydantic v2 sees only the base `float`/`int` and does NOT re-validate the smart-constructor range. `RetrievalOutcome` is built *internally* by `SolvedExampleRetriever` from a raw ChromaDB score — that float never passes `parse_similarity` — so type the `score` field `Annotated[Similarity, Field(ge=-1.0, le=1.0)]` and the `TokenCount` fields `Annotated[TokenCount, Field(ge=0)]`. This is the established repo idiom (`scip_slice.py`, `sandbox_jail.py`, `redacted_slice.py`) and keeps the nominal `NewType`.
- **`RecordProvenance.signing_method` literal set is unsourced — verify before GREEN (Rule 8 + Rule 12).** Neither ADR-0016 nor arch §Data model enumerates `signing_method`. `RecordProvenance` is first fully specified here. Confirm `"hmac_sha256_chain"` matches the actual Phase-3 spanning-log chain implementation (the `ChainHead` newtype is BLAKE3; the *signing* method is a separate concern). If it does not match, surface per Rule 7 and correct the literal; do not ship a contract field whose values you could not verify.
- **`FailureModeTag` placement (validator, Rule 7).** Ship `FailureModeTag = Literal[...]` rag-local at the top of `rag/models.py`. Two repo conventions compete: closed-set `Literal`s like `PackageManager`/`Ecosystem` live in `codegenie.types.identifiers`, but domain *reason* taxonomies (`NotApplicableReason`, `EscalationReason` in `transforms/outcomes.py`) are kept module-local. `FailureModeTag` is a remediation-failure vocabulary — closer to the reason-taxonomy precedent — so rag-local is the call. Document the choice + the competing precedent in the attempt log; do not silently average.
- **`BudgetSnapshot` invariants are validated at construction.** Pydantic v2 `@model_validator(mode="after")` runs after type coercion; raises `ValidationError`. The `consumed_tokens + outstanding_tokens <= cap_tokens` invariant is the load-bearing one Phase 5's running-total projection consumes.
- **`TypecheckNodeSignal` location.** Arch §Component 11 puts the *collector* in the plugin (`plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py`); the *model* is generic and ships here at `src/codegenie/rag/models.py`. ADR-0015 anticipates Phase-7 plugins reusing the model. A short docstring noting it is substrate-resident-for-reuse (not RAG-specific) helps the next reader.
- **No shared `FrozenModel` base — repeat `ConfigDict` inline.** The codebase has consciously not extracted a frozen base across 40+ models (`transforms/outcomes.py`, every `layer_*` probe model, `vuln_index/models.py`, …); each repeats `model_config = ConfigDict(frozen=True, extra="forbid")`. Match that (Rule 11) — do **not** introduce a base class.
- **Do not import `chromadb`/`fastembed`/`onnxruntime`** in this story's files. The path-scoped fence (S1-05) admits them only under `src/codegenie/rag/` modules that *need* them (`store.py`, `embedder.py`). `models.py` is pure Pydantic; pulling chromadb in here would trigger the fence-CI failure.
- **Newtypes everywhere.** Every field that names a domain primitive is typed against an existing newtype from `codegenie.types.identifiers`. The AST source-scan from S1-01 (`test_phase4_no_raw_str_for_domain_ids.py`) re-runs after this story lands and must remain green.
