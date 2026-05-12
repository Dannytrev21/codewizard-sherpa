# Story S3-01 — Cache store + two-level keys per ADR-0003

**Step:** Step 3 — Build the harness internals (cache, coordinator, validator, sanitizer, writer, config)
**Status:** Ready
**Effort:** M
**Depends on:** S2-05
**ADRs honored:** ADR-0001, ADR-0003, ADR-0011

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
- [ ] Corruption (JSON decode error), hash mismatch, missing blob, and TTL-stale entries all collapse to `get(...) == None` plus a structured `cache.blob.invalid` / `cache.stale` / `cache.miss` log event; the coordinator re-runs the probe.
- [ ] `tests/unit/test_cache_store.py` and `tests/unit/test_cache_invalidation_scope.py` exist and pass; the latter is the Gap-1 regression test (red → green → assert below).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/cache/`, and `pytest tests/unit/test_cache_store.py tests/unit/test_cache_invalidation_scope.py -q` are clean.

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
def test_get_returns_none_on_corrupt_blob(tmp_path):
    # arrange: put a valid record, then truncate the blob file to 0 bytes.
    # act: store.get(key)
    # assert: returns None; a structlog event "cache.blob.invalid" was emitted.
    ...

def test_atomic_write_no_partial_visible(tmp_path):
    # arrange: simulate an interrupted write by patching os.replace to raise.
    # act: store.put(...)
    # assert: the destination file does NOT exist; only the .tmp was left;
    #         a subsequent get(key) returns None (miss, not corruption).
    ...

def test_post_write_modes_are_0700_0600(tmp_path):
    # arrange: put a value.
    # assert: every dir under cache_dir is mode 0o700; every file 0o600.
    ...
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
| `src/codegenie/cache/keys.py` | New — per-probe vs envelope version, `key_for` |
| `src/codegenie/cache/store.py` | New — `CacheStore` with JSONL index + sharded blobs |
| `tests/unit/test_cache_store.py` | New — get/put/atomic/modes/corruption |
| `tests/unit/test_cache_invalidation_scope.py` | New — Gap-1 regression anchor |

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
