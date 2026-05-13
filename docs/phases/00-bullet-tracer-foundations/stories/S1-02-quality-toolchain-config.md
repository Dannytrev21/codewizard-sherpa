# Story S1-02 — Quality toolchain config (ruff + mypy + pytest + coverage)

**Step:** Step 1 — Establish project skeleton, tooling, and the `fence` CI job
**Status:** Ready (validated 2026-05-12 — HARDENED)
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0007

## Validation notes

Validated: 2026-05-12
Verdict: HARDENED
Findings addressed: 12 total — 0 blocks, 7 hardens, 5 nits

Changes applied:
- AC-1 strengthened — now explicitly closes the "T20 selected but T201 stripped by `ignore`/`extend-ignore`/`per-file-ignores`" loophole; Test 1 verifies `line-length`, the absence of T201-stripping config keys, and the `[tool.ruff.format]` table — Coverage F1, F2, F8, Test-Quality F1.
- AC-2 strengthened — Test 2 now verifies `warn_unreachable=true` (which `--strict` does *not* enable by default) and asserts the tests override actually sets `disallow_untyped_defs=false` AND `disallow_untyped_decorators=false`, not just that *some* override exists — Coverage F3, F4, Test-Quality F2.
- AC-4 strengthened — Test 4 tightened to exact-equality on the `omit` list (a lazy impl exempting `probes/*` would have inflated coverage and silently weakened Phase 1's contract) — Test-Quality F5.
- AC-5 relaxed — dropped "was committed at the red phase" (a process AC unverifiable from the working tree); replaced with "exists and is green" — Coverage F7.
- AC-8 added — new structural AC: `[tool.coverage.run]` shape (`branch = true`, `source = ["src/codegenie"]`) is verified, closing the gap where `--cov-branch` in `addopts` could be a no-op — Coverage F5.
- AC-9 added — new behavioral AC: `ruff check` actually rejects `print()` in `src/` with a T201 diagnostic. This is the only test that bridges from "config shape is right" to "tool actually enforces the load-bearing logging-strategy invariant" — Coverage F6, Test-Quality F4.
- TDD plan rewritten to match the hardened ACs (Tests 1, 2, 4 expanded; Tests 5 and 6 added).

Conflict resolutions:
- Consistency F1 (`T20` family vs arch-named `T201`): both expressions are behavior-equivalent for the print ban; Test 1 now accepts either `"T20"` or `"T201"` in `select` *and* enforces no downstream weakening. This honors both the story's existing AC wording and `phase-arch-design.md §Harness engineering`'s explicit naming of T201.
- Consistency F2 (goal "pytest -q exits 0" vs Refactor §3 "coverage may fail"): not a contradiction — the goal asserts the configured shape; the carve-out is the CI-side `--cov-fail-under=0` override documented in High-level-impl §Step 1 Done-criteria and already called out in this story's Implementer notes. No edit.
- Deferred-enforceability gap (Consistency F3, observational): `pytest-cov` does not expose a separate `--cov-fail-under-branch=75` flag, so the 75% branch floor (`phase-arch-design.md §Tradeoffs`) is collected (via `--cov-branch`) but not gate-enforced from `addopts`. This is a phase-arch-level limitation, not a story-level fix; surface but do not edit.

Full audit log: [`_validation/S1-02-quality-toolchain-config.md`](_validation/S1-02-quality-toolchain-config.md)

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

- [ ] AC-1: `pyproject.toml` contains `[tool.ruff]` with `target-version = "py311"`, `line-length = 100`, and `[tool.ruff.lint]` selecting at minimum `E`, `F`, `I` (imports), `B` (bugbear), `UP` (pyupgrade), and `T20` *or* `T201` (no-`print` — either expression is acceptable; `T20` is the family that includes `T201`); and `[tool.ruff.format]` table is declared. The T201 rule must remain *effective for `src/`* — neither `[tool.ruff.lint.ignore]`, `[tool.ruff.lint.extend-ignore]`, nor `[tool.ruff.lint.per-file-ignores]` may strip `T201` (or its family `T20`) from any `src/` pattern. (validator: hardened from original — original test used `issubset` against the family `T20` and never checked `ignore`/`extend-ignore`/`per-file-ignores`; `line-length` and `[tool.ruff.format]` were named in the AC but not asserted.)
- [ ] AC-2: `pyproject.toml` contains `[tool.mypy]` with `python_version = "3.11"`, `strict = true`, **`warn_unreachable = true`** (this is *not* enabled by `strict`; it must be set explicitly), plus a `[[tool.mypy.overrides]]` block whose `module` field matches a `tests`-rooted pattern (`"tests"`, `"tests.*"`, or a list containing one of those) and which sets **both** `disallow_untyped_defs = false` AND `disallow_untyped_decorators = false`. A bare override block with no flags is *not* sufficient. (validator: hardened — original test asserted only that *some* override block existed and that its `module` string contained `"tests"` as a substring; mutations like `module = "src/foo/contests.py"` with no flags would have passed.)
- [ ] AC-3: `pyproject.toml` contains `[tool.pytest.ini_options]` declaring `asyncio_mode = "auto"`, `testpaths = ["tests"]`, and `addopts` containing the tokens `--cov=src/codegenie`, `--cov-branch`, and `--cov-fail-under=85`.
- [ ] AC-4: `[tool.coverage.report]` declares `omit == ["src/codegenie/cli.py"]` **exactly** (no other entries — `cli.py` is the only architecturally-permitted exemption per `phase-arch-design.md §Testing strategy / Test pyramid`). (validator: hardened — original test used `in omit`; a lazy impl exempting `probes/*` would have inflated coverage and silently weakened Phase 1's contract.)
- [ ] AC-5: The TDD test file `tests/unit/test_toolchain_config.py` exists, and `pytest -q tests/unit/test_toolchain_config.py` exits 0. (validator: relaxed — removed unverifiable "was committed at the red phase" process clause; the executor's TDD workflow already enforces red→green order via its own attempt log.)
- [ ] AC-6: `ruff check .` and `ruff format --check .` exit 0 on the current tree (no source code regresses against the new config).
- [ ] AC-7: `mypy --strict src/` exits 0 on the current tree.
- [ ] AC-8: `[tool.coverage.run]` declares `branch = true` AND `source = ["src/codegenie"]`. Without these, the `--cov-branch` token in `addopts` is a no-op and the 75% branch floor (`phase-arch-design.md §Tradeoffs`) becomes unenforceable for every subsequent phase. (validator: added — load-bearing for the 85/75 coverage floor; no original AC covered the `[tool.coverage.run]` table.)
- [ ] AC-9: Running `ruff check` (with this story's `pyproject.toml` config applied) against a Python file under `src/codegenie/` containing the literal text `print('canary')` exits **non-zero** and emits a diagnostic referencing rule code `T201`. This is the *behavioral* contract for the load-bearing "no `print()` in `src/`" invariant from `phase-arch-design.md §Harness engineering / Logging strategy`. (validator: added — without this, any combination of `ignore`, `extend-ignore`, or `per-file-ignores` weakening that the introspection tests don't enumerate would still ship; the behavioral test catches unknown-unknown weakenings.)

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
import subprocess
import sys
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"

# Distribution-of-tasks for ruff's "print is banned" invariant: either the
# T20 family OR the specific T201 rule satisfies AC-1 (T20 ⊇ T201).
PRINT_BAN_TOKENS = {"T20", "T201"}


def _load() -> dict:
    return tomllib.loads(PYPROJECT.read_text())


def test_ruff_targets_py311_with_line_length_and_effective_print_ban() -> None:
    # AC-1: target, line-length, format-table, and an *effective* print ban.
    cfg = _load()
    ruff = cfg["tool"]["ruff"]
    assert ruff["target-version"] == "py311"
    # line-length is contract: pre-commit hooks in S1-04 reformat to this width.
    assert ruff["line-length"] == 100
    # [tool.ruff.format] table must be declared (signals format-config opt-in;
    # ruff format applies even with an empty sub-table, but the declaration is
    # the AC-named opt-in).
    assert "format" in ruff, "[tool.ruff.format] table must be declared"

    lint = ruff["lint"]
    selected = set(lint["select"])
    assert {"E", "F", "I", "B", "UP"}.issubset(selected)
    # Accept either the family token "T20" or the specific rule "T201". The
    # arch (phase-arch-design.md §Harness engineering) names T201; either is
    # behavior-equivalent.
    assert PRINT_BAN_TOKENS & selected, (
        f"AC-1: ruff must select T20 or T201 to ban print() in src/; "
        f"got select = {sorted(selected)}"
    )

    # Defense-in-depth: even if T20/T201 is selected, downstream weakening
    # would silently disable it. Reject all known weakening surfaces.
    ignored = set(lint.get("ignore", []))
    extend_ignored = set(lint.get("extend-ignore", []))
    for bucket_name, bucket in (("ignore", ignored), ("extend-ignore", extend_ignored)):
        assert not (PRINT_BAN_TOKENS & bucket), (
            f"AC-1: [tool.ruff.lint.{bucket_name}] must not strip T201/T20; "
            f"got {bucket_name} = {sorted(bucket)}"
        )
    per_file = lint.get("per-file-ignores", {}) or {}
    for pattern, rules in per_file.items():
        # Heuristic: any pattern targeting src/ (positively or via a glob) must
        # not weaken the print ban.
        if pattern.startswith("src/") or pattern == "src" or pattern == "**/src/**":
            rule_set = set(rules) if not isinstance(rules, str) else {rules}
            assert not (PRINT_BAN_TOKENS & rule_set), (
                f"AC-1: per-file-ignores must not disable T201/T20 for src/ "
                f"(violation: {pattern!r} -> {rules!r})"
            )


def test_mypy_strict_with_warn_unreachable_and_tests_override_relaxed() -> None:
    # AC-2: strict + warn_unreachable + a tests override that actually relaxes
    # the two named flags (not just a bare override block).
    cfg = _load()
    mypy = cfg["tool"]["mypy"]
    assert mypy["strict"] is True
    assert mypy["python_version"] == "3.11"
    # warn_unreachable is NOT enabled by --strict (it's a strict-extra); without
    # explicit `true`, dead-code-after-narrowing slips through silently.
    assert mypy["warn_unreachable"] is True, (
        "AC-2: warn_unreachable must be explicitly true (not enabled by strict)"
    )

    overrides = mypy["overrides"]
    tests_override = None
    for o in overrides:
        module = o.get("module", "")
        modules = module if isinstance(module, list) else [module]
        if any(m == "tests" or m == "tests.*" or m.startswith("tests.")
               for m in modules):
            tests_override = o
            break
    assert tests_override is not None, (
        "AC-2: must declare a [[tool.mypy.overrides]] block targeting tests"
    )
    # A bare override with no flags is a no-op; AC-2 demands both relaxations.
    assert tests_override.get("disallow_untyped_defs") is False, (
        "AC-2: tests override must set disallow_untyped_defs = false"
    )
    assert tests_override.get("disallow_untyped_decorators") is False, (
        "AC-2: tests override must set disallow_untyped_decorators = false"
    )


def test_pytest_runs_under_asyncio_auto_with_coverage_gate() -> None:
    # AC-3 unchanged.
    cfg = _load()
    pt = cfg["tool"]["pytest"]["ini_options"]
    # asyncio_mode=auto so coordinator tests (S3-05) don't need decorators
    assert pt["asyncio_mode"] == "auto"
    # testpaths anchored to tests/ (no accidental src/ scanning)
    assert pt["testpaths"] == ["tests"]
    # the coverage gate is wired (even though it goes live in S4-04)
    addopts = pt["addopts"]
    assert "--cov=src/codegenie" in addopts
    assert "--cov-branch" in addopts
    assert "--cov-fail-under=85" in addopts


def test_coverage_excludes_only_cli_py_per_phase_arch_design() -> None:
    # AC-4: exact-equality on omit. phase-arch §Testing strategy / Test pyramid
    # exempts ONLY cli.py. A lazy impl exempting probes/* would inflate coverage
    # and silently weaken Phase 1's contract.
    cfg = _load()
    omit = cfg["tool"]["coverage"]["report"]["omit"]
    assert omit == ["src/codegenie/cli.py"], (
        "AC-4: only cli.py may be omitted; "
        f"got omit = {omit}"
    )


def test_coverage_run_collects_branch_and_sources_only_src_codegenie() -> None:
    # AC-8: [tool.coverage.run] shape. Without branch=true, --cov-branch in
    # addopts is a no-op; without source pinned to src/codegenie, coverage
    # measurement drifts onto incidental working-dir files.
    cfg = _load()
    run = cfg["tool"]["coverage"]["run"]
    assert run["branch"] is True, "AC-8: [tool.coverage.run].branch must be true"
    assert run["source"] == ["src/codegenie"], (
        f"AC-8: source must be exactly ['src/codegenie']; got {run['source']}"
    )


def test_ruff_check_rejects_print_in_src_per_phase_arch_logging_strategy() -> None:
    # AC-9: behavioral test — proves the WIRED configuration enforces the
    # "no print() in src/" invariant from phase-arch-design.md §Harness
    # engineering / Logging strategy. This is the only test in the plan that
    # actually invokes ruff; it catches any unknown-unknown weakening of the
    # rule selection (e.g., a future ruff config key that strips T201) that
    # the introspection tests above can't enumerate.
    canary = PROJECT_ROOT / "src" / "codegenie" / "_validator_canary_for_test.py"
    canary.write_text("print('canary')\n", encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--no-cache",
             "--config", str(PYPROJECT), str(canary)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        canary.unlink(missing_ok=True)
    # Non-zero exit ⇒ ruff found at least one violation.
    assert result.returncode != 0, (
        f"AC-9: ruff must reject print() in src/; "
        f"exit={result.returncode}, stdout={result.stdout!r}, "
        f"stderr={result.stderr!r}"
    )
    # The diagnostic must cite T201 explicitly (so the failure is attributable
    # to the print ban, not e.g. an unrelated E501 line-length hit).
    combined = result.stdout + result.stderr
    assert "T201" in combined, (
        f"AC-9: expected T201 in diagnostic output; got: {combined}"
    )
```

The six tests fail initially because no `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`, or `[tool.coverage]` blocks exist in S1-01's `pyproject.toml`. Tests 1–5 fail with `KeyError`; Test 6 fails because (a) without `[tool.ruff.lint].select` containing `T20`/`T201`, the canary file's `print('canary')` is not flagged. Run them, confirm the expected failures, commit as the red marker.

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
