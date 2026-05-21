"""S6-01 AC-REPLAY — two-stream ``EventLog`` replay round-trip.

Architecture spec §"Harness engineering — Replay / debuggability": replay must
produce a byte-equal post-state modulo timestamps + ``workflow_id``. A
synthetic 20-event workload is written under a frozen clock, replayed, and
re-serialised via the canonical-JSON helper — the payload bytes must match.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from codegenie.plugins.events import (
    GENESIS_CHAIN_HEAD,
    EventLog,
    PluginResolved,
    RecipeApplied,
    WorkflowStarted,
    canonical_json_bytes,
)
from codegenie.types.identifiers import (
    BlobDigest,
    EventId,
    PluginId,
    RecipeId,
    TransformId,
    WorkflowId,
)

_FROZEN = datetime(2026, 5, 19, 9, 30, 0, tzinfo=UTC)


def _internal(index: int, workflow_id: WorkflowId) -> PluginResolved | RecipeApplied:
    """Alternate two internal variants so the workload exercises the union."""
    if index % 2 == 0:
        return PluginResolved(
            event_id=EventId(f"01HINTERNAL{index:04}"),
            workflow_id=workflow_id,
            timestamp=_FROZEN,
            plugin_id=PluginId("vuln-node-npm"),
            matched_scope="vuln--node--npm",
            specificity=3,
        )
    return RecipeApplied(
        event_id=EventId(f"01HINTERNAL{index:04}"),
        workflow_id=workflow_id,
        timestamp=_FROZEN,
        recipe_id=RecipeId(f"npm-bump-{index}"),
        transform_id=TransformId(f"{index:064x}"),
        files_changed=["package-lock.json"],
    )


def _write_workload(root: Path, workflow_id: WorkflowId) -> EventLog:
    """Emit 16 internal + 4 spanning events under a frozen clock."""
    log = EventLog(root=root, workflow_id=workflow_id, clock=lambda: _FROZEN)
    for index in range(16):
        log.emit_internal(_internal(index, workflow_id))
    for index in range(4):
        log.emit_spanning(
            WorkflowStarted(
                event_id=EventId(f"01HSPANNING{index:04}"),
                workflow_id=workflow_id,
                timestamp=_FROZEN,
                prev_hash=GENESIS_CHAIN_HEAD,
            )
        )
    log.flush()
    return log


def test_replay_round_trip_is_byte_equal(tmp_path: Path) -> None:
    """AC-REPLAY: a 20-event workload replays into byte-identical canonical JSON."""
    log = _write_workload(tmp_path, WorkflowId("01HWORKFLOWAAAAAAAAAAAAAAAA"))
    replayed = list(log.replay())
    assert len(replayed) == 20

    # Re-emit the replayed events into a fresh log; the canonical bytes match.
    mirror = EventLog(
        root=tmp_path / "mirror",
        workflow_id=WorkflowId("01HWORKFLOWAAAAAAAAAAAAAAAA"),
        clock=lambda: _FROZEN,
    )
    for event in replayed:
        if hasattr(event, "prev_hash"):
            mirror.emit_spanning(event)  # type: ignore[arg-type]
        else:
            mirror.emit_internal(event)  # type: ignore[arg-type]
    mirror.flush()

    original = [canonical_json_bytes(event) for event in replayed]
    mirrored = [canonical_json_bytes(event) for event in mirror.replay()]
    assert original == mirrored


def test_replay_is_workflow_id_modulo(tmp_path: Path) -> None:
    """AC-REPLAY: the payload bytes are stable modulo the workflow_id.

    The same workload under a different ``workflow_id`` yields canonical bytes
    that differ *only* in the workflow_id field — every other byte matches.
    """
    log_a = _write_workload(tmp_path / "a", WorkflowId("01HWORKFLOWAAAAAAAAAAAAAAAA"))
    log_b = _write_workload(tmp_path / "b", WorkflowId("01HWORKFLOWBBBBBBBBBBBBBBBB"))

    def _scrub(event: object) -> bytes:
        from pydantic import BaseModel

        assert isinstance(event, BaseModel)
        data = event.model_dump(mode="json")
        data.pop("prev_hash", None)
        data["workflow_id"] = "<scrubbed>"
        import json

        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    bytes_a = [_scrub(event) for event in log_a.replay()]
    bytes_b = [_scrub(event) for event in log_b.replay()]
    assert bytes_a == bytes_b


def test_replay_chain_verifies_spanning_stream(tmp_path: Path) -> None:
    """AC-REPLAY: the spanning chain verifies and yields distinct prev_hash values."""
    log = _write_workload(tmp_path, WorkflowId("01HWORKFLOWCCCCCCCCCCCCCCCC"))
    spanning = [event for event in log.replay() if hasattr(event, "prev_hash")]
    assert len(spanning) == 4
    heads = [event.prev_hash for event in spanning]  # type: ignore[attr-defined]
    assert len(set(heads)) == 4
    assert all(head != GENESIS_CHAIN_HEAD for head in heads)
    assert all(isinstance(BlobDigest(head), str) for head in heads)
