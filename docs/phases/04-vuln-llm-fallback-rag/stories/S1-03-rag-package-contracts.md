# Story S1-03 — `src/codegenie/rag/` package + `EmbeddingProvider` Protocol + `SolvedExample` v0.4.0

**Step:** Step 1 — Plant the contracts, the two ADR-gated Phase-3 edits, and the fence-CI rules every Phase 4 component consumes
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-P4-002, ADR-P4-005, ADR-P4-006, ADR-P4-015

## Context

Foundational, parallel sibling to S1-02. Stands up Phase 4's second new top-level package and freezes the `SolvedExample` schema at v0.4.0 — the writeback contract Phase 11's webhook (`merge_status` lifecycle) and Phase 15's recipe-authoring clusterer (`engine_trajectory`, `recipe_failure_reason`) consume. The schema is **task-class-generic** (ADR-P4-015): `task_class` is a Literal field shared by Phase 4 (`vuln`), Phase 7 (`chainguard`), and Phase 15 (`recipe_authoring`). Snapshot-tested so any drift is conspicuous.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Data model"` — verbatim `SolvedExample`, `Provenance`, `QueryKey`, `RetrievedExample`, `CachedPlan`, `ValidatorOutput`, `StoreHealth`, `EngineAttempt` shapes.
  - `../phase-arch-design.md §"Component design"` #7 — `EmbeddingProvider` Protocol with four required members (`available`, `embed`, `model_id`, `dimensions`, `model_digest`).
  - `../phase-arch-design.md §"Component design"` #4–6 — `SolvedExampleStore`, `QueryKeyCache`, `writeback_solved_example` all consume these types.
- **Phase ADRs:**
  - `../ADRs/0015-solved-example-schema-task-class-generic.md` — ADR-P4-015 — the full frozen schema; this story IS the implementation of that ADR.
  - `../ADRs/0002-two-tier-writeback-pending-promoted.md` — ADR-P4-002 — `Provenance.merge_status: Literal["pending_human","merged","withdrawn"]`.
  - `../ADRs/0006-bge-small-en-embedding-model-sha-pinned.md` — ADR-P4-006 — `model_digest` is SHA-pinned.
  - `../ADRs/0005-chromadb-in-process-with-stale-lock-detection.md` — ADR-P4-005 — `StoreHealth` shape.
- **Source design:**
  - `../final-design.md §"Synthesis ledger"` row "Writeback timing" — the two-tier lifecycle this schema persists.

## Goal

Create `src/codegenie/rag/` with `__init__.py`, `contract.py` (the `EmbeddingProvider` Protocol), and `models.py` (the eight Pydantic types listed below), and snapshot-test the public schema at v0.4.0.

## Acceptance criteria

- [ ] `src/codegenie/rag/__init__.py`, `src/codegenie/rag/contract.py`, `src/codegenie/rag/models.py` exist; imports for `EmbeddingProvider`, `SolvedExample`, `Provenance`, `AdvisoryRef`, `Fingerprint`, `EngineAttempt`, `QueryKey`, `RetrievedExample`, `CachedPlan`, `StoreHealth`, `ValidatorOutput` succeed.
- [ ] `EmbeddingProvider` is `@runtime_checkable` `Protocol` with `available() -> bool`, `embed(texts: Sequence[str]) -> list[list[float]]`, and `@property` `model_id: str`, `dimensions: int`, `model_digest: str`.
- [ ] `SolvedExample` Pydantic `frozen=True, extra="forbid"` with **every** field from `../phase-arch-design.md §"Data model"`: `id`, `schema_version: Literal["0.4.0"]`, `task_class: Literal["vuln","chainguard","recipe_authoring"]`, `ecosystem: Literal["npm","yarn","pnpm"]`, `language: Literal["javascript","typescript"]`, `advisory: AdvisoryRef`, `repo_fingerprint: Fingerprint`, `recipe_failure_reason: Literal["catalog_miss","range_break","peer_dep_conflict","no_engine","unsupported_dialect"]`, `engine_trajectory: list[EngineAttempt]`, `plan: Plan` (imported from `codegenie.llm.contract`), `diff_path: str`, `embedding_model: str`, `embedding_digest: str`, `dimensions: int`, `provenance: Provenance`, `created_at: datetime`.
- [ ] `Provenance` carries `run_id`, `repo_url`, `public: bool` (default False), `merge_status: Literal["pending_human","merged","withdrawn"]`, `reviewer: str | None`, `merge_sha: str | None`, `audit_chain_head: str`. `extra="forbid"`.
- [ ] `QueryKey` carries the seven-tuple from `../phase-arch-design.md §"Data model"`: `advisory_canonical_id`, `advisory_fixed_version`, `lockfile_blake3`, `node_major`, `recipe_selection_reason`, `recipe_catalog_blake3`, `task_class`.
- [ ] `EngineAttempt` carries `engine: Literal["ncu","openrewrite","rag_llm"]`, `reason: str`, `duration_ms: int`.
- [ ] `ValidatorOutput` carries `passed: bool`, `errors: list[str]`, `plan: Plan | None`.
- [ ] `StoreHealth` carries `count`, `embedding_model_digest`, `newest_example_age_days`, `mixed_embedding_models`, `query_latency_p50_ms`, `merge_status_distribution: dict[str,int]`.
- [ ] Snapshot test `tests/contracts/test_rag_contract_snapshot.py` byte-stable over `model_json_schema()` of every model above; committed under `tests/contracts/_snapshots/rag_contract.json`.
- [ ] Extra-field-rejection test for `SolvedExample`, `Provenance`, `QueryKey`, `EngineAttempt` (one extra key → `ValidationError`).
- [ ] `SolvedExample(schema_version="0.5.0")` is refused at validation time (Literal pin).
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/rag/` clean.

## Implementation outline

1. `mkdir -p src/codegenie/rag`; empty `__init__.py`.
2. `src/codegenie/rag/contract.py`: `EmbeddingProvider(Protocol)` + the property/method signatures. `@runtime_checkable`.
3. `src/codegenie/rag/models.py`:
   - `AdvisoryRef(BaseModel)` — `canonical_id: str`, `fixed_version: str`. `extra="forbid"`.
   - `Fingerprint(BaseModel)` — typed-fields-only; the actual fingerprint *builder* lands in S4-03. Here just declare the data shape (CVE id, package, fixed_range, recipe_failure_reason, node_major).
   - `EngineAttempt`, `Provenance`, `QueryKey`, `RetrievedExample`, `CachedPlan`, `ValidatorOutput`, `StoreHealth` per `../phase-arch-design.md §"Data model"`.
   - `SolvedExample` last (depends on the others + `Plan`).
4. `from codegenie.llm.contract import Plan` — this is the only cross-package import in Step 1 and it's allowed by the fence rule (rag may import llm contract types, but not anthropic/SDK).

   *Wait* — `../phase-arch-design.md §"Development view"` says `codegenie.rag ⊥ anthropic` (not `⊥ codegenie.llm`). Confirm the fence rule before importing. Re-read S1-07's planned graph: only `codegenie.transforms`, `codegenie.recipes` (except `engines/rag_llm.py`) are fenced off from `codegenie.llm`. `codegenie.rag` IS allowed to import `Plan` from `codegenie.llm.contract`. Verify S1-07's fence rule before merging.
5. Snapshot dump → commit → assert byte-equality.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/contracts/test_rag_contract_snapshot.py`

```python
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from codegenie.rag.models import (
    AdvisoryRef, EngineAttempt, Provenance, QueryKey,
    SolvedExample, ValidatorOutput, StoreHealth,
)
from codegenie.rag.contract import EmbeddingProvider

SNAPSHOT = Path(__file__).parent / "_snapshots" / "rag_contract.json"


def test_rag_contracts_match_frozen_snapshot():
    current = {
        "SolvedExample": SolvedExample.model_json_schema(),
        "Provenance": Provenance.model_json_schema(),
        "QueryKey": QueryKey.model_json_schema(),
        "EngineAttempt": EngineAttempt.model_json_schema(),
        "ValidatorOutput": ValidatorOutput.model_json_schema(),
        "StoreHealth": StoreHealth.model_json_schema(),
    }
    expected = json.loads(SNAPSHOT.read_text())
    assert current == expected, (
        "Phase-4 RAG contract drift. If intentional, bump schema_version "
        "AND mark this PR `phase-4-contract-bumped`."
    )


def test_solved_example_schema_version_pinned_at_v0_4_0():
    with pytest.raises(ValidationError):
        SolvedExample.model_validate({"schema_version": "0.5.0", ...})  # full minimal body


def test_provenance_merge_status_literal():
    with pytest.raises(ValidationError):
        Provenance(
            run_id="r", repo_url="u", public=False,
            merge_status="auto_promoted",  # not in Literal
            reviewer=None, merge_sha=None, audit_chain_head="x",
        )


def test_query_key_carries_task_class_for_phase7_collision_avoidance():
    qk = QueryKey(
        advisory_canonical_id="CVE-2024-1",
        advisory_fixed_version="2.0.0",
        lockfile_blake3="a",
        node_major=20,
        recipe_selection_reason="catalog_miss",
        recipe_catalog_blake3="b",
        task_class="vuln",
    )
    # different task_class must produce a different QueryKey identity
    other = qk.model_copy(update={"task_class": "chainguard"})
    assert qk != other


def test_embedding_provider_runtime_checkable():
    class _Stub:
        def available(self) -> bool: return True
        def embed(self, texts): return [[0.0]]
        @property
        def model_id(self) -> str: return "x"
        @property
        def dimensions(self) -> int: return 1
        @property
        def model_digest(self) -> str: return "abc"
    assert isinstance(_Stub(), EmbeddingProvider)
```

### Green — make it pass

Write the eight Pydantic models + the Protocol. Commit the snapshot dump.

### Refactor — clean up

- Type hint every property and method.
- Docstring each public class with the ADR row that pinned it.
- `created_at: datetime` — Pydantic v2 serialises UTC ISO-8601 by default; confirm with a round-trip test.
- Edge cases from `../phase-arch-design.md §"Edge cases"`: row #15 (chromadb upsert fails after body JSON written → orphan body), row #16 (two workers race same example_id) — neither is data-model wiring, but they motivate `id` being content-addressed in S6-01. Note this in a code comment so the implementer of S6-01 doesn't accidentally change `id` to a UUID.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/__init__.py` | New package. |
| `src/codegenie/rag/contract.py` | `EmbeddingProvider` Protocol. |
| `src/codegenie/rag/models.py` | The eight Pydantic types. |
| `tests/contracts/test_rag_contract_snapshot.py` | Frozen-schema gate. |
| `tests/contracts/_snapshots/rag_contract.json` | Frozen JSON Schema dump. |
| `tests/contracts/test_rag_models_extra_forbid.py` | Extra-field-rejection unit test per model. |

## Out of scope

- **`SolvedExampleStore`** — S4-04.
- **`SentenceTransformerProvider` concrete impl** — S4-01.
- **`fingerprint.py` builder logic** — S4-03 (this story only declares the `Fingerprint` data shape).
- **`QueryKeyCache` filesystem layout** — S4-05.
- **`writeback_solved_example`** — S6-01.
- **Snapshot regeneration on Phase 7 task_class extension** — Phase 7 ADR amendment.

## Notes for the implementer

- The `task_class` Literal includes `"recipe_authoring"` (Phase 15) — do **not** drop it because Phase 4 only uses `"vuln"`. ADR-P4-015 freezes the *full* enumeration at v0.4.0 so Phase 7/15 never re-bump.
- `recipe_failure_reason` Literal MUST match `EngineAttempt.reason` shape if `reason` is used as a free string today; the Literal is the canonical surface. Surface (Rule 7) if they conflict and pick the Literal.
- `embedding_digest: str` is the SHA-pinned commit hash from `tools/digests.yaml` (ADR-P4-006). Field is just `str` here; the **digest filter** lives in S4-04 (Gap 2 fix).
- `Provenance.public` defaults to `False` (NG7 defense-in-depth — cross-repo retrieval is opt-in). Default-False keeps the corpus private until widened explicitly.
- `audit_chain_head: str` is `blake3-hex` of the run's chain head — Phase 2 BLAKE3 chain integration. The chain-head value is *computed* in S6-01 at writeback time; this story only declares the field.
- Rule 11 (match conventions): Phase 0–3's Pydantic models use `ConfigDict(extra="forbid", frozen=True)`. Keep that. If any field type uses `Annotated[...]` constraints in Phase 3, mimic the style.
- The snapshot file is byte-sensitive — write it via `json.dumps(..., sort_keys=True, indent=2) + "\n"` so editor newline-discipline doesn't flap CI.
- Verify the cross-package import (`from codegenie.llm.contract import Plan`) is permitted by the planned fence rule in S1-07 before merging. The rule says `codegenie.rag ⊥ anthropic`; importing `Plan` (a Pydantic class with no SDK dependency) is allowed.
