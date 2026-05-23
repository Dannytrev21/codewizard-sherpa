# Story S3-05 — `BlobRef` smart constructor + content-addressed store

**Step:** Step 3 — Canonical event log, BlobRef store, and activity-boundary sanitizer
**Status:** Ready
**Effort:** M
**Depends on:** S1-02 (`BlobDigest` newtype; `BlobRef`'s referenced types); S2-03 (`events.blob_refs` table)
**ADRs honored:** ADR-0005 (payload-by-reference via `BlobRef` for activity payloads > 8 KiB — **load-bearing**), ADR-0012 (Postgres canonical event store), production ADR-0008 (secret-redaction — pairs with S3-06)

## Context

Temporal records every activity input/output in workflow history byte-by-byte. Phase 8's `ContextBundle` is 50-150 KiB; a Phase-3 `patch_diff` can be larger; sandbox logs bigger still. If those crossed the activity boundary inline, workflow history would inflate from ~14 records to thousands of KiB and Temporal-UI becomes illegible. **ADR-0005's answer: payloads > 8 KiB ride a `BlobRef(digest, content_kind, byte_len)`; bytes live in `events.blob_refs` keyed by `BLAKE3` digest with `ON CONFLICT DO NOTHING` (content-addressed dedup).**

This story ships the `BlobRef` Pydantic model + the `events.blob_refs` writer/reader + a per-worker LRU cache. **The smart-constructor discipline is load-bearing**: a `BlobRef` exists ONLY by way of `write_blob_ref` (the activity that lands in S4-02). This story ships the *kernel* — the `_BlobStore` class with `write` / `resolve` methods + `BlobRef` model. S4-02 wraps `_BlobStore.write` in the `@register_activity(name="write_blob_ref")` decorator.

The content-addressed dedup is the second load-bearing property: identical bytes produce identical `BlobDigest`s produce identical `events.blob_refs` PRIMARY KEY rows produce `ON CONFLICT DO NOTHING` no-ops. Two workflows that build the same `ContextBundle` share one blob row.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C6 — Payload-by-reference` (the canonical reference; public interface; `events.blob_refs` schema; smart-constructor discipline; per-worker LRU).
  - `../phase-arch-design.md §Data model — Postgres schema` (`events.blob_refs (digest BYTEA PRIMARY KEY, content BYTEA NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW(), content_kind TEXT NOT NULL, byte_len BIGINT NOT NULL)`).
  - `../phase-arch-design.md §Goals G8` (workflow-history compactness ≤ 30 events nominally — `BlobRef` is the mechanism).
- **Phase ADRs:**
  - `../ADRs/0005-payload-by-reference-blobref-threshold.md` — **load-bearing.** The 8 KiB threshold; content-addressed dedup via `ON CONFLICT DO NOTHING`; `BlobRef` constructed only by `write_blob_ref`; per-worker LRU cache; `BlobKind` sum-type (`ContextBundle | RepoSnapshotDelta | SandboxLog | PatchDiff | EvidenceBundle`).
  - `../ADRs/0012-event-store-topology-temporal-history-plus-postgres-events.md` — Postgres is the substrate; no separate object store.
- **Existing code:**
  - `src/codegenie/events/alembic/versions/0001_create_events_schema.py` (S2-03) — the `events.blob_refs` table this story writes.
  - `src/codegenie/types/identifiers.py` — `BlobDigest` newtype (S1-01).
  - `src/codegenie/durable/config.py` (S2-02) — `AsyncConnectionPool` factory; this story's `_BlobStore` takes the pool.
- **External:**
  - `blake3` Python binding (same as S3-01).
  - psycopg COPY-binary / parameterized INSERT.
  - Temporal payload-size guidance: `https://docs.temporal.io/workflows#payload-size`.

## Goal

Ship `BlobRef` (frozen Pydantic, `extra="forbid"`) + `_BlobStore.write(content: bytes, content_kind: BlobKind) -> BlobRef` (the smart constructor) + `_BlobStore.resolve(ref: BlobRef) -> bytes`. Content-addressed (`BLAKE3(content)` is the digest); `INSERT ... ON CONFLICT DO NOTHING` is the dedup mechanism. Per-worker LRU bounded to a sane default (start at 256 entries; ~50 MiB at typical bundle sizes). `resolve` raises `BlobDigestMismatchError` if the stored bytes' recomputed digest differs from the ref's digest (tamper-evident at the bytes level).

## Acceptance criteria

- [ ] **AC-1 — `BlobRef` Pydantic model.** `src/codegenie/events/blob_refs.py` exports `class BlobRef(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields `digest: BlobDigest`, `content_kind: BlobKind` (sum-type alias of `Literal["context_bundle", "repo_snapshot_delta", "sandbox_log", "patch_diff", "evidence_bundle"]`), `byte_len: int` (positive). Mutating an instance raises; constructing with an unknown field raises.
- [ ] **AC-2 — `BlobKind` is a closed `Literal` union.** `BlobKind` is defined as `Literal["context_bundle", "repo_snapshot_delta", "sandbox_log", "patch_diff", "evidence_bundle"]` (5 members, matching ADR-0005). Adding a sixth requires updating the type alias (additive). A `mypy --strict` test would flag any usage of a non-member string.
- [ ] **AC-3 — `_BlobStore.write` is the smart constructor.** `class _BlobStore` exposes `async def write(self, content: bytes, *, content_kind: BlobKind) -> BlobRef`. The method (a) computes `digest = BlobDigest(blake3(content).hexdigest())`; (b) issues `INSERT INTO events.blob_refs (digest, content, content_kind, byte_len, created_at) VALUES (...) ON CONFLICT (digest) DO NOTHING`; (c) returns `BlobRef(digest=digest, content_kind=content_kind, byte_len=len(content))`. **`_BlobStore` is module-private (underscore-prefixed)** — production code instantiates it through `write_blob_ref` activity (S4-02); test code accesses it directly.
- [ ] **AC-4 — Smart-constructor discipline.** `BlobRef` has NO `__init__` that takes raw bytes; the only way to produce a `BlobRef` whose `digest` is consistent with stored bytes is `_BlobStore.write`. A unit test attempts to construct `BlobRef(digest=BlobDigest("0"*64), content_kind="context_bundle", byte_len=100)` — succeeds at the Pydantic layer (we don't validate digest-against-bytes here; that's `resolve`'s job), but a test for production code asserts no `BlobRef(...)` construction site outside `_BlobStore` / tests. Use `grep` in a fence test: `tests/fence/test_blob_ref_construction.py` greps `src/codegenie/` for `BlobRef(` and asserts the only construction sites are inside `events/blob_refs.py` itself. Test files and the `write_blob_ref` activity (S4-02) are excluded from the grep.
- [ ] **AC-5 — Content-addressed dedup (`ON CONFLICT DO NOTHING`).** Writing the same bytes twice with the same `content_kind` produces (a) one row in `events.blob_refs`; (b) two structurally equal `BlobRef` objects (same `digest`, `content_kind`, `byte_len`); (c) no error on the second write. Integration test against testcontainers PG: write 100 KiB content; count rows = 1; write again; count rows still = 1.
- [ ] **AC-6 — Different `content_kind` for same bytes still dedups by digest.** Per ADR-0005's content-addressed semantics, `digest` is the PRIMARY KEY. If two callers `write` the same bytes with different `content_kind`s, the first wins (table has one row with the first `content_kind`); the second `write` returns a `BlobRef` with **the database row's `content_kind`**, not the caller's requested one (loud-failure alternative: raise an error). **Choose loud failure**: `_BlobStore.write` reads back the row after `ON CONFLICT DO NOTHING` and asserts `content_kind` matches the caller's; mismatch raises `BlobKindCollision(digest, db_kind, requested_kind)`. Test asserts this raises.
- [ ] **AC-7 — `_BlobStore.resolve` round-trips bytes.** `async def resolve(self, ref: BlobRef) -> bytes`. Returns `events.blob_refs.content` for the digest. Test: write 200 KiB random bytes via `write`; `resolve` returns byte-identical content.
- [ ] **AC-8 — `resolve` detects tamper.** If the stored `content` doesn't recompute to `ref.digest`, `resolve` raises `BlobDigestMismatchError(expected=ref.digest, actual=...)`. Adversarial test: use `migrations_role` to `UPDATE events.blob_refs SET content = $1 WHERE digest = $2` (replacing the bytes); `resolve(ref)` raises the typed error.
- [ ] **AC-9 — Per-worker LRU cache.** `_BlobStore` holds an LRU dict bounded to `lru_max=256` entries. `resolve` checks the cache first; on hit, returns the cached bytes (skipping Postgres). On miss, fetches from Postgres, caches, returns. Cache key is `BlobDigest` (the hex string). Eviction is LRU (OrderedDict + `move_to_end`). Test asserts a hot-path resolve issues zero Postgres queries.
- [ ] **AC-10 — LRU does NOT cache `write` bytes.** The contract is read-side caching only. After `_BlobStore.write(content)`, the next `resolve` hits Postgres (loud — proves the dedup INSERT actually committed). Tests assert this. (If a future phase wants write-side caching, that's an additive optimization gated by a benchmark; not in scope.)
- [ ] **AC-11 — `BlobDigest` is BLAKE3 hex of length 64.** `BlobDigest = NewType("BlobDigest", str)`; values are 64-char hex strings (BLAKE3 default 32-byte output). Test asserts `len(ref.digest) == 64` and `ref.digest` is `[0-9a-f]+`.
- [ ] **AC-12 — Bytes stored as `BYTEA`, not `TEXT`.** Verify via `pg_typeof` or schema inspection that `events.blob_refs.content` is `BYTEA` (S2-03 owns the schema; this test is a belt-and-suspenders snapshot).
- [ ] **AC-13 — `mypy --strict` + cold-start fence + import-cleanliness.** No circular imports; `import codegenie.events.blob_refs` is IO-free; `mypy --strict` clean.

## Implementation outline

1. **`BlobRef` model + `BlobKind` alias.**
    ```python
    BlobKind = Literal["context_bundle", "repo_snapshot_delta", "sandbox_log",
                       "patch_diff", "evidence_bundle"]

    class BlobRef(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        digest: BlobDigest
        content_kind: BlobKind
        byte_len: int = Field(gt=0)
    ```
2. **`BlobDigestMismatchError` + `BlobKindCollision`** in `src/codegenie/events/errors.py`. Both carry typed attributes for forensic triage.
3. **`_BlobStore` class.** Constructor takes `pool: AsyncConnectionPool, lru_max: int = 256`. Stores `self._pool`, `self._cache: OrderedDict[BlobDigest, bytes] = OrderedDict()`.
4. **`write` flow:**
    ```python
    async def write(self, content: bytes, *, content_kind: BlobKind) -> BlobRef:
        digest = BlobDigest(blake3(content).hexdigest())
        byte_len = len(content)
        async with self._pool.connection() as conn:
            async with conn.transaction():
                # Step 1: INSERT ... ON CONFLICT DO NOTHING
                await conn.execute(
                    "INSERT INTO events.blob_refs (digest, content, content_kind, byte_len) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (digest) DO NOTHING",
                    (bytes.fromhex(digest), content, content_kind, byte_len),
                )
                # Step 2: read back content_kind for collision detection
                row = await (await conn.execute(
                    "SELECT content_kind FROM events.blob_refs WHERE digest = %s",
                    (bytes.fromhex(digest),),
                )).fetchone()
                if row is None:
                    # Should not happen — we just inserted (or ON CONFLICT confirmed).
                    raise RuntimeError("BlobStore invariant: row missing after insert")
                if row[0] != content_kind:
                    raise BlobKindCollision(digest, db_kind=row[0], requested_kind=content_kind)
        return BlobRef(digest=digest, content_kind=content_kind, byte_len=byte_len)
    ```
    Note: `digest` is stored as `BYTEA` (32 bytes via `bytes.fromhex(digest)`); `BlobRef.digest` is the hex `str` for ergonomics + JSON-serializability in workflow history.
5. **`resolve` flow:**
    ```python
    async def resolve(self, ref: BlobRef) -> bytes:
        if ref.digest in self._cache:
            content = self._cache[ref.digest]
            self._cache.move_to_end(ref.digest)
            # Cached value is trusted — we wrote it through resolve (the cold path verifies).
            return content
        async with self._pool.connection() as conn:
            row = await (await conn.execute(
                "SELECT content FROM events.blob_refs WHERE digest = %s",
                (bytes.fromhex(ref.digest),),
            )).fetchone()
            if row is None:
                raise BlobNotFoundError(ref.digest)
            content = row[0]  # already bytes from BYTEA
        actual_digest = BlobDigest(blake3(content).hexdigest())
        if actual_digest != ref.digest:
            raise BlobDigestMismatchError(expected=ref.digest, actual=actual_digest)
        self._cache[ref.digest] = content
        if len(self._cache) > self._lru_max:
            self._cache.popitem(last=False)
        return content
    ```
6. **Construction-site fence test (AC-4).** `tests/fence/test_blob_ref_construction.py` does a `grep -rn "BlobRef(" src/codegenie/`; allowlist: `src/codegenie/events/blob_refs.py` only (where the model is defined and `write` constructs). Anyone else constructing `BlobRef(...)` directly bypasses the smart-constructor invariant.
7. **Adversarial tamper test (AC-8)** — uses the `migrations_pool` fixture from S3-04 to UPDATE the `content` column; `resolve(ref)` raises.

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/integration/events/test_blob_ref_roundtrip.py`

Test intent: A 200 KiB byte string written via `_BlobStore.write` and read back via `_BlobStore.resolve` is byte-identical. The first failing assertion is on the `import codegenie.events.blob_refs` line.

```python
# Test outline only.
async def test_write_resolve_roundtrip(pg_pool, fresh_events_schema):
    """AC-3, AC-7 — write-then-resolve preserves bytes byte-identically.
    The canonical smoke for the smart-constructor + content-addressed store."""
    store = _BlobStore(pool=pg_pool)
    content = secrets.token_bytes(200 * 1024)  # 200 KiB random

    ref = await store.write(content, content_kind="context_bundle")
    assert ref.byte_len == len(content)
    assert ref.content_kind == "context_bundle"
    assert len(ref.digest) == 64
    assert all(c in "0123456789abcdef" for c in ref.digest)

    retrieved = await store.resolve(ref)
    assert retrieved == content
```

Why it fails: `codegenie.events.blob_refs` doesn't exist yet.

### Green — minimal pass

- Add `BlobRef`, `BlobKind`, `_BlobStore`, errors.
- The red test passes.

### Required follow-on tests (one per AC)

- **`test_blob_ref_is_frozen`** (AC-1) — mutation attempt raises; extra field at construction raises.
- **`test_dedup_via_on_conflict`** (AC-5) — write same bytes twice; assert 1 row in `events.blob_refs`.
- **`test_blob_kind_collision_raises`** (AC-6) — write content with `kind=A`; write same content with `kind=B`; second raises `BlobKindCollision`.
- **`test_resolve_detects_tamper`** (AC-8) — `migrations_pool` UPDATE `content`; resolve raises `BlobDigestMismatchError`.
- **`test_resolve_caches_hot_reads`** (AC-9) — first resolve hits PG; second resolve does NOT (patch the pool to assert).
- **`test_write_does_not_warm_cache`** (AC-10) — `write(content)`; immediately `resolve(ref)` — PG query observed.
- **`test_lru_evicts_at_capacity`** (AC-9 cont) — write 257 distinct blobs (smaller for test); first resolve of blob[0] hits PG (was evicted).
- **`test_digest_is_blake3_hex_64`** (AC-11) — content-addressed; `blake3(content).hexdigest() == ref.digest`.
- **`test_content_column_is_bytea`** (AC-12) — `pg_typeof((content)) = 'bytea'` for an inserted row.

### Fence test

`tests/fence/test_blob_ref_construction.py` (AC-4):

```python
import pathlib, re

ALLOWED_FILES = {"src/codegenie/events/blob_refs.py"}

def test_blob_ref_constructed_only_in_blob_refs_module():
    """ADR-0005 — smart-constructor discipline. Only `_BlobStore.write`
    is the legal path to producing a BlobRef in production code.
    If this fails, a contributor bypassed the smart constructor."""
    pattern = re.compile(r"BlobRef\s*\(")
    offenders = []
    for path in pathlib.Path("src/codegenie").rglob("*.py"):
        if str(path) in ALLOWED_FILES:
            continue
        text = path.read_text()
        if pattern.search(text):
            offenders.append(str(path))
    assert offenders == [], (
        f"BlobRef constructed outside the smart-constructor module: {offenders}. "
        f"Production code must obtain a BlobRef via _BlobStore.write."
    )
```

### Property test (Hypothesis)

`tests/property/test_blob_store_roundtrip.py` — Hypothesis generates byte sequences of length 1 KiB to 1 MiB; for each, write + resolve and assert byte-equality. Catches encoding bugs (UTF-8 vs binary), partial-read bugs, and dedup misbehavior.

### Refactor

- Module docstring on `blob_refs.py` cites ADR-0005 and names the smart-constructor discipline + the fence test path.
- `_BlobStore` is module-private; the test code imports it directly; production code goes through S4-02's `write_blob_ref` activity wrapper.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/events/blob_refs.py` | `BlobRef` model + `BlobKind` + `_BlobStore` class. |
| `src/codegenie/events/errors.py` | Add `BlobDigestMismatchError`, `BlobKindCollision`, `BlobNotFoundError`. |
| `tests/integration/events/test_blob_ref_roundtrip.py` | All integration tests. |
| `tests/fence/test_blob_ref_construction.py` | Smart-constructor fence. |
| `tests/property/test_blob_store_roundtrip.py` | Hypothesis property. |
| `tests/adv/test_blob_tamper_detection.py` | Adversarial tamper test (AC-8). |

## Out of scope

- **`write_blob_ref` / `resolve_blob_ref` Temporal activities** — handled by S4-02. This story ships the kernel `_BlobStore`; S4-02 wraps it with `@activity.defn`.
- **Activity-boundary sanitizer / `RedactedActivityResult.seal`** — S3-06.
- **G6 throughput bench for blob writes** — S3-07.
- **S3 / external blob store adapter** — out of scope for Phase 9. ADR-0005 §Consequences notes that if blob growth outgrows Postgres comfort (~Phase 16), a `BlobStoreAdapter` Protocol swap is additive; `BlobRef` shape is stable.
- **Compression of stored bytes** — not adopted. Postgres TOAST handles large `BYTEA` columns transparently; explicit compression is premature.
- **Blob garbage collection** — out of scope. Phase 9 keeps every blob forever. Phase 13+ may add a retention policy; the content-addressed store makes "drop unreferenced blobs" mechanical when needed.
- **Encryption-at-rest** — out of scope per ADR-0009 (no `pgcrypto`). Postgres disk encryption is the deployment-level concern.

## Notes for the implementer

### §1 — Smart-constructor is the load-bearing invariant

The grep-based fence test (AC-4) is the structural defense. Without it, a contributor could construct a `BlobRef(digest="deadbeef" * 8, ...)` referring to bytes that don't exist; downstream `resolve` would raise `BlobNotFoundError` but only at runtime when the activity that depends on the ref runs. The fence catches it at PR time.

Allowed construction sites:
1. `src/codegenie/events/blob_refs.py` — the model definition itself + `_BlobStore.write`.
2. `src/codegenie/durable/activities/write_blob_ref.py` (S4-02) — the activity wrapper. **Add to `ALLOWED_FILES` in the fence test when S4-02 lands.**

Test files are excluded by the grep pattern (`src/codegenie/` prefix only). Don't add a `# noqa` style escape hatch — a contributor who needs to construct a `BlobRef` outside the allowlist must either go through `_BlobStore.write` or add their file to the allowlist (which is a code-review signal).

### §2 — `BlobDigest` is hex `str`, NOT `bytes`

`BlobDigest = NewType("BlobDigest", str)` — the 64-char hex form. Reasons:
- JSON-serializable in workflow history (Temporal's payload codec handles str natively; bytes need base64).
- Human-readable in `temporal-ui` and `make blob-show DIGEST=...`.
- Equality compares are lexicographic — same result as byte-compare on hex.

Postgres `BYTEA` column stores 32 raw bytes (smaller); converting between hex and bytes happens at the boundary (`bytes.fromhex(digest)` / `row[0].hex()`).

### §3 — Cache invalidation is "never"

The LRU caches resolved bytes for a digest. Because the store is content-addressed and `events.blob_refs.digest` is the PRIMARY KEY, **a given digest's bytes can never change** legitimately. Adversarial tamper (via `migrations_role`) is the only failure mode, and the cache's existence may mask it (a cached resolve doesn't re-verify the digest).

**This is fine** because the chain at the event-log level (S3-04) catches tamper of `BlobRef` references inside events. The cache is a hot-path optimization for legitimate reads; the tamper-detection lives one layer up.

If a future story wants belt-and-suspenders cache-side tamper detection, it can verify on every cache hit. Don't pre-pay this here — the cost is 50-100 µs per resolve.

### §4 — `byte_len` is informational, not load-bearing

`BlobRef.byte_len` is the length of the stored content. It's surfaced for ergonomics (`temporal-ui` shows it; operators can sanity-check sizes). It's NOT a security boundary — a tampered row whose `content` is shorter than the original would be detected by the digest mismatch in `resolve`, not by `byte_len`.

### §5 — `ON CONFLICT DO NOTHING` is the dedup mechanism

The INSERT statement is `INSERT INTO events.blob_refs (digest, content, content_kind, byte_len) VALUES (...) ON CONFLICT (digest) DO NOTHING`. The PRIMARY KEY conflict path leaves the existing row untouched. After the INSERT, the read-back SELECT validates `content_kind` (AC-6) — a benign re-write of identical content with identical kind is a no-op; a re-write with a different `content_kind` raises `BlobKindCollision`.

The collision-raise path is what makes the dedup tradeoff loud: ADR-0005 §Tradeoffs accepts that "the threshold is a magic number; some payloads at 7.9 KiB would benefit from refs and won't get them" — but the converse (same bytes, different `content_kind` labels) is a bug we want to surface.

### §6 — Two-step write inside one transaction

The `INSERT ... ON CONFLICT DO NOTHING` followed by `SELECT content_kind ...` is inside one `conn.transaction()`. This avoids a race where:
1. Caller A inserts (digest, kind=context_bundle).
2. Caller A's transaction commits.
3. Caller B inserts (digest, kind=patch_diff) — `ON CONFLICT DO NOTHING` no-ops.
4. Caller B's SELECT reads `kind=context_bundle` (the database row).
5. Caller B raises `BlobKindCollision` (correct).

Without the transaction wrapping, an intermediate UPDATE by `migrations_role` could create false positives. The transaction guarantees the SELECT sees the same row the INSERT just attempted.

### §7 — Per-worker LRU memory budget

256 entries × ~50 KiB average bundle = ~12 MiB resident per worker. At 5 activity workers per node, ~60 MiB. Within the per-worker memory envelope (`phase-arch-design.md §Physical view`).

If the LRU starves under burst (many distinct bundles), `resolve` falls back to Postgres — correctness preserved, perf degraded. The G6 bench (S3-07) will surface a starved cache as a regression; the response is to raise `lru_max` for the workload.

### §8 — Not adopted (YAGNI)

- **A public `BlobStore` interface** — not adopted. `_BlobStore` is module-private; production code goes through S4-02's activities. If a future test or admin tool needs direct access, add an explicit `events.blob_refs.test_helpers` module.
- **Streaming write for very-large blobs** — not adopted. ADR-0005's 8 KiB threshold + Temporal's 2 MiB hard cap means most blobs are 50-200 KiB; streaming I/O complexity is unwarranted.
- **TTL on `events.blob_refs.created_at`** — not adopted. Blob retention is a Phase-13+ observability concern.
- **`md5`/`sha256` as alternatives** — explicitly not adopted; BLAKE3 is the codebase standard (per `tools/digests.yaml`).
- **Async-compatible LRU library (`asyncache.LRUCache`)** — not adopted. `OrderedDict` + `move_to_end` is sufficient inside the asyncio-single-threaded execution model.
