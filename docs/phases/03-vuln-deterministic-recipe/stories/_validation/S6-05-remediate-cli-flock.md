# Validation report — S6-05 (`codegenie remediate` CLI + `.codegenie/.lock` flock + `audit verify` spanning-chain extension)

**Date:** 2026-05-19
**Validator:** phase-story-validator (inline four-lens analysis, mirroring the S6-04 validation report — the four critic lenses applied directly after Stage 1 surfaced multiple block-tier Consistency conflicts that any independent critic would converge on).
**Verdict:** **HARDENED**
**Story path:** [`docs/phases/03-vuln-deterministic-recipe/stories/S6-05-remediate-cli-flock.md`](../S6-05-remediate-cli-flock.md)

## Why HARDENED (not STRONG, not RESCUE)

The story's architectural intent is correct: it correctly identifies the three bundled concerns (CLI surface, outer flock, `audit verify` extension), correctly traces them to arch §Control flow + §Edge cases E13 + ADR-0005 §Consequences, and correctly proposes the exit-code matrix shape. Goal sentence and scope survive.

But the story drifted from shipped reality in several block-tier ways that an executor without the validator's eye would have followed straight into an `AttributeError`:

1. **Wrong `RemediationOutcome` variant class names.** Story uses `NotApplicable` / `Failed`; shipped S1-03 ships `RemediationNotApplicable` / `RemediationFailed`. The proposed `match` arms would never have matched (same C-F1 problem the S6-04 validator already caught — and which has now had time to land in code).
2. **String-grep test on `inspect.getsource(...)`** for "exhaustiveness" — the textbook brittle test. Refactoring the implementation can pass it; a `return 0` mutation would also pass it.
3. **`WorkflowConcurrent` variant ownership unresolved.** S6-01 ships exactly 9 spanning variants (per its AC-7). `WorkflowConcurrent` is NOT one of them. The story acknowledged the issue ("deferred to S6-01's spanning union — if not present, add a minimal variant in this story") but did not commit to a path the executor can follow without re-litigating the architecture.
4. **Smart-constructor call shape wrong.** Notes reference `CveId.parse(...)`; the codebase ships `parse_cve_id(s)` smart constructor returning `Result[CveId, ParseError]`. The `.unwrap()` call shape is also wrong — the codebase uses `match` on `Ok` / `Err`.
5. **Chain-verification primitive misidentified.** Notes say "reuses the chain-verification primitive from `src/codegenie/audit.py`" — but `audit.py` only has `_verify_one_blob` / `_verify_one_yaml` for per-run anchors. The actual chain step primitive is `_chain_step` in S6-01's `codegenie.plugins.events`. The executor would have either reimplemented BLAKE3 chain logic in `audit.py` (Rule 7 violation: two definitions) or stalled.
6. **Sanitizer module path placeholder.** Notes say "search `src/codegenie/output/sanitizer.py` or similar". The module exists at exactly that path (no "or similar"). An executor that took the placeholder seriously might have written a parallel scrubber.
7. **Flaky synchronization in concurrent integration test.** `time.sleep(0.5)` is the exact anti-pattern that produces CI flakes — the original test's docstring even noted timing sensitivity but offered no deterministic alternative.

All in-place fixable. ACs strengthened, test plan rewritten with mutation-thinking, Notes corrected with verified references. Verdict: HARDENED.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (post-edit):** ship `src/codegenie/cli/remediate.py` with `_workflow_lock` + `_exit_code_for` + `remediate` click subcommand; extend `audit verify` with `--spanning-events-path` + `_verify_spanning_chain` reusing S6-01's `_chain_step`; land the `WorkflowConcurrent` 10th variant on the `WorkflowSpanningEvent` discriminated union.
- **Status pre-validation:** `Ready` — never executed.
- **Status post-validation:** `HARDENED`.

### Shipped reality (as of git HEAD `a64d5f1`)

- `src/codegenie/transforms/outcomes.py:240-300` — `Validated(branch, report_path, passed, failing)` + `RequiresHumanReview(reason, handoff_path)` + `RemediationNotApplicable(reason)` + `RemediationFailed(error, partial_report_path)`. Discriminated union via `Annotated[... | Field(discriminator="kind")]`.
- `src/codegenie/cli.py:867-902` — existing `audit verify` subcommand with `--runs-dir`, `--cache-dir`, `--yaml-path`. Exit 0 / 4. Calls `audit.verify_runs(...)`.
- `src/codegenie/audit.py` — `verify_runs(runs_dir, cache_dir, yaml_path) -> int` aggregating `_verify_one_blob` + `_verify_one_yaml`. No chain-walker.
- `src/codegenie/types/parsers.py:154` — `parse_cve_id(s: str) -> Result[CveId, ParseError]`. The smart constructor.
- `src/codegenie/output/sanitizer.py` — exists. Path-scrubber lives here.
- `src/codegenie/cli.py:69-91` — `_EXIT_CODE_DISPATCH`, `_OUTCOME_BY_EXIT`. Exit 8 is NOT used today.

### Dependency status

- **S6-01** (two-stream EventLog): `HARDENED`, not GREEN. Ships exactly 9 spanning variants. `WorkflowConcurrent` is NOT yet defined.
- **S6-04** (orchestrator): `HARDENED`, not GREEN. Provides `RemediationOrchestrator.run(repo, cve, ctx)` per ADR-0001.
- **S1-03** (tagged-union outcomes): `GREEN` (2026-05-18). Shipped class names enforced.

### Cross-phase contract (immutable inputs)

- **ADR-0005 §Consequences:** "`codegenie audit verify` extends to verify the BLAKE3 chain on the spanning stream and refuses startup on break." The "refuses startup on break" wording is the contract for `audit verify` (exit non-zero), not for `remediate` itself.
- **ADR-0010 §Decision (3):** every dispatch site uses `match` + `assert_never`. The CLI's exit-code translator is the textbook example.
- **ADR-0011 (honest framing):** `fcntl.flock` is advisory; Phase 3 does not promise unforgeable isolation.
- **Arch §Edge cases E13:** `.codegenie/.lock` `fcntl.flock` exclusive lock; second exits exit 8 with `WorkflowConcurrent`.
- **Arch §Harness engineering — Idempotence:** lock-first ordering; explicit-fail rather than silent-re-apply.
- **Arch §Harness engineering — Logging:** never log absolute paths outside the jail, env values for sensitive keys, or capability bundles.

### Open ambiguities resolved before critics

- **Q1 — Who owns the `WorkflowConcurrent` variant?** Story hedged ("add a minimal variant in this story and surface the addition in S6-01's notes"). Resolution: S6-01 is HARDENED but not GREEN. The executor lands the variant in `src/codegenie/plugins/events.py` (S6-01's canonical site) as part of this story's commit, with a one-line note in S6-01's amendment trail. Same precedent as ADR-0010 Amendment 2026-05-18 — single canonical declaration site even when the variant arrives via a sibling story.
- **Q2 — Where does the chain-verification primitive live?** Resolution: `_chain_step` in `codegenie.plugins.events` is the S6-01-owned helper (per S6-01 AC-4). `audit.py` *aggregates*; it does not own the hash logic.
- **Q3 — Does `Validated(passed=False)` map to a different exit code than `RemediationFailed`?** Resolution: both → 4. Per ADR-0007, Phase 3 alone does not retry on failed validation; both represent "deterministic failure, escalation required." Phase 5's `GateRunner` is the retry envelope. Story now documents this explicitly.

## Findings

Severity legend: **block** (story unshippable without fix) · **harden** (in-place fix applied) · **nit** (small clarification).

### Consistency lens (highest priority)

#### C-F1 (block → fixed) — Wrong `RemediationOutcome` variant class names

- **What was wrong:** Story used `NotApplicable` / `Failed` (e.g., `case NotApplicable`, `RemediationOutcome.NotApplicable(reason)`). The shipped class names are `RemediationNotApplicable` / `RemediationFailed`.
- **Source of truth:** `src/codegenie/transforms/outcomes.py:274-294` + S6-04 validation report finding C-F1.
- **Fix applied:** All AC text + Implementation outline + TDD plan + Notes updated to the shipped names. AC-6 lists them verbatim.

#### C-F2 (block → fixed) — `WorkflowConcurrent` variant ownership unresolved

- **What was wrong:** Story implementation outline #4 said "deferred to S6-01's spanning union — if not present, add a minimal variant in this story". S6-01 ships exactly 9 variants and is HARDENED (cannot be silently re-validated). Without a resolution, the executor would either (a) reopen S6-01's contract, (b) put the variant somewhere arbitrary, or (c) stall.
- **Source of truth:** S6-01 AC-7 (9 variants enumerated) + ADR-0010 Amendment (single canonical declaration site).
- **Fix applied:** Validation notes block at story top explicitly resolves: variant lands in `src/codegenie/plugins/events.py` (S6-01's canonical site) as part of this story's commit, additively. New AC-12 + AC-13 pin the shape and the chain-step parity test.

#### C-F3 (block → fixed) — Smart-constructor call shape wrong

- **What was wrong:** Notes referenced `CveId.parse(...)` and `SandboxedPath.create(...).unwrap()`. The codebase ships `parse_cve_id(s) -> Result[CveId, ParseError]` (free function, not method); `Result` doesn't have `.unwrap()` — callers `match` on `Ok` / `Err`.
- **Source of truth:** `src/codegenie/types/parsers.py:154` + `src/codegenie/types/errors.py`.
- **Fix applied:** Notes corrected; Implementation outline §3a rewritten to use `parse_cve_id(cve)` with `match`-on-`Result`; AC-4 pins the click usage error with `ParseError.message` text.

#### C-F4 (harden → fixed) — Chain-verification primitive misidentified

- **What was wrong:** Notes said "reuses the chain-verification primitive from `src/codegenie/audit.py`". `audit.py` has no such primitive; its `_verify_one_*` helpers are for per-run anchor blobs and YAML hashes, not the BLAKE3 chain step.
- **Source of truth:** S6-01 AC-4 — "pure `_chain_step(prior_head, event_bytes) -> BlobDigest` helper that the S6-05 walker also consumes". The S6-01 author already pre-declared the contract for this story.
- **Fix applied:** AC-15 explicitly pins `_chain_step` from `codegenie.plugins.events` as the helper to import. Notes corrected. Files-to-touch updated to reflect the cross-module dependency.

#### C-F5 (nit → fixed) — Sanitizer module path placeholder

- **What was wrong:** Notes said "search `src/codegenie/output/sanitizer.py` or similar".
- **Source of truth:** The module exists at exactly `src/codegenie/output/sanitizer.py`.
- **Fix applied:** Verified path noted in AC-18; the "or similar" hedging dropped.

### Coverage lens

#### C-F6 (harden → fixed) — Several edge cases missing from ACs

- **What was missing:**
  - Lockfile-as-symlink (TOCTOU defence; mirrors E12).
  - Lockfile permissions (`0o600`).
  - `.codegenie/` missing → create.
  - Invalid `<repo>` path.
  - Invalid `--cve` format.
  - Lock release on `KeyboardInterrupt` / fatal signal.
- **Fix applied:** AC-3, AC-4, AC-8 (steps 1–7), AC-11 added. The `_workflow_lock` AC now specifies `O_NOFOLLOW` + `lstat` symlink check + `0o600` mode + `.codegenie/` auto-create with `0o700`.

#### C-F7 (harden → fixed) — `audit verify` flag surface not pinned

- **What was missing:** Original AC said "the existing subcommand additionally walks `<repo>/.codegenie/events/spanning/append.jsonl.zst` (if present)" but didn't specify how the path is derived or what flag the operator passes. The existing `audit verify` takes `--runs-dir`, `--cache-dir`, `--yaml-path`; no path is in scope for the spanning stream.
- **Fix applied:** AC-14 introduces `--spanning-events-path` option with a defaulting rule. AC-23 adds the missing-file-is-success integration test.

#### C-F8 (harden → fixed) — Sanitization ACs lacked concrete test

- **What was missing:** Original AC said "Operator-facing messages on stdout / stderr are sanitized" — true but unverifiable. No test would fail on a regression.
- **Fix applied:** AC-18 + AC-19 pin specific tests: synthetic absolute path injection + `GITHUB_TOKEN=test_pizzapizza_marker` env-leak detection.

### Test Quality lens

#### T-F1 (block → fixed) — `inspect.getsource(...)` string-grep is the textbook brittle test

- **What was wrong:** The original `test_exit_codes_exhaustive_over_remediation_outcome` asserted the *source* of `codegenie.cli.remediate` contains specific tokens. A refactored implementation could rearrange the match block and break the test; an implementation that returns `0` for everything would still pass the source-grep test. Same anti-pattern S6-04 validation flagged in its outer-loop `match` test.
- **Source of truth:** Rule 9 + S6-04 validation report.
- **Fix applied:** Replaced with a parametrized property test (5 rows, one per variant including both `Validated` branches) that calls `_exit_code_for(outcome)` directly. Mutation guard: a `return 0` mutation fails 4/5 rows; an unhandled variant fails `mypy --strict` at `assert_never`.

#### T-F2 (harden → fixed) — Flaky `time.sleep(0.5)` synchronization

- **What was wrong:** The original integration test relied on `time.sleep(0.5)` to let the first subprocess acquire the lock. On a loaded CI runner, the second subprocess could win the race. The original Notes acknowledged "timing-sensitive" but offered no deterministic alternative.
- **Source of truth:** general CI flake patterns; the codebase precedent of lockfile-with-PID synchronization barriers.
- **Fix applied:** AC-20 rewrites the test: poll the lockfile for a non-empty PID (max 5s, 50ms intervals); fail LOUD if the PID never appears ("first invocation never wrote PID to lockfile"); only then start the second subprocess. AC-8 adds the holder-PID write to the lock acquisition path.

#### T-F3 (harden → fixed) — `test_remediate_against_express_fixture_exits_zero` was a `...` placeholder

- **What was wrong:** Test body was literally `...` — not actionable.
- **Fix applied:** Folded into AC-2 (smoke happy-path) + AC-20 (the more interesting concurrent test does the heavy lifting). The CliRunner smoke + the integration test together cover the surface.

#### T-F4 (harden → fixed) — Missing tests for `_workflow_lock` invariants

- **What was missing:** No direct unit test of the context manager's symlink rejection, PID write, or release-on-exception behavior.
- **Fix applied:** New tests in TDD plan: `test_lock_rejects_symlink`, `test_lock_releases_on_keyboard_interrupt`, `test_lock_first_call_order`.

### Design Patterns lens

#### D-F1 (harden → fixed) — Exit-code translator was a "refactor" hint, not a first-class AC

- **What was wrong:** Original story put "extract `_exit_code_for(outcome) -> int`" in the refactor section. As a refactor, it is optional — the executor could ship the body inlined. But the translator IS the Open/Closed extension point for the exit-code matrix (adding a future variant = one new `match` arm; `assert_never` catches forgotten arms at mypy time).
- **Fix applied:** AC-6 + AC-7 promote the translator to a first-class AC: pure helper, single source of truth, parametrized property test.

#### D-F2 (harden → fixed) — Lock context manager was also a refactor hint

- **What was wrong:** Same shape — `_workflow_lock(repo)` was in the refactor section as nice-to-have. But the lock semantics (symlink defence, PID write, NB acquisition, finally release) deserve a single home — both for testability and for potential promotion to `src/codegenie/concurrency/locks.py` later.
- **Fix applied:** AC-8 promotes the context manager to first-class. Notes flag the future Port-promotion path.

#### D-F3 (nit → noted in Notes) — `AuditCheck` registry — at rule-of-three

- **What's interesting:** This story brings `audit verify` from one check (per-run anchors) to two (per-run anchors + spanning chain). A third check is foreseeable (Phase 5 contract-snapshot verifier, or a Phase 9 Postgres-side hash). At three, the right move is a `@register_audit_check` Protocol — Open/Closed: a new check is one decorated function. **But not now** (Rule 2: three similar lines beat premature abstraction at two).
- **Fix applied:** Notes-for-implementer documents the future opportunity so the next sibling story has the breadcrumb. NOT promoted to AC because the kernel/extract should land alongside its third consumer, not as speculative scaffolding.

#### D-F4 (harden → fixed) — `_emit_workflow_concurrent` and `_emit_operator_message` were not first-class

- **What was wrong:** Implementation outline described these inline; they are the seams where sanitization and one-shot emission live.
- **Fix applied:** Implementation outline §3 now explicitly lists them as named module-level helpers. AC-18 pins the sanitizer-routed write contract.

## Edits applied — summary

The story file was edited in place. The diff includes:

- Header — `Status: Ready` → `Status: HARDENED (validated 2026-05-19 — see _validation/S6-05-remediate-cli-flock.md)`; `Depends on: S6-04` widened to `S6-01 (must publish WorkflowConcurrent variant + _chain_step helper), S6-04 (orchestrator)`.
- New `## Validation notes (2026-05-19)` block under header listing the corrections.
- Exit-code list — corrected class names; added exit `2` for click usage errors; expanded mapping rationale.
- `## Acceptance criteria` — fully rewritten and renumbered AC-1 through AC-26, grouped by sub-section (CLI surface, Exit-code translator, Outer flock, `WorkflowConcurrent` variant amendment, `audit verify` spanning-chain extension, Sanitization, Integration tests, Hygiene). All ACs are individually verifiable (binary pass/fail by a third-party check); each AC has at least one corresponding test in the TDD plan.
- `## Implementation outline` — rewritten to order operations correctly (variant first, helpers next, click body, `audit verify` extension, refactor checks).
- `## TDD plan` — rewritten with mutation-thinking tests, parametrized exit-code property test, deterministic lockfile-PID synchronization, symlink rejection, sanitization regression. The `inspect.getsource(...)` test is removed.
- `## Files to touch` — corrected to reflect actual paths (`src/codegenie/cli.py` not `cli/__main__.py`; `audit.py` at module root, not `cli/audit.py`); added `src/codegenie/plugins/events.py` for the variant amendment + `tests/unit/plugins/test_events.py` for the chain-step parity test.
- `## Notes for the implementer` — rewritten in four sections: Read-before-write (Rule 8), Concurrency semantics, Single-async-boundary discipline, Design-pattern opportunities (for FUTURE stories, with the rule-of-three caveat), Test hygiene, Operator-facing failure modes.

## What "good" looks like — checklist

- [x] Every AC is individually verifiable.
- [x] The AC set collectively guarantees the goal.
- [x] Every AC has at least one mutation-resistant test in the TDD plan.
- [x] No AC is a tautology, "no exception thrown" check, or vague qualitative statement.
- [x] The TDD plan distinguishes intent-verifying tests from regression tests.
- [x] The story doesn't contradict the phase arch, any ADR, or CLAUDE.md (resolved C-F1 through C-F5).
- [x] Critical edge cases are listed: empty input (missing spanning stream), concurrency (the whole point), error paths (invalid CVE, missing repo, symlink), malformed input (tampered chain), fault injection (KeyboardInterrupt during lock hold).
- [x] Implementation consumes existing kernels: `parse_cve_id`, `_chain_step`, `scrub_paths`, `EventLog`, `RemediationOrchestrator`. Introduces new ones (`_exit_code_for`, `_workflow_lock`) where the boundary is real.
- [x] Domain identifiers are typed (`CveId`, `WorkflowId`, `BranchName`, `EventId`, `BlobDigest`).
- [x] Pure logic separable from I/O: `_exit_code_for` is pure; `_workflow_lock` is the impure boundary.
- [x] Tagged-union exhaustiveness via `match` + `assert_never`.

## Verdict

**HARDENED.** Story is ready for `phase-story-executor`.
