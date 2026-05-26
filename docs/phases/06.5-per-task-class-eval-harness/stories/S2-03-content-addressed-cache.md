# Story S2-03 — Content-addressed score cache (`get` / `put` / `gc`)

**Step:** Step 2 — Build harness internals: loader, cache, audit chain extension, canary + cost-tag shims
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-02
**ADRs honored:** Phase 0 ADR-0001 (`0001-cache-content-hash-algorithm.md` — single chokepoint for BLAKE3 + SHA-256), Phase 0 ADR-0011 (directory-permissions model — `0700` dirs / `0600` files), Phase 6.5 ADR-0005 (`cassette_canary_pin` participates in cache-key composition)

## Validation notes (phase-story-validator, 2026-05-26)

Hardened from the `Ready` draft after four parallel critics (Coverage, Test-Quality, Consistency, Design-Patterns). Full report: [`_validation/S2-03-content-addressed-cache.md`](_validation/S2-03-content-addressed-cache.md).

Highlights of what changed:

- **Dead lift removed.** `bytes_hash` stub deleted from "Files to touch" and Outline — `codegenie.hashing.content_hash_bytes` already exists (Phase 0 S2-03); the cache must call it, not edit `hashing.py`.
- **`os.rename` → `os.replace`** everywhere. Matches Phase 0 `cache/store.py:138` precedent (Rule 11; cross-platform-safe; overwrites atomically when target exists).
- **Filename indecision resolved.** On-disk filename is `<cache_dir>/<64-hex>.json` (hex only; the `blake3:` prefix lives only inside the `CacheKey` string, never on disk). Hedge deleted from Outline §3.
- **Newtype + smart constructor.** `CacheKey = NewType("CacheKey", str)` in `codegenie/types/identifiers.py`; `compose_cache_key(inputs: CacheKeyInputs) -> CacheKey` (frozen `CacheKeyInputs` dataclass) replaces the six-kwarg signature. CLAUDE.md *"Never raw `str` for domain IDs"* + *"Extension by addition — no silent edits"* applied at the function-arg boundary (adding a future input fails type-check at every call site, loudly).
- **AC additions for boundary conditions the runner will hit on day one:** `put` creates `cache_dir` (and parents) if missing; `get` on a missing `cache_dir` returns `None` without warning; `gc` on a missing or empty `cache_dir` returns `0` and never raises; `gc` boundary tests at `retain_days * 86400` second granularity; `gc` skips both `.lock` *and* `*.tmp` orphans; overwrite (`put(k, v2)` after `put(k, v1)`) is atomic and `get` then returns `v2`; `OSError` from `os.replace` propagates (never swallowed) and leaves the prior `<key>.json` byte-identical.
- **Fail-loud disciplines as ACs.** File-mode `0o600` is asserted post-`put` on both `<key>.json` and `.lock` (not just `<key>.tmp`); `put` re-chmods after `os.replace` to defeat CI restore-time umask flattening (Phase 0 ADR-0011 + Phase 0 `cache/store.py:380`).
- **Mutation-resistance rewrites of the TDD plan.**
  - Lock test (was: "two threads write valid JSON") rewritten to probe `flock` state directly with `LOCK_EX | LOCK_NB` from a sibling fd — the previous test passes even if `flock` is deleted (because `BenchScore` JSON fits under `PIPE_BUF`).
  - Atomicity test (was: patch `os.rename` and assert suffixes) rewritten to observe filesystem state at the moment of `os.replace` — the previous test passes for a degenerate `replace(path, path)`.
  - `compose_cache_key` tests (were: `...` placeholders) rewritten with six disjoint role-encoding values and a positional-swap parametrize over `itertools.combinations(range(6), 2)` — the previous tests cannot catch a `(case_digest, sut_digest)` swap mutation.
  - Corrupt-then-recover round-trip added (catches the "short-circuit if file exists" mutation).
  - `structlog.testing.capture_logs()` replaces `caplog` and asserts both `cache_key` and `path` kwargs (matches Phase 0 cache-store test convention).
  - Property test on `compose_cache_key` determinism over random shapes added (AC mandates Hypothesis; previous TDD plan was a fixed-input call).
  - ADR-0005 scoped-invalidation test added: rotating case A's pin must not change case B's key.
- **`compose_cache_key` input contract documented.** Pure bytes-to-hex; does not validate. Inputs must not contain `\x1f` (the unit separator); callers (S2-02 loader, Runner) own input-shape validation. Arity-byte omitted intentionally (kw-only signature pins arity at exactly six) — divergence from `hashing.identity_hash` documented in Notes.
- **Architectural divergence surfaced, not silently chosen.** Two intentional Phase-0 divergences are now explicit: (a) free-function module surface vs the arch class diagram's `class Cache`; (b) `fcntl.flock` vs Phase 0's `O_APPEND`+`PIPE_BUF` atomicity (BenchScore JSON exceeds 4 KB). See Notes for implementer.
- **Goal sentence widened** to include `compose_cache_key` (consistency with `__all__` and AC list).

## Context

The runner's per-case cache makes `lower_bound_95` computation cheap on warm reruns: a 10-case cold run is ≤12 min; the warm rerun must be ≤8 s (`High-level-impl.md §Step 5` done criterion). The cache is **content-addressed** under `BLAKE3(case_digest || sut_digest || rubric_digest || cassette_corpus_digest || harness_version || cassette_canary_pin)` (`phase-arch-design.md §Component design — cache.py`). The two load-bearing disciplines are (a) **atomic writes** — `<hex>.tmp` then `os.replace` to `<hex>.json` so a mid-write crash leaves the previous value intact (`phase-arch-design.md §Edge cases #16`; `os.replace` per Phase 0 `cache/store.py:138` precedent — cross-platform-safe and overwrites atomically when target exists); and (b) **corrupt-on-read is a miss, not a failure** — a truncated cache file emits a structlog warning and re-executes the case, never poisoning the run.

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
  - `src/codegenie/hashing.py` (Phase 0 S2-03) — `content_hash_bytes(b: bytes) -> "blake3:<hex>"` **already exists** at line ~85; reuse it. **Do not** import `blake3` directly (ADR-0001 chokepoint). **Do not** add a `bytes_hash` helper — `content_hash_bytes` is the right primitive.
  - `src/codegenie/cache/store.py` — Phase 0 atomic-write precedent. Mirror its shape: `_atomic_write_bytes` uses `os.replace` (not `os.rename`), pid+`secrets.token_hex(4)` tmp-suffix discipline, `os.write` + `os.fsync` + `os.close` + `os.replace` sequence, and a post-write `os.chmod` to defeat CI `actions/cache` umask flattening (Phase 0 ADR-0011 + `cache/store.py:380`).
  - `src/codegenie/types/identifiers.py` — newtype home. This story adds `CacheKey = NewType("CacheKey", str)` here (mirroring `ProbeId`, `IndexName`).

## Goal

`codegenie.eval.cache` exposes `compose_cache_key`, `get`, `put`, `gc` with content-addressed keys; `put` is atomic (`os.replace`) under `fcntl.flock`; `get` is lock-free and treats corrupt files as miss with a structured warning; `gc` evicts entries older than `retain_days` by mtime and skips both `.lock` and `*.tmp` orphans.

## Acceptance criteria

### Typed surface

- [ ] **Newtype + smart constructor.** `codegenie/types/identifiers.py` exports `CacheKey = NewType("CacheKey", str)` (mirrors `ProbeId`, `IndexName`). The *only* public way to construct a `CacheKey` is `compose_cache_key(...)`; module re-exports `CacheKey` from `codegenie.eval.cache`.
- [ ] **Cache-key inputs aggregate.** `compose_cache_key` takes a single `CacheKeyInputs` argument: `@dataclass(frozen=True, slots=True) class CacheKeyInputs(case_digest: str, sut_digest: str, rubric_digest: str, cassette_corpus_digest: str, harness_version: str, cassette_canary_pin: str)`. Adding a future input is a loud structural change (all call sites fail type-check until updated), not a silent positional argument addition — Extension-by-addition + Open/Closed at the function-arg boundary.
- [ ] **Module API:** `compose_cache_key(inputs: CacheKeyInputs) -> CacheKey`; `get(cache_key: CacheKey, cache_dir: Path) -> BenchScore | None`; `put(cache_key: CacheKey, score: BenchScore, cache_dir: Path) -> None`; `gc(cache_dir: Path, retain_days: int = 90) -> int` (returns count of `*.json` entries evicted; does NOT count `.tmp` orphans toward the return value).
- [ ] **`__all__`** equals exactly `("CacheKey", "CacheKeyInputs", "compose_cache_key", "get", "put", "gc")`; no other public names (asserted by `assert cache.__all__ == ...` in a fence-style test).

### Composer (`compose_cache_key`) semantics

- [ ] **Output shape.** Returns `CacheKey` whose string value matches `^blake3:[0-9a-f]{64}$` (prefix + 64 lowercase hex).
- [ ] **Composition.** Concatenates the six `CacheKeyInputs` fields **in the order declared on the dataclass** with `\x1f` (ASCII unit-separator) between them, UTF-8 encoded, then routed through `codegenie.hashing.content_hash_bytes`. `cache.py` MUST NOT `import blake3` (asserted by an AST-scan fence test in `tests/unit/eval/test_cache.py::test_no_direct_blake3_import`).
- [ ] **Determinism (Hypothesis property test).** For any `CacheKeyInputs` value, repeated calls return byte-identical `CacheKey`. Use `hypothesis.strategies.text(min_size=0, max_size=128, alphabet=...)` excluding `\x1f` for each field; `--no-cov` permitted for ad-hoc subset runs.
- [ ] **Per-field uniqueness.** Parametrized test (one row per field name) flips that one field and asserts `compose_cache_key(modified) != compose_cache_key(base)`. Base values are **six disjoint role-encoding strings** (e.g., `"case-d-AAA"`, `"sut-d-BBB"`, …) so any field can be uniquely identified in its slot.
- [ ] **Positional-swap resistance.** Parametrized test over `itertools.combinations(range(6), 2)` swaps every pair of input values via `dataclasses.replace`; asserts the resulting `CacheKey` differs from the base. Catches a mutant where, e.g., `compose_cache_key` builds the join from `(sut_digest, case_digest, ...)` instead of `(case_digest, sut_digest, ...)`.
- [ ] **ADR-0005 scoped invalidation.** Test: rotating case A's `cassette_canary_pin` changes A's `CacheKey` but does NOT change case B's `CacheKey` (B's pin is the only one that affects B's key). Encodes the per-case scoping consequence of ADR-0005, distinct from the bare per-field uniqueness check.
- [ ] **Input contract — pure bytes-to-hex.** `compose_cache_key` does **not** validate input shape or content; empty strings and arbitrary-length values hash to a valid `CacheKey`. Inputs MUST NOT contain `\x1f` (the unit-separator) — caller responsibility (the S2-02 loader validates `*_digest` shape; the Runner validates `harness_version` and `cassette_canary_pin`). Document this contract in the function docstring.
- [ ] **Keyword-only at call site.** `compose_cache_key(some_kwargs)` — positional `str` arguments are a `TypeError` (signature is `compose_cache_key(inputs: CacheKeyInputs)`, so this is automatic but assert it in a test for explicitness).

### `get` semantics

- [ ] **Round-trip.** `put(k, score, dir); assert get(k, dir) == score` for a freshly constructed `BenchScore` with every field populated. Pydantic equality holds (frozen models compare by field values).
- [ ] **Missing-`<hex>.json` is a miss.** `get` returns `None` without warning.
- [ ] **Missing `cache_dir` is a miss.** `get(k, /nonexistent/path)` returns `None` without raising, without warning.
- [ ] **Corrupt-file-on-read is a miss.** If `<cache_dir>/<hex>.json` exists but `BenchScore.model_validate_json` raises (`pydantic.ValidationError` OR `json.JSONDecodeError`), return `None` and emit `structlog.warn("cache.corrupt_entry", cache_key=<key>, path=<absolute path>)`. Do NOT raise; do NOT delete the file (operators may want to inspect). Event MUST contain both `cache_key` and `path` kwargs (asserted by `structlog.testing.capture_logs()` — NOT `caplog`, which loses structlog kwargs under the project's processor chain).
- [ ] **Corrupt-then-recover.** After `get` returns `None` on a corrupt `<hex>.json`, a subsequent `put(k, v, dir)` overwrites the corrupt file and the next `get(k, dir) == v`. Catches a mutant that short-circuits `put` if the destination exists.
- [ ] **Reader-during-writer safety.** While a writer holds `LOCK_EX` and is mid-`os.replace`, a concurrent `get(k, dir)` returns either the prior `<hex>.json` value (if any) or `None` — never raises, never returns a torn read. Verified by a thread-based test that interleaves `get` calls with a `monkeypatch`-slowed `os.replace`.

### `put` semantics

- [ ] **Atomicity at the syscall level.** `put` writes to `<cache_dir>/<hex>.<pid>.<6-char-secrets-hex>.tmp` (mirrors Phase 0 `cache/store.py` pid+token tmp-suffix to defeat any future cross-process tmp collision), then `os.fsync(fd)`, `os.close(fd)`, then `os.replace(tmp, <cache_dir>/<hex>.json)`. Verified by spying on `os.replace`: at the moment of replace, a `.tmp` file matching the per-writer pattern exists, and either no `<hex>.json` exists (cold) or the previous `<hex>.json` is byte-identical to its pre-`put` content (recovery is the next AC).
- [ ] **Crash-during-write preserves prior value.** Parametrized over four crash points (`tmp_create_fails`, `tmp_write_fails`, `fsync_fails`, `replace_fails` — each via `monkeypatch.setattr(..., side_effect=OSError)`): `put(k, v1, dir)` first, capture `v1_bytes = (cache_dir / f"{hex}.json").read_bytes()`, then `put(k, v2, dir)` raises `OSError`, and finally `(cache_dir / f"{hex}.json").read_bytes() == v1_bytes` (byte-identical, untouched). `OSError` propagates — never swallowed.
- [ ] **Overwrite is atomic.** `put(k, v2, dir)` after `put(k, v1, dir)` succeeds (no `FileExistsError`); subsequent `get(k, dir) == v2`. `os.replace` semantics (vs `os.rename`) carry the overwrite guarantee — this AC pins it as a contract, not an accident.
- [ ] **Lock discipline — direct probe.** `put` acquires `fcntl.flock(LOCK_EX)` on `<cache_dir>/.lock` (sentinel file, created with mode `0o600`) via a `@contextlib.contextmanager` helper `_cache_write_lock(cache_dir) -> Iterator[None]`; releases on success or exception. Verified by a test that pauses `put` mid-write (slow `os.replace`) and asserts a concurrent `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on `.lock` from a sibling fd raises `BlockingIOError`. The previous "two threads write valid JSON" test is **not** sufficient — `BenchScore` JSON fits under `PIPE_BUF=4096`, so even with the lock removed kernel atomicity for `os.write` would let it pass.
- [ ] **`get` does NOT take the lock.** Asserted: `get(k, dir)` succeeds while another thread holds `LOCK_EX` on `.lock` (returns whatever was on disk before the writer started, or `None`).
- [ ] **`cache_dir` auto-creation.** `put` creates `cache_dir` (and parents) via `mkdir(parents=True, exist_ok=True)` if missing; round-trip test runs against `tmp_path / "never-created" / "cache"`. Without this, the Runner crashes on the first `put` of a fresh checkout.
- [ ] **File modes are `0o600` post-`put`.** `stat.S_IMODE((cache_dir / f"{hex}.json").stat().st_mode) == 0o600` AND `stat.S_IMODE((cache_dir / ".lock").stat().st_mode) == 0o600`. `put` re-`os.chmod`s `<hex>.json` AFTER `os.replace` to defeat CI restore-time umask flattening (Phase 0 ADR-0011 + `cache/store.py:380` precedent).
- [ ] **Directory mode is `0o700` post-`put`.** When `put` creates `cache_dir`, the directory is `chmod 0o700`. Mirrors Phase 0 `_ensure_dir`.
- [ ] **Mode constants.** Module declares `_FILE_MODE: Final[int] = 0o600` and `_DIR_MODE: Final[int] = 0o700` — no inline `0o600`/`0o700` literals in function bodies.

### `gc` semantics

- [ ] **Mixed-age counting.** Given N entries with K older than `retain_days * 86400` seconds and N-K younger, `gc(cache_dir, retain_days)` returns exactly `K`, exactly the K old entries are `unlink`'d, exactly the N-K young entries remain readable via `get`. Verified by a multi-entry test with explicit `os.utime(path, (target_mtime, target_mtime))` mtime forging.
- [ ] **Boundary behavior at `retain_days * 86400` seconds.** Parametrized test at four mtime offsets — `(-91*86400, 1)`, `(-90*86400 - 1, 1)`, `(-90*86400 + 1, 0)`, `(-89*86400, 0)` — asserts the documented comparison operator (use `<`, not `<=`; entries written *exactly* `retain_days * 86400` seconds ago are retained).
- [ ] **`retain_days=0`.** `gc(cache_dir, retain_days=0)` evicts every `*.json` entry whose `mtime < time.time()` (effectively all of them).
- [ ] **Skip `.lock` sentinel.** Touch `.lock`, force its mtime to epoch zero, call `gc(cache_dir, retain_days=1)`, assert `.lock` still exists. Catches the mutant `Path.glob("*")` (which would unlink `.lock` and break every subsequent `put`).
- [ ] **Skip `*.tmp` orphans.** `*.tmp` files from a crashed prior `put` are NOT counted toward the return value and are NOT unlinked by `gc` (an in-flight `put` in another process may still need its `.tmp`). `gc` only touches `*.json` files. (Reaping `.tmp` orphans is deferred to a future story when the threat is empirical; for now the safer default is leave-alone — flagged in Notes for future revisit.)
- [ ] **Missing or empty `cache_dir`.** `gc(/nonexistent/path, retain_days=90) == 0` and does not raise; `gc(cache_dir_with_only_lock, retain_days=90) == 0` and does not raise.
- [ ] **Hypothesis property test — round-trip survives GC.** Generate a list of `(cache_key, score, mtime_offset_seconds)` tuples; `put` all; `gc(retain_days=R)`; assert `get(k) == score` for exactly the entries whose `mtime_offset_seconds > -R*86400`.

### Cross-cutting

- [ ] **No `import blake3`** in `cache.py` (AST-scan test).
- [ ] **No `import hashlib`** in `cache.py` (BLAKE3 chokepoint is `codegenie.hashing` only).
- [ ] **No `os.rename`** in `cache.py` (use `os.replace`; AST-scan test, matches Phase 0 `cache/store.py` discipline).
- [ ] **TDD red test exists, committed, green.**
- [ ] **`ruff format`, `ruff check`, `mypy --strict` clean.**
- [ ] **Coverage on `src/codegenie/eval/cache.py` ≥ 95% line, ≥ 90% branch.**

## Implementation outline

1. **Add the newtype** in `src/codegenie/types/identifiers.py`: `CacheKey = NewType("CacheKey", str)` (one line; mirrors the existing `ProbeId`, `IndexName` rows). Re-export from `codegenie.eval.cache`.
2. **Create `src/codegenie/eval/cache.py`** with module-level constants `_FILE_MODE: Final[int] = 0o600`, `_DIR_MODE: Final[int] = 0o700`, `_UNIT_SEP: Final[bytes] = b"\x1f"`. Module `__all__ = ("CacheKey", "CacheKeyInputs", "compose_cache_key", "get", "put", "gc")`.
3. **`CacheKeyInputs` dataclass** — `@dataclass(frozen=True, slots=True) class CacheKeyInputs` with the six `str` fields in the declared order: `case_digest`, `sut_digest`, `rubric_digest`, `cassette_corpus_digest`, `harness_version`, `cassette_canary_pin`.
4. **`compose_cache_key(inputs: CacheKeyInputs) -> CacheKey`** — read fields in dataclass order, UTF-8 encode each, join with `_UNIT_SEP`, route through `codegenie.hashing.content_hash_bytes(joined_bytes)`, wrap the resulting `"blake3:<hex>"` in `CacheKey(...)`. No validation of inputs. **Do not** `import blake3`. **Do not** add a `bytes_hash` helper to `hashing.py` — `content_hash_bytes` already exists.
5. **`get(cache_key, cache_dir)`** —
   - Resolve `hex_part = cache_key.removeprefix("blake3:")`, `path = cache_dir / f"{hex_part}.json"`.
   - If `cache_dir` or `path` is missing → return `None` without warning.
   - `try: return BenchScore.model_validate_json(path.read_bytes())` ; on `pydantic.ValidationError | json.JSONDecodeError` → `_log.warn("cache.corrupt_entry", cache_key=cache_key, path=str(path.resolve()))` and return `None`. Do not `unlink`.
   - Do NOT take the lock.
6. **`_cache_write_lock(cache_dir: Path) -> Iterator[None]`** — `@contextlib.contextmanager`-decorated; ensures `<cache_dir>/.lock` exists (mode `_FILE_MODE`), opens it `r`, `fcntl.flock(fh, LOCK_EX)`, yields, then `fcntl.flock(fh, LOCK_UN)` in a `finally`.
7. **`put(cache_key, score, cache_dir)`** —
   - `cache_dir.mkdir(parents=True, exist_ok=True)`; `os.chmod(cache_dir, _DIR_MODE)`.
   - `hex_part = cache_key.removeprefix("blake3:")`; `target = cache_dir / f"{hex_part}.json"`; `tmp = cache_dir / f"{hex_part}.{os.getpid()}.{secrets.token_hex(4)}.tmp"`.
   - `with _cache_write_lock(cache_dir):`
     - `data = score.model_dump_json().encode("utf-8")`.
     - `fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)`; `try: os.write(fd, data); os.fsync(fd) finally: os.close(fd)`.
     - `os.replace(tmp, target)`.
     - `os.chmod(target, _FILE_MODE)` — re-assert after `os.replace` (defeats CI umask flattening per Phase 0 ADR-0011).
   - `OSError` propagates; never swallowed.
8. **`gc(cache_dir, retain_days=90) -> int`** —
   - If `cache_dir` does not exist → return `0`.
   - `cutoff = time.time() - retain_days * 86400`.
   - Walk `cache_dir.glob("*.json")` (this naturally excludes `.lock` and `*.tmp`).
   - For each `p`: if `p.stat().st_mtime < cutoff`, `p.unlink()`, `evicted += 1`, emit `_log.info("cache.eviction", cache_dir=str(cache_dir), path=str(p))`.
   - Return `evicted`.
9. **Tests** in `tests/unit/eval/test_cache.py` (see TDD plan).

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/eval/test_cache.py`. All tests must be **mutation-resistant** — for each, name the wrong implementation the test catches.

```python
# ---- fixtures and helpers ----------------------------------------------------

KEY_A_HEX = "a" * 64
KEY_A = CacheKey(f"blake3:{KEY_A_HEX}")
KEY_B = CacheKey(f"blake3:{'b' * 64}")

_DISTINCT_INPUTS = CacheKeyInputs(
    case_digest="case-d-AAA",
    sut_digest="sut-d-BBB",
    rubric_digest="rubric-d-CCC",
    cassette_corpus_digest="corpus-d-DDD",
    harness_version="harness-EEE",
    cassette_canary_pin="canary-FFF",
)


def _score() -> BenchScore:
    return BenchScore(
        passed=True, score=1.0, breakdown={}, failure_modes=(),
        cost_usd=0.0, wall_clock_ms=10,
    )


# ---- get / put round-trip ---------------------------------------------------

def test_round_trip_get_returns_put_value(tmp_path):
    cache.put(KEY_A, _score(), tmp_path)
    assert cache.get(KEY_A, tmp_path) == _score()

def test_round_trip_creates_cache_dir_if_missing(tmp_path):
    """Catches: `put` assumes cache_dir exists; Runner crashes on fresh checkout."""
    fresh = tmp_path / "never" / "created" / "cache"
    cache.put(KEY_A, _score(), fresh)
    assert cache.get(KEY_A, fresh) == _score()

def test_get_missing_returns_none(tmp_path):
    assert cache.get(KEY_B, tmp_path) is None

def test_get_missing_cache_dir_returns_none_without_warning(tmp_path):
    """Catches: `get` raises FileNotFoundError on missing parent."""
    with structlog.testing.capture_logs() as captured:
        assert cache.get(KEY_A, tmp_path / "nonexistent") is None
    assert [e for e in captured if "cache.corrupt_entry" in e.get("event", "")] == []


# ---- corrupt-on-read --------------------------------------------------------

def test_get_corrupt_returns_none_and_emits_structured_warning(tmp_path):
    """Catches: warn event missing kwargs; or impl re-raises; or impl unlinks the file."""
    p = tmp_path / f"{KEY_A_HEX}.json"
    p.write_text("{not valid json")
    with structlog.testing.capture_logs() as captured:
        assert cache.get(KEY_A, tmp_path) is None
    events = [e for e in captured if e.get("event") == "cache.corrupt_entry"]
    assert len(events) == 1, events
    assert events[0]["cache_key"] == KEY_A
    assert Path(events[0]["path"]) == p.resolve()
    assert events[0]["log_level"] == "warning"
    assert p.exists(), "corrupt file MUST NOT be deleted (operators inspect)"

def test_corrupt_then_put_recovers(tmp_path):
    """Catches: `put` short-circuits if destination exists — corrupt entry becomes permanent."""
    p = tmp_path / f"{KEY_A_HEX}.json"
    p.write_text("{garbage")
    assert cache.get(KEY_A, tmp_path) is None
    cache.put(KEY_A, _score(), tmp_path)
    assert cache.get(KEY_A, tmp_path) == _score()


# ---- atomicity --------------------------------------------------------------

def test_put_uses_pid_token_tmp_then_os_replace(tmp_path, monkeypatch):
    """Catches: `replace(path, path)` self-rename; or `os.rename` used instead of `os.replace`."""
    seen_dirs: list[set[str]] = []
    real_replace = os.replace
    def spy(src, dst):
        seen_dirs.append({p.name for p in tmp_path.iterdir()})
        return real_replace(src, dst)
    monkeypatch.setattr(os, "replace", spy)
    cache.put(KEY_A, _score(), tmp_path)
    # At the moment of replace, a pid+token .tmp existed
    target_name = f"{KEY_A_HEX}.json"
    assert any(
        n.endswith(".tmp") and n.startswith(f"{KEY_A_HEX}.{os.getpid()}.") and target_name not in s
        for s in seen_dirs for n in s
    ), seen_dirs
    assert (tmp_path / target_name).exists()

@pytest.mark.parametrize("victim", ["os.write", "os.fsync", "os.replace"])
def test_previous_value_preserved_across_any_crash_point(tmp_path, monkeypatch, victim):
    """Catches: impl truncates target before tmp write; or swallows OSError; or rewrites in place."""
    cache.put(KEY_A, _score(), tmp_path)
    target = tmp_path / f"{KEY_A_HEX}.json"
    v1_bytes = target.read_bytes()
    # Patch the named primitive to raise OSError mid-write of v2.
    module, name = victim.rsplit(".", 1)
    monkeypatch.setattr(module, name, mock.Mock(side_effect=OSError("simulated")))
    v2 = _score().model_copy(update={"score": 0.5})
    with pytest.raises(OSError):
        cache.put(KEY_A, v2, tmp_path)
    assert target.read_bytes() == v1_bytes, f"v1 mutated by crash at {victim}"

def test_put_overwrite_is_atomic_no_file_exists_error(tmp_path):
    """Catches: impl uses `os.rename` (Windows) or `os.O_EXCL` — raises on existing target."""
    cache.put(KEY_A, _score(), tmp_path)
    v2 = _score().model_copy(update={"score": 0.42})
    cache.put(KEY_A, v2, tmp_path)  # must not raise FileExistsError
    assert cache.get(KEY_A, tmp_path) == v2


# ---- reader-during-writer safety ------------------------------------------

def test_get_does_not_take_lock_concurrent_with_writer(tmp_path):
    """Catches: `get` accidentally `flock`s — defeats the lock-free read design."""
    cache.put(KEY_A, _score(), tmp_path)
    lock_path = tmp_path / ".lock"
    with open(lock_path, "r") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            assert cache.get(KEY_A, tmp_path) == _score()  # must NOT block
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)

def test_get_returns_prior_value_or_none_during_writer(tmp_path, monkeypatch):
    """Catches: `get` returns torn read mid-replace."""
    cache.put(KEY_A, _score(), tmp_path)
    barrier = threading.Event()
    proceed = threading.Event()
    real_replace = os.replace
    def slow_replace(src, dst):
        barrier.set(); proceed.wait(5)
        return real_replace(src, dst)
    monkeypatch.setattr(os, "replace", slow_replace)
    v2 = _score().model_copy(update={"score": 0.5})
    writer = threading.Thread(target=cache.put, args=(KEY_A, v2, tmp_path))
    writer.start()
    barrier.wait(5)
    got = cache.get(KEY_A, tmp_path)
    proceed.set(); writer.join()
    assert got in (_score(), v2, None)  # prior value or post-replace, never torn


# ---- lock discipline (direct probe, not byte-pattern proxy) ----------------

def test_put_holds_exclusive_lock_during_write(tmp_path, monkeypatch):
    """Catches: `fcntl.flock` removed — BenchScore JSON < PIPE_BUF, byte test would pass."""
    barrier = threading.Event()
    proceed = threading.Event()
    real_replace = os.replace
    def slow_replace(src, dst):
        barrier.set(); proceed.wait(5)
        return real_replace(src, dst)
    monkeypatch.setattr(os, "replace", slow_replace)
    writer = threading.Thread(target=cache.put, args=(KEY_A, _score(), tmp_path))
    writer.start()
    barrier.wait(5)
    # While the writer holds LOCK_EX on .lock, a sibling fd's non-blocking
    # LOCK_EX MUST raise BlockingIOError.
    with open(tmp_path / ".lock", "r") as fh:
        with pytest.raises(BlockingIOError):
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    proceed.set(); writer.join()


# ---- file modes (Phase 0 ADR-0011) -----------------------------------------

def test_put_writes_files_with_mode_0600(tmp_path):
    cache.put(KEY_A, _score(), tmp_path)
    blob = tmp_path / f"{KEY_A_HEX}.json"
    lock = tmp_path / ".lock"
    assert stat.S_IMODE(blob.stat().st_mode) == 0o600, oct(blob.stat().st_mode)
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600, oct(lock.stat().st_mode)

def test_put_creates_cache_dir_with_mode_0700(tmp_path):
    fresh = tmp_path / "fresh"
    cache.put(KEY_A, _score(), fresh)
    assert stat.S_IMODE(fresh.stat().st_mode) == 0o700, oct(fresh.stat().st_mode)


# ---- GC --------------------------------------------------------------------

def test_gc_evicts_old_returns_exact_count(tmp_path):
    """Catches: returns `len(all_files)` instead of evicted count."""
    cache.put(KEY_A, _score(), tmp_path)
    cache.put(KEY_B, _score(), tmp_path)
    p_old = tmp_path / f"{KEY_A_HEX}.json"
    old_mtime = time.time() - 100 * 86400
    os.utime(p_old, (old_mtime, old_mtime))
    assert cache.gc(tmp_path, retain_days=90) == 1
    assert not p_old.exists()
    assert cache.get(KEY_B, tmp_path) == _score()

@pytest.mark.parametrize("offset_seconds,expected_evicted", [
    (-91 * 86400, 1),
    (-90 * 86400 - 1, 1),
    (-90 * 86400 + 1, 0),
    (-89 * 86400, 0),
])
def test_gc_retain_days_boundary(tmp_path, offset_seconds, expected_evicted):
    """Catches: `<` vs `<=` off-by-one at the retain_days * 86400 second boundary."""
    cache.put(KEY_A, _score(), tmp_path)
    p = tmp_path / f"{KEY_A_HEX}.json"
    mtime = time.time() + offset_seconds
    os.utime(p, (mtime, mtime))
    assert cache.gc(tmp_path, retain_days=90) == expected_evicted

def test_gc_does_not_evict_lock_file(tmp_path):
    """Catches: `Path.glob('*')` instead of `Path.glob('*.json')` — would unlink .lock."""
    (tmp_path / ".lock").touch()
    os.utime(tmp_path / ".lock", (0, 0))
    cache.gc(tmp_path, retain_days=1)
    assert (tmp_path / ".lock").exists()

def test_gc_does_not_evict_tmp_orphans(tmp_path):
    """Catches: `gc` unlinks a `.tmp` from a concurrent in-flight `put`."""
    tmp_orphan = tmp_path / f"{KEY_A_HEX}.99999.deadbe.tmp"
    tmp_orphan.touch()
    os.utime(tmp_orphan, (0, 0))
    assert cache.gc(tmp_path, retain_days=1) == 0
    assert tmp_orphan.exists()

def test_gc_returns_zero_on_missing_cache_dir(tmp_path):
    assert cache.gc(tmp_path / "nonexistent", retain_days=90) == 0

def test_gc_returns_zero_on_empty_cache_dir(tmp_path):
    assert cache.gc(tmp_path, retain_days=90) == 0


# ---- compose_cache_key -----------------------------------------------------

def test_compose_cache_key_shape():
    k = cache.compose_cache_key(_DISTINCT_INPUTS)
    assert isinstance(k, str)  # CacheKey is a NewType over str
    assert k.startswith("blake3:")
    assert len(k) == len("blake3:") + 64
    assert re.fullmatch(r"blake3:[0-9a-f]{64}", k)

def test_compose_cache_key_determinism_distinct_inputs():
    """Catches: impl reads dataclass fields in non-deterministic order."""
    k1 = cache.compose_cache_key(_DISTINCT_INPUTS)
    k2 = cache.compose_cache_key(_DISTINCT_INPUTS)
    assert k1 == k2

@given(st.builds(
    CacheKeyInputs,
    case_digest=st.text(alphabet=st.characters(blacklist_characters="\x1f"), min_size=0, max_size=128),
    sut_digest=st.text(alphabet=st.characters(blacklist_characters="\x1f"), min_size=0, max_size=128),
    rubric_digest=st.text(alphabet=st.characters(blacklist_characters="\x1f"), min_size=0, max_size=128),
    cassette_corpus_digest=st.text(alphabet=st.characters(blacklist_characters="\x1f"), min_size=0, max_size=128),
    harness_version=st.text(alphabet=st.characters(blacklist_characters="\x1f"), min_size=0, max_size=64),
    cassette_canary_pin=st.text(alphabet=st.characters(blacklist_characters="\x1f"), min_size=0, max_size=64),
))
def test_compose_cache_key_determinism_property(inputs):
    """Hypothesis: determinism across arbitrary input shapes (per AC)."""
    assert cache.compose_cache_key(inputs) == cache.compose_cache_key(inputs)

@pytest.mark.parametrize("varying", [
    "case_digest", "sut_digest", "rubric_digest",
    "cassette_corpus_digest", "harness_version", "cassette_canary_pin",
])
def test_compose_cache_key_per_field_uniqueness(varying):
    """Catches: impl ignores or hard-codes one of the six fields."""
    modified = dataclasses.replace(_DISTINCT_INPUTS, **{varying: "MODIFIED"})
    assert cache.compose_cache_key(modified) != cache.compose_cache_key(_DISTINCT_INPUTS)

@pytest.mark.parametrize("i,j", list(itertools.combinations(range(6), 2)))
def test_compose_cache_key_resists_positional_swap(i, j):
    """Catches: impl builds the join from fields in the wrong order."""
    field_names = list(dataclasses.fields(CacheKeyInputs))
    values = [getattr(_DISTINCT_INPUTS, f.name) for f in field_names]
    values[i], values[j] = values[j], values[i]
    swapped = CacheKeyInputs(**{f.name: v for f, v in zip(field_names, values)})
    assert cache.compose_cache_key(swapped) != cache.compose_cache_key(_DISTINCT_INPUTS)

def test_compose_cache_key_canary_rotation_does_not_affect_sibling(tmp_path):
    """ADR-0005 scoped invalidation: rotating case A's pin must NOT change case B's key."""
    a_v1 = cache.compose_cache_key(dataclasses.replace(_DISTINCT_INPUTS, case_digest="A", cassette_canary_pin="pin-A-v1"))
    b_v1 = cache.compose_cache_key(dataclasses.replace(_DISTINCT_INPUTS, case_digest="B", cassette_canary_pin="pin-B-v1"))
    a_v2 = cache.compose_cache_key(dataclasses.replace(_DISTINCT_INPUTS, case_digest="A", cassette_canary_pin="pin-A-v2"))  # rotated
    b_after = cache.compose_cache_key(dataclasses.replace(_DISTINCT_INPUTS, case_digest="B", cassette_canary_pin="pin-B-v1"))
    assert a_v2 != a_v1, "A's pin rotation must change A's key"
    assert b_after == b_v1, "A's pin rotation must NOT change B's key"


# ---- module surface fences -------------------------------------------------

def test_module_all_is_exact():
    """Catches: impl exports extra surface area (e.g., evict, has_key) — locks contract."""
    assert cache.__all__ == ("CacheKey", "CacheKeyInputs", "compose_cache_key", "get", "put", "gc")

def test_no_direct_blake3_import():
    """Catches: impl bypasses Phase 0 ADR-0001 chokepoint."""
    src = (Path("src") / "codegenie" / "eval" / "cache.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(a.name != "blake3" for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "blake3"

def test_no_hashlib_import():
    """Catches: impl uses SHA-256 directly instead of routing through codegenie.hashing."""
    src = (Path("src") / "codegenie" / "eval" / "cache.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(a.name != "hashlib" for a in node.names)

def test_no_os_rename_use():
    """Catches: impl uses os.rename (Windows-unsafe) instead of os.replace."""
    src = (Path("src") / "codegenie" / "eval" / "cache.py").read_text()
    assert "os.rename" not in src, "use os.replace (Phase 0 cache/store.py precedent)"
```

### Green

Smallest impl: §Implementation outline; ~110 lines including the `CacheKeyInputs` dataclass, the `_cache_write_lock` context manager, and the module-level constants. The implementer's job is to make every test above pass with the minimum code that satisfies the AC list — no speculative surface (no `evict`, no `has`, no `keys()`).

### Refactor

- Keep `_cache_write_lock` as the only fcntl callsite — type as `Iterator[None]`.
- Consider extracting `_atomic_write_bytes(path, data, mode)` if Phase-3 reuse arrives — for now it stays private (rule of three not met; Phase 0 `cache/store.py:_atomic_write_bytes` is the first site, this is the second).
- Document the `.lock` sentinel as part of the directory contract — never lives outside `cache_dir`; `gc` never touches it.
- Document the `*.tmp` orphan policy (leave alone, deferred reaping) so future readers see the intentional non-action.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/cache.py` | New module — `CacheKey`, `CacheKeyInputs`, `compose_cache_key`, `get`, `put`, `gc` |
| `src/codegenie/types/identifiers.py` | Add `CacheKey = NewType("CacheKey", str)` (one row; mirrors `ProbeId`, `IndexName`) |
| `tests/unit/eval/test_cache.py` | Red tests covering all ACs |

(**Do not** touch `src/codegenie/hashing.py` — `content_hash_bytes` already exists; reuse it.)

## Out of scope

- **Cache-key composition at runtime** — the runner (S3-01) constructs `CacheKeyInputs` from the per-run digests and calls `compose_cache_key`; this story only exposes the function.
- **GC scheduling** — the runner (S3-02 end-of-run) invokes `gc(retain_days=90)`; cron-style scheduling is out.
- **Cross-host cache sharing** — explicit non-goal (`phase-arch-design.md §Non-goals #9`).
- **Cache-key index / manifest** — the filesystem `<hex>.json` listing IS the index; no separate manifest.
- **`.tmp` orphan reaping** — current contract: `gc` leaves `*.tmp` alone (an in-flight `put` in another process may still need its `.tmp`). If `.tmp` accumulation becomes empirical on long-running CI hosts, a separate story sweeps the policy.
- **Cache-backend Strategy/DIP seam** — pure YAGNI per Non-goals #9. If a future phase needs a non-filesystem backend, the right shape is `class CacheBackend(Protocol)` with `read/write/list/delete`; the current module becomes the default `FilesystemBackend`. Do not introduce now.
- **Probe-module `_WARNING_IDS` discipline** — convention is scoped to probes (CLAUDE.md). Phase 0 `cache/store.py` does not declare `_WARNING_IDS`; this cache mirrors that. If a later story formalizes warning-ID discipline for non-probe modules, sweep both caches together.

## Notes for the implementer

### Hard constraints (load-bearing)

- **Reuse Phase 0's `content_hash_bytes`.** `src/codegenie/hashing.py:85` already exposes `content_hash_bytes(b: bytes) -> "blake3:<hex>"` — it was added in Phase 0 S2-03 specifically for this kind of use. **Do not** add `bytes_hash`; **do not** edit `hashing.py`.
- **`os.replace`, not `os.rename`.** Phase 0 `cache/store.py:138` uses `os.replace` (cross-platform-safe; overwrites atomically when target exists). Match that — Rule 11 (codebase conventions) + Rule 7 (don't average two patterns; pick the more tested).
- **Pid+token `.tmp` suffix.** Mirror Phase 0's `_atomic_write_bytes` (`<target>.<pid>.<secrets.token_hex(4)>.tmp`) — even though `fcntl.flock` serializes single-host writers today, the disambiguation costs ~one line and forecloses a class of cross-process `.tmp` collisions you don't want to think about ever again.
- **Re-`chmod` after `os.replace`.** Mode bits on the destination after `os.replace` carry from the tmp file, but CI `actions/cache` restore flattens modes to umask defaults — Phase 0 `cache/store.py:380` re-asserts modes per-`put` for exactly this reason.
- **`\x1f` is the established separator.** Phase 0's `identity_hash` (`hashing.py:74`) uses `\x1f` — the eval cache reuses it. Do not invent a new convention.

### Intentional Phase-0 divergences (surface, don't hide)

- **Module-level free functions vs `class Cache`.** The arch class diagram (`phase-arch-design.md §Logical view`, line 177) shows `class Cache`. The component spec (`phase-arch-design.md §src/codegenie/eval/cache.py`, line 606) defines `def get(...)`, `def put(...)`, `def gc(...)` at the module level — i.e., the arch component spec wins, and free functions are the prescribed surface. Rule 2 (simplicity first) supports this. Revisit if the Runner accumulates ≥ 3 cache-touching call sites that would benefit from constructor-time invariants — promote to `class Cache(cache_dir: Path)` then, with one-shot `_ensure_dir` + `_reapply_modes` at `__init__` (Phase 0 precedent).
- **`fcntl.flock` vs Phase 0's `O_APPEND`+`PIPE_BUF` atomicity.** Phase 0 `cache/store.py` deliberately uses no flock — it leans on `O_APPEND` atomicity for records ≤ `PIPE_BUF=4096B`. This cache uses `fcntl.flock` because `BenchScore` serialized JSON can exceed 4 KB once `breakdown` keys + `failure_modes` populate. Divergence is intentional; document in the module docstring.
- **Free-function module emits structlog events but does not declare `_WARNING_IDS`.** Phase 0 `cache/store.py` does the same. Convention is currently probe-scoped.

### Design-pattern decisions baked into the ACs

- **`CacheKey` newtype + smart constructor.** Per CLAUDE.md "Never raw `str` for domain IDs". The only public way to *construct* a `CacheKey` is `compose_cache_key(...)` — passing a hand-rolled string to `get`/`put` requires an explicit `CacheKey(my_str)` cast at the call site, which mypy-strict surfaces in code review.
- **`CacheKeyInputs` frozen dataclass.** Aggregates the six inputs so adding a future input (Phase 13+'s hypothetical `model_pin`) is a loud structural change — every call site fails type-check until updated. Closed-for-modification at the function-arg boundary; open for extension via a new dataclass field + ADR amendment. Six kwargs would be silently extensible (forgotten call sites keep compiling).
- **Arity-byte omitted (vs Phase 0's `identity_hash`).** The kw-only single-argument `CacheKeyInputs` signature pins arity at exactly six; `(parts_n, parts_m)`-shape boundary-shift collisions are unreachable by API. Documented; not load-bearing once the input contract bans `\x1f`.

### Operational notes

- **Input contract: no `\x1f` in field values.** `compose_cache_key` is pure bytes-to-hex; it does NOT validate. Callers (S2-02 loader for `*_digest`; Runner for `harness_version` and `cassette_canary_pin`) own input-shape validation. A `\x1f` smuggled into a field would silently shift the join boundary — the AC documents the prohibition; future caller stories should validate.
- **`fcntl.flock` is POSIX-only.** Phase 6.5 runs on Linux/macOS (the operator laptop substrate). Windows support is out-of-roadmap; if it ever arrives, the lock primitive is the swap-out point (`msvcrt.locking` on Windows).
- **`BenchScore` equality.** `frozen=True` Pydantic v2 → `==` compares by field values; `cache.put(k, v); cache.get(k) == v` is meaningful as written.
- **`structlog` capture in tests.** Use `structlog.testing.capture_logs()`, NOT `caplog` — `caplog` drops structlog kwargs under the project's processor chain. Phase 0 `tests/unit/test_cache_store.py` is the precedent (six call sites).
- **Coverage gate.** `pyproject.toml` has `--cov-fail-under=85`; when running this test file alone, append `--no-cov` per project convention (CLAUDE.md "running a narrow subset can falsely fail the coverage gate").
