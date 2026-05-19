---
name: phase-shakedown
description: Runs the codewizard-sherpa application end-to-end against a target phase, classifies every issue surfaced, and auto-routes findings (inline fix → spawned-task → `/phase-story-writer` story → `/phase-architect` ADR → critical escalation). Generic across all phases — derives "end-to-end" from each phase's `High-level-impl.md`, `final-design.md`, `roadmap.md`, and `_attempts/_lessons.md`. Always writes a committed `docs/phases/{phase}/_e2e/e2e-report-{ISO}.md` audit trail. Use whenever the user asks to "shake down", "smoke test", "audit", "run end-to-end", "find issues in", or do a closeout / sanity-check on a phase — e.g. "shake down phase 3", "is phase 2 healthy?", "e2e the current phase", "audit phase 0", "what's silently broken?". Auto-detects active phase from recent git activity unless named. Fire even if the user doesn't say "phase-shakedown" — match on end-to-end-run-and-triage intent.
---

# Phase Shakedown

Run the codewizard-sherpa app end-to-end against a target phase, classify
every issue surfaced, auto-route each one downstream, and leave behind a
committed audit trail at `docs/phases/{phase}/_e2e/e2e-report-{ISO}.md`.

This is the **runtime audit** skill in the phase pipeline:

1. `roadmap-phase-designer` — designs the phase
2. `phase-architect` — turns the design into ADRs + impl plan
3. `phase-story-writer` — turns the impl plan into stories
4. `phase-story-validator` — hardens stories before execution
5. `phase-story-executor` — turns one story into working code
6. **`phase-shakedown` (this skill)** — runs the assembled system, finds what's quietly broken, and routes the findings back into 2–5

It exists because individual stories pass their own tests and individual
fences pass their own assertions, but the *composition* — coordinator
plus probes plus CLI plus fences plus docs — only gets exercised
unstructured-by-a-human-noticing-something. This skill makes that
structured.

## When this skill fires

Trigger when the user wants an end-to-end runtime check on a phase:

- "shake down phase 3" / "smoke phase 2" / "audit phase 0"
- "is phase X healthy?" / "what's broken in phase 6?"
- "run the phase end to end" / "find issues in the current phase"
- "e2e the current phase before I close it out"
- Any closeout language: "phase 3 done criteria check", "phase 2 health"

Use it even when the user doesn't say "phase-shakedown" by name — match
on the end-to-end-run-and-triage intent. **Do not** fire for individual
test runs (`pytest tests/unit/...`), for fixing a known bug (use the
spawned-task chip directly), or for designing/writing/validating/
executing a story (those are the other phase-* skills).

## Inputs

- A phase number, folder name, or no argument
  - `phase=03` / `phase=03-vuln-deterministic-recipe` / `--phase=current`
  - Omitted → auto-detect (the **most-recently-touched** `docs/phases/NN-*/` folder per `git log --name-only -30`)
- Optional flags (all default to off / safe):
  - `--auto-confirm` — skip the inline yes-prompt for mutating actions (Stage 3). Default: off (the skill asks before mutating).
  - `--commit-report` — auto-commit the report + inline trivial fixes (Stage 7). Default: off — humans always merge. There is no `--no-commit`; "no commit" IS the default. Pass `--commit-report` only when you want the commit.
  - `--no-route` — dry-run; classify findings but don't fire downstream skills/tasks/edits/inline-edits (useful for first runs, evaluations, and worktree experiments). Default: off (routing fires).
  - `--include-bench` — presence-only flag; include `tests/bench/` performance canaries in the discovery. Default: off (perf canaries are advisory, not gating). Passing `--include-bench=false` is silently equivalent to omitting it.
  - `--include-contract` — presence-only flag; include `tests/contract/` real-binary tier in the discovery. Default: off (contract tests run nightly in CI by convention).
  - `--notify-author` — include the user's GitHub handle in critical-class escalation prompts. Resolves the handle from `git config user.email` → most recent commit author.

## Outputs

1. A committed (or staged, if `--no-commit`) markdown report at
   `docs/phases/{phase}/_e2e/e2e-report-{ISO-utc}.md` carrying the full
   execution log, every finding's class + route + downstream artifact
   link, gate summary, and a "Next-run primer" for the next shakedown
2. Spawned-task chips for every **bounded** finding
3. Draft stories under `docs/phases/{phase}/stories/_drafts/` for every
   **sub-system** finding (humans promote out of `_drafts/` after review)
4. Draft ADRs under `docs/phases/{phase}/ADRs/_drafts/` for every
   **architectural** finding (same promotion convention)
5. Inline edits for every **trivial** finding (lint, format, missing docstring)
6. On **critical**: a repo-root `FINDINGS.md` + red banner in the final
   summary + (with `--notify-author`) escalation prompt with the user's handle

## Workflow

Eight stages, sequential. Stages 0–6 always run; Stage 7 only on
`--commit-report`.

### Stage 0 — Environment doctor

Before anything else, check the tools every later stage assumes are on
`PATH`: `ruff`, `mypy`, `pytest`, `make`, `mkdocs`, and the project's
own CLI entry point (`codegenie` for codewizard-sherpa). If any are
missing, **bail loudly with a clear message** — do not fall through.

The most common cause is running from a git worktree that doesn't have
its own `.venv`. The error message should name the parent repo's venv
path explicitly so the operator can re-invoke with the right PATH:

```
phase-shakedown: environment precondition failed.
  Missing on PATH: ruff, mypy, pytest, codegenie
  Likely cause: this looks like a git worktree without its own venv.
  Try: PATH="<parent-repo>/.venv/bin:$PATH" <re-invocation>
```

If `make bootstrap` exists in the project, mention it as the alternate
remediation. Stage 0 does NOT auto-bootstrap — that's a state mutation
the operator should make consciously.

### Stage 1 — Detect the target phase

Default behaviour: tally `git log --name-only -30` over the
`docs/phases/NN-*/` prefixes and pick the most-touched. If the user
named a phase explicitly, skip detection. Print the resolved phase in
the first line of output so it's obvious what's being audited.

### Stage 2 — Discovery cascade

→ See [`references/discovery.md`](references/discovery.md) for the read
order and how to derive runnable commands from `**Done criteria:**`
checkboxes.

Produce a written **execution plan** before running anything. The
operator should be able to glance at it and predict every command the
skill will run.

### Stage 3 — Execute

Run each command. Capture exit codes, stdout, stderr, and the paths of
every file created or modified. **Default to read-only operations.**
Mutating actions need an inline yes-prompt unless `--auto-confirm` is
set.

→ See [`references/execution.md`](references/execution.md) for the
mutating-action allowlist, the structured-log capture pattern, and the
"why we don't use `subprocess.run(..., shell=True)` even here" note.

### Stage 4 — Triage

For every observed signal (failed gate, non-zero exit, probe
`exit_status=="error"` in a run record, fence regression, unhandled
exception, doc inconsistency), classify into one of five buckets.

→ See [`references/triage.md`](references/triage.md) for the five-class
severity ladder, the routing rules, and worked examples from real
incidents (the BudgetingContext drift, the plugins.manifest circular
import).

### Stage 5 — Route

Take the action mapped to each finding's class. **Sub-system** and
**architectural** routes write to `_drafts/` subfolders so the human
review step protects the audit trail (Rule 12 — fail loud + the
asymmetry of cost: a draft is easy to delete; a misfiled ADR pollutes
the trail).

| Class | Action |
|---|---|
| **Trivial** | Inline edit + note in the report |
| **Bounded** | `mcp__ccd_session__spawn_task` with self-contained prompt |
| **Sub-system** | `Skill(skill="phase-story-writer", args=...)` → `_drafts/` |
| **Architectural** | `Skill(skill="phase-architect", args=...)` → `_drafts/` |
| **Critical** | Spawned task + story + `FINDINGS.md` + red banner |

The skill **does not** ask before routing — Stage 3 was the consent
checkpoint for mutations. Routing decisions live in the report so a
reviewer can second-guess them.

### Stage 6 — Report

Write `docs/phases/{phase}/_e2e/e2e-report-{ISO-utc}.md` using the
template at [`references/reporting.md`](references/reporting.md). The
report is committed (or staged) and **lives in git** — these are the
phase's audit trail, the same way `_attempts/` is the audit trail for
stories.

Future shakedowns read the latest report first to know what's already
been deferred and what's been escalated. The "Next-run primer" footer
exists for that explicit purpose.

### Stage 7 — Commit (optional, gated)

Only with `--commit-report`. Stage the new report + any inline trivial
fixes; write a `docs(phase{NN}/e2e): shakedown {date}` commit; do NOT
push (humans always merge).

## Definition of done

A shakedown run is complete when ALL of these hold:

- [ ] Stage 0 environment doctor passed (all expected tools on PATH)
- [ ] The target phase is named in the first line of output
- [ ] An execution plan was written and (without `--auto-confirm`)
      confirmed before any mutating action
- [ ] Every command in the plan ran to completion. "Completion" means
      the command exited (with any code, zero or non-zero); a
      non-zero exit is a finding, not an incomplete run. The only
      incomplete state is a true hang / timeout / silent skip.
- [ ] Every observed signal has a class + route in the report
- [ ] Every **bounded** finding spawned a task chip
- [ ] Every **sub-system** finding produced a draft story file
- [ ] Every **architectural** finding produced a draft ADR file
- [ ] **Critical** findings (if any) wrote `FINDINGS.md` and printed
      the red banner
- [ ] The report file exists, is well-formed (frontmatter validates),
      and includes the "Next-run primer" footer
- [ ] Wall-clock and token-budget consumption are in the report

Anything less = the skill stopped early. Surface the gap explicitly.

## Best practices baked in

- **Read before you write** (Rule 8). The discovery cascade is the
  first half of the skill on purpose; classification leans on what the
  docs actually say, not what the skill imagines they say.
- **Surgical changes** (Rule 3). The skill itself touches `.codegenie/`
  + `docs/phases/{phase}/_e2e/` + `_drafts/` subfolders + (for trivial
  findings only) the single lines those findings name. Nothing else.
- **Fail loud** (Rule 12). Critical-class findings always escalate.
  Empty reports surface as "shakedown found zero issues — verify by
  spot-reading the execution plan", not as "all good ✓".
- **Match the codebase's conventions** (Rule 11). The skill reads
  `docs/contributing.md` as part of discovery and adopts the gate
  commands it finds there rather than hard-coding `make check`.
- **Routing rules are heuristics, not law.** The triage reference
  spells out the heuristics; reviewers override by recategorising a
  finding in the report and re-routing manually. The skill itself
  doesn't lock in decisions.

## Failure modes the skill handles explicitly

| Symptom | Action |
|---|---|
| Phase has no `High-level-impl.md` | Fall through to the generic floor + flag missing doc as a sub-system finding |
| `make check` is broken before the skill runs | First finding is "phase entry pre-condition fails" + critical class |
| A discovery-cascade command times out | Skip with a `[timeout]` note in the report; classify the timeout itself as a finding |
| Two stories' `_attempts/_lessons.md` disagree | Pick the more recent; flag the conflict as a doc inconsistency |
| No phase folder matches the user's argument | Stop. List available phases. Don't guess. |
| Auto-detection finds no recent phase activity | Default to the latest-numbered phase folder; print "auto-detect ambiguous; defaulting to most-numbered" |
| A downstream skill (`/phase-story-writer`, `/phase-architect`) errors | Capture the error in the report; spawn a task to fix the downstream skill instead; do not silently swallow |
| The report file path already exists (same-second collision) | Append a `-{counter}` suffix |

## References

- [`references/discovery.md`](references/discovery.md) — read order + how to parse Done-criteria + the generic floor
- [`references/triage.md`](references/triage.md) — five-class severity ladder + routing rules + worked examples
- [`references/execution.md`](references/execution.md) — safe-run rules + mutating-action allowlist + capture pattern
- [`references/reporting.md`](references/reporting.md) — the markdown report template + worked example
- [`references/escalation.md`](references/escalation.md) — `FINDINGS.md` format + critical banner + notification

## What NOT to do

- Do not redesign the phase (use `roadmap-phase-designer`)
- Do not write architecture (use `phase-architect` — the skill calls it for you)
- Do not write stories (use `phase-story-writer` — the skill calls it for you)
- Do not execute stories (use `phase-story-executor`)
- Do not auto-commit unless `--commit-report` was explicit
- Do not push to GitHub ever (humans always merge)
- Do not fix bugs beyond the trivial class inline (everything else routes downstream)
- Do not silently swallow errors from downstream skill calls — capture them as findings
- Do not skip the report even if zero issues were found (the report itself is the audit artifact)
