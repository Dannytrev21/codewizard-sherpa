"""``codegenie`` CLI entry point — placeholder slot.

Story S1-05 lands this stub so the ``[tool.importlinter]`` contract for
``codegenie.cli`` (declared in ``pyproject.toml``) has a real module to
analyse. The full CLI surface — ``gather``, ``audit verify``, ``cache gc``
— lands in S4-02 (vertical slice).

Until then, this file MUST stay free of top-level imports of the heavy
modules listed in the import-linter contract (``yaml``, ``jsonschema``,
``pydantic``, ``blake3``, ``structlog``). The cold-start invariant is
enforced by both ``tests/unit/test_cli_cold_start.py`` and the
``lint-imports`` CI job.
"""

from __future__ import annotations
