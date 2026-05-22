# Story S4-06 - `SolvedExampleWriter` + Phase-4-local capability mint

**Step:** Step 4 - Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-01 (Phase-4 domain newtypes), S1-04 (`SolvedExample` / `RecordProvenance` / retrieval models), S4-03 (`SolvedExampleStore.add(example, capability)`), S4-04 (canonical YAML + manifest digest), S4-05 (`RecordProvenance` verifier + event-log API alignment)
**ADRs honored:** ADR-0016 (write-gated `add()`; canonical record store), ADR-0009 (inline auto-harvest gate; writer is the receiving surface), final-design Component 9 ("Module Boundary pattern with CI enforcement")

## Validation notes

Refined by `phase-story-validator` on 2026-05-22. Full report: `./_validation/S4-06-ingest-capability-mint.md`.

The validator addressed **4 block, 9 harden, and 1 nit** findings. The important corrections are:

- `import-linter` cannot enforce imports of a function symbol such as `_phase4_local_capability_mint`; this story uses an AST fence for symbol-level scope and keeps `make lint-imports` green through the existing `pyproject.toml` import-linter config.
- `SolvedExampleHarvested` belongs in `src/codegenie/plugins/events.py` and uses the shipped event API (`event_type`, typed event unions, `emit_spanning`), not a new `src/codegenie/rag/events.py` module with a `kind` field.
- `ValidatedPlanOutcome`, `SolvedExample`, and `RecordProvenance` must reuse the S1-01/S1-04 names and fields. Do not reintroduce `TaskClassName`, `LanguageName`, `BuildSystemName`, `record_chain_head`, `model_id`, `embedding_dim`, `trust_outcome_passed`, or `confidence` on `RecordProvenance`.
- The writer remains silent. S6-03 owns the inline harvest gate and event emission; this story only provides the writer, the temporary mint, and the event class S6-03 will emit.

## Context

S4-03 declared `SolvedExampleWriteCapability` as a `@final` frozen dataclass marker. ADR-0016 requires `store.add(example, capability)` calls to be mint-gated: the production codebase should only construct write capabilities from `src/codegenie/rag/ingest.py` during Phase 4 and from `src/codegenie/gates/` once Phase 5 lands.

This is intentionally not a true object-capability runtime. Python code can still construct `SolvedExampleWriteCapability(...)` directly. The design pattern is a **module boundary with CI enforcement**:

- the public writer surface accepts a capability and does not know who minted it;
- the temporary Phase-4 mint is private by name and location;
- a source-level AST fence rejects forbidden imports/usages of `_phase4_local_capability_mint`;
- review policy treats edits to that fence and to the future gates mint as security-sensitive.

The original phase prose sometimes says "import-linter blocks importing the minting symbol." That is shorthand, not an executable import-linter contract: import-linter works on modules/packages, not individual functions. The executable enforcement in this story is the AST fence in `tests/fence/test_capability_mint_scoped.py`. `make lint-imports` still runs against `pyproject.toml` to preserve the phase's module-layering checks.

## References - where to look

- `../High-level-impl.md` Step 4 - `SolvedExampleWriter`, `SolvedExampleWriteCapability`, and the Phase-4-local mint.
- `../phase-arch-design.md` Component 10 and "Sequence - Scenario 2" - inline harvest calls the local mint, then the writer.
- `../final-design.md` Component 9 - names the pattern as module-boundary enforcement, not runtime unforgeability.
- `../ADRs/0009-inline-auto-harvest-confidence-gate.md` - S6-03 gates on `TrustOutcome.passed AND confidence == "high"` and calls this writer.
- `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` - `SolvedExampleStore.add(example, capability)` and canonical YAML store.
- `src/codegenie/plugins/events.py` - actual event model API: `event_type`, `WorkflowInternalEvent`, `WorkflowSpanningEvent`, `emit_internal`, `emit_spanning`, `_INTERNAL_CLASSES`, `_SPANNING_CLASSES`.
- `pyproject.toml` - existing import-linter config. There is no `.importlinter` file in this repo.
- `tests/fence/test_phase3_importlinter_contracts_shape.py` and `tests/fence/test_phase7_importlinter_contracts_shape.py` - shape-test precedent for import-linter configuration.

## Goal

Ship the Phase-4 ingestion writer in `src/codegenie/rag/ingest.py`, plus a temporary local capability mint and symbol-scope fence. The writer converts a validated fallback outcome into a canonical `SolvedExample`, embeds it, writes it through `SolvedExampleStore.add(example, capability)`, and returns the `SolvedExampleId`.

## Acceptance criteria

- [ ] **AC-1 - `ingest_solved_example` signature and behavior.** `src/codegenie/rag/ingest.py` exports a kwargs-only async writer:
  ```python
  async def ingest_solved_example(
      *,
      outcome: ValidatedPlanOutcome,
      store: SolvedExampleStore,
      embedder: Embedder,
      capability: SolvedExampleWriteCapability,
  ) -> SolvedExampleId: ...
  ```
  The function:
  1. gets the model id with `embedding_model = embedder.model_digest()`;
  2. materializes `embedding_vector = embedder.embed(outcome.query_text)`;
  3. constructs the S1-04 `SolvedExample` shape, including `embedding_vector`;
  4. calls `await store.add(example, capability)`;
  5. returns the `SolvedExampleId` returned by the store.

- [ ] **AC-2 - `ValidatedPlanOutcome` projection is typed and minimal.** If no suitable validated outcome variant already exists, define a frozen dataclass in `src/codegenie/rag/ingest.py` with only the fields the writer needs:
  ```python
  @dataclass(frozen=True, slots=True)
  class ValidatedPlanOutcome:
      workflow_id: WorkflowId
      event_chain_head: ChainHead
      query_text: str
      task_class: TaskClassId
      language: Language
      build_system: PackageManager
      cve_id: CveId
      advisory_digest: BlobDigest
      plan_proposal: PlanProposal
      transform_digest: BlobDigest
      trust_outcome_digest: BlobDigest
      confidence: Literal["high", "medium", "low"]
  ```
  Reuse canonical types from `codegenie.types.identifiers`; do not define `TaskClassName`, `LanguageName`, or `BuildSystemName`. If a first-class `QueryText` newtype exists by implementation time, use it instead of raw `str`; do not introduce an untyped dict projection.

- [ ] **AC-3 - `SolvedExample` and `RecordProvenance` fields match S1-04.** The writer mirrors S1-04 exactly:
  - `SolvedExample` includes `id`, `task_class`, `language`, `build_system`, `cve_id`, `advisory_digest`, `plan_kind`, `plan_proposal`, `transform_digest`, `trust_outcome_digest`, `provenance`, `origin`, `embedding_model`, `created_at`, and `embedding_vector`.
  - `RecordProvenance` is constructed with exactly `workflow_id`, `event_chain_head`, `created_at`, and `signing_method`.
  - The writer must not read or write stale provenance fields: `record_chain_head`, `model_id`, `embedding_dim`, `trust_outcome_passed`, or `confidence`.

- [ ] **AC-4 - Deterministic `SolvedExampleId`.** Add a pure helper:
  ```python
  def _solved_example_id_for(
      *,
      outcome: ValidatedPlanOutcome,
      embedding_model: ModelId,
  ) -> SolvedExampleId: ...
  ```
  The ID preimage is canonical and deterministic over stable identity fields only: `advisory_digest`, `transform_digest`, `embedding_model`, `plan_kind`, and a stable digest/serialization of `plan_proposal`. It must not include `workflow_id`, `event_chain_head`, `created_at`, or other per-run values. Route hashing through the repo's canonical hashing helper instead of importing `blake3` directly if such a helper exists.

- [ ] **AC-5 - Phase-4-local mint shape.** `src/codegenie/rag/ingest.py` defines:
  ```python
  def _phase4_local_capability_mint(
      *,
      workflow_id: WorkflowId,
      chain_head: ChainHead,
  ) -> SolvedExampleWriteCapability:
      """Phase-4-local mint.

      TODO(phase-5): replace callsites with
      `codegenie.gates._capability_mint.mint_solved_example_capability`
      once GateRunner owns validated harvests. `chain_head` is accepted
      now so the Phase-5 signature swap is mechanical; the Phase-4 marker
      carries only `workflow_id`.
      """
  ```
  The function returns `SolvedExampleWriteCapability(workflow_id=workflow_id)` and intentionally discards `chain_head` in Phase 4.

- [ ] **AC-6 - Symbol-scope fence for the mint.** Add `tests/fence/test_capability_mint_scoped.py`. It must scan production source with `ast` and fail if any file outside these paths imports or references `_phase4_local_capability_mint`:
  - `src/codegenie/rag/ingest.py`
  - `src/codegenie/gates/**` (Phase 5 allowlist; may be absent today)
  The scanner must catch both forms:
  - `from codegenie.rag.ingest import _phase4_local_capability_mint`
  - `codegenie.rag.ingest._phase4_local_capability_mint(...)`

- [ ] **AC-7 - Deliberate violation proves the fence, not default lint.** Add a small fixture source string or fixture file containing a forbidden mint import, and unit-test the shared AST scanner against it. Do not add a real violating module to the default import-linter corpus, and do not make `make lint-imports` depend on an env var to fail intentionally. `make lint-imports` must remain a normal green command.

- [ ] **AC-8 - Existing import-linter config remains green.** The implementation does not create `.importlinter`. If a config change is needed, edit `pyproject.toml` using the existing `[[tool.importlinter.contracts]]` shape and add/adjust a shape test. Do not add a fake `forbidden_modules = codegenie.rag.ingest._phase4_local_capability_mint` entry; import-linter cannot target that function.

- [ ] **AC-9 - `SolvedExampleHarvested` event class uses the shipped event API.** Extend `src/codegenie/plugins/events.py` with a spanning event class that S6-03 can emit after a successful write:
  ```python
  class SolvedExampleHarvested(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")

      event_type: Literal["solved_example_harvested"] = "solved_example_harvested"
      event_id: EventId
      workflow_id: WorkflowId
      timestamp: datetime
      prev_hash: BlobDigest
      solved_example_id: SolvedExampleId
      record_event_chain_head: ChainHead
      embedding_model: ModelId
      origin: Literal["llm_solved"] = "llm_solved"
  ```
  Register it in `WorkflowSpanningEvent`, `_SPANNING_CLASSES`, and `__all__`. The writer does not emit the event; the caller emits it in S6-03. `record_event_chain_head` is the validate-time `outcome.event_chain_head`, not a future harvest-event head.

- [ ] **AC-10 - Unit tests cover the writer contract.** Add `tests/unit/rag/test_ingest.py` with:
  - happy path: fake outcome, fake embedder, fake store spy; asserts store receives a full `SolvedExample` and the exact capability object passed in;
  - idempotence: same outcome and embedder model produce the same `SolvedExampleId`;
  - mint shape: `_phase4_local_capability_mint(workflow_id=..., chain_head=...)` returns a capability with the expected `workflow_id`;
  - documented limitation: constructing `SolvedExampleWriteCapability(...)` directly can still call `store.add(...)`; the test docstring states that unforgeability is a CI/review boundary, not a runtime guarantee.

- [ ] **AC-11 - Event registration tests cover replay.** Extend `tests/unit/plugins/test_events.py` (or the local event test file used by the repo) to assert:
  - `"solved_example_harvested"` is present in the spanning event discriminator mapping;
  - `EventLog.emit_spanning(...)` followed by replay round-trips `SolvedExampleHarvested`;
  - missing `prev_hash` is rejected, matching the existing spanning-event contract.

- [ ] **AC-12 - Lint, type, and fence checks pass.** Run:
  - `ruff check`
  - `ruff format --check`
  - `mypy --strict`
  - `make lint-imports`
  - `pytest tests/unit/rag/test_ingest.py tests/fence/test_capability_mint_scoped.py tests/unit/plugins/test_events.py`

## Implementation outline

1. **Define the small projection.** Prefer an existing validated outcome variant if it already carries the fields in AC-2. Otherwise define `ValidatedPlanOutcome` locally in `rag/ingest.py` and mark the attempt log with the integration note for S6-03.

2. **Implement deterministic identity as a functional core.** `_solved_example_id_for(...)` should be pure, have no clock or filesystem dependency, and use a canonical serializer. Keep the preimage in one private helper so S4-04/S5 integration can audit any future identity expansion.

3. **Construct the model in the writer shell.** `ingest_solved_example(...)` is the imperative shell: call the embedder, get `datetime.now(timezone.utc)` once for `created_at`, build `RecordProvenance`, build `SolvedExample`, call `store.add`, and return.

4. **Keep capability creation tiny.** `_phase4_local_capability_mint(...)` should be one return statement plus the Phase-5 TODO docstring. Do not put minting on `SolvedExampleWriteCapability` as a classmethod; that would make the mint reachable anywhere the class is imported.

5. **Use an AST fence for the private symbol.** Implement a reusable helper inside `tests/fence/test_capability_mint_scoped.py`, for example `_mint_scope_violations(paths: Iterable[Path]) -> list[str]`. Test it against production source and against a deliberate fixture/source string.

6. **Register the event by extension.** Add `SolvedExampleHarvested` to the existing plugin event module and unions. Do not create `src/codegenie/rag/events.py`.

## TDD plan - red / green / refactor

### Red

- Write `tests/unit/rag/test_ingest.py` first. The happy-path test should fail because `src/codegenie/rag/ingest.py` does not exist.
- Write `tests/fence/test_capability_mint_scoped.py`. The production scan should fail until the module and allowlist behavior are implemented.
- Extend event tests for `SolvedExampleHarvested`. They should fail until `plugins/events.py` is extended.

### Green

- Add `src/codegenie/rag/ingest.py` with the projection, ID helper, writer, and local mint.
- Add the AST fence helper and deliberate violation test.
- Add `SolvedExampleHarvested` to `src/codegenie/plugins/events.py` and its union/registration paths.
- Run the commands in AC-12.

### Refactor

- Keep `ingest.py` small. If helper code grows, extract only pure serialization/identity helpers; do not introduce a registry or plugin mechanism until more than one writer exists.
- Keep test fakes typed. Avoid `Any`, untyped dict fixtures, and mutable record shuffling.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/ingest.py` | `ValidatedPlanOutcome`, `ingest_solved_example`, `_solved_example_id_for`, `_phase4_local_capability_mint`. |
| `src/codegenie/plugins/events.py` | Add and register `SolvedExampleHarvested` as a spanning event. |
| `tests/unit/rag/test_ingest.py` | Writer behavior, deterministic ID, mint shape, documented runtime limitation. |
| `tests/fence/test_capability_mint_scoped.py` | Symbol-scope AST fence and deliberate violation proof. |
| `tests/unit/plugins/test_events.py` | Event registration and replay coverage. |
| `pyproject.toml` | Only if an existing import-linter shape test requires a config adjustment; do not create `.importlinter`. |

## Out of scope

- Phase-5 production mint in `src/codegenie/gates/_capability_mint.py`.
- Inline-harvest gate logic (`TrustOutcome.passed AND confidence == "high"`), owned by S6-03.
- Emitting `SolvedExampleHarvested`, `HarvestSkipped(reason=low_confidence)`, or `HarvestSkipped(reason=write_contention)`, all owned by S6-03.
- Runtime prevention of hand-forged capabilities.
- A generic plugin/registry system for solved-example writers. One writer exists in Phase 4; a registry would add surface area before there is a second implementation.

## Notes for the implementer

### 1. The mint is a function, not a method

Do not add `SolvedExampleWriteCapability.mint(...)`. A classmethod is reachable anywhere the class is imported and defeats the module-boundary design. The private function path is the boundary the AST fence can inspect.

### 2. ID determinism beats full-record hashing for this path

S1-01/S4-04 use "content addressed" language around canonical records. For ingestion idempotence, this story's ID helper must hash a stable identity preimage, not the full serialized record. Full records contain per-run values such as `created_at` and `workflow_id`; hashing them would make duplicate successful outcomes create different IDs.

If an executor discovers a stricter already-landed `SolvedExampleId` rule that requires full-body hashing, stop and surface the conflict instead of silently making ingestion non-idempotent.

### 3. The event is spanning; the writer is silent

`SolvedExampleHarvested` records a corpus mutation that S6-03 emits after the write. It belongs in the spanning event stream. The writer must not emit it because that would make the writer know about `EventLog`, split write ownership, and make tests pass without the real fallback caller proving its event behavior.

### 4. Import-linter is still useful, but not for this symbol

Keep `make lint-imports` as part of verification. It protects package-level layering. The mint boundary is narrower than package layering, so the AST fence is the precise enforcement tool here.

### 5. Capability limitation is deliberate

A future reviewer may try to reject hand-forged `SolvedExampleWriteCapability(...)` at runtime. Do not add that check in this story. The phase explicitly chose a CI/review boundary for Phase 4 and a production mint in Phase 5. If the design changes, that should be a new ADR or a Phase-5 story change, not an opportunistic runtime check here.
