# Validation report — S5-05 `RemediationReport` Pydantic model + writer

**Story:** `docs/phases/03-vuln-deterministic-recipe/stories/S5-05-remediation-report-writer.md`
**Validated at:** 2026-05-19
**Verdict:** **HARDENED** — many real, fixable defects against existing kernel APIs; edits applied in place.

## Context brief

S5-05 ships `src/codegenie/transforms/report.py` (`RemediationReport` Pydantic model + `write` / `from_yaml`) — one of the six Phase-3 contract symbols ADR-0001 freezes. The story is consumed by:

- S6-04 (orchestrator calls `report.write(...)` on every exit path, including failure)
- S6-06 (snapshot-pins the schema; failure ⇒ Phase 5 cannot ship)
- S8-02 (end-to-end golden file)

Phase 5 reads `trust_outcome.passed`, `trust_outcome.confidence`, `trust_outcome.failing`, `outcome.kind` from this artifact.

## Drift against the kernel — what the story prescribed vs. what landed

| # | Story prescribed | Actually shipped (verified) |
|---|---|---|
| 1 | `RemediationOutcome.Validated(...)`, `.NotApplicable(...)`, `.Failed(...)` (dot-access on the `Annotated` union) | `Validated`, `RequiresHumanReview`, `RemediationNotApplicable`, `RemediationFailed` are standalone classes in `src/codegenie/transforms/outcomes.py:242,263,274,285` — there are no `.Variant` attributes on the discriminated union |
| 2 | `RemediationOutcome.Failed(error={"reason": "lockfile_v1_unsupported"})` (raw dict for `error`) | `RemediationFailed.error: RemediationError` — typed Pydantic model with `error_id: ErrorId, message: str, details: dict[str, primitives] \| None` (outcomes.py:155, 285) |
| 3 | `Validated(branch=..., report_path="/tmp/r.yaml")` (only two fields) | `Validated(branch, report_path, passed, failing)` — `passed` + `failing` are required and constrained by a `model_validator` `_passed_iff_no_failing` (outcomes.py:242-260) |
| 4 | `Result.Ok(None)` / `Result.Err(IoError(...))` (static-method API) | `from codegenie.result import Ok, Err, Result` — `Ok(value=...)` and `Err(error=...)` are module-level Pydantic models (result.py:40, 60). No `Result.Ok` / `Result.Err` classmethods exist |
| 5 | `assert result.is_ok` (property access) | `is_ok` is a `def is_ok(self) -> bool` method (result.py:47, 67) — must be called: `result.is_ok()` |
| 6 | `ParseError(reason="schema_violation", field="magic_field")` | Canonical `ParseError` (types/errors.py:25) is `frozen=True, extra="forbid"` with **only** `message: str` + `value: str`. No `reason` / `field` fields exist. **This is the same drift S5-04 caught (S5-04 validation report, item 1).** Adding fields requires an ADR-0010 amendment |
| 7 | `Result.Err(IoError(reason="filesystem_race"\|"disk_full"\|"permission_denied", path=...))` | Canonical `IoError` (plugins/manifest.py:143) is part of the `ManifestError` discriminated union with shape `kind: Literal["io_error"], path: Path, errno: int, message: str` — no `reason` field |
| 8 | `from codegenie.transforms.trust_scorer import TrustOutcome` | `trust_scorer.py` is shipped by **S6-02**, not S5-05. The story declares `Depends on: S5-01` but the import on line 134 of the TDD-plan test would fail at story-execution time |
| 9 | `test_newtypes_enforced_at_construction` asserts `ReportMetadata(workflow_id="not-a-ulid", ...)` raises `ValidationError` | `WorkflowId = NewType("WorkflowId", str)` (types/identifiers.py:70) has **no runtime check** — passing a raw str succeeds at construction. The "newtype enforcement" is a `mypy --strict` discipline only, per CLAUDE.md "newtype identifiers" + ADR-0010 §Tradeoffs |
| 10 | `tmp = path.with_suffix(path.suffix + ".tmp")` | `Path.with_suffix` requires a single-component suffix; appending makes a multi-dot suffix (`.yaml.tmp`) — silently truncates or raises depending on input. Established precedent at output/writer.py:128 uses `dest.with_suffix(dest.suffix + f".{os.getpid()}.{_secrets.token_hex(4)}.tmp")` plus a `with_suffix` that the writer treats opaquely. Safer: `path.parent / (path.name + ".tmp")` |

## Critic findings

### Coverage critic — `block` / `harden`

- **C-1 (block).** `Validated` requires `passed: bool` + `failing: list[SignalKind]` with a `passed iff len(failing)==0` invariant. The AC field surface for the report does not require these to be reflected, but the constructor call in the TDD plan omits them — every round-trip test would fail at instance construction. Either: (a) update the fixtures to include `passed=True, failing=[]`; (b) clarify that the report stores the *flat* `Validated` instance, including the embedded `passed` / `failing` (the architecture's data-model snippet on line 826-830 of `phase-arch-design.md` already confirms this).
- **C-2 (harden).** Missing AC: **naive `datetime` is rejected.** Refactor section mentions it but no AC pins it. Without an explicit field-validator, an orchestrator bug that emits `datetime.utcnow()` instead of `datetime.now(timezone.utc)` ships an ambiguous timestamp into the golden file (S8-02 would silently drift).
- **C-3 (harden).** Missing AC: **YAML output contains no `!!python/...` tags.** Refactor section mentions it but no AC enforces it. A future `model_dump` change that surfaces a Python-typed value would slip past `extra="forbid"` and turn the human-facing artifact into Python-only-parseable. Already pre-empted by `yaml.safe_dump`, but a runtime regression on a custom serializer leak deserves a one-line `b"!!python" not in p.read_bytes()` AC.
- **C-4 (harden).** Missing AC: **bounded input on `from_yaml`** — `PluginManifest.from_yaml` caps at 1 MiB (manifest.py:99 `_MANIFEST_MAX_BYTES`). Reports are larger on average but still bounded; a 100 MiB report should be a `SchemaViolation` / size-cap variant, not a memory blow-up.
- **C-5 (harden).** Missing AC: **outcome-kind ↔ optional-field consistency.** The model permits `outcome.kind == "validated"` with `transform=None` / `branch=None`. The story acknowledges partial reports on failure paths, but the *Validated* case has stricter invariants: `Validated` implies a transform was applied and a branch was created. Without a `model_validator`, an orchestrator bug shipping `Validated` + `transform=None` is admitted by the schema and downstream consumers (Phase 5) see structurally-impossible state.
- **C-6 (harden).** Missing AC: **`outcome.kind == "failed"` requires `partial_report_path`-consistent `event_log_*` paths.** §C1 promises "Never silently catches"; the partial-report-failure test confirms the schema *permits* a truthful partial, but does not assert that the orchestrator's contract (truthful path or `None`) is encoded.
- **C-7 (nit).** Missing AC: **`tuple` round-trip stability** — Pydantic + YAML serializes tuples as sequences; on re-parse the type-annotated `tuple[str, ...]` is reconstructed, but a careless `list[str]` annotation would break equality. Worth a one-line AC: "`files_changed` round-trips as `tuple`, not `list`."
- **C-8 (nit).** Missing AC: **`schema_version` rejection happens before Pydantic schema validation**, mirroring the S5-04 `LockfilePolicy` precedent (AC-Load-2 in S5-04 pins validation order). Otherwise an `extra="forbid"` failure on a malformed v2 file masks the `unknown_schema_version` reason.

### Test-quality critic — `block` / `harden`

- **T-1 (block).** Every test that builds an outcome variant uses non-existent `RemediationOutcome.Validated(...)` / `.NotApplicable(...)` / `.Failed(...)` syntax. Import the standalone classes (`Validated`, `RemediationNotApplicable`, `RemediationFailed`, `RequiresHumanReview`) from `codegenie.transforms.outcomes`. **Without this fix every test fails at collection time, not at red-step.**
- **T-2 (block).** `RemediationFailed(error={"reason": "lockfile_v1_unsupported"})` — `error` must be a `RemediationError` instance, not a dict: `RemediationError(error_id=ErrorId("io.lockfile_v1_unsupported"), message="...")`.
- **T-3 (block).** `assert validated_report.write(p).is_ok` is wrong on two counts: (a) `is_ok` is a method, not a property — `.is_ok()`; (b) the value-equality pattern that actually catches mutations is `assert isinstance(result, Ok)` (typed) rather than `result.is_ok()` (boolean) — the typed check buys narrowing for the next line.
- **T-4 (block).** `test_round_trip_requires_human_review` is a stub: `RemediationReport(...)` with literal ellipsis. Must be filled in or it tests nothing.
- **T-5 (block).** `test_newtypes_enforced_at_construction` will fail — `WorkflowId = NewType("WorkflowId", str)` has no runtime check; the test as written is over-promised. Replace with the mypy-discipline note in `Notes for implementer`, or upgrade `WorkflowId` to a smart-constructor type via a separate story (out of scope here).
- **T-6 (harden).** `test_atomic_write_no_partial_on_crash` patches `os.replace` as a module attribute — but if `report.py` does `from os import replace` (uncommon) or imports `os` as the module (common), the monkeypatch target should be `codegenie.transforms.report.os.replace` so the patch hits the actual reference the function resolves. Use `monkeypatch.setattr("codegenie.transforms.report.os.replace", boom)`.
- **T-7 (harden).** `pyyaml.safe_dump` is imported as `yaml.safe_dump` everywhere else in the codebase (`output/writer.py:57`). The story's `import yaml` is fine; the `pyyaml.safe_dump(...)` reference in the Implementation outline's serialization snippet should read `yaml.safe_dump(...)`.
- **T-8 (harden).** Missing property/metamorphic test for **write→read→write byte equality**: not just `p1 == p2` from two adjacent writes, but also `write(write(read(write(report))))` produces the same bytes — the S8-02 golden file is replay-derived; if the writer is not idempotent under the full round-trip, the golden churns on every CI run.
- **T-9 (harden).** Missing **adversarial round-trip for the dispatch boundary**: a YAML doc with the wrong `outcome.kind` value (e.g., `"VALIDATED"` uppercase) should yield `schema_violation`, not a silent fallback variant; Pydantic's discriminator strictness covers this but a dedicated test pins the contract for Phase 5 / Phase 6 consumers.

### Consistency critic — `block` / `harden`

- **K-1 (block).** ADR-0001 §Consequences: "Phase 3 ships the `remediation-report.yaml` schema and ships with golden-file tests under `tests/golden/remediation-reports/`." The story files-to-touch list adds `tests/golden/remediation-reports/README.md` — that's correct, but missing is a **fence test** that the `tests/golden/remediation-reports/` directory exists and is read by S8-02. Without a directory marker the snapshot test for S6-06 won't find a fixture.
- **K-2 (block).** ADR-0010 §Consequences: "every Pydantic model in `src/codegenie/{plugins,transforms}/` uses `model_config = ConfigDict(frozen=True, extra="forbid")`." The story's `PluginSnapshot`, `TransformSnapshot`, `ReportMetadata`, `RemediationReport` must all carry this — currently called out only on `RemediationReport`. Add it to every nested model AC.
- **K-3 (block).** ADR-0010 + `tests/fence/test_no_any_in_plugin_surface.py` ban `dict[str, Any]` under `src/codegenie/transforms/`. The story's field surface is `Any`-free, but **`RemediationError.details: dict[str, str | int | bool | float] | None`** rides into the report via `Failed.error.details` — the story should call this out as a deliberate boundary (the dict is shape-typed-primitives, ADR-0010-compliant). Otherwise a reviewer adding `details: dict[str, Any]` later breaks the fence silently.
- **K-4 (block).** TrustOutcome forward-reference: Phase 3 arch §C6 (line 574) declares `TrustOutcome` lives in `src/codegenie/transforms/trust_scorer.py` (S6-02). S5-05 ships before S6-02. Options:
  - **(a)** Move `TrustOutcome` declaration to `src/codegenie/transforms/outcomes.py` (this file already owns every other outcome union). Re-export from `trust_scorer.py` for symmetry with the `adapters.confidence` re-export precedent (ADR-0010 Amendment 2026-05-18).
  - **(b)** Add `S6-02` to `Depends on:` and accept that S5-05 cannot ship before S6-02.
  - **(c)** Use a `TYPE_CHECKING` forward reference + `model_rebuild()` at S6-02 import time — fragile (`model_rebuild` after registration is an antipattern; failed model imports surface at first construction).
  - **Recommendation: (a).** It mirrors the established `transforms.outcomes` single-canonical-home discipline (Amendment 2026-05-18) and removes the cross-story import cycle. Story should declare `TrustOutcome` + `TrustSignal` itself (kernel home), with S6-02 layering the `TrustScorer.score()` consumer on top.
- **K-5 (harden).** ADR-0001 §Consequences names "the snapshot test S6-06" — the story correctly defers the snapshot to S6-06 in Out of scope, but should add a `Notes-for-implementer` line: "The `__all__` list and the field declaration order are part of the snapshot S6-06 will pin — any post-S5-05 reorder is a contract break."
- **K-6 (harden).** CLAUDE.md "YAML for the human-facing artifact" + "Newtype identifiers" — both honored. No conflict.
- **K-7 (harden).** Story prescribes `path.with_suffix(path.suffix + ".tmp")` (Implementation outline §4). Established precedent at `output/writer.py:128` proves this *works* for single-suffix paths but creates an unsafe multi-suffix path. Align to `path.parent / (path.name + ".tmp")` or copy the `output/writer.py:128` exact pattern (suffix + pid + token_hex + .tmp).

### Design-patterns critic — `harden`

- **D-1 (harden).** **Smart constructor pattern not applied to load errors.** The story uses the canonical `ParseError` shape (which it can't, per K-1 / item 6 of the drift table). The S5-04 precedent (`PolicyLoadError` discriminated union with `PolicyFileMissing | PolicyYamlSyntax | PolicySchemaViolation | PolicyUnknownSchemaVersion | PolicyEmptyAllowlist | PolicyInvalidRegistryUrl`) is the established pattern. **Mirror it:** declare a module-local `ReportLoadError` discriminated union with at least `ReportFileMissing`, `ReportYamlSyntax`, `ReportSchemaViolation`, `ReportUnknownSchemaVersion`, `ReportSizeCapExceeded`, `ReportSymlinkRefused`. `from_yaml` returns `Result[RemediationReport, ReportLoadError]`. This is Phase-3's documented load-error idiom; using anything else forks the convention.
- **D-2 (harden).** **Write errors: same pattern.** A module-local `ReportIoError` discriminated union (`SymlinkRefused | DiskFull | PermissionDenied | FilesystemRace | OtherIoError`) instead of trying to reuse the manifest's `IoError`. The manifest's `IoError` is part of the *manifest* loader's discriminated union and re-exporting it from `transforms.report` couples two unrelated concerns. Story should declare its own `ReportIoError`.
- **D-3 (harden).** **Make illegal states unrepresentable.** `Validated` outcome implies `branch != None` and `transform != None` (a Validated run, by definition, produced a transform and a branch). Currently the schema admits `outcome=Validated(...)` + `transform=None`. A `model_validator(mode="after")` on `RemediationReport` that asserts `(outcome.kind == "validated") ⇒ (transform is not None and branch is not None)` and `(outcome.kind in {"failed", "not_applicable"}) ⇒ (branch is None)` closes the door.
- **D-4 (nit).** **Open/Closed across phases.** The schema is `extra="forbid"` (closed); Phase 7's additive widening (e.g., `lockfile_policy_violations` widening from one variant to two) is admitted because the field's type is a discriminated union — *not* because the model is open. The story should clarify this in `Notes for the implementer`: extension is by adding variants to discriminated-union fields, never by editing `RemediationReport`'s field list (ADR-0001 freeze).
- **D-5 (nit).** **Functional core / imperative shell.** The `write` method mixes serialization (pure) with I/O (impure). Split into a pure `_serialize(self) -> bytes` (testable without a filesystem; supports the byte-identical determinism AC) and an impure `_write_bytes(path, payload) -> Result[None, ReportIoError]` (the atomic-write boundary). The S8-02 golden replay benefits from being able to call `_serialize` in isolation.
- **D-6 (nit).** **Adapter / facade vs. method.** `RemediationReport.write(path)` is fine — the alternative (a standalone `write_report(report, path) -> Result`) buys nothing here (one call site, one symbol). Rule-2 / Rule-3: keep it as a method.
- **D-7 (harden).** **Reuse the established `_atomic_write_bytes` chokepoint?** `output/writer.py:116-135` already implements `tmp → fsync → os.replace`. Extracting it to a shared `codegenie._io.atomic_write_bytes` would deduplicate, but couples `transforms/` to a new module and would need an ADR amendment to the structural defense tests (per-submodule cold-start). **Defer; copy the implementation.** Three similar lines beats premature abstraction (Rule 2). Mark a `_lessons.md` candidate: when a third writer needs the same pattern, extract.

## Researcher findings (Stage 3)

No critic finding tagged `NEEDS RESEARCH`. Every issue is resolvable with codebase precedents (S5-04 `PolicyLoadError`, `plugins/manifest.py` `ManifestError`, `output/writer.py` `_atomic_write_bytes`, `transforms/outcomes.py` variant shapes). Stage 3 skipped.

## Edits applied (summary)

1. **Validation notes block** added after the story header.
2. **Dependencies** widened: add `S6-02` annotation (or relocate `TrustOutcome` to `outcomes.py` — recommended option). Story records both, leaves the choice as an explicit `Open question` in `Notes for the implementer`.
3. **Acceptance criteria:**
   - All outcome-variant references use the correct standalone class names (`Validated`, `RemediationNotApplicable`, `RemediationFailed`, `RequiresHumanReview`).
   - `Validated` instances require `passed: bool` and `failing: list[SignalKind]` (Pydantic invariant from outcomes.py).
   - `RemediationFailed.error` is `RemediationError` (typed model), not raw dict.
   - New ACs added for: naive-datetime rejection (D-1 / C-2), `!!python/` tag absence (C-3), 1 MiB size cap on `from_yaml` (C-4), outcome-kind ↔ optional-field invariant (D-3), `tuple` round-trip (C-7), `schema_version` rejection-ordering (C-8), `RemediationError.details` boundary primitive-typed (K-3), adversarial mis-cased `outcome.kind` (T-9).
   - **Load-error union** `ReportLoadError = Annotated[ReportFileMissing | ReportYamlSyntax | ReportSchemaViolation | ReportUnknownSchemaVersion | ReportSizeCapExceeded | ReportSymlinkRefused, Field(discriminator="kind")]` — module-local discriminated union mirroring S5-04's `PolicyLoadError`. Canonical `ParseError` left untouched.
   - **Write-error union** `ReportIoError = Annotated[ReportSymlinkRefused | ReportDiskFull | ReportPermissionDenied | ReportFilesystemRace | ReportOtherIoError, Field(discriminator="kind")]` — module-local; manifest's `IoError` not reused.
   - `extra="forbid"` + `frozen=True` explicitly required on every nested model (`ReportMetadata`, `PluginSnapshot`, `TransformSnapshot`).
4. **Implementation outline:**
   - `write` split into pure `_serialize() -> bytes` + impure `_write_bytes(path, payload)` (D-5).
   - `tmp` filename built via `path.parent / (path.name + ".tmp")` (or copy `output/writer.py:128` pattern with pid + token_hex).
   - `from_yaml` checks size cap → symlink → file-existence → YAML syntax → `schema_version` → Pydantic schema (in that order — mirrors S5-04 AC-Load-2).
   - `model_validator(mode="after")` for outcome ↔ optional-field consistency.
   - `field_validator` rejecting naive datetimes on `started_at`, `completed_at`.
5. **TDD plan:**
   - All variant constructor calls fixed (standalone classes, full required field sets, `RemediationError` for `error` field).
   - `Ok` / `Err` imports from `codegenie.result`; calls are `result.is_ok()` (method) or `isinstance(result, Ok)` / `isinstance(result, Err)` (typed narrowing).
   - `test_round_trip_requires_human_review` filled in (HumanReviewReason literal, no handoff_path).
   - `test_newtypes_enforced_at_construction` replaced with a `mypy --strict` discipline note (no runtime test possible without a smart constructor).
   - `monkeypatch` target on `os.replace` corrected to the module-resolved reference.
   - Added tests for: naive-datetime rejection, `!!python/` tag absence, size-cap on `from_yaml`, outcome ↔ optional invariant, mis-cased `outcome.kind`, `tuple` round-trip.
   - Property/metamorphic write-read-write byte equality moved to an explicit corpus iteration over the four variants.
6. **Notes for the implementer** updated with:
   - Variant-name pitfalls and the dispatch convention.
   - `TrustOutcome` co-location decision and the recommended option (a — declare in `outcomes.py`).
   - `__all__` + declaration order load-bearing for S6-06 snapshot.
   - Rule-of-three deferral note on `_atomic_write_bytes` extraction.

## Verdict

**HARDENED.** Edits applied in place. Story is now ready for `phase-story-executor`.

The story's *intent* and *scope* were correct; the prescribed APIs simply did not match the kernel that landed across S1-01..S5-04. The hardening realigns the story with the canonical `Result` API, the discriminated-union load-error idiom from S5-04, and the standalone-variant import discipline of `transforms/outcomes.py`.
