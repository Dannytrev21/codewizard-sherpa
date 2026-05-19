# Story S5-05 — `RemediationReport` Pydantic model + `remediation-report.yaml` writer

**Step:** Step 5 — Transform ABC consumers, RecipeEngine Protocol, RecipeRegistry, lockfile policy
**Status:** HARDENED
**Effort:** S
**Depends on:** S5-01, (S6-02 if `TrustOutcome` is *not* relocated to `outcomes.py` — see Validation notes / `Notes-for-implementer`)
**ADRs honored:** ADR-0001, ADR-0010

## Validation notes (2026-05-19, phase-story-validator)

The original draft prescribed several APIs that do not exist in the kernel as it landed across S1-01..S5-04. Each correction below is verified against the actual source at the file/line cited. Full critic + decision log: `_validation/S5-05-remediation-report-writer.md`.

1. **Outcome variants are standalone classes, not union attributes.** Use `Validated`, `RemediationNotApplicable`, `RemediationFailed`, `RequiresHumanReview` from `codegenie.transforms.outcomes` (outcomes.py:242, 263, 274, 285). There is no `RemediationOutcome.Validated(...)` dot-access.
2. **`RemediationFailed.error: RemediationError`** is a typed Pydantic model (outcomes.py:155), **not a raw dict**. Construct as `RemediationError(error_id=ErrorId("io.lockfile_v1_unsupported"), message="...")`.
3. **`Validated`** requires `passed: bool` and `failing: list[SignalKind]` in addition to `branch, report_path`, and enforces `passed iff len(failing)==0` via a `model_validator` (outcomes.py:256-260). Round-trip fixtures must supply these fields.
4. **`Result` API**: import `Ok`, `Err`, `Result` from `codegenie.result` (result.py:40, 60). There are no `Result.Ok(...)` / `Result.Err(...)` classmethods. `is_ok` is a *method* (`result.is_ok()`), not a property. Tests should prefer `isinstance(result, Ok)` / `isinstance(result, Err)` for typed narrowing on the next line.
5. **Canonical `ParseError`** (types/errors.py:25) is `frozen=True, extra="forbid"` with **only** `message: str` + `value: str`. Adding `reason` / `field` requires an ADR-0010 amendment (the same drift S5-04's validator caught). **Mirror the S5-04 `PolicyLoadError` precedent**: declare a module-local discriminated-union load-error in `transforms/report.py` (`ReportLoadError`).
6. **Canonical `IoError`** (plugins/manifest.py:143) is a `ManifestError` variant with shape `kind: Literal["io_error"], path: Path, errno: int, message: str` — no `reason` field. **Do not reuse** the manifest's `IoError` from the report module (couples unrelated concerns). Declare a module-local `ReportIoError` discriminated union for write failures.
7. **`TrustOutcome` does not live at `codegenie.transforms.trust_scorer` yet** — S6-02 ships `trust_scorer.py`. The architecture's data-model snippet (phase-arch-design.md:839) places `TrustOutcome` in the same conceptual layer as `RemediationOutcome`. **Recommended option (A):** declare `TrustSignal` + `TrustOutcome` in `codegenie/transforms/outcomes.py` as part of this story (kernel home, mirrors the Amendment 2026-05-18 single-canonical-home discipline); S6-02 layers the `TrustScorer.score()` consumer on top via re-export. Option (B): add `S6-02` to `Depends on:` and let S5-05 wait. Pick (A); the AC list below assumes (A).
8. **`WorkflowId` is `NewType("WorkflowId", str)` (identifiers.py:70)** — there is **no runtime check**. `mypy --strict` is the discipline. The original `test_newtypes_enforced_at_construction` (which expected `ValidationError` from a raw-str `workflow_id`) is impossible; replaced with the mypy-discipline note.
9. **Atomic-write tmp path**: `Path.with_suffix(self.suffix + ".tmp")` creates a multi-suffix path (`.yaml.tmp`) — fragile. Use `path.parent / (path.name + ".tmp")` or copy the established `output/writer.py:128` pattern (`<suffix>.<pid>.<token_hex>.tmp`) so two concurrent writers do not collide.
10. **`monkeypatch` target**: patch `codegenie.transforms.report.os.replace`, not the top-level `os.replace`, so the patch hits the reference the function actually resolves.
11. **ADR-0010 + fence**: every nested model (`ReportMetadata`, `PluginSnapshot`, `TransformSnapshot`, and every load-/io-error variant) carries `model_config = ConfigDict(frozen=True, extra="forbid")` — required, not implied.
12. **`Make illegal states unrepresentable`** (ADR-0010): a `model_validator(mode="after")` on `RemediationReport` enforces `outcome.kind == "validated" ⇒ (transform, branch) ≠ (None, None)` and `outcome.kind ∈ {"failed", "not_applicable"} ⇒ branch is None`. The schema must close the door on structurally-impossible states.
13. **Functional core / imperative shell**: split `write()` into a pure `_serialize() -> bytes` (byte-identical determinism test runs without a filesystem) and an impure `_write_bytes(path, payload) -> Result[None, ReportIoError]`. The S8-02 golden replay benefits.

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

### Surface

- [ ] **AC-Surface-1.** `from codegenie.transforms.report import RemediationReport, ReportMetadata, PluginSnapshot, TransformSnapshot, ReportLoadError, ReportIoError` succeeds. Re-exported from `codegenie.transforms` (`src/codegenie/transforms/__init__.py`); `RemediationReport` is on the `__all__` list (ADR-0001 export-list fence).
- [ ] **AC-Surface-2.** `TrustSignal` and `TrustOutcome` are declared in `codegenie/transforms/outcomes.py` (kernel canonical home, mirroring the 2026-05-18 amendment's single-declaration-site discipline). S6-02's `trust_scorer.py` re-exports both. If the implementer chooses Option (B) instead (depend on S6-02), this AC is moved to S6-02 and the `Depends on:` line is updated accordingly.
- [ ] **AC-Surface-3.** `RemediationReport` is a Pydantic model with `model_config = ConfigDict(frozen=True, extra="forbid")` and the following field surface, in **declaration order** (the order itself is part of the S6-06 snapshot — re-ordering is a contract break):
  - `schema_version: Literal[1]`
  - `metadata: ReportMetadata`
  - `plugin: PluginSnapshot`
  - `transform: TransformSnapshot | None`
  - `outcome: RemediationOutcome` (the `Annotated[Validated | RequiresHumanReview | RemediationNotApplicable | RemediationFailed, Field(discriminator="kind")]` union from outcomes.py)
  - `trust_outcome: TrustOutcome | None` (null when Stage 6 never ran)
  - `branch: BranchName | None`
  - `event_log_internal_path: str` (relative to `.codegenie/`)
  - `event_log_spanning_path: str` (relative to `.codegenie/`)
  - `spanning_chain_head: BlobDigest`
  - `lockfile_policy_violations: tuple[PolicyViolation, ...] = ()` (S5-04 surface)
- [ ] **AC-Surface-4.** Every nested model (`ReportMetadata`, `PluginSnapshot`, `TransformSnapshot`) carries `model_config = ConfigDict(frozen=True, extra="forbid")` (ADR-0010 §Consequences requirement, not optional).
- [ ] **AC-Surface-5.** Nested-model field shapes:
  - `ReportMetadata`: `workflow_id: WorkflowId`, `cve: CveId`, `repo_path: str`, `started_at: datetime`, `completed_at: datetime`, `codegenie_version: str`.
  - `PluginSnapshot`: `plugin_id: PluginId`, `plugin_version: SemverVersion`, `recipe_id: RecipeId | None = None`, `recipe_version: SemverVersion | None = None`. The `None`-tuple is the *no-match* case (universal fallback or `NotApplicable` exit).
  - `TransformSnapshot`: `transform_id: TransformId`, `transform_kind: TransformKind`, `files_changed: tuple[str, ...]`, `diff_bytes_sha256: BlobDigest`. `files_changed` is declared `tuple[str, ...]` (frozen, hashable, deterministic iteration); round-trip preserves the tuple type — `list[str]` is a contract break.
- [ ] **AC-Surface-6.** `mypy --strict src/codegenie/transforms/report.py` clean. `ruff check` + `ruff format --check` green.

### Discipline (ADR-0010 + ADR-0001)

- [ ] **AC-Disc-1.** Every identifier field uses the newtype from `codegenie.types.identifiers` (`WorkflowId`, `CveId`, `PluginId`, `RecipeId`, `TransformId`, `BranchName`, `BlobDigest`, `SemverVersion`, `TransformKind`). NOT raw `str`. **Runtime enforcement is mypy-only** — `NewType` is a typecheck-time discipline (identifiers.py:65-88 use `NewType(...)`); a runtime check would require smart-constructor functions, which are S1-01's concern, not S5-05's.
- [ ] **AC-Disc-2.** `dict[str, Any]` does **not** appear in `transforms/report.py`. The `RemediationError.details: dict[str, str | int | bool | float] | None` shape rides into the report via `Failed.error.details`; this is the documented primitive-typed-dict boundary, not an `Any` escape hatch.
- [ ] **AC-Disc-3.** `schema_version: Literal[1]` is the explicit version pin; future schemas land as `Literal[2]` etc. The from_yaml loader pre-checks `schema_version` **before** Pydantic schema validation (mirrors S5-04 AC-Load-2 ordering) so an unknown-version file returns `ReportUnknownSchemaVersion`, not `ReportSchemaViolation`.
- [ ] **AC-Disc-4.** **Timezone-aware datetimes only.** A `field_validator` on `started_at` and `completed_at` rejects naive datetimes with a clear ValueError. Naive datetimes serialize ambiguously and break the S8-02 golden file silently.
- [ ] **AC-Disc-5.** **Outcome-kind ↔ optional-field invariant.** A `model_validator(mode="after")` on `RemediationReport` enforces:
  - `outcome.kind == "validated"` ⇒ `transform is not None` AND `branch is not None`.
  - `outcome.kind == "failed"` ⇒ `branch is None`.
  - `outcome.kind == "not_applicable"` ⇒ `branch is None`.
  - `outcome.kind == "requires_human_review"` ⇒ `branch is None`.
  - Violation raises `ValueError`; tests cover each invariant arm.
- [ ] **AC-Disc-6.** **`Validated` invariant**: every `Validated` instance carries `passed: bool` + `failing: list[SignalKind]` with the `_passed_iff_no_failing` invariant from outcomes.py:256-260. Round-trip fixtures must supply `passed=True, failing=[]` (or `passed=False, failing=[SignalKind("...")]`).

### Load errors — module-local discriminated union (mirrors S5-04 `PolicyLoadError`)

- [ ] **AC-Err-Load-1.** `ReportLoadError = Annotated[ReportFileMissing | ReportYamlSyntax | ReportSchemaViolation | ReportUnknownSchemaVersion | ReportSizeCapExceeded | ReportSymlinkRefused, Field(discriminator="kind")]`. Each variant is a `frozen=True, extra="forbid"` Pydantic model with `kind: Literal[...]` discriminator. **The canonical `codegenie.types.errors.ParseError` is NOT extended** (that's the S5-04 precedent — kernel `ParseError` shape is fixed at `message: str, value: str`).
- [ ] **AC-Err-Load-2.** Variant shapes:
  - `ReportFileMissing(kind="file_missing", path: str)`.
  - `ReportYamlSyntax(kind="yaml_syntax", path: str, message: str)`.
  - `ReportSchemaViolation(kind="schema_violation", path: str, field_errors: tuple[str, ...])` — Pydantic v2's stable `ErrorDetails['loc']` rendered as dotted strings.
  - `ReportUnknownSchemaVersion(kind="unknown_schema_version", path: str, found_version: int, supported_versions: tuple[int, ...])` — `supported_versions=(1,)` in Phase 3.
  - `ReportSizeCapExceeded(kind="size_cap_exceeded", path: str, actual_bytes: int, cap: int)` — `cap = 1 << 20` (1 MiB) mirroring `_MANIFEST_MAX_BYTES`.
  - `ReportSymlinkRefused(kind="symlink_refused", path: str)` — `O_NOFOLLOW` enforcement at read.

### Write errors — module-local discriminated union

- [ ] **AC-Err-Io-1.** `ReportIoError = Annotated[ReportWriteSymlinkRefused | ReportDiskFull | ReportPermissionDenied | ReportFilesystemRace | ReportOtherIoError, Field(discriminator="kind")]`. Each variant `frozen=True, extra="forbid"`. The manifest's `IoError` (`plugins/manifest.py:143`) is NOT reused.
- [ ] **AC-Err-Io-2.** Variant shapes carry at minimum `kind: Literal[...]`, `path: str`, `errno: int`, `message: str`. `ReportFilesystemRace` carries the same fields and corresponds to `errno.ELOOP` (symlink-replacement race). `ReportDiskFull` ↔ `errno.ENOSPC`. `ReportPermissionDenied` ↔ `errno.EACCES`. `ReportOtherIoError` is the catch-all default with `errno` preserved.

### `write` — atomic boundary

- [ ] **AC-Write-1.** `RemediationReport.write(self, path: SandboxedPath) -> Result[None, ReportIoError]` never raises. Every `OSError` is translated to the matching `ReportIoError` variant.
- [ ] **AC-Write-2.** Internally `write()` is `Ok(None)` on success / `Err(ReportIoError(...))` on failure. Built via `from codegenie.result import Ok, Err`. **No `Result.Ok(None)` classmethod exists** in the codebase.
- [ ] **AC-Write-3.** **Functional-core / imperative-shell split**:
  - `_serialize(self) -> bytes` — pure; no I/O; deterministic. Used directly by the byte-identical and `!!python/` tag absence ACs.
  - `_write_bytes(path: SandboxedPath, payload: bytes) -> Result[None, ReportIoError]` — impure; atomic write only.
- [ ] **AC-Write-4.** Atomic-write pattern: `tmp = path.parent / (path.name + f".{os.getpid()}.{secrets.token_hex(4)}.tmp")` (collision-safe across concurrent writers, mirroring `output/writer.py:128`); open with `os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW`, mode `0o600`; write; `os.fsync(fd)`; close; `os.replace(str(tmp), str(path))` (atomic on POSIX same-fs). Crash before `os.replace` leaves the original file intact; crash after leaves the new file complete.
- [ ] **AC-Write-5.** Serialization: `yaml.safe_dump(self.model_dump(mode="json"), default_flow_style=False, sort_keys=False, allow_unicode=True, width=120)` — deterministic key order matches Pydantic declaration order. **Not `pyyaml.safe_dump`** (the package name is `yaml`).
- [ ] **AC-Write-6.** **Byte-identical determinism**: writing the same `RemediationReport` instance twice produces byte-identical YAML output. `report._serialize() == report._serialize()` always; `p1.read_bytes() == p2.read_bytes()` after two writes always.
- [ ] **AC-Write-7.** **No `!!python/...` tags** in serialized output. `b"!!python" not in report._serialize()` for every Pydantic-buildable instance. (`yaml.safe_dump` does not emit them, but a future serializer leak would slip past `extra="forbid"`; an explicit assertion pins the contract.)

### `from_yaml` — smart constructor

- [ ] **AC-Load-1.** `RemediationReport.from_yaml(path: SandboxedPath) -> Result[RemediationReport, ReportLoadError]` smart constructor; never raises.
- [ ] **AC-Load-2.** **Validation order (pinned, mirrors S5-04 AC-Load-2):** symlink-refusal pre-check → file existence → size cap (≤ 1 MiB) → YAML syntax → `schema_version` pre-check (must be exactly `1`) → Pydantic schema validation. Each step maps to one `ReportLoadError` variant; subsequent steps do not run on failure.
- [ ] **AC-Load-3.** YAML file with unknown top-level key (`magic_field: true`) returns `Err(ReportSchemaViolation(path=..., field_errors=("magic_field",)))`.
- [ ] **AC-Load-4.** YAML file with `schema_version: 2` returns `Err(ReportUnknownSchemaVersion(path=..., found_version=2, supported_versions=(1,)))` — pre-Pydantic, so a malformed v2 file does NOT mask the version mismatch behind `schema_violation`.
- [ ] **AC-Load-5.** Symlink at `path` returns `Err(ReportSymlinkRefused(path=...))` *without* opening the target.
- [ ] **AC-Load-6.** File > 1 MiB returns `Err(ReportSizeCapExceeded(path=..., actual_bytes=..., cap=1048576))` *without* reading the whole file (use `os.fstat(fd).st_size` on the opened fd).

### Round-trip invariants

- [ ] **AC-Round-1.** Hand-build a `RemediationReport` instance for each of the four `RemediationOutcome` variants (`Validated`, `RequiresHumanReview`, `RemediationNotApplicable`, `RemediationFailed` — note the concrete class names; the union has no `.Variant` attributes); `write(...)` → `from_yaml(...).unwrap() == original`. Pydantic `BaseModel.__eq__` compares fields.
- [ ] **AC-Round-2.** **Partial-report happy path**: `RemediationReport(transform=None, trust_outcome=None, branch=None, outcome=RemediationNotApplicable(reason="PEER_DEP_CONFLICT"), ...)` round-trips byte-identical to itself.
- [ ] **AC-Round-3.** **Partial-report failure path** (§C1 invariant): `RemediationReport(outcome=RemediationFailed(error=RemediationError(error_id=ErrorId("io.lockfile_v1_unsupported"), message="..."), partial_report_path=None), transform=None, trust_outcome=None, branch=None, ...)` round-trips byte-identical. The orchestrator is responsible for truthful event-log paths; this story tests the schema *permits* a truthful partial report.
- [ ] **AC-Round-4.** **`outcome.kind` case-sensitivity**: a YAML with `outcome: {kind: "VALIDATED", ...}` returns `Err(ReportSchemaViolation(..., field_errors=("outcome.kind",)))` — Pydantic discriminator is case-sensitive; pinning protects Phase 5 / Phase 6 consumers from silent case drift.
- [ ] **AC-Round-5.** **`tuple` round-trip**: `files_changed` and `lockfile_policy_violations` survive write→read as the `tuple[...]` declared type, not `list[...]`. Equality via `==` confirms type fidelity.

### Golden-file convention placeholder

- [ ] **AC-Golden-1.** `tests/golden/remediation-reports/README.md` exists, explains the golden-file convention, and notes S8-02 populates the first concrete golden. ADR-0001 §Consequences names the directory by path; absence breaks the S6-06 snapshot test's fixture lookup.

### Coverage + structural

- [ ] **AC-Cov-1.** Branch coverage on `report.py` ≥ 95%.
- [ ] **AC-Struct-1.** `RemediationReport`, `ReportMetadata`, `PluginSnapshot`, `TransformSnapshot`, `ReportLoadError`, `ReportIoError` are all listed in `src/codegenie/transforms/__init__.__all__`.

## Implementation outline

1. **Co-locate `TrustOutcome` (Option A)**: add `TrustSignal` + `TrustOutcome` Pydantic models to `src/codegenie/transforms/outcomes.py` (right after the `RemediationOutcome` discriminated union). Single canonical home — mirrors the 2026-05-18 amendment's discipline for `Trusted` / `Degraded` / `Unavailable` / `AdapterConfidence`. S6-02 will re-export from `trust_scorer.py`.
2. Create `src/codegenie/transforms/report.py` with module docstring referencing ADR-0001 (Phase-5 contract surface) + ADR-0010 (domain-modeling discipline).
3. Define the `ReportLoadError` discriminated-union variants and the `ReportIoError` discriminated-union variants. Each is `frozen=True, extra="forbid"` with a `kind: Literal[...]` discriminator. The `Annotated[... | ..., Field(discriminator="kind")]` umbrellas declare the unions.
4. Define `ReportMetadata`, `PluginSnapshot`, `TransformSnapshot` as nested Pydantic models — each `extra="forbid"`, `frozen=True`. Add `field_validator`s on `ReportMetadata.started_at` and `ReportMetadata.completed_at` rejecting naive datetimes.
5. Define `RemediationReport(BaseModel)` with the field surface in the AC-Surface-3 declaration order. Add the `model_validator(mode="after")` from AC-Disc-5 enforcing outcome ↔ optional-field consistency.
6. Implement the **pure** `_serialize(self) -> bytes`:
   ```python
   def _serialize(self) -> bytes:
       return yaml.safe_dump(
           self.model_dump(mode="json"),
           default_flow_style=False, sort_keys=False,
           allow_unicode=True, width=120,
       ).encode("utf-8")
   ```
7. Implement the **impure** `_write_bytes` (atomic write with collision-safe tmp):
   ```python
   def _write_bytes(self, path: SandboxedPath, payload: bytes) -> Result[None, ReportIoError]:
       tmp = path.parent / f"{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
       try:
           fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
           try:
               os.write(fd, payload)
               os.fsync(fd)
           finally:
               os.close(fd)
           os.replace(str(tmp), str(path))
           return Ok(None)
       except OSError as e:
           # Best-effort cleanup; ignore secondary OSError on unlink.
           try:
               os.unlink(str(tmp))
           except OSError:
               pass
           return Err(_translate_oserror(path, e))
   ```
   `_translate_oserror` maps `errno.ELOOP → ReportFilesystemRace`, `errno.ENOSPC → ReportDiskFull`, `errno.EACCES → ReportPermissionDenied`, anything else → `ReportOtherIoError`.
8. `write(self, path: SandboxedPath) -> Result[None, ReportIoError]` is a one-liner: `return self._write_bytes(path, self._serialize())`.
9. `from_yaml(cls, path: SandboxedPath) -> Result[RemediationReport, ReportLoadError]` follows the AC-Load-2 ordering. Open with `os.O_RDONLY | os.O_NOFOLLOW`; on `OSError(errno=ELOOP)` return `ReportSymlinkRefused`; check `os.fstat(fd).st_size > 1 << 20` → `ReportSizeCapExceeded`; read; `yaml.safe_load(...)` (catch `yaml.YAMLError` → `ReportYamlSyntax`); pre-check `doc.get("schema_version")` → `ReportUnknownSchemaVersion` if not 1; `cls.model_validate(doc)` (catch `ValidationError` → `ReportSchemaViolation` with `field_errors = tuple(".".join(map(str, err["loc"])) for err in exc.errors())`).
10. `datetime` fields serialize via `model_dump(mode="json")` as ISO-8601 UTC strings; the `field_validator` from step 4 enforces `tzinfo is not None` at construction.
11. The `outcome: RemediationOutcome` discriminated union serializes/deserializes via Pydantic's `Field(discriminator="kind")` annotation already in place on outcomes.py:297.
12. Re-export from `src/codegenie/transforms/__init__.py`; add the new names to `__all__`.
13. Create `tests/golden/remediation-reports/README.md` with the convention note (S8-02 populates the first golden).
14. Tests (TDD plan below).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/transforms/test_remediation_report.py`. Critic-corrected against the actual kernel APIs in `codegenie.transforms.outcomes` (outcomes.py), `codegenie.result` (result.py), and `codegenie.types.identifiers` (identifiers.py).

```python
# tests/unit/transforms/test_remediation_report.py
from datetime import datetime, timezone
from pathlib import Path
import errno
import os
import secrets

import pytest
import yaml

from codegenie.result import Err, Ok
from codegenie.transforms.report import (
    RemediationReport, ReportMetadata, PluginSnapshot, TransformSnapshot,
    ReportLoadError, ReportSchemaViolation, ReportYamlSyntax,
    ReportUnknownSchemaVersion, ReportFileMissing, ReportSizeCapExceeded,
    ReportSymlinkRefused,
    ReportIoError, ReportFilesystemRace, ReportDiskFull,
    ReportPermissionDenied, ReportOtherIoError,
)
# IMPORTANT: standalone classes, NOT attributes of RemediationOutcome
from codegenie.transforms.outcomes import (
    Validated, RequiresHumanReview,
    RemediationNotApplicable, RemediationFailed,
    RemediationError,
    TrustOutcome, TrustSignal,   # co-located in outcomes.py per AC-Surface-2
)
from codegenie.transforms._forward import SandboxedPath  # currently aliases Path; S4-04 will widen
from codegenie.types.identifiers import (
    WorkflowId, CveId, PluginId, RecipeId, TransformId, TransformKind,
    BranchName, BlobDigest, SemverVersion, SignalKind, ErrorId,
)


# --- Fixtures ----------------------------------------------------------------

def _meta(**overrides) -> ReportMetadata:
    base = dict(
        workflow_id=WorkflowId("01HX0000000000000000000000"),
        cve=CveId("CVE-2024-21501"),
        repo_path="/tmp/fixture",
        started_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 17, 12, 0, 30, tzinfo=timezone.utc),
        codegenie_version="0.3.0",
    )
    base.update(overrides)
    return ReportMetadata(**base)

def _plugin(*, recipe: bool = True) -> PluginSnapshot:
    if recipe:
        return PluginSnapshot(
            plugin_id=PluginId("vulnerability-remediation--node--npm"),
            plugin_version=SemverVersion("0.1.0"),
            recipe_id=RecipeId("npm-lockfile-semver-bump"),
            recipe_version=SemverVersion("0.1.0"),
        )
    return PluginSnapshot(
        plugin_id=PluginId("vulnerability-remediation--node--npm"),
        plugin_version=SemverVersion("0.1.0"),
        recipe_id=None,
        recipe_version=None,
    )

def _transform() -> TransformSnapshot:
    return TransformSnapshot(
        transform_id=TransformId("blake3:abc123"),
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
        files_changed=("package.json", "package-lock.json"),
        diff_bytes_sha256=BlobDigest("a" * 64),
    )

def _trust_passed() -> TrustOutcome:
    return TrustOutcome(passed=True, failing=[], signals=[], confidence="high")

@pytest.fixture
def validated_report() -> RemediationReport:
    branch = BranchName("codegenie/cve-2024-21501-abc12")
    return RemediationReport(
        schema_version=1, metadata=_meta(), plugin=_plugin(),
        transform=_transform(),
        outcome=Validated(
            branch=branch,
            report_path="/tmp/r.yaml",
            passed=True,
            failing=[],
        ),
        trust_outcome=_trust_passed(),
        branch=branch,
        event_log_internal_path="events/internal/01HX....jsonl.zst",
        event_log_spanning_path="events/spanning/append.jsonl.zst",
        spanning_chain_head=BlobDigest("b" * 64),
        lockfile_policy_violations=(),
    )


# --- Round-trip — four outcome variants -------------------------------------

def test_round_trip_validated(tmp_path: Path, validated_report: RemediationReport) -> None:
    p = SandboxedPath(tmp_path / "r.yaml")
    result = validated_report.write(p)
    assert isinstance(result, Ok)
    loaded = RemediationReport.from_yaml(p)
    assert isinstance(loaded, Ok)
    assert loaded.unwrap() == validated_report

def test_round_trip_not_applicable(tmp_path: Path) -> None:
    r = RemediationReport(
        schema_version=1, metadata=_meta(), plugin=_plugin(recipe=False),
        transform=None,
        outcome=RemediationNotApplicable(reason="PEER_DEP_CONFLICT"),
        trust_outcome=None, branch=None,
        event_log_internal_path="events/internal/x.jsonl.zst",
        event_log_spanning_path="events/spanning/append.jsonl.zst",
        spanning_chain_head=BlobDigest("c" * 64),
    )
    p = SandboxedPath(tmp_path / "r.yaml")
    assert isinstance(r.write(p), Ok)
    assert RemediationReport.from_yaml(p).unwrap() == r

def test_round_trip_failed_partial_report(tmp_path: Path) -> None:
    err = RemediationError(
        error_id=ErrorId("io.lockfile_v1_unsupported"),
        message="lockfile schema v1 not supported by NpmLockfileRecipeEngine",
    )
    r = RemediationReport(
        schema_version=1, metadata=_meta(), plugin=_plugin(recipe=False),
        transform=None,
        outcome=RemediationFailed(error=err, partial_report_path=None),
        trust_outcome=None, branch=None,
        event_log_internal_path="events/internal/partial.jsonl.zst",
        event_log_spanning_path="events/spanning/append.jsonl.zst",
        spanning_chain_head=BlobDigest("d" * 64),
    )
    p = SandboxedPath(tmp_path / "r.yaml")
    assert isinstance(r.write(p), Ok)
    assert RemediationReport.from_yaml(p).unwrap() == r

def test_round_trip_requires_human_review(tmp_path: Path) -> None:
    r = RemediationReport(
        schema_version=1, metadata=_meta(), plugin=_plugin(recipe=False),
        transform=None,
        outcome=RequiresHumanReview(reason="no_concrete_match", handoff_path=None),
        trust_outcome=None, branch=None,
        event_log_internal_path="events/internal/hr.jsonl.zst",
        event_log_spanning_path="events/spanning/append.jsonl.zst",
        spanning_chain_head=BlobDigest("e" * 64),
    )
    p = SandboxedPath(tmp_path / "r.yaml")
    assert isinstance(r.write(p), Ok)
    assert RemediationReport.from_yaml(p).unwrap() == r


# --- Determinism ------------------------------------------------------------

def test_yaml_byte_identical_on_repeated_write(tmp_path: Path, validated_report: RemediationReport) -> None:
    p1, p2 = SandboxedPath(tmp_path / "a.yaml"), SandboxedPath(tmp_path / "b.yaml")
    assert isinstance(validated_report.write(p1), Ok)
    assert isinstance(validated_report.write(p2), Ok)
    assert p1.read_bytes() == p2.read_bytes()

def test_serialize_is_pure_and_byte_stable(validated_report: RemediationReport) -> None:
    # AC-Write-3 / AC-Write-6 — _serialize is pure; same instance => same bytes always.
    a = validated_report._serialize()
    b = validated_report._serialize()
    assert a == b

def test_no_python_tags_in_serialized_output(validated_report: RemediationReport) -> None:
    # AC-Write-7 — defensive: yaml.safe_dump shouldn't emit !!python tags;
    # explicit assertion locks the contract against future serializer leaks.
    assert b"!!python" not in validated_report._serialize()

def test_write_read_write_byte_identical(tmp_path: Path, validated_report: RemediationReport) -> None:
    # T-8 — metamorphic round-trip: write -> read -> write produces identical bytes.
    p1 = SandboxedPath(tmp_path / "r1.yaml")
    assert isinstance(validated_report.write(p1), Ok)
    loaded = RemediationReport.from_yaml(p1).unwrap()
    p2 = SandboxedPath(tmp_path / "r2.yaml")
    assert isinstance(loaded.write(p2), Ok)
    assert p1.read_bytes() == p2.read_bytes()


# --- Load-error variants ----------------------------------------------------

def test_file_missing(tmp_path: Path) -> None:
    result = RemediationReport.from_yaml(SandboxedPath(tmp_path / "nope.yaml"))
    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportFileMissing)

def test_yaml_syntax_error(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("schema_version: 1\nmetadata: {workflow_id:")  # truncated
    result = RemediationReport.from_yaml(SandboxedPath(p))
    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportYamlSyntax)

def test_extra_field_rejected(tmp_path: Path, validated_report: RemediationReport) -> None:
    p = SandboxedPath(tmp_path / "r.yaml")
    validated_report.write(p).unwrap()
    doc = yaml.safe_load(p.read_bytes())
    doc["magic_field"] = True
    hostile = tmp_path / "hostile.yaml"
    hostile.write_text(yaml.safe_dump(doc))
    result = RemediationReport.from_yaml(SandboxedPath(hostile))
    assert isinstance(result, Err)
    err = result.unwrap_err()
    assert isinstance(err, ReportSchemaViolation)
    assert "magic_field" in err.field_errors

def test_unknown_schema_version_pre_pydantic(tmp_path: Path, validated_report: RemediationReport) -> None:
    # AC-Load-4 — version check runs BEFORE Pydantic schema validation.
    p = SandboxedPath(tmp_path / "r.yaml")
    validated_report.write(p).unwrap()
    doc = yaml.safe_load(p.read_bytes())
    doc["schema_version"] = 2
    # Also corrupt another field to prove version-check wins ordering:
    doc["plugin"]["plugin_id"] = ""  # would normally be a schema_violation
    v2 = tmp_path / "v2.yaml"
    v2.write_text(yaml.safe_dump(doc))
    result = RemediationReport.from_yaml(SandboxedPath(v2))
    assert isinstance(result, Err)
    err = result.unwrap_err()
    assert isinstance(err, ReportUnknownSchemaVersion)
    assert err.found_version == 2
    assert err.supported_versions == (1,)

def test_size_cap_exceeded(tmp_path: Path) -> None:
    # AC-Load-6 — 1 MiB cap on input.
    p = tmp_path / "big.yaml"
    p.write_bytes(b"schema_version: 1\nfiller: " + b"x" * (1 << 20))
    result = RemediationReport.from_yaml(SandboxedPath(p))
    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportSizeCapExceeded)

def test_symlink_refused(tmp_path: Path, validated_report: RemediationReport) -> None:
    real = tmp_path / "real.yaml"
    validated_report.write(SandboxedPath(real)).unwrap()
    link = tmp_path / "link.yaml"
    link.symlink_to(real)
    result = RemediationReport.from_yaml(SandboxedPath(link))
    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportSymlinkRefused)

def test_outcome_kind_case_sensitive(tmp_path: Path, validated_report: RemediationReport) -> None:
    # AC-Round-4 — Pydantic discriminator is case-sensitive; "VALIDATED" fails.
    p = SandboxedPath(tmp_path / "r.yaml")
    validated_report.write(p).unwrap()
    doc = yaml.safe_load(p.read_bytes())
    doc["outcome"]["kind"] = "VALIDATED"
    hostile = tmp_path / "case.yaml"
    hostile.write_text(yaml.safe_dump(doc))
    result = RemediationReport.from_yaml(SandboxedPath(hostile))
    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportSchemaViolation)


# --- Outcome ↔ optional-field invariant (AC-Disc-5) -------------------------

def test_validated_outcome_requires_transform_and_branch() -> None:
    with pytest.raises(ValueError, match="validated"):
        RemediationReport(
            schema_version=1, metadata=_meta(), plugin=_plugin(),
            transform=None,  # invariant violation
            outcome=Validated(
                branch=BranchName("b"), report_path="/x", passed=True, failing=[]),
            trust_outcome=_trust_passed(), branch=BranchName("b"),
            event_log_internal_path="x", event_log_spanning_path="y",
            spanning_chain_head=BlobDigest("0" * 64),
        )

def test_failed_outcome_requires_branch_none() -> None:
    with pytest.raises(ValueError, match="failed"):
        RemediationReport(
            schema_version=1, metadata=_meta(), plugin=_plugin(recipe=False),
            transform=None,
            outcome=RemediationFailed(
                error=RemediationError(
                    error_id=ErrorId("io.x"), message="m"),
                partial_report_path=None),
            trust_outcome=None,
            branch=BranchName("should-be-None"),  # invariant violation
            event_log_internal_path="x", event_log_spanning_path="y",
            spanning_chain_head=BlobDigest("0" * 64),
        )


# --- Datetime discipline (AC-Disc-4) ----------------------------------------

def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        ReportMetadata(
            workflow_id=WorkflowId("01HX0000000000000000000000"),
            cve=CveId("CVE-2024-21501"), repo_path="/x",
            started_at=datetime(2026, 5, 17, 12, 0),  # naive!
            completed_at=datetime(2026, 5, 17, 12, 0, 30, tzinfo=timezone.utc),
            codegenie_version="0.3.0",
        )


# --- Atomic write (AC-Write-4) ----------------------------------------------

def test_atomic_write_no_partial_on_replace_failure(
    tmp_path: Path, validated_report: RemediationReport, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Patch the module-resolved reference, not top-level os.replace, so the
    # patch hits the actual call site (T-6).
    p = SandboxedPath(tmp_path / "r.yaml")
    p.write_text("PREVIOUS_CONTENT\n")
    boom_errno = errno.EACCES

    def boom(src: str, dst: str) -> None:
        raise OSError(boom_errno, "synthetic permission denied")

    monkeypatch.setattr("codegenie.transforms.report.os.replace", boom)
    result = validated_report.write(p)
    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportPermissionDenied)
    # Original content preserved; no partial overwrite.
    assert p.read_text() == "PREVIOUS_CONTENT\n"
    # Tmp shadow cleaned up.
    assert not any(child.name.endswith(".tmp") for child in tmp_path.iterdir())

def test_disk_full_translation(
    tmp_path: Path, validated_report: RemediationReport, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(src: str, dst: str) -> None:
        raise OSError(errno.ENOSPC, "no space")
    monkeypatch.setattr("codegenie.transforms.report.os.replace", boom)
    result = validated_report.write(SandboxedPath(tmp_path / "r.yaml"))
    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportDiskFull)


# --- Tuple round-trip (AC-Round-5) ------------------------------------------

def test_files_changed_tuple_round_trips(tmp_path: Path, validated_report: RemediationReport) -> None:
    p = SandboxedPath(tmp_path / "r.yaml")
    validated_report.write(p).unwrap()
    loaded = RemediationReport.from_yaml(p).unwrap()
    assert isinstance(loaded.transform.files_changed, tuple)
    assert loaded.transform.files_changed == ("package.json", "package-lock.json")
```

Run; confirm `ImportError` (then `AttributeError`, then `ValidationError`s); commit Red; implement Green.

### Green — make it pass

- Implement `transforms/outcomes.py`'s `TrustSignal` + `TrustOutcome` additions (Option A canonical home).
- Implement nested models in field-by-field correspondence; each carries `model_config = ConfigDict(frozen=True, extra="forbid")`.
- Field validators on `ReportMetadata.started_at` + `completed_at` raise `ValueError("started_at must be timezone-aware")` if `tzinfo is None`.
- `model_validator(mode="after")` on `RemediationReport` enforces the AC-Disc-5 invariants; messages embed `outcome.kind` so the test regex matches.
- `_serialize()` and `_write_bytes()` split per AC-Write-3.
- `_translate_oserror(path, exc) -> ReportIoError` dispatches on `exc.errno`.
- `from_yaml`: open with `O_RDONLY | O_NOFOLLOW`; on `ELOOP` → `ReportSymlinkRefused`; `os.fstat(fd).st_size > 1<<20` → `ReportSizeCapExceeded` (do NOT read past the cap); read; `yaml.safe_load`; pre-check `schema_version`; `cls.model_validate(...)`; render Pydantic `loc` tuples to dotted strings.

### Refactor — clean up

- Confirm `model_dump(mode="json")` emits ISO-8601 UTC datetimes with no microsecond drift across the round-trip (tests already pin via `==`; if a future Pydantic minor flips the rendering, the round-trip catches it).
- Confirm `yaml.safe_load` does not silently coerce numeric `schema_version` to `bool` or `str` — the pre-check uses `doc.get("schema_version") == 1` with `isinstance(...) == int`.
- The `__all__` list in `transforms/__init__.py` + the declaration order of `RemediationReport`'s fields are part of the S6-06 snapshot. Treat both as load-bearing.
- Re-confirm the `outcome.kind` literal values match Phase 5's expectations (`"validated"`, `"requires_human_review"`, `"not_applicable"`, `"failed"`) — outcomes.py:250/269/281/292 confirm these are the registered discriminator literals; Phase 5 inheritance is preserved.
- Run `pytest tests/unit/transforms/test_remediation_report.py -v` + `mypy --strict src/codegenie/transforms/report.py` + `ruff check`. Verify branch coverage on `report.py` ≥ 95% via `pytest --cov=codegenie.transforms.report --cov-report=term-missing`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/report.py` | New — `RemediationReport` + nested snapshots + `_serialize` / `_write_bytes` / `write` / `from_yaml` + `ReportLoadError` + `ReportIoError` discriminated unions |
| `src/codegenie/transforms/outcomes.py` | Additive — declare `TrustSignal` + `TrustOutcome` here (Option A canonical home; S6-02 re-exports from `trust_scorer.py`) |
| `tests/unit/transforms/test_remediation_report.py` | New — round-trip for all four outcome variants, partial reports, atomic write with errno translation, byte-identical determinism (`_serialize` purity + repeated-write + write→read→write metamorphic), `!!python/` tag absence, schema-version + extra-field + symlink + size-cap rejection, case-sensitivity on outcome.kind, outcome ↔ optional-field invariant, naive-datetime rejection, tuple-vs-list round-trip |
| `src/codegenie/transforms/__init__.py` | Add `RemediationReport`, `ReportMetadata`, `PluginSnapshot`, `TransformSnapshot`, `ReportLoadError`, `ReportIoError`, `TrustSignal`, `TrustOutcome` to `__all__` (ADR-0001 export-list fence) |
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
- **Outcome-variant import discipline (load-bearing)**: `Validated`, `RequiresHumanReview`, `RemediationNotApplicable`, `RemediationFailed`, `RemediationError`, `TrustOutcome`, `TrustSignal` are *standalone classes* in `codegenie.transforms.outcomes`. There is no `RemediationOutcome.Validated(...)` dot-access — `RemediationOutcome` is the `Annotated[... | ..., Field(discriminator="kind")]` umbrella alias, not a class. The variant constructors take **all** required fields (e.g., `Validated` requires `branch, report_path, passed, failing` with the `passed iff len(failing)==0` invariant from outcomes.py:256-260).
- **`Result` API**: `from codegenie.result import Ok, Err, Result`. Constructors are `Ok(value=...)` and `Err(error=...)` — module-level Pydantic models. The classmethod / static-method pattern (`Result.Ok(None)`) does not exist. `is_ok` is a *method* (`result.is_ok()`), not a property. For typed narrowing in tests, prefer `isinstance(result, Ok)` / `isinstance(result, Err)` so the next line gets the right type.
- **Load- and write-errors are module-local discriminated unions** — `ReportLoadError` and `ReportIoError` live in `transforms/report.py`. The canonical `codegenie.types.errors.ParseError` stays untouched (its `frozen=True, extra="forbid"` shape is `message: str, value: str` only — extending it requires an ADR-0010 amendment). The S5-04 `PolicyLoadError` is the precedent to mirror. The manifest's `IoError` (`plugins/manifest.py:143`) is NOT reused — it belongs to the `ManifestError` union and reusing it across modules couples unrelated concerns.
- **`TrustOutcome` canonical home decision**: this story declares `TrustSignal` + `TrustOutcome` in `transforms/outcomes.py` (Option A). S6-02's `trust_scorer.py` re-exports the same class objects (identity equality across both layers). This mirrors the 2026-05-18 amendment that put `Trusted` / `Degraded` / `Unavailable` in `outcomes.py` and made `adapters/confidence.py` a re-export. If a reviewer prefers Option B (move `TrustOutcome` to S6-02, add S6-02 to `Depends on:`), surface that as an explicit comment in the PR — both options are correct; we picked A for the absence of forward-reference fragility.
- **`SandboxedPath` is currently `pathlib.Path` (forward shim, `transforms/_forward.py:39`)**: S4-04 substitutes the real `O_NOFOLLOW`-jailed type. Tests pass `pathlib.Path` instances through the `SandboxedPath` alias today; the imports stay stable when S4-04 lands. The `_write_bytes` implementation should use `os.open(..., O_NOFOLLOW)` *now* (the shim type accepts any `Path`) so the substitution is purely structural.
- **`schema_version: Literal[1]` is the contract pin**: the snapshot test S6-06 will pin every field name; the `schema_version` lets us version the *whole schema* deliberately. Phase 7 adding a variant to the `lockfile_policy_violations` discriminated union does NOT bump the version (extension by addition); Phase 9 adding a top-level `cost: dict` for the cost ledger DOES bump (semantically a different consumer contract). Document the bump policy in the model docstring.
- **`extra="forbid"` is load-bearing**: ADR-0001 §Tradeoffs row 4: "Schema rigidity — Pydantic `extra="forbid"` means Phase 5 cannot quietly add fields; every addition is a contract amendment." This is a feature: the snapshot test S6-06 catches drift.
- **Atomic write via tmp+rename**: standard POSIX pattern. `os.replace(tmp, path)` is atomic on the same filesystem; the collision-safe tmp name (pid + token_hex) follows `output/writer.py:128` so two concurrent gather/remediate processes do not collide. `tmp.parent == path.parent` is a sanity-check assertion before the rename.
- **`!!python/` tag absence is a runtime contract** (not just refactor hygiene): if a future serializer leak emits `!!python/...` tags, the YAML becomes Python-only-parseable and `from_yaml` (which uses `yaml.safe_load`) breaks. AC-Write-7 pins it as a runtime assertion on `_serialize()`'s output.
- **`__all__` list and field-declaration order are load-bearing for S6-06**: the snapshot test will pin both. A post-S5-05 reorder of `RemediationReport`'s fields, or a quiet addition to `__all__`, is a contract break — Phase 5 cannot land.
- **What Phase 5 reads**: per `docs/phases/05-sandbox-trust-gates/`, Phase 5 reads `trust_outcome.passed`, `trust_outcome.confidence`, `trust_outcome.failing`, and `outcome.kind`. If Phase 5's `phase-arch-design.md` reveals additional fields, surface here (Rule 8) — add them in S5-05, not in Phase 5.
- **`_atomic_write_bytes` extraction deferred** (Rule 2 — three similar lines beats premature abstraction): the codebase has one existing atomic-write site at `output/writer.py:116-135`. This story creates the second. When a third site emerges (likely the S6-04 orchestrator's branch writer), extract to `codegenie._io.atomic_write_bytes` and update both consumers. Add a `_lessons.md` marker if available.
- **Hand-built instance test is the load-bearing one**: the High-level-impl `Done criteria` line 6 says explicitly "round-trips a hand-built `RemediationReport` instance". Name the test `test_round_trip_validated` (and analogues for the other three variants) so the criterion-to-test mapping is obvious in CI logs.
- **Mypy is the newtype gate, not runtime**: `WorkflowId = NewType("WorkflowId", str)` has no runtime validator. The original "newtype enforcement at construction" test was over-promised. Discipline is enforced by `mypy --strict` (CLAUDE.md "Newtype identifiers" + ADR-0010 §Tradeoffs) — a swap between `WorkflowId` and `BundleId` is a mypy error at the call site, but `ReportMetadata(workflow_id="not-a-ulid", ...)` passes at runtime. If a future story needs runtime validation, add a smart-constructor `parse_workflow_id(s) -> Result[WorkflowId, ParseError]` (mirroring `parse_plugin_id` in `types/parsers.py`) — that's a separate concern.
