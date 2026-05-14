# Story S5-01 — `ScenarioResult` + `ScannerOutcome` shared discriminated unions

**Step:** Step 5 — Ship Layer C (runtime + container) probes
**Status:** Ready
**Effort:** S
**Depends on:** S1-07 (`run_external_cli` lands the `ProcessResult` shape `ScannerFailed` mirrors), S3-03 (writer signature tightening — `ScannerOutcome` flows through the redaction chokepoint)
**ADRs honored:** 02-ADR-0001 (Layer C/G binaries — outcome types model the failure modes), 02-ADR-0006 (sum-type discipline for state machines)

## Context

Layer C's `RuntimeTraceProbe` (S5-02) and Layer G's scanner family (`SemgrepProbe`, `SyftProbe`, `GrypeProbe`, `GitleaksProbe`; S5-04 + S6-06 + S6-07) both need typed outcomes. `RuntimeTraceProbe` runs 5 scenarios per gather; each scenario can complete, fail (timeout / docker-build error / strace-unavailable), or be skipped (no Dockerfile present, image-digest unresolved). Every Layer G scanner can run, be skipped (tool missing), or fail (non-zero exit, invalid-JSON stdout). The architecture (phase-arch-design.md §"Data model" + §"Component design" #5–#6) names two discriminated unions:

- `ScenarioResult = TraceScenarioCompleted | TraceScenarioFailed | TraceScenarioSkipped` — Layer C only.
- `ScannerOutcome = ScannerRan | ScannerSkipped | ScannerFailed` — **shared** between Layer C (`SyftProbe`/`GrypeProbe` in S5-04) and Layer G (S6-06/S6-07/S6-08). Both layers must import the same type, so the type lives under `codegenie/probes/_shared/` per the manifest's pinned location.

This story plants both unions before any probe consumes them. ADR-0006's sum-type discipline (ADR-0033 §3, make-illegal-states-unrepresentable) applies: every variant carries a `kind: Literal[…]` discriminator, Pydantic `frozen=True, extra="forbid"`, round-trip identity through `model_dump_json` / `model_validate_json` is asserted by test, and consumers `match` exhaustively with `assert_never` on the otherwise-reachable branch.

## References

- [phase-arch-design.md §"Component design" #5 (Layer G scanners)](../phase-arch-design.md) — `ScannerOutcome` shape.
- [phase-arch-design.md §"Component design" #6 (`RuntimeTraceProbe`)](../phase-arch-design.md) — `ScenarioResult` shape.
- [phase-arch-design.md §"Data model"](../phase-arch-design.md) — explicit Pydantic class skeletons; `Field(discriminator="kind")`.
- [phase-arch-design.md §"Agentic best practices" — "Typed state"](../phase-arch-design.md) — every state machine is a Pydantic discriminated union; `mypy --warn-unreachable` enforcement.
- [phase-arch-design.md §"Edge cases" rows 2, 3, 5, 6](../phase-arch-design.md) — failure paths that map to each variant.
- [final-design.md §"Components" #5, #6](../final-design.md) — synthesis-pinned shapes.
- [localv2.md §5.3 C4](../../../localv2.md) — `scenarios_run`, `scenarios_failed`, `trace_coverage_confidence` semantics.
- [02-ADR-0006 (sum-type freshness location — sets the discipline)](../ADRs/0006-index-freshness-sum-type-location.md).
- Phase 1 ADR-0011 (sum-type round-trip property) — same discipline pattern reused.

## Goal

Land two pure-typing modules — `src/codegenie/probes/layer_c/scenario_result.py` and `src/codegenie/probes/_shared/scanner_outcome.py` — exporting Pydantic discriminated unions with `kind` discriminators, JSON round-trip identity, and exhaustive `match` enforced at the type level for downstream consumers. **Zero probes consume these in this story**; S5-02 / S5-04 / S6-06 / S6-07 / S6-08 are the consumers.

## Acceptance criteria

- [ ] `src/codegenie/probes/layer_c/scenario_result.py` exists and exports `TraceScenarioCompleted`, `TraceScenarioFailed`, `TraceScenarioSkipped`, `StraceUnavailable`, `ScenarioResult`, and the variants' `kind` Literal values; `__all__` is the authoritative export list.
- [ ] `src/codegenie/probes/_shared/__init__.py` and `src/codegenie/probes/_shared/scanner_outcome.py` exist; exports `ScannerRan`, `ScannerSkipped`, `ScannerFailed`, `ScannerOutcome`; both Layer C (S5-04) and Layer G (S6-06/07/08) probes import from this location (no duplicate definitions).
- [ ] Every variant is a Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` and a `kind: Literal["..."]` field with a unique value.
- [ ] `ScenarioResult` and `ScannerOutcome` are `Annotated[Union[...], Field(discriminator="kind")]` (exactly as phase-arch-design.md §"Data model" prescribes).
- [ ] **Round-trip identity test**: for every variant of both unions, `parse(dump(v)) == v` byte-for-byte through `model_dump_json` / `model_validate_json` (Hypothesis-friendly; the property test in S7-05 extends this).
- [ ] **Exhaustive `match` test**: a helper consumer function `_describe(outcome) -> str` `match`es every variant and `assert_never`s the otherwise branch; deliberately removing one `case` and running `mypy --warn-unreachable` against the test file produces a build error (proves the discipline is enforceable). The deletion test is documented but not committed in the deleted state — it is the smoke-test of `mypy` configuration once S1-11's per-module override is in place.
- [ ] `StraceUnavailable` is a Pydantic model carried as the `reason` field on `TraceScenarioFailed` when the macOS path triggers; the `reason` field's type is itself a discriminated union (placeholder variants today: `StraceUnavailable | DockerBuildFailed | ScenarioTimeout | ImageDigestUnresolved`) so S5-02 cannot smuggle a string. Each placeholder variant ships with `kind: Literal[…]` + round-trip; new variants are added by S5-02 implementation as needed (not invented speculatively here).
- [ ] `TraceScenarioSkipped` carries a typed `reason` (e.g., `NoDockerfile`, `ImageBuildUnavailable`) — same discriminated-union discipline.
- [ ] `ScannerFailed` carries `exit_code: int` and `stderr_tail: str` (capped at 4 KB at construction time — `field_validator` truncates if longer; documented in module docstring as "the writer caps further at 64 MB; this is the per-outcome cap").
- [ ] `ScannerSkipped` carries `reason: Literal["tool_missing", "tool_unhealthy", "upstream_unavailable"]` — a Literal-string enum keeps the slack tight; adding a fourth requires an ADR amendment to 02-ADR-0001's "what shape do scanner outcomes take" footnote or a follow-up ADR.
- [ ] `mypy --strict` clean on both modules; `mypy --warn-unreachable` per-module override (from S1-11) is configured for `codegenie.probes._shared.scanner_outcome` and `codegenie.probes.layer_c.scenario_result`.
- [ ] No file under `src/codegenie/probes/` imports a discriminated-union *variant* by name from outside `_shared/` or `layer_c/scenario_result.py` (a smoke import test asserts this); the contract is "import the union, not the variants" except for construction.
- [ ] No `model_construct` usage; the S1-11 `forbidden-patterns` extension already bans it under the relevant module trees (`tccm`, `indices`, `adapters`, etc.); this story extends the pre-commit grep to include `src/codegenie/probes/_shared/**` and `src/codegenie/probes/layer_c/scenario_result.py` if not already covered — surface in "Notes for the implementer" if the grep already covered them.

## Implementation outline

1. Create `src/codegenie/probes/_shared/__init__.py` and `src/codegenie/probes/_shared/scanner_outcome.py`.
2. Define `ScannerRan`, `ScannerSkipped`, `ScannerFailed` as Pydantic models with `frozen=True, extra="forbid"` and `kind` discriminators. `ScannerRan.findings: list[Finding]` is a forward reference to a `Finding` placeholder Pydantic model (also defined in this module — minimal shape: `kind: Literal["finding"]`, `id: str`, `severity: Literal["info","low","medium","high","critical"]`, `metadata: dict[str, JSONValue]`). The full `Finding` shape evolves with S5-04 / S6-06 / S6-07; today it is the smallest model that satisfies round-trip.
3. Export `ScannerOutcome = Annotated[Union[ScannerRan, ScannerSkipped, ScannerFailed], Field(discriminator="kind")]`.
4. Create `src/codegenie/probes/layer_c/__init__.py` and `src/codegenie/probes/layer_c/scenario_result.py`.
5. Define `StraceUnavailable`, `DockerBuildFailed`, `ScenarioTimeout`, `ImageDigestUnresolved` as Pydantic models (each `kind: Literal["…"]`), and a `TraceFailureReason = Annotated[Union[...], Field(discriminator="kind")]` union for the inner `reason` field.
6. Define `NoDockerfile`, `ImageBuildUnavailable` as Pydantic models, and a `TraceSkipReason = Annotated[Union[...], Field(discriminator="kind")]` union for `TraceScenarioSkipped.reason`.
7. Define `TraceScenarioCompleted(kind, scenario_name: str, artifact_uri: Path, wall_clock_ms: int, syscalls_observed: int, shared_libs_count: int)`; `TraceScenarioFailed(kind, scenario_name, reason: TraceFailureReason)`; `TraceScenarioSkipped(kind, scenario_name, reason: TraceSkipReason)`.
8. Export `ScenarioResult = Annotated[Union[TraceScenarioCompleted, TraceScenarioFailed, TraceScenarioSkipped], Field(discriminator="kind")]`.
9. Write the round-trip + exhaustive-match tests under `tests/unit/probes/_shared/test_scanner_outcome.py` and `tests/unit/probes/layer_c/test_scenario_result.py`.
10. Extend `pyproject.toml` `[tool.mypy]` per-module overrides if S1-11 hasn't already pinned `codegenie.probes._shared.*` and `codegenie.probes.layer_c.scenario_result` — surface the diff in "Notes for the implementer".

## TDD plan — red / green / refactor

**Red (write before code; both files start absent or empty):**

1. `test_scanner_outcome_roundtrip` (`tests/unit/probes/_shared/test_scanner_outcome.py`): import `ScannerOutcome` and each variant; construct one of each; assert `ScannerOutcome.__pydantic_discriminator__ == "kind"` (or equivalent introspection); for each constructed value `v`, assert `type(v).model_validate_json(v.model_dump_json()) == v`. Initial state: `ModuleNotFoundError`.
2. `test_scanner_outcome_match_exhaustive`: a private `_describe(outcome: ScannerOutcome) -> str` defined inside the test module `match`es each `kind`; `assert_never(outcome)` on the otherwise branch; assert each variant's string. Initial state: import fails.
3. `test_scenario_result_roundtrip` (`tests/unit/probes/layer_c/test_scenario_result.py`): construct one of each variant (using one of each `reason` placeholder for `Failed` / `Skipped`); assert byte-identical JSON round-trip. Initial state: `ModuleNotFoundError`.
4. `test_scenario_result_match_exhaustive`: helper `_describe(result: ScenarioResult) -> str` with exhaustive match + `assert_never`. Initial state: import fails.
5. `test_strace_unavailable_is_typed`: `TraceScenarioFailed(scenario_name="startup", reason=StraceUnavailable())` round-trips with `reason.kind == "strace_unavailable"`. Initial state: import fails.
6. `test_scanner_failed_stderr_tail_truncates`: construct `ScannerFailed(exit_code=1, stderr_tail="a" * 8192)`; assert `len(constructed.stderr_tail) == 4096` (the field validator capped it); Pydantic raises if the construction shape is wrong. Initial state: import fails.
7. `test_scanner_skipped_reason_is_enum`: construct `ScannerSkipped(reason="tool_missing")` succeeds; `ScannerSkipped(reason="ad_hoc")` raises `ValidationError`. Initial state: import fails.
8. `test_no_model_construct_under_shared_paths`: extends S1-11's existing forbidden-patterns assertion (or runs `pre-commit run --files <these>` and asserts the lint passes). If S1-11 already covers `_shared/` and `layer_c/`, this is a no-op smoke test; document the result.

**Green:**

1. Create the two modules with the variant models, the `Annotated[Union, Field(discriminator)]` unions, and the helper validators (`stderr_tail` truncation; `reason` literal-enum).
2. Make every test pass without touching any consumer probe.

**Refactor:**

1. Extract `JSONValue` type alias usage to match Phase 0's existing `JSONValue` import (do **not** re-define).
2. Add module docstrings naming the consumers (S5-02 / S5-04 / S6-06 / S6-07 / S6-08) and the load-bearing-discipline ("variants are exhaustive; new variant requires an ADR amendment").
3. Confirm `__all__` exports are the union + the variant names + the placeholder reason types — the union is the public surface; variants are public only for construction.

## Files to touch

- **New:** `src/codegenie/probes/_shared/__init__.py`, `src/codegenie/probes/_shared/scanner_outcome.py`, `src/codegenie/probes/layer_c/__init__.py`, `src/codegenie/probes/layer_c/scenario_result.py`.
- **New tests:** `tests/unit/probes/_shared/test_scanner_outcome.py`, `tests/unit/probes/layer_c/test_scenario_result.py`.
- **Possibly extend:** `pyproject.toml` `[tool.mypy]` per-module overrides — only if S1-11 didn't already list these two modules.
- **Possibly extend:** `src/codegenie/output/sanitizer.py` `forbidden-patterns` grep ranges — only if S1-11 didn't already cover `src/codegenie/probes/_shared/**` and `src/codegenie/probes/layer_c/scenario_result.py`.

## Out of scope

- Any probe implementation that constructs these values (`RuntimeTraceProbe` = S5-02; `SyftProbe` / `GrypeProbe` = S5-04; Layer G scanners = S6-06 / S6-07 / S6-08).
- The `Finding` shape's eventual full schema — placeholder model lands here; real shape evolves with consumers.
- Writer composition through `RedactedSlice` (`ScannerOutcome` flows through S3-03's writer signature — the writer already accepts `RedactedSlice`, and this story doesn't change that).
- Any change to `Probe` ABC or `ProbeContext` (banned in Phase 2 except for S1-09's `image_digest_resolver`).

## Notes for the implementer

- The choice to put `scanner_outcome.py` under `_shared/` (not `layer_c/` and not `layer_g/`) is load-bearing — Layer C's `SyftProbe`/`GrypeProbe` and Layer G's curated scanners (`SemgrepProbe`, `GitleaksProbe`, etc.) must import the same `ScannerOutcome` type. Duplicating it under `layer_c/scanner_outcome.py` and `layer_g/scanner_outcome.py` would re-introduce the structural drift Phase 2 is rejecting. If you find yourself wanting two locations, surface it in "Notes" and stop — that's an ADR-amend trigger.
- `Finding` is intentionally minimal here. Resist the urge to model semgrep / gitleaks / grype finding shapes now — S5-04 / S6-06 / S6-07 each emit their own `metadata` payload and the union's job in this story is only to round-trip. If you find yourself adding scanner-specific fields, you've slipped into S6-06 / S6-07 / S6-08.
- The `reason` field on `TraceScenarioFailed` is itself a discriminated union — not a string. This is deliberate per phase-arch-design.md §"Edge cases" rows 5/6 + final-design.md §"Components" #6: macOS's permanent path emits `StraceUnavailable()` and the consumer (S5-05's freshness check + S8-01's renderer) must `match` on it as a typed value. A stringly-typed `reason: str` would silently lose the `mypy --warn-unreachable` enforcement and was the exact "anti-pattern" called out in §"Anti-patterns avoided".
- `ScannerSkipped.reason` is the one place a `Literal` makes more sense than a sum type — three closed alternatives, no payload differs. If a fourth reason needs structured payload (e.g., "upstream_unavailable" needs the upstream slice name), promote to a discriminated union in a follow-up ADR rather than adding a `metadata: dict` escape hatch.
- macOS `dtruss` is not used; we emit `StraceUnavailable()` for *any* non-Linux host. The macOS path is **permanent** — final-design.md §"Where security/best-practices traded off perf" makes this explicit.
- Open-question echo: the S1-11 per-module override list should include both new modules. If it doesn't (because S1-11 landed before this story was scoped), this story's PR extends `pyproject.toml` minimally; document the diff in PR description so the S1-11 ADR's "Consequences" can be reviewed.
- The deliberate-`case`-deletion exhaustiveness smoke test is documented in "Acceptance criteria" but not committed in deleted state. Treat it as a developer-runnable check: remove one `case`, run `mypy --warn-unreachable`, confirm the error, restore the `case`. This is part of S8-01's renderer Implementation risk #4 verification — landing the discipline here de-risks Step 8.
- If `pytest-subprocess` or any other test dep is needed, it lands as `[project.optional-dependencies] dev = […]` and is verified by Phase 0 `fence` (it's not an LLM dep).
