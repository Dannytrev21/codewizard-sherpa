# Story S2-03 — Content-addressed score cache (`get` / `put` / `gc`)

**Step:** Step 2 — Build harness internals: loader, cache, audit chain extension, canary + cost-tag shims
**Status:** Ready
**Effort:** M
**Depends on:** S1-02
**ADRs honored:** Phase 0 ADR-0001 (BLAKE3 chokepoint reuse), ADR-0005 (`cassette_canary_pin` participates in cache-key composition)

## Context

The runner's per-case cache makes `lower_bound_95` computation cheap on warm reruns: a 10-case cold run is ≤12 min; the warm rerun must be ≤8 s (`High-level-impl.md §Step 5` done criterion). The cache is **content-addressed** under `BLAKE3(case_digest || sut_digest || rubric_digest || cassette_corpus_digest || harness_version || cassette_canary_pin)` (`phase-arch-design.md §Component design — cache.py`). The two load-bearing disciplines are (a) **atomic writes** — `<key>.tmp` then `os.rename` to `<key>.json` so a mid-write crash leaves the previous value intact (`phase-arch-design.md §Edge cases #16`); and (b) **corrupt-on-read is a miss, not a failure** — a truncated cache file emits a structlog warning and re-executes the case, never poisoning the run.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — src/codegenie/eval/cache.py` — public interface, cache-key composition, `fcntl.flock` discipline, GC by mtime
  - `../phase-arch-design.md §Edge cases #16` — corrupt cache file → miss
  - `../phase-arch-design.md §Edge cases #17` + `§Process view (Concurrency note)` — `fcntl.flock` serializes writers within one host
  - `../phase-arch-design.md §Non-goals #9, #10` — per-host cache only, no remote/shared; nightly single-host cadence
  - `../phase-arch-design.md §Property tests` — cache-key determinism and uniqueness invariants
- **Phase ADRs:**
  - `../ADRs/0005-cassette-canary-seed-parameterization.md §Consequences` — `cassette_canary_pin` is part of cache-key composition so a curator who rotates a pin invalidates only that case's cache entry
- **Source design:**
  - `../final-design.md §Components → cache.py` — original key-composition spec
- **Existing code:**
  - `src/codegenie/eval/models.py` (S1-02) — `BenchScore` Pydantic; `frozen=True`, `extra="forbid"`; the cache's value type
  - `src/codegenie/hashing.py` (Phase 0 S2-03) — `identity_hash` for SHA-256 composition if needed; `content_hash` for BLAKE3 — but cache-key is straight BLAKE3 over a concatenation, so reuse the BLAKE3 helper, do **not** import `blake3` directly
  - Phase 0 cache-store precedent (`src/codegenie/cache/store.py`) — atomic-write + flock pattern

## Goal

`codegenie.eval.cache` exposes `get` / `put` / `gc` with content-addressed keys; `put` is atomic (`os.rename`) under `fcntl.flock`; `get` is lock-free and treats corrupt files as miss with a structured warning; `gc` evicts entries older than `retain_days` by mtime.

## Acceptance criteria

- [ ] Module API: `get(cache_key: str, cache_dir: Path) -> BenchScore | None`, `put(cache_key: str, score: BenchScore, cache_dir: Path) -> None`, `gc(cache_dir: Path, retain_days: int = 90) -> int` (returns count evicted).
- [ ] **Cache-key composer:** `compose_cache_key(*, case_digest: str, sut_digest: str, rubric_digest: str, cassette_corpus_digest: str, harness_version: str, cassette_canary_pin: str) -> str` returns `blake3:<64-hex>`; the function is sort-stable in **input shape only** (positional vs kwargs); the inputs are concatenated in the documented fixed order via a non-ambiguous separator (`\x1f` unit-separator, per Phase 0 `hashing.identity_hash`'s convention), then run through BLAKE3.
- [ ] Round-trip: `put(k, score, dir); get(k, dir) == score` for a freshly constructed `BenchScore` with all fields populated; Pydantic equality holds (frozen models compare by field values).
- [ ] **Atomicity:** writing `<dir>/<key>.json` writes `<dir>/<key>.tmp` first, `os.fsync` the file (and ideally the dir), then `os.rename`. A simulated crash between `.tmp` create and `os.rename` (test deletes the `.tmp` mid-write) leaves any **previous** `<key>.json` intact and untouched.
- [ ] **Lock discipline:** `put` acquires `fcntl.flock(LOCK_EX)` on `<dir>/.lock` (a sentinel file, mode `0600`) and releases on success or exception (use a `with` block via `contextlib`). `get` does NOT take the lock.
- [ ] **Corrupt-file-on-read is a miss:** if `<dir>/<key>.json` exists but `BenchScore.model_validate_json` raises, return `None` and emit a `structlog.warn cache.corrupt_entry` event with `cache_key` and `path`. Do NOT raise; do NOT delete the file (operators may want to inspect).
- [ ] **Missing-file-on-read is a miss:** `get` returns `None` without warning.
- [ ] `gc(cache_dir, retain_days=90)` returns the number of entries deleted; uses `Path.stat().st_mtime`; never deletes `.lock`.
- [ ] **Cache-key composition determinism:** two calls to `compose_cache_key` with identical kwargs produce the byte-identical hex string (Hypothesis property test).
- [ ] **Cache-key composition uniqueness:** changing any one of the six inputs changes the output (parametrized test, one row per input).
- [ ] `cassette_canary_pin` participates in the key (ADR-0005) — a pin rotation on one case invalidates exactly that case's entry; verified by parametrized test row over `cassette_canary_pin`.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. Create `src/codegenie/eval/cache.py`.
2. `compose_cache_key(...)` — kw-only signature; concatenate the six values with `"\x1f"` separator (UTF-8 encoded); call `codegenie.hashing.content_hash` over the bytes (or expose a new helper `bytes_hash` in `hashing.py` — surface this with the implementer if Phase 0 helpers don't fit cleanly; minimal lift). Return `blake3:<hex>`.
3. `get(cache_key, cache_dir)`:
   - Resolve `path = cache_dir / f"{cache_key.removeprefix('blake3:')}.json"` (or stash the raw key — pick one in implementation; document).
   - If missing → return `None`.
   - Read bytes; `BenchScore.model_validate_json(...)`; on `pydantic.ValidationError` or `json.JSONDecodeError`, `structlog.warn` + return `None`.
4. `put(cache_key, score, cache_dir)`:
   - Ensure `cache_dir.mkdir(parents=True, exist_ok=True)`.
   - Touch `<cache_dir>/.lock` mode `0600` if missing.
   - `with open(lock_path, "r") as lockfile: fcntl.flock(lockfile, LOCK_EX)`.
   - Write `<key>.tmp` (mode `0600`), `os.fsync(fd)`, `os.rename` to `<key>.json`. Release lock on `with` exit.
5. `gc(cache_dir, retain_days)`:
   - Walk `*.json` under `cache_dir`; for each, if `mtime < now - retain_days * 86400`, `unlink`. Skip `.lock`.
6. Module `__all__ = ("get", "put", "gc", "compose_cache_key")`.

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/eval/test_cache.py`

```python
def test_round_trip_get_returns_put_value(tmp_path):
    score = BenchScore(passed=True, score=1.0, breakdown={}, failure_modes=(), cost_usd=0.0, wall_clock_ms=10)
    cache.put("blake3:" + "a"*64, score, tmp_path)
    assert cache.get("blake3:" + "a"*64, tmp_path) == score

def test_get_missing_returns_none(tmp_path):
    assert cache.get("blake3:" + "b"*64, tmp_path) is None

def test_get_corrupt_returns_none_and_warns(tmp_path, caplog):
    p = tmp_path / ("a"*64 + ".json")
    p.write_text("{not valid json")
    assert cache.get("blake3:" + "a"*64, tmp_path) is None
    # caplog contains cache.corrupt_entry with key+path
    ...

def test_put_writes_atomic_via_tmp_rename(tmp_path, monkeypatch):
    # Patch os.rename to record the source and dest; assert dest endswith .json, source endswith .tmp.
    ...

def test_put_does_not_touch_previous_value_on_simulated_mid_write_crash(tmp_path):
    # Put v1; simulate a partial write of v2 by leaving a .tmp file; assert get returns v1.
    ...

def test_put_takes_exclusive_lock(tmp_path):
    # Spawn two threads racing on cache.put; one's writes never interleave another's bytes — verified by
    # asserting each get() returns a complete, valid BenchScore (no JSON truncation).
    ...

def test_gc_evicts_old_returns_count(tmp_path):
    # Put two entries; touch one's mtime back 100 days; gc(retain_days=90) returns 1.
    ...

def test_compose_cache_key_determinism():
    k1 = cache.compose_cache_key(case_digest=..., sut_digest=..., rubric_digest=..., cassette_corpus_digest=..., harness_version=..., cassette_canary_pin=...)
    k2 = cache.compose_cache_key(case_digest=..., ...)  # same inputs
    assert k1 == k2 and k1.startswith("blake3:") and len(k1) == len("blake3:") + 64

@pytest.mark.parametrize("varying", ["case_digest", "sut_digest", "rubric_digest", "cassette_corpus_digest", "harness_version", "cassette_canary_pin"])
def test_compose_cache_key_uniqueness_per_input(varying):
    # Flip one input; assert key differs.
    ...
```

### Green

Smallest impl: §Implementation outline; ~70 lines.

### Refactor

- Extract `_atomic_write_json(path: Path, data: bytes) -> None` — usable later by `audit.py` (atomic-rename pattern is shared).
- Wrap `fcntl.flock` in a `contextlib.contextmanager` `_cache_write_lock(cache_dir)` for clarity.
- Add a structlog `info` event `cache.eviction` per evicted entry in `gc` (operator-debuggability).
- Document the `.lock` sentinel as part of the directory contract — never lives outside `cache_dir`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/cache.py` | New module — `get`, `put`, `gc`, `compose_cache_key` |
| `tests/unit/eval/test_cache.py` | Red tests covering all ACs |
| `src/codegenie/hashing.py` | (Optional, minimal) add `bytes_hash` helper if BLAKE3-over-bytes doesn't fit `content_hash`'s path-only signature |

## Out of scope

- **Cache-key composition at runtime** — the runner (S3-01) calls `compose_cache_key` once it has the per-run digests; this story only exposes the function.
- **GC scheduling** — the runner (S3-02 end-of-run) invokes `gc(retain_days=90)`; cron-style scheduling is out.
- **Cross-host cache sharing** — explicit non-goal (`phase-arch-design.md §Non-goals #9`).
- **Cache-key index / manifest** — the filesystem `<key>.json` listing IS the index; no separate manifest.

## Notes for the implementer

- **Do not import `blake3` here** — Phase 0 ADR-0001 says `codegenie.hashing` is the only file that does. If `content_hash` doesn't support raw bytes, add a small `bytes_hash` helper in `hashing.py` and reuse it.
- The `\x1f` (ASCII unit separator) is from Phase 0 S2-03 `identity_hash` — reuse, don't invent a new convention.
- `fcntl.flock` is Linux/macOS-only; this is fine — `phase-arch-design.md §Implementation-level risks #3` flags macOS surprises as a Step 3 concern, not here.
- Mode `0600` for both `<key>.json` and `.lock` — matches Phase 0 ADR-0011 directory-permissions model (audit anchor will use the same).
- `BenchScore` is `frozen=True`; `model_validate_json` returns a new instance every call — `==` works by field-value equality (Pydantic v2 default for frozen models). Tests can rely on `assert a == b`.
- Beware of the cache-key prefix in the filename: pick **either** `<full-key>.json` or `<hex>.json` (without prefix). Either works; document which. Keeping `blake3:` out of the filename avoids OS-level filename-character surprises (colon on Windows). Recommend filename = hex only; the prefix lives only inside the key string.
- The "simulated mid-write crash" test should use `unittest.mock.patch("os.rename", side_effect=OSError)`, then assert the `.tmp` file may still exist but `<key>.json` was never modified.
- `gc` returns an `int` count for observability (the runner can log "evicted N stale entries"). This is the only function with a non-`None` return aside from `get`.
