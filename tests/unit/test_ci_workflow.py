"""Parser test for ``.github/workflows/ci.yml`` + ``[tool.importlinter]``.

Closes the S1-04 "enumerate-then-test-zero" pattern: every contractual
property of the CI workflow (six jobs, matrix, SHA-pinning, concurrency,
permissions, fence install, lint-imports invocation, security job content,
docs path filtering) is asserted by parsing the workflow YAML rather than
by eyeball review. Owned by story S1-05 (AC-9).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
DOCS_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "docs.yml"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"

# Phase-0/1 jobs (legacy contract — must remain present after S8-03).
_LEGACY_JOBS = {"lint", "typecheck", "test", "security", "docs", "fence"}
# Phase-2 named lanes from `phase-arch-design.md §"CI gates"` (S8-03 AC-1).
_PHASE2_JOBS = {
    "contract-freeze",
    "unit",
    "integration",
    "portfolio",
    "adv-phase02",
    "mypy",
    "bench",
}
REQUIRED_JOBS = _LEGACY_JOBS | _PHASE2_JOBS
ALLOWED_TRIGGERS = {"pull_request", "push", "workflow_dispatch"}
SHA_PIN_RE = re.compile(r"^[A-Za-z0-9_./-]+@[0-9a-f]{40}$")

# PyYAML maps the bare YAML key `on` to the Python boolean ``True`` because
# of the YAML 1.1 boolean-key surface (on/off/yes/no). Tolerate both keys
# so the parser test is robust to the runtime's loader behaviour.
_ON_KEYS: tuple[Any, ...] = ("on", True)


def _wf() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text())


def _on(workflow: dict[str, Any]) -> Any:
    for key in _ON_KEYS:
        if key in workflow:
            return workflow[key]
    raise AssertionError(f"workflow has no `on:` trigger key; keys={list(workflow)}")


def _flatten_run(job: dict[str, Any]) -> str:
    return "\n".join(s.get("run", "") for s in job.get("steps", []) if "run" in s)


# ---------------------------------------------------------------------------
# AC-1: workflow parses; six required jobs; matrix; SHA-pinning.
# ---------------------------------------------------------------------------


def test_ci_workflow_parses() -> None:
    assert WORKFLOW.exists(), "AC-1: .github/workflows/ci.yml must exist"
    _wf()  # raises on parse failure


def test_ci_workflow_declares_exactly_six_required_jobs() -> None:
    # S8-03 reshape: this test now asserts the *union* of the legacy six and the
    # Phase-2 seven (minus `docs` when docs.yml owns it). The Phase-2 lanes are
    # additive: ADR-0009 + arch §"CI gates". See tests/unit/ci/test_workflow_yaml.py
    # for the per-lane invariants (subset / matrix / xdist veto / continue-on-error).
    jobs = set(_wf()["jobs"].keys())
    if DOCS_WORKFLOW.exists():
        # Option B: ci.yml MUST omit `docs` (docs.yml owns it).
        expected = REQUIRED_JOBS - {"docs"}
        assert jobs == expected, (
            f"AC-1/AC-12 Option B + S8-03 AC-1: ci.yml jobs must be {expected} "
            f"when docs.yml owns docs; got {jobs}"
        )
    else:
        assert jobs == REQUIRED_JOBS, f"AC-1: jobs must be exactly {REQUIRED_JOBS}; got {jobs}"


def test_ci_workflow_pins_python_311_312_on_ubuntu_2404() -> None:
    # AC-1 matrix.
    matrices = [
        j["strategy"]["matrix"]
        for j in _wf()["jobs"].values()
        if isinstance(j, dict) and "strategy" in j and "matrix" in j["strategy"]
    ]
    assert any(
        set(m.get("python", [])) == {"3.11", "3.12"} and list(m.get("os", [])) == ["ubuntu-24.04"]
        for m in matrices
    ), f"AC-1: no job pins the contractual matrix python×os; got matrices: {matrices}"


def test_every_third_party_action_is_sha_pinned_not_tag_pinned() -> None:
    # AC-1: every `uses:` whose value contains `/` (third-party action) must
    # be pinned by full 40-char SHA. Local composites (no `/`) are exempt.
    uses_values: list[str] = []
    for job in _wf()["jobs"].values():
        for step in job.get("steps", []):
            if "uses" in step and "/" in step["uses"]:
                uses_values.append(step["uses"])
    offenders = [u for u in uses_values if not SHA_PIN_RE.match(u)]
    assert offenders == [], (
        f"AC-1: these `uses:` lines are tag/branch-pinned, not SHA-pinned: {offenders}"
    )


# ---------------------------------------------------------------------------
# AC-2: concurrency, permissions, trigger surface.
# ---------------------------------------------------------------------------


def test_ci_workflow_concurrency_cancels_old_runs_on_same_ref() -> None:
    conc = _wf()["concurrency"]
    assert conc["group"] == "${{ github.ref }}", (
        f"AC-2: concurrency.group must be ${{{{ github.ref }}}}; got {conc.get('group')!r}"
    )
    assert conc.get("cancel-in-progress") is True, (
        "AC-2 mandates cancel-in-progress: true (CI quota; load-bearing)"
    )


def test_ci_workflow_top_level_permissions_are_read_only() -> None:
    # AC-2 exact equality — additional permission entries are forbidden in Phase 0.
    assert _wf()["permissions"] == {"contents": "read"}, (
        f"AC-2: workflow permissions must be exactly {{contents: read}}; "
        f"got {_wf().get('permissions')}"
    )


def test_ci_workflow_triggers_exclude_pull_request_target() -> None:
    triggers = _on(_wf())
    keys = set(triggers.keys()) if isinstance(triggers, dict) else set(triggers)
    assert "pull_request_target" not in keys, (
        "AC-2: pull_request_target grants write tokens to fork PRs; never enable in Phase 0"
    )
    assert "workflow_run" not in keys, "AC-2: workflow_run is forbidden in Phase 0"
    assert keys.issubset(ALLOWED_TRIGGERS), f"AC-2: unexpected triggers {keys - ALLOWED_TRIGGERS}"


def test_no_job_widens_contents_permission_beyond_read() -> None:
    # AC-2: job-level `contents: write` is forbidden in Phase 0.
    for name, job in _wf()["jobs"].items():
        perms = job.get("permissions", {})
        if isinstance(perms, dict):
            assert perms.get("contents", "read") == "read", (
                f"AC-2: job `{name}` elevates contents perm: {perms}"
            )


# ---------------------------------------------------------------------------
# AC-3: fence install discipline.
# ---------------------------------------------------------------------------


def test_fence_job_install_is_two_step_and_excludes_dev_extras() -> None:
    """AC-3 (Phase A closure-measurement invariant — ADR-0002 / ADR-0006).

    The fence job runs the closure-measurement test
    (``tests/unit/test_pyproject_fence.py``) BEFORE any ``[dev]`` /
    ``[agents]`` / ``[service]`` extras are installed. After the
    measurement, the Phase-4 S1-05 path-scoped fence (`tests/fence/`)
    runs against the full ``[dev]`` toolchain (`import-linter` etc.).
    Test ordering invariant: ``pip install -e .[dev]`` MUST NOT appear in
    any step before the closure-measurement ``pytest`` invocation.
    """
    fence = _wf()["jobs"]["fence"]
    steps = fence.get("steps", [])
    runs = _flatten_run(fence)
    assert "pip install -e ." in runs, "AC-3: fence job must install bare `pip install -e .`"
    assert "pip install pytest" in runs, (
        "AC-3: fence must install pytest STANDALONE after bare `pip install -e .` "
        "so the closure measurement is uncontaminated (ADR-0006 §Consequences)"
    )

    # Ordering invariant: the closure-measurement pytest invocation must come
    # before any [dev] install. Compute the index of the test invocation
    # against the index of the first step whose `run` mentions a forbidden
    # extras install.
    test_step_idx: int | None = None
    forbidden_install_idx: int | None = None
    for idx, step in enumerate(steps):
        run = step.get("run", "")
        if "tests/unit/test_pyproject_fence.py" in run and test_step_idx is None:
            test_step_idx = idx
        if any(token in run for token in ("[dev]", "[agents]", "[service]", "-e .[dev]")):
            if forbidden_install_idx is None:
                forbidden_install_idx = idx
    assert test_step_idx is not None, (
        "AC-3: fence job must invoke `pytest ... tests/unit/test_pyproject_fence.py`"
    )
    if forbidden_install_idx is not None:
        # If [dev] is installed in this job, it MUST be after the closure-
        # measurement test runs (Phase-4 S1-05 AC-22 — Phase B may install
        # [dev] for the path-scoped + audit-lint fence).
        assert forbidden_install_idx > test_step_idx, (
            "AC-3: [dev]/[agents]/[service] extras install must come AFTER the "
            f"closure-measurement step (test_step_idx={test_step_idx}, "
            f"forbidden_install_idx={forbidden_install_idx}). Installing extras "
            "before the closure measurement contaminates "
            "`scan_installed_distribution` (ADR-0002 / ADR-0006)."
        )
    assert "pytest -q" in runs, "AC-3: fence pytest invocation must use `-q`"


def test_fence_job_phase_b_runs_tests_fence_tree() -> None:
    """Phase-4 S1-05 AC-22 — the dedicated CI fence gate mirrors ``make fence``.

    The fence job's second phase runs ``tests/fence/`` so a path-scope
    regression (Phase-4 ADR-0003) fails the dedicated CI gate, not just the
    ``test`` job. Without this, ``make fence`` locally and the CI ``test``
    job both fail but the dedicated CI ``fence`` gate stays green — a
    confusing local/CI divergence the AC explicitly forbids.
    """
    fence = _wf()["jobs"]["fence"]
    runs = _flatten_run(fence)
    assert "tests/fence/" in runs, (
        "S1-05 AC-22: fence job must invoke `pytest ... tests/fence/` "
        "(mirrors `make fence` so the dedicated CI gate matches the local target)."
    )


# ---------------------------------------------------------------------------
# AC-6 reaches CI via the `lint` job (not `typecheck`).
# ---------------------------------------------------------------------------


def test_lint_job_invokes_make_lint_imports() -> None:
    runs = _flatten_run(_wf()["jobs"]["lint"])
    assert "make lint-imports" in runs, (
        "AC-6 contract must reach CI via the `lint` job, not `typecheck`"
    )


# ---------------------------------------------------------------------------
# AC-11: security job content.
# ---------------------------------------------------------------------------


def test_security_job_invokes_pip_audit_and_osv_scanner_against_uv_lock() -> None:
    sec = _wf()["jobs"]["security"]
    runs = _flatten_run(sec)
    uses_lines = [s.get("uses", "") for s in sec.get("steps", [])]
    assert "pip-audit" in runs, "AC-11: security job must invoke `pip-audit`"
    assert "uv.lock" in runs, "AC-11: security job must reference `uv.lock`"
    osv_via_action = any("google/osv-scanner-action" in u for u in uses_lines)
    osv_via_run = "osv-scanner" in runs
    assert osv_via_action or osv_via_run, (
        "AC-11: security job must invoke osv-scanner (action or direct run)"
    )


# ---------------------------------------------------------------------------
# AC-12: docs path filtering (Option A inline OR Option B separate workflow).
# ---------------------------------------------------------------------------


def test_docs_job_path_filtering_is_wired_per_ac_12() -> None:
    if DOCS_WORKFLOW.exists():
        # Option B: dedicated docs.yml with top-level paths filter.
        cfg = yaml.safe_load(DOCS_WORKFLOW.read_text())
        triggers = cfg.get(True) if True in cfg else cfg["on"]
        paths: list[str] | None = None
        if isinstance(triggers, dict):
            for trigger_name in ("pull_request", "push"):
                tcfg = triggers.get(trigger_name)
                if isinstance(tcfg, dict) and "paths" in tcfg:
                    paths = list(tcfg["paths"])
                    break
        assert paths is not None and {"docs/**", "mkdocs.yml"}.issubset(set(paths)), (
            f"AC-12 Option B: docs.yml must filter on docs/** + mkdocs.yml; got: {paths}"
        )
        return

    # Option A: inline `dorny/paths-filter` setup job + `docs` job `if:` guard.
    wf = _wf()
    uses_paths_filter = any(
        "dorny/paths-filter" in s.get("uses", "")
        for j in wf["jobs"].values()
        for s in j.get("steps", [])
    )
    docs_has_if = "if" in wf["jobs"].get("docs", {})
    assert uses_paths_filter and docs_has_if, (
        "AC-12 Option A: requires `dorny/paths-filter` setup job + `docs.if:` guard"
    )


# ---------------------------------------------------------------------------
# AC-5: [tool.importlinter] declarative validation (parsed from pyproject).
# ---------------------------------------------------------------------------


def _importlinter_cfg() -> dict[str, Any]:
    # pyproject.toml already pins >=3.11, so `tomllib` is always available.
    return tomllib.loads(PYPROJECT.read_text())["tool"]["importlinter"]


def test_importlinter_config_root_packages_includes_codegenie() -> None:
    cfg = _importlinter_cfg()
    roots = cfg.get("root_packages") or [cfg["root_package"]]
    assert "codegenie" in roots, (
        f"AC-5: [tool.importlinter] root_packages must include `codegenie`; got {roots}"
    )


def test_importlinter_has_two_forbidden_contracts_for_cli_and_init() -> None:
    contracts = _importlinter_cfg()["contracts"]
    forbidden = [c for c in contracts if c.get("type") == "forbidden"]
    sources_per_contract = [set(c.get("source_modules", [])) for c in forbidden]
    expected_heavy = {"yaml", "jsonschema", "pydantic", "blake3", "structlog"}
    cli_contract = next(
        (c for c, s in zip(forbidden, sources_per_contract, strict=True) if "codegenie.cli" in s),
        None,
    )
    init_contract = next(
        (c for c, s in zip(forbidden, sources_per_contract, strict=True) if s == {"codegenie"}),
        None,
    )
    assert cli_contract is not None, "AC-5: missing `type: forbidden` contract for codegenie.cli"
    assert init_contract is not None, (
        "AC-5: missing `type: forbidden` contract for codegenie (init)"
    )
    for c in (cli_contract, init_contract):
        assert set(c["forbidden_modules"]) >= expected_heavy, (
            f"AC-5: contract under-blocks heavy modules: {set(c['forbidden_modules'])}"
        )
