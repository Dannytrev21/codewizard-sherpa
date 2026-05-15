"""S5-05 — Phase-0 Gap-#4 + Phase-1 coordinator prelude pass.

The coordinator's prelude pass runs every ``tier == "base"`` probe
first (Phase 1: ``language_detection`` / ``ci`` / ``deployment``),
extracts ``language_stack.counts`` from ``LanguageDetectionProbe``'s
output, and dispatches every ``tier == "task_specific"`` probe (Phase 1:
``node_build_system`` / ``node_manifest`` / ``test_inventory``) against a
snapshot enriched with the merged counts. This test asserts that
invariant with TWO signals:

1. **PRIMARY (structural, causally bound).** The coordinator emits a
   ``coordinator.wave_2.dispatch`` event with ``detected_languages`` bound
   to the enriched snapshot's keys. If the prelude pass were broken
   (LD didn't run, or its counts didn't reach the enriched snapshot),
   the field would be empty / missing. No scheduler luck can fake this.
2. **SECONDARY (temporal redundancy).** ``language_detection``'s
   ``probe.success`` event precedes every Wave-2 ``probe.start`` event in
   the captured event stream. Redundant with the primary signal — if
   only this passes and primary fails, the prelude pass is broken.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from structlog.testing import capture_logs

from tests.integration.probes.conftest import (
    _copy_tree,
    _invoke_gather,
    _stub_node_version_check,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures"
_WAVE_2_PROBES = frozenset({"node_build_system", "node_manifest", "test_inventory"})


def test_prelude_pass_enriches_snapshot_before_wave_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-PR-1..3 — prelude enrichment is observable in the event stream."""
    _stub_node_version_check(monkeypatch)
    repo = _copy_tree(FIXTURE_ROOT / "node_typescript_helm", tmp_path / "repo")

    with capture_logs() as events:
        result = _invoke_gather(repo)
    assert result.exit_code == 0, result.output

    # AC-PR-2 — PRIMARY signal: coordinator.wave_2.dispatch event carries
    # ``detected_languages`` derived from the enriched snapshot.
    wave_2_dispatches = [e for e in events if e.get("event") == "coordinator.wave_2.dispatch"]
    assert wave_2_dispatches, (
        f"coordinator did not emit coordinator.wave_2.dispatch — prelude bind "
        f"is missing. events={events}"
    )
    bound = wave_2_dispatches[0]
    detected = bound.get("detected_languages")
    assert detected, (
        f"coordinator.wave_2.dispatch carried empty detected_languages — "
        f"the prelude pass did not enrich the snapshot. bound={bound}"
    )
    assert any(lang in ("javascript", "typescript") for lang in detected), (
        f"detected_languages must contain javascript or typescript on this fixture; got={detected}"
    )

    # AC-PR-3 — SECONDARY signal: temporal ordering. LD's probe.success
    # precedes every Wave-2 probe's probe.start by event-index.
    ld_success_indices = [
        i
        for i, e in enumerate(events)
        if e.get("event") == "probe.success" and e.get("probe") == "language_detection"
    ]
    assert ld_success_indices, (
        f"no probe.success for language_detection in event stream; events={events}"
    )
    ld_success_idx = ld_success_indices[0]

    wave_2_starts = [
        i
        for i, e in enumerate(events)
        if e.get("event") == "probe.start" and e.get("probe") in _WAVE_2_PROBES
    ]
    assert wave_2_starts, (
        f"no Wave-2 probe.start events — fixture isn't exercising the path; events={events}"
    )
    assert all(idx > ld_success_idx for idx in wave_2_starts), (
        f"Wave-2 probes started before language_detection completed — prelude "
        f"pass is broken. ld_success_idx={ld_success_idx}, "
        f"wave_2_starts={wave_2_starts}, events={events}"
    )
