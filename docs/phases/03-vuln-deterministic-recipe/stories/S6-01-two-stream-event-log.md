# Story S6-01 — Two-stream `EventLog` with BLAKE3-chained spanning stream

**Step:** Step 6 — RemediationOrchestrator, TrustScorer, two-stream EventLog, SubgraphNode Protocol, end-to-end happy path
**Status:** Ready
**Effort:** L
**Depends on:** S2-04, S5-04
**ADRs honored:** ADR-0005 (two-stream event log per ADR-0034), ADR-0010 (tagged-union outcomes; newtypes), ADR-0011 (honest-framing — chain is tamper-*evident* not tamper-proof), [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)

## Context

Production ADR-0034 commits to a **hybrid** event-sourcing backend: Phase 9 lands Temporal for workflow-internal history and Postgres for workflow-spanning audit. All three Phase 3 lens designs proposed a single stream and asserted Phase 9 would "lift unchanged" — the critic flagged this as the cardinal blind spot (see `../critique.md §Cross-design observations`). ADR-0005 resolves it by shipping the two-stream split **now**: per-workflow `.codegenie/events/workflow-internal/<workflow_id>.jsonl.zst` (Phase 9 ports to Temporal history) + shared append-only `.codegenie/events/spanning/append.jsonl.zst` (Phase 9 ports to Postgres `events` table). The on-disk locations are themselves a stable contract (ADR-0005 §Consequences).

The spanning stream is BLAKE3-chained for tamper evidence (lifts Phase 0's `audit_anchor` chain primitive from `src/codegenie/audit.py`) and `fcntl.flock`-protected so that two concurrent `codegenie remediate` invocations cannot interleave writes. The internal stream is per-workflow, so each workflow owns its file — fsync on workflow end is sufficient. Crossing the taxonomy boundary (emitting a workflow-internal variant on the spanning stream or vice versa) is a contract break gated by ADR amendment.

This story is **load-bearing for everything else in Step 6**: S6-02 (TrustScorer constructor-injects an `EventLog`), S6-03 (subgraph nodes emit via the `EventLog`), S6-04 (orchestrator constructs and owns the `EventLog` lifecycle), S6-05 (`codegenie audit verify` extends to walk the spanning chain), S6-06 (the contract snapshot freezes `EventLog`'s public surface). It is also the **single most attacked architectural decision in Phase 3** — under-specifying it now means Phase 9's migration becomes a re-taxonomize-the-world effort the architecture spec explicitly rejects.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C9` — `EventLog` public interface, both stream paths, the exhaustive `WorkflowInternalEvent` / `WorkflowSpanningEvent` variant lists, fsync-on-workflow-end + BLAKE3-per-emit semantics.
  - `../phase-arch-design.md §Data model` (lines ~846–874) — Pydantic shapes for both discriminated unions including `event_id: EventId`, `workflow_id: WorkflowId`, `prev_hash: BlobDigest` on spanning events.
  - `../phase-arch-design.md §Design patterns applied` row 6 — "Event sourcing as canonical primitive (two-stream split)" — pattern fit + why.
  - `../phase-arch-design.md §Edge cases E13` — concurrent invocation must be detected via `.codegenie/.lock` flock; spanning-stream `fcntl.flock` is the deeper line of defense if the outer lock is somehow bypassed.
  - `../phase-arch-design.md §Harness engineering — Replay / debuggability` — `codegenie audit verify` extends to the spanning stream; replay produces byte-equal post-state (modulo timestamps + `workflow_id`).
- **Phase ADRs:**
  - `../ADRs/0005-two-stream-event-log-per-adr-0034.md` — the decision document. Read §Decision, §Consequences (esp. "spanning stream is the seed source for Phase 6.5"), §Reversibility.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — the chain is tamper-*evident* not tamper-*proof*; the BLAKE3 chain catches accidental corruption + post-hoc tampering, not a determined real-time attacker.
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` §Consequences — `TrustScorer.__init__(event_log: EventLog)` constructor-injects the log; ambient-state rejected.
- **Production ADRs:**
  - `../../../production/adrs/0034-event-sourcing-canonical-primitive.md` — the hybrid backend ADR-0005 aligns to.
- **Existing code to reuse (NOT reinvent):**
  - `src/codegenie/audit.py` (Phase 0 / S3-06) — `audit_anchor` BLAKE3-chained writer; `chain_append` + `chain_verify` primitives. The spanning-stream writer is a **second instance** of this pattern with `fcntl.flock` added and `.jsonl.zst` compression; it is NOT a from-scratch reimplementation.
  - `src/codegenie/hashing.py` — `content_hash` (BLAKE3) helpers.
  - `src/codegenie/types/identifiers.py` (S1-01) — `WorkflowId`, `EventId`, `BlobDigest` newtypes.
- **This phase, parallel stories:**
  - S2-04 — `Resolver` is the producer of `PluginResolved` events; this story provides the writer.
  - S5-04 — `LockfilePolicy` violations become the payload of one of the `WorkflowInternalEvent` variants emitted during Stage 6.
  - S6-02 — `TrustScorer` consumes `EventLog.replay()` to fold `AdapterDegraded` into `TrustOutcome.confidence`.

## Goal

Land `src/codegenie/plugins/events.py` exposing `EventLog(root, workflow_id)` with four methods (`emit_internal`, `emit_spanning`, `replay`, `flush`); two Pydantic discriminated unions (`WorkflowInternalEvent` / `WorkflowSpanningEvent`) populated with every variant named in `../phase-arch-design.md §Component design C9`; on-disk format `jsonl.zst` per stream; BLAKE3 chain + `fcntl.flock` on the spanning stream; replay produces byte-equal post-state modulo timestamps + `workflow_id`.

## Acceptance criteria

- [ ] `src/codegenie/plugins/events.py` exists; `from codegenie.plugins.events import EventLog, WorkflowInternalEvent, WorkflowSpanningEvent` succeeds.
- [ ] `EventLog.__init__(self, root: Path, workflow_id: WorkflowId) -> None` constructs both directory paths (`<root>/events/workflow-internal/` and `<root>/events/spanning/`) with `parents=True, exist_ok=True`.
- [ ] `emit_internal(event: WorkflowInternalEvent) -> EventId` appends one zstd-compressed JSON line to `<root>/events/workflow-internal/<workflow_id>.jsonl.zst`; returns the minted `EventId` (ULID). No BLAKE3 chain on internal — per-workflow file, fsync on `flush()`.
- [ ] `emit_spanning(event: WorkflowSpanningEvent) -> EventId` appends one zstd-compressed JSON line to `<root>/events/spanning/append.jsonl.zst` under an exclusive `fcntl.flock(LOCK_EX)`; computes `event.prev_hash = BLAKE3(prior_chain_head || canonical_json(event - {prev_hash}))`; updates the in-process chain head; returns the minted `EventId`.
- [ ] Calling `emit_internal` with a `WorkflowSpanningEvent` (or vice versa) is a `TypeError` at the type-checker level (mypy `--strict` fails) AND a `ValueError` at runtime (Pydantic discriminated-union validation rejects).
- [ ] `WorkflowInternalEvent` is a Pydantic discriminated union (`Discriminator("event_type")`) with **all 16 variants** named in `../phase-arch-design.md §Component design C9`: `PluginsLoaded`, `PluginResolved`, `BundleBuilt`, `BundleEntryPromoted`, `RecipeMatched`, `RecipeApplied`, `RecipeSkipped`, `RecipeFailed`, `InstallStageOutcome`, `TestStageOutcome`, `LocalBranchWritten`, `RequiresHumanReview`, `AdapterDegraded`, `StageOutcome`, `FilesystemRaceDetected`, `GitHooksDisabledForRun`. Each variant is `frozen=True`, `extra="forbid"`, payload typed (no `dict[str, Any]`).
- [ ] `WorkflowSpanningEvent` is a Pydantic discriminated union with **all 8 variants** named in §C9: `WorkflowStarted`, `WorkflowCompleted`, `CostSandboxRun`, `CapabilityMinted`, `CapabilityUsed`, `PluginRegistryCorrupted`, `BenchReplayable`, `StaleVulnIndex`. Same constraints.
- [ ] `flush() -> None` `fsync`s the internal stream's file descriptor and the spanning stream's file descriptor; safe to call multiple times; idempotent.
- [ ] `replay() -> Iterator[Event]` reads back both streams in `(timestamp, event_id)` order and yields the parsed Pydantic events; reading a malformed line raises `EventLogCorrupted(path, line_number, reason)`.
- [ ] BLAKE3 chain on the spanning stream verifies: writing N events, then walking the file recomputing each `prev_hash`, matches the on-disk values byte-for-byte. Tamper test: flip one byte in any event's payload → walker raises `ChainTamperDetected(path, expected_prev, computed_prev)` at the first divergent record.
- [ ] `fcntl.flock(LOCK_EX)` cross-process: a unit test spawns two processes that both call `emit_spanning(...)` 100 times each against a shared `root`; the resulting chain verifies (no interleaving, no broken `prev_hash`).
- [ ] Replay round-trip is byte-equal modulo timestamps + `workflow_id`: `tests/integration/test_event_replay.py` writes a synthetic 20-event workload, calls `replay()`, re-serializes, and asserts equality modulo those two fields.
- [ ] `codegenie audit verify` (extended in S6-05) does NOT regress: this story does not edit the existing `verify` entrypoint — it only ships the spanning chain in a shape that S6-05's extension can walk.
- [ ] All event payload fields use **primitives only** (`str | int | bool | float | list[str]` per §C9 spec); a fence test AST-walks the variants and fails on any `dict[str, Any]` or `Any` annotation.
- [ ] Module-level docstring cites `ADR-0005` and `../phase-arch-design.md §Component design C9` as the source of truth.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. Write `tests/unit/plugins/test_events.py` first (red); confirm `ModuleNotFoundError` then `ImportError` on each missing variant as the union grows.
2. Create `src/codegenie/plugins/events.py`:
   - Module docstring naming ADR-0005 + `../phase-arch-design.md §Component design C9`.
   - Define each of the 16 `WorkflowInternalEvent` variants as `frozen=True, extra="forbid"` Pydantic models with a `event_type: Literal["<snake>"]` discriminator field + typed payload fields (NO `dict[str, Any]`). Example: `class PluginResolved(BaseModel): event_type: Literal["plugin_resolved"] = "plugin_resolved"; event_id: EventId; workflow_id: WorkflowId; timestamp: datetime; plugin_id: PluginId; matched_scope: str; specificity: int`.
   - Define each of the 8 `WorkflowSpanningEvent` variants similarly with the additional `prev_hash: BlobDigest` field.
   - `WorkflowInternalEvent: TypeAlias = Annotated[PluginsLoaded | PluginResolved | ... | GitHooksDisabledForRun, Discriminator("event_type")]`.
   - `WorkflowSpanningEvent: TypeAlias = Annotated[WorkflowStarted | ... | StaleVulnIndex, Discriminator("event_type")]`.
   - `class EventLog`:
     - `__init__` opens both files in append-binary mode wrapped in `zstandard.ZstdCompressor().stream_writer(...)`. Reads spanning-stream tail to compute `_chain_head: BlobDigest` (genesis = `"0" * 64` per Phase 0 audit convention).
     - `emit_internal(event)`: validate, canonical-JSON-encode (sorted keys, `separators=(",", ":")`), write line, return `event.event_id`.
     - `emit_spanning(event)`: acquire `fcntl.flock(self._spanning_fd, LOCK_EX)`; **re-read tail under lock** (another process may have appended); recompute `prev_hash = BLAKE3(self._chain_head || canonical_json(event - {prev_hash}))`; rewrite event with that `prev_hash`; write line; release lock; update local `_chain_head`. Return `event.event_id`.
     - `flush()`: `os.fsync` both file descriptors.
     - `replay()`: open both streams read-only, decompress, parse line-by-line, yield events in `(timestamp, event_id)` order. Raise `EventLogCorrupted` on parse failure.
   - `__all__` lists `EventLog`, both unions, every variant class, and the exceptions.
3. Add the `zstandard` and `blake3` dependencies if not already in `pyproject.toml` (both should be present from Phase 0 — verify with `grep`).
4. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/plugins/test_events.py`.

```python
# tests/unit/plugins/test_events.py
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from codegenie.plugins.events import (
    EventLog, WorkflowInternalEvent, WorkflowSpanningEvent,
    PluginResolved, WorkflowStarted, AdapterDegraded,
    ChainTamperDetected, EventLogCorrupted,
)
from codegenie.types.identifiers import WorkflowId, EventId, PluginId, BlobDigest


def _wf() -> WorkflowId:
    return WorkflowId("01HFEEDFACE0000000000000000")  # ULID-shape stub

def _now() -> datetime:
    return datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)


def test_two_streams_write_to_distinct_paths(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path, workflow_id=_wf())
    log.emit_internal(PluginResolved(event_id=EventId("01H...01"), workflow_id=_wf(),
                                     timestamp=_now(), plugin_id=PluginId("p"),
                                     matched_scope="vuln--node--npm", specificity=3))
    log.emit_spanning(WorkflowStarted(event_id=EventId("01H...02"), workflow_id=_wf(),
                                      timestamp=_now(), prev_hash=BlobDigest("0" * 64)))
    log.flush()
    internal = tmp_path / "events" / "workflow-internal" / f"{_wf()}.jsonl.zst"
    spanning = tmp_path / "events" / "spanning" / "append.jsonl.zst"
    assert internal.exists() and internal.stat().st_size > 0
    assert spanning.exists() and spanning.stat().st_size > 0


def test_internal_event_to_spanning_method_is_rejected(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path, workflow_id=_wf())
    internal_event = PluginResolved(event_id=EventId("01H...01"), workflow_id=_wf(),
                                    timestamp=_now(), plugin_id=PluginId("p"),
                                    matched_scope="*--*--*", specificity=0)
    with pytest.raises((TypeError, ValidationError)):
        log.emit_spanning(internal_event)  # type: ignore[arg-type]


def test_blake3_chain_verifies_then_breaks_on_tamper(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path, workflow_id=_wf())
    for i in range(10):
        log.emit_spanning(WorkflowStarted(event_id=EventId(f"01H...{i:02}"), workflow_id=_wf(),
                                          timestamp=_now(), prev_hash=BlobDigest("0" * 64)))
    log.flush()
    # Re-open and walk — should verify
    assert list(log.replay())  # no exception
    # Tamper: flip one byte in the spanning file (zstd-aware: decompress, edit, recompress)
    _flip_one_payload_byte(tmp_path / "events" / "spanning" / "append.jsonl.zst")
    with pytest.raises(ChainTamperDetected):
        list(log.replay())


def test_cross_process_flock_keeps_chain_intact(tmp_path: Path) -> None:
    # Spawn two subprocesses, each writes 50 events; verify chain after.
    # (See test body in §Refactor — uses multiprocessing.Process)
    ...


def test_replay_round_trip_byte_equal_modulo_timestamps(tmp_path: Path) -> None:
    # Write a known-shape workload; replay; re-serialize; assert equal modulo timestamp + workflow_id.
    ...


def test_all_16_internal_variants_exist() -> None:
    from codegenie.plugins import events as ev
    expected = {"PluginsLoaded", "PluginResolved", "BundleBuilt", "BundleEntryPromoted",
                "RecipeMatched", "RecipeApplied", "RecipeSkipped", "RecipeFailed",
                "InstallStageOutcome", "TestStageOutcome", "LocalBranchWritten",
                "RequiresHumanReview", "AdapterDegraded", "StageOutcome",
                "FilesystemRaceDetected", "GitHooksDisabledForRun"}
    for name in expected:
        assert hasattr(ev, name), f"missing internal variant: {name}"


def test_all_8_spanning_variants_exist() -> None:
    from codegenie.plugins import events as ev
    expected = {"WorkflowStarted", "WorkflowCompleted", "CostSandboxRun",
                "CapabilityMinted", "CapabilityUsed", "PluginRegistryCorrupted",
                "BenchReplayable", "StaleVulnIndex"}
    for name in expected:
        assert hasattr(ev, name), f"missing spanning variant: {name}"


def test_event_payloads_have_no_dict_any() -> None:
    """AST-fence: no Any / dict[str, Any] on any event variant payload."""
    import ast, inspect
    from codegenie.plugins import events as ev
    src = inspect.getsource(ev)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "Any":
            pytest.fail("Any annotation present in events.py")
```

Run; confirm `ModuleNotFoundError`. Commit the red marker.

### Green — make it pass

Implement `EventLog` with the minimum code to satisfy each test. Resist the urge to factor out a `_BaseEvent` mixin that hides payload fields — every variant is a tiny class, and the discriminated-union pattern requires the `event_type: Literal[...]` field literally on each class. The `_chain_head` is read by decompressing the spanning file's tail; if the file is empty (genesis), `_chain_head = "0" * 64`.

### Refactor — clean up

- Pull `canonical_json(model)` into a helper (use `model.model_dump_json(by_alias=False)` with sorted keys via a custom encoder; align with Phase 0's `src/codegenie/hashing.py` if a helper already exists there).
- Document the BLAKE3-chain composition: `prev_hash = BLAKE3(prior_chain_head_bytes || canonical_json_bytes(event - {prev_hash}))` — mirrors Phase 0's `chain_append` shape. The match-Phase-0 alignment is the reason S6-05's `codegenie audit verify` extension is mechanical.
- Document at the module level: **the chain is tamper-evident, not tamper-proof** (per ADR-0011 honest-framing). An attacker with shell access can re-write the entire chain end-to-end; the chain catches accidental corruption + after-the-fact integrity verification, not a real-time MITM.
- Test the genesis case explicitly (`emit_spanning` on an empty file → `prev_hash == "0" * 64`).
- Document `flush()` as the orchestrator's `finally`-block contract (per ADR-0005 §Consequences).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/events.py` | New file — `EventLog`, two discriminated unions, all 24 variants, BLAKE3 chain, `fcntl.flock` |
| `tests/unit/plugins/test_events.py` | New file — two-stream writer, chain verify, tamper detection, cross-process flock, all-variants-exist fence |
| `tests/integration/test_event_replay.py` | New file — replay round-trip byte-equal modulo timestamps + workflow_id (per architecture spec §Harness engineering) |
| `pyproject.toml` (verify) | `zstandard` and `blake3` must be in `[project.dependencies]` — both should already be present from Phase 0 |

## Out of scope

- **`codegenie audit verify` CLI extension** — S6-05 lands this. This story only ships the chain in a shape S6-05 can walk.
- **`TrustScorer` reading `AdapterDegraded` events** — S6-02 lands this. This story only ships the variant + the writer.
- **Phase 9 migration code** — Phase 9 reads these files via separate ingestion jobs; out of scope here.
- **OpenTelemetry / structured-tracing integration** — deferred to Phase 13 per `../phase-arch-design.md §Harness engineering`.
- **Compaction / log rotation of the spanning stream** — Phase 9+ territory; Phase 3 ships unbounded append-only.
- **`PluginsLoaded` emission** — the variant must exist (this story) but the *call site* lives in S2-03 / S7-01 plugin-loader code; no edit here.

## Notes for the implementer

- The two streams are **non-fungible**. A reviewer might suggest "why not one method, `emit(event)`, dispatching on type?" — the answer is that `WorkflowInternalEvent` and `WorkflowSpanningEvent` are two **typed channels** to two **different backends** in Phase 9 (Temporal vs. Postgres). Separate methods make the channel a compile-time choice; a single `emit` collapses the categorical distinction back into runtime dispatch — exactly the anti-pattern ADR-0005 was written to avoid.
- The BLAKE3 chain composition must match Phase 0's `audit.py` shape **exactly** so that `codegenie audit verify` (S6-05) is a one-line addition to the verify dispatcher, not a parallel implementation. Read `src/codegenie/audit.py::chain_append` before writing; if your `prev_hash` formula differs, you're wrong.
- `fcntl.flock(LOCK_EX)` on Linux + macOS only — Windows-CI is out of scope for Phase 3 (the `bwrap` substrate alone forbids it). The lock acquisition is **blocking** by default; the orchestrator's `.codegenie/.lock` outer lock (S6-05) usually means the inner lock is uncontended, but the inner lock is the deeper defense if a future feature lets two workflows share a `root` dir.
- The 24 event variants are tedious to write — resist the urge to generate them from a single `Literal[...]` and a `dict[str, type]` registry. Each variant carries a **typed payload schema** that downstream readers (Phase 9, `codegenie audit verify`, the contract snapshot in S6-06) rely on. A registry hides the schema behind `Any`. The verbosity is the contract.
- For payload fields, prefer `list[str]` over `tuple[str, ...]` to match the §C9 spec literally (`payload: dict[str, str | int | bool | float | list[str]]`). Pydantic round-trips both, but the spec is the contract.
- The "compact" zstd format with `level=3` is a good default — higher levels (e.g., 19) cost more CPU per event and Phase 3's per-emit budget (event-appender throughput >30k events/s per S9-03) won't tolerate it. Verify with a benchmark before merging.
- If `tests/integration/test_event_replay.py` flakes on timestamp comparison, use a `freezegun` fixture or pass a `clock: Callable[[], datetime]` to `EventLog.__init__` for testability — the latter is preferred (dependency injection beats time-mocking magic).
- The `EventLogCorrupted` exception is the *parse-time* failure (malformed JSON, missing `event_type` discriminator). `ChainTamperDetected` is the *integrity-time* failure (BLAKE3 mismatch). They are categorically different and must not be conflated.
- Avoid `pickle.loads` anywhere in this module — the `forbidden-patterns` pre-commit hook bans it repo-wide (per CLAUDE.md). JSON-only on disk.
- The phrase "Phase 9 lifts unchanged" in lens designs is the **wrong** framing per ADR-0005. The correct framing: "Phase 9 lifts each stream into its destined backend — the categorical split is the lift." If your test names or docstrings imply a single-backend model, rewrite them.
