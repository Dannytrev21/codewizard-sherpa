# Story S1-04 — `src/codegenie/tools/` package skeleton + shared Pydantic result base

**Step:** Step 1 — Plant sandbox extension, tool wrappers, tool-digest pin manifest, and the four Phase-0/1 in-place edits
**Status:** Ready
**Effort:** S
**Depends on:** S1-03
**ADRs honored:** ADR-0003, ADR-0005

## Context

Phase 2 introduces seven tool wrappers — one Pydantic-typed module per external CLI (`semgrep`, `syft`, `grype`, `gitleaks`, `scip_typescript`, `docker`, `treesitter`). Per `phase-arch-design.md §"Component design" #2`, every wrapper exports `async run(...) -> <Tool>Result`, routes through `exec.run_in_sandbox` (never `subprocess.run`), writes raw output before parsing, and raises the typed `Tool*` exception set from S1-01.

Before any individual wrapper lands (S1-05/06/07), the **package skeleton** and **shared result base class** must exist — otherwise three parallel wrapper stories all duplicate the same `ToolResult` definition and diverge under review. This story is small but is the contract-author surface every other wrapper conforms to.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2 (tools/ wrappers)` — full contract: `async run`, sandbox-only invocation, `raw_output_path` write before parse, typed exception set, Pydantic `extra="forbid"`, no HTTP from any `tools/` module.
  - `../phase-arch-design.md §"4+1 architectural views" "Logical view"` — `ToolResult` class diagram with `raw_output_path: Path`, `tool_digest: str`, `wall_clock_ms: int`.
- **Phase ADRs:**
  - `../ADRs/0003-subprocess-sandbox-profile-extension.md` — ADR-0003 — every wrapper consumes the extended `run_in_sandbox`.
  - `../ADRs/0005-allowed-binaries-additions.md` — ADR-0005 — each wrapper's binary is in `ALLOWED_BINARIES`.
- **Source design:**
  - `../final-design.md §"Components" #1 tools/ wrappers` — design statement.
- **Existing code:**
  - `src/codegenie/exec.py` (extended in S1-02 + S1-03) — every wrapper calls `run_in_sandbox`.
  - `src/codegenie/errors.py` (extended in S1-01) — every wrapper raises one of `ToolNotFound`, `ToolTimeout`, `ToolNonZeroExit`, `ToolOutputMalformed`, `ToolInvariantViolation`.
  - `src/codegenie/logging.py` (extended in S1-01) — every wrapper emits `probe.tool.invoked`.

## Goal

Land `src/codegenie/tools/__init__.py` with the public surface declaration and define `ToolResult` — a shared Pydantic base model with `extra="forbid"` exporting `raw_output_path`, `tool_digest`, `wall_clock_ms` — so every wrapper story (S1-05/06/07) extends a single shared shape rather than reinventing it.

## Acceptance criteria

- [ ] `src/codegenie/tools/__init__.py` exists with a one-paragraph module docstring naming `phase-arch-design.md §"Component design" #2`, ADR-0003, ADR-0005.
- [ ] `src/codegenie/tools/__init__.py` exports `ToolResult` and `WrapperContract` (a `Protocol` describing the `async run(...) -> ToolResult` shape).
- [ ] `ToolResult` is a `pydantic.BaseModel` with `model_config = ConfigDict(extra="forbid", frozen=True)` and fields: `raw_output_path: Path`, `tool_digest: str`, `wall_clock_ms: int`.
- [ ] `WrapperContract` is a `typing.Protocol` (or `runtime_checkable` Protocol) documenting that every wrapper module exposes `async def run(...) -> ToolResult` plus a module-level `TOOL_NAME: Final[str]` constant.
- [ ] `tools/__init__.py` docstring contains the **wrapper contract** as a checklist: (1) goes through `exec.run_in_sandbox`, never `subprocess.run`; (2) raises the typed `Tool*` exception set; (3) writes raw output to `raw_output_path` before parsing; (4) emits `probe.tool.invoked` with `FIELD_TOOL_NAME`; (5) no HTTP from any `tools/` module.
- [ ] `tests/unit/tools/test_tools_package.py` asserts: the package imports cleanly, `ToolResult` is frozen (mutation raises `ValidationError`), `extra="forbid"` rejects unknown fields, `wall_clock_ms` is an `int` and `tool_digest` is a non-empty `str`.
- [ ] A CI lint script `scripts/check_tools_no_subprocess.py` is shipped and wired into the `fence` job: greps `src/codegenie/tools/*.py` for `subprocess.run`, `subprocess.Popen`, `os.system`, `httpx`, `requests`, `urllib` — finds zero hits or fails CI. The lint runs in this story as a guard for the wrappers that land in S1-05/06/07.
- [ ] No edits to Phase 0/1 modules; only new files under `src/codegenie/tools/` and `scripts/`.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write `tests/unit/tools/test_tools_package.py` first (red) — import `codegenie.tools`, assert `ToolResult` exists and is frozen, assert `extra="forbid"` semantics with `pytest.raises(ValidationError)`.
2. Create `src/codegenie/tools/__init__.py` exporting `ToolResult` (Pydantic) and `WrapperContract` (Protocol). Include the wrapper-contract checklist in the module docstring.
3. Create `tests/unit/tools/__init__.py` (empty).
4. Write `scripts/check_tools_no_subprocess.py` — a small Python script that walks `src/codegenie/tools/*.py` and asserts none of the forbidden tokens appears outside string literals (use `ast.parse` + `ast.walk` over imports rather than regex, so a docstring mentioning `subprocess.run` doesn't trip the lint).
5. Wire `scripts/check_tools_no_subprocess.py` into `.github/workflows/<fence-job>.yml` (or whatever Phase 0 named the fence job). One new step in the existing job; do not create a new workflow.
6. Run `pytest tests/unit/tools/`, `python scripts/check_tools_no_subprocess.py`, `ruff check`, `mypy --strict src/codegenie/tools/`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/tools/test_tools_package.py`.

```python
from pathlib import Path

import pytest
from pydantic import ValidationError


def test_tools_package_imports():
    import codegenie.tools  # noqa: F401


def test_tool_result_frozen_and_extra_forbid():
    from codegenie.tools import ToolResult
    r = ToolResult(raw_output_path=Path("/tmp/x.json"), tool_digest="sha256:abc", wall_clock_ms=42)
    # frozen
    with pytest.raises(ValidationError):
        r.wall_clock_ms = 100  # type: ignore[misc]
    # extra forbid
    with pytest.raises(ValidationError):
        ToolResult(
            raw_output_path=Path("/tmp/x.json"),
            tool_digest="sha256:abc",
            wall_clock_ms=42,
            unknown_field="bad",  # type: ignore[call-arg]
        )


def test_wrapper_contract_protocol_describes_run_signature():
    from codegenie.tools import WrapperContract
    # WrapperContract.run is an awaitable returning ToolResult
    # Smoke check that the Protocol exists and has the expected attribute name
    assert hasattr(WrapperContract, "run")
```

A second test file `tests/unit/tools/test_no_subprocess_lint.py` validates the lint script:

```python
import subprocess
import sys


def test_lint_passes_on_empty_tools_dir():
    # No wrappers yet (or only __init__.py) — lint must succeed
    res = subprocess.run([sys.executable, "scripts/check_tools_no_subprocess.py"], capture_output=True)
    assert res.returncode == 0, res.stderr
```

Run; confirm import errors. Commit as red marker.

### Green — make it pass

`src/codegenie/tools/__init__.py`:

- Module docstring (the wrapper-contract checklist) at the top.
- Import `Protocol`, `runtime_checkable` from `typing`; import `Path`, `Final`; import `BaseModel`, `ConfigDict` from `pydantic`.
- Declare `ToolResult(BaseModel)` with `model_config = ConfigDict(extra="forbid", frozen=True)` and the three fields.
- Declare `WrapperContract(Protocol)` with `TOOL_NAME: ClassVar[str]` and `async def run(self, *args: object, **kwargs: object) -> ToolResult: ...`.
- `__all__ = ("ToolResult", "WrapperContract")`.

`scripts/check_tools_no_subprocess.py`:

- Walks every `.py` under `src/codegenie/tools/`.
- Parses each with `ast.parse`; looks for `ast.Import` and `ast.ImportFrom` nodes referencing `subprocess`, `httpx`, `requests`, `urllib`, `urllib3`, `socket` (top-level use).
- Also looks for `ast.Call` whose `func` resolves textually to `os.system`.
- Exits 1 on any hit with a clear `path:line` message; exits 0 otherwise.
- Excludes the `__init__.py` from `os.system` check if mentioned only in the docstring (ast won't see it inside a docstring).

### Refactor — clean up

- The `WrapperContract` Protocol is documentation-only — Python's structural typing means mypy can check wrapper modules against it, but runtime instances aren't required. Document this in a comment.
- The lint script is the load-bearing piece for keeping `tools/` honest as wrappers land. Add a small test that plants a `subprocess.run(...)` call in a temp fake-wrapper file and asserts the script exits 1 (this is the "test the test" pattern).
- Confirm `mypy --strict` clean on `tools/__init__.py` — Pydantic v2's plugin should infer field types; if mypy complains about `ConfigDict`, ensure `pydantic` is in the closure (it is, from Phase 0).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/tools/__init__.py` | New — `ToolResult`, `WrapperContract`, contract docstring |
| `scripts/check_tools_no_subprocess.py` | New — fence lint for `tools/` |
| `tests/unit/tools/__init__.py` | New (empty) |
| `tests/unit/tools/test_tools_package.py` | New — package import + ToolResult shape |
| `tests/unit/tools/test_no_subprocess_lint.py` | New — lint script smoke |
| `.github/workflows/<fence-job>.yml` | Wire `check_tools_no_subprocess.py` into existing fence job |

## Out of scope

- **The seven wrapper modules** (`semgrep.py`, `syft.py`, `grype.py`, `gitleaks.py`, `scip_typescript.py`, `docker.py`, `treesitter.py`) — handled by S1-05, S1-06, S1-07. This story is the contract scaffolding.
- **`tools/digests.yaml` pin manifest** — handled by S1-08. This story does not load digests.
- **Per-wrapper `TOOL_NAME` constants** — each wrapper declares its own; this story only documents the contract.
- **Wrapper-level `--ignore-scripts` invariant** — handled by S3-02 (`BuildGraphProbe`) and S1-05 (where applicable). This story does not pre-enumerate per-binary invariants.

## Notes for the implementer

- `ToolResult` is intentionally **minimal** — three fields. Per-tool wrappers extend it (e.g., `SemgrepResult(ToolResult)` adds `findings: list[Finding]`). The base must stay small so Phase 7's distroless wrappers can subclass it without first removing speculative cruft.
- `frozen=True` on the Pydantic config is load-bearing: it makes `ToolResult` instances immutable, which means `MappingProxyType` over a dict of them (S1-11) is truly read-only. If you skip `frozen=True`, the peer-output snapshot becomes a security hole.
- The wrapper-contract docstring is the canonical specification S1-05/06/07 read from. Make it precise. Suggested ordering: contract preconditions first (must call `run_in_sandbox`, must not import `subprocess`); contract output (must return `ToolResult`); contract failure (must raise typed exceptions); contract observability (must emit `probe.tool.invoked`).
- `scripts/check_tools_no_subprocess.py` is your enforcement seam. If a future wrapper author (or AI agent) writes `subprocess.run(...)` directly, the fence job is the early-surfacing canary — much louder than catching it in code review. Make the error message identify the file and line.
- `runtime_checkable` Protocol with `async def run` is awkward in Python's type system — `Protocol` cannot describe a variadic async function precisely. Document the limitation in the docstring; the mechanical contract is "wrapper module exposes `async def run` returning `ToolResult`," not "wrapper class implements Protocol."
- The lint must use `ast.parse`, not `grep`. A wrapper docstring that says "this wrapper does NOT use `subprocess.run`" would otherwise trip the grep. AST-based parsing only flags actual imports/calls. Per Rule 12 (Fail loud), false positives degrade the lint's trustworthiness — get it right the first time.
- Do **not** add a `BaseWrapper` abstract class. The `Protocol` is sufficient; concrete wrappers are module-level `async def run(...)` functions, not classes. Phase 7's distroless wrappers will follow the same module-function shape.
