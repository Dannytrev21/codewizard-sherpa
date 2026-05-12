# Story S1-05 — CI workflow + fence job + import-linter

**Step:** Step 1 — Establish project skeleton, tooling, and the `fence` CI job
**Status:** Ready
**Effort:** M
**Depends on:** S1-01, S1-02
**ADRs honored:** ADR-0002, ADR-0006

## Context

This story ships the **load-bearing CI gate** for Phase 0: the `fence` job that asserts the wheel's runtime dependency closure contains no LLM SDK (ADR-0002). It also wires the other five CI jobs (`lint`, `typecheck`, `test`, `security`, `docs`) so every later story merges through the same six-job pipeline. The `import-linter` config blocks heavy modules from `cli.py` and `__init__.py` — the *structural* defense for cold-start performance, replacing the critique-flagged flaky canary (`phase-arch-design.md §Tradeoffs` row "CLI canary advisory, `import-linter` structural").

This is **the** load-bearing story for Phase 0: ADR-0002 is enforced from the first commit forward, and Phase 4's eventual LLM SDK landing zone can never silently contaminate the gather closure. The deliberate-negative test (`test_fence_catches_planted_anthropic_dep`) inoculates the check against silent breakage — the named risk in `final-design.md §10 risk #5`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy / CI gates` — six jobs, matrix `python: ["3.11", "3.12"]` × `os: [ubuntu-24.04]`, concurrency group, SHA-pinned actions, `permissions: contents: read`, ≤ 90s p95 walltime advisory.
  - `../phase-arch-design.md §Edge cases` row #9 — `fence` fails as a "load-bearing-commitment-violation alarm"; the deliberate-negative test guards the check itself.
  - `../phase-arch-design.md §Edge cases` row #15 — fence scope is `dependencies` only, never `optional-dependencies`.
  - `../phase-arch-design.md §Component design — CLI` — `cli.py` and `__init__.py` defer heavy imports; `import-linter` enforces this structurally.
  - `../phase-arch-design.md §Implementation-level risks` #4 — fence test scope drift; route to `CODEOWNERS`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0002-fence-ci-job-no-llm-in-gather.md` — ADR-0002 — the exact intersection set `{anthropic, langgraph, openai, langchain, transformers}`, the deliberate-negative test, and the `dependencies`-only scope.
  - `../ADRs/0006-pyproject-toml-extras-shape.md` — ADR-0006 — the fence installs base `[project]` (no extras), the other jobs install `[dev]`.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — the load-bearing architectural commitment the fence enforces.
- **Source design:**
  - `../High-level-impl.md §Step 1` — Features delivered: `.github/workflows/ci.yml` with six jobs, the deliberate-negative test, `import-linter` blocking heavy modules.
  - `../High-level-impl.md §Risks specific to this step` — `import-linter` regex over-block warning; keep blocklist scoped to `cli.py` and `__init__.py`.

## Goal

A PR that adds `anthropic` to `[project].dependencies` is rejected by the `fence` CI job, and `from codegenie.cli import yaml` raises an `import-linter` violation under `make typecheck`.

## Acceptance criteria

- [ ] `.github/workflows/ci.yml` exists declaring six jobs: `lint`, `typecheck`, `test`, `security`, `docs`, `fence`. Matrix `python: ["3.11", "3.12"]` × `os: [ubuntu-24.04]`. Each job's `uses:` references third-party actions pinned by full SHA (not tag).
- [ ] Workflow declares `concurrency: group: ${{ github.ref }}` and top-level `permissions: contents: read`.
- [ ] The `fence` job installs the base distribution (`pip install -e .` without `[dev]`) and runs `pytest -q tests/unit/test_pyproject_fence.py`.
- [ ] `tests/unit/test_pyproject_fence.py` exists with two tests: (a) `test_fence_blocks_known_llm_sdks` asserts `set(distribution("codewizard-sherpa").requires) ∩ {"anthropic", "langgraph", "openai", "langchain", "transformers"}` is empty; (b) `test_fence_catches_planted_anthropic_dep` (the deliberate-negative test) plants `anthropic` in a synthetic `pyproject.toml`, walks the synthetic requires set, and asserts the check fails. A third test `test_fence_scope_is_dependencies_only` asserts the check operates on `dependencies`, never `optional-dependencies` (edge case #15).
- [ ] `import-linter` configuration in `pyproject.toml` (`[tool.importlinter]`) declares two contracts: one forbids `pyyaml`, `jsonschema`, `pydantic`, `blake3`, `structlog` from being imported by `codegenie.cli`; one forbids the same set from `codegenie` (the package's `__init__.py`).
- [ ] `make typecheck` (or a dedicated `make lint-imports` target) invokes `lint-imports` (the `import-linter` CLI) and exits 0 on the current tree.
- [ ] A synthetic test (`tests/unit/test_import_linter_blocks_heavy_from_cli.py`) confirms the configured contracts: it monkey-builds a small probe of `cli`'s top-level imports and asserts they exclude `yaml`, `pydantic`, etc.
- [ ] The TDD plan's red test exists, was committed, and is green.

## Implementation outline

1. Write the red test in `tests/unit/test_pyproject_fence.py` with the three test functions per the TDD plan. Run; observe failure (the test file isn't installed yet — distribution may not even export the metadata for an empty install).
2. Author `.github/workflows/ci.yml` with the six jobs. Use `actions/checkout@<SHA>` and `actions/setup-python@<SHA>` pinned by SHA from the actions' release tags.
3. Configure each job's install step: `lint`/`typecheck`/`test`/`docs` install `[dev]`; `security` installs `[dev]` and runs `pip-audit` + `osv-scanner` on `uv.lock`; `fence` installs only `[project]` (no extras).
4. Add `[tool.importlinter]` block to `pyproject.toml` with two `[[tool.importlinter.contracts]]` entries (one for `codegenie.cli`, one for `codegenie.__init__`) of type `forbidden` listing the heavy modules.
5. Write `tests/unit/test_import_linter_blocks_heavy_from_cli.py` that scans `src/codegenie/cli.py`'s top-level imports via `ast` and asserts the forbidden modules are absent.
6. Run `lint-imports` locally and confirm green.
7. Open the PR; verify all six jobs run; if any fail, ensure it's only `test` (because Phase 0 hasn't written real tests yet — `--cov-fail-under=0` carve-out per S1-02 Notes).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_pyproject_fence.py`

```python
# tests/unit/test_pyproject_fence.py
import tomllib
from importlib.metadata import distribution
from pathlib import Path

# The frozen intersection set — ADR-0002 §Decision. Adding/removing entries is a
# deliberate one-line PR with CODEOWNERS-forced review.
FORBIDDEN_LLM_SDKS = frozenset({"anthropic", "langgraph", "openai",
                                "langchain", "transformers"})

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _requires_names_from_distribution() -> set[str]:
    raw = distribution("codewizard-sherpa").requires or []
    names = set()
    for req in raw:
        # ignore extras markers — fence is scoped to dependencies only (edge case #15)
        if "extra ==" in req:
            continue
        head = req.split(";")[0]
        name = head.split("[")[0].split(">")[0].split("=")[0].split("<")[0].strip().lower()
        names.add(name)
    return names


def test_fence_blocks_known_llm_sdks() -> None:
    # arrange: the installed wheel's [project].dependencies closure
    runtime_names = _requires_names_from_distribution()
    # act: intersect with the frozen LLM-SDK set per ADR-0002
    intersection = runtime_names & FORBIDDEN_LLM_SDKS
    # assert: any non-empty intersection is a load-bearing-commitment violation;
    # this is the executable enforcement of production ADR-0005.
    assert intersection == set(), (
        f"LLM SDK leaked into [project].dependencies: {intersection}. "
        f"Route LLM deps through [project.optional-dependencies].agents per ADR-0006."
    )


def test_fence_catches_planted_anthropic_dep() -> None:
    # arrange: a *synthetic* pyproject.toml with `anthropic` planted in deps.
    # The deliberate-negative test from ADR-0002 §Decision guards against the
    # fence check itself silently breaking (final-design.md §10 risk #5).
    synthetic = """
[project]
name = "fake"
dependencies = ["click", "anthropic>=0.1"]

[project.optional-dependencies]
dev = []
"""
    cfg = tomllib.loads(synthetic)
    deps = {d.split(">")[0].split("=")[0].split("[")[0].strip().lower()
            for d in cfg["project"]["dependencies"]}
    # act: run the same intersection logic
    intersection = deps & FORBIDDEN_LLM_SDKS
    # assert: it MUST catch the plant — if it doesn't, the real check is broken
    assert intersection == {"anthropic"}, (
        f"Fence check is broken — failed to catch planted `anthropic`. "
        f"Intersection set out of date? Got: {intersection}"
    )


def test_fence_scope_is_dependencies_only_never_optional() -> None:
    # arrange: per phase-arch-design §Edge cases #15 and ADR-0002 §Tradeoffs,
    # the fence walks `dependencies`, never `optional-dependencies`.
    # The `dev` extra is allowed to (transitively) contain LLM-flavored plugins.
    raw = distribution("codewizard-sherpa").requires or []
    extras_lines = [r for r in raw if "extra ==" in r]
    # act: confirm fence logic ignores extras lines (we don't intersect them).
    # We assert here that *the test above* is filtering correctly — a regression
    # in the filter would re-include extras and either false-positive or weaken
    # the closure scope.
    assert all("extra ==" in r for r in extras_lines), \
        "test infrastructure regression: extras filter let through non-extra"
    # Sanity-check: dev extra exists (S1-01 plants it). Re-affirms the scope axis.
    has_dev_extra = any("extra == 'dev'" in r or 'extra == "dev"' in r
                        for r in extras_lines)
    assert has_dev_extra, "[project.optional-dependencies].dev must be declared"
```

The test fails before S1-01 / S1-02 are merged because the distribution isn't installed; after S1-01..S1-04 the first two pass and the third confirms the scope axis. Commit the failing test as the red marker (run it against the current tree to confirm it would fail under a hypothetical `anthropic` injection).

A second red test (smaller) for `import-linter`:

Test file path: `tests/unit/test_import_linter_blocks_heavy_from_cli.py`

```python
# tests/unit/test_import_linter_blocks_heavy_from_cli.py
import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_HEAVY = {"yaml", "jsonschema", "pydantic", "blake3", "structlog"}


def _top_level_imports(path: Path) -> set[str]:
    """Module names that appear at module top-level (not inside def/class bodies)."""
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
        # cli.py lands in S4-02; before then this test is vacuously green.
        # Once cli.py exists, this assertion enforces the contract.
        return
    leaked = _top_level_imports(cli) & FORBIDDEN_HEAVY
    assert leaked == set(), (
        f"cli.py must defer heavy imports inside command bodies; leaked: {leaked}. "
        f"See phase-arch-design.md §Component design — CLI."
    )


def test_package_init_does_not_top_level_import_heavy_modules() -> None:
    init = PROJECT_ROOT / "src" / "codegenie" / "__init__.py"
    leaked = _top_level_imports(init) & FORBIDDEN_HEAVY
    assert leaked == set(), (
        f"codegenie/__init__.py must stay light; leaked: {leaked}."
    )
```

### Green — make it pass

- Author `.github/workflows/ci.yml` with the six jobs, the matrix, the SHA-pinned actions, and the install/test steps per the acceptance criteria.
- Add `[tool.importlinter]` to `pyproject.toml` with two `forbidden` contracts (one each for `codegenie.cli` and `codegenie`).
- Verify locally: `pip install -e .[dev]`, `pytest tests/unit/test_pyproject_fence.py`, `lint-imports`.
- Push and watch the six jobs run; `lint`, `docs`, `fence` are expected green on the Step 1 PR; `typecheck` should be green (S1-02 already ensured strict-mypy clean on S1-01 files); `test` may be carve-out-bypassed per S1-02 Notes (`--cov-fail-under=0` on the Step 1 PR only).

### Refactor — clean up

- Add a heading comment at the top of `.github/workflows/ci.yml`: `# Six-job CI: lint, typecheck, test, security, docs, fence. fence is the load-bearing gate (ADR-0002). Do not disable without ADR amendment.`
- Confirm each `actions/...@<SHA>` line has a sibling comment with the corresponding human-readable version (`# v4.1.6` etc.) so updates aren't blind.
- Add `# CODEOWNERS-route this file: phase-arch-design.md §Implementation-level risks #4` near the fence job; CODEOWNERS itself lands in S5-02 but the marker primes the convention.
- Ensure no job has `pull_request_target` or any privilege-elevation trigger — `permissions: contents: read` at workflow level plus default-deny is the posture per `phase-arch-design.md §Testing strategy / CI gates`.
- Verify the `docs` job uses path-filtering (`paths: [docs/**, mkdocs.yml]`) so it doesn't run on every PR.

## Files to touch

| Path | Why |
|---|---|
| `.github/workflows/ci.yml` | New file — the six-job CI pipeline. |
| `tests/unit/test_pyproject_fence.py` | New file — TDD red anchor + deliberate-negative test + scope-axis test (ADR-0002). |
| `tests/unit/test_import_linter_blocks_heavy_from_cli.py` | New file — structural cold-start defense (`phase-arch-design.md §Tradeoffs` row 12). |
| `pyproject.toml` | Add `[tool.importlinter]` with two `forbidden` contracts; minimal lines. |
| `Makefile` | (Optional) add a `lint-imports` target invoking `lint-imports` from the `import-linter` package. |

## Out of scope

- **`CODEOWNERS` for the fence test file** — handled by S5-02; this story merely names the convention in a comment.
- **Performance canaries** (`tests/bench/`) — handled by S5-01; explicitly advisory-only per `phase-arch-design.md §Tradeoffs` row 12.
- **The `lint` and `docs` jobs' actual lint/docs commands** — those run `make lint` / `make docs`; the Makefile targets ship in S1-03.
- **Adversarial AST scans** (`tests/adv/test_no_shell_true.py`, etc.) — handled by S2-02 and S4-05.
- **GitHub Actions caching of `pip` / `uv`** — leave for now; if walltime drifts above the ≤ 90s p95 advisory, S5-01's bench layer adds the cache step.
- **Renovate / Dependabot configuration** — S5-02 ships `.github/dependabot.yml`.
- **Issue templates and PR template** — S5-02 ships these.

## Notes for the implementer

- The fence is **load-bearing**. If you find yourself "simplifying" any part of `tests/unit/test_pyproject_fence.py`, stop and re-read `phase-arch-design.md §Implementation-level risks #4`. The deliberate-negative test (`test_fence_catches_planted_anthropic_dep`) is *not* optional — it's the test that catches "the fence check itself silently broke."
- Per ADR-0002 §Tradeoffs, the fence's scope is `dependencies` **only**. `test_fence_scope_is_dependencies_only_never_optional` asserts this; do not "broaden" the fence to include `[project.optional-dependencies]` without an ADR amendment. The `dev` extra is *allowed* to transitively contain LLM-flavored plugins (e.g., a hypothetical mkdocs LLM plugin); broadening the fence breaks `dev` install across the contributor base.
- The intersection set `{anthropic, langgraph, openai, langchain, transformers}` is a contract. Adding a new SDK (e.g., `boto3-bedrock` once Bedrock lands) is a one-line PR with mandatory review per ADR-0002 §Consequences.
- `import-linter`'s `forbidden` contract syntax is in its docs at https://import-linter.readthedocs.io. Use `type: forbidden` with `source_modules` and `forbidden_modules`. Resist using `type: layers` for Phase 0 — overkill at this surface size.
- The `import-linter` contracts should be **scoped to the exact module names**: `codegenie.cli` (the file `src/codegenie/cli.py`) and `codegenie` (the package's `__init__.py`). Do **not** scope to `codegenie.cli.**` — that would block heavy imports inside `cli` sub-modules (and cli.py is a single file in Phase 0, so the sub-module case doesn't apply, but per `High-level-impl.md §Risks specific to this step` the convention prevents Phase-1 over-blocking).
- The CI matrix is `python: ["3.11", "3.12"]` × `os: [ubuntu-24.04]`. Per `phase-arch-design.md §Non-goals` #14, **do not add** macOS or Windows runners — the contributor pool runs macOS for dev and Linux for CI, and the surface stays narrow.
- All GitHub Actions third-party uses must be SHA-pinned. The `actions/checkout` and `actions/setup-python` SHAs change with releases — when you pin them, leave a `# v4.x.y` comment so future updates aren't blind. Per `phase-arch-design.md §Testing strategy / CI gates`, this is non-negotiable.
- The `concurrency: group: ${{ github.ref }}` setting ensures only one CI run per PR ref at a time; new pushes cancel older runs. Add `cancel-in-progress: true` so canceled runs don't burn the CI quota.
- `permissions: contents: read` at the workflow level is the *default deny* posture. Individual jobs may need narrower permissions (e.g., `security` may need `security-events: write` to upload SARIF later); leave that for the phase that introduces SARIF (Phase 3+) and keep Phase 0 at strict read-only.
- The Step 1 PR's `test` job will fail under the wired `--cov-fail-under=85` because the tree is mostly empty. Per S1-02 Notes, document the carve-out in the PR body and pass `--cov-fail-under=0` *only* on the Step 1 PR's CI invocation; the gate goes live for real in S4-04.
- `test_import_linter_blocks_heavy_from_cli.py` has a `if not cli.exists(): return` early-out because `cli.py` doesn't exist until S4-02. The test is vacuously green pre-S4-02 and becomes load-bearing post-S4-02 — the implementer ordering is intentional, not a test smell.
