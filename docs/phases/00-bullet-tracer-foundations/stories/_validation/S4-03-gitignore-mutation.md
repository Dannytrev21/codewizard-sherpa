# Validation report — S4-03-gitignore-mutation

**Verdict:** HARDENED
**Date:** 2026-05-13
**Validator:** phase-story-validator skill
**Story:** [`../S4-03-gitignore-mutation.md`](../S4-03-gitignore-mutation.md)

## Summary

Story v1 was substantially under-specified for autonomous execution. A `phase-story-executor` agent would have produced code that passed every test while violating multiple load-bearing commitments (the `final-design.md §2.15` comment line, the atomic-write contract, the S4-02 AC-14 signature pin). Three parallel critics surfaced 32 findings across 4 block-severity + 19 harden-severity + 9 nit-severity buckets. All findings were addressable through in-place edits — no `RESCUE` was needed. The story is now HARDENED and ready for the executor.

## Stage 1 — Context Brief

**What the story promises (v1 goal):** prompt on TTY / warn-and-continue on non-TTY; on accept, atomically append `.codegenie/\n`; flags override; second invocation a no-op.

**What the phase's exit criteria demand (`phase-arch-design.md §Goals` item 10):** `.gitignore` mutation path is exercised for both the TTY-accept and non-TTY-skip branches.

**What the arch + ADRs constrain:**
- `final-design.md §2.15`: append `.codegenie/` *with a comment line above* (`# codewizard-sherpa generated artifacts; safe to delete`). v1 silently dropped this.
- `phase-arch-design.md §Edge case #8`: append failure → `gitignore.append.failed` WARNING; gather continues.
- `phase-arch-design.md §Harness engineering — Idempotence`: idempotence on `.codegenie/` substring before appending (v1 used line-anchored regex — improvement over substring, but contract drift).
- ADR-0011: the analyzed repo's `.gitignore` is NOT under `.codegenie/`; keeps platform default mode.
- ADR-0012: no subprocess; pure-Python atomic append.
- **S4-02 AC-14** (cross-story): `_gitignore_mutation_stub(repo_root, *, auto: bool, skip: bool) -> None` is pinned; S4-03 promises *"replaces the body without changing the signature."* v1 introduced `(auto, never, is_tty)` — direct contradiction.

**Ambiguities surfaced:** signature contradiction with S4-02 (resolved: keep S4-02's pinned signature; compute `is_tty` internally), substring-vs-line-regex idempotence (resolved: story IMPROVES arch contract; one-line amendment to arch queued in same PR), event-name `gitignore.codegenie.not_present` in final-design (resolved: superseded by arch's `gitignore.append.*` family; one-line amendment to final-design queued).

## Stage 2 — Three parallel critics

### Critic A — Coverage (10 findings)

| ID | Severity | Symptom |
|---|---|---|
| C-1 | block | Missing comment line (final-design.md §2.15 dropped) |
| C-2 | block | Conflicting flags `--auto-gitignore` + `--no-gitignore` undefined behavior |
| C-3 | harden | TTY detection contract not pinned (stdin AND stdout both required) |
| C-4 | harden | Edge case #8 says "mid-write" but only `os.replace` failure tested |
| C-5 | harden | `.gitignore` as symlink/directory/fifo unspecified |
| C-6 | harden | Trailing-newline asymmetry → stray blank line |
| C-7 | harden | CRLF/BOM idempotence uncovered |
| C-8 | harden | Empty-file branch not covered |
| C-9 | nit | Event-name drift between final-design and arch |
| C-10 | harden | Atomicity claim never tested (`open(path, "a")` mutation passes) |

### Critic B — Test Quality (12 findings)

| ID | Severity | Symptom |
|---|---|---|
| T-1 | block | `test_tty_accept` passes for impl that DELETES existing content |
| T-2 | block | `caplog.message` is wrong API for structlog (tests don't catch what they claim) |
| T-3 | block | `test_auto_flag` doesn't verify "no prompt" — confirm-then-ignore impl passes |
| T-4 | harden | `test_never_flag` doesn't spy on `click.confirm` |
| T-5 | harden | Idempotence test doesn't pin "no write" (mtime + event name) |
| T-6 | block | Atomic-write contract untested; tmp cleanup-on-failure not asserted |
| T-7 | block | "File does not exist" branch (AC line 47) has ZERO tests |
| T-8 | harden | No negative test for substring-vs-regex (comment-line false positive) |
| T-9 | harden | Append-failure doesn't pin `exc_class` or exclude non-OS exceptions |
| T-10 | harden | `caplog.set_level` missing → DEBUG events invisible |
| T-11 | harden | No metamorphic "call-twice-is-no-op" test |
| T-12 | nit | TTY-decline doesn't pin that prompt was actually shown |

### Critic C — Consistency (10 findings)

| ID | Severity | Symptom |
|---|---|---|
| F1 | **block** | Signature contradicts S4-02 AC-14's pinned `inspect.signature` test |
| F2 | harden | Helper location drift (cli.py vs new module) — arch's file tree doesn't name the new path |
| F3 | harden | final-design.md §2.15 comment line dropped from ACs |
| F4 | harden | Idempotence: arch says substring, story uses line-regex (story improves; arch needs amendment) |
| F5 | nit | Stale event name `gitignore.codegenie.not_present` in final-design.md |
| F6 | harden | `gitignore.append.skipped` overloaded at two log levels (no AC pins per-reason level) |
| F7 | harden | Event-name family unverified in logging.py / S2-01 |
| F8 | nit | Idempotence under `--auto-gitignore` not isolated as its own test |
| F9 | nit | Goal phrasing diverges from final-design §2.15 |
| F10 | nit | "Six branches" listed as seven items (off-by-one) |

**Critic conflicts resolved:**
- C-2 (add AC for conflicting flags) vs F1 (signature is the bigger issue): both apply; AC-15 added covers both.
- F4: Coverage says "add an idempotence-line-regex AC" while Consistency says "arch contract is substring" — Consistency would normally win, but the implementer note in v1 already justified the line-regex (false-positive on comments). Resolution: story improves arch; one-line amendment queued for same PR; explicitly documented in Validation note #6.

No findings tagged `NEEDS RESEARCH`. **Stage 3 skipped.**

## Stage 4 — Synthesizer + edits applied

### Edits to the story file (`../S4-03-gitignore-mutation.md`)

**1. Header.** Status changed `Ready` → `Validated — HARDENED (2026-05-13)`; effort `S` → `S→M`; added `Validated by` reference.

**2. Validation notes block** appended after header (8 numbered notes documenting the major changes — see story top).

**3. Goal section** rewritten:
- Before: "appends `.codegenie/\n` atomically"
- After: "atomically appends the exact two-line block `# codewizard-sherpa generated artifacts; safe to delete\n.codegenie/\n` (preserving prior content; injecting a leading `\n` only if the existing file does not end with one)"

**4. Acceptance criteria** rewritten from 12 ACs → 23 ACs, organized into 5 sections (Surface & signature / Six branches / Write contract / Failure handling / Metamorphic + permissions / Logging & toolchain). Each AC is individually verifiable; each pins event name + level + reason field separately (kills T-2-class mutations). Key additions:
- AC-1, AC-2: signature locked to S4-02 AC-14; TTY detection internal.
- AC-9: byte-exact appended block (kills T-1 / C-6 / C-8 mutations).
- AC-10: atomic-write contract testable via `os.fsync`/`os.replace` spy (kills C-10 / T-6).
- AC-11: line-anchored regex with false-positive guard (kills T-8).
- AC-12: non-regular file refusal (covers C-5).
- AC-13: CRLF idempotence (covers C-7).
- AC-14: missing-file × 4 sub-cases (covers T-7).
- AC-15: `--auto-gitignore` + `--no-gitignore` mutually exclusive (covers C-2).
- AC-16: mid-write failure parameterized over 4 failure points with tmp cleanup (covers C-4 / T-6 / T-9).
- AC-17: KeyboardInterrupt propagates (covers T-9).
- AC-19: metamorphic two-call no-op (covers T-11).
- AC-20: ADR-0011 file-mode discipline (covers C-5).
- AC-21, AC-22: logging.py constants + structlog stderr/JSON capture pattern (covers T-2 / T-10 / F7).

**5. Implementation outline** rewritten to be a precise branch-order specification with code-shaped pseudocode for the atomic-write helper. Branch precedence is now contract.

**6. TDD plan** rewritten end-to-end. ~24 tests replacing the v1's 7; every assertion is on byte-exact bytes or on parsed structlog JSON events with `event` + `level` + `reason`/`exc_class` fields. `click.confirm` is spied (records argv+kwargs) on every path that promises "no prompt." `mtime_ns` is asserted on every "no-write" path. `os.fsync` and `os.replace` are spied for atomicity. Parametrized failure-point test covers `open` / `write` / `fsync` / `replace`.

**7. Files to touch** updated:
- New: `tests/unit/test_logging.py` (one-line addition for AC-21).
- New: arch amendment (`phase-arch-design.md` §Harness engineering — Idempotence: substring → line-anchored).
- New: final-design amendment (`final-design.md` §2.15: stale event-name supersession).
- Existing entries now explain WHY in more detail.

**8. Implementer notes** rewritten — signature is locked, branch order is contract, atomic write is module-local (don't import Writer), tests follow `test_logging.py`'s structlog pattern, comment line is non-negotiable.

### Edits NOT applied

- **No edits to `phase-arch-design.md` / `final-design.md` / S4-02 itself.** Those are queued for the same PR but the validator's scope is one story file. The story now flags them as in-PR deltas.
- **No edits to the story's stated dependencies (`S4-02`).** Confirmed S4-02 AC-14 is the source of truth; resolved by changing S4-03 to match, not vice versa.

## Verdict rationale

The story had real, fixable weaknesses. The lazy-impl thought experiment for v1 produced an implementation that:
- Could legally delete `node_modules/` from the user's `.gitignore` (T-1) while passing tests.
- Could use plain `open(path, "a")` and never `os.replace` (C-10) while passing tests.
- Would fail to compile against S4-02's pinned signature (F1).
- Would silently drop the courtesy comment line that the source design mandates (F3).

After edits, every one of those mutations is killed by at least one AC + at least one explicit test. The story is now ready for `phase-story-executor`.

## Final state

- **Story:** edited in place; status `Validated — HARDENED`; ready for executor.
- **Cross-doc amendments queued for same PR:** `phase-arch-design.md §Harness engineering — Idempotence` (one line); `final-design.md §2.15` (one line). Both flagged in Files-to-touch.
- **No `_attempts/S4-03-*.md` yet** — that file is created by the executor.
