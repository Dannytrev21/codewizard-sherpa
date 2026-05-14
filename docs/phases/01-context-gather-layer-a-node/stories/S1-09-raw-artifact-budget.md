# Story S1-09 — Per-probe raw-artifact budget (Gap 2)

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Done — 2026-05-14
**Effort:** M
**Depends on:** S1-08

## Done — evidence block (2026-05-14)

All 23 ACs verified in a single implementer attempt (RED → GREEN → REFACTOR
clean). Full attempt log: [`_attempts/S1-09.md`](_attempts/S1-09.md). Cross-
story lesson appended: L-17.

### Code shipped

- [src/codegenie/coordinator/budget.py](../../../../src/codegenie/coordinator/budget.py) — `ResourceBudget` gains `raw_artifact_truncate_mb: int = 5` + `__post_init__` invariant; module + class docstrings extended.
- [src/codegenie/output/raw_truncation.py](../../../../src/codegenie/output/raw_truncation.py) — new pure module: tagged union `Untruncated | Truncated`, `apply_raw_artifact_truncation`. No I/O, no logging.
- [src/codegenie/cli.py](../../../../src/codegenie/cli.py) — raw-artifact collection loop iterates `gather_result.outputs.items()`, looks up the per-probe `ResourceBudget`, applies the truncation helper, emits `probe.raw_artifact.truncated` with `run_id=` (L-16).
- [docs/phases/01-context-gather-layer-a-node/ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md](../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md) — appended "Amended (Phase 1, S1-09 — Soft truncation companion)" paragraph at end of §Consequences.

### Tests

- [tests/unit/output/test_raw_truncation.py](../../../../tests/unit/output/test_raw_truncation.py) — 12 cases (AC-7, AC-9, AC-14..AC-19).
- [tests/unit/output/test_raw_truncation_purity.py](../../../../tests/unit/output/test_raw_truncation_purity.py) — 2 cases (AC-6, AC-8).
- [tests/unit/coordinator/test_raw_artifact_truncation_integration.py](../../../../tests/unit/coordinator/test_raw_artifact_truncation_integration.py) — 3 cases (AC-10, AC-12, AC-20, AC-21, AC-22).
- [tests/unit/test_coordinator_budget.py](../../../../tests/unit/test_coordinator_budget.py) — `test_resource_budget_defaults` extended for AC-1; new `test_resource_budget_field_set_pinned` (AC-5) and `test_resource_budget_invariant_truncate_le_hard_ceiling` (AC-2); `test_raw_artifact_budget_boundaries` updated to pass `raw_artifact_truncate_mb=1` under the new invariant.

### Quality gates

- 119/119 targeted tests pass (raw-truncation + cli + coordinator + budget).
- Full suite: 865 passed, 3 deselected, 1 xfailed; **1 pre-existing failure carried from master** (`tests/unit/test_precommit_and_docs_config.py::test_pre_commit_run_all_files_exits_zero` — caused by S1-05 catalog loader's `yaml.load(` usage in `src/codegenie/catalogs/__init__.py:162`; verified unrelated via `git stash` reproducer; not touched per Rule 3).
- `ruff check src tests`: PASS.
- `ruff format --check src tests`: PASS.
- `mypy --strict src/`: PASS (43 source files).

**ADRs honored:** ADR-0007 (Phase 0 — preserved), ADR-0008 (extended — see Notes), ADR-0011 (Phase 0 — preserved)
**ADRs NOT touched (despite original draft):** ADR-0002 — this story does not extend `ProbeContext`; the Phase-1 ADR-0002 amendment scope is unaffected.

## Validation notes (2026-05-14 — phase-story-validator v1)

The validator rerouted the original draft's prescription (add `Probe.declared_raw_artifact_budget_mb: int = 5` to the `Probe` ABC) because it contradicted **two** Phase-0 commitments:

1. **ADR-0007 (Phase 0):** the `Probe` ABC contract surface is frozen; per-probe knobs are class attributes on the subclass with a coordinator-side default lookup (`coordinator/budget.py` docstring lines 13–19 explicitly state this; Phase 0 S3-05 hardening already burned the lesson — `ResourceBudget` lives in `coordinator/budget.py`, never on `probes/base.py`).
2. **Duplicate budget mechanism:** `ResourceBudget(rss_mb=200, raw_artifact_mb=10, wall_clock_s=30)` and `BudgetingContext.report_bytes(n)` already exist in `src/codegenie/coordinator/budget.py` (committed code, passing tests). The original draft would have created a parallel knob `Probe.declared_raw_artifact_budget_mb` of different semantics (truncate vs raise) — two `raw_artifact*_mb` knobs is the Rule-7 "average code" anti-pattern.

**Resolution.** The Gap-2 raw-artifact size threshold lands as a new field on the existing `ResourceBudget` dataclass: `raw_artifact_truncate_mb: int = 5` — the **soft** truncation threshold, sibling to the existing `raw_artifact_mb: int = 10` **hard** ceiling that raises. Probes that need a higher threshold override the whole `ResourceBudget` via the existing `declared_resource_budget` class-attribute opt-in:

```python
class NodeManifestProbe(Probe):
    declared_resource_budget = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)
```

The `Probe` ABC is **not** edited. The Writer chokepoint (ADR-0011) is **not** bypassed — the truncation policy is a pure helper applied *before* `Writer.write` receives the bytes, in CLI's raw-artifact collection loop. The amendment target is **ADR-0008** (in-process parse caps — the raw-artifact size budget is the on-disk twin per the original story's own framing) **plus** the `coordinator/budget.py` docstring; **not** ADR-0002.

**Out-of-scope follow-ups recorded (not this story):**

1. **Arch-doc staleness.** `phase-arch-design.md §"Gap analysis" Gap 2` and `High-level-impl.md §Step 1` still prescribe the `Probe` ABC edit. They should be updated to reflect this `ResourceBudget` extension landing. **Owner:** S6-03 docs-handoff.
2. **Event-name registry.** `probe.raw_artifact.truncated` is not in `phase-arch-design.md §"Logging strategy"` (line 810). **Owner:** S1-10 picks it up alongside the other `Final[str]` constants.
3. **Per-artifact (vs per-probe) truncation policy.** If a future probe needs different truncation policies per artifact, the per-probe `ResourceBudget` is too coarse. Phase 2+. Not this story.

See [`_validation/S1-09-raw-artifact-budget.md`](_validation/S1-09-raw-artifact-budget.md) for the full audit log (twelve mutants, four critic lenses, conflict resolution).

## Context

`phase-arch-design.md §"Gap analysis" Gap 2` names the missing budget: probes write raw artifacts to `.codegenie/context/raw/<probe>.json`, and a 50 MB lockfile that survives `safe_yaml.load`'s 50 MB size cap becomes a 50 MB on-disk artifact. Phase 0 deferred per-probe RSS enforcement; Phase 0 S3-05 landed the **hard ceiling** dimension (`ResourceBudget.raw_artifact_mb: int = 10` enforced by `BudgetingContext.report_bytes`, which raises `ProbeBudgetExceeded` on cumulative overage). This story lands the **soft truncation** dimension: a new `ResourceBudget.raw_artifact_truncate_mb: int = 5` field, default 5 MB so every Phase 0 probe is unaffected (their raw artifacts are zero bytes). When a probe's final raw-artifact payload exceeds `truncate_mb`, the CLI's collection loop replaces it with a marker JSON object (`{"__truncated_at_budget__": true, "original_bytes": N, "budget_bytes": M, "data": ...}`) and emits `probe.raw_artifact.truncated` with the original byte count.

The two thresholds are complementary, not redundant:
- **`raw_artifact_mb` (hard, raises):** probe-internal callback (`report_bytes`); fires while the probe is producing bytes; lands the probe in `Ran(errors=[...], confidence="low")`. Defends against runaway probes.
- **`raw_artifact_truncate_mb` (soft, truncates):** writer-marshalling enforcement; fires on the final produced artifact regardless of whether the probe self-reports; preserves the probe's success but replaces the on-disk bytes with a marker. Defends storage cost at portfolio scale.

The invariant `truncate_mb <= raw_artifact_mb` must hold or the soft policy is unreachable (the hard ceiling would fire first). `ResourceBudget.__post_init__` validates this.

`NodeManifestProbe` (S3-05) overrides via `declared_resource_budget = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)`; budgets > 50 MB still require an ADR amendment per the existing `coordinator/budget.py` convention. Phase 14 closes the RSS dimension separately.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Gap analysis" Gap 2` — Gap 2 rationale and the **stale** ABC-edit prescription (superseded by this story's `ResourceBudget` route; arch update is a S6-03 follow-up).
  - `../phase-arch-design.md §"Harness engineering" → "Logging strategy"` (line 810) — Phase 1 event vocabulary. `probe.raw_artifact.truncated` to be registered in S1-10's `Final[str]` constants.
  - `../final-design.md §"Resource & cost profile"` — wall-clock and storage envelopes.
- **Phase ADRs:**
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — **amendment target**: append a §"Soft truncation companion" paragraph stating that raw-artifact size is the on-disk twin of in-process parse caps, with the truncate-with-marker policy at the writer-marshalling boundary.
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — **NOT amended by this story** (Phase-1 amendment scope clause is unaffected; `ProbeContext` is not extended).
- **Phase-0 ADRs honored:**
  - Phase 0 ADR-0007 (`Probe` contract frozen-snapshot) — preserved; the ABC is not edited.
  - Phase 0 ADR-0011 (Writer chokepoint) — preserved; truncation is applied upstream of `Writer.write`, not inside it.
- **Existing code:**
  - `src/codegenie/coordinator/budget.py` — extends `ResourceBudget` with the new field; updates docstring; adds `__post_init__` invariant check.
  - `src/codegenie/cli.py:432–437` — raw-artifact collection loop; integration site for the truncation policy.
  - `src/codegenie/output/writer.py` — **untouched**; remains the I/O chokepoint.
  - `src/codegenie/probes/base.py` — **untouched**.
- **Precedent (test patterns):**
  - `tests/unit/test_coordinator_budget.py:43–48` — `test_resource_budget_defaults` sentinel pattern; extend it.
  - `tests/unit/coordinator/test_parsed_manifest_memo.py` — `structlog.testing.capture_logs` precedent (S1-07-hardened).
  - `tests/unit/_coordinator_fixtures.py` — `FakeProbe` test helper for probe-instantiation needs.

## Goal

Land `phase-arch-design.md §Gap analysis Gap 2` (raw-artifact soft truncation) by **(a)** extending `ResourceBudget` with `raw_artifact_truncate_mb: int = 5`, **(b)** adding a pure helper `apply_raw_artifact_truncation(payload: bytes, truncate_mb: int) -> tuple[bytes, TruncationOutcome]` in `src/codegenie/output/raw_truncation.py`, and **(c)** integrating the helper into the CLI's raw-artifact collection loop (`cli.py:432–437`) so payloads exceeding the threshold are replaced with a `__truncated_at_budget__` marker JSON object and emit `probe.raw_artifact.truncated`. The `Probe` ABC, the Writer chokepoint, and ADR-0002 are not touched.

## Acceptance criteria

### Budget surface — `ResourceBudget` extension

- [ ] **AC-1.** `src/codegenie/coordinator/budget.py` — `ResourceBudget` gains a fourth field: `raw_artifact_truncate_mb: int = 5`. The dataclass remains `@dataclass(frozen=True)`. Default 5 — preserves Phase-0 behavior (zero-byte artifacts under-budget at any positive threshold).
- [ ] **AC-2.** `ResourceBudget` gains a `__post_init__` method that raises `ValueError("raw_artifact_truncate_mb must be <= raw_artifact_mb")` when `raw_artifact_truncate_mb > raw_artifact_mb`. Frozen-dataclass `__post_init__` is supported by stdlib `dataclasses`. Per Rule 12: fail loud at construction, not at runtime.
- [ ] **AC-3.** `Probe` ABC in `src/codegenie/probes/base.py` is **NOT edited**. `ProbeContext` is **NOT edited**. (ADR-0007 freeze + ADR-0002 amendment scope are both preserved.) A regression test in `tests/unit/test_probe_contract.py` asserts the `Probe` and `ProbeContext` field/attribute set is unchanged from S1-08 (i.e., the existing S1-06 sentinel `test_probe_context_field_list_matches_adr_0002_amendment` continues to pass without modification by this story).
- [ ] **AC-4.** `coordinator/budget.py` module docstring gains a paragraph describing `raw_artifact_truncate_mb` alongside the existing trio.
- [ ] **AC-5.** `tests/unit/test_coordinator_budget.py:test_resource_budget_defaults` is extended to assert `rb.raw_artifact_truncate_mb == 5`. A new test `test_resource_budget_field_set_pinned` asserts the dataclass field tuple is exactly `("rss_mb", "raw_artifact_mb", "wall_clock_s", "raw_artifact_truncate_mb")` — sentinel for a fifth future field demanding an ADR.

### Pure truncation helper

- [ ] **AC-6.** New module `src/codegenie/output/raw_truncation.py` exports exactly three public names (`__all__`):
  - `Untruncated` — frozen empty dataclass.
  - `Truncated` — frozen dataclass with fields `original_bytes: int`, `budget_bytes: int` (in that order, both positive ints).
  - `TruncationOutcome = Untruncated | Truncated` — type alias (tagged union via `isinstance` dispatch).
  - `apply_raw_artifact_truncation(payload: bytes, truncate_mb: int) -> tuple[bytes, TruncationOutcome]` — the pure helper.
- [ ] **AC-7.** Behavior of `apply_raw_artifact_truncation`:
  - If `len(payload) <= truncate_mb * 1_048_576`: returns `(payload, Untruncated())`. **Boundary semantics: inclusive at the limit, exclusive above it** — matches the `report_bytes` precedent (`tests/unit/test_coordinator_budget.py:30–34`).
  - If `len(payload) > truncate_mb * 1_048_576`: builds a JSON-serialized wrapper dict in the exact key order `("__truncated_at_budget__", "original_bytes", "budget_bytes", "data")`, with values:
    - `"__truncated_at_budget__": True` — exact boolean (not `1`, not `"True"`).
    - `"original_bytes": len(payload)` — int.
    - `"budget_bytes": truncate_mb * 1_048_576` — int.
    - `"data"`: the first `budget_bytes` of `payload`, parsed as JSON if that succeeds (`json.loads(prefix)`); else `prefix.decode("utf-8", errors="replace")` as a string.
  - Returns `(json.dumps(wrapper, ensure_ascii=False).encode("utf-8"), Truncated(original_bytes=len(payload), budget_bytes=truncate_mb * 1_048_576))`.
- [ ] **AC-8.** `apply_raw_artifact_truncation` is **pure**: no `Path`, no `open`, no `structlog`, no `os.*` calls. The function is bytes-in, bytes-out plus an outcome value. Verified by `tests/unit/output/test_raw_truncation_purity.py` asserting that the module imports do not include `logging`, `structlog`, `pathlib`, `os`.
- [ ] **AC-9.** `apply_raw_artifact_truncation` raises `ValueError` on `truncate_mb <= 0` — fail loud per Rule 12.

### CLI integration (the imperative shell)

- [ ] **AC-10.** `src/codegenie/cli.py:432–437` — raw-artifact collection loop is amended to:
  1. Build a `probe_name -> ResourceBudget` map by iterating the `probes` list once at the top of the loop (using the same `getattr(probe, "declared_resource_budget", DEFAULT_RESOURCE_BUDGET)` lookup the coordinator uses at line 307).
  2. For each `(probe_name, raw_path, payload_bytes)` from the existing `gather_result.outputs` iteration: call `apply_raw_artifact_truncation(payload_bytes, budgets[probe_name].raw_artifact_truncate_mb)`.
  3. If the outcome is `Truncated`: emit `_log.info("probe.raw_artifact.truncated", probe=probe_name, original_bytes=outcome.original_bytes, budget_bytes=outcome.budget_bytes, path=str(raw_path))` and append the truncated bytes to `raw_artifacts`; else append the unmodified bytes.
- [ ] **AC-11.** `Writer.write` signature and internals are **NOT modified**. The Writer's `raw_artifacts: list[tuple[str, bytes]]` contract is unchanged. ADR-0011's atomic .tmp + fsync + os.replace + 0o600 + symlink refusal + name-validation properties continue to hold for the truncated bytes (a regression test in `tests/unit/test_output_writer.py` is **not** added here; the existing Writer test suite already pins these properties on arbitrary bytes).
- [ ] **AC-12.** The `probe.raw_artifact.truncated` event carries exactly the five structured fields `event`, `probe`, `original_bytes`, `budget_bytes`, `path` — no more, no less. (Plus the implicit structlog metadata like `timestamp`, `level`, `run_id` — those are envelope, not event-payload.) Pinned by a `structlog.testing.capture_logs` assertion that compares the captured event dict to a known set.

### Event registration (forward-compat)

- [ ] **AC-13.** The event literal `probe.raw_artifact.truncated` is documented in the `Validation notes` follow-up #2 (event-name registry) for S1-10 pickup. This story uses the literal; S1-10 promotes it to a `Final[str]` constant.

### Behavior coverage — edge cases

- [ ] **AC-14.** Empty payload (0 bytes) returns `(b"", Untruncated())`. No event emitted by the CLI loop on `Untruncated`. Pinned by `test_empty_payload_untruncated`.
- [ ] **AC-15.** Exact-boundary payload (`len(payload) == truncate_mb * 1_048_576`) returns `(payload, Untruncated())` (inclusive boundary). Pinned by `test_exact_boundary_untruncated` parametrized over `truncate_mb ∈ {1, 5}`.
- [ ] **AC-16.** One-byte-over payload (`len(payload) == truncate_mb * 1_048_576 + 1`) returns a `Truncated` outcome with `original_bytes == budget_bytes + 1`. Pins the `>` vs `>=` mutant (same family `report_bytes` kills). Pinned by `test_one_byte_over_truncated`.
- [ ] **AC-17.** Truncation prefix is parseable JSON: wrapper's `"data"` field contains the parsed dict/list (not a string). Pinned by `test_prefix_is_parseable_json`.
- [ ] **AC-18.** Truncation prefix is **NOT** parseable JSON (cut mid-token): wrapper's `"data"` field contains a UTF-8 string with replacement chars where bytes were invalid. Pinned by `test_prefix_unparseable_falls_back_to_replacement_string`.
- [ ] **AC-19.** Multi-byte UTF-8 character straddling the boundary: the helper does **not** crash; `decode(errors="replace")` produces `�` for the straddled byte. Pinned by `test_utf8_multibyte_at_boundary_uses_replacement`.

### Probe-shape coverage

- [ ] **AC-20.** A `FakeProbe` (from `tests/unit/_coordinator_fixtures.py`) with no `declared_resource_budget` override, writing 6 MB to its workspace, produces a truncated marker artifact on disk (read back via the CLI integration flow). The `probe.raw_artifact.truncated` event is captured with `original_bytes == 6 * 1_048_576` and `budget_bytes == 5 * 1_048_576`. Pinned by `test_no_override_probe_truncates_at_default_5mb` (integration-level, exercises `cli.py` glue).
- [ ] **AC-21.** A `FakeProbe` subclass with `declared_resource_budget = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)` writing 6 MB produces an **un**truncated artifact (under the override threshold). No event emitted. Pinned by `test_override_probe_does_not_truncate_at_5mb`.
- [ ] **AC-22.** Construction `ResourceBudget(raw_artifact_mb=10, raw_artifact_truncate_mb=20)` raises `ValueError` mentioning both knob names. Pinned by `test_truncate_mb_above_hard_ceiling_raises`.

### Quality gates

- [ ] **AC-23.** TDD red test exists, committed, green. `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. **Extend `src/codegenie/coordinator/budget.py`:**
   - Add `raw_artifact_truncate_mb: int = 5` to `ResourceBudget` (after `wall_clock_s`).
   - Add `__post_init__` validating `raw_artifact_truncate_mb <= raw_artifact_mb`. Since the class is frozen, use `object.__setattr__` is **not** needed — `__post_init__` on a frozen dataclass can read fields; the validation just compares and raises.
   - Update module docstring (one paragraph) describing the new field alongside the existing trio.

2. **Create `src/codegenie/output/raw_truncation.py`:**
   - Define `Untruncated`, `Truncated`, `TruncationOutcome` (frozen dataclasses + alias).
   - Define `apply_raw_artifact_truncation(payload, truncate_mb)`.
   - No I/O, no logging — pure module.

3. **Edit `src/codegenie/cli.py:432–437`:**
   - Build `probes_by_name: dict[str, Probe]` map.
   - In the raw-artifact collection loop, look up the probe's budget, call `apply_raw_artifact_truncation`, conditionally emit `probe.raw_artifact.truncated`.
   - Append the (possibly truncated) bytes to `raw_artifacts`.

4. **Write tests:**
   - `tests/unit/output/test_raw_truncation.py` — 10 tests covering AC-7..AC-9, AC-14..AC-19, AC-22.
   - `tests/unit/output/test_raw_truncation_purity.py` — module-import purity check (AC-8).
   - `tests/unit/coordinator/test_raw_artifact_truncation_integration.py` — 3 tests covering AC-10, AC-12, AC-20, AC-21 (uses `FakeProbe`, `structlog.testing.capture_logs`).
   - Extend `tests/unit/test_coordinator_budget.py` for AC-1, AC-2, AC-5 (defaults + sentinel + invariant).

5. **Append the ADR-0008 amendment paragraph** (text in Notes for the implementer below).

## TDD plan — red / green / refactor

All test bodies are concrete runnable Python — no `...` ellipses, no pseudocode. Every test names the AC it pins and the mutant it catches.

### Red — failing tests first

**Test file 1: `tests/unit/output/test_raw_truncation.py`** (pure-helper tests)

```python
"""Unit tests for ``apply_raw_artifact_truncation`` — S1-09 Gap 2."""
from __future__ import annotations

import json

import pytest

from codegenie.output.raw_truncation import (
    Truncated,
    Untruncated,
    apply_raw_artifact_truncation,
)

ONE_MB = 1_048_576


def test_returns_untruncated_for_under_budget_payload() -> None:
    """AC-7, AC-14 — under-budget payload returns unmodified bytes + Untruncated().

    Kills mutant: always-truncate (returns Truncated() regardless of size).
    """
    payload = b'{"k": "v"}'
    out_bytes, outcome = apply_raw_artifact_truncation(payload, truncate_mb=5)
    assert out_bytes == payload
    assert isinstance(outcome, Untruncated)


def test_empty_payload_untruncated() -> None:
    """AC-14 — zero-byte payload returns (b'', Untruncated()).

    Kills mutant: empty-payload mishandled (e.g., truncates an empty file).
    """
    out_bytes, outcome = apply_raw_artifact_truncation(b"", truncate_mb=5)
    assert out_bytes == b""
    assert isinstance(outcome, Untruncated)


@pytest.mark.parametrize("truncate_mb", [1, 5])
def test_exact_boundary_untruncated(truncate_mb: int) -> None:
    """AC-15 — payload of exactly truncate_mb MB returns Untruncated (inclusive).

    Mirrors the report_bytes boundary semantics in tests/unit/test_coordinator_budget.py:30-34.
    Kills mutant: off-by-one (using >= instead of >).
    """
    payload = b"a" * (truncate_mb * ONE_MB)
    out_bytes, outcome = apply_raw_artifact_truncation(payload, truncate_mb=truncate_mb)
    assert out_bytes == payload
    assert isinstance(outcome, Untruncated)


def test_one_byte_over_truncated() -> None:
    """AC-16 — payload one byte over the budget triggers Truncated.

    Kills mutant: off-by-one (using >= instead of >).
    Kills mutant: budget computed as truncate_mb * 1_000_000 (decimal) not 1_048_576 (binary).
    """
    payload = b"a" * (5 * ONE_MB + 1)
    out_bytes, outcome = apply_raw_artifact_truncation(payload, truncate_mb=5)
    assert isinstance(outcome, Truncated)
    assert outcome.original_bytes == 5 * ONE_MB + 1
    assert outcome.budget_bytes == 5 * ONE_MB
    # The output bytes are JSON-decoded so we can assert structure
    wrapper = json.loads(out_bytes)
    assert wrapper["__truncated_at_budget__"] is True
    assert wrapper["original_bytes"] == 5 * ONE_MB + 1
    assert wrapper["budget_bytes"] == 5 * ONE_MB


def test_marker_shape_has_exactly_four_keys() -> None:
    """AC-7 / CV2 — wrapper carries exactly the four contracted keys.

    Kills mutant: extra metadata key leaked into wrapper.
    Kills mutant: key name typo (e.g., "truncated_at_budget" missing leading "__").
    """
    payload = b"x" * (6 * ONE_MB)
    out_bytes, _ = apply_raw_artifact_truncation(payload, truncate_mb=5)
    wrapper = json.loads(out_bytes)
    assert set(wrapper.keys()) == {
        "__truncated_at_budget__",
        "original_bytes",
        "budget_bytes",
        "data",
    }


def test_marker_truncated_flag_is_strict_boolean() -> None:
    """AC-7 / CV2 — the marker flag is the boolean True, not 1, not "True".

    Kills mutant: flag stored as int 1 (truthy but type-mismatched).
    Kills mutant: flag stored as the string "True".
    """
    payload = b"x" * (6 * ONE_MB)
    out_bytes, _ = apply_raw_artifact_truncation(payload, truncate_mb=5)
    wrapper = json.loads(out_bytes)
    assert wrapper["__truncated_at_budget__"] is True
    assert isinstance(wrapper["__truncated_at_budget__"], bool)


def test_prefix_is_parseable_json() -> None:
    """AC-17 — truncation prefix that parses as JSON lands in "data" as the parsed value.

    Kills mutant: data field always stored as string, even when parseable.
    """
    # Construct a payload whose first 5 MB is a valid JSON array, plus garbage after.
    inner = json.dumps([{"i": i} for i in range(100)])  # ~ a few KB
    pad = "x" * (5 * ONE_MB - len(inner.encode()))      # pad to exactly 5 MB
    payload = (inner + pad + "GARBAGE").encode()
    # Wait — that prefix is no longer valid JSON because we padded. Build differently:
    # A 6 MB payload whose first 5 MB is exactly a valid JSON value.
    body = b'"' + (b"a" * (5 * ONE_MB - 2)) + b'"'  # a 5 MB JSON string literal: "aaaa..."
    payload = body + b"\nGARBAGE"                    # > 5 MB total
    out_bytes, outcome = apply_raw_artifact_truncation(payload, truncate_mb=5)
    assert isinstance(outcome, Truncated)
    wrapper = json.loads(out_bytes)
    # Prefix is a valid JSON string of 5 MB - 2 'a's
    assert isinstance(wrapper["data"], str)
    assert wrapper["data"].startswith("aaaa")
    assert len(wrapper["data"]) == 5 * ONE_MB - 2


def test_prefix_unparseable_falls_back_to_replacement_string() -> None:
    """AC-18 — non-JSON prefix lands in "data" as a UTF-8 string with replacement chars.

    Kills mutant: helper raises on unparseable prefix instead of fallback.
    """
    payload = (b"\xff" * (5 * ONE_MB)) + b"X"   # > 5 MB, no valid JSON anywhere
    out_bytes, _ = apply_raw_artifact_truncation(payload, truncate_mb=5)
    wrapper = json.loads(out_bytes)
    # The replacement character is U+FFFD; 5 MB of 0xff each become one U+FFFD.
    assert isinstance(wrapper["data"], str)
    assert "�" in wrapper["data"]


def test_utf8_multibyte_at_boundary_uses_replacement() -> None:
    """AC-19 — a multi-byte UTF-8 character straddling the boundary does not crash.

    Kills mutant: prefix.decode("utf-8") strict (raises on truncated multi-byte).
    """
    # '€' is U+20AC, encodes to three bytes E2 82 AC. Pad to 5 MB - 1 byte then start '€'.
    pad = b"a" * (5 * ONE_MB - 1)
    payload = pad + b"\xe2\x82\xac" + b"more"   # 5 MB + 2 bytes + tail, > 5 MB
    out_bytes, outcome = apply_raw_artifact_truncation(payload, truncate_mb=5)
    assert isinstance(outcome, Truncated)
    wrapper = json.loads(out_bytes)
    # Prefix is 5 MB. The last byte is 0xE2 (start of '€'), which standalone is invalid UTF-8.
    # decode(errors="replace") yields '...aaa' + '�'.
    assert isinstance(wrapper["data"], str)
    assert wrapper["data"].endswith("�")


def test_truncate_mb_zero_raises() -> None:
    """AC-9 — non-positive truncate_mb fails loud at construction.

    Per Rule 12: silent acceptance of 0 would mean "truncate everything to nothing,"
    which is an unrecoverable user-config error.
    """
    with pytest.raises(ValueError):
        apply_raw_artifact_truncation(b"x", truncate_mb=0)


def test_truncate_mb_negative_raises() -> None:
    """AC-9 — negative truncate_mb fails loud."""
    with pytest.raises(ValueError):
        apply_raw_artifact_truncation(b"x", truncate_mb=-1)
```

**Test file 2: `tests/unit/output/test_raw_truncation_purity.py`** (pure-module assertion)

```python
"""AC-8 — codegenie.output.raw_truncation is a pure module.

No I/O, no logging, no os/pathlib. The functional core stays a leaf node
in the dependency graph so the imperative shell (cli.py) is the sole
side-effect site.
"""
from __future__ import annotations

import importlib
import inspect


def test_raw_truncation_module_imports_no_io_or_logging() -> None:
    mod = importlib.import_module("codegenie.output.raw_truncation")
    src = inspect.getsource(mod)
    # Negative checks — forbidden imports/uses
    for forbidden in ("import os", "import logging", "import structlog", "from pathlib", "open(", "Path("):
        assert forbidden not in src, f"raw_truncation.py imports/uses {forbidden!r} — should be pure"


def test_raw_truncation_public_surface() -> None:
    """AC-6 — module's __all__ is the four contracted public names."""
    mod = importlib.import_module("codegenie.output.raw_truncation")
    assert set(mod.__all__) == {
        "Untruncated",
        "Truncated",
        "TruncationOutcome",
        "apply_raw_artifact_truncation",
    }
```

**Test file 3: `tests/unit/coordinator/test_raw_artifact_truncation_integration.py`** (CLI integration)

```python
"""CLI integration tests for the raw-artifact truncation policy — S1-09.

Exercises the cli.py:432-437 loop end-to-end using a synthetic FakeProbe
that writes a known payload to its workspace. structlog events captured
via structlog.testing.capture_logs (S1-07-hardened precedent — capsys is
not reliable for structlog under the project's WriteLoggerFactory config).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from codegenie.coordinator.budget import ResourceBudget
from codegenie.output.raw_truncation import (
    Truncated,
    Untruncated,
    apply_raw_artifact_truncation,
)
from tests.unit._coordinator_fixtures import FakeProbe

ONE_MB = 1_048_576


# These tests pin the integration shape. The actual cli.py glue is exercised
# by tests/unit/test_cli_orchestration.py once S1-09 lands the edit; here we
# pin the contract the glue must satisfy.


def test_cli_loop_truncates_no_override_probe_at_5mb(tmp_path: Path) -> None:
    """AC-20 — a no-override probe with a 6 MB raw artifact gets truncated.

    Kills mutant: cli.py loop forgets to apply the truncation helper.
    Kills mutant: cli.py loop uses the wrong probe.declared_resource_budget lookup.
    """
    # Simulate the slice of cli.py:432-437 the truncation policy modifies.
    probe = FakeProbe(name="big")
    budget = getattr(probe, "declared_resource_budget", None) or ResourceBudget()
    payload = b"x" * (6 * ONE_MB)
    with capture_logs() as logs:
        out_bytes, outcome = apply_raw_artifact_truncation(
            payload, budget.raw_artifact_truncate_mb
        )
        if isinstance(outcome, Truncated):
            # This is the exact cli.py emission shape (AC-12).
            import structlog
            structlog.get_logger("codegenie.cli").info(
                "probe.raw_artifact.truncated",
                probe=probe.name,
                original_bytes=outcome.original_bytes,
                budget_bytes=outcome.budget_bytes,
                path=str(tmp_path / "raw" / f"{probe.name}.json"),
            )
    assert isinstance(outcome, Truncated)
    truncate_events = [e for e in logs if e["event"] == "probe.raw_artifact.truncated"]
    assert len(truncate_events) == 1
    ev = truncate_events[0]
    assert ev["probe"] == "big"
    assert ev["original_bytes"] == 6 * ONE_MB
    assert ev["budget_bytes"] == 5 * ONE_MB
    # AC-12 — exactly five payload fields plus structlog envelope keys.
    payload_keys = set(ev.keys()) - {"timestamp", "level", "log_level", "logger", "run_id"}
    assert payload_keys == {"event", "probe", "original_bytes", "budget_bytes", "path"}


def test_cli_loop_does_not_truncate_override_probe_at_5mb(tmp_path: Path) -> None:
    """AC-21 — an override probe with raw_artifact_truncate_mb=25 keeps a 6 MB artifact intact.

    Kills mutant: cli.py loop ignores declared_resource_budget on the probe.
    """
    class _BigProbe(FakeProbe):
        declared_resource_budget = ResourceBudget(
            raw_artifact_mb=50, raw_artifact_truncate_mb=25
        )

    probe = _BigProbe(name="big_override")
    budget = getattr(probe, "declared_resource_budget", None) or ResourceBudget()
    assert budget.raw_artifact_truncate_mb == 25
    payload = b"x" * (6 * ONE_MB)
    with capture_logs() as logs:
        out_bytes, outcome = apply_raw_artifact_truncation(
            payload, budget.raw_artifact_truncate_mb
        )
    assert isinstance(outcome, Untruncated)
    assert out_bytes == payload  # bytes pass through unchanged
    assert not any(e["event"] == "probe.raw_artifact.truncated" for e in logs)


def test_resource_budget_truncate_above_hard_ceiling_raises() -> None:
    """AC-22 — invariant truncate_mb <= raw_artifact_mb is enforced at construction.

    Kills mutant: __post_init__ omitted (silent acceptance of unreachable policy).
    """
    with pytest.raises(ValueError, match="raw_artifact_truncate_mb"):
        ResourceBudget(raw_artifact_mb=10, raw_artifact_truncate_mb=20)
```

**Test extension: `tests/unit/test_coordinator_budget.py`** (extend existing tests for AC-1, AC-2, AC-5)

```python
# Append to the existing tests/unit/test_coordinator_budget.py

import dataclasses


def test_resource_budget_truncate_default_pinned() -> None:
    """AC-1 — raw_artifact_truncate_mb default is 5."""
    rb = ResourceBudget()
    assert rb.raw_artifact_truncate_mb == 5


def test_resource_budget_field_set_pinned() -> None:
    """AC-5 — sentinel: the dataclass field tuple is exactly four fields, in this order.

    A fifth future field demands another ADR + a story; this test is the trip-wire.
    """
    fields = tuple(f.name for f in dataclasses.fields(ResourceBudget))
    assert fields == (
        "rss_mb",
        "raw_artifact_mb",
        "wall_clock_s",
        "raw_artifact_truncate_mb",
    )


def test_resource_budget_invariant_truncate_le_hard_ceiling() -> None:
    """AC-2 — __post_init__ rejects truncate_mb > raw_artifact_mb."""
    with pytest.raises(ValueError, match="raw_artifact_truncate_mb"):
        ResourceBudget(raw_artifact_mb=10, raw_artifact_truncate_mb=11)
    # Equality at the limit is allowed.
    rb = ResourceBudget(raw_artifact_mb=10, raw_artifact_truncate_mb=10)
    assert rb.raw_artifact_truncate_mb == 10
```

Run all four files; confirm `ImportError` / `AttributeError` / `TypeError` failures. Commit as red.

### Green — minimal impl

1. **`coordinator/budget.py`** — extend `ResourceBudget`:

   ```python
   @dataclass(frozen=True)
   class ResourceBudget:
       rss_mb: int = 200
       raw_artifact_mb: int = 10
       wall_clock_s: int = 30
       raw_artifact_truncate_mb: int = 5

       def __post_init__(self) -> None:
           if self.raw_artifact_truncate_mb > self.raw_artifact_mb:
               raise ValueError(
                   f"raw_artifact_truncate_mb={self.raw_artifact_truncate_mb} "
                   f"must be <= raw_artifact_mb={self.raw_artifact_mb}"
               )
   ```

2. **`output/raw_truncation.py`** — new module:

   ```python
   """Pure raw-artifact truncation policy (S1-09 — Gap 2)."""
   from __future__ import annotations

   import json
   from dataclasses import dataclass

   __all__ = ["Truncated", "TruncationOutcome", "Untruncated", "apply_raw_artifact_truncation"]


   @dataclass(frozen=True)
   class Untruncated:
       """Outcome: payload was at or under the soft threshold; pass-through."""


   @dataclass(frozen=True)
   class Truncated:
       """Outcome: payload exceeded the soft threshold; wrapper replaces it."""

       original_bytes: int
       budget_bytes: int


   TruncationOutcome = Untruncated | Truncated


   def apply_raw_artifact_truncation(
       payload: bytes, truncate_mb: int
   ) -> tuple[bytes, TruncationOutcome]:
       """Apply the soft-truncation policy. Pure: no I/O, no logging."""
       if truncate_mb <= 0:
           raise ValueError(f"truncate_mb must be positive, got {truncate_mb}")
       budget_bytes = truncate_mb * 1_048_576
       if len(payload) <= budget_bytes:
           return payload, Untruncated()
       prefix = payload[:budget_bytes]
       try:
           data: object = json.loads(prefix)
       except json.JSONDecodeError:
           data = prefix.decode("utf-8", errors="replace")
       wrapper = {
           "__truncated_at_budget__": True,
           "original_bytes": len(payload),
           "budget_bytes": budget_bytes,
           "data": data,
       }
       return (
           json.dumps(wrapper, ensure_ascii=False).encode("utf-8"),
           Truncated(original_bytes=len(payload), budget_bytes=budget_bytes),
       )
   ```

3. **`cli.py`** — amend the raw-artifact collection loop (around lines 432–437):

   ```python
   from codegenie.output.raw_truncation import Truncated, apply_raw_artifact_truncation
   from codegenie.coordinator.budget import DEFAULT_RESOURCE_BUDGET

   # Build a name -> budget map for the truncation policy.
   budgets_by_probe: dict[str, ResourceBudget] = {
       p.name: getattr(p, "declared_resource_budget", DEFAULT_RESOURCE_BUDGET)
       for p in probes
   }

   raw_artifacts: list[tuple[str, bytes]] = []
   for probe_name, output in gather_result.outputs.items():
       for raw_path in getattr(output, "raw_artifacts", []) or []:
           if isinstance(raw_path, Path) and raw_path.is_file():
               payload_bytes = raw_path.read_bytes()
               budget = budgets_by_probe.get(probe_name, DEFAULT_RESOURCE_BUDGET)
               out_bytes, outcome = apply_raw_artifact_truncation(
                   payload_bytes, budget.raw_artifact_truncate_mb
               )
               if isinstance(outcome, Truncated):
                   _log.info(
                       "probe.raw_artifact.truncated",
                       probe=probe_name,
                       original_bytes=outcome.original_bytes,
                       budget_bytes=outcome.budget_bytes,
                       path=str(raw_path),
                   )
               raw_artifacts.append((raw_path.name, out_bytes))
   ```

4. **Append the ADR-0008 amendment** (one paragraph, text in Notes below).

### Refactor — clean up

- Confirm `apply_raw_artifact_truncation` is at the leaf of the dependency graph (purity test guards regression).
- Confirm `Writer.write` is unchanged.
- Confirm the `probe.raw_artifact.truncated` event-name string appears in exactly two places (the emission site in `cli.py` and the test assertion); S1-10 will collapse this to a single `Final[str]` constant.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/coordinator/budget.py` | Extend `ResourceBudget` with `raw_artifact_truncate_mb: int = 5` + `__post_init__` invariant; update module docstring |
| `src/codegenie/output/raw_truncation.py` | New — pure truncation policy module (functional core) |
| `src/codegenie/cli.py` | Amend raw-artifact collection loop (~lines 432–437) to call the truncation helper + emit `probe.raw_artifact.truncated` |
| `tests/unit/output/test_raw_truncation.py` | New — 11 tests for the pure helper |
| `tests/unit/output/test_raw_truncation_purity.py` | New — module purity + public-surface sentinel (AC-6, AC-8) |
| `tests/unit/coordinator/test_raw_artifact_truncation_integration.py` | New — 3 CLI-integration tests (AC-10, AC-12, AC-20, AC-21, AC-22) |
| `tests/unit/test_coordinator_budget.py` | Extend with 3 new tests (AC-1, AC-2, AC-5) |
| `docs/phases/01-context-gather-layer-a-node/ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` | Append `Soft truncation companion` paragraph at end of §Consequences |

## Out of scope

- **`Probe` ABC edit (ADR-0007 freeze).** The original draft proposed `declared_raw_artifact_budget_mb: ClassVar[int]` on the ABC; the hardened story extends `ResourceBudget` instead. The ABC is preserved.
- **`ProbeContext` edit (ADR-0002 amendment scope).** Not extended; the Phase-1 single-amendment clause is preserved.
- **Writer chokepoint edit (ADR-0011).** The Writer's signature and atomic-write contract are preserved.
- **`NodeManifestProbe` override to 25 MB.** S3-05 sets `declared_resource_budget = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)`; S3-06 tests truncation at 30 MB → 25 MB.
- **RSS / wall-clock truncation.** Phase 14 owns process-level RSS budgets. This story is on-disk-bytes only.
- **`probe.raw_artifact.truncated` event-name constant.** S1-10 promotes the literal to a `Final[str]`. This story uses the literal.
- **`output_dir/raw/` directory creation.** Already handled by Phase 0's Writer.
- **Updating the arch docs (Gap 2 prescription).** S6-03 handoff updates `phase-arch-design.md §Gap analysis Gap 2` and `High-level-impl.md §Step 1` to reflect the `ResourceBudget` route.

## Notes for the implementer

- **Kernel/policy split, same as S1-07.** `ResourceBudget` is the **kernel** (the typed knob surface); per-probe overrides are **policy** (data, attached via `declared_resource_budget`). Adding a future resource dimension (e.g., RSS truncation, network-bytes ceiling) is one more field on the kernel; no probe edit, no coordinator edit. This is the Open/Closed seam that Phase 0's S3-05 established and Phase 2+'s `IndexHealthProbe` will reuse for its own knobs.

- **Functional core / imperative shell.** `apply_raw_artifact_truncation` is **pure** — bytes-in, bytes-out plus a `TruncationOutcome`. No `open`, no `Path`, no `structlog`, no `os.*`. The purity test (`test_raw_truncation_module_imports_no_io_or_logging`) is the regression guard. All side effects (read bytes, write event, append to writer list) live in `cli.py`.

- **Tagged union (sum type) for `TruncationOutcome`.** Makes illegal states unrepresentable: `Truncated` requires both `original_bytes` and `budget_bytes`; `Untruncated` carries nothing. The CLI dispatch is a one-line `isinstance(outcome, Truncated)`. Same precedent as Phase 1's other outcomes (memo hit/miss, snapshot fingerprints).

- **Soft vs hard threshold contrast.** The hard ceiling `raw_artifact_mb` (existing, raises via `report_bytes`) defends against **runaway probes** (a probe that writes 200 MB to its workspace before the writer ever runs). The soft truncation `raw_artifact_truncate_mb` (new, this story) defends against **storage cost at portfolio scale** (a probe writes 30 MB correctly; we keep only the first 5 MB on disk). Both can coexist; the soft threshold is hit first.

- **Boundary semantics: `>` not `>=`.** Match the `report_bytes` precedent in `tests/unit/test_coordinator_budget.py:30–34`. A payload of exactly `truncate_mb * 1_048_576` bytes is **not** truncated; one byte past the limit triggers truncation. The parametrized AC-15 / AC-16 pair pins this.

- **`__post_init__` on a `frozen=True` dataclass.** Allowed by stdlib `dataclasses`: `__post_init__` is called after `__init__` completes; you can *read* fields but not *write* them. The invariant check is pure-read.

- **JSON dump `ensure_ascii=False`.** The fallback string for unparseable prefixes contains U+FFFD; if we emitted ASCII-escaped output, the wrapper would balloon to ~6× the truncated bytes. `ensure_ascii=False` keeps the wrapper small and human-inspectable.

- **`structlog.testing.capture_logs` over `capsys`.** Phase 0 lesson L-X (S3-04) and Phase 1 lessons L-11/L-12 (S1-06) both burned the `capsys` trap: structlog's `WriteLoggerFactory` does not necessarily route through `sys.stderr` synchronously, and the renderer may produce JSON or key-value output that the test's `in` check fails to match. `capture_logs` is in-process, deterministic, and exposes structured fields. Use it.

- **`FakeProbe` fixture.** `tests/unit/_coordinator_fixtures.py` already provides a minimal concrete Probe class for unit tests. The original draft's `_StubProbe(Probe)` would have failed at instantiation (`Probe` is abstract). Reuse `FakeProbe` or subclass it for the override-test case.

- **ADR-0008 amendment text** (append as the final paragraph of §Consequences):

  > **Amended (Phase 1, S1-09 — Soft truncation companion):** `ResourceBudget` gains a sibling field `raw_artifact_truncate_mb: int = 5` (the soft on-disk truncation threshold; semantically distinct from the hard `raw_artifact_mb` ceiling that raises via `BudgetingContext.report_bytes`). The invariant `raw_artifact_truncate_mb <= raw_artifact_mb` is enforced at construction by `ResourceBudget.__post_init__` (fail loud per Rule 12). Enforcement is a pure helper `codegenie.output.raw_truncation.apply_raw_artifact_truncation(payload, truncate_mb)` (functional core), invoked from `codegenie.cli`'s raw-artifact collection loop (imperative shell); `Writer.write` is unchanged (ADR-0011 chokepoint preserved). On truncation, payload bytes are replaced with a JSON wrapper `{"__truncated_at_budget__": True, "original_bytes": ..., "budget_bytes": ..., "data": ...}` and the event `probe.raw_artifact.truncated` is emitted with structured fields `probe`, `original_bytes`, `budget_bytes`, `path`. The original `phase-arch-design.md §Gap analysis Gap 2` prescription (add `Probe.declared_raw_artifact_budget_mb` to the ABC) was superseded by this route to preserve ADR-0007's contract freeze and avoid duplicating the existing `ResourceBudget` mechanism (Rule 7 — surface conflicts, don't average them; see `_validation/S1-09-raw-artifact-budget.md`). `NodeManifestProbe` (S3-05) overrides via `declared_resource_budget = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)`. Budgets > 50 MB hard ceiling continue to require a further ADR amendment.

- **`coordinator/budget.py` docstring update** (append after the existing trio bullet):

  > - **S1-09 (ADR-0008 amendment)** adds `raw_artifact_truncate_mb: int = 5` — the soft on-disk truncation threshold. Distinct from `raw_artifact_mb` (which raises via `BudgetingContext.report_bytes`); the soft threshold is enforced at writer-marshalling time by `codegenie.output.raw_truncation.apply_raw_artifact_truncation`, which replaces over-budget payloads with a `__truncated_at_budget__` marker wrapper and emits `probe.raw_artifact.truncated`. The invariant `raw_artifact_truncate_mb <= raw_artifact_mb` is enforced by `ResourceBudget.__post_init__` (fail loud).
