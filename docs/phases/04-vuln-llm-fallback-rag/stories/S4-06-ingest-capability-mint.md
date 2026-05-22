# Story S4-06 - `SolvedExampleWriter` + phase-4 capability mint boundary

**Step:** Step 4 - Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-01 (`SolvedExampleId`, `WorkflowId`, `ChainHead`, `BlobDigest`, `ModelId`, `LeafResponseId` newtypes), S1-02 (`PlanProposal`), S1-03 (`PlanOutcome` lineage / validated-outcome projection), S1-04 (`SolvedExample` / `RecordProvenance` exact field shapes, including the S4-03-required `embedding_vector` amendment), S1-06 (`pyproject.toml` import-linter contract precedent), S4-01 (`Embedder` Protocol), S4-03 (`SolvedExampleStore` + `SolvedExampleWriteCapability`), S4-04 (canonical YAML / manifest chain head), S4-05 (`RecordProvenance.verify` contract)
**ADRs honored:** ADR-0016 (write-gated `add()` and YAML-canonical solved examples), ADR-0009 (inline auto-harvest only after `TrustOutcome.passed AND confidence == "high"`; caller owns the gate), ADR-0003 (module-boundary enforcement via lint + tests), final-design Component 9 ("Module Boundary pattern with CI enforcement")

## Validation notes

Validated: 2026-05-22 13:45 EDT
Verdict: HARDENED
Findings addressed: 18 - 5 block, 10 harden, 3 nit

Changes applied:
- **Mint boundary made mechanically enforceable (block).** The draft put `_phase4_local_capability_mint` in `ingest.py` and tried to forbid imports of a function symbol. `import-linter` is module-level, not symbol-level. The hardened story moves the mint to `src/codegenie/rag/_capability_mint.py`, has `ingest.py` import that private module by alias, and pins a module-level import-linter contract plus AST fence.
- **`pyproject.toml`, not `.importlinter` (block).** The repo has no `.importlinter`; the live config is `pyproject.toml [tool.importlinter]`. ACs and tests now mirror the S1-06 / Phase-3 shape-test precedent.
- **No forward unmatched `ignore_imports` (block).** Pre-allowing future `codegenie.gates.*` imports would break `lint-imports` under import-linter 2.x. The contract allows only the real S4-06 edge (`codegenie.rag.ingest -> codegenie.rag._capability_mint`); Phase 5 appends a gates edge when that module exists.
- **Model-shape drift fixed (block).** The implementation outline now populates S1-04's hardened `RecordProvenance` fields only: `workflow_id`, `event_chain_head`, `created_at`, `signing_method`. Stale fields like `record_chain_head`, `model_id`, `embedding_dim`, `trust_outcome_passed`, and `confidence` are forbidden.
- **Event surface corrected (block).** `SolvedExampleHarvested` is registered in `src/codegenie/plugins/events.py` as a `WorkflowInternalEvent` with `event_type`, not in a new `src/codegenie/rag/events.py` module with `kind`.
- **Outcome projection typed.** The placeholder uses existing kernel names (`TaskClassId`, `Language`, `PackageManager`) and includes every field needed to build a `SolvedExample`, including `advisory_digest` and `chain_head`.
- **Functional core / imperative shell sharpened.** `_solved_example_id_for` and `_solved_example_from_outcome` are pure helpers; `ingest_solved_example` is the shell that embeds and calls `store.add(...)`.
- **Tests made mutation-resistant.** Added deterministic-ID property, exact-field stale-name AST guard, event-union round-trip, import-linter shape test, and live-fire planted violation using the established `lint-imports` console-script pattern.

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S4-06-ingest-capability-mint.md

## Context

S4-03 declares `SolvedExampleWriteCapability` as a frozen marker consumed by `SolvedExampleStore.add(example, capability)`. Python cannot make that marker runtime-unforgeable: any in-process module can construct `SolvedExampleWriteCapability(workflow_id=...)`. The honest control, per final-design Component 9 and ADR-0003, is a **Module Boundary pattern with CI enforcement**:

- The write path requires the capability argument.
- The only S4-06 mint lives in a private module, `src/codegenie/rag/_capability_mint.py`.
- `pyproject.toml [tool.importlinter]` forbids imports of that private module from `codegenie` except the real S4-06 edge: `codegenie.rag.ingest -> codegenie.rag._capability_mint`.
- AST fence tests catch symbol-level bypasses that import-linter cannot see, including `from codegenie.rag.ingest import _phase4_local_capability_mint`.

The private-module location is a validator correction to the arch prose. The arch says the factory is under `ingest.py`, but import-linter cannot forbid a single function inside a public module while still allowing imports of `ingest_solved_example`. Moving the mint into a one-purpose private module preserves the design intent and makes the boundary testable.

S4-06 also lands the writer surface:

```python
async def ingest_solved_example(
    *,
    outcome: ValidatedPlanOutcome,
    store: SolvedExampleStore,
    embedder: Embedder,
    capability: SolvedExampleWriteCapability,
) -> SolvedExampleId: ...
```

The caller owns the confidence gate (`TrustOutcome.passed AND confidence == "high"`) and event emission. This writer is deliberately silent: no `EventLog`, no `SolvedExampleHarvested` emission, no `HarvestSkipped`. It builds a canonical `SolvedExample`, embeds `outcome.query_text`, calls `await store.add(example, capability)`, and returns the `SolvedExampleId`.

`SolvedExampleHarvested` is still registered in this story because S6-03 needs a typed event to emit. Registration follows the actual Phase-3 event surface: `src/codegenie/plugins/events.py`, `WorkflowInternalEvent`, `_INTERNAL_CLASSES`, and `__all__`.

## References - where to look

- **Architecture:**
  - `../phase-arch-design.md` Component 10 - SolvedExampleWriter + capability; writer purpose and interim Phase-4 mint.
  - `../phase-arch-design.md` Sequence - Scenario 2; validated inline harvest path.
  - `../phase-arch-design.md` Design decisions and trade-offs; Phase-4-local mint shim and Phase-5 supersession.
- **Phase ADRs:**
  - `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` Consequences - `SolvedExampleStore.add(example, capability)` requires the capability; YAML records carry model/vector provenance.
  - `../ADRs/0003-path-scoped-fence-amendment.md` - module-boundary enforcement is lint/test time, not runtime capability security.
- **Source design:**
  - `../final-design.md` Component 9 - SolvedExampleWriter + SolvedExampleWriteCapability.
  - `../final-design.md` Inline auto-harvest - caller-side confidence gate.
- **Existing code and hardened precedents:**
  - `pyproject.toml [tool.importlinter]`, `Makefile lint-imports`, `tests/fence/test_phase3_importlinter_contracts_shape.py`, and `docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S1-06-import-linter-contracts.md` - import-linter config and test shape.
  - `src/codegenie/plugins/events.py` and `tests/unit/plugins/test_events.py` - typed event registration and replay pattern.
  - `docs/phases/04-vuln-llm-fallback-rag/stories/S1-04-rag-pydantic-models.md` - exact `SolvedExample` / `RecordProvenance` fields.
  - `docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S4-03-chroma-persistent-store.md` and `.../S4-04-yaml-canonical-and-manifest.md` - `embedding_vector` and canonical-YAML preconditions.

## Goal

Ship the Phase-4 solved-example writer and interim capability mint boundary:

1. `src/codegenie/rag/ingest.py` exposes `ValidatedPlanOutcome`, `_solved_example_id_for(...)`, and `ingest_solved_example(...)`.
2. `src/codegenie/rag/_capability_mint.py` exposes the private `_phase4_local_capability_mint(...)` shim used only by `ingest.py` in Phase 4 and superseded by Phase 5's gates mint.
3. `pyproject.toml` and fence tests enforce the mint boundary.
4. `src/codegenie/plugins/events.py` registers `SolvedExampleHarvested` for S6-03's caller-side emission.

## Acceptance criteria

- [ ] **AC-1 - `ValidatedPlanOutcome` is typed and sufficient.** `src/codegenie/rag/ingest.py` defines a frozen, extra-forbid Pydantic model or frozen dataclass named `ValidatedPlanOutcome` with no `dict[str, Any]` fields and no untyped payload escape hatch. It carries exactly the stable inputs needed to build a `SolvedExample`:
    ```python
    query_text: str
    plan_proposal: PlanProposal
    transform_digest: BlobDigest
    trust_outcome_digest: BlobDigest
    task_class: TaskClassId
    language: Language
    build_system: PackageManager
    cve_id: CveId
    advisory_digest: BlobDigest
    response_id: LeafResponseId
    chain_head: ChainHead
    ```
    Do not use stale names `TaskClassName`, `LanguageName`, or `BuildSystemName`. If S1-03 has already landed an equivalent validated-outcome variant, reuse or alias that type instead of duplicating it, but preserve this exact field availability through tests.
- [ ] **AC-2 - `ingest_solved_example` signature and writer behavior.** `src/codegenie/rag/ingest.py` exports:
    ```python
    async def ingest_solved_example(
        *,
        outcome: ValidatedPlanOutcome,
        store: SolvedExampleStore,
        embedder: Embedder,
        capability: SolvedExampleWriteCapability,
    ) -> SolvedExampleId: ...
    ```
    The function is keyword-only. It:
    1. calls `embedding_model_digest = embedder.model_digest()` exactly once;
    2. calls `vector = embedder.embed(outcome.query_text)` exactly once;
    3. builds a `SolvedExample` with S1-04's exact field set plus the S4-03-required `embedding_vector`;
    4. builds `RecordProvenance(workflow_id=capability.workflow_id, event_chain_head=outcome.chain_head, created_at=<utc-aware now>, signing_method="hmac_sha256_chain")`;
    5. calls `await store.add(example, capability)` exactly once;
    6. returns the `SolvedExampleId` returned by `store.add(...)`.
    It does **not** check `TrustOutcome.confidence`, does **not** emit `SolvedExampleHarvested`, and does **not** import or instantiate `EventLog`. S6-03 owns the gate and emission.
- [ ] **AC-3 - deterministic solved-example id helper.** `src/codegenie/rag/ingest.py` defines pure helper:
    ```python
    def _solved_example_id_for(
        *,
        outcome: ValidatedPlanOutcome,
        embedding_model: ModelId,
    ) -> SolvedExampleId: ...
    ```
    It BLAKE3-hashes canonical JSON bytes over exactly stable record-identity fields: `cve_id`, `advisory_digest`, `transform_digest`, `trust_outcome_digest`, and `embedding_model`. It must not include `workflow_id`, `chain_head`, `created_at`, `query_text`, or `response_id`. Tests assert the same outcome and embedding model produce the same id across two calls, while changing any one identity field changes the id.
- [ ] **AC-4 - no stale S1-04 provenance fields.** `tests/unit/rag/test_ingest.py` contains an AST/source guard over `codegenie.rag.ingest` forbidding these attribute names and constructor kwargs: `record_chain_head`, `model_id`, `embedding_dim`, `trust_outcome_passed`, `confidence`, `harvested_at`, and `solved_example_id` inside `RecordProvenance(...)`. The only provenance field read from the outcome is `chain_head`, and the only provenance field written from it is `event_chain_head`.
- [ ] **AC-5 - private Phase-4 mint module.** `src/codegenie/rag/_capability_mint.py` defines:
    ```python
    def _phase4_local_capability_mint(
        *,
        workflow_id: WorkflowId,
        chain_head: ChainHead,
    ) -> SolvedExampleWriteCapability:
        """Phase-4-local mint.

        TODO(phase-5): replace this shim with
        codegenie.gates._capability_mint.mint_solved_example_capability
        once GateRunner lands.
        """
        return SolvedExampleWriteCapability(workflow_id=workflow_id)
    ```
    `chain_head` is accepted and intentionally discarded in Phase 4 because S4-03's marker carries only `workflow_id`. The docstring says this plainly. `src/codegenie/rag/ingest.py` may import the private module by alias, but must not import or re-export the `_phase4_local_capability_mint` function symbol directly. `codegenie.rag.ingest.__all__` excludes it.
- [ ] **AC-6 - import-linter contract pins mint module scope.** `pyproject.toml [tool.importlinter.contracts]` gains:
    ```toml
    [[tool.importlinter.contracts]]
    name = "ADR-0016: phase4 solved-example mint module is scoped"
    type = "forbidden"
    source_modules = ["codegenie"]
    as_packages = true
    forbidden_modules = ["codegenie.rag._capability_mint"]
    ignore_imports = [
      "codegenie.rag.ingest -> codegenie.rag._capability_mint",
    ]
    ```
    Do not add a future `codegenie.gates.*` ignore entry yet: import-linter 2.x treats unmatched ignores as errors. Phase 5 appends the gates edge when the real gates module exists. `make lint-imports` must pass on the production tree.
- [ ] **AC-7 - contract shape and live-fire tests.** `tests/fence/test_phase4_capability_mint_scope.py`:
    - statically reads `pyproject.toml` with `tomllib` and asserts the contract name, type, `as_packages = true`, `source_modules`, `forbidden_modules`, and exact `ignore_imports` row;
    - walks `src/codegenie/**/*.py` with `ast` and asserts no production file outside `src/codegenie/rag/ingest.py` imports `codegenie.rag._capability_mint` by any spelling (`import codegenie.rag._capability_mint`, `from codegenie.rag._capability_mint import ...`, or `from codegenie.rag import _capability_mint`);
    - asserts no production file imports `_phase4_local_capability_mint` from `codegenie.rag.ingest`;
    - plants a temporary module under `src/codegenie/_test_phase4_mint_scope_violation.py` importing `codegenie.rag._capability_mint`, runs the `lint-imports` console script with `--config pyproject.toml --no-cache`, asserts non-zero exit and the contract name in output, and deletes the planted file in `finally`.
- [ ] **AC-8 - forged capability limitation is documented by test.** `tests/unit/rag/test_ingest.py` has a test that directly constructs `SolvedExampleWriteCapability(workflow_id=WorkflowId("hand-forged"))` and proves the writer/store path accepts it when supplied in-process. The test docstring states: "This is intentional: capability unforgeability is a lint/test enforced module boundary, not a runtime guarantee." If a future implementation adds runtime detection, surface per Rule 7 instead of silently changing the story.
- [ ] **AC-9 - `SolvedExampleHarvested` event uses real EventLog surface.** `src/codegenie/plugins/events.py` registers a frozen Pydantic `WorkflowInternalEvent` variant:
    ```python
    class SolvedExampleHarvested(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        event_type: Literal["solved_example_harvested"] = "solved_example_harvested"
        event_id: EventId
        workflow_id: WorkflowId
        timestamp: datetime
        solved_example_id: SolvedExampleId
        embedding_model: ModelId
        event_chain_head: ChainHead
        origin: Literal["llm_solved"] = "llm_solved"
    ```
    The class is wired into `WorkflowInternalEvent`, `_INTERNAL_CLASSES`, and `__all__`; `tests/unit/plugins/test_events.py` asserts the discriminator mapping contains `"solved_example_harvested"` and that `EventLog.emit_internal(...)` / `replay()` round-trips the typed event. Do not create `src/codegenie/rag/events.py`.
- [ ] **AC-10 - writer is silent.** A unit test monkeypatches or spies on `codegenie.plugins.events.EventLog` / `emit_internal` and asserts `ingest_solved_example(...)` never reaches either. The only observable write is `store.add(example, capability)`.
- [ ] **AC-11 - lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/rag/ src/codegenie/plugins/events.py` clean. No new `Any`, no untyped functions, no untyped dict shuffling.

## Implementation outline

1. **Create `src/codegenie/rag/_capability_mint.py`.** Keep it tiny and dependency-light: import `SolvedExampleWriteCapability`, `WorkflowId`, and `ChainHead`; define only `_phase4_local_capability_mint`; `__all__ = ["_phase4_local_capability_mint"]` is acceptable because the module itself is private and import-linter-scoped.
2. **Create / extend `src/codegenie/rag/ingest.py`:**
   - Define `ValidatedPlanOutcome`.
   - Define `_canonical_identity_bytes(...)`, `_solved_example_id_for(...)`, and `_solved_example_from_outcome(...)` as pure helpers.
   - Import the mint module by alias only, for example `from codegenie.rag import _capability_mint as _capability_mint_module`; do not bind `_phase4_local_capability_mint` into `ingest.py`'s module namespace.
   - Define `ingest_solved_example(...)` as the impure shell.
3. **Build the `SolvedExample` from the hardened S1-04 shape:**
   ```python
   now = datetime.now(UTC)
   embedding_model = ModelId(str(embedder.model_digest()))
   vector = embedder.embed(outcome.query_text)
   sid = _solved_example_id_for(outcome=outcome, embedding_model=embedding_model)
   example = SolvedExample(
       id=sid,
       task_class=outcome.task_class,
       language=outcome.language,
       build_system=outcome.build_system,
       cve_id=outcome.cve_id,
       advisory_digest=outcome.advisory_digest,
       plan_kind=outcome.plan_proposal.kind,
       plan_proposal=outcome.plan_proposal,
       transform_digest=outcome.transform_digest,
       trust_outcome_digest=outcome.trust_outcome_digest,
       provenance=RecordProvenance(
           workflow_id=capability.workflow_id,
           event_chain_head=outcome.chain_head,
           created_at=now,
           signing_method="hmac_sha256_chain",
       ),
       origin="llm_solved",
       embedding_model=embedding_model,
       embedding_vector=vector,
       created_at=now,
   )
   return await store.add(example, capability)
   ```
   If S1-04 has not yet been amended with `embedding_vector`, stop and surface the S4-03 validation blocker; do not invent a side-channel vector argument.
4. **Register `SolvedExampleHarvested` in `src/codegenie/plugins/events.py`.** Follow the existing workflow-internal event pattern: class, union row, `_INTERNAL_CLASSES`, and `__all__`. The writer still does not emit it.
5. **Append the pyproject import-linter contract** per AC-6. Run `make lint-imports` before committing.
6. **Tests:**
   - `tests/unit/rag/test_ingest.py` for AC-1..AC-5, AC-8, AC-10, deterministic id, exact field shapes, and stale-field AST guard.
   - `tests/fence/test_phase4_capability_mint_scope.py` for AC-6/AC-7.
   - `tests/unit/plugins/test_events.py` for AC-9.

## TDD plan - red / green / refactor

### Red - write failing tests first

Test file: `tests/fence/test_phase4_capability_mint_scope.py`

```python
from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Final

import pytest

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PYPROJECT: Final[Path] = REPO_ROOT / "pyproject.toml"
CONTRACT: Final[str] = "ADR-0016: phase4 solved-example mint module is scoped"
PLANTED: Final[Path] = REPO_ROOT / "src/codegenie/_test_phase4_mint_scope_violation.py"


def _contracts() -> dict[str, dict[str, object]]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    contracts = data.get("tool", {}).get("importlinter", {}).get("contracts", [])
    return {c["name"]: c for c in contracts if c.get("name") == CONTRACT}


def test_phase4_mint_contract_shape() -> None:
    contract = _contracts()[CONTRACT]
    assert contract["type"] == "forbidden"
    assert contract["source_modules"] == ["codegenie"]
    assert contract["as_packages"] is True
    assert contract["forbidden_modules"] == ["codegenie.rag._capability_mint"]
    assert contract["ignore_imports"] == [
        "codegenie.rag.ingest -> codegenie.rag._capability_mint"
    ]


def test_no_production_imports_private_mint_outside_ingest() -> None:
    violators: list[str] = []
    for path in (REPO_ROOT / "src/codegenie").rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel == "src/codegenie/rag/ingest.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in {
                "codegenie.rag._capability_mint",
                "codegenie.rag",
                "codegenie.rag.ingest",
            }:
                names = {alias.name for alias in node.names}
                if node.module == "codegenie.rag._capability_mint":
                    violators.append(rel)
                if node.module == "codegenie.rag" and "_capability_mint" in names:
                    violators.append(rel)
                if "_phase4_local_capability_mint" in names:
                    violators.append(rel)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "codegenie.rag._capability_mint":
                        violators.append(rel)
    assert not violators


def test_lint_imports_catches_planted_mint_scope_violation() -> None:
    binary = Path(sys.executable).parent / "lint-imports"
    if not binary.exists():
        found = shutil.which("lint-imports")
        assert found is not None, "lint-imports must be installed for fence tests"
        binary = Path(found)
    try:
        PLANTED.write_text(
            "import codegenie.rag._capability_mint  # noqa: F401\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [str(binary), "--config", "pyproject.toml", "--no-cache"],
            cwd=REPO_ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert CONTRACT in (result.stdout + result.stderr)
    finally:
        PLANTED.unlink(missing_ok=True)
```

Why it fails first: the private mint module, `ingest.py`, and the import-linter contract do not exist yet.

### Follow-on red tests

- `tests/unit/rag/test_ingest.py::test_ingest_builds_solved_example_and_calls_store_once` - fake outcome, fake embedder, fake async store; assert exact `SolvedExample` fields, vector forwarded, and returned id.
- `tests/unit/rag/test_ingest.py::test_solved_example_id_is_deterministic_and_excludes_workflow_context` - same identity fields produce same id; changed `chain_head` / `response_id` do not; changed `transform_digest` does.
- `tests/unit/rag/test_ingest.py::test_ingest_does_not_emit_events` - writer stays silent.
- `tests/unit/rag/test_ingest.py::test_record_provenance_stale_fields_are_absent` - AST/source stale-field guard.
- `tests/unit/plugins/test_events.py::test_solved_example_harvested_is_internal_event` - discriminator mapping + `EventLog.emit_internal` replay.

### Green

Implement the private mint module, writer helpers, event registration, and pyproject contract until the above tests pass.

### Refactor

Keep the pure helpers small:

- `_canonical_identity_bytes(...) -> bytes`
- `_solved_example_id_for(...) -> SolvedExampleId`
- `_solved_example_from_outcome(...) -> SolvedExample`

Do not introduce a registry or class hierarchy here. There is one writer surface and one interim mint. The extension point is the Phase-5 mint module, not a speculative Phase-4 plugin system.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/_capability_mint.py` | Private Phase-4-local mint module. |
| `src/codegenie/rag/ingest.py` | `ValidatedPlanOutcome`, pure helpers, and `ingest_solved_example`. |
| `src/codegenie/plugins/events.py` | Register `SolvedExampleHarvested` as a `WorkflowInternalEvent`. |
| `pyproject.toml` | Import-linter contract for the private mint module. |
| `tests/unit/rag/test_ingest.py` | Writer behavior, deterministic id, stale-field guard, forged-capability limitation. |
| `tests/fence/test_phase4_capability_mint_scope.py` | Contract shape, AST scope, live-fire planted violation. |
| `tests/unit/plugins/test_events.py` | Event union and replay test. |

## Out of scope

- Phase-5 production mint in `src/codegenie/gates/_capability_mint.py`; this story leaves a TODO and a pyproject shape that Phase 5 can extend once the gates module exists.
- Caller-side confidence gate (`TrustOutcome.passed AND confidence == "high"`); S6-03 owns it.
- `SolvedExampleHarvested` emission; S6-03 emits it after the writer returns.
- `HarvestSkipped` events and `SolvedExampleIngestFailed` handling; S6-03 owns caller policy.
- Runtime detection of hand-forged capabilities; explicitly rejected by final-design Component 9.
- A general writer registry or plugin system; one writer and one private mint are enough for Phase 4.

## Notes for the implementer

### 1. Import-linter is module-level

Do not try `forbidden_modules = ["codegenie.rag.ingest._phase4_local_capability_mint"]`. That string names no importable module, so the contract either does nothing useful or breaks parsing. The private-module split is what makes the boundary enforceable.

### 2. Do not pre-allow Phase 5 imports

S1-06 verified import-linter 2.x fails on unmatched `ignore_imports`. Add the future `codegenie.gates... -> codegenie.rag._capability_mint` ignore only when Phase 5 creates the real importing module.

### 3. The writer is not the gate

`ingest_solved_example` must not branch on confidence. It receives an already-validated projection. The Specification pattern lives in S6-03's caller-side gate; keeping it out of the writer avoids making the writer a second policy engine.

### 4. The event is registered here but emitted later

Registering `SolvedExampleHarvested` in `plugins/events.py` now gives S6-03 a typed event to emit. The writer staying silent is load-bearing; double emission would make replay ambiguous.

### 5. S1-04 / S4-03 precondition

This story assumes the S4-03 validator's cross-story amendment has happened: `SolvedExample` carries `embedding_vector: EmbeddingVector`. If it has not, stop and amend S1-04 first. Do not pass vectors to the store through an untyped side channel.

### 6. `ModelId(str(embedder.model_digest()))` is a boundary adapter

S4-01 exposes `model_digest() -> BlobDigest`; S1-04's `SolvedExample.embedding_model` is `ModelId`. Until the model field is amended to `BlobDigest`, the conversion must be explicit and commented. Do not let a raw `str` leak across the boundary.
