"""S5-05 — Turborepo monorepo block (S2-01 ``monorepo`` precedence chain).

Asserts the ``probes.language_detection.language_stack.monorepo``
block is populated with ``tool == "turbo"`` and ``markers`` ==
sorted-union of hit marker basenames when the fixture carries both
``turbo.json`` AND ``package.json#workspaces`` (the precedence-chain
shape S5-04's ``node_monorepo_turbo`` fixture exists to exercise).

Workspace-member traversal (``packages/app-web/package.json``,
``packages/app-api/package.json`` being individually probed) is **Phase
2** scope — not asserted here per ``phase-arch-design.md §"Open
questions"``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.schema.validator import validate as validate_envelope
from tests.integration.probes.conftest import (
    _copy_tree,
    _invoke_gather,
    _load_envelope,
    _stub_node_version_check,
    assert_monorepo_markers,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures"


def test_monorepo_turbo_block_populated_root_build_system(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-MR-1..4 — monorepo markers + root build_system + envelope validity."""
    _stub_node_version_check(monkeypatch)
    repo = _copy_tree(FIXTURE_ROOT / "node_monorepo_turbo", tmp_path / "repo")

    result = _invoke_gather(repo)
    assert result.exit_code == 0, result.output

    envelope = _load_envelope(repo)

    # AC-MR-2 — monorepo precedence-chain detection. ``markers`` is the
    # sorted union of all hit marker basenames per the
    # ``language_detection`` schema (S2-01).
    assert_monorepo_markers(
        envelope,
        expected_tool="turbo",
        expected_markers=["package.json", "turbo.json"],
    )

    # AC-MR-3 — root build_system slice. Workspace-member traversal is
    # Phase 2's concern; this story does not assert anything about
    # ``packages/app-web/package.json`` etc.
    bs = envelope["probes"]["node_build_system"]["build_system"]
    assert bs["package_manager"] == "pnpm", bs

    # AC-MR-4 — envelope validates via the production seam.
    validate_envelope(envelope)
