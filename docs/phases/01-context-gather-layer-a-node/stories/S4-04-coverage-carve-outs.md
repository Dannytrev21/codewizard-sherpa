# Story S4-04 — Coverage carve-outs declared in `pyproject.toml`

**Step:** Step 4 — Ship `CIProbe`, `DeploymentProbe`, and `TestInventoryProbe`
**Status:** Ready
**Effort:** S
**Depends on:** S4-01 (`CIProbe` on disk), S4-02 (`DeploymentProbe` on disk)
**ADRs honored:** **ADR-0005 (90/80 floor with 85/75 carve-out for `deployment.py` and `ci.py`)**

## Context

ADR-0005 commits the phase to a coverage ratchet from Phase 0's 85/75 to 90/80, **but** with explicit per-module carve-outs at 85/75 for `src/codegenie/probes/deployment.py` and `src/codegenie/probes/ci.py`. The rationale (Rule 9 — "tests verify intent, not just behavior"): both modules have many structurally-narrow branches (one `if` per supported CI provider; one `if` per deployment file marker) where a blanket 90% line coverage is gameable by branch-checkbox tests that assert *nothing meaningful*. Intent-verifying tests carry the load; coverage is supporting, not load-bearing.

This story does **not** raise the global gate (that happens in S6-02). It declares the carve-outs in `pyproject.toml` *now*, so that when S6-02 ratchets the global floor to 90/80, the carve-outs are already in place and `ci.py` / `deployment.py` continue passing at their 85/75 module floor. Splitting the declaration from the ratchet is deliberate per `High-level-impl.md §Step 4`: the carve-outs live with the probes they protect, the ratchet lives with the documentation handoff.

Further carve-outs require their own ADR — this ADR is the registry root for per-module coverage relaxations (per ADR-0005 §Decision). A Phase 2+ probe that wants relaxation must file its own ADR explaining (a) why the module's branch shape makes a higher floor gameable, (b) what specific test pattern would satisfy the higher floor and *be theater*, and (c) what intent-verifying tests it ships instead.

## References — where to look

- **Phase ADRs:**
  - **`../ADRs/0005-coverage-carve-outs-deployment-ci.md`** — the single ADR this story implements; read §Decision and §Consequences carefully.
  - `../ADRs/0007-warnings-id-pattern.md` — referenced by ADR-0005 as the related structural defense (coverage is supporting; the warning-ID pattern is the load-bearing structural defense).
- **Architecture:**
  - `../phase-arch-design.md §"Goals"` #7 — "90% line / 80% branch on `src/codegenie/` excluding `cli.py`. Per-module floor 85% line / 75% branch for `probes/deployment.py` and `probes/ci.py` declared in `pyproject.toml`."
  - `../phase-arch-design.md §"Testing strategy" "CI gates"` — `--cov-fail-under=90` enforcement (S6-02's job; this story is the carve-out declaration only).
  - `../phase-arch-design.md §"Tradeoffs (consolidated)"` row 9 — the 90/80 + 85/75 trade.
- **Implementation plan:**
  - `../High-level-impl.md §"Step 4" "Done criteria"` — "Per-module coverage carve-out (85% line / 75% branch) declared in `pyproject.toml` for `probes/deployment.py` and `probes/ci.py` per ADR-0005; rest of `src/codegenie/` at 90/80."
  - `../High-level-impl.md §"Step 6"` — the global ratchet to 90/80 (the *enforcement* counterpart of this story).
  - `../High-level-impl.md §"Implementation-level risks" #5` — "Coverage ratchet at 90/80 is tight enough to block Step 6 if any probe falls short."
- **Source design:**
  - `../final-design.md §"Goals"` — the 90/80 + 85/75 carve-out rule.
  - `../final-design.md §"Departures from all three inputs" #5` — codification rationale.
- **Existing config:**
  - `pyproject.toml` — Phase 0 declares `--cov-fail-under=85` (or wherever the gate lives). This story adds per-module thresholds without changing the global; S6-02 raises the global.
  - Phase 0's `[tool.pytest.ini_options]` and `[tool.coverage.report]` sections — the surface this story extends.
- **Global Rules:**
  - Rule 9 — "Tests verify intent, not just behavior" — the load-bearing rationale.
  - Rule 12 — "Fail loud" — coverage gate must fail CI explicitly when a module dips below its declared floor.

## Goal

`pyproject.toml` declares per-module coverage thresholds (85% line / 75% branch) for `src/codegenie/probes/deployment.py` and `src/codegenie/probes/ci.py`, and explicitly states (via comment or config docstring) that further carve-outs require an ADR amendment to ADR-0005. The global floor is **unchanged** in this story; S6-02 raises it to 90/80.

## Acceptance criteria

- [ ] `pyproject.toml` has a per-module coverage table (under `[tool.coverage.report]` or via `pytest-cov`-supported per-file thresholds; the mechanism is the implementer's call but must be honored by the `test` CI job).
- [ ] The table contains exactly two entries: `src/codegenie/probes/deployment.py` → line 85 / branch 75; `src/codegenie/probes/ci.py` → line 85 / branch 75.
- [ ] `pyproject.toml` carries an inline comment (or section docstring) referencing ADR-0005 by path: `# Per-module coverage carve-outs declared by ADR-0005. Further carve-outs require a new ADR amending 0005.`
- [ ] The global `--cov-fail-under` value is **not** changed in this story (S6-02 raises it). The current Phase 0 floor (85/75 globally) continues to hold.
- [ ] CI runs the existing `test` job; the local coverage report for the two carved-out modules shows the actual line/branch percentages and they are at or above 85/75 at the close of S4-01 and S4-02. If either is below at this story's PR time, the implementer **must** add intent-verifying tests to the failing probe's S4-01 / S4-02 PR — not lower the floor.
- [ ] Red test: a single deliberately-skipped branch in `ci.py` or `deployment.py` (introduced locally, reverted before commit) causes the per-module gate to fail. This is a manual verification step documented in the PR body — not a permanent test — confirming the mechanism wires through CI.
- [ ] `pyproject.toml` validates (`python -c "import tomllib; tomllib.loads(open('pyproject.toml').read())"`); the `test` CI job stays green; no other tests added.
- [ ] PR body lists the actual coverage percentages for `ci.py` and `deployment.py` at land time (per `High-level-impl.md §"Implementation-level risks" #5` — surface percentages early so S6-02's ratchet can't recover under-floor probes silently).

## Implementation outline

1. **Read the current `pyproject.toml`** to understand the existing coverage config shape (likely `[tool.pytest.ini_options]` with `addopts = "--cov=codegenie --cov-fail-under=85 --cov-branch ..."` and possibly `[tool.coverage.report]` with `fail_under = 85`).
2. **Choose the per-module mechanism.** Two options:
   - **`pytest-cov`'s per-file thresholds via `--cov-fail-under-file=...`** if the plugin version supports it (preferred — declarative, in `pyproject.toml`).
   - **`[tool.coverage.report]` `fail_under` is global only** — for per-file, use a custom check script invoked from the CI `test` job that parses `coverage.json` and applies the per-file floors.
   - If neither is clean, fall back to a tiny `scripts/check_coverage_carve_outs.py` invoked as a CI step. Document the mechanism in `pyproject.toml`'s comment.
3. **Declare the two carve-outs.** Example (with `pytest-cov`-style; adjust to actual plugin):
   ```toml
   # Per-module coverage carve-outs declared by ADR-0005.
   # Further carve-outs require a new ADR amending 0005.
   # The global --cov-fail-under floor (raised to 90 in S6-02) remains the default;
   # these two modules are explicitly relaxed to 85/75 because their branch shape
   # (one `if` per supported CI provider / deployment marker) makes the higher
   # floor gameable by branch-checkbox tests — see ADR-0005 §Tradeoffs.
   [tool.coverage.report]
   # global floor — set by S6-02 to 90; do not change here.
   [tool.coverage.paths.coverage_carve_outs_per_module]
   # 85/75 — see ADR-0005.
   # src/codegenie/probes/deployment.py
   # src/codegenie/probes/ci.py
   ```
   (The above is illustrative — adopt the actual `pytest-cov` / `coverage.py` config shape supported by the Phase 0 setup. The literal carve-out *declaration* is what matters; the syntax must follow what the `test` CI job enforces.)
4. **Run the local coverage report.** `pytest --cov=codegenie --cov-report=term-missing` after S4-01 and S4-02 land. Confirm both probes are ≥ 85% line / 75% branch. If below, **do not lower the carve-out** — go back to the failing probe's tests and add intent-verifying coverage. The carve-out is the floor; not the target.
5. **Update PR body** with the percentages and a note: "ci.py: 87% line / 78% branch — above carve-out floor. deployment.py: 86% line / 76% branch — above carve-out floor. Global gate ratchet to 90/80 in S6-02."
6. **Document the ADR-amendment workflow** in `docs/contributing.md` if it doesn't already cover coverage — but this is S6-03's territory. For S4-04, the inline comment in `pyproject.toml` is the contract.

## TDD plan — red / green / refactor

This story is **infrastructure configuration**, not behavior. There is no permanent unit test for `pyproject.toml`. The TDD shape is mechanism verification.

### Red — manual verification of the mechanism

Before declaring the carve-outs:

1. Locally introduce a single deliberately-untested branch in `src/codegenie/probes/ci.py` (e.g., `if False: return None  # noqa` — clearly marked as a sentinel).
2. Run the `test` CI command locally: `pytest --cov=codegenie --cov-fail-under=85 --cov-branch ...` (or whatever the Phase 0 invocation is).
3. Confirm the test job *passes* at 85/75 (no carve-out yet) — the sentinel reduces coverage but stays above the global floor.
4. Locally raise the global floor to 90/80 (simulating S6-02's future state). Confirm the test job *fails* — `ci.py` is now below the global floor.
5. Add the per-module carve-out at 85/75 for `ci.py`. Confirm the test job *passes* again — the carve-out catches `ci.py`'s drop while the rest of the codebase respects 90/80.
6. Revert the sentinel + the simulated 90/80 floor; commit only the carve-out declarations.

### Green — declare the carve-outs

Apply the chosen mechanism in `pyproject.toml` per **Implementation outline** step 3. Run `pytest --cov ...` against the current S4-01 + S4-02 state and confirm the test job stays green.

### Refactor — clean up

- Re-read the inline comment. It must explicitly cite ADR-0005 by relative path and the "further carve-outs require ADR amendment" rule. If it doesn't, future contributors will lower the floor in a one-line PR.
- Confirm `pyproject.toml` still parses (`python -c "import tomllib; tomllib.loads(open('pyproject.toml').read())"`).
- Verify the `[tool.coverage.report]` and `[tool.pytest.ini_options]` sections are deduplicated — coverage-related config tends to drift across both; the source of truth is one location.
- No code in `src/` changes. No tests in `tests/` added or removed. The PR diff should be `pyproject.toml` plus the PR description.

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | Declare the two per-module carve-outs + the ADR-pointing comment; do **not** change the global floor |
| `scripts/check_coverage_carve_outs.py` (if mechanism requires) | New only if `pytest-cov` lacks built-in per-file thresholds; otherwise omit |

## Out of scope

- **Raising the global floor to 90/80** — S6-02's job. This story declares the *carve-outs*; the *ratchet* lands later.
- **Adding intent-verifying tests to `ci.py` or `deployment.py`** — those landed in S4-01 and S4-02. If coverage is below 85/75 at this story's land time, that's a regression of the prior stories — go back to them, do not relax the carve-out.
- **Carve-outs for any other module** — Phase 2 may add more; each requires a new ADR amending 0005. Do not preemptively carve out additional modules in this story.
- **`docs/contributing.md` documentation of the carve-out workflow** — S6-03's job per `High-level-impl.md §Step 6`.
- **Coverage on `cli.py`** — already excluded entirely in Phase 0 per ADR-0005 §Decision; not revisited.
- **Branch coverage tuning beyond 75% for the carve-outs** — the trade is line 85 / branch 75 *exactly*. Tightening either later requires an ADR amendment.

## Notes for the implementer

- **The carve-out is a floor, not a target.** If `ci.py` lands at 89% line coverage, that's good — leave it. The carve-out exists for the cases where the *honest* test surface for those modules tops out around 85%. If you find yourself writing a coverage-shaped test that asserts nothing meaningful just to clear the floor, stop — that's the exact Rule 9 violation the carve-out was designed to prevent.
- **Surface the percentages in the PR body** at S4-04 land time, not at S6-02. Per `High-level-impl.md §"Implementation-level risks" #5`: if either probe is at 84% / 73% when S6-02 tries to ratchet to 90/80 globally, the carve-out catches it — but only if the carve-out is in place first. Order matters: declare the carve-out (S4-04), then ratchet (S6-02).
- **Mechanism choice (`pytest-cov` per-file vs. a custom script)** is implementer's judgment. The acceptance criterion is *that the CI job enforces the per-module floors*, not which tool does it. Document the choice in the `pyproject.toml` comment so future contributors can find it.
- **ADR-0005 is the registry root** for coverage carve-outs in this project. A Phase 2 PR proposing a third carved-out module **must** file a new ADR amending 0005 — the inline `pyproject.toml` comment makes this visible. If you find a Phase 2 PR that simply adds a third line to the table without an ADR, push back: "where's the ADR amendment?"
- **`coverage.py` configuration drift** — the `[tool.coverage.report]` and `[tool.pytest.ini_options]` sections both control coverage behavior. Pick one as source of truth (typically `[tool.coverage.report]`); reference it from the other if needed. A PR that splits the config across both is the start of drift.
- **The red phase is manual.** No permanent test asserts the carve-outs work — the CI `test` job is the test. Trust the CI gate; verify locally once that the mechanism fires (see the **Red** sub-section above).
- **Do not weaken the global floor.** This story's PR diff is **additive** to `pyproject.toml`. If a reviewer suggests "let's just keep it at 85/75 globally," push back: the carve-outs only exist because the global is being raised to 90/80 in S6-02. The two stories are paired; the carve-outs without the ratchet are dead config; the ratchet without the carve-outs blocks merge.
- **Per Rule 12 (Fail loud)**: if the mechanism you choose silently passes when a per-module floor is breached, that's worse than not having carve-outs. Verify the mechanism *fails* CI when a module is below its declared floor — the manual red-phase test above is the verification.
- **Consider naming the per-module thresholds** with module names that survive renames. If `deployment.py` is renamed to `deployment_probe.py` in Phase 2, the carve-out must follow — surface this as a `CODEOWNERS` or a doc-string note so the rename PR catches it.
