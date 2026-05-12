# Story S3-08 — `transforms/lockfile/resolver.py` + four-component cache key + transient retry + `cache.replay`

**Step:** Step 3 — Ship the `NcuRecipeEngine` vertical: `tools/npm` + `tools/ncu` wrappers, `LockfileResolver`, `LockfileCanonicalizer`, recipe catalog + selector
**Status:** Ready
**Effort:** L
**Depends on:** S3-07
**ADRs honored:** ADR-0006, ADR-0010, ADR-0011

## Context

`LockfileResolver` is the **only** retry surface in Phase 3 (per ADR-0006). It runs `npm install --package-lock-only --ignore-scripts --no-audit --no-fund` inside `run_in_sandbox(network="scoped", allowlist=["registry.npmjs.org"])`, regenerates `package-lock.json` deterministically for a bumped `package.json`, and caches aggressively via a four-component cache key. The patch-version of `npm` is **deliberately dropped** from the cache key per `final-design.md §Goals #8` to avoid portfolio-wide stampedes; the canonicalizer in S3-09 closes the byte-stability gap that patch-drift would otherwise introduce.

A cache hit replays the cached lockfile bytes (≈ 5 ms) **and** appends a `cache.replay` audit event referencing the original chain head (ADR-0010). This is the back-reference that lets `codegenie audit verify --run-id <id>` reconstruct the chain even when a run consists primarily of cache hits.

This is the single most load-bearing component in Step 3. Its correctness is what makes Phase-5's gate machinery (the wrapping retry layer) safe to add later.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #5 (LockfileResolver)` — full internal-design, cache key, retry policy, sandbox.
  - `../phase-arch-design.md §"Goals" #8` — patch-version dropped from cache key.
  - `../phase-arch-design.md §"Goals" #18` — single-retry exception inside Phase 3.
  - `../phase-arch-design.md §"Component design — Audit event vocabulary"` — `cache.replay` payload `{cache_key, original_chain_head_blake3}`.
- **Phase ADRs:**
  - `../ADRs/0006-retry-deferred-to-phase-5-transient-io-exception.md` — exactly one transient-retry seat lives here.
  - `../ADRs/0010-audit-chain-extension-cache-replay-event.md` — `cache.replay` event semantics + chain back-reference.
  - `../ADRs/0011-lockfile-canonicalization-and-npm-digest-pin-for-deterministic-diffs.md` — minor-version-precision pin lineage.
- **Source design:**
  - `../final-design.md §"Components" #5` — primary lineage.
- **Existing code:**
  - `src/codegenie/tools/npm.py` (S3-01) — the wrapper this consumes.
  - `src/codegenie/catalogs/tools/__init__.py` (S3-03) — `npm_minor_digest()` helper.
  - `src/codegenie/audit_writer.py` — Phase-2 audit chain (extended by S1-07 with `cache.replay`).
  - `src/codegenie/exec.py` — `run_in_sandbox` (extended in S1-05/S1-06).

## Goal

Ship `src/codegenie/transforms/lockfile/resolver.py` exporting `LockfileResolver.run(worktree_path, *, audit) -> ResolverResult` per the arch design: four-component blake3 cache key, ≤ 3 bounded transient retries with exponential backoff, cache-hit emits `cache.replay` with original-chain-head back-reference, non-transient failure → `LockfileResolveFailed` fail-fast.

## Acceptance criteria

- [ ] `src/codegenie/transforms/lockfile/resolver.py` exports `ResolverResult(BaseModel)` `{lockfile_bytes: bytes, cache_hit: bool, npm_stdout_path: Path, npm_stderr_path: Path, cache_key: str, attempts: int}` (`extra="forbid"`).
- [ ] `LockfileResolver.run(worktree_path: Path, *, audit: AuditWriter, registry_mirror_digest: str, recipe_digest: str) -> ResolverResult`:
  - Cache key: `blake3(blake3(package.json) || blake3(package-lock.json) || npm_minor_digest() || registry_mirror_digest)` (hex digest) at `.codegenie/cache/lockfile/<key>.zst` (zstd-compressed lockfile bytes).
  - On cache hit: load bytes, **emit `cache.replay` audit event** `{cache_key, original_chain_head_blake3: <stored_at_put_time>}` referencing the chain head at the time the cache entry was written.
  - On cache miss: invoke `tools.npm.run(["install","--package-lock-only","--ignore-scripts","--no-audit","--no-fund"], cwd=worktree_path, network="scoped", test_execution=False, ...)`.
  - Bounded transient retry: ≤ 3 attempts on `transient_npm_codes = {"ETIMEDOUT","EAI_AGAIN","ECONNRESET","ENETUNREACH"}` matched against `ToolNonZeroExit.stderr_excerpt` OR npm-internal codes; exponential backoff 200 ms / 500 ms / 1200 ms.
  - Non-transient (any other non-zero exit, or `ToolOutputMalformed`, or `NpmScriptsEnabled`) → raise `LockfileResolveFailed` (NO retry).
- [ ] After cache miss + success: write `<key>.zst` to cache + persist `original_chain_head_blake3` as a sidecar `<key>.meta.json` (so future replays can back-reference).
- [ ] Cache directory `.codegenie/cache/lockfile/` is created lazily; respects an explicit `cache_root` override for tests.
- [ ] `LockfileResolveFailed` carries `last_exit_code`, `last_stderr_excerpt`, `attempts`, `cache_key`.
- [ ] `tests/unit/transforms/lockfile/test_resolver.py` ≥ 6 tests:
  1. Cache-key derivation: changing any of the four inputs changes the key; identical inputs reproduce.
  2. Cache-hit path emits `cache.replay` with non-empty `original_chain_head_blake3`.
  3. Cache miss → success path writes the cache entry + the meta sidecar.
  4. Transient retry exhaustion → `LockfileResolveFailed(attempts=3)`.
  5. Non-transient → `LockfileResolveFailed(attempts=1)` (no retry).
  6. `recipe_digest` change → cache-key change (proves S3-04's cache-key dependency).
- [ ] `tests/unit/test_recipe_digest_in_cache_key.py` (from S3-04) now exercises this resolver and confirms cache invalidation.
- [ ] `ruff check`, `mypy --strict`, `pytest` pass.

## Implementation outline

1. Land `tests/unit/transforms/lockfile/test_resolver.py` first (red).
2. Implement `src/codegenie/transforms/lockfile/resolver.py`:
   - `_compute_cache_key(worktree, registry_mirror_digest, recipe_digest) -> str` — read `package.json` + `package-lock.json` bytes, compute the four blake3s, mix per the arch spec. Include `recipe_digest` per S3-04's cache-key contract — concretely, mix it into the final blake3 (this story extends the arch's 4-component spec to thread the recipe-digest dependency).
   - `_load_cache(key) -> tuple[bytes, str] | None` — read `<key>.zst` + `<key>.meta.json`.
   - `_persist_cache(key, bytes, chain_head)` — write both files atomically (`os.replace` after `tempfile.NamedTemporaryFile`).
   - `_is_transient(exc: ToolNonZeroExit) -> bool` — scan stderr against `TRANSIENT_NPM_CODES`.
   - `async run(worktree_path, *, audit, registry_mirror_digest, recipe_digest, cache_root=None)`:
     ```text
     key = compute_cache_key(...)
     cached = load_cache(key)
     if cached:
       (bytes, original_head) = cached
       audit.append("cache.replay", {"cache_key": key, "original_chain_head_blake3": original_head})
       return ResolverResult(lockfile_bytes=bytes, cache_hit=True, ..., attempts=0)
     attempts = 0
     while attempts < 3:
       try:
         result = await tools.npm.run([...])
         break
       except ToolNonZeroExit as exc:
         attempts += 1
         if not _is_transient(exc) or attempts == 3:
           raise LockfileResolveFailed(...)
         await asyncio.sleep(BACKOFF_MS[attempts - 1] / 1000)
     bytes = (worktree_path / "package-lock.json").read_bytes()
     persist_cache(key, bytes, audit.current_chain_head())
     return ResolverResult(..., cache_hit=False, attempts=attempts + 1)
     ```
3. Define `LockfileResolveFailed` in `src/codegenie/errors.py` (typed error).
4. Run unit tests.

## TDD plan — red / green / refactor

### Red
Path: `tests/unit/transforms/lockfile/test_resolver.py`
```python
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock

from codegenie.transforms.lockfile.resolver import LockfileResolver, ResolverResult
from codegenie.errors import LockfileResolveFailed, ToolNonZeroExit


def test_cache_key_changes_with_each_input(worktree_factory, audit_stub):
    base = worktree_factory(pkg_json='{"a":1}', lock='{"l":1}')
    k0 = LockfileResolver()._compute_cache_key(base, "mirror1", "recipe1")
    # Each of the four inputs perturbed yields a different key
    assert k0 != LockfileResolver()._compute_cache_key(
        worktree_factory(pkg_json='{"a":2}', lock='{"l":1}'), "mirror1", "recipe1",
    )
    assert k0 != LockfileResolver()._compute_cache_key(base, "mirror2", "recipe1")
    assert k0 != LockfileResolver()._compute_cache_key(base, "mirror1", "recipe2")


@pytest.mark.asyncio
async def test_cache_hit_emits_cache_replay_with_chain_head(
    worktree_factory, audit_stub, cache_with_entry,
):
    wt = worktree_factory(pkg_json='{"a":1}', lock='{"l":1}')
    cache_with_entry(key="<computed>", lockfile_bytes=b"cached", chain_head="abc123")
    res = await LockfileResolver().run(
        wt, audit=audit_stub, registry_mirror_digest="m", recipe_digest="r",
        cache_root=cache_with_entry.root,
    )
    assert res.cache_hit is True
    assert res.lockfile_bytes == b"cached"
    events = [e for e in audit_stub.events if e.event_type == "cache.replay"]
    assert len(events) == 1
    assert events[0].payload["original_chain_head_blake3"] == "abc123"


@pytest.mark.asyncio
async def test_transient_retry_exhaustion_raises(worktree_factory, audit_stub):
    wt = worktree_factory(pkg_json='{"a":1}', lock='{"l":1}')
    transient = ToolNonZeroExit(exit_code=1, stderr_excerpt="npm ERR! code ETIMEDOUT")
    with patch("codegenie.transforms.lockfile.resolver.npm.run",
               new=AsyncMock(side_effect=transient)):
        with pytest.raises(LockfileResolveFailed) as exc:
            await LockfileResolver().run(
                wt, audit=audit_stub, registry_mirror_digest="m", recipe_digest="r",
            )
    assert exc.value.attempts == 3


@pytest.mark.asyncio
async def test_non_transient_does_not_retry(worktree_factory, audit_stub):
    wt = worktree_factory(pkg_json='{"a":1}', lock='{"l":1}')
    non_transient = ToolNonZeroExit(exit_code=1, stderr_excerpt="404 not found")
    with patch("codegenie.transforms.lockfile.resolver.npm.run",
               new=AsyncMock(side_effect=non_transient)) as m:
        with pytest.raises(LockfileResolveFailed) as exc:
            await LockfileResolver().run(
                wt, audit=audit_stub, registry_mirror_digest="m", recipe_digest="r",
            )
    assert exc.value.attempts == 1
    assert m.call_count == 1
```

### Green
Smallest impl: deterministic blake3 cache key, three-attempt retry loop with backoff, cache I/O via `zstandard` (already in deps for Phase 2 cache layer) + JSON sidecar. Keep the module under ~250 LOC.

### Refactor
- The retry loop is small enough to inline; resist extracting a generic `retry_transient(...)` helper. The whole point of ADR-0006 is that this is the **only** retry seat — a generic helper would invite reuse and erode the invariant.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/lockfile/__init__.py` | New — package marker |
| `src/codegenie/transforms/lockfile/resolver.py` | New — `LockfileResolver` |
| `src/codegenie/errors.py` | Add `LockfileResolveFailed` |
| `tests/unit/transforms/lockfile/test_resolver.py` | New — ≥ 6 tests |
| `tests/unit/transforms/lockfile/conftest.py` | New — `worktree_factory`, `audit_stub`, `cache_with_entry` |

## Out of scope

- **Lockfile canonicalization** — handled by S3-09 (called by S5-01's transform, not by the resolver).
- **Lockfile policy scan** — handled by S4-01 (separate pass before the transform).
- **The transform that drives this resolver** — handled by S5-01.
- **Phase-5 wrapping retry / gate machinery** — out of Phase 3 entirely (ADR-0006).

## Notes for the implementer
- The four-component cache key is the **paper-lock cache** — it caches the `npm install --package-lock-only` output. The Stage-6 `install_validator` (S4-02) re-runs `npm ci` on the cached lockfile to prove it survives a real install; that is the oracle that makes the paper-lock safe to cache (`design-performance.md §Components "Lockfile Resolver"` tradeoff).
- **Do NOT mix `npm_patch_digest` into the cache key.** The arch deliberately drops it; the canonicalizer in S3-09 absorbs patch-version drift in the output bytes. If the hot-path test in S7-04 starts seeing cache misses on patch bumps, this is a bug — not the intended behavior.
- The `recipe_digest` mix is the gap-2 closure (S3-04). It threads the recipe-pin-manifest dependency into the cache key without coupling the resolver to YAML parsing.
- The transient-code allow-list is intentionally narrow. `404`, `ETARGET` (missing version), and `EAUTH` are **non-transient** — they're operator bugs (wrong CVE version, missing registry credentials). Retry would just delay the failure.
- The `cache.replay` event MUST be appended **after** the bytes are loaded but **before** `ResolverResult` is returned (any consumer-visible side effect must be audit-trailed first). Phase-2's chain integrity invariant carries forward.
- The cache directory is portfolio-wide (`.codegenie/cache/` is shared across repos in a single workspace); the four-component key is what gives it cross-repo safety. Phase-7's Docker transform will reuse the same cache root with a different keying scheme.
- Per Rule 12 (Fail loud): `LockfileResolveFailed` must carry **all three** of `last_exit_code`, `last_stderr_excerpt` (≤ 4 KiB), and `attempts` — otherwise triage requires re-running with `--verbose`, which defeats the determinism canary.
- Atomic cache writes via `tempfile.NamedTemporaryFile(dir=cache_dir) + os.replace(...)` to avoid half-written `<key>.zst` on `Ctrl-C`. Cache poisoning by interrupted writes is exactly the failure mode `design-performance.md §Risks #4` flags.
