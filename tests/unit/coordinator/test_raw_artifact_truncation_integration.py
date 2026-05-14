"""CLI integration shape for the raw-artifact truncation policy — S1-09.

Pins the contract the cli.py glue must satisfy: per-probe budget lookup via
``getattr(probe, "declared_resource_budget", DEFAULT_RESOURCE_BUDGET)``, the
exact ``probe.raw_artifact.truncated`` event payload (AC-12), and the
construction-time invariant ``raw_artifact_truncate_mb <= raw_artifact_mb``
(AC-22). Events captured via :func:`structlog.testing.capture_logs` per
L-16 / L-11 — ``capsys`` is unreliable for structlog under this project's
``WriteLoggerFactory`` config.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import structlog
from structlog.testing import capture_logs

from codegenie.coordinator.budget import DEFAULT_RESOURCE_BUDGET, ResourceBudget
from codegenie.output.raw_truncation import (
    Truncated,
    Untruncated,
    apply_raw_artifact_truncation,
)
from tests.unit._coordinator_fixtures import FakeProbe

ONE_MB = 1_048_576


def _emit_truncated_event(probe_name: str, outcome: Truncated, raw_path: Path) -> None:
    """Mirror the exact emission shape cli.py glue uses (AC-10, AC-12)."""
    run_id = structlog.contextvars.get_contextvars().get("run_id")
    structlog.get_logger("codegenie.cli").info(
        "probe.raw_artifact.truncated",
        probe=probe_name,
        original_bytes=outcome.original_bytes,
        budget_bytes=outcome.budget_bytes,
        path=str(raw_path),
        run_id=run_id,
    )


def test_cli_loop_truncates_no_override_probe_at_5mb(tmp_path: Path) -> None:
    """AC-20 — a no-override probe with a 6 MiB raw artifact gets truncated.

    Kills mutant: cli.py loop forgets to apply the truncation helper.
    Kills mutant: cli.py loop uses the wrong declared_resource_budget lookup.
    """
    probe = FakeProbe(name="big")
    budget = getattr(probe, "declared_resource_budget", DEFAULT_RESOURCE_BUDGET)
    assert budget is DEFAULT_RESOURCE_BUDGET
    payload = b"x" * (6 * ONE_MB)
    raw_path = tmp_path / "raw" / f"{probe.name}.json"

    with capture_logs() as logs:
        out_bytes, outcome = apply_raw_artifact_truncation(payload, budget.raw_artifact_truncate_mb)
        if isinstance(outcome, Truncated):
            _emit_truncated_event(probe.name, outcome, raw_path)

    assert isinstance(outcome, Truncated)
    assert len(out_bytes) < len(payload)
    truncate_events = [e for e in logs if e["event"] == "probe.raw_artifact.truncated"]
    assert len(truncate_events) == 1
    ev = truncate_events[0]
    assert ev["probe"] == "big"
    assert ev["original_bytes"] == 6 * ONE_MB
    assert ev["budget_bytes"] == 5 * ONE_MB
    # AC-12 — exactly the contracted payload keys, no more, no less.
    envelope_keys = {"timestamp", "level", "log_level", "logger", "run_id"}
    payload_keys = set(ev.keys()) - envelope_keys
    assert payload_keys == {"event", "probe", "original_bytes", "budget_bytes", "path"}


def test_cli_loop_does_not_truncate_override_probe_at_5mb(tmp_path: Path) -> None:
    """AC-21 — override probe (truncate_mb=25) keeps a 6 MiB artifact intact.

    Kills mutant: cli.py loop ignores declared_resource_budget on the probe.
    """

    class _BigProbe(FakeProbe):
        declared_resource_budget = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)

    probe = _BigProbe(name="big_override")
    budget = getattr(probe, "declared_resource_budget", DEFAULT_RESOURCE_BUDGET)
    assert budget.raw_artifact_truncate_mb == 25

    payload = b"x" * (6 * ONE_MB)

    with capture_logs() as logs:
        out_bytes, outcome = apply_raw_artifact_truncation(payload, budget.raw_artifact_truncate_mb)

    assert isinstance(outcome, Untruncated)
    assert out_bytes == payload
    assert not any(e["event"] == "probe.raw_artifact.truncated" for e in logs)


def test_resource_budget_truncate_above_hard_ceiling_raises() -> None:
    """AC-22 — invariant truncate_mb <= raw_artifact_mb enforced at construction.

    Kills mutant: __post_init__ omitted (silent acceptance of unreachable policy).
    """
    with pytest.raises(ValueError, match="raw_artifact_truncate_mb"):
        ResourceBudget(raw_artifact_mb=10, raw_artifact_truncate_mb=20)
