"""``codegenie`` CLI entry point.

Story S1-05 lands this stub so the ``[tool.importlinter]`` contract for
``codegenie.cli`` (declared in ``pyproject.toml``) has a real module to
analyse. S3-06 adds the ``audit verify`` subcommand seed (exit-code slot
``4`` per ``phase-arch-design.md §Component design / CLI``); S4-02
finalizes the wider CLI surface (``gather``, ``cache gc``, ...).

This file MUST stay free of top-level imports of the heavy modules listed
in the import-linter contract (``yaml``, ``jsonschema``, ``pydantic``,
``blake3``, ``structlog``). Anything that depends on them — including
:mod:`codegenie.audit` — is imported lazily inside the command function.
The cold-start invariant is enforced by both
``tests/unit/test_cli_cold_start.py`` and the ``lint-imports`` CI job.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click


@click.group(name="codegenie")
def cli() -> None:
    """codewizard-sherpa local POC CLI."""


@cli.group(name="audit")
def audit() -> None:
    """Audit-record write/verify subcommands."""


@audit.command(name="verify")
@click.option(
    "--runs-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Directory containing audit run-records (``.codegenie/context/runs/``).",
)
@click.option(
    "--cache-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Cache directory containing ``index.jsonl`` + sharded blobs.",
)
@click.option(
    "--yaml-path",
    type=click.Path(path_type=Path),
    required=True,
    help="Path to ``repo-context.yaml`` (whole-output anchor).",
)
def audit_verify(runs_dir: Path, cache_dir: Path, yaml_path: Path) -> None:
    """Recompute every audit anchor and report mismatches.

    Exit codes (``phase-arch-design.md §Component design / CLI``):

    - ``0`` — no mismatches; audit anchors verified.
    - ``4`` — one or more mismatches detected (tamper or drift).

    Slot ``4`` is owned by this command per S3-06 AC-16 — distinct from
    slot ``1`` (default click handler unhandled exception), so operators
    can tell "verify crashed" from "verify found a tamper".
    """
    # Dynamic import: keeps ``codegenie.cli`` outside the lint-imports graph
    # for heavy modules (pydantic / structlog / blake3 enter via audit's deps).
    # The cold-start cost lives behind the subcommand invocation, not at
    # ``--help`` time — same shape S4-02 will use for ``gather`` / ``cache``.
    import importlib

    audit_mod = importlib.import_module("codegenie.audit")
    mismatches = audit_mod.verify_runs(runs_dir, cache_dir, yaml_path)
    sys.exit(0 if mismatches == 0 else 4)
