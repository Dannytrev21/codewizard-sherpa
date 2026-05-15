"""Per-module coverage carve-outs — story S4-04, ADR-0005.

Permanent CI-enforced guard around the two declared carve-outs (line 85 /
branch 75) for ``src/codegenie/probes/deployment.py`` and
``src/codegenie/probes/ci.py``. Replaces the original story's manual
red-phase with a runtime test of the chosen enforcement mechanism so that
the carve-out floors are surfaced loudly (Rule 12) when a module drifts
below.

Covers AC-2, AC-3, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11 of the story.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
SCRIPT = PROJECT_ROOT / "scripts" / "check_coverage_carve_outs.py"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"

EXPECTED_CARVE_OUTS = {
    "src/codegenie/probes/deployment.py": {
        "module": "codegenie.probes.deployment",
        "line": 85,
        "branch": 75,
    },
    "src/codegenie/probes/ci.py": {
        "module": "codegenie.probes.ci",
        "line": 85,
        "branch": 75,
    },
}


def _load_pyproject() -> dict:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


# --------------------------------------------------------------------------- #
# AC-11 — pyproject parses
# --------------------------------------------------------------------------- #


def test_pyproject_parses() -> None:
    """AC-11: ``pyproject.toml`` must parse with ``tomllib``."""
    data = _load_pyproject()
    assert isinstance(data, dict)


# --------------------------------------------------------------------------- #
# AC-2 / AC-6 — carve-out table shape pinned
# --------------------------------------------------------------------------- #


def test_carve_out_table_has_exactly_two_entries() -> None:
    """AC-2 + AC-6: the ``[tool.coverage_carve_outs]`` table contains EXACTLY
    the two carve-outs from ADR-0005 at EXACTLY 85 line / 75 branch."""
    data = _load_pyproject()
    table = data["tool"]["coverage_carve_outs"]["entries"]
    assert isinstance(table, list)
    assert len(table) == 2, (
        f"carve-out table must have exactly 2 entries (ADR-0005); "
        f"got {len(table)}. Adding a third requires an ADR amendment."
    )
    seen_paths = {entry["path"] for entry in table}
    assert seen_paths == set(EXPECTED_CARVE_OUTS), f"unexpected carve-out paths: {seen_paths}"
    for entry in table:
        expected = EXPECTED_CARVE_OUTS[entry["path"]]
        assert entry["module"] == expected["module"], (
            f"rename guard: {entry['path']} module field "
            f"{entry['module']!r} != expected {expected['module']!r}"
        )
        assert entry["line"] == expected["line"], (
            f"{entry['path']} line floor must be exactly 85 (ADR-0005); got {entry['line']}"
        )
        assert entry["branch"] == expected["branch"], (
            f"{entry['path']} branch floor must be exactly 75 (ADR-0005); got {entry['branch']}"
        )
        assert entry["adr"] == "phase-01/ADR-0005"


# --------------------------------------------------------------------------- #
# AC-8 — inline rationale comment
# --------------------------------------------------------------------------- #


def test_inline_rationale_comment_present() -> None:
    """AC-8: the inline comment adjacent to the carve-out table includes
    all three required substrings (ADR pointer, rationale phrase, and the
    "Further carve-outs require..." closing prose)."""
    text = PYPROJECT.read_text()
    assert "ADR-0005" in text, "AC-8: ADR-0005 pointer missing"
    rationale_phrases = ("branch-shape", "gameable", "branch-checkbox")
    matched = [p for p in rationale_phrases if p in text]
    assert matched, (
        f"AC-8: at least one of {rationale_phrases!r} must appear in "
        f"pyproject.toml as the Rule-9 rationale phrase"
    )
    assert "Further carve-outs require a new ADR amending 0005." in text, (
        "AC-8: ADR-amendment trigger phrase missing"
    )


# --------------------------------------------------------------------------- #
# AC-9 — stale 87/77 ratchet-plan comment removed
# --------------------------------------------------------------------------- #


def test_stale_ratchet_plan_comment_removed() -> None:
    """AC-9: the stale ``Phase 1 bumps to 87/77`` prose is gone."""
    text = PYPROJECT.read_text()
    assert "87/77" not in text, (
        "AC-9: stale ratchet-plan substring '87/77' must be rewritten to "
        "match ADR-0005 (no 87/77 intermediate)"
    )


# --------------------------------------------------------------------------- #
# AC-3 — global floor unchanged
# --------------------------------------------------------------------------- #


def test_global_floor_unchanged() -> None:
    """AC-3: the global ``--cov-fail-under=85`` is unchanged in this story.
    The S6-02 PR raises it to 90; S4-04 must be additive only."""
    data = _load_pyproject()
    addopts = data["tool"]["pytest"]["ini_options"]["addopts"]
    assert "--cov-fail-under=85" in addopts, (
        f"AC-3: --cov-fail-under=85 (Phase 0 global) must remain; got: {addopts!r}"
    )
    report = data["tool"]["coverage"].get("report", {})
    assert "fail_under" not in report, (
        "AC-3: a fail_under key under [tool.coverage.report] would shadow "
        "the global pytest gate; S4-04 must not introduce one"
    )


# --------------------------------------------------------------------------- #
# AC-7 — script's check() flags under-floor modules
# --------------------------------------------------------------------------- #


def _import_check() -> object:
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        import importlib

        return importlib.import_module("scripts.check_coverage_carve_outs")
    finally:
        sys.path.pop(0)


def _coverage_json(
    *,
    ci_line: float = 100.0,
    ci_branch: float = 100.0,
    deployment_line: float = 100.0,
    deployment_branch: float = 100.0,
) -> dict:
    """Build a synthetic ``coverage.json`` document.

    Shape mirrors ``coverage.py``'s ``--cov-report=json`` output: a top-level
    ``files`` dict keyed by file path, each containing a ``summary`` with
    ``percent_covered`` (line) and ``percent_covered_branch``.
    """
    return {
        "files": {
            "src/codegenie/probes/ci.py": {
                "summary": {
                    "percent_covered": ci_line,
                    "percent_covered_branch": ci_branch,
                },
            },
            "src/codegenie/probes/deployment.py": {
                "summary": {
                    "percent_covered": deployment_line,
                    "percent_covered_branch": deployment_branch,
                },
            },
        },
    }


def _load_carve_outs() -> list:
    mod = _import_check()
    return mod.load_carve_outs(PYPROJECT)  # type: ignore[attr-defined]


def test_check_function_flags_under_floor_ci_py() -> None:
    """AC-7: ``check()`` flags ``ci.py`` when below the 85/75 floor."""
    mod = _import_check()
    violations = mod.check(  # type: ignore[attr-defined]
        _coverage_json(ci_line=60.0, ci_branch=50.0),
        _load_carve_outs(),
    )
    assert violations, "AC-7: under-floor ci.py must produce a violation"
    joined = "\n".join(violations)
    assert "codegenie.probes.ci" in joined or "src/codegenie/probes/ci.py" in joined, (
        f"AC-7: violation must name the offending module/path; got: {violations!r}"
    )


def test_check_function_flags_under_floor_deployment_py() -> None:
    """AC-7: ``check()`` flags ``deployment.py`` when below the 85/75 floor."""
    mod = _import_check()
    violations = mod.check(  # type: ignore[attr-defined]
        _coverage_json(deployment_line=70.0, deployment_branch=40.0),
        _load_carve_outs(),
    )
    assert violations
    joined = "\n".join(violations)
    assert "codegenie.probes.deployment" in joined or "src/codegenie/probes/deployment.py" in joined


def test_check_function_passes_when_all_at_floor() -> None:
    """AC-7: ``>= 85/75`` not ``> 85/75`` — at-floor must pass."""
    mod = _import_check()
    violations = mod.check(  # type: ignore[attr-defined]
        _coverage_json(
            ci_line=85.0,
            ci_branch=75.0,
            deployment_line=85.0,
            deployment_branch=75.0,
        ),
        _load_carve_outs(),
    )
    assert violations == []


def test_check_function_passes_when_above_floor() -> None:
    """AC-7: comfortably-above-floor coverage must pass."""
    mod = _import_check()
    violations = mod.check(  # type: ignore[attr-defined]
        _coverage_json(),
        _load_carve_outs(),
    )
    assert violations == []


# --------------------------------------------------------------------------- #
# AC-7 (CLI shape) — subprocess smoke test
# --------------------------------------------------------------------------- #


def test_script_smoke_exits_nonzero_on_violation(tmp_path: Path) -> None:
    """AC-7 end-to-end: invoking the script with a synthetic ``coverage.json``
    where ``ci.py`` is below floor must exit non-zero and name the module."""
    cov_json = tmp_path / "coverage.json"
    cov_json.write_text(json.dumps(_coverage_json(ci_line=60.0, ci_branch=50.0)))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(cov_json), str(PYPROJECT)],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    assert result.returncode != 0, (
        f"AC-7: script must exit non-zero on violation; "
        f"got {result.returncode}, stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    assert "codegenie.probes.ci" in result.stderr, (
        f"AC-7: stderr must name the offending module; got: {result.stderr!r}"
    )


def test_script_smoke_exits_zero_when_all_above_floor(tmp_path: Path) -> None:
    """AC-7 end-to-end: above-floor invocation must exit 0."""
    cov_json = tmp_path / "coverage.json"
    cov_json.write_text(json.dumps(_coverage_json()))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(cov_json), str(PYPROJECT)],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    assert result.returncode == 0, (
        f"above-floor invocation must exit 0; got {result.returncode}, stderr={result.stderr!r}"
    )


# --------------------------------------------------------------------------- #
# AC-10 — CI workflow invokes the script
# --------------------------------------------------------------------------- #


def test_ci_workflow_invokes_script() -> None:
    """AC-10: the CI workflow's ``test`` job invokes the script after pytest."""
    if not CI_WORKFLOW.exists():
        pytest.skip("CI workflow file not at expected path; AC-10 records skip")
    text = CI_WORKFLOW.read_text()
    assert "check_coverage_carve_outs.py" in text, (
        "AC-10: scripts/check_coverage_carve_outs.py must be invoked from "
        "the CI test job after pytest --cov"
    )


# --------------------------------------------------------------------------- #
# Pure-function discipline (DP-2 / Notes) — check() takes no I/O
# --------------------------------------------------------------------------- #


def test_check_function_is_pure_no_io() -> None:
    """DP-2: ``check()`` must accept a coverage dict + carve-out list and
    return a violation list — no file I/O, no environment access."""
    mod = _import_check()
    import inspect

    sig = inspect.signature(mod.check)  # type: ignore[attr-defined]
    params = list(sig.parameters)
    assert len(params) == 2, (
        f"DP-2: check() must take exactly 2 args (coverage_data, carve_outs); got {params}"
    )
    src = inspect.getsource(mod.check)  # type: ignore[attr-defined]
    forbidden = ("open(", "os.environ", "sys.exit", "print(", "Path(")
    leaks = [tok for tok in forbidden if tok in src]
    assert not leaks, f"DP-2: check() must be pure; found I/O tokens in body: {leaks!r}"
