# Story S7-01 — Per-file findings sub-cache module + LRU 5 GB cap

**Step:** Step 7 — Ship Layer D, Layer E (real + stubs), Layer G; plant per-file findings sub-caches
**Status:** Ready
**Effort:** M
**Depends on:** S2-07, S1-08
**ADRs honored:** ADR-0004 (digest pin manifest), `final-design.md` D14 (per-file findings sub-cache)

## Context

The per-file findings sub-cache is the disk substrate every Phase 2 expensive scanner (`semgrep`, `gitleaks`, `tree-sitter`) reads and writes. It's an independent layer from Phase 0's per-probe `ProbeOutput` cache: probes still hash their full input set into `cache_key` at the probe level, but they additionally consult a per-file blob keyed on `(file_content_blake3, rule_pack_version | grammar_version, tool_digest)`. The two layers don't compete — the per-probe cache decides "do I re-run the probe at all?" and the per-file cache decides "for each file that does need scanning, do I have a memoized finding?" An LRU-by-access-time eviction with a 5 GB cap keeps disk usage bounded; per-blob BLAKE3 integrity catches concurrent-poisoning attempts. Phase 2 ships the module; the three consumers (S7-02 semgrep, S7-03 gitleaks, S4-02 tree-sitter sub-cache shape) consume it.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #17` — full on-disk layout under `.codegenie/cache/<tool>/by-file/`; LRU + BLAKE3 integrity contract; `cache gc` extension; SCIP namespace separation.
  - `../phase-arch-design.md §"Data model"` — referenced shapes for `SemgrepFinding` / `GitleaksFinding` (consumers of this cache).
  - `../phase-arch-design.md §"Edge cases"` — concurrent-write + corruption handling.
  - `../phase-arch-design.md §"Goals" #6` — "Per-file findings cache invariant" — cross-file taint mode opt-in via `--paranoid` (bypasses this cache).
- **Phase ADRs:**
  - `../ADRs/0004-tools-digests-yaml-pin-manifest.md` — ADR-0004 (the `tool_digest` component of the cache key derives from this manifest).
- **Source design:**
  - `../final-design.md §"Conflict-resolution table" D14` — winner is `[P]` "Yes for semgrep, gitleaks, tree-sitter; cap by access-time LRU".
  - `../final-design.md §"Components" #8 Cache layer extension`.
- **Existing code:**
  - `src/codegenie/cache/` (Phase 0) — per-probe `ProbeOutput` blob cache; this module is a sibling layer, **not** an extension.
  - `src/codegenie/parsers/safe_yaml.py` (Phase 1) — `tools/digests.yaml` loader used for the `tool_digest` keyspace component.
  - `src/codegenie/coordinator/input_snapshot.py` (S1-08) — content-addressed BLAKE3 for files; the per-file cache reuses the same content_hash output shape (not the snapshot object itself).

## Goal

Ship `src/codegenie/coordinator/per_file_cache.py` exporting `PerFileCache` — read/write msgpack blobs at `(file_content_blake3, rule_pack_or_grammar_version, tool_digest)`; LRU-by-access-time eviction at 5 GB; per-blob BLAKE3 integrity check on read (mismatched blob deleted, caller re-runs); concurrent-poisoning resilient via atomic-write-then-rename + post-rename BLAKE3 verify.

## Acceptance criteria

- [ ] `src/codegenie/coordinator/per_file_cache.py` exports `PerFileCache(root: Path, *, tool: str, max_bytes: int = 5 * 1024**3)` with methods `get(content_hash: str, version_key: str, tool_digest: str) -> bytes | None` and `put(content_hash: str, version_key: str, tool_digest: str, blob: bytes) -> None`.
- [ ] On-disk layout: `<root>/cache/<tool>/by-file/<content_hash>.<version_key>.<tool_digest>.msgpack` — flat directory, no nesting; `tool` ∈ `{"semgrep", "gitleaks", "tree-sitter"}` (enforced; other names raise `ValueError`).
- [ ] `put` writes msgpack-serialized blob atomically: `tempfile.NamedTemporaryFile` in same directory → `os.replace` rename. Records BLAKE3-of-blob in a sidecar `.b3` file written atomically alongside.
- [ ] `get` reads the blob, re-hashes, compares to sidecar; **mismatch → delete both blob and sidecar; return `None`** (caller re-runs). Touch atime to mark recency.
- [ ] LRU-by-access-time eviction: on `put`, if total `<tool>/by-file/` directory size exceeds `max_bytes`, delete oldest-by-`st_atime_ns` blobs (and their sidecars) until under cap. Eviction is best-effort — does not raise on `OSError`.
- [ ] `msgpack` pinned in `pyproject.toml` `dependencies` with `~=` constraint; wheel hash recorded in `src/codegenie/catalogs/tools/digests.yaml` (ADR-0004 envelope) under a new `pip_wheels:` block (or equivalent — match the Step 1 pattern).
- [ ] `tests/unit/coordinator/test_per_file_cache.py` covers: put/get round-trip; cache miss returns `None`; integrity check (manually corrupt blob → next `get` returns `None` + blob deleted); LRU eviction (write `N` blobs sized to exceed 5 GB / 1 MB scaled cap → oldest evicted); `tool=` argument outside enum raises `ValueError`; atomic write (`os.replace` is exercised — no half-written blobs visible mid-write).
- [ ] `tests/adv/test_concurrent_cache_poisoning.py` — two threads/processes call `put` with the **same key + different blob content** — assert only one survives, and a subsequent `get` either returns one of the two valid blobs or `None` (never a corrupted hybrid). Mutates `BLAKE3` check is the witness.
- [ ] LRU eviction test runs with `max_bytes=10_485_760` (10 MB, scaled-down) — full 5 GB test is not feasible in CI; the test verifies the eviction algorithm, not the production cap.
- [ ] `cache gc` (Phase 0 CLI subcommand) extended to manage the per-file sub-caches: new flag `--include-sub-caches` (default false in Phase 2; flipped on in Phase 14). When set, walks `cache/<tool>/by-file/` directories and applies the same LRU pass. **Module-only addition; CLI plumbing is one new flag.**
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create `src/codegenie/coordinator/per_file_cache.py`:
   - `_ALLOWED_TOOLS: Final[frozenset[str]] = frozenset({"semgrep", "gitleaks", "tree-sitter"})`.
   - `PerFileCache.__init__` validates `tool` against the allowlist; resolves `<root>/cache/<tool>/by-file/`; `mkdir(parents=True, exist_ok=True)`.
   - `_blob_path(content_hash, version_key, tool_digest) -> Path` — string-formats the deterministic path.
   - `put(...)` — serialize via `msgpack.packb` (use `use_bin_type=True`); write to `NamedTemporaryFile(dir=self._dir, delete=False)`; write sidecar `.b3` next to it; `os.replace` both into final names; trigger LRU sweep.
   - `get(...)` — read blob bytes; read sidecar; compute `blake3(blob).hexdigest()`; compare; on mismatch, `os.unlink` both files (best-effort) and return `None`; on match, `os.utime(path, None)` to refresh atime; return `msgpack.unpackb(blob, raw=False)`.
   - `_evict_if_over_cap()` — `os.scandir` the directory; sum `st_size`s; if over `max_bytes`, sort by `st_atime_ns` ascending; unlink until under cap. Wrap each unlink in `try/except OSError: pass`.
2. Add `msgpack` to `pyproject.toml` `[project] dependencies` with a `~=` minor-version constraint. Add the wheel SHA-256 entry to `src/codegenie/catalogs/tools/digests.yaml` under the existing structure (mirror what Step 1 establishes).
3. Edit `src/codegenie/cli/commands/cache.py` (Phase 0 origin; light edit) to add `--include-sub-caches` flag to `cache gc`. Surgical change — Phase 0's existing gc loop stays untouched.

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/coordinator/test_per_file_cache.py`

```python
import os, time
from pathlib import Path
import pytest
from codegenie.coordinator.per_file_cache import PerFileCache

def test_round_trip(tmp_path):
    c = PerFileCache(tmp_path, tool="semgrep")
    c.put("h1", "v1", "d1", {"findings": []})
    assert c.get("h1", "v1", "d1") == {"findings": []}

def test_miss_returns_none(tmp_path):
    c = PerFileCache(tmp_path, tool="semgrep")
    assert c.get("h1", "v1", "d1") is None

def test_integrity_mismatch_deletes_blob(tmp_path):
    c = PerFileCache(tmp_path, tool="semgrep")
    c.put("h1", "v1", "d1", {"x": 1})
    blob_path = next(tmp_path.rglob("h1.v1.d1.msgpack"))
    blob_path.write_bytes(b"\x00corrupt")
    assert c.get("h1", "v1", "d1") is None
    assert not blob_path.exists()

def test_lru_evicts_oldest(tmp_path):
    c = PerFileCache(tmp_path, tool="semgrep", max_bytes=4096)
    # Write large-enough blobs to overflow; touch atime ordering by sleeping briefly.
    for i in range(8):
        c.put(f"h{i}", "v", "d", {"pad": "x" * 800})
        time.sleep(0.01)
    # Oldest entry h0 should be gone; newest h7 should remain.
    assert c.get("h0", "v", "d") is None
    assert c.get("h7", "v", "d") is not None

def test_unknown_tool_rejected(tmp_path):
    with pytest.raises(ValueError):
        PerFileCache(tmp_path, tool="bogus")
```

Adversarial test path: `tests/adv/test_concurrent_cache_poisoning.py`.

```python
import threading
from pathlib import Path
from codegenie.coordinator.per_file_cache import PerFileCache

def test_concurrent_writes_resolve_safely(tmp_path):
    c = PerFileCache(tmp_path, tool="semgrep")
    def writer(payload):
        c.put("h1", "v1", "d1", {"data": payload})
    t1 = threading.Thread(target=writer, args=("A",))
    t2 = threading.Thread(target=writer, args=("B",))
    t1.start(); t2.start(); t1.join(); t2.join()
    # Either A or B survives; never a corrupted hybrid; never raises.
    out = c.get("h1", "v1", "d1")
    assert out is None or out["data"] in {"A", "B"}
```

### Green

Implement `PerFileCache` per the outline. Wire `msgpack` into `pyproject.toml`. Add the `--include-sub-caches` flag on `cache gc` as a one-line Click option that branches to a new helper.

### Refactor

- Module docstring naming `phase-arch-design.md §"Component design" #17`, `final-design.md` ledger row D14.
- The `_ALLOWED_TOOLS` frozenset is `Final` at module scope — Phase 14 extends only via additive ADR.
- LRU sweep helper takes the directory + cap as explicit args; testable in isolation.
- All `os.unlink` calls wrapped in `try/except OSError`; logged via `structlog` at `debug` level (event name `cache.per_file.evict`).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/coordinator/per_file_cache.py` | New — `PerFileCache` class. |
| `pyproject.toml` | Add `msgpack` to `[project] dependencies`. |
| `src/codegenie/catalogs/tools/digests.yaml` | Pin `msgpack` wheel SHA-256 (mirror Step 1 pattern). |
| `src/codegenie/cli/commands/cache.py` | Add `--include-sub-caches` flag (surgical). |
| `tests/unit/coordinator/test_per_file_cache.py` | New — round-trip, miss, integrity, LRU, allowlist tests. |
| `tests/adv/test_concurrent_cache_poisoning.py` | New — concurrent-write resilience. |

## Out of scope

- **Cross-gather state in cache keys** — handled by ADR-0006 ("DaemonPool refused"). This cache is per-gather-consultable; never carries cross-gather state in the **key**, only as evicted entries on disk.
- **SCIP binary lifecycle** — `.codegenie/index/scip-index.scip` is per-repo (S4-01); this module's allowlist explicitly excludes `scip`.
- **Distributed cache** (Phase 14) — sub-cache stays local; ADR for cross-host invalidation deferred.
- **Cross-file taint mode** — `--paranoid` (S7-02) bypasses this cache; per-file cache is exclusively per-file rule families.

## Notes for the implementer

- **`msgpack.unpackb(raw=False)` is mandatory** — without it, all strings come back as bytes, breaking the Pydantic models that consume the unpacked dict downstream. Default `raw=True` is the Python 2 compatibility flag; pin it `False`.
- **`os.utime(path, None)` is the atime refresh** — relying on filesystem atime updates is *not* portable (Linux frequently mounts with `noatime` or `relatime`). The explicit `utime` call is the contract for LRU correctness; without it the sweep order is unstable on `noatime` filesystems.
- **`tempfile.NamedTemporaryFile(dir=self._dir, delete=False)`** must be in the *same* directory as the final blob — `os.replace` across filesystems is not atomic. Don't use `tempfile.gettempdir()`.
- **Sidecar `.b3` file is the witness.** The blob alone isn't self-verifying; the sidecar holds the expected BLAKE3. Both must be written atomically; if either is missing on `get`, treat as cache miss and clean up. Don't store the BLAKE3 *inside* the msgpack — circular.
- **5 GB is the Phase 2 default cap.** Phase 14 will tune (per `final-design.md "Components" #8`). Don't hardcode; expose as constructor arg with sensible default.
- **`--include-sub-caches` defaults to `False` in Phase 2.** Phase 0's `cache gc` already prunes the per-probe blob cache by age; this flag opts in to *additional* sub-cache pruning. The Phase 2 default keeps existing behavior unchanged.
- **No threads — but the test uses them.** The cache is called from `asyncio.to_thread` in probe code; the threading test is a stand-in for the worst-case interleave. If the test flakes on CI, raise the iteration count rather than adding a lock — the atomic-write + BLAKE3 verify is the correct invariant.
