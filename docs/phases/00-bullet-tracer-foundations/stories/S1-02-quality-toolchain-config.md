# Story S1-02 — Quality toolchain config (ruff + mypy + pytest + coverage)

**Step:** Step 1 — Establish project skeleton, tooling, and the `fence` CI job
**Status:** Ready
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0007

## Context

S1-01 landed the `pyproject.toml` skeleton. This story configures the four quality tools (`ruff` lint+format, `mypy` strict on `src/`, `pytest` with `pytest-asyncio` + `pytest-cov`, branch-coverage gate) *inside the same `pyproject.toml`*. Strict configuration is itself a contract every later phase inherits: every probe added in Phase 1 must be `mypy --strict` clean on day one, and every test from Step 3 onward must run under `pytest-asyncio`. The coverage gate (`--cov-fail-under=85`) is wired here but goes live in S4-04 once the vertical slice produces enough real code to hit the floor.

This is cross-cutting plumbing — without it, S1-04's pre-commit hooks have nothing to call and S1-05's CI jobs have no commands to run.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy / Test pyramid` — one unit-test file per public-API surface; `cli.py` exempt from coverage.
  - `../phase-arch-design.md §Testing strategy / CI gates` — declares `lint`, `typecheck`, `test` jobs and their wall-time targets.
  - `../phase-arch-design.md §Tradeoffs (consolidated)` — row "`pytest-xdist` off" (no parallel test runs), row "85/75 coverage floor."
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0007-probe-contract-frozen-snapshot.md` — ADR-0007 — `tests/snapshots/` is contract territory; coverage exclusion must not silently drop snapshot-test enforcement.
- **Source design:**
  - `../High-level-impl.md §Step 1` — Features delivered, "config for ruff (lint + format), strict mypy on `src/`, relaxed mypy on `tests/`, pytest (`--cov=src/codegenie --cov-branch --cov-fail-under=85`), coverage exclude for `cli.py`."
  - `../final-design.md §7` — testing pyramid and coverage policy.
- **External docs:**
  - https://docs.astral.sh/ruff/configuration/ — `[tool.ruff]` table.
  - https://mypy.readthedocs.io/en/stable/config_file.html — strict-mode flag set.
  - https://docs.pytest.org/en/stable/reference/customize.html — `[tool.pytest.ini_options]`.

## Goal

Running `ruff check .`, `ruff format --check .`, `mypy --strict src/`, and `pytest -q` from a clean checkout exits 0 with the configurations declared in `pyproject.toml`.

## Acceptance criteria

- [ ] `pyproject.toml` contains `[tool.ruff]` with `target-version = "py311"`, `line-length = 100`, and `[tool.ruff.lint]` selecting at minimum `E`, `F`, `I` (imports), `B` (bugbear), `UP` (pyupgrade), `T20` (no-`print`); and `[tool.ruff.format]` enabled.
- [ ] `pyproject.toml` contains `[tool.mypy]` with `python_version = "3.11"`, `strict = true`, `warn_unreachable = true`, plus a `[[tool.mypy.overrides]]` block targeting `tests/*` that relaxes `disallow_untyped_defs` and `disallow_untyped_decorators`.
- [ ] `pyproject.toml` contains `[tool.pytest.ini_options]` declaring `asyncio_mode = "auto"`, `testpaths = ["tests"]`, and `addopts = "-q --cov=src/codegenie --cov-branch --cov-fail-under=85"`.
- [ ] `pyproject.toml` contains `[tool.coverage.run]` with `branch = true` and `source = ["src/codegenie"]`; and `[tool.coverage.report]` with `omit = ["src/codegenie/cli.py"]` (the architectural exemption).
- [ ] The TDD red test at `tests/unit/test_toolchain_config.py` exists, was committed at the red phase, and is green.
- [ ] `ruff check .` and `ruff format --check .` exit 0 on the current tree (no source code regresses against the new config).
- [ ] `mypy --strict src/` exits 0 on the current tree.

## Implementation outline

1. Write the failing red test (`tests/unit/test_toolchain_config.py`) that loads `pyproject.toml`, queries each `[tool.*]` table, and asserts the contract above.
2. Add the four `[tool.*]` tables to `pyproject.toml`. Keep ruff's selected rules minimal; later phases can extend.
3. Run `ruff check .` / `ruff format` and fix the *minimal* issues so the existing S1-01 files pass. (There should be very few — a few imports to sort, possibly final-newline.)
4. Run `mypy --strict src/`; the placeholder S4-02 `__main__.py:main` must already have its return annotation per S1-01 Notes.
5. Run `pytest -q tests/unit/test_toolchain_config.py` and confirm green.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_toolchain_config.py`

```python
# tests/unit/test_toolchain_config.py
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def _load() -> dict:
    return tomllib.loads(PYPROJECT.read_text())


def test_ruff_targets_py311_and_selects_required_rules() -> None:
    # arrange: load pyproject.toml
    cfg = _load()
    # act: read the [tool.ruff] table
    ruff = cfg["tool"]["ruff"]
    # assert: 3.11 target so we can use the union "X | Y" syntax everywhere
    assert ruff["target-version"] == "py311"
    selected = set(ruff["lint"]["select"])
    # T20 bans `print(` in src/; required by phase-arch §Harness engineering "Logging strategy"
    assert {"E", "F", "I", "B", "UP", "T20"}.issubset(selected)


def test_mypy_strict_on_src_relaxed_on_tests() -> None:
    cfg = _load()
    mypy = cfg["tool"]["mypy"]
    # assert: strict-everywhere on src
    assert mypy["strict"] is True
    assert mypy["python_version"] == "3.11"
    # assert: a tests-relaxation override exists (otherwise pytest fixtures hit
    # disallow_untyped_defs and the test surface gets noisy for no value)
    overrides = mypy["overrides"]
    test_overrides = [o for o in overrides if o["module"].startswith("tests")
                      or "tests" in str(o.get("module", ""))]
    assert test_overrides, "must declare a tests override block"


def test_pytest_runs_under_asyncio_auto_with_coverage_gate() -> None:
    cfg = _load()
    pt = cfg["tool"]["pytest"]["ini_options"]
    # assert: asyncio_mode=auto so coordinator tests (S3-05) don't need decorators
    assert pt["asyncio_mode"] == "auto"
    # assert: testpaths anchored to tests/ (no accidental src/ scanning)
    assert pt["testpaths"] == ["tests"]
    # assert: the coverage gate is wired (even though it goes live in S4-04)
    addopts = pt["addopts"]
    assert "--cov=src/codegenie" in addopts
    assert "--cov-branch" in addopts
    assert "--cov-fail-under=85" in addopts


def test_coverage_excludes_cli_py_per_phase_arch_design() -> None:
    # arrange: phase-arch §Testing strategy / Test pyramid explicitly exempts cli.py
    # because the smoke test covers it (S4-04) and unit-testing click is low-value.
    cfg = _load()
    omit = cfg["tool"]["coverage"]["report"]["omit"]
    # act+assert: cli.py is excluded — this is a deliberate architectural choice,
    # not a way to inflate coverage. Document the exemption inline in pyproject.toml.
    assert "src/codegenie/cli.py" in omit
```

The test fails initially because no `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`, or `[tool.coverage]` blocks exist in S1-01's `pyproject.toml`. Run it, confirm `KeyError`, commit as the red marker.

### Green — make it pass

Add the four `[tool.*]` tables to `pyproject.toml`. The minimum shapes:
- `[tool.ruff]` + `[tool.ruff.lint]` + `[tool.ruff.format]` with the keys named in the test.
- `[tool.mypy]` + `[[tool.mypy.overrides]]` for `tests`.
- `[tool.pytest.ini_options]` with `asyncio_mode`, `testpaths`, `addopts`.
- `[tool.coverage.run]` + `[tool.coverage.report]` with the omit list.

Resist adding plugins, custom markers, or extra rules beyond what the test asserts.

### Refactor — clean up

- Add a one-line comment in `pyproject.toml` above the `[tool.coverage.report]` `omit` explaining the cli.py exemption (cite the phase-arch section name so future readers find the rationale).
- Make sure `ruff format --check` is clean on `pyproject.toml` itself (TOML formatting is incidental but the tree-wide check runs it).
- Verify the `--cov-fail-under=85` is **wired** but the existing tree is allowed to under-shoot in Step 1 (per High-level-impl §Step 1 Done criteria, the gate goes live in S4-04). If running `pytest` locally fails on coverage now, that's expected — leave it; S4-04 is when it must pass.
- Ensure `ruff check`'s `T20` rule (no `print`) is *not* relaxed for `src/`. If a transition placeholder snuck a `print()` in S1-01, replace it.

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | Add the `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`, `[tool.coverage.run]`, `[tool.coverage.report]` blocks. |
| `tests/unit/test_toolchain_config.py` | New file — TDD red anchor; pins every required configuration knob. |

## Out of scope

- **`.pre-commit-config.yaml` running these tools at commit time** — handled by S1-04.
- **`.github/workflows/ci.yml` invoking ruff / mypy / pytest** — handled by S1-05.
- **The `Makefile` `lint` / `typecheck` / `test` targets** — handled by S1-03.
- **The `fence` test and its scope guard** — handled by S1-05.
- **`forbidden-patterns` regex hook (`shell=True`, `yaml.load(`, etc.)** — handled by S1-04.
- **Flipping `--cov-fail-under=85` from "wired" to "real merge gate"** — handled by S4-04 once vertical-slice code can clear it.

## Notes for the implementer

- `ruff` and `mypy` config blocks both live inside the **same `pyproject.toml`** (no separate `.ruff.toml`, no `setup.cfg`). One source of truth for tooling per phase-arch §Tradeoffs.
- The `T20` rule (no `print` in src) is load-bearing: `phase-arch-design.md §Harness engineering` says all logging goes through `structlog`. If you must keep a `print` somewhere (e.g., a dev script under `scripts/`), explicitly exclude `scripts/` from `lint.select` rather than disabling `T20` globally.
- The tests-relaxation override must use `disallow_untyped_defs = false` and `disallow_untyped_decorators = false`. Do **not** set `ignore_errors = true` for tests — strict checking still catches real bugs in fixture types.
- `asyncio_mode = "auto"` is a `pytest-asyncio` setting that lets coroutine-shaped test functions run without `@pytest.mark.asyncio`. S3-05's coordinator tests rely on this; landing it here saves later boilerplate.
- The coverage `omit` list is **the only place** `cli.py` is exempted from a measurement. Do not add it to `[tool.mypy].exclude` — `cli.py` must still be strict-typed (S4-02 will be heavily linted).
- The `--cov-fail-under=85` value is wired here but not enforced as a *merge* gate until S4-04. Step 1's PR runs with whatever coverage the empty tree produces; the High-level-impl §Step 1 Done-criteria explicitly carve out the Step 1 PR to bypass via `--cov-fail-under=0` on its CI invocation only. Document this carve-out in the Step 1 PR body when you open it.
- After this story merges, **all subsequent stories** in Phase 0 must keep `ruff check`, `ruff format --check`, and `mypy --strict src/` green on their touched files. The Definition of Done (`stories/README.md`) enforces this; you don't need to restate it in every story's acceptance criteria.
