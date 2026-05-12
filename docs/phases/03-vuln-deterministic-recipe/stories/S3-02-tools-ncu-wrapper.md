# Story S3-02 — `tools/ncu.py` wrapper for `npm-check-updates`

**Step:** Step 3 — Ship the `NcuRecipeEngine` vertical: `tools/npm` + `tools/ncu` wrappers, `LockfileResolver`, `LockfileCanonicalizer`, recipe catalog + selector
**Status:** Ready
**Effort:** S
**Depends on:** S1-05
**ADRs honored:** ADR-0003, ADR-0014

## Context

`ncu` (`npm-check-updates`) is the engine binary for `NcuRecipeEngine` — it edits `package.json` to bump dependencies to a target (patch/minor/major), then defers lockfile regeneration to `LockfileResolver`. The wrapper is the only place `ncu` is invoked; the engine never calls `subprocess` directly. Compared to the `npm` wrapper, this one is intentionally narrow: ncu has a single subcommand shape and there is no `--ignore-scripts` invariant to pin (ncu does not run scripts).

S3-01 and S3-02 parallelize after S1-05 + S1-06 land.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2a NcuRecipeEngine` — the consumer; invocation pattern `ncu --packageFile package.json --upgrade --target patch --filter <pkg>`.
  - `../phase-arch-design.md §"Goals" #5` — second registered engine seat (this wrapper anchors the default seat).
- **Phase ADRs:**
  - `../ADRs/0003-recipe-engine-ncu-default-openrewrite-stub-registered.md` — `ncu` is the production default.
  - `../ADRs/0014-allowed-binaries-additions-npm-ncu-java.md` — `ncu` added to `ALLOWED_BINARIES`.
- **Source design:**
  - `../final-design.md §"Components" #2` — engine contract.
- **Existing code:**
  - `src/codegenie/exec.py` — `run_in_sandbox`.
  - `src/codegenie/tools/npm.py` (just landed in S3-01) — sibling-wrapper shape; mirror its structure.
  - `src/codegenie/errors.py` — `ToolNotFound`, `ToolTimeout`, `ToolNonZeroExit`, `ToolOutputMalformed`.

## Goal

Ship `src/codegenie/tools/ncu.py` as a typed wrapper for `npm-check-updates` routing through `exec.run_in_sandbox(network="scoped", allowlist=["registry.npmjs.org"])`, parsing the `--jsonUpgraded` output into a Pydantic `NcuResult`, and surfacing errors via the typed exception set.

## Acceptance criteria

- [ ] `src/codegenie/tools/ncu.py` exports `NcuResult(ToolResult)` (adds `upgrades: dict[str, str]` — package name → new version range), `TOOL_NAME = "ncu"`, and `async def run(package_file: Path, *, target: Literal["patch","minor","major"], filter_packages: Sequence[str], raw_output_path: Path, timeout_s: float = 60.0) -> NcuResult`.
- [ ] argv construction: `["ncu", "--packageFile", str(package_file), "--upgrade", "--target", target, "--jsonUpgraded"]` with `--filter <pkg>` appended for each package in `filter_packages`.
- [ ] Wrapper routes through `exec.run_in_sandbox(..., network="scoped", allowlist=["registry.npmjs.org"], test_execution=False)`; no `subprocess` import.
- [ ] Raw stdout written to `raw_output_path` **before** parsing; raw file remains on disk on parse failure.
- [ ] Typed-exception coverage: `ToolNotFound` (`ncu` missing on `$PATH`), `ToolNonZeroExit` (4 KiB stderr excerpt), `ToolOutputMalformed` (`--jsonUpgraded` output is not valid JSON dict), `ToolTimeout` (subprocess kill).
- [ ] Emits one `probe.tool.invoked` structlog event with `tool_name="ncu"`, `sandbox_network="scoped"`, `wall_clock_ms`, `exit_code`.
- [ ] `tests/unit/tools/test_ncu_wrapper.py` ships ≥ 4 tests: happy path, non-zero exit, missing binary, malformed output.
- [ ] `scripts/check_tools_no_subprocess.py` passes.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Land `tests/unit/tools/test_ncu_wrapper.py` first (red).
2. Implement `src/codegenie/tools/ncu.py`:
   - `class NcuResult(ToolResult)` with `upgrades: dict[str, str]` (Pydantic `extra="forbid"`).
   - `async def run(...)` builds argv, writes raw stdout to `raw_output_path` before parsing, parses via `pydantic.TypeAdapter(dict[str, str]).validate_json(...)`, returns `NcuResult(...)`.
   - Catch `ProcessTimeout` → `ToolTimeout`; non-zero exit → `ToolNonZeroExit`; `FileNotFoundError` → `ToolNotFound`; `pydantic.ValidationError` or `json.JSONDecodeError` → `ToolOutputMalformed`.
3. Emit `probe.tool.invoked` after subprocess completion.
4. Land recorded fixtures.

## TDD plan — red / green / refactor

### Red
Path: `tests/unit/tools/test_ncu_wrapper.py`
```python
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import codegenie.errors as e
from codegenie.tools import ncu


HAPPY_FIXTURE = Path("tests/fixtures/tool_outputs/ncu/happy.json")


@pytest.mark.asyncio
async def test_ncu_happy_path_parses_upgrades(tmp_path: Path):
    raw_out = tmp_path / "raw.json"
    fake_stdout = HAPPY_FIXTURE.read_text()
    with patch("codegenie.tools.ncu._spawn_sandboxed") as spawn:
        spawn.return_value = (fake_stdout, "", 0, 220)
        result = await ncu.run(
            package_file=tmp_path / "package.json",
            target="patch",
            filter_packages=["express"],
            raw_output_path=raw_out,
        )
    assert "express" in result.upgrades
    assert raw_out.read_text() == fake_stdout


@pytest.mark.asyncio
async def test_ncu_non_zero_exit_raises_typed(tmp_path: Path):
    with patch("codegenie.tools.ncu._spawn_sandboxed") as spawn:
        spawn.return_value = ("", "registry connection failed", 1, 50)
        with pytest.raises(e.ToolNonZeroExit):
            await ncu.run(
                package_file=tmp_path / "package.json",
                target="patch",
                filter_packages=[],
                raw_output_path=tmp_path / "r.json",
            )


@pytest.mark.asyncio
async def test_ncu_missing_binary_raises_tool_not_found(tmp_path: Path):
    with patch("codegenie.tools.ncu._spawn_sandboxed", side_effect=FileNotFoundError):
        with pytest.raises(e.ToolNotFound):
            await ncu.run(
                package_file=tmp_path / "package.json",
                target="patch",
                filter_packages=[],
                raw_output_path=tmp_path / "r.json",
            )


@pytest.mark.asyncio
async def test_ncu_malformed_output_raises_typed(tmp_path: Path):
    with patch("codegenie.tools.ncu._spawn_sandboxed") as spawn:
        spawn.return_value = ("not json", "", 0, 10)
        with pytest.raises(e.ToolOutputMalformed):
            await ncu.run(
                package_file=tmp_path / "package.json",
                target="patch",
                filter_packages=[],
                raw_output_path=tmp_path / "r.json",
            )
```

### Green
Mirror `tools/npm.py` shape minus the `--ignore-scripts` invariant; under ~80 LOC.

### Refactor
- After S3-07 lands and the engine drives this wrapper, revisit only if the `upgrades` dict shape needs a richer Pydantic model (don't pre-extract).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/tools/ncu.py` | New — wrapper |
| `tests/unit/tools/test_ncu_wrapper.py` | New — ≥ 4 tests |
| `tests/fixtures/tool_outputs/ncu/{happy.json,malformed.txt}` | New — recorded fixtures |

## Out of scope

- **`npm` digest pin + `ncu` digest pin in `tools/digests.yaml`** — handled by S3-03.
- **The engine that drives this wrapper** — handled by S3-07.
- **Recipe parameters (`target`, `filter_packages` payloads)** — handled by S3-05 (recipe model + first recipe).

## Notes for the implementer
- The argv ordering matters: `--upgrade` must precede `--jsonUpgraded` per the ncu CLI; check the recorded fixture's invocation comment.
- `--target patch` is the Phase-3 default — recipes can override (`target` is a `Recipe.params` field landed in S3-05).
- Do not pass `--registry`; the sandbox-allowlisted host (`registry.npmjs.org`) is the implicit default. A future internal-mirror change goes through `registry_mirror_digest` in S3-08's cache key, not here.
- The wrapper does **not** verify the npm registry response; that is `LockfileResolver`'s job. Stay narrow.
- `--filter` accepts a glob; the wrapper validates inputs as plain package names + ASCII to keep the seam audit-friendly (no regex injection surface).
