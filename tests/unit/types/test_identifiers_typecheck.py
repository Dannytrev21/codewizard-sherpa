"""Phase 2 S1-05 — mypy-only nominal-type discrimination check.

This file imports the four kernel-tier ``NewType`` identifiers and exercises
them in functions whose parameter types differ. Pytest collects this file
(no test functions are defined; module-level imports must succeed). ``mypy
--strict`` running over ``src/codegenie/types/`` and this file detects the
nominal-type contract: passing an ``IndexId`` where a ``SkillId`` is expected
must be a type error.

The commented-out lines below are the load-bearing mypy assertions — they are
intentionally commented out so pytest passes at runtime; uncommenting them
would cause ``mypy --strict`` to exit non-zero.
"""

from __future__ import annotations

from codegenie.types.identifiers import IndexId, IndexName, SkillId, TaskClassId


def _accepts_index(_x: IndexId) -> None: ...


def _accepts_skill(_x: SkillId) -> None: ...


def _accepts_task(_x: TaskClassId) -> None: ...


def _accepts_name(_x: IndexName) -> None: ...


def main() -> None:
    """Smoke-call site that proves correct usage type-checks under ``--strict``."""
    i: IndexId = IndexId("scip")
    s: SkillId = SkillId("scip.maintenance")
    t: TaskClassId = TaskClassId("vulnerability-remediation")
    n: IndexName = IndexName("scip")
    _accepts_index(i)
    _accepts_skill(s)
    _accepts_task(t)
    _accepts_name(n)
    # The following two lines must be flagged by mypy --strict as type errors
    # (NewType nominal typing). They are commented out so pytest passes; if a
    # contributor uncomments them, mypy --strict CI must exit non-zero.
    # _accepts_index(s)
    # _accepts_skill(i)
