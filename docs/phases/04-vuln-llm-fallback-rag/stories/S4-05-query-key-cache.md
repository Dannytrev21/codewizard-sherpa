# Story S4-05 — `QueryKeyCache` — mmap + canonical-JSON key + invalidation on catalog change

**Step:** Step 4 — Ship the RAG side — `EmbeddingProvider` + UDS sidecar, `SolvedExampleStore`, `QueryKeyCache`, `SolvedExampleHealthProbe`
**Status:** Ready
**Effort:** M
**Depends on:** S4-04 (`SolvedExampleStore` is the sibling RAG-side primitive; query-key cache pairs with it as tier-1 to tier-2)
**ADRs honored:** ADR-P4-015 (`task_class` in the cache key for Phase 7 collision-freedom), ADR-P4-006 (`embedding_model_digest` in the key so a model swap auto-invalidates every entry — Gap-2 sibling at the cache layer)

## Context

`QueryKeyCache` is the tier-1 exact-replay layer of the three-tier RAG pipeline. The compounding-savings story (ADR-0011) depends on it: a portfolio peer running the same advisory + same lockfile fingerprint hits the cache in microseconds with zero LLM cost. The cache is filesystem-backed at `.codegenie/cache/planner/query_key/<sha256>.json`, mmap-read for cost, written via `os.replace` for atomicity, and *fenced* by the recipe-catalog blake3 — when the recipe catalog changes (a new recipe lands), every prior key is structurally invalidated because the recipe-catalog blake3 changes. `task_class` is in the key so Phase 7 (Chainguard) doesn't collide with Phase 4 (vuln); `embedding_model_digest` is in the key so a model swap auto-invalidates every entry without requiring a separate purge. Corrupted entries are treated as misses and overwritten on next `put`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design"` #5 `QueryKeyCache` — full interface, mmap reads, `os.replace` writes, recipe-catalog-blake3 fencing, `task_class` collision-freedom.
  - `../phase-arch-design.md §"Edge cases"` rows #14 (worker crash between trust-pass and writeback — cache miss costs one extra LLM call), #22 (catalog blake3 changes → every entry invalidates).
  - `../phase-arch-design.md §"Testing strategy" §"Property tests"` — `test_query_key_determinism_property.py` (canonical JSON invariance).
  - `../phase-arch-design.md §"Performance regression tests"` — `test_query_key_replay_under_5ms.py` (G8 p95 ≤ 5ms).
- **Phase ADRs:**
  - `../ADRs/0015-solved-example-schema-task-class-generic.md` — ADR-P4-015 — `task_class` is in the key tuple (Phase 7 collision-freedom).
  - `../ADRs/0006-bge-small-en-embedding-model-sha-pinned.md` — ADR-P4-006 — `embedding_model_digest` in the key tuple auto-invalidates on model swap.
- **Production ADRs:**
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback.md` — the compounding-savings story this cache enables.
- **Source design:**
  - `../final-design.md §"Components"` #1 Tier 0 — query-key exact-replay; sub-millisecond intent.
  - `../final-design.md §"Data flow"` — second portfolio peer hits tier 0 / tier 1 first.
- **Existing code:**
  - `src/codegenie/rag/models.py` (S1-03) — `Plan` (the cached value).
  - `src/codegenie/rag/store.py` (S4-04) — sibling; shares the `.codegenie/cache/`-vs-`.codegenie/rag/` namespace.

## Goal

Ship `src/codegenie/rag/query_key_cache.py` exposing `QueryKeyCache(root)` with `get(qk)` mmap-reading `.codegenie/cache/planner/query_key/<sha256>.json` (corrupted entry → miss), `put(qk, plan, example_id)` writing via `os.replace`, and the module-level `compute_query_key(*, cve_id, fixed_range, lockfile_blake3, recipe_catalog_blake3, prompt_template_version, embedding_model_digest, model_id, task_class) -> str` that produces a sha256 over canonical-JSON of the named tuple (sorted keys, LF, UTF-8).

## Acceptance criteria

- [ ] `QueryKeyCache(root: Path)` constructable; creates `<root>/.codegenie/cache/planner/query_key/` lazily on first `put`.
- [ ] `get(query_key: str) -> CachedPlan | None`:
  - mmap-reads `<dir>/<query_key>.json`.
  - Parses canonical JSON.
  - Returns `CachedPlan(plan, example_id, written_at)` on hit.
  - **Corrupted entry** (JSON parse fail, schema mismatch, hash mismatch) → returns `None` (miss); does **not** delete (next `put` will overwrite).
  - Missing file → returns `None` cleanly.
- [ ] `put(query_key: str, plan: Plan, example_id: str) -> None`:
  - Serializes `CachedPlan(plan=plan, example_id=example_id, written_at=utcnow_iso())` via canonical JSON (sorted keys, LF, no trailing newline beyond LF, UTF-8).
  - Writes to a tmpfile under the same directory; `os.replace(tmp, final)` — atomic.
  - Overwrites on duplicate key (last-writer-wins by design — body content is what's keyed).
- [ ] `compute_query_key(*, cve_id, fixed_range, lockfile_blake3, recipe_catalog_blake3, prompt_template_version, embedding_model_digest, model_id, task_class) -> str` is a module-level function (keyword-only):
  - All eight inputs are required.
  - Output = `hashlib.sha256(canonical_json_bytes).hexdigest()`.
  - `canonical_json_bytes` = `json.dumps({...}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"`.
  - **Invariant:** byte-identical output across two calls with the same kwargs on the same Python version.
- [ ] **`task_class` differentiator (ADR-P4-015):** same inputs except `task_class="vuln"` vs `task_class="chainguard"` → different keys.
- [ ] **`recipe_catalog_blake3` fence (Edge case #22):** changing the catalog blake3 changes every key — confirmed in `test_catalog_blake3_invalidates_query_cache.py`.
- [ ] **`embedding_model_digest` in the key (Gap-2 sibling):** a model digest change automatically misses every prior key — no separate cache purge needed.
- [ ] `tests/unit/rag/test_query_key_canonicalization.py` — Hypothesis: `compute_query_key` invariant under JSON dict-ordering permutations of inputs (build kwargs in different orders; assert same key).
- [ ] `tests/unit/rag/test_query_key_task_class_differs.py` — Hypothesis: `task_class` change → different key for all other inputs equal.
- [ ] `tests/unit/rag/test_catalog_blake3_invalidates_query_cache.py` — seed a cache entry under `recipe_catalog_blake3=A`; change to `B`; old key misses (verified via `compute_query_key` change, not via cache deletion).
- [ ] `tests/unit/rag/test_query_key_cache_corrupted_entry_is_miss.py` — write garbage to a `<qk>.json` file; `get(qk)` returns `None` (not a raise); subsequent `put` overwrites the garbage.
- [ ] `tests/unit/rag/test_query_key_replay_under_5ms.py` (G8 perf canary) — 1000 iterations of `get` on a hit; p95 ≤ 5 ms (mmap-cheap).
- [ ] `tests/unit/rag/test_query_key_determinism_property.py` — Hypothesis: same kwargs → same key (sanity property, separate from canonicalization).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/rag/query_key_cache.py`, `pytest tests/unit/rag/test_query_key_*` all pass.

## Implementation outline

1. Write the failing tests (TDD plan below).
2. Create `src/codegenie/rag/query_key_cache.py`:
   - Module-level `compute_query_key(**kwargs) -> str` with the eight keyword-only args.
   - `class CachedPlan(BaseModel)`: `plan: Plan`, `example_id: str`, `written_at: datetime`; `model_config = ConfigDict(extra="forbid")`.
   - `class QueryKeyCache`:
     - `__init__(self, root: Path)`: stores the path; lazy mkdir.
     - `_path(self, qk: str) -> Path`: returns `<root>/.codegenie/cache/planner/query_key/<qk>.json`.
     - `get(self, qk: str) -> CachedPlan | None`: open file, mmap, parse, validate; on any error return `None`.
     - `put(self, qk: str, plan: Plan, example_id: str) -> None`: build `CachedPlan`, serialize canonical, tmpfile + `os.replace`.
3. Canonical JSON helper: `_canonical_json_bytes(obj) -> bytes` — `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"`. Reused for both `compute_query_key` and `put`.
4. mmap-read pattern:
   ```python
   with open(path, "rb") as f:
       with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
           raw = bytes(mm)
   ```
   Catch `(FileNotFoundError, ValueError, json.JSONDecodeError, pydantic.ValidationError)` → return `None`.
5. Run lint / format / mypy / pytest.

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/rag/test_query_key_canonicalization.py`

```python
from hypothesis import given, strategies as st
from codegenie.rag.query_key_cache import compute_query_key


# Eight kwargs, in any reorder — must yield same key.
_KWARGS = dict(
    cve_id="CVE-2024-0001",
    fixed_range="^6.0.0",
    lockfile_blake3="A" * 64,
    recipe_catalog_blake3="B" * 64,
    prompt_template_version="few_shot_rag.v1",
    embedding_model_digest="C" * 40,
    model_id="claude-sonnet-4-7-20251015",
    task_class="vuln",
)


def test_compute_query_key_deterministic_across_kwarg_ordering() -> None:
    """Canonical-JSON sorting must make key generation invariant under
    kwarg ordering — without this, two callers passing the same logical
    inputs in different orders would build different keys and miss the cache."""
    k1 = compute_query_key(**_KWARGS)
    # Python preserves insertion order; reorder by re-building the dict.
    reordered = {k: _KWARGS[k] for k in sorted(_KWARGS.keys())}
    k2 = compute_query_key(**reordered)
    rereordered = {k: _KWARGS[k] for k in reversed(sorted(_KWARGS.keys()))}
    k3 = compute_query_key(**rereordered)
    assert k1 == k2 == k3
    assert len(k1) == 64  # sha256 hex.
```

Path: `tests/unit/rag/test_query_key_task_class_differs.py`

```python
from codegenie.rag.query_key_cache import compute_query_key


def test_task_class_change_produces_different_key() -> None:
    """ADR-P4-015: Phase 7 (chainguard) MUST NOT collide with Phase 4 (vuln)
    on the cache layer. task_class is in the key tuple."""
    base = dict(
        cve_id="CVE-2024-0001", fixed_range="^6.0.0",
        lockfile_blake3="A" * 64, recipe_catalog_blake3="B" * 64,
        prompt_template_version="few_shot_rag.v1",
        embedding_model_digest="C" * 40, model_id="claude-sonnet-4-7",
    )
    vuln = compute_query_key(**base, task_class="vuln")
    cg = compute_query_key(**base, task_class="chainguard")
    assert vuln != cg
```

Path: `tests/unit/rag/test_catalog_blake3_invalidates_query_cache.py`

```python
from codegenie.rag.query_key_cache import compute_query_key


def test_recipe_catalog_blake3_change_invalidates_every_prior_key() -> None:
    """Edge case #22: a new recipe landing in the catalog must invalidate
    every cached entry — otherwise old keys hit, returning plans built
    against a stale catalog."""
    base = dict(
        cve_id="CVE-2024-0001", fixed_range="^6.0.0",
        lockfile_blake3="A" * 64, prompt_template_version="few_shot_rag.v1",
        embedding_model_digest="C" * 40, model_id="claude-sonnet-4-7",
        task_class="vuln",
    )
    before = compute_query_key(**base, recipe_catalog_blake3="OLD" + "0" * 61)
    after = compute_query_key(**base, recipe_catalog_blake3="NEW" + "0" * 61)
    assert before != after
```

Path: `tests/unit/rag/test_query_key_cache_corrupted_entry_is_miss.py`

```python
from pathlib import Path

from codegenie.rag.query_key_cache import QueryKeyCache


def test_corrupted_json_returns_miss_not_raise(tmp_path: Path) -> None:
    """A corrupted entry (partial write, disk error) is structurally
    indistinguishable from a miss to the caller — we must NOT raise.
    The next put() overwrites the garbage."""
    cache = QueryKeyCache(root=tmp_path)
    qk = "deadbeef" * 8
    bad_path = tmp_path / ".codegenie" / "cache" / "planner" / "query_key" / f"{qk}.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_bytes(b"{not json")
    assert cache.get(qk) is None
```

Path: `tests/unit/rag/test_query_key_replay_under_5ms.py`

```python
import time
from pathlib import Path

import pytest

from codegenie.rag.query_key_cache import QueryKeyCache, compute_query_key
# Plan import — use a minimal fixture.


@pytest.fixture
def populated_cache(tmp_path: Path):
    cache = QueryKeyCache(root=tmp_path)
    qk = "feedface" * 8
    plan = ...  # a fixture Plan; build via tests/fixtures factory.
    cache.put(qk, plan, example_id="ex-1")
    return cache, qk


def test_get_p95_under_5ms(populated_cache) -> None:
    """G8 perf canary: tier-1 replay must be sub-millisecond p95 because
    the compounding-savings story hangs on it. mmap reads are the cheapest
    primitive we have; if this regresses, look for sync I/O leaking in."""
    cache, qk = populated_cache
    # Warm.
    for _ in range(20):
        cache.get(qk)
    times_ms: list[float] = []
    for _ in range(1000):
        t0 = time.perf_counter()
        cache.get(qk)
        times_ms.append((time.perf_counter() - t0) * 1000)
    p95 = sorted(times_ms)[int(len(times_ms) * 0.95)]
    assert p95 <= 5.0, f"p95={p95:.2f}ms exceeds 5ms budget"
```

Commit red. All fail (`ImportError`).

### Green

- Smallest impl: ~80 lines.
- `Plan` fixture factory should already exist from S1-03 stories.

### Refactor

- Extract `_canonical_json_bytes` as a module-private helper reused by both `compute_query_key` and `put`.
- Add `last_modified(qk)` if the operator CLI in S6-04 (`solved-examples show`) needs it; otherwise defer.
- Add a docstring citing ADR-P4-015 + Edge case #22 + the G8 perf canary requirement.
- Verify property tests stay fast (`max_examples=200`).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/query_key_cache.py` | New — cache + `compute_query_key` |
| `tests/unit/rag/test_query_key_canonicalization.py` | New — Hypothesis canonicalization |
| `tests/unit/rag/test_query_key_task_class_differs.py` | New — Phase 7 collision-freedom |
| `tests/unit/rag/test_catalog_blake3_invalidates_query_cache.py` | New — Edge case #22 |
| `tests/unit/rag/test_query_key_cache_corrupted_entry_is_miss.py` | New — graceful miss |
| `tests/unit/rag/test_query_key_replay_under_5ms.py` | New — G8 perf canary |
| `tests/unit/rag/test_query_key_determinism_property.py` | New — Hypothesis determinism (companion to canonicalization) |

## Out of scope

- **Synchronous `put` inside `writeback_solved_example`** — S6-01 owns the writeback orchestration; this story exposes `put()` only.
- **TTL / eviction** — TTL is indefinite, recipe-catalog-blake3-fenced (a catalog change auto-invalidates). No size-based eviction in Phase 4; ADR-P4-005 documents the swap-out trigger if the cache grows beyond fast-mmap territory.
- **Cross-host cache** — Phase 4 is local-only; Phase 9+ Temporal subsumes this question.
- **Cache warmup / preload** — not needed in Phase 4; the compounding-savings story is purely emergent.
- **Atomic group-replace** — single-key `os.replace` is enough; no multi-key transaction semantics.

## Notes for the implementer

- **Canonical JSON is the only acceptable serialization.** `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")` + LF tail is the exact byte recipe. If you find yourself reaching for `pickle`, `msgpack`, or `pyjson5`, stop — every byte difference breaks deterministic key generation.
- **`os.replace` is atomic on POSIX *and* Windows.** Use it, not `os.rename`. The replace target is the final `<qk>.json` path; the tmpfile lives in the same directory (must, for atomicity).
- **The eight key inputs are load-bearing.** Adding a ninth would auto-invalidate the entire cache (which is fine); removing one would break Phase 7 (`task_class`) or break Gap-2 (`embedding_model_digest`). Surface any expansion as an ADR amendment.
- **`prompt_template_version` is in the key.** A prompt edit auto-invalidates the cache; this is by design. The S2-02 prompt loader exposes `template.version` per `phase-arch-design.md §"Component design"` #8.
- **mmap reads are the perf escape hatch.** Plain `open(...).read()` is fine for correctness but burns syscalls; the G8 5ms budget is tight enough that mmap matters. Use `mmap.ACCESS_READ` (not `ACCESS_COPY`) — the cache file is shared-readable.
- **Corrupted entries are a miss, not a raise.** This is critical for the worker-crash-mid-`put` edge case: the half-written file looks like garbage; the next caller misses and re-pays one LLM call (Edge case #14 — known cost, not gated). Raising would propagate transient I/O state up the engine stack.
- **No locking on `get`.** Cache writes via `os.replace` are atomic; concurrent readers see either the old file or the new file, never a half-written state. This is the reason `os.replace` (not `shutil.move`) is mandatory.
- **`example_id` is the link back to the body.** The cached `Plan` is the plan that was applied; the `example_id` is the chromadb row + body JSON. S6-01's writeback uses this for forensic linkage (the audit chain head is in the body, not the cache).
- **Do not introduce a `CachedPlan` schema version field.** The cache is regenerable; if the schema needs to change, bump `prompt_template_version` (or accept the implicit miss on schema mismatch — corrupted entries are misses). Avoid a separate cache-schema migration path.
