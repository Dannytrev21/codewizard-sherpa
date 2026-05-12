# Story S4-04 — `SolvedExampleStore` — chromadb in-process + flock + stale-lock-breaker (Gap 3) + always-filter-by-digest (Gap 2) + cross-repo filter

**Step:** Step 4 — Ship the RAG side — `EmbeddingProvider` + UDS sidecar, `SolvedExampleStore`, `QueryKeyCache`, `SolvedExampleHealthProbe`
**Status:** Ready
**Effort:** L
**Depends on:** S4-01 (`EmbeddingProvider.model_digest` is the filter input), S1-03 (`SolvedExample`, `Provenance`, `RetrievedExample` schemas), S1-06 (`--allow-cross-repo-rag` CLI flag plumbing)
**ADRs honored:** ADR-P4-005 (chromadb `PersistentClient` in-process + single-writer flock + stale-lock detection — Gap 3), ADR-P4-006 (`embedding_model_digest` filter on every query — Gap 2), ADR-P4-015 (`SolvedExample.task_class` generic), ADR-P4-008 (cross-repo retrieval defense-in-depth — NG7)

## Context

`SolvedExampleStore` is the load-bearing RAG primitive: it owns `chromadb`, owns the on-disk `.codegenie/rag/` namespace, and is the **single component every other RAG-side caller routes through**. Three previously-separable concerns collapse into this one class: (1) chromadb encapsulation per ADR-P4-005 (no other module imports `chromadb`), (2) the Gap-2 fix — `query()` **always** filters by current `EmbeddingProvider.model_digest` so a silent embedding-model swap cannot return mixed-vector-space results, and (3) the Gap-3 fix — single-writer `flock` with a stale-lock-breaker so a SIGKILL'd writer holding the exclusive lock cannot deadlock every other worker indefinitely. Cross-repo retrieval is filtered to same-repo-or-public by default (NG7 defense-in-depth); widening requires both a CLI flag and an env var. This story is the largest LOC concentration in Step 4.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design"` #4 `SolvedExampleStore` — full interface, two-table split, telemetry-off discipline.
  - `../phase-arch-design.md §"Gap analysis" §"Gap 2"` — `embedding_model_digest` filter on every query; no caller can forget.
  - `../phase-arch-design.md §"Gap analysis" §"Gap 3"` — stale-lock detection via `.lock.holder` (pid, hostname, timestamp) + 60s watchdog + `os.kill(pid, 0)`.
  - `../phase-arch-design.md §"Edge cases"` rows #3 (corruption quarantine), #15 (orphan body recovery), #16 (race on same `example_id`), #23 (cross-repo defense-in-depth).
- **Phase ADRs:**
  - `../ADRs/0005-chromadb-in-process-with-stale-lock-detection.md` — ADR-P4-005 — the chromadb posture; mandates `PersistentClient(is_persistent=True, allow_reset=False)`; telemetry off; two-table split; corruption quarantine.
  - `../ADRs/0006-bge-small-en-embedding-model-sha-pinned.md` — ADR-P4-006 — `model_digest` filter is mandatory on every query.
  - `../ADRs/0015-solved-example-schema-task-class-generic.md` — ADR-P4-015 — `task_class` is filterable metadata; default `task_class="vuln"` for Phase 4 queries.
  - `../ADRs/0008-prompt-injection-structural-defenses.md` — ADR-P4-008 — cross-repo retrieval is a defense-in-depth surface (NG7).
- **Production ADRs:**
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — same "honest-confidence" stance the store's `health()` surfaces upward to the probe.
- **Source design:**
  - `../final-design.md §"Components"` #7 `SolvedExampleStore` — single-writer discipline, body-first ordering, content-addressed `example_id`.
  - `../final-design.md §"Risks"` #4 — partial-write between body JSON and chromadb upsert.
- **Existing code:**
  - `src/codegenie/rag/models.py` (S1-03) — `SolvedExample`, `RetrievedExample`, `Provenance`.
  - `src/codegenie/rag/contract.py` (S1-03) — Protocols.
  - `src/codegenie/rag/embeddings/local.py` (S4-01) — `model_digest` source.
  - `tests/fence/test_fence_phase4.py` (S1-07) — `import chromadb` allowed *only* in this file.

## Goal

Ship `src/codegenie/rag/store.py` exposing `SolvedExampleStore(root, embed_dims, model_digest)` with `read()` / `write()` context managers acquiring shared/exclusive `flock`, a stale-lock-breaker that detects dead-PID lock holders after 60s, a `query()` method that **always** filters by the current `model_digest` plus a default cross-repo filter (`provenance.repo_url == current OR provenance.public == True`), corruption quarantine on `opens_cleanly()` failure, and a two-table split (chromadb stores `(id, embedding, small metadata)`; bodies live at `.codegenie/rag/bodies/<id>.json` canonical sorted-keys LF).

## Acceptance criteria

- [ ] `SolvedExampleStore(root: Path, embed_dims: int, model_digest: str, *, current_repo_url: str, allow_cross_repo: bool = False)` constructable; `__init__` does **not** open chromadb (lazy until first `read()` / `write()`); telemetry env vars set at module import time **before** any `import chromadb`.
- [ ] `read() -> AbstractContextManager[StoreReader]` acquires `fcntl.flock(LOCK_SH | LOCK_NB)` on `.codegenie/rag/.lock`; blocks with the 60s stale-lock watchdog (see below) when shared not available; releases on exit.
- [ ] `write() -> AbstractContextManager[StoreWriter]` acquires `fcntl.flock(LOCK_EX | LOCK_NB)`; atomically writes `.codegenie/rag/.lock.holder` with JSON `{pid, hostname, timestamp}` (canonical sorted-keys LF, `os.replace`); removes the holder file on context exit.
- [ ] **Gap-3 stale-lock-breaker:** a reader/writer that has been waiting > 60s on the lock reads `.lock.holder`, checks `os.kill(pid, 0)` (and verifies `hostname == socket.gethostname()`); if the holder PID is dead **and** same-host, emits `lock.broken_stale` audit event with `{stale_pid, stale_hostname, stale_timestamp_age_s}`, removes the lock file, and proceeds.
- [ ] **Gap-2 digest filter:** `StoreReader.query(vec, top_k, filters) -> list[RetrievedExample]` **always** adds `embedding_model_digest == self.model_digest` to the chromadb where-clause, regardless of caller-supplied `filters`. Caller cannot opt out; the parameter is overwritten with a warning audit `query.digest_filter_overridden` if it appears in `filters` with a different value.
- [ ] **Cross-repo default filter:** queries default to `provenance.repo_url == current_repo_url OR provenance.public == True`; widening requires `allow_cross_repo=True` **AND** the constructor was called from a context where env `CODEGENIE_ALLOW_PRIVATE_CROSS_REPO=1` is set (constructor reads `os.environ` once at init); both conditions must hold or widening is silently refused with a `cross_repo.refused` audit.
- [ ] `StoreWriter.add(example: SolvedExample, embedding: list[float]) -> None`:
  - Step 1 — write body JSON to `.codegenie/rag/bodies/<example.id>.json` (canonical sorted-keys LF) via `os.replace` (atomic).
  - Step 2 — chromadb `upsert` with `(id=example.id, embedding, metadata={"embedding_model_digest": ..., "task_class": ..., "ecosystem": ..., "language": ..., "cve_year": ..., "engine_used": ..., "node_major": ..., "merge_status": ..., "provenance_repo_url": ..., "provenance_public": ...})`.
  - Body-first ordering is invariant. If step 2 fails, leave the orphan body and re-raise.
- [ ] `count() -> int`, `opens_cleanly() -> bool`, `prune(predicate) -> int`, `health() -> StoreHealth` all implemented per `phase-arch-design.md §"Component design"` #4.
- [ ] **Corruption recovery:** `opens_cleanly() == False` (SQLite checksum failure) → orchestrator path quarantines `<root>` to `<root>.corrupt-<ts>`, rebuilds empty store, and the calling factory forces `--no-rag` for the run with `audit.warning: store.corruption_quarantined`. The store class exposes a `quarantine_and_rebuild() -> Path` helper returning the quarantine path.
- [ ] `health() -> StoreHealth` returns `{count, embedding_model_digest, mixed_embedding_models: bool, query_latency_p50_ms, newest_example_age_days, merge_status_distribution}`; `mixed_embedding_models` is `True` iff the chromadb metadata contains ≥ 2 distinct `embedding_model_digest` values.
- [ ] `chromadb` is imported **only** inside `src/codegenie/rag/store.py`; `tests/fence/test_fence_phase4.py` extended to assert this; telemetry disabled at module-import time (`os.environ.setdefault("ANONYMIZED_TELEMETRY","False")` and the `chromadb.config.Settings(anonymized_telemetry=False)` defensive pair).
- [ ] `tests/unit/rag/test_query_filters_by_embedding_digest.py` — store with one example under digest `A`; current provider has digest `B`; `query()` returns `[]` regardless of caller-supplied filters (Gap 2 fix).
- [ ] `tests/unit/rag/test_store_breaks_stale_lock_after_60s.py` — process holding exclusive lock SIGKILLed; reader 60s later breaks lock and proceeds; `lock.broken_stale` audit event recorded; assertion uses a `monkeypatch`-shrunk watchdog timeout (e.g., 1s) so the test runs fast while preserving the production 60s default.
- [ ] `tests/unit/rag/test_store_cross_repo_filter_default.py` — by default, retrieval filters to `repo_url == current OR public == True`; setting `allow_cross_repo=True` without the env var still refuses; both conditions required to widen.
- [ ] `tests/unit/rag/test_store_opens_cleanly.py` — fresh store opens; pre-corrupted SQLite quarantined and rebuilt; warning audit emitted.
- [ ] `tests/unit/rag/test_store_body_first_ordering.py` — chromadb-upsert mock that raises; body JSON file exists on disk afterward (orphan body recovered by `prune --orphans` per Edge case #15).
- [ ] `tests/unit/rag/test_store_telemetry_disabled.py` — env var `ANONYMIZED_TELEMETRY=False` set before chromadb import.
- [ ] `tests/unit/rag/test_store_extra_forbid_on_metadata.py` — chromadb metadata only contains the seven indexed fields plus `embedding_model_digest` + provenance pair; any unexpected field is refused at `add()`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/rag/store.py`, `pytest tests/unit/rag/test_store_*` all pass.

## Implementation outline

1. Write the failing tests first (TDD plan below). The stale-lock test needs a `multiprocessing` subprocess that acquires the exclusive lock, then SIGKILLs itself; the test then attempts a `read()` with a 1-second watchdog (via constructor or monkeypatch hook) and asserts the audit event.
2. Top of `store.py`:
   ```python
   import os
   os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
   import chromadb
   from chromadb.config import Settings
   ```
3. `class SolvedExampleStore`:
   - `__init__`: validate `root` exists / create; record `model_digest`, `current_repo_url`, `allow_cross_repo` (gated by env var).
   - `_client` is lazy; uses `PersistentClient(path=str(root / "solved-examples"), settings=Settings(anonymized_telemetry=False, allow_reset=False))`.
   - `_collection`: one collection `vuln_solved_examples_pending` for Phase 4; ADR-P4-002's two-table split (pending/promoted) is owned by S6-x; this story ships pending only and leaves the collection-name strategy in a const so promoted collection lands later additively.
4. Lock implementation (`_LockManager` helper):
   - `acquire(mode: Literal["shared","exclusive"], stale_watchdog_s: float = 60.0)`: open lock file; try `fcntl.flock(..., LOCK_SH if shared else LOCK_EX | LOCK_NB)`; loop with sleep + watchdog; on watchdog expiry, read `.lock.holder`, verify dead+same-host, audit, break.
   - `release()`.
   - Holder writes happen *after* acquire; reads happen on watchdog expiry.
5. `read()` / `write()` context managers wrap the lock + yield a `StoreReader` / `StoreWriter`.
6. `StoreReader.query`:
   - Build `where`: start from `{"embedding_model_digest": self.model_digest}`; merge caller filters (Gap-2 enforcement: any caller-supplied `embedding_model_digest` with a different value is overwritten + audited).
   - Apply cross-repo filter: `{"$or": [{"provenance_repo_url": current}, {"provenance_public": True}]}` unless widening conditions met.
   - Apply caller's metadata pre-filters (ecosystem, language, etc.).
   - Call `collection.query(query_embeddings=[vec], n_results=top_k, where=...)`.
   - Hydrate `RetrievedExample` by reading `.codegenie/rag/bodies/<id>.json` for each match.
7. `StoreWriter.add`:
   - Body-first: `body_path = root / "bodies" / f"{example.id}.json"`; `os.replace(tmp, body_path)`.
   - chromadb upsert with metadata; on failure, do not delete body — `prune --orphans` is the recovery path.
8. `opens_cleanly()`: open chromadb in a try/except; on any error, return `False`.
9. `quarantine_and_rebuild()`: rename `<root>` → `<root>.corrupt-<ts>`; `mkdir` fresh `<root>`; emit `store.corruption_quarantined`.
10. `health()`: query chromadb for distinct `embedding_model_digest` values; if > 1, `mixed_embedding_models = True`.
11. Run lint/format/mypy/pytest.

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/rag/test_query_filters_by_embedding_digest.py`

```python
from pathlib import Path

import pytest

from codegenie.rag.store import SolvedExampleStore


def _seed_example(store: SolvedExampleStore, digest: str, repo_url: str = "https://x") -> str:
    # Minimal helper: write a SolvedExample whose embedding_model_digest=A.
    ...


def test_query_returns_empty_when_provider_digest_differs(tmp_path: Path) -> None:
    """Gap 2: an operator who bumps the embedding model and forgets to reindex
    must NOT get back stale vectors as if they were valid. The store filters
    on every query — no caller can forget."""
    store_a = SolvedExampleStore(
        root=tmp_path, embed_dims=384, model_digest="DIGEST_A",
        current_repo_url="https://x",
    )
    with store_a.write() as w:
        _seed_example(w, digest="DIGEST_A")

    # Now construct the store as if the operator bumped the model.
    store_b = SolvedExampleStore(
        root=tmp_path, embed_dims=384, model_digest="DIGEST_B",
        current_repo_url="https://x",
    )
    with store_b.read() as r:
        results = r.query(vec=[0.1] * 384, top_k=5, filters={})
    assert results == []


def test_caller_supplied_digest_filter_is_overridden_and_audited(tmp_path: Path, audit_capture) -> None:
    """If a caller passes a different embedding_model_digest, the store
    overwrites it with the current provider's digest and audits — the
    Gap-2 invariant is not bypassable."""
    store = SolvedExampleStore(
        root=tmp_path, embed_dims=384, model_digest="DIGEST_B",
        current_repo_url="https://x",
    )
    with store.read() as r:
        r.query(vec=[0.1] * 384, top_k=5,
                filters={"embedding_model_digest": "DIGEST_A"})
    assert any(e.kind == "query.digest_filter_overridden" for e in audit_capture)
```

Path: `tests/unit/rag/test_store_breaks_stale_lock_after_60s.py`

```python
import os
import signal
import time
import multiprocessing as mp
from pathlib import Path

import pytest

from codegenie.rag.store import SolvedExampleStore


def _acquire_exclusive_and_die(root: str, ready: mp.Event) -> None:
    store = SolvedExampleStore(
        root=Path(root), embed_dims=384, model_digest="D",
        current_repo_url="https://x",
    )
    with store.write():
        ready.set()
        # Simulate SIGKILL — the lock file persists, the holder file persists,
        # and the PID is dead.
        os.kill(os.getpid(), signal.SIGKILL)


def test_reader_breaks_stale_lock_when_holder_pid_is_dead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, audit_capture
) -> None:
    """Gap 3: a SIGKILL'd writer holding the exclusive lock would otherwise
    block every other worker indefinitely. The 60s watchdog (shrunk to 1s
    for the test) detects the dead PID and breaks the lock."""
    monkeypatch.setenv("CODEGENIE_LOCK_STALE_WATCHDOG_S", "1.0")

    ready = mp.Event()
    p = mp.Process(target=_acquire_exclusive_and_die, args=(str(tmp_path), ready))
    p.start()
    ready.wait(timeout=5)
    # By the time ready is set, the child has SIGKILLed itself.
    p.join(timeout=5)
    assert p.exitcode != 0  # SIGKILL.

    store = SolvedExampleStore(
        root=tmp_path, embed_dims=384, model_digest="D",
        current_repo_url="https://x",
    )
    # Reader should break the lock within ~1s + watchdog overhead.
    t0 = time.perf_counter()
    with store.read():
        pass
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"reader hung; elapsed={elapsed:.1f}s"
    assert any(e.kind == "lock.broken_stale" for e in audit_capture)
```

Path: `tests/unit/rag/test_store_cross_repo_filter_default.py`

```python
import pytest
from pathlib import Path

from codegenie.rag.store import SolvedExampleStore


def test_default_filter_excludes_other_private_repos(tmp_path: Path) -> None:
    """NG7 defense-in-depth: a private example from repo X must NOT surface
    when retrieving for repo Y by default. The filter is at the store layer,
    not at the engine layer, so no caller can forget."""
    store = SolvedExampleStore(
        root=tmp_path, embed_dims=384, model_digest="D",
        current_repo_url="https://y",
    )
    with store.write() as w:
        _seed_example(w, digest="D", repo_url="https://x", public=False)
    with store.read() as r:
        results = r.query(vec=[0.1] * 384, top_k=5, filters={})
    assert results == []


def test_allow_cross_repo_requires_both_flag_and_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Widening requires BOTH --allow-cross-repo-rag AND env var. Either
    alone refuses silently with an audit."""
    monkeypatch.delenv("CODEGENIE_ALLOW_PRIVATE_CROSS_REPO", raising=False)
    store = SolvedExampleStore(
        root=tmp_path, embed_dims=384, model_digest="D",
        current_repo_url="https://y", allow_cross_repo=True,  # flag only
    )
    with store.write() as w:
        _seed_example(w, digest="D", repo_url="https://x", public=False)
    with store.read() as r:
        results = r.query(vec=[0.1] * 384, top_k=5, filters={})
    assert results == []  # flag without env is refused
```

Commit red. All fail (`ImportError` initially).

### Green

- `store.py`: ~250 lines (the largest module of Step 4). The lock-manager and the query-filter merger are the trickiest pieces; keep each helper ≤ 30 LOC.

### Refactor

- Extract `_LockManager`, `_metadata_for_chromadb`, `_apply_default_filters` as private helpers.
- Docstrings on every public method cite the relevant ADR.
- The `quarantine_and_rebuild` flow logs the full `<root>.corrupt-<ts>` path so the operator can recover by hand.
- Add property tests covering `count()` and `prune(predicate)` if time allows.
- Verify the fence-CI test in S1-07 covers `chromadb` containment to this file.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/store.py` | New — `SolvedExampleStore` + reader/writer + lock manager |
| `src/codegenie/rag/_lock.py` (optional) | New if `_LockManager` extracted |
| `tests/unit/rag/test_query_filters_by_embedding_digest.py` | New — Gap 2 |
| `tests/unit/rag/test_store_breaks_stale_lock_after_60s.py` | New — Gap 3 |
| `tests/unit/rag/test_store_cross_repo_filter_default.py` | New — NG7 |
| `tests/unit/rag/test_store_opens_cleanly.py` | New — corruption quarantine |
| `tests/unit/rag/test_store_body_first_ordering.py` | New — orphan-body invariant |
| `tests/unit/rag/test_store_telemetry_disabled.py` | New — env-var-before-import |
| `tests/unit/rag/test_store_extra_forbid_on_metadata.py` | New — metadata allowlist |
| `tests/fence/test_fence_phase4.py` | Extend — `import chromadb` allowed only in `store.py` |
| `tests/conftest.py` | Add `audit_capture` fixture if not already shipped |

## Out of scope

- **The two-table split into `pending` / `promoted` collections** — Phase 4 ships only the `pending` collection by name; ADR-P4-002 promotion path lands in Phase 11 webhook + a Phase-4 follow-up. The story leaves a constant for the collection name so the split is additive.
- **`writeback_solved_example` itself** — S6-01 owns the three-write orchestration; this story exposes `add()` only.
- **`QueryKeyCache`** — S4-05 owns the tier-1 exact-replay cache; the store's filtering is independent.
- **CLI subcommands** — S4-07 wires `solved-examples reindex` and `prune --orphans`; this story only ships the underlying `prune(predicate)` API.
- **Eviction / GC** — corpus is monotonic until ~5k examples; ADR-P4-005 documents the qdrant swap-out trigger.
- **chromadb supply-chain hash-pin in `requirements.lock`** — ships via the CI gate work in S7-06.

## Notes for the implementer

- **Telemetry-off must happen at module-import time, not at `__init__`.** `import chromadb` triggers a telemetry handshake; setting `ANONYMIZED_TELEMETRY=False` after the import is too late. Top-of-file env-var mutation is the only reliable shape. Verify with the `test_store_telemetry_disabled.py` companion test.
- **Body-first ordering is the only reason `prune --orphans` works.** If you reverse the write order (chromadb first, body second), a crash between the two writes leaves an orphan chromadb row pointing at a missing body — and `RetrievedExample` construction will fail loud on every read. Body-first leaves recoverable state.
- **The watchdog timeout default is 60s but must be parametrized for tests.** Read `CODEGENIE_LOCK_STALE_WATCHDOG_S` env override at `_LockManager` init time so the test can shrink to 1s. Do NOT make the watchdog configurable via CLI flag — that's an operator footgun.
- **`os.kill(pid, 0)` is not multi-host-safe.** Phase 4 is local-only, single-host; the holder file records `hostname` so cross-host cases (Phase 9+ Temporal Activities) explicitly refuse to break the lock. Mismatched hostname → no breakage; audit and re-loop.
- **chromadb `where` filter syntax is `{"field": "value"}` for equality, `{"$or": [...]}` for OR.** Validate against the chromadb 0.4.x docs version pinned in `requirements.lock`; the wire format has shifted between versions.
- **The Gap-2 override-and-audit posture is intentional.** A caller passing a deliberately different digest is a bug; the store *could* raise, but auditing + overriding is friendlier during development and keeps RAG-side production paths from crashing on a benign misconfiguration. The audit makes the bug visible.
- **`mixed_embedding_models: bool` is the honest-confidence signal.** It's what the health probe in S4-06 reads to emit `confidence=low`. Compute it by querying chromadb for distinct `embedding_model_digest` values — cheap on small corpora; if the corpus grows past 1k and this query becomes hot, cache it.
- **Corruption quarantine is loud, not silent.** The `audit.warning: store.corruption_quarantined` event includes the quarantine path; the operator may want to recover data from `<root>.corrupt-<ts>`. The forced `--no-rag` for the run lands in S5-x (engine factory); this story exposes `opens_cleanly()` and `quarantine_and_rebuild()` only.
- **Fence-CI is the structural defense.** If you find yourself needing to import chromadb elsewhere, stop. The right answer is to widen `SolvedExampleStore`'s public surface, not to leak the dependency.
