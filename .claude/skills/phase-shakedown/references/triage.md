# Triage — five-class severity ladder + routing rules

Every observable signal the shakedown surfaces is classified into one
of five buckets. The class determines the route. The routes are
intentionally asymmetric — trivial things get fixed inline; everything
bigger goes through a downstream skill or task pipeline so humans stay
in the loop.

## The five classes

### 1. **Trivial**

A change a careful reviewer would land in a one-line PR comment. No
behaviour change. No new state. No invariant questioned.

**Examples:**
- A test was skipped without a reason — add the reason
- A module has no docstring — add a one-line one
- A ruff / format drift on a file in the shakedown's path
- A comment that explains WHAT instead of WHY — delete or rename

**Route:** the skill edits the file inline as part of this run. Note
the edit in the report under "Inline fixes".

**Anti-pattern to avoid:** anything that touches a frozen contract,
even if it's "just a comment". Frozen-contract files belong to ADRs —
escalate to architectural.

### 2. **Bounded**

A real bug, but the fix is localised to one module, one clear failure
mode, and one PR-sized change. The skill knows the bug exists and
knows roughly how to fix it but the fix is out of scope for an
auto-run (testing, review, possibly a CI cycle).

**Examples:**
- BudgetingContext drift: `BudgetingContext` is missing `output_dir`;
  probes silently `AttributeError`. Fix is single-file + one new
  assertion. Spawn a task.
- A typed exception leaks through when it should be caught and
  translated to a Result variant
- A probe times out on a specific fixture; raise its timeout or split
  its work
- Cold-start fence's `_KNOWN_BROKEN_PRE_FIX` set grows (a regression
  added a new module to the cycle)
- A doc-fence test fails because a referenced file moved

**Route:** `mcp__ccd_session__spawn_task` with a self-contained prompt
(the spawned session has no memory of this conversation; include
reproduction, file paths, expected end state, project-context
breadcrumbs).

### 3. **Sub-system**

A real gap that needs design discussion, multiple files, ACs, a TDD
plan, and the full story rigour. Or — equivalently — a fix that
crosses two-or-more files in a non-obvious way.

**Examples:**
- A `roadmap.md`-promised test file doesn't exist (e.g., "Phase 3 was
  supposed to ship `tests/property/test_cache_invariant.py`")
- A probe-output schema slice claims fields its production code never
  emits (or vice versa)
- A doc inconsistency that spans 2+ docs (e.g., arch says
  `precedence: int = 0`, production-ADR says `50`)
- A story's stated AC has no test that exercises it
- A "cross-cutting test-architecture addition" from `roadmap.md` is
  named but the file doesn't exist

**Route:** `Skill(skill="phase-story-writer", args=...)` writes a
draft story under `docs/phases/{phase}/stories/_drafts/`. A human
promotes it to the canonical location after review.

Include in the args: the finding's evidence, the proposed AC list (let
the writer harden), the files it spans, the relevant ADR / arch
references the writer should pull.

### 4. **Architectural**

A contract has drifted, a new pattern is needed, a decision crosses
phase boundaries, or the right answer requires an ADR-grade
discussion. The fix is too consequential for a story — it needs a
named decision in the audit trail.

**Examples:**
- `BudgetingContext` doesn't satisfy `ProbeContext` structurally — the
  whole ctx-shape decision crosses Phase 0's ADR-0007 and Phase 3's
  plugin context plans
- A circular import between two top-level packages — the import-graph
  decision is architectural even though the fix is small
- A new task class needs a primitive that doesn't exist; the primitive
  belongs in the shared layer (per production ADR-0039 bounded-additive
  exception) — that's an ADR amendment
- A frozen surface (`Plugin` Protocol, `ProbeContext`, exception
  marker invariant) has drifted and the spec needs updating to match
  reality OR the code needs to be brought back into line

**Route:** `Skill(skill="phase-architect", args=...)` writes a draft
ADR under `docs/phases/{phase}/ADRs/_drafts/`. A human promotes it.

### 5. **Critical**

Production-floor-broken state, or anything that blocks the phase's
exit criteria, or anything security-relevant.

**Examples:**
- A test in `tests/fence/` newly fails (these are the structural
  defences — a regression here means a class of bug just got
  introduced)
- `make lint-imports` reports a NEW broken contract
- CI has been red on master for the same probe/module across the last
  7 days
- A probe emits a secret-shaped field (exit 6 territory, ADR-0010 was
  designed to catch this — if it leaked through, the sanitiser itself
  is broken)
- A fence's `xfail(strict=True)` sentinel just XPASSed and nobody
  removed the marker (an unhandled "the fix landed but we didn't tell
  the test" state)
- An `AssertionError` from a load-bearing-invariant module at import
  time (catalogs failing self-validation, etc.)

**Route:** ALL of the lower routes + a repo-root `FINDINGS.md` (or
appended to if one exists) + a red banner in the final summary +
(with `--notify-author`) include user's handle in the escalation
prompt.

## Heuristic table

When a signal fires, walk these rules top-down. Stop at the first
match. If no rule matches, default to **bounded** + log "no triage
rule matched — please refine references/triage.md" as a separate
sub-system finding.

| # | Symptom heuristic | Class |
|---|---|---|
| 1 | `tests/fence/` test newly fails (not xfail, not skipped) | Critical |
| 2 | `make lint-imports` reports new broken contract | Critical |
| 3 | `make fence` exits non-zero | Critical |
| 4 | A `xfail(strict=True)` sentinel XPASSed and marker is still in place | Critical |
| 5 | Probe emits secret-shaped field (sanitiser leak) | Critical |
| 6 | Import-time `AssertionError` from a catalogue / registry / fence | Critical |
| 7 | A frozen-contract file changed without an ADR amendment | Architectural |
| 8 | A circular import between top-level packages | Architectural |
| 9 | A primitive needed for a new task class belongs in the shared layer | Architectural |
| 10 | Contract-conformance fence (ProbeContext / Plugin Protocol) fails | Architectural |
| 11 | A `roadmap.md`-promised test file doesn't exist | Sub-system |
| 12 | An AC in a story has no corresponding test | Sub-system |
| 13 | Two docs disagree (arch vs ADR vs roadmap) | Sub-system |
| 14 | Probe schema slice diverges from sub-schema declaration | Sub-system |
| 15 | A "Test architecture evolution" obligation isn't yet shipped | Sub-system |
| 16 | Probe `exit_status=="error"` on a smoke fixture (AttributeError-class) | Bounded |
| 17 | Typed exception leaks instead of being translated to a Result variant | Bounded |
| 18 | A test times out / flakes on a specific fixture | Bounded |
| 19 | Cold-start fence skip-set grew (new module hit the cycle) | Bounded |
| 20 | Doc-fence test fails because a referenced file moved | Bounded |
| 21 | Ruff or ruff-format complaint on a file in the shakedown's path | Trivial |
| 22 | Module has no docstring | Trivial |
| 23 | Test skipped without `reason=` | Trivial |
| 24 | Comment explains WHAT instead of WHY | Trivial |
| ∅ | None of the above | **Bounded** + log "triage rule gap" as a separate sub-system finding |

## Worked examples (today's bugs)

**Bug A — BudgetingContext drift.** Probes `scip_index`,
`tree_sitter_import_graph`, and `slo` AttributeError on `ctx.output_dir`
because BudgetingContext omits five of ProbeContext's attributes.

- Symptom: probe `exit_status=="error"` (heuristic 16) + contract-
  conformance fence fails (heuristic 10)
- The contract-conformance heuristic wins (higher precedence) →
  **Architectural**
- Route: `Skill(skill="phase-architect", args="draft an ADR amendment
  for Phase 0 ADR-0007 reconciling ProbeContext and the
  coordinator-built ctx — either BudgetingContext implements
  ProbeContext structurally, or ADR-0007 drops the omitted attrs from
  the contract")`

**Bug B — plugins.manifest circular import.** Importing
`codegenie.plugins.manifest` from a fresh subprocess crashes;
`types/identifiers → probes/node_build_system → probes/__init__ →
layer_b/dep_graph → depgraph/__init__ → depgraph/registry →
types/identifiers`.

- Symptom: circular import between top-level packages (heuristic 8) →
  **Architectural**
- Route: `Skill(skill="phase-architect", args="draft an ADR for Phase
  3 (or Phase 1 amendment) deciding the owning module for
  PackageManager — inline definition in types.identifiers, or
  re-export-from-probes pattern with a TYPE_CHECKING shim")`

**Bug C — `_KNOWN_BROKEN_PRE_FIX` set growth.** Imagine a future
shakedown notices the cold-start fence skip-set grew from 28 to 32.

- Symptom: cold-start fence skip-set grew (heuristic 19) → **Bounded**
- Route: spawned task — "the cold-start fence skip-set grew. Identify
  which new modules joined the cycle and either fix the cycle or
  surface an architectural finding if the fix isn't local."

## Promotion / demotion rules

- If a **bounded** finding has appeared in ≥2 previous e2e reports for
  this phase, **promote to sub-system**. Recurrence means the bug-class
  isn't a one-off; it deserves a story.
- If a **sub-system** finding has appeared in ≥2 previous e2e reports
  with the same root cause, **promote to architectural**. The story
  pipeline hasn't fixed it; the underlying decision needs
  reconsideration.
- If a **critical** finding has appeared in ≥1 previous e2e report
  unfixed, **page** (with `--notify-author`, include the user's handle
  in the spawned task's prompt — this is a recurrence signal, not a
  new bug).

The previous-report check happens during discovery: read the most
recent `docs/phases/{phase}/_e2e/e2e-report-*.md` first.

## What NOT to triage

- Tests marked `xfail` (without strict) — these are documented known
  states; only `xfail(strict=True)` that XPASSes is critical
- Tests marked `@pytest.mark.bench` — performance canaries, not
  correctness; skip unless `--include-bench`
- Anything inside `_drafts/` — these are this skill's own output;
  don't double-flag
