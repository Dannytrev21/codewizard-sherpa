# Story S17-01 — `MigrationConfidence` sum type + `aggregate_migration_confidence` pure rollup

**Step:** Step 17 — Migration confidence + multi-arch / external-registry checks (M1, G11, G13)
**Status:** Ready
**Effort:** M
**Depends on:** S15-03 (`RuntimeCompatProbe` shipped — the last load-bearing probe `confidence` the rollup must consider; its slice name closes the load-bearing set the fence checks against); S16-01 (`RemediationOutcome.PendingHumanReview` refusal variants shipped in `src/codegenie/transforms/outcomes.py` — the `Refused` arm of the rollup is driven by an already-present typed refusal)
**ADRs honored:** Phase 7 ADR-0026 (`MigrationConfidence` is a single sum-type rollup the orchestrator refuses against — this story *is* ADR-0026); Phase 7 ADR-0024 (`AdapterConfidence.Degraded` from non-public-registry detection feeds the rollup); Phase 7 ADR-0025 (the refusal taxonomy supplies the `Refused` arm); Phase 7 ADR-0029 (`migration_confidence.py` is an Amendment-A net-new file allowlisted by the byte-edit fence); Phase 7 ADR-0009 (no byte-edit to Phase 0–6.5 / Phase 3 files outside the allowlist — this story is **net-new-files-only**); production ADR-0033 (domain-modeling discipline — sum type for state, make illegal states unrepresentable, exhaustive `match`/`assert_never`); production ADR-0007 (frozen Probe contract — every probe `confidence: Literal["high","medium","low"]` is an *input* the rollup consumes, never edited).

## Context

By Amendment A the gather pipeline emits a dozen confidence signals. Every probe reports `confidence: Literal["high","medium","low"]` (the frozen Probe contract — `src/codegenie/probes/base.py`). Every provenance adapter reports `AdapterConfidence ∈ {High, Degraded, Unavailable}` (`src/codegenie/primitives/vuln_provenance/types.py`, shipped in S1-02). `BaseImageProbe`'s non-public-registry detection (S17-02 / ADR-0024) degrades an adapter; `RuntimeShellInvocationProbe` (S15-01) and `RuntimeCompatProbe` (S15-03) each carry their own `confidence`.

The problem (M1 in `../final-design.md §Amendment A §A.2`): **there is no single value the orchestrator can refuse against.** Today it would have to scatter `if slice.confidence == "low"` and `if adapter.confidence == Degraded` checks across the dispatch path — gate-and-pray, with no one place that says "this migration is too uncertain to auto-apply." A probe added in a later story would silently *not* be considered unless someone remembered to add another check. That is exactly the primitive-obsession / hidden-state failure the project's domain-modeling discipline (production ADR-0033) forbids.

`../phase-arch-design.md §Component design — Amendment A §21` resolves M1 with **one typed rollup and one pure aggregation function**. This story ships both: a frozen tagged union `MigrationConfidence = High | Degraded(reasons) | Refused(reason)` and the pure free function `aggregate_migration_confidence(slices, adapters) -> MigrationConfidence`. The function is **functional-core** — deterministic, no I/O, no hidden state, all inputs passed explicitly — so the orchestrator (the imperative shell, downstream) does a single exhaustive `match`: `High` → apply the recipe; `Degraded` → escalate to HITL instead of applying; `Refused` → halt with the typed refusal.

The rollup is a **lattice**: `High > Degraded > Refused`. The load-bearing invariant is **monotonicity** — adding a `Degraded`/`low` signal to the input set can only move the verdict *down* the lattice or hold it; it can never *improve* the rollup. A future edit that broke this (e.g. a `low` probe that "cancels out" another) would be a silent regression that lets an uncertain migration auto-apply. The monotonicity property is the guard against that, and is property-tested with Hypothesis in this story (AC-9).

The module lives at `plugins/distroless-migration--node--npm/migration_confidence.py` — **NOT** under `src/codegenie/`. It is a net-new Amendment-A file, allowlisted by ADR-0029 row category #1. The load-bearing-probe set — the slice names whose `confidence == "low"` is allowed to degrade the rollup — is a module-level `Final[tuple[str, ...]]`; a fence test (AC-10) asserts it against the registered Phase-7 probe set so a probe added later cannot be silently omitted from the gate.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Amendment A §21 (MigrationConfidence aggregator)` — names the `aggregate_migration_confidence(slices, adapters) -> MigrationConfidence` signature, the three-arm union shape, and the "pure / functional-core" requirement.
  - `../phase-arch-design.md §Amendment A gaps §M1` — the gate-and-pray problem and the single-refusal-point resolution.
  - `../final-design.md §Amendment A §A.2 (M1 row)` — `MigrationConfidence` aggregator; `§A.1` — governing principle "refuse with typed evidence."
- **Phase ADRs:**
  - `../ADRs/0026-migration-confidence-aggregation.md` — **this story implements ADR-0026 verbatim.** The `Decision` block gives the union shape and the rollup rule; the `Consequences` block names the file path, the load-bearing-probe `Final` tuple, the fence test, and the monotonicity property test.
  - `../ADRs/0024-multi-arch-and-external-registry-checks.md` — `non_public_registry == True` → `AdapterConfidence.Degraded`; this rollup consumes that `Degraded`. S17-02 produces it.
  - `../ADRs/0025-migration-refusal-taxonomy.md` — the closed `RemediationOutcome.PendingHumanReview` variant set; a refusal already present in the inputs drives the `Refused` arm.
  - `../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md` — row category #1 allowlists `migration_confidence.py` as an Amendment-A net-new file.
- **Existing code / precedents:**
  - `src/codegenie/primitives/vuln_provenance/types.py` — `class AdapterConfidence(str, Enum)` with `HIGH = "high"`, `DEGRADED = "degraded"`, `UNAVAILABLE = "unavailable"` (S1-02). The `_Frozen` base (`frozen=True, extra="forbid"`) every Phase-7 primitive `BaseModel` inherits lives here — the `MigrationConfidence` arms reuse it, mirroring the seven-variant `Provenance` union shape in `provenance.py`.
  - `src/codegenie/primitives/vuln_provenance/provenance.py` (S1-03) — the seven-variant discriminated `Provenance` union is the **canonical sum-type precedent** for Phase 7: `Annotated[Union[...], Field(discriminator="kind")]`, `_Frozen` base, `match`/`assert_never` exhaustiveness. Mirror it; do not fork it.
  - `src/codegenie/probes/base.py` — the frozen Probe ABC; `confidence: Literal["high","medium","low"]` is the field every probe `ProbeOutput` carries. The rollup reads it; it never edits the ABC.
  - `src/codegenie/transforms/outcomes.py` — `RemediationOutcome.PendingHumanReview` and the S16-01 refusal variants (`RefusedArchitectureLoss`, `RefusedRuntimeShellOutInProductionCode`, …). A refusal among the inputs → the `Refused` arm.
- **Story-pipeline neighbors:**
  - `S15-03-runtime-compat-probe.md` — last load-bearing probe; its slice name (`runtime_compat`) closes the `_LOAD_BEARING_PROBE_SLICES` tuple.
  - `S16-01-migration-refusal-taxonomy.md` — ships the refusal variants in `outcomes.py`; must land first so the `Refused` arm has a typed input to detect.
  - `S17-02-base-image-multiarch-registry.md` — sibling Step-17 story; produces the `AdapterConfidence.Degraded` (non-public mirror) this rollup consumes. The two stories share Step 17 but have no direct code dependency — S17-01 reads `AdapterConfidence`, S17-02 produces it.
  - `S18-01-migration-observability-events.md` — downstream consumer; renders `Degraded.reasons` / `Refused.reason` into the PR description (M3).

## Goal

Land `migration_confidence.py` under `plugins/distroless-migration--node--npm/` as a net-new Amendment-A file containing (1) the frozen tagged union `MigrationConfidence = High | Degraded(reasons) | Refused(reason)` built on the Phase-7 `_Frozen` base with exhaustive `match`/`assert_never` discipline, and (2) the pure free function `aggregate_migration_confidence(slices, adapters) -> MigrationConfidence` that rolls every probe `confidence` and every `AdapterConfidence` into the single value the orchestrator refuses against — `High` when all inputs are clean, `Degraded(reasons)` naming every degrading probe/adapter when any load-bearing probe is `low` or any adapter is `Degraded`, `Refused(reason)` when a typed refusal is already present. The function is functional-core: deterministic, no I/O, no hidden state. The rollup is monotone on the `High > Degraded > Refused` lattice, property-tested with Hypothesis. `mypy --strict` clean, no `Any` in the public surface.

## Acceptance criteria

**Sum-type shape (AC-1 through AC-3)**
- [ ] **AC-1** `plugins/distroless-migration--node--npm/migration_confidence.py` exists. It defines three frozen variant classes — `High`, `Degraded`, `Refused` — each inheriting the Phase-7 `_Frozen` base (`frozen=True, extra="forbid"`) from `codegenie.primitives.vuln_provenance.types`. `High` carries no payload. `Degraded` carries `reasons: tuple[str, ...]` (human-readable, each entry names the degrading probe slice or adapter). `Refused` carries `reason: str`. The public alias `MigrationConfidence = Union[High, Degraded, Refused]` is exported. Verified by `tests/unit/plugins/distroless_migration_node_npm/test_migration_confidence_shape.py::test_three_arms_are_frozen` — constructs one of each, asserts each is an instance of `_Frozen`, asserts `frozen` mutation raises (`pytest.raises((TypeError, ValidationError))` on attribute set), and asserts `Degraded.reasons` / `Refused.reason` round-trip the constructor argument byte-equal.
- [ ] **AC-2** The union is **closed at exactly three arms**. A `match`/`assert_never` exhaustiveness anchor is present in the module (a `_describe(mc: MigrationConfidence) -> str` helper that `match`es all three arms and calls `assert_never` in the fall-through). Verified by `test_migration_confidence_shape.py::test_match_is_exhaustive` — `mypy --strict` over the module reports no `assert_never` reachability error (the test asserts `mypy` exit 0 on the file), and a runtime call of `_describe` on each of the three arms returns a distinct non-empty string. A planted fourth-arm stub (commented red-by-construction note in the test) documents that adding an arm without updating `_describe` is a `mypy` failure.
- [ ] **AC-3** `Degraded.reasons` is a `tuple[str, ...]` (immutable), never a `list`. `Refused.reason` is a non-empty `str`. Verified by `test_migration_confidence_shape.py::test_reasons_is_immutable_tuple` — asserts `isinstance(Degraded(reasons=("x",)).reasons, tuple)`, asserts constructing `Degraded(reasons=["x"])` from a list either coerces to `tuple` or is rejected (pin whichever Pydantic does — the AC is "the stored value is a `tuple`"), and asserts `Refused(reason="")` is rejected (empty-string refusal carries no evidence — fails the "typed evidence" principle of `../final-design.md §A.1`).

**Aggregation function — happy + degraded + refused (AC-4 through AC-8)**
- [ ] **AC-4** `aggregate_migration_confidence(slices, adapters) -> MigrationConfidence` is a **pure free function** (module-level `def`, not a method). Its inputs are `slices: Mapping[str, ProbeSlice]` (probe slice name → slice carrying `confidence`) and `adapters: Sequence[AdapterResult]` (each carrying an `AdapterConfidence`). It performs **no I/O** — no file reads, no network, no subprocess, no logging. Verified by `tests/fence/test_migration_confidence_purity.py` (AST-walk) — rejects `open(`, `subprocess.*`, `os.system`, `requests.*`, `urllib.*`, `httpx.*`, `print(`, any `logging` call, and any LLM-SDK import inside `migration_confidence.py`; three planted-violation parametrized cases prove the walker fires. The fence file uses `raise AssertionError("...")` — bare `assert` is forbidden.
- [ ] **AC-5** All-high inputs → `High`. Given a `slices` mapping where every load-bearing probe reports `confidence == "high"` and an `adapters` sequence where every adapter reports `AdapterConfidence.HIGH`, `aggregate_migration_confidence(...)` returns an instance of `High`. Verified by `test_migration_confidence_aggregate.py::test_all_high_inputs_roll_up_high` — builds the input set explicitly (every Phase-7 load-bearing slice name present, each `confidence="high"`), asserts `isinstance(result, High)`.
- [ ] **AC-6** One low probe → `Degraded` naming that probe. Given a `slices` mapping identical to AC-5 except one load-bearing probe (e.g. `runtime_compat`) reports `confidence == "low"`, the result is an instance of `Degraded` and `result.reasons` contains at least one entry that **names that probe's slice** (the probe slice name `"runtime_compat"` is a substring of some reason). Verified by `test_migration_confidence_aggregate.py::test_one_low_probe_degrades_and_names_it` — asserts `isinstance(result, Degraded)` AND `any("runtime_compat" in r for r in result.reasons)`. A `Degraded` result whose `reasons` does not name the degrading probe fails this AC (HITL must see *which* probe degraded — `../ADRs/0026 §Tradeoffs`).
- [ ] **AC-7** One `Degraded` adapter → `Degraded` naming that adapter. Given all probes `high` but one adapter reporting `AdapterConfidence.DEGRADED` (the non-public-mirror case from S17-02 / ADR-0024), the result is `Degraded` and `result.reasons` contains an entry naming that adapter. Verified by `test_migration_confidence_aggregate.py::test_one_degraded_adapter_degrades_and_names_it` — asserts `isinstance(result, Degraded)` AND `result.reasons` contains the adapter's identifier. This pins the ADR-0024 → ADR-0026 channel: a non-public registry degrades the rollup without the orchestrator scattering an `if adapter.confidence == Degraded` check.
- [ ] **AC-8** A refusal input → `Refused`. Given the input set contains a typed refusal already present (a `RemediationOutcome.PendingHumanReview` variant from S16-01 — e.g. `RefusedArchitectureLoss` — surfaced into the function via the agreed input channel), the result is an instance of `Refused` and `result.reason` is a non-empty string naming the refusal variant. `Refused` **dominates** `Degraded`: if the inputs carry *both* a `low` probe and a refusal, the result is `Refused` (the lattice bottom). Verified by `test_migration_confidence_aggregate.py::test_refusal_input_rolls_up_refused` and `::test_refused_dominates_degraded` — the second asserts that adding a `low` probe to a refusal-bearing input set still yields `Refused`.

**Monotonicity property (AC-9)**
- [ ] **AC-9** A Hypothesis property test pins **monotonicity** on the `High > Degraded > Refused` lattice: for any input set, **adding a `Degraded` adapter or a `low` probe to that set never improves the rollup** — the new verdict is `≤` the old verdict on the lattice. `tests/unit/plugins/distroless_migration_node_npm/test_migration_confidence_property.py::test_adding_a_degrading_signal_never_improves_the_rollup` uses a Hypothesis strategy generating arbitrary `(slices, adapters)` input sets, computes `before = aggregate_migration_confidence(slices, adapters)`, then constructs `after` by adding exactly one degrading signal (a `low` probe OR a `Degraded` adapter, `@given`-chosen), and asserts `_lattice_rank(after) <= _lattice_rank(before)` where `_lattice_rank` maps `High→2, Degraded→1, Refused→0`. A second property — `::test_aggregation_is_deterministic` — asserts the function returns equal results for the same input across repeated calls (no hidden state). The strategy must be able to generate all three output arms (a coverage assertion in the test body, via `hypothesis.event`, confirms `High`/`Degraded`/`Refused` are each hit across the run).

**Load-bearing-probe-set fence (AC-10)**
- [ ] **AC-10** `_LOAD_BEARING_PROBE_SLICES: Final[tuple[str, ...]]` is a module-level tuple of the probe slice names whose `confidence == "low"` is allowed to degrade the rollup. A fence test `tests/fence/test_load_bearing_probe_set_complete.py::test_every_phase7_probe_is_load_bearing_or_explicitly_excluded` constructs a fresh `Registry`, imports the Phase-7 plugin probe modules, and asserts every registered Phase-7 probe slice name is **either** in `_LOAD_BEARING_PROBE_SLICES` **or** in a sibling `_EXPLICITLY_NON_LOAD_BEARING: Final[frozenset[str]]` set carrying a one-line docstring rationale per entry. A Phase-7 probe that is in neither set fails the fence — this is the mechanical guard against a later-added probe being silently omitted from the gate (`../ADRs/0026 §Tradeoffs` row 1, `§Consequences`).

**Fence + lint discipline (AC-11 through AC-13)**
- [ ] **AC-11** `make lint-imports` green; `migration_confidence.py` introduces no forbidden import path. The import-linter contract from S5-03 already forbids `plugins/distroless-migration--*/` → LLM SDKs; the module imports only `typing`, `dataclasses`/`pydantic`, `codegenie.primitives.vuln_provenance.types`, and `codegenie.transforms.outcomes` (for the refusal-variant types it `match`es on).
- [ ] **AC-12** `ruff check`, `ruff format --check`, `mypy --strict plugins/distroless-migration--node--npm/migration_confidence.py` all clean. **No `Any` in any annotation** — the Phase 3 / Phase 7 `test_no_any_in_plugin_surface` discipline applies. `aggregate_migration_confidence`'s signature is fully typed (`Mapping[str, ProbeSlice]`, `Sequence[AdapterResult]`, `-> MigrationConfidence`).
- [ ] **AC-13** Phase 7 ADR-0009 / ADR-0029 byte-edit allowlist fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) green: this story adds files only under `plugins/distroless-migration--node--npm/` and `tests/`; no Phase 0–6.5 / Phase 3 file is byte-edited. `migration_confidence.py` is covered by ADR-0029 row category #1 (Amendment-A net-new plugin-internal module). The allowlist row for it is added in S13-03 (the fence-amendment story); if S13-03 has not yet landed the row, this story's executor adds it as the one fixture-data edit ADR-0029 permits — coordinate sequencing in the attempt log.

## Implementation outline

1. **Net-new files only — no edits to Phase 0–6.5 / Phase 3.** Create:
   - `plugins/distroless-migration--node--npm/migration_confidence.py` — the union + the pure function + the two `Final` sets.
   - `tests/unit/plugins/distroless_migration_node_npm/test_migration_confidence_shape.py` (AC-1, AC-2, AC-3).
   - `tests/unit/plugins/distroless_migration_node_npm/test_migration_confidence_aggregate.py` (AC-5..AC-8).
   - `tests/unit/plugins/distroless_migration_node_npm/test_migration_confidence_property.py` (AC-9 — Hypothesis).
   - `tests/fence/test_migration_confidence_purity.py` (AC-4 — AST fence).
   - `tests/fence/test_load_bearing_probe_set_complete.py` (AC-10 — registry fence).

2. **The sum type in `migration_confidence.py`:**
   ```python
   from typing import Final, Union
   from codegenie.primitives.vuln_provenance.types import _Frozen

   class High(_Frozen):
       """All load-bearing probes high, all adapters High — auto-apply the recipe."""

   class Degraded(_Frozen):
       """A load-bearing probe is low or an adapter is Degraded — escalate to HITL."""
       reasons: tuple[str, ...]   # each entry names the degrading probe slice / adapter

   class Refused(_Frozen):
       """A typed refusal is already present — halt with the refusal evidence."""
       reason: str                # non-empty; names the refusal variant

   MigrationConfidence = Union[High, Degraded, Refused]
   ```
   Mirror the S1-03 `Provenance`-union module shape — `_Frozen` base, `extra="forbid"`. `Refused.reason` carries a Pydantic constraint rejecting the empty string (AC-3).

3. **Load-bearing-probe set (module-level data, AC-10):**
   ```python
   _LOAD_BEARING_PROBE_SLICES: Final[tuple[str, ...]] = (
       "base_image",
       "shell_invocation_trace",
       "dockerfile_secret_pattern",
       "target_image_content",
       "runtime_shell_invocation",
       "container_probe_compat",
       "runtime_compat",
   )
   _EXPLICITLY_NON_LOAD_BEARING: Final[frozenset[str]] = frozenset()
   ```
   Confirm the exact registered Phase-7 slice names against the registry at implementation time — the fence (AC-10) is the source of truth and will fail if a name drifts.

4. **`_lattice_rank(mc: MigrationConfidence) -> int`** — the lattice helper: `High → 2`, `Degraded → 1`, `Refused → 0`. Implemented with an exhaustive `match`/`assert_never` (this is also the AC-2 exhaustiveness anchor, or a sibling to `_describe`).

5. **`aggregate_migration_confidence(slices, adapters) -> MigrationConfidence`** — the pure rollup:
   - **Refused first (lattice bottom dominates).** If any input carries a typed refusal (a `RemediationOutcome.PendingHumanReview` refusal variant present among the inputs), return `Refused(reason=<variant name + source location>)`. `Refused` dominates `Degraded` (AC-8).
   - **Degraded next.** Collect `reasons`: for each slice name in `_LOAD_BEARING_PROBE_SLICES`, if `slices[name].confidence == "low"` append `f"{name}: probe confidence low"`; for each adapter in `adapters`, if `adapter.confidence is AdapterConfidence.DEGRADED` append `f"{adapter_identifier}: adapter Degraded"` (also fold `AdapterConfidence.UNAVAILABLE` per ADR-0024's degraded-channel intent — pin the decision in the attempt log; the ADR's rollup rule names `Degraded`, treat `Unavailable` as at-least-`Degraded`). If `reasons` is non-empty, return `Degraded(reasons=tuple(reasons))`.
   - **High fallthrough.** Otherwise return `High()`.
   - Pure throughout — no logging, no I/O. The reasons are sorted deterministically (sorted `tuple`) so the output is stable for the property test's determinism assertion.

6. **`_describe(mc) -> str`** — the `match`/`assert_never` exhaustiveness anchor (AC-2). `match mc: case High(): ... case Degraded(): ... case Refused(): ... case _: assert_never(mc)`.

7. **Tests:**
   - Shape tests construct each arm, assert frozen-ness, assert the `tuple`/non-empty-`str` constraints.
   - Aggregate tests build explicit input sets per AC-5..AC-8.
   - The Hypothesis property test (AC-9) drives monotonicity + determinism + arm-coverage.
   - The two fence tests (AST purity, registry completeness).

## TDD plan — red / green / refactor

**Red** — write `test_migration_confidence_shape.py::test_three_arms_are_frozen` first. It imports `from plugins.distroless_migration_node_npm.migration_confidence import High, Degraded, Refused, MigrationConfidence`. Run pytest — fails with `ModuleNotFoundError` (the module does not exist). This is the concrete red.

**Green** — minimum code: create `migration_confidence.py` with the three `_Frozen`-based variant classes and the `MigrationConfidence` union alias. Re-run — `test_three_arms_are_frozen` and `test_reasons_is_immutable_tuple` go green; aggregate tests still fail (no function).

**Red+** — write `test_migration_confidence_aggregate.py::test_all_high_inputs_roll_up_high`. Pytest fails — `aggregate_migration_confidence` is undefined (`ImportError` / `AttributeError`).

**Green+** — implement `aggregate_migration_confidence` for the `High` path, then add the `Degraded` collection and the `Refused`-first short-circuit. Iterate AC-5 → AC-6 → AC-7 → AC-8 until each aggregate test is green.

**Red++** — write `test_migration_confidence_property.py::test_adding_a_degrading_signal_never_improves_the_rollup` with the Hypothesis strategy and `_lattice_rank` assertion. If the rollup is not yet monotone (e.g. an early implementation that overwrites rather than accumulates reasons), Hypothesis finds a counterexample and fails. Implement `_lattice_rank` and fix the rollup until monotonicity holds.

**Red+++** — write `test_migration_confidence_purity.py::test_no_io_in_aggregate` with a planted-violation parametrize case (`open(`). Pytest fails because the AST walker isn't written. Implement the walker; three planted rows (`open`, `subprocess.run`, `urllib.request.urlopen`) are red-by-construction proof the fence fires.

**Red++++** — write `test_load_bearing_probe_set_complete.py`. It fails until `_LOAD_BEARING_PROBE_SLICES` exactly partitions the registered Phase-7 probe set with `_EXPLICITLY_NON_LOAD_BEARING`.

**Refactor** — extract `_lattice_rank` and `_describe` as the shared exhaustiveness anchors; sort the `reasons` tuple for determinism; confirm `aggregate_migration_confidence` has no `if/elif` chain on confidence *strings* — the load-bearing set is iterated, not branched on. `mypy --strict` + `ruff` clean.

## Files to touch

**New files (no Phase 0–6.5 / Phase 3 byte-edits):**

| Path | Purpose |
|---|---|
| `plugins/distroless-migration--node--npm/migration_confidence.py` | The `MigrationConfidence` union + `aggregate_migration_confidence` pure function + the two `Final` sets (ADR-0026; ADR-0029 row #1) |
| `tests/unit/plugins/distroless_migration_node_npm/test_migration_confidence_shape.py` | AC-1, AC-2, AC-3 — frozen arms, exhaustiveness anchor, `tuple`/non-empty-`str` constraints |
| `tests/unit/plugins/distroless_migration_node_npm/test_migration_confidence_aggregate.py` | AC-5..AC-8 — per-arm aggregation behavior |
| `tests/unit/plugins/distroless_migration_node_npm/test_migration_confidence_property.py` | AC-9 — Hypothesis monotonicity + determinism + arm-coverage |
| `tests/fence/test_migration_confidence_purity.py` | AC-4 — AST fence (no I/O in the pure function) |
| `tests/fence/test_load_bearing_probe_set_complete.py` | AC-10 — registry fence (no probe silently omitted) |

**Files NOT touched** (would fail the ADR-0009 / ADR-0029 fence): `src/codegenie/probes/`, `src/codegenie/primitives/`, `src/codegenie/transforms/outcomes.py`, `src/codegenie/schema/`, `pyproject.toml`. The `outcomes.py` refusal variants land in S16-01; the fence-allowlist row for `migration_confidence.py` lands in S13-03 (or is added here per ADR-0029 if S13-03 lags — see AC-13).

## Out of scope

- **The orchestrator's `match` on `MigrationConfidence`** — this story ships the *value* and the *pure aggregation*; the imperative shell that `match`es `High` → apply / `Degraded` → escalate-to-HITL / `Refused` → halt is the orchestrator's job, downstream of Phase 7's gather scope. This story makes the value the orchestrator will consume; it does not wire the dispatch. (`../ADRs/0026 §Decision`: "the orchestrator does a single exhaustive `match`" — the orchestrator is not a Phase-7 gather component.)
- **The HITL escalation payload rendering** — `Degraded.reasons` / `Refused.reason` rendered into the PR description is M3 / S18-01.
- **Producing `AdapterConfidence.Degraded`** — S17-02 (`BaseImageProbe` non-public-registry detection) produces it; this story *consumes* it. S17-01 must not depend on S17-02 landing — the aggregate tests stub `AdapterResult` values directly.
- **The refusal variants themselves** — S16-01 ships `RefusedArchitectureLoss` et al. in `outcomes.py`. This story `match`es on the variant *types* S16-01 defines; it does not define them.
- **The `RuntimeCompatProbe` / `RuntimeShellInvocationProbe` slices** — S15-01 / S15-03 ship those probes; this story reads their `confidence` field through the generic `ProbeSlice` shape.

## Notes for the implementer

- **Rule 2 — simplicity first.** `aggregate_migration_confidence` is ≤ ~40 LOC. It is three short branches: refusal-present → `Refused`; any-degraded → `Degraded`; else → `High`. Do not introduce a numeric score, a threshold, or a config knob — ADR-0026 §Options C explicitly rejects the opaque-threshold design ("0.62 is not actionable; a numeric score invites tuning the threshold to make a borderline migration pass"). Three coarse states is the *decision*, not a limitation to engineer around.
- **Rule 9 — tests verify intent.** AC-6 and AC-7 do not merely assert `isinstance(result, Degraded)` — they assert `result.reasons` *names the degrading source*. A `Degraded` with an empty or generic `reasons` tuple would pass a behavior-only test but fails the AC, because HITL must see *which* probe/adapter degraded (ADR-0026 §Tradeoffs row 2: "HITL sees `base_image` adapter Degraded: non-public mirror registry, not an opaque 0.62"). The property test (AC-9) verifies the *design intent* — monotonicity is the invariant a future refactor must not break.
- **Monotonicity is the load-bearing property.** The lattice is `High(2) > Degraded(1) > Refused(0)`. Adding a degrading signal moves the verdict *down or holds*. The naive failure mode the property test catches: an implementation that *overwrites* `reasons` instead of *accumulating* them, or one where a second `low` probe somehow flips a `Refused` back to `Degraded`. Refused dominates — once any input is a refusal, no quantity of merely-`Degraded` signals can lift the verdict. Make `Refused` the first check in the function and the test for `_refused_dominates_degraded` (AC-8) will hold for free.
- **Functional core / imperative shell.** `aggregate_migration_confidence` is pure: every input is passed explicitly, there is no module-level mutable state, no I/O. The AST fence (AC-4) is the mechanical enforcer — without it a future engineer adds a `logging.info("rolled up …")` and the function is no longer trivially property-testable. Determinism (AC-9 second property) depends on sorting the `reasons` tuple — an unsorted set-iteration would make the output order non-deterministic and the determinism property flaky.
- **`AdapterConfidence.UNAVAILABLE` handling.** ADR-0026's rollup rule names `AdapterConfidence.Degraded` explicitly. `Unavailable` is *strictly worse* than `Degraded` (the adapter could not run at all). Treat `Unavailable` as **at-least-degrading** — fold it into the `Degraded` branch with a reason naming it. Record this decision in `_attempts/S17-01.md`: the ADR text says "Degraded"; the honest reading is "Degraded or worse." Do not let an `Unavailable` adapter silently roll up `High`.
- **The load-bearing-probe set is the silent-omission guard.** `_LOAD_BEARING_PROBE_SLICES` plus `_EXPLICITLY_NON_LOAD_BEARING` must *partition* the registered Phase-7 probe set — every probe is in exactly one. The fence (AC-10) fails if a probe is in neither. This is the mechanism ADR-0026 §Tradeoffs row 1 demands: "a probe omitted from the set is silently not considered — mitigated: the set is one module-level `Final` tuple, AST-fence-checked against the registered Phase-7 probes." If you add `_EXPLICITLY_NON_LOAD_BEARING` entries, each needs a one-line docstring rationale — an unexplained exclusion is a future bug.
- **Rule 11 — match the convention.** The seven-variant `Provenance` union in `src/codegenie/primitives/vuln_provenance/provenance.py` (S1-03) is the canonical Phase-7 sum-type module: `_Frozen` base, `extra="forbid"`, `match`/`assert_never` anchor, sorted `__all__`. Mirror that module's shape. Do not invent a new sum-type idiom (`@dataclass`-only, or an `Enum`-tagged union) — the `_Frozen`-Pydantic-variant pattern is the established one.
- **Rule 12 — fail loud.** `Refused(reason="")` must be rejected at construction (AC-3) — an empty refusal reason is a silent failure dressed as a typed outcome. Likewise an `Unavailable` adapter folded into `High` would be a silent loss of a real signal. The whole point of M1 is *one honest value*; a falsely-`High` rollup is the worst possible regression.
- **Token-budget guard (Rule 6).** Single-session-implementable at ~4k tokens. The module is small (~80 LOC); the bulk of the work is the Hypothesis strategy in the property test. If the strategy fights you (e.g. it cannot reliably hit all three output arms for the coverage assertion), simplify it to compose `slices`/`adapters` from small fixed pools rather than fully-arbitrary generation — the monotonicity property only needs *some* variety, not maximal entropy.
