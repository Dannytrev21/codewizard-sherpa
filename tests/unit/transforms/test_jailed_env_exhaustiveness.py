"""AC-Env-2 — ``JailedEnv`` exhaustiveness fence (positive + negative mypy).

:func:`render` below is an exhaustive ``match`` over the S5-03-widened
``JailedEnv`` sum (``NpmEnv | GitEnv | JvmEnv``); ``assert_never`` in the
wildcard arm makes a missing arm a ``mypy --strict`` error.
:func:`test_mypy_strict_accepts_this_file` proves the exhaustive form
type-checks; :func:`test_mypy_strict_rejects_missing_jvm_arm` proves that
dropping the ``JvmEnv`` arm fails. The negative fence AC-Env-2 names
(``test_jailed_env_mypy_negative.py``) is consolidated into this file per
Rule 7 — one location for the ``JailedEnv`` exhaustiveness discipline.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from typing import assert_never

from codegenie.transforms.sandbox_jail import GitEnv, JailedEnv, JvmEnv, NpmEnv

_REPO_ROOT = Path(__file__).resolve().parents[3]


def render(env: JailedEnv) -> str:
    """Exhaustive dispatch over the widened ``JailedEnv`` sum."""
    match env:
        case NpmEnv():
            return "npm"
        case GitEnv():
            return "git"
        case JvmEnv():
            return "jvm"
        case _:
            assert_never(env)


def test_render_dispatches_every_variant() -> None:
    """AC-Env-2 runtime control — each variant routes to its own arm."""
    assert render(NpmEnv()) == "npm"
    assert render(GitEnv()) == "git"
    assert render(JvmEnv(java_home="/opt/java", max_heap_mib=1024)) == "jvm"


def test_mypy_strict_accepts_this_file() -> None:
    """AC-Env-2 positive — ``mypy --strict`` accepts this file: the ``render``
    ``match`` is exhaustive over ``NpmEnv | GitEnv | JvmEnv``."""
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(Path(__file__))],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_REPO_ROOT),
    )
    assert proc.returncode == 0, (
        f"mypy --strict rejected the exhaustive JailedEnv match; "
        f"stdout=\n{proc.stdout}\nstderr=\n{proc.stderr}"
    )


_MISSING_JVM_ARM = textwrap.dedent(
    """
    from typing import assert_never
    from codegenie.transforms.sandbox_jail import GitEnv, JailedEnv, NpmEnv

    def render(env: JailedEnv) -> str:
        match env:
            case NpmEnv():
                return "npm"
            case GitEnv():
                return "git"
            case _ as unexpected:
                assert_never(unexpected)
        return ""
    """
)


def test_mypy_strict_rejects_missing_jvm_arm(tmp_path: Path) -> None:
    """AC-Env-2 negative — dropping the ``JvmEnv`` arm fails ``mypy --strict``:
    ``assert_never`` cannot narrow the un-handled ``JvmEnv`` to ``Never``."""
    fixture = tmp_path / "missing_jvm_arm.py"
    fixture.write_text(_MISSING_JVM_ARM)
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(fixture)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_REPO_ROOT),
    )
    combined = (proc.stdout + proc.stderr).lower()
    assert proc.returncode != 0, (
        f"mypy --strict accepted a JailedEnv match missing the JvmEnv arm; "
        f"stdout=\n{proc.stdout}\nstderr=\n{proc.stderr}"
    )
    assert "never" in combined or "assert_never" in combined or "argument" in combined, (
        f"mypy error did not reference the assert_never narrowing failure: "
        f"stdout=\n{proc.stdout}\nstderr=\n{proc.stderr}"
    )
