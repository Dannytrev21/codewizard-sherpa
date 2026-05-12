# Story S1-02 — `sandbox/contract.py` — `SandboxClient` Protocol + `SandboxSpec/Run/Health/CopyInEntry` models

**Step:** Step 1 — Scaffold packages, contracts, and CI fences
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0001, ADR-0006, ADR-0012

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

- [ ] `from codegenie.sandbox.contract import SandboxClient, SandboxSpec, SandboxRun, SandboxHealth, CopyInEntry` succeeds.
- [ ] `SandboxClient` is declared with `@runtime_checkable` and defines exactly two methods (`execute`, `health`); a stub class with both methods passes `isinstance(stub, SandboxClient)`; a stub missing `health` fails it.
- [ ] All four models carry `model_config = ConfigDict(extra="forbid", frozen=True)`; constructing any model with an unknown field raises `pydantic.ValidationError`; mutating any field after construction raises `pydantic.ValidationError`.
- [ ] `SandboxSpec.network` is `Literal["none", "scoped"]`; `SandboxRun.backend` is `Literal["docker_in_docker", "firecracker"]`; `SandboxRun.gate_isolation_class` is `Literal["shared_kernel", "microvm"]`; `SandboxHealth.confidence` is `Literal["high", "medium", "low"]`. Each literal rejects out-of-set values at construction.
- [ ] `CopyInEntry.mode` default is `"ro"`; the union is `Literal["ro", "rw"]`.
- [ ] `SandboxSpec` round-trips canonical JSON: `SandboxSpec.model_validate_json(spec.model_dump_json())` yields a byte-equal model (property test with hypothesis).
- [ ] TDD plan's red tests exist, are committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/sandbox/contract.py`, `pytest tests/sandbox/test_contract_models.py tests/sandbox/test_sandbox_client_protocol.py` all pass.
- [ ] Branch coverage on `src/codegenie/sandbox/contract.py` ≥ 95% (the 95/90 floor from `stories/README.md §Definition of done`).

## Implementation outline

1. Create `src/codegenie/sandbox/contract.py`. Import `typing.Protocol`, `runtime_checkable`, `Literal`, `Mapping`; `pathlib.Path`, `PurePosixPath`; `datetime`; `pydantic.BaseModel`, `ConfigDict`.
2. Define `CopyInEntry` per the pseudo-code (`src`, `dst`, `mode`).
3. Define `SandboxSpec` per the pseudo-code, including `sandbox_spec_hash: str` (BLAKE3-128 hex placeholder; computation lives in S3-01).
4. Define `SandboxRun` per the pseudo-code (every field: `run_id`, `spec`, `backend`, `gate_isolation_class`, `started_at`, `ended_at`, `exit_code`, `duration_ms`, `microvm_seconds`, `image_pull_bytes`, `build_cache_hit`, `logs_dir`, `trace_path`, `copy_out_root`, `timed_out`, `killed_by_oom`).
5. Define `SandboxHealth` per the pseudo-code (`backend`, `reachable`, `confidence`, `reasons`, `warnings`, `detected_at`).
6. Declare `SandboxClient` Protocol with `execute(self, spec: SandboxSpec) -> SandboxRun` and `health(self) -> SandboxHealth`; decorate with `@runtime_checkable`.
7. Add the two `tests/sandbox/test_*` files.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/sandbox/test_contract_models.py`, `tests/sandbox/test_sandbox_client_protocol.py`.

```python
# tests/sandbox/test_contract_models.py
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import pytest
from pydantic import ValidationError
from codegenie.sandbox.contract import (
    CopyInEntry, SandboxSpec, SandboxRun, SandboxHealth,
)

def _valid_spec(**overrides):
    base = dict(
        base_image="cgr.dev/chainguard/node@sha256:abc",
        copy_in=[CopyInEntry(src=Path("/tmp/x"), dst=PurePosixPath("/work"))],
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
        sandbox_spec_hash="0" * 32,
    )
    base.update(overrides)
    return SandboxSpec(**base)

def test_spec_rejects_unknown_field():
    with pytest.raises(ValidationError):
        _valid_spec(unexpected="boom")  # extra="forbid"

def test_spec_is_frozen():
    spec = _valid_spec()
    with pytest.raises(ValidationError):
        spec.label = "mutated"  # frozen=True

def test_spec_network_literal_rejects_unknown_value():
    with pytest.raises(ValidationError):
        _valid_spec(network="anywhere")

def test_run_backend_and_isolation_literals():
    spec = _valid_spec()
    with pytest.raises(ValidationError):
        SandboxRun(
            run_id="r1", spec=spec, backend="kvm",  # invalid
            gate_isolation_class="shared_kernel",
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            exit_code=0, duration_ms=10, microvm_seconds=0.0,
            image_pull_bytes=0, build_cache_hit=False,
            logs_dir=Path("/tmp/logs"), trace_path=None,
            copy_out_root=Path("/tmp/co"),
            timed_out=False, killed_by_oom=False,
        )

def test_copy_in_default_mode_ro():
    e = CopyInEntry(src=Path("/x"), dst=PurePosixPath("/y"))
    assert e.mode == "ro"

def test_health_confidence_literal():
    with pytest.raises(ValidationError):
        SandboxHealth(
            backend="docker_in_docker", reachable=True,
            confidence="absolute",  # invalid
            reasons=[], warnings=[],
            detected_at=datetime.now(timezone.utc),
        )

def test_spec_round_trip_json_byte_equal():
    spec = _valid_spec()
    j = spec.model_dump_json()
    again = SandboxSpec.model_validate_json(j)
    assert again.model_dump_json() == j
```

```python
# tests/sandbox/test_sandbox_client_protocol.py
from codegenie.sandbox.contract import SandboxClient, SandboxSpec, SandboxRun, SandboxHealth

class _Good:
    def execute(self, spec: SandboxSpec) -> SandboxRun: ...
    def health(self) -> SandboxHealth: ...

class _MissingHealth:
    def execute(self, spec: SandboxSpec) -> SandboxRun: ...

def test_protocol_is_runtime_checkable_accepts_compliant_stub():
    assert isinstance(_Good(), SandboxClient)

def test_protocol_rejects_partial_implementation():
    assert not isinstance(_MissingHealth(), SandboxClient)
```

Run; confirm `ImportError` on contract members, commit, then implement.

### Green — make it pass

Implement `contract.py` with the four `BaseModel` classes (each with `model_config = ConfigDict(extra="forbid", frozen=True)`) and the `SandboxClient` Protocol. Use `Mapping[str, str]` for `SandboxSpec.env` (not `dict` — read-only intent matches ADR-0012's filter output). Use `Path | None` for `trace_path`. No methods on the models; no constants.

### Refactor — clean up

- Add a docstring on each class quoting the contract role (one sentence each; pulled from `phase-arch-design.md §Data model` comments).
- Confirm `mypy --strict` passes; in particular check that `runtime_checkable` + `Protocol` does not surface any `unreachable` warnings.
- Edge case: `SandboxRun.trace_path` is `Path | None` — confirm `None` round-trips through JSON (`null`).
- Edge case: ADR-0006 mandates *no* shared default behavior on the Protocol — confirm no `__init__`, no class attributes.
- Logging: this story emits no log lines; constants from S1-01 are imported by callers, not by the contract.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/contract.py` | New file — Protocol + four frozen Pydantic models per ADR-0001/0006 |
| `tests/sandbox/test_contract_models.py` | New test — frozen/extra-forbid/literal coverage |
| `tests/sandbox/test_sandbox_client_protocol.py` | New test — `isinstance` against the Protocol |

## Out of scope

- **`sandbox_spec_hash` computation** — this story declares the field; the BLAKE3 canonical hashing lives in story S3-01 (`SandboxSpecBuilder`).
- **`env_allowlist.filter` behavior** — story S1-05.
- **`SandboxHealthProbe`** — story S3-06 (uses `SandboxHealth` produced here).
- **Backend implementations (`DockerInDockerClient`, `FirecrackerClient`)** — Step 3 and Step 6 respectively.
- **`ObjectiveSignals`** — story S1-03 (different file: `sandbox/signals/models.py`).

## Notes for the implementer

- Pydantic v2 syntax: `model_config = ConfigDict(extra="forbid", frozen=True)`. Do NOT use the v1 `class Config` style — the project is Python 3.11+ and Pydantic 2.
- `SandboxSpec.env: Mapping[str, str]` — Pydantic will coerce a plain `dict` into the model and treat the field as read-only. Do not weaken to `dict[str, str]` unless mypy complains and you can prove it (note your finding in the PR body).
- `PurePosixPath` for `CopyInEntry.dst` (sandbox is POSIX even on macOS hosts) and `Path` for `src` (host path).
- `sandbox_spec_hash` is `str` here, not `bytes` — canonical-JSON hashing comes later; the contract just guarantees the field's *presence and type*.
- The `Literal` values must match `phase-arch-design.md §Data model` exactly — `"docker_in_docker"`, NOT `"dind"`; `"shared_kernel"`, NOT `"linux_namespace"`. Downstream readers (Phase 13 cost ledger) depend on the spelling.
- Coverage: this is one of two modules with the 95/90 floor (per `stories/README.md §Definition of done`). Cover every literal mismatch + frozen + extra-forbid + round-trip.
