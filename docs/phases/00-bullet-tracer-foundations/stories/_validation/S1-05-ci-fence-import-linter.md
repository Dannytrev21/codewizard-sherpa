# Validation report: S1-05 — CI workflow + fence job + import-linter

**Validated:** 2026-05-13
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story file:** [`../S1-05-ci-fence-import-linter.md`](../S1-05-ci-fence-import-linter.md)

## Summary

S1-05 is the load-bearing story of Phase 0: it ships the `fence` CI job that makes "no LLM in gather" (production ADR-0005 / phase ADR-0002) an executable test from day one, plus the `import-linter` structural defense for cold-start (`phase-arch-design.md §Tradeoffs` row 12 — replaces the critique-flagged flaky CLI canary). The story's high-level alignment with phase-arch §Goals (#5 six CI jobs, #7 fence blocks LLM SDKs), §Edge cases (#9, #15), the four-slot extras shape from ADR-0006, and CLAUDE.md commitments (no LLM in gather, extension by addition, determinism) was structurally sound — no `block`-class architectural issues. But the original 8 ACs and 5 tests across 2 files contained four `block`-severity defects and ~9 `harden` items that would have let an implementer ship 50–60% of the contract while passing every literal AC.

The defects clustered in three buckets:

1. **Self-checking tautologies in the deliberate-negative tests.** ADR-0002 §Decision names the deliberate-negative test as "the test that catches the fence check itself silently broken" — but the original `test_fence_catches_planted_anthropic_dep` reimplemented the parsing logic in-test, then asserted on its own arithmetic. Mutation guard: rewrite the production fence to `return set()` always — both fence tests still pass. This is the textbook *Hard-coded matching hard-coded* anti-pattern from `story-smells.md`. The third test, `test_fence_scope_is_dependencies_only_never_optional`, asserted `all("extra ==" in r for r in extras_lines)` where `extras_lines` was *defined as* `[r for r in raw if "extra ==" in r]` — `True` by construction. Two `block`-severity findings, one structural fix: extract the production helper `src/codegenie/_fence.py` and have all five (now-parametrized) fence tests invoke it.

2. **Self-contradictory and missing install discipline.** AC-3 said the fence job installs bare `[project]` AND runs `pytest -q` — but `pytest` is in `[dev]`, so the two clauses cannot both be true without an explicit second install step the story never specified. Separately, AC-6 required `lint-imports` to run from `make typecheck`, but `import-linter` was never added to `[dev]` (the comment in `pyproject.toml` line 44 explicitly says S1-04/S1-05 own that addition) — the binary would be `command not found` in CI. Two more `block`-severity findings: (a) split the fence install into two steps (bare base, then standalone pytest); (b) add `import-linter` and `pip-audit` to `[dev]`, re-run `uv lock`.

3. **Enumerate-then-test-zero / behavioral-AC-with-no-behavioral-test (the recurring S1-04 pattern).** AC-1, AC-2, AC-3 enumerated detailed workflow contents — six job names, the Python × OS matrix, SHA-pinning, `concurrency`, `permissions`, the `fence` install — with **zero parser tests**. An implementer can ship a 4-job workflow with tag-pinned actions, no `cancel-in-progress`, the `fence` job silently installing `[dev]`, and pass every test in the original plan because the only fence-related test merely measures the *installed dist's* requires (which was empty in the Step 1 PR). AC-6 said `make typecheck` (or `make lint-imports`) invokes `lint-imports` — leaving the implementer free to bundle import-linter under typecheck (against the six-job decomposition) or skip it entirely. AC-8 was the cataloged `was committed, and is green` process clause already closed on S1-04. The `security` job's content (`pip-audit` + `osv-scanner`) was named in the High-level-impl but had no AC — `security: { run: echo OK }` would have passed. The `docs` job's path filter, `cancel-in-progress: true`, the absence of `pull_request_target`, the `# v4.x.y` SHA-pinning comment convention, and the `lint-imports --no-cache` flag all lived in the Refactor / Notes prose but had no AC anchor.

Other smaller defects: the `cli.py` AST scan's narrow scope (`from .submodule import X` re-exports defeat it — a runtime-side-effect test catches what AST cannot); the stale reference to `phase-arch-design.md §Implementation-level risks #4` (no such section exists; the actual home is `§Edge cases #15` + `High-level-impl.md §Step 1 — Risks specific to this step`).

The synthesizer extracted the `src/codegenie/_fence.py` production helper, rewrote AC-1..AC-8 (renumbered AC-1..AC-12), grew the TDD plan from 5 tests across 2 files to 12 tests across 4 files, dropped the process-clause AC, and resolved AC-6's "or" by collapsing to a dedicated `make lint-imports` target invoked by the `lint` CI job. Goal sentence updated (`make typecheck` → `make lint-imports`). Four references updated to point at the actual sources. No structural rewrites to the story's intent: the goal, the load-bearing fence + import-linter framing, the ADR-0002/0006 honor, and the dependency on S1-01/S1-02 are unchanged. **Verdict: HARDENED.** No `RESCUE` conditions encountered — the story's premise is sound; only its enforceability needed sharpening.

## Findings by critic

### Coverage critic findings — S1-05

#### F-Coverage-1 — AC-3 install assertion is text-only, not behavioral
- **Severity:** harden
- **What's wrong:** AC-3 says the fence job installs `[project]` without `[dev]` and runs pytest. There is no AC that *parses* `ci.yml` and asserts those install steps. A lazy implementer can write `pip install -e .[dev]` and pass — the unit tests still pass locally because they query installed metadata, and Goal-clause-1 happens to remain true while the closure scope has silently widened.
- **Fix applied:** Added AC-9's `test_fence_job_install_is_two_step_and_excludes_dev_extras` — parses ci.yml, asserts the fence's `run:` text contains `pip install -e .` AND `pip install pytest` AND none of `[dev]`, `[agents]`, `[service]`.

#### F-Coverage-2 — AC-1 enumerates six jobs with no parser test
- **Severity:** harden
- **Fix applied:** AC-9's `test_ci_workflow_declares_exactly_six_required_jobs` asserts set equality.

#### F-Coverage-3 — SHA-pinning unverified
- **Severity:** harden
- **Fix applied:** AC-9's `test_every_third_party_action_is_sha_pinned_not_tag_pinned` regexes every `uses:` value containing `/` against `^[A-Za-z0-9_./-]+@[0-9a-f]{40}$`.

#### F-Coverage-4 — `cancel-in-progress: true` in implementer notes, not in any AC
- **Severity:** harden
- **Fix applied:** AC-2 expanded to mandate the full `concurrency: { group, cancel-in-progress }` shape; AC-9's `test_ci_workflow_concurrency_cancels_old_runs_on_same_ref` asserts `is True`.

#### F-Coverage-5 — `docs` job path filter in Refactor §5, not in AC
- **Severity:** medium (`NEEDS RESEARCH` flag from coverage critic)
- **Resolution without Stage 3 research:** GHA does not natively support per-job `paths:` (workflow-level `paths:` gates the entire workflow, not just one job). The two canonical patterns are (A) `dorny/paths-filter@<SHA>` action setting an output, with `if:` guards on subsequent jobs; (B) split the docs job into a separate workflow file. Story now offers both as AC-12 options; the parser test in AC-9 validates whichever was chosen.

#### F-Coverage-6 — `click` ambiguity in `__init__.py` contract
- **Severity:** harden
- **Fix applied:** AC-5 explicitly states `click` is allowed at `__init__.py` top level (CLI entry point requires it; cold-start advisory accepts the overhead).

#### F-Coverage-7 — AC-6 doesn't assert the `typecheck`/`lint` CI job actually invokes the Makefile target
- **Severity:** harden
- **Fix applied:** AC-9's `test_lint_job_invokes_make_lint_imports` asserts the `lint` job's `run:` contains `make lint-imports`. AC-6 simultaneously rewritten to route `lint-imports` through the `lint` job (not `typecheck`).

#### F-Coverage-8 — `import-linter` config runnability not asserted
- **Severity:** harden
- **Fix applied:** AC-9's `test_importlinter_has_two_forbidden_contracts_for_cli_and_init` parses pyproject.toml and asserts both contracts have `type: forbidden`, the right `source_modules`, and the full `forbidden_modules` set. AC-10's `test_lint_imports_actually_blocks_a_planted_heavy_import` runs the real `lint-imports` against a planted violation.

#### F-Coverage-9 — Tautological scope-axis test
- **Severity:** harden
- **Fix applied:** Replaced with the metamorphic `test_fence_ignores_llm_sdk_when_planted_in_optional_extras` (plants in `[project.optional-dependencies].agents`, asserts the production scanner ignores it).

#### F-Coverage-10 — Coverage carve-out has no AC
- **Severity:** nit
- **Fix applied:** Refactor step now mandates a "Coverage carve-out" PR-body section + a `# TODO(S4-04)` comment if the carve-out is set in `ci.yml`.

#### F-Coverage-11 — `security` job content has no AC
- **Severity:** harden
- **Fix applied:** New AC-11 — `pip-audit` + `osv-scanner` against `uv.lock`; pip-audit added to `[dev]`, osv-scanner via `google/osv-scanner-action@<SHA>`; severity gating wired. AC-9's `test_security_job_invokes_pip_audit_and_osv_scanner_against_uv_lock` enforces.

#### F-Coverage-12 — AC-8 process clause
- **Severity:** harden
- **Fix applied:** Old AC-8 ("was committed, and is green") deleted — the test-shaped ACs already cover this. (Same nit S1-04 closed.)

#### F-Coverage-13 — No AC excludes `pull_request_target`
- **Severity:** harden
- **Fix applied:** AC-2 expanded to cap triggers at `{pull_request, push, workflow_dispatch}`; AC-9's `test_ci_workflow_triggers_exclude_pull_request_target` asserts.

**Coverage verdict:** HARDENABLE → HARDENED.

### Test-Quality critic findings — S1-05

#### F-Test-Quality-1 — `test_fence_catches_planted_anthropic_dep` is a tautology (BLOCK)
- **Severity:** block
- **What's wrong:** The test parses synthetic TOML, reimplements the fence's name-extraction logic in-test, intersects with `FORBIDDEN_LLM_SDKS`, and asserts on its own arithmetic. **Mutation: rewrite the production fence to `return set()` always — this test still passes.** ADR-0002 calls this test "the one that catches the fence silently broken" — the original implementation does the exact opposite of that.
- **Fix applied:** Extracted production helper `src/codegenie/_fence.py` with `parse_runtime_dep_names_from_toml`; the deliberate-negative test now invokes it. Mutation-killing real: change `&` to `|` in production and `test_fence_blocks_known_llm_sdks` dies; drop the parser's filter logic and `test_fence_helper_strips_version_specifiers_and_extras_markers` dies.

#### F-Test-Quality-2 — Scope-axis test contains a no-op tautology assertion (BLOCK)
- **Severity:** block
- **What's wrong:** `assert all("extra ==" in r for r in extras_lines)` where `extras_lines = [r for r in raw if "extra ==" in r]` — `True` by construction. The test does not verify the **production fence** filters out extras. Mutation: change the production code to *include* extras (`if "extra ==" in req: pass` instead of `continue`) — this test still passes.
- **Fix applied:** Replaced with the metamorphic `test_fence_ignores_llm_sdk_when_planted_in_optional_extras` (plant `anthropic` in `[project.optional-dependencies].agents`, assert empty intersection through the production helper).

#### F-Test-Quality-3 — Single planted SDK leaves N-1 silent failure modes
- **Severity:** harden
- **Fix applied:** `test_fence_catches_each_planted_llm_sdk` is now `@pytest.mark.parametrize`'d over all five SDKs; a separate `test_forbidden_set_is_exactly_adr_0002_closure` asserts the production set against the expected set (any silent erosion fails this).

#### F-Test-Quality-4 — No subprocess test invokes `lint-imports`
- **Severity:** harden
- **Fix applied:** AC-10 + new test file `tests/unit/test_lint_imports_canary.py` with both `test_lint_imports_exits_zero_on_current_tree` and `test_lint_imports_actually_blocks_a_planted_heavy_import`. Mirrors S1-02's `test_ruff_check_rejects_print_in_src_per_phase_arch_logging_strategy` (`tests/unit/test_toolchain_config.py:132-163`) — established codebase pattern.

#### F-Test-Quality-5 — Workflow YAML contents have no parsing test (BLOCK)
- **Severity:** block
- **Fix applied:** New file `tests/unit/test_ci_workflow.py` with twelve assertions covering jobs/concurrency/permissions/triggers/matrix/SHA-pinning/fence install/lint job/security job/docs path filter/import-linter config. Each test dies under at least one obvious mutation (drop a job, switch to tag pin, flip cancel-in-progress, sneak `[dev]` into fence install).

#### F-Test-Quality-6 — `cli.py` AST test vacuously green; no fixture-based mutation guard
- **Severity:** harden
- **Fix applied:** AC-10's `test_lint_imports_actually_blocks_a_planted_heavy_import` plants a violation, runs the real linter, asserts non-zero, restores. Pre-S4-02 the existing `cli.py` AST test now uses `pytest.skip` (visible in `-v` output) rather than a silent `return`.

#### F-Test-Quality-7 — `__init__.py` AST scan defeated by transitive re-exports
- **Severity:** harden
- **What's wrong:** `from .submodule import X` where `.submodule` top-level imports `yaml` passes the AST scan but Python *still* loads `yaml` at package import time.
- **Fix applied:** AC-7 adds `test_importing_codegenie_does_not_load_heavy_modules` — spawns a subprocess that imports codegenie and inspects `sys.modules` for transitive heavy-module loads. The fast AST guards are retained as redundant cheap checks.

#### F-Test-Quality-8 — AC-6 disjunction creates an implementation fork
- **Severity:** harden
- **Fix applied:** AC-6 collapsed to a single dedicated `make lint-imports` target invoked by the `lint` CI job. Per Rule 7 (Surface conflicts, don't average them) — the `or` was averaging two design choices.

#### F-Test-Quality-9 — `lint-imports` cache may mask stale-contract failures
- **Severity:** harden
- **Fix applied:** AC-6 mandates `--no-cache` in the Makefile recipe; implementer notes call out *why* (cache keys on file mtimes; an edit to `pyproject.toml` that drops a forbidden module without touching source can serve stale "ok").

**Test-quality verdict:** NOT-READY → HARDENED. Two block-severity findings (F1, F2, F5) resolved with structural fixes (production helper extraction, metamorphic test, parser test file). All harden items absorbed.

### Consistency critic findings — S1-05

#### F-Consistency-1 — AC-3 self-contradiction: `pytest` not installed (BLOCK)
- **Severity:** block
- **What's wrong:** "fence job installs base distribution (`pip install -e .` without `[dev]`) AND runs `pytest`" — pytest is in `[dev]`, so both clauses cannot hold without an explicit second install step.
- **Fix applied:** AC-3 split into two-step install: (a) bare `pip install -e .` (measures closure); (b) `pip install pytest` standalone (after, so closure is uncontaminated). AC-9 parser test enforces the two-step shape.

#### F-Consistency-2 — `import-linter` not added to `[dev]` (BLOCK)
- **Severity:** block
- **What's wrong:** Current `pyproject.toml` line 44 explicitly says: *"Additional entries (import-linter, pip-audit, osv-scanner, bandit) are owned by S1-04 / S1-05."* The story's Files-to-touch only mentioned adding `[tool.importlinter]` config — not the dependency itself. CI would fail with `lint-imports: command not found`.
- **Fix applied:** New AC-8 mandates adding `import-linter` (and `pip-audit` per AC-11) to `[dev]`; `uv.lock` re-locked per S1-03 AC-7.

#### F-Consistency-3 — Stale reference to `phase-arch-design.md §Implementation-level risks #4`
- **Severity:** harden
- **What's wrong:** Section does not exist. The actual sources for the "fence test scope drift" instinct are `phase-arch-design.md §Edge cases #15` and `High-level-impl.md §Step 1 — Risks specific to this step`.
- **Fix applied:** References block, Refactor §3, and Notes section all updated to cite the correct sources. Old citation marked as "validator-corrected stale citation" in the References block for trace-ability.

#### F-Consistency-4 — AC-6 ambiguity contradicts six-job decomposition AND Files-to-touch "Optional" tag
- **Severity:** harden
- **Fix applied:** Per F-Test-Quality-8 — AC-6 is now a single dedicated `make lint-imports` target invoked by the `lint` CI job. `typecheck` is untouched (preserves the six-job decomposition — `phase-arch-design.md §Testing strategy / CI gates`). Files-to-touch row for `Makefile` upgraded from "Optional" to "Required".

#### F-Consistency-5 — `security` job content has no AC
- **Severity:** harden
- **Fix applied:** Same as F-Coverage-11 — new AC-11.

#### F-Consistency-6 — Vacuously-green import-linter test should be made explicit
- **Severity:** nit
- **Fix applied:** Context paragraph appended with explicit note: between S1-05 and S4-02 the `cli`-targeted contract's executable enforcement lives in AC-10's deliberate-negative canary (which plants a fixture `cli.py`). Test (b) in `test_cli_cold_start.py` uses `pytest.skip` so the deferred state is visible in `-v`.

#### F-Consistency-7 — Brittle `has_dev_extra` sanity check coupling
- **Severity:** nit
- **Fix applied:** Subsumed by F-Test-Quality-2 — the original test was deleted in favor of the metamorphic version, which has no infrastructure-coupling assertion.

#### F-Consistency-8 — Goal sentence pinned to one ambiguous AC-6 path
- **Severity:** nit
- **Fix applied:** Goal sentence updated to `make lint-imports` (matches the resolved AC-6 path).

#### F-Consistency-9 — `cancel-in-progress: true` in Notes but not in AC
- **Severity:** nit
- **Fix applied:** Same as F-Coverage-4 — lifted into AC-2 with mandatory force.

**Consistency verdict:** HARDENABLE → HARDENED. F1, F2 (block) resolved with structural changes. All harden/nit items closed.

## Researcher findings

Stage 3 not invoked. The single `NEEDS RESEARCH` flag (F-Coverage-5 on docs path filtering) was resolvable from prior Claude knowledge of GitHub Actions' triggering model: native per-job `paths:` does not exist; the canonical patterns are `dorny/paths-filter` (Option A) or split-into-separate-workflow (Option B). Story now presents both options as AC-12; AC-9's parser test validates whichever is chosen. No external doc citations added — the GitHub Actions docs at `https://docs.github.com/en/actions/using-workflows/triggering-a-workflow` are the authoritative source for the implementer if needed.

## Edits applied to the story

| Section | Change |
|---|---|
| Header | `Status: Ready` → `Status: Ready — HARDENED`; `Depends on:` adds `S1-03` (Makefile target conventions); new `Validation notes` block summarizing all 14 substantive changes. |
| Context | Appended paragraph explaining the production helper extraction and the deferred-enforcement note for the `cli`-targeted contract. |
| References | Stale `§Implementation-level risks #4` citation explicitly marked as validator-corrected; replaced with `§Edge cases #15` + `High-level-impl.md §Step 1 — Risks specific to this step`. |
| Goal | `make typecheck` → `make lint-imports`. |
| Acceptance criteria | Old AC-1..AC-8 (8 ACs) → new AC-1..AC-12 (12 ACs). Old AC-8 process clause dropped. New ACs: AC-8 (`import-linter` in `[dev]`), AC-9 (workflow + import-linter parser test), AC-10 (deliberate-negative lint-imports canary), AC-11 (security job content), AC-12 (docs path filter). All ACs strengthened with explicit verifiability anchors. |
| Implementation outline | Old 7 steps → new 9 steps. Step 1 now extracts the production helper first; new steps for `[dev]` deps, `Makefile` wiring, and AC-12 path filter. |
| TDD plan / Red | Old 2 test files (5 tests, with the tautology and the no-op assertion) → new 4 test files (12 tests, all mutation-resistant). Production helper `src/codegenie/_fence.py` extracted so deliberate-negative tests invoke real code. |
| TDD plan / Green | Updated to enumerate the helper, dep additions, Makefile target, six-job workflow, and four-test-file suite. |
| TDD plan / Refactor | Stale CODEOWNERS reference fixed; AC-9 / AC-2 / AC-12 re-verification added; coverage carve-out documentation step added. |
| Files to touch | Old 5 rows → new 9 rows. New: `_fence.py`, `docs.yml` (conditional), `test_cli_cold_start.py`, `test_ci_workflow.py`, `test_lint_imports_canary.py`, `uv.lock`. `Makefile` upgraded from "Optional" to "Required"; old `test_import_linter_blocks_heavy_from_cli.py` superseded by `test_cli_cold_start.py`. |
| Notes for the implementer | Stale `§Implementation-level risks #4` reference fixed; the `cli.exists()` early-out note rewritten to explain the new `pytest.skip` + AC-10 canary substitution; added the "why a production helper" paragraph; added the "lint job runs both make lint AND make lint-imports" note; added the `--no-cache` rationale. |

## Resolution of conflicts between critics

- **Coverage F5 (`NEEDS RESEARCH` for docs path filter) vs Test-Quality / Consistency:** No conflict — Coverage flagged the missing AC, Consistency had no opinion. Synthesizer resolved without Stage 3 by offering Option A / Option B in AC-12.
- **AC-6 disjunction** flagged by Coverage F7, Test-Quality F8, Consistency F4 — three independent confirmations, one fix (collapse to dedicated `make lint-imports` invoked by `lint` job).
- **Test-Quality F1 (extract production helper)** vs original story's "minimal lines" framing: Test-Quality (mutation-resistance) wins because the deliberate-negative test was structurally non-functional otherwise. The added file is small (~40 lines) and is private (`_` prefix) — matches Rule 3 (surgical).

## Confidence in the verdict

Confidence: **high**. All four block-severity findings have concrete, mutation-resistant fixes. The new TDD plan kills every obvious production-code mutation: change the fence intersection operator, drop a forbidden SDK from the set, widen the fence to optional-dependencies, drop a workflow job, tag-pin instead of SHA-pin, omit `cancel-in-progress`, sneak `[dev]` into the fence install, misconfigure the import-linter contract, drop `import-linter` from `[dev]`, bundle `lint-imports` under `typecheck`, leave the `security` job empty, ship `pull_request_target` — *each* of these dies under at least one named test.

Story is **execution-ready** for the phase-story-executor. The implementer should expect ~9 implementation steps producing the production helper, two `pyproject.toml` deltas, one `Makefile` delta, one `uv.lock` re-lock, one `ci.yml` (and possibly `docs.yml`), and four test files containing 12 mutation-resistant tests.
