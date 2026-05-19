"""Fixture for the ``--ignore-scripts`` CLI-half static fence (AC-19).

Constructs a ``JailedSubprocessSpec`` with an ``npm install`` ``cmd`` tuple
that is **missing** the ``--ignore-scripts`` flag. The fence walker must
detect this exact shape; if a future refactor of the walker silently
returns ``[]`` regardless of input, AC-19 catches the regression here.

Intentionally NOT imported by any production module. Skipped by the
default pytest collection (no ``test_*`` function); only the walker
reaches in via direct file-path read.
"""

from __future__ import annotations

from codegenie.transforms.sandbox_jail import JailedSubprocessSpec  # noqa: F401


def _build_bad_spec() -> object:
    """Return a deliberately-malformed npm spec for fence detection.

    Real consumers must construct this via S5-02's helper that always
    prepends ``--ignore-scripts``; this fixture is the negative test.
    """
    # This call is NEVER executed in the live test suite — the file is
    # parsed by the AST walker, not imported. The shape on disk is what
    # the walker reports.
    spec = JailedSubprocessSpec(  # type: ignore[call-arg]
        cmd=("npm", "install", "--package-lock-only"),
    )
    return spec
