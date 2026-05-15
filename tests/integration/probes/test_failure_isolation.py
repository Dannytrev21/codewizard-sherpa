"""S5-05 — AC-ERR-1: probe failure isolation (Phase 1 fail-loud + recovery).

If one probe's ``run()`` raises, ``codegenie gather`` must:

1. Exit 0 (failure isolation — ``phase-arch-design.md §"Failure modes &
   recovery"``).
2. Populate every other probe's slice normally.
3. Record the failing probe in the audit run-record with
   ``exit_status == "error"`` (per ``audit._exit_status_for``'s mapping
   of a ``Ran(errors=[...])`` execution).

This test monkeypatches :meth:`codegenie.probes.deployment.DeploymentProbe.run`
to raise. Deployment is the chosen sacrificial probe because its slice
is **not** load-bearing for any sibling probe's correctness (CI /
Language / NBS / NM / TestInventory all dispatch independently of
Deployment's output).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.probes.conftest import (
    PHASE_1_PROBE_TO_SLICE,
    _copy_tree,
    _invoke_gather,
    _load_envelope,
    _stub_node_version_check,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures"


def test_deployment_failure_does_not_kill_gather(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-ERR-1 — one probe raising leaves the other five slices intact."""
    _stub_node_version_check(monkeypatch)

    import codegenie.probes.deployment as deployment_mod

    async def _exploding_run(self: object, repo: object, ctx: object) -> object:  # noqa: ARG001
        raise RuntimeError("forced deployment failure for AC-ERR-1")

    monkeypatch.setattr(deployment_mod.DeploymentProbe, "run", _exploding_run)

    repo = _copy_tree(FIXTURE_ROOT / "node_typescript_helm", tmp_path / "repo")
    result = _invoke_gather(repo)

    # Exit 0 — failure isolation contract.
    assert result.exit_code == 0, result.output

    envelope = _load_envelope(repo)
    probes = envelope["probes"]

    # The five non-deployment probes must produce their slice normally.
    for probe_name, slice_key in PHASE_1_PROBE_TO_SLICE.items():
        if probe_name == "deployment":
            continue
        assert probe_name in probes, f"{probe_name} missing despite being unrelated to the failure"
        assert probes[probe_name].get(slice_key), (
            f"{probe_name}.{slice_key} empty despite being unrelated to the failure"
        )

    # The audit run-record carries an error-variant for deployment.
    import json

    runs_dir = repo / ".codegenie" / "context" / "runs"
    run_files = sorted(runs_dir.glob("*.json"))
    assert run_files, runs_dir
    record = json.loads(run_files[-1].read_text())
    by_name = {p["name"]: p for p in record["probes"]}
    dp_row = by_name.get("deployment")
    assert dp_row is not None, by_name
    assert dp_row["exit_status"] == "error", dp_row
    # blob_sha256 is the empty-string sentinel for errored Ran outputs
    # per ``audit._blob_sha256_for``.
    assert dp_row["blob_sha256"] == "", dp_row
