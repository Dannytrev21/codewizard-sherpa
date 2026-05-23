# Story S4-03 — `resolve_plugin`, `build_bundle`, `route` activities (Phase-8 Supervisor 1:1)

**Step:** Step 4 — Activity catalog (one file per activity, typed in and out, registry-collected)
**Status:** Ready
**Effort:** M
**Depends on:** S4-01 (`_POLICIES`)
**ADRs honored:** ADR-0010 (asymmetric activity granularity — Supervisor's three nodes map 1:1 to Activities; the [P]/[B] shape); ADR-0005 (BlobRef threshold for bundles >8 KiB); ADR-0007 (these three live on `vuln-remediation-node-npm` queue); ADR-0008 (typed-credential blocklist at seal); production ADR-0042 (multi-plugin coordination flows through `route` decisions)

## Context

The Phase-8 Supervisor was designed from day one **to be the Temporal seam** (ADR-0010): its three LangGraph nodes (`resolve_plugin`, `build_bundle`, `route`) carry no `SutDigest` invariance constraint, so each one maps 1:1 to a Temporal Activity. The asymmetric-granularity decision in ADR-0010 names this shape ([P]/[B]) explicitly — the *fat* `run_vuln_subgraph` is reserved for Phase-6's SHERPA subgraph where the digest contract pins the in-process LangGraph checkpoint structure.

These three activities are **thin Pydantic-typed wrappers** around the existing Phase-8 Supervisor functions. They (a) accept the typed input the Supervisor function expects (rebuilt as Pydantic models, not Phase-8 internal types), (b) call the underlying Supervisor function, (c) emit one typed event each (`PluginResolved`, `BundleBuilt`, `RouteDecided`) via `emit_event` (S4-02), (d) seal the return.

**Gap-3 lands here.** The architect explicitly carried the freshness-window field into `RouteDecided` from day one (manifest exec summary): `RouteDecision` records `decided_at: datetime` and `freshness_window: timedelta`. The workflow body's resume check (S5-03) compares `workflow.now() - decided_at <= freshness_window` and tier-descends on stale resume. This story just *carries the fields*; S5-03 acts on them.

**`build_bundle` and the BlobRef threshold.** Phase-8's `ContextBundle` is 50–150 KiB hot views; this exceeds the 8 KiB threshold in ADR-0005. `build_bundle` therefore returns a `BlobRef` for the bundle, not the bundle bytes — the workflow history stays compact (G8). The bundle bytes land in `events.blob_refs` via `write_blob_ref` (S4-02); subsequent activities (`route`, `run_vuln_subgraph`) take the `BlobRef` as input and `resolve_blob_ref` when they need the bytes.

**Scope reminder.** This story ships the three activities + their input/output models + the `RouteDecision` Pydantic record (carrying the Gap-3 freshness fields). The S5-03 resume check is a *consumer*; the workflow body owns the comparison. The `PluginResolved`, `BundleBuilt`, `RouteDecided` event variants are landed by S1-02; this story emits them.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C2 — Activity catalog` (lines 465-486) — `resolve_plugin p95 < 50 ms`, `build_bundle p95 < 200 ms`, `route p95 < 20 ms` performance envelope.
  - `../phase-arch-design.md §Sequence diagrams Scenario 1 happy path` — flow: `resolve_plugin` → `PluginResolved` (batched) → `build_bundle` → `write_blob_ref(bundle)` → `BundleBuilt` (batched) → `route` → `RouteDecided` (batched, NOT synchronous — critic correction).
  - `../phase-arch-design.md §Gap analysis — Gap-3 freshness window` — the `RouteDecision` carries `decided_at: datetime` + `freshness_window: timedelta` from day one.
- **Phase ADRs:**
  - `../ADRs/0010-activity-granularity-asymmetric.md` — three Supervisor nodes → three Activities; ADR-0010 §Consequences names this shape.
  - `../ADRs/0005-payload-by-reference-blobref-threshold.md` — bundles >8 KiB cross as `BlobRef`.
  - `../ADRs/0007-two-task-queue-partitioning-and-expansion-by-addition.md` — `vuln-remediation-node-npm` is the queue for these three.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — `resolve_plugin` lookup semantics.
  - `../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md` — `MultiPluginDispatch` is the parent's input; child workflows each get their own `resolve_plugin` activity invocation.
- **Existing Phase-8 source (the thing being wrapped):**
  - `src/codegenie/plugins/supervisor/*.py` (Phase-8 Supervisor implementation) — `resolve_plugin`, `build_bundle`, `route` functions; this story carries no logic, only the Activity wrapper.
- **Sibling stories:**
  - `S4-02-system-queue-activities.md` — the template these activities mirror; `emit_event` consumer pattern.
  - `S5-03-freshness-window-resume.md` — workflow consumer of `RouteDecision.freshness_window`.

## Goal

Ship three `@activity.defn`-decorated functions under `src/codegenie/durable/activities/` — `resolve_plugin.py`, `build_bundle.py`, `route.py` — each (a) typed Pydantic input + `RedactedActivityResult`-derived output, (b) idempotent on `AttemptId`, (c) registered on the `vuln-remediation-node-npm` task queue, (d) emitting exactly one typed event per invocation via `emit_event`, (e) `build_bundle` returning a `BlobRef` for bundles >8 KiB, (f) `route` carrying the Gap-3 `freshness_window` + `decided_at` fields.

## Acceptance criteria

- [ ] **AC-1 — `resolve_plugin` input/output.** `src/codegenie/durable/activities/resolve_plugin.py` defines `class ResolvePluginInput(BaseModel, frozen=True, extra="forbid")` with `repo_context_ref: BlobRef`, `task_class_id: TaskClassId`, `attempt_id: AttemptId`. Defines `class ResolvePluginOutput(RedactedActivityResult)` with `plugin_id: PluginId`, `plugin_version: str`, `resolution_rationale: str`.
- [ ] **AC-2 — `build_bundle` input/output + BlobRef threshold.** `src/codegenie/durable/activities/build_bundle.py` defines `class BuildBundleInput(BaseModel, frozen=True, extra="forbid")` with `plugin_id: PluginId`, `repo_context_ref: BlobRef`, `attempt_id: AttemptId`. Defines `class BuildBundleOutput(RedactedActivityResult)` with `bundle_ref: BlobRef` (NOT `bundle: bytes` — bundles >8 KiB cross as `BlobRef` per ADR-0005), `bundle_kind: BlobKind = BlobKind.ContextBundle`, `byte_len: int`. A test asserts `bundle_ref.byte_len > 8192` invariably for the canonical fixture (catches a regression that returned bytes directly).
- [ ] **AC-3 — `route` input/output + Gap-3 freshness fields.** `src/codegenie/durable/activities/route.py` defines `class RouteInput(BaseModel, frozen=True, extra="forbid")` with `plugin_id: PluginId`, `bundle_ref: BlobRef`, `cve_record_ref: BlobRef`, `attempt_id: AttemptId`. Defines `class RouteOutput(RedactedActivityResult)` with `decision: RouteDecision`, where `RouteDecision = Recipe | Rag | Llm` discriminated union; each variant carries **`decided_at: datetime` + `freshness_window: timedelta`** (the Gap-3 fields). A test asserts a `RouteDecision` reconstituted from `model_dump_json()` has byte-identical `decided_at` and `freshness_window` values.
- [ ] **AC-4 — Decorator stack on all three.** Each function is `@register_activity(name=ActivityName("<name>"), task_queue=TaskQueueName("vuln-remediation-node-npm"))` (outer) + `@activity.defn(name="<name>")` (inner). The names match `_POLICIES` exactly: `"resolve_plugin"`, `"build_bundle"`, `"route"`. Decoration drift triggers AC-9.
- [ ] **AC-5 — Idempotence-on-`AttemptId`.** Each activity, on re-dispatch with identical `attempt_id`, returns identical output bytes. For `resolve_plugin`: idempotence comes from the deterministic Phase-8 resolver — same input deterministically yields same output. For `build_bundle`: idempotence comes from the content-addressed `BlobStore` (`ON CONFLICT DO NOTHING`). For `route`: idempotence comes from `decided_at` being recorded in the canonical log on first emission and re-read on re-dispatch — re-dispatch DOES NOT mint a fresh `decided_at` (or workflow-resume staleness checks would always pass).
- [ ] **AC-6 — Exactly one event per invocation.** A test, per activity, asserts that invoking the activity emits exactly ONE typed event into the canonical log (via `emit_event`, batched): `resolve_plugin` → `PluginResolved`; `build_bundle` → `BundleBuilt`; `route` → `RouteDecided`. Catches a contributor doubling the event emission (one in the activity body, one in the called Supervisor function).
- [ ] **AC-7 — `route` is BATCHED, not synchronous.** Per `phase-arch-design.md §Sequence diagrams Scenario 1` ("`RouteDecided` (BATCHED, not synchronous — critic correction"), `route`'s `emit_event` invocation MUST NOT include the `@critical_event` flag. A test asserts the call site uses the default batched path, not `EventLog.append_synchronous`. The reason: routing decisions are not in the five-variant `@critical_event` vocabulary (S1-03); inflating them to synchronous flushes inflates the workflow body's p95 latency.
- [ ] **AC-8 — `seal()` at the boundary.** Each activity's return annotation is `ResolvePluginOutput` / `BuildBundleOutput` / `RouteOutput`, each `RedactedActivityResult`-derived. Body uses `seal()` to construct. Mirrors S4-02 AC-10.
- [ ] **AC-9 — `_EXPECTED_BUT_UNSHIPPED` trim.** This story's executor removes `ActivityName("resolve_plugin")`, `ActivityName("build_bundle")`, `ActivityName("route")` from `_EXPECTED_BUT_UNSHIPPED` in `retry_policies.py`. AC-9's test asserts `policy_for(ActivityName("resolve_plugin")).start_to_close_timeout == timedelta(seconds=30)` (S4-01's table value).
- [ ] **AC-10 — Explicit-import collection extension.** `__init__.py` adds three import lines for the three new modules; AC-8 of S4-02's collection test extends to assert six activity names register on import.
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean. `make lint-imports` clean (no inward imports from `codegenie.durable.workflows.*`).

## Implementation outline

1. **`RouteDecision` sum type** lives in `src/codegenie/durable/activities/route.py` (or in `codegenie.events.payloads` if it leaks across modules). Each variant carries `decided_at: datetime` + `freshness_window: timedelta`; the discriminator is `kind: Literal["Recipe", "Rag", "Llm"]`. `Field(discriminator="kind")` on the union.
2. **`resolve_plugin.py`**: thin wrapper around the Phase-8 `Supervisor.resolve_plugin(...)` function; body is < 25 LOC; the Supervisor function does the heavy lifting.
3. **`build_bundle.py`**: wraps `Supervisor.build_bundle(...)`; the Supervisor returns bytes; this Activity calls `write_blob_ref(content=bundle_bytes, content_kind=BlobKind.ContextBundle, ...)` via the **data-layer** `write_blob_ref` function (NOT the Activity — invoking an Activity from inside another Activity is an anti-pattern; the data layer is the consumer here). Returns a `BuildBundleOutput` carrying the `BlobRef`.
4. **`route.py`**: wraps `Supervisor.route(...)`; converts the Supervisor's decision shape into the typed `RouteDecision` sum type; **records `decided_at = workflow.now()`-equivalent** — but wait: activities are the imperative shell where non-determinism is fine. Use `datetime.now(timezone.utc)`. The workflow body never calls `datetime.now`; the *activity* does (the workflow consumes the recorded value via the activity's typed return — exactly the determinism boundary ADR-0004 names).
5. **Update `__init__.py`**: three new explicit-import lines. Same shape as S4-02.
6. **Update `_EXPECTED_BUT_UNSHIPPED`** in `retry_policies.py`: remove the three names.

## TDD plan — red / green / refactor

### Red — failing test first

```python
# tests/unit/durable/activities/test_route.py
import pytest
from datetime import timedelta
from codegenie.durable.activities.route import route, RouteInput
from codegenie.types.identifiers import AttemptId, BlobDigest, PluginId


async def test_route_decision_carries_freshness_fields(
    fake_event_log, vuln_capability,
):
    """AC-3 — Gap-3 lands in S4-03: route's RouteDecision MUST carry
    decided_at and freshness_window from day one. The workflow resume check
    in S5-03 reads these. The reason this is the red test: if RouteDecision
    is shipped without these fields, S5-03 has nothing to read and Gap-3
    silently re-opens. Lock in the shape today."""
    out = await route(RouteInput(
        plugin_id=PluginId("vulnerability-remediation--node--npm"),
        bundle_ref=BlobRef(digest=BlobDigest("a"*64), content_kind=BlobKind.ContextBundle, byte_len=9000),
        cve_record_ref=BlobRef(...),
        attempt_id=AttemptId("a-1"),
    ))
    assert out.decision.decided_at is not None
    assert out.decision.freshness_window > timedelta()
```

Why it fails: `codegenie.durable.activities.route` doesn't exist yet.

### Green — minimal pass

- Ship the three activity modules; thin wrappers around Phase-8 Supervisor calls.
- `RouteDecision` carries `decided_at` + `freshness_window` from day one.

### Required follow-on tests (per AC)

```python
async def test_build_bundle_returns_blob_ref_not_bytes(fake_blob_store, vuln_capability):
    """AC-2 — bundles >8 KiB cross as BlobRef. If a contributor 'optimizes'
    by inlining the bytes, the workflow history bloats and G8 regresses
    silently. Catch the regression at the type-level: BuildBundleOutput
    field is BlobRef, not bytes."""
    out = await build_bundle(BuildBundleInput(
        plugin_id=PluginId("vulnerability-remediation--node--npm"),
        repo_context_ref=BlobRef(...),
        attempt_id=AttemptId("a-1"),
    ))
    assert isinstance(out.bundle_ref, BlobRef)
    assert out.bundle_ref.byte_len > 8192


async def test_route_event_is_batched_not_synchronous(
    fake_event_log, vuln_capability,
):
    """AC-7 — RouteDecided is NOT in the five-variant @critical_event
    vocabulary. The activity body uses the batched path; inflating it to
    synchronous (~15 ms commit) would regress the per-workflow latency
    budget by ~30 ms (every route decision)."""
    out = await route(RouteInput(...))
    # Assert the emission landed in the batched queue, not the synchronous
    # path. The fake_event_log fixture exposes both counters.
    assert fake_event_log.batched_count == 1
    assert fake_event_log.synchronous_count == 0


async def test_resolve_plugin_idempotent_on_attempt_id(fake_event_log, vuln_capability):
    """AC-5 — re-dispatch returns identical output bytes. Phase-8's resolver
    is deterministic; the test pins the determinism at the Activity wrapper
    so a future contributor adding cache-busting (e.g., 'fresh ts on each call')
    is caught."""
    inp = ResolvePluginInput(
        repo_context_ref=BlobRef(...),
        task_class_id=TaskClassId("vuln-remediation"),
        attempt_id=AttemptId("a-1"),
    )
    first = await resolve_plugin(inp)
    second = await resolve_plugin(inp)
    assert first.model_dump_json() == second.model_dump_json()


async def test_each_activity_emits_exactly_one_event(fake_event_log, vuln_capability):
    """AC-6 — one invocation produces one event in the canonical log.
    Doubling the emission (one in the Activity body, one in the called
    Supervisor function) is the silent-bug failure mode; the test catches
    by asserting the emitted-events tuple has length 1 after each call."""
    fake_event_log.reset()
    await resolve_plugin(...)
    assert fake_event_log.kinds_emitted() == ("PluginResolved",)
    fake_event_log.reset()
    await build_bundle(...)
    assert fake_event_log.kinds_emitted() == ("BundleBuilt",)
    fake_event_log.reset()
    await route(...)
    assert fake_event_log.kinds_emitted() == ("RouteDecided",)


def test_route_decision_round_trips_json_with_freshness_fields():
    """AC-3 — the discriminated union round-trips with decided_at and
    freshness_window preserved. The reason it matters: workflow resume reads
    the recorded decision from Temporal history, which is JSON; if the fields
    don't round-trip, S5-03's freshness check reads None and silently
    skips the descent."""
    decision = Recipe(
        recipe_id=RecipeId("..."),
        decided_at=datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc),
        freshness_window=timedelta(days=7),
    )
    payload = decision.model_dump_json()
    rebuilt = RouteDecisionAdapter.validate_json(payload)
    assert rebuilt == decision
```

### Refactor

- Each activity file's module docstring names the Phase-8 source function it wraps + the canonical-log event it emits + the task queue.
- `RouteDecision` lives in `codegenie.events.payloads` if more than one module references it (forward-declaration); otherwise it stays in `route.py`. Default to colocation in `route.py` and lift only when the second consumer lands.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/activities/resolve_plugin.py` | Activity body + input/output models. |
| `src/codegenie/durable/activities/build_bundle.py` | Activity body + input/output models + `BlobRef`-on-output. |
| `src/codegenie/durable/activities/route.py` | Activity body + `RouteDecision` sum type + Gap-3 fields. |
| `src/codegenie/durable/activities/__init__.py` | Three new explicit-import lines. |
| `src/codegenie/durable/activities/retry_policies.py` | Trim three names from `_EXPECTED_BUT_UNSHIPPED`. |
| `tests/unit/durable/activities/test_resolve_plugin.py` | Per-activity test file. |
| `tests/unit/durable/activities/test_build_bundle.py` | Per-activity test file. |
| `tests/unit/durable/activities/test_route.py` | Per-activity test file + freshness-fields round-trip. |
| `tests/unit/durable/activities/conftest.py` | Add `vuln_capability` fixture (queue=`vuln-remediation-node-npm`). |

## Out of scope

- The Phase-8 Supervisor logic itself — already shipped; this story wraps, not authors.
- The workflow body that dispatches these activities — S5-02.
- The freshness-window resume check — S5-03 (consumer).
- The `MultiPluginParentWorkflow` parent-child fanout — S5-04 (parent spawns N children; each child has its own `resolve_plugin` invocation).
- The G6 throughput bench — S8-04 (these activities' per-call latency feeds the canary; the canary itself is later).
- The Gap-1 route-activity overhead canary — S8-04. Today's story carries the Gap-3 fields; Gap-1's evidence lands in the bench.

## Notes for the implementer

### §1 — Why three Activities instead of one fat one

ADR-0010 names this: the Phase-8 Supervisor was designed to be the Temporal seam from day one (it has no `SutDigest` invariance constraint). Each node maps cleanly to one Activity, which gives per-node observability in `temporal-ui` and per-node retry policies. The asymmetric shape — three thin Activities for the Supervisor, one fat Activity for the SHERPA subgraph — is the right pattern in each context; collapsing it to one fat Activity here would lose the natural seam and inflate the smallest unit of retryable work to "the entire Supervisor + the entire SHERPA loop."

### §2 — `decided_at` and the determinism boundary

Workflows MUST NOT call `datetime.now()` — S1-07's fence enforces this. Activities CAN — they're the imperative shell. The pattern is: the Activity records `decided_at = datetime.now(timezone.utc)` once on first dispatch; Temporal's at-least-once delivery means the next dispatch (after worker SIGKILL) re-invokes the Activity — which MUST be idempotent on `AttemptId`. Idempotence here means: read the prior decision's `decided_at` from the canonical event log (`EventLog.read_by_attempt`) and reuse it instead of minting a fresh one. Without this discipline, every worker restart bumps `decided_at` to "now" and the S5-03 freshness check always sees fresh — Gap-3 silently re-opens.

### §3 — `build_bundle` bytes never cross the workflow

The Supervisor's `build_bundle` produces 50–150 KiB of context. That bundle CANNOT cross the workflow-to-activity-result wire — Temporal workflow history would balloon (G8 regression). The Activity body MUST call `write_blob_ref(...)` from the data layer (S3-05's function, NOT the Activity from S4-02) and return only the `BlobRef`. The subsequent `route` Activity takes the `BlobRef` as input; if it needs the bytes, it calls `resolve_blob_ref(...)` from the data layer.

Why the data-layer function instead of dispatching `write_blob_ref` as an Activity? Two reasons: (a) Activity-from-Activity dispatch is an anti-pattern; it doubles the Temporal history records, doubles the retry surface, and shifts the failure semantics. (b) The data-layer function is idempotent at the content-addressed level (the `BlobDigest` IS the content); a second call with identical bytes is `ON CONFLICT DO NOTHING`. The Activity wrapper would be redundant indirection.

### §4 — `RouteDecided` is batched, not synchronous

The five-variant `@critical_event` vocabulary (S1-03) is `{MergeOutcome, BudgetExhausted, TrustGateFailed, WorkflowTerminated, ChainTamperDetected}`. `RouteDecided` is *not* in that list. Per `phase-arch-design.md §Sequence diagrams Scenario 1`, the architect explicitly carries this correction ("RouteDecided (BATCHED, not synchronous — critic correction)") — an earlier draft inflated routing to synchronous and the critic destroyed it on p95 grounds. AC-7 reasserts the corrected posture.

### §5 — `RouteDecision` sum type vs string

`RouteDecision = Recipe | Rag | Llm` is a discriminated union; `Field(discriminator="kind")` on the union. NOT a string `kind` field — that's primitive-obsession (ADR-0008's design-pattern-discipline criticism). Adding a fourth route in Phase 10 (e.g., `Bypass` for pre-validated patches) is a fourth variant — one row in the union; the workflow body's `match` arm with `assert_never` makes the addition surface as a mypy error in every consumer until they handle it (Open/Closed at the file boundary).

### §6 — Don't import from Phase-8 internals into the type layer

If Phase-8 exposes `from codegenie.plugins.supervisor.types import PluginCandidate`, do NOT re-export that type from the Activity input. Instead, this Activity's `ResolvePluginInput` carries the *minimal* shape it needs (`repo_context_ref: BlobRef`, `task_class_id: TaskClassId`) and the Activity body translates to whatever Phase-8 wants internally. This keeps the Activity wire-shape stable against Phase-8 refactors.

### §7 — Gap-3 evidence lands here, decision is in S5-03

Today the freshness-window fields are *carried*; tomorrow (S5-03) they're *acted on*. Per the manifest's open-questions table, the default `freshness_window=7 days` is recorded but not yet ADR'd (the architect names ADR-0018 as the future home). When S5-03 implements the comparison, ADR-0018 lands in the same commit.
