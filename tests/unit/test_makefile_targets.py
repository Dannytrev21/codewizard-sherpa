"""Makefile contract — pins the nine required targets and their recipe bodies.

TDD red anchor for story S1-03. Asserts that ``Makefile`` exists at the repo
root, declares the nine targets (each ``.PHONY``), and that every recipe whose
body is contractual contains the load-bearing tool invocation verbatim. Also
pins ``uv.lock`` parity with ``pyproject.toml`` (catches stale lockfiles) and
guards recipe bodies against bash-isms that would silently diverge between
macOS (sh-as-bash) and Linux (sh-as-dash) CI runners.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = PROJECT_ROOT / "Makefile"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
UV_LOCK = PROJECT_ROOT / "uv.lock"

REQUIRED_TARGETS = {
    "bootstrap",
    "check",
    "lint",
    "typecheck",
    "test",
    "docs",
    "fence",
    "audit-verify",
    "clean",
}


def _recipe_body(target: str, text: str) -> str:
    """Return the literal recipe-body text for ``target``.

    The body is the tab-indented lines immediately following ``target:`` up to
    the next non-tab line. Returns empty string if the target has no recipe
    (e.g., a prerequisite-only target like ``check``).
    """
    m = re.search(
        rf"^{re.escape(target)}:[^\n]*\n((?:\t.*\n)*)",
        text,
        flags=re.MULTILINE,
    )
    return m.group(1) if m else ""


# --- AC-1 -------------------------------------------------------------------


def test_makefile_exists_at_repo_root() -> None:
    # AC-1: file present at root
    assert MAKEFILE.is_file(), "Makefile must exist at the repo root"


def test_makefile_declares_all_required_targets_as_phony() -> None:
    # AC-1: nine targets declared, all .PHONY
    text = MAKEFILE.read_text()
    declared = set(re.findall(r"^([a-zA-Z][\w\-]*):", text, flags=re.MULTILINE))
    missing = REQUIRED_TARGETS - declared
    assert not missing, f"Makefile missing targets: {missing}"
    phony_decls = re.findall(r"^\.PHONY:\s*(.+)$", text, flags=re.MULTILINE)
    phony_names = {name for line in phony_decls for name in line.split()}
    assert REQUIRED_TARGETS.issubset(phony_names), (
        f".PHONY missing: {REQUIRED_TARGETS - phony_names}"
    )


# --- AC-2 -------------------------------------------------------------------


def test_bootstrap_recipe_has_both_uv_and_python_m_pip_branches() -> None:
    # AC-2: both branches present; substrings chosen so they DO NOT overlap.
    # The bare substring "pip install" overlaps with "uv pip install", so a
    # single uv-only line would falsely satisfy a "pip install" check. We
    # assert "python -m pip install" instead — that string appears ONLY in
    # the fallback branch, never in the uv branch.
    body = _recipe_body("bootstrap", MAKEFILE.read_text())
    assert body, "bootstrap must have a recipe"
    assert "uv pip install" in body, "bootstrap must use `uv pip install` when uv is available"
    assert "python -m pip install" in body, (
        "bootstrap must fall back to `python -m pip install` when uv is absent "
        "(NOT just `pip install` — that substring is also inside `uv pip install`)"
    )
    assert "command -v uv" in body or "which uv" in body, (
        "bootstrap must detect uv on PATH via shell (`command -v uv` or `which uv`); "
        "Python-based detection is forbidden by AC-2"
    )


# --- AC-3 -------------------------------------------------------------------


def test_check_is_prerequisite_chain_in_exact_order() -> None:
    # AC-3: prerequisite-style, exact order, no recipe body
    text = MAKEFILE.read_text()
    m = re.search(r"^check:\s*(.+)$", text, flags=re.MULTILINE)
    assert m is not None, "check target must exist"
    deps = m.group(1).split()
    assert deps == ["lint", "typecheck", "test", "fence"], (
        f"`make check` must chain lint → typecheck → test → fence as prerequisites; got {deps}"
    )
    body = _recipe_body("check", text)
    assert body.strip() == "", (
        f"`check` should be prerequisites-only (no recipe body); got body:\n{body}"
    )


# --- AC-4 -------------------------------------------------------------------


def test_lint_recipe_invokes_ruff_check_and_ruff_format_check() -> None:
    body = _recipe_body("lint", MAKEFILE.read_text())
    assert "ruff check" in body, "lint must invoke `ruff check`"
    assert "ruff format --check" in body, "lint must invoke `ruff format --check`"


def test_typecheck_recipe_invokes_mypy_strict_on_src() -> None:
    body = _recipe_body("typecheck", MAKEFILE.read_text())
    # accept both `mypy --strict src/` and `mypy --strict src`
    assert re.search(r"mypy --strict src/?(\s|$)", body), (
        "typecheck must invoke `mypy --strict src/`"
    )


def test_test_recipe_invokes_pytest_q() -> None:
    body = _recipe_body("test", MAKEFILE.read_text())
    assert "pytest -q" in body, "test must invoke `pytest -q`"


def test_fence_recipe_invokes_pytest_on_fence_test_path() -> None:
    body = _recipe_body("fence", MAKEFILE.read_text())
    assert "pytest -q tests/unit/test_pyproject_fence.py" in body, (
        "fence must invoke `pytest -q tests/unit/test_pyproject_fence.py`"
    )


# --- AC-5, AC-6 -------------------------------------------------------------


def test_docs_recipe_invokes_mkdocs_build_strict() -> None:
    # AC-5: `--strict` is load-bearing per phase-arch §CI gates; bare
    # `mkdocs build` silently downgrades the docs gate.
    body = _recipe_body("docs", MAKEFILE.read_text())
    assert "mkdocs build --strict" in body, (
        "docs must invoke `mkdocs build --strict` (the --strict flag is load-bearing)"
    )


def test_audit_verify_recipe_invokes_codegenie_audit_verify() -> None:
    # AC-6
    body = _recipe_body("audit-verify", MAKEFILE.read_text())
    assert "python -m codegenie audit verify" in body, (
        "audit-verify must invoke `python -m codegenie audit verify`"
    )


# --- AC-7 -------------------------------------------------------------------


def _normalize(name: str) -> str:
    return name.lower().replace("_", "-")


def _declared_packages_from_pyproject() -> set[str]:
    pyproj = tomllib.loads(PYPROJECT.read_text())
    deps: list[str] = list(pyproj["project"].get("dependencies", []))
    deps += list(pyproj["project"].get("optional-dependencies", {}).get("dev", []))
    declared: set[str] = set()
    for spec in deps:
        # Take the leading [A-Za-z0-9._-]+ as the package name.
        m = re.match(r"[A-Za-z0-9._-]+", spec)
        if m:
            declared.add(_normalize(m.group(0)))
    return declared


def test_uv_lock_exists_and_is_non_empty() -> None:
    # AC-7 (existence half)
    assert UV_LOCK.is_file(), "uv.lock must be committed at the repo root"
    assert UV_LOCK.stat().st_size > 0, "uv.lock must not be empty"


def test_uv_lock_is_in_lockstep_with_pyproject_dep_set() -> None:
    # AC-7 (parity half): every package named in pyproject.toml's
    # [project.dependencies] and [project.optional-dependencies.dev] must
    # appear in uv.lock's [[package]] table. Catches stale lockfiles that
    # predate S1-01's pyproject.toml without forcing the test to invoke `uv`.
    declared = _declared_packages_from_pyproject()
    lock = tomllib.loads(UV_LOCK.read_text())
    locked = {_normalize(p["name"]) for p in lock.get("package", [])}
    missing = declared - locked
    assert not missing, (
        f"uv.lock is stale relative to pyproject.toml; missing packages: {sorted(missing)}. "
        "Re-run `uv lock` and commit the result."
    )


# --- AC-9 -------------------------------------------------------------------


def test_makefile_recipes_contain_no_bash_isms() -> None:
    # AC-9: recipe shell defaults to /bin/sh (POSIX). Bash-isms are a latent
    # macOS-vs-Linux divergence (default sh on macOS may be bash, masking the
    # bug locally; on Linux CI the default sh is dash and recipes break).
    text = MAKEFILE.read_text()
    all_bodies = "".join(_recipe_body(t, text) for t in REQUIRED_TARGETS)
    assert "[[" not in all_bodies, (
        "Makefile recipes must not use bash `[[`; recipe shell is /bin/sh"
    )
    assert "]]" not in all_bodies, "Makefile recipes must not use bash `]]`"
    assert re.search(r"\bfunction\s+\w+\s*\(\)", all_bodies) is None, (
        "Makefile recipes must not use bash `function NAME()` syntax"
    )


# --- AC-8 (this file is the red anchor; its existence + green is AC-8) -----
# Implicit: pytest discovering and passing this file IS AC-8.
