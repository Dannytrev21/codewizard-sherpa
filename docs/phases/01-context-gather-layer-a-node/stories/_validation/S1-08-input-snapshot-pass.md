# Validation report — S1-08 Pre-dispatch input-snapshot pass (Gap 1)

**Story:** [S1-08-input-snapshot-pass.md](../S1-08-input-snapshot-pass.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S1-08 lands `phase-arch-design.md §"Gap analysis"` Gap 1: the coordinator pins each probe's `declared_inputs` fingerprint set (path, mtime_ns, size, blake3 content_hash) at dispatch time and the memo's cache gains a `(content_hash,)` key shape sourced from the snapshot. The original draft had a sound Goal but 7 block-tier defects, 22 harden-tier gaps, and 4 design-pattern opportunities that, left unaddressed, would have produced a story the executor could not implement faithfully (wrong import path, wrong wiring target, self-contradicting handling of oversize / symlink / OSError, TOCTOU-closure test that couldn't prove the closure, silent Windows correctness bug on path canonicalization).

The four critics ran in parallel against `phase-arch-design.md`, ADR-0002, Phase 0 ADR-0001 / ADR-0007 / ADR-0008 / ADR-0010, S1-06's and S1-07's hardened stories, the S1-07 validation report, the current `src/codegenie/coordinator/{coordinator,budget}.py`, `src/codegenie/probes/base.py`, `src/codegenie/hashing.py`, and `src/codegenie/parsers/_io.py`. No `NEEDS RESEARCH` findings — every weakness is answerable from authority docs + Phase 1 precedent. Stage 3 (researcher) skipped per skill's token-economy guidance.

**The most load-bearing seven block-tier issues:**

1. **`InputFingerprint` import path was wrong.** Story referenced `codegenie.coordinator.input_snapshot` (which does not exist). S1-06 hardening moved the newtype into `src/codegenie/probes/base.py` (the contract surface). The original red commit would have failed with `ModuleNotFoundError` for the wrong reason. CN1 + TQ1 + CV1.
2. **`ProbeContext` vs `BudgetingContext` wiring target wrong.** AC-3 said "assigned to that probe's `ProbeContext`" — but the runtime ctx is `BudgetingContext` (S1-07 hardening lesson). S1-07 already mirrored `input_snapshot` onto `BudgetingContext`; S1-08's wiring must go through `_make_probe_context → BudgetingContext`. Hardened: AC-16, AC-17, AC-18 pin the wiring at the runtime-ctx site. CN2 + TQ2 + CV2.
3. **ADR-0002 amendment missing.** ADR-0002 §Consequences currently says "The Gap #1 improvement ... is documented as a future amendment to this ADR if Phase 14's concurrent-gather threat model demands it. This story lands the improvement now." So S1-08 MUST amend ADR-0002 §"`ParsedManifestMemo` semantics" (Key bullet) and §Consequences. Hardened: AC-22 + doc-grep test. CN3.
4. **Self-contradictions on oversize / symlink / OSError handling.** Three different prescriptions for oversize (AC-2 said "cap at 50 MB", Green said "<oversize>", Notes said "Option (b) is simpler... Use it"); two for symlink (Green: `<refused>`; never pinned as AC); two for OSError (Green: blanket `except OSError`; Notes: per Rule 12 raise on unexpected). Hardened: AC-9 (oversize → sentinel + event), AC-10 (symlink → sentinel + retry semantics), AC-11 (narrow catch — `ELOOP` and `FileNotFoundError` only; everything else propagates; parametrized test catches blanket OSError catch). CN7 + CV5 + CV6 + CV7 + TQ4 + TQ5 + TQ7.
5. **TOCTOU-closure red test was provably useless.** The original `test_memo_key_uses_content_hash_not_live_stat` bumped `mtime_ns` via `p.touch()` on a file with identical content — `content_hash` was naturally equal, so multiple wrong implementations all return `a is b`. The actual Gap 1 scenario is **bytes change** mid-gather with the snapshot pinning the parse. Hardened: T-16 (`test_snapshot_pins_parse_against_concurrent_byte_change`) overwrites bytes with different size+content between two adapter calls and asserts identity. TQ8 + CV16.
6. **Path-canonicalization protocol unpinned — silent Windows correctness bug.** `fp.path` shape (red test used `.as_posix()`; Notes adapter used `str(path.resolve())`) silently diverges on Windows: adapter's lookup key never matches → memo falls back to legacy stat-tuple key → the TOCTOU window the story is supposed to close stays open. Hardened: AC-12 pins `fp.path == str(matched_path.resolve())` exactly; T-8 + T-11 close the roundtrip. CN9 + CV13 + DP10 + TQ13.
7. **AC-5 (additive memo signature) and AC-7 (snapshot-missing path) contradicted each other.** AC-7 said memo returns `None` for paths not in the snapshot; AC-5 said `content_hash=None` falls back to the S1-07 key (which parses and caches). Hardened: AC-14 + AC-15 reconcile — sentinel content_hash (`<oversize>`/`<refused>`) bypasses the memo (returns `None`); legitimate `content_hash=None` falls back to S1-07's stat-tuple key; the adapter's `by_path.get(path)` returns `None` for non-snapshotted paths which triggers the legacy path. CN9 + CV15 + TQ9 + TQ10.

**Departure from arch surfaced and recorded (per Rule 7).** Arch line 990 prescribes a **full key flip** (`(content_hash,)` replaces `(abspath, mtime_ns, size)`); S1-08 ships the **additive** variant (legacy key preserved when `content_hash=None`). Rationale recorded in story §Context and ADR-0002 amendment AC-22: (a) preserves S1-07's hardened test suite intact, (b) supports non-coordinator callers (tests, ad-hoc CLI), (c) the coordinator's adapter always passes `content_hash=...`, so on-the-warm-path behavior is the arch-prescribed shape. No observable regression. CN4 (Option B applied).

**Design-pattern opportunities lifted from buried Notes into explicit ACs:**

- **Functional core / imperative shell split.** `_fingerprint_from_fd(fd, abs_path, *, max_bytes)` (pure-ish I/O orchestration over a single fd) inside the impure `compute_input_snapshot` shell. Pinned as Notes for implementer; the determinism property test (T-10) is the contract. DP2.
- **Per-probe policy injection (`max_bytes_per_file` kwarg).** The 50 MB cap is no longer a hardcoded literal; it's a keyword-only parameter with default `_DEFAULT_MAX_BYTES_PER_FILE: Final[int] = 52_428_800`. Phase 2's `IndexHealthProbe` (different cap for SCIP indexes) extends by addition. AC-1 + DP3.
- **Sentinel constants** `_CONTENT_HASH_OVERSIZE` / `_CONTENT_HASH_REFUSED` at module scope. AC-9 + AC-10 + AC-15. DP4.
- **`make_parsed_manifest_adapter` lifted from a buried Notes closure into a named, exported, testable helper.** AC-13 + T-11. This is the seam Phase 14's parallel snapshot will swap. DP5.
- **Module naming collision averted.** Notes originally said "extract to `coordinator/snapshot.py`"; that file already exists (S3-05 — builds `RepoSnapshot`). New module is `coordinator/input_snapshot.py`. AC-1 + DP1.
- **Closed module surface** via `__all__ = ["compute_input_snapshot", "make_parsed_manifest_adapter"]`. Mirrors S1-07 AC-20. DP12.
- **ADR-0001 chokepoint preserved.** AC-7 + AC-8 + T-4 pin `"blake3:"` prefix shape AND forbid direct `blake3` imports in the new module. DP7 + CN5.

**Three design-pattern opportunities deliberately deferred (rule-of-three not yet met):**

- `type InputSnapshot = frozenset[InputFingerprint]` alias — three use sites, but introducing it edits the frozen probe-contract surface (ADR-0007) and re-snapshots `tests/snapshots/probe_contract.v1.json`. Phase 2's `IndexHealthProbe` is the fourth consumer; that's the right ADR moment. DP9 + Notes.
- `FileEnumerator` Strategy — `Path.glob` vs `git ls-files` vs `os.walk`. Single strategy today; Phase 14 may demand the split. DP11.
- Smart constructor on `InputFingerprint` itself — `probes/base.py` is stdlib-only; cannot import `os`/`codegenie.hashing`. Smart-construction discipline lives in the snapshot module's `_fingerprint_from_fd` helper instead. DP6.

The synthesizer rewrote the story from **11 single-bullet ACs to 23 individually verifiable ACs**, replaced the TDD plan's 4 thin tests with **14 named tests** (T-1..T-16; T-1..T-13 in the helper file, T-14..T-16 in the coordinator-wiring file, plus one doc-grep test), added an ADR-0002 amendment AC, surfaced the `Notes for implementer` design-opportunity entries (functional-core split, future moves), and recorded the Rule-7 departure from arch in both the story and the ADR amendment. The story is now executable.

## Context Brief (Stage 1)

- **Goal as written:** Coordinator computes `frozenset[InputFingerprint]` for each probe's `declared_inputs` once before dispatch; freezes it on `ctx.input_snapshot`; `ParsedManifestMemo` keys parsed dicts by `content_hash` (not live `os.stat`); closes the TOCTOU window between cache-key derivation and probe parse.

- **Phase exit criteria touched:**
  - Arch §"Gap analysis" Gap 1 (lines 982–990) — full rationale; the seam.
  - Arch §"Component design" #3 — `ParsedManifestMemo`'s key gains content_hash shape.
  - Arch §"Data model" — `InputFingerprint` shape (S1-06 lands the type in `probes/base.py`).
  - Arch §"Edge cases" row 16 — mid-gather edit re-parses; this story preserves that on a per-probe basis.
  - Arch §"Process view" — sequence: Coordinator constructs memo, then per probe computes `input_snapshot`, then dispatches.
  - Arch §"Harness engineering" → "Logging strategy" — `probe.input_snapshot.computed` event (Phase 1 introduces this name; lives alongside `probe.memo.hit`/`probe.memo.miss`).

- **ADRs:**
  - ADR-0002 (this phase) — S1-08 amends §"`ParsedManifestMemo` semantics" (Key bullet → dual-shape) and §Consequences (resolved-in-this-ADR note).
  - Phase 0 ADR-0001 — single-chokepoint discipline for `blake3` / `hashlib`. The snapshot pass MUST use `hashing.content_hash_bytes(data)` on bytes already read through an `O_NOFOLLOW` fd. The new module must NOT import `blake3` directly.
  - Phase 0 ADR-0007 — `probes/base.py` is stdlib-only; `InputFingerprint` cannot grow a classmethod that imports `os` or `codegenie.hashing`. Smart-construction lives in the snapshot module.
  - Phase 0 ADR-0008 + ADR-0010 — the two trust boundaries the snapshot pass MUST NOT cross (it never writes to disk).

- **Predecessor state (load-bearing for S1-08):**
  - `src/codegenie/probes/base.py:39-44` — `InputFingerprint` NamedTuple with fields `(path: str, mtime_ns: int, size: int, content_hash: str)`.
  - `src/codegenie/probes/base.py:53-54` — `ProbeContext.parsed_manifest`/`input_snapshot` fields (None-default).
  - S1-07 hardened story commits `BudgetingContext` to mirror those two fields (AC-15).
  - S1-07 hardened story commits the memo with `get(path)` signature and key `(str(path.resolve()), mtime_ns, size)`; `__all__ = ["ParsedManifestMemo"]`; allowlist injected via `__init__(*, allowlist=...)`.
  - `src/codegenie/hashing.py` — `content_hash(path)` opens the path directly (follows symlinks; do NOT call from snapshot); `content_hash_bytes(b)` is the correct chokepoint for the snapshot's `O_NOFOLLOW`-read bytes; returned form is `"blake3:<64-hex>"`.
  - `src/codegenie/coordinator/coordinator.py:230-239` — `_make_probe_context` returns `BudgetingContext`; gets called from `_dispatch_one:297`.

- **Open ambiguities surfaced:**
  1. Story's "ProbeContext" wiring contradicted runtime reality (`BudgetingContext`). Resolved by AC-16/17/18.
  2. Story said "memo flips" but signature was additive. Resolved by AC-14 (dual-shape, additive) + AC-22 (ADR amendment + departure record).
  3. Hash chokepoint — `content_hash(path)` vs `content_hash_bytes(b)`. Resolved by AC-7 + AC-8 + T-4.
  4. Sentinel string sentinels vs typed `Union` — resolved by `Final[str]` constants (string protocol preserved).
  5. Helper location — `coordinator.py` vs `coordinator/snapshot.py` (taken) vs `coordinator/input_snapshot.py` (new). Resolved by AC-1.
  6. Empty / no-match semantics — resolved by AC-6.
  7. Path canonicalization — `.as_posix()` vs `str(.resolve())`. Resolved by AC-12 (the latter, mandatorily).
  8. Per-probe vs per-gather snapshot scope. Resolved by AC-16.
  9. Case-sensitivity of `Path.glob`. Resolved by AC-3 + T-3.
  10. Rule-12 narrowing of OSError catch. Resolved by AC-11 + T-7 (parametrized).

## Stage 2 — Critic reports

Four critics ran in parallel. Each returned 10-20 findings tagged `block` / `harden` / `nit`. The synthesizer merged using priority `Consistency > Coverage > Test-Quality > Design-Patterns` and applied Rule 2 (Simplicity First) on design-pattern findings (no premature abstraction).

### Coverage (verdict: COVERAGE-RESCUE → patched to HARDEN)

20 findings (CV1–CV20). Top defects: import-path drift (CV1), runtime-ctx target wrong (CV2), helper-location ambiguity (CV3), `content_hash` prefix unpinned (CV4), oversize self-contradiction (CV5), symlink sentinel unpinned (CV6), Rule-12 propagation unpinned (CV7), empty-snapshot semantics unpinned (CV8), `parsed_manifest` snapshot-missing fallback contradicted itself (CV9), no integration test for gather() wiring (CV10), per-probe scoping unpinned (CV11), event structured-field shape unpinned (CV12), path canonicalization unpinned (CV13), overlapping-glob dedup commentary-only (CV14), additive vs flip contradiction (CV15), TOCTOU-closure test could not prove TOCTOU closure (CV16), oversize event name unpinned (CV17), `Path.glob` non-glob fast-path harmful (CV18), AC count below phase bar (CV19), `O_NOFOLLOW` symmetry with hashing.py unpinned (CV20).

All 20 resolved into the hardened story's ACs and TDD plan. CV19 raised the AC count from 11 to 23, matching the phase bar set by S1-06 (18) and S1-07 (22).

### Test Quality (verdict: TESTS-RESCUE → patched to HARDEN)

16 findings (TQ1–TQ16). Per-test mutation-fuzzing labels showed 3 of 4 original tests failed mutation-fuzzing (only `test_snapshot_content_hash_changes_with_content` partially passed; the rest were trivially survivable). Top defects mirror the coverage findings: import path (TQ1), no coordinator wiring test (TQ2), no `"blake3:"` prefix test (TQ3), no symlink test (TQ4), no oversize test (TQ5), no event-emission test (TQ6), no Rule-12 propagation test (TQ7), TOCTOU-closure test cannot distinguish content-hash from stat-tuple (TQ8), no additive-signature fallback test (TQ9), snapshot-missing-path contradiction (TQ10), no determinism property (TQ11), no per-probe independence test (TQ12), path canonicalization (TQ13), no `Path.glob` recursion/empty-result tests (TQ14), no overlapping-globs dedup (TQ15), helper-signature mismatch in TDD plan (TQ16).

All 16 resolved into 14 named tests (T-1..T-16) plus one doc-grep test, each annotated with AC + caught mutation. Test count matches the phase bar set by S1-07 (~16 named tests).

### Consistency (verdict: CONSISTENCY-HARDEN)

14 findings (CN1–CN14). Five block-tier (CN1–CN4 plus CN9). Six harden-tier (CN5–CN11). Three nit/touchup (CN12–CN14). Authority contradictions resolved by editing the story to match the source of truth:

- CN1 (S1-06 import-path) → fixed via AC-2 + grep test.
- CN2 (S1-07 runtime-ctx) → fixed via AC-16/17/18.
- CN3 (ADR-0002 amendment) → fixed via AC-22 + doc-grep test.
- CN4 (full-flip vs additive) → Rule-7 surfaced; departure recorded in story §Context + AC-22.
- CN5 (ADR-0001 chokepoint) → fixed via AC-7 + AC-8 + T-4.
- CN6 (stale `final-design.md "Synthesis ledger"` reference) → reference corrected to `phase-arch-design.md §"Gap analysis"` Gap 1.
- CN7 (Rule 12 contradictions) → fixed via AC-11 + T-7.
- CN8 (determinism commitment) → fixed via AC-21 + T-10.
- CN9 (`mtime_ns`/`size` from same fd) → fixed via AC-4 step (ii).
- CN10 (`Path.glob` case-sensitivity) → fixed via AC-3 + T-3.
- CN11 (50 MB literal) → fixed via AC-1 (`_DEFAULT_MAX_BYTES_PER_FILE: Final[int]`).
- CN12 (Goal #4 cosmetic) → surfaced in story Notes.
- CN13 (`Mapping[str, Any]`) → tightened via AC-14 signature.
- CN14 (`localv2.md §4`) → confirmed unaffected via AC-23.

### Design Patterns (verdict: DESIGN-HARDEN)

12 findings (DP1–DP12). Two block-tier (DP1 module collision; DP10 path canonicalization — also raised by Coverage CV13 and Consistency CN9). Six harden-tier (DP2–DP7 + DP12) lifted into the implementation outline + ACs. Four future-moves (DP8–DP11) recorded in Notes for the implementer (rule-of-three not yet met).

Synthesizer applied Rule 2 (Simplicity First):

- DP1 (module name collision) → fixed to `coordinator/input_snapshot.py` in AC-1.
- DP2 (functional-core split) → as Notes for implementer; T-10 enforces the determinism property without forcing the split.
- DP3 (per-probe `max_bytes_per_file` kwarg) → AC-1 makes it keyword-only.
- DP4 (sentinel constants) → `Final[str]` constants in implementation outline + AC-9/AC-10/AC-15.
- DP5 (adapter as named helper) → AC-13 + T-11.
- DP6 (smart constructor) → colocated as `_fingerprint_from_fd` in implementation outline; AC-4 names it explicitly; Notes records why it can't live on `InputFingerprint` itself (ADR-0007).
- DP7 (`hashing.content_hash_bytes` chokepoint) → AC-7 + AC-8 + T-4.
- DP8 (Path.exists fast path) → Notes removes the suggestion.
- DP9 (`type InputSnapshot` alias) → Notes future move.
- DP10 (path canonicalization) → AC-12 + T-8.
- DP11 (`FileEnumerator` Strategy) → Notes future move.
- DP12 (`__all__` declaration) → AC-1.

## Stage 3 — Researcher

**Skipped.** No critic finding tagged `NEEDS RESEARCH`. Every weakness is answerable from authority docs + Phase 1 precedent + the existing Phase 0 source tree. The canonical patterns invoked — `O_NOFOLLOW`, `os.fstat`-via-fd, `structlog.testing.capture_logs`, `Final[str]` constants, `__all__`-closed module surfaces, additive signatures preserving caller call sites — are all stdlib-/structlog-/Phase-0-documented.

## Stage 4 — Synthesis

Conflict resolution applied per skill priority `Consistency > Coverage > Test-Quality > Design-Patterns`:

- **Consistency vs Coverage (full-flip vs additive).** Arch prescribes full flip; story shipped additive. Consistency would win → flip. But the additive variant preserves S1-07's hardened test suite (which the executor would otherwise be required to rewrite inside this PR — Rule 3 violation, surgical changes) AND supports non-coordinator callers. Rule 7 applied: departure surfaced explicitly in story §Context, AC-22 amends ADR-0002 to record the reconciliation. **Departure ratified.**
- **Coverage vs Design-Patterns (Notes burial vs explicit AC).** Coverage wants every load-bearing decision pinned as AC; Design-Patterns wants pattern advice as Notes (not ACs). Synthesizer rule: if the pattern crosses the rule-of-three threshold OR is a load-bearing correctness invariant, lift into an AC. Path-canonicalization (DP10): correctness — AC. `make_parsed_manifest_adapter` named helper (DP5): seam for Phase 14 (third concrete consumer) — AC. Functional-core split (DP2): correctness benefit but Rule 2 says wait — Notes. Smart constructor (DP6): two siblings, but ADR-0007 forbids the colocation; the alternative location is the natural Notes mention.
- **Test-Quality vs Design-Patterns.** Test-Quality wins always — if a pattern hardens a test, lift the test into the TDD plan.

The verdict is **HARDENED**: the original story had real but fixable weaknesses; all edits applied to the story file in place; the story is ready for `phase-story-executor`.

## Files written

- Edited: `docs/phases/01-context-gather-layer-a-node/stories/S1-08-input-snapshot-pass.md` (full rewrite preserving Goal; 23 ACs; 14 named tests; ADR-0002 amendment AC; Validation notes appended).
- New: `docs/phases/01-context-gather-layer-a-node/stories/_validation/S1-08-input-snapshot-pass.md` (this file).

## Recommended next step

`phase-story-executor` on the hardened story. The story is now self-contained (every load-bearing decision is an AC or a TDD-plan test); the executor's Validator pass will have concrete bindings to check against. Expected effort: M (3 in-place edits to coordinator code + new `input_snapshot.py` module + memo signature extension + ADR amendment).
