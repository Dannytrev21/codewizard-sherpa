# Story S1-07 — `src/codegenie/audit/events.py` Pydantic event payload schemas + audit-event enum extension

**Step:** Step 1 — Plant the two ABCs, the four Phase 0/1/2 additive edits, and the foundations every Phase 3 component consumes
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0010

## Context

Phase 2 ADR-0012 established the rolling BLAKE3 audit chain (chain breaks are observability, not gather failure). Phase 3 adds 17 new event types — `cve.feed.synced`, `recipe.selected`, `transform.applied`, `gate.signal_escalate`, `cache.replay`, etc. — each of which is integrity-relevant and needs tamper-evidence. ADR-0010 commits the closed event vocabulary at v0.3.0: adding a new event type requires an ADR amendment.

This story plants two things in one place: (1) the Pydantic payload schema for each Phase-3 event type (so emitters write structured payloads, not free-form dicts, and readers — Phase 5 gates, Phase 11 PR notifier — can decode any event with a single schema), and (2) the one-line additive edit to `src/codegenie/audit_writer.py` that extends its `event_type` enum to include the new names. The malformed-event-drop discipline (`meta.event_validation_failure` appended, chain integrity preserved) is the load-bearing piece — without it, a buggy emitter can break the chain in a way Phase 2's chain-break observability event cannot distinguish from tampering.

## References — where to look

- **Architecture:** `../phase-arch-design.md §"Component design" #14 (Audit chain — Phase-3 event extensions)` — the canonical 17 event types + per-event payload fields.
- **Architecture:** `../phase-arch-design.md §"Data model" → Audit event payload extensions (Phase 3)` — the `AuditEvent` Literal extension; field set unchanged at the chain-head level.
- **Phase ADRs:** `../ADRs/0010-audit-chain-extension-cache-replay-event.md` — ADR-0010 — closed-enum vocabulary, `cache.replay` back-reference semantics, malformed-event-drop policy.
- **Phase ADRs:** `../ADRs/0005-single-sandbox-profile-test-execution-overlay-signal-escalate.md` — ADR-0005 — `gate.signal_escalate` payload semantics.
- **Phase ADRs:** `../ADRs/0007-lockfile-policy-scanner-graded-allow-policy-violations.md` — ADR-0007 — `lockfile.scanned`, `lockfile.policy_violation`, `escalation.policy_violation` payloads.
- **Phase ADRs:** `../ADRs/0008-cve-feed-integrity-content-hash-best-effort-signature-graded-staleness.md` — ADR-0008 — `cve.feed.synced`, `cve.feed.signature_check` payloads.
- **Phase ADRs:** `../ADRs/0009-cve-retraction-probe-evidence-stale-marker.md` — ADR-0009 — `cve.retraction.detected`, `evidence_stale.marked` payloads.
- **Phase 2 ADRs:** `../../02-context-gather-layers-b-g/ADRs/0012-audit-chain-blake3-rolling-head.md` — chain-head model this story extends.
- **Source design:** `../final-design.md §"Trust & safety goals" #15` — closed event vocabulary commitment.
- **Existing code:** `src/codegenie/audit_writer.py` (Phase 0 + Phase 2 extensions) — the `event_type` enum site this story extends by one line.

## Goal

Land `src/codegenie/audit/events.py` with one Pydantic payload schema per Phase-3 event type (17 schemas + the `meta.event_validation_failure` and `meta.unexpected_exception` types), make a one-line additive edit to `src/codegenie/audit_writer.py`'s `event_type` enum to include the new names, and prove (a) every payload schema validates a happy-path example, (b) a malformed event is dropped and `meta.event_validation_failure` is appended in its place, (c) the audit-chain head still advances.

## Acceptance criteria

- [ ] `src/codegenie/audit/events.py` (new module) defines a Pydantic model per Phase-3 event type. All frozen, `extra="forbid"`. Models named e.g. `CveFeedSyncedPayload`, `RecipeSelectedPayload`, `RecipeEngineInvokedPayload`, `TransformAppliedPayload`, `LockfileScannedPayload`, `LockfilePolicyViolationPayload`, `NpmInstallRunPayload`, `TestsExecutedPayload`, `GateFailedPayload`, `GateSignalEscalatePayload`, `EvidenceStaleMarkedPayload`, `BranchCreatedPayload`, `BranchRefusedDirtyTreePayload`, `BranchRefusedExistsPayload`, `CveFeedSignatureCheckPayload`, `CveRetractionDetectedPayload`, `CacheReplayPayload`, `MetaUnexpectedExceptionPayload`, `MetaEventValidationFailurePayload`.
- [ ] Each payload schema has the fields listed in `phase-arch-design.md §"Component design" #14` (e.g., `CveFeedSyncedPayload` has `source`, `snapshot_sha256`, `record_count`, `fetched_at`; `RecipeSelectedPayload` has `recipe_id: str | None`, `reason: Literal[<six values>]`, `diagnostics: dict`; `CacheReplayPayload` has `cache_key`, `original_chain_head_blake3`, `original_run_id`).
- [ ] `src/codegenie/audit/events.py` exports `EVENT_TYPE_TO_PAYLOAD: dict[str, type[BaseModel]]` mapping each event-type string (e.g., `"cve.feed.synced"`) to its payload class — a single source of truth that readers (Phase 5, Phase 11) consume.
- [ ] `src/codegenie/audit_writer.py` `event_type` `Literal[...]` (or equivalent enum) extends additively to include all 17 Phase-3 event types + `meta.unexpected_exception` + `meta.event_validation_failure`. No Phase 0/2 entries are reordered or removed.
- [ ] `audit_writer.write_event(event_type, payload)` validates `payload` against `EVENT_TYPE_TO_PAYLOAD[event_type]`. On `ValidationError`: log to stderr; **drop** the malformed event; append a `meta.event_validation_failure` event with payload `{"intended_event_type": <str>, "validation_error": <str>}`; advance the chain head normally.
- [ ] `tests/unit/audit/test_events_phase3.py` covers (a) every Phase-3 event type has a payload schema in `EVENT_TYPE_TO_PAYLOAD`, (b) a happy-path payload per event-type round-trips, (c) malformed payload → `meta.event_validation_failure` appended + chain head advanced + original (malformed) event not in the log.
- [ ] `tests/unit/audit/test_audit_writer_enum_extension.py` asserts (a) all 17 + 2 new event types are accepted by `audit_writer.write_event`, (b) every Phase 0/2 event type from prior tests is still accepted (regression guard).
- [ ] No edits to the BLAKE3 chain-head computation logic — Phase 2 ADR-0012's chain stays byte-identical. (`cache.replay` references the original chain head in its payload, but the chain-head advance is unaffected.)
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/audit/ src/codegenie/audit_writer.py tests/unit/audit/` pass.

## Implementation outline

1. Read `src/codegenie/audit_writer.py` end-to-end — Rule 8. Identify the `event_type` enum site, the chain-head computation, and the existing payload-validation hook (Phase 2 may already have a `dict` payload; this story tightens to typed Pydantic per event-type).
2. Create `src/codegenie/audit/__init__.py` (if not already present) and `src/codegenie/audit/events.py`.
3. Write `tests/unit/audit/test_events_phase3.py` red — `from codegenie.audit.events import EVENT_TYPE_TO_PAYLOAD` ImportErrors.
4. Implement each payload schema. Use `Literal` for closed enums (e.g., `RecipeSelectedPayload.reason: Literal["matched","no_engine",...]` mirrors S1-04's `RecipeSelection.reason`). Use `datetime` for timestamps. Use `int` for counts and `str` for hashes/run-ids.
5. Build `EVENT_TYPE_TO_PAYLOAD` as a module-level dict at the bottom of `events.py`. Assert at import time that every key is unique and every value is a `BaseModel` subclass (sanity check; cheap).
6. Edit `src/codegenie/audit_writer.py`:
   - Extend the `event_type` `Literal[...]` enum additively to include the 17 + 2 new names.
   - In `write_event`, before computing the chain-head, look up the payload schema via `EVENT_TYPE_TO_PAYLOAD.get(event_type)`. If found, attempt `model_validate(payload)`. On success: proceed. On failure: log + drop + emit `meta.event_validation_failure` instead.
7. Write `tests/unit/audit/test_audit_writer_enum_extension.py` covering both directions (accepts new + accepts prior).
8. Run `pytest tests/unit/audit/`; green.

## TDD plan — red / green / refactor

### Red — failing test first

Test file paths: `tests/unit/audit/test_events_phase3.py`, `tests/unit/audit/test_audit_writer_enum_extension.py`.

```python
# tests/unit/audit/test_events_phase3.py
from codegenie.audit.events import EVENT_TYPE_TO_PAYLOAD
from codegenie.audit_writer import write_event
import codegenie.logging as L

PHASE3_EVENT_TYPES = {
    L.CVE_FEED_SYNCED, L.CVE_FEED_SIGNATURE_CHECK, L.CVE_RETRACTION_DETECTED,
    L.EVIDENCE_STALE_MARKED, L.RECIPE_SELECTED, L.RECIPE_ENGINE_INVOKED,
    L.TRANSFORM_APPLIED, L.LOCKFILE_SCANNED, L.LOCKFILE_POLICY_VIOLATION,
    L.NPM_INSTALL_RUN, L.TESTS_EXECUTED, L.GATE_FAILED, L.GATE_SIGNAL_ESCALATE,
    L.BRANCH_CREATED, L.BRANCH_REFUSED_DIRTY_TREE, L.BRANCH_REFUSED_EXISTS,
    L.CACHE_REPLAY,
}

def test_every_phase3_event_type_has_a_payload_schema():
    for evt in PHASE3_EVENT_TYPES:
        assert evt in EVENT_TYPE_TO_PAYLOAD, f"missing schema for {evt}"

def test_happy_path_payload_per_event_round_trips():
    # one minimal valid payload per event; construct + dump + validate
    ...

def test_malformed_payload_appends_event_validation_failure_and_drops_original(tmp_path):
    # write_event("cve.feed.synced", {"bogus": True})
    # expected: meta.event_validation_failure appended; original event absent;
    #           chain head advanced exactly once
    ...
```

```python
# tests/unit/audit/test_audit_writer_enum_extension.py
from codegenie.audit_writer import write_event
import codegenie.logging as L

PRIOR_EVENT_TYPES = {
    # Phase 0/2 events — pin verbatim so silent removal fails CI
    "gather.started", "probe.run", "probe.cache_hit", "audit.chain_head_advanced",
    ...
}

def test_prior_phase_event_types_still_accepted(tmp_path):
    for evt in PRIOR_EVENT_TYPES:
        # construct a minimal valid prior-phase payload; write_event must accept
        ...

def test_phase3_event_types_accepted_after_extension(tmp_path):
    for evt in PHASE3_EVENT_TYPES:
        ...
```

Run; commit red.

### Green — make it pass

- Implement each payload schema in `events.py`. Field names match `phase-arch-design.md §"Component design" #14` and the per-event ADRs.
- Wire `EVENT_TYPE_TO_PAYLOAD` dict at module bottom; one entry per event-type.
- Extend `audit_writer.py`'s enum by appending to the `Literal[...]` tuple. Wire the lookup-and-validate hook in `write_event`.
- Make the malformed-event-drop path explicit: catch `ValidationError`, log to stderr, write `meta.event_validation_failure` with the captured error string + original event-type name, advance the chain head.

### Refactor — clean up

- Module docstring on `events.py`: cite ADR-0010 + Phase 2 ADR-0012; explicitly call out the malformed-event-drop policy.
- One-line comment beside the `audit_writer.py` enum extension: `# Phase 3 — ADR-0010 — closed event vocabulary v0.3.0; adding an entry requires an ADR amendment.`
- `__all__` on `events.py` lists every payload class + the `EVENT_TYPE_TO_PAYLOAD` dict.
- `mypy --strict` clean across the audit subpackage.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/audit/__init__.py` | Package marker (create if absent) |
| `src/codegenie/audit/events.py` | New module — 19 payload schemas + `EVENT_TYPE_TO_PAYLOAD` dict |
| `src/codegenie/audit_writer.py` | Extend `event_type` enum additively; wire payload-validation hook with malformed-drop |
| `tests/unit/audit/__init__.py` | pytest package marker |
| `tests/unit/audit/test_events_phase3.py` | Per-event schema + malformed-drop tests |
| `tests/unit/audit/test_audit_writer_enum_extension.py` | Regression guard for prior + new event types |

## Out of scope

- **`escalation.policy_violation` payload + emitter** — that event ships with the `LockfilePolicyScanner` exit-7 path in Step 4. This story plants the typed shape if it appears in ADR-0010's table; otherwise it lands in S4-*. (Per `phase-arch-design.md §"Component design" #14` the event is `escalation.policy_violation` and is part of the ADR-0010 set — include the payload schema here.)
- **Audit-chain-break observability event** — Phase 2 ADR-0012 owns this; not edited.
- **Emitting any of these events from production code** — that wiring lives in the consuming stories (S2-07 emits `cve.feed.*`; S3-* emits `recipe.*`, `npm.install.run`; S4-* emits `gate.*`; S5-* emits `branch.*` + `transform.applied`; the resolver cache emits `cache.replay` in Step 3).
- **`meta.unexpected_exception` raise-and-emit handler** — the top-level CLI exception handler that emits this event lives in `cli.py` (Step 5). This story plants only the payload schema.
- **Cache-replay back-reference logic** — the lockfile cache writes `original_chain_head_blake3` into entries (Step 3); this story plants only the `CacheReplayPayload` shape.

## Notes for the implementer

- **Closed enum discipline.** Resist adding an 18th event type "while we're here." ADR-0010 explicitly closes the set at v0.3.0; any addition requires an ADR amendment in the same PR. The test `test_every_phase3_event_type_has_a_payload_schema` reads the canonical list from `codegenie.logging` constants (S1-01) — if S1-01's constants drift, this test catches it.
- **Malformed-event-drop is the load-bearing safety net.** Without it, a buggy emitter (e.g., a S5-04 implementation that forgets to pass `head_sha` to `BranchCreatedPayload`) breaks the chain in a way that looks identical to tampering. The drop policy keeps the chain forward-progress invariant and surfaces the bug via `meta.event_validation_failure`. Document this prominently in `audit/events.py`'s module docstring.
- **Use `Literal` types where the ADR specifies closed-enum payload values.** `RecipeSelectedPayload.reason`, `CveFeedSignatureCheckPayload.signature_status: Literal["verified","unsupported","failed"]`, `NpmInstallRunPayload.mode: Literal["package_lock_only","ci"]`. This makes the payload schema self-documenting and prevents typos from emitters.
- **`datetime` over `str` for timestamps.** Pydantic v2 serializes `datetime` to ISO-8601 in `model_dump(mode="json")` by default; readers parse back. Mixed `str`/`datetime` in payloads is a maintenance trap.
- **`Path` over `str` for file paths.** Same rationale; Pydantic stringifies on dump and re-parses on validate.
- **The 19 schemas should fit in ~300 lines.** Keep each schema 3–8 fields; resist the urge to add description fields, version fields, or correlation IDs not specified by the ADRs. Phase 5/11 readers depend on the closed shape.
- **`EVENT_TYPE_TO_PAYLOAD` is the single source of truth.** Phase 5's gate machinery, Phase 11's PR notifier, and any future audit dashboard read this dict to dispatch by event type. Do not duplicate the mapping in `audit_writer.py` — import from `events.py`.
- **Phase 2 ADR-0012's chain-head computation is unchanged.** Do not edit the BLAKE3 update logic. The chain head advances over **each** event written (including `meta.event_validation_failure`); the back-reference in `CacheReplayPayload.original_chain_head_blake3` is a payload field, not a chain modification.
- Do not import `pydantic.v1`. Use pydantic v2.
