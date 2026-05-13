"""Toolchain configuration contract — pins ruff / mypy / pytest / coverage.

This test file is the TDD red anchor for story S1-02. It introspects
``pyproject.toml`` and exercises one behavioral check (AC-9) to ensure the
"no ``print()`` in ``src/``" invariant from
``phase-arch-design.md §Harness engineering / Logging strategy`` is actually
enforced by ``ruff`` — not merely declared.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"

# Either the family token "T20" or the specific rule "T201" satisfies the
# print-ban AC (T20 ⊇ T201).
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
    # [tool.ruff.format] table must be declared.
    assert "format" in ruff, "[tool.ruff.format] table must be declared"

    lint = ruff["lint"]
    selected = set(lint["select"])
    assert {"E", "F", "I", "B", "UP"}.issubset(selected)
    assert PRINT_BAN_TOKENS & selected, (
        f"AC-1: ruff must select T20 or T201 to ban print() in src/; "
        f"got select = {sorted(selected)}"
    )

    # Defense-in-depth: reject downstream weakening surfaces.
    ignored = set(lint.get("ignore", []))
    extend_ignored = set(lint.get("extend-ignore", []))
    for bucket_name, bucket in (
        ("ignore", ignored),
        ("extend-ignore", extend_ignored),
    ):
        assert not (PRINT_BAN_TOKENS & bucket), (
            f"AC-1: [tool.ruff.lint.{bucket_name}] must not strip T201/T20; "
            f"got {bucket_name} = {sorted(bucket)}"
        )
    per_file = lint.get("per-file-ignores", {}) or {}
    for pattern, rules in per_file.items():
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
    # warn_unreachable is NOT enabled by --strict (strict-extra); without explicit
    # `true`, dead-code-after-narrowing slips through silently.
    assert mypy["warn_unreachable"] is True, (
        "AC-2: warn_unreachable must be explicitly true (not enabled by strict)"
    )

    overrides = mypy["overrides"]
    tests_override = None
    for o in overrides:
        module = o.get("module", "")
        modules = module if isinstance(module, list) else [module]
        if any(m == "tests" or m == "tests.*" or m.startswith("tests.") for m in modules):
            tests_override = o
            break
    assert tests_override is not None, (
        "AC-2: must declare a [[tool.mypy.overrides]] block targeting tests"
    )
    assert tests_override.get("disallow_untyped_defs") is False, (
        "AC-2: tests override must set disallow_untyped_defs = false"
    )
    assert tests_override.get("disallow_untyped_decorators") is False, (
        "AC-2: tests override must set disallow_untyped_decorators = false"
    )


def test_pytest_runs_under_asyncio_auto_with_coverage_gate() -> None:
    # AC-3.
    cfg = _load()
    pt = cfg["tool"]["pytest"]["ini_options"]
    assert pt["asyncio_mode"] == "auto"
    assert pt["testpaths"] == ["tests"]
    addopts = pt["addopts"]
    assert "--cov=src/codegenie" in addopts
    assert "--cov-branch" in addopts
    assert "--cov-fail-under=85" in addopts


def test_coverage_excludes_only_cli_py_per_phase_arch_design() -> None:
    # AC-4: exact-equality on omit. phase-arch §Testing strategy / Test pyramid
    # exempts ONLY cli.py.
    cfg = _load()
    omit = cfg["tool"]["coverage"]["report"]["omit"]
    assert omit == ["src/codegenie/cli.py"], f"AC-4: only cli.py may be omitted; got omit = {omit}"


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
    # engineering / Logging strategy.
    canary = PROJECT_ROOT / "src" / "codegenie" / "_validator_canary_for_test.py"
    canary.write_text("print('canary')\n", encoding="utf-8")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--no-cache",
                "--config",
                str(PYPROJECT),
                str(canary),
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        canary.unlink(missing_ok=True)
    assert result.returncode != 0, (
        f"AC-9: ruff must reject print() in src/; "
        f"exit={result.returncode}, stdout={result.stdout!r}, "
        f"stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "T201" in combined, f"AC-9: expected T201 in diagnostic output; got: {combined}"
