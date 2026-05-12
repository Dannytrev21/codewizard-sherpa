# Story S1-11 — `Probe.consumes_peer_outputs` ABC attr + Coordinator dispatch branch

**Step:** Step 1 — Plant sandbox extension, tool wrappers, tool-digest pin manifest, and the four Phase-0/1 in-place edits
**Status:** Ready
**Effort:** M
**Depends on:** S1-04, S1-09, S1-10
**ADRs honored:** ADR-0001

## Context

`IndexHealthProbe` (B2) is the load-bearing freshness oracle in Phase 2. It rolls up per-domain views (SCIP, SBOM, CVE, semgrep, gitleaks, runtime_trace) from the **actual outputs** of upstream probes — not from a side cache, not from disk. To do that it must, at run time, read the post-sanitizer outputs of every peer probe it depends on.

The best-practices lens proposed `ProbeContext.peer_outputs: Mapping`; the critic dismantled that as a Phase-0 contract mutation that affects 99% of probes that don't need it. ADR-0001 chose an opt-in mechanism keyed off the probe itself: a `consumes_peer_outputs: ClassVar[bool] = False` class attribute on `Probe`, and a single Coordinator branch that inspects the attribute and chooses two-arg or three-arg dispatch. `ProbeContext`'s public field set is unchanged.

This is the **only Phase-0 ABC contract amendment** in Phase 2. The snapshot test (`tests/unit/test_probe_contract.py`) regenerates with the documented attribute addition; subsequent ABC edits must fail CI. Per "Implementation-level risks" #3, the regen script encodes the allowed-attribute list so a third attribute can't slip in by accident.

This is the fourth of the four ADR-gated in-place edits Phase 2 makes to Phase 0/1 code (others: `exec.py` in S1-02, `ALLOWED_BINARIES` in S1-03, `output_sanitizer.py` in S1-09; ADR-0012 in S1-10 amends `audit_writer.py` additively without being an ABC contract edit).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"4+1 architectural views" "Logical view"` — class diagram with `consumes_peer_outputs: ClassVar[bool] = False` on `Probe`.
  - `../phase-arch-design.md §"Component design" #5 IndexHealthProbe` — the only consumer; `requires = ["scip_index", "syft_sbom", "grype_cve", "semgrep", "gitleaks", "runtime_trace"]`.
- **Phase ADRs:**
  - `../ADRs/0001-peer-outputs-binding.md` — ADR-0001 — full decision; snapshot is frozen (`MappingProxyType`); post-sanitizer; coordinator-private; `inspect.signature` check at registration; one branch in `Coordinator.dispatch`.
- **Production ADRs:**
  - `../../../production/adrs/0006-deterministic-gather-no-llm.md` — the deterministic-gather invariant peer-output binding defends.
- **Source design:**
  - `../final-design.md §"Departures from all three inputs"` #2 — synthesizer call-out.
  - `../final-design.md §"Conflict-resolution table" D6` — the resolution.
- **Existing code:**
  - `src/codegenie/probes/base.py` (Phase 0) — the frozen ABC; this story adds **exactly one** optional class attribute.
  - `src/codegenie/coordinator.py` (Phase 0) — the dispatch loop; this story adds **exactly one** branch.
  - `src/codegenie/output_sanitizer.py` (extended in S1-09) — Pass 5 must complete before the snapshot is built.
  - `src/codegenie/audit_writer.py` (extended in S1-10) — the snapshot-built event is audited.
  - `tests/unit/test_probe_contract.py` (Phase 0 snapshot test) — regenerated.

## Goal

Make two ADR-0001-gated edits — (a) extend `src/codegenie/probes/base.py` with `Probe.consumes_peer_outputs: ClassVar[bool] = False` as an optional class attribute, (b) extend `src/codegenie/coordinator.py` dispatch loop with one branch on `getattr(probe, "consumes_peer_outputs", False)` that builds a frozen `MappingProxyType` peer-output snapshot and passes it as the third positional argument; enforce three-arg `run(snapshot, ctx, peer_outputs)` signature on consumers via `inspect.signature` at registration; route `probes/base.py` to CODEOWNERS so further ABC edits require gating.

## Acceptance criteria

- [ ] `src/codegenie/probes/base.py` adds **exactly one** new attribute on `Probe`: `consumes_peer_outputs: ClassVar[bool] = False`. No other field is added, removed, or renamed.
- [ ] `src/codegenie/coordinator.py` adds **exactly one** new branch inside its existing dispatch method: when `getattr(probe, "consumes_peer_outputs", False)` is `True`, the coordinator builds a `MappingProxyType` over the post-sanitizer outputs collected so far and passes it as a third positional argument to `probe.run(snapshot, ctx, peer_outputs)`.
- [ ] `_build_frozen_peer_snapshot(completed: Mapping[str, ProbeOutput]) -> Mapping[str, ProbeOutput]` is a private helper in `src/codegenie/coordinator/` (next to Phase 1's `parsed_manifest_memo.py`) returning a `MappingProxyType[str, ProbeOutput]`. The snapshot is constructed once per gather, after the relevant Wave's sanitizer passes (1–5) have run on every peer output.
- [ ] At probe registration time, the coordinator calls `inspect.signature(probe.run)` and verifies the parameter count: probes declaring `consumes_peer_outputs = True` must have a three-positional-arg `run(snapshot, ctx, peer_outputs)` signature; probes declaring `False` (or not declaring) must have the existing two-arg signature. Mismatch raises `ProbeRegistrationError`; the CLI exits 2 at startup. (`ProbeRegistrationError` may exist from Phase 0/1; if not, append it to `errors.py` additively.)
- [ ] When the snapshot is built, the coordinator emits `probe.peer_outputs.snapshot_built` once per gather with `peer_count: int`, `built_at_wave: int` fields.
- [ ] The `MappingProxyType` peer-output snapshot is immutable at the Python type-system level: a consumer probe attempting `peer_outputs["x"] = something` raises `TypeError`.
- [ ] The contained `ProbeOutput` instances are Pydantic-frozen (per S1-04's `ToolResult` discipline and Phase 0's `ProbeOutput` config); mutation of a contained output also raises.
- [ ] `ProbeContext`'s public field set is **unchanged**.
- [ ] `tests/unit/test_probe_contract.py` regenerates with the new attribute documented. The regen script (`scripts/regen_probe_contract_snapshot.py` or wherever it lives in Phase 0) **encodes the allowed attribute list inside the script** so a third attribute can't slip in without an explicit script edit + ADR. A unit test on the regen script asserts the allowed-attribute list is `{"name", "version", "applies", "run", "requires", "applies_to_tasks", "applies_to_languages", "declared_inputs", "cache_strategy", "consumes_peer_outputs"}` (or whatever Phase 0/1's existing set is, plus exactly the one new entry).
- [ ] `tests/unit/coordinator/test_peer_output_binding.py` ships ≥ 5 tests — probe without the attribute receives two-arg call; probe with `consumes_peer_outputs=True` receives three-arg call with frozen snapshot; mutation attempt raises `TypeError`; signature mismatch at registration raises `ProbeRegistrationError`; snapshot construction logs `probe.peer_outputs.snapshot_built`.
- [ ] A `CODEOWNERS` entry is added for `src/codegenie/probes/base.py` (and ideally the contract snapshot test) routing further edits to a designated owner — Phase 0/Phase 1/Phase 2 maintainers per the repo's CODEOWNERS conventions.
- [ ] No other Phase 0/1 module is edited (`output_sanitizer.py`, `audit_writer.py`, `parsers/`, etc. unchanged by this story; their extensions live in earlier Step 1 stories).
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write the failing tests under `tests/unit/coordinator/test_peer_output_binding.py` (red).
2. Edit `src/codegenie/probes/base.py`:
   - Append exactly: `consumes_peer_outputs: ClassVar[bool] = False`.
   - Extend the class docstring with two sentences naming ADR-0001 and the opt-in semantics.
3. Edit `src/codegenie/coordinator.py`:
   - Add a private import for `MappingProxyType`.
   - Add the `_build_frozen_peer_snapshot` helper (or import from `coordinator/peer_snapshot.py` if Phase 1's layout supports that).
   - In the existing dispatch loop, before invoking `probe.run(...)`, branch on `getattr(probe, "consumes_peer_outputs", False)`; on `True`, build snapshot, pass three-arg; on `False`, retain existing two-arg call.
   - Emit `probe.peer_outputs.snapshot_built` once at snapshot construction.
4. Add registration-time signature check: when probes register (in whatever Phase 0/1 mechanism — likely the `@register_probe` decorator or the coordinator's startup `_load_probes()`), call `inspect.signature(probe_cls.run)` and assert parameter count matches the `consumes_peer_outputs` declaration. On mismatch, raise `ProbeRegistrationError`. CLI exits 2.
5. Edit the regen script `scripts/regen_probe_contract_snapshot.py` (or wherever Phase 0 placed it) to encode the allowed-attribute list explicitly; add a test that asserts the list shape.
6. Regenerate the snapshot test fixture file (committed alongside the test); the new attribute appears in the canonical attribute list.
7. Add the `CODEOWNERS` entry. The repo's existing CODEOWNERS file gets one new line; if no CODEOWNERS file exists, create `.github/CODEOWNERS` with this one entry.
8. Run pytest, ruff, mypy.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/coordinator/test_peer_output_binding.py`.

```python
from types import MappingProxyType
from typing import Any

import pytest

import codegenie.errors as e
from codegenie.coordinator import Coordinator
from codegenie.probes.base import Probe, ProbeOutput, ProbeContext


class TwoArgProbe(Probe):
    name = "two_arg"
    async def run(self, snapshot, ctx):  # type: ignore[override]
        return ProbeOutput(...)  # minimal stub


class ThreeArgProbe(Probe):
    name = "three_arg"
    consumes_peer_outputs = True
    async def run(self, snapshot, ctx, peer_outputs):  # type: ignore[override]
        # consumer probe asserts immutability at runtime
        with pytest.raises(TypeError):
            peer_outputs["new"] = "bad"
        return ProbeOutput(...)


class MisdeclaredProbe(Probe):
    name = "misdeclared"
    consumes_peer_outputs = True
    async def run(self, snapshot, ctx):  # two-arg but declares True
        return ProbeOutput(...)


def test_probe_without_attribute_gets_two_arg_call():
    coord = Coordinator(probes=[TwoArgProbe()])
    # Coordinator's dispatch must not pass a third arg
    # (Test by inspecting Coordinator._dispatch behavior or via call recorder)


def test_three_arg_probe_receives_frozen_snapshot():
    coord = Coordinator(probes=[ThreeArgProbe()])
    # Run gather; ensure ThreeArgProbe.run receives MappingProxyType


def test_signature_mismatch_at_registration_raises():
    with pytest.raises(e.ProbeRegistrationError):
        Coordinator(probes=[MisdeclaredProbe()])  # signature inspection fires


def test_peer_outputs_immutable_at_type_level():
    proxy: MappingProxyType = MappingProxyType({"a": "b"})
    with pytest.raises(TypeError):
        proxy["c"] = "d"  # type: ignore[index]


def test_snapshot_built_event_emitted(caplog):
    coord = Coordinator(probes=[ThreeArgProbe(), TwoArgProbe()])
    # run a gather; assert exactly one probe.peer_outputs.snapshot_built event
    # appears in structlog records carrying peer_count and built_at_wave
```

Test file `tests/unit/test_probe_contract.py` (extend):

```python
EXPECTED_PROBE_ATTRS = {
    # Phase 0/1 attrs (verbatim from existing snapshot)
    "name", "version", "applies", "run", "requires",
    "applies_to_tasks", "applies_to_languages", "declared_inputs", "cache_strategy",
    # Phase 2 — ADR-0001
    "consumes_peer_outputs",
}

def test_probe_attrs_snapshot():
    from codegenie.probes.base import Probe
    actual = {a for a in dir(Probe) if not a.startswith("_")}
    # equality, not subset — a third attribute fails the test
    assert actual == EXPECTED_PROBE_ATTRS
```

Run; confirm failures. Commit as red marker.

### Green — make it pass

Land the two edits per the implementation outline. Keep the diff in `probes/base.py` to one new line + a docstring extension. Keep the diff in `coordinator.py` to one new branch + the helper import.

### Refactor — clean up

- `_build_frozen_peer_snapshot` can be a small helper in `src/codegenie/coordinator/peer_snapshot.py` (separate file) for cohesion with `parsed_manifest_memo.py` (Phase 1 ADR-0002 pattern). Pick the location that matches Phase 1's existing structure.
- The regen script edit is small: add a `_EXPECTED_ATTRS: frozenset[str] = frozenset({...})` constant; the script writes the snapshot only if `dir(Probe) - {"_"-prefixed}` equals the constant. The script's own test (`tests/unit/scripts/test_regen_probe_contract.py`) asserts the constant matches `EXPECTED_PROBE_ATTRS` from the contract test.
- Module docstring on `coordinator.py` extended with one paragraph naming ADR-0001 and the snapshot-built event.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/base.py` | Append `consumes_peer_outputs` ClassVar |
| `src/codegenie/coordinator.py` | One dispatch branch + helper import |
| `src/codegenie/coordinator/peer_snapshot.py` | New — `_build_frozen_peer_snapshot` |
| `src/codegenie/errors.py` | If not already present, append `ProbeRegistrationError` |
| `scripts/regen_probe_contract_snapshot.py` | Encode allowed-attribute list inline |
| `tests/unit/test_probe_contract.py` | Update `EXPECTED_PROBE_ATTRS` |
| `tests/unit/coordinator/test_peer_output_binding.py` | New — ≥ 5 tests |
| `tests/unit/scripts/test_regen_probe_contract.py` | New — pin the allowed-attribute list |
| `.github/CODEOWNERS` | Route `probes/base.py` reviews |

## Out of scope

- **`IndexHealthProbe` consumer implementation** — handled by S3-01. This story exposes the seam; S3-01 is the first (and only Phase 2) consumer.
- **`ProbeContext.parsed_manifest` extension** — Phase 1's ADR-0002 already shipped this; Phase 2 does not edit `ProbeContext`.
- **Cache-key extension for `sub_schema_version`** — handled by S2-06. This story does not change cache-key derivation.
- **Phase 5 `RuntimeTraceProbe` declaring `consumes_peer_outputs = True`** — Phase 5 may declare it; the seam is ready. Out of Phase 2 scope.

## Notes for the implementer

- **The ADR-0001 contract is "opt-in via class attribute, not via ProbeContext field."** If you find yourself adding a `peer_outputs: Mapping` parameter to `ProbeContext.__init__`, stop — you're implementing the rejected option. Reread ADR-0001's "Decision" section.
- **`MappingProxyType` is necessary AND sufficient at the type-system level.** `MappingProxyType` raises `TypeError` on `__setitem__` / `__delitem__`. The contained `ProbeOutput` Pydantic models are frozen by Phase 0's config (and any new ones in Phase 2 use `extra="forbid", frozen=True`). Together, the snapshot is read-only.
- **`inspect.signature` at registration time, not per call.** Per ADR-0001's "Inspect.signature is called once at registration, not per call — no hot-path reflection." The check runs once when probes load; the dispatch path uses `getattr` (constant time).
- **The regen script's encoded allow-list is the early-surfacing canary** per "Implementation-level risks" #3 in `High-level-impl.md`. If a future contributor (or AI agent) tries to add a *second* Phase-2 attribute to `Probe` without an ADR, the regen script's constant check fires before CI even sees the snapshot diff. The encoded list is harder to silently drift than a regenerated golden file.
- The snapshot is built **after Wave 1–4 sanitizer passes have completed** — meaning the bytes the consumer sees are the bytes that hit `repo-context.yaml`. Wire the snapshot construction at the boundary between sanitizer completion and consumer dispatch. If a probe runs in the same wave as its consumer, the snapshot for that wave excludes the same-wave probes (they haven't completed yet). `IndexHealthProbe` is the last wave by design (its `requires` set ensures it).
- The `built_at_wave` field on the snapshot-built event is the wave number at construction; useful for debugging order-of-dispatch issues. Phase 0's coordinator should already have a wave concept; if not, the field can default to `-1` and a follow-up issue can refine the value.
- `ProbeRegistrationError` may already exist in Phase 0/1's `errors.py`; if not, this story adds it additively (one more class, one `__all__` entry). Do not block on the question — `grep -n "ProbeRegistrationError" src/codegenie/errors.py` answers it.
- This is one of the four ADR-gated in-place edits Phase 2 makes to Phase 0/1 code. The PR description must cite ADR-0001 explicitly, confirm `ProbeContext` is unchanged, confirm the snapshot test regenerated, and confirm the regen script's allowed-attribute list is correct. Per "Cross-cutting concerns" in `stories/README.md`, `CODEOWNERS` routing for `probes/base.py` is a load-bearing piece.
- Resist the temptation to "improve" any other part of `coordinator.py` while editing (Rule 3 — Surgical Changes). The diff should be `git diff coordinator.py` minimal: import + one branch + one helper call.
- The `getattr(probe, "consumes_peer_outputs", False)` access (with default `False`) means Phase 0/1 probes that never declare the attribute behave identically — no per-probe defensive code needed. This is the "99% of probes see the original two-arg signature" gain from ADR-0001's Tradeoffs table.
