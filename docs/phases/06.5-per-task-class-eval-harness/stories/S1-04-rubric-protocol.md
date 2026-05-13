# Story S1-04 — Rubric Protocol

**Step:** Step 1 — Establish contracts: package scaffold, wire models, registry, Protocol
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0001 (subprocess invocation is the runner's call site; in-process is the bench-author-test-only call site), Phase 5 ADR-0006 (Protocol vs ABC convention — structural Protocol, no shared behavior)

## Context

The `Rubric` Protocol is the per-task-class scoring contract: one method, `score(case, harness_output) -> BenchScore`. The runner *never* imports a rubric module — ADR-0001 mandates subprocess invocation across a process boundary. The Protocol exists primarily so bench-author unit tests (`bench/<tc>/tests/test_rubric_unit.py`) can type-check the in-process call, and so the registry's `TaskClass.rubric_class: type[Rubric]` field carries a non-vacuous static-type relationship for mypy `--strict`. Phase 5 ADR-0006 chose `Protocol` over `ABC` for cases where there is no shared default behavior across implementations; rubrics are the textbook fit (every rubric is task-class-specific; nothing is shared).

This story is tiny on the surface (one file, ~15 LOC) but load-bearing: it is what makes the `@register_task_class` decorator's `type[Rubric]` annotation meaningful, and what S1-03's tests use to declare their stub rubric classes.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design → src/codegenie/eval/rubric.py` — full module contract; `@runtime_checkable` Protocol, single `score` method, two call sites (in-process for bench-author tests; subprocess for runner).
  - `../phase-arch-design.md §Agentic best practices — Tool-use safety` — the Protocol exists *because* the runner does not type-check across the subprocess boundary; bench-author unit tests are the trusted typed surface.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — "The `Rubric` Protocol exists primarily so bench-author unit tests can type-check (the runner does not type-check the subprocess — there is no static type relationship across the process boundary)."
- **Production / cross-phase precedent:**
  - `../../05-sandbox-trust-gates/ADRs/0006-protocol-vs-abc-convention.md` — Phase 5 chose Protocol where there is no shared default behavior across implementations. Rubrics meet that criterion (every task class has its own).
- **This phase, parallel stories:**
  - S1-02 — `BenchScore`, `BenchCase` types this Protocol references.
  - S1-03 — `TaskClass.rubric_class: type[Rubric]` annotation depends on this story landing.

## Goal

Land `src/codegenie/eval/rubric.py` exposing a `@runtime_checkable` `Rubric(Protocol)` with one method, `score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore`, and a unit test asserting Protocol semantics (structural conformance, runtime `isinstance`).

## Acceptance criteria

- [ ] `src/codegenie/eval/rubric.py` exists; `from codegenie.eval.rubric import Rubric` succeeds.
- [ ] `Rubric` is decorated `@runtime_checkable` and inherits from `typing.Protocol` (Python 3.11+).
- [ ] `Rubric` declares exactly one method: `def score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore: ...` — body is `...` (no implementation; Protocol semantics).
- [ ] A duck-typed class with a `score(case, harness_output) -> BenchScore` method passes `isinstance(instance, Rubric)` at runtime.
- [ ] A class missing `score` (or with a wrong-signature `score`) fails `isinstance(instance, Rubric)` at runtime — the Protocol catches the structural mismatch.
- [ ] The Protocol has no class attributes (`Rubric.__abstractmethods__ == frozenset({"score"})` *only* by virtue of Protocol semantics; no `@abstractmethod` decorator is added).
- [ ] mypy `--strict` is clean: a stub class that implements `score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore` type-checks as `Rubric` *without* explicit inheritance (structural subtyping).
- [ ] The red tests from §TDD plan exist, were committed at the red marker, and are now green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/test_rubric_protocol.py` all pass.

## Implementation outline

1. Write `tests/unit/test_rubric_protocol.py` first (red); confirm `ImportError`.
2. Create `src/codegenie/eval/rubric.py`:
   - Imports: `from collections.abc import Mapping`, `from typing import Any, Protocol, runtime_checkable`, `from codegenie.eval.models import BenchCase, BenchScore`.
   - Module docstring naming `../phase-arch-design.md §Component design → rubric.py` and `../ADRs/0001` as the why.
   - `@runtime_checkable class Rubric(Protocol):` with one `def score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore: ...`.
   - `__all__ = ["Rubric"]`.
3. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_rubric_protocol.py`

```python
# tests/unit/test_rubric_protocol.py
from collections.abc import Mapping
from typing import Any

import pytest

from codegenie.eval.models import BenchCase, BenchScore
from codegenie.eval.rubric import Rubric


def _ok_score() -> BenchScore:
    return BenchScore(
        passed=True, score=0.5, breakdown={},
        failure_modes=(), cost_usd=0.0, wall_clock_ms=0,
    )


class _DuckTypedRubric:
    """No inheritance from Rubric — structural conformance only."""
    def score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore:
        return _ok_score()


class _MissingScore:
    """Lacks .score — should fail isinstance(..., Rubric)."""
    def evaluate(self, case, harness_output):  # type: ignore[no-untyped-def]
        return _ok_score()


def test_rubric_is_a_runtime_checkable_protocol():
    # Protocol semantics: isinstance must work on duck-typed conformers.
    duck = _DuckTypedRubric()
    assert isinstance(duck, Rubric)


def test_class_missing_score_fails_isinstance():
    # Defense: a class with a typoed method name does not silently satisfy the contract.
    bad = _MissingScore()
    assert not isinstance(bad, Rubric)


def test_protocol_exposes_only_one_method_named_score():
    # The contract is exactly one method. Adding more without an ADR amendment
    # widens the bench-author burden silently.
    members = {name for name in dir(Rubric)
               if not name.startswith("_") and callable(getattr(Rubric, name, None))}
    assert members == {"score"}


def test_runtime_checkable_decorator_is_applied():
    # Without @runtime_checkable, isinstance() raises TypeError on Protocols.
    # We verify by attempting the isinstance call — it must not raise.
    try:
        isinstance(object(), Rubric)
    except TypeError as exc:  # pragma: no cover
        pytest.fail(f"Rubric is not @runtime_checkable: {exc}")
```

Run; confirm `ModuleNotFoundError`. Commit the red marker.

### Green — make it pass

```python
# src/codegenie/eval/rubric.py (approximate body, not the spec)
@runtime_checkable
class Rubric(Protocol):
    def score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore: ...
```

Nothing else.

### Refactor — clean up

- Module docstring cites the two ADRs (`ADR-0001` for "why subprocess, not in-process — the Protocol is a typing aid, not a runtime contract for the runner") and `Phase 5 ADR-0006` (Protocol vs ABC).
- One-line class docstring on `Rubric` naming the two call sites (bench-author tests in-process; runner via subprocess).
- Confirm mypy `--strict` resolves `BenchCase` and `BenchScore` without forward references; if not, add `from __future__ import annotations`.
- No `score` body even as `pass` — Protocol convention is `...` literal as the method body, which signals "this is an abstract method-spec, not a default implementation."

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/rubric.py` | New file — `@runtime_checkable class Rubric(Protocol)` with one `score` method |
| `tests/unit/test_rubric_protocol.py` | New file — structural conformance + missing-method rejection + single-method closure |

## Out of scope

- **`type[Rubric]` annotation on `TaskClass.rubric_class`** — handled by S1-03 (this story provides the type; the registry uses it).
- **`isinstance(rubric, Rubric)` runtime check at registration time** — `phase-arch-design.md §Component design → rubric.py` notes the check exists "only at the Protocol surface"; this means the *test* (`test_rubric_protocol.py` does `isinstance`), not the registry. The registry does **not** call `isinstance` because doing so couples it to a Protocol that only matters for bench-author tests.
- **Subprocess invocation of `python rubric.py`** — handled by S3-03 (the runner spawns the subprocess; the Protocol does not.).
- **Bench-author unit-test scaffolding (`bench/<tc>/tests/test_rubric_unit.py`)** — handled by S5-02 (vuln-remediation) and S6-01 (distroless); this story only provides the type bench-author tests import.
- **Adding `@abstractmethod` to `score`** — explicitly out of scope. Protocols use `...` body; mixing `@abstractmethod` is a category error per Phase 5 ADR-0006.

## Notes for the implementer

- Resist the urge to add methods. The Protocol has *one* method. Phase 7 will be tempted to add a `prepare(case)` hook or a `cleanup()` hook; both belong in the subprocess `if __name__ == "__main__":` entrypoint, not in the Protocol surface. Widening the Protocol forces every existing bench-author rubric (vuln-remediation, distroless) to update — exactly the anti-pattern the open-registry design avoids.
- The Protocol body must be `...`, not `pass`, not `raise NotImplementedError`. The first two are equivalent at runtime; `...` is the convention that signals "this is a method specification" to readers (and to mypy's structural-subtyping engine).
- `@runtime_checkable` is load-bearing for the `isinstance(..., Rubric)` calls in the *tests* (and only there). Without it, `isinstance` raises `TypeError`. The test `test_runtime_checkable_decorator_is_applied` is the structural marker — if a future refactor drops the decorator, the test catches it.
- The Protocol's method signature **must match the subprocess JSON contract**. The runner spawns `python rubric.py` and passes JSON-serialized `case` + `harness_output` on stdin; the subprocess deserializes, calls `score(case, harness_output)` *internally* on its own rubric instance, and writes the `BenchScore` JSON to stdout. The Protocol describes the in-process surface; the *wire* contract (S5-02 and S6-01 will implement the rubric subprocess entrypoint) matches it by construction.
- The two call sites — bench-author tests (in-process, typed, `isinstance`-checked) vs runner (subprocess, untyped across the process boundary) — is the asymmetry ADR-0001 calls out as deliberate. Do not try to "harmonize" them with a wrapper class; the asymmetry is the security posture.
- `tests/unit/test_rubric_protocol.py` is the only place `isinstance(..., Rubric)` is called in production code paths. The registry (S1-03) does not call it. If a reviewer asks "why doesn't the registry verify the decorated class is a `Rubric`?" — the answer is: mypy `--strict` already verifies it at type-check time; runtime `isinstance` adds nothing because the registration site (`@register_task_class`) takes a class and stores it; the only consumer is the bench-author test, which calls `isinstance` itself.
