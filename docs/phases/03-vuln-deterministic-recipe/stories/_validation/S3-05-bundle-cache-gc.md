# Validation report — S3-05 Bundle cache key + `BundleCacheGc` + `codegenie cache prune` CLI (Gap 4 fix)

**Story:** [`docs/phases/03-vuln-deterministic-recipe/stories/S3-05-bundle-cache-gc.md`](../S3-05-bundle-cache-gc.md)
**Date:** 2026-05-18
**Verdict:** **HARDENED**
**Validator:** `/phase-story-validator` skill (Opus 4.7, scheduled `story-validation-corrector` run)

## Context brief

S3-05 ships the **Gap 4 fix** identified in `phase-arch-design.md §Gap analysis #4` — the synthesis under-specified Bundle cache eviction ("GC after 7 days mtime" was named; no component owned the mechanism). At portfolio scale (Phase 10) an un-GC'd cache becomes load-bearing.

The story carries three deliverables tied together:
1. **`compose_bundle_cache_key`** — pure BLAKE3 composer over 8 inputs including `vuln_index.digest` (ADR-0008 correctness: CVE-feed re-classifications MUST invalidate Bundle cache).
2. **`BundleCacheStore`** — on-disk put/get with atomic-rename + mode discipline + content-addressed key validation.
3. **`BundleCacheGc` + `codegenie cache prune` CLI** — once-a-day amortized eviction with `.gc-stamp`, plus the operator CLI emitting exactly one `CacheGcCompletedEvent` spanning event.

Load-bearing decisions: ADR-0008 (`vuln_index.digest` in cache key + deterministic GC eviction policy); ADR-0001 (BLAKE3 chokepoint — no direct `blake3` imports outside `codegenie.hashing`); ADR-0011 (`0o700`/`0o600` mode + `os.replace` cross-platform atomicity); ADR-0010 (frozen Pydantic error models + closed `Literal[...]` + smart-constructed newtypes).

## Stage 1 — Context Loader

Documents read:

- The story itself (263 lines pre-validation).
- `docs/phases/03-vuln-deterministic-recipe/ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md` (Decision, Tradeoffs, Pattern fit, Consequences).
- `docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md` §C7 (BundleBuilder), §C9 (EventLog + `WorkflowSpanningEvent.event_type` Literal at line ~872), §Gap analysis #4 (lines ~1168–1172).
- `docs/phases/03-vuln-deterministic-recipe/ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md`.
- `docs/phases/00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md` (BLAKE3 chokepoint).
- `docs/phases/03-vuln-deterministic-recipe/stories/S3-01-tccm-context-query-models.md` (TCCMParseError shape precedent).
- `docs/phases/03-vuln-deterministic-recipe/stories/S3-02-vuln-index-sqlite.md` (`_parse_max_age_seconds` + env-knob reject corpus precedent).
- `docs/phases/03-vuln-deterministic-recipe/stories/_validation/S3-04-bundle-builder-serial-fallback.md` (BundleBuilderError + `SandboxedPath` + `_compose_entry` purity precedent).
- `src/codegenie/hashing.py` (public surface, separator convention).
- `src/codegenie/cache/store.py` (`_atomic_write_bytes` + `_reapply_modes` precedent).
- `src/codegenie/types/identifiers.py` (newtype catalog — confirmed `SemverVersion` does NOT exist).
- `src/codegenie/errors.py` (markers-only discipline).
- `src/codegenie/cli.py` (confirmed `@cli.group("cache")` + `cache gc` Phase-1+ stub at lines 898–912).
- `CLAUDE.md` — Extension by addition, Functional core / imperative shell, Newtype identifiers, Match the codebase's conventions, Rule 12 (fail loud).

## Stage 2 — four critics in parallel

### Coverage critic — 13 findings (3 blocks / 8 hardens / 2 nits)

| # | Tag | Issue | Resolution |
|---|---|---|---|
| F1 | block | `SemverVersion` newtype does NOT exist in `identifiers.py` | AC-5 — downgraded to `str`; deferred via Notes DP-B (mirrors S3-04 `CanonicalArgsJson` deferral) |
| F2 | block | Participation parametrize mutates with `base[vary] + "x"` — a buggy impl omitting `vuln_index_digest` could survive (length-induced divergence is the wrong reason) | AC-8 rewritten with same-length distinct-equivalence-class mutation table `_MUTATION`; AC-7 adds positive declared-order byte-layout assertion |
| F3 | harden | `args_canonical` canonicalization contract unspecified | AC-12 + module docstring documents caller-canonical form |
| F4 | harden | Separator-poisoning (`\x1f` in any input value) | AC-10 — composer rejects with `BundleCacheRaise(reason="separator_in_input")` |
| F5 | harden | `BundleCacheStore` missing mode + idempotence + path-traversal defenses | AC-15 (key validation), AC-16 (mode + atomicity), AC-17 (idempotence) |
| F6 | harden | `BundleCacheGc.run` edge cases (missing `bundles/`, non-hex files, symlinks, subdirs, boundary) | AC-27 + AC-28 (skip rules + `Path.is_file()` + `is_symlink()`); AC-29 (strict-`<` boundary) |
| F7 | harden | Hashing chokepoint enforcement | AC-13 AST test + AC-50 import-linter contract |
| F8 | harden | Orchestrator-path event-emission AC (currently only CLI-fenced) | AC-32 — `run()` with `event_emitter=spy` calls `spy` exactly once; no-op branch zero |
| F9 | harden | `.gc-stamp` failure modes (missing / corrupt / future-dated / concurrent) | AC-36 / AC-37 / AC-38 / AC-39 |
| F10 | block | Existing `cache gc` stub coexistence | AC-42 — stub preserved bytes-for-bytes; regression test pins `cache.gc.stub` log line |
| F11 | harden | `capture_spanning_events` fixture binding | AC-46 — defined in `tests/integration/cli/conftest.py`; reads interim JSON-lines from `<cache_dir>/../events/spanning/append.jsonl` |
| F12 | nit | AC4 self-contradiction (kwargs-only enforcement + "positional vs kwargs" comparison) | AC-6 pinned (`*` after definition; positional → `TypeError`) |
| F13 | nit | TTL parametrize used only the default (7 days) | AC-31 — `(ttl_days, age_days, expected_evicted)` parametrize over multiple rows + reject corpus |

### Test-Quality critic — 17 findings (5 blocks / 9 hardens / 3 nits)

| # | Tag | Issue | Resolution |
|---|---|---|---|
| TQ1 | block | No test pins the declared byte layout / `\x1f` separator integrity | AC-7 (`content_hash_bytes(payload)` equality) + AC-9 (boundary-shift collision test) |
| TQ2 | block | `base[vary] + "x"` parametrize is fragile (off-by-one collisions) | AC-8 rewritten with same-length distinct-class mutations (resolved by F2) |
| TQ3 | block | `bytes_reclaimed >= 2` is mutant-friendly | AC-30 — exact equality `result.bytes_reclaimed == sum(stat().st_size before unlink)` |
| TQ4 | block | `BundleCacheStore.put` no atomicity / mode tests | AC-16 + `test_put_writes_atomically_no_residual_tmp` + `test_put_file_mode_0600` |
| TQ5 | block | `test_corrupt_file_returns_none_and_warns` does NOT assert file survives | AC-18 — explicit `corrupt_path.exists()` assertion |
| TQ6 | harden | No pure helpers / property tests for the GC's logical core | AC-24 + AC-25 — `_parse_ttl_seconds` / `_is_evictable` / `_should_run_amortized` extracted; Hypothesis metamorphic properties added |
| TQ7 | harden | TTL boundary unpinned (strict `>` vs `>=`) | AC-29 — exact-7-days-old kept; one second older evicted |
| TQ8 | harden | `monkeypatch.setattr("time.time", lambda: time.time() + 86401)` recursive | AC-40 — capture `real_time` ref, monkeypatch `codegenie.plugins.cache_gc.time.time` (module-local) |
| TQ9 | harden | `.gc-stamp` mtime not observed in noop test | AC-41 — bound to `t_before <= float(stamp.read_text()) <= t_after` |
| TQ10 | harden | CLI test missing empty-cache case | AC-44 — parametrize over (seed_stale: True/False); empty cache also emits exactly one event with `entries_evicted=0` |
| TQ11 | harden | `args_canonical` re-canonicalization contract unpinned | AC-12 — composer treats as opaque bytes |
| TQ12 | harden | Env-reader needs reject corpus parametrize | AC-31 — corpus `{"", "0", "-1", "7.5", "+7", "not-an-int", "  ", "1e2", "0x7"}` |
| TQ13 | harden | `test_gc_stamp_updated_atomically` is point-in-time weak | AC-35 documents the limit honestly + parseable-float invariant |
| TQ14 | harden | `Bundle` JSON round-trip not asserted | AC-19 — round-trip canary at boundary (catches tuple↔list ambiguity here, not at S6-04) |
| TQ15 | nit | Intent comments on load-bearing assertions | Added inline (red tests carry "ADR-0008 correctness" / "Gap 4 fix" / "two emits corrupt the chain" comments) |
| TQ16 | nit | No AST chokepoint test | AC-13 + new `test_cache_no_blake3_import.py` |
| TQ17 | nit | Determinism test runs only 2× | AC-11 — N=100 |

### Consistency critic — 14 findings (4 blocks / 4 hardens / 6 nits)

| # | Tag | Issue | Resolution |
|---|---|---|---|
| C-A | block | `BundleCacheError(CodegenieError)` markers-only contradicts `reason=` kwarg call | AC-3 — frozen Pydantic `BundleCacheErrorModel(BaseModel)` + thin `BundleCacheRaise(CodegenieError)` wrapper (S3-01 `TCCMParseError` + S3-04 `BundleBuilderRaise` precedent) |
| C-B | block | `SemverVersion` newtype dangling | AC-5 — `str` for `plugin_version`; Notes DP-B records the deferral |
| C-C | nit | `PluginId` import path not enumerated | Implementation outline §2 enumerates imports |
| C-D | block | `bytes_hash` does not exist in `codegenie.hashing` | AC-7 + outline §2 pin to `content_hash_bytes` (already prefix-tagged; outline pseudocode's double-`"blake3:"` bug fixed) |
| C-E | harden | `os.rename` → `os.replace` | Every AC + outline + Notes rewritten; AC-35 explicit |
| C-F | nit | Filename-without-`blake3:` invariant only in Notes | AC-14 — on-disk filename `<64-hex>.json` |
| C-G | block | `cache_gc_completed` not in arch §C9 `event_type` Literal | AC-23 — additive arch edit; cites arch line ~1077's additive-extension authorization. AC-45 pins the interim wire format so the CLI integration test is on a stable substrate |
| C-H | harden | `fcntl.flock` on `BundleCacheStore.put` unjustified | AC-16 — `flock` dropped from blob store; AC-39 retains `flock` for `.gc-stamp` lock (the one place it's justified) |
| C-I | nit | `.gc-stamp` location not pinned as AC | AC-34 |
| C-J | harden | ADR-0008 env-var ceiling commits to two; this story adds a third | AC-47 — additive ADR-0008 postscript |
| C-K | (ok) | `CacheGcCompletedEvent` field shape consistent with arch §C9 | No change |
| C-L | block | Existing `cache gc` stub coexistence not pinned | AC-42 (resolved jointly with F10) |
| C-M | nit | AC ↔ Goal traceability — orchestrator-path event AC missing | AC-32 (resolved jointly with F8) |
| C-N | nit | `Bundle` JSON-roundtrip coupling parked in Notes | AC-19 — canary test landed here (5 lines) |

### Design-Patterns critic — 12 findings (0 blocks / 6 hardens / 6 nits-as-Notes)

| # | Tag | Issue | Resolution |
|---|---|---|---|
| DP1 | harden | Env read at `__init__` ties construction to env state | AC-26 — env read deferred to `.run()`; constructor accepts `ttl_seconds: int \| None` |
| DP2 | harden | Functional core / imperative shell missing | AC-24 (pure helpers) + AC-25 (AST purity fence) |
| DP3 | harden | `cache_dir: Path` contradicts S3-04 alignment to `SandboxedPath` | AC-14 + AC-20 + AC-26 — `SandboxedPath` everywhere; `__annotations__` test pins |
| DP4 | nit-as-Notes | Sum-type discipline on `trigger` future dispatch | Notes paragraph on `match` + `assert_never` future site (no dispatch ships in S3-05) |
| DP5 | nit-as-Notes | `args_canonical: str` primitive obsession — S3-04 deferred to S3-05 | Notes DP-C records the lineage; rule-of-three still not met (2 callers) |
| DP6 | harden | `BundleCacheKey` newtype rule-of-three met (composer + put + get) | AC-4 — newtype added to `identifiers.py`; construction funneled through composer |
| DP7 | nit-as-Notes | Cache-key Open/Closed seam (Phase 4+ digest inputs) | Notes DP-E — keep explicit 8-kwarg signature today; elevate when 9th input + second composer appear |
| DP8 | nit-as-Notes | Evictable-families registry | Notes DP-F — defer; one family today |
| DP9 | nit-as-Notes | `_fs_atomic` extraction at 2 of 3 callers | Notes DP-G — sharpens the story's existing refactor note; flags that this story itself adds a third atomic-write site (so the executor may elevate early at their discretion) |
| DP10 | harden | Event missing `wall_clock_iso` + `duration_ms` for Phase 9 latency correlation | AC-20 + AC-21 — both fields added; AC-27 prescribes computation via `time.monotonic_ns()` + `datetime.now(timezone.utc)` |
| DP11 | nit-as-Notes | CLI coexistence rationale | Notes paragraph confirming two CLIs > one flag-discriminated CLI |
| DP12 | harden | `CacheGcResult` ↔ `CacheGcCompletedEvent` field duplication | AC-22 — `from_result(...)` classmethod + field-set drift canary test |

## Stage 3 — researcher

**Not invoked.** No critic finding tagged `NEEDS RESEARCH`. All proposed tests are standard pytest / Hypothesis / AST; all proposed patterns have repo precedent (S3-01 TCCMParseError shape, S3-02 `_parse_max_age_seconds` env reader, S3-04 `_compose_entry` purity + `SandboxedPath` alignment, Phase-0 `cache/store.py` atomic-write discipline).

The strongest non-obvious technique applied — Hypothesis metamorphic property "older entries are always at-least-as-evictable as newer ones" — is canonical property-based-testing methodology with a clear precedent in S3-02's `_is_stale_pure` + `(days, age_days)` property, so it ships inline without external research.

## Stage 4 — synthesizer + editor

Conflict resolution applied per priority `Consistency > Coverage > Test-Quality > Design-Patterns`:

- **C-A (Pydantic error model)** dominates the BundleCacheError shape; consistency with S3-01 + S3-04's HARDENED precedent locks the answer.
- **C-G (additive arch edit + interim wire format)** wins the event-emission substrate question (the alternative — defer emission to S6-04 entirely — would leave Gap 4 only partially fixed, since the operator CLI is the user-facing half of the gap).
- **DP6 (BundleCacheKey newtype)** elevated to AC because three concrete call sites in this story alone meet rule-of-three; cost is one `NewType` line.
- **DP5 (CanonicalArgsJson)** kept as Notes — second user, not third; same reasoning as S3-04 used to defer.
- **DP7 / DP8 (cache-key Open/Closed seam + evictable-families registry)** kept as Notes — Rule 2 / explicit-at-callsite trumps premature abstraction at 1–2 callers.
- **TQ3 + F2 + TQ1 + TQ2** all attack different facets of the same mutation-resistance gap and were resolved jointly with three AC changes (AC-7 declared-order byte layout, AC-8 same-length distinct-class mutation table, AC-9 boundary-shift collision test) and the new `_MUTATION` table in the red test.

Story edits applied in-place:

- **Header.** `Status: Ready` → `Status: HARDENED`; ADRs honored list expanded from 2 to 6 (adds ADR-0010 for the typed-error shape, ADR-0001 for the hashing chokepoint, ADR-0011 for cache-permissions, plus the additive arch §C9 edit and the additive ADR-0008 amendment).
- **Validation notes** block added under the header summarizing every change (~50 bullets).
- **Context.** Rewritten — three deliverables enumerated, with the ADR-0008 / ADR-0001 / atomicity-discipline anchors.
- **References.** Rewritten with correct hashing function names (`content_hash_bytes` etc.), correct file:line citations (`cli.py:898-912`, `cache/store.py:118-168`, `errors.py:21-183`, `identifiers.py:54-83`), and S3-01 + S3-04 validation-report cross-references.
- **Goal.** Rewritten — pins SandboxedPath, env-read-at-run(), `wall_clock_iso` + `duration_ms` on event, exactly-once emission, three veto-strength invariants.
- **Acceptance criteria.** Rewritten from ~17 unnumbered bullets into 50 numbered ACs grouped: Module + types (AC-1..5), Cache key composer (AC-6..13), BundleCacheStore (AC-14..19), Result + event models (AC-20..23), BundleCacheGc pure-helpers + run + amortization (AC-24..33), `.gc-stamp` semantics (AC-34..41), CLI (AC-42..46), ADR amendments (AC-47), Gate (AC-48..50).
- **Implementation outline.** Rewritten — additive newtype, explicit imports list, pure helpers as a first-class section, additive CLI command + interim emitter shim, additive arch + ADR edits.
- **TDD plan — red.** Rewritten — every test now uses `BundleCacheRaise(model=...)` shape; declared-order byte-layout pin uses `content_hash_bytes`; `_MUTATION` table makes the participation test mutation-resistant; boundary-shift collision test; separator-poisoning parametrize; `Bundle` JSON-roundtrip canary; full AST purity test and AST chokepoint test as their own files; integration test parametrizes over `seed_stale: True/False`; `cache gc` stub regression.
- **TDD plan — refactor.** Trimmed; surfaces the `_fs_atomic` rule-of-three question honestly.
- **Files to touch.** Expanded — 13 files (was 7), adds AST tests + conftest fixture + arch + ADR edits.
- **Out of scope.** Expanded — `CanonicalArgsJson` lineage, `SemverVersion` deferral, EventLog/zstd/chain split.
- **Notes for the implementer.** Substantially expanded — 12 bullets covering load-bearing invariants, every deferral with lineage to the prior validation, `.gc-stamp` discipline, CLI coexistence, fail-loud rationale.

## Verdict — HARDENED

The story is now ready for `phase-story-executor`. Every block became a typed AC; every harden became an AC or a Notes paragraph with the appropriate deferral rationale; nits were promoted to ACs where the test bar required it and demoted to Notes otherwise.

The four veto-strength invariants each have at least one AC + at least one mutation-resistant test or structural defense:

1. **ADR-0008 cache-key correctness** — AC-7 (declared-order byte layout) + AC-8 (mutation-resistant participation) + AC-9 (boundary-shift collision) + AC-10 (separator-poisoning).
2. **No direct `blake3` import** — AC-13 (AST test) + AC-50 (import-linter).
3. **Strict `<` TTL boundary** — AC-29 (exact-7-days-kept test) + AC-24 (`_is_evictable` Hypothesis property).
4. **Exactly-one event per `run()`** — AC-32 (helper-level recording fake) + AC-44 (CLI integration, parametrized over populated + empty cache).

Open cross-phase items the executor should surface if encountered:

1. **S3-04 ships `Bundle` with `tuple[BundleEntry, ...]`?** — AC-19 round-trip canary catches the gotcha here; if it fails, S3-04 normalizes to `list` and S3-05 is unblocked.
2. **S3-03 ships `VulnIndex.digest` returning `BlobDigest`?** — Composer accepts `BlobDigest` (newtype = `str`) so any `VulnIndex` shape that exposes a `digest` attribute satisfies the contract.
3. **S6-01 spanning-event wire format** — AC-45 pins an uncompressed JSON-lines interim format; S6-01 absorbs it additively into the chained zstd file. The integration test's `capture_spanning_events` fixture is wire-format-bound; only the decoder swaps.
