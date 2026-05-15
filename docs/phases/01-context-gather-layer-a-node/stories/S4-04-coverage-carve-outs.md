# Story S4-04 — Coverage carve-outs declared in `pyproject.toml`

**Step:** Step 4 — Ship `CIProbe`, `DeploymentProbe`, and `TestInventoryProbe`
**Status:** Ready (HARDENED 2026-05-14)
**Effort:** S
**Depends on:** S4-01 (`CIProbe` on disk), S4-02 (`DeploymentProbe` on disk)
**ADRs honored:** **ADR-0005 (90/80 floor with 85/75 carve-out for `deployment.py` and `ci.py`)**

## Validation notes (2026-05-14)

Hardened by `phase-story-validator`. Verdict: **HARDENED**. Full report at [`_validation/S4-04-coverage-carve-outs.md`](_validation/S4-04-coverage-carve-outs.md). Headline changes:

- **CN-1 (block) — Stale `pyproject.toml` ratchet-plan comment.** Lines 175–177 currently say *"Phase 1 bumps to 87/77, Phase 2 to 90/80"*, which contradicts ADR-0005 (Phase 1's ratchet is 90/80 with 85/75 carve-outs; there is no 87/77 intermediate). New **AC-9** requires the comment be rewritten in this PR to match ADR-0005 — leaving the stale prose in the file the PR touches is Rule 7 (surface conflicts, don't average them) + Rule 12 (Fail loud) territory. The new comment must still say "global gate not raised in S4-04 — raised in S6-02"; it must not preemptively bake in 90/80.
- **CN-2 / CV-1 (block) — Mechanism reality pinned in ACs.** `coverage.py`'s `[tool.coverage.report] fail_under` is **global only**. `[tool.coverage.paths]` is path-aliasing, **not** thresholds. `pytest-cov` has no `--cov-fail-under-file` flag (the original story body suggested one — it doesn't exist). `[tool.coverage.report] exclude_also` (the phrasing in High-level-impl.md §Step 6) *excludes lines from coverage measurement entirely* — the **opposite** of declaring a per-module floor. The implementer must therefore choose **a custom check script** (preferred, ~30–50 LOC, reads `coverage.json`) **or** document a non-obvious mechanism actually supported by the installed `coverage.py` / `pytest-cov` versions. New **AC-1**, **AC-2**, and **AC-10** pin this explicitly.
- **TQ-1 / CN-3 (block) — Permanent automated test replaces manual red-phase.** ADR-0005 §Decision: *"CI fails if any module drops below its declared floor."* The original red phase was a manual local toggle reverted before commit — that leaves zero permanent signal guarding the mechanism. New **AC-6** + **AC-7** require a permanent test under `tests/unit/build/test_coverage_carve_outs.py` that (a) parses `pyproject.toml` and asserts the carve-out table contains exactly the two entries at exactly 85/75; (b) drives the chosen mechanism (custom script or otherwise) with a synthetic coverage report where `ci.py` is at 60% line / 50% branch and asserts non-zero exit + the offending module name in stderr.
- **CV-2 / CV-3 (harden) — PR-time runtime conditions lifted out of ACs.** AC-5 (original) bundled the "if below floor at land time, go fix the parent probe" rule into a coverage-claim AC. Split: AC-13 lists the percentages requirement; AC-14 codifies the "do not lower the carve-out; fix the parent probe" rule as a binary check the reviewer applies.
- **CV-5 (harden) — ADR-0005 comment must carry its rationale, not just a pointer.** New **AC-8** requires the inline comment to include the substantive reason (branch-shape gameability, Rule 9 trade) so the next reviewer doesn't have to chase the ADR cold. The story body already drafts this comment; AC-8 makes shipping that prose binding.
- **DP-1 (Notes-only)** — If a custom script is the mechanism, structure the script as a pure function over (`coverage.json`, carve-out map) reading the carve-out list as **data from `pyproject.toml`** (e.g., a `[tool.coverage_carve_outs]` table the script parses). With two carve-outs today this is a Rule 2 "borderline registry"; making the data-driven shape now buys Phase 2+ a one-entry config edit (still ADR-gated). Surfaced in *Notes for the implementer*, not as an AC.
- **DP-3 (Notes-only)** — Recommend naming carve-outs by **both** module-qualified name (`codegenie.probes.deployment`) **and** file path (`src/codegenie/probes/deployment.py`); a future rename PR then breaks the test in **AC-6**, surfacing the drift.

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

### Mechanism

- [ ] **AC-1 — Mechanism is data-driven and CI-enforced.** Per-module floors are declared as **data** (a `[tool.coverage_carve_outs]` TOML table, or equivalent declarative shape) and enforced by **either** (a) a tiny `scripts/check_coverage_carve_outs.py` invoked from the CI `test` job after the `pytest --cov` run, **or** (b) a native `coverage.py` / `pytest-cov` mechanism verified to exist *in the installed version's documentation* and demonstrated to fail CI for an under-floor module. The PR body must state which option was chosen and why. Native flags fabricated from memory (`--cov-fail-under-file`, `[tool.coverage.paths]` as a threshold map, `[tool.coverage.report] exclude_also` as a floor) are **NOT acceptable**: `exclude_also` removes lines from measurement entirely (the opposite of a floor); `[tool.coverage.paths]` is path-aliasing; `--cov-fail-under-file` does not exist.
- [ ] **AC-2 — The carve-out table contains exactly two entries.** `src/codegenie/probes/deployment.py` → line 85 / branch 75; `src/codegenie/probes/ci.py` → line 85 / branch 75. Both file path **and** module-qualified name (`codegenie.probes.deployment`, `codegenie.probes.ci`) are recorded, so a future rename of either file in Phase 2+ surfaces the drift via the test in AC-6.
- [ ] **AC-3 — Global floor unchanged in this story.** `--cov-fail-under` and any `[tool.coverage.report] fail_under` remain at the Phase 0 value (currently `85`). S6-02 raises the global; S4-04 does not. The PR diff must not modify the global value.

### Comments and ratchet-plan cleanup

- [ ] **AC-8 — Inline rationale comment (not just an ADR pointer).** `pyproject.toml` carries an inline comment adjacent to the carve-out table whose text includes **all three** of: (i) the literal phrase `ADR-0005`; (ii) the rationale phrase that `deployment.py` and `ci.py` have *structurally-narrow branches that make a higher floor gameable by branch-checkbox tests* (Rule 9); (iii) the literal phrase `Further carve-outs require a new ADR amending 0005.` A test parses the comment block and asserts all three substrings appear (see AC-6).
- [ ] **AC-9 — Stale ratchet-plan comment rewritten to match ADR-0005.** The current `pyproject.toml` block at the `[tool.pytest.ini_options]` `addopts` comment (lines 175–177 at story-write time) says *"Phase 1 bumps to 87/77, Phase 2 to 90/80"*. This contradicts ADR-0005 (Phase 1's ratchet is 90/80 with 85/75 carve-outs; no 87/77 intermediate exists). Rewrite the comment to say: *"`--cov-fail-under` is the Phase 0 global gate. Phase 1 (this phase) leaves the global unchanged in S4-04 and raises it to 90/80 in S6-02 with the 85/75 carve-outs declared below (ADR-0005). Do NOT raise ahead."* The replacement must not bake in 90/80 in this PR.

### Enforcement test (permanent, automated)

- [ ] **AC-6 — Permanent test pins the carve-out config.** `tests/unit/build/test_coverage_carve_outs.py` exists and asserts: (a) `pyproject.toml` parses with `tomllib`; (b) the carve-out table contains **exactly** the two entries from AC-2 at **exactly** 85 line / 75 branch (no other rows; not 86; not 84); (c) the inline comment from AC-8 contains all three substrings; (d) the global `--cov-fail-under` value still equals the Phase 0 value (per AC-3). Adding a third carve-out without an ADR amendment to 0005 fails this test.
- [ ] **AC-7 — Permanent test exercises the mechanism end-to-end with synthetic coverage.** The same test file (or a sibling) drives the chosen mechanism (custom script or otherwise) with a synthetic `coverage.json` (or `.coverage` equivalent) in which `src/codegenie/probes/ci.py` registers at 60% line / 50% branch and everything else is at 100%. The mechanism MUST exit non-zero and the failure output (stderr or report) MUST contain the literal substring `codegenie.probes.ci` (or `src/codegenie/probes/ci.py`). A symmetrical row covers `deployment.py`. This is the Rule 12 "fail loud" guarantee — it replaces the original manual red-phase step.
- [ ] **AC-10 — CI invokes the mechanism in the `test` job.** If the chosen mechanism is a custom script, the `test` job's step list (workflow file or Makefile target the job calls) names the script explicitly and runs it after `pytest --cov`. If the chosen mechanism is native to `coverage.py` / `pytest-cov`, no extra step is needed but the PR body cites the version-specific docs URL and the exact flag/config key. A grep test in `tests/unit/build/test_coverage_carve_outs.py` checks for the script invocation in the workflow file (skipped with explicit reason if native).

### Land-time conditions

- [ ] **AC-13 — PR body lists actual coverage percentages.** PR body lists the line/branch percentages for `probes/ci.py` and `probes/deployment.py` at land time (e.g., `ci.py: 87% line / 78% branch`). Per `High-level-impl.md §"Implementation-level risks" #5`: surfacing percentages early so S6-02's ratchet cannot recover under-floor probes silently.
- [ ] **AC-14 — If a probe is below its carve-out floor at land time, this PR does not merge.** Instead, the parent probe's S4-01 or S4-02 PR is reopened and intent-verifying tests are added there. The carve-out is a **floor**, not a **target**. The S4-04 PR description must explicitly confirm both modules are at or above 85/75 (a one-line check, blocking merge).

### Hygiene

- [ ] **AC-11 — `pyproject.toml` parses.** `python -c "import tomllib; tomllib.loads(open('pyproject.toml','rb').read())"` exits 0. (Note: `tomllib.loads` takes `str` in 3.11 but the file should be opened binary for `tomllib.load`; either form is acceptable provided the assertion holds.)
- [ ] **AC-12 — No other tests added or removed; no `src/` changes.** PR diff is: `pyproject.toml`, the new `tests/unit/build/test_coverage_carve_outs.py`, and (if chosen) `scripts/check_coverage_carve_outs.py` plus any CI workflow edit naming it. Nothing else.

## Implementation outline

1. **Read the current `pyproject.toml`** to understand the existing coverage config shape. At story-write time: `[tool.pytest.ini_options]` `addopts = "-ra --strict-markers -m \"not bench\" --cov=src/codegenie --cov-branch --cov-fail-under=85"`; `[tool.coverage.run] branch = true`; `[tool.coverage.report] omit = ["src/codegenie/cli.py"]`. **No `fail_under` is currently set in `[tool.coverage.report]`** — the global is enforced via `--cov-fail-under=85` on the pytest CLI.
2. **Audit the stale ratchet-plan comment (AC-9).** The comment block at lines ~175–177 says *"Phase 1 bumps to 87/77, Phase 2 to 90/80"*. This is wrong per ADR-0005. Replace it now (in this PR) with the AC-9 text.
3. **Pick the mechanism (AC-1) — almost certainly a custom script.** `coverage.py`'s `[tool.coverage.report] fail_under` is **global only**; `pytest-cov` has no `--cov-fail-under-file` flag; `[tool.coverage.report] exclude_also` *removes lines from measurement entirely* — the opposite of declaring a floor. The high-confidence path is a 30–50 LOC `scripts/check_coverage_carve_outs.py` that reads the carve-out list from `pyproject.toml`, runs against `coverage.json` (generated by `--cov-report=json`), and exits non-zero with `codegenie.probes.<module>: <line>%/<branch>% < <floor_line>/<floor_branch>` on stderr for any under-floor module. Before settling on the script, briefly verify nothing has shipped in `coverage.py >= 7.x` or `pytest-cov` that obsoletes it — if so, prefer the native flag and cite the doc URL in the PR body.
4. **Add the carve-out table as data (`[tool.coverage_carve_outs]`)** — a declarative table the script reads. Sketch:
   ```toml
   # Per-module coverage carve-outs declared by ADR-0005. The two modules below
   # have structurally-narrow branches (one `if` per supported CI provider /
   # deployment marker) that make the higher 90/80 floor gameable by branch-
   # checkbox tests asserting nothing meaningful — see ADR-0005 §Tradeoffs and
   # Rule 9 ("Tests verify intent, not just behavior"). The global gate is NOT
   # raised in S4-04; S6-02 raises it to 90/80 with these carve-outs already in
   # place. Further carve-outs require a new ADR amending 0005.
   [[tool.coverage_carve_outs]]
   path = "src/codegenie/probes/deployment.py"
   module = "codegenie.probes.deployment"
   line = 85
   branch = 75
   adr = "phase-01/ADR-0005"

   [[tool.coverage_carve_outs]]
   path = "src/codegenie/probes/ci.py"
   module = "codegenie.probes.ci"
   line = 85
   branch = 75
   adr = "phase-01/ADR-0005"
   ```
   The literal TOML shape is the implementer's call provided AC-2 holds. Keep the table machine-parseable; the test in AC-6 reads it via `tomllib`.
5. **Write `scripts/check_coverage_carve_outs.py`** if the mechanism is the script. Shape (pure function over inputs, no globals):
   ```python
   def check(coverage_data: dict, carve_outs: list[CarveOut]) -> list[str]:
       """Return a list of violation strings; empty list means pass."""
   ```
   Wire `main()` as imperative shell: read `coverage.json` and `pyproject.toml`, call `check`, print violations to stderr, exit non-zero on any. Keep ≤ 50 LOC.
6. **Write `tests/unit/build/test_coverage_carve_outs.py`** covering AC-6, AC-7, and AC-10. Drive `check()` directly with synthetic data — do not invoke the script as a subprocess for the violation-shape assertion; reserve the subprocess exec for one CLI-shape smoke test confirming non-zero exit.
7. **Run the real coverage locally** after S4-01 and S4-02 are merged: `pytest --cov=src/codegenie --cov-branch --cov-report=json --cov-report=term-missing`. Confirm both probes are ≥ 85 line / 75 branch. If below, **do not lower the carve-out** (AC-14) — reopen the parent probe's PR and add intent-verifying tests there.
8. **Update the CI workflow (AC-10)** if a script is used: add a step after `pytest` that invokes `python scripts/check_coverage_carve_outs.py`. The grep test in AC-10 enforces the wiring.
9. **PR body** lists percentages (AC-13) and explicitly confirms both modules are at or above floor (AC-14).
10. **Do NOT** document the ADR-amendment workflow in `docs/contributing.md` here — that is S6-03's territory. The inline comment in `pyproject.toml` (AC-8) is the contract for S4-04.

## TDD plan — red / green / refactor

This story is **infrastructure configuration plus a tiny enforcement script**. Per the validator's TQ-1 finding, the original manual red-phase has been replaced with a **permanent automated test** under `tests/unit/build/test_coverage_carve_outs.py` so that the mechanism is guarded in CI rather than verified once and forgotten (Rule 12 — Fail loud).

### Red — write the failing tests first

Create `tests/unit/build/test_coverage_carve_outs.py` with these tests (all initially failing because the script + the TOML table don't exist yet):

1. **`test_pyproject_parses`** — `tomllib.load(open('pyproject.toml','rb'))` succeeds. (Sanity. Will pass without any change.)
2. **`test_carve_out_table_has_exactly_two_entries`** — Reads `[tool.coverage_carve_outs]` (or the chosen TOML shape), asserts `len(table) == 2`, asserts the two entries have `path` ∈ {`src/codegenie/probes/deployment.py`, `src/codegenie/probes/ci.py`}, each with `line == 85` and `branch == 75`, each with `module` ∈ {`codegenie.probes.deployment`, `codegenie.probes.ci`}. (AC-2.) **Fails: table doesn't exist yet.**
3. **`test_inline_rationale_comment_present`** — Reads `pyproject.toml` as text, asserts the comment block adjacent to the carve-out table contains all three substrings: `ADR-0005`, the rationale phrase (test for any of: `branch-shape`, `gameable`, `branch-checkbox`), and the literal `Further carve-outs require a new ADR amending 0005.` (AC-8.) **Fails: comment absent.**
4. **`test_stale_ratchet_plan_comment_removed`** — Asserts the literal substring `87/77` does NOT appear anywhere in `pyproject.toml`. (AC-9.) **Fails: substring currently present at lines ~175–177.**
5. **`test_global_floor_unchanged`** — Asserts `--cov-fail-under=85` is still present in the `[tool.pytest.ini_options]` `addopts` string AND no `fail_under` key has appeared in `[tool.coverage.report]`. (AC-3.) **Passes initially; guards against accidental ratchet.**
6. **`test_check_function_flags_under_floor_ci_py`** — Imports `check()` from `scripts.check_coverage_carve_outs`, feeds it a synthetic coverage dict where `src/codegenie/probes/ci.py` is at 60% line / 50% branch and everything else at 100%, asserts the returned violation list is non-empty AND the violation string contains `codegenie.probes.ci` (or `src/codegenie/probes/ci.py`). (AC-7, half 1.) **Fails: script doesn't exist.**
7. **`test_check_function_flags_under_floor_deployment_py`** — Symmetrical row for `deployment.py`. (AC-7, half 2.) **Fails: script doesn't exist.**
8. **`test_check_function_passes_when_all_at_floor`** — Feeds `check()` a coverage dict where both carve-out modules are at exactly 85/75 and everything else at 100%. Asserts the violation list is empty. **Fails: script doesn't exist.** *(Guards against off-by-one: `>= 85` not `> 85`.)*
9. **`test_check_function_passes_when_above_floor`** — All probes at 100%. Empty violations. (Sanity; cheap; catches an inverted-comparison regression.) **Fails: script doesn't exist.**
10. **`test_script_smoke_exits_nonzero_on_violation`** — Runs `python scripts/check_coverage_carve_outs.py` as a subprocess with a synthetic `coverage.json` in a `tmp_path`. Asserts exit code != 0 AND stderr contains `codegenie.probes.ci`. (AC-7, end-to-end CLI shape; one subprocess test is enough.) **Fails: script doesn't exist.**
11. **`test_ci_workflow_invokes_script`** — Reads the CI workflow file (e.g., `.github/workflows/ci.yml` or the Makefile target the `test` job uses), asserts a step contains the literal `check_coverage_carve_outs.py`. If the mechanism turned out to be native (no script), `pytest.skip("native mechanism — see PR body for docs URL")` with the skip reason recorded. (AC-10.) **Fails: workflow has no such step yet.**

(Skipping fixture for the per-module pyproject-rename guard: AC-2's `module` field is the rename guard already; if `deployment.py` is renamed without updating the module-qualified name, AC-7's synthetic-coverage test fails because the script can't locate the file.)

### Green — minimal changes to flip the bar to green

1. Update `pyproject.toml`: (a) rewrite the stale ratchet-plan comment (AC-9, satisfies test 4); (b) add the `[tool.coverage_carve_outs]` table with the two entries (AC-2, satisfies test 2); (c) write the inline rationale comment containing the three substrings (AC-8, satisfies test 3); (d) confirm `--cov-fail-under=85` is unchanged (AC-3, test 5 stays green).
2. Write `scripts/check_coverage_carve_outs.py` with the `check()` pure-function plus a small `main()` imperative shell (satisfies tests 6–10).
3. Update the CI workflow / Makefile to invoke the script after `pytest --cov` (satisfies test 11).
4. Run `pytest tests/unit/build/test_coverage_carve_outs.py` — all green.
5. Run the full `pytest --cov=src/codegenie --cov-branch --cov-report=json` plus `python scripts/check_coverage_carve_outs.py coverage.json` against the merged S4-01 + S4-02 state. Both probes must be at or above 85/75 (AC-14).

### Refactor — clean up

- Re-read the inline rationale comment (AC-8). Confirm all three required substrings are present and the phrasing is reviewer-comprehensible without chasing ADR-0005.
- Confirm the stale `87/77` substring is gone everywhere (`grep -n "87/77" pyproject.toml` returns nothing).
- Confirm `pyproject.toml` still parses (`python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"` exits 0).
- Verify `[tool.coverage.report]`, `[tool.pytest.ini_options]`, and `[tool.coverage_carve_outs]` are not duplicated — coverage-related config tends to drift across the first two; the new third table is single-purpose.
- Confirm `check()` is a **pure function** (no `open`, no `os.environ`, no `print`). The `main()` shell does the I/O.
- Confirm the script is ≤ 50 LOC (excluding the docstring and the `if __name__ == "__main__":` block).
- PR diff is exactly: `pyproject.toml`, `scripts/check_coverage_carve_outs.py` (if chosen), `tests/unit/build/test_coverage_carve_outs.py`, and (if needed) the CI workflow / Makefile entry. Nothing in `src/`; no other test files changed.

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | (a) Add `[tool.coverage_carve_outs]` table with the two entries (AC-2); (b) write inline rationale comment with all three required substrings (AC-8); (c) rewrite the stale `87/77` ratchet-plan comment to match ADR-0005 (AC-9); (d) leave global `--cov-fail-under` unchanged (AC-3) |
| `scripts/check_coverage_carve_outs.py` | Pure `check(coverage_data, carve_outs) -> list[str]` plus a small CLI shell; ≤ 50 LOC. **Almost certainly required** — `coverage.py` and `pytest-cov` have no native per-module floor mechanism (AC-1). Omit only if a native mechanism is found and verified |
| `tests/unit/build/test_coverage_carve_outs.py` | New permanent test covering AC-6, AC-7, AC-10. Drives `check()` directly with synthetic coverage data; one subprocess smoke test for the CLI shape |
| CI workflow file (e.g., `.github/workflows/ci.yml`) **or** Makefile `test` target | Add a step naming `scripts/check_coverage_carve_outs.py` after `pytest --cov` (AC-10). Skip only if a native mechanism is used (record decision in PR body) |

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
- **Consider naming the per-module thresholds** with module names that survive renames. If `deployment.py` is renamed to `deployment_probe.py` in Phase 2, the carve-out must follow — AC-2 requires both the file path **and** the dotted module name be recorded, so the AC-7 synthetic-coverage test fails immediately on a half-applied rename. Surface the rename obligation in a doc-string note inside `scripts/check_coverage_carve_outs.py` and (optionally) as a `CODEOWNERS` entry.
- **Data-driven registry, not inlined constants (DP-1 — surfaced by validator, not an AC).** Even though there are only two carve-outs today (Rule 2 — Simplicity First — applies; we are *not* introducing a registry abstraction speculatively), the implementation already crosses one threshold worth recognising: the carve-out list is **read by a script** and **read by a test**. Putting the list in `pyproject.toml` as a TOML table — rather than hardcoding the same two entries in three places (`pyproject.toml` config, the script's constants, and the test) — eliminates the drift class where a future PR updates one site and forgets another. Phase 2+ adding a third carve-out (still ADR-gated by ADR-0005) is then a one-row TOML edit. Open/Closed at the config-file boundary, without inventing a Python registry class.
- **`check()` is pure; `main()` is the imperative shell (DP-2 — surfaced by validator, not an AC).** Keep `check(coverage_data: dict, carve_outs: list[CarveOut]) -> list[str]` free of `open`, `os.environ`, `print`, and `sys.exit`. All I/O lives in `main()`. The TDD plan tests `check()` directly with synthetic dicts; the subprocess smoke test exercises `main()` once. This is the same functional-core / imperative-shell discipline the probes use; the script is small enough that the seam costs nothing.
- **Don't elevate the registry into a `parsers/_carve_outs.py` kernel.** With two consumers (the script and one test file), the Rule of Three is not met; the in-script `CarveOut` `NamedTuple` is enough. If Phase 2 adds a third consumer (e.g., a `make coverage` target reading the same table), revisit.
