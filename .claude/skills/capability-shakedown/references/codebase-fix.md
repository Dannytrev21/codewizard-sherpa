# Codebase fix — test-gap analysis, failing tests first, fix, verify

This is the heart of the skill. A codebase bug that reached a shakedown
got past the whole test suite — so fixing the code is only half the job.
The other half is closing the **test gap** that let it through, so the
*class* of bug cannot return. Work the five steps in order.

## Step 1 — Test-gap analysis: why did the suite miss this?

Before writing any code, answer: the suite has thousands of tests — how
did this bug pass? The answer is almost always one of these patterns.
Check each against the failing capability:

- **Consumer tests fabricate their own upstream.** The consumer's unit
  test hand-writes the input it should be reading from a real producer
  (e.g. a `_write_dockerfile_slice()` helper that fabricates
  `raw/dockerfile.json`). The producer→consumer *seam* is never tested as
  a pair, so a producer that emits nothing is invisible.
- **Golden / snapshot tests baked in the broken output.** A snapshot
  test runs the real thing but the committed baseline *is* the broken
  output (`confidence: unavailable` recorded as "expected"). A golden
  catches drift, not wrongness — a wrong baseline passes forever.
- **No integration / e2e slice.** Every test is a unit test; nothing
  runs the capability end-to-end and asserts the *semantic* result. The
  composition is never exercised.
- **Unrealistic fixtures.** Test fixtures omit a field real output
  carries (e.g. semgrep fixtures with no `time.rules` block), so the
  failure state is structurally unrepresentable in any test.
- **Smoke fixtures don't reach the feature.** The end-to-end fixtures
  lack the input that would exercise this code path at all (no smoke
  fixture has a `Dockerfile`, so the Layer C chain never runs).
- **A known bug parked as `xfail`.** A regression test exists but is
  `xfail`-ed — the bug was known and silenced with no forcing function.

Name the specific gap(s) in the report. The gap analysis is what makes
the fix durable; without it you fix one instance and the next one ships
the same way.

## Step 2 — Write the failing test at the right level

The new test must exercise the gap, not paper over it:

- **Test the seam, not a fabricated input.** If the gap was "consumer
  tests fabricate the upstream", the new test must run the *real*
  producer and the *real* consumer together — an integration test that
  runs the actual capability, not a unit test with a hand-written input.
- **Assert intent, not a snapshot.** If the gap was a baked-in golden,
  add a behavioral assertion that encodes the *expectation* ("a repo with
  a Dockerfile yields a non-empty entrypoint") — something a wrong
  baseline cannot satisfy.
- **Make it structural where possible.** The strongest test catches the
  whole bug *class*, not one instance — e.g. "every `raw/<name>.json` a
  probe declares as an input is actually produced by a gather" catches
  the next mis-wired probe for free, not just this one.
- Put it where the repo puts that tier — `tests/integration/` for a
  seam/e2e slice, `tests/fence/` for a structural invariant. Match the
  conventions in `docs/contributing.md`.

## Step 3 — Run it; confirm RED

Run the new test against the **unfixed** code and watch it fail. This is
non-negotiable (Rule 9): a test that never went red has not been shown to
test anything. If it passes on the broken code, it is the wrong test —
go back to Step 2.

Capture the RED output for the report.

## Step 4 — Fix the code (minimum change)

Write the smallest change that makes the test pass. Surgical — fix the
finding, do not refactor neighbours (Rule 3). Match the existing pattern:
if four sibling modules already persist a sidecar with a `_write_files`
helper, the fix is a fifth `_write_files`, not a new abstraction.

If the fix would require editing a **frozen contract** (the probe ABC,
a fence, anything an ADR froze) — stop. That is not an autonomous fix;
flag it in the report as needing an ADR amendment and move to the next
finding.

## Step 5 — Verify: GREEN, non-vacuous, gates pass

Three checks, all required:

1. **The new test passes** on the fixed code.
2. **The test is non-vacuous.** Prove it genuinely binds: neuter the fix
   (revert just the changed lines, or stub the new helper to a no-op),
   confirm the test goes RED again, then restore. A test that passes
   whether or not the fix is present is worthless.
3. **`make check` is green** — lint, typecheck, the full suite, fences.
   Run it via the project venv on `PATH`. Pre-existing snapshot/golden
   tests may now legitimately fail because the *correct* output changed
   — regenerate them (the repo has a regen path; the failing test names
   it) only after eyeballing each diff to confirm it is the intended
   behavior change, never blindly.

## The retry loop

If `make check` is not green after the fix, you have up to
`--max-fix-attempts` (default 3) total attempts. Each retry: re-read the
failure, adjust, re-verify. If the cap is hit and the gate is still red:
**stop**. Leave the working tree as-is, write the report with a red
banner naming exactly what is still failing, and surface it. A red gate
is never reported as success (Rule 12).

## What lands

For each codebase bug: the test-gap analysis (in the report), one or
more new tests (RED-verified, non-vacuous), the minimal code fix, any
legitimately-regenerated snapshots, and `make check` green. Then Stage 7
sweeps the docs the behavior change touched.
