---
name: capability-shakedown
description: Exercises one codewizard-sherpa capability (a CLI command or runnable workflow) end-to-end against a real sample app, finds everything missing/empty/wrong/no-op in the output, diagnoses each finding down to a root cause, and then autonomously carries the fix all the way through — codebase bugs (with a test-gap analysis and failing tests written first), sample-app deficiencies, or environment/Docker setup — and finally sweeps every affected doc (ADRs, design docs, phase docs, roadmap, get-started). Use this skill whenever the user wants to run / exercise / shake down / smoke-test / "try out" a capability or CLI command against a sample app, verify a feature actually works end-to-end, figure out why output is empty or missing or looks wrong, or says "run X and fix whatever's broken". Trigger on phrasing like "shake down codegenie gather", "exercise the vuln-index flow", "run the CLI against a sample app and see what's missing", "does the dep-graph feature actually work", "why is the entrypoint probe empty", "test this capability end to end". Fire even when the user does not say "capability-shakedown" by name — match on the run-a-capability-against-a-sample-app-and-fix-it intent. Do NOT fire for auditing a whole roadmap phase (that is `phase-shakedown`) or for running a bare `pytest` invocation.
---

# Capability Shakedown

Take one **capability** of codewizard-sherpa — a CLI command or runnable
workflow, e.g. `codegenie gather`, `codegenie vuln-index refresh`,
`codegenie audit verify` — exercise it end-to-end against a real **sample
app**, and treat the gap between *what it produced* and *what it should
have produced* as the work. Every gap is diagnosed to a root cause and
the fix is carried all the way through: a real codebase bug gets a
test-gap analysis, failing tests, a code fix, and green gates; a
sample-app deficiency gets the sample app fixed; an environment gap gets
the environment set up and the run docs updated. Then every affected doc
is swept. A committed audit report is left behind.

This is the **does-it-actually-work** skill. Stories pass their own unit
tests and fences pass their own assertions, but a capability is only
*known to work* when it has been run against a real input and its output
inspected against the spec. This skill makes that loop structured and
repeatable — it is the exact loop a careful engineer runs by hand when
they clone a sample repo, run the tool, and squint at the output.

## Relationship to `phase-shakedown`

They are siblings on different axes — do not confuse them:

| | `phase-shakedown` | `capability-shakedown` (this skill) |
|---|---|---|
| Unit of work | a roadmap **phase** | one **capability** / CLI command |
| Driven by | the phase's `High-level-impl.md` done-criteria | a **sample app** the capability runs against |
| On a finding | **routes** it downstream (draft story / draft ADR / task chip) | **fixes** it in place — code, sample app, or environment |
| Output | `docs/phases/{phase}/_e2e/` report | `docs/_shakedowns/` report + the actual fixes |

If the user names a phase number, that is `phase-shakedown`. If they name
a command, a feature, or "a sample app", that is this skill.

## When this skill fires

Fire when the user wants a capability *run for real and made to work*:

- "shake down `codegenie gather`" / "exercise the vuln-index refresh flow"
- "run the CLI against a sample app and tell me what's missing"
- "does the dep-graph / SBOM / entrypoint feature actually work end-to-end?"
- "why is probe X's output empty / why does this say `unavailable`?"
- "try out `codegenie audit verify` and fix whatever breaks"

Do **not** fire for: auditing a whole roadmap phase (`phase-shakedown`),
running a single `pytest` file, implementing a known story
(`phase-story-executor`), or designing architecture (`phase-architect`).

## Inputs

- `capability=` — the command/workflow to exercise. Accepts a CLI
  subcommand (`gather`, `vuln-index refresh`, `audit verify`) or a plain
  description ("the SBOM probe"). Omitted → infer from the user's request;
  if still ambiguous, default to `gather` (the primary shipped capability)
  and say so in the first line of output.
- `--sample-app=` — name of an app under the user's sample-apps repo
  (e.g. `javascript/npm/esbuild`). Omitted → auto-select the best-fit
  existing app, or create one (Stage 2).
- `--diagnose-only` — run Stages 0–5 + the report, make **zero**
  mutations (no code, sample-app, environment, or doc changes). Use for
  first runs, CI, and evaluations. Default: off (the skill fixes).
- `--commit` — commit the codebase fixes + report at the end. Default:
  off — humans always merge, and the skill **never** pushes.
- `--max-fix-attempts=N` — cap on the codebase-fix retry loop (Stage 6).
  Default: 3 (mirrors `phase-story-executor`).

## Outputs

1. A committed-or-staged report at
   `docs/_shakedowns/{capability-slug}-{ISO-utc}.md` — the run log, every
   finding's root-cause class, the fix applied, the test-gap analysis for
   every codebase bug, the doc sweep, and a "Next-run primer".
2. For codebase bugs: new/strengthened tests (failing-first, verified
   non-vacuous) + the minimal code fix, with `make check` green.
3. For sample-app deficiencies: the fixed sample app in a local clone of
   the user's sample-apps repo, handed back for the user to push.
4. For environment gaps: the environment set up + the run docs
   (`docs/get-started.md`, `CLAUDE.md`) updated with the new prerequisite.
5. An updated doc set — every ADR / design doc / phase doc / roadmap
   entry / story whose accuracy the fix changed.

## Workflow

Nine stages, sequential. Stages 0–5 + 8 always run. Stages 6–7 are
skipped under `--diagnose-only`.

### Stage 0 — Environment doctor

Check the tools every later stage needs on `PATH`: `ruff`, `mypy`,
`pytest`, `make`, `git`, and the project CLI (`codegenie`). `docker` is
checked **lazily** — only when a finding's diagnosis needs it (Stage 6).
On a missing tool, bail loudly naming the likely cause (a git worktree
without its own `.venv` is the usual one) and the exact re-invocation.
Stage 0 never auto-bootstraps — that is a state mutation the operator
makes consciously.

### Stage 1 — Explore the project, derive the run command

First, read the most recent prior report for this capability under
`docs/_shakedowns/` if one exists — it tells you what was already fixed,
deferred, or found to be by-design, so this run does not re-litigate
settled findings. Then read the project to learn how the capability is
invoked and what it is *supposed* to produce. Do not assume — the CLI
surface, flags, and exit codes are all written down.

→ See [`references/explore-and-run.md`](references/explore-and-run.md).

### Stage 2 — Acquire the sample app

Clone the user's sample-apps repo, pick the best-fit existing app for the
capability, or create a new one if none fits. A sample app is only useful
if it actually contains the inputs the capability consumes.

→ See [`references/sample-app.md`](references/sample-app.md).

### Stage 3 — Run the capability

Run the derived command against the sample app. Capture exit code,
stdout, stderr, every artifact written, and every structured-log event.
Run it **twice** when the capability caches — the second run is itself a
signal (cache behavior, idempotence).

### Stage 4 — Inspect output against the spec

For every probe / field / artifact the capability should have produced,
compare what landed against what the design docs say should land. The
output of this stage is a flat list of **findings**: each is one
concrete thing that is missing, empty, `unavailable`, wrong, or no-op.
An all-clean run still produces a report — say so explicitly rather than
declaring victory silently (Rule 12).

### Stage 5 — Diagnose each finding to a root cause

Every finding is classified into exactly one root-cause bucket:
codebase-bug, environment, sample-app, or by-design. Getting this right
is the whole skill — a misdiagnosis sends the fix down the wrong route.

→ See [`references/diagnosis.md`](references/diagnosis.md).

### Stage 6 — Fix, by route (skipped under `--diagnose-only`)

| Root cause | Action |
|---|---|
| **by-design** | No code change. Document the honest degradation (a `get-started.md` troubleshooting note). It is not a bug. |
| **environment** | Set the environment up (start Docker, install the tool, build the image). Update `docs/get-started.md` + `CLAUDE.md` with the prerequisite. Re-run from Stage 3. |
| **sample-app** | Fix the sample app in the local clone — add the missing Dockerfile / lockfile / source. Re-run from Stage 3. Hand the diff back for the user to push. |
| **codebase-bug** | The deep loop: test-gap analysis → failing tests first → code fix → verify. → See [`references/codebase-fix.md`](references/codebase-fix.md). |

The skill does not pause for approval — it carries each fix through. The
safety rails below are what make that safe.

### Stage 7 — Doc sweep (skipped under `--diagnose-only`)

Once every fix has landed and `make check` is green, find and update
every doc the fix made stale: ADRs, production + phase design docs, the
roadmap, future stories, `get-started.md`, `CLAUDE.md`.

→ See [`references/doc-sweep.md`](references/doc-sweep.md).

### Stage 8 — Report

Write `docs/_shakedowns/{capability-slug}-{ISO-utc}.md`. Commit only
under `--commit`; never push.

→ See [`references/reporting.md`](references/reporting.md).

## Autonomous-fix safety rails

This skill mutates code, tests, docs, and sample apps without pausing.
These rails are non-negotiable — they are what make "fully autonomous"
safe instead of reckless:

- **No fix without a failing test first.** Every codebase fix begins
  with a test that is *run and observed to fail* on the broken code. A
  fix whose test never went red is rejected — you cannot show it fixed
  anything. (Rule 9.)
- **Verify the test is non-vacuous.** Before trusting a new test, prove
  it fails on the bug and passes on the fix — the cleanest proof is to
  neuter the suspected cause, watch the test go red, then restore.
- **Green gates are the definition of done.** `make check` must pass
  before the run completes. If it cannot be made green within
  `--max-fix-attempts`, **stop**, leave the working tree as-is, and write
  the report with the partial state flagged in a red banner. Never report
  success on a red gate (Rule 12).
- **Never push. Never force.** Commit only with `--commit`; humans always
  merge. Sample-app changes stay in the local clone for the user to push.
- **Frozen contracts stop the skill.** The probe ABC (`probes/base.py`),
  the fences, and anything an ADR explicitly froze are off-limits to
  autonomous edits. If a fix genuinely needs one changed, stop and flag
  it as needing an ADR amendment — do not edit it and move on.
- **Surgical changes only.** Fix the finding; do not refactor adjacent
  code (Rule 3).
- **The report is always written**, even on partial or failed runs.

## Definition of done

A shakedown run is complete when ALL hold:

- [ ] Stage 0 passed (tools on PATH) and the capability + sample app are
      named in the first line of output
- [ ] The capability ran to completion against the sample app; exit code,
      output artifacts, and logs were captured
- [ ] Every finding has exactly one root-cause class with evidence
- [ ] (not `--diagnose-only`) every codebase-bug finding has: a test-gap
      analysis, a test verified to fail-then-pass, a code fix, and
      `make check` green — or the run stopped and flagged the failure
- [ ] (not `--diagnose-only`) every sample-app finding was fixed in the
      clone and the capability re-run clean; every environment finding was
      set up and the run docs updated; every by-design finding documented
- [ ] (not `--diagnose-only`) the doc sweep ran and every stale doc was
      updated, or the report states explicitly that none were affected
- [ ] The report exists, validates, and carries the "Next-run primer"
- [ ] Wall-clock and token consumption are in the report

Anything less means the skill stopped early — surface the gap loudly.

## Best practices baked in

- **Read before you write** (Rule 8). Stages 1–2 are exploration; the
  diagnosis leans on what the docs *say* the output should be, never on a
  guess.
- **Fail loud** (Rule 12). A clean run is reported as "found zero issues
  — verify by spot-reading the run log", not a silent ✓. A red gate is
  never dressed up as success.
- **Tests verify intent** (Rule 9). The codebase-fix loop refuses any fix
  whose test did not first go red — see `references/codebase-fix.md`.
- **Match the codebase's conventions** (Rule 11). Discovery reads
  `CLAUDE.md` + `docs/contributing.md` and adopts the gate commands and
  test patterns it finds there.
- **A diagnosis is a hypothesis until proven.** "Probe X is no-op" is not
  a finding until you have run X in isolation and watched it produce
  nothing — see the discriminating tests in `references/diagnosis.md`.

## Failure modes the skill handles explicitly

| Symptom | Action |
|---|---|
| The capability is not a real CLI command | List the real `codegenie --help` surface; stop. Don't guess. |
| The sample-apps repo can't be cloned | Fall back to creating a hermetic sample app under a scratch dir; flag the clone failure in the report. |
| No sample app fits and the capability's inputs are unclear | Read the spec for the capability's declared inputs; build the minimal app that satisfies them. |
| `make check` was already red before the skill ran | First finding is "entry precondition fails"; do not attribute it to the capability. |
| A codebase fix can't be made green in `--max-fix-attempts` | Stop. Leave the tree as-is. Red banner in the report. Do not partially-commit. |
| The fix would need a frozen-contract edit | Stop that fix; flag it as needing an ADR; carry on with the other findings. |
| A finding is ambiguous between two root causes | Report both hypotheses with evidence; take the safer route (document over code-change); flag for human review. |
| The report path collides (same second) | Append a `-{counter}` suffix. |

## References

- [`references/explore-and-run.md`](references/explore-and-run.md) — exploring the project + deriving the exact run command + the capability catalog
- [`references/sample-app.md`](references/sample-app.md) — cloning / selecting / creating a sample app in the user's sample-apps repo
- [`references/diagnosis.md`](references/diagnosis.md) — the root-cause buckets + the discriminating tests that tell them apart
- [`references/codebase-fix.md`](references/codebase-fix.md) — the test-gap analysis + failing-tests-first + fix + verify loop
- [`references/doc-sweep.md`](references/doc-sweep.md) — which docs a fix can make stale and how to decide
- [`references/reporting.md`](references/reporting.md) — the report template + worked example

## What NOT to do

- Do not audit a whole roadmap phase — that is `phase-shakedown`.
- Do not skip the failing-test-first step for a codebase fix, ever.
- Do not report success when `make check` is red.
- Do not push to GitHub, or commit without `--commit`.
- Do not edit a frozen contract (probe ABC, fences) autonomously — stop and flag.
- Do not refactor adjacent code while fixing a finding (Rule 3).
- Do not declare a probe "no-op" without having run it and watched it produce nothing.
- Do not skip the report, even on a clean run or a failed run.
