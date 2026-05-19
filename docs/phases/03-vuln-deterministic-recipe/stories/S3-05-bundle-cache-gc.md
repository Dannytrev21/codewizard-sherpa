# Story S3-05 — Bundle cache key (incl. `vuln_index.digest`) + `BundleCacheGc` + `codegenie cache prune` CLI (Gap 4 fix)

**Step:** Step 3 — TCCM, BundleBuilder, VulnIndex, content-addressed cache
**Status:** HARDENED
**Effort:** S
**Depends on:** S3-03 (VulnIndex.digest), S3-04 (Bundle shape)
**ADRs honored:**
- Phase 3 ADR-0008 — `vuln_index.digest` participates in Bundle cache key + Bundle cache **eviction policy** (Gap 4 origin); this story carries an additive amendment to ADR-0008 §Tradeoffs raising the Phase-3 env-var ceiling from two to three (`CODEGENIE_BUNDLE_CACHE_TTL_DAYS` joins `CODEGENIE_BUNDLE_CONCURRENCY` and `CODEGENIE_VULN_INDEX_PATH`).
- Phase 3 ADR-0005 — two-stream `EventLog` taxonomy; `CacheGcCompleted` is a spanning event.
- Phase 3 ADR-0010 — domain-modeling discipline (frozen Pydantic error models, `Literal[...]` closed sets, smart-constructor newtypes; `match` + `assert_never` at dispatch sites).
- Phase 0 ADR-0001 — hashing chokepoint (all BLAKE3 routes through `codegenie.hashing`; this story takes a hard dependency).
- Phase 0 ADR-0011 — cache-permission discipline (`0o700` directories, `0o600` files, `os.replace` for cross-platform atomic rename).
- Phase 3 phase-arch-design §C9 — additive edit lands `"cache_gc_completed"` in `WorkflowSpanningEvent.event_type` Literal.

## Validation notes (2026-05-18)

`/phase-story-validator` ran four critics; no `NEEDS RESEARCH` findings. Verdict: **HARDENED**. Summary of edits (full audit at `_validation/S3-05-bundle-cache-gc.md`):

- **C-A (block).** `BundleCacheError` was specified "markers-only" yet constructed with a `reason=` kwarg — `TypeError` at runtime. Adopted S3-01 / S3-04 precedent: frozen Pydantic `BundleCacheErrorModel(BaseModel)` carrying `reason: Literal[...]` + `details`; thin `BundleCacheRaise(CodegenieError)` exception wraps and is the raise surface.
- **C-B (block).** `SemverVersion` newtype does not exist in `codegenie.types.identifiers`. Downgraded `plugin_version` to `str` for this story; surfaced the S1-01-amendment opportunity in Notes (mirrors S3-04's `CanonicalArgsJson` deferral — rule-of-three not yet met).
- **C-D (block).** `bytes_hash` is not in `codegenie.hashing`. Pinned to `codegenie.hashing.content_hash_bytes` (already prefix-tagged `blake3:`). The double-`"blake3:"` bug in the original outline pseudocode is fixed.
- **C-G (block).** `WorkflowSpanningEvent.event_type` Literal at `phase-arch-design.md:872` does NOT yet include `"cache_gc_completed"`. This story carries an **additive** edit landing the variant (arch line 1077 already authorises additive extension of the union). The CLI integration test is bound to a pinned interim wire format (single-line append to `.codegenie/events/spanning/append.jsonl`, uncompressed) that S6-01 absorbs into the chained zstd format additively.
- **C-E (harden).** Replaced every `os.rename` with `os.replace` (`src/codegenie/cache/store.py:135` precedent; cross-platform atomic overwrite).
- **C-H (harden).** Dropped `fcntl.flock` from `BundleCacheStore.put` — Bundle blobs are content-addressed; two writers of the same key write identical bytes; `_atomic_write_bytes` alone matches the Phase-0 cache-store discipline.
- **C-L / F10 (block).** Existing `@cli.group("cache")` + `cache gc` Phase-1+ stub at `cli.py:898-912` is preserved bytes-for-bytes; `cache prune` is added as a sibling subcommand. Regression test pins the `cache.gc.stub` log line.
- **Coverage F2 + Test-Quality TQ1.** The participation parametrize was mutating each input by appending `"x"`, which a buggy implementation that omits `vuln_index_digest` could survive. Replaced with **same-length, distinct-equivalence-class** mutations + a positive **declared-order byte-layout** assertion (`compose_bundle_cache_key(...) == content_hash_bytes(declared_order_concat)`) + a **boundary-shift collision** test (separator integrity).
- **F4 (harden).** Separator-poisoning defense: composer rejects any input containing `\x1f` with `BundleCacheRaise(BundleCacheErrorModel(reason="separator_in_input"))`.
- **F5 + TQ4 (harden).** `BundleCacheStore` ACs now pin (a) mode `0o600` files / `0o700` dirs, (b) key validation `^blake3:[0-9a-f]{64}$` (path-traversal defense), (c) idempotent puts, (d) atomic-write no-residual-tmp.
- **F6 + TQ7 (harden).** GC edge cases AC-fenced: missing `bundles/` returns `entries_evicted=0`; non-hex filenames + `.lock` + `.gc-stamp` + dotfiles + symlinks + subdirectories are NOT touched; **strict `<` comparison at the TTL boundary** is pinned by an exact-7-days-old-is-kept test.
- **F8 + C-M (harden).** Added orchestrator-path event-emission AC: `BundleCacheGc(...).run()` with `event_emitter=spy` calls `spy` exactly once; `run_amortized()` on the no-op branch calls `spy` zero times. Closes the symmetry with the CLI test.
- **F9 (harden).** `.gc-stamp` failure-mode ACs: missing → treated as `0.0` (run + write); unparseable → `BundleCacheRaise(reason="corrupt_gc_stamp")`; future-dated → treated as stale (run + rewrite to `time.time()`); concurrent callers serialized via `fcntl.flock(LOCK_EX)` on `<cache_dir>/.gc-stamp.lock` (this is the one place `flock` is justified — race target is `.gc-stamp`, not blobs).
- **F11 (harden).** `capture_spanning_events` fixture binding pinned: defined in `tests/integration/cli/conftest.py`, reads `<cache_dir>/../events/spanning/append.jsonl` and decodes each line into `CacheGcCompletedEvent`.
- **F12 (nit).** AC4's self-contradiction fixed (`def compose_bundle_cache_key(*, ...)` makes positional call a `TypeError` — pinned).
- **F13 + TQ12 (harden).** TTL env now parametrized over multiple `(ttl_days, age_days, expected_evicted)` rows + a reject corpus (`""`, `"0"`, `"-1"`, `"7.5"`, `"not-an-int"`, `"  "`, `"1e2"`, `"0x7"`).
- **TQ3 (block).** `bytes_reclaimed` accounting tightened to **exact equality** against `sum(stat().st_size before unlink)`. A mutant returning a constant or `len(evicted)` is now caught.
- **TQ5 (block).** `corrupt-on-read does NOT delete the file` AC pinned (operators must be able to inspect).
- **TQ8 (harden).** Recursive-monkeypatch bug in `test_24h_elapsed_runs_again` fixed (capture `real_time` reference; monkeypatch `codegenie.plugins.cache_gc.time.time` not global `time.time`).
- **TQ9 + TQ13.** `.gc-stamp` mtime is asserted to lie between two real-clock snapshots; the test honestly documents that point-in-time atomicity (no interleaved-reader thread) is the limit.
- **TQ10 (harden).** Empty-cache CLI test added — exactly-one event with `entries_evicted=0`.
- **TQ11.** `args_canonical` passthrough-verbatim test added (composer is NOT a re-canonicalizer).
- **TQ16.** AST chokepoint test added: neither `plugins/cache.py` nor `plugins/cache_gc.py` may `import blake3` directly.
- **TQ17.** Determinism test runs N=100 (catches an impl that reads `os.urandom`).
- **DP1.** Env read moves from `__init__` to `run()` (S3-02's `_parse_max_age_seconds` precedent). Constructor accepts optional `ttl_seconds: int | None = None`; `None` → read env at `run()`.
- **DP2.** Pure module-level helpers extracted + Hypothesis property-tested + an AST purity test fences them against `os.`, `Path.`, `time.`, `os.environ` references (mirrors S3-04 AC-27/28).
- **DP3.** `cache_dir: SandboxedPath` (matches S3-04's §C4 alignment); `__annotations__` test pins it.
- **DP6.** `BundleCacheKey = NewType("BundleCacheKey", str)` added to `codegenie.types.identifiers` (rule-of-three met: composer + `put` + `get`); construction funneled through `compose_bundle_cache_key`.
- **DP10.** `CacheGcCompletedEvent` gains `wall_clock_iso: str` (RFC3339 UTC) and `duration_ms: int` (monotonic delta) — Phase 9 latency correlation.
- **DP12.** `CacheGcCompletedEvent.from_result(result, *, trigger, wall_clock_iso, duration_ms)` classmethod + a drift canary test (`CacheGcResult` field names ⊆ `CacheGcCompletedEvent` field names).
- **C-N.** `Bundle` JSON-roundtrip canary test landed here (5 lines): `Bundle.model_validate_json(b.model_dump_json()) == b` including the `tuple[BundleEntry, ...]` field; if it fails, S3-04 implementer normalizes to `list` and S3-05 is unblocked. Does NOT defer to S6-04 — the boundary lives here.

The story is now ready for `phase-story-executor`. The four veto-strength invariants — (1) ADR-0008 cache-key correctness, (2) no direct `blake3` import, (3) strict-`<` TTL boundary, (4) exactly-one-event per `run()` — each have at least one AC + at least one mutation-resistant test or structural defense.

## Context

This story is **the Gap 4 fix from `phase-arch-design.md §Gap analysis`** — the synthesis under-specified Bundle cache eviction ("GC after 7 days mtime" was named but no component owned the mechanism). At portfolio scale (Phase 10) an un-GC'd cache becomes load-bearing; at Phase 3 it's a slow leak but a real one (~50 KB/Bundle × thousands of warm workflows).

This story ships three pieces tied together:

1. **`compose_bundle_cache_key`** — the pure BLAKE3 composer that **must** include `vuln_index.digest` (ADR-0008 — a CVE-feed refresh that re-classifies a CVE MUST NOT return a stale cache hit). Routes through `codegenie.hashing.content_hash_bytes` (ADR-0001 chokepoint).
2. **`BundleCacheStore`** — the on-disk put/get pair (sibling of the Phase-0 probe-cache store), content-addressed, atomic-rename, `0o600`/`0o700` mode discipline, no `flock` on blobs.
3. **`BundleCacheGc` + `codegenie cache prune` CLI** — the once-a-day amortized eviction helper (`.gc-stamp` carries the last-run timestamp) and the operator-facing CLI that calls the same helper unconditionally and emits exactly one `CacheGcCompletedEvent` spanning event with `entries_evicted`, `bytes_reclaimed`, `wall_clock_iso`, `duration_ms`, and `trigger ∈ {"amortized", "operator_cli"}`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis #4 — BundleBuilder cache eviction has no specified GC policy` (lines ~1168–1172) — the gap and the improvement spec. **This story IS the fix.**
  - `../phase-arch-design.md §C7. BundleBuilder` (lines ~588–606) — cache key shape.
  - `../phase-arch-design.md §C9. EventLog` (lines ~637–665) — spanning-event union shape. **The story carries an additive edit to line 872 landing `"cache_gc_completed"` in the Literal.**

- **Phase ADRs (load-bearing):**
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md §Decision` — the cache key MUST include `vuln_index.digest`; this story ships the composer. **§Tradeoffs (line 48) is amended additively to enumerate three Phase-3 env vars.**
  - `../ADRs/0005-two-stream-event-log-per-adr-0034.md` — spanning-stream taxonomy.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — frozen Pydantic error models, `Literal` closed sets, `BlobDigest`/`PluginId`/`PrimitiveName` newtypes, `match` + `assert_never` at dispatch.

- **Cross-phase ADRs:**
  - `../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md` — BLAKE3 chokepoint; **no direct `blake3` import** outside `codegenie.hashing`.
  - `../../00-bullet-tracer-foundations/ADRs/0011-cache-permissions-and-actions-cache-survival.md` — `0o700`/`0o600` mode discipline; `_reapply_modes` walker.

- **Implementation plan:**
  - `../High-level-impl.md §Step 3` — features delivered + done criterion ("`codegenie cache prune` exits 0 and emits one `CacheGcCompleted` spanning event").

- **Existing code (read; cite line numbers; do NOT edit unless explicitly named):**
  - `src/codegenie/hashing.py` lines 38–95 — public surface: `content_hash`, `content_hash_bytes`, `content_hash_fd`, `content_hash_of_inputs`, `identity_hash`, `identity_hash_bytes`. **Use `content_hash_bytes` for the composer payload.**
  - `src/codegenie/cache/store.py` lines 118–168 — `_atomic_write_bytes` (`<dest>.tmp` + fsync + `os.replace`) and `_reapply_modes` walker. Reuse the pattern; do **NOT** edit `cache/store.py`.
  - `src/codegenie/cache/keys.py` — Phase 0/2 per-probe cache key derivation. **Do NOT edit** — Bundle cache is a sibling concept; read for the `\x1f` separator convention only.
  - `src/codegenie/cli.py` lines 898–912 — `@cli.group(name="cache")` and `@cache.command(name="gc")` Phase-1+ stub. **Already exists.** Add `cache prune` as a sibling under the same group; do NOT redeclare the group; do NOT touch `cache_gc`.
  - `src/codegenie/types/identifiers.py` lines 54–83 — newtype catalog. **Add `BundleCacheKey` here** (one line; smart-constructed by `compose_bundle_cache_key`).
  - `src/codegenie/transforms/_forward.py` — `SandboxedPath` alias (S3-04 already uses it; mirror).
  - `src/codegenie/errors.py` lines 21–183 — `CodegenieError` is markers-only; subclasses carry no state. Pattern for typed errors: frozen Pydantic `BaseModel` (the value) + thin `*Raise(CodegenieError)` exception (the carrier). See `S3-01 §AC-4` and the S3-04 validation report §C5 for two prior precedents.
  - `src/codegenie/plugins/bundle.py` (S3-04) — `Bundle` instances are the cached values.
  - `src/codegenie/vuln_index/index.py` (S3-02) — `VulnIndex.digest` returns `BlobDigest("blake3:...")`; this story **consumes** that value (the composer is decoupled from S3-02 implementation).

- **Validation precedents:**
  - `_validation/S3-01-tccm-context-query-models.md` — `TCCMParseError` shape.
  - `_validation/S3-04-bundle-builder-serial-fallback.md` — `BundleBuilderError` (Pydantic + thin Exception wrapper); `cache_dir: SandboxedPath`; pure-helper + AST purity test precedent; `CanonicalArgsJson` deferral.

## Goal

`codegenie.plugins.cache` exposes:

- A pure `compose_bundle_cache_key(*, plugin_id, plugin_version, primitive, args_canonical, repo_ctx_digest, scip_digest, dep_graph_digest, vuln_index_digest) -> BundleCacheKey` that BLAKE3-hashes the eight inputs in **declared positional order** separated by `\x1f`, routes through `codegenie.hashing.content_hash_bytes`, rejects inputs containing the `\x1f` separator, and returns a smart-constructed `BundleCacheKey` newtype (`"blake3:<64-hex>"`).
- A `BundleCacheStore` (`SandboxedPath`-rooted, atomic `<dest>.tmp + fsync + os.replace`, `0o600` files / `0o700` dirs, no `flock` on blobs) that round-trips `Bundle` Pydantic values keyed by `BundleCacheKey`, rejects malformed keys (defense against path-traversal in the filename derivation), is idempotent on identical-content puts, and on corrupt-on-read returns `None` + a structured `cache.bundle.corrupt` warn event **without deleting the file**.

`codegenie.plugins.cache_gc` exposes:

- `BundleCacheGc(cache_dir: SandboxedPath, *, ttl_seconds: int | None = None, event_emitter: Callable[[CacheGcCompletedEvent], None] | None = None)` whose `__init__` does **no I/O and no env read** (DP1).
- `.run() -> CacheGcResult` walks `<cache_dir>/bundles/*.json`, evicts entries with `_is_evictable(now, mtime, ttl_seconds)` true (strict `<` boundary), returns a `CacheGcResult(entries_evicted, bytes_reclaimed, cache_dir, ttl_days, duration_ms, wall_clock_iso)`, and (if `event_emitter` is provided) calls it **exactly once** with a `CacheGcCompletedEvent(trigger="amortized")`.
- `.run_amortized() -> CacheGcResult | None` consults `<cache_dir>/.gc-stamp` (with `fcntl.flock` on `<cache_dir>/.gc-stamp.lock`), returns `None` if `_should_run_amortized(now, last_stamp, 86400)` is false, otherwise calls `.run()`, atomically updates `.gc-stamp` (`<dest>.tmp` + `os.replace`), and returns the result.

`codegenie cache prune [--cache-dir PATH]` is added under the existing `@cli.group("cache")` (sibling of the Phase-1+ `cache gc` stub, which is preserved bytes-for-bytes). It calls `BundleCacheGc(...).run()` unconditionally and emits **exactly one** `CacheGcCompletedEvent(trigger="operator_cli")` — even when nothing was evicted — to `.codegenie/events/spanning/append.jsonl` (interim wire format; S6-01 absorbs into the chained zstd file additively). Exits `0` on success.

Three veto-strength invariants are AC-fenced: (a) the cache key MUST include `vuln_index_digest` (ADR-0008 correctness; mutation-resistant test); (b) hashing routes through `codegenie.hashing` (ADR-0001 chokepoint; AST test); (c) `CacheGcCompletedEvent` emission is **exactly once** per `.run()` invocation (operator + spanning-stream integrity).

## Acceptance criteria

### Module + types

- [ ] **AC-1.** New module `src/codegenie/plugins/cache.py` exports exactly `compose_bundle_cache_key`, `BundleCacheStore`, `BundleCacheErrorModel`, `BundleCacheRaise`, `BundleCacheKey` (re-exported from `codegenie.types.identifiers`). `__all__` is a sorted tuple containing exactly these names (set equality, not superset). Module docstring cites ADR-0008 §Decision (`vuln_index.digest` in cache key), ADR-0001 (hashing chokepoint), and the Gap 4 origin in arch §Gap analysis #4.
- [ ] **AC-2.** New module `src/codegenie/plugins/cache_gc.py` exports exactly `BundleCacheGc`, `CacheGcResult`, `CacheGcCompletedEvent`. Module docstring cites Gap 4 explicitly: "This module IS the Gap 4 fix from `docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md §Gap analysis`."
- [ ] **AC-3.** `BundleCacheErrorModel` is a frozen Pydantic `BaseModel` (`model_config = ConfigDict(frozen=True, extra="forbid")`) with `reason: Literal["invalid_ttl_env", "separator_in_input", "invalid_key", "corrupt_gc_stamp"]` (closed set; additions require an ADR amendment) and `details: dict[str, str | int] = {}`. `BundleCacheRaise(CodegenieError)` is the raise surface: `__init__(self, model: BundleCacheErrorModel) -> None`; `self.model` carries the typed value. Mirrors S3-01 `TCCMParseError` + S3-04 `BundleBuilderRaise`.
- [ ] **AC-4.** `BundleCacheKey = NewType("BundleCacheKey", str)` lands in `src/codegenie/types/identifiers.py`. Module docstring documents the smart-constructor convention: construction is funneled through `compose_bundle_cache_key`; direct `BundleCacheKey(...)` calls outside the composer are forbidden by an AST test.
- [ ] **AC-5.** `plugin_version: str` (NOT a `SemverVersion` newtype — the newtype does not yet exist in `codegenie.types.identifiers`; deferred to a future S1-01 amendment; see Notes-for-implementer DP-B). All other identifiers use their existing newtypes: `PluginId`, `PrimitiveName`, `BlobDigest`.

### Cache key composer

- [ ] **AC-6.** `def compose_bundle_cache_key(*, plugin_id: PluginId, plugin_version: str, primitive: PrimitiveName, args_canonical: str, repo_ctx_digest: BlobDigest, scip_digest: BlobDigest, dep_graph_digest: BlobDigest, vuln_index_digest: BlobDigest) -> BundleCacheKey`. **All eight kwargs are required (no defaults).** Signature is keyword-only (`*` after `self`-less definition); passing any input positionally raises `TypeError` at the call site (unit-tested).
- [ ] **AC-7. Declared-order byte layout (TQ1, mutation-resistant).** Inputs are concatenated in this exact order: `plugin_id`, `plugin_version`, `primitive`, `args_canonical`, `repo_ctx_digest`, `scip_digest`, `dep_graph_digest`, `vuln_index_digest`, joined by `"\x1f"` (matching `codegenie.hashing._UNIT_SEP`). The result is `codegenie.hashing.content_hash_bytes(payload_bytes)` — already prefix-tagged `"blake3:"` (do NOT double-prefix). A unit test pins the on-the-wire layout by computing the expected hash with `content_hash_bytes` on a hand-built payload and asserting equality.
- [ ] **AC-8. Mutation-resistant participation (ADR-0008 correctness).** Holding the other seven inputs constant and varying ONLY `vuln_index_digest` to a **same-length, distinct-equivalence-class** value (`"blake3:" + "a"*64` → `"blake3:" + "b"*64`) produces a different key. Parametrize covers each of the 8 inputs; each row uses an equally-long substitute. An implementation that omits any one input from the concatenation MUST fail this parametrize.
- [ ] **AC-9. Boundary-shift collision defense.** `compose_bundle_cache_key(plugin_id="ab", plugin_version="c", ...rest_pinned) != compose_bundle_cache_key(plugin_id="a", plugin_version="bc", ...rest_pinned)`. The `\x1f` separator is what defuses this; the test pins it. (Mirrors `identity_hash`'s arity-byte witness rationale at `hashing.py:84-95`.)
- [ ] **AC-10. Separator-poisoning defense.** Any kwarg whose value contains `"\x1f"` raises `BundleCacheRaise(BundleCacheErrorModel(reason="separator_in_input", details={"input": <kwarg-name>}))`. Parametrize covers all 8 inputs each carrying an embedded `\x1f`.
- [ ] **AC-11. Determinism (N=100).** Two-hundred calls with byte-identical kwargs return one unique key (`len({compose_bundle_cache_key(**kw) for _ in range(100)}) == 1`). Defends against a mutant that reads `os.urandom` or `time.time`.
- [ ] **AC-12. `args_canonical` is opaque to the composer.** Two semantically-equivalent JSON strings differing only in whitespace produce DIFFERENT keys (`'{"a":1}'` vs `'{"a": 1}'`). The composer does NOT re-canonicalize; caller owns canonicalization (`json.dumps(..., sort_keys=True, separators=(',', ':'), ensure_ascii=False)` is the canonical caller form, documented in the module docstring and S3-04's adjacent canonicalizer).
- [ ] **AC-13. Hashing chokepoint (AST).** A unit test `tests/unit/plugins/test_cache_no_blake3_import.py` AST-walks both `src/codegenie/plugins/cache.py` and `src/codegenie/plugins/cache_gc.py`; asserts neither contains `import blake3` nor `from blake3 import …`. ADR-0001 chokepoint.

### BundleCacheStore

- [ ] **AC-14.** `class BundleCacheStore: def __init__(self, cache_dir: SandboxedPath) -> None`. `__annotations__["cache_dir"] is SandboxedPath` (matches S3-04's §C4 alignment; static test pins it). On-disk layout: `<cache_dir>/bundles/<64-hex>.json`. The `blake3:` prefix lives ONLY in the `BundleCacheKey` string, NOT in the filename (Windows-clean even though Phase 3 is Linux/macOS).
- [ ] **AC-15. Key validation.** `put` / `get` reject any key that does not match `^blake3:[0-9a-f]{64}$` with `BundleCacheRaise(BundleCacheErrorModel(reason="invalid_key", details={"key_prefix": key[:16]}))`. Defends against path-traversal in the filename derivation (`"blake3:../../etc/passwd"` is rejected). Test parametrizes over a corpus of malformed keys.
- [ ] **AC-16. Atomic, mode-disciplined `put`.** `put(key: BundleCacheKey, bundle: Bundle) -> None` writes via `<dest>.tmp` + `fsync` + `os.replace` (Phase-0 `_atomic_write_bytes` precedent at `cache/store.py:118-135`). NO `fcntl.flock` on the blob (content-addressed; concurrent writers of the same key write identical bytes — Phase-0 cache-store discipline). File mode is `0o600`; the `<cache_dir>/bundles/` directory is created with mode `0o700` if absent. After put, no `.tmp` residue exists in `<cache_dir>/bundles/`.
- [ ] **AC-17. Idempotent puts.** Writing the same `(key, bundle)` twice succeeds and leaves a single file with byte-identical content. Writing the same key with a different `Bundle` is a clean overwrite (no exception); the resulting file is the second `Bundle`'s serialization.
- [ ] **AC-18. `get` semantics.** Lock-free read. Returns `Bundle.model_validate_json(<file-bytes>)` on success; returns `None` on missing file or missing `cache_dir`/`bundles/` directory. On `pydantic.ValidationError` or `json.JSONDecodeError`, returns `None` + emits a structured `cache.bundle.corrupt` warn event (structlog); **the file is NOT deleted** (operator inspection). The post-corrupt-read existence assertion is part of the test (`corrupt_path.exists()`).
- [ ] **AC-19. `Bundle` JSON-roundtrip canary.** A unit test under `tests/unit/plugins/test_bundle_cache_store.py` asserts `Bundle.model_validate_json(b.model_dump_json()) == b` for a `Bundle` populated with non-empty `tuple[BundleEntry, ...]` (the field S3-04 ships). If this fails, S3-04 normalizes its container type to `list[BundleEntry]` and S3-05 is unblocked; either way the boundary lives here, not at S6-04.

### Result + event models

- [ ] **AC-20.** `class CacheGcResult(BaseModel)`: `model_config = ConfigDict(frozen=True, extra="forbid")`; fields: `entries_evicted: int`, `bytes_reclaimed: int`, `cache_dir: SandboxedPath`, `ttl_days: int`, `duration_ms: int`, `wall_clock_iso: str`. `@field_serializer("cache_dir")` emits the string form for JSON payloads.
- [ ] **AC-21.** `class CacheGcCompletedEvent(BaseModel)`: `model_config = ConfigDict(frozen=True, extra="forbid")`; fields: `event_type: Literal["cache_gc_completed"]`, `cache_dir: str`, `entries_evicted: int`, `bytes_reclaimed: int`, `ttl_days: int`, `duration_ms: int`, `wall_clock_iso: str` (RFC3339 UTC, e.g. `"2026-05-18T12:34:56.789Z"`), `trigger: Literal["amortized", "operator_cli"]`.
- [ ] **AC-22. Drift canary + classmethod constructor (DP12).** `CacheGcCompletedEvent.from_result(result: CacheGcResult, *, trigger: Literal["amortized", "operator_cli"]) -> CacheGcCompletedEvent` reuses the result's `entries_evicted`, `bytes_reclaimed`, `ttl_days`, `duration_ms`, `wall_clock_iso`, and stringifies `cache_dir`. A unit test asserts the field-name set relationship `{f.name for f in CacheGcResult.model_fields.values()} - {"cache_dir"} ⊆ {f.name for f in CacheGcCompletedEvent.model_fields.values()}` — drift canary.
- [ ] **AC-23. Additive arch edit.** `docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md` §C9 `WorkflowSpanningEvent.event_type` Literal at line ~872 is amended **additively** to include `"cache_gc_completed"`. Cite the arch authority for additive extension (arch line ~1077). A `grep` test or similar can confirm the literal lands; minimum bar is a docs build that doesn't break (`make docs`).

### BundleCacheGc — pure helpers + run + amortization

- [ ] **AC-24. Pure helpers (functional core, DP2).** `src/codegenie/plugins/cache_gc.py` exposes three module-private pure helpers, each unit-tested with Hypothesis:
  - `_parse_ttl_seconds(env: Mapping[str, str]) -> int` — reads `env.get("CODEGENIE_BUNDLE_CACHE_TTL_DAYS", "7")`, strips whitespace, decimal-int only; raises `BundleCacheRaise(BundleCacheErrorModel(reason="invalid_ttl_env", details={"value": <raw>}))` on anything else; multiplies by 86400. Mirrors S3-02's `_parse_max_age_seconds`.
  - `_is_evictable(now: float, mtime: float, ttl_seconds: int) -> bool` — returns `(now - mtime) > ttl_seconds`. **Strict `>` boundary** (matches arch §Gap-4 prose `mtime > 7 days`). Metamorphic Hypothesis property: older entries are always at-least-as-evictable as newer ones.
  - `_should_run_amortized(now: float, last_stamp: float, interval_seconds: int) -> bool` — returns `True` iff `(now - last_stamp) >= interval_seconds` OR `last_stamp > now` (clock-skew resilience: future-dated stamp is treated as stale).
- [ ] **AC-25. AST purity test (DP2, S3-04 AC-27 precedent).** `tests/unit/plugins/test_cache_gc_purity.py` AST-walks `src/codegenie/plugins/cache_gc.py` and asserts that the bodies of `_parse_ttl_seconds`, `_is_evictable`, and `_should_run_amortized` contain no `ast.Attribute` references whose root name is `os`, `Path`, `time`, or `structlog`, and no `import` statements naming those modules at function scope. Fences the pure-impure split.
- [ ] **AC-26. Constructor does no I/O.** `BundleCacheGc.__init__(self, cache_dir: SandboxedPath, *, ttl_seconds: int | None = None, event_emitter: Callable[[CacheGcCompletedEvent], None] | None = None) -> None` does NOT read the filesystem or the environment; constructor with invalid env still succeeds. A unit test monkeypatches env to a malformed value, constructs the GC successfully, and asserts that only `.run()` (or `.run_amortized()` on the elapsed branch) raises `BundleCacheRaise(reason="invalid_ttl_env")`. (DP1.)
- [ ] **AC-27. `run()` semantics.** `def run(self) -> CacheGcResult`: walks `<cache_dir>/bundles/`, considers only files matching `^[0-9a-f]{64}\.json$` (regex-anchored), reads `Path.stat().st_size` **before** `Path.unlink()`, counts bytes cumulatively, returns `CacheGcResult` with `duration_ms` from `time.monotonic_ns()` delta and `wall_clock_iso` from `datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")`. NEVER deletes `.lock`, `.gc-stamp`, dotfiles, subdirectories, symlinks (uses `Path.is_file()` + `not Path.is_symlink()` check), or any non-hex filename.
- [ ] **AC-28. Empty / missing inputs.** `run()` on a `cache_dir` where `bundles/` does NOT exist returns `CacheGcResult(entries_evicted=0, bytes_reclaimed=0, ...)` WITHOUT raising. `run()` on an EMPTY `bundles/` directory returns `entries_evicted=0` likewise.
- [ ] **AC-29. TTL boundary (TQ7).** With `ttl_seconds=7*86400`, an entry whose `mtime` is exactly `now - 7*86400` is **kept** (strict `>` test). An entry at `now - 7*86400 - 1` is evicted. Pinned by a dedicated test, not a mutated parametrize row.
- [ ] **AC-30. `bytes_reclaimed` exact accounting (TQ3).** `result.bytes_reclaimed == sum(<size of each evicted file>) measured before unlink`. Test writes a multi-byte file of known size and asserts exact equality (not `>= n`).
- [ ] **AC-31. TTL env parametrize (F13 + TQ12).**
  - Accept corpus: `{"7", " 7 ", "7\n", "1", "30", "365"}` (all decimal-int after strip; success).
  - **Reject corpus:** `{"", "0", "-1", "7.5", "+7", "not-an-int", "  ", "1e2", "0x7"}` — each raises `BundleCacheRaise(BundleCacheErrorModel(reason="invalid_ttl_env", details={"value": raw}))`.
  - Combined (ttl, age, evicted) parametrize: `{(7, 8, True), (7, 6, False), (7, 7, False), (1, 2, True), (1, 0.5, False), (30, 8, False)}`. Each row sets `CODEGENIE_BUNDLE_CACHE_TTL_DAYS` and asserts eviction iff `age_days > ttl_days`.
- [ ] **AC-32. Event emission (exactly-once, both triggers).** `BundleCacheGc(cache_dir, event_emitter=spy).run()` calls `spy` **exactly once** with a `CacheGcCompletedEvent(trigger="amortized")`. `BundleCacheGc(cache_dir, event_emitter=spy).run_amortized()` on the elapsed branch calls `spy` exactly once with `trigger="amortized"`. On the no-op branch (within 24h), `spy` is NOT invoked. `run()` with `event_emitter=None` emits zero events. A unit test uses a recording fake emitter.
- [ ] **AC-33. Emitter exceptions surface (fail-loud).** If `event_emitter` raises, the exception propagates out of `run()` (no swallow). Mirrors S3-04 AC-21.

### `.gc-stamp` semantics

- [ ] **AC-34. `.gc-stamp` location.** Lives at `<cache_dir>/.gc-stamp` (sibling of `bundles/`, NOT inside it). Pinned by an explicit `assert (cache_dir / ".gc-stamp").exists()` test after the first `run_amortized()` call.
- [ ] **AC-35. Atomic write.** `.gc-stamp` content is the float-as-text wall-clock seconds. Write via `<cache_dir>/.gc-stamp.tmp` + `fsync` + `os.replace` (NOT `os.rename`; cross-platform discipline per Phase-0 cache-store at `cache/store.py:135`). Test asserts `.gc-stamp.tmp` does NOT exist after a successful run and the content parses cleanly as a `float`.
- [ ] **AC-36. Missing `.gc-stamp` → run + write.** First-time invocation (no `.gc-stamp` present) runs the GC and writes the stamp. `_should_run_amortized(now, last_stamp=0.0, 86400)` returns `True` by construction.
- [ ] **AC-37. Corrupt `.gc-stamp` → fail loud.** Content that cannot be parsed as `float` raises `BundleCacheRaise(BundleCacheErrorModel(reason="corrupt_gc_stamp", details={"content": <first 32 chars>}))`. Rule 12 — operators want to know.
- [ ] **AC-38. Future-dated `.gc-stamp` → treated as stale.** If `last_stamp > now` (clock skew or tampering), `run_amortized()` still runs and rewrites the stamp to `time.time()`. Pinned by a test that writes `.gc-stamp` with `str(time.time() + 86400)`.
- [ ] **AC-39. Concurrent callers serialized.** `run_amortized()` acquires `fcntl.flock(LOCK_EX)` on `<cache_dir>/.gc-stamp.lock` for the read-stamp / decide / write-stamp critical section. Two-threaded test: both threads call `run_amortized()` concurrently; exactly one runs the GC (sees `_should_run_amortized = True`); the other sees the updated stamp and no-ops. NOTE: this is the only `flock` in the story (the blob store deliberately uses `os.replace` alone — see AC-16).
- [ ] **AC-40. 24h-elapsed branch (TQ8 — recursion fix).** Test captures `real_time = time.time` reference BEFORE monkeypatching; monkeypatches `codegenie.plugins.cache_gc.time.time` (NOT global `time.time`) to a lambda returning `t0 + 86401`; asserts `gc.run_amortized()` returns non-`None` on the second call AND `float(.gc-stamp.read_text()) > stamp_before` (proves the stamp write happened, not just that `run` returned).
- [ ] **AC-41. Within-24h no-op (TQ9).** Test bounds: first call returns non-`None`; capture `t_before` / `t_after` snapshots of real clock around the two calls; assert the second call returns `None` AND `t_before <= float(.gc-stamp.read_text()) <= t_after` (stamp was written to roughly `time.time()`).

### CLI

- [ ] **AC-42. `cache prune` subcommand under existing group (C-L).** `src/codegenie/cli.py` adds `@cache.command(name="prune")` under the existing `@cli.group(name="cache")` at line 898. **The existing `cache_gc` function at line 903 is preserved bytes-for-bytes.** A regression test invokes `runner.invoke(cli, ["cache", "gc"])` and asserts exit code 0 + a structlog event with `event="cache.gc.stub"` is emitted (Phase-1+ migration contract).
- [ ] **AC-43. Flag surface.** `cache prune [--cache-dir PATH]`. Default `--cache-dir` is `<cwd>/.codegenie/cache`. Invoking `--help` returns exit code 0 and prints the flag.
- [ ] **AC-44. Exactly-one event, including empty (F8 + TQ10).** Integration test under `tests/integration/cli/test_cache_prune.py`: parametrizes (populated cache with stale entry / empty cache); BOTH cases produce exit code 0 AND `len(decoded_events) == 1` AND `decoded_events[0].trigger == "operator_cli"` AND `decoded_events[0].event_type == "cache_gc_completed"`. Empty-cache row asserts `entries_evicted == 0 and bytes_reclaimed == 0`.
- [ ] **AC-45. Interim event-emission substrate (C-G).** The CLI emits to `<cache_dir>/../events/spanning/append.jsonl` (uncompressed, one JSON document per line, append-only). Each line is `json.dumps(event.model_dump(), separators=(',', ':'), sort_keys=True)`. The file is created with mode `0o600` and its parent dir with `0o700` if absent. **S6-01 absorbs this file additively into the chained zstd format**; do NOT pre-implement the chain here.
- [ ] **AC-46. `capture_spanning_events` fixture (F11).** Defined in `tests/integration/cli/conftest.py`. Reads `<cache_dir>/../events/spanning/append.jsonl` after CLI exit; returns `list[CacheGcCompletedEvent]` decoded via `CacheGcCompletedEvent.model_validate_json` on each line. Fixture docstring records the interim-wire-format contract per AC-45.

### ADR amendments

- [ ] **AC-47. ADR-0008 §Tradeoffs env-var ceiling amendment (C-J).** Appended an additive postscript paragraph to `docs/phases/03-vuln-deterministic-recipe/ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md` §Tradeoffs noting Phase-3 env vars are now three: `CODEGENIE_BUNDLE_CONCURRENCY`, `CODEGENIE_VULN_INDEX_PATH`, `CODEGENIE_BUNDLE_CACHE_TTL_DAYS`. The amendment is additive (no edit to the original "two" claim's line — postscript style). `make docs` passes.

### Gate

- [ ] **AC-48.** TDD red tests committed first, then green; refactors carry tests through.
- [ ] **AC-49.** `ruff format --check`, `ruff check`, `mypy --strict` clean.
- [ ] **AC-50.** `make lint-imports` (import-linter) passes — `codegenie.plugins.cache` and `codegenie.plugins.cache_gc` do NOT take `blake3` as a direct import (already AC-13 from the AST side; this is the structural fence).

## Implementation outline

1. **`src/codegenie/types/identifiers.py`** (additive, one line):
   - `BundleCacheKey = NewType("BundleCacheKey", str)` — module docstring extended one sentence noting smart-constructor convention.

2. **`src/codegenie/plugins/cache.py`** (new):
   - Imports: `from codegenie.types.identifiers import BundleCacheKey, PluginId, PrimitiveName, BlobDigest`, `from codegenie.errors import CodegenieError`, `from codegenie.hashing import content_hash_bytes, _UNIT_SEP` (the existing `\x1f`), `from codegenie.transforms._forward import SandboxedPath`, `from codegenie.plugins.bundle import Bundle` (S3-04).
   - `class BundleCacheErrorModel(BaseModel)` — frozen, `extra="forbid"`, `reason: Literal[...]`, `details`.
   - `class BundleCacheRaise(CodegenieError): def __init__(self, model: BundleCacheErrorModel) -> None: ...; self.model`.
   - `def compose_bundle_cache_key(**kwargs) -> BundleCacheKey` — kw-only signature, all 8 required, separator-poisoning check, `payload = _UNIT_SEP.join([...]).encode("utf-8")`, `return BundleCacheKey(content_hash_bytes(payload))`.
   - `def _validate_key(key: str) -> None` — regex check, raises `BundleCacheRaise(reason="invalid_key")`.
   - `class BundleCacheStore`: `__init__(cache_dir: SandboxedPath)`, `put(key: BundleCacheKey, bundle: Bundle)` (reuses Phase-0 atomic-write pattern; does NOT import from `codegenie.cache.store` to keep the modules sibling-decoupled — inline `<dest>.tmp + fsync + os.replace` is ~10 lines), `get(key: BundleCacheKey) -> Bundle | None`.

3. **`src/codegenie/plugins/cache_gc.py`** (new):
   - `_DEFAULT_TTL_DAYS: Final[int] = 7`, `_GC_STAMP_FILENAME: Final[str] = ".gc-stamp"`, `_GC_STAMP_LOCK_FILENAME: Final[str] = ".gc-stamp.lock"`, `_AMORTIZATION_SECONDS: Final[int] = 86400`, `_HEX_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}\.json$")`.
   - Pure helpers (no I/O, no env): `_parse_ttl_seconds`, `_is_evictable`, `_should_run_amortized`.
   - `_atomic_write_text(path, content)` inline helper (~5 lines; rule-of-three for `_fs_atomic` extraction NOT met yet — see Notes DP-G).
   - `class CacheGcResult(BaseModel)`, `class CacheGcCompletedEvent(BaseModel)` with `.from_result(...)` classmethod (DP12).
   - `class BundleCacheGc`: `__init__(cache_dir, *, ttl_seconds=None, event_emitter=None)`; `run() -> CacheGcResult` (impure shell composing pure helpers + filesystem walk + emitter call); `run_amortized() -> CacheGcResult | None` (impure shell taking flock on `.gc-stamp.lock`, reading stamp, deciding via `_should_run_amortized`, optionally calling `run()`, atomically updating stamp).

4. **`src/codegenie/cli.py`** (additive only — DO NOT redeclare `cache` group, DO NOT touch `cache_gc`):
   - Add `@cache.command(name="prune") @click.option("--cache-dir", type=Path, default=None) def cache_prune(cache_dir: Path | None) -> None:` under the existing group at line 898.
   - Resolve `--cache-dir` default to `Path.cwd() / ".codegenie" / "cache"`.
   - Wrap path in `SandboxedPath(...)` (mirrors S3-04 import path).
   - Construct an inline emitter (~6 lines) that appends one JSON line to `<cache_dir>/../events/spanning/append.jsonl` (creates parent dirs with mode `0o700`; file with `0o600`). This shim is per AC-45; S6-04 swaps it for the real `EventLog.emit_spanning`.
   - Compute `t0 = time.monotonic_ns()`, `wall_clock = datetime.now(timezone.utc)...`, call `BundleCacheGc(sandboxed, event_emitter=emitter).run()`, emit `CacheGcCompletedEvent.from_result(result, trigger="operator_cli")`, exit `0`.

5. **`docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md`** — additive edit at §C9 Literal (line ~872): append `, "cache_gc_completed"` to the `event_type: Literal[...]` tuple. Cite arch line ~1077's additive-extension authorization in the changelog row of the arch design's revision footer (if one exists; otherwise inline comment is fine).

6. **`docs/phases/03-vuln-deterministic-recipe/ADRs/0008-...md`** — additive postscript paragraph at §Tradeoffs (per AC-47).

7. **Coordination notes (Out-of-scope here):**
   - S6-04 swaps the CLI's inline emitter for `event_log.emit_spanning`.
   - S6-04 calls `BundleCacheGc(cache_dir, event_emitter=event_log.emit_spanning).run_amortized()` at orchestrator init.
   - S7-02 wires `BundleBuilder` cache lookup through `BundleCacheStore.get` / `.put` (today the store stands alone).

## TDD plan — red / green / refactor

### Red

**`tests/unit/plugins/test_bundle_cache_key.py`**

```python
import json
import pytest
from codegenie.plugins.cache import (
    compose_bundle_cache_key, BundleCacheRaise, BundleCacheErrorModel,
)
from codegenie.hashing import content_hash_bytes

# Sample digests/IDs sized so base[k] + "x" is byte-unique vs every other base[k'].
_SAMPLE: dict[str, str] = {
    "plugin_id": "vuln-node-npm",
    "plugin_version": "0.1.0",
    "primitive": "scip.refs",
    "args_canonical": '{"symbol":"x"}',
    "repo_ctx_digest": "blake3:" + "a"*64,
    "scip_digest":     "blake3:" + "b"*64,
    "dep_graph_digest":"blake3:" + "c"*64,
    "vuln_index_digest":"blake3:" + "d"*64,
}
# Same-length, distinct-equivalence-class mutation table — mutation-kills an
# implementation that silently omits any one input from the concatenation.
_MUTATION: dict[str, str] = {
    "plugin_id":         "vuln-node-yrn",   # 13 chars, distinct
    "plugin_version":    "0.1.1",           # same length
    "primitive":         "scip.defs",       # same length
    "args_canonical":    '{"symbol":"y"}',  # same length
    "repo_ctx_digest":   "blake3:" + "e"*64,
    "scip_digest":       "blake3:" + "f"*64,
    "dep_graph_digest":  "blake3:" + "0"*64,
    "vuln_index_digest": "blake3:" + "1"*64,
}

class TestComposeBundleCacheKey:

    def test_returns_blake3_prefixed_64_hex(self):
        key = compose_bundle_cache_key(**_SAMPLE)
        assert key.startswith("blake3:") and len(key) == len("blake3:") + 64

    def test_declared_order_byte_layout(self):
        # AC-7 — pin the on-the-wire order. A mutant that sorts kwargs
        # alphabetically would produce a different hash and fail here.
        payload = "\x1f".join([
            _SAMPLE["plugin_id"], _SAMPLE["plugin_version"], _SAMPLE["primitive"],
            _SAMPLE["args_canonical"], _SAMPLE["repo_ctx_digest"],
            _SAMPLE["scip_digest"], _SAMPLE["dep_graph_digest"],
            _SAMPLE["vuln_index_digest"],
        ]).encode("utf-8")
        assert compose_bundle_cache_key(**_SAMPLE) == content_hash_bytes(payload)

    def test_boundary_shift_collisions_blocked(self):
        # AC-9 — \x1f separator defuses ("ab","c") vs ("a","bc") collision.
        rest = {k: v for k, v in _SAMPLE.items() if k not in ("plugin_id", "plugin_version")}
        k1 = compose_bundle_cache_key(plugin_id="ab", plugin_version="c", **rest)
        k2 = compose_bundle_cache_key(plugin_id="a",  plugin_version="bc", **rest)
        assert k1 != k2

    @pytest.mark.parametrize("vary", list(_SAMPLE))
    def test_each_input_participates_mutation_resistant(self, vary):
        # AC-8 — ADR-0008 correctness: omitting any one input must change the key.
        # Mutation strategy is same-length distinct-class, NOT append-"x" — a buggy
        # impl that omits `vuln_index_digest` is reliably caught.
        modified = {**_SAMPLE, vary: _MUTATION[vary]}
        assert compose_bundle_cache_key(**_SAMPLE) != compose_bundle_cache_key(**modified)

    def test_kwargs_only_signature(self):
        # AC-6 — positional call raises TypeError.
        with pytest.raises(TypeError):
            compose_bundle_cache_key(  # type: ignore[misc]
                "vuln-node-npm", "0.1.0", "scip.refs", "{}",
                "blake3:" + "a"*64, "blake3:" + "b"*64,
                "blake3:" + "c"*64, "blake3:" + "d"*64,
            )

    def test_determinism_n_100(self):
        # AC-11 — 100 calls produce one unique key.
        keys = {compose_bundle_cache_key(**_SAMPLE) for _ in range(100)}
        assert len(keys) == 1

    def test_args_canonical_passthrough_verbatim(self):
        # AC-12 — composer treats args_canonical as opaque bytes.
        k_tight = compose_bundle_cache_key(**{**_SAMPLE, "args_canonical": '{"a":1}'})
        k_loose = compose_bundle_cache_key(**{**_SAMPLE, "args_canonical": '{"a": 1}'})
        assert k_tight != k_loose

    @pytest.mark.parametrize("poisoned_field", list(_SAMPLE))
    def test_separator_poisoning_rejected(self, poisoned_field):
        # AC-10 — \x1f embedded in any input raises BundleCacheRaise.
        kw = {**_SAMPLE, poisoned_field: _SAMPLE[poisoned_field] + "\x1ftrailer"}
        with pytest.raises(BundleCacheRaise) as exc:
            compose_bundle_cache_key(**kw)
        assert exc.value.model.reason == "separator_in_input"
        assert exc.value.model.details["input"] == poisoned_field
```

**`tests/unit/plugins/test_bundle_cache_store.py`** (round-trip, mode, idempotence, key validation, corrupt preservation, `Bundle` JSON-roundtrip canary):

```python
import json, os, pytest
from pathlib import Path
from codegenie.plugins.cache import BundleCacheStore, BundleCacheRaise
from codegenie.plugins.bundle import Bundle  # S3-04
from codegenie.transforms._forward import SandboxedPath

_VALID_KEY = "blake3:" + "a"*64

def test_put_then_get_round_trips(tmp_path, sample_bundle):
    store = BundleCacheStore(SandboxedPath(tmp_path))
    store.put(_VALID_KEY, sample_bundle)
    got = store.get(_VALID_KEY)
    assert got == sample_bundle
    assert type(got.entries) is type(sample_bundle.entries), \
        "container type must round-trip (catches the tuple→list JSON ambiguity)"

def test_put_writes_atomically_no_residual_tmp(tmp_path, sample_bundle):
    store = BundleCacheStore(SandboxedPath(tmp_path))
    store.put(_VALID_KEY, sample_bundle)
    assert list((tmp_path / "bundles").glob("*.tmp")) == []

def test_put_file_mode_0600(tmp_path, sample_bundle):
    store = BundleCacheStore(SandboxedPath(tmp_path))
    store.put(_VALID_KEY, sample_bundle)
    blob = tmp_path / "bundles" / ("a"*64 + ".json")
    assert blob.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "bundles").stat().st_mode & 0o777 == 0o700

def test_idempotent_put(tmp_path, sample_bundle):
    store = BundleCacheStore(SandboxedPath(tmp_path))
    store.put(_VALID_KEY, sample_bundle)
    blob = tmp_path / "bundles" / ("a"*64 + ".json")
    first = blob.read_bytes()
    store.put(_VALID_KEY, sample_bundle)
    assert blob.read_bytes() == first

def test_get_missing_returns_none(tmp_path):
    assert BundleCacheStore(SandboxedPath(tmp_path)).get("blake3:" + "b"*64) is None

def test_corrupt_file_returns_none_and_file_survives(tmp_path, caplog):
    store = BundleCacheStore(SandboxedPath(tmp_path))
    (tmp_path / "bundles").mkdir(parents=True)
    corrupt = tmp_path / "bundles" / ("c"*64 + ".json")
    corrupt.write_text("{not valid json")
    assert store.get("blake3:" + "c"*64) is None
    assert corrupt.exists(), "Rule 12: do NOT delete the file (operator inspection)"

@pytest.mark.parametrize("bad_key", [
    "", "blake3:", "blake3:" + "z"*64, "blake3:../../etc/passwd",
    "blake3:" + "a"*63, "blake3:" + "a"*65, "sha256:" + "a"*64, "a"*64,
])
def test_key_validation_rejects_malformed(tmp_path, bad_key, sample_bundle):
    store = BundleCacheStore(SandboxedPath(tmp_path))
    with pytest.raises(BundleCacheRaise) as exc:
        store.put(bad_key, sample_bundle)
    assert exc.value.model.reason == "invalid_key"

def test_bundle_json_round_trip_canary(sample_bundle):
    # AC-19 — if this fails, S3-04 normalizes tuple→list and S3-05 is unblocked.
    rehydrated = type(sample_bundle).model_validate_json(sample_bundle.model_dump_json())
    assert rehydrated == sample_bundle
```

**`tests/unit/plugins/test_bundle_cache_gc.py`** (pure helpers + Hypothesis + run/amortized/edge cases):

```python
import os, re, time, pytest
from hypothesis import given, strategies as st
from codegenie.plugins.cache_gc import (
    BundleCacheGc, BundleCacheRaise, CacheGcCompletedEvent, CacheGcResult,
    _parse_ttl_seconds, _is_evictable, _should_run_amortized,
)
from codegenie.transforms._forward import SandboxedPath

class TestPureHelpers:

    @given(now=st.floats(0, 1e10), mtime=st.floats(0, 1e10), ttl=st.integers(1, 365*86400))
    def test_is_evictable_monotone_in_age(self, now, mtime, ttl):
        # Metamorphic: older entries are always at-least-as-evictable as newer ones.
        older = mtime - 1
        assert _is_evictable(now, older, ttl) >= _is_evictable(now, mtime, ttl)

    def test_is_evictable_strict_boundary(self):
        # AC-29: exactly-TTL-old kept; one second older evicted.
        now = 1_000_000.0
        ttl = 7 * 86400
        assert not _is_evictable(now, now - ttl, ttl)
        assert _is_evictable(now, now - ttl - 1, ttl)

    @given(now=st.floats(0, 1e10), stamp=st.floats(0, 1e10), iv=st.integers(1, 86400))
    def test_should_run_amortized_idempotent_within_interval(self, now, stamp, iv):
        if stamp <= now and not _should_run_amortized(now, stamp, iv):
            assert not _should_run_amortized(now + iv // 2, stamp, iv)

    def test_should_run_amortized_future_dated_stamp_runs(self):
        # AC-38: clock-skew resilience.
        now = 1_000.0
        assert _should_run_amortized(now, last_stamp=now + 86_400, interval_seconds=86_400)

    @pytest.mark.parametrize("raw,expected", [
        ("7", 7*86400), (" 7 ", 7*86400), ("7\n", 7*86400),
        ("1", 86400), ("30", 30*86400), ("365", 365*86400),
    ])
    def test_parse_ttl_accepts(self, raw, expected):
        assert _parse_ttl_seconds({"CODEGENIE_BUNDLE_CACHE_TTL_DAYS": raw}) == expected

    @pytest.mark.parametrize("bad", ["", "0", "-1", "7.5", "+7", "not-an-int", "  ", "1e2", "0x7"])
    def test_parse_ttl_reject_corpus(self, bad):
        # AC-31 reject corpus.
        with pytest.raises(BundleCacheRaise) as exc:
            _parse_ttl_seconds({"CODEGENIE_BUNDLE_CACHE_TTL_DAYS": bad})
        assert exc.value.model.reason == "invalid_ttl_env"
        assert exc.value.model.details["value"] == bad

class TestRun:

    def test_constructor_does_no_io(self, tmp_path, monkeypatch):
        # AC-26 — invalid env should NOT raise at __init__.
        monkeypatch.setenv("CODEGENIE_BUNDLE_CACHE_TTL_DAYS", "not-an-int")
        gc = BundleCacheGc(SandboxedPath(tmp_path))  # ← must NOT raise
        with pytest.raises(BundleCacheRaise) as exc:
            gc.run()
        assert exc.value.model.reason == "invalid_ttl_env"

    def test_evicts_only_files_older_than_ttl(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CODEGENIE_BUNDLE_CACHE_TTL_DAYS", "7")
        bundles = tmp_path / "bundles"; bundles.mkdir(parents=True)
        old = bundles / ("a"*64 + ".json"); old.write_text('{"x":1}')
        size_old = old.stat().st_size
        os.utime(old, (time.time() - 8 * 86400,) * 2)
        fresh = bundles / ("b"*64 + ".json"); fresh.write_text('{"x":1}')
        result = BundleCacheGc(SandboxedPath(tmp_path)).run()
        assert not old.exists() and fresh.exists()
        assert result.entries_evicted == 1
        assert result.bytes_reclaimed == size_old  # AC-30: exact accounting
        assert result.duration_ms >= 0
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", result.wall_clock_iso)

    def test_run_on_missing_bundles_dir_returns_zero(self, tmp_path):
        # AC-28
        result = BundleCacheGc(SandboxedPath(tmp_path)).run()
        assert result.entries_evicted == 0 and result.bytes_reclaimed == 0

    def test_run_skips_non_hex_files_and_special_paths(self, tmp_path):
        bundles = tmp_path / "bundles"; bundles.mkdir(parents=True)
        (bundles / ".lock").write_text("")
        (tmp_path / ".gc-stamp").write_text(str(time.time() - 100*86400))
        (bundles / "README.md").write_text("ignore me")
        (bundles / "not-hex.json").write_text("{}")
        (bundles / "subdir").mkdir()
        # Stale-mtime everything; only valid hex names should be evicted (none here).
        os.utime(tmp_path / ".gc-stamp", (time.time() - 100*86400,) * 2)
        for p in bundles.iterdir():
            if p.is_file():
                os.utime(p, (time.time() - 100*86400,) * 2)
        BundleCacheGc(SandboxedPath(tmp_path)).run()
        for p in [bundles / ".lock", bundles / "README.md", bundles / "not-hex.json",
                  bundles / "subdir", tmp_path / ".gc-stamp"]:
            assert p.exists(), f"non-hex / special path must NOT be touched: {p}"

    def test_event_emitter_called_exactly_once(self, tmp_path):
        # AC-32
        seen: list[CacheGcCompletedEvent] = []
        gc = BundleCacheGc(SandboxedPath(tmp_path), event_emitter=seen.append)
        gc.run()
        assert len(seen) == 1
        assert seen[0].trigger == "amortized"
        assert seen[0].event_type == "cache_gc_completed"

    def test_event_emitter_none_emits_zero(self, tmp_path):
        # AC-32 — emitter optional.
        gc = BundleCacheGc(SandboxedPath(tmp_path), event_emitter=None)
        gc.run()  # ← does not raise; nothing to assert beyond return type

    def test_emitter_exceptions_propagate(self, tmp_path):
        # AC-33 — Rule 12, fail loud.
        def bad(_): raise RuntimeError("emitter blew up")
        gc = BundleCacheGc(SandboxedPath(tmp_path), event_emitter=bad)
        with pytest.raises(RuntimeError, match="emitter blew up"):
            gc.run()

class TestAmortization:

    def test_first_call_writes_stamp(self, tmp_path):
        # AC-34 + AC-36
        t_before = time.time()
        result = BundleCacheGc(SandboxedPath(tmp_path)).run_amortized()
        t_after = time.time()
        stamp_path = tmp_path / ".gc-stamp"
        assert result is not None
        assert stamp_path.exists()
        assert t_before <= float(stamp_path.read_text()) <= t_after

    def test_within_24h_is_noop_and_does_not_emit(self, tmp_path):
        # AC-32 (no-op branch) + AC-41
        seen: list[CacheGcCompletedEvent] = []
        gc = BundleCacheGc(SandboxedPath(tmp_path), event_emitter=seen.append)
        first = gc.run_amortized()
        second = gc.run_amortized()
        assert first is not None and second is None
        assert len(seen) == 1, "no-op branch must NOT emit a second event"

    def test_24h_elapsed_runs_again(self, tmp_path, monkeypatch):
        # AC-40 — captures real_time BEFORE patching to avoid recursion.
        import codegenie.plugins.cache_gc as cg
        gc = BundleCacheGc(SandboxedPath(tmp_path))
        assert gc.run_amortized() is not None
        stamp_before = float((tmp_path / ".gc-stamp").read_text())
        t_jump = stamp_before + 86_401
        monkeypatch.setattr(cg.time, "time", lambda: t_jump)
        assert gc.run_amortized() is not None
        stamp_after = float((tmp_path / ".gc-stamp").read_text())
        assert stamp_after > stamp_before

    def test_stamp_atomic_no_tmp_residue(self, tmp_path):
        # AC-35
        BundleCacheGc(SandboxedPath(tmp_path)).run_amortized()
        assert not (tmp_path / ".gc-stamp.tmp").exists()
        assert float((tmp_path / ".gc-stamp").read_text()) > 0  # parseable float

    def test_corrupt_gc_stamp_fails_loud(self, tmp_path):
        # AC-37
        (tmp_path / ".gc-stamp").write_text("not-a-float")
        with pytest.raises(BundleCacheRaise) as exc:
            BundleCacheGc(SandboxedPath(tmp_path)).run_amortized()
        assert exc.value.model.reason == "corrupt_gc_stamp"

    def test_future_dated_stamp_treated_as_stale(self, tmp_path):
        # AC-38
        future = time.time() + 86_400
        (tmp_path / ".gc-stamp").write_text(str(future))
        result = BundleCacheGc(SandboxedPath(tmp_path)).run_amortized()
        assert result is not None
        new_stamp = float((tmp_path / ".gc-stamp").read_text())
        assert new_stamp < future, "future-dated stamp must be rewritten to time.time()"

    def test_concurrent_callers_serialized(self, tmp_path):
        # AC-39 — only one of two concurrent run_amortized calls runs the GC.
        import threading
        gc = BundleCacheGc(SandboxedPath(tmp_path))
        results: list[CacheGcResult | None] = []
        def call(): results.append(gc.run_amortized())
        t1 = threading.Thread(target=call); t2 = threading.Thread(target=call)
        t1.start(); t2.start(); t1.join(); t2.join()
        assert sum(r is not None for r in results) == 1
        assert sum(r is None for r in results) == 1
```

**`tests/unit/plugins/test_cache_gc_purity.py`** (AST purity fence — DP2 / AC-25):

```python
import ast, pathlib

_TARGET_FUNCS = {"_parse_ttl_seconds", "_is_evictable", "_should_run_amortized"}
_FORBIDDEN_ROOTS = {"os", "Path", "time", "structlog"}

def test_pure_helpers_have_no_io_or_clock_references():
    src = pathlib.Path("src/codegenie/plugins/cache_gc.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in _TARGET_FUNCS:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Attribute):
                    root = inner.value
                    while isinstance(root, ast.Attribute):
                        root = root.value
                    if isinstance(root, ast.Name) and root.id in _FORBIDDEN_ROOTS:
                        raise AssertionError(
                            f"{node.name} references forbidden root '{root.id}'"
                        )
```

**`tests/unit/plugins/test_cache_no_blake3_import.py`** (AC-13):

```python
import ast, pathlib

def _imports(path: str) -> set[str]:
    tree = ast.parse(pathlib.Path(path).read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names

def test_neither_cache_module_imports_blake3_directly():
    for path in ("src/codegenie/plugins/cache.py", "src/codegenie/plugins/cache_gc.py"):
        names = _imports(path)
        assert not any(n.startswith("blake3") for n in names), \
            f"{path}: ADR-0001 chokepoint — only codegenie.hashing imports blake3"
```

**`tests/integration/cli/test_cache_prune.py`** (AC-44 + AC-46 + AC-42):

```python
import os, time, pytest
from pathlib import Path
from click.testing import CliRunner
from codegenie.cli import cli

@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()

@pytest.fixture
def capture_spanning_events(tmp_path):
    """Reads <cache_dir>/../events/spanning/append.jsonl. AC-45 interim format.

    S6-01 absorbs this file into the chained zstd format additively; tests
    do not need to be rewritten when that happens (decoder swap only).
    """
    def _read(cache_dir: Path):
        from codegenie.plugins.cache_gc import CacheGcCompletedEvent
        jl = cache_dir.parent / "events" / "spanning" / "append.jsonl"
        if not jl.exists():
            return []
        return [
            CacheGcCompletedEvent.model_validate_json(line)
            for line in jl.read_text().splitlines() if line.strip()
        ]
    return _read

@pytest.mark.parametrize("seed_stale", [True, False])
def test_cache_prune_emits_exactly_one_event(tmp_path, runner, capture_spanning_events, seed_stale):
    cache_dir = tmp_path / "cache"
    bundles = cache_dir / "bundles"; bundles.mkdir(parents=True)
    if seed_stale:
        stale = bundles / ("a"*64 + ".json"); stale.write_text('{"x":1}')
        os.utime(stale, (time.time() - 10*86400,) * 2)
    result = runner.invoke(cli, ["cache", "prune", "--cache-dir", str(cache_dir)])
    assert result.exit_code == 0, result.output
    events = capture_spanning_events(cache_dir)
    assert len(events) == 1, "exactly-one-event invariant holds for empty cache too"
    ev = events[0]
    assert ev.event_type == "cache_gc_completed"
    assert ev.trigger == "operator_cli"
    if seed_stale:
        assert ev.entries_evicted == 1 and ev.bytes_reclaimed > 0
    else:
        assert ev.entries_evicted == 0 and ev.bytes_reclaimed == 0

def test_cache_prune_help_exit_zero(runner):
    # AC-43
    assert runner.invoke(cli, ["cache", "prune", "--help"]).exit_code == 0

def test_cache_gc_stub_preserved(runner, caplog):
    # AC-42 — Phase-1+ migration contract.
    result = runner.invoke(cli, ["cache", "gc"])
    assert result.exit_code == 0
    assert any(r.message == "cache.gc.stub" or "cache.gc.stub" in r.message
               for r in caplog.records)
```

### Green

Smallest impl: §Implementation outline; ~250 lines across the four touched code files. Property tests run on every `make test` (no `bench` marker).

### Refactor

- If a third atomic-write site appears (likely Phase 4 recipe cache OR `BundleCacheStore.put`'s internal write), extract a `codegenie._fs_atomic.atomic_write_bytes` / `atomic_write_text` helper. Until then keep inline (rule-of-three not met — see Notes DP-G).
- The CLI's inline emitter is replaced by `EventLog.emit_spanning` in S6-04; the test assertions are wire-format-bound, not function-bound, so they survive the swap.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Additive: `BundleCacheKey = NewType(...)`; one-line docstring extension |
| `src/codegenie/plugins/cache.py` | New module — composer, store, error model + raise wrapper |
| `src/codegenie/plugins/cache_gc.py` | New module — `BundleCacheGc`, `CacheGcResult`, `CacheGcCompletedEvent`, pure helpers (Gap 4 fix) |
| `src/codegenie/cli.py` | Additive: `@cache.command(name="prune")` only — DO NOT touch the `cache` group declaration at line 898 or the existing `cache_gc` at line 903 |
| `tests/unit/plugins/test_bundle_cache_key.py` | Composer tests (declared order, mutation-resistant participation, boundary shift, determinism N=100, args_canonical passthrough, separator-poisoning) |
| `tests/unit/plugins/test_bundle_cache_store.py` | put/get round-trip, atomicity, mode, idempotence, key validation, corrupt-survives, `Bundle` JSON-roundtrip canary |
| `tests/unit/plugins/test_bundle_cache_gc.py` | Pure helpers + Hypothesis + run + amortization + edge cases + concurrent serialization |
| `tests/unit/plugins/test_cache_gc_purity.py` | AST purity fence (DP2 / AC-25) |
| `tests/unit/plugins/test_cache_no_blake3_import.py` | AST chokepoint fence (AC-13 / ADR-0001) |
| `tests/integration/cli/test_cache_prune.py` | End-to-end CLI + event-emission + `cache gc` stub regression |
| `tests/integration/cli/conftest.py` | `capture_spanning_events` fixture (interim JSON-lines reader; AC-46) |
| `docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md` | Additive: `"cache_gc_completed"` in §C9 Literal (AC-23) |
| `docs/phases/03-vuln-deterministic-recipe/ADRs/0008-...md` | Additive postscript: env-var ceiling raised to three (AC-47) |

## Out of scope

- **Editing `src/codegenie/cache/keys.py` or `src/codegenie/cache/store.py`** — Phase-0 probe-cache is a sibling concept. Reuse the pattern, do NOT unify.
- **`EventLog` infrastructure / BLAKE3 chain / zstd compression** — S6-01 owns those. This story exports `CacheGcCompletedEvent` and emits to a single uncompressed `append.jsonl` per AC-45; S6-01 absorbs the file into the chained zstd format additively.
- **`BundleBuilder` cache lookup integration** — S3-04 ships the builder; this story exposes the key composer + store; wiring `BundleBuilder.build` to consult `BundleCacheStore.get` lives in S7-02 (production-wiring).
- **Per-plugin TTL knobs** — one `CODEGENIE_BUNDLE_CACHE_TTL_DAYS` is enough at Phase 3.
- **Cache-key versioning** — if the key shape changes (Phase 4 adds a 9th input), bump via additive ADR-0008 amendment + an additive `compose_bundle_cache_key` wrapper. Phase 3 does not version the key.
- **Bench / perf assertions** — `run()` over 10k entries should be fast (~100 ms) but no bench gate; S9-03 may add one.
- **`CanonicalArgsJson` newtype** — second user of `args_canonical: str` lands here; rule-of-three not yet met (S3-04 was the first). See Notes DP-E.
- **`SemverVersion` newtype** — does not yet exist; this story uses `plugin_version: str` and surfaces the gap for a future S1-01 amendment. See Notes DP-B.

## Notes for the implementer

- **`vuln_index_digest` is the load-bearing input (ADR-0008 §Context / Hidden Assumption #3).** The single most important test in this story is the mutation-resistant participation parametrize at AC-8: a `compose_bundle_cache_key` implementation that silently omits `vuln_index_digest` MUST fail the parametrize row that varies it. The `_MUTATION` table in the test deliberately uses same-length distinct-class values so the test cannot pass for the wrong reason (string-length-induced hash divergence).

- **DP-A (functional core / imperative shell).** `_parse_ttl_seconds`, `_is_evictable`, `_should_run_amortized` are pure (no `os.`, no `Path.`, no `time.`, no `structlog`). The AST fence at `tests/unit/plugins/test_cache_gc_purity.py` is what holds the line over the refactor cycle. Mirrors S3-04 AC-27/28 ("`_compose_entry` pure"). The impure shells (`run`, `run_amortized`) compose pure decisions with filesystem + clock + emitter.

- **DP-B (`SemverVersion` deferral).** `plugin_version: str` is intentional. `codegenie.types.identifiers` has `PluginId`, `RecipeId`, `BlobDigest`, `PrimitiveName`, etc., but no `SemverVersion` — `src/codegenie/transforms/transform.py:49,126` flagged the same gap and chose the same workaround. When a third caller appears (likely Phase 4's recipe registry or S7-02's adapter manifest), elevate to `SemverVersion = NewType("SemverVersion", str)` with a smart constructor validating `r"^\d+\.\d+\.\d+(?:[-+].*)?$"`. Not now.

- **DP-C (`CanonicalArgsJson` deferral, second-user lineage).** S3-04 validation §DP1 flagged the `args_canonical: str` primitive obsession and deferred to S3-05; S3-05 is now the second user. Still two callers — rule-of-three not met. When the third caller appears (Phase 4 recipe-cache composer OR S7-02 adapter dispatch), elevate to `CanonicalArgsJson = NewType("CanonicalArgsJson", str)` with `canonicalize_args(payload: Mapping[str, Any]) -> CanonicalArgsJson` smart constructor that calls `json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)`. The module docstring of `cache.py` documents the canonical-caller form so callers don't drift.

- **DP-D (`BundleCacheKey` newtype rule-of-three).** Three call sites (composer + put + get) — newtype lands here. Construction is funneled through `compose_bundle_cache_key`. An AST test (TODO if appetite — not required by an AC; rule-of-three for the AST fence itself is not met) can enforce that no other module calls `BundleCacheKey(...)` directly.

- **DP-E (Cache-key Open/Closed seam — premature).** ADR-0008 says additional digest inputs are "mechanical." Today one call site, 8 fixed kwargs — explicit beats premature. When Phase 4+ adds a 9th input AND a second composer appears (e.g., `codegenie.recipes.cache.compose_recipe_cache_key`), elevate to an ordered tuple of `(name: str, digest: BlobDigest | str)` pairs hashed in declared order with a `@register_cache_key_input(name)` decorator. Bump ADR-0008 additively. NOT NOW.

- **DP-F (Evictable-families registry — premature).** `_HEX_NAME_RE` + `<cache_dir>/bundles/` is hardcoded. When Phase 4 (recipe cache) and Phase 7 (transform cache) add second / third families, elevate to a `@register_evictable_family(name)` decorator producing `Iterable[CachedEntry]`. Today one family; iteration over a single tuple is simpler than a registry of one. Mirrors `@register_index_freshness_check` shape.

- **DP-G (`_fs_atomic` extraction — at 2 of 3 callers).** Phase-0 `cache/store.py:_atomic_write_bytes` and this story's `_atomic_write_text` (for `.gc-stamp`) are the two atomic-write sites. The third likely caller — `BundleCacheStore.put`'s internal blob write OR Phase 4's recipe-cache writer — triggers extraction to `codegenie._fs_atomic` with `atomic_write_bytes` / `atomic_write_text`. Until the third lands, duplicate inline (~6 lines). Rule 2 trumps DRY at two callers. (Note: `BundleCacheStore.put` IS another atomic-write site in this story — that brings the count to 3 in the same PR. If the executor wants to extract early they MAY, but the AC bar is "two duplicated atomic-write helpers" not "one shared helper" — surface the choice in the attempt log.)

- **`.gc-stamp` discipline.** Lives at `<cache_dir>/.gc-stamp`, NOT `<cache_dir>/bundles/.gc-stamp` (keeps `ls bundles/` clean for operator debugging). Atomic write: `<cache_dir>/.gc-stamp.tmp` + `fsync` + `os.replace`. **`fcntl.flock` is acquired on `<cache_dir>/.gc-stamp.lock`** for the read-stamp / decide / write-stamp critical section of `run_amortized` (the one and only `flock` in the story — blob writes deliberately avoid `flock` per AC-16). The lock is held across the GC walk inside `run_amortized` — at orchestrator init that's once per 24h, so the contention cost is negligible.

- **Fail-loud on bad TTL env.** Same rule as S3-02's `MAX_AGE_DAYS` env validator. Silent default-fallback hides operator typos (Rule 12).

- **`CacheGcCompletedEvent.trigger` discriminator** — `"amortized"` for `run`/`run_amortized` invocations from the orchestrator; `"operator_cli"` for `codegenie cache prune`. Phase 9 reads the trigger to distinguish background GC from operator-driven prune in spanning-stream queries. If a future dispatch site on `trigger` appears, that site MUST use `match` + `from typing import assert_never` (ADR-0010); no dispatch site ships in S3-05, so no AC enforces it here.

- **The event MUST be emitted exactly once per `run()`** — integration-tested for both the CLI and the helper. Two emits would corrupt the chained spanning stream's append semantics; zero would let operators wonder if the prune actually happened. The CLI test IS the canary; the helper-level AC-32 closes the orchestrator-path gap.

- **Do not preemptively add a `--force` flag.** S6-04's orchestrator calls `run_amortized()`; operators who want unconditional GC use `codegenie cache prune`. Two CLIs > one CLI with a flag (Rule 2).

- **CLI coexistence.** `codegenie cache prune` (this story) coexists with the Phase-1+ `cache gc` stub (`cli.py:898-912`). They are conceptually distinct — `cache gc` operates on the probe cache (`codegenie.cache.store`); `cache prune` operates on the Bundle cache (`codegenie.plugins.cache`). Do NOT unify them and do NOT delete the stub: its `cache.gc.stub` log line is a Phase-1+ migration-contract anchor per its docstring.

- **Cite Gap 4 explicitly in module docstrings.** Reviewers reading `cache_gc.py` for the first time should see "This module IS the Gap 4 fix from `docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md §Gap analysis`." Saves a confused re-read.
