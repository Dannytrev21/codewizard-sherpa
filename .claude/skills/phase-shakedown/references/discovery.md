# Discovery — how to figure out what to run for an arbitrary phase

The shakedown skill is generic across phases 0–16. It can't hard-code
which commands matter for which phase — phase scopes diverge wildly
(Phase 0 is bullet-tracer foundations, Phase 7 is distroless container
migrations, Phase 11 is Sigstore signing). The discovery cascade is how
the skill works out, from the docs alone, what "end-to-end" means for
the named target.

## Read order (cascade)

Read in this order. Each layer adds commands to the execution plan;
later layers can override or supplement earlier ones.

### Layer 1 — `docs/phases/{phase}/High-level-impl.md`

Every phase that's progressed past `final-design.md` ships a
`High-level-impl.md`. It's an ordered list of Steps, and every Step
ends in a `**Done criteria:**` block of `- [ ]` checkboxes. Each
checkbox is a runnable assertion in plain English; the skill translates
each into a pytest invocation, a CLI command, or a doc-check.

**Translation patterns** (use these heuristically; the doc-author may
have used a different phrasing):

| Checkbox phrasing | Derive |
|---|---|
| "every fixture loads" / "fixtures smoke-load" | `pytest tests/fixtures/test_fixtures_load.py` |
| "make check clean" / "lint, type, test all green" | `make check` |
| "golden-file comparisons byte-equal" | `pytest tests/golden/ --no-cov` |
| "cache hits on the second run" | `pytest tests/smoke/test_cli_end_to_end.py::test_cache_hit_on_second_run` |
| "audit verify exits 0" | `codegenie audit verify --runs-dir … --cache-dir … --yaml-path …` (paths from a smoke fixture run) |
| "schema validation gate" | `pytest tests/unit/test_schema_validation.py` |
| "fence stays green" | `make fence` |
| "tests/property/X passes over ≥N Hypothesis runs" | `pytest tests/property/X -v` |
| "tests/contract/Y green" | `pytest tests/contract/Y -m contract` |
| "tests/e2e/scenarios.yaml row N exits 0" | `pytest tests/e2e/test_e2e_{slug}.py -v` |
| "PR opened" / "branch created" / anything human-merge | **skip** — humans always merge |

If a phrasing doesn't translate cleanly, **don't guess**. Add it as a
"doc inconsistency" sub-system finding and move on; the human picks it
up in the report review.

### Layer 2 — `docs/phases/{phase}/final-design.md` §"Exit criteria"

If `High-level-impl.md` didn't land yet, `final-design.md` (always
present after `roadmap-phase-designer` ran) carries the exit criteria
in plain prose. Apply the same translation patterns above; expect more
ambiguity and more sub-system "ambiguous criterion" findings.

### Layer 3 — `docs/roadmap.md`

Two sections matter:

- The per-phase entry (Phase 0, Phase 1, … Phase 16) — carries scope,
  testing summary, exit criteria
- The "Test architecture evolution" table near the top — lists the
  cross-cutting test capabilities each phase is supposed to land. Any
  capability that's named for the target phase but missing from
  `tests/` is a **sub-system** finding ("Phase 3 was supposed to ship
  `tests/property/test_cache_invariant.py` but the file doesn't
  exist").

### Layer 4 — `docs/contributing.md` §"Project conventions"

Carries the canonical gate commands the project uses (today: `make
check`, `make lint-imports`, `make fence`, `pre-commit run --all-files`).
Use these verbatim — don't invent. If a convention says "every PR
runs `make foo`", add `make foo` to the plan.

### Layer 5 — Latest 3 entries under `docs/phases/{phase}/stories/_attempts/`

The story attempt logs are where the most recent ground-truth lives.
Read `_attempts/_lessons.md` first (cross-story carry-forward), then
the three most-recent per-story attempt files (sorted by mtime). Note:

- What probes / fixtures / commands the stories most recently touched
  — add their tests to the plan
- What "deferred" items are mentioned — every deferral is a candidate
  finding (sub-system, usually)
- What lessons-learned name as a recurring trap — bake the trap-check
  into the run (e.g., if a lesson says "always re-run `make
  lint-imports` after editing pyproject.toml", add a regression check)

### Layer 6 — Generic floor (always runs)

Regardless of phase, always include:

```
codegenie gather tests/fixtures/polyglot/    # the existing smoke fixture
codegenie audit verify --runs-dir … --cache-dir … --yaml-path …
make check
make lint-imports
make fence
pytest tests/fence/ -q --no-cov              # all structural defenses
pytest tests/smoke/ -q --no-cov              # the end-to-end smoke suite
```

These exist on every phase from Phase 0 onward; if they're broken, the
phase itself is broken regardless of what else the phase claims to
ship. Always-broken floor = critical finding.

## How to write the execution plan

Produce a markdown block the operator can scan:

```markdown
## Execution plan for Phase 03 (vuln-deterministic-recipe)

Derived from:
- High-level-impl.md §Step 4 — Done criteria (4 commands)
- final-design.md §Exit criteria (1 additional command)
- roadmap.md §Test architecture evolution row "Phase 3" (4 test files referenced)
- contributing.md §Project conventions (3 gate commands)
- _attempts/_lessons.md (1 trap-check)
- generic floor (7 commands)

Total: 20 commands; ~6 of them mutate (those are flagged ⚠️)

| # | Command | Source | Mutates? |
|---|---|---|---|
| 1 | `make check` | contributing.md + generic floor | no |
| 2 | `pytest tests/property/test_cache_invariant.py -v` | roadmap.md (Phase 3 row, item a) | no |
| 3 | `codegenie gather tests/fixtures/polyglot/` | generic floor | yes (writes .codegenie/) |
| … | | | |
```

Print this **before** running anything. Without `--auto-confirm`, wait
for the operator to type "yes" / "go" / "ok" before Stage 3 starts.

## Cross-phase awareness

Scan **every** phase's most recent e2e report — not just the
immediately-prior phase. Specifically: for every directory matching
`docs/phases/*/`, read the newest-mtime file in `_e2e/e2e-report-*.md`
if one exists. Why all phases, not just N-1:

- **Cross-phase contamination is the norm, not the exception.** The
  generic floor (`tests/fence/`, `tests/adv/`, `make check`) sweeps
  test files from every phase indiscriminately. A regression
  introduced in Phase 7 can surface in a Phase 0 shakedown because
  Phase 0's floor includes Phase 7's fences.
- **Recurrence promotion needs full history.** The promotion rules in
  `triage.md` (bounded ≥2 → sub-system, sub-system ≥2 → architectural)
  count occurrences across reports. Limiting the lookback to one
  phase makes the count under-report.
- **Architectural findings cross phase boundaries by definition.**
  A `PackageManager` ownership decision (Phase 1 ADR-0013) surfacing
  inside Phase 3's shakedown is the canonical example.

For each previous-phase report:

- Read the **Verification footer** (the Next-run primer section) — it
  enumerates the explicit carry-forward items
- Read the **Findings** section for anything unresolved
- Add unresolved findings to the current run's "previous-report
  carry-forward" candidates; the triage stage decides whether each
  still applies and whether recurrence-promotion fires

If no previous reports exist anywhere, this step is a no-op. First
shakedowns establish the baseline; the recurrence engine warms up
after the second run.

## What NOT to discover

- Tests that explicitly opt out via `pytest.mark.bench` — those are
  performance canaries, not correctness gates; run them only on
  `--include-bench`
- Tests under `tests/contract/` — by convention they run nightly in CI,
  not on shakedown (loaded only on `--include-contract`)
- Any command requiring credentials (`gh`, `kubectl`, `docker push`) —
  shakedown is local-only
- Anything under `_drafts/` — drafts are by definition not yet
  contract-pinned; they're the *output* of shakedown, not input

## Failure modes during discovery

| Symptom | Action |
|---|---|
| The named phase folder doesn't exist | Stop. Don't fall through to a different phase. List available phases in the error. |
| `High-level-impl.md` exists but has no `**Done criteria:**` blocks | Sub-system finding: "Phase X High-level-impl is missing Done-criteria — discovery falls through to final-design". Continue with Layer 2. |
| A checkbox phrasing has no translation | Sub-system finding: "criterion X has no shakedown translation — add a row to references/discovery.md" |
| Two layers disagree (e.g., final-design says `make check`; contributing.md says `make verify`) | Pick the more recent doc; flag the conflict as a sub-system finding |
| The generic floor itself fails | Critical: "phase entry pre-condition fails — fix this before shakedown can run meaningfully" |
