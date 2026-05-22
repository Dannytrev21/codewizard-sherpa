# Doc sweep — what a fix can make stale

A fix changes behavior; the docs describe behavior; so a fix can make
docs lie. Stage 7 finds and repairs every doc the fix made stale. Run it
only after every fix has landed and `make check` is green.

## The governing question

For each doc, ask one thing: **"What did a reader of this doc believe
that the fix just made false?"** If the answer is "nothing", do not touch
it. Surgical edits only — this stage is not a docs rewrite.

## The doc map

| Doc | Owns | A fix makes it stale when… |
|---|---|---|
| `docs/production/adrs/` | Frozen architectural decisions (Nygard format) | the fix changed behavior an ADR froze, or established a new decision worth recording. Amend the ADR (a dated "Correction"/"Amendment" note) or add a new one. |
| `docs/production/design.md` | The production-target architecture | the fix changed a component contract or data flow the design describes. |
| `docs/localv2.md` | The local POC spec — probe inventory, `RepoContext` schema, CLI surface | a probe's output shape, availability, or confidence changed; a CLI flag/exit code changed. |
| `docs/phases/{NN}/final-design.md` + `phase-arch-design.md` | One phase's design + 4+1 views + edge cases | the fix corrected behavior that phase designed; the phase's edge-case table missed this case. |
| `docs/phases/{NN}/ADRs/` | Per-phase decisions | same as production ADRs, scoped to the phase. |
| `docs/phases/{NN}/stories/` + `_attempts/` | Executable units + their attempt logs | a story's premise or status changed; a story shipped output the fix proved wrong. A bug a story called `Done`/`GREEN` may deserve a note in its `_attempts/` log. |
| `docs/roadmap.md` | Phase scope + exit criteria | scope understanding changed — e.g. something believed "later-phase" turned out shippable now, or vice versa. |
| `docs/get-started.md` | The operator run guide | a new prerequisite, platform constraint, exit code, or troubleshooting case. Environment fixes almost always land a note here. |
| `docs/contributing.md` | Contributor guide — test disciplines, structural defenses | the fix added a new structural defense / test tier contributors must keep green. |
| `CLAUDE.md` | Repo guidance for agents | the "Common commands" or "Current state" sections drifted; a load-bearing commitment changed. |

## Which fix touches which doc

- **codebase-bug fix** → the ADR that froze the changed behavior (amend,
  don't silently contradict — Rule 7); the owning phase's design docs if
  an edge case was missed; `localv2.md` if a probe's output surface
  changed; `contributing.md` if a new test discipline was added.
- **environment fix** → `get-started.md` (the prerequisite) and
  `CLAUDE.md` if the run surface changed. This is the most common sweep.
- **sample-app fix** → usually no codewizard-sherpa doc; note the change
  in the report and in the sample-apps repo's own README if it has one.
- **by-design finding** → `get-started.md` troubleshooting (so the next
  operator does not re-file the "bug"), and `localv2.md`/phase docs if
  the limitation was undocumented.

## New ADRs

If a fix embodies a genuine architectural decision that no ADR covers —
not a bug fix, a *decision* with trade-offs — write a new ADR in Nygard
format (Context / Decision / Consequences) in the correct `ADRs/`
directory, numbered after the current highest. Most fixes do **not**
warrant a new ADR; an amendment note on an existing one usually suffices.
When in doubt, prefer amending — a sprawl of thin ADRs is its own debt.

## Surface conflicts, do not average them

If the fix revealed two docs that already contradicted each other (Rule
7), do not blend them. Pick the one that matches the now-correct
behavior, update the other, and note the conflict in the report so a
human knows it was resolved deliberately.

## Output

A "Docs swept" section in the report: every doc touched, one line on what
was stale and what it now says — or the explicit sentence "No docs were
made stale by these fixes" when that is genuinely true.
