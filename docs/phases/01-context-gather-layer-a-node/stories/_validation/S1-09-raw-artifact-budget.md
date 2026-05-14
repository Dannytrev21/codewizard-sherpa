# Validation report — S1-09 Per-probe raw-artifact budget (Gap 2)

**Story:** [`../S1-09-raw-artifact-budget.md`](../S1-09-raw-artifact-budget.md)
**Validator version:** phase-story-validator v1
**Date:** 2026-05-14
**Verdict:** **HARDENED**

## Executive summary

S1-09 lands `phase-arch-design.md §"Gap analysis"` Gap 2 — a per-probe raw-artifact size budget that truncates with a marker and emits `probe.raw_artifact.truncated`. The original draft had a sound **intent** (truncate-with-marker for 50 MB lockfile dumps) but four block-tier defects that, left unaddressed, would have caused the executor to either (a) fail CI on the ADR-0007 Probe-ABC freeze, (b) duplicate the existing `ResourceBudget` mechanism with conflicting semantics, (c) bypass the ADR-0011 Writer chokepoint, or (d) write tests that can't instantiate the abstract `Probe` class.

The critics ran against `phase-arch-design.md §Gap analysis Gap 2 & §Logging strategy`, ADR-0002, ADR-0008, Phase 0 ADR-0007 (Probe contract freeze), Phase 0 ADR-0011, the current `src/codegenie/coordinator/{budget,coordinator}.py`, `src/codegenie/output/writer.py`, `src/codegenie/cli.py:420-465`, `src/codegenie/probes/base.py`, `tests/unit/test_coordinator_budget.py`, `tests/unit/coordinator/test_parsed_manifest_memo.py`, and the S1-06 / S1-07 / S1-08 hardened-story precedent (kernel/policy split; `BudgetingContext` mirroring; `structlog.testing.capture_logs`; mutation-killer tests). No `NEEDS RESEARCH` findings — every weakness is answerable from authority docs + Phase 1 precedent. Stage 3 (researcher) skipped per skill's token-economy guidance.

## Departure from arch surfaced and recorded (per Rule 7)

`phase-arch-design.md §Gap analysis Gap 2` and `High-level-impl.md §Step 1` both prescribe **"add `Probe.declared_raw_artifact_budget_mb: int = 5` class attribute"**. This contradicts the **more-recent, more-tested** Phase 0 mechanism (committed code with passing tests) that explicitly chose to keep budgets *off* the `Probe` ABC per ADR-0007's freeze (see `coordinator/budget.py` docstring lines 13–19: *"The default lives here (NOT on `probes/base.py`'s `Probe` ABC) because ADR-0007 freezes the contract surface; budgets are a coordinator-side concern."*). Phase 0's S3-05 hardening already burned this lesson. Per Rule 7 (surface conflicts, don't average them), the hardened story routes Gap 2 through the established `ResourceBudget` extension point — `raw_artifact_truncate_mb: int = 5` added to `ResourceBudget` (sibling to the existing `raw_artifact_mb: int = 10` hard ceiling). This preserves ADR-0007 *and* yields a single, uniform per-probe budget surface. The arch docs are stale and are flagged for follow-up in `Validation notes` on the story.

## Context Brief

### Story snapshot
- **Goal (verbatim, original):** Add `Probe.declared_raw_artifact_budget_mb: int = 5`; coordinator enforces, truncates with a marker, emits `probe.raw_artifact.truncated`.
- **Goal (intent, preserved):** Land Gap 2 — a per-probe raw-artifact size threshold that truncates with a marker JSON object at the boundary (default 5 MB, override-able per probe), emitting a structlog event with the original byte count. **The truncation is a soft policy at write time, distinct from the hard `report_bytes` ceiling that raises** — this story owns truncation; the hard ceiling is already shipped by Phase 0 S3-05.

### Phase / arch constraints
- **ADR-0007 (Phase 0):** `Probe` ABC contract surface is frozen. Per-probe knobs live as opt-in class attributes (e.g., `declared_resource_budget = ResourceBudget(...)`), not as fields on the ABC. Coordinator reads via `getattr(probe, "...", DEFAULT)`.
- **ADR-0002 (Phase 1) amendment scope:** "No further extensions to `ProbeContext` are permitted in Phase 1 without a new ADR." S1-09 does not edit `ProbeContext`, so this is unviolated — but the story's draft attempted to edit `Probe` ABC, which is the parallel ADR-0007 freeze. Both routes are blocked.
- **ADR-0008 (Phase 1):** In-process parse caps in `parsers/`. The story's framing (Gap 2 raw-artifact budget is the "on-disk twin") is sound — the truncation policy is a natural extension of ADR-0008's protect-the-disk story.
- **ADR-0011 (Phase 0, Writer chokepoint):** `Writer.write` is the sole place leaf names hit disk; atomic .tmp + fsync + os.replace + 0o600 + symlink refusal + name-validation. Truncation **must not bypass** this chokepoint.

### Existing infrastructure the original story missed
1. `src/codegenie/coordinator/budget.py` — `ResourceBudget(rss_mb=200, raw_artifact_mb=10, wall_clock_s=30)` frozen dataclass; `DEFAULT_RESOURCE_BUDGET` singleton; `BudgetingContext(workspace, raw_artifact_mb, bytes_written, parsed_manifest, input_snapshot)` runtime ctx with `report_bytes(n)` callback that raises `ProbeBudgetExceeded` on cumulative overage (`> raw_artifact_mb` strict).
2. `src/codegenie/coordinator/coordinator.py:307–313` — coordinator reads `budget = getattr(probe, "declared_resource_budget", DEFAULT_RESOURCE_BUDGET)` and threads `budget.raw_artifact_mb` into `BudgetingContext` via `_make_probe_context`.
3. `src/codegenie/output/writer.py:142–185` — `Writer.write(envelope, raw_artifacts: list[tuple[str, bytes]], output_dir)` is the I/O chokepoint. Probes do NOT call this directly; CLI marshalls bytes between probe-side workspace files and the writer.
4. `src/codegenie/cli.py:432–437` — CLI's raw-artifact collection loop reads each probe's `raw_artifacts: list[Path]` back into `list[tuple[str, bytes]]` for the Writer.
5. `tests/unit/test_coordinator_budget.py:43–48` — `test_resource_budget_defaults` pins the dataclass field set; sentinel for extensions.

### Goal-to-AC trace (original draft)
- AC-1..AC-2 (Probe ABC edit) → goal: contradicts ADR-0007. **REROUTE.**
- AC-3 (coordinator/writer truncation) → goal: YES, but the prescribed function `_write_raw_artifact_with_budget` doesn't exist and bypasses Writer chokepoint. **HARDEN.**
- AC-4 (event) → goal: YES; event not registered in arch §Logging strategy. **HARDEN.**
- AC-5 (Phase 0 probes unaffected) → goal: YES; trivially true under any landing. KEEP.
- AC-6 (unit test) → goal: YES, but the prescribed test stub can't instantiate `Probe`. **HARDEN.**
- AC-7 (ADR-0002 amendment) → goal: WRONG target ADR. **REROUTE to ADR-0008 + budget.py docstring.**

## Critic findings

Findings are tagged `[block]` / `[harden]` / `[nit]` and labeled by lens: **CV** (coverage), **TQ** (test quality), **CN** (consistency), **DP** (design patterns).

### CN1 — `[block]` Adding to `Probe` ABC violates ADR-0007 (Phase 0)
The original Goal/AC-1 says `Probe` ABC gains `declared_raw_artifact_budget_mb: ClassVar[int] = 5`. ADR-0007 freezes the ABC contract surface; per-probe knobs are class attributes on the subclass with a coordinator-side default lookup (`coordinator/budget.py` docstring lines 13–19 explicitly state this; Phase 0 S3-05 hardening burned this lesson). **Resolution:** extend `ResourceBudget` with `raw_artifact_truncate_mb: int = 5` and consume it via the existing `declared_resource_budget` mechanism. The `Probe` ABC is not edited.

### CN2 — `[block]` Duplicate budget mechanism (Open/Closed violation, primitive obsession)
The original prescribed a parallel knob `Probe.declared_raw_artifact_budget_mb` (raw `int` ClassVar) alongside the existing `ResourceBudget.raw_artifact_mb`. Two `raw_artifact*_mb` knobs of different semantics is a Rule-7 "average code" anti-pattern. **Resolution:** the new field is `ResourceBudget.raw_artifact_truncate_mb: int = 5` — additive on the existing frozen dataclass, semantically distinct (soft truncation), naming makes the contrast loud. `raw_artifact_mb` keeps its current meaning (hard ceiling, raises). Adding a future resource dimension (e.g., RSS truncation) is one more field on the same dataclass — no kernel edit.

### CN3 — `[block]` ADR amendment target wrong
The original said "amend ADR-0002 (`ParsedManifestMemo`) §Consequences." ADR-0002 is about the `ProbeContext` extension for `parsed_manifest` + `input_snapshot`; the raw-artifact budget is a `coordinator/budget.py` concern. The natural homes are: (a) **ADR-0008 §"Soft truncation companion"** — adds an amendment paragraph stating that raw-artifact size is the on-disk twin of the in-process parse caps, with the truncate-with-marker policy at the writer-marshalling boundary; (b) the `budget.py` module docstring — documents the new field alongside the existing trio. **Resolution:** retarget the amendment.

### CN4 — `[harden]` Writer chokepoint preservation (ADR-0011)
The original prescribed `_write_raw_artifact_with_budget(probe, payload_bytes, out_path)` writing via `out_path.write_bytes(...)` — this **bypasses** the Writer's atomic .tmp + fsync + os.replace + 0o600 + symlink refusal + name-validation chokepoint. **Resolution:** the truncation policy is a **pure helper** applied *before* `Writer.write` receives the bytes; the Writer continues to be the sole I/O chokepoint, and its contract `raw_artifacts: list[tuple[str, bytes]]` is unchanged. The CLI's raw-artifact collection loop (`src/codegenie/cli.py:432–437`) is the natural integration site — it already has both the bytes and the per-probe object.

### TQ1 — `[block]` Stub `_StubProbe` cannot instantiate
The test plan defines `class _StubProbe(Probe): name = "stub"; declared_inputs = []` and later calls `_StubProbe()`. `Probe` is an ABC with `@abstractmethod async def run(...)` plus required class attributes `layer`, `tier`, `applies_to_tasks`, `applies_to_languages`, `requires`. The test will fail at instantiation with `TypeError: Can't instantiate abstract class _StubProbe with abstract method run` — the executor cannot get past the import-and-collect phase. **Resolution:** use the existing `FakeProbe` test helper from `tests/unit/_coordinator_fixtures.py` (the same one S3-05 / S1-07 / S1-08 unit tests reuse), or build a minimal concrete probe inline.

### TQ2 — `[block]` Event capture via `capsys` is fragile and contradicts Phase 1 precedent
The original asserts `"probe.raw_artifact.truncated" in capsys.readouterr().err`. structlog under the project's logging config does NOT necessarily route to `sys.stderr` synchronously (depends on `WriteLoggerFactory` configuration and renderer flushes; `caplog` was found unreliable in S3-04; the same trap was burned in S1-07 / S1-08 hardenings). The hardened precedent is `structlog.testing.capture_logs()` which is in-process, deterministic, and exposes structured fields (`probe`, `original_bytes`, `budget_bytes`, `path`) for direct equality assertions. **Resolution:** rewrite event-assertion tests with `with capture_logs() as logs: ...; assert any(e["event"] == "probe.raw_artifact.truncated" and e["probe"] == "stub" and e["original_bytes"] == ... for e in logs)`.

### TQ3 — `[harden]` Tautological test `test_class_attribute_default_is_5`
`assert Probe.declared_raw_artifact_budget_mb == 5` is Rule-9 worthless — it just restates the source code; a mutant that changes the default to `4` would flip the test, but a mutant that disables the truncation **entirely** (default remains 5, no enforcement) leaves the test green. The default's *behavioral* meaning is "truncation fires at 5 MB on a probe that didn't opt out"; the test that pins this is a 5.1 MB payload test asserting a marker write, not an attribute read. **Resolution:** drop the attribute-read test; add a "default applies to no-override probe" behavioral test that proves a 6 MB payload from a no-override probe produces a truncated marker.

### CV1 — `[harden]` Missing edge cases (eight)
The original TDD plan has 4 tests. The truncation policy has at least **eight** distinct edge cases that need to be pinned:

1. **Empty payload (0 bytes).** Must not truncate; write empty file.
2. **Exact-boundary payload (`len == budget_bytes`).** Inclusive at the limit (matches `report_bytes` precedent — see `tests/unit/test_coordinator_budget.py:30–34`); no truncation.
3. **One-byte-over payload (`len == budget_bytes + 1`).** First byte that triggers truncation; pins the `>` vs `>=` ambiguity (same mutant family `report_bytes` kills).
4. **Truncation prefix is parseable JSON.** Marker `data` field holds the parsed dict/list.
5. **Truncation prefix is NOT parseable JSON (cut mid-token).** Marker `data` field holds a UTF-8 string with replacement chars.
6. **Multi-byte UTF-8 character straddling the boundary.** `decode(errors="replace")` produces `�`; pins the "don't crash on truncated UTF-8" property.
7. **No-override Phase-0 probe writes a tiny artifact (`< 1 MB`).** No truncation; no event emitted. Pins "Phase 0 probes unaffected."
8. **Override probe (`raw_artifact_truncate_mb=25`) writes 6 MB.** No truncation; no event emitted. Pins the override mechanism.

### CV2 — `[harden]` Marker invariants need at least one structural test
The marker shape `{"__truncated_at_budget__": True, "original_bytes": <n>, "budget_bytes": <m>, "data": ...}` has invariants the original TDD plan doesn't pin individually:
- `__truncated_at_budget__` is exactly `True` (boolean, not `1`, not the string `"True"`). Pins the no-coerce mutant.
- `original_bytes >= budget_bytes` always (a truncation event by definition exceeded the budget). Property test or per-case assertion.
- The four marker keys are present and ONLY those four. Pins the "extra metadata leak" mutant.
- `original_bytes` equals the actual `len(payload_bytes)` from the input (not some other quantity like file size of a different file). Pins the "wrong byte count" mutant.

### CV3 — `[harden]` Truncation–hard-ceiling interaction not pinned
The hardened design has two thresholds on the same `ResourceBudget`: `raw_artifact_truncate_mb=5` (soft, truncates) and `raw_artifact_mb=10` (hard, raises via `report_bytes`). The invariant `truncate_mb <= raw_artifact_mb` must hold or the truncation policy is unreachable (the hard ceiling fires first). **Resolution:** add an AC validating the invariant in `ResourceBudget.__post_init__` (frozen dataclass + `__post_init__` is fine), and a unit test that constructs `ResourceBudget(raw_artifact_truncate_mb=20, raw_artifact_mb=10)` and expects a `ValueError`. Fail-loud per Rule 12.

### CV4 — `[harden]` Event `probe.raw_artifact.truncated` not registered in arch §Logging strategy
`phase-arch-design.md §"Harness engineering" → "Logging strategy"` (line 810) enumerates the Phase 1 event vocabulary: `probe.parser.cap_exceeded`, `probe.memo.hit`/`miss`, `probe.catalog.load`. The new `probe.raw_artifact.truncated` event appears only in Gap 2 prose. S1-10 (event-name `Final[str]` constants registry) is the natural follow-up landing; this story should declare the literal **and** flag the arch-doc registration as a `Validation notes` follow-up so S1-10 picks it up.

### DP1 — `[harden]` Functional core / imperative shell split
The original `_write_raw_artifact_with_budget` does five things in one function: (a) budget check, (b) JSON parse of prefix, (c) JSON dump of wrapper, (d) file write, (e) structlog emit. Per the "functional core, imperative shell" pattern, split into:
- **Pure:** `apply_raw_artifact_truncation(payload: bytes, truncate_mb: int) -> tuple[bytes, TruncationOutcome]` in `src/codegenie/output/raw_truncation.py` — bytes in, bytes out + outcome metadata. No I/O, no logging.
- **Shell:** the CLI's raw-artifact collection loop (`src/codegenie/cli.py:432–437`) calls the pure helper, emits the structlog event when the outcome is `Truncated`, and passes the (possibly modified) bytes to `Writer.write`.

This separates the policy logic (pure, easy to test, no fixtures) from the I/O concerns (writer chokepoint) and the observability concerns (structlog).

### DP2 — `[harden]` Tagged union for `TruncationOutcome`
The pure helper's return type benefits from a sum type:

```python
@dataclass(frozen=True)
class Untruncated: ...

@dataclass(frozen=True)
class Truncated:
    original_bytes: int
    budget_bytes: int

TruncationOutcome = Untruncated | Truncated
```

Makes illegal states unrepresentable (you cannot have a `Truncated` outcome with `original_bytes < budget_bytes`; you cannot read `original_bytes` off an `Untruncated`). The CLI dispatch is a one-line `isinstance(outcome, Truncated)` instead of a nullable-int check. This is the same pattern S1-07 / S1-08 established (sum types for memo/snapshot outcomes).

### DP3 — `[harden]` Field naming reflects the contrast with the hard ceiling
The original name `declared_raw_artifact_budget_mb` collides semantically with `ResourceBudget.raw_artifact_mb` (both look like *the* raw-artifact budget). The hardened name `raw_artifact_truncate_mb` (or `raw_artifact_soft_mb` — same idea) makes the soft/hard distinction loud at every call site. Match the precedent set by `wall_clock_s` (qualifier-suffixed unit) and `rss_mb` (knob-name-then-unit).

### DP4 — `[nit]` Sentinel test for `ResourceBudget` field set
S1-06 / S1-08 established the convention: when a contract dataclass gains a field, a sentinel test pins the new field tuple so a third future field demands an ADR. Extend `tests/unit/test_coordinator_budget.py:43-48` (`test_resource_budget_defaults`) with the new field. Add a `test_resource_budget_field_set_pinned` sentinel naming this story.

### DP5 — `[nit]` Kernel/policy split — the allowlist of overrideable budget knobs
Phase 2's `IndexHealthProbe` might need a higher `wall_clock_s`; Phase 3's recipe probe might need a higher `rss_mb`. The `ResourceBudget` is already the kernel/policy seam — adding `raw_artifact_truncate_mb` is one more knob in the established Open/Closed surface. No kernel edit ever needed for a new knob.

## Stage 4 — synthesis & priority

Conflict resolution per priority `Consistency > Coverage > Test-Quality > Design-Patterns`:

- CN1 vs the architecture docs (arch §Gap 2 + High-level-impl Step 1 prescribe the ABC edit) — **Consistency with code wins.** Code shipped, tests pinned, ADR-0007 explicit. The arch docs are stale; this is flagged in `Validation notes` for follow-up.
- CN2 / CN3 / CN4 ↔ Original ACs — Consistency rewrites.
- CV1 / CV2 / CV3 / CV4 — Coverage gaps; all addable as new ACs without changing the goal.
- TQ1 / TQ2 / TQ3 — Test-quality fixes; mechanical replacements.
- DP1 / DP2 / DP3 / DP4 / DP5 — Design-pattern hardenings; converted into ACs where observable (e.g., `apply_raw_artifact_truncation` is the symbol the tests import; that's observable) and `Notes for implementer` paragraphs otherwise.

## Edits applied to the story

The story file was rewritten in place — Goal preserved (intent), ACs expanded from **9** to **23** individually verifiable items, TDD plan rewritten with concrete runnable Python, edge cases added, ADR amendment retargeted from ADR-0002 to ADR-0008 + budget.py docstring, the architectural conflict surfaced as a `Validation notes` block at the top of the story, and a `Notes for the implementer` section expanded with the kernel/policy framing.

**Files modified:**
- `docs/phases/01-context-gather-layer-a-node/stories/S1-09-raw-artifact-budget.md` (full rewrite preserving Goal-intent)
- `docs/phases/01-context-gather-layer-a-node/stories/_validation/S1-09-raw-artifact-budget.md` (this file, new)

## Verdict

**HARDENED.** The story is ready for `phase-story-executor`. The structural Phase-0-contract-freeze conflict (the original story's most load-bearing defect) is resolved by routing Gap 2 through the established `ResourceBudget` extension point. The kernel/policy seam is preserved for future budget dimensions. All plausible wrong implementations (twelve mutants tracked: budget=0, budget=infinity, off-by-one boundary, missing marker key, wrong marker key name, truncation-bypassed-writer, raw-bytes-coerced-to-string, JSON-parse-on-fallback-string, missing-event, event-name-typo, event-wrong-fields, no-truncate-on-no-override-probe) are caught by named tests with explicit AC anchors.

Three architectural follow-ups surfaced (out-of-scope per Rule 3, recorded in `Validation notes` on the story for separate action):

1. **Arch-doc staleness.** `phase-arch-design.md §"Gap analysis" Gap 2` and `High-level-impl.md §Step 1` still prescribe the `Probe` ABC edit. They should be updated to reflect the `ResourceBudget` extension landing.
2. **Event-name registry.** `probe.raw_artifact.truncated` is not in `phase-arch-design.md §"Logging strategy"` (line 810). S1-10 should pick it up alongside the other `Final[str]` constants.
3. **Writer-contract widening (forward-looking).** If a future probe needs different truncation policies per artifact (not per probe), the per-probe `ResourceBudget` is too coarse. Phase 2+ may want to widen `Writer.write`'s `raw_artifacts` shape to carry per-artifact policy. Not this story.
