# Validation report: S5-01 — Performance canaries + concurrent-cache test

**Validated:** 2026-05-13
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S5-01 ships three advisory bench canaries (cold start, dispatch overhead, cache-hit dispatch ratio) plus one concurrent-cache test pinning edge case #12 from `phase-arch-design.md`. The original draft had two structural issues and several coverage gaps: (1) the TDD red test imported and called four APIs that do not exist in the codebase (`construct_snapshot`, `gather` with wrong signature, `CacheStore(root=...)`, probe classes used as instances) — the test would have failed at import, not as a meaningful "red"; (2) the choice of `asyncio.gather` for "concurrent" gathers contradicts edge case #12's literal "two-process test" wording and does not actually exercise the `O_APPEND` kernel-atomicity invariant (asyncio tasks share one OS thread and serialize at the Python level). Additionally, AC-4's "two `Ran`s or one `Ran` + one `CacheHit`" disjunction was too permissive — it admits a "cache silently never hits" bug — and the bench tests had no minimum-viability assertions, so a `try/except: pass` regression would silently produce empty output.

Edits: pivoted the concurrent test to two-process `subprocess.Popen`; corrected all API signatures; added a metamorphic third-gather partner and a perm-restoration partner inside the concurrent test file; strengthened AC-3 with a non-advisory `CacheHit` assertion (ADR-0009); added ACs for `bench-results.json` schema + atomic write + collection-count guard + fixture immutability + sequential-control follow-up; fixed the implementer-notes kernel-atomicity claim. The goal is unchanged; the implementation surface is now executor-ready.

## Findings by critic

### Coverage critic

**AC verifiability**
- AC-1: WEAK — schema undefined; no anchor to the under-test binary.
- AC-2: WEAK — no AC pins the real coordinator/sanitizer/validator/writer chain observably.
- AC-3: WEAK — ratio undefined; no assertion that run-2 was a `CacheHit`.
- AC-4: YES verifiable but inherently flaky-prone (non-deterministic ordering with no repeat-loop).
- AC-5: YES.
- AC-6: WEAK — "post-run" wording weaker than ADR-0011's "post-`gather`" framing.
- AC-7: WEAK — no AC asserts the bench step discovers ≥3 tests.
- AC-8: YES.

**Goal coverage gaps**
- AC-3 doesn't distinguish a real cache hit from a fast cold run.
- No AC asserts bench suite non-empty under the `bench` marker.
- No AC pins `js_only/` fixture immutability across concurrent runs.
- No AC requires the test to exercise interleaving (single-shot may always observe same ordering).

**Missing edge cases (block)**
- bench-collection-count guard.
- AC-3 `CacheHit` assertion via ADR-0009.

**Missing edge cases (harden)**
- AC-6 "after `await asyncio.gather(...)` returns" wording (now "after both subprocesses have exited").
- Cold-start canary should invoke `sys.executable -m codegenie --help` not bare `codegenie`.
- Metamorphic baseline (single-flight reduction).
- `bench-results.json` atomic merge schema.

**Severity rollup**: block: 2 | harden: 4 | nit: 2

### Test-Quality critic

**Compile / API mismatch failures (blockers — test won't even run)**
- `construct_snapshot` is not exported (`build_snapshot(repo_root, config)` is real).
- `gather(snapshot, task=..., probes=probes, cache=cache)` is missing `config` and `sanitizer`.
- `default_registry.for_task` returns `tuple[type[Probe], ...]` (classes), not instances.
- `CacheStore(root=cache_root)` is the wrong constructor (`CacheStore(cache_dir, ttl_hours)`).
- `for_task("__bullet_tracer__", frozenset({"unknown"}))` would yield zero probes — `outputs` would be empty and AC-4's `"language_detection" in result.outputs` would fail for the wrong reason.
- `pytest.mark.asyncio` registered but `asyncio_mode = "auto"` may already cover it.

**Mutation analysis**
- M1 — coordinator silently serializes both gathers: NOT CAUGHT.
- M2 — second gather returns empty outputs: WEAK (gated by broken probes lookup).
- M3 — `CacheStore.put` writes two JSON objects on one line: CAUGHT.
- M4 — `os.chmod` dropped after `put`: WEAK (depends on creation path; new test addresses).
- M5 — both dispatches return `Ran` and never `CacheHit`: NOT CAUGHT — AC-4 disjunction admits it.
- M6 — torn JSON record at 4097 bytes: NOT CAUGHT (out of scope per Out-of-scope).

**Thin or tautological**
- Bench tests have zero assertions; an empty-output regression stays green.
- AC-6's post-run walk doesn't distinguish "chmod once" from "chmod after every put".

**Concurrency-not-actually-concurrent risk**
- Coordinator's `Semaphore(1)` regression would not be caught.
- asyncio same-event-loop tasks don't exercise kernel-level contention.

**Severity rollup**: block: 6 | harden: 5 | nit: 1

### Consistency critic

**Direct ADR / arch contradictions (block)**
- `gather()` signature mismatch (test won't compile).
- `construct_snapshot` import mismatch.
- AC-4 "two `Ran`s" branch unreachable under same-event-loop asyncio + shared `CacheStore` (would require two separate processes).
- Edge case #12 names a "two-process" test; story silently downgraded to asyncio task-level, which does not exercise `O_APPEND`'s kernel-atomicity guarantee. The implementer-note rationale ("`open(..., 'a')` uses `O_APPEND` under the hood") conflates the file-mode flag with the contention scenario the invariant tests.

**Subtle inconsistencies (harden)**
- AC-6 says "ADR-0011 enforcement" but ADR-0011 does not contemplate concurrent gathers — the AC extends rather than restates.
- `pytest_benchmark` exclusion consistent with ADR-0006 ✓.
- p50 ≡ median ✓.
- `continue-on-error: true` consistent with advisory posture ✓.

**Reference path issues**: none.

**Severity rollup**: block: 4 | harden: 3 | nit: 0

## Conflict resolutions

- **Consistency vs Coverage on the async-vs-subprocess choice**: Consistency wins — arch (edge case #12) is authoritative and explicitly names "two-process test". This is the bigger pivot in the story: switched to `subprocess.Popen` two-process invocation. As a side-effect, AC-4's "two `Ran`s OR one `Ran` + one `CacheHit`" disjunction is now reachable on both branches (kept).
- **Coverage vs Test-Quality on bench-test assertions**: aligned — both wanted the same "file exists + parses + has key + positive float" minimum-viability check. Added as a new AC plus an implementer-notes spec for the atomic merge helper.

## Edits applied

### Edit 1 — Validation notes block prepended to story
- Records verdict, change summary, and pointer to this report.

### Edit 2 — AC-1 strengthened
- Was: "runs `codegenie --help` five times via `subprocess.run`".
- Now: invokes `sys.executable -m codegenie --help`; writes JSON with `wall_clock_s_median` + `samples`; pins the under-test interpreter and installed wheel.

### Edit 3 — AC-2 strengthened
- Now names the real chain explicitly (real `OutputSanitizer`, real `_ProbeOutputValidator` inside the coordinator, real `CacheStore`).

### Edit 4 — AC-3 strengthened
- Run in-process so `GatherResult.executions` is observable; added non-advisory `isinstance(..., CacheHit)` per ADR-0009.

### Edit 5 — AC for bench-results schema + atomic write added
- New AC covers atomic merge helper, per-test top-level keys, positive-float self-check at teardown.

### Edit 6 — AC-4 pivoted to subprocess two-process; assertion surface re-anchored to audit records
- Both `Ran`/`CacheHit` branches now reachable; assertion reads `ProbeExecutionRecord.cache_hit` from `.codegenie/runs/<utc-iso>.json` since in-memory `GatherResult` is per-process.

### Edit 7 — AC-5 strengthened
- Explicit "no two JSON on one line" check (`b"}{" not in line`) rules out missing-newline mutation.

### Edit 8 — AC-6 re-scoped
- "After both subprocesses have exited" (matches ADR-0011's "post-`gather`" framing); note that this extends rather than restates ADR-0011.

### Edit 9 — Perm-restoration metamorphic AC added
- `chmod 0o644` between gathers; assert restored to `0o600` post-next-gather.

### Edit 10 — Fixture immutability AC added
- Recursive SHA-256 manifest compare pre/post (excluding `.codegenie/`).

### Edit 11 — Sequential-control AC added
- Fourth in-process gather post-concurrent-pair must be `CacheHit` (catches Test-Quality mutation M5).

### Edit 12 — bench-collection-guard CI step (gating) added
- `pytest --collect-only -m bench tests/bench/ -q` fails the job if count ≠ 3.

### Edit 13 — TDD red-test code block rewritten
- Three test functions: `test_two_concurrent_gathers_leave_consistent_cache` (subprocess.Popen × 2), `test_concurrent_then_in_process_third_gather_is_cache_hit` (metamorphic), `test_perm_restoration_after_concurrent_runs`. All imports + signatures match real codebase: `build_snapshot`, `CacheStore(cache_dir, ttl_hours)`, `gather(snap, task, [probe_instance], cfg, cache, san)`.

### Edit 14 — Implementation outline updated
- 9 steps reflecting the subprocess pivot, in-process bench-cache-hit, atomic merge helper, two CI steps (collection-guard + advisory).

### Edit 15 — Green-phase + Refactor sections updated
- Added `_hash_tree` and `_merge_bench_result` helpers; clarified bench-results path resolution via `GITHUB_WORKSPACE`.

### Edit 16 — Files-to-touch updated
- Added `tests/bench/_helpers.py`; expanded CI workflow modify scope.

### Edit 17 — Out-of-scope expanded
- Added "Deterministic interleaving assertions" and "NFS / case-insensitive FS" with explicit deferral rationale.

### Edit 18 — Implementer notes corrected
- Removed false "`open(..., 'a')` uses `O_APPEND` under the hood and is just as effective" claim. Replaced with the kernel-atomicity-vs-task-serialization explanation. Added the three correct API signatures (gather, build_snapshot, CacheStore) inline so the implementer cannot miss them.

## Verdict rationale

HARDENED. The story's goal is intact and traces to the phase exit criteria (edge case #12 closure + three advisory canaries). The 12 block-severity findings across the three critics collapse to two real categories: API drift in the TDD red test (mechanically fixable by reading the source) and the async-vs-subprocess scoping mismatch (a clean substitution that makes both AC-4 branches reachable and matches edge case #12's literal wording). Both fixes are surgical — no goal rewrite needed; no out-of-story files touched.

## Recommended next step

`phase-story-executor` to implement. The executor's Validator pass should pay special attention to: (a) the bench-collection-guard CI step actually failing on a manufactured break (rename the `bench` marker on a synthetic branch); (b) the metamorphic third-gather producing `CacheHit` not `Ran` — if `Ran`, the cache read path is broken and the story should not be marked Done; (c) all four corrected API signatures matching the real codebase at execution time (codebase may evolve; re-verify before writing the red test).
