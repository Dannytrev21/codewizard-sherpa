# Validation report — S2-03 Content-addressed score cache

**Story:** [`../S2-03-content-addressed-cache.md`](../S2-03-content-addressed-cache.md)
**Validated:** 2026-05-26
**Validator:** phase-story-validator skill (Stage 1–4, four parallel critics, no live research lookup)
**Verdict:** **HARDENED**
**Status transition:** `Ready` → `HARDENED`

---

## Why this validation fired

The story passes through `phase-story-executor` next. Its `Ready` draft had the right intent but several places where an autonomous executor could ship technically-passing-but-actually-wrong code:

1. The TDD plan's lock test asserts "two threads produce valid JSON" — but `BenchScore` JSON fits under `PIPE_BUF=4096`, so the kernel's `os.write` atomicity carries the test even with `fcntl.flock` deleted. The lock would be invisible.
2. The atomicity test patches `os.rename` and asserts suffixes — but the Phase 0 precedent uses `os.replace`, so patching `os.rename` is a no-op against a Rule 11–compliant impl.
3. `compose_cache_key` tests have `...` placeholders for the six inputs — if filled with identical values, *any* positional swap of two inputs is undetectable (they hash to the same bytes).
4. The story prescribes adding a `bytes_hash` helper to `hashing.py`, but `content_hash_bytes` already exists at line 85 (Phase 0 S2-03 era) — a literal-follow of the outline edits the chokepoint unnecessarily.
5. The on-disk filename convention is left to the implementer ("pick one — document").
6. `cache_key` is raw `str` (CLAUDE.md says newtype for domain IDs).
7. `compose_cache_key` is six kwargs (silent positional extension; Open/Closed regression vs a `CacheKeyInputs` dataclass).

---

## Stage 1 — Context Brief

- **Goal (verbatim):** `codegenie.eval.cache` exposes `get/put/gc` with content-addressed keys; `put` is atomic under `fcntl.flock`; `get` is lock-free + corrupt-as-miss with structured warn; `gc` evicts by mtime.
- **Phase exit criteria the story serves:** `High-level-impl.md §Step 2` done criteria — round-trip works; mid-write kill leaves prior value intact; corrupt is miss; warm rerun ≤ 8 s (S5 done criterion this enables).
- **ADRs honored:** Phase 0 ADR-0001 (BLAKE3 chokepoint), Phase 0 ADR-0011 (`0700`/`0600` modes), Phase 6.5 ADR-0005 (`cassette_canary_pin` in cache key).
- **Sibling-family lineage:** This is the **third** content-addressed cache in the codebase (after Phase 0 `cache/store.py`'s `CacheStore`, and the Phase 4 RAG embeddings cache `cache_embeddings.py` indirectly). Rule-of-three not yet met for extracting `_atomic_write_bytes` to a shared `codegenie.fs` module — duplication intentional.
- **Open ambiguities resolved before Stage 2:** filename shape (hex-only, per Notes recommendation); `bytes_hash` vs `content_hash_bytes` (use existing). `os.rename` vs `os.replace` (Phase 0 uses `os.replace`).

---

## Stage 2 — Critic findings

Four critics ran in parallel. Severity tags: **block** (story can't ship), **harden** (real weakness, fixable), **nit** (polish).

### Coverage critic — 1 block, 9 harden, 5 nit

| ID | Severity | What | Action taken |
|---|---|---|---|
| C-1 | harden | `gc` on missing/empty `cache_dir` not in ACs | Added AC: `gc(missing_dir) == 0`, no raise |
| C-2 | harden | `get` on missing `cache_dir` not in ACs | Added AC: returns `None` without warning |
| C-3 | **block** | `mkdir parents` is in outline but not contract | Promoted to AC; round-trip test against `tmp_path / "never" / "created" / "cache"` |
| C-4 | harden | `gc(retain_days=0)` boundary unspecified | Added AC documenting strict `<` operator + four-row boundary parametrize |
| C-5 | harden | `.tmp` orphan policy unspecified | Documented: `gc` leaves `.tmp` alone (in-flight `put`s); reaping deferred to a separate story |
| C-6 | harden | Lock-file mode `0600` not asserted | Added AC + `test_put_writes_files_with_mode_0600` |
| C-7 | harden | `put` overwrite semantics undefined | Added AC: overwrite is atomic, no `FileExistsError`; `get` returns the new value |
| C-8 | harden | Disk-full `OSError` propagation not asserted | Added AC + parametrized test over four crash points |
| C-9 | harden | `structlog.warn` event structure not asserted | Tightened AC + test uses `structlog.testing.capture_logs()` and asserts both `cache_key` and `path` |
| C-10 | nit | `cassette_canary_pin` AC overlapped uniqueness | Rewritten as scoped-invalidation: rotation of A's pin must not change B's key (ADR-0005 consequence) |
| C-11 | harden | Multi-entry mixed-age `gc` counting not in ACs | Tightened AC + multi-entry test |
| C-12 | nit | `harness_version` provenance is S3-01's | No change; flagged for traceability only |
| C-13 | nit | `put(k, None, dir)` undefined | No change — mypy-strict catches; runtime is belt-and-suspenders |
| C-14 | nit | `__all__` exact-equals not asserted | Added AC + fence test `test_module_all_is_exact` |
| C-15 | harden | Reader-during-writer safety not asserted | Added AC + test that interleaves `get` with `monkeypatch`-slowed `os.replace` |

### Test-Quality critic — 5 block, 6 harden, 1 nit, 1 NEEDS RESEARCH

| ID | Severity | What | Action taken |
|---|---|---|---|
| TQ-1 | **block** | Test 4 patches `os.rename` — vacuous against `os.replace` impl; mocks shape not semantics | Rewrote as `test_put_uses_pid_token_tmp_then_os_replace` — spies `os.replace`, checks tmp file pattern (pid+token) and target absence at moment of replace |
| TQ-2 | **block** | Test 6 (two threads + valid JSON) — lock invisible because JSON < PIPE_BUF | Rewrote as `test_put_holds_exclusive_lock_during_write` — pauses `put` mid-`os.replace`, asserts sibling `LOCK_EX | LOCK_NB` raises `BlockingIOError` |
| TQ-3 | harden | Tests 4+5 conflate three crash scenarios | Replaced with `test_previous_value_preserved_across_any_crash_point` parametrized over `os.write`, `os.fsync`, `os.replace` victims |
| TQ-4 | **block** | `caplog` is wrong for structlog; name-only assertion | Rewrote using `structlog.testing.capture_logs()`; asserts `cache_key` + `path` kwargs + `log_level == warning` |
| TQ-5 | **block** | `...` placeholders mask positional swaps | Defined `_DISTINCT_INPUTS` with six disjoint role-encoding values; added `test_compose_cache_key_resists_positional_swap` over `itertools.combinations(range(6), 2)` |
| TQ-6 | harden / NEEDS RESEARCH | Arity-byte missing vs Phase 0 `identity_hash` | Resolved by Cn-5: kw-only six-field signature pins arity by API; input contract bans `\x1f` (documented in AC + Notes). No code change to add arity byte. |
| TQ-7 | **block** | No corrupt-then-recover round-trip | Added `test_corrupt_then_put_recovers` |
| TQ-8 | harden | GC boundary, skip-`.lock`, skip-`.tmp` untested | Added four tests: `test_gc_retain_days_boundary` (parametrized), `test_gc_does_not_evict_lock_file`, `test_gc_does_not_evict_tmp_orphans`, plus missing/empty dir tests |
| TQ-9 | harden | File modes asserted in AC, not test | Added `test_put_writes_files_with_mode_0600` + `test_put_creates_cache_dir_with_mode_0700` |
| TQ-10 | harden | Hypothesis property test missing from TDD plan despite AC | Added `test_compose_cache_key_determinism_property` with `hypothesis.strategies.text` excluding `\x1f` |
| TQ-11 | harden | `os.rename` vs `os.replace` consistency | Standardized on `os.replace` throughout story + Notes + tests |
| TQ-12 | harden | Single-row pin uniqueness doesn't prove ADR-0005 scoping | Added explicit `test_compose_cache_key_canary_rotation_does_not_affect_sibling` |
| TQ-13 | nit | Kw-only not enforced at runtime | Replaced concept with `CacheKeyInputs` dataclass — positional `str` rejection is automatic |

### Consistency critic — 3 harden, 1 conditional, 6 nit

| ID | Severity | What | Action taken |
|---|---|---|---|
| Cn-1 | harden | `bytes_hash` dead lift — `content_hash_bytes` exists | Deleted `bytes_hash` from outline, Notes, and Files-to-touch row |
| Cn-2 | harden | `os.rename` → `os.replace` (Phase 0 precedent) | Standardized in Goal, AC, Context, Outline, Notes |
| Cn-3 | harden | Single `<key>.tmp` slot vs Phase 0 pid+token | Adopted Phase 0 pid+`secrets.token_hex(4)` pattern as AC + outline |
| Cn-4 | nit | Duplicating `_atomic_write_bytes` vs sharing | Notes documents the intentional duplication + path to future promotion (rule of three) |
| Cn-5 | nit | `compose_cache_key` missing arity byte | Documented in Notes: kw-only single-dataclass-arg signature pins arity at six by API; input contract bans `\x1f` |
| Cn-6 | nit | BLAKE3 chokepoint implicit | Added fence AC + AST-scan test `test_no_direct_blake3_import` |
| Cn-7 | nit | `_WARNING_IDS` convention | Documented as scoped to probes (Phase 0 cache also omits) |
| Cn-8 | nit | `fcntl.flock` vs Phase 0 `O_APPEND` divergence | Documented in Notes as intentional (BenchScore JSON exceeds PIPE_BUF) |
| Cn-9 | harden | Unresolved filename convention | Promoted hex-only to AC; deleted hedge |
| Cn-10 | harden | `<key>.json` mode not asserted post-replace | Added AC: re-`chmod` after `os.replace`; test asserts mode |
| Cn-11 | nit | Goal sentence omits `compose_cache_key` | Widened Goal |
| Cn-12 | nit | Phase 0 ADR-0001 reference label | Updated reference to `0001-cache-content-hash-algorithm.md` |

### Design-Patterns critic — 1 block, 3 harden, 10 nit

| ID | Severity | What | Action taken |
|---|---|---|---|
| DP-1 | harden | Free functions vs arch's `class Cache` | Surfaced the conflict in Notes; chose free functions (component spec `phase-arch-design.md §src/codegenie/eval/cache.py` line 606 prescribes module-level `def`s; class diagram is a logical view); Notes name the revisit trigger (≥ 3 call sites) |
| DP-2 | harden | Primitive obsession on `cache_key: str` | Added AC: `CacheKey = NewType("CacheKey", str)` in `codegenie/types/identifiers.py` |
| DP-3 | harden | Six kwargs vs `CacheKeyInputs` frozen dataclass | Added AC + Notes — adding a future input becomes a structural type-check failure at every call site |
| DP-4 | **block** | Filename indecision (full key vs hex-only) | Resolved to hex-only as AC; deleted hedge |
| DP-5 | nit | `_atomic_write_bytes` rule of three | Notes documents the duplication + future promotion path |
| DP-6 | nit | Inline mode literals | AC requires `_FILE_MODE`/`_DIR_MODE` module-level constants |
| DP-7 | nit | `_cache_write_lock` return type | Outline specifies `Iterator[None]` |
| DP-8 | nit | `gc` returns `int` (could be `GcReport`) | Kept `int`; documented in Notes |
| DP-9 | nit | `get` collapses miss reasons to `None` | Kept; mirror Phase 0 (distinct structured events; single `None` return) |
| DP-10 | nit | Storage-backend Strategy seam | Notes documents `CacheBackend` Protocol shape for future-Phase 13+; do not introduce now (YAGNI per Non-goals #9) |
| DP-11 | nit | `harness_version` provenance | Confirmed strength (explicit DI); no change |
| DP-12 | nit | `compose_cache_key` input validation | Documented as pure bytes-to-hex; no validation; caller responsibility |
| DP-13 | (confirm) | Functional core / imperative shell | Confirmed clean split; no action |
| DP-14 | nit | `_WARNING_IDS` for non-probe modules | Documented as scoped to probes |

---

## Stage 3 — Researcher: **SKIPPED**

One `NEEDS RESEARCH` flag from TQ-6 (arity-byte) was resolvable from the Consistency critic's parallel analysis (Cn-5) — the kw-only signature pins arity by API, so a research lookup wouldn't move the answer. No live research run.

---

## Stage 4 — Synthesizer + Editor

### Conflict resolutions (priority: Consistency > Coverage > Test-Quality > Design-Patterns)

- **DP-1 (free functions vs class)** — Conflict between Design-Patterns ("arch diagram shows class") and Consistency ("arch component spec line 606 shows free functions"). Consistency wins on the *literal* arch spec (the component design is the source of truth; the class diagram is the logical view). Free functions retained; Notes surface the tradeoff and the revisit trigger.
- **DP-2 / DP-3 (newtype + dataclass)** — No conflict with arch or ADRs (the component spec gives signatures only; refinement is welcome). CLAUDE.md *"Never raw `str` for domain IDs"* + *"Extension by addition"* are load-bearing. Adopted as ACs.
- **TQ-6 / Cn-5 (arity byte)** — Resolution: the kw-only single-`CacheKeyInputs`-argument signature pins arity at exactly six by API; boundary-shift collisions are unreachable. Input contract bans `\x1f`; Notes document the divergence from `hashing.identity_hash`'s arity byte. No code change.

### Edits applied to the story file

1. Status: `Ready` → `HARDENED`.
2. ADRs honored: added Phase 0 ADR-0011 (modes) + updated label for ADR-0001.
3. New `## Validation notes (phase-story-validator, 2026-05-26)` block after the header summarizing the changes.
4. Context paragraph: `os.rename` → `os.replace`; filename `<key>.tmp` → `<hex>.tmp`; added cross-platform-safety note.
5. References: deleted stale `identity_hash` mention; called out `content_hash_bytes` by name + line number; clarified `_atomic_write_bytes` shape to mirror.
6. Goal sentence: widened to include `compose_cache_key`; added `gc` skip-`.lock`-and-`.tmp` clause.
7. Acceptance criteria: reorganized into **Typed surface**, **Composer semantics**, **`get` semantics**, **`put` semantics**, **`gc` semantics**, **Cross-cutting** sections. Net change: ~12 new ACs, ~5 tightened, 0 removed.
8. Implementation outline: replaced with a step-by-step outline that bakes in the `CacheKeyInputs` dataclass, `CacheKey` newtype, `_cache_write_lock` context manager, pid+token tmp suffix, `os.replace`, post-replace `os.chmod`, mode constants. Deleted dead `bytes_hash` lift.
9. TDD plan: replaced wholesale with mutation-resistant tests. Each test names the wrong-impl mutant it catches. Added structlog `capture_logs()` discipline, Hypothesis property test, ADR-0005 scoped-invalidation test, three AST-scan fences (`no_blake3_import`, `no_hashlib_import`, `no_os_rename`).
10. Files to touch: removed `hashing.py` row; added `codegenie/types/identifiers.py`.
11. Out of scope: added `.tmp` orphan reaping, cache-backend Strategy seam, `_WARNING_IDS` convention scoping.
12. Notes for the implementer: rewrote into three groupings — **Hard constraints**, **Intentional Phase-0 divergences (surface, don't hide)**, **Design-pattern decisions baked into ACs**, **Operational notes**. Made every prior implicit choice explicit.

### Edits NOT applied

- Did not promote `_atomic_write_bytes` to a shared `codegenie.fs.atomic_write_bytes` module — rule-of-three not yet met (this is the second site). Notes flag the future path.
- Did not change `gc` return from `int` to a `GcReport` dataclass — current call sites only need the count + per-eviction log event (Phase 0 precedent).
- Did not introduce a `CacheBackend` Protocol — pure YAGNI per Non-goals #9. Notes document the seam shape for future-Phase 13+ adoption.
- Did not change the goal of the story or its scope (per skill's anti-goals).

---

## Final verdict

**HARDENED** — story is now ready for `phase-story-executor`. The core change classes:

- **Mutation-resistance.** Every test names the wrong-impl it catches. The previous lock/atomicity/composer tests were sound in *shape* but vacuous against the realistic mutants (PIPE_BUF-fits writes, `os.replace` substitution, equal-placeholder positional swap).
- **Open/Closed at the function-arg boundary.** `CacheKeyInputs` + `CacheKey` newtype convert future input additions from silent positional changes to loud type-check failures at every call site. This is the CLAUDE.md *"Extension by addition — no silent edits"* commitment applied where it matters for cache invariance.
- **Phase-0 conformance.** `os.replace`, pid+token tmp, post-`os.replace` `chmod`, mode constants, no direct `blake3` import, no `bytes_hash` invention. Rule 11 obeyed; Rule 7 respected (picked the more-tested pattern; didn't blend).
- **Boundary-condition ACs the Runner depends on day one.** `cache_dir` auto-creation, missing-dir is no-raise, GC on missing/empty dir, overwrite is atomic, `OSError` propagates, reader-during-writer safety.
- **No silent design indecision left for the implementer.** Filename shape, lock pattern, mode discipline, miss-reason discrimination, kw-only enforcement all pinned in ACs.

The executor can proceed.
