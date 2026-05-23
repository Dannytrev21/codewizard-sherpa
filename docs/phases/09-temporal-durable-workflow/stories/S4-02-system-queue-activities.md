# Story S4-02 — `emit_event`, `write_blob_ref`, `resolve_blob_ref` activities (the `system` task queue)

**Step:** Step 4 — Activity catalog (one file per activity, typed in and out, registry-collected)
**Status:** Ready
**Effort:** M
**Depends on:** S1-06 (`LangGraphCheckpointerPort` + capability records — `EventLogWriteCapability`), S3-04 (`EventLog.read_workflow` + chain-verify), S3-06 (`RedactedActivityResult.seal()`), S4-01 (`_POLICIES`)
**ADRs honored:** ADR-0007 (two task queues — these three live on `system`); ADR-0005 (BlobRef payload-by-reference); ADR-0008 (typed-credential blocklist at seal); ADR-0010 (per-activity timeouts from `_POLICIES`); production ADR-0034 (every activity emits typed events into the canonical log)

## Context

`emit_event`, `write_blob_ref`, `resolve_blob_ref` are the three **infra activities** that the workflow body and every other activity dispatches at. They share the `system` task queue (ADR-0007) because they hold only the `EventLogWriteCapability` / `AsyncConnectionPool` — they do not touch a repo, never call GitHub, never spawn a sandbox. Their typed-input / typed-output / idempotent-on-`AttemptId` discipline is the template the other six activities (S4-03..S4-05) mirror; landing them first means S4-03..S4-05 reviewers can copy the shape verbatim.

The smart-constructor pattern from S3-05 / S3-06 is load-bearing here:
- `BlobRef` is constructible **only** via `write_blob_ref` (the activity is the constructor — `resolve_blob_ref` reads but does not produce a fresh `BlobRef`).
- Every return value is `RedactedActivityResult`-derived; `seal()` is called inside the activity body and the `mypy --strict` annotation is what `tests/fence/test_activity_payload_typing.py` (S4-06) introspects.

`emit_event` carries an `EventLogWriteCapability` typed-Pydantic-record threaded explicitly from the worker bootstrap (S6-02). No `ContextVar`; no hidden state. Phase-arch's `§Capability threading discipline` names the max-three-frames rule: worker → activity wrapper → `EventLog.append_batch` call site. This story enforces that depth.

**Scope reminder.** This story ships the three activities + their idempotence machinery + the `@register_activity` wiring. Capability *minting* (the worker bootstrap that constructs an `EventLogWriteCapability`) is S6-02; this story only consumes the typed record. The `system` queue *worker bootstrap* is S6-01 — but the activities must exist with `task_queue="system"` registration before S6-01 can register them.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C2 — Activity catalog` (lines 465-486) — interface shape, per-activity envelope.
  - `../phase-arch-design.md §C5 — Canonical event log` (lines 524-544) — `EventLog.append` + `append_batch` + `EventLogWriteCapability` shape; per-workflow chain machinery.
  - `../phase-arch-design.md §C6 — Payload-by-reference` (lines 546-566) — `BlobRef` smart-constructor pattern; `events.blob_refs` table shape.
  - `../phase-arch-design.md §Sequence diagrams Scenario 1 happy path` — every event emission flow that `emit_event` services.
- **Phase ADRs:**
  - `../ADRs/0005-payload-by-reference-blobref-threshold.md` — ≥8 KiB threshold; `BlobRef` is the only payload >8 KiB in workflow history.
  - `../ADRs/0006-critical-event-synchronous-flush-vocabulary.md` — `@critical_event` variants bypass the batcher; `emit_event` propagates this via `EventBatchWriter.flush_now()`.
  - `../ADRs/0007-two-task-queue-partitioning-and-expansion-by-addition.md` — these three activities live on `system`.
  - `../ADRs/0008-typed-credential-blocklist-not-regex.md` — `seal()` discipline applies to these returns.
- **Existing code (precedent to mirror):**
  - `src/codegenie/probes/registry.py` — module-level `Final` registration pattern; `@register_activity` mirrors this.
  - `src/codegenie/depgraph/registry.py:30-38` — sibling deferral docstring pattern.
- **Sibling stories:**
  - `S1-04-register-activity-kernel.md` — `@register_activity` shape this story uses.
  - `S3-05-blob-ref-store.md` — `write_blob_ref(content) -> BlobRef` smart constructor at the data layer; this story wraps it as an Activity.
  - `S3-06-sanitizer-seal.md` — `RedactedActivityResult.seal()` semantics this story consumes.

## Goal

Ship three `@activity.defn`-decorated functions under `src/codegenie/durable/activities/` — `emit_event.py`, `write_blob_ref.py`, `resolve_blob_ref.py` — each (a) typed Pydantic input + `RedactedActivityResult`-derived output, (b) idempotent (`emit_event` on `event_id`, blob activities content-addressed on `BlobDigest`), (c) registered via `@register_activity(name=..., task_queue="system")`, (d) capability-threaded where applicable (`emit_event`), (e) explicit-import-collected in `__init__.py`.

## Acceptance criteria

- [ ] **AC-1 — `emit_event` typed input + output.** `src/codegenie/durable/activities/emit_event.py` defines `class EmitEventInput(BaseModel)` (`model_config = ConfigDict(frozen=True, extra="forbid")`) with fields: `events: tuple[EventPayload, ...]` (one or more variants from the S1-02 discriminated union), `capability: EventLogWriteCapability`, `attempt_id: AttemptId`. Defines `class EmitEventOutput(RedactedActivityResult)` with field `committed_event_ids: tuple[EventId, ...]`.
- [ ] **AC-2 — `emit_event` body shape.** The function is `@register_activity(name=ActivityName("emit_event"), task_queue=TaskQueueName("system"))` + `@activity.defn(name="emit_event")` (in that decorator order — the registry-side decoration is the outermost). Body: (a) idempotence check — if `attempt_id` × `event_id` tuple has already committed, return the cached `committed_event_ids` (read from `EventLog.read_by_attempt(attempt_id)`); (b) call `event_log.append_batch(input.events, capability=input.capability)`; (c) `return EmitEventOutput.seal(committed_event_ids=...)`. No retries inside the body.
- [ ] **AC-3 — `emit_event` capability honoring.** A test asserts that calling `emit_event` with an `EventLogWriteCapability` whose `allowed_kinds: frozenset[str]` excludes a variant in `input.events` raises a typed `CapabilityScopeError`; the error's `.kind` attribute is the offending event kind. This is the G9 blast-radius check at the activity layer — S8-03 exercises the cross-process version.
- [ ] **AC-4 — `write_blob_ref` typed input + output.** `src/codegenie/durable/activities/write_blob_ref.py` defines `class WriteBlobInput(BaseModel)` with `content: bytes`, `content_kind: BlobKind`, `attempt_id: AttemptId` (frozen, forbid). Defines `class WriteBlobOutput(RedactedActivityResult)` carrying `blob_ref: BlobRef`. Activity body delegates to S3-05's `write_blob_ref(content, content_kind, capability)`; `ON CONFLICT DO NOTHING` makes re-dispatch with identical content a no-op at the data layer.
- [ ] **AC-5 — `resolve_blob_ref` typed input + output.** `src/codegenie/durable/activities/resolve_blob_ref.py` defines `class ResolveBlobInput(BaseModel)` with `blob_ref: BlobRef`, `attempt_id: AttemptId`. Defines `class ResolveBlobOutput(RedactedActivityResult)` carrying `content: bytes`. Body: `bytes_content = await blob_store.resolve(input.blob_ref)`; `BlobDigestMismatchError` from the store is **non-retryable** (re-raise as is — `_POLICIES["resolve_blob_ref"].non_retryable_error_types` includes it).
- [ ] **AC-6 — Idempotence-on-`AttemptId` (the cross-cutting invariant).** Three tests, one per activity:
    - `emit_event`: invoking twice with identical `(attempt_id, events)` produces a single row in `events.events` (asserted by reading via `EventLog.read_workflow`) and identical `committed_event_ids` on both returns.
    - `write_blob_ref`: invoking twice with identical `content` produces one row in `events.blob_refs` (`ON CONFLICT DO NOTHING` machinery — assert `SELECT COUNT(*) WHERE digest = ...` returns 1).
    - `resolve_blob_ref`: invoking twice with identical `blob_ref` returns byte-identical content and the second call is served from the per-worker LRU (asserted via a probe counter — see Notes §3).
- [ ] **AC-7 — Pydantic round-trip.** A property test (`hypothesis`, dev-dep) generates random `EmitEventInput` / `WriteBlobInput` / `ResolveBlobInput` instances and asserts `Cls.model_validate_json(instance.model_dump_json()) == instance`. Catches a contributor adding a `dict[str, Any]` field that breaks JSON round-trip.
- [ ] **AC-8 — Explicit-import collection.** `src/codegenie/durable/activities/__init__.py` carries an explicit-import block: `from . import emit_event as _emit_event; from . import write_blob_ref as _write_blob_ref; from . import resolve_blob_ref as _resolve_blob_ref`. A test asserts importing `codegenie.durable.activities` registers all three names into `_ACTIVITIES`.
- [ ] **AC-9 — `policy_for(name)` consumption.** Each activity's `_POLICIES` row was declared in S4-01; this story's executor trims each of `emit_event`, `write_blob_ref`, `resolve_blob_ref` out of `_EXPECTED_BUT_UNSHIPPED` (S4-01 AC-6). A test asserts `policy_for(ActivityName("emit_event")).start_to_close_timeout == timedelta(seconds=5)`.
- [ ] **AC-10 — `seal()` at the boundary.** Each activity's return annotation is `EmitEventOutput` / `WriteBlobOutput` / `ResolveBlobOutput`, each `RedactedActivityResult`-derived. A test asserts `inspect.signature(emit_event).return_annotation` is `EmitEventOutput`. S4-06's fence test exercises the generic version of this.
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on the three activity files + their test files. `make lint-imports` clean (no activity imports from `codegenie.durable.workflows.*` — S4-08 enforces).

## Implementation outline

1. **Define the input/output Pydantic models** in each activity's module (NOT in a shared `payloads.py` — keep one-file-per-activity discipline).
2. **Idempotence helper** in `src/codegenie/durable/activities/_idempotence.py`: `async def has_committed(attempt_id: AttemptId, event_log: EventLog) -> tuple[EventId, ...] | None`. Used by `emit_event` only; `write_blob_ref` / `resolve_blob_ref` get idempotence for free from the content-addressed store (`ON CONFLICT DO NOTHING`).
3. **Activity bodies**: each is < 25 LOC; pure dispatch + idempotence check + `seal()`. Resist adding logging or metrics — Phase-9 observability comes from typed events, not log lines.
4. **Decorator order**: outer = `@register_activity(name=..., task_queue=...)`; inner = `@activity.defn(name=...)`. Reason: the `temporalio` decorator wraps the function with metadata Temporal needs; the registry decorator captures a reference to the already-wrapped object. Reversing the order leaves Temporal unable to find the activity.
5. **`__init__.py` collection**: explicit-import per S1-04's discipline — no `importlib.metadata` entry-point scan, no `importlib.iter_modules`. Adding an activity = one new import line.
6. **`_EXPECTED_BUT_UNSHIPPED` trim**: the same commit that adds the three activities removes their names from `_EXPECTED_BUT_UNSHIPPED` in `retry_policies.py`.
7. **Test fixtures**: `tests/unit/durable/activities/conftest.py` exposes `fake_event_log` (in-memory `EventLog` test double), `fake_blob_store`, `system_capability` (an `EventLogWriteCapability` with `allowed_kinds=frozenset({"WorkflowStarted", "PluginResolved", ...})`).

## TDD plan — red / green / refactor

### Red — failing test first

```python
# tests/unit/durable/activities/test_emit_event.py
import pytest
from codegenie.durable.activities.emit_event import emit_event, EmitEventInput
from codegenie.events.payloads import WorkflowStarted
from codegenie.types.identifiers import AttemptId, EventId, WorkflowId


async def test_emit_event_appends_then_returns_committed_ids(
    fake_event_log, system_capability
):
    """AC-2 — emit_event delegates to EventLog.append_batch and returns the
    committed EventId tuple. The reason this is the first red test: every
    later activity emits events via this seam; if the input/output shape is
    wrong, every downstream test fails for the wrong reason."""
    event = WorkflowStarted(workflow_id=WorkflowId("wf-1"), ...)
    out = await emit_event(EmitEventInput(
        events=(event,),
        capability=system_capability,
        attempt_id=AttemptId("a-1"),
    ))
    assert len(out.committed_event_ids) == 1
    assert isinstance(out.committed_event_ids[0], EventId)
```

Why it fails: `codegenie.durable.activities.emit_event` doesn't exist yet — `ImportError`.

### Green — minimal pass

- Ship the three modules.
- `emit_event` body: idempotence check via `_idempotence.has_committed`; delegate to `EventLog.append_batch`; `seal()`.
- `write_blob_ref` / `resolve_blob_ref` delegate to the S3-05 layer.

### Required follow-on tests (per AC)

```python
async def test_emit_event_idempotent_on_attempt_id(fake_event_log, system_capability):
    """AC-6 — exactly-once at the data layer. Two invocations with identical
    (attempt_id, events) produce one row, not two. The reason: Temporal's
    at-least-once delivery semantics mean every activity will re-run under
    failure; without this check, the canonical log doubles every event for
    every retry, projection counts go wrong, BLAKE3 chain still verifies
    (because the duplicates are real rows), and the audit trail lies."""
    event = WorkflowStarted(workflow_id=WorkflowId("wf-1"), ...)
    inp = EmitEventInput(events=(event,), capability=system_capability,
                         attempt_id=AttemptId("a-1"))
    first = await emit_event(inp)
    second = await emit_event(inp)
    assert first.committed_event_ids == second.committed_event_ids
    rows = [e async for e in fake_event_log.read_workflow(WorkflowId("wf-1"))]
    assert len(rows) == 1


async def test_emit_event_rejects_kind_outside_capability_allowlist(
    fake_event_log,
):
    """AC-3 — G9 blast-radius at the activity boundary. A worker holding a
    narrow EventLogWriteCapability cannot emit a variant outside its allowed
    kinds; CapabilityScopeError surfaces the offending kind explicitly so
    the operator can audit."""
    from codegenie.durable.capabilities import CapabilityScopeError, EventLogWriteCapability
    narrow_cap = EventLogWriteCapability(
        task_queue=TaskQueueName("system"),
        allowed_kinds=frozenset({"WorkflowStarted"}),  # not MergeOutcome
    )
    bad_event = MergeOutcome(...)
    with pytest.raises(CapabilityScopeError) as exc_info:
        await emit_event(EmitEventInput(
            events=(bad_event,), capability=narrow_cap, attempt_id=AttemptId("a-1"),
        ))
    assert exc_info.value.kind == "MergeOutcome"


async def test_write_blob_ref_content_addressed_dedupe(fake_blob_store):
    """AC-6 — write twice with identical bytes → one row in events.blob_refs.
    The reason: Temporal will re-dispatch on activity-worker SIGKILL; without
    ON CONFLICT DO NOTHING, the second write would raise a PK violation and
    the activity would retry until max_attempts; with it, the second write
    silently dedupes and the activity completes idempotently."""
    content = b"x" * 9000  # > 8 KiB threshold
    inp = WriteBlobInput(content=content, content_kind=BlobKind.ContextBundle,
                         attempt_id=AttemptId("a-1"))
    first = await write_blob_ref(inp)
    second = await write_blob_ref(inp)
    assert first.blob_ref == second.blob_ref
    assert fake_blob_store.row_count_for(first.blob_ref.digest) == 1


async def test_resolve_blob_ref_byte_identical_after_round_trip(fake_blob_store):
    """AC-5 — resolve returns byte-identical content; the BlobRef shape is
    the only payload-by-reference the workflow history sees."""
    content = b"x" * 9000
    ref = (await write_blob_ref(WriteBlobInput(content=content, ...))).blob_ref
    out = await resolve_blob_ref(ResolveBlobInput(blob_ref=ref, attempt_id=AttemptId("a-1")))
    assert out.content == content


def test_seal_at_return_boundary():
    """AC-10 — return annotations are RedactedActivityResult-derived; this is
    the static-check counterpart of S4-06's fence test."""
    import inspect
    assert issubclass(inspect.signature(emit_event).return_annotation, RedactedActivityResult)
    assert issubclass(inspect.signature(write_blob_ref).return_annotation, RedactedActivityResult)
    assert issubclass(inspect.signature(resolve_blob_ref).return_annotation, RedactedActivityResult)
```

### Refactor

- `__init__.py` module docstring names the three activities + their task queue (`system`); cites ADR-0007.
- `_idempotence.py` carries the contract docstring: "every side-effect-bearing activity must idempotency-check before mutation; this helper centralizes the read."
- Each activity file's module docstring carries a one-liner naming the consumer (workflow / other activity) so a grep for the activity name lands on the contract paragraph first.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/activities/__init__.py` | Explicit-import collection of the three modules. |
| `src/codegenie/durable/activities/emit_event.py` | `EmitEventInput`, `EmitEventOutput`, `emit_event` body. |
| `src/codegenie/durable/activities/write_blob_ref.py` | `WriteBlobInput`, `WriteBlobOutput`, `write_blob_ref` body. |
| `src/codegenie/durable/activities/resolve_blob_ref.py` | `ResolveBlobInput`, `ResolveBlobOutput`, `resolve_blob_ref` body. |
| `src/codegenie/durable/activities/_idempotence.py` | `has_committed(attempt_id, event_log)` shared helper. |
| `src/codegenie/durable/activities/retry_policies.py` | Trim three names from `_EXPECTED_BUT_UNSHIPPED` (S4-01 AC-6). |
| `tests/unit/durable/activities/test_emit_event.py` | Red test + per-AC follow-on. |
| `tests/unit/durable/activities/test_write_blob_ref.py` | Per-activity test file. |
| `tests/unit/durable/activities/test_resolve_blob_ref.py` | Per-activity test file. |
| `tests/unit/durable/activities/conftest.py` | `fake_event_log`, `fake_blob_store`, `system_capability` fixtures. |

## Out of scope

- The worker bootstrap that constructs `EventLogWriteCapability` from a K8s ServiceAccount mount — S6-02.
- The `system` worker process itself — S6-01.
- The `EventBatchWriter` flush internals — S3-02.
- The BlobRef LRU cache in the activity worker — S3-05's data-layer concern; this story uses the cache transparently.
- The `@critical_event` sync-flush bypass — already in place at the `EventLog` layer (S3-03); `emit_event` calls `append_batch` which honors the bypass.
- The G9 cross-process blast-radius adversarial — S8-03. This story tests the in-process `CapabilityScopeError` path.

## Notes for the implementer

### §1 — Decorator order matters

`@register_activity(...)` is the outermost decorator. `@activity.defn(...)` is inner. The runtime registration captures the `temporalio`-wrapped function. If you flip the order, Temporal won't see the activity at worker registration time and the workflow will hang on `execute_activity`. The S1-04 docstring on `@register_activity` carries the same warning — read it before writing the decoration line.

### §2 — Idempotence is the load-bearing invariant

Temporal's delivery semantics are *at-least-once*. Without explicit idempotence on `AttemptId`, every activity that mutates the canonical log doubles its writes on every worker SIGKILL. The G1 durability test (S8-01) exercises this exact path — `test_kill_worker_resume.py` kills the activity worker mid-flight, Temporal re-dispatches, and the test asserts the terminal `VulnLedger` is byte-identical AND the event log has *one* copy of each event. Without AC-6, the event log would have N copies (one per retry).

### §3 — Don't observe the LRU directly from tests

The per-worker `BlobRef` LRU cache (mentioned in `phase-arch-design.md §C6`) is an internal optimization. Tests assert *behavior* (byte-identical content on resolve) not *implementation* (cache hit count). If a future PR replaces the LRU with a different cache shape, AC-5's test should still pass — that's the test-quality invariant. The "probe counter" mention in AC-6 is for an *optional* observability hook that S3-05 may ship; if it's not present, drop that assertion (the behavioral assertion is sufficient).

### §4 — One file per activity is a strict rule

Resist the urge to put `emit_event` + `write_blob_ref` in a `system_activities.py` module "because they share the task queue." Phase 4 explicitly carries "one file per activity" because (a) future activities get a stable per-file home for their `git log`, (b) the `tests/unit/durable/activities/test_{activity}.py` mirror is uniform, (c) `mypy --strict` errors point at one file's line numbers without confusion. The shared `_idempotence.py` is the *exception* — it's deliberately *not* an activity; it's a small helper consumed by one of them. A second helper would trigger the rule-of-three discussion (see Notes §5).

### §5 — Rule-of-three on activity-helpers

If S4-03..S4-05 add more shared helpers (`_attempt_keyed_lookup`, `_blob_threshold_router`), revisit the question: should there be a `_lib.py` carrying common helpers? Today the count is N=1 (`_idempotence.py`); keep the layout flat. If N hits 3, the next story landing should add a one-paragraph rule-of-three observation to `__init__.py`'s docstring (mirror `depgraph/registry.py:30-38`) and defer the extract.

### §6 — `seal()` is non-negotiable

Every return is `RedactedActivityResult`-derived. The static check is in the type annotation (`-> EmitEventOutput`); the runtime check is in the body (`return EmitEventOutput.seal(...)`); the fence check is in `tests/fence/test_activity_payload_typing.py` (S4-06). Three independent layers — ADR-0004's layered-defense pattern applied to the sanitizer instead of the workflow body. Removing the `seal()` call inside an activity body is undetected by mypy (the annotation still matches because `EmitEventOutput` extends `RedactedActivityResult`) — but a value not produced by `seal()` skips layers (b) and (c) of the sanitizer (ADR-0008). S3-06's tests catch the "constructed `EmitEventOutput` without `seal()`" case via the `_sanitized: Literal[True]` discipline.

### §7 — Don't import from `codegenie.durable.workflows`

S4-08 ships the import-linter contract that enforces this; this story respects it pre-emptively. The activity layer's dependency direction is **only** outward from `codegenie.events.*` / `codegenie.types.*` — never inward from `codegenie.durable.workflows`. If a contributor needs a type that lives in the workflow module, the type belongs in `codegenie.events.payloads` or `codegenie.durable.capabilities` instead.
