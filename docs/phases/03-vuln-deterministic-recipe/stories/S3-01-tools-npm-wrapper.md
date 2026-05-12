# Story S3-01 — `tools/npm.py` wrapper + wrapper-level `NpmScriptsEnabled` guard

**Step:** Step 3 — Ship the `NcuRecipeEngine` vertical: `tools/npm` + `tools/ncu` wrappers, `LockfileResolver`, `LockfileCanonicalizer`, recipe catalog + selector
**Status:** Ready
**Effort:** M
**Depends on:** S1-05, S1-06
**ADRs honored:** ADR-0005, ADR-0011, ADR-0014

## Context

`npm` is the third allowed binary added by ADR-0014 and the load-bearing subprocess for the entire Phase-3 vertical. Every consumer downstream — `LockfileResolver` (S3-08), `install_validator` (S4-02), `build_validator` (S4-04), `test_validator` (S4-03) — calls into `tools.npm.run(...)` rather than `subprocess.run`, mirroring the Phase-2 wrapper precedent. The wrapper is where the **wrapper-level `--ignore-scripts` invariant** lives: any caller that invokes `install` or `ci` without `--ignore-scripts` and without `test_execution=True` is rejected before the subprocess ever starts. Putting the guard here (not in the orchestrator) means a Phase-7 Docker transform or Phase-15 recipe-author cannot accidentally drop the flag — the wrapper raises `NpmScriptsEnabled` for them automatically.

This story ships the wrapper only. Digest pinning lives in S3-03; the resolver that consumes the wrapper lives in S3-08.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #5 (LockfileResolver)` — the load-bearing consumer of this wrapper; lines documenting `--ignore-scripts` enforcement.
  - `../phase-arch-design.md §"Goals" #9` — `--ignore-scripts` mandatory in non-test mode; wrapper-level guard.
  - `../phase-arch-design.md §"Cross-cutting concerns" wrapper-enforced --ignore-scripts` — invariant statement.
- **Phase ADRs:**
  - `../ADRs/0005-single-sandbox-profile-test-execution-overlay-signal-escalate.md` — `test_execution=True` overlay is the **only** way to run scripts.
  - `../ADRs/0014-allowed-binaries-additions-npm-ncu-java.md` — `npm` added to `ALLOWED_BINARIES`.
- **Source design:**
  - `../final-design.md §Goals #9` — wrapper-level invariant lineage.
- **Existing code:**
  - `src/codegenie/exec.py` — `run_in_sandbox` (extended in S1-05 + S1-06 for `npm` + `test_execution=True`).
  - `src/codegenie/tools/__init__.py` — `ToolResult` base; Phase-2 wrapper precedent.
  - `src/codegenie/errors.py` — `ToolNotFound`, `ToolTimeout`, `ToolNonZeroExit`, `ToolOutputMalformed`, plus the new `NpmScriptsEnabled` (added in S1-01).
  - `src/codegenie/tools/semgrep.py` — closest-shaped Phase-2 wrapper for argv-builder/invariant pattern.

## Goal

Ship `src/codegenie/tools/npm.py` exposing a typed `async run(...)` that routes through `exec.run_in_sandbox`, rejects `install`/`ci` calls missing `--ignore-scripts` with `NpmScriptsEnabled` *before* spawning the subprocess, and surfaces all errors via the typed exception set inherited from Phase 2.

## Acceptance criteria

- [ ] `src/codegenie/tools/npm.py` exports `NpmResult(ToolResult)`, `TOOL_NAME = "npm"`, and `async def run(argv: Sequence[str], *, cwd: Path, raw_output_path: Path, network: Literal["none","scoped"] = "scoped", test_execution: bool = False, timeout_s: float = 180.0) -> NpmResult`.
- [ ] When `argv[0]` is `install` or `ci`, the wrapper requires `--ignore-scripts` in `argv` **unless** `test_execution=True`; missing → `NpmScriptsEnabled` raised before any spawn.
- [ ] The wrapper routes through `exec.run_in_sandbox(..., network=network, test_execution=test_execution, allowlist=["registry.npmjs.org"] if network=="scoped" else [])`; no direct `subprocess` call.
- [ ] Raw stdout written to `raw_output_path` **before** any Pydantic parsing; raw file remains on disk on parse failure.
- [ ] Typed-exception coverage: `ToolNotFound` (binary missing), `ToolTimeout`, `ToolNonZeroExit` (4 KiB stderr excerpt), `ToolOutputMalformed`, `NpmScriptsEnabled` (the new wrapper-level invariant).
- [ ] Emits one `probe.tool.invoked` structlog event per call with `tool_name`, `sandbox_network`, `test_execution`, `wall_clock_ms`, `exit_code`.
- [ ] `tests/unit/tools/test_npm_wrapper.py` ships ≥ 5 tests: happy path, non-zero exit, timeout, malformed JSON, missing binary.
- [ ] `tests/adv/test_npm_wrapper_rejects_scripts_enabled.py` pins the invariant: `install`/`ci` without `--ignore-scripts` and `test_execution=False` raises `NpmScriptsEnabled`; the same call with `test_execution=True` does NOT raise.
- [ ] `scripts/check_tools_no_subprocess.py` (from Phase 2 S1-04) passes against the new module.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Land `tests/unit/tools/test_npm_wrapper.py` and `tests/adv/test_npm_wrapper_rejects_scripts_enabled.py` first (red).
2. Implement `src/codegenie/tools/npm.py`:
   - `class NpmResult(ToolResult)` with `parsed: dict | None = None` (npm outputs JSON only when `--json` is passed; some subcommands have no parseable output).
   - `_build_argv(argv, *, test_execution)` validates the invariant: if `argv[0] in {"install","ci"}` and `"--ignore-scripts"` not in `argv` and not `test_execution`, raise `NpmScriptsEnabled`.
   - `async def run(...)` calls `_build_argv`, then `_spawn_sandboxed("npm", final_argv, cwd=cwd, network=network, test_execution=test_execution, timeout_s=timeout_s)`.
   - Catch `ProcessTimeout` → `ToolTimeout`; non-zero exit → `ToolNonZeroExit(exit_code, stderr_excerpt=stderr[:4096])`; `FileNotFoundError` → `ToolNotFound`; `json.JSONDecodeError` only when the caller passed `--json` (gated by inspecting argv) → `ToolOutputMalformed`.
3. Emit `probe.tool.invoked` at the wrapper level after the subprocess completes; pull `wall_clock_ms` from `time.monotonic_ns()` delta.
4. Run unit + adversarial tests; confirm green.

## TDD plan — red / green / refactor

### Red
Path: `tests/adv/test_npm_wrapper_rejects_scripts_enabled.py`
```python
import pytest
from pathlib import Path
from unittest.mock import patch

from codegenie.tools import npm
from codegenie.errors import NpmScriptsEnabled


@pytest.mark.asyncio
async def test_npm_install_without_ignore_scripts_raises(tmp_path: Path):
    with pytest.raises(NpmScriptsEnabled):
        await npm.run(
            argv=["install", "express@4.21.0"],
            cwd=tmp_path,
            raw_output_path=tmp_path / "out.txt",
            network="scoped",
            test_execution=False,
        )


@pytest.mark.asyncio
async def test_npm_install_with_test_execution_does_not_raise(tmp_path: Path):
    with patch("codegenie.tools.npm._spawn_sandboxed") as spawn:
        spawn.return_value = ("ok", "", 0, 10)
        result = await npm.run(
            argv=["install"],            # NOTE: no --ignore-scripts on purpose
            cwd=tmp_path,
            raw_output_path=tmp_path / "out.txt",
            network="scoped",
            test_execution=True,         # the overlay forgives the missing flag
        )
    assert result.exit_code == 0
```

### Green
Smallest impl shape: a single `_build_argv` function that does the invariant check; `run` wires through `_spawn_sandboxed`; `NpmScriptsEnabled` is the new typed exception (already declared in S1-01).

### Refactor
- Only after S3-08 lands. Resist extracting a base "subcommand validator" until a second invariant appears (Rule 3 — surgical changes).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/tools/npm.py` | New — wrapper |
| `tests/unit/tools/test_npm_wrapper.py` | New — ≥ 5 tests |
| `tests/adv/test_npm_wrapper_rejects_scripts_enabled.py` | New — invariant pin |
| `tests/fixtures/tool_outputs/npm/{install_happy.txt,malformed.json}` | New — recorded fixtures |

## Out of scope

- **`ncu` wrapper** — handled by S3-02.
- **`npm` digest pinning in `tools/digests.yaml`** — handled by S3-03.
- **Cache key + transient retry** — handled by S3-08 (`LockfileResolver`).
- **`npm ci` validation invocation** — handled by S4-02.
- **`test_execution=True` overlay implementation** — landed in S1-06; this wrapper consumes it.

## Notes for the implementer

- The invariant guard must run **before** `_spawn_sandboxed`. A test that mocks `_spawn_sandboxed` and asserts it was never called when the invariant fires is the cleanest pin.
- Do **not** add a generic `subcommand: str` parameter; the argv-first shape mirrors Phase-2 wrappers and keeps the call sites self-documenting (`tools.npm.run(["install","--package-lock-only","--ignore-scripts","--no-audit","--no-fund"], ...)`).
- The `network` parameter is `Literal["none","scoped"]` only — no `"all"` overload, ever. ADR-0005 reserves `network="all"` as nonexistent in Phase 3.
- A future Phase-7 Docker transform calling `tools.npm.run(...)` should not need to know about `--ignore-scripts`; it simply omits the flag in `test_execution=False` mode and gets a typed exception with a clear error message pointing at this file.
- Per Rule 12 (Fail loud): the `NpmScriptsEnabled` message must include the offending argv (truncated to 256 chars) so triage is one-shot.
- The recorded fixture for "happy install JSON" should be the output of `npm install --json --package-lock-only` on a tiny test package (commit the fixture, don't regenerate at test time — same Phase-2 discipline).
