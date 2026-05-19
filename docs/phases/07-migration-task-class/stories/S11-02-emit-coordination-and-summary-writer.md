# Story S11-02 — `emit_coordination` writer + `coordination-summary.yaml` schema + `_index.tsv`

**Step:** Step 11 — `Both` variant emission + `coordination-summary.yaml` writer + `codegenie list-coordination-candidates` CLI
**Status:** Ready
**Effort:** M
**Depends on:** S11-01 (`RequiresMultiPluginCoordination` typed event — the payload this writer emits)
**ADRs honored:** Phase 7 ADR-0001 (no `MultiPluginCoordinator`; this story's writer is the entire Phase 7 "what happens on `Both`" surface), Phase 7 ADR-0017 (`coordination-summary.yaml` schema + `_index.tsv` rollup; `extra="forbid"`; `schema_version: "phase-7-0"`), production ADR-0034 (event sourcing — append-only spanning log)

## Context

S11-01 ships the typed event. This story is the **writer** — the function that, when `assemble_provenance` returns `Both`, appends the event to the spanning log + writes the operator-readable `coordination-summary.yaml` + appends a row to `.codegenie/coordination/_index.tsv` (the Gap-5 rollup that makes pending events visible at portfolio scale before Phase 13.5 ships an operator portal).

Three contracts land in one story because they are deliberately co-located: the writer's signature (`emit_coordination(orch_ctx, both: Both) -> None`), the YAML's Pydantic schema (with its own `schema_version: "phase-7-0"`, separate from the event's — different reader, different forward-compat axis), and the `_index.tsv` row format. Splitting them invites schema drift between the on-disk YAML and the operator-readable index.

Phase 7 ADR-0017 §Decision §2 pins the **provisional** YAML field set: `workflow_id`, `cve_id`, `app` (kind + package + manifest_path), `base` (kind + image_digest + distro_pkg), `proposed_plugin_routes`, `awaiting: phase_8_planner`, `schema_version: "phase-7-0"`. This story is the "first implementation story" the ADR defers the exact schema to (Open Question §1) — so the schema lands here, exactly, with `extra="forbid"` and a golden fixture (`tests/golden/coordination-summary/both-app-direct-plus-base-image.yaml`) that locks the operator-readable shape.

The writer returns `Applicability.PendingCoordination` so the orchestrator can translate that to exit code 8 (wired in S11-04). The `_index.tsv` is the Gap-5 mitigation: with no Phase 8 Planner for ~3 months, `Both` events accumulate unread; the TSV's append-only row-per-workflow shape lets `codegenie list-coordination-candidates` (S11-03) and ad-hoc `awk` / `sort` pipelines surface them without parsing zstd-compressed JSONL.

Two failure modes the story explicitly defends against: (1) **partial write** — the spanning-log append and the YAML write are NOT atomic across processes; the writer orders them so a crash mid-write leaves the spanning log as source-of-truth (per production ADR-0034) and the YAML as a derived artifact that can be rebuilt by Phase 8; (2) **duplicate `_index.tsv` rows** — `WorkflowId` is per-invocation per ADR-0017 §Tradeoffs, but a re-run with the same `workflow_id` still appends (the TSV is a log, not a state file). Operators can `sort -u -k1` the TSV if they want unique-by-workflow rollups.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §13` (lines 905–948) — `emit_coordination` signature, `coordination-summary.yaml` shape (the provisional spec this story pins), `_index.tsv` mention.
  - `../phase-arch-design.md §Scenarios §Scenario C` (lines 455–486) — sequence diagram: orchestrator calls `emit_coordination` → spanning-log append → YAML write → exit code 8.
  - `../phase-arch-design.md §Gap 5 (events accumulating unread)` — `_index.tsv` is the named mitigation for the pre-Phase-13.5 window.
  - `../phase-arch-design.md §Gap 2 (`coordination-summary.yaml` schema provisional)` — `schema_version: "phase-7-0"` is the forward-compat hook; this story pins it for the YAML.
- **Phase ADRs:**
  - `../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md §Consequences` — `codegenie list-coordination-candidates` ships as a tiny operator-facing CLI subcommand; the `_index.tsv` rollup is the per-event index.
  - `../ADRs/0017-both-provenance-exits-code-8-with-coordination-summary.md §Decision §2` — full YAML field set + `extra="forbid"` + `schema_version: "phase-7-0"` + `<workflow_id>.yaml` filename pattern.
- **Production ADRs:**
  - `../../../production/adrs/0034-event-sourcing-canonical-primitive.md` — append-only spanning log; the YAML is a **projection**, not the source of truth.
  - `../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md` — Phase 8 reads the spanning log, not the YAML; the YAML is operator-facing only.
- **Existing code:**
  - `src/codegenie/primitives/vuln_provenance/events.py` (S11-01) — `RequiresMultiPluginCoordination` typed event.
  - `src/codegenie/primitives/vuln_provenance/types.py` (S1-03) — `Both` discriminated-union variant.
  - `src/codegenie/transforms/outcomes.py` (S1-03 of Phase 3) — `Applicability` discriminated union; this story **adds** `PendingCoordination` variant additively.
  - `src/codegenie/plugins/cache_gc.py:153` — existing reference to the spanning-log API surface (`WorkflowSpanningEvent.event_type`); use the existing append-spanning seam, do not invent a new one.

## Goal

Land `plugins/distroless-migration--node--npm/subgraph/api.py` with an `emit_coordination(orch_ctx, both: Both) -> Applicability.PendingCoordination` writer that (a) constructs a `RequiresMultiPluginCoordination` event from `both`, (b) appends it to the spanning event log via the existing `orch_ctx.event_log.append_spanning(...)` seam, (c) writes `coordination-summary.yaml` to `.codegenie/coordination/<workflow_id>.yaml` against a frozen Pydantic schema with `extra="forbid"` and `schema_version: "phase-7-0"`, (d) appends one row to `.codegenie/coordination/_index.tsv`, and (e) returns `Applicability.PendingCoordination`. Plus the golden file `tests/golden/coordination-summary/both-app-direct-plus-base-image.yaml` locking the YAML's operator-readable shape.

## Acceptance criteria

- [ ] **AC-1 — Module landing.** `plugins/distroless-migration--node--npm/subgraph/__init__.py` and `plugins/distroless-migration--node--npm/subgraph/api.py` exist. The `api.py` module exports `emit_coordination` from `__all__`.
- [ ] **AC-2 — Signature locked.** `def emit_coordination(orch_ctx: OrchestratorContext, both: Both) -> PendingCoordination: ...`. Returns the typed `Applicability.PendingCoordination` variant (added additively to `codegenie.transforms.outcomes.Applicability` per ADR-0001 / ADR-0017). Importing the function from the plugin tree is byte-stable (the loader explicit-import in S8-03 wires this).
- [ ] **AC-3 — `Applicability.PendingCoordination` variant added additively.** `Applicability = Applies | NotApplies | PendingCoordination` (discriminated union widened, NOT renamed). `PendingCoordination(kind="pending_coordination", workflow_id: WorkflowId, summary_path: Path)`. Existing `Applies` / `NotApplies` round-trip + discriminator-string pins remain green (the Phase 3 `test_outcomes.py` suite must not regress).
- [ ] **AC-4 — `coordination-summary.yaml` Pydantic schema.** A `CoordinationSummary(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` and these exact fields (locking Open Question §1):
  - `schema_version: Literal["phase-7-0"] = "phase-7-0"`.
  - `workflow_id: WorkflowId`.
  - `cve_id: CveId`.
  - `app: AppSummary` — frozen nested model with `kind: AppKindLiteral` (`Literal["app_direct", "app_transitive", "app_vendored"]`), `package: PackageId`, `manifest_path: str`.
  - `base: BaseSummary` — frozen nested model with `kind: BaseKindLiteral` (`Literal["base_image", "runtime_bundled"]`), `image_digest: ImageDigest`, `distro_pkg: DistroPackage`.
  - `proposed_plugin_routes: list[PluginId]` — ordered list of candidate plugin IDs (e.g., `["vulnerability-remediation--node--npm", "distroless-migration--node--npm"]`). Phase 8's Planner re-derives; this is operator-readable hinting only.
  - `awaiting: Literal["phase_8_planner"] = "phase_8_planner"`.
  - `emitted_at: datetime` (UTC tz-aware, same `field_validator` discipline as S11-01).
- [ ] **AC-5 — YAML serialization.** `CoordinationSummary` serializes to YAML via `yaml.safe_dump(model.model_dump(mode="json"), sort_keys=False)` (key order preserved per schema declaration); round-trips cleanly through `yaml.safe_load(text)` → `CoordinationSummary.model_validate(...)`.
- [ ] **AC-6 — Write target path.** YAML lands at `<orch_ctx.codegenie_root>/coordination/<workflow_id>.yaml`. The parent directory is created if missing (`mkdir(parents=True, exist_ok=True)`).
- [ ] **AC-7 — Spanning-log append.** `emit_coordination` calls `orch_ctx.event_log.append_spanning(event)` exactly once with the `RequiresMultiPluginCoordination` event. Test mocks `event_log` and asserts the call.
- [ ] **AC-8 — `_index.tsv` append-on-write row.** `<orch_ctx.codegenie_root>/coordination/_index.tsv` is appended one tab-separated row: `<emitted_at_iso>\t<workflow_id>\t<cve_id>\t<app_kind>\t<base_kind>\t<summary_path>`. The first write creates the file with a header row `# emitted_at\tworkflow_id\tcve_id\tapp_kind\tbase_kind\tsummary_path`; subsequent writes append only the data row. No locking is taken (single-orchestrator-process invariant per Phase 5); test pins the format.
- [ ] **AC-9 — Write order: spanning-log first, YAML second, TSV third.** If the spanning-log append raises, the YAML and TSV are not written (the spanning log is source-of-truth per ADR-0034). If the YAML write raises, the TSV row is not appended. Test asserts via an exception-injected `event_log` mock and a `Path` mock.
- [ ] **AC-10 — `extra="forbid"` on every nested model.** `CoordinationSummary`, `AppSummary`, `BaseSummary` all reject extra fields. Parametrized test covers extra at top-level, nested-in-`app`, nested-in-`base`.
- [ ] **AC-11 — `schema_version` literal pinned.** Constructing `CoordinationSummary(..., schema_version="phase-8-0")` raises `ValidationError`. The default (no kwarg) is `"phase-7-0"`.
- [ ] **AC-12 — Golden file equality.** `tests/golden/coordination-summary/both-app-direct-plus-base-image.yaml` exists and serializing a fixed `CoordinationSummary` produces byte-identical YAML (LF line endings, trailing newline). The fixture covers the canonical `Both(AppDirect, BaseImage)` case.
- [ ] **AC-13 — Return value.** `emit_coordination(...)` returns a `PendingCoordination(workflow_id=..., summary_path=...)`. Type-narrowing test: `match` over `Applicability` with all three arms + `assert_never` is mypy-clean.
- [ ] **AC-14 — Property test: every `Both` produces exactly one event + one YAML + one TSV row.** `tests/property/vuln_provenance/test_both_always_emits_coordination.py` (per ADR-0001 §Consequences) — Hypothesis generates 50 `Both` instances; for each, run `emit_coordination` against a fake `event_log` + `tmp_path`; assert spanning log has exactly one event with `kind == "requires_multi_plugin_coordination"`; YAML at the expected path; one TSV data row.
- [ ] **AC-15 — Writer is in the plugin tree, not core.** `plugins/distroless-migration--node--npm/subgraph/api.py`, NOT `src/codegenie/`. The fence `tests/fence/test_provenance_primitive_in_plugin_directory.py` (S5-02) covers this; this story adds one assertion to that fence (`emit_coordination` resolves to the plugin path).
- [ ] **AC-16 — `mypy --strict` clean on the writer + the new YAML schema models.**
- [ ] **AC-17 — `ruff check` + `ruff format --check` clean.**
- [ ] **AC-18 — `make lint-imports` green.** The plugin tree may not import LLM SDKs; the primitive may not import from `plugins/` (S5-03's contract).
- [ ] **AC-19 — Phase 3–6.5 regression suite green** (`make check`); `bench/vuln-remediation/` cassette replay byte-equal (cost-ledger ε ≤ $0.01).
- [ ] **AC-20 — TDD plan's red test (the AC-7 spanning-log-append assertion) exists, was committed in a failing state, is now green.**

## Implementation outline

1. **Add `PendingCoordination` to `Applicability`.** Edit `src/codegenie/transforms/outcomes.py` additively (the ADR-0001 contract-snapshot test in Phase 3 must continue to pass — verify the snapshot list permits new variants additively; if it does not, add a Phase 7 ADR-0017 §Consequences-justified expansion line). `PendingCoordination(kind="pending_coordination", workflow_id: WorkflowId, summary_path: Path)`. Update the umbrella `Applicability = Annotated[Applies | NotApplies | PendingCoordination, Field(discriminator="kind")]`. Update `tests/unit/transforms/test_outcomes.py` parametrizations to include the new variant (round-trip, extra-reject, frozen, discriminator-string pin, JSON-shape pin, exhaustiveness via `match` + `assert_never`).
2. **Create `plugins/distroless-migration--node--npm/subgraph/{__init__.py, api.py}`.** Module docstring on `api.py` names ADR-0001 + ADR-0017 + ADR-0034 and the "Phase 7 produces evidence, Phase 8 owns sequencing" line.
3. **Create `plugins/distroless-migration--node--npm/subgraph/_yaml_schema.py`** with `CoordinationSummary`, `AppSummary`, `BaseSummary` Pydantic models per AC-4. Every model `frozen=True, extra="forbid"`; `schema_version: Literal["phase-7-0"] = "phase-7-0"`; `field_validator("emitted_at")` for tz-awareness; `model_config = ConfigDict(frozen=True, extra="forbid")` on each.
4. **Implement `emit_coordination(orch_ctx, both)`** in `api.py`:
   ```python
   def emit_coordination(orch_ctx: OrchestratorContext, both: Both) -> PendingCoordination:
       workflow_id = orch_ctx.workflow_id
       summary_dir = orch_ctx.codegenie_root / "coordination"
       summary_dir.mkdir(parents=True, exist_ok=True)
       summary_path = summary_dir / f"{workflow_id}.yaml"
       emitted_at = datetime.now(tz=timezone.utc)

       event = RequiresMultiPluginCoordination(
           workflow_id=workflow_id,
           app_record=both.app_record,
           base_record=both.base_record,
           summary_path=summary_path,
           emitted_at=emitted_at,
       )
       # Step 1: spanning log is source of truth. If this raises, abort.
       orch_ctx.event_log.append_spanning(event)

       # Step 2: write derived YAML projection.
       summary = _build_summary(both, workflow_id, summary_path, emitted_at, orch_ctx)
       summary_path.write_text(_dump_yaml(summary))

       # Step 3: append TSV row (Gap 5 rollup).
       _append_index_row(summary_dir / "_index.tsv", summary)

       return PendingCoordination(workflow_id=workflow_id, summary_path=summary_path)
   ```
5. **Build helpers** (`_build_summary`, `_dump_yaml`, `_append_index_row`) as pure module-level functions. `_append_index_row` checks if the TSV exists; if not, writes the header line + data row; if yes, appends only the data row (atomic single-line append via `open(path, "a")`).
6. **Golden fixture.** `tests/golden/coordination-summary/both-app-direct-plus-base-image.yaml` — hand-write the expected YAML for a canonical `Both(AppDirect(CVE-2026-0001, express@4.17.0), BaseImage(sha256:..., sha256:..., DistroPackage(alpine, openssl, 1.1.1k), <stage>))` instance with `workflow_id="wf-test-1"`, `emitted_at="2026-05-19T00:00:00+00:00"`. The test renders the same instance and asserts byte-equality.
7. **Tests** under `tests/unit/plugins/distroless_migration_node_npm/`:
   - `test_emit_coordination.py` — covers AC-6..AC-9, AC-13.
   - `test_coordination_summary_schema.py` — covers AC-4, AC-10, AC-11.
   - `test_coordination_summary_golden.py` — covers AC-12.
   - `test_index_tsv_append.py` — covers AC-8 (header-creation + data-row append + multi-row sequencing).
8. **Property test.** `tests/property/vuln_provenance/test_both_always_emits_coordination.py` — covers AC-14 (Hypothesis-driven invariant per ADR-0001 §Consequences).
9. **Run `make check`** + the `bench/vuln-remediation/` cassette replay; assert cost-ledger byte-equality.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/plugins/distroless_migration_node_npm/test_emit_coordination.py`

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from codegenie.primitives.vuln_provenance.events import RequiresMultiPluginCoordination
from codegenie.primitives.vuln_provenance.types import AppDirect, BaseImage, Both
from codegenie.transforms.outcomes import PendingCoordination
from codegenie.types.identifiers import WorkflowId, CveId, PackageId, ImageDigest, LayerDigest

from plugins.distroless_migration_node_npm.subgraph.api import emit_coordination


def _make_both() -> Both:
    return Both(
        app_record=AppDirect(cve_id=CveId("CVE-2026-0001"), package_id=PackageId("express@4.17.0")),
        base_record=BaseImage(
            image_digest=ImageDigest("sha256:" + "a" * 64),
            layer_digest=LayerDigest("sha256:" + "b" * 64),
            distro_pkg=...,
            stage=...,
        ),
    )


def _make_ctx(tmp_path: Path) -> MagicMock:
    ctx = MagicMock()
    ctx.workflow_id = WorkflowId("wf-test-1")
    ctx.codegenie_root = tmp_path
    ctx.event_log = MagicMock()
    return ctx


def test_emit_coordination_returns_pending_coordination(tmp_path):
    """AC-13 — return value carries workflow_id + summary_path."""
    ctx = _make_ctx(tmp_path)
    result = emit_coordination(ctx, _make_both())
    assert isinstance(result, PendingCoordination)
    assert result.workflow_id == WorkflowId("wf-test-1")
    assert result.summary_path == tmp_path / "coordination" / "wf-test-1.yaml"


def test_emit_coordination_appends_spanning_event(tmp_path):
    """AC-7 — exactly one append_spanning call with the typed event."""
    ctx = _make_ctx(tmp_path)
    emit_coordination(ctx, _make_both())
    assert ctx.event_log.append_spanning.call_count == 1
    event = ctx.event_log.append_spanning.call_args.args[0]
    assert isinstance(event, RequiresMultiPluginCoordination)
    assert event.kind == "requires_multi_plugin_coordination"
    assert event.workflow_id == WorkflowId("wf-test-1")


def test_emit_coordination_writes_yaml(tmp_path):
    """AC-6 — YAML lands at <codegenie_root>/coordination/<workflow_id>.yaml."""
    ctx = _make_ctx(tmp_path)
    emit_coordination(ctx, _make_both())
    yaml_path = tmp_path / "coordination" / "wf-test-1.yaml"
    assert yaml_path.exists()
    loaded = yaml.safe_load(yaml_path.read_text())
    assert loaded["schema_version"] == "phase-7-0"
    assert loaded["workflow_id"] == "wf-test-1"
    assert loaded["awaiting"] == "phase_8_planner"


def test_emit_coordination_appends_tsv_index(tmp_path):
    """AC-8 — _index.tsv created with header on first write; one data row appended."""
    ctx = _make_ctx(tmp_path)
    emit_coordination(ctx, _make_both())
    tsv = tmp_path / "coordination" / "_index.tsv"
    lines = tsv.read_text().splitlines()
    assert lines[0].startswith("# emitted_at\tworkflow_id\tcve_id")
    assert len(lines) == 2  # header + one data row
    fields = lines[1].split("\t")
    assert fields[1] == "wf-test-1"
    assert fields[2] == "CVE-2026-0001"


def test_emit_coordination_abort_if_spanning_log_fails(tmp_path):
    """AC-9 — if spanning-log append raises, no YAML, no TSV row."""
    ctx = _make_ctx(tmp_path)
    ctx.event_log.append_spanning.side_effect = RuntimeError("disk full")
    with pytest.raises(RuntimeError):
        emit_coordination(ctx, _make_both())
    yaml_path = tmp_path / "coordination" / "wf-test-1.yaml"
    tsv = tmp_path / "coordination" / "_index.tsv"
    assert not yaml_path.exists()
    assert not tsv.exists()
```

State why the red tests fail: `ModuleNotFoundError: plugins.distroless_migration_node_npm.subgraph.api` — module + function do not exist; `PendingCoordination` not yet added to `outcomes.py`.

### Green — minimal pass

- Add `PendingCoordination` variant to `src/codegenie/transforms/outcomes.py`; widen `Applicability` umbrella; update `__all__`.
- Create the `subgraph/api.py` + `_yaml_schema.py` per the implementation outline. Implement `emit_coordination` with the three-step write order; build helpers; render YAML via `yaml.safe_dump`.
- Land the golden fixture.

### Refactor

- Add module docstrings; doc-link the writer to ADR-0001 / ADR-0017.
- Add a code comment on the three-step write order naming ADR-0034 ("spanning log is source-of-truth").
- Verify `make check` clean and Phase 3 regression-suite-green.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/outcomes.py` | EDIT (additive) — add `PendingCoordination` variant to `Applicability`. |
| `tests/unit/transforms/test_outcomes.py` | EDIT (additive) — parametrize the new variant into existing round-trip / frozen / extra-reject / discriminator-pin tests. |
| `tests/unit/transforms/test_exhaustiveness.py` | EDIT (additive) — add the new arm to `test_exhaustiveness_applicability`. |
| `plugins/distroless-migration--node--npm/subgraph/__init__.py` | NEW — package marker. |
| `plugins/distroless-migration--node--npm/subgraph/api.py` | NEW — `emit_coordination` writer. |
| `plugins/distroless-migration--node--npm/subgraph/_yaml_schema.py` | NEW — `CoordinationSummary` + `AppSummary` + `BaseSummary` Pydantic models. |
| `tests/unit/plugins/distroless_migration_node_npm/test_emit_coordination.py` | NEW — writer behavior (AC-6..AC-9, AC-13). |
| `tests/unit/plugins/distroless_migration_node_npm/test_coordination_summary_schema.py` | NEW — schema validation (AC-4, AC-10, AC-11). |
| `tests/unit/plugins/distroless_migration_node_npm/test_coordination_summary_golden.py` | NEW — golden-file equality (AC-12). |
| `tests/unit/plugins/distroless_migration_node_npm/test_index_tsv_append.py` | NEW — TSV format (AC-8). |
| `tests/property/vuln_provenance/test_both_always_emits_coordination.py` | NEW — Hypothesis property (AC-14). |
| `tests/golden/coordination-summary/both-app-direct-plus-base-image.yaml` | NEW — canonical operator-readable shape. |

## Out of scope

- **`codegenie list-coordination-candidates` CLI** — S11-03.
- **Exit-code 8 wiring + orchestrator translation** — S11-04.
- **Phase 8 Planner projection** — Phase 8.
- **Atomic-or-nothing merge gate behavior** — Phase 11.
- **`coordination-summary.yaml` schema evolution to `"phase-8-0"`** — Phase 8 (the `Literal` widening pattern is established here, used there).
- **TSV row uniqueness / dedup** — operator concern, handled by `sort -u`. The writer is append-only by design.
- **Multi-orchestrator-process safety** — Phase 5 invariant is single-process per workflow; this story does not take file locks. If Phase 9 / Phase 11 changes that, a follow-up story adds `fcntl.flock` on the TSV.

## Notes for the implementer

- **`Applicability` widening is additive, not a rename.** The ADR-0001 contract-snapshot test in Phase 3 (`tests/unit/transforms/test_outcomes_contract.py` or equivalent) enumerates the known variant set. Adding `PendingCoordination` requires updating that test's expected set — that update is the load-bearing audit trail. The Phase 5 GateRunner and orchestrator both `match` over `Applicability`; landing the new variant + `mypy --strict` clean is what proves every consumer has been updated (per the `assert_never` discipline in S1-03 of Phase 3). If `mypy --strict` errors, the consumer needs a new `case PendingCoordination():` arm — do not silence the error.
- **`CoordinationSummary.schema_version` is distinct from `RequiresMultiPluginCoordination.schema_version` (S11-01).** The event's `schema_version` is consumed by Phase 8's Planner (reads the spanning log); the YAML's `schema_version` is consumed by operators + the CLI subcommand (S11-03). They evolve independently. Both default to `"phase-7-0"`; both reject `"phase-8-0"` at this story's landing. Phase 8 widens one or both as needed.
- **Write order: spanning log → YAML → TSV.** ADR-0034 names the spanning log as source-of-truth. If the spanning log append raises (disk full, fsync error, codec error), the YAML and TSV writes do not happen — Phase 8 reconstructs nothing from a partial write. If the YAML write raises after the spanning-log append succeeds, the spanning log has the truth; the TSV is not appended; the operator notices via the `_index.tsv` not having the row; a manual re-run with the same `WorkflowId` (or Phase 8's projection) recovers. Do NOT swap the order or attempt to make the three writes "atomic" — the spanning log is the contract surface; the others are projections.
- **`_index.tsv` header-creation discipline.** First write creates the file with `# emitted_at\tworkflow_id\tcve_id\tapp_kind\tbase_kind\tsummary_path\n` followed by the first data row. The `#` prefix lets operators `grep -v '^#' _index.tsv | wc -l` to count rows. Subsequent writes use `open(path, "a")` and append only the data row. Test the multi-write sequencing explicitly: write twice, assert exactly one header row and exactly two data rows.
- **YAML key order via `sort_keys=False`.** `yaml.safe_dump(model.model_dump(mode="json"), sort_keys=False)` preserves Pydantic's field-declaration order. This is what makes the golden file stable across `model_dump_json()` reorderings. If a future Pydantic version changes field ordering, the golden breaks loudly — that is the desired failure mode.
- **`AppSummary` / `BaseSummary` are NOT the same as `AppKind` / `BaseKind` (S11-01).** The event payload carries the full discriminated-union records (for Phase 8 routing without re-running adapters). The YAML carries flat denormalized projections (for operator readability). The two evolve independently; the YAML is operator-side, the event is Planner-side. If you find yourself tempted to ship a single `Both` shape that serves both, resist — Phase 8's Planner needs the full `AppKind` discriminated payload, operators need a flat YAML. Two consumers, two shapes, locked at `schema_version`.
- **`proposed_plugin_routes` is operator-readable hinting only.** Phase 8's Planner derives the actual routes from the typed event (`app_record`, `base_record`). The YAML carries `proposed_plugin_routes: list[PluginId]` for operator visibility — e.g., `["vulnerability-remediation--node--npm", "distroless-migration--node--npm"]` so the operator sees at a glance which two plugins are pending coordination. Do NOT make Phase 8 depend on this field; document it in the schema docstring.
- **Closest precedent.** Phase 3's `remediation-report.yaml` writer (under the Phase 3 plugin's subgraph) is the structural twin: Pydantic schema + golden fixture + `extra="forbid"` + `schema_version` literal + plugin-tree home. Mirror its shape; do not re-invent.
- **Phase 3–6.5 regression suite green is hard pre-merge.** Per ADR-0009 + Step 11's done-criteria. The additive variant on `Applicability` is the load-bearing risk — verify the cassette replay byte-equal before opening the PR.
