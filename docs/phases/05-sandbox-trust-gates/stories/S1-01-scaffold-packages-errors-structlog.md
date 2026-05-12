# Story S1-01 — Scaffold `sandbox/` + `gates/` packages with errors and structlog event constants

**Step:** Step 1 — Scaffold packages, contracts, and CI fences
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0001, ADR-0006, ADR-0008

## Context

Phase 5 introduces two brand-new top-level packages (`src/codegenie/sandbox/` and `src/codegenie/gates/`) and every later story in this phase imports from them. This story plants the empty packages, the error-class hierarchies, and the canonical `structlog` event-name constants so every other Step 1 story can land its contracts without inventing names ad hoc. Nothing executes yet; this is foundational scaffolding the rest of the phase grows from.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Development view — how is the source code organized?` — the directory tree Phase 5 ships under `src/codegenie/sandbox/` and `src/codegenie/gates/`.
  - `../phase-arch-design.md §Harness engineering` — structured logging policy: every record carries `run_id`, `workflow_id`, `gate_id`, `attempt_id`, `sandbox_run_id`; no log line > 4 KB.
  - `../phase-arch-design.md §Component design — DockerInDockerClient` — names the error classes (`SandboxBackendError`, `SandboxImageUnavailable`).
  - `../phase-arch-design.md §Component design — FirecrackerClient` — names `FirecrackerKvmMissing`, `FirecrackerBinaryMissing`, `FirecrackerRootfsMissing`.
  - `../phase-arch-design.md §Component design — Gate ABC + StrictAndGate` — names `GateMissingRequiredSignal`.
  - `../phase-arch-design.md §Component design — RetryLedger` — names `AuditChainCorrupted`, `LedgerAttemptOutOfOrder`.
  - `../phase-arch-design.md §Component design — SandboxSpecBuilder` — names `GateCatalogInvalid`, `SandboxSpecForbidden`.
- **Phase ADRs (rules this story honors):**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — ADR-0001 — two new packages exist; the seam is `SandboxClient`, not a generalized `run_in_sandbox`.
  - `../ADRs/0006-protocol-vs-abc-convention.md` — ADR-0006 — `sandbox/` will host a Protocol; `gates/` will host an ABC; this story creates both package roots.
  - `../ADRs/0008-llm-judge-persona-deferral.md` — ADR-0008 — Phase 5 ships no LLM in `sandbox/` or `gates/`; fence imports are added by S1-07 but this scaffold must not import `anthropic`/`langgraph`.
- **Source design:**
  - `../final-design.md §Component-1 / Component-2` — package boundaries.
- **High-level impl:**
  - `../High-level-impl.md §Step 1 — Features delivered` — bullets 1–2 (the packages, `__init__.py`, `errors.py`).

## Goal

Create the two new top-level packages with empty `__init__.py` files, populated `errors.py` hierarchies, and a `logging.py` module exposing canonical structlog event-name constants the rest of Phase 5 imports.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/__init__.py` and `src/codegenie/gates/__init__.py` exist; importing each at a fresh Python session succeeds with no side effects.
- [ ] `src/codegenie/sandbox/errors.py` defines a `SandboxError` base plus subclasses: `SandboxBackendError`, `SandboxBackendInvalid`, `SandboxImageUnavailable`, `SandboxSpecForbidden`, `FirecrackerKvmMissing`, `FirecrackerBinaryMissing`, `FirecrackerRootfsMissing`, `RepoAlreadyInProgress`, `SignalKindAlreadyRegistered`.
- [ ] `src/codegenie/gates/errors.py` defines a `GateError` base plus subclasses: `GateMissingRequiredSignal`, `GateCatalogInvalid`, `AuditChainCorrupted`, `LedgerAttemptOutOfOrder`.
- [ ] `src/codegenie/sandbox/logging.py` and `src/codegenie/gates/logging.py` export module-level string constants (e.g., `EVT_GATE_RUN_STARTED`, `EVT_SANDBOX_EXECUTE_STARTED`, `EVT_PRE_EXECUTE_MARKER_WRITTEN`, `EVT_PROMPT_INJECTION_DETECTED`, `EVT_GATE_ATTEMPTS_OVERRIDE`, `EVT_SANDBOX_EGRESS_BLOCKED`) — every event name in `phase-arch-design.md §Harness engineering` and `§Edge cases` has a constant.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] No import of `anthropic`, `langgraph`, `chromadb`, or `sentence_transformers` anywhere under either package (verified by `python -c "import ast; ..."` smoke; the formal AST fence lands in S1-07).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on `src/codegenie/sandbox/` and `src/codegenie/gates/`; `pytest tests/sandbox/test_scaffold.py tests/gates/test_scaffold.py` passes.

## Implementation outline

1. Create `src/codegenie/sandbox/__init__.py` (empty docstring header — name + one-line purpose).
2. Create `src/codegenie/gates/__init__.py` (same shape).
3. Create `src/codegenie/sandbox/errors.py` with the `SandboxError` hierarchy. Each class carries one `__doc__` sentence and no `__init__` body beyond `super().__init__`.
4. Create `src/codegenie/gates/errors.py` with the `GateError` hierarchy.
5. Create `src/codegenie/sandbox/logging.py` and `src/codegenie/gates/logging.py` with `Final[str]` constants for every event name referenced in arch §Harness engineering, §Edge cases, and §Adversarial tests.
6. Add `tests/sandbox/__init__.py` and `tests/gates/__init__.py` packages plus `tests/sandbox/test_scaffold.py` and `tests/gates/test_scaffold.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/sandbox/test_scaffold.py`, `tests/gates/test_scaffold.py`.

```python
# tests/sandbox/test_scaffold.py
import importlib
import pytest

def test_sandbox_package_imports_cleanly():
    mod = importlib.import_module("codegenie.sandbox")
    assert mod is not None

def test_sandbox_errors_exposes_full_hierarchy():
    from codegenie.sandbox import errors
    assert issubclass(errors.SandboxBackendError, errors.SandboxError)
    assert issubclass(errors.SandboxBackendInvalid, errors.SandboxError)
    assert issubclass(errors.SandboxImageUnavailable, errors.SandboxError)
    assert issubclass(errors.SandboxSpecForbidden, errors.SandboxError)
    assert issubclass(errors.FirecrackerKvmMissing, errors.SandboxError)
    assert issubclass(errors.FirecrackerBinaryMissing, errors.SandboxError)
    assert issubclass(errors.FirecrackerRootfsMissing, errors.SandboxError)
    assert issubclass(errors.RepoAlreadyInProgress, errors.SandboxError)
    assert issubclass(errors.SignalKindAlreadyRegistered, errors.SandboxError)

def test_sandbox_logging_event_constants_are_unique_strings():
    from codegenie.sandbox import logging as sandbox_log
    names = [
        "EVT_SANDBOX_EXECUTE_STARTED",
        "EVT_SANDBOX_EXECUTE_COMPLETED",
        "EVT_SANDBOX_EGRESS_BLOCKED",
        "EVT_PROMPT_INJECTION_DETECTED",
    ]
    values = [getattr(sandbox_log, n) for n in names]
    assert all(isinstance(v, str) and v for v in values)
    assert len(set(values)) == len(values), "event constants must be unique"

def test_sandbox_package_has_no_forbidden_imports():
    import codegenie.sandbox as pkg
    import sys
    # importing sandbox must not pull anthropic/langgraph into sys.modules
    for banned in ("anthropic", "langgraph", "chromadb", "sentence_transformers"):
        assert banned not in sys.modules
```

```python
# tests/gates/test_scaffold.py
import importlib
import pytest

def test_gates_package_imports_cleanly():
    mod = importlib.import_module("codegenie.gates")
    assert mod is not None

def test_gates_errors_hierarchy():
    from codegenie.gates import errors
    assert issubclass(errors.GateMissingRequiredSignal, errors.GateError)
    assert issubclass(errors.GateCatalogInvalid, errors.GateError)
    assert issubclass(errors.AuditChainCorrupted, errors.GateError)
    assert issubclass(errors.LedgerAttemptOutOfOrder, errors.GateError)

def test_gates_logging_event_constants_present():
    from codegenie.gates import logging as gates_log
    for n in (
        "EVT_GATE_RUN_STARTED",
        "EVT_GATE_ATTEMPT_STARTED",
        "EVT_GATE_ATTEMPT_COMPLETED",
        "EVT_PRE_EXECUTE_MARKER_WRITTEN",
        "EVT_GATE_ATTEMPTS_OVERRIDE",
    ):
        v = getattr(gates_log, n)
        assert isinstance(v, str) and v
```

Run, confirm each fails (`ModuleNotFoundError` first, then `AttributeError` on members), commit, then implement.

### Green — make it pass

Create the two `__init__.py` files (empty modules). Define `SandboxError(Exception)` and the subclasses in `errors.py`; define `GateError(Exception)` similarly. Populate the two `logging.py` modules with `Final[str]` constants whose values are the exact event names used downstream (e.g., `"sandbox.execute.started"`, `"gate.attempts.override"`). Do not implement any behavior beyond name definitions.

### Refactor — clean up

- Add module-level docstrings on `errors.py` and `logging.py` (single sentence each).
- Add `__all__` lists in both `logging.py` modules so `from codegenie.sandbox.logging import *` is explicit.
- Type hint each constant as `typing.Final[str]`.
- Confirm `ruff format`/`ruff check`/`mypy --strict` clean.
- ADR-0008 rule compliance: no `anthropic` / `langgraph` / `chromadb` / `sentence_transformers` import (the formal fence is S1-07; this story owns "don't introduce one in the scaffold").

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/__init__.py` | New file — package root for sandbox seam per ADR-0001 |
| `src/codegenie/sandbox/errors.py` | New file — error hierarchy referenced by every later sandbox story |
| `src/codegenie/sandbox/logging.py` | New file — event-name constants imported across phase per arch §Harness engineering |
| `src/codegenie/gates/__init__.py` | New file — package root for gate seam per ADR-0006 |
| `src/codegenie/gates/errors.py` | New file — error hierarchy referenced by `RetryLedger`, `GateRunner` |
| `src/codegenie/gates/logging.py` | New file — gate event-name constants |
| `tests/sandbox/__init__.py` | New file — make `tests/sandbox/` a package |
| `tests/gates/__init__.py` | New file — make `tests/gates/` a package |
| `tests/sandbox/test_scaffold.py` | New test — TDD red for package + errors + logging |
| `tests/gates/test_scaffold.py` | New test — TDD red for gates package |

## Out of scope

- **`SandboxClient` Protocol + models** — handled by story S1-02.
- **`ObjectiveSignals` sub-models** — handled by S1-03.
- **`Gate` ABC and `GateContext`** — handled by S1-04.
- **Decorator registries (`@register_sandbox_backend`, `@register_signal_kind`)** — handled by S1-05.
- **The formal AST fence tests** — handled by S1-07; here we only avoid introducing banned imports.
- **`structlog` BoundLogger configuration** — only the *constants* are introduced; wiring lands wherever the first emitter does (likely S2-01 `RetryLedger`).

## Notes for the implementer

- Use `from typing import Final` and annotate every event-name constant. This is what makes `mypy --strict` happy and what later AST checks rely on.
- Event-name string values should be dotted lowercase (`"gate.run.started"`, not `"GATE_RUN_STARTED"`). Search `phase-arch-design.md` for `audit event` / `INFO` / `WARNING` strings — there are concrete names like `prompt_injection.detected`, `sandbox.egress.blocked`, `gate.attempts_override`. Reuse those exactly.
- Do not add `__init__.py` exports that re-export error classes — keep imports explicit (`from codegenie.sandbox.errors import ...`); flat namespaces grow into cycles fast.
- `SandboxError` and `GateError` should each inherit from `Exception` (not `BaseException`). Do not give them custom `__init__` signatures; later stories may want to attach structured fields and a uniform shape is easier to extend.
- Cross-reference every event-name constant you add against ADR text: ADR-0007 references the pre-execute marker (`EVT_PRE_EXECUTE_MARKER_WRITTEN`), ADR-0012 references the postinstall-exfil audit event (`EVT_SANDBOX_EGRESS_BLOCKED`). If you add a constant ADR text doesn't motivate, remove it — S1-01 is scaffolding, not API speculation.
- Keep this story tight. Each file should be < 80 lines.
