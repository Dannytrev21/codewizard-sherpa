# Validation report: S7-08 — Final `kernel-frozen` verification

**Validated:** 2026-05-24
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S7-08 is the Phase-4 Step-7 merge gate: at branch completion it runs the
shipped `tests/fence/test_kernel_frozen.py` (Phase-3 S1-05), the path-scoped
`tests/fence/test_pyproject_fence_phase4.py` (S1-05), the property test
`tests/property/test_plan_outcome_no_recipe_outcome_widening.py` (S1-03), and a
**new** path-allow-list diff-walker (`tests/fence/test_phase4_diff_within_allow_list.py`)
to prove the Phase-4 branch's footprint stays inside the kernel-frozen contract
(arch §G3 + ADR-0004 + ADR-0003 + production ADR-0031).

The story's **goal is correct** — it's the Step-7 verification gate, and the
arch / ADRs all call for it. But the body has multiple block-class drifts
against shipped code plus several mutation-resistance gaps that would let a
sneaky kernel edit slip past the very gate this story exists to enforce:

1. **`src/codegenie/orchestrator/` does not exist** in the shipped tree
   (`RemediationOrchestrator` is named in arch but not yet built). The AC
   `git diff master -- src/codegenie/orchestrator/` returns empty
   **vacuously** — the guard fires only on a path that can't exist. The
   `Plugin` / `RecipeEngine` / `Transform` pin must be against actual shipped
   files: `src/codegenie/plugins/protocols.py:69`,
   `src/codegenie/transforms/recipe_engine.py:67`,
   `src/codegenie/transforms/transform.py:64`.
2. **`git diff master -- src/codegenie/transforms/` would always be non-empty**
   — Phase 3 shipped `transforms/{engines,policy,sandbox}/` and many files
   under that tree (`bundle.py`, `cache.py`, `sandbox_path.py`, etc.). The
   intent is "the `Transform` ABC must not be edited," and the ABC lives in
   exactly one file (`transform.py`); the same applies to the `RecipeEngine`
   Protocol (one file: `recipe_engine.py`). The story's directory-scope diff
   inverts the failure mode: anything touched under `transforms/` would
   trip the assertion in normal Phase-4 work even though the ABC is untouched.
3. **Bash syntax bug** in the prescribed TDD test: `git diff -- "{base}..HEAD" -- {f}`
   is invalid (double `--`). The correct form is
   `git diff "{base}..HEAD" -- {f}`. The story's own prescribed test would
   raise on first run.
4. **AC bucket-list and TDD `ALLOWED_EXACT` disagree.** TDD plan includes
   `uv.lock`; the AC bucket list does not. Either both or neither — the
   discrepancy guarantees a violation message (or silent miss) depending on
   which side the executor reads first.
5. **Missing dependencies.** The story's first three ACs invoke companion
   tests shipped by S1-03 (`test_plan_outcome_no_recipe_outcome_widening.py`)
   and S1-05 (`test_pyproject_fence_phase4.py`), but `Depends on:` lists
   only S7-01 and S1-07. S1-07 is itself **RESCUE** (see
   `_validation/S1-07-test-kernel-frozen.md`) — the Phase-3 baseline row
   it should have pinned was never landed. The story must surface that
   dependency chain explicitly (Global Rule 12: fail loud about what isn't
   done yet) and treat it as BLOCKED-PARTIAL on S1-07.
6. **Recursive pytest invocation.** `test_companion_property_test_still_green`
   spawns a separate pytest subprocess to assert another test passes — flaky
   (PATH/venv-dependent), slow, and redundant with the property test running
   normally in the suite. Drop it; AC-2 already covers the property test.
7. **Mutation-resistance holes.** If a contributor set
   `ALLOWED_PREFIXES = ("",)` or `("/",)` every path would be "inside the
   allow-list" — the live diff test would pass vacuously. There's also no
   planted-violation unit test, so a contributor refactoring the diff-walk
   wouldn't notice the classifier had become a no-op. The fix is to extract
   a pure `_classify(path, prefixes, exact) -> bool` helper and table-test
   it (planted violators flagged, planted non-violators not flagged) plus
   an invariant test (every prefix is non-empty and rooted).
8. **Run-on-master `assert paths` failure.** On `master` itself, the merge-base
   diff is empty — the test would error rather than no-op. Should skip with a
   structured `pytest.skip` when the diff is empty and HEAD == master, fail
   loud otherwise (Rule 12).
9. **Forbidden-paths assertion list is narrower than Goal G3.** G3 names
   `src/codegenie/{probes,coordinator,cache,output,schema}/` plus four
   protocols/ABCs. The story's `test_phase_3_kernel_files_unmodified` covers
   only 4 of those — every other kernel-scope directory is unguarded.

All nine are in-place-fixable. Two critic lenses (Coverage + Consistency) were
the load-bearing ones; Test-Quality and Design-Patterns concur and were
applied inline (the four-critic-subagent pattern would re-read the same files
in parallel without context-window protection benefit — global Rule 6).

Verdict: **HARDENED**. Twelve edits applied across the story header,
References, Depends-on, ACs, TDD plan, and Notes for the implementer. The
Status flips from `Ready` to `HARDENED` with a `BLOCKED-PARTIAL on S1-07`
qualifier so `phase-story-executor` knows to surface the S1-07 chain before
running.

## Method note

Stage 1 loaded: the story, `phase-arch-design.md §G3 + §CI gates + §Gap 5`,
`ADR-0003`, `ADR-0004`, `production/adrs/0031-plugin-architecture.md`,
`tests/fence/test_kernel_frozen.py` (full read), the prior
`_validation/S1-07-test-kernel-frozen.md` RESCUE report, and a directory
listing of `src/codegenie/{orchestrator,transforms,plugins}/`. Open ambiguity
surfaced inline: the story's pinning of `src/codegenie/orchestrator/`
references a path that does not exist in the shipped tree (no `orchestrator`
package under `src/codegenie/`). Resolution: pin the four real shipped paths
that own the contract (`plugins/protocols.py`, `transforms/transform.py`,
`transforms/recipe_engine.py`, `plugins/registry.py` — the `Plugin` /
`Transform` / `RecipeEngine` / registry-kernel files).

Stage 3 (Researcher) was not invoked — no finding required canonical-pattern
research beyond reading shipped code.

## Findings by critic

### Consistency critic

#### F1 — `src/codegenie/orchestrator/` does not exist in the shipped tree
- **Severity:** block
- **Smell:** Stale references / Vacuous assertion
- **What's wrong:** AC `git diff master -- src/codegenie/orchestrator/` returns
  empty on every run because the directory doesn't exist (`ls
  src/codegenie/orchestrator` → no such file). The guard is a no-op. Arch
  references `RemediationOrchestrator` as a forward-looking name but Phase 3
  did not ship that package — Phase-3 orchestration lives under
  `plugins/registry.py`, `plugins/loader.py`, `transforms/transform_registry.py`,
  and per-plugin `subgraph/` modules. The story's pin guards a path the test
  cannot ever fail on.
- **Proposed fix:** Replace the orchestrator pin with explicit-file pins
  against the four shipped kernel contract files: `src/codegenie/plugins/protocols.py`,
  `src/codegenie/plugins/registry.py`, `src/codegenie/transforms/recipe_engine.py`,
  `src/codegenie/transforms/transform.py`.
- **Confidence:** high
- **Source:** `ls src/codegenie/` (no `orchestrator/`); `grep -r "class
  RemediationOrchestrator" src/` (no match); `grep -n "class Plugin\|class
  Transform\|class RecipeEngine" src/codegenie/{plugins,transforms}/` (located
  the four shipped contract files).

#### F2 — `git diff master -- src/codegenie/transforms/` over-scopes
- **Severity:** block
- **Smell:** Directory-scope pin inverts intent
- **What's wrong:** The intent (arch §G3) is "the `Transform` ABC must not be
  edited." The ABC lives in **one file**: `src/codegenie/transforms/transform.py:64`.
  The directory `src/codegenie/transforms/` also contains `engines/`,
  `policy/`, `sandbox/`, `bundle.py`, `cache.py`, `transform_registry.py`,
  `outcomes.py`, `repo_context.py`, `report.py`, `signal_kinds.py`, etc. — most
  of which legitimately evolve in normal Phase-3/4 plugin work. A
  directory-scope `git diff` would *always* be non-empty on a real Phase-4
  branch and the AC would fire on every run.
- **Proposed fix:** Pin the ABC file specifically: `src/codegenie/transforms/transform.py`.
  Apply the same fix for `RecipeEngine` (one file: `recipe_engine.py`).
- **Confidence:** high
- **Source:** `ls src/codegenie/transforms/` (24 entries, many legitimately
  evolving); `grep -n "class Transform" src/codegenie/transforms/transform.py`
  (line 64 — the ABC).

#### F3 — `Depends on` undercount; S1-07 chain not surfaced
- **Severity:** block
- **Smell:** Hidden precondition
- **What's wrong:** AC-2/AC-3 invoke `test_plan_outcome_no_recipe_outcome_widening.py`
  (S1-03 deliverable) and `test_pyproject_fence_phase4.py` (S1-05
  deliverable). Neither is in `Depends on:`. Worse: AC-1 invokes
  `test_kernel_frozen.py` and *expects* the Phase-3 baseline row to be present
  (so the Phase-3 kernel state is actually being checked) — but the Phase-3
  baseline row is the S1-07 deliverable, and S1-07 is **RESCUE**. The story
  is a downstream consumer of an unrescued story; executor needs to know.
- **Proposed fix:** Add S1-03 and S1-05 to `Depends on:`. Add an explicit
  `BLOCKED-PARTIAL on S1-07` qualifier in the Status line with a one-line
  routing note: "Re-author S1-07 first (or accept that AC-1 will run against
  the phase-2 baseline only — flag in attempt log as known-deferred
  coverage)."
- **Confidence:** high
- **Source:** S1-03 / S1-05 / S1-07 story headers; this story's AC-1 / AC-2 /
  AC-3 wording; `_validation/S1-07-test-kernel-frozen.md` (RESCUE verdict).

#### F4 — `git diff` syntax bug in TDD plan
- **Severity:** block
- **Smell:** Test-as-written-would-not-run
- **What's wrong:** `subprocess.check_output(["git", "diff", "--", f"{base}..HEAD", "--", f], ...)`
  has two `--` separators. The first `--` terminates option parsing; git then
  treats `{base}..HEAD` as a pathspec, not a revision range. The second `--`
  is unexpected. Correct invocation: `["git", "diff", f"{base}..HEAD", "--", f]`
  (revision range, then `--`, then pathspec).
- **Proposed fix:** Remove the first `--`; keep the post-revspec one.
- **Confidence:** high
- **Source:** `git diff --help` rev/pathspec separator rules; quick
  reproduction at the shell.

#### F5 — AC bucket-list vs TDD `ALLOWED_EXACT` disagree
- **Severity:** block
- **Smell:** Internal inconsistency
- **What's wrong:** TDD `ALLOWED_EXACT` includes `uv.lock`; AC bucket-list
  does not. ADR-0003 §Decision references `.importlinter` as a complementary
  enforcement surface that grows in Phase 4 (path-scoped contracts); neither
  list includes it. `.github/workflows/ci.yml` is mentioned in S1-05 F8
  (the `fence` job needs a wiring update to run the new path-scoped fence)
  but absent from both lists. The executor reading either side reaches a
  different answer.
- **Proposed fix:** Reconcile: AC bucket list and the TDD constants must
  enumerate the **same** set. Final allow-list (from intersection +
  ADR-0003 + S1-05 attempt evidence):
  - Prefixes: `src/codegenie/fallback/`, `src/codegenie/rag/`,
    `plugins/vulnerability-remediation--node--npm/`, `tests/`,
    `docs/phases/04-vuln-llm-fallback-rag/`
  - Exact: `pyproject.toml`, `uv.lock`, `Makefile`, `CODEOWNERS`,
    `.codeowners`, `.importlinter`, `.github/workflows/ci.yml`,
    `docs/operations/secrets.md`, `docs/operations/cassettes.md`,
    `docs/operations/embeddings.md`.
- **Confidence:** high
- **Source:** story body AC #6 vs TDD code block lines 102–119; ADR-0003
  §Decision (path-scoped fence + `.importlinter` belt-and-suspenders);
  `_validation/S1-05-path-scoped-fence-amendment.md` F8 (CI wiring).

#### F6 — Forbidden-paths assertion list narrower than Goal G3
- **Severity:** harden
- **Smell:** AC-to-goal undercoverage
- **What's wrong:** Arch §G3 names **eight** untouchable surfaces (5 dirs +
  3 contract files). The story's `test_phase_3_kernel_files_unmodified`
  lists 4 (the broken `orchestrator/orchestrator.py`, the broken
  `transforms/` dir, `plugins/protocols.py`, the Phase-0 fence file). A
  silent edit to `src/codegenie/probes/`, `coordinator/`, `cache/`,
  `output/`, or `schema/` would not be caught by this test (though it
  *would* be caught by the underlying `test_kernel_frozen.py` baseline-SHA
  fence, once S1-07's phase-3 row is pinned — circular).
- **Proposed fix:** Expand the test's forbidden-path list to match G3:
  `src/codegenie/{probes,coordinator,cache,output,schema}/` (directory
  globs via `git diff --name-only` filter) + the three contract files
  (`plugins/protocols.py`, `transforms/recipe_engine.py`,
  `transforms/transform.py`) + the Phase-0 fence file. Use a `Final` tuple
  so adding new forbidden paths is a one-row append.
- **Confidence:** high
- **Source:** `phase-arch-design.md §G3` (8 surfaces); story TDD block
  (4 surfaces).

### Test-Quality critic

#### F7 — `test_companion_property_test_still_green` is fragile and redundant
- **Severity:** harden
- **Smell:** Spawned-pytest-from-pytest / Indirect assertion
- **What's wrong:** Spawning `pytest -q tests/property/test_plan_outcome_no_recipe_outcome_widening.py`
  as a subprocess is PATH-dependent, venv-dependent, slow, and re-runs a test
  that already runs in the same `make check` invocation that runs *this*
  test. If the property test is broken, `make check` already fails — there's
  no additional signal in re-asserting it from within another test.
- **Proposed fix:** Delete the test. AC-2 ("`test_plan_outcome_no_recipe_outcome_widening.py`
  runs green") is already discharged by the normal pytest run.
- **Confidence:** high
- **Source:** prescribed test code in story TDD plan; pytest best practice
  (no recursive pytest).

#### F8 — Vacuous-allow-list mutation guard missing
- **Severity:** harden
- **Smell:** Defeated-by-empty-string / No mutation test
- **What's wrong:** If `ALLOWED_PREFIXES = ("",)` (an empty string in the
  tuple), every path satisfies `p.startswith("")` and the entire gate
  silently passes. There is no test asserting `all(p and p != "/" for p in
  ALLOWED_PREFIXES)`. A contributor "cleaning up" the constants and
  accidentally leaving an empty entry would silently disable the fence.
- **Proposed fix:** Add a `test_allowed_prefixes_are_non_empty_and_rooted`
  case that asserts every entry is non-empty, starts with a path-shaped
  prefix (not `/`), and ends with `/`. Mirror for `ALLOWED_EXACT` (every
  entry non-empty + matches a real-file-shape pattern).
- **Confidence:** high

#### F9 — Planted-violation unit test missing
- **Severity:** harden
- **Smell:** Tests verify behavior, not intent (Rule 9)
- **What's wrong:** The live `test_every_diff_path_inside_allow_list` only
  fires when the branch *happens* to have a violation. A refactor that
  silently breaks the classifier (e.g., `return True` early-exit) would not
  be caught by any test on a clean branch. Rule 9: "every test must encode
  WHY the behavior matters."
- **Proposed fix:** Extract a pure `_classify(path: str, prefixes:
  Sequence[str], exact: frozenset[str]) -> bool` helper. Table-test it with
  planted violators (`src/codegenie/probes/_dummy.py`,
  `src/codegenie/coordinator/_dummy.py`,
  `src/codegenie/schema/repo_context.schema.json`) flagged as outside, and
  planted non-violators (`src/codegenie/fallback/x.py`,
  `tests/unit/x.py`, `pyproject.toml`) flagged as inside.
- **Confidence:** high

#### F10 — `assert paths` on master errors instead of skipping
- **Severity:** harden
- **Smell:** Wrong failure mode for the no-op case
- **What's wrong:** On `master`, `git merge-base master HEAD` = `HEAD`,
  so the diff is empty. The test errors with "no diff from master;
  nothing to verify" — a *failure* state, even though running on master is
  the trivial-no-op case. CI on `master` would go red without any actual
  kernel-frozen violation.
- **Proposed fix:** Detect the empty-diff-on-master case and `pytest.skip`
  with a structured reason (`"running on master/empty-diff branch; nothing
  to gate"`). Keep the loud failure for the genuinely-pathological case
  (HEAD detached, no merge-base resolvable). This is Rule 12 done correctly:
  fail loud on real violations, skip silently only on the trivially-correct
  no-op case, never silently pass on a real violation.
- **Confidence:** high

#### F11 — Docstring-update AC is unverifiable as written
- **Severity:** harden
- **Smell:** Manual AC dressed as automated
- **What's wrong:** "`test_kernel_frozen.py`'s module docstring is updated
  with a one-line as-merged confirmation at the bottom" has no test — a
  reviewer must manually grep. Either make it verifiable (an AST/regex
  test for the line shape) or demote it to a Notes paragraph (Rule 9: ACs
  must be observable).
- **Proposed fix:** Demote to Notes for the implementer; keep the
  prescribed shape but note it as a manual hygiene step the implementer
  performs as part of the merge commit. (Tightening it to a regex test
  would over-engineer for a one-off docstring line; Rule 2 wins.)
- **Confidence:** medium

### Design-Patterns critic

#### F12 — Functional core / imperative shell split for the classifier
- **Severity:** harden
- **Smell:** Pure-impure tangle
- **What's wrong:** As written, the live test mixes the impure
  `_phase4_diff_paths` (subprocess) with the pure classification logic
  inline. The pure logic can't be unit-tested without mocking subprocess.
  CLAUDE.md "Functional core / imperative shell" load-bearing commitment
  applies.
- **Proposed fix:** Extract `_classify(path, prefixes, exact) -> bool` as
  a pure module-level helper. The live test plumbs subprocess output into
  it; F9's planted-violation unit tests call it directly. Same fix
  discharges F8/F9 simultaneously.
- **Confidence:** high

#### F13 — Optional `_kernel_allow_list.py` extraction is premature
- **Severity:** nit
- **Smell:** Speculative abstraction (Rule 2 violation hint)
- **What's wrong:** The story's refactor step suggests extracting
  `tests/fence/_kernel_allow_list.py` "if Phase 7 wants to reuse." That's a
  speculative future consumer — Phase 7 isn't designed yet, and Rule 2
  ("three similar lines is better than a premature abstraction") + Rule of
  Three say: wait for the third consumer.
- **Proposed fix:** Demote to Notes for the implementer: "Phase 7 will
  likely want a sibling allow-list file; if so, extract a shared module at
  *that* time (rule of three). Do not extract in this story."
- **Confidence:** high

### Coverage critic (inline — concurrent with above)

#### F14 — Failure message must include bucket-classification map
- **Severity:** harden
- **What's wrong:** The Notes for implementer mentions "story-attempt log
  records the diff-walk output (path list + bucket assignment)" — but the
  failure message itself only emits the violator list. A reviewer reading
  CI output can't immediately tell which paths *did* fit a bucket. The
  Phase-3 fence (`test_kernel_frozen.py`) names baseline file + ADR in the
  failure message; mirror that pattern (Rule 11 — match existing
  conventions).
- **Proposed fix:** Failure message includes (a) violators, (b) the
  ADR-amendment escape hatch wording ("either fit a bucket via ADR-0003
  amendment or revert"), and (c) a hint that the full bucket-classification
  map for non-violators is at `/tmp/phase4-diff-paths.txt`.

### Coverage strengths recorded

- Goal traces cleanly to arch §G3 + ADR-0004 + ADR-0003 + production ADR-0031.
- Three failure modes named in Context cover the realistic attack surface
  (silent edits to `protocols.py`, fence widening, ABC edits).
- Out-of-scope is real and specific (Phase 7 mirror; tightening proposed-not-applied;
  S7-09 adversarial corpus).
- The Notes for the implementer's "do not silently widen the allow-list"
  is correctly framed as Rule-12 territory — kept verbatim.

## Research briefs

None — no finding required canonical-pattern research; all resolutions came
from reading shipped code and prior validation history.

## Conflict resolutions

- **F2 vs F6.** F2 (don't directory-scope `transforms/`) and F6 (G3 says
  to guard `transforms/` per arch) appear to conflict. Resolution:
  G3 names the **ABC** (`Transform`) as untouchable, not the directory tree.
  The directory contains legitimately-evolving plugin-side code
  (`engines/`, `policy/`). Both findings apply: pin the ABC file
  specifically, and the *baseline-SHA fence* (`test_kernel_frozen.py`)
  already covers the dir-scope question via `_KERNEL_ALLOWLIST` once
  S1-07's phase-3 baseline row lands. No contradiction.
- **F11 (manual docstring AC) vs Rule 9 (ACs must be verifiable).** Rule 9
  generally wins; here we demote the AC to a Notes paragraph rather than
  building a regex test for a one-off docstring line (Rule 2 — premature
  abstraction). The verifiable substitute is the `make check` AC plus the
  manual hygiene step in Notes.

## Edits applied

### Edit 1 — `Validation notes` block under story header
Records verdict, 14 findings, the per-AC change list, the `BLOCKED-PARTIAL on
S1-07` qualifier, and the F1/F2 file-pinning correction.

### Edit 2 — `Depends on:` line
Added S1-03 (`test_plan_outcome_no_recipe_outcome_widening.py`) and S1-05
(`test_pyproject_fence_phase4.py`) as explicit dependencies. Surfaced S1-07
RESCUE state with the routing note.

### Edit 3 — Status line
Flipped from `Ready` to `HARDENED (2026-05-24 — phase-story-validator)`
with `BLOCKED-PARTIAL on S1-07 (Phase-3 baseline row)` qualifier.

### Edit 4 — References block additions
Added cross-links to S1-03, S1-05, S1-07 stories + the RESCUE report.

### Edit 5 — Acceptance criteria reconciliation
- AC-1 / AC-2 / AC-3 annotated with their dependency stories.
- AC bucket list reconciled with TDD `ALLOWED_EXACT` (added `uv.lock`,
  `.importlinter`, `.github/workflows/ci.yml`).
- Removed `src/codegenie/orchestrator/` AC (vacuous — directory does not
  exist).
- Replaced `src/codegenie/transforms/` directory diff with explicit-file
  pins: `transforms/transform.py` and `transforms/recipe_engine.py`.
- Added new AC for the planted-violation unit-test coverage (F9).
- Added new AC for the vacuous-allow-list invariant guard (F8).
- Added new AC for the master/no-diff skip behavior (F10).
- Added new AC for the bucket-classification failure-message map (F14).
- Demoted the docstring-update AC to a Notes paragraph (F11).

### Edit 6 — TDD plan rewrite
- Fixed `git diff` double-`--` bug (F4).
- Dropped `test_companion_property_test_still_green` (F7).
- Extracted pure `_classify` helper; added planted-violation table tests
  (F8/F9/F12).
- Added invariant test for non-empty rooted `ALLOWED_PREFIXES`.
- Updated `test_phase_3_kernel_files_unmodified` forbidden-paths list to
  cover all 8 G3 surfaces (F6).
- Added empty-diff-on-master skip path (F10).
- Updated failure message to include bucket-classification hint (F14).

### Edit 7 — Implementation outline
Surfaced the S1-07 dependency check as step 0; tightened step 5 to use the
explicit-file pins; clarified that "tightening" stays a Notes-only TODO.

### Edit 8 — Files to touch
Removed the optional `_kernel_allow_list.py` row (F13 — defer to Phase 7
when there's a real second consumer). Added `tests/fence/_phase4_allow_list_constants.py`
as a small extracted-pure-helper module if `_classify` extraction warrants
a separate file (executor's judgment; not mandated).

### Edit 9 — Notes for the implementer
Added paragraph on Phase-7 mirror pattern + extraction-only-on-rule-of-three.
Moved the docstring-update hygiene step here from ACs (F11). Added the F3
S1-07-routing paragraph (re-author or document deferred coverage).

## Verdict rationale

HARDENED, not RESCUE. The goal — "Phase-4 Step-7 merge gate that re-verifies
the kernel-frozen contract" — is exactly what arch §G3 + ADR-0004 + ADR-0003
+ production ADR-0031 call for. The body has fixable drifts: stale paths,
syntax bugs, missing dependencies, vacuous guards. Twelve targeted edits put
the story on a footing where `phase-story-executor` can land it, subject to
the S1-07-BLOCKED qualifier (which is honest reporting, not blockage — the
story can still run with documented deferred phase-3 baseline coverage).

## Recommended next step

`phase-story-executor` may run the story **after** S1-07 is re-authored and
GREEN — at which point AC-1 has full coverage including the phase-3 baseline.
Alternatively the executor may run S7-08 first with the S1-07-deferred note
in the attempt log; this is acceptable per the BLOCKED-PARTIAL qualifier, but
the Phase-3 kernel state will not be diff-checked until S1-07 lands.
