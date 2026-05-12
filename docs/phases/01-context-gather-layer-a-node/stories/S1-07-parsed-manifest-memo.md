# Story S1-07 — `ParsedManifestMemo` per-gather coordinator memo

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready
**Effort:** M
**Depends on:** S1-02, S1-06
**ADRs honored:** ADR-0002

## Context

`ParsedManifestMemo` is the in-coordinator per-gather memo that eliminates 3× `package.json` parsing across `LanguageDetectionProbe` (extended), `NodeBuildSystemProbe`, `NodeManifestProbe`, and `TestInventoryProbe`. It lives in process memory only — never written to disk, never crossing `OutputSanitizer` or `_ProbeOutputValidator` (Phase 0 chokepoints unchanged). Its key derives from the pre-dispatch `InputFingerprint.content_hash` (S1-08 lands the snapshot pass; this story's first iteration falls back to `(absolute_path, mtime_ns, size)` and S1-08 flips the key to `content_hash`).

Allowlist for Phase 1: `{"package.json"}`. Each probe defensive-checks `ctx.parsed_manifest is not None` and falls back to direct `safe_json.load`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #3` — full interface, allowlist, lifetime, immutability via `MappingProxyType`, failure-doesn't-cache semantics.
  - `../phase-arch-design.md §"Data model"` — class skeleton (`__init__(repo_root)`, `_cache` dict, `get(path)`).
  - `../phase-arch-design.md §"Edge cases"` rows 12, 16 — memo-is-None fallback; mid-gather edit re-parses.
  - `../phase-arch-design.md §"Harness engineering" → "Logging strategy"` — `probe.memo.hit` / `probe.memo.miss` events.
  - `../phase-arch-design.md §"Process view"` — coordinator constructs memo at gather start, exposes via `ProbeContext.parsed_manifest=memo.get`.
- **Phase ADRs:**
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — full design rationale; allowlist additive in future phases.
- **Source design:**
  - `../final-design.md §"Components" #2` — design statement; explicit rejection of the msgpack side-channel.
- **Existing code:**
  - `src/codegenie/parsers/safe_json.py` (S1-02) — memo parses through this.
  - `src/codegenie/probes/base.py` (S1-06) — `ProbeContext.parsed_manifest` exists.
  - `src/codegenie/coordinator/coordinator.py` (Phase 0) — `gather()` is the integration point; constructs the memo and injects on every `ProbeContext`.
  - `src/codegenie/errors.py` (S1-01) — typed exceptions; memo does NOT cache on parse failure.

## Goal

Ship `src/codegenie/coordinator/parsed_manifest_memo.py` with a `ParsedManifestMemo` class keyed initially by `(absolute_path, mtime_ns, size)` (flipped to `input_fingerprint.content_hash` in S1-08), allowlisted to `{"package.json"}`, returning `MappingProxyType`-wrapped parsed dicts, emitting `probe.memo.{hit,miss}` events; coordinator constructs one per `gather()` and injects `ctx.parsed_manifest = memo.get` on every `ProbeContext`.

## Acceptance criteria

- [ ] `src/codegenie/coordinator/parsed_manifest_memo.py` exports `ParsedManifestMemo` with `__init__(self, repo_root: Path)` and `get(self, path: Path) -> Mapping[str, JSONValue] | None`.
- [ ] `get(path)` returns `None` if `path.name` is not in the allowlist `{"package.json"}`.
- [ ] First call for an allowlisted path parses via `safe_json.load(path, max_bytes=5_242_880)`; result wrapped in `MappingProxyType`; cached under `(absolute_path, mtime_ns, size)`.
- [ ] Subsequent call with same key returns the **same instance** (identity check, `is`) — emits `probe.memo.hit`.
- [ ] mtime or size change on the file → cache miss → re-parse — emits `probe.memo.miss`.
- [ ] `safe_json.load` raising any `CodegenieError` does **not** cache; the exception propagates; next call retries.
- [ ] Coordinator (`src/codegenie/coordinator/coordinator.py`) constructs one memo per `gather()` invocation and assigns `ctx.parsed_manifest = memo.get` on every `ProbeContext` it builds.
- [ ] Memo never writes to disk; never invokes `OutputSanitizer` or `_ProbeOutputValidator` (verify in test via monkeypatch of those names — assert they're not entered).
- [ ] Unit tests: first-call parse, second-call same-instance (`a is b`), mtime-change re-parse, size-change re-parse, parse-failure-no-cache, non-allowlisted path returns `None`, allowlist case-sensitivity (`Package.json` is not in allowlist).
- [ ] Integration-leaning unit test: coordinator wires `ctx.parsed_manifest` correctly across two probes.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create `src/codegenie/coordinator/parsed_manifest_memo.py`:
   ```python
   ALLOWLIST: Final[frozenset[str]] = frozenset({"package.json"})

   class ParsedManifestMemo:
       def __init__(self, repo_root: Path) -> None:
           self._repo_root = repo_root.resolve()
           self._cache: dict[tuple[str, int, int], MappingProxyType] = {}

       def get(self, path: Path) -> Mapping[str, JSONValue] | None:
           if path.name not in ALLOWLIST:
               return None
           try:
               st = path.stat()
           except FileNotFoundError:
               return None
           key = (str(path.resolve()), st.st_mtime_ns, st.st_size)
           hit = self._cache.get(key)
           if hit is not None:
               structlog.get_logger().info("probe.memo.hit", path=str(path), allowlist_match="package.json")
               return hit
           # miss
           parsed = safe_json.load(path, max_bytes=5_242_880)  # may raise; do NOT cache failures
           wrapped = MappingProxyType(parsed)
           self._cache[key] = wrapped
           structlog.get_logger().info("probe.memo.miss", path=str(path), allowlist_match="package.json")
           return wrapped
   ```
2. Edit `src/codegenie/coordinator/coordinator.py` (Phase 0 file — surgical addition only):
   - Import `ParsedManifestMemo`.
   - In `gather(...)` after constructing the runtime state, construct one memo: `memo = ParsedManifestMemo(snapshot.root)`.
   - Where `ProbeContext(...)` is built, set `parsed_manifest=memo.get`.
3. Write unit tests in `tests/unit/coordinator/test_parsed_manifest_memo.py`.

## TDD plan — red / green / refactor

### Red — failing test first

Test file: `tests/unit/coordinator/test_parsed_manifest_memo.py`.

```python
# tests/unit/coordinator/test_parsed_manifest_memo.py
import json
import os
import time
from pathlib import Path
from types import MappingProxyType

import pytest

import codegenie.errors as e
from codegenie.coordinator.parsed_manifest_memo import ParsedManifestMemo


def _write(tmp_path: Path, name: str, payload: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload))
    return p

def test_first_call_parses_and_returns_mappingproxy(tmp_path):
    p = _write(tmp_path, "package.json", {"name": "x"})
    memo = ParsedManifestMemo(tmp_path)
    out = memo.get(p)
    assert isinstance(out, MappingProxyType)
    assert out["name"] == "x"

def test_second_call_returns_same_instance(tmp_path):
    p = _write(tmp_path, "package.json", {"name": "x"})
    memo = ParsedManifestMemo(tmp_path)
    a = memo.get(p)
    b = memo.get(p)
    # identity matters: this is the contract the warm-path test reads
    assert a is b

def test_mtime_change_triggers_reparse(tmp_path):
    p = _write(tmp_path, "package.json", {"name": "x"})
    memo = ParsedManifestMemo(tmp_path)
    a = memo.get(p)
    # bump mtime; rewrite same size, different content
    time.sleep(0.01)
    p.write_text(json.dumps({"name": "y"}))
    b = memo.get(p)
    assert a is not b
    assert b["name"] == "y"

def test_size_change_triggers_reparse(tmp_path):
    p = _write(tmp_path, "package.json", {"name": "x"})
    memo = ParsedManifestMemo(tmp_path)
    a = memo.get(p)
    p.write_text(json.dumps({"name": "xxxxxxxxxxxxxxxxx"}))
    b = memo.get(p)
    assert a is not b

def test_non_allowlisted_path_returns_none(tmp_path):
    p = _write(tmp_path, "yarn.lock", {"k": 1})
    memo = ParsedManifestMemo(tmp_path)
    assert memo.get(p) is None

def test_parse_failure_does_not_cache(tmp_path):
    p = tmp_path / "package.json"
    p.write_text("{not json}")
    memo = ParsedManifestMemo(tmp_path)
    with pytest.raises(e.MalformedJSONError):
        memo.get(p)
    # fix the file; next call should re-parse, not return a stale value
    p.write_text(json.dumps({"name": "ok"}))
    out = memo.get(p)
    assert out["name"] == "ok"

def test_emits_memo_hit_and_miss_events(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("sys.stderr.isatty", lambda: False)
    from codegenie.logging import configure_logging
    configure_logging(verbose=False)
    p = _write(tmp_path, "package.json", {"name": "x"})
    memo = ParsedManifestMemo(tmp_path)
    memo.get(p)  # miss
    memo.get(p)  # hit
    err = capsys.readouterr().err
    assert "probe.memo.miss" in err
    assert "probe.memo.hit" in err
```

Coordinator-wiring smoke test (integration-leaning unit test):

```python
# tests/unit/coordinator/test_coordinator_injects_memo.py
# Use the Phase 0 coordinator construction path; assert ctx.parsed_manifest is callable.
import pytest
from codegenie.coordinator.coordinator import Coordinator
# ... build the minimum Snapshot + Config + Probes list to invoke gather()
# Assert: a stub probe in the registry sees ctx.parsed_manifest is not None and callable.
```

Run; confirm failures. Commit as red.

### Green — minimal impl

Implement `ParsedManifestMemo` per the outline. Wire the coordinator. The coordinator change is one variable construction (`memo = ParsedManifestMemo(snapshot.root)`) plus passing `memo.get` as `parsed_manifest` to every `ProbeContext` instantiation. Per Rule 3 (Surgical Changes), don't touch any other coordinator state.

### Refactor — clean up

- Module docstring naming `phase-arch-design.md §"Component design" #3`, ADR-0002, the explicit msgpack rejection from `final-design.md`.
- Allowlist is a `Final[frozenset[str]]` at module scope — Phase 2 extends additively.
- `get()`'s `try: stat = path.stat()` block — only catch `FileNotFoundError`; let other `OSError`s bubble (the caller has more context).
- Note (comment + ADR link): the S1-08 follow-up flips the key from `(path, mtime_ns, size)` to `content_hash`. Mark the `key = (...)` line with `# S1-08: this becomes (content_hash,) sourced from ctx.input_snapshot`.
- The structlog events use literal `"probe.memo.hit"` / `"probe.memo.miss"`. S1-10 lifts to constants.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/coordinator/parsed_manifest_memo.py` | New — `ParsedManifestMemo` class |
| `src/codegenie/coordinator/coordinator.py` | Surgical: construct memo per `gather()`, inject `memo.get` on every `ProbeContext` |
| `tests/unit/coordinator/test_parsed_manifest_memo.py` | New — 7 unit tests |
| `tests/unit/coordinator/test_coordinator_injects_memo.py` | New — wiring smoke test |

## Out of scope

- **Pre-dispatch input-snapshot pass (Gap 1)** — S1-08 lands the `(content_hash,)`-keyed flip and the `ctx.input_snapshot` computation.
- **Wave-1 prelude ADR** — `phase-arch-design.md §"Open implementation questions"` #11 leaves ADR creation as judgment in S1-07. **Recommendation:** skip ADR creation here; the Wave-1 prelude is documented coordinator behavior already, not a new commitment. File an ADR in Phase 2 if `IndexHealthProbe` extends the prelude to multi-probe.
- **Allowlist beyond `{"package.json"}`** — Phase 2 extends.
- **Cross-gather caching** — by design, never. Per-gather memo discarded at gather end.

## Notes for the implementer

- **`MappingProxyType` only wraps the top level.** Nested dicts/lists are returned by reference. Probes treat the result as `Mapping`-typed; mypy will flag mutation, but a determined caller can still `dict(out["scripts"])["new"] = "x"` — that's runtime convention. Do not deep-freeze; the perf cost isn't justified.
- **Identity check (`a is b`)** is the contract for warm-path tests in S2-04 (`probe.memo.hit` count == 1). Don't replace `MappingProxyType` with a new instance on each call.
- **Failure must not cache.** Per ADR-0002: "if `safe_json.load` raises, the memo does *not* cache the result; the next probe retries and sees the same error." This is the contract. Use a `try` around the parse, but only insert into `_cache` after success.
- **Memo does NOT cross `OutputSanitizer`.** Verify by reading the coordinator's `gather()` flow — `ProbeContext.parsed_manifest=memo.get` is a callable handed *to* probes, not a `ProbeOutput`-shaped artifact written *from* probes. The sanitizer only sees `ProbeOutput` bytes; this seam is invisible to it. Adding an assertion to the wiring test is paranoid but warranted: `monkeypatch.setattr(OutputSanitizer, "scrub", raise_on_call)` — confirm it's not called during `memo.get`.
- **Key shape for now** is `(absolute_path, mtime_ns, size)`. S1-08 flips this to `content_hash` sourced from the pre-dispatch snapshot. Be explicit in this story's commit message that S1-08 is the planned follow-up — don't make the flip here.
- **Threading:** Phase 0 coordinator uses asyncio + a bounded worker pool, but probe `run()` calls happen on the event loop (`asyncio.to_thread` is used for blocking I/O). `ParsedManifestMemo` is **not** thread-safe; calls happen serially in Phase 0/1's model. Document this in the docstring: "Not thread-safe; per-gather coordinator scope assumes serial access." If Phase 14 introduces real concurrency, that phase wraps with a lock.
- **Coordinator change is the second Phase-0 file edit** (after `probes/base.py` in S1-06). The other allowed edit is `exec.py` (S1-10). No other Phase-0 source files change in Step 1.
