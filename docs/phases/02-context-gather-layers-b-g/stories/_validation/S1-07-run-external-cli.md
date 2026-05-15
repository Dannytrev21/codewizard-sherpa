# Validation report — S1-07-run-external-cli

**Verdict:** HARDENED
**Date:** 2026-05-15
**Pass:** 1
**Validator:** phase-story-validator skill

## Summary

S1-07 had **three BLOCK-tier consistency violations** (one of which would have caused the executor to either roll back already-merged work or ship a broken implementation) plus several test-quality and coverage gaps. All BLOCK items were resolved by editing the story in place; HARDEN items were applied. No `NEEDS RESEARCH` tags fired — Stage 3 skipped.

The story is now ready for the executor.

## Stage 1 — Context loaded

Files read:
- `docs/phases/02-context-gather-layers-b-g/stories/S1-07-run-external-cli.md` (original draft)
- `docs/phases/02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md` (especially §Consequences last bullet, §Decision Amendment 2026-05-15)
- `docs/phases/02-context-gather-layers-b-g/stories/S1-06-allowed-binaries-extension.md` (AC-15 closed-set negative-list test pinning `bwrap`/`bubblewrap` as NOT allowlisted)
- `docs/phases/02-context-gather-layers-b-g/phase-arch-design.md` (§"Component design" #3, §"Design patterns applied", §"Anti-patterns avoided", §"Tradeoffs (consolidated)", §"Goals" G6)
- `src/codegenie/exec.py` (the merged Phase 0 implementation — `run_allowlisted`, `_filter_env`, `_escalate_and_kill`, `_RUNNING_PROCS`)
- `.pre-commit-config.yaml` + `scripts/check_forbidden_patterns.py` (actual structural defense for "no shell, no new subprocess sites")
- Repo state: `tests/adv/`, `tests/unit/exec/`, `tests/property/` (codebase test conventions)

## Stage 2 — Parallel critics

Two combined critics ran in parallel (Consistency+Coverage; Test-Quality+Design-Patterns). Findings cross-referenced for conflicts; one major conflict resolved per priority order.

### Critic 1 — Consistency + Coverage (block findings)

**B1 (consistency, block).** Original AC-3 said the argv passed to `run_allowlisted` is `["bwrap", "--unshare-net", ...] + argv`. But `run_allowlisted`'s first action (Phase 0 invariant #1, `src/codegenie/exec.py:237-243`) is `if argv[0] not in ALLOWED_BINARIES: raise DisallowedSubprocessError`. Since `bwrap` is intentionally NOT in `ALLOWED_BINARIES` (per merged 02-ADR-0001 §Consequences last bullet + S1-06 AC-15 regression test), the original AC-3 cannot succeed. Original Refactor "Reconcile" paragraph and Notes §1 then proposed *adding* `bwrap` to `ALLOWED_BINARIES`, which would (a) break the merged S1-06 regression test `test_allowed_binaries_closed_set_regression`, (b) directly contradict the 02-ADR-0001 amendment that was merged same-day, (c) roll back the wrapper-pattern exception that 02-ADR-0001 §Consequences was literally amended to record.

**B2 (consistency, block).** Original AC-7 pinned env to the 4-key Phase 0 baseline (`PATH`, `HOME`, `LANG`, `LC_ALL`). The architecture text at `phase-arch-design.md` line 506 enumerated 6 keys (`PATH`, `HOME`, `LANG`, `LC_ALL`, `TERM`, `CODEGENIE_*`). One is wrong; neither acknowledged the other.

**B3 (consistency, block).** Original AC-5 said cap "on exceed only"; arch line 510 said "tail-included in failures" (success unstated). The implicit story behavior was "cap on every call." Three different stories about when truncation runs.

**Other block (Critic 2):** AC-5 text said truncate to "the last `max_stdout_bytes // 2` bytes" but Implementation outline §3 and the Green sketch both used `cap - len(_TRUNC_MARKER)` (~all of `cap`, not half). Internal contradiction the executor couldn't have resolved against any single test.

### Critic 1 — Coverage (harden findings)

- **C1.** AC-8 last assertion `result.stdout.endswith(b"A" * 1024)` could not distinguish head-vs-tail truncation (input was uniform `A`). A head-bug mutant returning `_TRUNC_MARKER + buf[:keep]` would pass.
- **C2.** Tmpdir cleanup was mentioned in passing in AC-3 ("cleaned up in `finally`") but had no AC and no test. A mutant deleting the `shutil.rmtree` call would ship green.
- **C3.** AC-1 typed `probe_name: ProbeId` but the TDD plan passed bare strings, which would fail `mypy --strict` (`NewType` is nominal).
- **C4.** `probe_name` flows into `tempfile.mkdtemp(prefix=...)` without validation. `ProbeId = NewType("ProbeId", str)` has zero character-class constraint at runtime.

### Critic 2 — Test quality (harden findings)

- **T1.** AC-10 named three structured log events but the TDD plan asserted none of them. AC-4's "warn once" claim was tested only by argv inspection (mutant that emits on every call would pass).
- **T2.** The 100 MB allocation in the cap test was slow + RAM-hungry for what is an algorithmic property; a small-cap parametrized test proves the same invariant faster and more readably.
- **T3.** `_truncate_tail` has natural Hypothesis invariants (length bound, identity under cap, marker-prefix + tail-suffix when over cap). The codebase already uses Hypothesis (`tests/property/test_index_freshness_roundtrip.py`).
- **T4.** `monkeypatch.setattr(sys, "platform", "darwin")` is fragile to refactors that cache `_IS_LINUX` at import time. (Nit only — flagged in Notes for future readers, no story change.)
- **T5.** AC-8 lumped eight scenarios into one criterion — hard for the executor's self-validator to check individually.

### Critic 2 — Design patterns (harden / nit)

- **D1.** `_maybe_wrap_with_bwrap` mixes pure (build argv) and impure (create tmpdir, mutate global). The rule-of-three is NOT yet hit (one wrapper, one no-op fallback). Don't split now; flag the future seam in Notes so the next implementer (Phase 5 microVM author) knows where to extract.
- **D2.** Sandbox-wrapper registry — same reasoning; defer until wrapper #2 (Phase 5).
- **D3.** Magic constants `64 * 1024 * 1024` appear in three places (signature default, AC, test). The `1024` byte assertion in the cap test was brittle and would pass for a "keep only last 1024 bytes" mutant. Resolved by using the exact tail length expression.

### Conflict between critics

**Critic 1 said:** Keep `bwrap` OUT of `ALLOWED_BINARIES` (per merged ADR); invoke via a private `_spawn_bwrap_wrapped` / `_spawn_with_invariants` helper inside `exec.py`.

**Critic 2 said:** Add `bwrap` to `ALLOWED_BINARIES` because it's "the simpler path" and keeps `tests/adv/test_no_shell_true.py` green.

**Synthesizer resolution.** Per the priority `Consistency > Coverage > Test-Quality > Design-Patterns`, Critic 1's path wins because:

1. 02-ADR-0001 §Consequences last bullet, **already merged**, explicitly states *"`bwrap`/`bubblewrap` is intentionally NOT in `ALLOWED_BINARIES`. … This records the wrapper-pattern exception as a load-bearing decision so the policy survives any future refactor."*
2. S1-06 AC-15, **already merged**, ships `tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression` with `bwrap` and `bubblewrap` in the closed-set negative-list.
3. Critic 2's "simpler path" requires rolling back two pieces of merged work — that's not "harden," that's revert, and it's out of S1-07's scope.
4. The "structural" concern Critic 2 raised (a second `asyncio.create_subprocess_exec` callsite would break `tests/adv/test_no_shell_true.py`) is wrong: the test file in question does not exist in the merged repo (verified by `ls`); the actual defense is the `forbidden-patterns` pre-commit hook which checks per-file but excludes `exec.py` by convention. The bwrap spawn lives *inside* `exec.py`, so the single-file invariant is preserved by extracting `_spawn_with_invariants` (which `run_allowlisted` already morally contains).

The Critic 2 design-patterns concern (rule-of-three not yet hit for a registry) is preserved as a Notes-for-implementer paragraph.

## Stage 3 — Research

Skipped. No findings tagged `NEEDS RESEARCH`. The Hypothesis property-test idiom (T3) is already established in the codebase (`tests/property/test_index_freshness_roundtrip.py`); the `structlog.testing.capture_logs()` pattern (T1) is already used in `tests/unit/test_exec.py` ~line 285.

## Stage 4 — Edits applied

The story file was edited in place. Diff summary:

| Section | Change |
|---|---|
| Header | Added `Validation notes` block recording the audit trail. `Status: Ready (HARDENED 2026-05-15)`. |
| Goal | Rewrote to make the bwrap path's actual spawn route explicit (private `_spawn_bwrap_wrapped` + shared `_spawn_with_invariants`, NOT `run_allowlisted`). Six Phase 0 invariants preserved by composition. |
| AC-1 | Unchanged in spirit; added explicit return type. |
| AC-2 | Rewrote to reference the shared `_spawn_with_invariants` extraction. |
| AC-3 | Rewrote to specify the private helper path; `bwrap` argv shape via direct spawn. |
| AC-3a (new) | Pins `"bwrap" not in ALLOWED_BINARIES` and `"bubblewrap" not in ALLOWED_BINARIES` as a regression. Cites 02-ADR-0001 §Consequences and S1-06 AC-15. |
| AC-3b (new) | Asserts the exact bwrap argv shape via a mocked `_spawn_with_invariants` capture. |
| AC-3c (new) | Tmpdir cleanup across three exit paths (success / non-zero / timeout) with explicit `not Path.exists()` assertion. |
| AC-4 | Strengthened: structlog-capture verification of warn-once behavior (was: argv inspection only). |
| AC-5 | Rewrote: cap on every call; formula `cap - len(_TRUNC_MARKER)` (struck `// 2`); arch-doc edit noted. |
| AC-7 | Pinned 4-key Phase 0 baseline; one-line arch-doc edit noted. |
| AC-8 | Split into AC-8.1 … AC-8.10 for legibility and individual coverage tracking. |
| AC-8.3 (new sub) | Head-vs-tail discrimination test with head=A / tail=B input. |
| AC-8.10 (new sub) | Inner-argv allowlist enforcement happens before any spawn or tmpdir. |
| AC-9 | Rewrote to reference the actual structural defense (`forbidden-patterns` pre-commit hook); noted the AST-scan backlog gap as out-of-scope. |
| AC-10 | Strengthened: explicit log levels, structured fields, per-stream `subproc.stdout.truncated` events. |
| AC-13 (new) | Hypothesis property test for `_truncate_tail` at `tests/property/test_truncate_tail.py`. Three invariants. |
| AC-14 (new) | `probe_name` regex validation `^[a-z][a-z0-9_]{0,63}$` with red test. |
| Implementation outline | Rewrote: extract `_spawn_with_invariants`, refactor `run_allowlisted` to delegate, add `_spawn_bwrap_wrapped` path, explicit allowlist check on inner argv, sequential cleanup discipline. |
| Green sketch | Rewrote to match the new implementation outline. `bwrap` NOT in allowlist; spawn via `_spawn_with_invariants`. |
| TDD plan red tests | Replaced entire test file content. Uses `ProbeId(...)` wrappers, `structlog.testing.capture_logs()`, parametrized cleanup test, head-vs-tail discrimination, small-cap algorithmic test, AC-14 rejection cases. Added companion property-test file. |
| Refactor | Struck "Reconcile" paragraph (it was the contradiction). Replaced with the correct refactor steps. |
| Files to touch | Added arch-doc edit; added property test file; added "Explicitly NOT touched" subtable pinning the S1-06/ADR-0001 invariants. |
| Out of scope | Added explicit "Adding bwrap to ALLOWED_BINARIES — forbidden"; added `ProbeId` constructor-level validation; added sandbox-wrapper registry deferral. |
| Notes for implementer | Struck §1 (bwrap allowlist reconciliation — was the contradiction). Replaced with the correct policy explanation. Added G6 alignment paragraph, refactor-`run_allowlisted` scoping note, length-invariant note, sandbox-wrapper registry deferral note, log-level reasoning. |

## Final verdict: HARDENED

The story is ready for `phase-story-executor`. The executor will encounter:

1. A clear, contradiction-free set of ACs (each individually verifiable).
2. A TDD plan with tests that distinguish correct implementations from common mutants (head-vs-tail, missing cleanup, missing warn-once gate, missing log emission, missing inner-argv allowlist check).
3. An implementation outline that explicitly resolves the bwrap allowlist policy per the merged ADR.
4. Files-to-touch that explicitly excludes the merged S1-06 frozenset and 02-ADR-0001 (no rollback risk).
5. Design-pattern guidance (extension by addition, rule-of-three for the sandbox-wrapper registry, primitive-obsession defense at the `probe_name` boundary) without premature abstraction.

The two backlog items surfaced during validation:
- **Phase 0 S4-05 gap.** `tests/adv/test_no_shell_true.py` is referenced by `exec.py`'s docstring and the phase-arch-design but does not exist in the merged repo. The `forbidden-patterns` pre-commit hook handles part of the structural defense but does not currently ban `asyncio.create_subprocess_exec` outside `exec.py`. Recommend a separate Phase 0 story to land the AST scan.
- **`ProbeId` constructor validation.** S1-05 shipped `ProbeId = NewType("ProbeId", str)` without runtime character-class enforcement. S1-07 patches at the `run_external_cli` boundary (AC-14), but a constructor-level validator on `ProbeId` itself would be defense-in-depth across all callers. Recommend a follow-up story under Phase 2 S1-05's family.
