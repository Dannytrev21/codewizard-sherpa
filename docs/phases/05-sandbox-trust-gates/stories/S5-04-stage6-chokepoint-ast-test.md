# Story S5-04 — Stage 6 chokepoint AST test + orchestrator wiring

**Step:** Step 5 — GateRunner three-retry loop + Phase 4 replan_hook integration
**Status:** Ready
**Effort:** S
**Depends on:** S5-02
**ADRs honored:** ADR-0001

## Context

The phase's first goal — "No transform leaves the sandbox unverified" — is structurally enforced by a single AST-walking CI test: only `src/codegenie/gates/runner.py` and the `RemediationOrchestrator` may reach `validation.*`. S1-07 landed this test as a *stub* (presence-only); now that `GateRunner` exists (S5-02), this story promotes it to a real AST walk that fails loud if any other module imports or calls `validation.*`. Promoting it now (rather than later) catches any pre-existing callers surfaced during Phase 5 integration — exactly the surprise `High-level-impl.md §Step 5 — Risks` warned about. The orchestrator wiring (swap the direct `validation.*` call for `GateRunner.run`) lands alongside the test so the green PR proves the chokepoint holds.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals` Goal 1 — "No transform leaves the sandbox unverified. Phase 3 Stage 6 `Validate` is the only callsite; it is wrapped by `GateRunner.run`. Static CI test asserts no other module under `src/codegenie/` calls `validation.*` directly (`tests/schema/test_stage6_chokepoint.py`)."
  - `../phase-arch-design.md §Testing strategy` — fence/structural tests inventory.
  - `../phase-arch-design.md §Development view` — "Stage 6's previous direct call becomes `GateRunner.run(ctx)`."
  - `../phase-arch-design.md §Happy path` — "The orchestrator instantiates `GateRunner(...)`. It calls `gate_runner.run(GateContext(...))`."
- **Phase ADRs:**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — Stage 6's callsite swaps to `GateRunner.run`; chokepoint test is the enforcement.
- **Source design:**
  - `../final-design.md §Synthesis ledger — Stage 6 chokepoint row`.
- **Existing code:**
  - `tests/schema/test_stage6_chokepoint.py` (stubbed in S1-07) — promote.
  - `src/codegenie/orchestrator/__init__.py` or `remediation.py` (Phase 3) — `RemediationOrchestrator` lives here; this is the only legitimate non-`runner.py` caller.
  - `src/codegenie/validation/` (Phase 3) — the package being chokepointed.
  - Any existing direct `validation.*` import in Phase 3 — must be migrated to `GateRunner.run` invocation in this story.

## Goal

Promote `tests/schema/test_stage6_chokepoint.py` from a stub to a real AST walk that asserts only `src/codegenie/gates/runner.py` and the `RemediationOrchestrator` module reach `validation.*`, and wire the orchestrator to call `GateRunner.run` at the Stage 6 site.

## Acceptance criteria

- [ ] `tests/schema/test_stage6_chokepoint.py` walks every `.py` file under `src/codegenie/` with `ast.parse(...)` and collects: (a) `from codegenie.validation...` imports; (b) `import codegenie.validation...` imports; (c) attribute access of the form `validation.<name>` on any module-level or qualified name; (d) any string literal matching the regex `r"\bcodegenie\.validation\.\w+"` used as a dynamic import target (`importlib.import_module(...)`); the test fails if any callsite lives outside the allowlist.
- [ ] Allowlist is `frozenset({"src/codegenie/gates/runner.py", "src/codegenie/orchestrator/remediation.py"})` (path of `RemediationOrchestrator`); the path constants live at the top of the test file with comments citing ADR-0001.
- [ ] The test runs with `pytest tests/schema/test_stage6_chokepoint.py` in ≤ 1 s on a clean checkout.
- [ ] Adversarial fixture: a temporary `tests/schema/_fixtures/forbidden_caller.py.txt` (data file, not loaded as code) is parsed inline by a sub-test asserting the same walker **detects** an out-of-allowlist `from codegenie.validation import run_validation` and yields a path-prefixed error message naming the offending file and line.
- [ ] `RemediationOrchestrator` (whatever module currently calls `validation.*` directly) is refactored so the previous direct call becomes `GateRunner(client=..., gate=..., ledger=..., spec_builder=..., replan_hook=...).run(GateContext(...))`; the direct `validation.*` import is removed from that module if no other allowlisted callsite still uses it.
- [ ] If the AST walk surfaces any pre-existing caller outside the allowlist (the surprise warned about in §Step 5 Risks), the story refactors **that** caller into either `GateRunner` (the right answer) or escalates with an ADR amendment (`docs/phases/05-sandbox-trust-gates/ADRs/`); the PR body lists every surfaced caller and its disposition.
- [ ] Test message on failure includes: offending file path (relative to repo root), offending line number, and offending symbol — so the next contributor knows *what* and *where* without reading the AST walker.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff`, `mypy --strict`, `pytest` pass; the existing `test_no_subprocess_outside_build_chokepoint.py` and `test_no_llm_imports_in_sandbox.py` (S1-07) remain green.

## Implementation outline

1. Replace the S1-07 stub with a real AST walker. Use `ast.NodeVisitor` and override `visit_ImportFrom`, `visit_Import`, `visit_Attribute`, `visit_Call`.
2. For each `.py` under `src/codegenie/`:
   - Skip if path is in the allowlist.
   - `tree = ast.parse(path.read_text())`.
   - Visit: any `ImportFrom` with `module` starting with `codegenie.validation` → record; any `Import` of `codegenie.validation` → record; any `Attribute` access where the value chain resolves to `validation` against a known top-level alias → record; any `Call` to `importlib.import_module(...)` with a literal arg matching `codegenie.validation.*` → record.
3. Assert collected violations list is empty; on failure, emit a multi-line message: `tests/schema/test_stage6_chokepoint.py: violations:\n  - {path}:{lineno} -> {symbol}\n  ...`.
4. Wire the orchestrator: find the existing `validation.run_validation(...)` (or analogous) call in `src/codegenie/orchestrator/remediation.py`; replace with `GateRunner(...).run(GateContext(...))`; map the returned `GateOutcome.state` to the orchestrator's existing branching (`passed → continue; escalate/failed_unrecoverable → propagate exit code per §Decision points and defaults`).
5. Add the adversarial fixture data file and a parametrized sub-test verifying the walker would have caught it.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/schema/test_stage6_chokepoint.py`

```python
# tests/schema/test_stage6_chokepoint.py
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "codegenie"
ALLOWLIST = frozenset(
    {
        # ADR-0001: only GateRunner and RemediationOrchestrator may reach validation.*
        SRC / "gates" / "runner.py",
        SRC / "orchestrator" / "remediation.py",
    }
)
DYNAMIC_RE = re.compile(r"\bcodegenie\.validation\.\w+")


class _Walker(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[tuple[int, str]] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.module.startswith("codegenie.validation"):
            self.violations.append((node.lineno, f"from {node.module} import ..."))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name.startswith("codegenie.validation"):
                self.violations.append((node.lineno, f"import {alias.name}"))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # importlib.import_module("codegenie.validation.x")
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and DYNAMIC_RE.search(node.args[0].value)
        ):
            self.violations.append((node.lineno, f"import_module({node.args[0].value!r})"))
        self.generic_visit(node)


def _walk(path: Path) -> list[tuple[int, str]]:
    w = _Walker(path)
    w.visit(ast.parse(path.read_text()))
    return w.violations


def test_only_allowlisted_modules_reach_validation_namespace() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if path in ALLOWLIST:
            continue
        for lineno, sym in _walk(path):
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno} -> {sym}")
    assert not offenders, (
        "Stage 6 chokepoint violated (ADR-0001). "
        "Only GateRunner.run and RemediationOrchestrator may reach validation.*:\n  "
        + "\n  ".join(offenders)
    )


def test_walker_detects_forbidden_caller_fixture(tmp_path: Path) -> None:
    forbidden = tmp_path / "forbidden_caller.py"
    forbidden.write_text(
        "from codegenie.validation import run_validation\n"
        "def go():\n"
        "    return run_validation()\n"
    )
    violations = _walk(forbidden)
    assert violations, "walker must catch an out-of-allowlist validation import"
    assert any("from codegenie.validation" in v[1] for v in violations)
```

### Green — make it pass

- Migrate the single direct `validation.*` callsite in Phase 3's orchestrator to `GateRunner.run`. Update import lines.
- If the AST walker surfaces additional callers, refactor each into either (a) a `GateRunner.run` invocation (allowlisted via `RemediationOrchestrator`) or (b) move the helper out of `validation/` if it does not actually need to be there.
- Re-run the test until green.

### Refactor — clean up

- Add a module docstring on the test file citing ADR-0001 and §Goal 1.
- Extract `_Walker` into a private function or leave inline — keep the test self-contained for grep-ability.
- Verify the walker handles aliased imports (`import codegenie.validation as v` → `v.run_validation()`): if the codebase uses this pattern, add a `visit_Attribute` check using a small symbol table built in `visit_Import`. If no such pattern exists in-tree, leave the simpler walker and document the limitation.
- Confirm path comparisons use resolved absolute paths so a symlinked checkout does not bypass the allowlist.

## Files to touch

| Path | Why |
|---|---|
| `tests/schema/test_stage6_chokepoint.py` | Promote stub to AST walk. |
| `src/codegenie/orchestrator/remediation.py` | Swap direct `validation.*` call → `GateRunner.run`. |
| `src/codegenie/orchestrator/__init__.py` | Re-export `RemediationOrchestrator` if signature changed. |
| Any module surfaced as a pre-existing direct caller | Refactor or escalate via ADR. |
| `tests/orchestrator/test_remediation_dispatch.py` | Regression: `GateOutcome.state` mapping to exit codes 0/11/12. |

## Out of scope

- `GateRunner.run` implementation — S5-02.
- VCR integration test against real Phase 4 — S5-05.
- `--max-attempts-override` CLI flag wiring — S8-02.
- Cost emission — S7-03.
- Concurrent-remediate flock — S7-04.

## Notes for the implementer

- `Path` comparisons in the allowlist must be `Path` objects (not strings) so the `in` check works against `SRC.rglob`-produced `Path` instances. Use `.resolve()` on both sides if the test runs from a non-root cwd in CI.
- If the orchestrator currently builds `GateContext` somewhere else, do not duplicate that construction — call into the existing factory; this story is *surgical*, not a refactor.
- The walker intentionally does not chase function calls (e.g., `helper_that_calls_validation()`). Phase 5's chokepoint is at the *import + direct attribute* level — indirect helpers should also live in the allowlist or not exist; if you find one, refactor it into the orchestrator, do not extend the walker.
- The adversarial fixture test uses `tmp_path` to write inline — keep the body string small and obvious; it documents the walker's contract.
- When the walker surfaces a previously-hidden caller, the right escalation is an ADR amendment to ADR-0001 (add the third allowlist entry with rationale), **not** to silently broaden the allowlist in the test. Default to refactoring into `RemediationOrchestrator`.
- The test must run with `pytest --no-cov` cleanly; do not add coverage exemptions inside it.
