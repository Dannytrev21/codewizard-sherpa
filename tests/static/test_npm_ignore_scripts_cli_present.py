"""S4-05 AC-18 / AC-19 — forward-looking ``--ignore-scripts`` CLI-half
static fence.

Phase 3 03-ADR-0006 requires every ``npm`` subprocess invocation to pass
``--ignore-scripts`` at BOTH the CLI tuple AND the environment
(``npm_config_ignore_scripts="true"``). S4-01 already pins the env half
inside :class:`NpmEnv`. This static fence pins the CLI half: it AST-walks
every ``JailedSubprocessSpec(...)`` construction under
``src/codegenie/transforms/engines/`` (S5-02's future home) and asserts
that any ``cmd`` tuple starting with ``"npm"`` and naming a
lifecycle-running subcommand also literally contains ``"--ignore-scripts"``.

The fence is **forward-looking**: when S5-02 lands the
``NpmLockfileRecipeEngine``, this fence wakes up structurally. Until then
the live target directory is empty and the fence skips loudly (with
``"S5-02"`` in the skip message so future readers can grep the cause).
AC-19's planted-positive ensures the walker code is exercised even when
the live scan target is empty — a mutant walker that returns ``[]``
regardless of input is killed.

**Catalog rationale** (resolved by validator notes 8 + 9 in the story):
the lifecycle-running subset is the canonical list of npm subcommands
that *can* execute package scripts. ``install``/``rebuild``/``update``/
``run-script`` are the load-bearing ones; aliases (``i``/``rb``/``up``/
``t``) cover idiomatic shorthand. ``audit``/``ls`` are advisory commands
that do NOT run lifecycle scripts and are intentionally omitted.

**Literal-only limitation**: the walker matches only literal tuples/lists;
``JailedSubprocessSpec(cmd=variable_holding_cmd)`` is NOT followed. S5-02
adds the paired runtime defence (the npm engine constructs every spec via
a helper that always-prepends ``--ignore-scripts``).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

__all__ = ["_NPM_LIFECYCLE_SUBCOMMANDS", "_find_npm_specs_missing_ignore_scripts"]


_NPM_LIFECYCLE_SUBCOMMANDS: Final[frozenset[str]] = frozenset(
    {
        "install",
        "i",
        "ci",
        "test",
        "t",
        "rebuild",
        "rb",
        "update",
        "up",
        "pack",
        "publish",
        "exec",
        "run",
        "run-script",
        "start",
        "stop",
        "restart",
    }
)


def _find_npm_specs_missing_ignore_scripts(root: Path) -> list[tuple[Path, int]]:
    """Walker — returns ``(file, lineno)`` for every ``JailedSubprocessSpec``
    Call node whose literal ``cmd`` tuple/list starts with ``"npm"``,
    names a lifecycle subcommand, and OMITS ``"--ignore-scripts"``.

    Pure function; no I/O beyond ``rglob`` + ``read_text``. Mirrors the
    ``_capability_fence`` walker shape — same kill discipline.
    """
    findings: list[tuple[Path, int]] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "JailedSubprocessSpec"
            ):
                continue
            for kw in node.keywords:
                if kw.arg != "cmd":
                    continue
                if not isinstance(kw.value, (ast.Tuple, ast.List)):
                    continue
                tokens: list[str] = []
                for el in kw.value.elts:
                    if isinstance(el, ast.Constant) and isinstance(el.value, str):
                        tokens.append(el.value)
                if not tokens or tokens[0] != "npm":
                    continue
                if not any(t in _NPM_LIFECYCLE_SUBCOMMANDS for t in tokens[1:]):
                    continue
                if "--ignore-scripts" not in tokens:
                    findings.append((path, node.lineno))
    return findings


# ───────────────────────────────────────────────────────────────────────────
# AC-18 — live forward-looking scan (dormant until S5-02 lands).
# ───────────────────────────────────────────────────────────────────────────


def test_every_npm_spec_includes_ignore_scripts() -> None:
    """AC-18 — every ``JailedSubprocessSpec`` constructed under
    ``src/codegenie/transforms/engines/`` with an ``npm`` lifecycle
    subcommand carries ``--ignore-scripts``. Forward-looking — dormant
    until S5-02 lands; skips loudly with the story ID in the message
    so future readers can grep the cause."""
    engines = Path("src/codegenie/transforms/engines")
    if not engines.exists() or not any(engines.rglob("*.py")):
        pytest.skip("Phase 3 npm engines not yet present (S5-02) — fence dormant")
    violations = _find_npm_specs_missing_ignore_scripts(engines)
    assert violations == [], (
        f"JailedSubprocessSpec with npm lifecycle cmd missing --ignore-scripts: {violations!r}"
    )


# ───────────────────────────────────────────────────────────────────────────
# AC-19 — planted positive: the walker is alive.
# ───────────────────────────────────────────────────────────────────────────


def test_fence_walker_is_alive() -> None:
    """AC-19 — the shipped fixture ``bad_engine.py`` carries the exact
    bad-shape (npm install without ``--ignore-scripts``). The walker
    reports it. A mutant walker that returns ``[]`` regardless of input
    is killed here even when the live scan target (AC-18) is empty."""
    fixture_dir = Path(__file__).parent / "_ignore_scripts_fence_fixtures"
    assert fixture_dir.exists(), (
        f"fixture directory missing: {fixture_dir}; AC-19 cannot prove the walker is alive"
    )

    violations = _find_npm_specs_missing_ignore_scripts(fixture_dir)

    assert len(violations) >= 1, (
        f"fence walker must detect the planted ``npm install`` without "
        f"``--ignore-scripts`` under {fixture_dir!r}; got: {violations!r}"
    )


def test_fence_walker_synthesises_arbitrary_violation(tmp_path: Path) -> None:
    """AC-19 (companion) — a tmp_path-synthesised violation is detected
    too. Catches a regression that hardcodes the fixture directory."""
    bad = tmp_path / "engine.py"
    bad.write_text(
        "from codegenie.transforms.sandbox_jail import JailedSubprocessSpec\n"
        "spec = JailedSubprocessSpec(cmd=('npm', 'rebuild'))\n"
    )

    violations = _find_npm_specs_missing_ignore_scripts(tmp_path)

    assert len(violations) == 1, f"expected one violation; got {violations!r}"


def test_fence_walker_admits_well_formed_spec(tmp_path: Path) -> None:
    """AC-19 (companion) — a spec carrying ``--ignore-scripts`` is NOT
    reported (the walker's positive predicate is the conjunction of
    ``starts-with-npm`` AND ``names-lifecycle-subcommand`` AND
    ``MISSING --ignore-scripts``)."""
    good = tmp_path / "engine_ok.py"
    good.write_text(
        "from codegenie.transforms.sandbox_jail import JailedSubprocessSpec\n"
        "spec = JailedSubprocessSpec(cmd=('npm', 'install', '--ignore-scripts'))\n"
    )

    violations = _find_npm_specs_missing_ignore_scripts(tmp_path)

    assert violations == [], (
        f"a well-formed npm install spec must NOT be flagged; got: {violations!r}"
    )


def test_fence_walker_ignores_non_lifecycle_subcommand(tmp_path: Path) -> None:
    """AC-18 / AC-19 — ``npm audit`` and ``npm ls`` do not run lifecycle
    scripts; the walker does not flag specs missing ``--ignore-scripts``
    on advisory subcommands. Pins the catalog scope discipline."""
    advisory = tmp_path / "audit.py"
    advisory.write_text(
        "from codegenie.transforms.sandbox_jail import JailedSubprocessSpec\n"
        "spec = JailedSubprocessSpec(cmd=('npm', 'audit', '--json'))\n"
    )

    violations = _find_npm_specs_missing_ignore_scripts(tmp_path)

    assert violations == [], (
        f"advisory npm subcommands must not require --ignore-scripts; got: {violations!r}"
    )
