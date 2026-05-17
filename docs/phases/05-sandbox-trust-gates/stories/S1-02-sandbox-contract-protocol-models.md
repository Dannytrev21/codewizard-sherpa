# Story S1-02 — `sandbox/contract.py` — `SandboxClient` Protocol + `SandboxSpec/Run/Health/CopyInEntry` models

**Step:** Step 1 — Scaffold packages, contracts, and CI fences
**Status:** Ready (Hardened 2026-05-16)
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0001, ADR-0006, ADR-0012

## Validation notes (2026-05-16)

Hardened via `phase-story-validator` (verdict: HARDENED). Source-of-truth contradictions resolved against [`../phase-arch-design.md §Data model`](../phase-arch-design.md), [ADR-0001](../ADRs/0001-two-chokepoint-sandbox-seam.md), [ADR-0006](../ADRs/0006-protocol-vs-abc-convention.md), [ADR-0012](../ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md), and codebase precedents ([`src/codegenie/adapters/protocols.py`](../../../../src/codegenie/adapters/protocols.py), [`src/codegenie/result.py`](../../../../src/codegenie/result.py)). Full report: [`_validation/S1-02-sandbox-contract-protocol-models.md`](_validation/S1-02-sandbox-contract-protocol-models.md).

Headline edits (every weakness the four critics flagged would have let a structurally-wrong implementation slip past the executor's validator):

1. **Canonical literal spellings pinned positively.** Draft only asserted negative cases (`backend="kvm"` rejected). Shipping `Literal["dind", "firecracker"]` round-tripped every existing test silently — but Phase 13's cost ledger keys on the exact spelling `"docker_in_docker"`. New AC asserts `typing.get_args(...)` byte-equal to the canonical tuples (Goals 5/6 commitment).
2. **Backend ↔ isolation cross-field correlation now enforced.** Arch §Goals 5/6 require `(docker_in_docker, shared_kernel)` and `(firecracker, microvm)` as the only valid pairs; the draft allowed mixed nonsense like `(docker_in_docker, microvm)`. Added a `@model_validator(mode='after')` on `SandboxRun` + paired ACs.
3. **`extra="forbid", frozen=True` asserted *directly* via `model_config` introspection** on all four models (not just by side-effect on `SandboxSpec`). The draft only proved `SandboxSpec` frozen; `Run`/`Health`/`CopyInEntry` could have silently shipped `extra="ignore"`.
4. **`@runtime_checkable` decorator + Protocol surface cardinality pinned.** Draft asserted `isinstance` behavior; new ACs assert the decorator's presence directly and `set(get_protocol_members(SandboxClient)) == {'execute', 'health'}` (catches the M-12 mutation: adding a third method).
5. **ADR-0006 "no shared default behavior" now enforced by AST walk.** Protocol method bodies must be exactly `Expr(Constant(Ellipsis))` — a future contributor cannot silently add a default `health()` implementation that breaks duck-typing semantics.
6. **Source-level annotation pinning** for `env: Mapping[str, str]` (ADR-0012), `dst: PurePosixPath` vs `src: Path` (CopyInEntry), `trace_path: Path | None`. Pydantic coerces at runtime, so the annotation source is the only authoritative check.
7. **Newtype seam introduced for `RunId` and `SandboxSpecHash`.** Both cross ≥ 5 module boundaries (S2-01 ledger, S3-01 builder, S5-02 runner, S7-03 cost emitter, S8-01 CLI). CLAUDE.md "Domain identifiers ... are typed (newtype) when they cross ≥ 2 module boundaries" + the Phase-2 precedent `TestId` in [`adapters/protocols.py:41`](../../../../src/codegenie/adapters/protocols.py:41) demand the newtype now, not later.
8. **Numeric range constraints** at the contract level: `Field(gt=0)` on resource budgets (`time_budget_seconds`, `memory_limit_mib`, `pids_limit`); `Field(ge=0)` on observed counters (`duration_ms`, `image_pull_bytes`, `microvm_seconds`). A `-1` budget is contractually impossible.
9. **Cross-field invariants on `SandboxRun`:** `ended_at >= started_at`; `not (timed_out and killed_by_oom)` (arch §Edge cases 3/4 treats them as exclusive); on `SandboxSpec`: `network=="none"` implies `egress_allowlist == []`.
10. **`Mapping` import source.** Draft prescribed `typing.Mapping` (deprecated since 3.9); codebase precedent is unanimous on `collections.abc.Mapping`. CLAUDE.md Rule 11. Changed in Implementation outline §1.
11. **`__all__` discipline + module purity invariant** mirrors Phase-2's [`adapters/protocols.py`](../../../../src/codegenie/adapters/protocols.py) precedent: `from __future__ import annotations`, explicit `__all__` (alphabetized), module docstring citing ADR-0001/0006/0012, and a purity test asserting the module imports only stdlib + pydantic + `codegenie.errors` (no logger, no sibling Phase-5 modules).
12. **Coverage floor wording corrected.** Draft said "≥ 95% branch" — arch §Goal 12 and `stories/README.md §Definition of done` specify **95% line / 90% branch**. Now reads "line ≥ 95% AND branch ≥ 90%".
13. **Hypothesis property test promoted from a passing mention in AC-6 to an actual code block** in the TDD plan with an explicit env-dict-reorder strategy.
14. **Forward-seam note** added: `SandboxRun.backend: Literal[…]` is a *closed mirror* of the open `@register_sandbox_backend` registry (S1-05). Phase 7 distroless will need an ADR-0001 amendment to widen the Literal — *not* a silent change to `str`.

No `RESCUE`-tier findings (no AC contradicted a Goal beyond what the edits above fix). No Stage-3 research needed — every gap was answerable from Phase 5 arch + ADRs + codebase precedent (`src/codegenie/adapters/protocols.py`, `src/codegenie/result.py`).

## Context

`SandboxClient` is one of the three load-bearing public abstractions in Phase 5 (the others are `Gate` and `RetryLedger`). It is the seam Phase 6 lifts unchanged into LangGraph node side-effects, and the contract every backend (DinD in Step 3, Firecracker in Step 6) must satisfy. This story ships the Protocol plus the four frozen Pydantic data models (`SandboxSpec`, `SandboxRun`, `SandboxHealth`, `CopyInEntry`) that flow across the seam. No backend logic exists yet — only the byte-stable contract.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — SandboxClient (Protocol)` — exact public interface; `@runtime_checkable`.
  - `../phase-arch-design.md §Component design — SandboxSpec / SandboxRun / ObjectiveSignals (Pydantic models)` — all `extra="forbid", frozen=True`; construction cost envelope.
  - `../phase-arch-design.md §Data model` — the pseudo-code blocks for `CopyInEntry`, `SandboxSpec`, `SandboxRun`, `SandboxHealth` are the source of truth for field names, types, literals.
  - `../phase-arch-design.md §Goals` items 5 and 6 — `gate_isolation_class` literal values (`"shared_kernel"` for DinD, `"microvm"` for Firecracker).
  - `../phase-arch-design.md §Integration with Phase 6` — `SandboxClient` lifted unchanged; do not weaken.
- **Phase ADRs (rules this story honors):**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — ADR-0001 — `SandboxClient` is the gate seam, distinct from `run_in_sandbox`.
  - `../ADRs/0006-protocol-vs-abc-convention.md` — ADR-0006 — `SandboxClient` is a `runtime_checkable` Protocol (duck-typed; backends share no default behavior).
  - `../ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md` — ADR-0012 — `SandboxSpec.env` carries the *post-filter* view; this story's job is to keep the type `Mapping[str, str]`.
- **Source design:**
  - `../final-design.md §Component-1 — SandboxClient` — duck-type rationale.
- **High-level impl:**
  - `../High-level-impl.md §Step 1 — Features delivered` — bullet 2.

## Goal

Ship `src/codegenie/sandbox/contract.py` exposing the `SandboxClient` Protocol plus the four frozen `extra="forbid"` Pydantic models (`CopyInEntry`, `SandboxSpec`, `SandboxRun`, `SandboxHealth`) with the field names and types from `phase-arch-design.md §Data model`.

## Acceptance criteria

### A. Import surface and `__all__`

- [ ] **AC-1 — Import:** `from codegenie.sandbox.contract import SandboxClient, SandboxSpec, SandboxRun, SandboxHealth, CopyInEntry, RunId, SandboxSpecHash` succeeds with no side effects (idempotent on second import: `id(mod_first) == id(mod_second)`).
- [ ] **AC-1a — `__all__` is the exact public surface:** `set(codegenie.sandbox.contract.__all__) == {"CopyInEntry", "RunId", "SandboxClient", "SandboxHealth", "SandboxRun", "SandboxSpec", "SandboxSpecHash"}`. Asserted as a frozen contract (re-orderings, typos, and accidental widenings fail at unit-test time).

### B. `SandboxClient` Protocol shape (ADR-0006)

- [ ] **AC-2 — `@runtime_checkable` decorator present directly:** `getattr(SandboxClient, "_is_runtime_protocol", False) is True` (asserted directly, not via `isinstance` side-effect — a `Protocol` *without* the decorator but with `__subclasshook__` would pass the legacy isinstance test).
- [ ] **AC-2a — Protocol member set is exactly `{execute, health}`:** `set(typing.get_protocol_members(SandboxClient)) == {"execute", "health"}` (set equality, not subset — catches the M-12 mutation where a 3rd method is silently added).
- [ ] **AC-2b — Protocol methods have only `...` bodies (ADR-0006 "no shared default behavior"):** AST walk of `contract.py` asserts for each `FunctionDef` directly under `class SandboxClient`, the body is exactly one statement of shape `ast.Expr(value=ast.Constant(value=Ellipsis))`. A `def health(self): return SandboxHealth(...)` body fails this AC.
- [ ] **AC-2c — Protocol has no `__init__`, no class attributes:** `set(vars(SandboxClient)) - {dunder Protocol/runtime_checkable machinery}` contains only `execute` and `health` as callable members. Concretely: no entry of `vars(SandboxClient)` outside the allowed set `{'_is_runtime_protocol', '_is_protocol', '__init__', '__init_subclass__', '__subclasshook__', '__class_getitem__', '__protocol_attrs__', '__non_callable_proto_members__', '__abstractmethods__', '__dict__', '__doc__', '__module__', '__parameters__', '__weakref__', '__orig_bases__', 'execute', 'health'}` (the dunder allowlist follows Python's Protocol scaffolding; any name not in it fails the AC).
- [ ] **AC-2d — Protocol satisfaction is duck-typed:** an anonymous stub class `class _Good: def execute(self,spec): ...; def health(self): ...` returns `isinstance(_Good(), SandboxClient) is True`; a class missing `health` returns `False`; a class with an additional method returns `True` (Protocol checks presence, not absence — confirms structural typing).

### C. Pydantic `model_config` discipline (all four models)

- [ ] **AC-3 — `extra="forbid", frozen=True` asserted directly via `model_config` introspection on every model:** for `Cls in (CopyInEntry, SandboxSpec, SandboxRun, SandboxHealth)`, `Cls.model_config['extra'] == 'forbid'` AND `Cls.model_config['frozen'] is True`. Parametrized test.
- [ ] **AC-3a — Unknown-field rejection on every model:** for each of the four models, constructing with a valid kwarg set plus `_bogus="x"` raises `pydantic.ValidationError`.
- [ ] **AC-3b — Mutation rejection on every model:** for each of the four models, constructing a valid instance and attempting `setattr(instance, <some-field>, <new-value>)` raises `pydantic.ValidationError`.

### D. Literal value sets, byte-exact (Goals 5/6, Phase 13 cost-ledger keys)

- [ ] **AC-4 — Canonical literal spellings positively pinned:** assert via `typing.get_args(...)` on the `model_fields[...].annotation` of each field, OR via direct `typing.get_type_hints` introspection, that the literal *tuples* equal byte-exact:
  - `SandboxSpec.network` → `("none", "scoped")`
  - `SandboxRun.backend` → `("docker_in_docker", "firecracker")` (NOT `"dind"`, NOT `"docker"`)
  - `SandboxRun.gate_isolation_class` → `("shared_kernel", "microvm")` (NOT `"linux_namespace"`, NOT `"namespace"`)
  - `SandboxHealth.confidence` → `("high", "medium", "low")`
  - `CopyInEntry.mode` → `("ro", "rw")`
- [ ] **AC-4a — Each canonical literal *constructs successfully* (positive path):** parametrized test constructs one instance per accepted Literal value (`SandboxRun(backend="docker_in_docker", …)`, `SandboxRun(backend="firecracker", …)`, …) — closes the M-6/M-7 gap where a draft that ships `Literal["dind", "firecracker"]` rejects the legacy negative-case `"kvm"` but silently breaks the positive contract.
- [ ] **AC-4b — Out-of-set values rejected (negative path):** parametrized test asserts `ValidationError` on at least one out-of-set value per Literal field (e.g., `network="anywhere"`, `backend="kvm"`, `gate_isolation_class="linux_namespace"`, `confidence="absolute"`, `mode="rwx"`).
- [ ] **AC-4c — `CopyInEntry.mode` default is `"ro"`:** `CopyInEntry(src=Path("/x"), dst=PurePosixPath("/y")).mode == "ro"`.

### E. Source-level type-annotation pinning (ADR-0012 + arch §Data model)

- [ ] **AC-5 — `SandboxSpec.env` is `Mapping[str, str]`, not `dict[str, str]`:** `typing.get_type_hints(SandboxSpec)['env']` is `collections.abc.Mapping[str, str]`. ADR-0012's "post-filter view" depends on this read-only intent — a `dict[str, str]` annotation silently weakens the contract.
- [ ] **AC-5a — `CopyInEntry.src` is `pathlib.Path` (host path); `CopyInEntry.dst` is `pathlib.PurePosixPath` (sandbox path, POSIX even on macOS):** `typing.get_type_hints(CopyInEntry)['src'] is pathlib.Path` and `typing.get_type_hints(CopyInEntry)['dst'] is pathlib.PurePosixPath`.
- [ ] **AC-5b — `SandboxRun.trace_path` is `Path | None`, JSON-round-trips as `null`:** `SandboxRun(trace_path=None, …).model_dump_json()` contains `"trace_path":null`; `SandboxRun.model_validate_json(...).trace_path is None`. A coercion to `""` would corrupt downstream collectors.

### F. Newtype seams for domain primitives (CLAUDE.md "newtype when crossing ≥ 2 modules")

- [ ] **AC-6 — `RunId` is declared as `NewType('RunId', str)` and used as the annotation of `SandboxRun.run_id`:** `typing.get_type_hints(SandboxRun)['run_id'] is RunId`; `RunId.__supertype__ is str`. Mirrors Phase-2 precedent `TestId` at [`src/codegenie/adapters/protocols.py:41`](../../../../src/codegenie/adapters/protocols.py:41).
- [ ] **AC-6a — `SandboxSpecHash` is declared as `NewType('SandboxSpecHash', str)` and used as the annotation of `SandboxSpec.sandbox_spec_hash`:** `typing.get_type_hints(SandboxSpec)['sandbox_spec_hash'] is SandboxSpecHash`; `SandboxSpecHash.__supertype__ is str`. Phase 13 cost ledger and S3-01 spec-builder downstream consumers will accept `SandboxSpecHash`, not bare `str`.
- [ ] **AC-6b — `mypy --strict` rejects type confusion between `RunId` and `SandboxSpecHash`:** a `tests/sandbox/test_contract_newtypes_mypy.py` file containing `run_id: RunId = SandboxSpecHash("x"); spec_hash: SandboxSpecHash = RunId("y")` is referenced from `[tool.mypy] # known-bad-fixtures` *or* lives under `tests/static/typing/` and is executed via `mypy --strict` returning exit-code 1. (Project may use `pytest-mypy-plugins` style: see Notes for the implementer.)

### G. Numeric range and cross-field invariants (illegal-states-unrepresentable)

- [ ] **AC-7 — Resource-budget fields are `Field(gt=0)`:** `SandboxSpec.time_budget_seconds`, `SandboxSpec.memory_limit_mib`, `SandboxSpec.pids_limit` reject `0` and `-1` with `ValidationError`. Parametrized test.
- [ ] **AC-7a — Observed-counter fields are `Field(ge=0)`:** `SandboxRun.duration_ms`, `SandboxRun.image_pull_bytes`, `SandboxRun.microvm_seconds` reject `-1` (but accept `0`).
- [ ] **AC-7b — `SandboxRun` rejects mismatched `(backend, gate_isolation_class)` pairs** via a `@model_validator(mode='after')`. Goals 5/6 commitment. Specifically:
  - `(docker_in_docker, shared_kernel)` — constructs successfully.
  - `(firecracker, microvm)` — constructs successfully.
  - `(docker_in_docker, microvm)` — raises `ValidationError`.
  - `(firecracker, shared_kernel)` — raises `ValidationError`.
- [ ] **AC-7c — `SandboxRun` rejects `ended_at < started_at`** via the same `@model_validator(mode='after')` and raises `ValidationError`.
- [ ] **AC-7d — `SandboxRun` rejects simultaneous `timed_out=True` AND `killed_by_oom=True`** (arch §Edge cases 3/4 treats them as mutually exclusive failure modes); raises `ValidationError`.
- [ ] **AC-7e — `SandboxSpec` rejects `network="none"` with a non-empty `egress_allowlist`** via a `@model_validator(mode='after')`; raises `ValidationError`. ("`none` means no network; an allowlist is meaningless and a misconfiguration.")

### H. JSON round-trip (forward-compat with Phase 9 cache-key seam)

- [ ] **AC-8 — Canonical JSON round-trip is byte-stable under env-dict reordering** (hypothesis property test): for any valid `SandboxSpec` (random `env`, `cmd`, `egress_allowlist`, `copy_out`), `SandboxSpec.model_validate_json(spec.model_dump_json()).model_dump_json() == spec.model_dump_json()`. Run with at least 50 hypothesis examples.

### I. Module purity + structural discipline

- [ ] **AC-9 — `from __future__ import annotations` on line 1 of the docstring-prefaced module:** static check on the file source.
- [ ] **AC-9a — Module imports only stdlib + pydantic + sibling `codegenie.errors`:** `tests/sandbox/test_contract_purity.py` walks every `Import`/`ImportFrom` node and asserts membership in `{typing, collections, collections.abc, datetime, pathlib, re, pydantic, codegenie.errors}`. No `logging` shadow, no sibling Phase-5 modules (`sandbox.errors`, `sandbox.registry`, etc.), no I/O modules. Mirrors Phase-2 [`adapters/protocols.py`](../../../../src/codegenie/adapters/protocols.py) precedent. (Note: `codegenie.errors` is project-wide and used only if a custom `ValidationError` subclass is needed; the default Pydantic `ValidationError` is the AC default.)
- [ ] **AC-9b — Module docstring cites ADR-0001, ADR-0006, ADR-0012 by filename** (substring match on the file source).

### J. Process gates (tooling + coverage)

- [ ] **AC-10 — Tooling clean:** `ruff check src/codegenie/sandbox/contract.py`, `ruff format --check src/codegenie/sandbox/contract.py`, `mypy --strict src/codegenie/sandbox/contract.py`, `pytest tests/sandbox/test_contract_models.py tests/sandbox/test_sandbox_client_protocol.py tests/sandbox/test_contract_purity.py` all pass.
- [ ] **AC-11 — Coverage on `src/codegenie/sandbox/contract.py`: line ≥ 95% AND branch ≥ 90%** (the 95/90 floor from [`stories/README.md §Definition of done`](README.md) — note: 95 *line*, 90 *branch*, not "95 branch" as the draft conflated).
- [ ] **AC-12 — Fence-test non-regression:** `tests/schema/test_no_llm_imports_in_sandbox.py` (if present from S1-01/S1-07) remains green. `contract.py` imports no symbol from `anthropic`, `langgraph`, `chromadb`, or `sentence_transformers`. (S1-07 lands the formal fence; this story does not regress its precondition.)

## Implementation outline

1. Create `src/codegenie/sandbox/contract.py`. Module preamble:
   - `from __future__ import annotations` (AC-9).
   - Module docstring citing ADR-0001 (two-chokepoint), ADR-0006 (Protocol vs ABC), ADR-0012 (env allowlist) by filename and quoting the "no I/O, no logger, no sibling Phase-5 modules" purity invariant (AC-9b, mirrors [`adapters/protocols.py`](../../../../src/codegenie/adapters/protocols.py:32) precedent).
   - Imports: `typing.{Annotated, Protocol, NewType, Literal, runtime_checkable}`; `collections.abc.Mapping` (NOT `typing.Mapping` — deprecated since 3.9, CLAUDE.md Rule 11); `pathlib.{Path, PurePosixPath}`; `datetime.datetime`; `pydantic.{BaseModel, ConfigDict, Field, model_validator, ValidationError}`.
   - Declare `__all__` explicitly (AC-1a, sorted alphabetically).
2. **Declare two NewTypes at module top** (AC-6, AC-6a — mirrors [`adapters/protocols.py:41`](../../../../src/codegenie/adapters/protocols.py:41) `TestId` precedent):
   ```python
   RunId = NewType("RunId", str)
   """Sandbox run identifier (UUID7 hex). Generated in S3-02 DinD client / S6-01
   Firecracker client. Crosses ≥ 5 modules: contract.py (here), retry_ledger.py
   (S2-01), runner.py (S5-02), cost.py (S7-03), CLI inspect (S8-01)."""

   SandboxSpecHash = NewType("SandboxSpecHash", str)
   """BLAKE3-128 hex digest of canonical-JSON SandboxSpec (sorted env keys).
   Computed in S3-01 SandboxSpecBuilder; consumed by Phase 9 cache key.
   Opaque at the contract level — *shape* validation (32-hex regex) lives in
   the builder, not here, so the contract stays a typed envelope."""
   ```
3. Define `CopyInEntry`. `src: Path` (host), `dst: PurePosixPath` (sandbox POSIX), `mode: Literal["ro", "rw"] = "ro"`. `model_config = ConfigDict(extra="forbid", frozen=True)`.
4. Define `SandboxSpec`:
   - `base_image: str`
   - `copy_in: list[CopyInEntry]`
   - `env: Mapping[str, str]` (from `collections.abc`; ADR-0012)
   - `cmd: list[str]`
   - `network: Literal["none", "scoped"]`
   - `egress_allowlist: list[str]`
   - `enable_trace: bool`
   - `time_budget_seconds: Annotated[int, Field(gt=0)]`
   - `memory_limit_mib: Annotated[int, Field(gt=0)]`
   - `pids_limit: Annotated[int, Field(gt=0)]`
   - `copy_out: list[str]`
   - `label: str`
   - `sandbox_spec_hash: SandboxSpecHash`
   - `model_config = ConfigDict(extra="forbid", frozen=True)`
   - `@model_validator(mode="after")` named `_check_network_implies_no_allowlist`: if `network == "none"` and `egress_allowlist != []`, raise `ValueError` (AC-7e).
5. Define `SandboxRun`:
   - `run_id: RunId`
   - `spec: SandboxSpec`
   - `backend: Literal["docker_in_docker", "firecracker"]`
   - `gate_isolation_class: Literal["shared_kernel", "microvm"]`
   - `started_at: datetime`
   - `ended_at: datetime`
   - `exit_code: int`
   - `duration_ms: Annotated[int, Field(ge=0)]`
   - `microvm_seconds: Annotated[float, Field(ge=0.0)]`
   - `image_pull_bytes: Annotated[int, Field(ge=0)]`
   - `build_cache_hit: bool`
   - `logs_dir: Path`
   - `trace_path: Path | None`
   - `copy_out_root: Path`
   - `timed_out: bool`
   - `killed_by_oom: bool`
   - `model_config = ConfigDict(extra="forbid", frozen=True)`
   - `@model_validator(mode="after")` named `_check_run_invariants`: enforces (a) `(backend, gate_isolation_class)` ∈ `{("docker_in_docker","shared_kernel"), ("firecracker","microvm")}` — AC-7b; (b) `ended_at >= started_at` — AC-7c; (c) `not (timed_out and killed_by_oom)` — AC-7d.
6. Define `SandboxHealth` (`backend`, `reachable`, `confidence`, `reasons`, `warnings`, `detected_at`) with the same `model_config`.
7. Declare `SandboxClient`:
   ```python
   @runtime_checkable
   class SandboxClient(Protocol):
       """Single contract every sandbox backend satisfies. Duck-typed per ADR-0006
       — no shared default behavior; backends register via @register_sandbox_backend
       (S1-05). Phase 6 lifts this Protocol unchanged into LangGraph node side-effects."""

       def execute(self, spec: SandboxSpec) -> SandboxRun: ...
       def health(self) -> SandboxHealth: ...
   ```
   Method bodies are exactly `...` (AC-2b). No `__init__`. No class attributes (AC-2c).
8. Add three test files: `tests/sandbox/test_contract_models.py` (data-model behavior), `tests/sandbox/test_sandbox_client_protocol.py` (Protocol shape), `tests/sandbox/test_contract_purity.py` (module-purity invariant, mirrors `tests/unit/adapters/test_protocols.py` AC-15 precedent).

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file paths:
- `tests/sandbox/test_contract_models.py` — model behavior (Pydantic config, literals, cross-field, range, JSON, newtypes).
- `tests/sandbox/test_sandbox_client_protocol.py` — Protocol shape (decorator, member set, AST body check, duck typing).
- `tests/sandbox/test_contract_purity.py` — module purity invariant (imports + future annotations + `__all__`).

```python
# tests/sandbox/test_contract_models.py
"""Model behavior — every Pydantic-side AC for S1-02."""
from __future__ import annotations

import typing
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from codegenie.sandbox import contract as contract_mod
from codegenie.sandbox.contract import (
    CopyInEntry, RunId, SandboxClient, SandboxHealth, SandboxRun,
    SandboxSpec, SandboxSpecHash,
)


# ----------------- fixtures -----------------

_NOW = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)


def _valid_copy_in_entry(**ov):
    base = dict(src=Path("/tmp/x"), dst=PurePosixPath("/work"))
    base.update(ov)
    return CopyInEntry(**base)


def _valid_spec_kwargs(**ov):
    base = dict(
        base_image="cgr.dev/chainguard/node@sha256:abc",
        copy_in=[_valid_copy_in_entry()],
        env={"PATH": "/usr/bin"},
        cmd=["sh", "-c", "echo hi"],
        network="none",
        egress_allowlist=[],
        enable_trace=False,
        time_budget_seconds=60,
        memory_limit_mib=512,
        pids_limit=128,
        copy_out=[],
        label="stage6.tests.attempt1",
        sandbox_spec_hash=SandboxSpecHash("0" * 32),
    )
    base.update(ov)
    return base


def _valid_spec(**ov):
    return SandboxSpec(**_valid_spec_kwargs(**ov))


def _valid_run_kwargs(**ov):
    base = dict(
        run_id=RunId("01890000-0000-7000-8000-000000000001"),
        spec=_valid_spec(),
        backend="docker_in_docker",
        gate_isolation_class="shared_kernel",
        started_at=_NOW,
        ended_at=_NOW + timedelta(seconds=10),
        exit_code=0,
        duration_ms=10_000,
        microvm_seconds=0.0,
        image_pull_bytes=0,
        build_cache_hit=False,
        logs_dir=Path("/tmp/logs"),
        trace_path=None,
        copy_out_root=Path("/tmp/co"),
        timed_out=False,
        killed_by_oom=False,
    )
    base.update(ov)
    return base


def _valid_health_kwargs(**ov):
    base = dict(
        backend="docker_in_docker",
        reachable=True,
        confidence="high",
        reasons=[],
        warnings=[],
        detected_at=_NOW,
    )
    base.update(ov)
    return base


# ----------------- AC-1, AC-1a: import + __all__ -----------------

def test_all_is_exact_public_surface():
    """AC-1a: __all__ is a frozen contract."""
    assert set(contract_mod.__all__) == {
        "CopyInEntry", "RunId", "SandboxClient", "SandboxHealth",
        "SandboxRun", "SandboxSpec", "SandboxSpecHash",
    }


# ----------------- AC-3: model_config introspection -----------------

@pytest.mark.parametrize("cls", [CopyInEntry, SandboxSpec, SandboxRun, SandboxHealth])
def test_each_model_is_frozen_and_extra_forbid_in_config(cls):
    """AC-3: model_config asserted *directly*, not by side-effect."""
    assert cls.model_config["extra"] == "forbid"
    assert cls.model_config["frozen"] is True


# ----------------- AC-3a: unknown-field rejection on every model -----------------

@pytest.mark.parametrize("factory,kwargs", [
    (CopyInEntry, dict(src=Path("/x"), dst=PurePosixPath("/y"))),
    (SandboxSpec, _valid_spec_kwargs()),
    (SandboxRun, _valid_run_kwargs()),
    (SandboxHealth, _valid_health_kwargs()),
])
def test_each_model_rejects_unknown_field(factory, kwargs):
    """AC-3a."""
    with pytest.raises(ValidationError):
        factory(**kwargs, _bogus="x")


# ----------------- AC-3b: mutation rejection on every model -----------------

@pytest.mark.parametrize("instance_factory,field,new_value", [
    (lambda: _valid_copy_in_entry(),       "mode",     "rw"),
    (lambda: _valid_spec(),                "label",    "mutated"),
    (lambda: SandboxRun(**_valid_run_kwargs()), "exit_code", 99),
    (lambda: SandboxHealth(**_valid_health_kwargs()), "reachable", False),
])
def test_each_model_is_frozen_at_runtime(instance_factory, field, new_value):
    """AC-3b: frozen=True at runtime, every model."""
    inst = instance_factory()
    with pytest.raises(ValidationError):
        setattr(inst, field, new_value)


# ----------------- AC-4: canonical literal SETS, byte-exact -----------------

def _literal_args(cls, field_name):
    ann = cls.model_fields[field_name].annotation
    return typing.get_args(ann)

def test_literal_value_sets_are_byte_exact():
    """AC-4: catches M-6/M-7 — shipping 'dind' or 'linux_namespace' silently."""
    assert _literal_args(SandboxSpec, "network") == ("none", "scoped")
    assert _literal_args(SandboxRun,  "backend") == ("docker_in_docker", "firecracker")
    assert _literal_args(SandboxRun,  "gate_isolation_class") == ("shared_kernel", "microvm")
    assert _literal_args(SandboxHealth, "confidence") == ("high", "medium", "low")
    assert _literal_args(CopyInEntry, "mode") == ("ro", "rw")


# ----------------- AC-4a: each canonical value positively constructs -----------------

@pytest.mark.parametrize("backend,iso", [
    ("docker_in_docker", "shared_kernel"),
    ("firecracker",      "microvm"),
])
def test_run_accepts_exact_canonical_pairings(backend, iso):
    """AC-4a + AC-7b (positive path of cross-field correlation)."""
    SandboxRun(**_valid_run_kwargs(backend=backend, gate_isolation_class=iso))


@pytest.mark.parametrize("confidence", ["high", "medium", "low"])
def test_health_accepts_each_confidence_value(confidence):
    SandboxHealth(**_valid_health_kwargs(confidence=confidence))


@pytest.mark.parametrize("network", ["none", "scoped"])
def test_spec_accepts_each_network_value(network):
    _valid_spec(network=network)


# ----------------- AC-4b: out-of-set rejection -----------------

@pytest.mark.parametrize("kwargs", [
    dict(network="anywhere"),
])
def test_spec_rejects_invalid_network_literal(kwargs):
    with pytest.raises(ValidationError):
        _valid_spec(**kwargs)


def test_run_rejects_invalid_backend_literal():
    with pytest.raises(ValidationError):
        SandboxRun(**_valid_run_kwargs(backend="kvm"))


def test_run_rejects_invalid_isolation_literal():
    with pytest.raises(ValidationError):
        SandboxRun(**_valid_run_kwargs(gate_isolation_class="linux_namespace",
                                       backend="firecracker"))


def test_health_rejects_invalid_confidence_literal():
    with pytest.raises(ValidationError):
        SandboxHealth(**_valid_health_kwargs(confidence="absolute"))


def test_copy_in_rejects_invalid_mode():
    with pytest.raises(ValidationError):
        CopyInEntry(src=Path("/x"), dst=PurePosixPath("/y"), mode="rwx")


# ----------------- AC-4c: CopyInEntry default mode -----------------

def test_copy_in_default_mode_ro():
    assert _valid_copy_in_entry().mode == "ro"


# ----------------- AC-5: source-level annotation pinning -----------------

def test_spec_env_annotation_is_mapping_not_dict():
    """AC-5: ADR-0012 requires Mapping[str, str] read-only intent."""
    hints = typing.get_type_hints(SandboxSpec)
    origin = typing.get_origin(hints["env"])
    args = typing.get_args(hints["env"])
    assert origin is Mapping, f"expected collections.abc.Mapping, got {origin!r}"
    assert args == (str, str)


def test_copy_in_path_types_are_distinguished():
    """AC-5a: src=Path (host); dst=PurePosixPath (sandbox)."""
    hints = typing.get_type_hints(CopyInEntry)
    assert hints["src"] is Path
    assert hints["dst"] is PurePosixPath


def test_run_trace_path_round_trips_none_as_null():
    """AC-5b: None must serialize as JSON null, not "" or omitted."""
    run = SandboxRun(**_valid_run_kwargs(trace_path=None))
    j = run.model_dump_json()
    assert '"trace_path":null' in j
    again = SandboxRun.model_validate_json(j)
    assert again.trace_path is None


# ----------------- AC-6, AC-6a: NewType seams -----------------

def test_run_id_is_newtype_over_str():
    """AC-6: RunId is a NewType, mirroring TestId precedent in adapters/protocols.py:41."""
    assert RunId.__supertype__ is str
    # the annotation pin:
    assert typing.get_type_hints(SandboxRun)["run_id"] is RunId


def test_sandbox_spec_hash_is_newtype_over_str():
    """AC-6a."""
    assert SandboxSpecHash.__supertype__ is str
    assert typing.get_type_hints(SandboxSpec)["sandbox_spec_hash"] is SandboxSpecHash


# ----------------- AC-7: numeric range constraints -----------------

@pytest.mark.parametrize("field,bad", [
    ("time_budget_seconds", 0),
    ("time_budget_seconds", -1),
    ("memory_limit_mib", 0),
    ("memory_limit_mib", -1),
    ("pids_limit", 0),
    ("pids_limit", -1),
])
def test_spec_rejects_non_positive_resource_budgets(field, bad):
    """AC-7."""
    with pytest.raises(ValidationError):
        _valid_spec(**{field: bad})


@pytest.mark.parametrize("field,bad", [
    ("duration_ms", -1),
    ("image_pull_bytes", -1),
    ("microvm_seconds", -0.1),
])
def test_run_rejects_negative_observed_counters(field, bad):
    """AC-7a — negative; zero is allowed for these."""
    with pytest.raises(ValidationError):
        SandboxRun(**_valid_run_kwargs(**{field: bad}))


# ----------------- AC-7b: cross-field backend/isolation invariant -----------------

@pytest.mark.parametrize("backend,iso", [
    ("docker_in_docker", "microvm"),
    ("firecracker",      "shared_kernel"),
])
def test_run_rejects_mismatched_backend_isolation_pair(backend, iso):
    """AC-7b — Goals 5/6 commitment."""
    with pytest.raises(ValidationError):
        SandboxRun(**_valid_run_kwargs(backend=backend, gate_isolation_class=iso))


# ----------------- AC-7c: ended_at >= started_at -----------------

def test_run_rejects_ended_before_started():
    with pytest.raises(ValidationError):
        SandboxRun(**_valid_run_kwargs(started_at=_NOW, ended_at=_NOW - timedelta(seconds=1)))


# ----------------- AC-7d: timed_out XOR killed_by_oom -----------------

def test_run_rejects_simultaneous_timeout_and_oom():
    with pytest.raises(ValidationError):
        SandboxRun(**_valid_run_kwargs(timed_out=True, killed_by_oom=True))


# ----------------- AC-7e: network=none implies empty egress_allowlist -----------------

def test_spec_rejects_none_network_with_nonempty_allowlist():
    with pytest.raises(ValidationError):
        _valid_spec(network="none", egress_allowlist=["github.com"])


def test_spec_accepts_scoped_with_allowlist():
    _valid_spec(network="scoped", egress_allowlist=["registry.npmjs.org"])


# ----------------- AC-8: JSON round-trip property (hypothesis) -----------------

@settings(max_examples=50, deadline=None)
@given(
    env=st.dictionaries(
        keys=st.text(min_size=1, max_size=8, alphabet=st.characters(min_codepoint=65, max_codepoint=90)),
        values=st.text(max_size=16, alphabet=st.characters(min_codepoint=32, max_codepoint=126)),
        max_size=5,
    ),
    cmd=st.lists(st.text(min_size=1, max_size=8), min_size=1, max_size=4),
    allowlist=st.lists(st.text(min_size=1, max_size=12), max_size=3),
)
def test_spec_canonical_json_round_trip_is_byte_stable(env, cmd, allowlist):
    """AC-8: catches env-dict reordering bugs in Phase 9 cache-key seam."""
    spec = _valid_spec(env=env, cmd=cmd, network="scoped", egress_allowlist=allowlist)
    j1 = spec.model_dump_json()
    again = SandboxSpec.model_validate_json(j1)
    assert again.model_dump_json() == j1
```

```python
# tests/sandbox/test_sandbox_client_protocol.py
"""Protocol shape — ADR-0006 + duck-typing ACs."""
from __future__ import annotations

import ast
import typing
from pathlib import Path

from codegenie.sandbox import contract as contract_mod
from codegenie.sandbox.contract import (
    SandboxClient, SandboxHealth, SandboxRun, SandboxSpec,
)


class _Good:
    def execute(self, spec: SandboxSpec) -> SandboxRun: ...  # type: ignore[empty-body]
    def health(self) -> SandboxHealth: ...  # type: ignore[empty-body]


class _GoodPlusExtra:
    def execute(self, spec: SandboxSpec) -> SandboxRun: ...  # type: ignore[empty-body]
    def health(self) -> SandboxHealth: ...  # type: ignore[empty-body]
    def cleanup(self) -> None: ...


class _MissingHealth:
    def execute(self, spec: SandboxSpec) -> SandboxRun: ...  # type: ignore[empty-body]


# ----------------- AC-2: @runtime_checkable present directly -----------------

def test_sandbox_client_is_runtime_checkable():
    """AC-2 — asserted directly, not via isinstance side-effect."""
    assert getattr(SandboxClient, "_is_runtime_protocol", False) is True


# ----------------- AC-2a: surface cardinality -----------------

def test_protocol_member_set_is_exactly_execute_and_health():
    """AC-2a — catches M-12: adding a third method silently."""
    members = set(typing.get_protocol_members(SandboxClient))
    assert members == {"execute", "health"}


# ----------------- AC-2b: AST walk — method bodies are exactly `...` -----------------

def test_protocol_method_bodies_are_ellipsis_only():
    """AC-2b — ADR-0006: no shared default behavior."""
    src = Path(contract_mod.__file__).read_text()
    tree = ast.parse(src)
    cls = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "SandboxClient"
    )
    fn_defs = [n for n in cls.body if isinstance(n, ast.FunctionDef)]
    assert {fn.name for fn in fn_defs} == {"execute", "health"}
    for fn in fn_defs:
        assert len(fn.body) == 1, f"{fn.name}: body has {len(fn.body)} stmts; ADR-0006 requires 1"
        stmt = fn.body[0]
        assert isinstance(stmt, ast.Expr), f"{fn.name}: body[0] is {type(stmt).__name__}"
        assert isinstance(stmt.value, ast.Constant), f"{fn.name}: body[0].value not a Constant"
        assert stmt.value.value is Ellipsis, f"{fn.name}: body is not `...`"


# ----------------- AC-2c: no __init__, no class attrs -----------------

def test_protocol_has_no_init_and_no_class_attrs():
    """AC-2c — pure structural typing only."""
    callable_attrs = {
        name for name in vars(SandboxClient)
        if callable(vars(SandboxClient)[name])
        and not name.startswith("__")
    }
    assert callable_attrs == {"execute", "health"}


# ----------------- AC-2d: duck-typed satisfaction -----------------

def test_protocol_accepts_compliant_stub():
    assert isinstance(_Good(), SandboxClient)


def test_protocol_rejects_partial_implementation():
    assert not isinstance(_MissingHealth(), SandboxClient)


def test_protocol_accepts_stub_with_extra_methods():
    """Protocol checks presence, not absence — structural typing semantics."""
    assert isinstance(_GoodPlusExtra(), SandboxClient)
```

```python
# tests/sandbox/test_contract_purity.py
"""Module purity invariant — mirrors Phase-2 adapters/protocols.py precedent."""
from __future__ import annotations

import ast
from pathlib import Path

from codegenie.sandbox import contract as contract_mod


_ALLOWED_TOPLEVEL_IMPORTS = {
    "typing", "collections", "collections.abc",
    "datetime", "pathlib", "re",
    "pydantic",
    "codegenie.errors",
}


def _imported_modules(src: str) -> set[str]:
    tree = ast.parse(src)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.add(node.module)
    return out


def test_contract_module_has_future_annotations():
    """AC-9."""
    src = Path(contract_mod.__file__).read_text()
    assert "from __future__ import annotations" in src.splitlines()[:25]


def test_contract_module_imports_only_allowed_sources():
    """AC-9a — purity. No I/O, no logger, no sibling Phase-5 modules."""
    src = Path(contract_mod.__file__).read_text()
    seen = _imported_modules(src)
    extra = seen - _ALLOWED_TOPLEVEL_IMPORTS
    assert not extra, (
        f"contract.py imported disallowed modules: {sorted(extra)}. "
        f"Allowed: {sorted(_ALLOWED_TOPLEVEL_IMPORTS)}"
    )


def test_contract_module_docstring_cites_adrs():
    """AC-9b."""
    doc = contract_mod.__doc__ or ""
    for adr in ("ADR-0001", "ADR-0006", "ADR-0012"):
        assert adr in doc, f"module docstring must cite {adr}"
```

Run the three test files; confirm `ImportError` on every contract symbol (including `RunId`, `SandboxSpecHash`); commit the red tests; then implement.

### Green — make it pass

Implement `contract.py` per the Implementation outline. Notes for the green pass:

- Use `Mapping[str, str]` from `collections.abc` (NOT `typing.Mapping` — deprecated since 3.9; codebase convention is unanimous across 10+ modules).
- Pydantic v2 model-validator syntax: `@model_validator(mode="after")` on a method that returns `self` after raising `ValueError` on the invariant violation; Pydantic wraps `ValueError` into `ValidationError` for the AC tests.
- The two `@model_validator` methods on `SandboxRun` should be named with leading underscore (`_check_run_invariants`) — they are not part of the public API.
- `RunId` and `SandboxSpecHash` are `typing.NewType`s — they exist *only* at the type-checker level; at runtime, `RunId("x")` returns the bare string `"x"`. Tests use them as constructors to document intent (mirrors `adapters/protocols.py` TestId usage).
- For `Field(gt=0)` / `Field(ge=0)` constraints, prefer `Annotated[int, Field(gt=0)]` over `int = Field(..., gt=0)` — keeps mypy --strict happy and makes the constraint visible at the annotation level (introspectable by future tooling).

### Refactor — clean up

- Add a one-sentence docstring to each model class (`CopyInEntry`, `SandboxSpec`, `SandboxRun`, `SandboxHealth`) and to `SandboxClient`, quoting the contract role from `phase-arch-design.md §Data model` comments.
- Confirm `mypy --strict` passes with **zero** warnings; `runtime_checkable` + `Protocol` does not surface `unreachable` warnings at this version of the project's mypy config.
- Re-read every `@model_validator` for clarity. Each one should raise `ValueError(<short, specific message>)` — the message bubbles into Pydantic's `ValidationError` and is observable in test debug output.
- Confirm `__all__` is alphabetized (matches the `set(...)` assertion in AC-1a).
- Verify the module-purity test passes after the implementation — if `pydantic.types`, `pydantic_core`, etc. are imported transitively, add them to the allowlist with a comment explaining the addition.
- Logging: this story emits no log lines; structlog event constants from S1-01 are imported only by callers (S2-01 ledger onward), not by the contract.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/contract.py` | New file — Protocol + four frozen Pydantic models per ADR-0001/0006/0012; declares `RunId` and `SandboxSpecHash` NewTypes |
| `tests/sandbox/test_contract_models.py` | New test — `model_config` introspection, literal sets byte-exact (positive + negative), source-level annotation pinning, newtype assertions, numeric range constraints, cross-field invariants, hypothesis round-trip |
| `tests/sandbox/test_sandbox_client_protocol.py` | New test — `@runtime_checkable` direct assertion, surface cardinality, AST walk of method bodies (ADR-0006), duck-typed satisfaction |
| `tests/sandbox/test_contract_purity.py` | New test — `from __future__ import annotations`, import allowlist (mirrors Phase-2 `adapters/protocols.py` purity precedent), module docstring cites ADRs |

## Out of scope

- **`sandbox_spec_hash` *computation* AND *hex-shape validation*** — this story declares the field as the opaque `SandboxSpecHash` NewType over `str`. Both BLAKE3 canonical hashing AND the `^[0-9a-f]{32}$` regex enforcement live in story S3-01 (`SandboxSpecBuilder`). The contract is a typed envelope, not a guard — keeps S1-02 free of policy.
- **`env_allowlist.filter` behavior** — story S1-05. The contract declares `env: Mapping[str, str]`; the filter that produces the post-filter view is separate.
- **`SandboxHealthProbe`** — story S3-06 (uses `SandboxHealth` produced here).
- **Backend implementations (`DockerInDockerClient`, `FirecrackerClient`)** — Step 3 and Step 6 respectively.
- **`ObjectiveSignals`** — story S1-03 (different file: `sandbox/signals/models.py`).
- **RunId generation** — `RunId` is the *type*; UUID7 generation lives in S3-02 DinD client / S6-01 Firecracker client.

## Notes for the implementer

### Pydantic v2 idioms

- **Always** `model_config = ConfigDict(extra="forbid", frozen=True)`. Never the v1 `class Config` style — the project is Python 3.11+ and Pydantic 2.
- **Range constraints prefer `Annotated[T, Field(...)]`** over `field: T = Field(...)` — keeps the annotation introspectable by `typing.get_type_hints` and clean under `mypy --strict`.
- **`@model_validator(mode="after")`** raises `ValueError` on invariant violation; Pydantic wraps it in `ValidationError` for callers. Method name should be `_check_<invariant>` (leading underscore — internal). Returns `self`.
- **NewType is a type-checker shim**, not a runtime wrapper. `RunId("x")` returns the bare `str` at runtime; tests use the constructor form only as intent documentation. Mirrors the `TestId = NewType("TestId", str)` pattern at [`src/codegenie/adapters/protocols.py:41`](../../../../src/codegenie/adapters/protocols.py:41).

### Domain primitives + codebase convention (CLAUDE.md Rule 11)

- **`Mapping` comes from `collections.abc`, NOT `typing`.** The codebase uses `from collections.abc import Mapping` unanimously across 10+ modules; `typing.Mapping` is deprecated since 3.9. This is non-negotiable.
- **`PurePosixPath` for `CopyInEntry.dst`** (sandbox is POSIX even on macOS hosts); **`Path` for `src`** (host path). The distinction is not cosmetic — Windows host paths must never leak into sandbox path semantics.
- **Literal value spellings are byte-exact, no aliases.** `"docker_in_docker"` NOT `"dind"`, `"shared_kernel"` NOT `"linux_namespace"`. Phase 13's cost ledger uses these strings as primary keys; the eval-harness Phase 6.5 will reference them by exact-match. Mistakes here cascade.

### Cross-field invariants (illegal-states-unrepresentable)

The story's `@model_validator` choices treat the contract as the seam where invariants live. The alternative — pushing them into the builders (`SandboxSpecBuilder` S3-01, `DockerInDockerClient` S3-02) — would let callers construct nonsense intermediaries. ADR-0001 says the contract is what Phase 6 lifts unchanged; if the contract permits illegal states, Phase 6's LangGraph nodes inherit them. So:

- **`(backend, gate_isolation_class)` correlation** lives on `SandboxRun`, not on the backend implementation.
- **`network=="none"` → empty `egress_allowlist`** lives on `SandboxSpec`, not on `SandboxSpecBuilder`. The builder may still call `egress_allowlist=[]` defensively, but the model rejects the contradictory combination at construction.
- **`ended_at >= started_at`** + **`not (timed_out and killed_by_oom)`** live on `SandboxRun` for the same reason.

### Forward-seam notes — what *doesn't* go in `contract.py` (Rule 2)

- **`SandboxRun.backend: Literal["docker_in_docker", "firecracker"]` is a closed Literal today.** That's intentional: Phase 7 distroless and any future Podman/Kata backend will need an ADR-0001 amendment that widens this Literal. Do **not** silently widen to `str` — that breaks the Phase 13 cost ledger's primary-key contract. The Protocol itself (open seam) + `@register_sandbox_backend` registry (S1-05, also open) handle backend extensibility at the *code* level; the data model's `Literal` is the *closed mirror* that downstream consumers depend on.
- **`SandboxRun.confidence`-style tagged union** (`SuccessfulRun | TimedOutRun | OomKilledRun | FailedRun`) is *not* part of this story. The flat shape with cross-field validators is the architect's prescribed minimum (`phase-arch-design.md §Data model`). If a future story needs to discriminate on outcome, the sum-type refactor is its job — the `@model_validator` makes the illegal combinations unrepresentable today without requiring the larger refactor.
- **`SandboxSpecHash` shape validation (32 lowercase hex)** is deliberately not enforced in the contract — it's `SandboxSpecBuilder`'s responsibility (S3-01). Keeps the contract module free of policy and the test surface small.

### NewType discipline

- **`RunId`** crosses ≥ 5 module boundaries (contract → S2-01 ledger → S5-02 runner → S7-03 cost emitter → S8-01 CLI inspect). CLAUDE.md's "Domain identifiers ... are typed (newtype) when they cross ≥ 2 module boundaries" + the [Phase-2 `TestId` precedent](../../../../src/codegenie/adapters/protocols.py:41) demand the newtype now, not later.
- **`SandboxSpecHash`** crosses contract → S3-01 builder → S5-02 runner → Phase 9 cache-key. Same threshold.
- Other `str`-shaped fields (`base_image`, `label`, `egress_allowlist[i]`, `cmd[i]`, `copy_out[i]`, `reasons[i]`, `warnings[i]`) **do not** get newtypes today — Rule 2 caps the abstraction. If a future story consumes any of these as a typed surface (e.g., `base_image` becomes `BaseImageRef` when Phase 7 distroless lands), the newtype goes there.

### Coverage floor and process

- This module sits on the **95% line / 90% branch** floor per [`stories/README.md §Definition of done`](README.md). Cover every literal mismatch, every model_validator branch (positive + each negative path), the JSON round-trip, the newtype assertions, and the AST walk.
- Run the three test files in order: models → protocol → purity. Failures in `test_contract_purity.py` are usually a forgotten `__future__` import or a stray `import logging` — fix at the source, do not relax the allowlist without an explanatory comment.
