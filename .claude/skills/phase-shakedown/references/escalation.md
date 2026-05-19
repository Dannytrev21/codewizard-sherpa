# Escalation — critical-class handling

Critical findings are the ones that block the phase or signal a class
of bug just escaped the existing defences. They get the full
escalation treatment: spawned task + draft story + draft ADR +
`FINDINGS.md` + red banner.

## What lands on critical class (recap from triage.md)

- `tests/fence/` test newly fails (regression in a structural defence)
- `make lint-imports` reports a NEW broken contract
- `make fence` exits non-zero
- A `xfail(strict=True)` sentinel XPASSed and marker is still in place
- A probe emits a secret-shaped field (sanitiser leak)
- Import-time `AssertionError` from a catalogue / registry / fence
- CI red on master for the same probe/module for ≥7 days (carry-
  forward from cross-run check)
- A previously-flagged critical finding is still unfixed (recurrence)

## `FINDINGS.md` at repo root

If there are any critical findings, write or append to `FINDINGS.md`
at the analyzed repo's root. The file lives in git when committed.

### Format

```markdown
# FINDINGS — codewizard-sherpa

Append-only critical-class findings from phase-shakedown runs. Resolve
an entry by striking through (`~~…~~`) and adding a resolved-by link.
Do NOT delete entries — the history is the audit trail.

---

## 2026-05-19T03:24:18Z — Phase 03 shakedown — F-01

**Class:** Critical
**Symptom:** Per-submodule cold-start fence regression — 4 new
modules joined `_KNOWN_BROKEN_PRE_FIX` (was 28, now 32) between
shakedowns on 2026-05-17 and 2026-05-19.
**Why critical:** the fence's job is to *catch* the cycle; a
growing skip-set means we're working around the fence instead of
fixing the cycle.
**Spawned task:** `<task-id>` (link)
**Draft story:** `docs/phases/03-…/stories/_drafts/S10-03-…` (link)
**Draft ADR:** `docs/phases/03-…/ADRs/_drafts/0015-…` (link)
**Notify:** @dannytrev21 (`--notify-author` was set)

---
```

### When to start a new entry vs append

- **New entry** for each unique critical finding (don't compress
  related findings into one)
- **Same entry, append a sub-bullet** if a subsequent shakedown
  surfaces the *exact same* finding (recurrence) — adds a recurrence
  count

## Red banner in final output

When critical findings exist, the skill's terminal summary leads with
a clearly-visible escalation banner:

```
================================================================
  ⚠  PHASE 03 SHAKEDOWN — 2 CRITICAL FINDINGS — REVIEW REQUIRED
================================================================
  F-01  Cold-start fence regression (skip-set grew 28 → 32)
  F-05  xfail(strict=True) sentinel XPASSed; marker still in place
  See FINDINGS.md and the full report at:
    docs/phases/03-vuln-deterministic-recipe/_e2e/e2e-report-2026-05-19T032418Z.md
================================================================
```

The banner appears regardless of `--commit-report` / `--auto-confirm`
state — it's informational and always visible.

## Notification (`--notify-author`)

When the flag is set, the skill includes the user's GitHub handle in:

- The spawned-task prompt (as a "page" line: `@<handle> — recurrence
  of <symptom>, please review`)
- The draft story's Notes-for-implementer section
- The draft ADR's Status section as a `Review trigger`

The handle resolves from `git config user.email` → derive from the
local profile or the most recent commit author.

## What NOT to escalate as critical

- A test that's been documented as `xfail` (without `strict`) — it's
  a known state, not a regression
- A test that's been documented as `skip` (with a reason) — same
- A new finding that surfaced because a phase intentionally landed a
  new test or capability (the *first* run after a Phase-N test
  addition will surface every gap it now catches — those are
  baseline-establishment findings, not regressions)
- Anything the previous report already escalated this week (avoid
  doubling up — link to the existing entry instead)

## Promotion to critical from a lower class

The triage rules in `triage.md` define the initial class. The
shakedown can *promote* to critical mid-run when:

- A bounded finding is the **third** recurrence of the same symptom
  (across previous reports)
- A sub-system finding is the **second** recurrence with the same
  root cause
- An architectural finding is the **first** recurrence (architectural
  decisions don't get re-deferred)

Promotion logic runs after the report's Findings list is assembled
but before the Verification footer is written. The footer carries
the promotion note.
