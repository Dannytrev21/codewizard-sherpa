# Story S4-01 — `SentenceTransformerProvider` — `bge-small-en-v1.5` SHA-pinned

**Step:** Step 4 — Ship the RAG side — `EmbeddingProvider` + UDS sidecar, `SolvedExampleStore`, `QueryKeyCache`, `SolvedExampleHealthProbe`
**Status:** Ready
**Effort:** M
**Depends on:** S1-03 (`rag/contract.py` `EmbeddingProvider` Protocol + `rag/models.py` `SolvedExample` schema)
**ADRs honored:** ADR-P4-006 (`bge-small-en-v1.5` SHA-pinned), ADR-P4-005 (chromadb encapsulation — provider must not import chromadb)

## Context

`SentenceTransformerProvider` is the default and only-active `EmbeddingProvider` implementation in Phase 4. It loads `BAAI/bge-small-en-v1.5` (384-dim) from the local `huggingface_hub` cache via `snapshot_download(revision=<commit_sha>)`, re-verifies the SHA on every load, and hard-fails when the on-disk digest does not match `tools/digests.yaml`. A `VoyageProvider` stub ships at the same time but returns `available() == False` without an explicit opt-in (Phase 14 reopens). This story is the load-bearing supply-chain pin for the entire RAG side — every downstream component (`SolvedExampleStore`, `QueryKeyCache`, writeback, the health probe) trusts the digest this provider exposes.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design"` #7 `EmbeddingProvider` ABC + `SentenceTransformerProvider` — Protocol signature, sidecar/in-proc split, telemetry-off discipline.
  - `../phase-arch-design.md §"Edge cases"` row #2 — embedding model digest mismatch behaviour (hard-fail at engine init; loud `embedding_model.hash_mismatch`).
  - `../phase-arch-design.md §"Gap analysis" §"Gap 2"` — digest mismatch invalidates retrieval, not just cache; this story plants the field the store filters on.
- **Phase ADRs:**
  - `../ADRs/0006-bge-small-en-embedding-model-sha-pinned.md` — ADR-P4-006 — `BAAI/bge-small-en-v1.5`, 384-d, SHA-pinned via `huggingface_hub.snapshot_download(repo_id, revision=<commit_sha>)`; first-write protection on `tools/digests.yaml`.
  - `../ADRs/0005-chromadb-in-process-with-stale-lock-detection.md` — ADR-P4-005 — fence-CI forbids `import chromadb` outside `rag/store.py`; this provider must not transitively import chromadb.
- **Production ADRs:**
  - `../../../production/adrs/0028-task-class-introduction-order.md` — task-class is in `SolvedExample`; the embedding model is task-class agnostic and must stay so.
- **Source design:**
  - `../final-design.md §"Components"` #8 — `EmbeddingProvider` ABC + `SentenceTransformerProvider`; cold boot ≤ 2.5s, warm embed ~28ms.
  - `../final-design.md §"Synthesis ledger"` row "Embedding model" — `bge-small` over MiniLM resolves critic §performance.1.
- **Existing code:**
  - `src/codegenie/rag/contract.py` (S1-03) — `EmbeddingProvider` Protocol the impl must satisfy.
  - `tools/digests.yaml` — the canonical SHA pin file (may need creation as part of this story if S1-03 didn't seed it).

## Goal

Ship `src/codegenie/rag/embeddings/local.py` exposing `SentenceTransformerProvider` that loads `BAAI/bge-small-en-v1.5` from `huggingface_hub.snapshot_download(revision=<sha>)`, re-verifies the SHA against `tools/digests.yaml` on every load, raises `EmbeddingDigestMismatch` (and emits `embedding_model.hash_mismatch` audit) on drift, exposes `model_digest`/`model_id`/`dimensions`/`available()`/`embed(texts)`, and ship `src/codegenie/rag/embeddings/voyage.py` as a registered stub whose `available()` returns `False` without `--embedding-provider=voyage`.

## Acceptance criteria

- [ ] `src/codegenie/rag/embeddings/local.py` defines `SentenceTransformerProvider` satisfying the `EmbeddingProvider` Protocol from `rag.contract`; importable as `from codegenie.rag.embeddings.local import SentenceTransformerProvider`.
- [ ] Constructor signature: `SentenceTransformerProvider(model_id: str = "BAAI/bge-small-en-v1.5", digests_path: Path = Path("tools/digests.yaml"))`. No other public init args.
- [ ] `tools/digests.yaml` contains a `bge-small-en-v1.5: <commit_sha>` entry (real HF commit SHA recorded; the test fixture for digest mismatch overrides the path).
- [ ] On `__init__`: reads the expected SHA from `digests_path`; calls `huggingface_hub.snapshot_download(repo_id=model_id, revision=<expected_sha>, cache_dir=...)`; verifies the returned snapshot directory's commit SHA matches; mismatch raises `EmbeddingDigestMismatch(expected, observed)` (a Phase-1 typed error subclass) **and** emits an `embedding_model.hash_mismatch` audit event with payload `{model_id, expected_digest, observed_digest, source: "init"}` before raising.
- [ ] `available() -> bool` returns `True` iff the model snapshot is present at the cache path **and** the digest matches; `False` otherwise (no exception thrown from `available()` — callers may probe it cheaply).
- [ ] `model_digest -> str` property returns the verified commit SHA; `model_id -> str` returns `"BAAI/bge-small-en-v1.5"`; `dimensions -> int` returns `384`.
- [ ] `embed(texts: Sequence[str]) -> list[list[float]]` returns one 384-float vector per input; empty `texts` returns `[]` cleanly (no `sentence_transformers` call); empty individual string is allowed and embedded.
- [ ] Telemetry is disabled **before any `sentence_transformers` import** — module-level code sets `HF_HUB_DISABLE_TELEMETRY=1`, `TRANSFORMERS_NO_ADVISORY_WARNINGS=1`, and similar env vars at module import; `tests/unit/rag/test_embedding_telemetry_disabled.py` asserts these env vars are set after importing the module.
- [ ] `src/codegenie/rag/embeddings/voyage.py` defines `VoyageProvider` satisfying the same Protocol; `available()` returns `False` unconditionally unless env `CODEGENIE_EMBEDDING_PROVIDER=voyage` is set; `embed()` raises `NotImplementedError("VoyageProvider opt-in path lands in Phase 14")` until then.
- [ ] No transitive `import chromadb` — `tests/fence/test_fence_phase4.py` extension covers `rag/embeddings/`; the story may add an AST-scan unit if the fence test is structurally absent.
- [ ] `tests/unit/rag/test_embedding_digest_mismatch_refuses.py` ships and covers the mismatch path (red test — see TDD plan).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/rag/embeddings/`, `pytest tests/unit/rag/test_embedding_*` all pass.

## Implementation outline

1. Write the failing tests (see TDD plan). Pin a synthetic `tools/digests.yaml` in a `tmp_path` fixture for the mismatch test so the real model cache is not required.
2. Create `src/codegenie/rag/embeddings/__init__.py` (empty exports surface).
3. Create `src/codegenie/rag/embeddings/local.py`. Top of file: `os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY","1")` and any other telemetry env-var muffles **before** the `from sentence_transformers import SentenceTransformer` line.
4. `class EmbeddingDigestMismatch(CodegenieError)` (extends Phase-1 `CodegenieError`). Payload includes `model_id`, `expected`, `observed`.
5. `SentenceTransformerProvider.__init__`: load expected SHA from YAML (`pyyaml`), call `snapshot_download(repo_id=model_id, revision=expected, local_files_only=False)`. Verify by reading `<snapshot_dir>/.git_commit` or by re-resolving the path against the cache layout. On mismatch: emit audit event, raise.
6. Implement `embed`, `available`, properties. `embed` lazily instantiates one `SentenceTransformer` instance per provider; reuse on subsequent calls.
7. Create `src/codegenie/rag/embeddings/voyage.py` per spec.
8. Ship/update `tools/digests.yaml` with the production-pinned SHA.
9. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`. Add the `test_embedding_telemetry_disabled.py` companion test.

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/rag/test_embedding_digest_mismatch_refuses.py`

```python
from pathlib import Path
import yaml
import pytest

from codegenie.rag.embeddings.local import (
    SentenceTransformerProvider,
    EmbeddingDigestMismatch,
)


def test_init_raises_when_observed_digest_does_not_match_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Digest drift is the single most dangerous silent failure for RAG —
    a swapped model invalidates every cosine score in the store. The provider
    must hard-fail at construction so no caller can accidentally embed under
    the wrong vector space.
    """
    fake_yaml = tmp_path / "digests.yaml"
    fake_yaml.write_text(yaml.safe_dump({"bge-small-en-v1.5": "deadbeef" * 5}))

    audit_events: list[dict] = []
    monkeypatch.setattr(
        "codegenie.rag.embeddings.local._emit_audit",
        lambda kind, payload: audit_events.append({"kind": kind, **payload}),
    )

    with pytest.raises(EmbeddingDigestMismatch) as exc:
        SentenceTransformerProvider(digests_path=fake_yaml)

    # Loud audit event fired *before* the raise — operator must be able to see it.
    assert any(e["kind"] == "embedding_model.hash_mismatch" for e in audit_events)
    assert exc.value.expected.startswith("deadbeef")
    assert exc.value.expected != exc.value.observed


def test_available_returns_false_on_digest_drift_without_raising(
    tmp_path: Path,
) -> None:
    """available() is a probe — callers (RagLlmEngine.available(),
    SolvedExampleHealthProbe) must be able to ask cheaply without
    catching an exception. False means 'unusable'; True means 'verified'.
    """
    fake_yaml = tmp_path / "digests.yaml"
    fake_yaml.write_text(yaml.safe_dump({"bge-small-en-v1.5": "deadbeef" * 5}))
    # Construct via a backdoor or check available() statically — the impl
    # decides whether to expose a classmethod. The intent: probe must not raise.
    assert SentenceTransformerProvider.probe_available(digests_path=fake_yaml) is False


def test_voyage_provider_unavailable_by_default() -> None:
    from codegenie.rag.embeddings.voyage import VoyageProvider

    p = VoyageProvider()
    assert p.available() is False
    with pytest.raises(NotImplementedError):
        p.embed(["hello"])
```

Run; expect `ImportError` / `AttributeError`. Commit red marker.

### Green

- Smallest possible `local.py` that satisfies the three tests: a class with `__init__` that reads the YAML, computes/observes a digest, raises with the audit hook fired first, plus a `probe_available` classmethod that returns `False` on mismatch silently.
- `voyage.py` is ~15 lines: a class with `available() == False` and `embed()` raising `NotImplementedError`.

### Refactor

- Extract a `_load_expected_digest(path: Path, key: str) -> str` helper for testability.
- Add full type annotations (`Sequence[str]`, `list[list[float]]`, `Path`).
- Docstrings citing ADR-P4-006 and the supply-chain rationale.
- Add `test_embedding_telemetry_disabled.py` — `import importlib; importlib.reload(...); assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"`.
- Add an `EmbeddingDigestMismatch` `__str__` that prints both digests truncated to 12 chars for log-friendly output.
- Verify the fence-CI test passes (`rag/embeddings/` does not transitively import `chromadb`).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/embeddings/__init__.py` | New — namespace package |
| `src/codegenie/rag/embeddings/local.py` | New — `SentenceTransformerProvider` |
| `src/codegenie/rag/embeddings/voyage.py` | New — registered stub provider |
| `tools/digests.yaml` | New or extended — pinned `bge-small-en-v1.5` commit SHA |
| `src/codegenie/rag/errors.py` | Add `EmbeddingDigestMismatch` (or place in `local.py` if errors module not present) |
| `tests/unit/rag/test_embedding_digest_mismatch_refuses.py` | New — red test |
| `tests/unit/rag/test_embedding_telemetry_disabled.py` | New — assert env vars set on import |
| `tests/unit/rag/test_voyage_provider_stub.py` | New — registered but unavailable |

## Out of scope

- **The UDS sidecar / `embed_worker.py`** — S4-02 owns the long-lived sidecar; this story ships the in-proc provider that the sidecar will wrap.
- **`codegenie models fetch` CLI subcommand** — S4-07 wires the operator-facing download/verify flow.
- **Re-embedding the corpus on digest swap** — S4-07 (`solved-examples reindex --model-digest <new>`).
- **`tools/digests.yaml` first-write pre-commit hook** — ADR-P4-006 mandates it; the hook itself ships in S7-06 (CI gates + runbook); this story only consumes the file.
- **VoyageProvider opt-in path** — Phase 14 (`final-design.md §"Open questions"` #6).

## Notes for the implementer

- **Telemetry-off before import is the easy-to-forget rule.** `os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY","1")` must run *before* `from sentence_transformers import ...` — the import triggers HF telemetry handshakes otherwise. Move all env-var mutations to the top of the module file, not inside `__init__`.
- **`snapshot_download` revision verification.** `huggingface_hub` returns the local snapshot path; the *guarantee* that the path reflects the requested revision depends on `local_files_only=False` actually re-resolving. In tests, prefer the cached layout (`~/.cache/huggingface/hub/models--BAAI--bge-small-en-v1.5/snapshots/<sha>/`) — the SHA is in the directory name; that's the cheapest observed-digest source.
- **`embed([])` is a legitimate call.** The store's reindex flow may probe with an empty batch; return `[]` without touching `sentence_transformers`. Hypothesis property `test_fingerprint_property.py` will exercise this.
- **`available()` must be cheap.** It's called from `RagLlmEngine.available()` and from the health probe; avoid loading the model just to probe. A file-existence + digest-string-compare is enough.
- **Do not pre-load the model in `__init__`.** Construction should verify the digest pin only. Model weights load lazily on first `embed()` call so the orchestrator startup path stays fast (~ 10ms) and the health probe doesn't pay 2.5s.
- **`EmbeddingDigestMismatch` is a typed Phase-1 error.** Inherit from `codegenie.errors.CodegenieError` so the CLI exit-code mapping in S1-06 routes it correctly. If S1-03 hasn't seeded the rag-specific error class, this story creates `src/codegenie/rag/errors.py` — one line.
- **Fence-CI compliance is load-bearing.** `import chromadb` is forbidden in this module (ADR-P4-005). `sentence_transformers` is allowed only inside `rag/embeddings/`; nowhere else. If the fence test in S1-07 doesn't already cover this path, surface the omission — do not silently widen the import graph.
