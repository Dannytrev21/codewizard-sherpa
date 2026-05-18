# Story S1-04 — RAG-side Pydantic models

**Step:** Step 1 — Establish Phase-4 type substrate + path-scoped fence amendment
**Status:** Ready
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0010 (`BudgetToken` is the capability; this story lands the Pydantic frozen-extra-forbid model wrapping `BudgetTokenId` + the `_marker` Literal), ADR-0016 (canonical YAML SolvedExample with chain-verified `RecordProvenance`), ADR-0008 (`RetrievalOutcome` is a closed three-way union — `RagHit | RagMiss | RagDegraded` — feeding the two-threshold band)

## Context

Steps 2 through 7 read every RAG-side primitive landed here as a frozen Pydantic model: `SolvedExample` (the persisted record), `Query` (the typed-fields input to retrieval, no f-strings), `RecordProvenance` (chain-verify input), `RetrievalOutcome` (the closed `RagHit | RagMiss | RagDegraded` union), `BudgetSnapshot` (Phase-5-consumed projection from `LlmInvocationGuard.running_total`), `BudgetToken` (capability wrapper around `BudgetTokenId`), and `TypecheckNodeSignal` (the Phase-3 `@register_signal_kind` `kind: Literal["typecheck.typescript"]` shape). They land *together* in Step 1 because each is a contract surface: any consumer (`SolvedExampleStore.add`, `SolvedExampleRetriever.query`, `LlmInvocationGuard.precharge`, `TrustScorer.fold`) is typed against these shapes, and the alternative — landing them lazily as each consumer arrives — produces a "fix-the-shape-and-everything-breaks" cascade that is the load-bearing risk Step 1 exists to prevent.

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

- [ ] AC-1 — `src/codegenie/rag/__init__.py` and `src/codegenie/rag/models.py` exist.
- [ ] AC-2 — `SolvedExample` model in `rag/models.py` with `frozen=True, extra="forbid"` and these fields exactly:
  - `id: SolvedExampleId`
  - `task_class: TaskClassId` (or `TaskClassName` — match the canonical Phase-3 name; document per Rule 7)
  - `language: Language` (or `LanguageName`)
  - `build_system: PackageManager` (the Phase-1 ADR-0013-owned enum; **do not redefine**)
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
- [ ] AC-3 — `Query` model with `frozen=True, extra="forbid"`:
  - `task_class: TaskClassId`
  - `language: Language`
  - `build_system: PackageManager`
  - `cve_id: CveId`
  - `affected_package: PackageId`
  - `failure_mode: FailureModeTag` — **typed `Literal`**, not free-text. The literal set lives at module level: `FailureModeTag = Literal["build_break", "test_fail", "typecheck_fail", "lockfile_resolution_fail", "callsite_signature_drift", "policy_block"]`. Six values cover Phase-4 fixture portfolio per arch §Fixture portfolio + §Edge cases.
  - `def digest(self) -> BlobDigest:` — returns BLAKE3 hex over the model's canonical JSON dump (sorted keys, no spaces). Deterministic across runs.
- [ ] AC-4 — `RetrievalOutcome` closed three-way union:
  - `RagHit` (`kind: Literal["hit"]`, `record: SolvedExample`, `similarity: Similarity`)
  - `RagMiss` (`kind: Literal["miss"]`, `reason: Literal["empty_store", "no_record_above_floor", "all_records_chain_orphan", "all_records_model_mismatch"]`)
  - `RagDegraded` (`kind: Literal["degraded"]`, `record: SolvedExample`, `similarity: Similarity`) — record returned but below `high_floor` and at-or-above `degraded_floor`.
  - `RetrievalOutcome = Annotated[RagHit | RagMiss | RagDegraded, Discriminator("kind")]`.
- [ ] AC-5 — `RecordProvenance` model with `frozen=True, extra="forbid"`:
  - `workflow_id: WorkflowId`
  - `event_chain_head: ChainHead` (BLAKE3 — the spanning-log head this record was witnessed at)
  - `created_at: datetime` (tz-aware UTC)
  - `signing_method: Literal["hmac_sha256_chain", "operator_attestation"]`.
- [ ] AC-6 — `BudgetSnapshot` model in `src/codegenie/fallback/budget.py` with `frozen=True, extra="forbid"`:
  - `consumed_tokens: TokenCount`
  - `consumed_dollars: Decimal`
  - `outstanding_tokens: TokenCount`
  - `cap_tokens: TokenCount`
  - `cap_dollars: Decimal`.
  - **Invariants enforced via `@model_validator(mode="after")`:** `consumed_tokens + outstanding_tokens <= cap_tokens` (refused otherwise); `consumed_dollars <= cap_dollars`; `consumed_dollars >= 0`. (`TokenCount` ≥ 0 is enforced by the `parse_token_count` smart constructor at the boundary; here we re-assert the relation via Pydantic validation.)
- [ ] AC-7 — `BudgetToken` model with `frozen=True, extra="forbid"`:
  - `id: BudgetTokenId`
  - `precharge_tokens: TokenCount`
  - `_marker: Literal["budget_token"] = "budget_token"` — the capability tag the import-linter contract (S2-05) and the AST-walk in S2-05 use to verify capability flow.
  - **No issuer logic here** — `LlmInvocationGuard.precharge` (S2-05) is where issuance happens. This story ships the shape only.
- [ ] AC-8 — `TypecheckNodeSignal` model (named per arch §Data model; mirrors Phase-3 `TrustSignal` shape):
  - `kind: Literal["typecheck.typescript"] = "typecheck.typescript"`
  - `passed: bool`
  - `details: dict[str, str | int | bool]` (carries forward Phase 3 convention; no Phase-4 widening)
  - `confidence: Literal["high", "medium", "low"]`
  - **No `@register_signal_kind` call here** — S6-05 wires it; this story ships the model alone.
- [ ] AC-9 — All seven models export from their package `__init__.py` and through `codegenie.rag`/`codegenie.fallback` boundary modules.

### Verification

- [ ] AC-10 — `tests/unit/rag/test_models.py` covers each model:
  - Happy: each constructs from a valid dict; tz-aware `datetime` accepted; naive `datetime` rejected.
  - Sad — `extra="forbid"` rejects unknown keys.
  - Sad — `frozen=True` rejects assignment.
  - Sad — discriminator routes unknown `kind` to `ValidationError` (`RetrievalOutcome`).
  - Sad — `Query.digest()` is **deterministic** across two constructions with the same field values.
  - Sad — `Query.digest()` **differs** when any single field changes.
  - Sad — `Query.digest()` length is exactly 64 hex chars (BLAKE3).
  - Sad — `Query.failure_mode` outside the six literals rejected.
  - Sad — `BudgetSnapshot` with `consumed_tokens + outstanding_tokens > cap_tokens` rejected.
  - Sad — `BudgetSnapshot` with `consumed_dollars > cap_dollars` rejected.
  - Sad — `BudgetSnapshot` with `consumed_dollars < 0` rejected.
  - Sad — `RagHit` constructed with `similarity = Similarity(0.85)` (boundary inclusive) accepted; with `Similarity(1.5)` the `parse_similarity` boundary at S1-01 has already rejected (re-verify the wrap point — the Pydantic model itself does not re-validate `Similarity` beyond the NewType identity).
- [ ] AC-11 — **`Query.digest()` determinism property** (`tests/property/test_query_digest_determinism.py`):
  - Hypothesis-generate `Query` field values (drawn from valid strategies). For any drawn `q`, `q.digest() == q.digest()` (purity) and `q.digest()` is 64 lowercase hex.
  - Field-perturbation: changing any single field changes the digest (parametrized over each field).
- [ ] AC-12 — **`SolvedExample` JSON round-trip property** (`tests/property/test_solved_example_yaml_roundtrip.py` — skeleton; YAML roundtrip lands fully in S4-04. JSON round-trip here proves the Pydantic shape is serializable):
  - For Hypothesis-generated valid `SolvedExample`, `SolvedExample.model_validate_json(s.model_dump_json()) == s` (deep equal).
- [ ] AC-13 — **`tz-aware datetime` enforcement** — parametrized test: `created_at=datetime(2026, 1, 1)` (naive) → `ValidationError`; `created_at=datetime(2026, 1, 1, tzinfo=UTC)` → `Ok`. Applies to both `SolvedExample.created_at` and `RecordProvenance.created_at`.
- [ ] AC-14 — `mypy --strict src/codegenie/rag/` and `mypy --strict src/codegenie/fallback/` clean. `ruff check`, `ruff format --check` clean.
- [ ] AC-15 — The TDD plan's red tests exist, are committed, and are green.

## Implementation outline

1. Create `src/codegenie/rag/__init__.py` and `src/codegenie/rag/models.py`. Ensure `tests/unit/rag/__init__.py` exists.
2. Define `FailureModeTag = Literal[...]` (six values) at module top of `rag/models.py` per AC-3.
3. Define `RecordProvenance`, `Query`, `SolvedExample` (in order — `SolvedExample` references both), `RagHit`, `RagMiss`, `RagDegraded`, `RetrievalOutcome`.
4. Implement `Query.digest()` using BLAKE3 over `self.model_dump_json(round_trip=True, by_alias=False)` with `sort_keys`-equivalent canonicalization (Pydantic v2 `mode="json"` + a stable serialization helper).
5. Add tz-aware datetime validator: `@field_validator("created_at") def _utc_aware(cls, v: datetime) -> datetime` rejecting `v.tzinfo is None`.
6. Create `src/codegenie/fallback/budget.py` containing only `BudgetSnapshot` and `BudgetToken` (issuer logic deferred to S2-05). Implement the `@model_validator(mode="after")` invariants on `BudgetSnapshot`.
7. Move `TypecheckNodeSignal` to `plugins/vulnerability-remediation--node--npm/adapters/typecheck_signal_model.py` **OR** `src/codegenie/fallback/typecheck_signal.py` — pick the location S6-05 imports from. Document choice in attempt log; the model is plugin-resident vs. substrate-resident per arch §Component 11.
   - **Resolution: ship at `src/codegenie/rag/models.py` for now** (it is a Pydantic data class; the *collector* is plugin-resident in S6-05). Cross-plugin reuse is anticipated by ADR-0015.
8. Wire `src/codegenie/rag/__init__.py` re-exports.
9. Write `tests/unit/rag/test_models.py`, `tests/unit/fallback/test_budget_models.py`, `tests/property/test_query_digest_determinism.py`, `tests/property/test_solved_example_yaml_roundtrip.py` (skeleton).
10. Run `mypy --strict` + `make check`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/rag/test_models.py`

```python
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

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
from codegenie.fallback.budget import BudgetSnapshot, BudgetToken
from codegenie.fallback.plan_proposal import PlanProposalDepBump
from codegenie.types.identifiers import (
    BlobDigest, BudgetTokenId, ChainHead, CveId, Language, ModelId,
    PackageId, Similarity, SolvedExampleId, TaskClassId, TokenCount, WorkflowId,
)
from codegenie.probes.node_build_system import PackageManager


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
    "build_system": PackageManager.NPM.value if hasattr(PackageManager, "NPM") else "npm",
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
    "build_system": PackageManager.NPM.value if hasattr(PackageManager, "NPM") else "npm",
    "cve_id": "CVE-2026-1234",
    "affected_package": "express@4.18.0",
    "failure_mode": "build_break",
}


def test_solved_example_happy():
    s = SolvedExample.model_validate(_SOLVED)
    assert s.id == SolvedExampleId(_HEX64)
    assert s.created_at == _UTC_NOW


def test_solved_example_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        SolvedExample.model_validate({**_SOLVED, "created_at": datetime(2026, 1, 1)})


def test_solved_example_extra_keys_rejected():
    with pytest.raises(ValidationError):
        SolvedExample.model_validate({**_SOLVED, "shell": "rm"})


def test_solved_example_frozen():
    s = SolvedExample.model_validate(_SOLVED)
    with pytest.raises(ValidationError):
        s.cve_id = CveId("CVE-2026-9999")  # type: ignore[misc]


def test_query_digest_is_64_hex_lowercase():
    q = Query.model_validate(_QUERY)
    d = q.digest()
    assert len(d) == 64 and all(c in "0123456789abcdef" for c in d)


def test_query_digest_deterministic():
    q1 = Query.model_validate(_QUERY)
    q2 = Query.model_validate(_QUERY)
    assert q1.digest() == q2.digest()


@pytest.mark.parametrize(
    "field,value",
    [
        ("cve_id", "CVE-2026-9999"),
        ("affected_package", "lodash@4.17.21"),
        ("failure_mode", "test_fail"),
    ],
)
def test_query_digest_changes_with_field(field, value):
    base = Query.model_validate(_QUERY)
    perturbed = Query.model_validate({**_QUERY, field: value})
    assert base.digest() != perturbed.digest()


def test_query_failure_mode_literal():
    with pytest.raises(ValidationError):
        Query.model_validate({**_QUERY, "failure_mode": "freeform"})


# --- RetrievalOutcome ---

def test_rag_hit_happy():
    rh = RagHit.model_validate({
        "kind": "hit", "record": _SOLVED, "similarity": 0.96,
    })
    assert isinstance(rh.record, SolvedExample)


def test_retrieval_outcome_routes_by_kind():
    adapter = TypeAdapter(RetrievalOutcome)
    assert isinstance(
        adapter.validate_python({"kind": "miss", "reason": "empty_store"}),
        RagMiss,
    )
    assert isinstance(
        adapter.validate_python({"kind": "degraded", "record": _SOLVED, "similarity": 0.7}),
        RagDegraded,
    )


def test_retrieval_outcome_unknown_kind_rejected():
    adapter = TypeAdapter(RetrievalOutcome)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "exception", "trace": "..."})


# --- BudgetSnapshot invariants ---

def test_budget_snapshot_happy():
    snap = BudgetSnapshot(
        consumed_tokens=TokenCount(100),
        consumed_dollars=Decimal("0.5"),
        outstanding_tokens=TokenCount(0),
        cap_tokens=TokenCount(1_000),
        cap_dollars=Decimal("1.5"),
    )
    assert snap.consumed_tokens == 100


def test_budget_snapshot_consumed_plus_outstanding_exceeds_cap_rejected():
    with pytest.raises(ValidationError):
        BudgetSnapshot(
            consumed_tokens=TokenCount(800),
            consumed_dollars=Decimal("0.5"),
            outstanding_tokens=TokenCount(300),
            cap_tokens=TokenCount(1_000),
            cap_dollars=Decimal("1.5"),
        )


def test_budget_snapshot_consumed_dollars_exceeds_cap_rejected():
    with pytest.raises(ValidationError):
        BudgetSnapshot(
            consumed_tokens=TokenCount(100),
            consumed_dollars=Decimal("2.0"),
            outstanding_tokens=TokenCount(0),
            cap_tokens=TokenCount(1_000),
            cap_dollars=Decimal("1.5"),
        )


def test_budget_snapshot_negative_dollars_rejected():
    with pytest.raises(ValidationError):
        BudgetSnapshot(
            consumed_tokens=TokenCount(100),
            consumed_dollars=Decimal("-0.5"),
            outstanding_tokens=TokenCount(0),
            cap_tokens=TokenCount(1_000),
            cap_dollars=Decimal("1.5"),
        )


# --- BudgetToken ---

def test_budget_token_marker():
    bt = BudgetToken(
        id=BudgetTokenId("12345678-1234-4abc-89ab-1234567890ab"),
        precharge_tokens=TokenCount(5_000),
    )
    assert bt._marker == "budget_token"


# --- TypecheckNodeSignal ---

def test_typecheck_signal_kind_pinned():
    sig = TypecheckNodeSignal(
        passed=True, details={"errors": 0}, confidence="high",
    )
    assert sig.kind == "typecheck.typescript"
```

The `Query.digest()` Hypothesis property:

```python
# tests/property/test_query_digest_determinism.py
from __future__ import annotations

from hypothesis import given, strategies as st

from codegenie.rag.models import Query


@given(cve=st.from_regex(r"^CVE-\d{4}-\d{4,7}$", fullmatch=True))
def test_query_digest_is_deterministic(cve):
    base = {
        "task_class": "vuln_remediation",
        "language": "typescript",
        "build_system": "npm",
        "cve_id": cve,
        "affected_package": "lodash@4.17.21",
        "failure_mode": "build_break",
    }
    q1 = Query.model_validate(base)
    q2 = Query.model_validate(base)
    assert q1.digest() == q2.digest()
    assert len(q1.digest()) == 64
```

State why it fails: `ImportError` — `codegenie.rag.models`, `codegenie.fallback.budget` don't exist.

### Green — make it pass

- Create `rag/__init__.py`, `rag/models.py`, `fallback/budget.py`.
- Wire types, validators, and `digest()` implementation. Use `blake3` for the digest (already a project dep).
- Export from `__init__.py` modules.

### Refactor — clean up

- Lift the literal sets to module-level `Final` constants where they recur (e.g., `_FAILURE_MODE_TAGS: Final[tuple[str, ...]]`).
- Docstring each model naming the contract surface ("CONTRACT — persisted in chromadb; Phase 5 reads `.digest()`; ADR-0016.").
- The `_marker` field on `BudgetToken` carries the inline comment naming S2-05 (the issuer) and the import-linter contract.
- Edge cases enumerated in arch that touch this code: #14 (chain-orphan — `RecordProvenance.event_chain_head` carries the chain anchor used in S5-03 exclusion), #19 (model-mismatch — `SolvedExample.embedding_model: ModelId` is the field compared against `embedder.model_digest()` in S5-03).
- Naming alignment per Rule 7: if the arch uses `TaskClassName` but `identifiers.py` ships `TaskClassId`, document the choice in the attempt log and use the *existing* canonical name.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/__init__.py` | NEW — package skeleton. |
| `src/codegenie/rag/models.py` | NEW — `SolvedExample`, `Query`, `RecordProvenance`, `RetrievalOutcome` (3 variants), `TypecheckNodeSignal`. |
| `src/codegenie/fallback/budget.py` | NEW — `BudgetSnapshot`, `BudgetToken` shapes (issuer logic deferred to S2-05). |
| `src/codegenie/fallback/__init__.py` | Add `BudgetSnapshot`/`BudgetToken` to exports. |
| `tests/unit/rag/__init__.py` | NEW — package marker. |
| `tests/unit/rag/test_models.py` | NEW — happy/sad paths for all five RAG-side models. |
| `tests/unit/fallback/test_budget_models.py` | NEW — `BudgetSnapshot` invariant checks; `BudgetToken._marker` pin. |
| `tests/property/test_query_digest_determinism.py` | NEW — Hypothesis purity + field-perturbation. |
| `tests/property/test_solved_example_yaml_roundtrip.py` | NEW skeleton — JSON round-trip; YAML round-trip lands in S4-04. |

## Out of scope

- **`SolvedExampleStore` Protocol + `ChromaPersistentStore`** — S4-03 (consumes `SolvedExample`).
- **`SolvedExampleRetriever.query`** — S5-01 (consumes `Query` + emits `RetrievalOutcome`).
- **`LlmInvocationGuard.precharge/reconcile`** — S2-05 (issues `BudgetToken`; emits `BudgetSnapshot`).
- **`RecordProvenance.verify(record, spanning_log) -> bool`** — S4-05 (this story ships only the model, not the chain-verify logic).
- **YAML serialization of `SolvedExample` to `.codegenie/rag/records/<id>.yaml`** — S4-04.
- **`TypecheckTypescriptSignal` collector** — S6-05 (this story ships the model; the collector wraps `tsc` and `@register_signal_kind`s it).
- **Path-scoped fence amendment** — S1-05 (no chromadb / fastembed import yet — this story is pure Pydantic).

## Notes for the implementer

- **Verify Phase-2/3 canonical names before typing the fields (Rule 8 + Rule 7).** Arch §Data model uses `TaskClassName`, `LanguageName`, `BuildSystemName` — these may not match the names in `codegenie.types.identifiers` (likely `TaskClassId`, `Language`, and `PackageManager`). The story conforms to **the existing canonical names**; document the alignment in the attempt log. If a Phase-3 module already imports a name that drifts from the arch doc, the existing import wins (CLAUDE.md "Match the codebase's conventions").
- **`PackageManager` is Phase-1-owned (ADR-0013).** Re-export, never redefine. The `SolvedExample.build_system: PackageManager` field carries the enum directly.
- **`Query.digest()` must be deterministic across runs.** Use Pydantic v2's `model_dump_json(round_trip=True)` (canonical key order) → BLAKE3. Test runs assert this; field-perturbation parametrization is the mutation guard.
- **tz-aware datetime is mandatory.** A naive `datetime` in the chain head silently breaks `RecordProvenance.verify` across timezone-shifted CI runners. The validator (`@field_validator("created_at")`) rejects `v.tzinfo is None`.
- **`BudgetSnapshot` invariants are validated at construction.** Pydantic v2 `@model_validator(mode="after")` runs after type coercion; raises `ValidationError`. The `consumed_tokens + outstanding_tokens <= cap_tokens` invariant is the load-bearing one Phase 5's running-total projection consumes.
- **`BudgetToken._marker` is the capability tag.** S2-05's import-linter contract (`BudgetToken` may be imported only by `tier.py` and `leaf/anthropic_adapter.py`) is the *containment* contract; `_marker` is the *identity* tag the AST-walk uses to recognize a capability flow. Do not rename without surfacing per Rule 7.
- **`TypecheckNodeSignal` location.** Arch §Component 11 puts the *collector* in the plugin (`plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py`), but the *model* is generic and ships here at `src/codegenie/rag/models.py`. ADR-0015 anticipates Phase-7 plugins reusing the model. If this turns out to feel wrong at S6-05 implementation time, surface per Rule 7.
- **`RetrievalOutcome.RagDegraded` carries a `SolvedExample` record.** S5-02's two-threshold band returns a `record` for `degraded` so the LLM gets the few-shot with an explicit "low-confidence" tag (arch §Agentic best practices §Confidence handling). A `RagDegraded` without a `record` is a model bug.
- **Do not import `chromadb`/`fastembed`/`onnxruntime`** in this story's files. The path-scoped fence (S1-05) admits them only under `src/codegenie/rag/` modules that *need* them (`store.py`, `embedder.py`). `models.py` is pure Pydantic; pulling chromadb in here would trigger the fence-CI failure.
- **Newtypes everywhere.** Every field that names a domain primitive is typed against an existing newtype from `codegenie.types.identifiers`. The AST source-scan from S1-01 (`test_phase4_no_raw_str_for_domain_ids.py`) re-runs after this story lands and must remain green.
