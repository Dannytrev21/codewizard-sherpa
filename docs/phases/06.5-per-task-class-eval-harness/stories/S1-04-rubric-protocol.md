# Story S1-04 — Rubric Protocol

**Step:** Step 1 — Establish contracts: package scaffold, wire models, registry, Protocol
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-02 (wire models — `BenchCase`, `BenchScore`)
**ADRs honored:** ADR-0001 (subprocess invocation is the runner's call site; in-process is the bench-author-test-only call site), Phase 5 ADR-0006 (Protocol vs ABC convention — structural Protocol, no shared behavior)

## Validation notes

Validated 2026-05-26 by `phase-story-validator` — verdict: **HARDENED**. Full report at `_validation/S1-04-rubric-protocol.md`. Key changes:

- **AC-6 was factually wrong and would have failed the green step.** The original AC asserted `Rubric.__abstractmethods__ == frozenset({"score"})` "only by virtue of Protocol semantics" — but a vanilla `@runtime_checkable Protocol` body does **NOT** populate `__abstractmethods__` in Python 3.11+; that frozenset is `frozenset()`. The only way to populate it is to add `@abstractmethod` — which the same AC forbids. Replaced with AC-6a/b/c (`typing._get_protocol_attrs` canonical; AST no-`@abstractmethod`; `dir()`-filter belt). Empirically verified against Python 3.13.
- **Signature shape is now introspected, not just annotated** (AC-3a + AC-3b). A regression renaming `case` → `c` or `harness_output` → `output` would silently break the subprocess JSON-to-kwargs unpacking that ADR-0001 depends on; mypy alone doesn't catch parameter-name drift across modules that share the Protocol.
- **Protocol's runtime-isinstance limitation is pinned as specification-by-example** (AC-10 + AC-10a). `isinstance(obj, Rubric)` checks **attribute names only** — a class with `def score(self): pass` (wrong signature) or `score = 42` (non-callable) passes the gate. Tests document the limitation as deliberate-per-ADR-0001, not a bug to "fix" with a runtime signature check.
- **Module-shape conventions enforced as observable contracts** (AC-12/13/14): `__all__ = ["Rubric"]`, `from __future__ import annotations`, module docstring cites both ADRs. Mirrors sibling Protocol-port files (`vuln_index/protocol.py`, `fallback/leaf/port.py`).
- **`Depends on:` corrected** from `—` to `S1-02 (wire models)` — the story's `_ok_score()` helper constructs a `BenchScore`, so S1-02 must be GREEN before S1-04's red marker can be reached.
- **Notes for implementer** expanded with: ADR-0001 footgun discipline (don't expect runtime isinstance to catch signature mismatches); sibling Protocol-port file:line references; explicit push-back on adding a runtime `isinstance(rubric, Rubric)` guard at S1-03's registration site (ADR-0001 binding — mypy is the structural enforcer); deferred extract trigger for a `port_base.py` kernel; AST-introspection as a structural-defense pattern.

## Context

The `Rubric` Protocol is the per-task-class scoring contract: one method, `score(case, harness_output) -> BenchScore`. The runner *never* imports a rubric module — ADR-0001 mandates subprocess invocation across a process boundary. The Protocol exists primarily so bench-author unit tests (`bench/<tc>/tests/test_rubric_unit.py`) can type-check the in-process call, and so the registry's `TaskClass.rubric_class: type[Rubric]` field carries a non-vacuous static-type relationship for mypy `--strict`. Phase 5 ADR-0006 chose `Protocol` over `ABC` for cases where there is no shared default behavior across implementations; rubrics are the textbook fit (every rubric is task-class-specific; nothing is shared).

This story is tiny on the surface (one file, ~20 LOC) but load-bearing: it is what makes the `@register_task_class` decorator's `type[Rubric]` annotation meaningful, and what S1-03's tests use to declare their stub rubric classes. The empirically-correct Python 3.11+ Protocol semantics (verified during validation) drive the test discipline — see `_validation/S1-04-rubric-protocol.md` for the verification transcript.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design → src/codegenie/eval/rubric.py` — full module contract; `@runtime_checkable` Protocol, single `score` method, two call sites (in-process for bench-author tests; subprocess for runner).
  - `../phase-arch-design.md §Agentic best practices — Tool-use safety` — the Protocol exists *because* the runner does not type-check across the subprocess boundary; bench-author unit tests are the trusted typed surface.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — "The `Rubric` Protocol exists primarily so bench-author unit tests can type-check (the runner does not type-check the subprocess — there is no static type relationship across the process boundary)."
- **Production / cross-phase precedent:**
  - `../../05-sandbox-trust-gates/ADRs/0006-protocol-vs-abc-convention.md` — Phase 5 chose Protocol where there is no shared default behavior across implementations. Rubrics meet that criterion (every task class has its own).
- **Sibling Protocol-port files in this repo (the codebase convention to mirror):**
  - `src/codegenie/vuln_index/protocol.py` — `Feed` Protocol; `@runtime_checkable`, one logical port, `__all__`, module docstring citing the Phase-3 ADR that justifies the seam, `from __future__ import annotations`.
  - `src/codegenie/fallback/leaf/port.py` — `LeafLlmPort`; cross-process-boundary precedent (Protocol surface vs subprocess wire — same asymmetry as Rubric).
- **This phase, parallel stories:**
  - S1-02 — `BenchScore`, `BenchCase` types this Protocol references (**dependency: S1-02 must be GREEN first**).
  - S1-03 — `TaskClass.rubric_class: type[Rubric]` annotation depends on this story landing.

## Goal

Land `src/codegenie/eval/rubric.py` exposing a `@runtime_checkable` `Rubric(Protocol)` with one method, `score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore`, plus the module-shape conventions (`from __future__ import annotations`, `__all__ = ["Rubric"]`, module docstring citing ADR-0001 and Phase 5 ADR-0006); plus a unit test suite asserting Protocol semantics (canonical declared-attrs, signature introspection, structural conformance, runtime-isinstance specification-by-example, module-shape conventions, direct-instantiation defense).

## Acceptance criteria

- [ ] **AC-1:** `src/codegenie/eval/rubric.py` exists; `from codegenie.eval.rubric import Rubric` succeeds.
- [ ] **AC-2:** `Rubric` is decorated `@runtime_checkable` and inherits from `typing.Protocol` (Python 3.11+). Verified by `Rubric._is_runtime_protocol is True` and `Rubric._is_protocol is True`.
- [ ] **AC-3:** `Rubric` declares exactly one method: `def score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore: ...` — body is `...` (no implementation; Protocol semantics).
- [ ] **AC-3a:** `inspect.signature(Rubric.score).parameters` keys equal `("self", "case", "harness_output")` *exactly* (introspected, not annotated); arity (excluding `self`) is 2.
- [ ] **AC-3b:** `typing.get_type_hints(Rubric.score, globalns=vars(codegenie.eval.rubric))` resolves `case → BenchCase`, `harness_output → collections.abc.Mapping[str, typing.Any]`, return → `BenchScore` *exactly* (not `dict[str, Any]`, not any structural-supertype).
- [ ] **AC-4:** A duck-typed class with a `score(self, case, harness_output) -> BenchScore` method passes `isinstance(instance, Rubric)` at runtime.
- [ ] **AC-5:** A class missing `score` (a typo'd `evaluate` for example) fails `isinstance(instance, Rubric)` at runtime — the Protocol catches the missing-attribute case.
- [ ] **AC-6a:** `typing._get_protocol_attrs(Rubric) == frozenset({"score"})` — the canonical Protocol-internals introspection pins exactly one declared attribute.
- [ ] **AC-6b:** AST inspection of `src/codegenie/eval/rubric.py` proves (i) no `from abc import abstractmethod` (or equivalent) import, (ii) no `@abstractmethod` decorator on the `score` method. The Protocol does not mix `@abstractmethod` per Phase 5 ADR-0006.
- [ ] **AC-6c:** Belt-and-suspenders structural smoke: `{name for name in dir(Rubric) if not name.startswith("_") and callable(getattr(Rubric, name, None))} == {"score"}`. This test passes today *and* would catch a future Protocol-internals leak (e.g., a public name added to `typing.Protocol` in a Python upgrade).
- [ ] **AC-7:** mypy `--strict` is clean: a stub class that implements `score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore` type-checks as `Rubric` *without* explicit inheritance (structural subtyping).
- [ ] **AC-8:** The red tests from §TDD plan exist, were committed at the red marker, and are now green.
- [ ] **AC-9:** `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/test_rubric_protocol.py` all pass.
- [ ] **AC-10:** A class with a *wrong-signature* `score` (e.g., `def score(self): pass` — zero positional params beyond self) **passes** `isinstance(instance, Rubric)`. This is **deliberate** per ADR-0001 — runtime Protocol isinstance checks attribute names, not signatures; mypy `--strict` is the structural enforcer. Test docstring names the rationale.
- [ ] **AC-10a:** A class with a *non-callable* `score` attribute (e.g., `score = 42`) **passes** `isinstance(instance, Rubric)`. Same rationale as AC-10 — deliberate, not a bug to "fix" with a runtime callable-check.
- [ ] **AC-11:** Direct instantiation `Rubric()` raises `TypeError`; the exception message contains the substring `"Protocol"` (not `"abstract"`). A regression refactoring `Rubric` from `Protocol` to `ABC` would raise `TypeError("Can't instantiate abstract class Rubric...")` instead — this AC catches that mutation.
- [ ] **AC-12:** Module exports exactly `__all__ = ["Rubric"]` — pinned by attribute introspection on the imported module (`from codegenie.eval import rubric; assert tuple(rubric.__all__) == ("Rubric",)`).
- [ ] **AC-13:** AST inspection finds `from __future__ import annotations` in `rubric.py`'s import block — codebase convention for Protocol-port files (cf. `vuln_index/protocol.py:17`, `fallback/leaf/port.py`).
- [ ] **AC-14:** Module docstring (parsed via `ast.get_docstring`) cites both `ADR-0001` and `ADR-0006` literally (substring presence is sufficient — the goal is rationale traceability, not prose form).

## Implementation outline

1. Write `tests/unit/test_rubric_protocol.py` first (red — 12 tests, see §TDD plan); confirm `ModuleNotFoundError` for `codegenie.eval.rubric`.
2. Create `src/codegenie/eval/rubric.py`:
   - **First line:** `"""<module docstring>"""` — naming `../phase-arch-design.md §Component design → rubric.py`, `ADR-0001` (subprocess isolation rationale), and `Phase 5 ADR-0006` (Protocol vs ABC convention). Cite the two sibling Protocol-port files (`vuln_index/protocol.py`, `fallback/leaf/port.py`) as the codebase convention being mirrored.
   - **Second:** `from __future__ import annotations` (codebase convention; supports forward references and PEP 604 syntax).
   - Imports: `from collections.abc import Mapping`, `from typing import Any, Protocol, runtime_checkable`, `from codegenie.eval.models import BenchCase, BenchScore`.
   - `__all__ = ["Rubric"]`.
   - `@runtime_checkable class Rubric(Protocol):` with one `def score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore: ...`.
   - One-line class docstring naming the two call sites (bench-author tests in-process; runner via subprocess per ADR-0001).
3. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest tests/unit/test_rubric_protocol.py`.
4. Verify AC-14 by reading the docstring's literal text contains both `"ADR-0001"` and `"ADR-0006"`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_rubric_protocol.py`

```python
# tests/unit/test_rubric_protocol.py
"""Protocol-shape contracts for codegenie.eval.rubric.Rubric.

Empirically grounded against Python 3.11+ typing semantics. Tests pin
both the structural conformance (happy path + obvious-typo negative)
AND the deliberate language limitations (runtime isinstance is name-only,
not signature-checking — per ADR-0001's two-call-site asymmetry).
"""
from __future__ import annotations

import ast
import importlib
import inspect
import typing
from collections.abc import Mapping
from typing import Any, get_type_hints

import pytest
from pydantic import ValidationError

from codegenie.eval.models import BenchCase, BenchScore
from codegenie.eval import rubric as rubric_mod
from codegenie.eval.rubric import Rubric


def _ok_score() -> BenchScore:
    """Construct a minimal valid BenchScore. Routes S1-02-drift failures to S1-02."""
    try:
        return BenchScore(
            passed=True, score=0.5, breakdown={},
            failure_modes=(), cost_usd=0.0, wall_clock_ms=0,
        )
    except ValidationError as exc:  # pragma: no cover
        pytest.skip(f"S1-02 BenchScore field-set drift; resolve in S1-02: {exc}")


# ---------------------------------------------------------------------------
# Structural conformers used by isinstance tests
# ---------------------------------------------------------------------------
class _DuckTypedRubric:
    """No inheritance from Rubric — structural conformance only."""
    def score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore:
        return _ok_score()


class _MissingScore:
    """Lacks .score — should fail isinstance(..., Rubric)."""
    def evaluate(self, case, harness_output):  # type: ignore[no-untyped-def]
        return _ok_score()


class _WrongSignatureScore:
    """Has `score` but wrong arity. AC-10: isinstance() passes deliberately."""
    def score(self):  # type: ignore[no-untyped-def]
        return None


class _NonCallableScore:
    """Has `score` but it's a non-callable int. AC-10a: isinstance() passes deliberately."""
    score = 42


# ---------------------------------------------------------------------------
# AC-4 / AC-5 — original obvious-conformer + obvious-typo coverage
# ---------------------------------------------------------------------------
def test_rubric_is_a_runtime_checkable_protocol() -> None:
    """AC-4: duck-typed conformer satisfies isinstance."""
    assert isinstance(_DuckTypedRubric(), Rubric)


def test_class_missing_score_fails_isinstance() -> None:
    """AC-5: a class with a typo'd method name does not silently satisfy the contract."""
    assert not isinstance(_MissingScore(), Rubric)


# ---------------------------------------------------------------------------
# AC-2 — runtime_checkable + Protocol markers (positive introspection,
#         no try/except; mutation-resistant)
# ---------------------------------------------------------------------------
def test_runtime_checkable_marker_is_set() -> None:
    """AC-2: @runtime_checkable sets the canonical typing-internal flag."""
    assert getattr(Rubric, "_is_runtime_protocol", False) is True
    assert getattr(Rubric, "_is_protocol", False) is True


def test_runtime_isinstance_returns_false_for_unconformant_object() -> None:
    """AC-2: complement — a bare object() doesn't have score, must return False
    (not raise — that'd indicate @runtime_checkable was dropped)."""
    assert isinstance(object(), Rubric) is False


# ---------------------------------------------------------------------------
# AC-3a / AC-3b — signature introspection (the wire contract per ADR-0001)
# ---------------------------------------------------------------------------
def test_score_signature_parameter_names_and_arity() -> None:
    """AC-3a: parameter names AND arity are the wire contract — subprocess
    JSON-to-kwargs unpacking depends on these names (ADR-0001). A rename
    `case`→`c` is mypy-clean for any new call site but silently breaks
    every existing keyword call."""
    sig = inspect.signature(Rubric.score)
    assert tuple(sig.parameters.keys()) == ("self", "case", "harness_output")
    # Arity excluding self is 2.
    assert len(sig.parameters) - 1 == 2


def test_score_annotation_types() -> None:
    """AC-3b: return annotation is BenchScore exactly (not dict[str, Any], not
    any structural-supertype). Forward refs resolved via the module's globalns."""
    hints = get_type_hints(Rubric.score, globalns=vars(rubric_mod))
    assert hints["case"] is BenchCase
    # Mapping[str, Any] — origin Mapping, args (str, Any).
    assert typing.get_origin(hints["harness_output"]) is Mapping
    assert typing.get_args(hints["harness_output"]) == (str, Any)
    assert hints["return"] is BenchScore


# ---------------------------------------------------------------------------
# AC-6a / AC-6b / AC-6c — Protocol declared-attrs triad
# ---------------------------------------------------------------------------
def test_protocol_attrs_canonical() -> None:
    """AC-6a: typing._get_protocol_attrs is the canonical declared-attrs API.
    Returns exactly {'score'} for a Protocol with one method body."""
    # _get_protocol_attrs is a private but stable typing helper since 3.8.
    get_attrs = typing._get_protocol_attrs  # type: ignore[attr-defined]
    assert get_attrs(Rubric) == frozenset({"score"})


def test_ast_proves_no_abstractmethod_decorator_or_import() -> None:
    """AC-6b: Protocol vs ABC convention (Phase 5 ADR-0006). The Protocol
    body must use bare `...`; no `@abstractmethod`, no `from abc import
    abstractmethod`. AST inspection is the structural-defense pattern
    (mirrors tests/fence/ discipline)."""
    src = (importlib.resources.files("codegenie.eval") / "rubric.py").read_text()
    tree = ast.parse(src)

    # No `from abc import ... abstractmethod ...`
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "abc":
            names = {alias.name for alias in node.names}
            assert "abstractmethod" not in names, "ADR-0006: Protocol must not mix @abstractmethod"

    # The Rubric class's `score` method has no @abstractmethod decorator.
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Rubric":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "score":
                    for dec in item.decorator_list:
                        # Either Name("abstractmethod") or Attribute(attr="abstractmethod")
                        attr = getattr(dec, "attr", getattr(dec, "id", ""))
                        assert attr != "abstractmethod", (
                            "ADR-0006: Protocol must not mix @abstractmethod"
                        )


def test_dir_filter_belt_and_suspenders() -> None:
    """AC-6c: structural smoke — exactly one public callable named 'score'.
    Catches a future Protocol-internals leak (e.g., a new public name
    surfaced on typing.Protocol in a Python upgrade)."""
    members = {
        name for name in dir(Rubric)
        if not name.startswith("_") and callable(getattr(Rubric, name, None))
    }
    assert members == {"score"}


# ---------------------------------------------------------------------------
# AC-10 / AC-10a — Protocol-isinstance footgun, specification-by-example
# ---------------------------------------------------------------------------
def test_isinstance_passes_for_wrong_signature_score_method() -> None:
    """AC-10: DELIBERATE per ADR-0001. Runtime Protocol isinstance checks
    attribute NAMES, not signatures. mypy --strict is the structural
    enforcer; the runtime check is name-presence only. A future contributor
    must NOT add a runtime signature guard expecting tighter semantics —
    that would be a category error per the two-call-site asymmetry."""
    assert isinstance(_WrongSignatureScore(), Rubric) is True


def test_isinstance_passes_for_non_callable_score_attribute() -> None:
    """AC-10a: DELIBERATE per ADR-0001. Runtime Protocol isinstance does
    not even require the attribute to be callable — name presence is the
    only check. mypy is the structural enforcer at type-check time."""
    assert isinstance(_NonCallableScore(), Rubric) is True


# ---------------------------------------------------------------------------
# AC-11 — direct instantiation defense
# ---------------------------------------------------------------------------
def test_rubric_cannot_be_instantiated() -> None:
    """AC-11: Rubric() raises TypeError with 'Protocol' in the message.
    A regression refactoring Protocol→ABC would still raise TypeError but
    with 'abstract' in the message — this assertion catches that mutation."""
    with pytest.raises(TypeError) as excinfo:
        Rubric()  # type: ignore[abstract]
    assert "Protocol" in str(excinfo.value), (
        f"Expected 'Protocol' in error; got: {excinfo.value!r}. "
        f"Did Rubric get refactored from Protocol to ABC?"
    )


# ---------------------------------------------------------------------------
# AC-12 / AC-13 / AC-14 — module-shape conventions
# ---------------------------------------------------------------------------
def test_module_exports_only_rubric() -> None:
    """AC-12: __all__ is the public-surface contract. Adding a 2nd export
    requires an ADR amendment, not a silent edit."""
    assert tuple(rubric_mod.__all__) == ("Rubric",)


def test_future_annotations_imported() -> None:
    """AC-13: codebase convention for Protocol-port files (cf.
    vuln_index/protocol.py, fallback/leaf/port.py)."""
    src = (importlib.resources.files("codegenie.eval") / "rubric.py").read_text()
    tree = ast.parse(src)
    has_future = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in ast.walk(tree)
    )
    assert has_future, "rubric.py must `from __future__ import annotations`"


def test_module_docstring_cites_both_adrs() -> None:
    """AC-14: rationale traceability — the module docstring must name
    ADR-0001 and ADR-0006 so a future reader sees the why."""
    src = (importlib.resources.files("codegenie.eval") / "rubric.py").read_text()
    docstring = ast.get_docstring(ast.parse(src)) or ""
    assert "ADR-0001" in docstring, "Module docstring must cite ADR-0001"
    assert "ADR-0006" in docstring, "Module docstring must cite Phase 5 ADR-0006"
```

Run; confirm `ModuleNotFoundError`. Commit the red marker.

### Green — make it pass

```python
# src/codegenie/eval/rubric.py
"""Rubric Protocol — the per-task-class scoring contract (one method, two call sites).

The Protocol exists primarily so bench-author unit tests
(`bench/{task-class}/tests/test_rubric_unit.py`) can type-check the in-process
call to `score()`. The eval runner NEVER imports a rubric module — per
ADR-0001 (rubric-execution-isolation-via-subprocess), invocation is across a
process boundary via `python bench/{task-class}/rubric.py` with scrubbed env.
There is no static type relationship across the subprocess; the Protocol is
a typing aid for the trusted in-process surface only.

Phase 5 ADR-0006 (Protocol vs ABC convention) chose Protocol over ABC where
no shared default behavior exists across implementations — every rubric is
task-class-specific; nothing is shared. The pattern mirrors sibling
Protocol-port files: `codegenie.vuln_index.protocol.Feed`,
`codegenie.fallback.leaf.port.LeafLlmPort`.

See `docs/phases/06.5-per-task-class-eval-harness/phase-arch-design.md`
§Component design → rubric.py for the full contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from codegenie.eval.models import BenchCase, BenchScore

__all__ = ["Rubric"]


@runtime_checkable
class Rubric(Protocol):
    """Score one bench case's harness output. In-process (bench-author tests)
    or subprocess (runner) per ADR-0001's two-call-site asymmetry."""

    def score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore: ...
```

Nothing else.

### Refactor — clean up

- Module docstring cites the two ADRs (`ADR-0001` for "why subprocess, not in-process — the Protocol is a typing aid, not a runtime contract for the runner") and `Phase 5 ADR-0006` (Protocol vs ABC). Already required by AC-14.
- One-line class docstring on `Rubric` naming the two call sites (bench-author tests in-process; runner via subprocess).
- Confirm mypy `--strict` resolves `BenchCase` and `BenchScore` without forward references; `from __future__ import annotations` is already present per AC-13.
- No `score` body even as `pass` — Protocol convention is `...` literal as the method body, which signals "this is an abstract method-spec, not a default implementation." (AC-6b's AST check forbids `@abstractmethod`; the test does not constrain `...` vs `pass`, but the convention is documented here and in the sibling Protocol-port files.)
- The AST-introspectable shape (`__all__`, `from __future__ import annotations`, module docstring citing ADRs) is enforced *by tests in this story*, not by review-only convention. Drift would surface as a CI failure.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/rubric.py` | New file — `@runtime_checkable class Rubric(Protocol)` with one `score` method + module-shape conventions |
| `tests/unit/test_rubric_protocol.py` | New file — 12 tests covering AC-1..AC-14 (structural conformance, signature introspection, runtime-Protocol-limitation specification, module-shape conventions, direct-instantiation defense) |

## Out of scope

- **`type[Rubric]` annotation on `TaskClass.rubric_class`** — handled by S1-03 (this story provides the type; the registry uses it).
- **`isinstance(rubric, Rubric)` runtime check at registration time** — explicitly **forbidden** per ADR-0001. mypy `--strict` is the structural enforcer at type-check time; adding a runtime guard at the S1-03 registry would be a category error (the registration site is already-compiled code; the rubric class is the source the registration site names; mypy has already validated). If a reviewer or executor proposes such a guard during S1-03, push back with this paragraph. The only `isinstance(..., Rubric)` calls in production code paths live in *this story's tests*, nowhere else.
- **Subprocess invocation of `python rubric.py`** — handled by S3-03 (the runner spawns the subprocess; the Protocol does not).
- **Bench-author unit-test scaffolding (`bench/<tc>/tests/test_rubric_unit.py`)** — handled by S5-02 (vuln-remediation) and S6-01 (distroless); this story only provides the type bench-author tests import.
- **Adding `@abstractmethod` to `score`** — explicitly out of scope. Protocols use `...` body; mixing `@abstractmethod` is a category error per Phase 5 ADR-0006 and would invalidate the structural-typing intent. AC-6b enforces this via AST.
- **Extracting a shared `port_base.py` kernel** for the three Protocol-port files (`Feed`, `LeafLlmPort`, `Rubric`) — YAGNI. Each port is task-domain-specific; the shared invariants (`@runtime_checkable`, `__all__`, docstring ADRs) are Python-language conventions, not domain-relevant ones. Defer; revisit only if a 5th Protocol-port lands and the discipline drifts.
- **A `TaskClassName` / `RubricName` newtype** — not applicable here (this Protocol exposes no identifier surface). The deferral is tracked in `_validation/S1-03-taskclass-dataclass-and-registry.md` for the `TaskClass.name` consolidation surface.

## Notes for the implementer

- Resist the urge to add methods. The Protocol has *one* method. Phase 7 will be tempted to add a `prepare(case)` hook or a `cleanup()` hook; both belong in the subprocess `if __name__ == "__main__":` entrypoint, not in the Protocol surface. Widening the Protocol forces every existing bench-author rubric (vuln-remediation, distroless) to update — exactly the anti-pattern the open-registry design avoids.

- The Protocol body must be `...`, not `pass`, not `raise NotImplementedError`. The first two are equivalent at runtime; `...` is the convention that signals "this is a method specification" to readers (and to mypy's structural-subtyping engine).

- `@runtime_checkable` is load-bearing for the `isinstance(..., Rubric)` calls in the *tests* (and only there). Without it, `isinstance` raises `TypeError`. The test `test_runtime_checkable_marker_is_set` is the structural marker — if a future refactor drops the decorator, the test catches it.

- **Empirically-grounded Protocol semantics (verified during validation 2026-05-26 on Python 3.13):**
  - `Rubric.__abstractmethods__` is `frozenset()` for a vanilla `@runtime_checkable Protocol`; it is **not** automatically populated with method names. Earlier drafts of this story claimed otherwise and would have had a failing test. Use `typing._get_protocol_attrs(Rubric)` for the canonical declared-attrs introspection (returns `frozenset({"score"})`).
  - Runtime `isinstance(obj, Rubric)` checks **attribute names only** — not signatures, not callability. A class with `def score(self): ...` (wrong arity) or `score = 42` (non-callable) passes the gate. AC-10/AC-10a pin this as **deliberate per ADR-0001**, not a bug. mypy `--strict` is the structural enforcer; runtime Protocol is the name-presence gate.
  - `Rubric()` raises `TypeError("Protocols cannot be instantiated")`. A regression to ABC would raise `TypeError("Can't instantiate abstract class ...")`. AC-11 distinguishes the two via the `"Protocol"` substring.

- The Protocol's method signature **must match the subprocess JSON contract**. The runner spawns `python rubric.py` and passes JSON-serialized `case` + `harness_output` on stdin; the subprocess deserializes, calls `score(case, harness_output)` *internally* on its own rubric instance, and writes the `BenchScore` JSON to stdout. The Protocol describes the in-process surface; the *wire* contract (S5-02 and S6-01 will implement the rubric subprocess entrypoint) matches it by construction. **The parameter names `case` and `harness_output` are part of the wire contract** — bench-author tests use them as kwargs; runner-side JSON unpacking uses them as kwargs. A rename is not a refactor; it is a breaking change. AC-3a is the introspection guard.

- The two call sites — bench-author tests (in-process, typed, `isinstance`-checked) vs runner (subprocess, untyped across the process boundary) — is the asymmetry ADR-0001 calls out as deliberate. Do not try to "harmonize" them with a wrapper class; the asymmetry is the security posture.

- `tests/unit/test_rubric_protocol.py` is the only place `isinstance(..., Rubric)` is called in production code paths. The registry (S1-03) does not call it. If a reviewer asks "why doesn't the registry verify the decorated class is a `Rubric`?" — the answer is: mypy `--strict` already verifies it at type-check time; runtime `isinstance` adds nothing because the registration site (`@register_task_class`) takes a class and stores it; the only consumer is the bench-author test, which calls `isinstance` itself. **If S1-03's executor proposes adding such a guard, push back — ADR-0001 binding.**

- **Sibling Protocol-port lineage to mirror** (Rule 11 — match codebase conventions):
  - `src/codegenie/vuln_index/protocol.py:1-15` — module docstring discipline (ADRs honored, port purpose stated in the first sentence, `__all__` immediately after imports).
  - `src/codegenie/vuln_index/protocol.py:17` — `from __future__ import annotations` directly after the docstring.
  - `src/codegenie/fallback/leaf/port.py` — cross-process-boundary precedent; same asymmetry (typed in-process port + parallel subprocess wire) as Rubric. Use as the reference for the Rubric module's docstring.

- **AST-based negative checks as structural defense.** The tests use AST inspection to enforce three negative invariants (no `@abstractmethod`, no `from abc import abstractmethod`) and three positive invariants (`from __future__ import annotations`, `__all__ = ["Rubric"]`, module docstring cites both ADRs). This mirrors the `tests/fence/` discipline of enforcing structural defenses observably rather than by review-only convention. Convention without test enforcement drifts.

- The story envelope is ~20 LOC of production code (module docstring + imports + `__all__` + class + method stub) and ~150 LOC of tests (12 tests, several with rich docstrings naming ADR-0001 / Phase 5 ADR-0006 for the next reader). The asymmetry is intentional — the Protocol is small and load-bearing; the discipline must be enforced where it lives.

- **`Mapping[str, Any]` for `harness_output` — typed-at-the-edge** is the correct choice (not `BaseModel`, not `dict[str, Any]`). Each rubric internally narrows the mapping to its task-class-specific shape; the Protocol stays generic enough to support per-task-class diversity. `BaseModel` would couple every rubric to a phase-pinned schema; `dict[str, Any]` would lose `Mapping`'s read-only invariance.
