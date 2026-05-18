"""S7-03 AC-38 — Phase 1 fixture coexistence (non-collision).

Phase 1's ``tests/fixtures/node_typescript_helm/`` is **not** under
``tests/fixtures/portfolio/`` and is **not** swept by ``regen_golden.py
--portfolio``. The two tests here assert that:

1. No Phase-1 per-probe collision: no file at
   ``tests/golden/probes/*/node_typescript_helm.json``.
2. If Phase 1's YAML golden exists at
   ``tests/golden/node_typescript_helm.repo-context.yaml`` (S6-01),
   S7-03's regen does not touch it.

S6-01 has not shipped yet as of this story; if/when it does, the YAML
golden's SHA-256 is captured before invoking ``regen_golden.py
--portfolio`` and re-checked after.
"""

from __future__ import annotations

import hashlib
import subprocess  # noqa: S404 — tests/ scope
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_ROOT = _REPO_ROOT / "tests" / "golden"
_PHASE1_YAML = _GOLDEN_ROOT / "node_typescript_helm.repo-context.yaml"
_REGEN_SCRIPT = _REPO_ROOT / "scripts" / "regen_golden.py"


def test_no_phase1_per_probe_collision() -> None:
    """No portfolio golden lands at probes/<probe>/node_typescript_helm.json."""
    collisions = sorted(_GOLDEN_ROOT.glob("probes/*/node_typescript_helm.json"))
    assert not collisions, (
        f"Phase 1's fixture name ``node_typescript_helm`` collided with "
        f"the portfolio per-probe tree: {collisions}. AC-38 forbids this."
    )


@pytest.mark.skipif(
    not _PHASE1_YAML.exists(),
    reason="S6-01 has not shipped Phase-1's YAML golden yet",
)
def test_phase1_yaml_golden_untouched_by_regen() -> None:
    """Invoking ``--check --portfolio`` must not mutate S6-01's YAML golden."""
    before = hashlib.sha256(_PHASE1_YAML.read_bytes()).hexdigest()
    subprocess.run(
        [sys.executable, str(_REGEN_SCRIPT), "--check", "--portfolio"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        timeout=600,
    )
    after = hashlib.sha256(_PHASE1_YAML.read_bytes()).hexdigest()
    assert before == after, (
        "S7-03's regen mutated S6-01's Phase-1 YAML golden — non-collision "
        "guarantee broken (AC-38)."
    )
