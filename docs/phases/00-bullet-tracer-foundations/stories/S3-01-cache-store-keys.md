# Story S3-01 — Cache store + two-level keys per ADR-0003

**Step:** Step 3 — Build the harness internals (cache, coordinator, validator, sanitizer, writer, config)
**Status:** Ready
**Effort:** M
**Depends on:** S2-05
**ADRs honored:** ADR-0001, ADR-0003, ADR-0004, ADR-0011

## Validation notes

**Validated:** 2026-05-13 · **Verdict:** HARDENED · **Validator:** phase-story-validator v1
**Report:** [`_validation/S3-01-cache-store-keys.md`](_validation/S3-01-cache-store-keys.md)

The story's goal and shape are correct (it is the load-bearing landing for Gap 1 from `phase-arch-design.md §Gap analysis`). Three critics surfaced four classes of holes:

1. **Three of the four "miss paths" are only sketched.** AC-5 names corruption, hash-mismatch, missing-blob, and TTL-stale as collapsing to `get == None`, but the TDD plan only pins corruption-as-zero-bytes. The other three paths (valid-JSON-but-wrong-SHA-256, index-record-orphaned-blob-deleted, index-record-older-than-TTL) are independent code paths the executor can ship as no-ops without any test failing. A mutant that skips the SHA-256 verification step survives the existing TDD plan unchanged.
2. **The happy-path round-trip is unpinned.** No AC or TDD test asserts that `put(key, output)` followed by `get(key)` returns a value equal to `output`. A `put` that silently returns without writing anything passes every existing test (corruption-as-miss is a *miss* test, not a hit test).
3. **The index record schema is implicit.** The story body says blobs are content-addressed by BLAKE3, the index carries a SHA-256 tamper-check, and TTL is enforced — but the fields of the JSONL record (`key`, `blob_blake3`, `blob_sha256`, `created_at_unix_s`, ...) are never pinned. The executor has to guess; downstream consumers (`AuditWriter` in S3-06, ADR-0004's `cache_key` + `blob_sha256` linkage) need a stable shape.
4. **Two helper-functions referenced by the story do not exist yet.** `declared_inputs_for(probe, snapshot)` is called from the proposed `key_for` body in Implementation outline §1 but is undefined anywhere in the codebase or arch. Likewise, `hashing.py` (frozen by S2-03) does not export a SHA-256-of-bytes or BLAKE3-of-bytes helper — yet the store needs to compute *both* over the serialized blob bytes (BLAKE3 for the content-addressed filename; SHA-256 for the index tamper-check), and ADR-0001's chokepoint discipline forbids importing `hashlib.sha256` or `blake3` outside `hashing.py`.

Edits applied:

- ADR-0004 added to the honored-ADRs list (the dual cache_key + blob_sha256 anchors this story produces are consumed by S3-06's `AuditWriter`).
- AC-5 split into a four-row miss-matrix (corruption / hash-mismatch / missing-blob / TTL-stale → distinct log events) and AC-6 (cold-start: `get` against a nonexistent index returns `None` + `cache.miss`).
- Five new ACs appended (AC-8 through AC-12) pinning: round-trip equality, the index-record schema, the `per_probe_schema_version` fallback to envelope on `FileNotFoundError`, last-write-wins multi-record semantics, the `index.jsonl` mode bits + record-size guard.
- One new AC (AC-13) requiring `src/codegenie/hashing.py` to grow two byte-hash helpers (`content_hash_bytes`, `identity_hash_bytes`) with their own `test_hashing.py` cases — surgical extension of the ADR-0001 chokepoint.
- One new AC (AC-14) pinning `declared_inputs_for(probe, snapshot) -> list[Path]` in `cache/keys.py` resolving each glob in `probe.declared_inputs` against `snapshot.root` (stable sort, missing-paths skipped without raising).
- TDD plan red section rewritten end-to-end so each new miss path, the round-trip, the fallback, the multi-record case, and the `0600` index assertion have one mutation-resistant snippet each (no more `...  # detail in implementation` placeholders for the load-bearing tests).
- Implementer notes extended with the `declared_inputs_for` shape, the hashing-helper extension policy, and the JSONL record schema.
- `Files to touch` now includes `src/codegenie/hashing.py` and `tests/unit/test_hashing.py` (extension, not rewrite).

Architectural inconsistencies surfaced (not auto-fixed — out of scope per editor surgical-edit rules):

- `phase-arch-design.md §Component design — CacheStore` (line ~496) names the key inputs as `content_hash_of_declared_inputs`; the story's `key_for` calls `content_hash_of_inputs(declared_inputs_for(...))`. The two are the same in intent but the arch line never defines the resolution helper. Recommended doc-correction: add a one-sentence note to that section pointing at `cache/keys.declared_inputs_for`.
- `phase-arch-design.md §CacheStore` does not name where the blob-content hash (the `<blake3-hex>` in the filename) is computed; the chokepoint discipline implies it must live in `hashing.py`. The new AC-13 captures the resolution.

## Context

Phase 0's cache is the seam Phase 14's continuous-gather model is built on, and the cache key the audit anchor in ADR-0004 references. The synthesis identified Gap 1 (`phase-arch-design.md §Gap analysis Gap 1`): `final-design.md §2.7`'s "SHA-256(probe_name | probe_version | schema_version | inputs_hash_hex)" tuple under-specifies what `schema_version` means, which would cause a single probe's sub-schema bump to invalidate every probe's cache entries. This story lands the surgical-invalidation fix (per-probe schema version in the key, envelope version NOT in the key) and the JSONL-index + sharded-blob `CacheStore` itself.

This is foundational — every probe that runs in Phase 0+ reads and writes through this store, and the test pinning the invalidation scope is the load-bearing regression test for Gap 1.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — CacheStore` — JSONL index, sharded blobs, atomic writes, miss-on-error semantics
  - `../phase-arch-design.md §Gap analysis Gap 1` — the under-specification this story closes; defines `envelope_schema_version` vs `per_probe_schema_version`
  - `../phase-arch-design.md §Edge cases` rows 3, 6, 12 — corruption-as-miss, CI cache-restore mode flatten, concurrent JSONL append
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-two-level-cache-key-schema-versioning.md` — ADR-0003 — per-probe sub-schema `$id` is in the key; envelope version is NOT
  - `../ADRs/0001-cache-content-hash-algorithm.md` — ADR-0001 — BLAKE3 for content hash of inputs, SHA-256 for identity tuple; both via `hashing.py`
  - `../ADRs/0011-codegenie-directory-permissions-model.md` — ADR-0011 — `0700` dirs, `0600` files, re-applied via `os.chmod` after every write
- **Source design:**
  - `../final-design.md §2.7` — original cache key tuple (under-specified; Gap 1 closes it)
- **Existing code (if any):**
  - `src/codegenie/hashing.py` — already lands in S2-03; reuse `identity_hash` and `content_hash_of_inputs`
  - `src/codegenie/probes/base.py` — `Probe` ABC carries `name`, `version`, `declared_inputs`
  - `src/codegenie/errors.py` — `CacheError`

## Goal

`CacheStore.key_for(probe, snapshot, task)` returns an `sha256:<hex>` identity hash composed from `(probe.name, probe.version, per_probe_schema_version(probe), content_hash_of_inputs(...))` — and bumping one probe's sub-schema `$id` does not invalidate any other probe's cache entry.

## Acceptance criteria

- [ ] `src/codegenie/cache/keys.py` exports `envelope_schema_version() -> str`, `per_probe_schema_version(probe: type[Probe]) -> str`, and `key_for(probe, snapshot, task) -> str`. `key_for`'s return is prefixed `sha256:`.
- [ ] `per_probe_schema_version` reads the probe's declared sub-schema path (`src/codegenie/schema/probes/<name>.schema.json`) and extracts the `$id` field; if the probe has no sub-schema, falls back to `envelope_schema_version()`.
- [ ] The key tuple does **not** include `envelope_schema_version` — only `per_probe_schema_version(probe)`.
- [ ] `src/codegenie/cache/store.py` exports `CacheStore` with `get(key) -> ProbeOutput | None`, `put(key, output) -> None`, `key_for(probe, snapshot, task) -> str`. Storage layout: `.codegenie/cache/index.jsonl` (append-only, records ≤ 4096 B) + `.codegenie/cache/blobs/<2-char-shard>/<blake3-hex>.json`.
- [ ] All writes are atomic: `<dest>.tmp` → `os.fsync` → `os.replace`. After every write, `os.chmod` re-applies `0700` on every directory and `0600` on every file (ADR-0011).
- [ ] **Miss-matrix (four independent paths, each tested).** Every row collapses to `get(...) == None` *and* emits the named structured log event; the coordinator re-runs the probe. Each row is one separate test in `test_cache_store.py` (a mutant that skips any one verification step must fail at least one row):

  | # | Path | How tested | Log event |
  |---|---|---|---|
  | 5a | Blob bytes unreadable as JSON (e.g., truncated to 0 bytes) | `put(...)` then truncate the blob file | `cache.blob.invalid` |
  | 5b | Blob bytes parse as JSON but their SHA-256 ≠ the index record's `blob_sha256` (tamper-check) | `put(...)` then rewrite the blob with different valid JSON, leaving the index entry pointing at the old SHA-256 | `cache.blob.invalid` |
  | 5c | Index record exists but the blob file is missing (orphan) | `put(...)` then `os.unlink` the blob file | `cache.blob.invalid` |
  | 5d | Index record's `created_at_unix_s` is older than `ttl_hours` | `put(...)` then monkeypatch wall-clock / freeze time forward past `ttl_hours` | `cache.stale` |
- [ ] **Cold-start.** `get(key)` against a `cache_dir` whose `index.jsonl` does not exist returns `None` and emits a `cache.miss` event; no exception is raised; `cache_dir` itself is created if absent (with mode `0700`).
- [ ] `tests/unit/test_cache_store.py` and `tests/unit/test_cache_invalidation_scope.py` exist and pass; the latter is the Gap-1 regression test (red → green → assert below).
- [ ] **Round-trip happy path.** `put(key, output)` followed by `get(key)` returns a `ProbeOutput` whose every field (including `schema_slice`, `raw_artifacts` paths, `confidence`, `duration_ms`, `warnings`, `errors`) equals the original — guarding against a `put` that silently no-ops or a `get` that returns a partial reconstruction. Paths in `raw_artifacts` round-trip as `Path` (or `str` consistently — pin one and assert).
- [ ] **Index record schema.** Each `index.jsonl` line is a single-line JSON object with at least these fields, sorted-keys, compact-separators (`json.dumps(..., sort_keys=True, separators=(",", ":"))`): `{"key": str, "blob_blake3": str, "blob_sha256": str, "created_at_unix_s": int, "probe_name": str, "probe_version": str}`. Test pins both the field set and the serialization shape (a record reading back via `json.loads` returns exactly these keys with the right types).
- [ ] **`per_probe_schema_version` fallback.** Calling `per_probe_schema_version(probe_cls)` on a probe whose declared sub-schema path does not exist returns `envelope_schema_version()` — pinned by a test that registers a synthetic probe with no sub-schema and asserts equality.
- [ ] **Last-write-wins on multi-record.** After two successive `put(key, output1)` then `put(key, output2)` for the same key (with different content), `get(key)` returns the `output2` payload — the index `get` walk returns the *latest* matching record, not the first.
- [ ] **`index.jsonl` mode + record-size guard.** After any `put`, `index.jsonl` is mode `0o600` (separate assertion from the blob and dir mode checks). `put` must refuse to write a record whose serialized length (including the trailing `\n`) exceeds `4096` bytes — raises `CacheError` and does not append anything, preserving the `PIPE_BUF` atomicity invariant from `phase-arch-design.md §Edge case 12`. A test crafts a probe with an oversized `schema_slice` and asserts both the raise and that `index.jsonl` is unchanged.
- [ ] **Hashing chokepoint extension.** `src/codegenie/hashing.py` grows two public helpers — `content_hash_bytes(b: bytes) -> str` returning `"blake3:<64-hex>"` and `identity_hash_bytes(b: bytes) -> str` returning `"sha256:<64-hex>"` — *and only these helpers are imported by `cache/store.py`*. `tests/unit/test_hashing.py` gains a parity test asserting `content_hash_bytes(p.read_bytes()) == content_hash(p)` for any `p`, and another asserting `identity_hash_bytes(b)` matches an external `hashlib.sha256(b).hexdigest()` known-vector. ADR-0001's "no other file imports `blake3` or `hashlib.sha256`" remains unviolated.
- [ ] **`declared_inputs_for(probe, snapshot) -> list[Path]`** exists in `src/codegenie/cache/keys.py`. Each glob in `probe.declared_inputs` is resolved against `snapshot.root` using `Path.rglob` (or equivalent); the returned list is sorted (deterministic), de-duplicated, and silently skips paths that do not exist on disk (no `FileNotFoundError` raised — that's the cache-miss layer's job). A test fixture with two probes and three globbed files pins the sorted-and-dedup'd output.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/cache/`, and `pytest tests/unit/test_cache_store.py tests/unit/test_cache_invalidation_scope.py tests/unit/test_hashing.py -q` are clean.

## Implementation outline

1. Author `src/codegenie/cache/keys.py`. Define `envelope_schema_version()` reading the envelope schema's `$id`. Define `per_probe_schema_version(probe)` reading `src/codegenie/schema/probes/<probe.name>.schema.json`'s `$id`; fall back to envelope on `FileNotFoundError`. Implement `key_for(probe, snapshot, task)` calling `identity_hash(probe.name, probe.version, per_probe_schema_version(probe), content_hash_of_inputs(declared_inputs_for(probe, snapshot)))`.
2. Author `src/codegenie/cache/store.py`. `CacheStore.__init__(self, cache_dir: Path, ttl_hours: int)`. Implement `key_for` as a thin delegate to `keys.key_for`. Implement `get` by reading `index.jsonl` line-by-line (no mmap; ADR §Edge case 12), finding the latest record with matching `key`, reading the blob at `blobs/<shard>/<blake3>.json`, validating the blob's SHA-256 against the index, returning a `ProbeOutput`. On any error, return `None` and emit a structured log event.
3. Implement `put` by writing the blob to `<dest>.tmp`, fsync, `os.replace`, then appending a single-line JSON record to `index.jsonl` via `O_APPEND` (single `os.write` call; record ≤ 4096 B). After both writes, re-apply `os.chmod 0700` to every directory and `0600` to every file in the cache tree.
4. Write the two test files. The invalidation-scope test is the Gap-1 anchor.
5. Document at the top of `keys.py` the two-version distinction in a 3-sentence docstring referencing ADR-0003.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_cache_invalidation_scope.py` (Gap-1 regression anchor) and `tests/unit/test_cache_store.py`.

```python
# tests/unit/test_cache_invalidation_scope.py
def test_cache_invalidation_scope_is_per_probe(tmp_path, monkeypatch):
    """Gap 1: bumping NodeManifestProbe's sub-schema $id MUST NOT invalidate
    LanguageDetectionProbe's cache entry. The envelope version is NOT in the key."""
    # arrange: register two synthetic probes A and B, each with its own sub-schema
    #          installed under tmp_path / "schema/probes/{a,b}.schema.json".
    #          Compute key_for(A) and key_for(B). Snapshot/Task are constants.
    # act: bump B's sub-schema $id from v0.1.0 to v0.2.0 (rewrite the file).
    #      Recompute key_for(A) and key_for(B).
    # assert: key_for(A) is UNCHANGED across the bump; key_for(B) IS changed.
    ...

def test_envelope_version_bump_does_not_invalidate_any_probe(tmp_path):
    """The envelope $id is metadata; bumping it must not touch any probe key."""
    # arrange: register one probe with a sub-schema; capture key_for(probe).
    # act: rewrite the envelope schema's $id from v0.1.0 to v0.2.0.
    # assert: key_for(probe) is unchanged.
    ...
```

```python
# tests/unit/test_cache_store.py

# ---- Happy-path round-trip -------------------------------------------------

def test_put_then_get_returns_equivalent_output(tmp_path):
    """AC: round-trip happy path. A put-no-op mutant fails here.
    Why: corruption-as-miss tests are MISS tests; without this, put could
    silently return without writing and every other test still passes."""
    store, key, output = _store_with_key(tmp_path)  # synthetic probe + inputs
    store.put(key, output)
    got = store.get(key)
    assert got is not None
    assert got.schema_slice == output.schema_slice
    assert got.confidence == output.confidence
    assert got.duration_ms == output.duration_ms
    assert got.warnings == output.warnings
    assert got.errors == output.errors
    # raw_artifacts shape pinned: see AC; assertion mirrors implementation choice
    assert [str(p) for p in got.raw_artifacts] == [str(p) for p in output.raw_artifacts]


def test_last_write_wins_on_multi_record(tmp_path):
    """AC: multi-record. A get that returns the first matching index line
    (instead of the last) regresses here."""
    store, key, out1 = _store_with_key(tmp_path, schema_slice={"v": 1})
    store.put(key, out1)
    out2 = _make_output(schema_slice={"v": 2})
    store.put(key, out2)
    got = store.get(key)
    assert got is not None and got.schema_slice == {"v": 2}


# ---- Miss-matrix (four independent paths from AC-5) ------------------------

def test_get_none_on_corrupt_blob_zero_bytes(tmp_path, caplog):
    """AC 5a: blob bytes unreadable as JSON."""
    store, key, output = _store_with_key(tmp_path)
    store.put(key, output)
    blob_path = _resolve_blob_path(store, key)
    blob_path.write_bytes(b"")  # truncate
    assert store.get(key) is None
    assert any(r.message == "cache.blob.invalid" for r in caplog.records)


def test_get_none_on_blob_sha256_mismatch(tmp_path, caplog):
    """AC 5b: blob valid JSON but SHA-256 ≠ index record's blob_sha256.
    Mutation-killer: a CacheStore that skips the SHA-256 verification step
    returns the tampered output here instead of None."""
    store, key, output = _store_with_key(tmp_path)
    store.put(key, output)
    blob_path = _resolve_blob_path(store, key)
    # write different but valid JSON; the index still references the old SHA-256
    blob_path.write_text('{"schema_slice":{"tampered":true},"confidence":"low",'
                         '"duration_ms":0,"warnings":[],"errors":[],"raw_artifacts":[]}')
    assert store.get(key) is None
    assert any(r.message == "cache.blob.invalid" for r in caplog.records)


def test_get_none_on_missing_blob(tmp_path, caplog):
    """AC 5c: orphan index record, blob file removed underneath us."""
    store, key, output = _store_with_key(tmp_path)
    store.put(key, output)
    _resolve_blob_path(store, key).unlink()
    assert store.get(key) is None
    assert any(r.message == "cache.blob.invalid" for r in caplog.records)


def test_get_none_on_ttl_stale_entry(tmp_path, caplog, monkeypatch):
    """AC 5d: index record older than ttl_hours.
    Mutation-killer: a CacheStore that ignores ttl_hours returns the value here."""
    store, key, output = _store_with_key(tmp_path, ttl_hours=1)
    store.put(key, output)
    # freeze the clock to 2 hours after the put
    real_time = __import__("time").time
    frozen = real_time() + 2 * 3600
    monkeypatch.setattr("codegenie.cache.store.time.time", lambda: frozen)
    assert store.get(key) is None
    assert any(r.message == "cache.stale" for r in caplog.records)


def test_get_none_on_cold_start_no_index(tmp_path, caplog):
    """AC: cold-start. Empty cache_dir → None + cache.miss, no exception."""
    from codegenie.cache.store import CacheStore
    store = CacheStore(cache_dir=tmp_path / "fresh", ttl_hours=24)
    assert store.get("sha256:" + "0" * 64) is None
    assert any(r.message == "cache.miss" for r in caplog.records)
    # the dir was created with mode 0700
    assert (tmp_path / "fresh").stat().st_mode & 0o777 == 0o700


# ---- Index record schema (AC) ----------------------------------------------

def test_index_record_schema_pin(tmp_path):
    """AC: every index.jsonl line is a single JSON object with the named fields,
    sort_keys + compact separators."""
    store, key, output = _store_with_key(tmp_path)
    store.put(key, output)
    line = (tmp_path / "cache" / "index.jsonl").read_text().splitlines()[0]
    record = __import__("json").loads(line)
    assert set(record) >= {
        "key", "blob_blake3", "blob_sha256",
        "created_at_unix_s", "probe_name", "probe_version",
    }
    assert isinstance(record["created_at_unix_s"], int)
    assert record["blob_sha256"].startswith("sha256:")
    assert record["blob_blake3"].startswith("blake3:")
    # serialization shape: no whitespace, sorted keys
    assert " " not in line  # compact separators
    assert ", " not in line


# ---- Atomic write + modes --------------------------------------------------

def test_atomic_write_no_partial_visible(tmp_path):
    """AC: atomic write. If os.replace fails mid-write, no destination file
    exists (the .tmp may or may not — the invariant is that a partial file is
    never visible at the final path)."""
    import os, pytest
    store, key, output = _store_with_key(tmp_path)
    real_replace = os.replace
    def _boom(src, dst): raise OSError("simulated mid-write crash")
    __import__("unittest.mock").mock.patch("os.replace", _boom).start()
    with pytest.raises(OSError):
        store.put(key, output)
    __import__("unittest.mock").mock.patch.stopall()
    # final blob path was never visible
    final_blob = _resolve_blob_path(store, key)
    assert not final_blob.exists()
    assert store.get(key) is None  # miss, not corruption


def test_post_write_modes_pin_dirs_blobs_and_index(tmp_path):
    """AC: every dir 0700, every blob file 0600, index.jsonl 0600 (pinned
    separately so a 'forgot to chmod index.jsonl' mutant fails)."""
    store, key, output = _store_with_key(tmp_path)
    store.put(key, output)
    cache_root = tmp_path / "cache"
    assert cache_root.stat().st_mode & 0o777 == 0o700
    index = cache_root / "index.jsonl"
    assert index.stat().st_mode & 0o777 == 0o600
    for p in cache_root.rglob("*"):
        if p.is_dir():
            assert p.stat().st_mode & 0o777 == 0o700, p
        else:
            assert p.stat().st_mode & 0o777 == 0o600, p


def test_record_size_guard_refuses_oversize(tmp_path):
    """AC: a record whose serialized length exceeds PIPE_BUF=4096 B is
    refused (CacheError); index.jsonl is unchanged."""
    import pytest
    from codegenie.errors import CacheError
    store, key, _ = _store_with_key(tmp_path)
    # craft an output whose serialized record will exceed 4096 B
    huge = _make_output(schema_slice={"big": "x" * 5000})
    index = tmp_path / "cache" / "index.jsonl"
    before = index.read_bytes() if index.exists() else b""
    with pytest.raises(CacheError):
        store.put(key, huge)
    after = index.read_bytes() if index.exists() else b""
    assert before == after
```

```python
# tests/unit/test_cache_invalidation_scope.py
def test_cache_invalidation_scope_is_per_probe(tmp_path, monkeypatch):
    """Gap 1: bumping NodeManifestProbe's sub-schema $id MUST NOT invalidate
    LanguageDetectionProbe's cache entry. The envelope version is NOT in the key.
    Mutation-killer: a key_for that includes envelope_schema_version (or that
    swaps per_probe for envelope) fails here."""
    # arrange: monkeypatch the schema-probe-dir resolver so per_probe_schema_version
    #          reads from tmp_path / "schema/probes/" instead of the installed path.
    # arrange: write a.schema.json with $id ".../probes/a/v0.1.0.json"
    #          and b.schema.json with $id ".../probes/b/v0.1.0.json".
    #          Register synthetic Probe subclasses A and B.
    #          Compute key_for(A) and key_for(B). Snapshot/Task are constants.
    # act: rewrite b.schema.json with $id ".../probes/b/v0.2.0.json".
    #      Recompute key_for(A) and key_for(B).
    # assert: key_for(A) is UNCHANGED across the bump; key_for(B) IS changed.
    ...


def test_envelope_version_bump_does_not_invalidate_any_probe(tmp_path, monkeypatch):
    """The envelope $id is metadata; bumping it must not touch any probe key.
    Mutation-killer: a key_for that includes envelope_schema_version in the
    tuple (alongside or instead of per-probe) fails here."""
    # arrange: register one probe WITH a sub-schema; capture key_for(probe).
    # act: rewrite the envelope schema's $id from v0.1.0 to v0.2.0.
    # assert: key_for(probe) is unchanged.
    ...


def test_per_probe_schema_version_falls_back_to_envelope_on_missing(tmp_path, monkeypatch):
    """AC: fallback. A probe with no sub-schema file uses envelope_schema_version().
    Mutation-killer: a fallback that raises FileNotFoundError or returns "" fails."""
    from codegenie.cache.keys import envelope_schema_version, per_probe_schema_version
    # monkeypatch the schema-probe-dir resolver to point at an empty dir
    # register a synthetic Probe with name "no_subschema_probe"
    assert per_probe_schema_version(NoSubschemaProbe) == envelope_schema_version()
```

Run the two test files; they must fail with `ImportError`/`AttributeError`/`AssertionError`. Commit as the red marker.

### Green — make it pass

1. Land `src/codegenie/cache/keys.py` with the two functions and `key_for`.
2. Land `src/codegenie/cache/store.py` with the `CacheStore` class. Implement `get` and `put` minimally — index walk + blob read/write with atomic-replace + chmod re-apply. No GC, no sharding optimization, no fancy TTL eviction yet.
3. Wire the schema-path resolution so `per_probe_schema_version` can find `schema/probes/<probe.name>.schema.json`. Phase 0 has only `language_detection`; future probes follow the convention.

### Refactor — clean up

- Type hints throughout; `mypy --strict` clean on `src/codegenie/cache/`.
- Docstrings on `CacheStore.get`, `.put`, `.key_for`, and the two `keys.py` functions. The `keys.py` module docstring cites ADR-0003.
- Add the corruption/stale/miss log events with structlog field names matching `phase-arch-design.md §Harness engineering` (`cache.blob.invalid`, `cache.stale`, `cache.miss`).
- Honor edge case #12: appended records stay under `PIPE_BUF=4096` B by construction (compact JSON, no whitespace).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cache/__init__.py` | Package marker; re-exports `CacheStore`, `key_for` |
| `src/codegenie/cache/keys.py` | New — per-probe vs envelope version, `key_for`, `declared_inputs_for` |
| `src/codegenie/cache/store.py` | New — `CacheStore` with JSONL index + sharded blobs |
| `src/codegenie/hashing.py` | **Extension** — adds `content_hash_bytes(b)` and `identity_hash_bytes(b)` to keep ADR-0001's chokepoint discipline intact (`cache/store.py` must not import `blake3` or `hashlib.sha256` directly). |
| `tests/unit/test_cache_store.py` | New — round-trip, four-row miss matrix, cold-start, last-write-wins, index-record-schema, atomic write, modes (incl. `index.jsonl`), record-size guard |
| `tests/unit/test_cache_invalidation_scope.py` | New — Gap-1 regression anchor + envelope-bump invariance + fallback-to-envelope-on-missing |
| `tests/unit/test_hashing.py` | **Extension** — parity tests for the two new byte-hash helpers (matches `content_hash(path)` over the same bytes and a stdlib `hashlib.sha256` known-vector). |

## Out of scope

- **Concurrent-cache stress test** — handled by S5-01 (`test_cache_concurrent.py`).
- **`cache gc` subcommand body** — stubbed in S4-02; full implementation deferred (no exit criterion this phase).
- **HMAC-signed index** — explicitly deferred to Phase 14 (`phase-arch-design.md §Non-goals` row 4).
- **Audit anchor population** — handled by S3-06 (`AuditWriter.record(...)` reads `cache_key` produced by this store).

## Notes for the implementer

- **This story implements Gap 1 from `phase-arch-design.md §Gap analysis`.** The regression test (`test_cache_invalidation_scope_is_per_probe`) is the load-bearing assertion. If you find yourself tempted to include the envelope version in the key "for safety," stop — that defeats the gap fix. ADR-0003 §Decision is unambiguous.
- The blob hash you store in the index record must be SHA-256 of the blob bytes (so `get` can verify against tampering). The BLAKE3 content hash is over *inputs* (going into `key_for`), not outputs. Don't conflate them.
- `index.jsonl` writes use `O_APPEND` so concurrent writers don't tear records as long as each record is ≤ `PIPE_BUF=4096` B. Keep the record schema compact (no human-readable timestamps; UTC unix epoch ints).
- Per ADR-0011, after every write apply `os.chmod` walking the cache tree. The CI `actions/cache` restore re-flattens modes; the next write must restore them. Tests assert *post-gather* state, not post-restore state.
- Corrupt / mismatched / stale all collapse to miss (`final-design.md §2.7`). Never raise to the coordinator; emit a log event and return `None`.
- Don't use `mmap` for the index (`phase-arch-design.md §Non-goals` row 9 + edge case 12). Plain buffered reads.
- The `schema_slice` field of `ProbeOutput` may contain nested dicts; serialize via `json.dumps(..., sort_keys=True, separators=(",", ":"))` so the blob is byte-identical for byte-identical content (deterministic round-trip).
- **`declared_inputs_for(probe, snapshot)` lives in `cache/keys.py`.** Resolution: for each glob in `probe.declared_inputs`, call `snapshot.root.rglob(glob)`, flatten, drop entries that no longer exist (`Path.exists()`), `sorted()` by `str(path)` for determinism, de-duplicate. Do **not** raise on missing paths — the miss-on-error semantics in the store catch that at the cache-layer boundary. (`final-design.md §2.7`.)
- **Hashing helpers — ADR-0001 chokepoint extension.** `content_hash_bytes(b: bytes) -> str` and `identity_hash_bytes(b: bytes) -> str` are added to `hashing.py` in this story. They are the *only* path by which `cache/store.py` computes the blob's BLAKE3 filename component and the blob's SHA-256 tamper-check. ADR-0001's invariant ("no other file under `src/codegenie/` imports `blake3` or `hashlib.sha256`") is preserved — adding to the chokepoint is allowed; bypassing it is not. The parity test `content_hash_bytes(p.read_bytes()) == content_hash(p)` is the load-bearing equivalence-class assertion.
- **Index record schema — pinned.** Each line: `{"key": str, "blob_blake3": str, "blob_sha256": str, "created_at_unix_s": int, "probe_name": str, "probe_version": str}`. The SHA-256 in the record (`blob_sha256`) is what S3-06's `AuditWriter` (per ADR-0004) reads as the audit anchor; do not omit it, do not rename it. Future fields (per-probe-schema-version, `confidence`) may be added as Phase 1+ work — additive only, never breaking.
- **`cache.miss` / `cache.stale` / `cache.blob.invalid` log events.** All three are required by the AC and by `phase-arch-design.md §Harness engineering`. `cache.miss` covers cold-start and a true index-doesn't-contain-key miss; `cache.stale` covers TTL expiry; `cache.blob.invalid` covers all three corruption variants (5a/5b/5c). Emit via `structlog` (or stdlib `logging` for Phase 0 — match the convention S2-01 set) with the cache key as a field.
- **`CacheError` is unused at the store-to-coordinator boundary by policy** (per `phase-arch-design.md §Component design / Failure behavior`: "Never raises to the coordinator"). It IS raised for one in-process precondition violation: the record-size guard (AC-12). Keep this distinction explicit so the coordinator doesn't grow a misleading `except CacheError`.
