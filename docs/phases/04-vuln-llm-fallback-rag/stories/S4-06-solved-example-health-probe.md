# Story S4-06 — `SolvedExampleHealthProbe` — registered via `@register_probe`

**Step:** Step 4 — Ship the RAG side — `EmbeddingProvider` + UDS sidecar, `SolvedExampleStore`, `QueryKeyCache`, `SolvedExampleHealthProbe`
**Status:** Ready
**Effort:** S
**Depends on:** S4-04 (`SolvedExampleStore.health()` — the data source)
**ADRs honored:** ADR-P4-005 (probe reads through the store's `health()` API; never imports chromadb), ADR-P4-006 (`mixed_embedding_models` is the digest-drift sentinel), ADR-P4-015 (`task_class` partitioning is reflected in the probe's per-class counts)

## Context

`SolvedExampleHealthProbe` is the Phase-2 `IndexHealthProbe` (B2) analog applied to the RAG corpus: it surfaces staleness, embedding-model drift, and empty-store conditions as a first-class probe alongside every other Phase-1+ probe. It is the *only* Phase-4 probe and reuses Phase 0's probe registry verbatim (per `CLAUDE.md` load-bearing commitments: "Adding Java, Python, or a new task type must be new probes + new Skills, never edits to existing probes or the coordinator"). The probe **never raises**; it emits `confidence=low` when `count == 0` or `mixed_embedding_models == True`. Phase 4 only *surfaces* the probe; **gating** on it (e.g., refusing to query RAG when mixed digests detected) is Phase 5 work — this story does not couple the probe output to the engine flow.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design"` #11 `SolvedExampleHealthProbe` — Probe ABC reuse, output fields, low-confidence triggers.
  - `../phase-arch-design.md §"Goals"` G15 — index/health probes' honest-confidence discipline (B2 ancestor).
  - `../phase-arch-design.md §"Edge cases"` rows #2 (digest mismatch), #3 (corruption) — the probe is the place these surface non-fatally.
- **Phase ADRs:**
  - `../ADRs/0005-chromadb-in-process-with-stale-lock-detection.md` — ADR-P4-005 — probe must route through `SolvedExampleStore.health()`; no direct chromadb import.
  - `../ADRs/0006-bge-small-en-embedding-model-sha-pinned.md` — ADR-P4-006 — `mixed_embedding_models` is the operator-facing surface for Gap-2 staleness.
- **Production ADRs:**
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — honest-confidence discipline; probe never lies.
  - `../../../production/design.md §"Continuous gather"` — probes as first-class continuous-gather artifacts.
- **Source design:**
  - `../final-design.md §"Components"` #11 — probe specification.
  - `../final-design.md §"Synthesis ledger"` — Phase-1 probe ABC reuse.
- **Existing code:**
  - `src/codegenie/probes/contract.py` (Phase 0) — `Probe` ABC + `@register_probe` decorator + `ProbeOutput`.
  - `src/codegenie/probes/__init__.py` (Phase 0) — registry surface.
  - `src/codegenie/rag/store.py` (S4-04) — `SolvedExampleStore.health()` returns `StoreHealth`.

## Goal

Ship `src/codegenie/probes/solved_example_health.py` exposing a probe class registered via `@register_probe`, with `applies_to_tasks=["vuln_remediation"]`, `applies_to_languages=["*"]`, that reads `SolvedExampleStore.health()` and emits `ProbeOutput(confidence=..., data=..., provenance=...)` where `confidence == "low"` iff `count == 0` OR `mixed_embedding_models == True`.

## Acceptance criteria

- [ ] `src/codegenie/probes/solved_example_health.py` defines a probe class (e.g., `class SolvedExampleHealthProbe(Probe)`) decorated `@register_probe(name="solved_example_health", applies_to_tasks=["vuln_remediation"], applies_to_languages=["*"])`.
- [ ] The probe is discovered by Phase 0's registry — `from codegenie.probes import get_registry; get_registry().probes["solved_example_health"]` returns the class.
- [ ] `Probe.run(repo_ctx) -> ProbeOutput` is the contract method. Implementation:
  - Constructs a `SolvedExampleStore` from the run config (root, embed_dims, model_digest from current `EmbeddingProvider`).
  - On store-construction error (corruption, missing dir): returns `ProbeOutput(confidence="low", data={"count": 0, "error": "store_unavailable"}, ...)` — **does not raise**.
  - On `SolvedExampleProvider.available() == False` (model not fetched): returns `ProbeOutput(confidence="low", data={"count": 0, "error": "embedding_provider_unavailable"}, ...)`.
  - On happy path: calls `store.read()` → `health()`; populates `data`.
- [ ] `ProbeOutput.data` is a dict containing exactly the following keys (extra forbidden via per-probe schema if Phase 0 enforces; otherwise as a documented contract): `count`, `embedding_model_digest`, `provider_name`, `dimensions`, `newest_example_age_days`, `mixed_embedding_models` (bool), `query_latency_p50_ms`, `merge_status_distribution` (dict[str,int] keyed by `"pending_human"`/`"merged"`/`"withdrawn"`).
- [ ] **Confidence rules:**
  - `confidence = "low"` iff `data["count"] == 0` OR `data["mixed_embedding_models"] is True` OR `data` carries an `"error"` key.
  - `confidence = "high"` otherwise.
  - No `"medium"` bucket (the probe is binary; honest-confidence discipline).
- [ ] Probe **never raises** — every exception path produces a `ProbeOutput(confidence="low", data={"error": "<reason>"}, ...)` and an `audit.warning: probe.solved_example_health.swallowed_error` event with the exception type (no traceback content in the audit body — `[S]` discipline).
- [ ] `query_latency_p50_ms` is measured *during* the probe run (10-sample warm probe against the store with a dummy 384-zero vector); if the store is empty, `query_latency_p50_ms` is `None` (JSON null) — the probe does not synthesize fake latencies.
- [ ] Probe `applies_to_tasks=["vuln_remediation"]` so Phase 7's Chainguard task class does not auto-include it (Phase 7 may opt-in additively).
- [ ] `tests/unit/probes/test_solved_example_health_probe.py` ships with ≥ 4 tests: (a) empty store → `count=0`, `confidence="low"`; (b) populated store with single-digest examples → `confidence="high"`; (c) mixed-digest store → `mixed_embedding_models=True`, `confidence="low"`; (d) store construction error swallowed → `confidence="low"`, audit warning emitted, no raise.
- [ ] `tests/unit/probes/test_solved_example_health_probe_registered.py` — asserts `@register_probe` registration is visible in the registry; `applies_to_tasks == ["vuln_remediation"]`; `applies_to_languages == ["*"]`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/probes/solved_example_health.py`, `pytest tests/unit/probes/test_solved_example_health_probe*` all pass.

## Implementation outline

1. Write the failing tests first (TDD plan below).
2. Create `src/codegenie/probes/solved_example_health.py`:
   - Import `Probe`, `ProbeOutput`, `@register_probe` from `codegenie.probes.contract`.
   - Import `SolvedExampleStore` from `codegenie.rag.store`.
   - Import the active `EmbeddingProvider` factory (or a getter from a small config module — defer the wiring detail to the engine factory in S5).
   - `@register_probe(name="solved_example_health", applies_to_tasks=["vuln_remediation"], applies_to_languages=["*"])`
     `class SolvedExampleHealthProbe(Probe): ...`
   - `def run(self, repo_ctx)`:
     - Try to construct `SolvedExampleStore` and resolve the embedding provider; on failure, return the `confidence="low"` shape with `error` key.
     - Open `store.read()`; call `store.health()`.
     - Sample query latency (10× warm probe with a zero-vector against current digest).
     - Build `data` dict.
     - Return `ProbeOutput(confidence=..., data=..., provenance=Provenance(probe="solved_example_health", run_at=..., source="local"))`.
3. Run lint / format / mypy / pytest.

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/probes/test_solved_example_health_probe.py`

```python
from pathlib import Path
import pytest

# Probe import triggers @register_probe side-effect.
from codegenie.probes.solved_example_health import SolvedExampleHealthProbe


def test_empty_store_returns_low_confidence(tmp_path: Path, fake_repo_ctx) -> None:
    """The corpus starts empty. The probe MUST surface this honestly so
    the operator does not see a green-shaped 'RAG healthy' signal when
    there's nothing to retrieve from."""
    fake_repo_ctx.rag_root = tmp_path  # store backed by tmp_path
    out = SolvedExampleHealthProbe().run(fake_repo_ctx)
    assert out.confidence == "low"
    assert out.data["count"] == 0


def test_mixed_embedding_models_low_confidence(populated_mixed_digest_store, fake_repo_ctx) -> None:
    """Gap-2 operator-facing surface: if the corpus contains vectors from
    two different embedding models, similarity scores are mathematically
    meaningless. The probe is the early-warning channel before retrieval
    silently returns wrong neighbors."""
    fake_repo_ctx.rag_root = populated_mixed_digest_store
    out = SolvedExampleHealthProbe().run(fake_repo_ctx)
    assert out.data["mixed_embedding_models"] is True
    assert out.confidence == "low"


def test_healthy_populated_store_high_confidence(populated_single_digest_store, fake_repo_ctx) -> None:
    """A populated single-digest store with successful latency-probe samples
    yields confidence=high. This is the only path that does."""
    fake_repo_ctx.rag_root = populated_single_digest_store
    out = SolvedExampleHealthProbe().run(fake_repo_ctx)
    assert out.confidence == "high"
    assert out.data["count"] >= 1
    assert out.data["mixed_embedding_models"] is False
    assert out.data["query_latency_p50_ms"] is not None


def test_store_construction_error_swallowed(tmp_path: Path, fake_repo_ctx,
                                              monkeypatch: pytest.MonkeyPatch,
                                              audit_capture) -> None:
    """The probe NEVER raises. A corrupted store, a missing model, a permission
    error — all become confidence=low + an audit warning. The orchestrator's
    probe loop must never crash on a single probe."""
    from codegenie.rag import store as store_mod
    def _boom(*args, **kwargs):
        raise OSError("permission denied")
    monkeypatch.setattr(store_mod, "SolvedExampleStore", _boom)

    fake_repo_ctx.rag_root = tmp_path
    out = SolvedExampleHealthProbe().run(fake_repo_ctx)
    assert out.confidence == "low"
    assert "error" in out.data
    assert any(e.kind == "probe.solved_example_health.swallowed_error" for e in audit_capture)
```

Path: `tests/unit/probes/test_solved_example_health_probe_registered.py`

```python
import codegenie.probes.solved_example_health  # noqa: F401 — side-effect import
from codegenie.probes import get_registry


def test_probe_registered_via_decorator() -> None:
    """Probes must register via @register_probe — never via edits to a
    central list. CLAUDE.md load-bearing rule: 'Adding a new probe is
    new probes + new Skills, never edits to existing probes or the
    coordinator.'"""
    reg = get_registry()
    probe = reg.probes["solved_example_health"]
    assert probe.applies_to_tasks == ["vuln_remediation"]
    assert probe.applies_to_languages == ["*"]
```

Commit red. Both fail (`ImportError`).

### Green

- `solved_example_health.py`: ~80 lines.
- The `fake_repo_ctx`, `populated_single_digest_store`, `populated_mixed_digest_store`, and `audit_capture` fixtures live in `tests/conftest.py` (shared with S4-04's test suite).

### Refactor

- Extract `_sample_query_latency(store, dims) -> float | None` helper.
- Docstrings cite ADR-P4-006 and the B2 IndexHealthProbe ancestor.
- Add explicit `from __future__ import annotations` for forward references.
- Verify the probe's `applies_to_tasks` matches the Literal in `task_class` to avoid drift.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/solved_example_health.py` | New — probe class |
| `tests/unit/probes/test_solved_example_health_probe.py` | New — confidence + error-swallowing |
| `tests/unit/probes/test_solved_example_health_probe_registered.py` | New — registry discovery |
| `tests/conftest.py` | Add `populated_single_digest_store`, `populated_mixed_digest_store` fixtures if not present |

## Out of scope

- **Gating on probe output** — Phase 5 owns this. Phase 4 only *surfaces* the probe; refusing RAG queries on `mixed_embedding_models=True` is a Phase-5 decision (see `phase-arch-design.md §"Component design"` #11 note: "Phase 4 only surfaces the probe; gating on it is Phase 5 work").
- **Chainguard-task-class participation** — Phase 7 opt-in additively per ADR-P4-015.
- **Probe scheduling / continuous gather operationalization** — Phase 14.
- **Probe telemetry export** — Phase 13's cost-ledger consumer is the natural home; the probe writes structured JSON, the exporter reads.
- **Auto-recovery suggestions** — the probe surfaces facts; recovery (`codegenie solved-examples reindex`) is operator-driven via S4-07's CLI.

## Notes for the implementer

- **The probe must NEVER raise.** Every exception path becomes `confidence="low"` + audit warning. This is the load-bearing invariant: a single broken probe must not crash the orchestrator's probe loop. Add an outer `try/except Exception` around the entire `run` body.
- **Latency sampling is a *probe of the probe target*, not an op-side instrumentation.** The point is to surface what queries actually take in this operator's environment — laptop vs CI vs Linux jail. Sample 10× with a zero vector; report p50.
- **`merge_status_distribution` is forward-compatible.** Phase 4 only writes `pending_human`; Phase 11's webhook promotes to `merged`; Phase 9's audit handles `withdrawn`. The probe surfaces all three keys with default 0 counts so the operator-facing surface doesn't reshape across phases.
- **`embedding_model_digest` in the probe output is the operator's diagnostic.** Pair it with `newest_example_age_days` and `count` — if the operator sees `count=42, newest_example_age_days=14, mixed_embedding_models=True`, they can deduce a model bump happened 14 days ago and decide whether to reindex.
- **Do not import chromadb.** The probe routes through `SolvedExampleStore.health()` only. Fence-CI in S1-07 enforces; if you find yourself reaching for `chromadb.HttpClient` here, surface the omission in S4-04's surface area instead.
- **`applies_to_tasks=["vuln_remediation"]` is the correct value for Phase 4.** Phase 7's Chainguard task class will opt in by extending the list in an ADR amendment (or by a sibling probe — extension by addition is preferred per CLAUDE.md). Do not preemptively widen.
- **`provenance` field on `ProbeOutput`.** Phase 0's probe contract mandates provenance (probe name, run timestamp, source). Use the standard helper; do not invent a new shape.
- **Probe registration is import-time side-effecting.** The `@register_probe` decorator runs on module import. Ensure the module is imported by Phase 0's probe-discovery mechanism — typically a package-level `__init__.py` re-export or an entry-point declaration. If Phase 0 uses lazy auto-discovery, this story may need to add a one-line import in `src/codegenie/probes/__init__.py`. Surface any wiring gap.
