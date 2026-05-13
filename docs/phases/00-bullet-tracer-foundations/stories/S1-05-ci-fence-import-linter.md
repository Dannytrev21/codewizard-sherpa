# Story S1-05 — CI workflow + fence job + import-linter

**Step:** Step 1 — Establish project skeleton, tooling, and the `fence` CI job
**Status:** Done — 2026-05-13 (phase-story-executor, attempt 1, GREEN)
**Effort:** M
**Depends on:** S1-01, S1-02, S1-03 (Makefile target conventions)
**ADRs honored:** ADR-0002, ADR-0006

## Execution evidence (2026-05-13)

Attempt log: [`_attempts/S1-05.md`](_attempts/S1-05.md).

All twelve ACs satisfied with runtime evidence; 28 new tests across four test
files, all green; `make lint` / `make typecheck` / `make lint-imports` /
`pre-commit run --all-files` all clean; full suite `pytest -q --cov-fail-under=0`
**79 passed**.

| AC | Evidence |
|---|---|
| AC-1 | `tests/unit/test_ci_workflow.py::test_ci_workflow_declares_exactly_six_required_jobs` + `::test_ci_workflow_pins_python_311_312_on_ubuntu_2404` + `::test_every_third_party_action_is_sha_pinned_not_tag_pinned` |
| AC-2 | `::test_ci_workflow_concurrency_cancels_old_runs_on_same_ref` + `::test_ci_workflow_top_level_permissions_are_read_only` + `::test_ci_workflow_triggers_exclude_pull_request_target` + `::test_no_job_widens_contents_permission_beyond_read` |
| AC-3 | `::test_fence_job_install_is_two_step_and_excludes_dev_extras` |
| AC-4 | `tests/unit/test_pyproject_fence.py` (9 tests; parametrized over 5 SDKs) |
| AC-5 | `::test_importlinter_config_root_packages_includes_codegenie` + `::test_importlinter_has_two_forbidden_contracts_for_cli_and_init` |
| AC-6 | `Makefile` `lint-imports` target invokes `lint-imports --config pyproject.toml --no-cache`; `::test_lint_job_invokes_make_lint_imports` |
| AC-7 | `tests/unit/test_cli_cold_start.py` (3 tests; subprocess `sys.modules` probe is load-bearing) |
| AC-8 | `pyproject.toml` `[project.optional-dependencies].dev` contains `import-linter` + `pip-audit`; `uv.lock` regenerated; S1-03 lockstep test green |
| AC-9 | `tests/unit/test_ci_workflow.py` (14 parser assertions over `ci.yml` + `[tool.importlinter]`) |
| AC-10 | `tests/unit/test_lint_imports_canary.py` (green half + deliberate-negative half with `finally:` restore) |
| AC-11 | `::test_security_job_invokes_pip_audit_and_osv_scanner_against_uv_lock` |
| AC-12 | **Option B** — `.github/workflows/docs.yml` with `paths: [docs/**, mkdocs.yml]`; `::test_docs_job_path_filtering_is_wired_per_ac_12` |

**Deviations from "Files to touch"** (see attempt log for full justification):

1. `src/codegenie/cli.py` placeholder stub created — import-linter v2 hard-errors when `source_modules` references a non-existent module; the story's "vacuously enforced until S4-02" framing is not realizable as a literal no-op. S4-02 will expand the stub.
2. `include_external_packages = true` added to `[tool.importlinter]` — required by import-linter v2 when `forbidden_modules` names external packages.
3. `.pre-commit-config.yaml` — `packaging` added to the mypy hook's `additional_dependencies:` so the isolated env can resolve `packaging.requirements` (`_fence.py`'s only new external import).

## Validation notes (2026-05-13, phase-story-validator v1)

Hardened from STRONG-CRITICS-CONDITIONAL → HARDENED. Verdict: HARDENED. See [`_validation/S1-05-ci-fence-import-linter.md`](_validation/S1-05-ci-fence-import-linter.md) for the full audit log.

Eight original ACs grew to twelve; TDD plan grew from 5 to 12 tests across 4 test files. Substantive changes:

1. **Goal sentence:** swapped `make typecheck` → `make lint-imports` (resolves AC-6 ambiguity per F-Consistency-4 / F-Test-Quality-8).
2. **AC-3 (fence install):** split into the explicit two-step install (bare `pip install -e .`, *then* standalone `pip install pytest`) — prior wording said "install bare `[project]` AND run pytest" which was self-contradictory because pytest is in `[dev]` (F-Consistency-1, block).
3. **AC-4 (fence tests):** the original `test_fence_catches_planted_anthropic_dep` reimplemented the parsing in-test and asserted on its own arithmetic — the textbook tautology smell (F-Test-Quality-1, block). Production helper `src/codegenie/_fence.py` extracted; the deliberate-negative test now invokes the real function. Parametrized over all five members of the forbidden set (F-Test-Quality-3). The vacuous `test_fence_scope_is_dependencies_only_never_optional` replaced with a metamorphic version that plants `anthropic` in `[project.optional-dependencies].agents` and asserts the production scanner ignores it (F-Test-Quality-2, block).
4. **NEW AC-8 (`import-linter` in `[dev]`):** the prior story would have shipped `lint-imports: command not found` in CI because no AC mandated adding it to `[project.optional-dependencies].dev` (F-Consistency-2, block).
5. **NEW AC-6 (single Makefile target):** AC-6's "or" disjunction collapsed to a dedicated `make lint-imports` target invoked by the `lint` CI job — bundling under `typecheck` muddles the six-job decomposition (F-Consistency-4, F-Test-Quality-8). `--no-cache` flag added to defeat stale-contract failures (F-Test-Quality-9). The S1-03 Makefile is amended; `Files to touch` upgraded `Makefile` from "Optional" to "Required."
6. **NEW AC-7 (runtime side-effect import test):** the AST scan caught only the literal `import` statements at module-level; `from .submodule import X` where `submodule` top-level imports `yaml` would slip through silently (F-Test-Quality-7). Replaced with a subprocess test that imports `codegenie` and inspects `sys.modules` for transitive heavy-module loads. The fast AST scan retained as a redundant guard.
7. **NEW AC-9 (workflow YAML parser test):** AC-1/AC-2/AC-3 enumerated workflow contents (six jobs, matrix, SHA-pinning, concurrency, permissions, fence install) with zero parser test — the same S1-04 "enumerate-then-test-zero" failure mode (F-Coverage-1/2/3/7, F-Test-Quality-5, block). New `tests/unit/test_ci_workflow.py` mutation-tests each contractual property (set-equality on jobs, regex on SHAs, `cancel-in-progress: true`, no `pull_request_target`).
8. **NEW AC-10 (deliberate-negative `lint-imports` canary):** mirrors S1-02's ruff `print(` canary (`test_toolchain_config.py:132-163`). Plants `import yaml` in a fixture file, runs `lint-imports`, asserts non-zero exit, cleans up. Without this, the `[tool.importlinter]` config could be silently misconfigured and every test still passes (F-Test-Quality-6).
9. **NEW AC-11 (`security` job content):** AC-1 declared the job but nothing said what it ran (F-Coverage-11, F-Consistency-5). Now requires `pip-audit` + `osv-scanner` invocations against `uv.lock`; `pip-audit` added to `[dev]`, `osv-scanner` installed in CI via the `google/osv-scanner-action@<SHA>` action (Go binary; not pip-installable).
10. **NEW AC-12 (docs path filtering):** `docs` job must skip on non-docs PRs to honor the ≤90s p95 walltime advisory (F-Coverage-5). Implementer chooses between `dorny/paths-filter@<SHA>` + `if:` guard, or a separate workflow file `.github/workflows/docs.yml` with top-level `paths:`.
11. **AC-2 expanded:** `cancel-in-progress: true` lifted from implementer notes (F-Coverage-4); explicit ban on `pull_request_target` (F-Coverage-13).
12. **Old AC-8 dropped** (process clause "was committed, and is green" — same nit S1-04 closed; the test-shaped ACs already cover this).
13. **References:** stale citation `phase-arch-design.md §Implementation-level risks #4` (section does not exist) replaced with the actual sources: `phase-arch-design.md §Edge cases #15` + `High-level-impl.md §Step 1 — Risks specific to this step` (F-Consistency-3).
14. **Goal-clause-2** (`from codegenie.cli import yaml` raises a violation under `make lint-imports`) is *vacuously* satisfied until S4-02 lands `src/codegenie/cli.py`. AC-7's deliberate-negative canary makes the contract executable today by planting a fixture; the real cli.py guard lights up with S4-02 (F-Consistency-6).

## Context

This story ships the **load-bearing CI gate** for Phase 0: the `fence` job that asserts the wheel's runtime dependency closure contains no LLM SDK (ADR-0002). It also wires the other five CI jobs (`lint`, `typecheck`, `test`, `security`, `docs`) so every later story merges through the same six-job pipeline. The `import-linter` config blocks heavy modules from `cli.py` and `__init__.py` — the *structural* defense for cold-start performance, replacing the critique-flagged flaky canary (`phase-arch-design.md §Tradeoffs` row "CLI canary advisory, `import-linter` structural").

This is **the** load-bearing story for Phase 0: ADR-0002 is enforced from the first commit forward, and Phase 4's eventual LLM SDK landing zone can never silently contaminate the gather closure. The deliberate-negative test (`test_fence_catches_planted_anthropic_dep`) inoculates the check against silent breakage — the named risk in `final-design.md §10 risk #5`. To make that inoculation real (rather than a self-checking tautology), the fence's name-extraction logic is extracted into a one-file production helper `src/codegenie/_fence.py` so both the live test (which queries the installed distribution) and the deliberate-negative test (which scans synthetic TOML) invoke the *same* code path — mutating the production scanner kills both tests.

**Note on the `cli`-targeted import-linter contract:** the `[tool.importlinter]` configuration lands here, but its `cli`-source contract is *vacuously* enforceable until `src/codegenie/cli.py` lands in S4-02 (vertical slice). Between S1-05 and S4-02 the cold-start defense lives in two places: (1) the configuration in `pyproject.toml` (a no-op `lint-imports` run for `cli`); (2) AC-10's deliberate-negative canary that *plants* an `import yaml` in a fixture `cli.py`, runs `lint-imports`, asserts non-zero exit, and cleans up — making the contract executable today. The `__init__.py` contract is operative immediately because `src/codegenie/__init__.py` exists from S1-01.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy / CI gates` — six jobs, matrix `python: ["3.11", "3.12"]` × `os: [ubuntu-24.04]`, concurrency group, SHA-pinned actions, `permissions: contents: read`, ≤ 90s p95 walltime advisory.
  - `../phase-arch-design.md §Edge cases` row #9 — `fence` fails as a "load-bearing-commitment-violation alarm"; the deliberate-negative test guards the check itself.
  - `../phase-arch-design.md §Edge cases` row #15 — fence scope is `dependencies` only, never `optional-dependencies`. **This is the source for "scope drift never silently widens" — replaces the validator-corrected stale citation `phase-arch-design.md §Implementation-level risks #4` (no such section exists).**
  - `../phase-arch-design.md §Component design — CLI` — `cli.py` and `__init__.py` defer heavy imports; `import-linter` enforces this structurally.
  - `../High-level-impl.md §Step 1 — Risks specific to this step` — "the `fence` test scope (`dependencies` only, never `optional-dependencies`) must be encoded so it can never be widened silently — assert it in the test itself." This is the corrected source for the CODEOWNERS-routing instinct (the actual CODEOWNERS file lands in S5-02 — see Refactor §3 of this story).
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0002-fence-ci-job-no-llm-in-gather.md` — ADR-0002 — the exact intersection set `{anthropic, langgraph, openai, langchain, transformers}`, the deliberate-negative test, and the `dependencies`-only scope.
  - `../ADRs/0006-pyproject-toml-extras-shape.md` — ADR-0006 — the fence installs base `[project]` (no extras), the other jobs install `[dev]`.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — the load-bearing architectural commitment the fence enforces.
- **Source design:**
  - `../High-level-impl.md §Step 1` — Features delivered: `.github/workflows/ci.yml` with six jobs, the deliberate-negative test, `import-linter` blocking heavy modules.
  - `../High-level-impl.md §Risks specific to this step` — `import-linter` regex over-block warning; keep blocklist scoped to `cli.py` and `__init__.py`.

## Goal

A PR that adds `anthropic` to `[project].dependencies` is rejected by the `fence` CI job, and `from codegenie.cli import yaml` raises an `import-linter` violation under `make lint-imports`.

## Acceptance criteria

- [ ] **AC-1 (workflow exists, six named jobs, matrix, SHA-pinning):** `.github/workflows/ci.yml` exists declaring exactly six jobs: `lint`, `typecheck`, `test`, `security`, `docs`, `fence` (set equality — no extras, no missing). At least one job (or the workflow's `strategy: matrix:`) pins `python: ["3.11", "3.12"]` × `os: ["ubuntu-24.04"]`. Every step's `uses:` value across all jobs whose action contains a `/` (i.e., a third-party action, not a local composite) matches the regex `^[A-Za-z0-9_./-]+@[0-9a-f]{40}$` — full 40-char SHA, never `@v4`, `@main`, etc. Each `uses:` line carries a sibling `# v<MAJOR>.<MINOR>(.<PATCH>)?` comment immediately before so future updates aren't blind.
- [ ] **AC-2 (concurrency, permissions, trigger surface):** Workflow declares `concurrency: { group: ${{ github.ref }}, cancel-in-progress: true }` (cancellation is load-bearing for CI quota; advisory in implementer notes alone is too weak). Top-level `permissions: contents: read`. The `on:` trigger map's keys are a subset of `{pull_request, push, workflow_dispatch}` — `pull_request_target` and `workflow_run` are explicitly forbidden (the textbook OSS supply-chain attack surface). No job declares a `permissions:` block that *widens* `contents` beyond `read` (job-level `contents: write` is forbidden in Phase 0; `security-events: write` for SARIF is allowed only for jobs that legitimately need it — none in Phase 0).
- [ ] **AC-3 (fence job install discipline, two-step):** The `fence` job's `steps[*].run` text contains exactly the install sequence (a) `pip install -e .` (bare, no extras — *measures* the actual gather-pipeline closure per ADR-0006 §Consequences), then (b) `pip install pytest` (standalone, *after* (a) so the closure measurement is uncontaminated by the harness). The fence job's install steps MUST NOT contain the substrings `[dev]`, `-e .[dev]`, `[agents]`, `[service]`. The job's test step invokes `pytest -q tests/unit/test_pyproject_fence.py`.
- [ ] **AC-4 (fence test file with FIVE tests, all mutation-resistant):** `tests/unit/test_pyproject_fence.py` exists. The fence's name-extraction logic lives in `src/codegenie/_fence.py` (production code) — both the live test and the deliberate-negative tests invoke that function so mutating production kills both classes of test. The tests are:
  - **(a) `test_fence_blocks_known_llm_sdks`** — calls `_fence.scan_installed_distribution()` (which queries `distribution("codewizard-sherpa").requires`, filters out `extra ==` markers, intersects with `_fence.FORBIDDEN_LLM_SDKS`); asserts the intersection is empty. Mutation guard: changing `&` to `|` in production dies here.
  - **(b) `test_forbidden_set_is_exactly_adr_0002_closure`** — asserts `_fence.FORBIDDEN_LLM_SDKS == frozenset({"anthropic", "langgraph", "openai", "langchain", "transformers"})`. Mutation guard: silently dropping `langchain` from the production set fails this.
  - **(c) `test_fence_catches_each_planted_llm_sdk`** — `@pytest.mark.parametrize` over each member of the forbidden set; for each, builds a synthetic `pyproject.toml` text with that SDK in `dependencies`, calls `_fence.parse_runtime_dep_names_from_toml(text)`, intersects with `FORBIDDEN_LLM_SDKS`, asserts intersection equals `{<that-sdk>}`. Mutation guard: any SDK left out of the production scanner's filter kills its parametrized case.
  - **(d) `test_fence_ignores_llm_sdk_when_planted_in_optional_extras`** — the metamorphic complement (replaces the prior tautological scope-axis test). Builds synthetic TOML with `anthropic` planted under `[project.optional-dependencies].agents`, calls `_fence.parse_runtime_dep_names_from_toml(text)`, asserts intersection with `FORBIDDEN_LLM_SDKS` is empty. Mutation guard: a regression that drops the `optional-dependencies` filter (widens fence to extras) re-includes `anthropic` and dies. This is the executable encoding of edge case #15.
  - **(e) `test_fence_helper_strips_version_specifiers_and_extras_markers`** — calls `_fence.parse_runtime_dep_names_from_toml('[project]\ndependencies = ["anthropic>=0.1", "langchain[all]<2.0", "click; python_version >= \\"3.11\\""]\n')` and asserts the returned set is `{"anthropic", "langchain", "click"}` (lowercase, no version specs, no extras brackets, no markers). Mutation guard: a sloppy parser that compares raw `requires` strings against bare names misses every version-specced dep.
- [ ] **AC-5 (`[tool.importlinter]` configuration in `pyproject.toml`):** `pyproject.toml` `[tool.importlinter]` declares `root_packages = ["codegenie"]` (or equivalent `root_package = "codegenie"`) and at least two contracts of `type: forbidden`. Contract A: `source_modules = ["codegenie.cli"]` (the file `src/codegenie/cli.py` — exact module name, NOT `codegenie.cli.**`), `forbidden_modules = ["yaml", "jsonschema", "pydantic", "blake3", "structlog"]`. Contract B: `source_modules = ["codegenie"]` (the package's `__init__.py`), `forbidden_modules = ["yaml", "jsonschema", "pydantic", "blake3", "structlog"]`. (`click` is intentionally allowed at `__init__.py` top level — the CLI entry point requires it; cold-start advisory accepts `click`'s overhead.) AC-9's parser test asserts the contracts are present and well-shaped — proving the config is not just syntactically present but contractually correct.
- [ ] **AC-6 (dedicated `make lint-imports` target invoked by the `lint` CI job):** `Makefile` declares a `lint-imports` target (added to `.PHONY`) whose recipe runs `lint-imports --config pyproject.toml --no-cache` (the `--no-cache` flag defeats stale-cache contract failures). `make lint-imports` exits 0 on the current tree. The `typecheck` target is **NOT** modified — `import-linter` is a structural lint, not a type check, and routes through the `lint` job in CI per the six-job decomposition (`phase-arch-design.md §Testing strategy / CI gates`). The `lint` CI job's recipe invokes `make lint-imports` (verified by AC-9 parser test).
- [ ] **AC-7 (`__init__.py` cold-start: runtime side-effect test + AST fast-guard):** Three tests in `tests/unit/test_cli_cold_start.py`:
  - **(a) `test_importing_codegenie_does_not_load_heavy_modules`** (load-bearing) — spawns a subprocess that runs `import sys, json; pre = set(sys.modules); import codegenie; loaded = set(sys.modules) - pre; print(json.dumps(sorted(loaded)))`; parses stdout; asserts `{"yaml", "jsonschema", "pydantic", "blake3", "structlog"} & loaded == set()`. Mutation guard: a `from .submodule import RepoContext` re-export where `.submodule` top-level imports `yaml` is caught here (the AST scan misses transitive imports).
  - **(b) `test_cli_does_not_top_level_import_heavy_modules`** (fast guard) — AST-walks `src/codegenie/cli.py`'s module-level imports and asserts the forbidden set is excluded. Uses an explicit `pytest.skip("cli.py lands in S4-02; see story §Note")` (NOT a silent `return`) so the deferred-enforcement is visible in `pytest -v` output.
  - **(c) `test_package_init_does_not_top_level_import_heavy_modules`** — same AST scan over `src/codegenie/__init__.py`; this one is operative immediately since `__init__.py` exists from S1-01.
- [ ] **AC-8 (`import-linter` in `[dev]`; `uv.lock` re-locked):** `pyproject.toml`'s `[project.optional-dependencies].dev` list contains `"import-linter"`. `uv.lock` re-generated via `uv lock` and committed (so S1-03 AC-7's `test_uv_lock_is_in_lockstep_with_pyproject_dep_set` stays green). Without this AC the `lint-imports` binary is unavailable in CI and AC-6 fails with `command not found`.
- [ ] **AC-9 (workflow YAML + import-linter config parser test — single file, multiple assertions):** `tests/unit/test_ci_workflow.py` exists, loads `.github/workflows/ci.yml` via `yaml.safe_load`, and asserts (one assertion per test function for clear failure messages):
  - The workflow YAML parses without raising.
  - `set(workflow["jobs"].keys())` equals exactly `{"lint", "typecheck", "test", "security", "docs", "fence"}`.
  - `workflow["concurrency"]["group"] == "${{ github.ref }}"` and `workflow["concurrency"]["cancel-in-progress"] is True`.
  - `workflow["permissions"] == {"contents": "read"}`.
  - `set(workflow["on"].keys()).issubset({"pull_request", "push", "workflow_dispatch"})` AND `"pull_request_target" not in workflow["on"]`.
  - At least one job's `strategy.matrix` carries `python: ["3.11", "3.12"]` AND `os: ["ubuntu-24.04"]`.
  - Every step's `uses:` value across all jobs that contains `/` matches `^[A-Za-z0-9_./-]+@[0-9a-f]{40}$` (full SHA pin). Empty list is also acceptable (no third-party actions).
  - The `fence` job's flattened `run:` text contains `pip install -e .` AND `pip install pytest` AND `pytest -q tests/unit/test_pyproject_fence.py`, and contains *none* of `[dev]`, `[agents]`, `[service]`.
  - The `lint` job's flattened `run:` text contains `make lint-imports` (so AC-6's contract reaches CI).
  - The `security` job's flattened `run:` text contains `pip-audit` AND references `uv.lock`; uses `google/osv-scanner-action` either via `uses:` or invokes `osv-scanner` directly in `run:` (so AC-11 reaches CI).
  - For every job with a `permissions:` block, `permissions.get("contents", "read") == "read"` (no job widens write access).
  - Loads `pyproject.toml`, asserts `[tool.importlinter]` declares `root_packages` (or `root_package`) covering `codegenie`, and that two contracts of `type: forbidden` exist whose `source_modules` cover `codegenie.cli` and `codegenie` (validates AC-5 declaratively without invoking `lint-imports`).
- [ ] **AC-10 (deliberate-negative `lint-imports` canary):** `tests/unit/test_lint_imports_canary.py` exists with two tests:
  - **(a) `test_lint_imports_exits_zero_on_current_tree`** — `subprocess.run([sys.executable, "-m", "importlinter", "--config", "pyproject.toml", "--no-cache"], cwd=PROJECT_ROOT, check=False, capture_output=True, text=True, timeout=30)` exits with returncode 0.
  - **(b) `test_lint_imports_actually_blocks_a_planted_heavy_import`** — writes `src/codegenie/cli.py` (or, if it already exists, snapshots and overwrites) with `import yaml  # planted by validator canary\n`, runs `lint-imports --no-cache`, asserts non-zero exit, restores original content (or `unlink`s the planted file) in a `finally:` block. Mirrors S1-02's `test_ruff_check_rejects_print_in_src_per_phase_arch_logging_strategy` (`tests/unit/test_toolchain_config.py:132-163`). Without this, the `[tool.importlinter]` config could ship with `forbidden_modules: ["nonexistent"]` and every other AC still passes.
- [ ] **AC-11 (`security` job content):** The `security` CI job's recipe invokes both `pip-audit` and `osv-scanner` against `uv.lock`. `pip-audit` is added to `[project.optional-dependencies].dev` (it's pip-installable). `osv-scanner` is a Go binary — installed in CI via `google/osv-scanner-action@<SHA>` (SHA-pinned per AC-1). Severity gating (HIGH/CRITICAL fail, MEDIUM/LOW advisory) per `phase-arch-design.md §Testing strategy / CI gates` job 4 is wired via the action's input flags or `--fail-on=critical,high`. Verified by the `security` substring assertion in AC-9.
- [ ] **AC-12 (docs job path filtering):** The `docs` job runs *only* when files under `docs/**` or `mkdocs.yml` change, honoring the ≤90s p95 walltime advisory (`phase-arch-design.md §Testing strategy / CI gates`, `final-design.md §9`). Implementation choice belongs to the implementer:
  - **Option A:** add `dorny/paths-filter@<SHA>` (SHA-pinned per AC-1) as an early step of a `changes` setup job that sets a `docs_changed` output, then guard the `docs` job with `if: needs.changes.outputs.docs_changed == 'true'`.
  - **Option B:** split the `docs` job into a dedicated workflow file `.github/workflows/docs.yml` triggered on `pull_request` + `paths: ["docs/**", "mkdocs.yml"]`. **If Option B is chosen, AC-9's set-equality on jobs is relaxed to `{lint, typecheck, test, security, fence}` for `ci.yml` and a parallel parser test asserts `docs.yml`'s `paths:` filter.**
  - Whichever option is chosen, AC-9's parser test validates the chosen mechanism explicitly.

## Implementation outline

1. **Extract production helper first.** Author `src/codegenie/_fence.py` with: (a) `FORBIDDEN_LLM_SDKS: frozenset[str] = frozenset({"anthropic", "langgraph", "openai", "langchain", "transformers"})`; (b) `parse_runtime_dep_names_from_toml(toml_text: str) -> set[str]` — uses `tomllib.loads`, extracts `[project].dependencies`, runs each through `packaging.Requirement(req).name.lower()` for spec/extras/marker stripping; (c) `requires_names_from_distribution(name: str = "codewizard-sherpa") -> set[str]` — queries `importlib.metadata.distribution(name).requires`, filters out entries with `extra ==` markers, runs each through `packaging.Requirement(req).name.lower()`; (d) `scan_installed_distribution(name: str = "codewizard-sherpa") -> frozenset[str]` — returns `frozenset(requires_names_from_distribution(name) & FORBIDDEN_LLM_SDKS)`. The `_` prefix marks it private (not part of the public API).
2. **Write the red tests.** All five fence tests in `tests/unit/test_pyproject_fence.py` per the TDD plan (each invokes the production helper). All three cold-start tests in `tests/unit/test_cli_cold_start.py`. The `test_ci_workflow.py` parser tests. The `test_lint_imports_canary.py` deliberate-negative tests. Run; observe failures (workflow doesn't exist, importlinter config doesn't exist, etc.).
3. **Add `import-linter` and `pip-audit` to `[dev]`** in `pyproject.toml`; run `uv lock` and commit `uv.lock` (S1-03 AC-7 lockstep).
4. **Add `[tool.importlinter]` block to `pyproject.toml`** with `root_packages = ["codegenie"]` and two `[[tool.importlinter.contracts]]` entries (one for `source_modules: ["codegenie.cli"]`, one for `source_modules: ["codegenie"]`) of `type: forbidden` listing the five heavy modules. Do **not** scope to `codegenie.cli.**` (per `High-level-impl.md §Risks specific to this step` — over-block warning).
5. **Author `.github/workflows/ci.yml`** with the six jobs. Use `actions/checkout@<SHA>` and `actions/setup-python@<SHA>` pinned by full SHA (run `gh api repos/actions/checkout/commits/v4.1.6 --jq .sha` to resolve a tag → SHA, then add a `# v4.1.6` comment above the `uses:` line). Configure each job's install step: `lint`/`typecheck`/`test`/`docs` install `[dev]`; `security` installs `[dev]` (which now includes `pip-audit`) AND uses `google/osv-scanner-action@<SHA>`; `fence` performs the two-step install (bare `pip install -e .` then `pip install pytest`).
6. **Wire up `make lint-imports`** — append a `lint-imports` target to the existing `Makefile` (and add to `.PHONY`); recipe: `@lint-imports --config pyproject.toml --no-cache`. The `lint` CI job's recipe becomes `make lint && make lint-imports`. `make typecheck` is **untouched**.
7. **Wire AC-12's path filter** for the `docs` job (Option A: add a `changes` setup job using `dorny/paths-filter@<SHA>`; Option B: split into `.github/workflows/docs.yml`). Document the choice in the workflow's leading comment block.
8. **Run `lint-imports` locally** and confirm green; run `pytest tests/unit/test_pyproject_fence.py tests/unit/test_cli_cold_start.py tests/unit/test_ci_workflow.py tests/unit/test_lint_imports_canary.py -q` and confirm green.
9. Open the PR; verify all six jobs run; if any fail, ensure it's only `test` (because Phase 0 hasn't written real tests yet — `--cov-fail-under=0` carve-out per S1-02 Notes; document in PR body).

## TDD plan — red / green / refactor

### Red — write the failing tests first

Four test files. Each one is mutation-resistant (every test dies under at least one obviously-wrong production change). The fence tests invoke the production helper `src/codegenie/_fence.py` so the deliberate-negative tests cannot pass when production is broken.

#### Test file 1: `tests/unit/test_pyproject_fence.py`

```python
# tests/unit/test_pyproject_fence.py
"""Fence: enforce no-LLM-in-gather (ADR-0002, production ADR-0005).

The deliberate-negative tests (c, d) invoke the SAME production code path
as the live test (a) — see codegenie._fence. Mutating the scanner kills both.
"""
from __future__ import annotations

import pytest

from codegenie._fence import (
    FORBIDDEN_LLM_SDKS,
    parse_runtime_dep_names_from_toml,
    scan_installed_distribution,
)

EXPECTED_FORBIDDEN_SET = frozenset(
    {"anthropic", "langgraph", "openai", "langchain", "transformers"}
)


def test_fence_blocks_known_llm_sdks() -> None:
    # The live check against the actually-installed distribution.
    # Mutation guard: changing & to | in production dies here on a non-empty `dev`.
    leaked = scan_installed_distribution("codewizard-sherpa")
    assert leaked == frozenset(), (
        f"LLM SDK leaked into [project].dependencies: {leaked}. "
        f"Route LLM deps through [project.optional-dependencies].agents per ADR-0006."
    )


def test_forbidden_set_is_exactly_adr_0002_closure() -> None:
    # Mutation guard: silently dropping `langchain` from production dies here.
    assert FORBIDDEN_LLM_SDKS == EXPECTED_FORBIDDEN_SET


@pytest.mark.parametrize("sdk", sorted(EXPECTED_FORBIDDEN_SET))
def test_fence_catches_each_planted_llm_sdk(sdk: str) -> None:
    # Plant ONE forbidden SDK at a time in synthetic deps; the production
    # parser MUST see it. Mutation guard: a bug that filters out one SDK
    # kills its parametrized case (5 cases, 5 independent mutation guards).
    synthetic = (
        f'[project]\nname = "fake"\n'
        f'dependencies = ["click", "{sdk}>=0.1"]\n'
    )
    names = parse_runtime_dep_names_from_toml(synthetic)
    assert names & FORBIDDEN_LLM_SDKS == {sdk}, (
        f"Fence check is broken — failed to catch planted `{sdk}`. Got: {names}"
    )


def test_fence_ignores_llm_sdk_when_planted_in_optional_extras() -> None:
    # Metamorphic complement: the SAME SDK in `optional-dependencies` MUST be
    # ignored (edge case #15). Mutation guard: a regression that drops the
    # `extra ==` filter (widens the fence to extras) re-includes anthropic and dies.
    synthetic = (
        '[project]\nname = "fake"\ndependencies = ["click"]\n'
        '[project.optional-dependencies]\nagents = ["anthropic>=0.1"]\n'
    )
    names = parse_runtime_dep_names_from_toml(synthetic)
    assert names & FORBIDDEN_LLM_SDKS == set(), (
        f"Fence widened scope to optional-dependencies (edge case #15 violation). "
        f"Got: {names & FORBIDDEN_LLM_SDKS}"
    )


def test_fence_helper_strips_version_specifiers_and_extras_markers() -> None:
    # Mutation guard: a sloppy parser that compares raw `requires` strings
    # against bare names misses every version-specced or extras-bracketed dep.
    synthetic = (
        '[project]\nname = "fake"\n'
        'dependencies = [\n'
        '  "anthropic>=0.1",\n'
        '  "langchain[all]<2.0",\n'
        '  "click; python_version >= \\"3.11\\"",\n'
        ']\n'
    )
    names = parse_runtime_dep_names_from_toml(synthetic)
    assert names == {"anthropic", "langchain", "click"}, (
        f"Parser must strip version specs / extras / markers. Got: {names}"
    )
```

The `test_fence_blocks_known_llm_sdks` test fails before `_fence.py` exists (`ImportError`); after the production helper lands and the dist is installed, it passes. Commit the failing test as the red marker.

#### Test file 2: `tests/unit/test_cli_cold_start.py`

```python
# tests/unit/test_cli_cold_start.py
"""Cold-start invariant: `import codegenie` must not transitively load heavy modules.

Test (a) is the load-bearing one — it spawns a subprocess to measure REAL runtime
side-effects. Tests (b)/(c) are fast AST guards.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_HEAVY = {"yaml", "jsonschema", "pydantic", "blake3", "structlog"}


def test_importing_codegenie_does_not_load_heavy_modules() -> None:
    """LOAD-BEARING. Mutation guard: a `from .submodule import X` re-export
    where `.submodule` top-level imports `yaml` is caught HERE (the AST scan misses it)."""
    probe = (
        "import sys, json; "
        "pre = set(sys.modules); "
        "import codegenie; "
        "loaded = set(sys.modules) - pre; "
        "print(json.dumps(sorted(loaded)))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True, check=True, timeout=10,
        cwd=PROJECT_ROOT,
    )
    loaded = set(json.loads(result.stdout))
    leaked = FORBIDDEN_HEAVY & loaded
    assert leaked == set(), (
        f"Importing `codegenie` transitively loaded forbidden heavy modules: {leaked}. "
        f"Move the offending import inside a function body. "
        f"See phase-arch-design.md §Component design — CLI."
    )


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in tree.body:  # module-level only
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def test_cli_does_not_top_level_import_heavy_modules() -> None:
    cli = PROJECT_ROOT / "src" / "codegenie" / "cli.py"
    if not cli.exists():
        pytest.skip(
            "cli.py lands in S4-02 (vertical slice); see story S1-05 §Note on the "
            "cli-targeted import-linter contract. AC-10's deliberate-negative canary "
            "exercises the import-linter contract until then."
        )
    leaked = _top_level_imports(cli) & FORBIDDEN_HEAVY
    assert leaked == set(), (
        f"cli.py must defer heavy imports inside command bodies; leaked: {leaked}."
    )


def test_package_init_does_not_top_level_import_heavy_modules() -> None:
    init = PROJECT_ROOT / "src" / "codegenie" / "__init__.py"
    leaked = _top_level_imports(init) & FORBIDDEN_HEAVY
    assert leaked == set(), (
        f"codegenie/__init__.py must stay light (AST scan); leaked: {leaked}. "
        f"NOTE: this AST scan is a fast guard — the load-bearing test is "
        f"test_importing_codegenie_does_not_load_heavy_modules above."
    )
```

#### Test file 3: `tests/unit/test_ci_workflow.py`

```python
# tests/unit/test_ci_workflow.py
"""Parser test: assert .github/workflows/ci.yml + [tool.importlinter] match the
contractual properties of S1-05 ACs 1, 2, 3, 5, 6, 11, 12.

Without this test the workflow's enumerated contents (six jobs, matrix, SHA-pinning,
concurrency, permissions) are asserted only by code review — repeating S1-04's
"enumerate-then-test-zero" defect.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
REQUIRED_JOBS = {"lint", "typecheck", "test", "security", "docs", "fence"}
ALLOWED_TRIGGERS = {"pull_request", "push", "workflow_dispatch"}
SHA_PIN_RE = re.compile(r"^[A-Za-z0-9_./-]+@[0-9a-f]{40}$")


def _wf() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def _flatten_run(job: dict) -> str:
    return "\n".join(s.get("run", "") for s in job.get("steps", []) if "run" in s)


def test_ci_workflow_parses() -> None:
    assert WORKFLOW.exists(), "ci.yml must exist (AC-1)"
    _wf()  # raises on parse failure


def test_ci_workflow_declares_exactly_six_required_jobs() -> None:
    # Set equality — extras and missing both fail.
    # If AC-12 Option B was chosen, `docs` lives in docs.yml; the assertion
    # below is then `REQUIRED_JOBS - {"docs"}`. Implementer adjusts.
    assert set(_wf()["jobs"].keys()) == REQUIRED_JOBS, (
        f"jobs must be exactly {REQUIRED_JOBS}; got {set(_wf()['jobs'].keys())}"
    )


def test_ci_workflow_concurrency_cancels_old_runs_on_same_ref() -> None:
    conc = _wf()["concurrency"]
    assert conc["group"] == "${{ github.ref }}"
    assert conc.get("cancel-in-progress") is True, (
        "AC-2 mandates cancel-in-progress: true (CI quota)"
    )


def test_ci_workflow_top_level_permissions_are_read_only() -> None:
    assert _wf()["permissions"] == {"contents": "read"}


def test_ci_workflow_triggers_exclude_pull_request_target() -> None:
    triggers = _wf()["on"]
    keys = set(triggers.keys()) if isinstance(triggers, dict) else set(triggers)
    assert "pull_request_target" not in keys, (
        "pull_request_target grants write tokens to fork PRs; never enable in Phase 0"
    )
    assert "workflow_run" not in keys
    assert keys.issubset(ALLOWED_TRIGGERS), (
        f"unexpected triggers {keys - ALLOWED_TRIGGERS}"
    )


def test_ci_workflow_pins_python_311_312_on_ubuntu_2404() -> None:
    matrices = [
        j["strategy"]["matrix"] for j in _wf()["jobs"].values()
        if isinstance(j, dict) and "strategy" in j and "matrix" in j["strategy"]
    ]
    assert any(
        set(m.get("python", [])) == {"3.11", "3.12"}
        and m.get("os", []) == ["ubuntu-24.04"]
        for m in matrices
    ), f"no job pins the contractual matrix; got: {matrices}"


def test_every_third_party_action_is_sha_pinned_not_tag_pinned() -> None:
    uses_values: list[str] = []
    for job in _wf()["jobs"].values():
        for step in job.get("steps", []):
            if "uses" in step and "/" in step["uses"]:
                uses_values.append(step["uses"])
    offenders = [u for u in uses_values if not SHA_PIN_RE.match(u)]
    assert offenders == [], (
        f"these `uses:` lines are tag/branch-pinned, not SHA-pinned: {offenders}"
    )


def test_fence_job_install_is_two_step_and_excludes_dev_extras() -> None:
    fence = _wf()["jobs"]["fence"]
    runs = _flatten_run(fence)
    assert "pip install -e ." in runs
    assert "pip install pytest" in runs, (
        "fence must install pytest STANDALONE after bare `pip install -e .` "
        "so the closure measurement is uncontaminated (ADR-0006 §Consequences)"
    )
    for forbidden in ("[dev]", "[agents]", "[service]", "-e .[dev]"):
        assert forbidden not in runs, (
            f"fence job MUST NOT install {forbidden} — contaminates closure scope"
        )
    assert "pytest -q tests/unit/test_pyproject_fence.py" in runs


def test_lint_job_invokes_make_lint_imports() -> None:
    runs = _flatten_run(_wf()["jobs"]["lint"])
    assert "make lint-imports" in runs, (
        "AC-6 contract reaches CI via the `lint` job, not `typecheck`"
    )


def test_security_job_invokes_pip_audit_and_osv_scanner_against_uv_lock() -> None:
    sec = _wf()["jobs"]["security"]
    runs = _flatten_run(sec)
    uses_lines = [s.get("uses", "") for s in sec.get("steps", [])]
    assert "pip-audit" in runs
    assert "uv.lock" in runs
    osv_via_action = any("google/osv-scanner-action" in u for u in uses_lines)
    osv_via_run = "osv-scanner" in runs
    assert osv_via_action or osv_via_run, (
        "AC-11: security job must invoke osv-scanner (action or direct run)"
    )


def test_no_job_widens_contents_permission_beyond_read() -> None:
    for name, job in _wf()["jobs"].items():
        perms = job.get("permissions", {})
        if isinstance(perms, dict):
            assert perms.get("contents", "read") == "read", (
                f"job {name} elevates contents perm: {perms}"
            )


def test_docs_job_path_filtering_is_wired_per_ac_12() -> None:
    # Either Option A (uses dorny/paths-filter in some `changes`-style setup job
    # AND `docs` job has `if:`) OR Option B (docs.yml exists with paths filter).
    docs_yml = PROJECT_ROOT / ".github" / "workflows" / "docs.yml"
    if docs_yml.exists():
        # Option B
        cfg = yaml.safe_load(docs_yml.read_text())
        triggers = cfg["on"]
        if isinstance(triggers, dict):
            paths = triggers.get("pull_request", {}).get("paths") or \
                triggers.get("push", {}).get("paths")
        else:
            paths = None
        assert paths and {"docs/**", "mkdocs.yml"}.issubset(set(paths)), (
            f"docs.yml must filter on docs/** + mkdocs.yml; got: {paths}"
        )
        return
    # Option A
    wf = _wf()
    uses_paths_filter = any(
        "dorny/paths-filter" in s.get("uses", "")
        for j in wf["jobs"].values() for s in j.get("steps", [])
    )
    docs_has_if = "if" in wf["jobs"].get("docs", {})
    assert uses_paths_filter and docs_has_if, (
        "AC-12 requires either docs.yml with paths filter OR dorny/paths-filter + docs.if"
    )


# ---- import-linter config (validates AC-5 declaratively) ----

def _importlinter_cfg() -> dict:
    return tomllib.loads(PYPROJECT.read_text())["tool"]["importlinter"]


def test_importlinter_config_root_packages_includes_codegenie() -> None:
    cfg = _importlinter_cfg()
    roots = cfg.get("root_packages") or [cfg["root_package"]]
    assert "codegenie" in roots


def test_importlinter_has_two_forbidden_contracts_for_cli_and_init() -> None:
    contracts = _importlinter_cfg()["contracts"]
    forbidden = [c for c in contracts if c.get("type") == "forbidden"]
    sources_per_contract = [set(c.get("source_modules", [])) for c in forbidden]
    expected_heavy = {"yaml", "jsonschema", "pydantic", "blake3", "structlog"}
    cli_contract = next(
        (c for c, s in zip(forbidden, sources_per_contract) if "codegenie.cli" in s),
        None,
    )
    init_contract = next(
        (c for c, s in zip(forbidden, sources_per_contract) if s == {"codegenie"}),
        None,
    )
    assert cli_contract is not None, "missing forbidden contract for codegenie.cli"
    assert init_contract is not None, "missing forbidden contract for codegenie (init)"
    for c in (cli_contract, init_contract):
        assert set(c["forbidden_modules"]) >= expected_heavy, (
            f"contract under-blocks: {set(c['forbidden_modules'])}"
        )
```

#### Test file 4: `tests/unit/test_lint_imports_canary.py`

```python
# tests/unit/test_lint_imports_canary.py
"""Deliberate-negative canary for the [tool.importlinter] config.

Mirrors S1-02's test_ruff_check_rejects_print_in_src_per_phase_arch_logging_strategy
(tests/unit/test_toolchain_config.py:132-163). Without this canary, the config could
ship with `forbidden_modules: ["nonexistent"]` and every other AC still passes.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLI = PROJECT_ROOT / "src" / "codegenie" / "cli.py"


def _run_lint_imports() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "importlinter", "--config", "pyproject.toml", "--no-cache"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=False, timeout=30,
    )


def test_lint_imports_exits_zero_on_current_tree() -> None:
    result = _run_lint_imports()
    assert result.returncode == 0, (
        f"lint-imports failed on current tree: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_lint_imports_actually_blocks_a_planted_heavy_import() -> None:
    """Plant `import yaml` in cli.py, run lint-imports, assert non-zero exit, restore."""
    original = CLI.read_text() if CLI.exists() else None
    CLI.parent.mkdir(parents=True, exist_ok=True)
    CLI.write_text("import yaml  # planted by validator canary — DO NOT COMMIT\n")
    try:
        result = _run_lint_imports()
        assert result.returncode != 0, (
            f"lint-imports failed to catch planted `import yaml` in cli.py — "
            f"the [tool.importlinter] config is misconfigured. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    finally:
        if original is not None:
            CLI.write_text(original)
        else:
            CLI.unlink(missing_ok=True)
```

### Green — make it pass

- Implement `src/codegenie/_fence.py` with `FORBIDDEN_LLM_SDKS`, `parse_runtime_dep_names_from_toml`, `requires_names_from_distribution`, `scan_installed_distribution`. Use `packaging.Requirement(req).name.lower()` for parsing — never substring-split.
- Add `import-linter` and `pip-audit` to `pyproject.toml` `[project.optional-dependencies].dev`. Run `uv lock` and commit `uv.lock`.
- Add `[tool.importlinter]` to `pyproject.toml` with `root_packages = ["codegenie"]` and two `forbidden` contracts (one each for `codegenie.cli` and `codegenie`), each blocking the five heavy modules.
- Append a `lint-imports` target to `Makefile` (and add to `.PHONY`); recipe `@lint-imports --config pyproject.toml --no-cache`.
- Author `.github/workflows/ci.yml` with the six jobs, the matrix, SHA-pinned actions, the two-step `fence` install, the `lint` job's `make lint && make lint-imports` recipe, the `security` job's `pip-audit` + `osv-scanner` invocations, and the AC-12 docs path filter.
- Verify locally: `pip install -e .[dev]`, `make lint-imports`, `pytest tests/unit/test_pyproject_fence.py tests/unit/test_cli_cold_start.py tests/unit/test_ci_workflow.py tests/unit/test_lint_imports_canary.py -q`.
- Push and watch the six jobs run; `lint`, `docs`, `fence` are expected green on the Step 1 PR; `typecheck` should be green (S1-02 already ensured strict-mypy clean on S1-01 files); `test` may be carve-out-bypassed per S1-02 Notes (`--cov-fail-under=0` on the Step 1 PR only).

### Refactor — clean up

- Add a heading comment at the top of `.github/workflows/ci.yml`: `# Six-job CI: lint, typecheck, test, security, docs, fence. fence is the load-bearing gate (ADR-0002). Do not disable without ADR amendment.`
- Confirm each `actions/...@<SHA>` line has a sibling `# v<MAJOR>.<MINOR>(.<PATCH>)?` comment immediately above so future updates aren't blind. (AC-1's regex enforces presence of the SHA pin; the version comment is also asserted-by-convention via the CI-workflow test if you choose to add a regex check on the raw YAML text — recommended.)
- Add `# CODEOWNERS-route this file when CODEOWNERS lands in S5-02; pin to phase-arch-design.md §Edge cases #15` near the `fence` job; the actual `CODEOWNERS` file lands in S5-02 but the marker primes the convention.
- Re-confirm AC-2 / AC-9 hold: no job has `pull_request_target` / `workflow_run`; no job widens `contents` beyond `read`; `permissions: contents: read` is at workflow level.
- Re-confirm AC-12: the `docs` job is path-filtered (Option A or B). If Option B, document the `docs.yml` split in `ci.yml`'s leading comment block.
- Document the `--cov-fail-under=0` carve-out in the PR body under a heading "Coverage carve-out" referencing S4-04 cutover; if the carve-out is set in `ci.yml` rather than per-PR, add a `# TODO(S4-04): remove --cov-fail-under=0` comment alongside it.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/_fence.py` | **New file (production code)** — `FORBIDDEN_LLM_SDKS` + name-extraction helpers. The single source of truth that both the live and deliberate-negative tests invoke (kills the prior tautology smell). |
| `.github/workflows/ci.yml` | **New file** — the six-job CI pipeline. |
| `.github/workflows/docs.yml` | **(Conditional, AC-12 Option B)** — dedicated docs workflow with `paths:` filter. Skip if Option A (dorny/paths-filter) is chosen. |
| `tests/unit/test_pyproject_fence.py` | **New file** — five mutation-resistant fence tests (live + set-equality + parametrized planted SDKs + metamorphic optional-extras + parser strip-test). |
| `tests/unit/test_cli_cold_start.py` | **New file** — runtime-side-effect test (subprocess + `sys.modules`) plus AST fast-guards for `cli.py` and `__init__.py`. Replaces and supersedes the prior `test_import_linter_blocks_heavy_from_cli.py`. |
| `tests/unit/test_ci_workflow.py` | **New file** — workflow YAML + `[tool.importlinter]` parser test (twelve assertions). Closes the S1-04 enumerate-then-test-zero pattern. |
| `tests/unit/test_lint_imports_canary.py` | **New file** — deliberate-negative canary mirroring S1-02's ruff `print(` canary. Plants `import yaml` in `cli.py`, runs `lint-imports`, asserts non-zero, restores. |
| `pyproject.toml` | Add `import-linter` and `pip-audit` to `[project.optional-dependencies].dev`; add `[tool.importlinter]` with `root_packages = ["codegenie"]` and two `forbidden` contracts. |
| `Makefile` | **Required** — add a `lint-imports` target (`@lint-imports --config pyproject.toml --no-cache`) and add it to `.PHONY`. Do **not** modify `typecheck`. |
| `uv.lock` | **Re-generate via `uv lock`** after adding `import-linter` + `pip-audit` to `[dev]`; commit alongside `pyproject.toml` (S1-03 AC-7 lockstep). |

## Out of scope

- **`CODEOWNERS` for the fence test file** — handled by S5-02; this story merely names the convention in a comment.
- **Performance canaries** (`tests/bench/`) — handled by S5-01; explicitly advisory-only per `phase-arch-design.md §Tradeoffs` row 12.
- **The `lint` and `docs` jobs' actual lint/docs commands** — those run `make lint` / `make docs`; the Makefile targets ship in S1-03.
- **Adversarial AST scans** (`tests/adv/test_no_shell_true.py`, etc.) — handled by S2-02 and S4-05.
- **GitHub Actions caching of `pip` / `uv`** — leave for now; if walltime drifts above the ≤ 90s p95 advisory, S5-01's bench layer adds the cache step.
- **Renovate / Dependabot configuration** — S5-02 ships `.github/dependabot.yml`.
- **Issue templates and PR template** — S5-02 ships these.

## Notes for the implementer

- The fence is **load-bearing**. If you find yourself "simplifying" any part of `tests/unit/test_pyproject_fence.py` or `src/codegenie/_fence.py`, stop and re-read `phase-arch-design.md §Edge cases #15` and `High-level-impl.md §Step 1 — Risks specific to this step`. The deliberate-negative parametrized tests (`test_fence_catches_each_planted_llm_sdk` + `test_fence_ignores_llm_sdk_when_planted_in_optional_extras`) are *not* optional — together they catch "the fence check itself silently broke" in both directions (false-negative on planted SDK, false-positive on widened scope). They are mutation-resistant only because they invoke the SAME `_fence.parse_runtime_dep_names_from_toml` helper that production uses; do not duplicate the parsing in-test.
- Per ADR-0002 §Tradeoffs, the fence's scope is `dependencies` **only**. `test_fence_ignores_llm_sdk_when_planted_in_optional_extras` asserts this metamorphically (plant in `[project.optional-dependencies].agents`, assert empty intersection); do not "broaden" the fence to include `[project.optional-dependencies]` without an ADR amendment. The `dev` extra is *allowed* to transitively contain LLM-flavored plugins (e.g., a hypothetical mkdocs LLM plugin); broadening the fence breaks `dev` install across the contributor base.
- The intersection set `{anthropic, langgraph, openai, langchain, transformers}` is a contract. Adding a new SDK (e.g., `boto3-bedrock` once Bedrock lands) is a one-line PR with mandatory review per ADR-0002 §Consequences.
- `import-linter`'s `forbidden` contract syntax is in its docs at https://import-linter.readthedocs.io. Use `type: forbidden` with `source_modules` and `forbidden_modules`. Resist using `type: layers` for Phase 0 — overkill at this surface size.
- The `import-linter` contracts should be **scoped to the exact module names**: `codegenie.cli` (the file `src/codegenie/cli.py`) and `codegenie` (the package's `__init__.py`). Do **not** scope to `codegenie.cli.**` — that would block heavy imports inside `cli` sub-modules (and cli.py is a single file in Phase 0, so the sub-module case doesn't apply, but per `High-level-impl.md §Risks specific to this step` the convention prevents Phase-1 over-blocking).
- The CI matrix is `python: ["3.11", "3.12"]` × `os: [ubuntu-24.04]`. Per `phase-arch-design.md §Non-goals` #14, **do not add** macOS or Windows runners — the contributor pool runs macOS for dev and Linux for CI, and the surface stays narrow.
- All GitHub Actions third-party uses must be SHA-pinned. The `actions/checkout` and `actions/setup-python` SHAs change with releases — when you pin them, leave a `# v4.x.y` comment so future updates aren't blind. Per `phase-arch-design.md §Testing strategy / CI gates`, this is non-negotiable.
- The `concurrency: group: ${{ github.ref }}` setting ensures only one CI run per PR ref at a time; new pushes cancel older runs. Add `cancel-in-progress: true` so canceled runs don't burn the CI quota.
- `permissions: contents: read` at the workflow level is the *default deny* posture. Individual jobs may need narrower permissions (e.g., `security` may need `security-events: write` to upload SARIF later); leave that for the phase that introduces SARIF (Phase 3+) and keep Phase 0 at strict read-only.
- The Step 1 PR's `test` job will fail under the wired `--cov-fail-under=85` because the tree is mostly empty. Per S1-02 Notes, document the carve-out in the PR body and pass `--cov-fail-under=0` *only* on the Step 1 PR's CI invocation; the gate goes live for real in S4-04.
- `test_cli_does_not_top_level_import_heavy_modules` (in `test_cli_cold_start.py`) uses an explicit `pytest.skip("cli.py lands in S4-02 ...")` — *not* a silent `return` — when `cli.py` doesn't yet exist. This makes the deferred enforcement visible in `pytest -v` output (1 skipped, not silently passed). It becomes load-bearing the moment S4-02 lands `cli.py`. In the meantime, the *operative* enforcement of the cli-targeted contract is `test_lint_imports_actually_blocks_a_planted_heavy_import` (AC-10) — that test plants `import yaml` in a fixture `cli.py`, runs `lint-imports`, asserts non-zero exit, and restores. So the contract is exercised today even though no production `cli.py` ships in this story.
- **Why a production helper (`src/codegenie/_fence.py`) instead of test-local logic?** The prior version of this story duplicated the parsing logic inside `test_fence_catches_planted_anthropic_dep`, then asserted on its own arithmetic — meaning the test could not detect a broken production scanner. By extracting to `_fence.py` and having both the live test and all four planted/metamorphic tests invoke that helper, mutation-killing is real: change `&` to `|` in production and `test_fence_blocks_known_llm_sdks` dies; drop the `extra ==` filter and `test_fence_ignores_llm_sdk_when_planted_in_optional_extras` dies; drop a SDK from `FORBIDDEN_LLM_SDKS` and both `test_forbidden_set_is_exactly_adr_0002_closure` AND the corresponding parametrized case die.
- The `lint` job's recipe is `make lint && make lint-imports` — *both*, in that order. Putting `lint-imports` under `make typecheck` was rejected because it muddles the six-job decomposition (`phase-arch-design.md §Testing strategy / CI gates`): a `lint-imports` failure should surface as a `lint` job failure, not a `typecheck` failure. Do not bundle them.
- `--no-cache` on `lint-imports`: the import-linter cache keys on file mtimes; without `--no-cache`, an edit to `pyproject.toml` that drops a forbidden module without touching analyzed source files can serve a stale "ok" result. Always pass `--no-cache` in CI and in the Makefile target.
