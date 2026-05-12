# Story S1-08 — Pre-dispatch input-snapshot pass (Gap 1)

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready
**Effort:** M
**Depends on:** S1-06, S1-07
**ADRs honored:** ADR-0002

## Context

The mtime-based memo key from S1-07 is TOCTOU-sensitive across the lockfile read in `NodeManifestProbe`: `package.json` can be edited mid-gather between the moment its `declared_inputs` content-hash is computed (cache-key derivation) and the moment the memo is consulted, producing a cache entry whose key reflects the old bytes but whose data was parsed from the new bytes. The fix per `phase-arch-design.md §"Gap analysis" Gap 1`: pin the per-probe input snapshot at **coordinator dispatch time**, expose it as `ctx.input_snapshot: frozenset[InputFingerprint]`, and flip the memo key from live `os.stat` to `input_fingerprint.content_hash`.

This is **load-bearing for Phase 14's** webhook-driven continuous gather, where mid-gather concurrent edits are the norm. The cost is ~5 ms of pre-dispatch I/O for the 1k-file fixture; the benefit is coherence between cache keys and parsed bytes.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Gap analysis" Gap 1` — full rationale, the seam: coordinator computes `(path, mtime_ns, size, content_hash)` once before dispatch.
  - `../phase-arch-design.md §"Component design" #3` — `ParsedManifestMemo`'s key changes from `(abspath, mtime_ns, size)` to `(content_hash,)` sourced from the snapshot.
  - `../phase-arch-design.md §"Data model"` — `InputFingerprint` shape (already declared in S1-06).
  - `../phase-arch-design.md §"Edge cases"` row 16 — mid-gather edit re-parses; this story preserves that behavior on a per-probe basis (the new probe call sees the new snapshot in the *next* dispatch wave).
  - `../phase-arch-design.md §"Process view"` — the sequence: Coordinator constructs memo, then per probe computes `input_snapshot`, then dispatches.
- **Phase ADRs:**
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — Consequences §: "The Gap #1 improvement in `phase-arch-design.md` is documented as a future amendment to this ADR if Phase 14's concurrent-gather threat model demands it." This story lands the improvement now.
- **Source design:**
  - `../final-design.md §"Synthesis ledger"` row referencing the input-snapshot.
- **Existing code:**
  - `src/codegenie/coordinator/coordinator.py` — `gather()` builds `ProbeContext` per probe; this story adds the snapshot computation before `ctx` construction.
  - `src/codegenie/coordinator/parsed_manifest_memo.py` (S1-07) — key shape flips to `content_hash`.
  - `src/codegenie/coordinator/input_snapshot.py` (S1-06) — `InputFingerprint` NamedTuple.
  - `src/codegenie/hashing.py` (Phase 0) — blake3 hashing utilities; reuse the same algorithm.

## Goal

Coordinator computes `frozenset[InputFingerprint]` for each probe's `declared_inputs` **once before dispatch**, freezes it on `ctx.input_snapshot`, and `ParsedManifestMemo` keys parsed dicts by `content_hash` (not live `os.stat`), closing the TOCTOU window between cache-key derivation and probe parse.

## Acceptance criteria

- [ ] `src/codegenie/coordinator/coordinator.py` — `gather()` adds a `_compute_input_snapshot(probe, snapshot, repo_root) -> frozenset[InputFingerprint]` helper called **once before each probe's dispatch**.
- [ ] The helper walks `probe.declared_inputs` globs, resolves matching files under `repo_root`, opens each with `O_NOFOLLOW`, reads bytes (capped at the probe-relevant safe-parse cap if a parser is involved, or at 50 MB default), computes blake3 content hash via `src/codegenie/hashing.py`, records `(path, mtime_ns, size, content_hash)`.
- [ ] The returned `frozenset[InputFingerprint]` is assigned to `ctx.input_snapshot` for that probe's `ProbeContext`.
- [ ] `ParsedManifestMemo.get(path)` flips its cache key from `(abspath, mtime_ns, size)` to `(content_hash,)` — looking the `content_hash` up from the **caller's `ctx.input_snapshot`** is the contract.
- [ ] Memo signature changes additively: `get(self, path: Path, *, content_hash: str | None = None) -> Mapping | None`. If `content_hash` is `None`, fall back to the old key shape (preserves S1-07's tests + non-coordinator construction paths).
- [ ] Coordinator passes `content_hash` when calling `memo.get` — extends the wiring: `ctx.parsed_manifest = functools.partial(memo.get, content_hash=<looked-up from snapshot>)` or equivalent helper. Document the chosen approach in the coordinator commit message.
- [ ] If `ctx.parsed_manifest(path)` is called for a path not in `ctx.input_snapshot`, fall back to direct `safe_json.load` semantics (memo returns `None`); the probe still parses correctly.
- [ ] Coordinator emits `probe.input_snapshot.computed` structlog event per probe with `entries: int`, `total_bytes: int`, `wall_clock_ms: int`.
- [ ] Unit test `tests/unit/coordinator/test_input_snapshot.py`: pre-dispatch fingerprint computation; frozen-set membership; memo key derives from `content_hash` (not live `os.stat`); mid-test mtime bump on the file does NOT trigger memo miss within the same dispatch (snapshot is frozen).
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Add `_compute_input_snapshot(probe, repo_root) -> frozenset[InputFingerprint]` to `coordinator/coordinator.py` (or a new private module under `coordinator/`).
2. Implement file enumeration via `pathlib.Path.glob` over `probe.declared_inputs`; for each match, `os.open(..., O_NOFOLLOW)` → `os.fstat` → `os.read` → blake3 → close. Cap individual file size at 50 MB (lockfile cap) by default; if exceeded, still record `(path, mtime_ns, size, content_hash="<oversize>")` and emit a warning event — the probe itself will refuse to parse it via its own `safe_parse` cap.
3. In `gather()`, before each probe's dispatch: compute the snapshot, build `ctx` with `input_snapshot=snapshot`, hand `memo` and the snapshot to the probe.
4. Wire `ctx.parsed_manifest` so it carries `content_hash` lookup. Two clean options:
   - **Option A (preferred):** `ctx.parsed_manifest = lambda p: memo.get(p, content_hash=_lookup_hash(ctx.input_snapshot, p))`.
   - **Option B:** Coordinator passes a `partial`-shaped closure; equivalent.
5. Update `ParsedManifestMemo.get` signature additively (with default).
6. Update tests in S1-07's `test_parsed_manifest_memo.py` — content_hash-keyed cases stay; the old `(abspath, mtime_ns, size)` cases continue to work via the default fallback.

## TDD plan — red / green / refactor

### Red — failing test first

Test file: `tests/unit/coordinator/test_input_snapshot.py`.

```python
# tests/unit/coordinator/test_input_snapshot.py
import json
import time
from pathlib import Path

import pytest

from codegenie.coordinator.coordinator import _compute_input_snapshot  # type: ignore[attr-defined]
from codegenie.coordinator.input_snapshot import InputFingerprint


class _FakeProbe:
    name = "x"
    declared_inputs = ["package.json", "pnpm-lock.yaml"]


def test_pre_dispatch_snapshot_contains_all_declared_inputs(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}))
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    snap = _compute_input_snapshot(_FakeProbe(), tmp_path)
    paths = {fp.path for fp in snap}
    assert (tmp_path / "package.json").as_posix() in paths
    assert (tmp_path / "pnpm-lock.yaml").as_posix() in paths

def test_snapshot_is_frozenset_of_input_fingerprints(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    snap = _compute_input_snapshot(_FakeProbe(), tmp_path)
    assert isinstance(snap, frozenset)
    for fp in snap:
        assert isinstance(fp, InputFingerprint)

def test_snapshot_content_hash_changes_with_content(tmp_path):
    p = tmp_path / "package.json"
    p.write_text("{}")
    snap1 = _compute_input_snapshot(_FakeProbe(), tmp_path)
    h1 = {fp.path: fp.content_hash for fp in snap1}
    p.write_text('{"name": "x"}')
    snap2 = _compute_input_snapshot(_FakeProbe(), tmp_path)
    h2 = {fp.path: fp.content_hash for fp in snap2}
    assert h1[p.as_posix()] != h2[p.as_posix()]

def test_memo_key_uses_content_hash_not_live_stat(tmp_path):
    # Gap 1 closure: file mtime bumped mid-gather; memo continues to serve the snapshotted parse
    from codegenie.coordinator.parsed_manifest_memo import ParsedManifestMemo
    p = tmp_path / "package.json"
    p.write_text(json.dumps({"name": "x"}))
    memo = ParsedManifestMemo(tmp_path)
    snap = _compute_input_snapshot(_FakeProbe(), tmp_path)
    fp = next(fp for fp in snap if Path(fp.path).name == "package.json")
    a = memo.get(p, content_hash=fp.content_hash)
    # bump mtime; same content_hash since content unchanged
    time.sleep(0.01)
    p.touch()
    b = memo.get(p, content_hash=fp.content_hash)
    # identity: snapshot pinned the parse
    assert a is b
```

Run; confirm failures (helper doesn't exist, memo signature missing `content_hash` kwarg). Commit as red.

### Green — minimal impl

- `_compute_input_snapshot(probe, repo_root)`:
  - Globs each `declared_inputs` pattern under `repo_root` (use `Path.glob` with `**` support).
  - For each file: `os.open` with `O_NOFOLLOW`, `os.fstat`, read up to 50 MB, blake3 hex, close.
  - Returns `frozenset` of `InputFingerprint`.
  - Catch `OSError` (symlink refused, permission) per-file → record `content_hash="<refused>"` and continue (the probe will see no successful parse and degrade).
- `ParsedManifestMemo.get`: add `content_hash: str | None = None` kwarg. If provided, key is `(content_hash,)`; else fall back to S1-07's `(abspath, mtime_ns, size)`.
- Coordinator: compute snapshot per probe; build `ctx.input_snapshot`; wrap `memo.get` in a closure binding the right `content_hash` per path.

### Refactor — clean up

- Module docstring on the helper: name Gap 1, ADR-0002 (Consequences §), and the load-bearing role for Phase 14.
- Coordinator: keep the snapshot logic in `_compute_input_snapshot` rather than inlining — easier to swap to a parallelized version in Phase 14.
- Logged event includes `wall_clock_ms` so the bench-canary (S6-02) can track snapshot cost separately from probe cost.
- Note that `Path.glob` is one-shot; if `probe.declared_inputs` contains overlapping globs, the resulting set deduplicates by `(path, ...)` because `InputFingerprint` is a `NamedTuple` and `frozenset` dedups by equality.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/coordinator/coordinator.py` | Add `_compute_input_snapshot`; wire `ctx.input_snapshot` per probe; wrap `memo.get` with `content_hash` lookup |
| `src/codegenie/coordinator/parsed_manifest_memo.py` | Add `content_hash: str \| None = None` kwarg; flip key shape when present |
| `tests/unit/coordinator/test_input_snapshot.py` | New — 4 unit tests |
| `tests/unit/coordinator/test_parsed_manifest_memo.py` | Augment with one content-hash-keyed test (don't remove the old ones) |

## Out of scope

- **Per-probe raw-artifact budget** — S1-09.
- **Cache-key derivation in `CacheStore.put` using `input_snapshot`** — Phase 0's `CacheStore` already derives keys from `declared_inputs` content hashes (S3-01 from Phase 0). This story does not edit `CacheStore`; the `input_snapshot` is what flows into the same hashing function the coordinator already uses pre-dispatch. If those hashes weren't already content-based, mark a follow-up in the PR.
- **Parallelizing snapshot computation** — Phase 14 may parallelize per-probe snapshot computation across worker threads. Phase 1's sequential pre-dispatch pass is correct and cheap (≤ 50 ms p50 on the 1k-file fixture).
- **Concurrent re-snapshotting on long-running gathers** — out of scope; Phase 14 owns it.

## Notes for the implementer

- **Coordinator is the only file outside `coordinator/` that this story edits.** Memo is already coordinator-local. The helper lives in `coordinator/coordinator.py`; alternatively in a sibling `coordinator/snapshot.py` if that file is busy.
- **`Path.glob("**/*.yaml")`** is recursive and uses `**` — confirm Python 3.11+ semantics. For non-glob entries like `"package.json"`, do a single `Path.exists()` check rather than glob.
- **`O_NOFOLLOW` parity with safe_json/safe_yaml:** the snapshot pass uses the same open semantics. A symlinked declared input is recorded as `content_hash="<refused>"`. The probe's own parse will also refuse the file. Together: the cache key is coherent (it includes the refusal) AND the probe degrades to `confidence: low`.
- **`hashing.py` from Phase 0** likely exposes a `blake3_file(path) -> str` or `blake3_bytes(data) -> str`. Reuse it — don't re-implement hashing here.
- **50 MB read cap during snapshotting:** if a declared input is > 50 MB, you still need a stable `content_hash` for cache-key derivation. Two options: (a) hash only the first 50 MB and prefix with `"<truncated-50mb>:"`; (b) record `content_hash="<oversize>"` and let the probe's safe_parse raise `SizeCapExceeded`. Option (b) is simpler and per Rule 2 (Simplicity First). Use it.
- **The `wall_clock_ms` field on the event** is the entire snapshot computation for the probe — not per-file. The bench-canary (S6-02) reads this.
- **Per Rule 12:** if the snapshot fails to enumerate any declared input (e.g., `OSError` other than the symlink case), do NOT fall back to "snapshot is empty." Raise — the gather can't proceed coherently. The CLI's top-level catch handles it.
- **Coordinator wiring:** `ctx.parsed_manifest` is a callable. The wrapped form is:
  ```python
  def _parsed_manifest_for_ctx(snapshot: frozenset[InputFingerprint], memo: ParsedManifestMemo):
      by_path = {fp.path: fp.content_hash for fp in snapshot}
      def get(path: Path) -> Mapping | None:
          return memo.get(path, content_hash=by_path.get(str(path.resolve())))
      return get
  ```
  Per Rule 2: this is six lines; don't over-abstract.
