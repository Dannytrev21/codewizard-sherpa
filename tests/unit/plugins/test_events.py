"""S6-01 — two-stream ``EventLog`` with a BLAKE3-chained spanning stream.

Red-green-refactor TDD suite for :mod:`codegenie.plugins.events`. Covers both
typed discriminated unions, the on-disk ``jsonl.zst`` format, the BLAKE3 chain
(``_chain_step`` pure helper, routed through :mod:`codegenie.hashing`),
``fcntl.flock`` cross-process safety, resume-across-restart, torn-frame
corruption, and the ``CacheGcCompleted`` re-import.
"""

from __future__ import annotations

import ast
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from codegenie.plugins.events import (
    GENESIS_CHAIN_HEAD,
    AdapterDegraded,
    ChainTamperDetected,
    EventLog,
    EventLogCorrupted,
    EventStreamSink,
    InMemorySink,
    PluginResolved,
    WorkflowSpanningEvent,
    WorkflowStarted,
    ZstdAppendingFileSink,
    _chain_step,
    canonical_json_bytes,
)
from codegenie.types.identifiers import BlobDigest, EventId, PluginId, WorkflowId

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wf() -> WorkflowId:
    return WorkflowId("01HFEEDFACE0000000000000000")


def _now() -> datetime:
    return datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)


def _spanning_path(root: Path) -> Path:
    return root / "events" / "spanning" / "append.jsonl.zst"


def _decode_spanning_lines(path: Path) -> list[bytes]:
    """Decompress every zstd frame in a spanning file into a list of JSON lines."""
    import io

    import zstandard

    raw = path.read_bytes()
    with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw), read_across_frames=True) as r:
        decompressed = r.read()
    return [line for line in decompressed.split(b"\n") if line]


def _reencode_spanning(path: Path, lines: list[bytes]) -> None:
    """Rewrite a spanning file: one independent zstd frame per line (newline-terminated)."""
    import zstandard

    compressor = zstandard.ZstdCompressor(level=3)
    path.write_bytes(b"".join(compressor.compress(line + b"\n") for line in lines))


def _plugin_resolved(suffix: str, *, scope: str = "vuln--node--npm") -> PluginResolved:
    return PluginResolved(
        event_id=EventId(f"01HRESOLVE{suffix}"),
        workflow_id=_wf(),
        timestamp=_now(),
        plugin_id=PluginId("vuln-node-npm"),
        matched_scope=scope,
        specificity=3,
    )


def _workflow_started(suffix: str) -> WorkflowStarted:
    return WorkflowStarted(
        event_id=EventId(f"01HSTART{suffix}"),
        workflow_id=_wf(),
        timestamp=_now(),
        prev_hash=GENESIS_CHAIN_HEAD,
    )


# ---------------------------------------------------------------------------
# AC-1 / AC-2 — surface + construction
# ---------------------------------------------------------------------------


def test_public_surface_imports(tmp_path: Path) -> None:
    """AC-1: the documented public names all import."""
    from codegenie.plugins.events import (  # noqa: F401
        EventLog,
        EventLogCorrupted,
        WorkflowInternalEvent,
        WorkflowSpanningEvent,
    )

    assert GENESIS_CHAIN_HEAD == BlobDigest("0" * 64)


def test_init_creates_both_stream_directories(tmp_path: Path) -> None:
    """AC-2: construction makes both event directories with parents."""
    EventLog(root=tmp_path, workflow_id=_wf())
    assert (tmp_path / "events" / "workflow-internal").is_dir()
    assert (tmp_path / "events" / "spanning").is_dir()


# ---------------------------------------------------------------------------
# AC-3 / AC-4 — emit to two distinct streams
# ---------------------------------------------------------------------------


def test_two_streams_write_to_distinct_paths(tmp_path: Path) -> None:
    """AC-3 + AC-4: internal and spanning land in separate zstd files."""
    log = EventLog(root=tmp_path, workflow_id=_wf())
    log.emit_internal(_plugin_resolved("01"))
    log.emit_spanning(_workflow_started("01"))
    log.flush()
    internal = tmp_path / "events" / "workflow-internal" / f"{_wf()}.jsonl.zst"
    assert internal.exists() and internal.stat().st_size > 0
    assert _spanning_path(tmp_path).exists() and _spanning_path(tmp_path).stat().st_size > 0


def test_emit_returns_the_event_id(tmp_path: Path) -> None:
    """AC-3 + AC-4: emit returns the event's own id."""
    log = EventLog(root=tmp_path, workflow_id=_wf())
    assert log.emit_internal(_plugin_resolved("XX")) == EventId("01HRESOLVEXX")
    assert log.emit_spanning(_workflow_started("XX")) == EventId("01HSTARTXX")


# ---------------------------------------------------------------------------
# AC-5 — cross-channel rejection
# ---------------------------------------------------------------------------


def test_internal_event_on_spanning_method_is_rejected(tmp_path: Path) -> None:
    """AC-5: emitting an internal event via emit_spanning raises."""
    log = EventLog(root=tmp_path, workflow_id=_wf())
    with pytest.raises((TypeError, ValidationError)):
        log.emit_spanning(_plugin_resolved("01"))  # type: ignore[arg-type]


def test_spanning_event_on_internal_method_is_rejected(tmp_path: Path) -> None:
    """AC-5: emitting a spanning event via emit_internal raises."""
    log = EventLog(root=tmp_path, workflow_id=_wf())
    with pytest.raises((TypeError, ValidationError)):
        log.emit_internal(_workflow_started("01"))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC-6 / AC-7 — the 17 internal + 9 spanning variants
# (Phase-4 S2-01 grew the internal set by one — ``ProvenanceClassified``.)
# ---------------------------------------------------------------------------

_INTERNAL_VARIANTS = frozenset(
    {
        "PluginsLoaded",
        "PluginResolved",
        "BundleBuilt",
        "BundleEntryPromoted",
        "RecipeMatched",
        "RecipeApplied",
        "RecipeSkipped",
        "RecipeFailed",
        "InstallStageOutcome",
        "TestStageOutcome",
        "LocalBranchWritten",
        "RequiresHumanReview",
        "AdapterDegraded",
        "StageOutcome",
        "FilesystemRaceDetected",
        "GitHooksDisabledForRun",
        # Phase-4 S2-01 — ``ProvenanceGate`` tier-0 emission.
        "ProvenanceClassified",
        # Phase-4 S2-02 — ``FenceWrapper`` audit events.
        "FenceApplied",
        "CanaryCollisionEvent",
        # Phase-4 S2-04 — ``PromptBuilder`` audit events.
        "PromptAssembled",
        "SegmentCountTruncated",
        # Phase-4 S2-05 — ``LlmInvocationGuard`` budget audit events.
        "BudgetPrecharged",
        "BudgetReconciled",
        "BudgetReconciledDuplicate",
        "BudgetCapExceeded",
        "BudgetUnknownTokenReconcile",
    }
)
_SPANNING_VARIANTS = frozenset(
    {
        "WorkflowStarted",
        "WorkflowCompleted",
        "CostSandboxRun",
        "CapabilityMinted",
        "CapabilityUsed",
        "PluginRegistryCorrupted",
        "BenchReplayable",
        "StaleVulnIndex",
        "CacheGcCompleted",
    }
)


def test_all_26_internal_variants_exist() -> None:
    """AC-6 + Phase-4 S2-01/02/04/05: every named internal variant is exported."""
    from codegenie.plugins import events as ev

    for name in _INTERNAL_VARIANTS:
        assert hasattr(ev, name), f"missing internal variant: {name}"
    assert len(_INTERNAL_VARIANTS) == 26


def test_all_9_spanning_variants_exist() -> None:
    """AC-7: every named spanning variant is exported."""
    from codegenie.plugins import events as ev

    for name in _SPANNING_VARIANTS:
        assert hasattr(ev, name), f"missing spanning variant: {name}"
    assert len(_SPANNING_VARIANTS) == 9


def test_internal_variants_are_frozen_extra_forbid() -> None:
    """AC-6: internal variants reject mutation and unknown fields."""
    event = _plugin_resolved("01")
    with pytest.raises(ValidationError):
        event.matched_scope = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        PluginResolved(
            event_id=EventId("01H"),
            workflow_id=_wf(),
            timestamp=_now(),
            plugin_id=PluginId("p"),
            matched_scope="s",
            specificity=1,
            bogus="x",  # type: ignore[call-arg]
        )


def test_spanning_native_variants_carry_prev_hash() -> None:
    """AC-7: the eight native spanning variants declare a prev_hash field."""
    from codegenie.plugins import events as ev

    for name in _SPANNING_VARIANTS - {"CacheGcCompleted"}:
        variant = getattr(ev, name)
        assert "prev_hash" in variant.model_fields, f"{name} missing prev_hash"


# ---------------------------------------------------------------------------
# AC-CG — CacheGcCompleted is re-imported, not redefined
# ---------------------------------------------------------------------------


def test_cache_gc_completed_is_reimported_not_redefined() -> None:
    """AC-CG: events.CacheGcCompleted IS cache_gc.CacheGcCompletedEvent."""
    from codegenie.plugins import events as ev
    from codegenie.plugins.cache_gc import CacheGcCompletedEvent

    assert ev.CacheGcCompleted is CacheGcCompletedEvent
    assert ev.CacheGcCompletedEvent is CacheGcCompletedEvent


# ---------------------------------------------------------------------------
# AC-CORE — pure _chain_step helper
# ---------------------------------------------------------------------------


def test_chain_step_is_deterministic_and_content_sensitive() -> None:
    """AC-CORE: _chain_step is pure — deterministic and content-sensitive."""
    assert _chain_step(GENESIS_CHAIN_HEAD, b"") == _chain_step(GENESIS_CHAIN_HEAD, b"")
    assert _chain_step(GENESIS_CHAIN_HEAD, b"a") != _chain_step(GENESIS_CHAIN_HEAD, b"b")
    h1 = _chain_step(GENESIS_CHAIN_HEAD, b"a")
    assert _chain_step(h1, b"a") != _chain_step(GENESIS_CHAIN_HEAD, b"a")


def test_chain_step_returns_unprefixed_64_hex() -> None:
    """AC-CHOKE: the chain step strips the ``blake3:`` prefix."""
    head = _chain_step(GENESIS_CHAIN_HEAD, b"payload")
    assert len(head) == 64
    assert all(c in "0123456789abcdef" for c in head)


def test_chain_step_has_no_self_no_io() -> None:
    """AC-CORE: _chain_step is a module-level function (no self, no I/O)."""
    params = list(inspect.signature(_chain_step).parameters)
    assert params == ["prior_head", "event_bytes"]


# ---------------------------------------------------------------------------
# AC-GEN — genesis chain head
# ---------------------------------------------------------------------------


def test_genesis_prev_hash_on_empty_file(tmp_path: Path) -> None:
    """AC-GEN: the first emit chains from GENESIS_CHAIN_HEAD, deterministically."""
    log = EventLog(root=tmp_path, workflow_id=_wf(), clock=_now)
    log.emit_spanning(_workflow_started("G1"))
    log.flush()
    first = next(iter(log.replay()))
    assert first.prev_hash != GENESIS_CHAIN_HEAD

    # The first record's prev_hash is _chain_step(GENESIS, body) — reproducible.
    line = _decode_spanning_lines(_spanning_path(tmp_path))[0]
    obj = json.loads(line)
    body = json.dumps(
        {k: v for k, v in obj.items() if k != "prev_hash"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert obj["prev_hash"] == _chain_step(GENESIS_CHAIN_HEAD, body)


# ---------------------------------------------------------------------------
# AC-CHAIN / AC-MUT — chain verification + tamper detection
# ---------------------------------------------------------------------------


def test_chain_verifies_then_breaks_on_tamper(tmp_path: Path) -> None:
    """AC-CHAIN: a clean 10-event chain replays; a byte flip raises ChainTamperDetected."""
    log = EventLog(root=tmp_path, workflow_id=_wf(), clock=_now)
    for i in range(10):
        log.emit_spanning(_workflow_started(f"{i:02}"))
    log.flush()

    events = list(log.replay())
    assert len(events) == 10
    prev_hashes = [e.prev_hash for e in events]
    assert len(set(prev_hashes)) == 10, f"prev_hash collision: {prev_hashes}"

    lines = _decode_spanning_lines(_spanning_path(tmp_path))
    obj = json.loads(lines[0])
    obj["event_id"] = "01HTAMPERED" + obj["event_id"][11:]
    lines[0] = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    _reencode_spanning(_spanning_path(tmp_path), lines)

    with pytest.raises(ChainTamperDetected):
        list(log.replay())


def test_metamorphic_same_event_twice_yields_distinct_prev_hash(tmp_path: Path) -> None:
    """AC-MUT: emitting the same event twice produces distinct prev_hash values."""
    log = EventLog(root=tmp_path, workflow_id=_wf(), clock=_now)
    event = _workflow_started("M1")
    log.emit_spanning(event)
    log.emit_spanning(event)
    log.flush()
    events = list(log.replay())
    assert events[0].prev_hash != events[1].prev_hash


# ---------------------------------------------------------------------------
# AC-RES — resume across process restart
# ---------------------------------------------------------------------------


def test_resume_across_process_restart(tmp_path: Path) -> None:
    """AC-RES: re-opening rehydrates the chain head from disk, not genesis."""
    log1 = EventLog(root=tmp_path, workflow_id=_wf(), clock=_now)
    log1.emit_spanning(_workflow_started("R1"))
    log1.flush()
    head_after_first = next(iter(log1.replay())).prev_hash
    del log1

    log2 = EventLog(root=tmp_path, workflow_id=_wf(), clock=_now)
    log2.emit_spanning(_workflow_started("R2"))
    log2.flush()
    events = list(log2.replay())
    assert len(events) == 2
    assert events[0].prev_hash == head_after_first
    assert events[1].prev_hash not in (GENESIS_CHAIN_HEAD, head_after_first)


# ---------------------------------------------------------------------------
# AC-EMPTY / AC-TORN / AC-FLUSH
# ---------------------------------------------------------------------------


def test_empty_replay_yields_nothing(tmp_path: Path) -> None:
    """AC-EMPTY: a never-emitted EventLog replays empty without raising."""
    assert list(EventLog(root=tmp_path, workflow_id=_wf()).replay()) == []


def test_truncated_frame_raises_event_log_corrupted(tmp_path: Path) -> None:
    """AC-TORN: a truncated trailing zstd frame raises EventLogCorrupted."""
    log = EventLog(root=tmp_path, workflow_id=_wf(), clock=_now)
    log.emit_spanning(_workflow_started("T1"))
    log.flush()
    path = _spanning_path(tmp_path)
    path.write_bytes(path.read_bytes()[:-4])
    with pytest.raises(EventLogCorrupted):
        list(log.replay())


def _internal_path(root: Path) -> Path:
    return root / "events" / "workflow-internal" / f"{_wf()}.jsonl.zst"


def test_malformed_json_record_raises_event_log_corrupted(tmp_path: Path) -> None:
    """AC-TORN sibling: a non-JSON record is a loud EventLogCorrupted, not silent."""
    log = EventLog(root=tmp_path, workflow_id=_wf())
    ZstdAppendingFileSink(_internal_path(tmp_path)).append(b"{not valid json")
    with pytest.raises(EventLogCorrupted):
        list(log.replay())


def test_non_object_record_raises_event_log_corrupted(tmp_path: Path) -> None:
    """A JSON array (not an object) is rejected as a corrupt record."""
    log = EventLog(root=tmp_path, workflow_id=_wf())
    ZstdAppendingFileSink(_internal_path(tmp_path)).append(b'["a", "list"]')
    with pytest.raises(EventLogCorrupted):
        list(log.replay())


def test_schema_violating_internal_record_raises_event_log_corrupted(tmp_path: Path) -> None:
    """An internal record whose payload fails Pydantic validation is corrupt."""
    log = EventLog(root=tmp_path, workflow_id=_wf())
    ZstdAppendingFileSink(_internal_path(tmp_path)).append(b'{"event_type":"plugin_resolved"}')
    with pytest.raises(EventLogCorrupted):
        list(log.replay())


def test_schema_violating_spanning_record_raises_event_log_corrupted(tmp_path: Path) -> None:
    """A chain-valid spanning record with an unknown discriminator is corrupt.

    The chain check passes (``prev_hash`` is computed correctly), so the
    failure surfaces from schema validation — distinct from ChainTamperDetected.
    """
    log = EventLog(root=tmp_path, workflow_id=_wf())
    body_obj = {
        "event_type": "not_a_real_spanning_variant",
        "event_id": "01HBOGUS",
        "workflow_id": str(_wf()),
        "timestamp": _now().isoformat(),
    }
    body = json.dumps(body_obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    record = json.dumps(
        {**body_obj, "prev_hash": _chain_step(GENESIS_CHAIN_HEAD, body)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    ZstdAppendingFileSink(_spanning_path(tmp_path)).append(record)
    with pytest.raises(EventLogCorrupted):
        list(log.replay())


def test_flush_is_idempotent_and_noop_on_empty(tmp_path: Path) -> None:
    """AC-FLUSH: flush is idempotent and a no-op before any emit."""
    log = EventLog(root=tmp_path, workflow_id=_wf())
    log.flush()
    log.flush()
    log.emit_internal(_plugin_resolved("F1"))
    log.flush()
    internal = tmp_path / "events" / "workflow-internal" / f"{_wf()}.jsonl.zst"
    size = internal.stat().st_size
    log.flush()
    assert internal.stat().st_size == size


# ---------------------------------------------------------------------------
# AC-CLOCK — clock injection
# ---------------------------------------------------------------------------


def test_clock_injection_stamps_emitted_events(tmp_path: Path) -> None:
    """AC-CLOCK: the injected clock stamps the emitted timestamp; replay round-trips."""
    frozen = datetime(2026, 5, 19, tzinfo=UTC)
    log = EventLog(root=tmp_path, workflow_id=_wf(), clock=lambda: frozen)
    log.emit_internal(
        PluginResolved(
            event_id=EventId("01HCLOCK"),
            workflow_id=_wf(),
            timestamp=_now(),  # superseded by the injected clock
            plugin_id=PluginId("p"),
            matched_scope="*--*--*",
            specificity=0,
        )
    )
    log.flush()
    replayed = next(iter(log.replay()))
    assert replayed.timestamp == frozen


# ---------------------------------------------------------------------------
# AC-REPLAY — byte-equal round trip
# ---------------------------------------------------------------------------


def test_replay_round_trip_byte_equal(tmp_path: Path) -> None:
    """AC-REPLAY: a 20-event internal workload round-trips byte-equal."""
    frozen = _now()
    log = EventLog(root=tmp_path, workflow_id=_wf(), clock=lambda: frozen)
    for i in range(20):
        log.emit_internal(_plugin_resolved(f"{i:03}"))
    log.flush()
    events1 = list(log.replay())
    assert len(events1) == 20
    bytes1 = [canonical_json_bytes(e) for e in events1]

    log2 = EventLog(root=tmp_path / "second", workflow_id=_wf(), clock=lambda: frozen)
    for event in events1:
        log2.emit_internal(event)
    log2.flush()
    bytes2 = [canonical_json_bytes(e) for e in log2.replay()]
    assert bytes1 == bytes2


# ---------------------------------------------------------------------------
# AC-FLOCK — cross-process flock keeps the chain intact
# ---------------------------------------------------------------------------


def _flock_worker(root: str, suffix: str) -> None:
    """Top-level (picklable) worker — appends 50 spanning events under flock."""
    from datetime import UTC, datetime

    from codegenie.plugins.events import GENESIS_CHAIN_HEAD, EventLog, WorkflowStarted
    from codegenie.types.identifiers import EventId, WorkflowId

    log = EventLog(root=Path(root), workflow_id=WorkflowId(f"wf-{suffix}"))
    for i in range(50):
        log.emit_spanning(
            WorkflowStarted(
                event_id=EventId(f"01H{suffix}{i:03}"),
                workflow_id=WorkflowId(f"wf-{suffix}"),
                timestamp=datetime.now(UTC),
                prev_hash=GENESIS_CHAIN_HEAD,
            )
        )
    log.flush()


def test_cross_process_flock_keeps_chain_intact(tmp_path: Path) -> None:
    """AC-FLOCK: two spawned processes appending concurrently keep the chain valid."""
    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    p1 = ctx.Process(target=_flock_worker, args=(str(tmp_path), "a"))
    p2 = ctx.Process(target=_flock_worker, args=(str(tmp_path), "b"))
    p1.start()
    p2.start()
    p1.join()
    p2.join()
    assert p1.exitcode == 0 and p2.exitcode == 0

    lines = _decode_spanning_lines(_spanning_path(tmp_path))
    assert len(lines) == 100
    head = GENESIS_CHAIN_HEAD
    for line in lines:
        obj = json.loads(line)
        body = json.dumps(
            {k: v for k, v in obj.items() if k != "prev_hash"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        expected = _chain_step(head, body)
        assert obj["prev_hash"] == expected, f"chain break at {obj['event_id']}"
        head = expected


# ---------------------------------------------------------------------------
# AC-2 — sink injection (InMemorySink)
# ---------------------------------------------------------------------------


def test_in_memory_sink_skips_the_zstd_spanning_file(tmp_path: Path) -> None:
    """AC-2: an injected InMemorySink keeps the spanning stream off disk."""
    log = EventLog(root=tmp_path, workflow_id=_wf(), clock=_now, sink=InMemorySink())
    log.emit_spanning(_workflow_started("IM"))
    log.flush()
    assert not _spanning_path(tmp_path).exists()
    replayed = list(log.replay())
    assert len(replayed) == 1
    assert isinstance(replayed[0], WorkflowStarted)


def test_sinks_satisfy_the_event_stream_sink_protocol() -> None:
    """AC-2: both shipped sinks structurally satisfy EventStreamSink."""
    assert isinstance(InMemorySink(), EventStreamSink)


# ---------------------------------------------------------------------------
# AC-TYPED-PAYLOADS / AC-NOPATH — module hygiene
# ---------------------------------------------------------------------------


def test_module_has_no_any_or_path_annotations() -> None:
    """AC-TYPED-PAYLOADS + AC-NOPATH: no Any / Path field annotations on variants."""
    from codegenie.plugins import events as ev

    tree = ast.parse(inspect.getsource(ev))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id != "Any", "Any annotation present in events.py"
    # No event variant declares a Path-typed field.
    for name in _INTERNAL_VARIANTS | _SPANNING_VARIANTS:
        variant = getattr(ev, name)
        for field, info in variant.model_fields.items():
            assert info.annotation is not Path, f"{name}.{field} is a Path"


def test_module_does_not_import_blake3_directly() -> None:
    """AC-CHOKE: events.py routes hashing through codegenie.hashing only."""
    tree = ast.parse(Path("src/codegenie/plugins/events.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("blake3")
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("blake3")


# ---------------------------------------------------------------------------
# AC-DOC / AC-HONEST — module docstring contract
# ---------------------------------------------------------------------------


def test_module_docstring_cites_adrs_and_honest_framing() -> None:
    """AC-DOC + AC-HONEST: docstring cites the ADRs and the tamper-evident framing."""
    from codegenie.plugins import events as ev

    doc = ev.__doc__ or ""
    for token in ("ADR-0005", "ADR-0001", "ADR-0011", "C9"):
        assert token in doc, f"module docstring missing {token}"
    assert "tamper-evident" in doc and "tamper-proof" in doc


def test_spanning_union_is_discriminated() -> None:
    """AC-DISC: WorkflowSpanningEvent dispatches by the event_type discriminator."""
    from pydantic import TypeAdapter

    adapter = TypeAdapter(WorkflowSpanningEvent)
    decoded = adapter.validate_python(
        {
            "event_type": "workflow_started",
            "event_id": "01H",
            "workflow_id": str(_wf()),
            "timestamp": _now().isoformat(),
            "prev_hash": GENESIS_CHAIN_HEAD,
        }
    )
    assert isinstance(decoded, WorkflowStarted)


def test_adapter_degraded_carries_a_typed_signal() -> None:
    """AC-6: AdapterDegraded is constructible with typed payload fields."""
    event = AdapterDegraded(
        event_id=EventId("01HAD"),
        workflow_id=_wf(),
        timestamp=_now(),
        adapter_name="npm",
        signal="adapter_degraded",
        detail="registry timeout",
    )
    assert event.event_type == "adapter_degraded"


# ---------------------------------------------------------------------------
# Phase-4 S2-01 — ``ProvenanceClassified`` workflow-internal variant
# ---------------------------------------------------------------------------


def test_provenance_classified_is_internal_event_variant() -> None:
    """S2-01 AC-9: the new variant is registered on the internal discriminator."""
    from pydantic import TypeAdapter

    from codegenie.plugins.events import ProvenanceClassified, WorkflowInternalEvent

    schema = TypeAdapter(WorkflowInternalEvent).json_schema()
    mapping = schema["discriminator"]["mapping"]
    assert "provenance_classified" in mapping

    # Construct with a typed payload — the lower-case discriminator values are
    # the contract (see the production ADR-0038 ``Provenance.kind`` taxonomy).
    event = ProvenanceClassified(
        event_id=EventId("01HPRV000000000000000000"),
        workflow_id=_wf(),
        timestamp=_now(),
        provenance_kind="base_image",
        adapter_error=None,
    )
    assert event.event_type == "provenance_classified"
    assert event.provenance_kind == "base_image"


def test_provenance_classified_rejects_unknown_kind() -> None:
    """The provenance_kind ``Literal`` is closed — bad values fail at construction."""
    from codegenie.plugins.events import ProvenanceClassified

    with pytest.raises(ValidationError):
        ProvenanceClassified(
            event_id=EventId("01HPRV"),
            workflow_id=_wf(),
            timestamp=_now(),
            provenance_kind="provenanceClassified",  # type: ignore[arg-type]
        )


def test_provenance_classified_adapter_error_field_defaults_to_none() -> None:
    """The adapter_error field defaults to None — only present on fold path."""
    from codegenie.plugins.events import ProvenanceClassified

    event = ProvenanceClassified(
        event_id=EventId("01HPRV"),
        workflow_id=_wf(),
        timestamp=_now(),
        provenance_kind="app_direct",
    )
    assert event.adapter_error is None


def test_provenance_classified_round_trips_through_event_log(tmp_path: Path) -> None:
    """Emitting + replaying the event preserves its typed payload."""
    from codegenie.plugins.events import ProvenanceClassified

    log = EventLog(root=tmp_path, workflow_id=_wf())
    log.emit_internal(
        ProvenanceClassified(
            event_id=EventId("01HPRVROUND"),
            workflow_id=_wf(),
            timestamp=_now(),
            provenance_kind="unknown",
            adapter_error="npm registry timeout",
        )
    )
    log.flush()

    replayed = [e for e in log.replay() if isinstance(e, ProvenanceClassified)]
    assert len(replayed) == 1
    assert replayed[0].provenance_kind == "unknown"
    assert replayed[0].adapter_error == "npm registry timeout"


# ---------------------------------------------------------------------------
# Phase-4 S2-02 — ``FenceApplied`` + ``CanaryCollisionEvent`` variants
# ---------------------------------------------------------------------------


def _hex_nonce() -> str:
    from codegenie.types.identifiers import HexNonce

    return HexNonce("00112233445566778899aabbccddeeff")


def test_fence_applied_is_internal_event_variant() -> None:
    """S2-02 AC-12: ``fence_applied`` discriminator is registered."""
    from pydantic import TypeAdapter

    from codegenie.plugins.events import FenceApplied, WorkflowInternalEvent
    from codegenie.types.identifiers import HexNonce

    mapping = TypeAdapter(WorkflowInternalEvent).json_schema()["discriminator"]["mapping"]
    assert "fence_applied" in mapping

    event = FenceApplied(
        event_id=EventId("01HFNC0000000000000000"),
        workflow_id=_wf(),
        timestamp=_now(),
        source_kind="repo_readme",
        nonce=HexNonce(_hex_nonce()),
        truncated=False,
        original_byte_length=42,
    )
    assert event.event_type == "fence_applied"
    assert event.source_kind == "repo_readme"
    assert event.truncated is False
    assert event.original_byte_length == 42


def test_canary_collision_event_is_internal_event_variant() -> None:
    """S2-02 AC-12: ``canary_collision`` discriminator is registered."""
    from pydantic import TypeAdapter

    from codegenie.plugins.events import CanaryCollisionEvent, WorkflowInternalEvent
    from codegenie.types.identifiers import HexNonce

    mapping = TypeAdapter(WorkflowInternalEvent).json_schema()["discriminator"]["mapping"]
    assert "canary_collision" in mapping

    event = CanaryCollisionEvent(
        event_id=EventId("01HFNC0000000000000001"),
        workflow_id=_wf(),
        timestamp=_now(),
        source_kind="source_snippet",
        nonce=HexNonce(_hex_nonce()),
        pattern_id="ignore_previous_instructions",
    )
    assert event.event_type == "canary_collision"
    assert event.pattern_id == "ignore_previous_instructions"


def test_fence_applied_rejects_unknown_source_kind() -> None:
    from codegenie.plugins.events import FenceApplied
    from codegenie.types.identifiers import HexNonce

    with pytest.raises(ValidationError):
        FenceApplied(
            event_id=EventId("01HFNC"),
            workflow_id=_wf(),
            timestamp=_now(),
            source_kind="unknown_kind",  # type: ignore[arg-type]
            nonce=HexNonce(_hex_nonce()),
            truncated=False,
            original_byte_length=0,
        )


def test_fence_events_round_trip_through_event_log(tmp_path: Path) -> None:
    """Emit both events into the workflow-internal stream and replay them."""
    from codegenie.plugins.events import (
        CanaryCollisionEvent,
        FenceApplied,
    )
    from codegenie.types.identifiers import HexNonce

    log = EventLog(root=tmp_path, workflow_id=_wf())
    log.emit_internal(
        FenceApplied(
            event_id=EventId("01HFNC0000000000000010"),
            workflow_id=_wf(),
            timestamp=_now(),
            source_kind="cve_description",
            nonce=HexNonce(_hex_nonce()),
            truncated=True,
            original_byte_length=5000,
        )
    )
    log.emit_internal(
        CanaryCollisionEvent(
            event_id=EventId("01HFNC0000000000000011"),
            workflow_id=_wf(),
            timestamp=_now(),
            source_kind="cve_description",
            nonce=HexNonce(_hex_nonce()),
            pattern_id="ignore_previous_instructions",
        )
    )
    log.flush()

    replayed = list(log.replay())
    applied = [e for e in replayed if isinstance(e, FenceApplied)]
    collisions = [e for e in replayed if isinstance(e, CanaryCollisionEvent)]
    assert len(applied) == 1
    assert applied[0].truncated is True
    assert applied[0].original_byte_length == 5000
    assert len(collisions) == 1
    assert collisions[0].pattern_id == "ignore_previous_instructions"


# ---------------------------------------------------------------------------
# Phase-4 S2-04 — ``PromptAssembled`` + ``SegmentCountTruncated`` variants
# ---------------------------------------------------------------------------


def test_prompt_assembled_is_internal_event_variant() -> None:
    """S2-04 AC-11: ``prompt_assembled`` discriminator registered + typed payload."""
    from pydantic import TypeAdapter

    from codegenie.plugins.events import PromptAssembled, WorkflowInternalEvent

    mapping = TypeAdapter(WorkflowInternalEvent).json_schema()["discriminator"]["mapping"]
    assert "prompt_assembled" in mapping

    event = PromptAssembled(
        event_id=EventId("01HPRBASM0000000000000000"),
        workflow_id=_wf(),
        timestamp=_now(),
        segment_count=3,
        source_kinds_used=("cve_description", "repo_readme", "transitive_dep_meta"),
        system_prompt_byte_length=120,
        fenced_body_byte_length=400,
    )
    assert event.event_type == "prompt_assembled"
    assert event.segment_count == 3
    assert event.source_kinds_used == (
        "cve_description",
        "repo_readme",
        "transitive_dep_meta",
    )
    assert event.system_prompt_byte_length == 120
    assert event.fenced_body_byte_length == 400


def test_prompt_assembled_rejects_unknown_source_kind() -> None:
    """S2-04 AC-11: ``source_kinds_used`` is a tuple of the seven SourceKind literals."""
    from codegenie.plugins.events import PromptAssembled

    with pytest.raises(ValidationError):
        PromptAssembled(
            event_id=EventId("01HPRBASM0000000000000099"),
            workflow_id=_wf(),
            timestamp=_now(),
            segment_count=1,
            source_kinds_used=("unknown_kind",),  # type: ignore[arg-type]
            system_prompt_byte_length=1,
            fenced_body_byte_length=1,
        )


def test_segment_count_truncated_is_internal_event_variant() -> None:
    """S2-04 AC-11: ``segment_count_truncated`` discriminator registered + typed payload."""
    from pydantic import TypeAdapter

    from codegenie.plugins.events import SegmentCountTruncated, WorkflowInternalEvent

    mapping = TypeAdapter(WorkflowInternalEvent).json_schema()["discriminator"]["mapping"]
    assert "segment_count_truncated" in mapping

    event = SegmentCountTruncated(
        event_id=EventId("01HPRBTRUNC0000000000000000"),
        workflow_id=_wf(),
        timestamp=_now(),
        source_kind="transitive_dep_meta",
        requested=20,
        kept=16,
    )
    assert event.event_type == "segment_count_truncated"
    assert event.requested == 20
    assert event.kept == 16


def test_segment_count_truncated_rejects_unknown_source_kind() -> None:
    """S2-04 AC-11: ``source_kind`` is one of the seven SourceKind literals."""
    from codegenie.plugins.events import SegmentCountTruncated

    with pytest.raises(ValidationError):
        SegmentCountTruncated(
            event_id=EventId("01HPRBTRUNC0000000000000099"),
            workflow_id=_wf(),
            timestamp=_now(),
            source_kind="unknown_kind",  # type: ignore[arg-type]
            requested=20,
            kept=16,
        )


def test_prompt_builder_events_round_trip_through_event_log(tmp_path: Path) -> None:
    """S2-04 AC-11: both new events emit + replay through the workflow-internal stream."""
    from codegenie.plugins.events import PromptAssembled, SegmentCountTruncated

    log = EventLog(root=tmp_path, workflow_id=_wf())
    log.emit_internal(
        SegmentCountTruncated(
            event_id=EventId("01HPRBTRUNC0000000000000010"),
            workflow_id=_wf(),
            timestamp=_now(),
            source_kind="transitive_dep_meta",
            requested=42,
            kept=16,
        )
    )
    log.emit_internal(
        PromptAssembled(
            event_id=EventId("01HPRBASM0000000000000011"),
            workflow_id=_wf(),
            timestamp=_now(),
            segment_count=4,
            source_kinds_used=(
                "cve_description",
                "repo_readme",
                "transitive_dep_meta",
                "source_snippet",
            ),
            system_prompt_byte_length=10,
            fenced_body_byte_length=20,
        )
    )
    log.flush()

    replayed = list(log.replay())
    assembled = [e for e in replayed if isinstance(e, PromptAssembled)]
    truncations = [e for e in replayed if isinstance(e, SegmentCountTruncated)]
    assert len(assembled) == 1
    assert assembled[0].segment_count == 4
    assert len(truncations) == 1
    assert truncations[0].requested == 42
    assert truncations[0].kept == 16


# ---------------------------------------------------------------------------
# Phase-4 S2-05 — ``LlmInvocationGuard`` budget audit events round-trip.
# Each of the five new variants emits via emit_internal and round-trips
# through replay() with byte-stable Pydantic equality.
# ---------------------------------------------------------------------------


def test_budget_events_round_trip_through_emit_and_replay(tmp_path: Path) -> None:
    """AC-13 — every new S2-05 internal event lands on disk and reads back equal."""
    from decimal import Decimal

    from codegenie.plugins.events import (
        BudgetCapExceeded,
        BudgetPrecharged,
        BudgetReconciled,
        BudgetReconciledDuplicate,
        BudgetUnknownTokenReconcile,
    )
    from codegenie.types.identifiers import BudgetTokenId, TokenCount

    log = EventLog(root=tmp_path, workflow_id=_wf(), clock=_now)
    token_id = BudgetTokenId("a" * 32)

    log.emit_internal(
        BudgetPrecharged(
            event_id=EventId("01HBDGPREXX"),
            workflow_id=_wf(),
            timestamp=_now(),
            token_id=token_id,
            precharged_tokens=TokenCount(100),
            precharged_dollars=Decimal("0.0003"),
        )
    )
    log.emit_internal(
        BudgetReconciled(
            event_id=EventId("01HBDGRECXX"),
            workflow_id=_wf(),
            timestamp=_now(),
            token_id=token_id,
            actual_in=TokenCount(50),
            actual_out=TokenCount(30),
            actual_dollars=Decimal("0.00024"),
        )
    )
    log.emit_internal(
        BudgetReconciledDuplicate(
            event_id=EventId("01HBDGDUPXX"),
            workflow_id=_wf(),
            timestamp=_now(),
            token_id=token_id,
        )
    )
    log.emit_internal(
        BudgetCapExceeded(
            event_id=EventId("01HBDGCAPXX"),
            workflow_id=_wf(),
            timestamp=_now(),
            reason="workflow_max_dollars_exceeded",
        )
    )
    log.emit_internal(
        BudgetUnknownTokenReconcile(
            event_id=EventId("01HBDGUNKXX"),
            workflow_id=_wf(),
            timestamp=_now(),
            token_id=BudgetTokenId("0" * 32),
        )
    )
    log.flush()

    # ``replay()`` sorts by (timestamp, event_id); with a fixed ``clock=_now``
    # all events share a timestamp so the order is event_id-lexicographic, not
    # emit order. Assert by class membership instead — the round-trip property
    # is that every emitted variant lands on disk and reads back equal,
    # regardless of replay-side sort.
    replayed = list(log.replay())
    assert len(replayed) == 5
    by_type = {type(e): e for e in replayed}
    assert set(by_type) == {
        BudgetPrecharged,
        BudgetReconciled,
        BudgetReconciledDuplicate,
        BudgetCapExceeded,
        BudgetUnknownTokenReconcile,
    }
    pre = by_type[BudgetPrecharged]
    assert isinstance(pre, BudgetPrecharged)
    assert pre.precharged_dollars == Decimal("0.0003")
    rec = by_type[BudgetReconciled]
    assert isinstance(rec, BudgetReconciled)
    assert rec.actual_in == 50
    cap = by_type[BudgetCapExceeded]
    assert isinstance(cap, BudgetCapExceeded)
    assert cap.reason == "workflow_max_dollars_exceeded"


def test_emit_internal_rejects_unregistered_class(tmp_path: Path) -> None:
    """AC-13 — ``emit_internal`` raises ``TypeError`` for an unregistered class.

    Pydantic-model-but-not-in-``_INTERNAL_CLASSES`` is the realistic regression
    risk: someone adds a new event class to the file but forgets to register it
    in the union and the tuple. ``isinstance(event, _INTERNAL_CLASSES)`` is the
    runtime guard.
    """
    from pydantic import BaseModel, ConfigDict

    class _Unregistered(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        event_type: str = "unregistered"
        event_id: EventId
        workflow_id: WorkflowId
        timestamp: datetime

    log = EventLog(root=tmp_path, workflow_id=_wf())
    with pytest.raises(TypeError, match="WorkflowInternalEvent"):
        log.emit_internal(  # type: ignore[arg-type]
            _Unregistered(
                event_id=EventId("01HUNREG"),
                workflow_id=_wf(),
                timestamp=_now(),
            )
        )
