# Story S1-01 — Scaffold `sandbox/` + `gates/` packages with errors and structlog event constants

**Step:** Step 1 — Scaffold packages, contracts, and CI fences
**Status:** Ready (HARDENED 2026-05-16)
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0001, ADR-0006, ADR-0008

## Validation notes (2026-05-16 — phase-story-validator)

This story was hardened in place after a four-critic pass. Verdict: **HARDENED**. Key edits, with severity tags:

- **(consistency / Rule 11) `EVT_*` → `EVENT_*` everywhere.** Phase 0 (`src/codegenie/logging.py`) and every existing consumer under `src/codegenie/probes/`, `src/codegenie/parsers/` already use the `EVENT_*` prefix (`EVENT_PROBE_START`, `EVENT_PROBE_PARSER_CAP_EXCEEDED`, etc.). The original draft introduced a parallel `EVT_*` prefix with no rationale — that's convention drift, not a deliberate departure. Renamed in ACs, TDD plan, and implementer notes. (Rule 11: "Match the codebase's conventions, even if you disagree.")
- **(coverage) Vague AC "every event name in arch has a constant" replaced with an exact, enumerated list of event constants → exact dotted-lowercase string values.** The arch text names `gate.run`, `gate.attempt`, `gate.attempts_override`, `sandbox.egress.blocked`, `prompt_injection.detected`, plus the pre-execute marker called out in ADR-0007. Pinning these by name + value is what makes the rename test possible; otherwise a future story can silently rename `"gate.run.started"` → `"gate.start"` and the structural test still passes.
- **(test-quality) Forbidden-import test rewritten as a subprocess + AST walk instead of `sys.modules` introspection.** The original test (`for banned in (...): assert banned not in sys.modules`) is unreliable inside pytest — another test in the session may have imported `anthropic` already, producing a false negative. The hardened test (a) walks every `.py` under `src/codegenie/sandbox/` and `src/codegenie/gates/` for top-level `Import` / `ImportFrom` AST nodes naming the banned modules, and (b) runs a fresh `python -c "import codegenie.sandbox; import sys; print([m for m in sys.modules if ...])"` subprocess to confirm transitive cleanliness. The formal AST fence ships in S1-07; this story owns its non-regression scaffold.
- **(coverage + test-quality) Promoted three behaviors from Refactor to AC level:** `Final[str]` annotation on every event constant; module-level `__all__` list in `logging.py`; error classes extend `Exception` (not `BaseException`) and have **no** custom `__init__` body. These were already in the Notes/Refactor sections but unobservable to the executor's Validator — the executor must see a runtime-verifiable AC, not a hidden refactor step.
- **(test-quality / mutation thinking) Added value-level assertions for event constants.** The original test asserted `isinstance(v, str)` and uniqueness, but did NOT pin the actual string values. A wrong implementation that emits `"gates.run.started"` (plural) or `"GATE_RUN_STARTED"` (uppercase) would still pass. The hardened test parametrizes `(constant_name, expected_dotted_lowercase_value)` pairs and asserts equality byte-for-byte — including the dotted-lowercase shape (regex `^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$`).
- **(test-quality) Added idempotent-import test.** AC-1 says "importing each at a fresh Python session succeeds with no side effects" but the original TDD plan only verified `mod is not None`. A new test asserts the same module object is returned on a second `importlib.import_module`, and that importing does not write to disk, stdout, or stderr.
- **(design-patterns / Open-Closed) Surfaced extension-by-addition in implementer notes.** Adding a new error subclass or event constant in a later story (S1-02 onwards) must NOT edit `SandboxError`/`GateError` or pre-existing constants — they extend by appending. The Notes section now states this explicitly; the AC level keeps observable-only criteria.
- **(consistency) `gates/logging.py` and `sandbox/logging.py` shadow the stdlib `logging` name.** Phase 0 already accepted this shape at the package root and uses `import logging as _stdlib_logging` inside the module. New AC requires the same idiom if either new module imports stdlib `logging`.
- **(coverage) Added an `error_message_does_not_leak_path` smoke** — every error class, when raised with an arbitrary message, reproduces the message verbatim with no extra side-channel; protects later stories that compose errors into structured logging.

No Stage-3 research was needed — every gap was answerable from Phase 0/1 codebase precedent (`src/codegenie/logging.py`, `src/codegenie/errors.py`) plus the existing ADRs. See `_validation/S1-01-scaffold-packages-errors-structlog.md` for the full audit log.

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

## Canonical event-name table (pinned values — string constants must equal these byte-for-byte)

This table is the contract. Every constant below must exist, must be typed `Final[str]`, must equal the exact dotted-lowercase value shown, and must be reachable through the module's `__all__`. Future stories add new constants below this table; they do **not** rename or re-value existing entries.

**`codegenie/sandbox/logging.py`**

| Constant | Value | Sourced from |
|---|---|---|
| `EVENT_SANDBOX_EXECUTE_STARTED` | `"sandbox.execute.started"` | `phase-arch-design.md §Harness engineering` |
| `EVENT_SANDBOX_EXECUTE_COMPLETED` | `"sandbox.execute.completed"` | `phase-arch-design.md §Harness engineering` |
| `EVENT_SANDBOX_EGRESS_BLOCKED` | `"sandbox.egress.blocked"` | `§Edge cases` row 5, `§Adversarial tests` test_postinstall_exfil |
| `EVENT_PROMPT_INJECTION_DETECTED` | `"prompt_injection.detected"` | `§Edge cases` row 16 |

**`codegenie/gates/logging.py`**

| Constant | Value | Sourced from |
|---|---|---|
| `EVENT_GATE_RUN_STARTED` | `"gate.run.started"` | `phase-arch-design.md §Tracing strategy` (`gate.run` span) |
| `EVENT_GATE_RUN_COMPLETED` | `"gate.run.completed"` | `§Tracing strategy` |
| `EVENT_GATE_ATTEMPT_STARTED` | `"gate.attempt.started"` | `§Tracing strategy` (`gate.attempt` span) |
| `EVENT_GATE_ATTEMPT_COMPLETED` | `"gate.attempt.completed"` | `§Tracing strategy` |
| `EVENT_GATE_ATTEMPTS_OVERRIDE` | `"gate.attempts_override"` | `§Decision points` + `§Edge cases` row 14 (CLI audit event) |
| `EVENT_PRE_EXECUTE_MARKER_WRITTEN` | `"gate.pre_execute.written"` | ADR-0007 + `phase-arch-design.md §Gap 1` improvement (`pre_execute` JSONL line) |

If a later story (S2-01 ledger, S5-01 replan hook, S6-02 firecracker network) needs a new event name, it adds a row below the existing entries — it does not rename, reorder, or re-value an existing row.

## Acceptance criteria

- [ ] **AC-1 (package roots).** `src/codegenie/sandbox/__init__.py` and `src/codegenie/gates/__init__.py` exist as plain modules (single-line module docstring only — no executable code, no re-exports). Importing each in a fresh Python session via `python -c "import codegenie.sandbox; import codegenie.gates"` succeeds with exit 0, writes nothing to stdout/stderr/disk, and does not touch any `sys.modules` entry whose name starts with `anthropic`, `langgraph`, `chromadb`, or `sentence_transformers`.
- [ ] **AC-1a (import idempotence).** A second `importlib.import_module("codegenie.sandbox")` in the same interpreter returns the **same** module object (identity, not equality); same for `codegenie.gates`. No side effects on repeat import.
- [ ] **AC-2 (sandbox error hierarchy).** `src/codegenie/sandbox/errors.py` defines `SandboxError` as a direct subclass of `Exception` (NOT `BaseException`), and every one of `SandboxBackendError`, `SandboxBackendInvalid`, `SandboxImageUnavailable`, `SandboxSpecForbidden`, `FirecrackerKvmMissing`, `FirecrackerBinaryMissing`, `FirecrackerRootfsMissing`, `RepoAlreadyInProgress`, `SignalKindAlreadyRegistered` is a direct subclass of `SandboxError`. Each class body is a single module docstring + `pass` (or just a docstring) — **no custom `__init__`, no class attributes, no `__str__` override**. The module exposes `__all__` listing all 10 names exactly.
- [ ] **AC-3 (gate error hierarchy).** `src/codegenie/gates/errors.py` defines `GateError` as a direct subclass of `Exception`, and `GateMissingRequiredSignal`, `GateCatalogInvalid`, `AuditChainCorrupted`, `LedgerAttemptOutOfOrder` as direct subclasses of `GateError`, same structural constraints as AC-2 (docstring only; no `__init__`; no attributes). `__all__` lists all 5 names.
- [ ] **AC-4 (event-name constants — names + types + values).** Every row in the **Canonical event-name table** above is present in the named module as a `Final[str]` annotated module-level constant with the exact value shown. Concretely:
  - `getattr(codegenie.sandbox.logging, name) == value` for each sandbox row.
  - `getattr(codegenie.gates.logging, name) == value` for each gate row.
  - `typing.get_type_hints(codegenie.sandbox.logging)[name]` resolves to `str` and the source-text annotation is `Final[str]` (verified by `ast.parse` on the source).
- [ ] **AC-4a (event-name string shape).** Every event-constant value matches the regex `^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$` (dotted lowercase, ≥ one dot, no uppercase, no leading digit). This is the established Phase 0 convention (`probe.start`, `gitignore.append.accepted`) and locks Rule 11 at the value level.
- [ ] **AC-4b (`__all__` discipline).** Both `logging.py` modules declare a sorted, complete `__all__` list — every event constant the module defines is exactly one element of `__all__`, and `__all__` contains no extra entries. `from codegenie.sandbox.logging import *` exposes exactly the constants in `__all__`.
- [ ] **AC-4c (no value collisions).** Across both `logging.py` modules, the set of constant *values* has the same cardinality as the set of constant *names* (no two constants map to the same string value, neither within a module nor across them).
- [ ] **AC-5 (stdlib-logging shadow safety).** Neither `sandbox/logging.py` nor `gates/logging.py` imports the stdlib `logging` module at top level under the bare name `logging`. If stdlib `logging` is needed, it is imported as `import logging as _stdlib_logging` (matches the existing `src/codegenie/logging.py` precedent). For S1-01 the simpler path is no stdlib-logging dependency at all; verified by AST walk.
- [ ] **AC-6 (no LLM/RAG dependencies anywhere under either package).** Static AST walk of every `*.py` file under `src/codegenie/sandbox/` and `src/codegenie/gates/` finds zero `Import` / `ImportFrom` nodes naming `anthropic`, `langgraph`, `chromadb`, `sentence_transformers`, or any submodule of those. Independently, a fresh subprocess (`python -c "import codegenie.sandbox; import codegenie.gates; import sys; ..."`) confirms none of those names appear in `sys.modules` after import. The formal CI fence lands in S1-07; this story owns its non-regression scaffold.
- [ ] **AC-7 (error messages are passthrough).** For every concrete error class in either package, `str(ErrCls("hello-world-42"))` returns exactly `"hello-world-42"` — no prefix, suffix, formatting, or side channel introduced by the class.
- [ ] **AC-8 (tooling).** `ruff check src/codegenie/sandbox src/codegenie/gates tests/sandbox tests/gates`, `ruff format --check` (same paths), and `mypy --strict src/codegenie/sandbox src/codegenie/gates` all exit 0. `pytest tests/sandbox/test_scaffold.py tests/gates/test_scaffold.py -q` exits 0.
- [ ] **AC-9 (TDD discipline).** The red test commit is in the git log before the green commit; both are committed. The red commit, when checked out and run, exits non-zero with `ModuleNotFoundError` / `AttributeError`. The green commit, when checked out and run, exits zero.

## Implementation outline

1. Create `src/codegenie/sandbox/__init__.py` (module docstring only — package name + one-sentence purpose pointing readers at `phase-arch-design.md §Component design`). No re-exports — keep the namespace flat per ADR-0006 Consequences and the Phase 0 / Phase 1 precedent (no chain importing from `__init__.py`).
2. Create `src/codegenie/gates/__init__.py` (same shape).
3. Create `src/codegenie/sandbox/errors.py` with the `SandboxError` hierarchy. Each class is a single docstring + `pass`. **No** custom `__init__` (not even `super().__init__()`), **no** class attributes, **no** `__str__` overrides — markers only, matching `src/codegenie/errors.py`'s Phase 0 shape verbatim. Declare a sorted `__all__` listing all 10 names.
4. Create `src/codegenie/gates/errors.py` with the `GateError` hierarchy (same structural rules). Declare `__all__` (5 names).
5. Create `src/codegenie/sandbox/logging.py` and `src/codegenie/gates/logging.py`. Each constant is annotated `Final[str]` and assigned the exact value from the **Canonical event-name table**. Declare a sorted `__all__` listing every constant. Module docstring cites the table by name. **Do NOT import stdlib `logging`** in either file — these modules are constants-only. (If a later story needs stdlib `logging`, it imports it as `import logging as _stdlib_logging` per the Phase 0 precedent in `src/codegenie/logging.py`.)
6. Add `tests/sandbox/__init__.py` and `tests/gates/__init__.py` (empty packages) plus `tests/sandbox/test_scaffold.py` and `tests/gates/test_scaffold.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/sandbox/test_scaffold.py`, `tests/gates/test_scaffold.py`.

Each test below names the AC it constrains. Tests are written so an obviously-wrong implementation (e.g., renaming a constant value, dropping `Final[str]`, giving an error class a custom `__init__`) fails at least one of them.

```python
# tests/sandbox/test_scaffold.py
"""Scaffold tests for codegenie.sandbox — verifies S1-01 ACs.

Every test docstring names the AC it covers. Mutation-resistance: an
implementation that drops `Final[str]`, renames a constant value, swaps
constant values between names, gives an error class a custom __init__,
adds a custom __str__, or pulls in any banned LLM/RAG import must fail at
least one of these tests.
"""

from __future__ import annotations

import ast
import importlib
import re
import subprocess
import sys
import typing
from pathlib import Path

import pytest

# --- canonical sources of truth from S1-01 -----------------------------------

# AC-4 — pinned values from the Canonical event-name table in S1-01.
EXPECTED_SANDBOX_EVENTS: dict[str, str] = {
    "EVENT_SANDBOX_EXECUTE_STARTED": "sandbox.execute.started",
    "EVENT_SANDBOX_EXECUTE_COMPLETED": "sandbox.execute.completed",
    "EVENT_SANDBOX_EGRESS_BLOCKED": "sandbox.egress.blocked",
    "EVENT_PROMPT_INJECTION_DETECTED": "prompt_injection.detected",
}

# AC-2 — pinned subclass list from S1-01.
EXPECTED_SANDBOX_ERRORS: tuple[str, ...] = (
    "SandboxBackendError",
    "SandboxBackendInvalid",
    "SandboxImageUnavailable",
    "SandboxSpecForbidden",
    "FirecrackerKvmMissing",
    "FirecrackerBinaryMissing",
    "FirecrackerRootfsMissing",
    "RepoAlreadyInProgress",
    "SignalKindAlreadyRegistered",
)

BANNED_TOP_LEVEL_MODULES: tuple[str, ...] = (
    "anthropic",
    "langgraph",
    "chromadb",
    "sentence_transformers",
)

# AC-4a — dotted lowercase, ≥ one dot, no uppercase, no leading digit.
EVENT_VALUE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


# --- AC-1, AC-1a -------------------------------------------------------------

def test_sandbox_package_imports_cleanly_and_is_side_effect_free():
    """AC-1: import succeeds with no stdout/stderr; AC-1a: idempotent."""
    result = subprocess.run(
        [sys.executable, "-c", "import codegenie.sandbox; print('OK')"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"
    assert result.stderr == ""


def test_sandbox_import_is_idempotent_same_object():
    """AC-1a: a second import returns the same module object (identity)."""
    a = importlib.import_module("codegenie.sandbox")
    b = importlib.import_module("codegenie.sandbox")
    assert a is b


# --- AC-2, AC-7 --------------------------------------------------------------

def test_sandbox_error_base_extends_exception_not_baseexception():
    """AC-2: SandboxError must be a direct Exception subclass."""
    from codegenie.sandbox import errors

    assert errors.SandboxError.__bases__ == (Exception,)


@pytest.mark.parametrize("name", EXPECTED_SANDBOX_ERRORS)
def test_each_sandbox_subclass_is_direct_child_of_sandbox_error(name: str):
    """AC-2: every named subclass is a *direct* child of SandboxError."""
    from codegenie.sandbox import errors

    cls = getattr(errors, name)
    assert cls.__bases__ == (errors.SandboxError,), (
        f"{name} must inherit directly from SandboxError, got {cls.__bases__}"
    )


@pytest.mark.parametrize("name", ("SandboxError",) + EXPECTED_SANDBOX_ERRORS)
def test_each_sandbox_error_class_is_marker_only(name: str):
    """AC-2: error classes are markers — no custom __init__, no __str__, no class attrs.

    Mutation target: an implementation that adds `def __init__(self, *a, **kw):`
    or `def __str__(self): return f"foo"` would let later code attach
    surprise state. We forbid both at the structural level.
    """
    from codegenie.sandbox import errors

    cls = getattr(errors, name)
    # Class body must not define its own __init__ or __str__ — they must
    # be inherited from Exception / SandboxError.
    own = set(vars(cls).keys()) - {"__module__", "__qualname__", "__doc__", "__dict__", "__weakref__"}
    assert own == set(), f"{name} must be a bare marker; unexpected members: {sorted(own)}"


@pytest.mark.parametrize("name", EXPECTED_SANDBOX_ERRORS)
def test_sandbox_error_message_is_passthrough(name: str):
    """AC-7: str(Err('x')) == 'x' — no prefix/suffix introduced by the class."""
    from codegenie.sandbox import errors

    cls = getattr(errors, name)
    assert str(cls("hello-world-42")) == "hello-world-42"


def test_sandbox_errors_all_list_is_exact():
    """AC-2: __all__ lists all 10 names exactly (base + 9 subclasses)."""
    from codegenie.sandbox import errors

    expected = sorted(("SandboxError",) + EXPECTED_SANDBOX_ERRORS)
    assert sorted(errors.__all__) == expected


# --- AC-4, AC-4a, AC-4b, AC-4c ----------------------------------------------

@pytest.mark.parametrize("name,expected_value", list(EXPECTED_SANDBOX_EVENTS.items()))
def test_sandbox_event_constants_have_pinned_values(name: str, expected_value: str):
    """AC-4: each constant equals its canonical-table value byte-for-byte.

    Mutation target: swapping two constant values (e.g.,
    EVENT_SANDBOX_EGRESS_BLOCKED = 'sandbox.execute.started') round-trips
    structurally but breaks every downstream consumer. This per-constant
    parametrized test catches it.
    """
    from codegenie.sandbox import logging as sandbox_log

    assert getattr(sandbox_log, name) == expected_value


@pytest.mark.parametrize("value", list(EXPECTED_SANDBOX_EVENTS.values()))
def test_sandbox_event_values_match_dotted_lowercase_shape(value: str):
    """AC-4a: enforces the dotted-lowercase convention at the value level."""
    assert EVENT_VALUE_RE.match(value), f"{value!r} violates dotted-lowercase shape"


def test_sandbox_event_constants_are_typed_final_str_in_source():
    """AC-4: the source-text annotation is Final[str] for every event constant."""
    src = Path(importlib.util.find_spec("codegenie.sandbox.logging").origin).read_text()
    tree = ast.parse(src)
    annotated_finals: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            annotated_finals[node.target.id] = ast.unparse(node.annotation)
    for name in EXPECTED_SANDBOX_EVENTS:
        assert name in annotated_finals, f"{name} missing source-level annotation"
        assert annotated_finals[name] == "Final[str]", (
            f"{name} must be annotated Final[str], got {annotated_finals[name]!r}"
        )


def test_sandbox_logging_all_list_matches_defined_constants():
    """AC-4b: __all__ is exactly the set of event constants defined in the module."""
    from codegenie.sandbox import logging as sandbox_log

    assert sorted(sandbox_log.__all__) == sorted(EXPECTED_SANDBOX_EVENTS.keys())


def test_sandbox_event_constant_values_are_unique():
    """AC-4c: no two constants in this module share a value."""
    from codegenie.sandbox import logging as sandbox_log

    values = [getattr(sandbox_log, n) for n in EXPECTED_SANDBOX_EVENTS]
    assert len(set(values)) == len(values)


# --- AC-5 --------------------------------------------------------------------

def test_sandbox_logging_does_not_shadow_stdlib_logging():
    """AC-5: sandbox/logging.py must not import stdlib `logging` bare-named."""
    src = Path(importlib.util.find_spec("codegenie.sandbox.logging").origin).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "logging" and alias.asname is None:
                    pytest.fail("import logging is forbidden — use `import logging as _stdlib_logging`")


# --- AC-6 --------------------------------------------------------------------

def test_no_banned_imports_in_sandbox_package_static_ast():
    """AC-6 (static): AST walk of every .py file under sandbox/ — no banned imports."""
    root = Path(importlib.util.find_spec("codegenie.sandbox").submodule_search_locations[0])
    offenders: list[str] = []
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in BANNED_TOP_LEVEL_MODULES:
                        offenders.append(f"{py}: import {a.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in BANNED_TOP_LEVEL_MODULES:
                    offenders.append(f"{py}: from {node.module} import ...")
    assert offenders == [], f"banned imports found: {offenders}"


def test_no_banned_imports_in_sandbox_package_runtime_subprocess():
    """AC-6 (runtime): fresh interpreter — none of the banned modules in sys.modules."""
    code = (
        "import codegenie.sandbox, sys; "
        "import json; "
        f"print(json.dumps([m for m in sys.modules if m.split('.')[0] in {list(BANNED_TOP_LEVEL_MODULES)!r}]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    import json

    assert json.loads(result.stdout.strip()) == []
```

```python
# tests/gates/test_scaffold.py
"""Scaffold tests for codegenie.gates — verifies S1-01 ACs.

Mirrors tests/sandbox/test_scaffold.py — same mutation-resistance discipline,
specialized to the Gate hierarchy + gate event constants.
"""

from __future__ import annotations

import ast
import importlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

EXPECTED_GATE_EVENTS: dict[str, str] = {
    "EVENT_GATE_RUN_STARTED": "gate.run.started",
    "EVENT_GATE_RUN_COMPLETED": "gate.run.completed",
    "EVENT_GATE_ATTEMPT_STARTED": "gate.attempt.started",
    "EVENT_GATE_ATTEMPT_COMPLETED": "gate.attempt.completed",
    "EVENT_GATE_ATTEMPTS_OVERRIDE": "gate.attempts_override",
    "EVENT_PRE_EXECUTE_MARKER_WRITTEN": "gate.pre_execute.written",
}

EXPECTED_GATE_ERRORS: tuple[str, ...] = (
    "GateMissingRequiredSignal",
    "GateCatalogInvalid",
    "AuditChainCorrupted",
    "LedgerAttemptOutOfOrder",
)

BANNED_TOP_LEVEL_MODULES: tuple[str, ...] = (
    "anthropic",
    "langgraph",
    "chromadb",
    "sentence_transformers",
)

EVENT_VALUE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


def test_gates_package_imports_cleanly_and_is_side_effect_free():
    result = subprocess.run(
        [sys.executable, "-c", "import codegenie.gates; print('OK')"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"
    assert result.stderr == ""


def test_gates_import_is_idempotent_same_object():
    a = importlib.import_module("codegenie.gates")
    b = importlib.import_module("codegenie.gates")
    assert a is b


def test_gate_error_base_extends_exception_not_baseexception():
    from codegenie.gates import errors

    assert errors.GateError.__bases__ == (Exception,)


@pytest.mark.parametrize("name", EXPECTED_GATE_ERRORS)
def test_each_gate_subclass_is_direct_child_of_gate_error(name: str):
    from codegenie.gates import errors

    cls = getattr(errors, name)
    assert cls.__bases__ == (errors.GateError,)


@pytest.mark.parametrize("name", ("GateError",) + EXPECTED_GATE_ERRORS)
def test_each_gate_error_class_is_marker_only(name: str):
    from codegenie.gates import errors

    cls = getattr(errors, name)
    own = set(vars(cls).keys()) - {"__module__", "__qualname__", "__doc__", "__dict__", "__weakref__"}
    assert own == set(), f"{name} must be a bare marker; unexpected members: {sorted(own)}"


@pytest.mark.parametrize("name", EXPECTED_GATE_ERRORS)
def test_gate_error_message_is_passthrough(name: str):
    from codegenie.gates import errors

    cls = getattr(errors, name)
    assert str(cls("hello-world-42")) == "hello-world-42"


def test_gate_errors_all_list_is_exact():
    from codegenie.gates import errors

    expected = sorted(("GateError",) + EXPECTED_GATE_ERRORS)
    assert sorted(errors.__all__) == expected


@pytest.mark.parametrize("name,expected_value", list(EXPECTED_GATE_EVENTS.items()))
def test_gate_event_constants_have_pinned_values(name: str, expected_value: str):
    from codegenie.gates import logging as gates_log

    assert getattr(gates_log, name) == expected_value


@pytest.mark.parametrize("value", list(EXPECTED_GATE_EVENTS.values()))
def test_gate_event_values_match_dotted_lowercase_shape(value: str):
    assert EVENT_VALUE_RE.match(value), f"{value!r} violates dotted-lowercase shape"


def test_gate_event_constants_are_typed_final_str_in_source():
    src = Path(importlib.util.find_spec("codegenie.gates.logging").origin).read_text()
    tree = ast.parse(src)
    annotated_finals: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            annotated_finals[node.target.id] = ast.unparse(node.annotation)
    for name in EXPECTED_GATE_EVENTS:
        assert name in annotated_finals
        assert annotated_finals[name] == "Final[str]"


def test_gate_logging_all_list_matches_defined_constants():
    from codegenie.gates import logging as gates_log

    assert sorted(gates_log.__all__) == sorted(EXPECTED_GATE_EVENTS.keys())


def test_gate_event_constant_values_are_unique():
    from codegenie.gates import logging as gates_log

    values = [getattr(gates_log, n) for n in EXPECTED_GATE_EVENTS]
    assert len(set(values)) == len(values)


def test_gates_logging_does_not_shadow_stdlib_logging():
    src = Path(importlib.util.find_spec("codegenie.gates.logging").origin).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "logging" and alias.asname is None:
                    pytest.fail("import logging is forbidden — use `import logging as _stdlib_logging`")


def test_no_banned_imports_in_gates_package_static_ast():
    root = Path(importlib.util.find_spec("codegenie.gates").submodule_search_locations[0])
    offenders: list[str] = []
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in BANNED_TOP_LEVEL_MODULES:
                        offenders.append(f"{py}: import {a.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in BANNED_TOP_LEVEL_MODULES:
                    offenders.append(f"{py}: from {node.module} import ...")
    assert offenders == []


def test_no_banned_imports_across_both_packages_runtime():
    code = (
        "import codegenie.sandbox, codegenie.gates, sys, json; "
        f"print(json.dumps([m for m in sys.modules if m.split('.')[0] in {list(BANNED_TOP_LEVEL_MODULES)!r}]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    import json

    assert json.loads(result.stdout.strip()) == []


def test_event_values_are_globally_unique_across_both_packages():
    """AC-4c global: no value collides between sandbox and gates modules."""
    from codegenie.sandbox import logging as sandbox_log
    from codegenie.gates import logging as gates_log

    sandbox_values = {getattr(sandbox_log, n) for n in sandbox_log.__all__}
    gates_values = {getattr(gates_log, n) for n in gates_log.__all__}
    assert sandbox_values.isdisjoint(gates_values), (
        f"event values collide across packages: {sandbox_values & gates_values}"
    )
```

Run, confirm each fails (`ModuleNotFoundError` first, then `AttributeError` on members, then assertion failures), commit on a `red` commit, then implement and commit on a `green` commit. AC-9 requires both commits in git history.

### Green — make it pass

Create the two `__init__.py` files (single docstring line; no executable code). Define `SandboxError(Exception)` and the 9 subclasses in `errors.py` as bare marker classes (docstring + `pass`). Define `GateError(Exception)` and the 4 subclasses the same way. Populate the two `logging.py` modules with `Final[str]` constants whose values come **verbatim** from the Canonical event-name table above. Add `__all__` to all four modules (`errors.py` and `logging.py` in each package). Do not implement any behavior beyond name definitions.

### Refactor — clean up

The behaviors below are now AC-enforced rather than refactor-only — they should already be in place after Green. Use Refactor to polish docstrings and tighten imports, not to add new structure.

- Module-level docstrings on `errors.py` and `logging.py` cite the Canonical event-name table and the relevant ADRs (e.g., `errors.py` cites ADR-0001; `logging.py` cites ADR-0007 for the pre-execute marker).
- Confirm `ruff format` / `ruff check` / `mypy --strict` clean.
- Confirm the static-AST banned-import test passes (locks ADR-0008; formal fence ships in S1-07).

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

### Naming conventions (Rule 11 — match the codebase)

- **`EVENT_*` prefix, NOT `EVT_*`.** Phase 0 (`src/codegenie/logging.py`) and every existing consumer use `EVENT_*` (`EVENT_PROBE_START`, `EVENT_PROBE_PARSER_CAP_EXCEEDED`). The validator-hardened ACs lock this in; the original `EVT_*` draft was convention drift.
- **`Final[str]`** for every event constant — `from typing import Final`. This is what makes `mypy --strict` happy and what the formal AST fence in S1-07 will rely on.
- **Dotted lowercase values** (`"gate.run.started"`, not `"GATE_RUN_STARTED"`). Matches Phase 0 (`probe.start`, `gitignore.append.accepted`) and the arch's own audit-event strings (`prompt_injection.detected`, `sandbox.egress.blocked`, `gate.attempts_override`). AC-4a's regex enforces this.

### Extension-by-addition contract (CLAUDE.md load-bearing commitment)

This story is the **kernel** for two extension points the rest of Phase 5 builds on:

1. **Adding a new error class** (in S1-02, S1-04, S2-01, S5-01, etc.) means adding a new direct subclass of `SandboxError` / `GateError` in the same `errors.py`, and adding the name to that module's `__all__`. **Never** edit the base class. **Never** introduce a sibling intermediate base (`SandboxBackendError → SandboxBackendDockerError → ...`) — the flat-hierarchy precedent from `src/codegenie/errors.py` is load-bearing. If a future story wants behavior on an error (e.g., structured `details: dict[str, Any]`), the **catch site** attaches it, not the class.
2. **Adding a new event constant** (in S2-01, S3-06, S6-01, etc.) means appending a new `EVENT_*: Final[str] = "..."` to the relevant `logging.py`, adding the name to `__all__`, and adding a row to the Canonical event-name table in **that future story's body**. **Never** rename or re-value an existing constant — the audit chain and downstream cost ledger key off these strings.

This is the same Open/Closed shape used by `src/codegenie/parsers/` and `src/codegenie/probes/`: kernels are touched once, consumers extend by addition.

### Anti-speculation discipline (Rule 2 — simplicity first)

- Do **not** add classes, constants, or modules the arch text does not explicitly motivate. S1-01 ships exactly the names listed in AC-2, AC-3, and the Canonical event-name table — no more.
- Cross-reference every event-name constant against the source row in the table. The two strongest ADR anchors are ADR-0007 (`EVENT_PRE_EXECUTE_MARKER_WRITTEN` — pre-execute marker for resume safety) and ADR-0012 (`EVENT_SANDBOX_EGRESS_BLOCKED` — postinstall-exfil audit event). If you find yourself wanting to add a constant the table doesn't list, that's a signal you're solving S2-01/S5-01's problem, not S1-01's.
- Each file should be < 80 lines. Errors module: ~20 lines (docstring + base + 9 subclasses + `__all__`). Logging module: ~30 lines (docstring + 4–6 constants + `__all__`).

### Why these design-pattern choices (for future-you)

- **Bare-marker errors** (no `__init__`, no `__str__`) are a deliberate choice from Phase 0: failure markers should let the **catch site** decide what structured context to attach (via structlog's `bind`/`event_dict`), not bake formatting into the class. This keeps the class hierarchy stable while letting log shape evolve.
- **`Final[str]` constants, not `StrEnum`** matches Phase 0's documented rationale (`src/codegenie/logging.py` module docstring): Phase 13's cost ledger destructures via `type(x) is str`, so values must be plain `str`, not enum members. Don't be tempted by the type-safety improvement of `StrEnum` here — it breaks downstream.
- **Module-shadowing of stdlib `logging` is accepted** as a Phase 0 precedent. AC-5 forbids `import logging` bare-named within these modules; if a later story needs stdlib logging it imports as `_stdlib_logging`.

### Common pitfalls to avoid

- Adding `from .errors import SandboxError` to `sandbox/__init__.py` to "make imports nicer" — this is what AC-1 forbids. Flat namespaces grow into cycles fast.
- Sprinkling `__str__` overrides on errors for "better logging" — that's the catch site's job; the class stays bare.
- Using `EVT_GATE_*` because it's shorter — Rule 11 wins; rename it.
