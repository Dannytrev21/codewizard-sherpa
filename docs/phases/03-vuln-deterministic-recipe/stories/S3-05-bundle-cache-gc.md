# Story S3-05 — Bundle cache key (incl. `vuln_index.digest`) + `BundleCacheGc` + `codegenie cache prune` CLI (Gap 4 fix)

**Step:** Step 3 — TCCM, BundleBuilder, VulnIndex, content-addressed cache
**Status:** Ready
**Effort:** S
**Depends on:** S3-03
**ADRs honored:** Phase 3 ADR-0008 (`vuln_index.digest` participates in Bundle cache key — load-bearing for correctness when CVE feeds re-classify), Phase 3 ADR-0005 (two-stream `EventLog` — `CacheGcCompleted` is a spanning event)

## Context

This story is **the Gap 4 fix from `phase-arch-design.md §Gap analysis`** — the synthesis under-specified Bundle cache eviction: "GC after 7 days mtime" was named but no component owned the mechanism. At portfolio scale (Phase 10) an un-GC'd cache becomes load-bearing; at Phase 3 it's a slow leak but a real one (`~50 KB/Bundle × thousands of warm workflows`). This story ships three small pieces tied together: (1) the BLAKE3 cache key composer that **must** include `vuln_index.digest` (per ADR-0008 — a CVE-feed refresh that re-classifies a CVE MUST NOT return a stale cache hit); (2) the `BundleCacheGc` helper invoked once-a-day at orchestrator init via `.codegenie/cache/.gc-stamp` amortization; (3) the operator-facing `codegenie cache prune` CLI command that calls the same helper unconditionally and emits one `CacheGcCompleted` spanning event with `bytes_reclaimed` and `entries_evicted`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis #4 — BundleBuilder cache eviction has no specified GC policy` (lines ~1168–1172) — the gap and the improvement spec. This story IS the fix.
  - `../phase-arch-design.md §C7. BundleBuilder` — cache key shape: `blake3(plugin_id || plugin_version || primitive || canonicalize(args) || repo_ctx.digest || scip.digest || dep_graph.digest || vuln_index.digest)`.
  - `../phase-arch-design.md §C9` — `WorkflowSpanningEvent.event_type` includes `cache_gc_completed` (add the variant if S6-01 hasn't yet — coordinate).
- **Phase ADRs (load-bearing):**
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md §Decision` — the cache key MUST include `vuln_index.digest`; this story ships the composer.
  - `../ADRs/0005-two-stream-event-log-per-adr-0034.md` — spanning-stream taxonomy includes lifecycle events; `CacheGcCompleted` is one.
- **Implementation plan:**
  - `../High-level-impl.md §Step 3` — features delivered: "`src/codegenie/plugins/cache.py`: BLAKE3 cache key `blake3(plugin_id || plugin_version || primitive || canonicalize(args) || repo_ctx.digest || scip.digest || dep_graph.digest || vuln_index.digest)`." + "`src/codegenie/plugins/cache_gc.py`: `BundleCacheGc` invoked once-a-day at orchestrator init via `.codegenie/cache/.gc-stamp`; operator-invoked via `codegenie cache prune`. (Gap 4 fix.)" + done criterion: "`codegenie cache prune` exits 0 and emits one `CacheGcCompleted` spanning event."
- **Existing code:**
  - `src/codegenie/cache/keys.py` — Phase 0/2 per-probe cache key derivation. **Do NOT edit** — Bundle cache is a sibling concept (plugin-level, not probe-level); read for the `\x1f` separator convention + `identity_hash` pattern only.
  - `src/codegenie/hashing.py` — `content_hash` / `bytes_hash` (or add one — do NOT import `blake3` directly; ADR-0001 hashing-chokepoint discipline).
  - `src/codegenie/plugins/bundle.py` (S3-04) — `Bundle` instances are the cached values.
  - `src/codegenie/vuln_index/index.py` (S3-02) — `VulnIndex.digest()` returns `BlobDigest("blake3:...")`; this story consumes it.
  - `src/codegenie/cli.py` (Phase 0; S3-03 added `vuln-index` group) — add `cache prune` subcommand.

## Goal

`codegenie.plugins.cache` exposes `compose_bundle_cache_key(...) -> str` (BLAKE3 over the 8-tuple including `vuln_index.digest`); `codegenie.plugins.cache_gc.BundleCacheGc` evicts entries older than `CODEGENIE_BUNDLE_CACHE_TTL_DAYS` (default `7`) and is invoked **once-a-day** at orchestrator init via `.codegenie/cache/.gc-stamp` amortization; `codegenie cache prune` CLI command invokes the same helper unconditionally and emits exactly one `CacheGcCompleted` spanning event with `bytes_reclaimed` and `entries_evicted`.

## Acceptance criteria

- [ ] New module `src/codegenie/plugins/cache.py` exports `compose_bundle_cache_key`, `BundleCacheStore`, `BundleCacheError`. Module docstring cites ADR-0008 §Decision (cache key includes `vuln_index.digest`) and the Gap 4 origin.
- [ ] `compose_bundle_cache_key(*, plugin_id: PluginId, plugin_version: SemverVersion, primitive: PrimitiveName, args_canonical: str, repo_ctx_digest: BlobDigest, scip_digest: BlobDigest, dep_graph_digest: BlobDigest, vuln_index_digest: BlobDigest) -> str` returns `blake3:<64-hex>`. All eight kwargs are required (no defaults — explicit at the call site). Inputs are concatenated in **fixed declared order** with `"\x1f"` separator (matches Phase 0 `identity_hash` convention) before BLAKE3.
- [ ] **`vuln_index_digest` participation test (ADR-0008 correctness):** holding the other seven inputs constant and varying ONLY `vuln_index_digest` produces a different key — single-row parametrize covers each of the eight inputs.
- [ ] **Determinism test:** two calls with byte-identical kwargs return byte-identical keys; sort-stable in input shape only (positional vs kwargs).
- [ ] `class BundleCacheStore:` on-disk store at `<cache_dir>/bundles/<hex>.json` (key prefix `blake3:` lives only in the key string, NOT in the filename — colon on Windows considered, but mostly for cleanliness):
  - `put(key: str, bundle: Bundle) -> None` — atomic write (`.tmp` then `os.rename`), `fcntl.flock(LOCK_EX)` on `<cache_dir>/bundles/.lock`, mode `0600`. Reuses the Phase 0 cache-store pattern.
  - `get(key: str) -> Bundle | None` — lock-free read; missing returns `None`; corrupt-on-read returns `None` + structlog warn (do NOT delete the file; operators may want to inspect — same discipline as `codegenie.eval.cache`).
- [ ] New module `src/codegenie/plugins/cache_gc.py` exports `BundleCacheGc`, `CacheGcResult`. Module docstring cites Gap 4.
- [ ] `class CacheGcResult(BaseModel)` frozen, `extra="forbid"`: `entries_evicted: int`, `bytes_reclaimed: int`, `cache_dir: str`, `ttl_days: int`.
- [ ] `class BundleCacheGc:`
  - `__init__(self, cache_dir: Path, *, event_emitter: Callable[[CacheGcCompletedEvent], None] | None = None)`.
  - `def run(self) -> CacheGcResult` — walk `<cache_dir>/bundles/*.json`, evict any with `mtime < now - ttl_days * 86400`, count bytes via `Path.stat().st_size` BEFORE unlink, return `CacheGcResult`. NEVER deletes `.lock` or `.gc-stamp`.
  - `def run_amortized(self) -> CacheGcResult | None` — reads `<cache_dir>/.gc-stamp` (ts float); if `time.time() - stamp_ts < 86400`, returns `None` (no-op); else calls `run()`, updates `.gc-stamp` to `time.time()`, returns the result. Atomically rewrites `.gc-stamp` via `.tmp` + `os.rename`.
- [ ] **TTL env knob:** `CODEGENIE_BUNDLE_CACHE_TTL_DAYS` env (default `7`); positive int; non-positive or non-int raises `BundleCacheError(reason="invalid_ttl_env")` at `BundleCacheGc.__init__` (fail loud, Rule 12).
- [ ] **CLI:** `codegenie cache prune [--cache-dir PATH]` click subcommand. Calls `BundleCacheGc(cache_dir).run()` (unconditional — operator override of the daily amortization) AND emits exactly one `CacheGcCompletedEvent` spanning event. Exits `0` on success.
- [ ] **`CacheGcCompletedEvent`** Pydantic with `frozen=True, extra="forbid"`: `event_type: Literal["cache_gc_completed"]`, `cache_dir: str`, `entries_evicted: int`, `bytes_reclaimed: int`, `ttl_days: int`, `trigger: Literal["amortized", "operator_cli"]`. The `trigger` discriminator distinguishes orchestrator-init calls from `codegenie cache prune` invocations.
- [ ] **Amortization test:** call `run_amortized()` twice in quick succession — second call returns `None` (no second eviction); `.gc-stamp` mtime is between the two calls.
- [ ] **24h-elapsed test:** monkeypatch `time.time` to return `t + 86401` on the second call; second call DOES run and updates `.gc-stamp`.
- [ ] **TTL applies correctly:** entry with `mtime` `8 days` old AND env `CODEGENIE_BUNDLE_CACHE_TTL_DAYS=7` is evicted; entry with `mtime` `6 days` old is kept.
- [ ] `codegenie cache prune` emits EXACTLY ONE `CacheGcCompletedEvent` (not zero, not two; integration-tested).
- [ ] `codegenie cache prune --help` exit code `0`.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. `src/codegenie/plugins/cache.py`:
   - `class BundleCacheError(CodegenieError)` markers-only.
   - `def compose_bundle_cache_key(**kwargs) -> str` — kw-only, validates all 8 present, concatenates with `"\x1f"`, returns `"blake3:" + bytes_hash(payload)`.
   - `class BundleCacheStore:` with `put` / `get`. Reuse the pattern from `src/codegenie/eval/cache.py` (atomic-rename + flock).
2. `src/codegenie/plugins/cache_gc.py`:
   - Module-level `_DEFAULT_TTL_DAYS: Final[int] = 7`, `_GC_STAMP_PATH = ".gc-stamp"`.
   - `def _read_ttl_days() -> int` — env-reader; fail loud.
   - `class CacheGcResult(BaseModel)`, `class CacheGcCompletedEvent(BaseModel)`.
   - `class BundleCacheGc:` with `run` and `run_amortized`.
3. `src/codegenie/cli.py`:
   - Add `@cli.group("cache")` and `@cache.command("prune")`. Wire `--cache-dir` (default `<cwd>/.codegenie/cache`), call `BundleCacheGc(...).run()`, emit `CacheGcCompletedEvent(trigger="operator_cli")` via a thin `EventLog` shim (or stash to file directly if S6-01 hasn't landed — leave a TODO that S6-04 wires the real `EventLog`).
4. Coordinate with S6-04: orchestrator's `__init__` calls `BundleCacheGc(cache_dir, event_emitter=event_log.emit_spanning).run_amortized()`. **Out of scope here** (this story exposes the helper; S6-04 wires it).

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/plugins/test_bundle_cache_key.py`

```python
import pytest
from codegenie.plugins.cache import compose_bundle_cache_key

class TestBundleCacheKey:
    def test_returns_blake3_prefixed_64_hex(self):
        # Arrange + Act
        key = compose_bundle_cache_key(
            plugin_id="vuln-node-npm", plugin_version="0.1.0",
            primitive="scip.refs", args_canonical='{"symbol":"x"}',
            repo_ctx_digest="blake3:" + "a"*64, scip_digest="blake3:" + "b"*64,
            dep_graph_digest="blake3:" + "c"*64, vuln_index_digest="blake3:" + "d"*64,
        )
        # Assert: well-formed; downstream cache-store relies on this shape
        assert key.startswith("blake3:") and len(key) == len("blake3:") + 64

    def test_determinism_byte_identical_keys(self):
        # Same inputs → same key; the determinism property test (S8-03) depends on this
        k1 = compose_bundle_cache_key(**_sample_kwargs())
        k2 = compose_bundle_cache_key(**_sample_kwargs())
        assert k1 == k2

    @pytest.mark.parametrize("vary", [
        "plugin_id", "plugin_version", "primitive", "args_canonical",
        "repo_ctx_digest", "scip_digest", "dep_graph_digest", "vuln_index_digest",
    ])
    def test_each_input_participates_in_the_key(self, vary):
        # ADR-0008 correctness: ALL 8 inputs invalidate the cache; vuln_index_digest is the
        # critic's Hidden Assumption #3 — stale CVE-feed cache hit MUST be impossible
        base = _sample_kwargs()
        modified = {**base, vary: base[vary] + "x"}
        assert compose_bundle_cache_key(**base) != compose_bundle_cache_key(**modified)

    def test_vuln_index_digest_change_invalidates_key(self):
        # Spotlight test for the load-bearing input — ADR-0008's reason for existing
        base = _sample_kwargs()
        before = compose_bundle_cache_key(**base)
        after = compose_bundle_cache_key(**{**base, "vuln_index_digest": "blake3:" + "f"*64})
        assert before != after
```

Test file: `tests/unit/plugins/test_bundle_cache_store.py`

```python
def test_put_then_get_round_trips(tmp_path, sample_bundle):
    store = BundleCacheStore(tmp_path)
    store.put("blake3:" + "a"*64, sample_bundle)
    assert store.get("blake3:" + "a"*64) == sample_bundle

def test_get_missing_returns_none(tmp_path):
    assert BundleCacheStore(tmp_path).get("blake3:" + "b"*64) is None

def test_corrupt_file_returns_none_and_warns(tmp_path, caplog):
    store = BundleCacheStore(tmp_path)
    (tmp_path / "bundles").mkdir(parents=True)
    (tmp_path / "bundles" / ("c"*64 + ".json")).write_text("{not valid json")
    assert store.get("blake3:" + "c"*64) is None
    # caplog contains warn event
```

Test file: `tests/unit/plugins/test_bundle_cache_gc.py`

```python
import time, os
from pathlib import Path
import pytest
from codegenie.plugins.cache_gc import BundleCacheGc, BundleCacheError, CacheGcCompletedEvent

class TestRun:
    def test_evicts_entry_older_than_ttl(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CODEGENIE_BUNDLE_CACHE_TTL_DAYS", "7")
        bundles = tmp_path / "bundles"; bundles.mkdir(parents=True)
        old = bundles / "old.json"; old.write_text("{}")
        os.utime(old, (time.time() - 8 * 86400,) * 2)
        fresh = bundles / "fresh.json"; fresh.write_text("{}")
        # Act
        result = BundleCacheGc(tmp_path).run()
        # Assert: old gone, fresh kept (intent: Gap 4 fix — keep cache bounded without surprises)
        assert not old.exists() and fresh.exists()
        assert result.entries_evicted == 1 and result.bytes_reclaimed >= 2

    def test_invalid_ttl_env_fails_loud(self, tmp_path, monkeypatch):
        # Rule 12: silent default-fallback is the wrong behavior here
        monkeypatch.setenv("CODEGENIE_BUNDLE_CACHE_TTL_DAYS", "not-an-int")
        with pytest.raises(BundleCacheError):
            BundleCacheGc(tmp_path).run()

    def test_never_deletes_lock_or_stamp(self, tmp_path):
        (tmp_path / ".gc-stamp").write_text(str(time.time() - 100 * 86400))
        (tmp_path / "bundles").mkdir(parents=True)
        (tmp_path / "bundles" / ".lock").write_text("")
        os.utime(tmp_path / ".gc-stamp", (time.time() - 100 * 86400,) * 2)
        BundleCacheGc(tmp_path).run()
        assert (tmp_path / ".gc-stamp").exists()
        assert (tmp_path / "bundles" / ".lock").exists()

class TestAmortization:
    def test_second_call_within_24h_is_noop(self, tmp_path):
        gc = BundleCacheGc(tmp_path)
        first = gc.run_amortized()
        second = gc.run_amortized()
        # Amortization: at most one GC per 24h at orchestrator init
        assert first is not None and second is None

    def test_24h_elapsed_runs_again(self, tmp_path, monkeypatch):
        gc = BundleCacheGc(tmp_path)
        gc.run_amortized()
        monkeypatch.setattr("time.time", lambda: time.time() + 86401)
        assert gc.run_amortized() is not None

    def test_gc_stamp_updated_atomically(self, tmp_path):
        gc = BundleCacheGc(tmp_path)
        gc.run_amortized()
        # .gc-stamp.tmp must NOT exist after a successful run (atomic rename)
        assert not (tmp_path / ".gc-stamp.tmp").exists()
        assert (tmp_path / ".gc-stamp").exists()
```

Test file: `tests/integration/cli/test_cache_prune.py`

```python
def test_cache_prune_emits_exactly_one_event(tmp_path, runner, capture_spanning_events):
    # Seed: one stale entry
    (tmp_path / "cache" / "bundles").mkdir(parents=True)
    stale = tmp_path / "cache" / "bundles" / "stale.json"
    stale.write_text('{"x":1}')
    os.utime(stale, (time.time() - 10 * 86400,) * 2)
    # Act
    result = runner.invoke(cli, ["cache", "prune", "--cache-dir", str(tmp_path / "cache")])
    # Assert: success + exactly one event + correct trigger discriminator
    assert result.exit_code == 0
    events = capture_spanning_events()
    assert len(events) == 1
    assert events[0].event_type == "cache_gc_completed"
    assert events[0].trigger == "operator_cli"
    assert events[0].entries_evicted == 1
```

### Green

Smallest impl: §Implementation outline; ~180 lines across the three modules + CLI wiring.

### Refactor

- Lift `_atomic_write_text(path, content)` from `BundleCacheGc.run_amortized`'s `.gc-stamp` update — same pattern as `BundleCacheStore.put`. Centralize in `codegenie.plugins.cache` or in a tiny `codegenie._fs_atomic` if more callers appear (do NOT preemptively extract).
- Add a `--dry-run` flag to `codegenie cache prune` that emits the event but doesn't unlink (operator audit; reasonable scope, but kick to a follow-up if it grows the PR).
- Wire the `CacheGcCompletedEvent` into S6-01's `WorkflowSpanningEvent` union once that story lands; for now it's a sibling Pydantic that S6-01 can absorb into its discriminated union additively.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/cache.py` | New module — `compose_bundle_cache_key`, `BundleCacheStore`, `BundleCacheError` |
| `src/codegenie/plugins/cache_gc.py` | New module — `BundleCacheGc`, `CacheGcResult`, `CacheGcCompletedEvent` (Gap 4 fix) |
| `src/codegenie/cli.py` | Add `cache prune` subcommand group |
| `tests/unit/plugins/test_bundle_cache_key.py` | Cache-key composer tests |
| `tests/unit/plugins/test_bundle_cache_store.py` | put/get/corrupt store tests |
| `tests/unit/plugins/test_bundle_cache_gc.py` | run + amortize + env tests |
| `tests/integration/cli/test_cache_prune.py` | End-to-end CLI + event-emission test |

## Out of scope

- **Editing `src/codegenie/cache/keys.py`** — Phase 0/2 probe-cache key is a sibling concept. Bundle cache is plugin-level and shipped under `codegenie.plugins.cache`. Surface the design parallel as a comment, do NOT unify.
- **`EventLog` infrastructure** — S6-01 owns `EventLog`; this story exports a `CacheGcCompletedEvent` Pydantic that S6-01 absorbs into `WorkflowSpanningEvent`. The CLI emits the event via a thin shim (write to `.codegenie/events/spanning/append.jsonl.zst` directly, or wire to a stub that S6-04 swaps).
- **`BundleBuilder` cache lookup integration** — S3-04 ships the builder; this story exposes the key composer + store. Wiring `BundleBuilder` to read/write via `BundleCacheStore` is the natural next step but lives in S6-04 (orchestrator wires it).
- **Per-plugin TTL knobs** — single `CODEGENIE_BUNDLE_CACHE_TTL_DAYS` is enough for Phase 3.
- **Cache-key versioning** — if the key shape changes (e.g., Phase 4 adds a 9th input), bump via additive ADR amendment to ADR-0008. Phase 3 does not version the key.
- **Bench / perf assertions** — `run()` over 10k entries should be fast (~100 ms) but no bench gate; S9-03 may add one.

## Notes for the implementer

- **`vuln_index_digest` is the load-bearing input.** ADR-0008 §Context (Hidden Assumption #3): the synthesis missed it; without it, a `codegenie vuln-index refresh` that re-classifies CVE-2024-21501 (severity widens) leaves stale Bundle cache entries that the orchestrator happily uses. The parametrize test row over `vuln_index_digest` is the single most important test in this story.
- **`.gc-stamp` lives at `<cache_dir>/.gc-stamp`, NOT `<cache_dir>/bundles/.gc-stamp`.** Keeps the bundles directory listing clean for operator `ls` debugging. Match what `phase-arch-design.md §Gap 4 improvement` specifies.
- **Atomic `.gc-stamp` write** — write `.gc-stamp.tmp` then `os.rename`. If the GC succeeded but the stamp write failed, the worst case is "GC runs again on next orchestrator init" — idempotent, acceptable; we still want the rename to be atomic so partial writes can't poison the read.
- **Filename: hex only, no `blake3:` prefix.** Matches the discipline in `src/codegenie/eval/cache.py` (see `S2-03` of Phase 6.5 for the precedent). Colon-in-filename is a Windows surprise even though Phase 3 is Linux/macOS.
- **`Bundle` Pydantic round-trip** — `BundleCacheStore.get` calls `Bundle.model_validate_json(...)`; this requires the `Bundle` shape from S3-04 to be JSON-roundtrip-safe. If `tuple[BundleEntry, ...]` doesn't round-trip cleanly, switch to `list[BundleEntry]` in `Bundle` and convert at boundaries — coordinate with S3-04 implementer.
- **`fail loud` on bad TTL env** — same rule as S3-02's `MAX_AGE_DAYS` env validator. Silent default-fallback hides operator typos.
- **`CacheGcCompletedEvent.trigger` discriminator** — `"amortized"` for orchestrator-init calls, `"operator_cli"` for `codegenie cache prune`. Phase 9 reads the trigger to distinguish background GC from operator-driven prune in spanning-stream queries.
- **The event MUST be emitted exactly once** — integration-tested. Two emits would corrupt the BLAKE3-chained spanning stream's append semantics; zero would let operators wonder if the prune actually happened. The CLI test is the canary.
- **Do not preemptively add a `--force` flag.** S6-04's orchestrator already calls `run_amortized()`; operators who want unconditional GC use `codegenie cache prune`. Two CLIs > one CLI with a flag.
- **Cite Gap 4 explicitly in module docstrings.** Reviewers reading `cache_gc.py` for the first time should see "This module IS the Gap 4 fix from `docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md §Gap analysis`." Saves a confused re-read.
