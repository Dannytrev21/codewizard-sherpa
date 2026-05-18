# Story S5-05 — `RemediationReport` Pydantic model + `remediation-report.yaml` writer

**Step:** Step 5 — Transform ABC consumers, RecipeEngine Protocol, RecipeRegistry, lockfile policy
**Status:** Ready
**Effort:** S
**Depends on:** S5-01
**ADRs honored:** ADR-0001, ADR-0010

## Context

`remediation-report.yaml` is the *artifact* Phase 5 reads to decide retry, the file Phase 9's event projector indexes alongside both event streams, the human-facing summary the operator opens after `codegenie remediate <repo> --cve <id>` exits, and one of the six load-bearing names Phase 3 ships per ADR-0001 (`RemediationOrchestrator`, `TrustScorer`, `Transform`, `ApplyContext`, `RecipeEngine`, `remediation-report.yaml`). This story ships the schema **and** the writer — *not* the orchestrator integration (S6-04 wires `report.write(...)` into the happy + every failure path).

The architecture has three load-bearing commitments this story honors:

1. **The schema is Phase-5-frozen** (ADR-0001 §Consequences: "The `remediation-report.yaml` schema lives in `src/codegenie/transforms/report.py` and ships with golden-file tests under `tests/golden/remediation-reports/`."). Phase 5's gates read `trust_outcome.passed`, `trust_outcome.confidence`, `outcome.kind`, `prior_attempts`-shaped fields. Any change to the surface requires an ADR amendment + Phase 5 ADR-update + golden refresh.
2. **Partial reports on failure** (§C1 Failure behavior: "On exception in any stage, the orchestrator writes a partial `remediation-report.yaml` with `outcome.kind = 'failed'` and re-raises. **Never** silently catches."). The writer must accept a partially-populated report (e.g., no `transform`, no `trust_outcome` if Stage 6 never ran) and emit a syntactically valid YAML — every nullable field is explicitly modeled as `Optional`.
3. **Round-trip invariant**: a hand-built `RemediationReport` instance, serialized to YAML, then re-parsed, equals the original. This is the testable surface for the snapshot test (S6-06) that gates Phase 5's ability to ship.

The schema indexes both event streams (`event_log_internal_path: SandboxedPath`, `event_log_spanning_path: SandboxedPath`) and carries the audit-chain BLAKE3 head (`spanning_chain_head: BlobDigest`). The `outcome: RemediationOutcome` field is the discriminated union from S1-03 (`Validated | RequiresHumanReview | NotApplicable | Failed`); the `trust_outcome: TrustOutcome | None` is null when Stage 6 never ran (e.g., `NotApplicable` exit before validation).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C1 Failure behavior` — partial-report-on-failure invariant; "Never silently catches".
  - `../phase-arch-design.md §Control flow step 10` — `report.write(...)` indexes both event streams + outcome; audit-chain head computed.
  - `../phase-arch-design.md §Data model` — `RemediationOutcome`, `TrustOutcome`, `Transform`, `BlobDigest`, `SandboxedPath` types the report composes.
  - `../phase-arch-design.md §Harness engineering` — "Two-stream event log; per-workflow file is enough to reconstruct workflow-internal state."
  - `../phase-arch-design.md §Confidence handling` — `TrustOutcome.confidence ∈ {high, degraded}` flows verbatim into `remediation-report.yaml`; Phase 5's gates read it.
  - `../phase-arch-design.md §Testing strategy — Golden files` — `tests/golden/remediation-reports/express-cve-2024-21501.yaml` modulo `workflow_id` + `timestamps`.
- **Phase ADRs:**
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — ADR-0001 — `remediation-report.yaml` is one of the six Phase-5-named seams; §Consequences pins the location and golden-file commitment; **this is the load-bearing reference for the story**.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — ADR-0010 — newtype `WorkflowId`, `CveId`, `BranchName`, `BlobDigest`; tagged-union `RemediationOutcome`; `extra="forbid"` + `frozen=True`.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Remediation report schema"` (Phase 5 inheritance).
- **High-level impl:**
  - `../High-level-impl.md §Step 5 — Features delivered` bullet 6 (`transforms/report.py`); `Done criteria` line 6 (round-trip a hand-built instance).
- **Phase 5 inheritance:**
  - `docs/phases/05-sandbox-trust-gates/phase-arch-design.md` (or `final-design.md`) — Phase 5's `GateRunner.run` consumes this artifact's `trust_outcome` + `prior_attempts` shape. Read before authoring the schema; if Phase 5 documents specific field names not listed here, add them (Rule 8 — read before you write).
- **Sibling stories:**
  - `S5-01-recipe-registry.md` — `RecipeOutcome`, `RecipePlan`, `Transform`.
  - `S1-03-tagged-union-outcomes.md` — `RemediationOutcome` discriminated union (`Validated | RequiresHumanReview | NotApplicable | Failed`).
  - `S6-04-remediation-orchestrator.md` — calls `report.write(...)` from the orchestrator's happy + every failure path.
  - `S6-06-phase5-contract-snapshot.md` — snapshots this schema; failure means Phase 5 cannot ship.

## Goal

Ship `src/codegenie/transforms/report.py` exposing `RemediationReport` (Pydantic `extra="forbid"`, `frozen=True`), `RemediationReport.write(path: SandboxedPath) -> Result[None, IoError]`, `RemediationReport.from_yaml(path: SandboxedPath) -> Result[RemediationReport, ParseError]`, and the field surface Phase 5 will read. Round-trip test confirms a hand-built instance serializes to YAML and re-parses to an equal instance.

## Acceptance criteria

- [ ] `from codegenie.transforms.report import RemediationReport, ReportMetadata` succeeds.
- [ ] `RemediationReport` is a Pydantic model with `model_config = ConfigDict(frozen=True, extra="forbid")` and the following field surface (every name reviewed against Phase 5's known consumers):
  - `schema_version: Literal[1]`
  - `metadata: ReportMetadata` (nested model carrying `workflow_id: WorkflowId`, `cve: CveId`, `repo_path: str`, `started_at: datetime`, `completed_at: datetime`, `codegenie_version: str`)
  - `plugin: PluginSnapshot` (nested model carrying `plugin_id: PluginId`, `plugin_version: SemverVersion`, `recipe_id: RecipeId | None`, `recipe_version: SemverVersion | None`) — recipe nulls when no match occurred
  - `transform: TransformSnapshot | None` (nested model carrying `transform_id: TransformId`, `transform_kind: TransformKind`, `files_changed: tuple[str, ...]`, `diff_bytes_sha256: BlobDigest`) — null on `NotApplicable` / pre-match failure
  - `outcome: RemediationOutcome` (the discriminated union from S1-03)
  - `trust_outcome: TrustOutcome | None` (null when Stage 6 never ran)
  - `branch: BranchName | None` (null on every non-`Validated` outcome)
  - `event_log_internal_path: str` (relative to `.codegenie/`)
  - `event_log_spanning_path: str` (relative to `.codegenie/`)
  - `spanning_chain_head: BlobDigest`
  - `lockfile_policy_violations: tuple[PolicyViolation, ...] = ()` (S5-04 surface; empty tuple when no violations or Stage 6 didn't run)
- [ ] **Every field is either required or has an explicit `Optional`/default**. No silent `Optional`s; `mypy --strict` enforces.
- [ ] **`schema_version: Literal[1]`** — explicit version pin; future schemas refuse with a `ParseError` (mirrors `LockfilePolicy` from S5-04).
- [ ] `RemediationReport.write(path: SandboxedPath) -> Result[None, IoError]`:
  - Serializes via `pyyaml.safe_dump(..., default_flow_style=False, sort_keys=False, allow_unicode=True, width=120)` — deterministic key order (matches Pydantic's declaration order via `model_dump(mode="json")`).
  - Writes through `SandboxedPath` with `O_NOFOLLOW` (S4-04) — same TOCTOU defense as the engine writer.
  - Atomically renames: write to `<path>.tmp` first, fsync, then `os.replace(tmp, path)`. Crash mid-write yields either old-or-new, never partial.
  - Returns `Result.Ok(None)` on success; `Result.Err(IoError(reason="filesystem_race"|"disk_full"|"permission_denied", path=...))` on failure.
- [ ] `RemediationReport.from_yaml(path: SandboxedPath) -> Result[RemediationReport, ParseError]` smart constructor; same `ParseError.reason` taxonomy as `LockfilePolicy.from_yaml` (`file_missing`, `yaml_syntax`, `schema_violation`, `unknown_schema_version`). Round-trip closure (see next AC).
- [ ] **Round-trip invariant** (the load-bearing test):
  - Hand-build a `RemediationReport` instance (use `outcome=RemediationOutcome.Validated(...)` happy path).
  - `report.write(tmp / "r.yaml")` → succeed.
  - `RemediationReport.from_yaml(tmp / "r.yaml").unwrap()` → equal to the original (`==` via Pydantic equality).
  - Repeat for `RemediationOutcome.NotApplicable`, `RemediationOutcome.Failed`, `RemediationOutcome.RequiresHumanReview` — all four discriminated-union variants survive round-trip.
- [ ] **Partial-report happy path**: a `RemediationReport` with `transform=None`, `trust_outcome=None`, `branch=None`, `outcome=RemediationOutcome.NotApplicable(reason="PEER_DEP_CONFLICT")` serializes to YAML cleanly and round-trips.
- [ ] **Partial-report failure path** (§C1 invariant): a `RemediationReport` with `outcome=RemediationOutcome.Failed(error=...)`, `transform=None`, `trust_outcome=None`, `branch=None`, and a *truncated* event-log path (e.g., the workflow crashed before flushing the spanning stream) — the model still validates, writes, and reads back equal. (The orchestrator is responsible for not lying about the event-log path; this story tests that the schema *permits* a truthful partial report.)
- [ ] **Deterministic key order in YAML**: writing the same `RemediationReport` instance twice produces byte-identical YAML output (the golden test for S8-02 depends on this).
- [ ] **`extra="forbid"`**: a YAML file with an unknown top-level key (e.g., `magic_field: true`) returns `Result.Err(ParseError(reason="schema_violation", field="magic_field"))`.
- [ ] **Newtype enforcement**: all identifier fields (`workflow_id`, `cve`, `plugin_id`, `recipe_id`, `transform_id`, `branch`, `spanning_chain_head`) are typed via the newtypes from S1-01 (not raw `str`); mypy `--strict` catches a swap.
- [ ] `mypy --strict src/codegenie/transforms/report.py` clean.
- [ ] `ruff check`, `ruff format --check`, `pytest tests/unit/transforms/test_remediation_report.py` all green.
- [ ] Branch coverage on `report.py` ≥ 95%.
- [ ] The module is re-exported from `src/codegenie/transforms/__init__.py` and `RemediationReport` is on the `__all__` list (ADR-0001 export-list fence).

## Implementation outline

1. Create `src/codegenie/transforms/report.py`.
2. Define `ReportMetadata`, `PluginSnapshot`, `TransformSnapshot` as nested Pydantic models — each `extra="forbid"`, `frozen=True`.
3. Define `RemediationReport(BaseModel)` with the field surface above. Order fields in declaration order matching the human-facing YAML reading order: `schema_version` first, `metadata` second, `plugin` third, then `transform`, `outcome`, `trust_outcome`, `branch`, event log paths, audit head, policy violations.
4. `write` method:
   ```python
   def write(self, path: SandboxedPath) -> Result[None, IoError]:
       try:
           tmp = path.with_suffix(path.suffix + ".tmp")
           payload = yaml.safe_dump(
               self.model_dump(mode="json"),
               default_flow_style=False, sort_keys=False,
               allow_unicode=True, width=120,
           ).encode("utf-8")
           with tmp.open("wb") as f:   # O_NOFOLLOW
               f.write(payload); f.flush(); os.fsync(f.fileno())
           os.replace(str(tmp), str(path))   # atomic on POSIX
           return Result.Ok(None)
       except OSError as e:
           reason = "filesystem_race" if e.errno == errno.ELOOP else (
               "disk_full" if e.errno == errno.ENOSPC else
               "permission_denied" if e.errno == errno.EACCES else "io_error")
           return Result.Err(IoError(reason=reason, path=str(path), errno=e.errno))
   ```
5. `from_yaml` mirrors `LockfilePolicy.from_yaml` from S5-04 (file existence → parse → Pydantic validate → version pin); reuse the `ParseError` shape from S5-04 if a module already exposes it (Rule 7 — pick one; do not invent a parallel error type).
6. Datetime serialization: `datetime` fields serialize as ISO-8601 UTC strings (`.isoformat()`); the model's `model_dump(mode="json")` does this by default for `aware` datetimes; document the UTC requirement at the field annotation.
7. The `outcome: RemediationOutcome` discriminated union from S1-03 should serialize/deserialize cleanly via the `Discriminator("kind")` Pydantic annotation; the round-trip test covers all four arms.
8. Tests (TDD plan below).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/transforms/test_remediation_report.py`.

```python
# tests/unit/transforms/test_remediation_report.py
from datetime import datetime, timezone
from pathlib import Path
import pytest
import yaml
from pydantic import ValidationError
from codegenie.transforms.report import (
    RemediationReport, ReportMetadata, PluginSnapshot, TransformSnapshot,
)
from codegenie.transforms.outcomes import RemediationOutcome
from codegenie.transforms.trust_scorer import TrustOutcome
from codegenie.types.identifiers import (
    WorkflowId, CveId, PluginId, RecipeId, TransformId, TransformKind,
    BranchName, BlobDigest, SemverVersion,
)

def _meta(**overrides):
    base = dict(
        workflow_id=WorkflowId("01HX0000000000000000000000"),
        cve=CveId("CVE-2024-21501"), repo_path="/tmp/fixture",
        started_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 17, 12, 0, 30, tzinfo=timezone.utc),
        codegenie_version="0.3.0",
    )
    base.update(overrides)
    return ReportMetadata(**base)

def _plugin():
    return PluginSnapshot(
        plugin_id=PluginId("vulnerability-remediation--node--npm"),
        plugin_version=SemverVersion("0.1.0"),
        recipe_id=RecipeId("npm-lockfile-semver-bump"),
        recipe_version=SemverVersion("0.1.0"),
    )

def _transform():
    return TransformSnapshot(
        transform_id=TransformId("blake3:abc123"),
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
        files_changed=("package.json", "package-lock.json"),
        diff_bytes_sha256=BlobDigest("a" * 64),
    )

def _trust_passed():
    return TrustOutcome(passed=True, failing=[], signals=[], confidence="high")

@pytest.fixture
def validated_report():
    return RemediationReport(
        schema_version=1, metadata=_meta(), plugin=_plugin(),
        transform=_transform(),
        outcome=RemediationOutcome.Validated(
            branch=BranchName("codegenie/cve-2024-21501-abc12"),
            report_path="/tmp/r.yaml",
        ),
        trust_outcome=_trust_passed(),
        branch=BranchName("codegenie/cve-2024-21501-abc12"),
        event_log_internal_path="events/internal/01HX....jsonl.zst",
        event_log_spanning_path="events/spanning/append.jsonl.zst",
        spanning_chain_head=BlobDigest("b" * 64),
        lockfile_policy_violations=(),
    )

def test_round_trip_validated(tmp_path, validated_report):
    p = SandboxedPath(tmp_path / "r.yaml")
    assert validated_report.write(p).is_ok
    loaded = RemediationReport.from_yaml(p).unwrap()
    assert loaded == validated_report

def test_round_trip_not_applicable(tmp_path):
    r = RemediationReport(
        schema_version=1, metadata=_meta(), plugin=_plugin().model_copy(
            update={"recipe_id": None, "recipe_version": None}),
        transform=None,
        outcome=RemediationOutcome.NotApplicable(reason="PEER_DEP_CONFLICT"),
        trust_outcome=None, branch=None,
        event_log_internal_path="events/internal/x.jsonl.zst",
        event_log_spanning_path="events/spanning/append.jsonl.zst",
        spanning_chain_head=BlobDigest("c" * 64),
    )
    p = SandboxedPath(tmp_path / "r.yaml")
    r.write(p).unwrap()
    assert RemediationReport.from_yaml(p).unwrap() == r

def test_round_trip_failed_partial_report(tmp_path):
    r = RemediationReport(
        schema_version=1, metadata=_meta(), plugin=_plugin().model_copy(
            update={"recipe_id": None, "recipe_version": None}),
        transform=None,
        outcome=RemediationOutcome.Failed(error={"reason": "lockfile_v1_unsupported"}),
        trust_outcome=None, branch=None,
        event_log_internal_path="events/internal/partial.jsonl.zst",
        event_log_spanning_path="events/spanning/append.jsonl.zst",
        spanning_chain_head=BlobDigest("d" * 64),
    )
    p = SandboxedPath(tmp_path / "r.yaml")
    r.write(p).unwrap()
    assert RemediationReport.from_yaml(p).unwrap() == r

def test_round_trip_requires_human_review(tmp_path):
    r = RemediationReport(...)   # build with RemediationOutcome.RequiresHumanReview
    p = SandboxedPath(tmp_path / "r.yaml")
    r.write(p).unwrap()
    assert RemediationReport.from_yaml(p).unwrap() == r

def test_yaml_byte_identical_on_repeated_write(tmp_path, validated_report):
    p1, p2 = SandboxedPath(tmp_path / "a.yaml"), SandboxedPath(tmp_path / "b.yaml")
    validated_report.write(p1).unwrap()
    validated_report.write(p2).unwrap()
    assert p1.read_bytes() == p2.read_bytes()

def test_extra_field_rejected(tmp_path, validated_report):
    p = SandboxedPath(tmp_path / "r.yaml")
    validated_report.write(p).unwrap()
    doc = yaml.safe_load(p.read_bytes())
    doc["magic_field"] = True
    (tmp_path / "hostile.yaml").write_text(yaml.safe_dump(doc))
    result = RemediationReport.from_yaml(SandboxedPath(tmp_path / "hostile.yaml"))
    assert not result.is_ok and result.error.reason == "schema_violation"

def test_unknown_schema_version_rejected(tmp_path, validated_report):
    p = SandboxedPath(tmp_path / "r.yaml")
    validated_report.write(p).unwrap()
    doc = yaml.safe_load(p.read_bytes()); doc["schema_version"] = 2
    (tmp_path / "v2.yaml").write_text(yaml.safe_dump(doc))
    result = RemediationReport.from_yaml(SandboxedPath(tmp_path / "v2.yaml"))
    assert not result.is_ok and result.error.reason == "unknown_schema_version"

def test_atomic_write_no_partial_on_crash(tmp_path, validated_report, monkeypatch):
    # Simulate a write that fails between tmp-write and rename
    p = SandboxedPath(tmp_path / "r.yaml")
    p.write_text("PREVIOUS_CONTENT\n")
    def boom(*a, **kw): raise OSError("synthetic")
    monkeypatch.setattr("os.replace", boom)
    result = validated_report.write(p)
    assert not result.is_ok
    assert p.read_text() == "PREVIOUS_CONTENT\n"   # never partial-overwritten

def test_newtypes_enforced_at_construction():
    with pytest.raises(ValidationError):
        ReportMetadata(
            workflow_id="not-a-ulid",   # would parse as raw str; smart constructor must reject
            cve=CveId("CVE-2024-21501"),
            repo_path="/x", started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc), codegenie_version="0.3.0",
        )
```

Run; confirm `ImportError`; commit; implement.

### Green — make it pass

- Implement the nested models in field-by-field correspondence; document each field with a one-line comment noting Phase 5 / Phase 9 / human consumer.
- `model_dump(mode="json")` gives ISO-8601 datetimes and string-encoded newtypes for free; `yaml.safe_dump` round-trips that cleanly into native YAML.
- For the atomic-write test, the `monkeypatch` on `os.replace` is the standard approach; the `try/except OSError` block catches and returns `Err`, leaving the original file intact.
- The `RemediationOutcome` discriminated union from S1-03 must already serialize correctly via Pydantic's `Discriminator("kind")`; if it doesn't, that's a S1-03 bug to surface, not a S5-05 workaround (Rule 8).

### Refactor — clean up

- Confirm every datetime field is **timezone-aware** (`tzinfo=timezone.utc`) — naive datetimes serialize ambiguously and break the golden test S8-02 depends on. Add a field-validator that rejects naive datetimes with a clear error.
- Confirm the YAML output has **no `!!python/...` tags** — `yaml.safe_dump` won't emit them, but if a custom serializer leaks one, the report becomes Python-only-parseable. Defensive test: parse the YAML with a non-Python loader (text grep for `!!python`) and assert absent.
- Re-check the ADR-0001 §Consequences clause: "the `remediation-report.yaml` schema lives in `src/codegenie/transforms/report.py` and ships with golden-file tests under `tests/golden/remediation-reports/`." The golden file itself is S8-02's deliverable (end-to-end Express CVE), but this story should leave a placeholder `tests/golden/remediation-reports/README.md` explaining the file convention and that S8-02 will populate the first golden.
- Field-order in YAML: Pydantic preserves declaration order in `model_dump`; `yaml.safe_dump(..., sort_keys=False)` honors it. Run the byte-identical test on a fresh model rebuild to ensure no accidental alphabetization.
- Cross-check that the `outcome.kind` literal values match exactly the ones Phase 5 / Phase 6 expect (`"validated"`, `"requires_human_review"`, `"not_applicable"`, `"failed"`). If Phase 5's design doc uses different casing, surface the conflict (Rule 7) — do not silently convert.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/report.py` | New — `RemediationReport` + nested snapshots + `write` + `from_yaml` |
| `tests/unit/transforms/test_remediation_report.py` | New — round-trip for all four outcomes, partial reports, atomic-write, schema-version + extra-field rejection, byte-identical determinism |
| `src/codegenie/transforms/__init__.py` | Add `RemediationReport` to `__all__` (ADR-0001 export-list fence) |
| `tests/golden/remediation-reports/README.md` | New — explains the golden-file convention; S8-02 populates the first golden |

## Out of scope

- **The golden file itself** (`tests/golden/remediation-reports/express-cve-2024-21501.yaml`) — S8-02 ships it from the end-to-end Express CVE run.
- **`report.write(...)` integration into the orchestrator** — S6-04 (happy path + every failure path).
- **The Phase-5 contract snapshot test** (`tests/integration/test_phase5_contract_snapshot.py`) — S6-06 (this story produces the schema the snapshot test pins).
- **Event-stream replay verification** — S6-01 (`EventLog.replay`).
- **The audit-chain BLAKE3 computation** — S6-01 (`EventLog` computes the head; this story only stores it as a `BlobDigest` field).
- **`lockfile_policy_violations` *evaluation*** — S5-04 (this story only carries the violations field; Stage 6 evaluator populates it).
- **`prior_attempts` field on `ApplyContext`** — S1-04 (this story does NOT embed `ApplyContext` in the report; the report is the *post-hoc* artifact, not the input bundle; Phase 5 reads `prior_attempts` from a separate retry ledger).
- **JSON serialization** — Phase 9's projector may want JSON for its postgres landing; that's a Phase 9 transform on top of YAML, not this story's concern.

## Notes for the implementer

- **YAML over JSON for the artifact**: the codebase convention (project CLAUDE.md) is "YAML for the human-facing artifact". The `remediation-report.yaml` is human-readable by operators; YAML wins. Raw probe outputs are JSON. Don't invert this.
- **`schema_version: Literal[1]` is the contract pin**: the snapshot test S6-06 will pin every field name; the `schema_version` lets us version the *whole schema* deliberately. Phase 7 adding a field that fits into v1 (e.g., `lockfile_policy_violations` widening from one variant to two) does NOT bump the version; Phase 9 adding a `cost: dict` for the cost ledger DOES bump (semantically a different consumer contract). Document the bump policy in the model docstring.
- **Atomic write via tmp+rename**: standard POSIX pattern. `os.replace(tmp, path)` is atomic on the same filesystem; if `tmp` is on a different fs (rare but possible with `/tmp` cross-mounts), `os.replace` falls back to copy+unlink which is *not* atomic. Sanity check: assert `tmp.parent == path.parent` before the rename.
- **`SandboxedPath` vs `Path`**: write paths must be `SandboxedPath`. The `from_yaml` *can* accept `SandboxedPath` too (the report we read back is also inside the analyzed repo's `.codegenie/`); use the same type for symmetry. If callers have a `Path`, they construct a `SandboxedPath(jail=..., relative=...)` at the call site.
- **`extra="forbid"` is load-bearing**: ADR-0001 §Tradeoffs row 4: "Schema rigidity — Pydantic `extra="forbid"` means Phase 5 cannot quietly add fields; every addition is a contract amendment." This is a feature: the snapshot test S6-06 catches drift.
- **Equality**: Pydantic `BaseModel.__eq__` compares fields; with `frozen=True` instances are hashable. The round-trip test uses `==`; if a field type (e.g., a custom newtype) doesn't compare correctly, surface that as a S1-01 bug (Rule 8).
- **Datetime UTC discipline**: every `started_at`/`completed_at` is `tz=timezone.utc`. The orchestrator (S6-04) is responsible for using `datetime.now(timezone.utc)` consistently; this story enforces with a field validator.
- **What Phase 5 reads**: based on `docs/phases/05-sandbox-trust-gates/` design, Phase 5 reads `trust_outcome.passed`, `trust_outcome.confidence`, `trust_outcome.failing`, and `outcome.kind`. If Phase 5's gates inspect any other field (e.g., `transform.diff_bytes_sha256`), confirm by reading Phase 5's `phase-arch-design.md` *before* finalizing the field list (Rule 8). If a needed field is missing, add it here, not in Phase 5.
- **Hand-built instance test is the load-bearing one**: the High-level-impl `Done criteria` line 6 says explicitly "round-trips a hand-built `RemediationReport` instance" — this is the entire S5-05 spec in one sentence. Make sure the test name reflects this verbatim so the criterion-to-test mapping is obvious in CI logs.
