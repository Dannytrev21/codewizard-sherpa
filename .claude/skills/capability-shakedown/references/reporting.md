# Reporting — the shakedown report

Every run writes one report to
`docs/_shakedowns/{capability-slug}-{ISO-utc}.md`. It is the audit trail:
a future run reads the latest report first to know what was already
fixed, deferred, or found to be by-design. The report is written on
every run — clean, fixed, or failed. Commit it only under `--commit`;
never push.

`{capability-slug}` is the capability kebab-cased (`gather`,
`vuln-index-refresh`). `{ISO-utc}` is `YYYY-MM-DDTHH-MM-SSZ`. On a
same-second path collision, append `-{counter}`.

## Template

Use this structure verbatim — a future run depends on the headings.

```markdown
---
capability: <gather | vuln-index refresh | …>
sample_app: <path in sample-apps repo, or "created: <path>">
run_utc: <ISO-8601>
mode: <full | diagnose-only>
gate: <green | RED | not-run>
findings: <n total — n codebase, n environment, n sample-app, n by-design>
---

# Capability shakedown — `<capability>`

## Run summary

One paragraph: what was exercised, against which app, and the headline
outcome. If zero issues were found, say so here AND say how to verify
it ("verify by spot-reading the run log below") — never a silent ✓.

## Execution plan

The exact command(s) run, the sample app, and the output checks Stage 4
made. A reader should be able to predict every command.

## Findings

| # | Finding | Root cause | Evidence | Route |
|---|---|---|---|---|
| 1 | entrypoint probe emits `confidence: unavailable` | codebase-bug: no-op | `raw/dockerfile.json` absent after gather; `dockerfile` probe returns `raw_artifacts=[]` | code fix |
| 2 | runtime_trace fails every scenario | by-design | macOS has no `strace` (`runtime_trace.py` docstring) | document |

## Codebase fixes

For each codebase-bug finding:

### Finding <n> — <title>

- **Test-gap analysis:** why the suite missed it (which of the patterns
  in `codebase-fix.md` applied).
- **Tests added:** file + name; the RED evidence (it failed on the
  unfixed code); the non-vacuous proof (neuter → RED → restore).
- **Code fix:** the files + the one-line description of the change.
- **Gate:** `make check` result.

## Sample-app changes

Each app file added/modified, and the reminder that the user must push
the sample-apps clone.

## Environment setup

Each tool/image/service set up, and the doc updated with the prerequisite.

## Docs swept

Each doc touched, one line on what was stale → what it now says. Or the
explicit sentence "No docs were made stale by these fixes."

## Gate summary

`make check` final state; the regenerated snapshots (if any) and why each
diff was the intended behavior change.

## Budget

Wall-clock and approximate token consumption.

## Next-run primer

What a future shakedown of this capability should know: the by-design
limitations already documented (don't re-file them), the deferred items,
the sample app to reuse.
```

## Discipline

- **Never report success on a red gate.** If `make check` could not be
  made green, the frontmatter `gate:` is `RED`, the run summary leads
  with it, and the report opens with a red banner. (Rule 12.)
- **Every finding has a root cause and evidence** — an unexplained
  finding is an incomplete run.
- **The test-gap analysis is mandatory** for every codebase fix. A fix
  with code but no gap analysis means the bug class can ship again — the
  report must show the gap was closed.
- **`--diagnose-only` runs** still produce the full Findings table and
  root causes; the Codebase-fixes / Sample-app / Environment / Docs
  sections each read "skipped — diagnose-only".
