# Story S4-08 — One-way import fence: activities cannot import workflows

**Step:** Step 4 — Activity catalog (one file per activity, typed in and out, registry-collected)
**Status:** Ready
**Effort:** S
**Depends on:** S4-02 (`codegenie.durable.activities.*` modules exist as the targets the contract scopes)
**ADRs honored:** ADR-0010 (asymmetric activity granularity — activities are leaves; workflows orchestrate over them, never the other way); ADR-0004 (workflow-determinism enforcement three layers — adds a *fourth* boundary, the activity-side of the workflow seam); production ADR-0043 ("extension by addition" requires fenced boundaries)

## Context

Phase 9's dependency direction is **one-way**: workflows orchestrate over activities; activities NEVER import from workflows. The reasons:
1. **Replay-determinism asymmetry.** Workflows must be deterministic and pure (S1-07's fence forbids `random`, `time`, `datetime`, `uuid`, etc.). Activities are the imperative shell — they may call HTTP APIs, write to Postgres, spawn sandboxes. If an Activity were to import from a workflow module, the activity's import graph could pull in something the workflow forbids, creating a confusing one-way-import-but-bidirectional-dependency state.
2. **Test isolation.** Activities have their own unit tests under `tests/unit/durable/activities/`; workflow tests live under `tests/workflows/` and rely on Temporal's `WorkflowEnvironment`. If activities imported workflow code, every activity test would force-load the workflow module's `temporalio` workflow registry, slowing the activity test suite from milliseconds to seconds.
3. **Conceptual layering.** Workflows DEPEND ON activities (`execute_activity(...)`); activities DEPEND ON event log / capabilities / Phase-3..8 modules. The dependency arrow points one way; any reverse import is an architectural smell that an `import-linter` contract catches at the import level (no need to wait for runtime breakage).

This story extends the existing `import-linter` config (the project's `lint-imports` target — Phase 0 ADR-0002 set this up) with **one new contract** that forbids imports from `codegenie.durable.activities.*` → `codegenie.durable.workflows.*`. It also ships a deliberate-violation xfail fixture under `tests/fence/_violations/` so the contract is exercised (proving the rule isn't passing trivially).

**Scope reminder.** This story extends `pyproject.toml`'s `[tool.importlinter]` section (or `.importlinter` config file — whichever the codebase uses) with ONE contract. S1-07 already ships the workflow-determinism contracts (forbidding `random`, `time`, etc.); this story adds the orthogonal one-way-import contract. The S8 closeout (S8-06) wires the import-linter run into `make check`; this story just adds the contract.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C2 — Activity catalog` line 482 — activities depend on "`temporalio.activity`, Phase 3–8 modules, `codegenie.durable.sanitizer`, `codegenie.events.log` (via `EventLogWriteCapability`), `codegenie.types.identifiers`." Notably absent: `codegenie.durable.workflows`.
  - `../phase-arch-design.md §Component design C1 — Workflow worker` — workflows dispatch `workflow.execute_activity("name", ...)` by string name, not by importing the activity function. The string-name dispatch is itself the load-bearing decoupling.
- **Phase ADRs:**
  - `../ADRs/0010-activity-granularity-asymmetric.md` §Consequences — "the activities catalog is leaf-level; the workflow is the orchestrator."
  - `../ADRs/0004-workflow-determinism-enforcement-three-layers.md` — pattern for "structurally-defended layer boundaries via import-linter."
- **Production ADRs:**
  - `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — fences are the load-bearing enforcement mechanism.
- **Existing precedent (the import-linter config):**
  - `pyproject.toml` (`[tool.importlinter]` section, or `.importlinter` file if it exists) — current contracts include the Phase 0 cold-start contracts (forbidding LLM SDK imports) and the Phase 1+ structural contracts. This story ADDS one contract; does not touch the existing ones.
  - `Makefile` `lint-imports` target — runs `import-linter` over the configured contracts.
  - `tests/fence/_violations/` — the xfail fixture convention; same idiom used in S4-06 and S4-07.
- **Sibling stories:**
  - `S1-07-workflow-determinism-fences.md` — the determinism contracts on the workflow side; this story adds the activity side.
  - `S4-06-activity-payload-typing-fence.md` — uses the same `_violations/` directory convention.
  - `S4-07-no-merge-fence.md` — also a fence; mirrors the discipline.

## Goal

Extend the project's `import-linter` configuration with ONE new contract:

```
[importlinter:contract:activities-must-not-import-workflows]
name = Activities are leaves; never import workflows
type = forbidden
source_modules =
    codegenie.durable.activities
forbidden_modules =
    codegenie.durable.workflows
```

Plus a deliberate-violation xfail fixture under `tests/fence/_violations/` that imports `codegenie.durable.workflows` from an activity-like module; plus a test that asserts the import-linter run flags the violation when scoped at that fixture.

## Acceptance criteria

- [ ] **AC-1 — `import-linter` contract added.** The project's `pyproject.toml` `[tool.importlinter]` section (or whichever file the codebase uses) gains exactly one new contract named `activities-must-not-import-workflows` (the kebab-case name is the import-linter convention). The contract is type `forbidden`; `source_modules = codegenie.durable.activities`; `forbidden_modules = codegenie.durable.workflows`. No other contracts edited.
- [ ] **AC-2 — `make lint-imports` runs the contract.** Running `make lint-imports` exits zero (because no current activity imports any workflow); the contract's name appears in the import-linter output (proves the contract is loaded, not skipped).
- [ ] **AC-3 — Deliberate-violation xfail fixture.** `tests/fence/_violations/test_one_way_import_violation.py` declares a function whose body contains `from codegenie.durable.workflows import vuln_remediation` (an import that WOULD trigger the contract). The file is NOT under `src/codegenie/durable/activities/*.py` (so import-linter's `source_modules = codegenie.durable.activities` does NOT match it). A pytest test in the same file asserts (a) the import succeeds at runtime (no import error from Python itself); (b) if we manually run import-linter against a synthetic config pointed at this file, the synthetic run flags the violation. The synthetic-run mechanism: use `import_linter.lib.api` or `subprocess.run(["import-linter", "--config", tmp_config])` against a tmp config that names this fixture's module.
- [ ] **AC-4 — Real activity modules pass.** A test iterates `_ACTIVITIES.items()` (today: 9 activities once S4-02..S4-05 land) and asserts each activity module's source AST does NOT contain a `from codegenie.durable.workflows...` or `import codegenie.durable.workflows...` shape. This is a belt-and-braces against an import-linter misconfiguration that silently passes when the contract is mis-typed.
- [ ] **AC-5 — One-way semantics test (positive control).** A test asserts that the REVERSE direction (`from codegenie.durable.activities import emit_event` from a workflow module) IS allowed by this contract. The reason: import-linter contracts can be misread as bidirectional; this test pins the asymmetry. The S1-07 workflow-determinism contracts may forbid other things in workflow modules, but they do NOT forbid imports of activities.
- [ ] **AC-6 — Documentation in `pyproject.toml` comment.** A one-line `#` comment above the new contract names ADR-0010 + this story file as the audit anchor. Mirrors the existing import-linter contracts in the file.
- [ ] **AC-7 — Contract collision check.** A test asserts that the contract names in `[tool.importlinter]` are all unique (catches a contributor naming a future contract `activities-must-not-import-workflows` again by mistake — silently overriding this one).
- [ ] **AC-8 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean. `make check` green.

## Implementation outline

1. **Locate the import-linter config.** Most likely `pyproject.toml` `[tool.importlinter]`; possibly `.importlinter` in repo root. Identify the existing `[importlinter:contract:*]` entries to mirror the formatting.
2. **Add the new contract entry** with the exact shape in AC-1. Add a `#`-comment line above naming ADR-0010 and S4-08.
3. **Create `tests/fence/_violations/test_one_way_import_violation.py`**: declares a small module-level function with the deliberate violation import; ships a test that synthesizes a tmp `.importlinter` config pointed at the fixture and runs `import-linter` via `subprocess.run` or via the `importlinter.api` Python interface (the codebase precedent will decide which).
4. **Create AC-4 test**: under `tests/fence/test_one_way_import_fence.py`, iterate `_ACTIVITIES` + AST-scan each module's source for forbidden imports.
5. **Create AC-7 test**: parse `pyproject.toml`, extract `[tool.importlinter]` contract names, assert no duplicates.

## TDD plan — red / green / refactor

### Red — failing test first

```python
# tests/fence/test_one_way_import_fence.py
import ast
from pathlib import Path

import pytest

from codegenie.durable.activities import _ACTIVITIES


@pytest.mark.fence
def test_no_activity_imports_workflow_module():
    """ADR-0010 — activities are leaves; workflows orchestrate. The reason
    this is the red test: a reverse import (activity → workflow) creates
    a cyclic dependency state where the activity's import graph pulls in
    the workflow's `temporalio.workflow.defn`-decorated functions, which
    register against Temporal's global workflow registry at import time —
    re-importing activities under test would then re-register workflows
    and break the WorkflowEnvironment's isolation. The contract catches
    the import before runtime breaks."""
    offenders: list[str] = []
    for name, registration in _ACTIVITIES.items():
        module = registration.func.__module__
        # Resolve the source file:
        module_path = Path(__import__(module).__file__)  # type: ignore[arg-type]
        tree = ast.parse(module_path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("codegenie.durable.workflows"):
                    offenders.append(f"{module}:{node.lineno} imports {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("codegenie.durable.workflows"):
                        offenders.append(f"{module}:{node.lineno} imports {alias.name}")
    assert not offenders, "\n".join(offenders)
```

Why it fails first: today, no activities exist yet (in a CI re-order where this story lands before S4-02), so the loop iterates zero times → assertion passes trivially. The TRUE red test is the AC-3 violation fixture test, which fails until the import-linter contract is added.

### Green — minimal pass

- Add the import-linter contract entry.
- Ship the violation fixture + AC-3 synthetic-run test.
- Ship the AC-4 AST-scan test as belt-and-braces.

### Required follow-on tests (per AC)

```python
# tests/fence/_violations/test_one_way_import_violation.py
import subprocess
import textwrap
import pytest


def test_import_linter_flags_activity_to_workflow_import(tmp_path):
    """AC-3 — synthetic import-linter run against a fixture file with the
    deliberate violation MUST flag it. Proves the contract's assertion
    logic is correct and isn't passing trivially because no current
    activity violates."""
    # Construct a synthetic source tree:
    src_root = tmp_path / "src"
    activity_dir = src_root / "codegenie" / "durable" / "activities"
    activity_dir.mkdir(parents=True)
    (activity_dir / "__init__.py").write_text("")
    (activity_dir / "violating_activity.py").write_text(
        "from codegenie.durable.workflows import vuln_remediation\n"
    )
    workflow_dir = src_root / "codegenie" / "durable" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "__init__.py").write_text("")
    (workflow_dir / "vuln_remediation.py").write_text("# stub workflow\n")
    # Also need the namespace markers:
    (src_root / "codegenie" / "__init__.py").write_text("")
    (src_root / "codegenie" / "durable" / "__init__.py").write_text("")

    # Synthetic .importlinter config:
    config = tmp_path / ".importlinter"
    config.write_text(textwrap.dedent("""
        [importlinter]
        root_package = codegenie

        [importlinter:contract:activities-must-not-import-workflows]
        name = Activities are leaves; never import workflows
        type = forbidden
        source_modules =
            codegenie.durable.activities
        forbidden_modules =
            codegenie.durable.workflows
    """))

    # Run import-linter against the synthetic tree:
    result = subprocess.run(
        ["lint-imports", "--config", str(config)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(src_root)},
    )
    assert result.returncode != 0, (
        "import-linter did not flag the deliberate violation — contract is broken"
    )
    assert "activities-must-not-import-workflows" in result.stdout + result.stderr


def test_workflow_can_import_activity_module_one_way_semantics():
    """AC-5 — the contract is ONE-WAY. workflows MAY import activities
    (they need to reference the typed input/output models). The S1-07
    workflow-determinism contracts forbid other things in workflow modules,
    but NOT imports of activity payloads."""
    # Smoke test: this import succeeds and does not trigger any contract:
    from codegenie.durable.activities.emit_event import EmitEventInput
    assert EmitEventInput is not None


def test_contract_names_are_unique():
    """AC-7 — duplicate contract names silently override; the rule catches
    a contributor naming a future contract the same."""
    import tomllib
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    contracts = data.get("tool", {}).get("importlinter", {}).get("contracts", [])
    names = [c.get("name") for c in contracts]
    assert len(names) == len(set(names)), f"duplicate contract names: {names}"
```

### Refactor

- The contract entry in `pyproject.toml` carries a one-line `#`-comment above it: `# ADR-0010: activities are leaves; workflows orchestrate. See docs/phases/09-temporal-durable-workflow/stories/S4-08-one-way-import-fence.md`.
- The fence-test module docstring names ADR-0010 + ADR-0004 (the layered-defense pattern source).
- The violation file's docstring is a SHOUT: "DO NOT remove the deliberate import. This file exercises the import-linter contract via a synthetic run."

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | Add one `[importlinter:contract:activities-must-not-import-workflows]` entry (or whichever syntax the codebase uses for import-linter config). |
| `tests/fence/test_one_way_import_fence.py` | AST-scan belt-and-braces test (AC-4) + one-way-semantics positive control (AC-5). |
| `tests/fence/_violations/test_one_way_import_violation.py` | Synthetic-run test against a fixture (AC-3) + the contract-uniqueness assertion (AC-7). |

## Out of scope

- The workflow-determinism contracts (forbidding `random`, `time`, etc. in workflow modules) — S1-07.
- The activity-payload-typing fence — S4-06.
- The no-merge-activity fence — S4-07.
- `make check` integration — S8-06.
- The workflow modules themselves — S5-02 / S5-04.

## Notes for the implementer

### §1 — One contract; resist adding more

A temptation: "let's also forbid `codegenie.durable.activities.*` from importing `codegenie.transforms.*`" or "forbid `codegenie.events.*` from importing `codegenie.durable.*`." Don't, in this story. Each additional contract is its own architectural decision; each deserves its own story to surface the tradeoff. This story ships the ONE contract the architect explicitly named: activities → workflows. Future stories add others additively per ADR-0043.

### §2 — String-name dispatch is the load-bearing decoupling

Workflows call `workflow.execute_activity("emit_event", input)` — by STRING NAME. They do NOT call `from codegenie.durable.activities.emit_event import emit_event; await emit_event(input)`. The string-name dispatch is the load-bearing decoupling: it means workflows DON'T need to import the activity functions, even though they reference them. The import-linter contract enforces the asymmetry: workflows MAY import activity *type definitions* (input/output Pydantic models), they MAY NOT import activity *function references*.

In practice, workflows import the typed input/output classes:

```python
# codegenie/durable/workflows/vuln_remediation.py
from codegenie.durable.activities.emit_event import EmitEventInput, EmitEventOutput

@workflow.defn
class VulnRemediationWorkflow:
    async def run(...):
        result = await workflow.execute_activity(
            "emit_event",
            EmitEventInput(...),
            start_to_close_timeout=...,
            retry_policy=...,
        )
```

This import is the workflow → activity direction (which the contract permits). The activity FUNCTION (`emit_event` itself) is never imported.

### §3 — Why import-linter, not a custom AST check

The codebase already runs `import-linter` via `make lint-imports` (Phase 0 ADR-0002). Adding a contract to the existing tool is one config-file edit; adding a custom AST checker is a separate tool + a separate runner + a separate failure mode. Reuse what's there.

The belt-and-braces AC-4 AST scan is an ADDITIONAL check, not a replacement. It runs as a pytest test (not in `make lint-imports`), giving faster feedback during local development. The two together = "the contract is checked at CI time AND at test time."

### §4 — Synthetic-run testing of import-linter contracts

import-linter's CLI doesn't directly support "test this one contract against this synthetic source tree." The workaround is to write a tmp `.importlinter` config + a tmp `src/` tree + invoke `lint-imports` via `subprocess.run`. This is exactly what AC-3's test does.

If subprocess invocation is awkward (CI environment differences), an alternative is to use `import_linter.lib.api` directly — but the API is not as stable across versions. Default to subprocess; document the alternative in the test's docstring.

### §5 — AC-5's positive control is the asymmetry pin

Reviewers who see this contract may misread it as "workflows can't import activities either" (bidirectional rules are easier to misread than one-way ones). AC-5's positive-control test EXPLICITLY exercises the workflow → activity direction and asserts it's allowed. Without this pin, a future contributor "tightening" the contract to bidirectional would break workflow code without realizing the contract was intended to be one-way.

### §6 — Future contracts apply this idiom

When Step 7 lands the projection modules + Phase-8 events fanout (S7-03), the same fence idiom applies: `codegenie.events.projections.*` MUST NOT import `codegenie.plugins.events` (Phase-8's old log, scheduled for deletion in Phase 10). That contract lives in S7-03; this story's idiom is the precedent.
