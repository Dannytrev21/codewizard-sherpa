# Story S4-06 — `SolvedExampleWriter` + `_phase4_local_capability_mint` + import-linter mint-scope contract

**Step:** Step 4 — Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** Ready
**Effort:** M
**Depends on:** S4-05 (`RecordProvenance.verify` + `RagRecordChainOrphan` event landed; ingestion needs to validate provenance shape against current spanning head)
**ADRs honored:** ADR-0016 (write-gated `add()`; capability shape), ADR-0009 (this phase — inline auto-harvest gated on `TrustOutcome.passed AND TrustOutcome.confidence == "high"`; the writer is the seam), final-design §Component 9 + §"Module Boundary pattern with CI enforcement"

## Context

S4-03 declared `SolvedExampleWriteCapability` as a `@final` frozen dataclass — an inert marker. ADR-0016 §Consequences requires `store.add(example, capability)` calls to be **mint-gated**: only modules in `{src/codegenie/gates/, src/codegenie/rag/ingest.py}` may construct the capability. The control is the **Module Boundary pattern with CI enforcement** (named honestly; Python has no object-capability runtime per final-design §Component 9 + ADR-0003 §Pattern fit).

This story lands three pieces:

1. **`SolvedExampleWriter` writer surface** at `src/codegenie/rag/ingest.py` — the orchestrating function `ingest_solved_example(outcome, store, embedder, capability) -> SolvedExampleId` that S6-03's `FallbackTier.on_validated` calls.
2. **`_phase4_local_capability_mint(workflow_id, chain_head) -> SolvedExampleWriteCapability`** — the **module-private** factory under `src/codegenie/rag/ingest.py` whose name begins with `_` to make the symbol private by convention; the import-linter contract enforces the boundary.
3. **`import-linter` contract** at `.importlinter` pinning the mint symbol to `{src/codegenie/gates/, src/codegenie/rag/ingest.py}`; deliberately-violating fixture (a test module that imports `_phase4_local_capability_mint` from a forbidden location) fails CI with a precise diagnostic.

The mint is **Phase-4-local**; Phase 5's `GateRunner` ships the real production mint (`src/codegenie/gates/_capability_mint.py`) which supersedes this one — but the `import-linter` contract already includes `src/codegenie/gates/` so the Phase-5 swap is mechanical. A `# TODO(phase-5)` marker on the mint signals this (open question §6 of the planner manifest).

Final-design §Component 9 calls out: the capability **does not claim runtime unforgeability**. Python has no object-capability runtime; the enforcement is at **lint time** (`import-linter`) and **test time** (the deliberately-violating fixture). The naming is honest: "Module Boundary pattern with CI enforcement," not "Capability" pattern.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 10 — SolvedExampleWriter + capability` — `ingest_solved_example(outcome, store, embedder, capability) -> SolvedExampleId`; `_phase4_local_capability_mint` shipped here; Phase 5's `GateRunner` mint supersedes.
  - `../phase-arch-design.md §"Sequence — Scenario 2"` (line 407) — `_phase4_local_capability_mint(workflow_id, chain_head)` is the inline-harvest path's mint callsite.
  - `../phase-arch-design.md §"Design decisions and trade-offs"` (line 1077) — Phase-4-local `_phase4_local_capability_mint` shim.
- **Phase ADRs:**
  - `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` §Consequences — `SolvedExampleStore.add(example, capability)` requires the capability.
  - `../ADRs/0003-path-scoped-fence-amendment.md` — import-linter contracts are the canonical Phase-4 enforcement mechanism for module-boundary discipline.
- **Source design:**
  - `../final-design.md §Component 9 — SolvedExampleWriter + SolvedExampleWriteCapability` (line 421) — "Module Boundary pattern with CI enforcement"; `import-linter` blocks importing the minting symbol; CI test asserts the contract.
  - `../final-design.md §"Inline auto-harvest"` — gate on `TrustOutcome.passed AND TrustOutcome.confidence == "high"` (S6-03 owns the call; S4-06 ships the receiving surface).
- **Existing code (precedent to mirror):**
  - `.importlinter` — existing contract file; mirror the contract-block layout used for Phase 1/2 kernel-layering contracts (S1-06 of this phase already extended `.importlinter` for fence-mirroring; this story adds a new contract block).
  - `src/codegenie/exec/run_allowlisted.py` — small "boundary-respecting helper" precedent.
  - `src/codegenie/rag/store.py` (S4-03) — the consumer; `add(example, capability)` already validates the capability is *present* (typed parameter); this story ships the only legitimate construction site.

## Goal

Ship `ingest_solved_example` writer + `_phase4_local_capability_mint` private factory in `src/codegenie/rag/ingest.py`, plus an `import-linter` contract pinning the mint-symbol import to `{src/codegenie/gates/*, src/codegenie/rag/ingest.py}`; a deliberately-violating test fixture proves the contract fails CI loudly with a precise diagnostic.

## Acceptance criteria

- [ ] **AC-1 — `ingest_solved_example` signature + behavior.** `src/codegenie/rag/ingest.py` exports:
    ```python
    async def ingest_solved_example(
        *,
        outcome: ValidatedPlanOutcome,   # the projection from FallbackTier.on_validated
        store: SolvedExampleStore,
        embedder: Embedder,
        capability: SolvedExampleWriteCapability,
    ) -> SolvedExampleId: ...
    ```
    The function:
    1. Builds a `SolvedExample` from the `outcome` projection (id = `BLAKE3` of canonical body bytes; `embedding_model = embedder.model_digest()`; `provenance` populated from the outcome's harvest context).
    2. Calls `vec = embedder.embed(outcome.query_text)` to materialize the embedding (pre-stored — chromadb needs it).
    3. Calls `await store.add(example, capability)` and returns the resulting `SolvedExampleId`.
    All callsites use kwargs only (`*` forces this — catches positional-arg-drift mutants).
- [ ] **AC-2 — `_phase4_local_capability_mint` shape.** Module-level private function in `src/codegenie/rag/ingest.py`:
    ```python
    def _phase4_local_capability_mint(
        *,
        workflow_id: WorkflowId,
        chain_head: ChainHead,  # spanning-log head at validate time
    ) -> SolvedExampleWriteCapability:
        """Phase-4-local mint.  TODO(phase-5): replace with
        `src/codegenie/gates/_capability_mint.py`'s `mint_solved_example_capability`
        once Phase 5's GateRunner lands.  See planner Open Question §6."""
        return SolvedExampleWriteCapability(workflow_id=workflow_id)
    ```
    The `chain_head` parameter is accepted **and discarded** in Phase 4 — the marker dataclass only carries `workflow_id`. The parameter is present so the Phase-5 swap (which will embed the chain head in the mint) is mechanical (signature already shaped). Document this explicitly in the docstring.
- [ ] **AC-3 — `import-linter` contract pins mint scope.** `.importlinter` (existing file) gains a new contract block:
    ```ini
    [importlinter:contract:phase4-mint-scope]
    name = Phase 4: _phase4_local_capability_mint may only be imported by gates/ or rag/ingest.py
    type = forbidden
    source_modules =
        codegenie
    forbidden_modules =
        codegenie.rag.ingest._phase4_local_capability_mint
    ignore_imports =
        codegenie.gates.* -> codegenie.rag.ingest._phase4_local_capability_mint
        codegenie.rag.ingest -> codegenie.rag.ingest._phase4_local_capability_mint
    ```
    (Adjust to import-linter's exact syntax; the precedent in the existing `.importlinter` carries the right shape — mirror that shape verbatim.) `make lint-imports` passes; introducing a deliberate violation (AC-4) fails it.
- [ ] **AC-4 — Deliberately-violating fixture proves the contract.** `tests/fence/test_capability_mint_scoped.py`:
    - **(a)** Asserts the production tree does NOT contain any `from codegenie.rag.ingest import _phase4_local_capability_mint` (AST-walk over `src/codegenie/`) except inside `src/codegenie/rag/ingest.py` (the defining module) and `src/codegenie/gates/*` (the future Phase-5 site; OK if empty today).
    - **(b)** Asserts `make lint-imports` (invoked as a subprocess) **fails** with the contract's name in the stderr when a `tests/fixtures/violations/mint_scope_violator.py` module imports the mint. The fixture file exists at `tests/fixtures/violations/mint_scope_violator.py` and contains exactly:
      ```python
      # Deliberately violates phase4-mint-scope; CI must catch this.
      from codegenie.rag.ingest import _phase4_local_capability_mint  # noqa: F401
      ```
      The contract's `source_modules` includes test directories (verify import-linter config), OR the fence test invokes import-linter scoped to include `tests/fixtures/violations/`. Either way, the violation must be caught — the test asserts the failure mode end-to-end.
- [ ] **AC-5 — `store.add()` rejects a fabricated capability.** This is impossible to *enforce* at runtime (Python; final-design §Component 9 acknowledges); the test is documentation-shaped:
    - A test constructs `SolvedExampleWriteCapability(workflow_id=WorkflowId("hand-forged"))` directly (not through the mint), calls `await store.add(...)`, asserts the call succeeds (no runtime check). The test's docstring states: "This test documents the *intentional* limitation: capability unforgeability is a CI-enforced module boundary, not a runtime check. The lint contract (AC-3) is the enforcement. If this test fails because we added a runtime check, surface per Rule 7 before reverting."
- [ ] **AC-6 — `SolvedExampleHarvested` event class.** `src/codegenie/rag/events.py` extends with:
    ```python
    class SolvedExampleHarvested(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        kind: Literal["solved_example_harvested"] = "solved_example_harvested"
        solved_example_id: SolvedExampleId
        workflow_id: WorkflowId
        embedding_model: ModelId
        harvested_at: datetime
    ```
    `ingest_solved_example` returns the `SolvedExampleId`; the **caller** (S6-03) emits `SolvedExampleHarvested`. The writer does not double-emit (avoids the emission contract bleeding into two places).
- [ ] **AC-7 — Path-scoped fence still green.** Re-run `tests/fence/test_pyproject_fence_phase4.py`. `src/codegenie/rag/ingest.py` is under `src/codegenie/rag/` so any incidental import (e.g., `from codegenie.rag.store import ...`) is admitted.
- [ ] **AC-8 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean.

## Implementation outline

1. **Define `ValidatedPlanOutcome` shape** — this is the projection S6-03 passes in. Phase 4 may not have shipped this type yet; if S1-03 (`PlanOutcome wraps RecipeOutcome`) lands the union and a downstream "validated successfully" variant exists, reuse it. **If not yet shipped:** define a minimal `@dataclass(frozen=True)` placeholder in `src/codegenie/rag/ingest.py` with fields `{query_text: str, plan_proposal: PlanProposal, transform_digest: BlobDigest, trust_outcome_digest: BlobDigest, task_class: TaskClassName, language: LanguageName, build_system: BuildSystemName, cve_id: CveId, response_id: LeafResponseId, confidence: Literal["high","medium","low"], chain_head: ChainHead}` — sufficient to populate a `SolvedExample`. S6-03's executor will refine the projection; surface the placeholder per Rule 7 in the implementer notes.
2. **`_solved_example_id_for(outcome) -> SolvedExampleId`** pure helper:
   ```python
   def _solved_example_id_for(*, outcome: ValidatedPlanOutcome, embedding_model: ModelId) -> SolvedExampleId:
       body = canonical_json_bytes({"cve_id": outcome.cve_id, "transform_digest": outcome.transform_digest, "embedding_model": embedding_model})
       return SolvedExampleId(blake3.blake3(body).hexdigest())
   ```
   The ID is content-addressed; the same `(cve_id, transform_digest, embedding_model)` triple always produces the same ID — so re-ingesting the same outcome is idempotent (store.add's INSERT OR REPLACE handles the chromadb side; YAML file overwrite is also idempotent).
3. **`ingest_solved_example` body:**
   ```python
   async def ingest_solved_example(*, outcome, store, embedder, capability) -> SolvedExampleId:
       digest = embedder.model_digest()
       sid = _solved_example_id_for(outcome=outcome, embedding_model=ModelId(str(digest)))
       vec = embedder.embed(outcome.query_text)
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
               solved_example_id=sid,
               workflow_id=capability.workflow_id,
               event_chain_head=outcome.chain_head,
               trust_outcome_passed=True,
               confidence=outcome.confidence,
               model_id=ModelId(str(digest)),
               embedding_dim=len(vec),
               harvested_at=datetime.now(timezone.utc),
               record_chain_head=ChainHead(blake3.blake3(canonical_json_bytes({"sid": sid, "head": outcome.chain_head})).hexdigest()),
           ),
           origin="llm_solved",
           embedding_model=ModelId(str(digest)),
           created_at=datetime.now(timezone.utc),
           embedding_vector=vec,  # depending on S1-04 schema; if not on SolvedExample, pass separately
       )
       return await store.add(example, capability)
   ```
   (The exact field-set depends on S1-04's `SolvedExample` schema — mirror it; if `embedding_vector` lives on the example or is passed separately to `store.add`, follow S4-04's wiring.)
4. **`_phase4_local_capability_mint`** — short and trivial per AC-2.
5. **`.importlinter` contract** — extend the file per AC-3. Verify the contract by running `make lint-imports` locally before pushing.
6. **Tests:**
   - `tests/unit/rag/test_ingest.py` — AC-1 happy path; AC-5 fabricated-capability documentation.
   - `tests/fence/test_capability_mint_scoped.py` — AC-3, AC-4.
   - `tests/fixtures/violations/mint_scope_violator.py` — the deliberate violation fixture.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/fence/test_capability_mint_scoped.py`

```python
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_no_production_module_imports_phase4_mint_outside_allowlist() -> None:
    """ADR-0016 + final-design §Component 9: the mint symbol is private to
    `src/codegenie/rag/ingest.py` and may be re-exported only by
    `src/codegenie/gates/*` (Phase 5).  Any other importer is a Module-Boundary
    breach the import-linter contract will catch — but we also AST-walk here
    so a contributor with import-linter disabled gets the diagnostic locally."""
    src_root = REPO_ROOT / "src" / "codegenie"
    violators: list[str] = []
    for py in src_root.rglob("*.py"):
        rel = py.relative_to(REPO_ROOT).as_posix()
        if rel == "src/codegenie/rag/ingest.py":
            continue  # the defining module
        if rel.startswith("src/codegenie/gates/"):
            continue  # Phase 5 site allowlisted
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "codegenie.rag.ingest":
                names = {alias.name for alias in node.names}
                if "_phase4_local_capability_mint" in names:
                    violators.append(rel)
    assert not violators, (
        f"Phase-4 mint imported outside allowlist: {violators}. "
        "Mint scope is enforced by `.importlinter`; this AST test is the "
        "local fast-fail diagnostic.  See final-design §Component 9."
    )


def test_deliberate_violator_fails_import_linter() -> None:
    """AC-4 — end-to-end CI assertion: a fixture module that imports the mint
    from a forbidden location causes `lint-imports` to fail with the contract
    name in the diagnostic.  Catches a future "we silently widened the
    allowlist" mutation."""
    result = subprocess.run(
        ["make", "lint-imports"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={"PHASE4_INCLUDE_VIOLATOR_FIXTURE": "1"},  # see Notes §3 for env-flag rationale
    )
    assert result.returncode != 0, "lint-imports must FAIL when violator fixture is included"
    assert "phase4-mint-scope" in (result.stdout + result.stderr), (
        "diagnostic must name the contract — reviewers grep on this"
    )
```

Why it fails: `src/codegenie/rag/ingest.py` doesn't exist; the import-linter contract isn't yet declared.

### Green — make it pass

- Land `src/codegenie/rag/ingest.py` per Implementation Outline.
- Land the `.importlinter` contract per AC-3.
- The AST test passes once the only mint import is the self-import.
- The `lint-imports` test needs the env-flag plumbing (Notes §3) — the violator fixture is **only included** when `PHASE4_INCLUDE_VIOLATOR_FIXTURE=1` is set (so day-to-day `make lint-imports` doesn't fail).

### Refactor

- Extract `_solved_example_id_for` into the pure helper documented in Implementation Outline §2.
- Module docstring on `ingest.py` cites final-design §Component 9 + ADR-0016 + the `# TODO(phase-5)` for the Phase-5 mint swap.

### Required follow-on tests

- `test_ingest_happy_path_returns_solved_example_id` (AC-1) — fake outcome, fake store (spy that records the `(example, capability)` pair), fake embedder; assert `await ingest_solved_example(...)` returns the expected `SolvedExampleId`; spy captured the canonical `SolvedExample` shape.
- `test_ingest_idempotent_on_same_outcome` — second call with the **same outcome** produces the **same** `SolvedExampleId` (content-addressed).
- `test_fabricated_capability_documents_intentional_limitation` (AC-5) — see AC body.
- `test_phase4_local_mint_returns_capability_with_workflow_id` (AC-2) — `cap = _phase4_local_capability_mint(workflow_id=WorkflowId("wf-1"), chain_head=ChainHead("ch-1"))`; `assert cap.workflow_id == WorkflowId("wf-1")`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/ingest.py` | `ingest_solved_example` + `_phase4_local_capability_mint` + `_solved_example_id_for` + (placeholder) `ValidatedPlanOutcome` if S1-03 hasn't shipped a suitable type. |
| `src/codegenie/rag/events.py` | Extend with `SolvedExampleHarvested` event class. |
| `.importlinter` | New contract block per AC-3. |
| `tests/unit/rag/test_ingest.py` | AC-1, AC-2, AC-5 + idempotence. |
| `tests/fence/test_capability_mint_scoped.py` | AC-3, AC-4 (AST + subprocess). |
| `tests/fixtures/violations/__init__.py` | Test-fixture package marker. |
| `tests/fixtures/violations/mint_scope_violator.py` | The deliberate import — gated by env-var inclusion. |
| `Makefile` | Document the `PHASE4_INCLUDE_VIOLATOR_FIXTURE=1 make lint-imports` invocation in a comment (do **not** change default behavior). |

## Out of scope

- **Phase-5 production mint (`src/codegenie/gates/_capability_mint.py`)** — Phase 5 ships; this story leaves the `# TODO(phase-5)` marker and pre-includes `src/codegenie/gates/` in the import-linter allowlist so the swap is mechanical.
- **Inline-harvest gate logic (`confidence == "high"`)** — S6-03 (`FallbackTier.on_validated`) owns the gate; this story only ships the receiving surface.
- **`SolvedExampleHarvested` emission** — S6-03 (the caller emits; the writer is silent).
- **`HarvestSkipped(reason=low_confidence)` event** — S6-03.
- **`HarvestSkipped(reason=write_contention)` emission** — S6-03 catches `StoreWriteContention` from `store.add` and emits this; not the writer's job.
- **Hand-forged-capability runtime detection** — explicitly out per AC-5; final-design §Component 9 is unambiguous.

## Notes for the implementer

### §1 — The mint is a function, not a method on the capability class

Tempting to put `mint(workflow_id, chain_head) -> SolvedExampleWriteCapability` as a `@classmethod` on the dataclass itself. **Don't.** The Module Boundary pattern relies on the *importable symbol's* location for `import-linter` enforcement. A classmethod is reachable as `SolvedExampleWriteCapability.mint(...)` from any module that imports the class — defeating the boundary. The function form ties the symbol to the `codegenie.rag.ingest` module path; only an import-from of that module triggers the contract. Function form is the right shape here.

### §2 — `_solved_example_id_for` must be deterministic

Content-addressing the ID off `(cve_id, transform_digest, embedding_model)` means re-ingesting the same outcome produces the same ID (idempotent). **Do not** include `workflow_id`, `created_at`, or `harvested_at` in the digest input — those are per-workflow non-determinism that would make re-ingests produce new IDs and break the "second run hits RAG, lower cost" exit criterion the Phase-7 E2E test verifies.

### §3 — `PHASE4_INCLUDE_VIOLATOR_FIXTURE` env-flag

The violator fixture (`tests/fixtures/violations/mint_scope_violator.py`) contains a real-violating import — adding it to the default `lint-imports` corpus would make CI fail. Two options to expose the failure mode for testing without breaking the default lint:

- **(A) Env-flag inclusion.** `make lint-imports` reads `PHASE4_INCLUDE_VIOLATOR_FIXTURE`; if set, expand the lint corpus to include `tests/fixtures/violations/`. The fence test sets the env-var in its subprocess invocation.
- **(B) Separate make target.** `make lint-imports-with-violator-fixture` runs lint scoped to include the violator fixture; the fence test invokes that target.

**Pick (B).** A separate make target is cleaner: no env-flag plumbing, no risk of CI accidentally setting the var. Update the AC-4 test to invoke `make lint-imports-with-violator-fixture`. The default `make lint-imports` (which CI invokes) excludes `tests/fixtures/violations/`. Document the target's purpose in the Makefile comment block.

### §4 — `import-linter` syntax — verify against existing contracts

The `.importlinter` syntax has shifted across versions. Before writing the contract block, **read** the existing `.importlinter` file for the precedent shape (Phase 1/2 kernel-layering contracts); mirror that shape verbatim. If the syntax differs from this story's example, the actual file is the source of truth — adapt.

### §5 — `# TODO(phase-5)` marker is part of the design

The marker on `_phase4_local_capability_mint` is **not** a code-smell to fix; it's the contractually-correct signpost for Phase 5's swap. The planner manifest open question §6 names this explicitly: "S4-06 docstring must cross-link the Phase-5 ADR + add a `# TODO(phase-5)` marker so the swap is mechanical when Phase 5's `gates._capability_mint` lands." A reviewer who flags "no TODOs in production code" should be redirected to this design note.

### §6 — `ValidatedPlanOutcome` placeholder risk

If S1-03's `PlanOutcome` union doesn't yet expose a "validated successfully" variant with the fields `ingest_solved_example` needs, the placeholder defined in this story will likely diverge from what S6-03 actually passes. Two paths:

- **(A) Surface and stop.** Per Rule 7, surface the conflict and request that S1-03's executor (already shipped per the planner status — `S1-03 → S1-04 → S4-03 → S4-04 → S4-05 → S4-06`) revisit and add the variant.
- **(B) Ship the placeholder.** Accept that S6-03 will refine the projection at integration time; the placeholder is a clearly-marked stub.

**Default to (A) if the gap is shape-substantive** (e.g., S1-03's variants don't carry `transform_digest`). **Default to (B) if it's purely a naming gap** (the fields exist under a different name). Surface either way in the attempt log.

### §7 — The `tests/fixtures/violations/` directory is new

It will be reused by other phase stories that need deliberate violations (Phase 6 fence-amendment contracts, etc.). Treat the directory as a versioned location for "tests prove the negative case." Documentation in the directory's `__init__.py` names this convention.

### §8 — Acceptance of CI-enforcement limitation

A reviewer comparing this story's "capability" to a true Erlang/object-capability runtime will (correctly) note that nothing prevents a malicious contributor from *adding* their module to the import-linter allowlist in the same PR that imports the mint. The honest answer is: **CODEOWNERS approval on `.importlinter`** is the human control; the lint contract is the structural one. Don't oversell the runtime guarantee; the discipline is at the PR-review level + import-linter together. Final-design §Component 9 is unambiguous about this; the AC-5 test makes the limitation a positive assertion ("we intentionally do not runtime-check") so a future reviewer doesn't "fix" the gap and break the design's stated posture.
