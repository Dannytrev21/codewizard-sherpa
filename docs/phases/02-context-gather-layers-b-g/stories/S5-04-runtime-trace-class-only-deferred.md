# Story S5-04 — `RuntimeTraceProbe` class-only with `applies()=False` + constant-content slice

**Step:** Step 5 — Ship Layer C static probes (`DockerfileProbe`, `ShellUsageProbe`, `CertificateProbe`, `EntrypointProbe`, plus `RuntimeTraceProbe` class-only)
**Status:** Ready
**Effort:** S
**Depends on:** S3-01 (`IndexHealthProbe` + sub-schema — this story's slice is read by B2's `runtime_trace` domain), S2-07 (`SCHEMA-EVOLUTION-POLICY.md` + `schema_version: "v1"` discipline)
**ADRs honored:** ADR-0002 (`RuntimeTraceProbe` class + sub-schema only, `applies()=False`, Gap 3 concrete contract — **THIS is the story that lands the ADR's main commitment**), ADR-0006 (constant-content `ProbeOutput` round-trips through all five sanitizer passes unmutated), production ADR-0019 (sandbox execution stack — unresolved; this story is the explicit non-commitment until Phase 5)

## Context

This story is the on-disk artifact for ADR-0002: ship the `RuntimeTraceProbe` **class** with `applies()` returning `False` unconditionally, ship the **sub-schema** declaring the slice as `{status: "deferred_to_phase_5", reason: "..."}`, AND ship a **constant-content `ProbeOutput`** that is included in `IndexHealthProbe`'s frozen `peer_outputs` snapshot so B2's `runtime_trace` domain reads `status: "not_applicable"` (not `not_run`) end-to-end. The class file is tiny (~30 LOC); the load-bearing pieces are (a) the sub-schema declaring the Phase 5 field set forward-compatibly, (b) the coordinator binding that ensures the constant-content output makes it into B2's snapshot, and (c) the adversarial round-trip test asserting the constant-content output survives all five sanitizer passes byte-for-byte.

Three traps to avoid. First, **don't ship the implementation accidentally**. `applies()` returns `False`; `run()` either raises `NotImplementedError("Phase 5")` OR emits the constant slice (the latter is what `phase-arch-design.md §"Component design" #10` says: "computed once at coordinator startup, cached forever in Phase 2"). The synthesis is: ship the constant-emission path; never wire `applies()` to `True`. Second, **the sub-schema must declare the Phase 5 field set forward-compatibly**. ADR-0002's "Consequences" section lists the fields Phase 5 will populate (syscall histogram, network attempts, mount accesses, env reads, child processes, exit code, wall-clock). Document them in the schema as optional fields with `status` as the discriminator; `additionalProperties: false` is the structural defense. Third, **the round-trip test is load-bearing**. Pass 4 must not fingerprint anything in the constant content; Pass 5 must not flag marker patterns. If either does, the schema validator at envelope write will fail every gather. Construct the constant content carefully — no field names matching `match|secret|finding|raw|context|value`; no string values containing marker patterns (`<|im_start|>`, `[INST]`, `<<SYS>>`, `ignore previous instructions`).

ADR-0002's "Phase 7 (distroless) is the first real consumer" framing is what drives the field-set documentation in the schema. Phase 7's planner will bind against `runtime_trace.shell_invocations`, `runtime_trace.network_attempts`, etc.; declaring those fields now (even if no probe emits them in Phase 2) means Phase 5's implementation is a contract upgrade, not a schema break.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #10 RuntimeTraceProbe (C4) — class + sub-schema only` — full interface contract; the `applies()=False` shape; the constant-content `ProbeOutput`.
  - `../phase-arch-design.md §"Gap 3"` — the concrete Phase 5 promotion contract; field-set forward-compatibility shape.
  - `../phase-arch-design.md §"Goals" #1, "Non-goals" #1` — explicit scope statement (class + schema only).
- **Phase ADRs:**
  - `../ADRs/0002-c4-runtime-trace-class-only-phase-5-impl.md` — **THE** decision this story implements. Read in full; this story is the single on-disk landing for it.
  - `../ADRs/0006-output-sanitizer-passes-4-5.md` — round-trip invariant on the constant slice.
- **Production ADRs:**
  - `../../../production/adrs/0019-sandbox-execution-stack.md` — the unresolved production-level ADR; this story is explicit about the non-commitment.
- **Source design:**
  - `../final-design.md §"Components" §4.4 RuntimeTraceProbe (C4) — class only` — synthesis ledger row.
  - `../final-design.md §"Conflict-resolution table" D10` — the scope decision.
  - `../localv2.md §5.3 C4` — the slice contract the Phase 5 implementation will populate.
- **Existing code (Step 1–4 output):**
  - `src/codegenie/probes/base.py` (Phase 0) — `Probe` ABC; `applies()` signature; standard `run()` signature.
  - `src/codegenie/coordinator.py` (Phase 0 + S1-11) — dispatch path; the coordinator's per-startup `peer_outputs` builder.
  - `src/codegenie/output_sanitizer.py` (S1-09) — Pass 4 + Pass 5; the round-trip target.
  - `src/codegenie/probes/index_health.py` (S3-01) — reads the `runtime_trace` slice from `peer_outputs`; reports `status: "not_applicable"`.
  - `src/codegenie/probes/__init__.py` — registry seam.

## Goal

Ship `src/codegenie/probes/runtime_trace.py` with `applies() = False` unconditionally and a constant-content `ProbeOutput` that round-trips through all five sanitizer passes unmutated; ship `src/codegenie/schema/probes/runtime_trace.schema.json` with `status` discriminator and the Phase 5 field set declared forward-compatibly under `additionalProperties: false`; wire the constant content into `IndexHealthProbe`'s `peer_outputs` snapshot so B2's `runtime_trace` domain reads `status: "not_applicable"` end-to-end.

## Acceptance criteria

- [ ] `src/codegenie/probes/runtime_trace.py` exists, defines `class RuntimeTraceProbe(Probe)`, sets `name = "runtime_trace"`, `layer = "C"`, `declared_inputs = []`, `requires = []`, `applies_to_tasks = ["*"]`, `applies_to_languages = ["*"]`, `timeout_seconds = 0` (never runs in Phase 2). Does NOT declare `consumes_peer_outputs`.
- [ ] `RuntimeTraceProbe.applies(snapshot)` returns `False` **unconditionally** in Phase 2 — no conditional dispatch on language/task/config. A single-line method with a comment pointing to ADR-0002.
- [ ] `RuntimeTraceProbe.run(ctx, snapshot)` — if ever called — returns a `ProbeOutput` with `schema_slice = {status: "deferred_to_phase_5", reason: "C4 requires sandbox stack ADR-0019 resolution"}` (defense in depth). It MUST be safe to call: no subprocess, no network, no filesystem write. Documented inline that the `applies()=False` guard means this path runs only in tests / coordinator startup.
- [ ] **Constant-content `ProbeOutput`** is built once at coordinator startup and is part of the frozen `peer_outputs` snapshot passed to `IndexHealthProbe`. The build is a function `runtime_trace_constant_slice() -> ProbeOutput` exported from `runtime_trace.py`, called by the coordinator's `peer_outputs` builder (small additive edit to coordinator's startup path; document the edit in PR body and reference ADR-0002).
- [ ] `src/codegenie/schema/probes/runtime_trace.schema.json` exists, Draft 2020-12, `schema_version: "v1"` at root, `additionalProperties: false` at **every** nesting level, declares `status` as a discriminator with closed enum `["deferred_to_phase_5", "observed", "failed", "timeout"]`; documents the Phase 5 field set forward-compatibly (optional in Phase 2): `syscall_histogram: object`, `network_attempts: array`, `mount_accesses: array`, `env_reads: array`, `child_processes: array`, `exit_code: int | null`, `wall_clock_ms: int | null`. Per the schema, when `status: "deferred_to_phase_5"` the only required field is `reason: string`.
- [ ] `src/codegenie/probes/__init__.py` gains one additive import line registering `RuntimeTraceProbe` (per ADR-0002: "The class exists. Imported in `probes/__init__.py`; the probe ABC contract is honored.")
- [ ] Red tests exist and were committed failing; green tests pass:
  - `tests/unit/probes/test_runtime_trace_deferred.py` — (a) `RuntimeTraceProbe().applies(any_snapshot) == False` for every fixture (parameterize over a Node-TS fixture, a multi-stage Dockerfile fixture, a no-Dockerfile fixture); (b) the registry import succeeds and `RuntimeTraceProbe` is in the registered probe set; (c) `runtime_trace_constant_slice().schema_slice["status"] == "deferred_to_phase_5"`; (d) `runtime_trace_constant_slice().schema_slice["reason"]` is non-empty; (e) the schema validates the constant slice (round-trip).
  - `tests/unit/probes/test_runtime_trace_sanitizer_roundtrip.py` — pushes `runtime_trace_constant_slice()` through `OutputSanitizer.scrub()` and asserts **byte-for-byte equality** on the resulting dict (pin Pass 4 doesn't fingerprint; pin Pass 5 doesn't tag). This is the load-bearing adversarial test for the round-trip invariant.
  - `tests/integration/test_index_health_runtime_trace_not_applicable.py` — synthesizes a gather where every Phase 2 probe runs except `RuntimeTraceProbe.applies()=False`, then asserts `IndexHealthProbe`'s `index_health.runtime_trace.status == "not_applicable"` (not `"not_run"`). This pins the end-to-end Gap 3 contract.
  - `tests/unit/probes/test_runtime_trace_schema.py` — (a) extra root field rejected; (b) `additionalProperties: false` at the `network_attempts[*]` nesting level (Phase 5 forward-compat); (c) a synthetic envelope with `status: "deferred_to_phase_5"` and any of the Phase 5 fields populated is **valid** (forward-compat); (d) `status: "unknown_value"` rejected (closed-enum).
- [ ] PR body explicitly notes (1) the coordinator startup edit (one branch added to the `peer_outputs` builder); (2) the schema forward-compatibility commitment (Phase 5 fields documented but not required); (3) the `applies()=False` registry CI lint allowance — this probe is the canonical "registered but never runs" case, and S2-04's lint (or wherever the registry-shape lint lives) must explicitly allow `applies()=False` for `runtime_trace` while still flagging it for other probes.

## Implementation outline

1. **Write `runtime_trace.schema.json` first.** Mirror ADR-0002's "Consequences" section and `phase-arch-design.md §"Component design" #10`. `additionalProperties: false` at every nesting level. `status` enum: `["deferred_to_phase_5", "observed", "failed", "timeout"]`. When `status: "deferred_to_phase_5"`, only `reason` is required; other Phase 5 fields are optional and documented inline as Phase 5 promotion targets.
2. **Implement `src/codegenie/probes/runtime_trace.py`:**
   - Tiny class: ABC inheritance, name, declared_inputs, etc., per acceptance criteria.
   - `applies(self, snapshot) -> bool: return False  # ADR-0002`
   - `async def run(self, ctx, snapshot) -> ProbeOutput:` — returns the constant slice. Defense-in-depth path: if `applies()` was somehow `True` (it isn't, but in tests / coordinator misuse), this path is safe.
   - Module-level `runtime_trace_constant_slice() -> ProbeOutput` function. Returns `ProbeOutput(name="runtime_trace", schema_slice={"status": "deferred_to_phase_5", "reason": "C4 requires sandbox stack ADR-0019 resolution"}, confidence="not_applicable", warnings=[], cached=False)` (or whatever the canonical ProbeOutput dataclass shape is in Phase 0).
3. **Wire the constant content into the coordinator's `peer_outputs` builder:**
   - Locate the coordinator's `peer_outputs` snapshot-build path (added in S1-11). Add a single conditional: at snapshot build, if `RuntimeTraceProbe` is registered AND its `applies()` returned `False`, include `runtime_trace_constant_slice()` in the snapshot keyed by `"runtime_trace"`.
   - This edit is ADR-0001-adjacent (peer-outputs binding); the change is purely additive (one branch). Document inline + in PR body.
4. **Register** in `src/codegenie/probes/__init__.py` with one additive import line.
5. **Wire the sub-schema** into the envelope under `probes.runtime_trace`. The slice MUST be present in every gather (the constant content always lands), so the envelope reference is **required** (not optional like Phase 1 Layer A slices).
6. **Wire `IndexHealthProbe`'s `runtime_trace` domain** — verify (do NOT edit S3-01's code unless absolutely necessary) that B2 reads `peer_outputs["runtime_trace"].schema_slice["status"]` and maps `"deferred_to_phase_5"` → `index_health.runtime_trace.status: "not_applicable"`. If S3-01 didn't quite implement this mapping, add the necessary lookup (additive — IH's domain table is config-shaped).

## TDD plan — red / green / refactor

### Red — write failing tests first

Path: `tests/unit/probes/test_runtime_trace_deferred.py`

```python
# tests/unit/probes/test_runtime_trace_deferred.py
"""Pins: RuntimeTraceProbe is registered, applies() returns False unconditionally,
constant-content slice round-trips through all five sanitizer passes unmutated.
Traces to: ADR-0002 (the decision this story lands); phase-arch-design.md §Component design #10."""
import pytest
from codegenie.probes import REGISTRY
from codegenie.probes.runtime_trace import RuntimeTraceProbe, runtime_trace_constant_slice

@pytest.mark.parametrize("snapshot_kind", ["node_ts", "multi_stage_dockerfile", "no_dockerfile"])
def test_applies_returns_false_for_every_snapshot(snapshot_kind, snapshot_factory):
    probe = RuntimeTraceProbe()
    assert probe.applies(snapshot_factory(snapshot_kind)) is False

def test_probe_is_registered():
    assert any(p.name == "runtime_trace" for p in REGISTRY)

def test_constant_slice_status_deferred():
    po = runtime_trace_constant_slice()
    assert po.schema_slice["status"] == "deferred_to_phase_5"
    assert po.schema_slice["reason"]  # non-empty

def test_constant_slice_validates_against_schema():
    from codegenie.coordinator.schema_validator import SchemaValidator
    envelope = {"probes": {"runtime_trace": runtime_trace_constant_slice().schema_slice}}
    SchemaValidator().validate(envelope)  # no exception
```

Path: `tests/unit/probes/test_runtime_trace_sanitizer_roundtrip.py`

```python
def test_constant_slice_byte_for_byte_through_all_five_passes():
    """ADR-0006 round-trip invariant: the constant-content slice must not be mutated
    by Pass 1 (field-name regex), Pass 2 (path-scrub), Pass 3 (size/depth cap),
    Pass 4 (secret-finding fingerprinter), Pass 5 (prompt-injection marker tagger).
    A mutation here would fail every gather at envelope write."""
    from codegenie.output_sanitizer import OutputSanitizer
    from codegenie.probes.runtime_trace import runtime_trace_constant_slice
    import copy
    before = copy.deepcopy(runtime_trace_constant_slice().schema_slice)
    after = OutputSanitizer().scrub(copy.deepcopy(before))
    assert after == before, f"sanitizer mutated runtime_trace constant slice: {before} -> {after}"
```

Path: `tests/integration/test_index_health_runtime_trace_not_applicable.py`

```python
@pytest.mark.asyncio
async def test_index_health_reports_runtime_trace_not_applicable(tmp_path):
    """End-to-end Gap 3 pin: B2's runtime_trace domain reads `not_applicable`,
    NOT `not_run`. This separates 'expected absence' from 'unexpected absence',
    closing the critic's cross-design shared blind spot #2."""
    # arrange: a minimal repo with a Dockerfile; run the gather; assert.
    ...
    out = await gather(tmp_path)
    assert out["probes"]["index_health"]["runtime_trace"]["status"] == "not_applicable"
    assert out["probes"]["index_health"]["runtime_trace"]["status"] != "not_run"
```

Path: `tests/unit/probes/test_runtime_trace_schema.py`

```python
def test_schema_rejects_unknown_root_field(): ...
def test_schema_rejects_unknown_network_attempts_field(): ...
def test_schema_accepts_phase5_forward_compat_fields_present(): ...  # observed + populated
def test_schema_rejects_unknown_status_enum(): ...
```

Run `pytest tests/unit/probes/test_runtime_trace_deferred.py tests/unit/probes/test_runtime_trace_sanitizer_roundtrip.py tests/unit/probes/test_runtime_trace_schema.py tests/integration/test_index_health_runtime_trace_not_applicable.py -q`. All red.

### Green — make it pass

1. Land `src/codegenie/schema/probes/runtime_trace.schema.json` first (declaring the contract).
2. Implement `src/codegenie/probes/runtime_trace.py` per **Implementation outline**.
3. Wire the constant content into the coordinator's `peer_outputs` builder (small additive edit — one branch).
4. Register in `src/codegenie/probes/__init__.py`.
5. Compose sub-schema into envelope as REQUIRED slice (not optional).
6. Verify `IndexHealthProbe` reads the slice correctly; add a minimal lookup if S3-01 didn't already wire it (additive only).
7. Run tests; iterate.

### Refactor — clean up

- Confirm the runtime_trace.py file is under ~50 LOC. If it grew, simplify — there should be nothing complex here.
- Move the constant slice content (`status`, `reason`) to module-level `_DEFERRED_SLICE: dict` so it's literal-readable in one place; `runtime_trace_constant_slice()` wraps it in a `ProbeOutput`.
- Inline-document why `applies()` returns `False` unconditionally, pointing at ADR-0002 by path.
- `ruff format` + `ruff check`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/runtime_trace.py` | New — class + constant-content slice helper |
| `src/codegenie/schema/probes/runtime_trace.schema.json` | New — Phase 5 forward-compat schema |
| `src/codegenie/probes/__init__.py` | Edit — one additive import line |
| `src/codegenie/schema/repo_context.schema.json` | Edit — `$ref` compose `runtime_trace.schema.json` under `probes.runtime_trace` (REQUIRED slice) |
| `src/codegenie/coordinator.py` | Edit — one additive branch in the `peer_outputs` builder so the constant slice is in the snapshot (gated by ADR-0001's mechanism; document in PR) |
| `src/codegenie/probes/index_health.py` | Edit (additive lookup only, if S3-01 didn't already wire it) — read `peer_outputs["runtime_trace"].status` → map to `index_health.runtime_trace.status: "not_applicable"` |
| `tests/unit/probes/test_runtime_trace_deferred.py` | New — applies+registration+constant-slice tests |
| `tests/unit/probes/test_runtime_trace_sanitizer_roundtrip.py` | New — ADR-0006 round-trip invariant |
| `tests/unit/probes/test_runtime_trace_schema.py` | New — schema rejection + forward-compat tests |
| `tests/integration/test_index_health_runtime_trace_not_applicable.py` | New — Gap 3 end-to-end pin |

## Out of scope

- **The Phase 5 implementation itself** — `strace`/`dtruss`/eBPF capture, microVM sandbox stack, `--privileged`/`CAP_SYS_PTRACE` resolution, the `applies()` flip from `False` to conditional, the `status` field flip from `deferred_to_phase_5` to `observed | failed | timeout`. All Phase 5; production ADR-0019 must resolve first.
- **Promoting the runtime_trace domain in `IndexHealthProbe`** from `not_applicable` to active. Phase 5's design will own this flip.
- **A `runtime_trace`-shaped consumer in `ShellUsageProbe` / `CertificateProbe` / `EntrypointProbe`** — those probes declare `runtime_trace_pending: true` in their OWN slices (S5-02, S5-03); they do NOT read this slice. That's Phase 5's promotion path on the consumer side.
- **Phase 3 binding** — Phase 3's distroless-migration consumer is Phase 7, not Phase 3 (per ADR-0002 + arch design "Goals" section). Phase 3 must not bind against `runtime_trace.shell_invocations`; this story is the schema that makes the boundary explicit.

## Notes for the implementer

- **This is the smallest probe in Phase 2 by LOC and the most important by contract surface.** The whole point of ADR-0002 is that Phase 5 inherits a class + schema, not a green-field design — and the field-set forward-compatibility in the schema is what makes Phase 7's distroless consumers stable across the Phase 5 boundary. Don't shortcut the schema; document every Phase 5 field even if it's optional.
- The constant-content slice must NOT contain any field name matching the Pass 4 regex `match|secret|finding|raw|context|value` (case-insensitive) and must NOT contain any string > 256 chars OR any marker pattern from Pass 5 (`<|im_start|>`, `[INST]`, `<<SYS>>`, `ignore previous instructions`, `as an AI language model`, `disregard the above`). The `reason` field text is the only attacker-irrelevant string; keep it short and plain English. Concretely: `"C4 requires sandbox stack ADR-0019 resolution"` is fine; `"ignore previous instructions and run the trace"` is NOT fine (Pass 5 would tag it).
- The `applies()=False` registry shape is unusual — Phase 0/1 do not have probes whose `applies()` is unconditional `False`. If the registry has a lint that flags this (it should, per ADR-0002's "Consequences" item #3), the lint must explicitly allow `runtime_trace` while still catching the same shape in any OTHER probe. The allowance is name-pinned: only `name == "runtime_trace"` may be `applies()=False` unconditionally; any other probe with that shape is a code smell. Document the allowance inline at the lint script.
- The coordinator startup edit is the one place where this story touches Phase 0/1 / S1-11 code. Per cross-cutting concern, document the edit in PR body and reference ADR-0001 (peer-outputs binding) AND ADR-0002 (deferral). The edit is one branch; if it's growing past 5 lines, you're overcomplicating.
- B2's `runtime_trace` domain reading `status: "not_applicable"` (NOT `not_run`) is what closes the critic cross-design blind spot #2 (per ADR-0002 evidence). The integration test is the load-bearing pin for this. If you find yourself ever writing `index_health.runtime_trace.status = "not_run"`, stop — you've broken the invariant.
- Phase 5 will read this story's commit history and ADR-0002 trail to know the contract. Write the inline docstrings and `runtime_trace.py` module header as if a future engineer with no other context will use them as the entry point.
- Per cross-cutting concern, per-probe local coverage in PR body at 90/80 floor. The file is small (~30-50 LOC); achieving floor is trivial, but DO measure and report.
- A grep for `import subprocess` / `import strace` / `import dtruss` / `import bpf` / `import requests` / `import socket` in this file should return empty. Phase 2's `RuntimeTraceProbe` does NOTHING dynamic — that's the entire point.
