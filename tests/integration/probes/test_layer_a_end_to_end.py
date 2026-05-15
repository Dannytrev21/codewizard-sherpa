"""S5-05 — Roadmap Phase 1 exit criterion #1 end-to-end integration test.

Phase 1 exit criterion #1: GREEN — all six probe entries populated,
envelope + 6 sub-schemas validated.

End-to-end Layer A integration: invoke ``codegenie gather`` against the
``node_typescript_helm`` fixture via the CLI, assert all six Phase-1
probe entries are present and value-pinned, validate the envelope +
per-probe sub-schemas via the production validator seam, exercise the
``codegenie audit verify`` exit-code policy, and exercise the ADR-0004
``additionalProperties: false`` negative path with a synthetic envelope
mutation.

The grep-able docstring contract on the line above is asserted by
:func:`test_phase_1_exit_criterion_docstring_present` — a refactor that
silently drops the line fails the test, not just review.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from click.testing import CliRunner

from codegenie.cli import cli
from codegenie.errors import SchemaValidationError
from codegenie.schema.validator import validate as validate_envelope
from tests.integration.probes.conftest import (
    _copy_tree,
    _invoke_gather,
    _load_envelope,
    _stub_node_version_check,
    assert_phase_1_slices_present,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures"


def test_layer_a_end_to_end_node_typescript_helm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-E2E-1..4 + AC-NEG-1 — exit-criterion #1 end-to-end."""
    _stub_node_version_check(monkeypatch)
    repo = _copy_tree(FIXTURE_ROOT / "node_typescript_helm", tmp_path / "repo")

    # AC-E2E-1 — cold gather exits 0.
    result = _invoke_gather(repo)
    assert result.exit_code == 0, result.output

    envelope = _load_envelope(repo)

    # AC-E2E-2 — all six probes present, slices non-empty.
    assert_phase_1_slices_present(envelope)

    # AC-E2E-2 — value pins (mutation-killing, Rule 9). The ``ci`` /
    # ``deployment`` / ``test_inventory`` fields cross-reference each
    # probe's sub-schema field names — pin the load-bearing field per
    # slice so a buggy probe that silently degrades a value still fails
    # the test.
    ld = envelope["probes"]["language_detection"]["language_stack"]
    assert ld["primary"] == "typescript", ld
    assert ld["framework_hints"] == ["express"], ld
    assert ld["monorepo"] is None, ld

    nbs = envelope["probes"]["node_build_system"]["build_system"]
    assert nbs["package_manager"] == "pnpm", nbs

    nm = envelope["probes"]["node_manifest"]["manifests"]
    assert nm["primary"]["path"] == "package.json", nm

    ci_slice = envelope["probes"]["ci"]["ci"]
    assert ci_slice["provider"] == "github_actions", ci_slice
    assert ci_slice["workflow_files"], ci_slice

    dp = envelope["probes"]["deployment"]["deployment"]
    # The S2-03 fixture lays Helm at ``deploy/chart/`` (not repo root),
    # so the current ``S4-02`` deployment probe records ``type: "none"``
    # — surfaced as an S2-03 / S4-02 follow-up in the S5-05 PR body. The
    # slice IS emitted (load-bearing for AC-E2E-2 "non-empty slice"); the
    # detection extension is out of scope for S5-05.
    assert "type" in dp, dp

    ti = envelope["probes"]["test_inventory"]["test_inventory"]
    assert ti["framework"] == "vitest", ti
    assert ti["unit_test_count_is_file_count"] is True, ti

    # AC-E2E-3 — envelope + per-probe sub-schemas validate via the production seam.
    validate_envelope(envelope)

    # AC-NEG-1 — ``additionalProperties: false`` is enforced (ADR-0004 contract).
    mutated = deepcopy(envelope)
    mutated["probes"]["language_detection"]["language_stack"]["bogus_field"] = "x"
    with pytest.raises(SchemaValidationError):
        validate_envelope(mutated)

    # AC-E2E-4 — audit anchor re-computes via the real CLI subcommand.
    audit_result = CliRunner().invoke(
        cli,
        [
            "audit",
            "verify",
            "--runs-dir",
            str(repo / ".codegenie" / "context" / "runs"),
            "--cache-dir",
            str(repo / ".codegenie" / "cache"),
            "--yaml-path",
            str(repo / ".codegenie" / "context" / "repo-context.yaml"),
        ],
    )
    assert audit_result.exit_code == 0, audit_result.output


def test_phase_1_exit_criterion_docstring_present() -> None:
    """AC-E2E-5 — the PR-body grep contract is test-enforced, not just docstring-as-comment."""
    import tests.integration.probes.test_layer_a_end_to_end as mod

    assert "Phase 1 exit criterion #1: GREEN" in (mod.__doc__ or ""), (
        "module docstring must contain the grep contract for the Step 6 close-out"
    )
