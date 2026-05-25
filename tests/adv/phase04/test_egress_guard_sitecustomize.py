"""AC-26 — :file:`sitecustomize.py` at the repo root must be auto-discovered.

Every other test in the suite calls :meth:`EgressGuard.install` explicitly
(via the autouse fixture in :mod:`test_egress_guard`). This is the **only**
test that proves the ``sitecustomize.py``-at-repo-root mechanism actually
fires: it launches a fresh interpreter from the repo root with no explicit
install and asserts the ``self-check egress`` command reports
``installed=True``.

If the subprocess reports ``installed=False``, the repo-root
``sitecustomize.py`` is not being picked up by this project's hatchling
editable install — surface as a blocker, do not paper over.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.phase04_adv

_REPO_ROOT: Path = Path(__file__).resolve().parents[3]


def test_sitecustomize_auto_installs_in_fresh_interpreter() -> None:
    # Sanity-pin the expected location of sitecustomize.py.
    assert (_REPO_ROOT / "sitecustomize.py").is_file(), (
        f"sitecustomize.py missing at {_REPO_ROOT} — AC-5 file precondition fails"
    )

    env = os.environ.copy()
    # Belt-and-suspenders: ensure the repo root is on PYTHONPATH so site.py
    # discovers ``sitecustomize`` even on installs where ``-m`` does not add
    # cwd to ``sys.path[0]`` before site.py runs. The story (AC-26) accepts
    # either bootstrap path — what matters is the wrapper is active.
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(_REPO_ROOT) + (os.pathsep + existing if existing else "")

    result = subprocess.run(  # noqa: S603 — we control argv; not shell=True
        [sys.executable, "-m", "codegenie", "self-check", "egress"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
        env=env,
        timeout=30,
    )
    assert "installed=True" in result.stdout, (
        f"sitecustomize.py auto-discovery failed. stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
