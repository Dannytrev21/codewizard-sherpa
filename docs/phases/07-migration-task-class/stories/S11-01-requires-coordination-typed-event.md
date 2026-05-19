# Story S11-01 — `RequiresMultiPluginCoordination` typed event

**Step:** Step 11 — `Both` variant emission + `coordination-summary.yaml` writer + `codegenie list-coordination-candidates` CLI
**Status:** Ready
**Effort:** S
**Depends on:** S2-04 (`assemble_provenance` free function — the producer of `Both` and therefore the typed-event payload's upstream invariant)
**ADRs honored:** Phase 7 ADR-0001 (no `MultiPluginCoordinator`; `Both` emits evidence and stops), Phase 7 ADR-0017 (exit code 8 + `coordination-summary.yaml` + event into the spanning log), production ADR-0034 (Event sourcing canonical primitive — every event is a typed Pydantic record), production ADR-0042 (Phase 8's Planner is the consumer)

## Context

Phase 7 ADR-0001 is the keystone of Step 11: when `assemble_provenance` returns `Both`, Phase 7 does **NOT** coordinate. It emits typed evidence into the append-only spanning event log (`.codegenie/events/spanning/*.jsonl.zst`, established by Phases 6 / 6.5) and stops. ADR-0017 names exactly what that evidence is: a `RequiresMultiPluginCoordination` event with five fields — `workflow_id`, `app_record`, `base_record`, `summary_path`, `emitted_at` — plus the canonical `kind` discriminator that Phase 8's Planner will filter on.

This story lands ONE typed Pydantic model (under `src/codegenie/primitives/vuln_provenance/events.py`) that conforms to production ADR-0034's `_TypedEvent` base. It is the contract surface Phase 8 will project against, so every field is locked at design time: `extra="forbid"`, `frozen=True`, `schema_version: Literal["phase-7-0"] = "phase-7-0"` (the Gap-2 forward-compat hook — Phase 8 introduces `"phase-8-0"` when it lands and consumers branch on version). The story is small (S) and intentionally narrow: it ships the typed payload only. The writer (`emit_coordination` + `coordination-summary.yaml`) is S11-02; the CLI subcommand is S11-03; the exit-code-8 wiring is S11-04.

The load-bearing risk is field drift between this event and `Both.app_record` / `Both.base_record` (S1-03). The event payload **carries the same `AppKind` and `BaseKind` discriminated-union types** so Phase 8's Planner routes without re-running adapters. Renaming `app_record` → `application_record` or widening `AppKind` to `str` would force Phase 8 to migrate; this story pins both via Pydantic typing + the round-trip + `extra="forbid"` rejection tests.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §13` (lines 905–924) — full public interface of `RequiresMultiPluginCoordination` including the `_TypedEvent` base class, the five fields, and the `kind: Literal["requires_multi_plugin_coordination"]` discriminator string.
  - `../phase-arch-design.md §Data model` (lines 1005–1011) — class-shape repeated under "Contract — Spanning event variants Phase 7 ships."
  - `../phase-arch-design.md §Scenario C` (lines 455–486) — sequence diagram showing the event landing in the spanning log right before the CLI exits code 8.
  - `../phase-arch-design.md §Gap 2 (`coordination-summary.yaml` schema provisional)` — `schema_version: "phase-7-0"` forward-compat hook (pinned in S11-02; this story pins the *event* schema_version, not the YAML's).
- **Phase ADRs:**
  - `../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md §Consequences` — `RequiresMultiPluginCoordination` event variant ships in `src/codegenie/primitives/vuln_provenance/events.py` (typed Pydantic per ADR-0034); append-only spanning log.
  - `../ADRs/0017-both-provenance-exits-code-8-with-coordination-summary.md §Decision §1` — the event field set verbatim.
- **Production ADRs:**
  - `../../../production/adrs/0034-event-sourcing-canonical-primitive.md` — `_TypedEvent` base; every event is a frozen Pydantic record with `kind: Literal[...]` discriminator.
  - `../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md` — Phase 8's Planner is the consumer; this event is the contract surface.
- **Existing code:**
  - `src/codegenie/plugins/cache_gc.py:153` — existing reference to `codegenie.events.WorkflowSpanningEvent.event_type` (the existing spanning-event Literal-union — Phase 7 will extend this union additively in a downstream story or via discriminator-string-stable widening; this story focuses on the typed-event class itself, not the union wiring, which is consumer-side).
  - `src/codegenie/primitives/vuln_provenance/types.py` (lands in S1-03) — `Both`, `AppKind`, `BaseKind` discriminated unions; the event payload re-uses these types via `Both.app_record: AppKind`.
  - `src/codegenie/types/identifiers.py` (extended in S1-01) — `WorkflowId` newtype (already exists in Phase 3; reused here).

## Goal

Land `src/codegenie/primitives/vuln_provenance/events.py` with a single Pydantic v2 typed event `RequiresMultiPluginCoordination(_TypedEvent)` carrying `workflow_id: WorkflowId`, `app_record: AppKind`, `base_record: BaseKind`, `summary_path: Path`, `emitted_at: datetime`, `schema_version: Literal["phase-7-0"] = "phase-7-0"`, plus the `kind: Literal["requires_multi_plugin_coordination"] = "requires_multi_plugin_coordination"` discriminator — `frozen=True`, `extra="forbid"`, round-trippable through `model_dump_json()` / `model_validate_json(...)` with byte-identical recovery and rejecting any extra fields.

## Acceptance criteria

- [ ] **AC-1** `src/codegenie/primitives/vuln_provenance/events.py` exists and exports `RequiresMultiPluginCoordination` from `__all__`. Module docstring names ADR-0001 + ADR-0017 + ADR-0034 as the governing contracts.
- [ ] **AC-2** `RequiresMultiPluginCoordination` is a Pydantic v2 `BaseModel` subclass with `model_config = ConfigDict(frozen=True, extra="forbid")`. Inheriting from `_TypedEvent` is acceptable if `_TypedEvent` already carries the config; this story may introduce `_TypedEvent` as a private base in the same module if it does not yet exist project-wide.
- [ ] **AC-3 — Field set (locked).** Exactly six fields:
  - `kind: Literal["requires_multi_plugin_coordination"] = "requires_multi_plugin_coordination"` (default-value form, per the repo convention).
  - `workflow_id: WorkflowId` — from `codegenie.types.identifiers`.
  - `app_record: AppKind` — from `codegenie.primitives.vuln_provenance.types` (S1-03).
  - `base_record: BaseKind` — from `codegenie.primitives.vuln_provenance.types` (S1-03).
  - `summary_path: Path` — `pathlib.Path` carrying the location of the on-disk `coordination-summary.yaml` (the writer is S11-02).
  - `emitted_at: datetime` — `datetime.datetime` (timezone-aware; UTC enforced by `field_validator`).
  - `schema_version: Literal["phase-7-0"] = "phase-7-0"` (Gap-2 forward-compat hook — Phase 8 introduces `"phase-8-0"` if it needs to).
- [ ] **AC-4 — JSON round-trip.** `RequiresMultiPluginCoordination.model_validate_json(inst.model_dump_json()) == inst`. Round-trip preserves `app_record` and `base_record` as their concrete discriminated-union variant types (e.g., `AppDirect` round-trips to `AppDirect`, not generic `AppKind`).
- [ ] **AC-5 — `extra="forbid"` rejection.** `RequiresMultiPluginCoordination.model_validate({...valid payload..., "_oops": "x"})` raises `ValidationError`. Parametrized over at least two extra-field positions: top-level and nested-into-`app_record`.
- [ ] **AC-6 — `kind` discriminator is exactly pinned.** A direct equality test `inst.kind == "requires_multi_plugin_coordination"` (catches a `kind` → `tag` rename per the precedent in `tests/unit/indices/test_freshness.py`).
- [ ] **AC-7 — `schema_version` default value pinned.** `RequiresMultiPluginCoordination(workflow_id=..., app_record=..., base_record=..., summary_path=..., emitted_at=...).schema_version == "phase-7-0"` AND constructing with `schema_version="phase-8-0"` raises `ValidationError` (Literal constraint).
- [ ] **AC-8 — `emitted_at` timezone-aware.** Constructing with a naive `datetime` raises `ValidationError` (UTC-aware required); a `datetime.now(tz=timezone.utc)` instance constructs OK.
- [ ] **AC-9 — Frozen after construction.** `inst.workflow_id = ...` raises `ValidationError`. Parametrized across all six fields.
- [ ] **AC-10 — `__all__` is an exact set.** `set(events.__all__) == {"RequiresMultiPluginCoordination"}` (plus `_TypedEvent` if introduced as public; otherwise private, leading-underscore export-excluded).
- [ ] **AC-11 — Module purity (import allowlist).** AST source-scan of `events.py`; allowed import set is exactly `{__future__, typing, datetime, pathlib, pydantic, codegenie.types.identifiers, codegenie.primitives.vuln_provenance.types}`. Anything else fails.
- [ ] **AC-12 — No `model_construct` shortcut.** `"model_construct" not in Path(events.__file__).read_text()` (mirrors the Phase 3 module-purity discipline).
- [ ] **AC-13 — `mypy --strict src/codegenie/primitives/vuln_provenance/events.py` clean.**
- [ ] **AC-14 — `ruff check` + `ruff format --check` clean on touched files.**
- [ ] **AC-15 — `make lint-imports` green.** S1-06's primitive import-linter contract covers this module — no LLM SDK leakage; primitive may not import from `plugins/`.
- [ ] **AC-16 — TDD plan's red test exists, was committed in a failing state, is now green.**

## Implementation outline

1. Create `src/codegenie/primitives/vuln_provenance/events.py`. Module docstring names ADR-0001, ADR-0017, ADR-0034, and the field-rename-is-forbidden invariant (renaming any of the six fields breaks the Phase 8 Planner contract — call it out at top of file).
2. Define `_TypedEvent` (or import if it already exists project-wide; check via `grep "_TypedEvent" src/codegenie/`). If introducing locally as the canonical base, follow the production ADR-0034 shape: `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`, no other fields — `kind` is variant-specific.
3. Define `RequiresMultiPluginCoordination(_TypedEvent)`:
   - `kind: Literal["requires_multi_plugin_coordination"] = "requires_multi_plugin_coordination"`.
   - `workflow_id: WorkflowId`, `app_record: AppKind`, `base_record: BaseKind`, `summary_path: Path`, `emitted_at: datetime`, `schema_version: Literal["phase-7-0"] = "phase-7-0"`.
   - `field_validator("emitted_at")` rejecting naive datetimes (`tzinfo is None` → `ValueError`).
4. Pin `__all__` to `{"RequiresMultiPluginCoordination"}` (plus `"_TypedEvent"` if public).
5. Add `tests/unit/primitives/vuln_provenance/test_events.py` covering AC-3..AC-9 inclusive.
6. Add `tests/unit/primitives/vuln_provenance/test_events_purity.py` covering AC-11 + AC-12.
7. Run `mypy --strict src/codegenie/primitives/vuln_provenance/events.py` and `pytest tests/unit/primitives/vuln_provenance/test_events.py -v`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/primitives/vuln_provenance/test_events.py`

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from codegenie.primitives.vuln_provenance.events import RequiresMultiPluginCoordination
from codegenie.primitives.vuln_provenance.types import AppDirect, BaseImage
from codegenie.types.identifiers import (
    WorkflowId, CveId, PackageId, ImageDigest, LayerDigest,
)


def _valid_kwargs() -> dict:
    return dict(
        workflow_id=WorkflowId("wf-1"),
        app_record=AppDirect(
            cve_id=CveId("CVE-2026-0001"),
            package_id=PackageId("express@4.17.0"),
        ),
        base_record=BaseImage(
            image_digest=ImageDigest("sha256:" + "a" * 64),
            layer_digest=LayerDigest("sha256:" + "b" * 64),
            distro_pkg=...,  # whatever S1-02 DistroPackage shape is
            stage=...,
        ),
        summary_path=Path("/codegenie/coordination/wf-1.yaml"),
        emitted_at=datetime(2026, 5, 19, tzinfo=timezone.utc),
    )


def test_construct_round_trip():
    """AC-4 — JSON round-trip preserves concrete payload types."""
    inst = RequiresMultiPluginCoordination(**_valid_kwargs())
    decoded = RequiresMultiPluginCoordination.model_validate_json(inst.model_dump_json())
    assert decoded == inst
    assert type(decoded.app_record) is type(inst.app_record)
    assert type(decoded.base_record) is type(inst.base_record)


def test_kind_discriminator_pinned():
    """AC-6 — discriminator string is exactly 'requires_multi_plugin_coordination'."""
    inst = RequiresMultiPluginCoordination(**_valid_kwargs())
    assert inst.kind == "requires_multi_plugin_coordination"


def test_schema_version_default_phase_7_0():
    """AC-7 — schema_version defaults to 'phase-7-0' and rejects 'phase-8-0'."""
    inst = RequiresMultiPluginCoordination(**_valid_kwargs())
    assert inst.schema_version == "phase-7-0"
    with pytest.raises(ValidationError):
        RequiresMultiPluginCoordination(**_valid_kwargs(), schema_version="phase-8-0")


def test_extra_field_top_level_rejected():
    """AC-5 — top-level extra field rejected."""
    payload = RequiresMultiPluginCoordination(**_valid_kwargs()).model_dump()
    payload["_oops"] = "x"
    with pytest.raises(ValidationError):
        RequiresMultiPluginCoordination.model_validate(payload)


def test_emitted_at_naive_rejected():
    """AC-8 — naive datetime rejected; tz-aware accepted."""
    naive = datetime(2026, 5, 19)
    with pytest.raises(ValidationError):
        RequiresMultiPluginCoordination(**{**_valid_kwargs(), "emitted_at": naive})


@pytest.mark.parametrize("field", [
    "workflow_id", "app_record", "base_record",
    "summary_path", "emitted_at", "schema_version",
])
def test_frozen_after_construction(field):
    """AC-9 — every field is frozen."""
    inst = RequiresMultiPluginCoordination(**_valid_kwargs())
    with pytest.raises(ValidationError):
        setattr(inst, field, getattr(inst, field))
```

State why the red tests fail: `ModuleNotFoundError: codegenie.primitives.vuln_provenance.events` — the module does not exist yet.

### Green — minimal pass

Create `src/codegenie/primitives/vuln_provenance/events.py` with `_TypedEvent` base (frozen + extra=forbid) and `RequiresMultiPluginCoordination` carrying the six locked fields, the `kind` literal default, the `schema_version` literal default, and the `field_validator("emitted_at")` for tz-awareness. `__all__ = ("RequiresMultiPluginCoordination",)`.

### Refactor

- Add module docstring naming ADR-0001 / ADR-0017 / ADR-0034 and the field-rename-is-forbidden invariant.
- Verify `__all__` exact-set test passes; verify the AST source-scan and `model_construct` purity guards pass.
- Verify `mypy --strict` clean.
- Cross-link the variant docstring to the consumer (Phase 8 Planner per ADR-0042) so future readers know who reads this event.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/primitives/vuln_provenance/events.py` | NEW — typed `_TypedEvent` base + `RequiresMultiPluginCoordination` event class. |
| `tests/unit/primitives/vuln_provenance/__init__.py` | NEW (if missing) — test package marker. |
| `tests/unit/primitives/vuln_provenance/test_events.py` | NEW — construct, round-trip, discriminator pin, schema_version pin, extra-field rejection, naive-datetime rejection, frozen test. |
| `tests/unit/primitives/vuln_provenance/test_events_purity.py` | NEW — `__all__` exact-set; AST import allowlist; `model_construct` absence. |

## Out of scope

- **`emit_coordination` writer + `coordination-summary.yaml`** — S11-02.
- **`codegenie list-coordination-candidates` CLI** — S11-03.
- **Exit-code-8 wiring + orchestrator translation** — S11-04.
- **Phase 8 Planner projection of this event** — Phase 8.
- **`WorkflowSpanningEvent` Literal-union extension** — handled additively by consumer code (S11-02's writer); not this story's concern.
- **`coordination-summary.yaml` `schema_version` field** — distinct from the event's `schema_version`; pinned in S11-02. This story's `schema_version` is the event payload's, NOT the YAML's.

## Notes for the implementer

- **`_TypedEvent` introduction.** Before introducing `_TypedEvent` locally to this module, `grep -rn "_TypedEvent\|WorkflowSpanningEvent" src/codegenie/`. Phase 6 / 6.5's spanning-log infrastructure may already define a canonical typed-event base. If so, **import and inherit** rather than redeclare (CLAUDE.md Rule 11 — match conventions). If `_TypedEvent` is not yet a public symbol but `WorkflowSpanningEvent` exists as a Pydantic Literal-union, surface this in the attempt log and route through S11-02's writer to extend the union additively. Do not silently fork two typed-event bases.
- **Field renames are contract-breaking.** Phase 8's Planner reads `app_record` and `base_record` directly. Renaming either to (say) `app` / `base` or `application_record` / `base_image_record` forces Phase 8 to migrate — the round-trip + JSON-shape pin tests are the load-bearing protection. A future PR-reviewer who sees a one-byte field rename should reject it on contract grounds; this story's `extra="forbid"` plus discriminator-string-pin plus the AC-3 exact-name list make the contract visible.
- **`AppKind` and `BaseKind` are discriminated unions, not enum strings.** `Both.app_record: AppKind` (per S1-03 / arch §177–185) is `AppDirect | AppTransitive | AppVendored` (a discriminated union over the seven-variant `Provenance`'s app side). The event carries the **full record**, not just the kind string, so Phase 8 routes without re-running adapters. The round-trip test (AC-4) verifies concrete variant preservation — if you accidentally widen `app_record: AppKind` to `app_record: str`, the test fails because `decoded.app_record` would be a string, not an `AppDirect` instance.
- **`summary_path: Path`, not `str`.** The writer (S11-02) computes the absolute path `.codegenie/coordination/<workflow_id>.yaml` and passes it in. Carrying `Path` (not `str`) preserves type discipline; Pydantic v2 serializes `Path` to JSON as a string and decodes back to `Path` automatically. If the project has a `SandboxedPath` newtype (S4-01 in Phase 3), prefer `Path` here — `SandboxedPath` is for code that **writes** to the path; this event just **records** where the write went, and a later read may happen from outside the sandbox.
- **`emitted_at: datetime` UTC-aware.** A naive `datetime` is type-illegal at this seam — the `field_validator` raises `ValueError("emitted_at must be timezone-aware")`. The writer (S11-02) calls `datetime.now(tz=timezone.utc)`. CLI consumers (S11-03's `--since DATE`) parse with `datetime.fromisoformat(...)` which round-trips correctly through `model_dump_json`.
- **`schema_version: Literal["phase-7-0"]` is the Gap-2 forward-compat hook.** When Phase 8 lands and needs to extend the event payload (e.g., a `phase_8_planner_decision` field), Phase 8 ships a new event variant or adds a `Literal["phase-7-0", "phase-8-0"]` widening **plus** the new optional field. Existing reads branch on `event.schema_version == "phase-7-0"`. The Pydantic Literal here is what makes that branching tractable: the type system knows `schema_version` is a closed set.
- **Append-only spanning log discipline.** This story does NOT touch the writer. But the event is **shaped for append-only consumption** — every field is set at emit time; nothing is mutable; there is no `last_updated` field; there is no `state` field that a consumer would update. Phase 8's projector reads and emits child workflows; if a `Both` workflow recurs (same `workflow_id`), a new event is emitted, not the old one mutated. The `frozen=True` test (AC-9) protects this invariant at the type level.
- **Closest precedent to mirror.** `src/codegenie/indices/freshness.py` (Phase 2) and `src/codegenie/transforms/outcomes.py` (Phase 3) — both ship frozen Pydantic v2 models with `kind: Literal[...] = "..."` discriminator, `extra="forbid"`, parametrized round-trip + frozen + extra-rejection tests, AST module-purity scan, `__all__` exact-set. Match shape and test idiom.
- **The S11-02 writer will append this event** via the existing spanning-log API (`orch_ctx.event_log.append_spanning(event)` per arch §13). This story does not couple to that API — the event class is the contract; the writer is the consumer of this story's contract.
