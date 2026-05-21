"""S6-01 — two-stream :class:`EventLog` with a BLAKE3-chained spanning stream.

Sources of truth: ``docs/phases/03-vuln-deterministic-recipe/ADRs/
0005-two-stream-event-log-per-adr-0034.md`` (the decision), Phase-0
``ADRs/0001-cache-content-hash-algorithm.md`` (the hashing chokepoint),
``ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md`` (honest
framing), and ``../phase-arch-design.md §Component design C9``.

**Two non-fungible streams.** Production ADR-0034 commits to a hybrid
event-sourcing backend; ADR-0005 ships the split *now* so Phase 9 lifts each
stream into its destined backend rather than re-taxonomising the world:

- ``<root>/events/workflow-internal/<workflow_id>.jsonl.zst`` — one file per
  workflow; Phase 9 ports it to Temporal history. No BLAKE3 chain (the file
  is owned by a single workflow; ``flush()`` fsyncs on workflow end).
- ``<root>/events/spanning/append.jsonl.zst`` — one append-only file shared
  across workflows; Phase 9 ports it to a Postgres ``events`` table. Every
  record is BLAKE3-chained (``prev_hash``) and every append happens under an
  exclusive ``fcntl.flock`` so two concurrent ``codegenie remediate``
  invocations cannot interleave writes.

:meth:`EventLog.emit_internal` and :meth:`EventLog.emit_spanning` are two
typed channels — a single ``emit`` dispatching on type would collapse the
categorical distinction back into runtime dispatch, the anti-pattern ADR-0005
exists to prevent.

**Honest framing (ADR-0011).** The BLAKE3 chain on the spanning stream is
tamper-evident, not tamper-proof. An attacker with shell access can re-write
the entire chain end-to-end; the chain catches accidental corruption and
supports after-the-fact integrity verification, not a real-time MITM.

**Hashing chokepoint (ADR-0001).** This module never imports ``blake3``
directly — every BLAKE3 call routes through
:func:`codegenie.hashing.content_hash_bytes`. The ``blake3:`` prefix is
stripped to populate the un-prefixed 64-hex :data:`~codegenie.types.
identifiers.BlobDigest`.

**Concurrency contract.** :meth:`EventLog.emit_spanning` is *synchronous* and
blocks on ``fcntl.flock(LOCK_EX)``. The orchestrator (S6-04) wraps each call
in ``asyncio.to_thread(...)`` — mirroring the established ``SubprocessJail.
run`` pattern. The lock is held only for the chain-step + append (sub-
millisecond), so blocking is acceptable.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Final, Literal, Protocol, runtime_checkable

import zstandard
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from codegenie.hashing import content_hash_bytes
from codegenie.plugins.cache_gc import CacheGcCompletedEvent
from codegenie.types.identifiers import (
    BlobDigest,
    BranchName,
    CveId,
    EventId,
    PluginId,
    PrimitiveName,
    RecipeId,
    SignalKind,
    TransformId,
    WorkflowId,
)

# --- Constants --------------------------------------------------------------

#: The chain head before the first spanning record — 64 hex zeros.
GENESIS_CHAIN_HEAD: Final[BlobDigest] = BlobDigest("0" * 64)

_ZSTD_LEVEL: Final[int] = 3
_READ_CHUNK: Final[int] = 65_536
_FILE_MODE: Final[int] = 0o600
_DIR_MODE: Final[int] = 0o700
_BLAKE3_PREFIX: Final[str] = "blake3:"

# ``CacheGcCompleted`` is the 9th spanning variant. S3-05 shipped the class as
# ``CacheGcCompletedEvent``; this module re-exports it under both names rather
# than redefining it (preserves S3-05's external contract — ADR-0005).
CacheGcCompleted = CacheGcCompletedEvent


# --- Exceptions -------------------------------------------------------------


class EventLogError(Exception):
    """Base class for every :class:`EventLog` failure."""


class EventLogCorrupted(EventLogError):
    """A stream could not be parsed — the *parse-time* failure.

    Raised on malformed JSON, a missing ``event_type`` discriminator, an
    unknown variant, or a truncated trailing zstd frame. Categorically
    distinct from :class:`ChainTamperDetected` (the *integrity-time* failure).
    """

    def __init__(self, path: Path, line_number: int, reason: str) -> None:
        self.path = path
        self.line_number = line_number
        self.reason = reason
        super().__init__(f"event log corrupted at {path}:{line_number} — {reason}")


class ChainTamperDetected(EventLogError):
    """A spanning record's ``prev_hash`` does not match the recomputed chain.

    The *integrity-time* failure — the BLAKE3 chain caught accidental
    corruption or after-the-fact tampering (ADR-0011: tamper-evident, not
    tamper-proof).
    """

    def __init__(self, path: Path, expected_prev: str | None, computed_prev: str) -> None:
        self.path = path
        self.expected_prev = expected_prev
        self.computed_prev = computed_prev
        super().__init__(
            f"chain tamper detected in {path} — on-disk prev_hash {expected_prev!r} "
            f"!= recomputed {computed_prev!r}"
        )


# --- Pure helpers (functional core — no I/O, no state) ----------------------


def canonical_json_bytes(event: BaseModel) -> bytes:
    """Return the deterministic canonical-JSON encoding of ``event``.

    Sorted keys + tight separators so the bytes are stable across Pydantic
    minor versions. The ``prev_hash`` field is dropped before serialising —
    the chain step computes it, so it must not fold into its own input.
    """
    data = event.model_dump(mode="json")
    data.pop("prev_hash", None)
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _chain_step(prior_head: BlobDigest, event_bytes: bytes) -> BlobDigest:
    """Fold one record into the BLAKE3 chain — the pure shared chain primitive.

    Composes ``content_hash_bytes(bytes.fromhex(prior_head) + event_bytes)``
    and strips the ``blake3:`` prefix to yield an un-prefixed 64-hex
    :data:`~codegenie.types.identifiers.BlobDigest`. No ``self``, no I/O, no
    state — S6-05's ``codegenie audit verify`` extension calls this exact
    function from a stateless chain walker (ADR-0001 chokepoint discipline).
    """
    digest = content_hash_bytes(bytes.fromhex(prior_head) + event_bytes)
    return BlobDigest(digest.removeprefix(_BLAKE3_PREFIX))


# --- Workflow-internal event variants (16; Phase 9 → Temporal history) ------


class PluginsLoaded(BaseModel):
    """The plugin loader finished discovering and verifying plugins."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["plugins_loaded"] = "plugins_loaded"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    plugin_ids: list[str]
    registry_digest: BlobDigest


class PluginResolved(BaseModel):
    """The resolver matched a plugin to the run's task/language/ecosystem scope."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["plugin_resolved"] = "plugin_resolved"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    plugin_id: PluginId
    matched_scope: str
    specificity: int


class BundleBuilt(BaseModel):
    """A capability bundle was assembled (cache hit or fresh build)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["bundle_built"] = "bundle_built"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    bundle_key: str
    plugin_count: int
    cache_hit: bool


class BundleEntryPromoted(BaseModel):
    """A more-specific plugin scope superseded a broader one in the bundle."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["bundle_entry_promoted"] = "bundle_entry_promoted"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    plugin_id: PluginId
    from_scope: str
    to_scope: str


class RecipeMatched(BaseModel):
    """A recipe in a plugin's catalog declared itself applicable to a CVE."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["recipe_matched"] = "recipe_matched"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    recipe_id: RecipeId
    plugin_id: PluginId
    cve_id: CveId


class RecipeApplied(BaseModel):
    """A recipe produced a deterministic transform."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["recipe_applied"] = "recipe_applied"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    recipe_id: RecipeId
    transform_id: TransformId
    files_changed: list[str]


class RecipeSkipped(BaseModel):
    """A recipe declined — its preconditions were not met."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["recipe_skipped"] = "recipe_skipped"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    recipe_id: RecipeId
    reason: str


class RecipeFailed(BaseModel):
    """A recipe raised an unrecoverable error while producing its transform."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["recipe_failed"] = "recipe_failed"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    recipe_id: RecipeId
    error_id: str
    detail: str


class InstallStageOutcome(BaseModel):
    """The sandboxed dependency-install stage finished."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["install_stage_outcome"] = "install_stage_outcome"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    passed: bool
    duration_ms: int
    exit_code: int


class TestStageOutcome(BaseModel):
    """The sandboxed test stage finished."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["test_stage_outcome"] = "test_stage_outcome"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    passed: bool
    duration_ms: int
    tests_run: int


class LocalBranchWritten(BaseModel):
    """The orchestrator committed the remediation to a local git branch."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["local_branch_written"] = "local_branch_written"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    branch: BranchName
    commit_count: int


class RequiresHumanReview(BaseModel):
    """The universal fallback exhausted automated remediation."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["requires_human_review"] = "requires_human_review"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    reason: str
    handoff_path: str


class AdapterDegraded(BaseModel):
    """An adapter ran in a degraded mode; the trust scorer folds this in (S6-02)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["adapter_degraded"] = "adapter_degraded"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    adapter_name: str
    signal: SignalKind
    detail: str


class StageOutcome(BaseModel):
    """A generic orchestrator-stage transition outcome."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["stage_outcome"] = "stage_outcome"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    stage: str
    passed: bool
    duration_ms: int


class FilesystemRaceDetected(BaseModel):
    """A TOCTOU race was detected at ``SandboxedPath.open`` time (ELOOP)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["filesystem_race_detected"] = "filesystem_race_detected"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    path: str
    errno: int
    detail: str


class GitHooksDisabledForRun(BaseModel):
    """The orchestrator disabled repo git hooks for the duration of the run."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["git_hooks_disabled_for_run"] = "git_hooks_disabled_for_run"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    hook_names: list[str]
    reason: str


# --- Workflow-spanning event variants (9; Phase 9 → Postgres ``events``) ----
# The eight native variants carry ``prev_hash``; ``CacheGcCompleted`` is the
# re-imported 9th variant and is chained at the on-disk envelope level instead
# (it predates the chain — see :meth:`EventLog.emit_spanning`).


class WorkflowStarted(BaseModel):
    """A ``codegenie remediate`` workflow began."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["workflow_started"] = "workflow_started"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    prev_hash: BlobDigest


class WorkflowCompleted(BaseModel):
    """A ``codegenie remediate`` workflow finished."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["workflow_completed"] = "workflow_completed"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    prev_hash: BlobDigest
    outcome: str
    duration_ms: int


class CostSandboxRun(BaseModel):
    """A sandboxed subprocess run consumed measured CPU/wall budget."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["cost_sandbox_run"] = "cost_sandbox_run"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    prev_hash: BlobDigest
    cpu_ms: int
    wall_ms: int
    exit_code: int


class CapabilityMinted(BaseModel):
    """A capability token was minted for a plugin."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["capability_minted"] = "capability_minted"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    prev_hash: BlobDigest
    primitive: PrimitiveName
    plugin_id: PluginId


class CapabilityUsed(BaseModel):
    """A minted capability token was exercised."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["capability_used"] = "capability_used"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    prev_hash: BlobDigest
    primitive: PrimitiveName
    detail: str


class PluginRegistryCorrupted(BaseModel):
    """The plugin registry failed an integrity check."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["plugin_registry_corrupted"] = "plugin_registry_corrupted"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    prev_hash: BlobDigest
    reason: str
    detail: str


class BenchReplayable(BaseModel):
    """A benchmark run was recorded as replayable (S9-04)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["bench_replayable"] = "bench_replayable"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    prev_hash: BlobDigest
    bench_name: str
    replay_digest: BlobDigest


class StaleVulnIndex(BaseModel):
    """The vulnerability index was observed to be stale (warn, not block)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: Literal["stale_vuln_index"] = "stale_vuln_index"
    event_id: EventId
    workflow_id: WorkflowId
    timestamp: datetime
    prev_hash: BlobDigest
    index_age_days: int
    index_digest: BlobDigest


# --- Discriminated unions (codebase convention — ``transforms/outcomes.py``) -

WorkflowInternalEvent = Annotated[
    PluginsLoaded
    | PluginResolved
    | BundleBuilt
    | BundleEntryPromoted
    | RecipeMatched
    | RecipeApplied
    | RecipeSkipped
    | RecipeFailed
    | InstallStageOutcome
    | TestStageOutcome
    | LocalBranchWritten
    | RequiresHumanReview
    | AdapterDegraded
    | StageOutcome
    | FilesystemRaceDetected
    | GitHooksDisabledForRun,
    Field(discriminator="event_type"),
]

WorkflowSpanningEvent = Annotated[
    WorkflowStarted
    | WorkflowCompleted
    | CostSandboxRun
    | CapabilityMinted
    | CapabilityUsed
    | PluginRegistryCorrupted
    | BenchReplayable
    | StaleVulnIndex
    | CacheGcCompleted,
    Field(discriminator="event_type"),
]

_INTERNAL_ADAPTER: Final[TypeAdapter[WorkflowInternalEvent]] = TypeAdapter(WorkflowInternalEvent)
_SPANNING_ADAPTER: Final[TypeAdapter[WorkflowSpanningEvent]] = TypeAdapter(WorkflowSpanningEvent)

_INTERNAL_CLASSES: Final[tuple[type[BaseModel], ...]] = (
    PluginsLoaded,
    PluginResolved,
    BundleBuilt,
    BundleEntryPromoted,
    RecipeMatched,
    RecipeApplied,
    RecipeSkipped,
    RecipeFailed,
    InstallStageOutcome,
    TestStageOutcome,
    LocalBranchWritten,
    RequiresHumanReview,
    AdapterDegraded,
    StageOutcome,
    FilesystemRaceDetected,
    GitHooksDisabledForRun,
)
_SPANNING_CLASSES: Final[tuple[type[BaseModel], ...]] = (
    WorkflowStarted,
    WorkflowCompleted,
    CostSandboxRun,
    CapabilityMinted,
    CapabilityUsed,
    PluginRegistryCorrupted,
    BenchReplayable,
    StaleVulnIndex,
    CacheGcCompleted,
)
_CACHE_GC_EVENT_TYPE: Final[str] = "cache_gc_completed"


# --- Sinks (imperative shell — the ``EventStreamSink`` port + two adapters) --


@runtime_checkable
class EventStreamSink(Protocol):
    """A per-stream storage port — production zstd files or in-memory tests.

    Phase 9's port to Postgres is a third adapter behind this same interface.
    """

    def append(self, line: bytes) -> None:
        """Append one record's canonical-JSON bytes (no trailing newline)."""

    def read_all(self) -> Iterator[bytes]:
        """Yield every record's bytes in append order."""

    def fsync(self) -> None:
        """Durably flush buffered writes."""

    def tail_chain_head(self) -> BlobDigest:
        """Return the last record's ``prev_hash``, or :data:`GENESIS_CHAIN_HEAD`."""

    def lock(self) -> AbstractContextManager[None]:
        """Acquire an exclusive append lock for the duration of the context."""


def _tail_chain_head(lines: Iterator[bytes]) -> BlobDigest:
    """Return the ``prev_hash`` of the last record, or genesis if there is none."""
    head = GENESIS_CHAIN_HEAD
    for line in lines:
        value = json.loads(line).get("prev_hash")
        if isinstance(value, str):
            head = BlobDigest(value)
    return head


class ZstdAppendingFileSink:
    """Production sink — one self-contained zstd frame appended per record.

    Each ``append`` writes an independent ``level=3`` frame, so a torn
    trailing frame never corrupts the prior BLAKE3 chain. No file descriptor
    is held between calls (every operation opens, acts, closes) — the
    spanning chain's correctness rests on ``fcntl.flock``, not on a long-
    lived handle.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._compressor = zstandard.ZstdCompressor(level=_ZSTD_LEVEL)

    def append(self, line: bytes) -> None:
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, _FILE_MODE)
        try:
            os.fchmod(fd, _FILE_MODE)
            os.write(fd, self._compressor.compress(line + b"\n"))
        finally:
            os.close(fd)

    def read_all(self) -> Iterator[bytes]:
        try:
            raw = self._path.read_bytes()
        except FileNotFoundError:
            return
        if not raw:
            return
        # Walk the concatenated frames: ``decompressobj`` finds each frame
        # boundary (``unused_data``); a one-shot ``decompress`` of that exact
        # frame raises ``ZstdError`` on a truncated frame — the streaming
        # readers decode a torn trailing frame silently, so this fails loud.
        decompressor = zstandard.ZstdDecompressor()
        remaining = raw
        line_number = 0
        while remaining:
            line_number += 1
            try:
                boundary = decompressor.decompressobj()
                boundary.decompress(remaining)
                frame = remaining[: len(remaining) - len(boundary.unused_data)]
                content = decompressor.decompress(frame)
            except zstandard.ZstdError as exc:
                raise EventLogCorrupted(self._path, line_number, "truncated_frame") from exc
            remaining = boundary.unused_data
            record = content.rstrip(b"\n")
            if record:
                yield record

    def fsync(self) -> None:
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, _FILE_MODE)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def tail_chain_head(self) -> BlobDigest:
        return _tail_chain_head(self.read_all())

    @contextmanager
    def lock(self) -> Iterator[None]:
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, _FILE_MODE)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


class InMemorySink:
    """Test sink — keeps records in a list so assertions skip the zstd round trip."""

    def __init__(self) -> None:
        self._lines: list[bytes] = []

    def append(self, line: bytes) -> None:
        self._lines.append(line)

    def read_all(self) -> Iterator[bytes]:
        yield from self._lines

    def fsync(self) -> None:
        return None

    def tail_chain_head(self) -> BlobDigest:
        return _tail_chain_head(iter(self._lines))

    @contextmanager
    def lock(self) -> Iterator[None]:
        # Single-process tests need no real lock — cross-process safety is
        # exercised against the file sink.
        yield


# --- EventLog ---------------------------------------------------------------


def _default_clock() -> datetime:
    """Return the current UTC time — the default emit-time stamper."""
    return datetime.now(UTC)


def _chmod_quiet(path: Path) -> None:
    """Best-effort tighten ``path`` to ``0o700`` (event dirs are owner-only)."""
    try:
        os.chmod(path, _DIR_MODE)
    except OSError:
        pass


def _replay_sort_key(event: BaseModel) -> tuple[datetime, str]:
    """Order replayed events by ``(timestamp, event_id)`` (ADR-0005 replay)."""
    timestamp = getattr(event, "timestamp", None)
    if timestamp is None:
        # ``CacheGcCompleted`` predates the envelope — fall back to its ISO clock.
        iso = getattr(event, "wall_clock_iso", "")
        try:
            timestamp = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            timestamp = datetime.min.replace(tzinfo=UTC)
    return (timestamp, str(getattr(event, "event_id", "")))


class EventLog:
    """Two-stream typed event writer — internal (per-workflow) + spanning (shared).

    The spanning stream is BLAKE3-chained and ``fcntl.flock``-protected;
    :meth:`emit_spanning` is synchronous and blocks on the lock (the
    orchestrator wraps it in ``asyncio.to_thread``). :meth:`flush` is the
    orchestrator's ``finally``-block contract (ADR-0005 §Consequences).
    """

    def __init__(
        self,
        root: Path,
        workflow_id: WorkflowId,
        *,
        clock: Callable[[], datetime] | None = None,
        sink: EventStreamSink | None = None,
    ) -> None:
        """Construct both stream directories and open both sinks.

        ``clock`` defaults to UTC ``datetime.now`` and stamps every emitted
        event's ``timestamp``. ``sink`` overrides the *spanning* sink (the
        internal stream always uses :class:`ZstdAppendingFileSink`) — tests
        pass an :class:`InMemorySink` for deterministic byte assertions.
        """
        self._clock: Callable[[], datetime] = clock if clock is not None else _default_clock

        # Public, read-only-by-convention — S6-02's ``TrustScorer`` folds
        # ``AdapterDegraded`` events filtered to this id into
        # ``TrustOutcome.confidence``; S6-04's orchestrator reads it too.
        self.workflow_id: WorkflowId = workflow_id

        events_dir = root / "events"
        internal_dir = events_dir / "workflow-internal"
        spanning_dir = events_dir / "spanning"
        internal_dir.mkdir(parents=True, exist_ok=True)
        spanning_dir.mkdir(parents=True, exist_ok=True)
        for directory in (events_dir, internal_dir, spanning_dir):
            _chmod_quiet(directory)

        self._internal_path: Path = internal_dir / f"{workflow_id}.jsonl.zst"
        self._spanning_path: Path = spanning_dir / "append.jsonl.zst"
        self._internal_sink: EventStreamSink = ZstdAppendingFileSink(self._internal_path)
        self._spanning_sink: EventStreamSink = (
            sink if sink is not None else ZstdAppendingFileSink(self._spanning_path)
        )
        self._chain_head: BlobDigest = self._spanning_sink.tail_chain_head()

    def _stamp(self, event: BaseModel) -> BaseModel:
        """Return ``event`` with its ``timestamp`` set from the injected clock.

        ``CacheGcCompleted`` carries no ``timestamp`` field (it predates the
        envelope) and is returned unchanged.
        """
        if "timestamp" in type(event).model_fields:
            return event.model_copy(update={"timestamp": self._clock()})
        return event

    def emit_internal(self, event: WorkflowInternalEvent) -> EventId:
        """Append one workflow-internal event; return its ``event_id``.

        No BLAKE3 chain — the file is owned by a single workflow.
        """
        if not isinstance(event, _INTERNAL_CLASSES):
            raise TypeError(
                f"emit_internal expects a WorkflowInternalEvent, got {type(event).__name__}"
            )
        stamped = self._stamp(event)
        self._internal_sink.append(canonical_json_bytes(stamped))
        return EventId(str(stamped.event_id))  # type: ignore[attr-defined]

    def emit_spanning(self, event: WorkflowSpanningEvent) -> EventId:
        """Append one BLAKE3-chained workflow-spanning event; return its id.

        Synchronous — blocks on ``fcntl.flock(LOCK_EX)``. Under the lock the
        on-disk chain tail is re-read (another process may have appended),
        the record's ``prev_hash`` is computed via :func:`_chain_step`, and
        the chained line is appended.
        """
        if not isinstance(event, _SPANNING_CLASSES):
            raise TypeError(
                f"emit_spanning expects a WorkflowSpanningEvent, got {type(event).__name__}"
            )
        stamped = self._stamp(event)
        dumped = stamped.model_dump(mode="json")
        dumped.pop("prev_hash", None)
        body = json.dumps(dumped, sort_keys=True, separators=(",", ":")).encode("utf-8")
        with self._spanning_sink.lock():
            prior_head = self._spanning_sink.tail_chain_head()
            new_head = _chain_step(prior_head, body)
            record = {**dumped, "prev_hash": new_head}
            line = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
            self._spanning_sink.append(line)
            self._chain_head = new_head
        event_id = getattr(stamped, "event_id", None)
        # ``CacheGcCompleted`` predates the envelope and has no ``event_id`` —
        # the per-record chain head is its unique synthetic identifier.
        return EventId(str(event_id)) if event_id is not None else EventId(new_head)

    def flush(self) -> None:
        """Fsync both streams — idempotent; a no-op before the first emit."""
        self._internal_sink.fsync()
        self._spanning_sink.fsync()

    def replay(self) -> Iterator[WorkflowInternalEvent | WorkflowSpanningEvent]:
        """Yield every event from both streams in ``(timestamp, event_id)`` order.

        The spanning stream is chain-verified in file order while reading;
        a mismatch raises :class:`ChainTamperDetected`. Malformed records or
        a truncated zstd frame raise :class:`EventLogCorrupted`.
        """
        events: list[WorkflowInternalEvent | WorkflowSpanningEvent] = []
        for line_number, line in enumerate(self._internal_sink.read_all(), start=1):
            events.append(self._decode_internal(line, line_number))

        head = GENESIS_CHAIN_HEAD
        for line_number, line in enumerate(self._spanning_sink.read_all(), start=1):
            obj = self._loads(line, self._spanning_path, line_number)
            body_obj = {key: value for key, value in obj.items() if key != "prev_hash"}
            body = json.dumps(body_obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
            computed = _chain_step(head, body)
            on_disk_prev = obj.get("prev_hash")
            if on_disk_prev != computed:
                raise ChainTamperDetected(
                    self._spanning_path,
                    on_disk_prev if isinstance(on_disk_prev, str) else None,
                    computed,
                )
            head = computed
            events.append(self._decode_spanning(obj, line_number))

        events.sort(key=_replay_sort_key)
        yield from events

    @staticmethod
    def _loads(line: bytes, path: Path, line_number: int) -> dict[str, object]:
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EventLogCorrupted(path, line_number, "malformed_json") from exc
        if not isinstance(decoded, dict):
            raise EventLogCorrupted(path, line_number, "non_object_record")
        return decoded

    def _decode_internal(self, line: bytes, line_number: int) -> WorkflowInternalEvent:
        obj = self._loads(line, self._internal_path, line_number)
        try:
            return _INTERNAL_ADAPTER.validate_python(obj)
        except ValueError as exc:
            raise EventLogCorrupted(self._internal_path, line_number, "schema_violation") from exc

    def _decode_spanning(self, obj: dict[str, object], line_number: int) -> WorkflowSpanningEvent:
        # ``CacheGcCompleted`` has no ``prev_hash`` field — strip the envelope
        # key before validating it (``extra="forbid"`` would otherwise reject).
        payload = obj
        if obj.get("event_type") == _CACHE_GC_EVENT_TYPE:
            payload = {key: value for key, value in obj.items() if key != "prev_hash"}
        try:
            return _SPANNING_ADAPTER.validate_python(payload)
        except ValueError as exc:
            raise EventLogCorrupted(self._spanning_path, line_number, "schema_violation") from exc


__all__ = [
    "GENESIS_CHAIN_HEAD",
    "AdapterDegraded",
    "BenchReplayable",
    "BundleBuilt",
    "BundleEntryPromoted",
    "CacheGcCompleted",
    "CacheGcCompletedEvent",
    "CapabilityMinted",
    "CapabilityUsed",
    "ChainTamperDetected",
    "CostSandboxRun",
    "EventLog",
    "EventLogCorrupted",
    "EventLogError",
    "EventStreamSink",
    "FilesystemRaceDetected",
    "GitHooksDisabledForRun",
    "InMemorySink",
    "InstallStageOutcome",
    "LocalBranchWritten",
    "PluginRegistryCorrupted",
    "PluginResolved",
    "PluginsLoaded",
    "RecipeApplied",
    "RecipeFailed",
    "RecipeMatched",
    "RecipeSkipped",
    "RequiresHumanReview",
    "StageOutcome",
    "StaleVulnIndex",
    "TestStageOutcome",
    "WorkflowCompleted",
    "WorkflowInternalEvent",
    "WorkflowSpanningEvent",
    "WorkflowStarted",
    "ZstdAppendingFileSink",
    "canonical_json_bytes",
]
