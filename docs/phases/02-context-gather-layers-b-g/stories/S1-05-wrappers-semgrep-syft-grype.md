# Story S1-05 — Wrappers: `semgrep`, `syft`, `grype`

**Step:** Step 1 — Plant sandbox extension, tool wrappers, tool-digest pin manifest, and the four Phase-0/1 in-place edits
**Status:** Ready
**Effort:** M
**Depends on:** S1-04
**ADRs honored:** ADR-0003, ADR-0005

## Context

Three of the seven Phase 2 tool wrappers land in this story. All three are SAST/SBOM/CVE tools that consume attacker-controlled bytes (rule packs, container images, SBOM JSON) and would otherwise be subprocess-direct call sites scattered across probes. The wrappers are the chokepoint: probes call `tools.semgrep.run(...)` / `tools.syft.run(...)` / `tools.grype.run(...)` and never see `subprocess`.

`semgrep` is special — the wrapper enforces `--disable-version-check --disable-metrics` mandatory (no network, no telemetry) and rule packs are pre-warmed via `SEMGREP_RULES_CACHE` at install time. `grype` is the only Phase 2 default outbound network path: `grype db update` runs with `network="scoped"` against the grype DB host on DB-stale cache misses. `syft` runs `network="none"` for the scan itself (the image is already on disk from S6-01's `docker build`).

S1-05, S1-06, and S1-07 parallelize after S1-04 lands.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2 (tools/ wrappers)` — full wrapper contract; per-tool invariants.
  - `../phase-arch-design.md §"Failure modes & recovery"` — semgrep ReDoS, syft zip-bomb, grype DB-stale rows.
- **Phase ADRs:**
  - `../ADRs/0003-subprocess-sandbox-profile-extension.md` — `network="none"` default; `network="scoped"` for `grype db update`.
  - `../ADRs/0005-allowed-binaries-additions.md` — per-binary subsections for `semgrep`, `syft`, `grype` (threat surface + invocation pattern + `--version` cross-check).
- **Source design:**
  - `../final-design.md §"Components" #1 tools/ wrappers` — design statement.
- **Existing code:**
  - `src/codegenie/exec.py` — `run_in_sandbox` (extended in S1-02).
  - `src/codegenie/tools/__init__.py` — `ToolResult` base (S1-04).
  - `src/codegenie/errors.py` — `ToolNotFound`, `ToolTimeout`, `ToolNonZeroExit`, `ToolOutputMalformed`, `ToolInvariantViolation` (S1-01).
  - `src/codegenie/logging.py` — `PROBE_TOOL_INVOKED`, `FIELD_TOOL_NAME`, `FIELD_SANDBOX_NETWORK` (S1-01).

## Goal

Implement `src/codegenie/tools/semgrep.py`, `src/codegenie/tools/syft.py`, and `src/codegenie/tools/grype.py` per the wrapper contract, each exposing `async run(...) -> <Tool>Result` with Pydantic `extra="forbid"`, raising the typed exception set, writing raw output before parsing, and emitting `probe.tool.invoked`.

## Acceptance criteria

- [ ] `src/codegenie/tools/semgrep.py` exports `SemgrepResult(ToolResult)` (with `findings: list[SemgrepFinding]`), `TOOL_NAME = "semgrep"`, and `async def run(target: Path, rule_packs: Sequence[Path], raw_output_path: Path, timeout_s: float = 120.0) -> SemgrepResult`. The wrapper invokes semgrep with `--disable-version-check --disable-metrics` mandatory; missing either flag in the constructed argv raises `ToolInvariantViolation`.
- [ ] `src/codegenie/tools/syft.py` exports `SyftResult(ToolResult)` (with `packages: list[SyftPackage]`), `TOOL_NAME = "syft"`, and `async def run(image_ref: str, raw_output_path: Path, timeout_s: float = 180.0) -> SyftResult`. The wrapper writes SBOM JSON to `raw_output_path` before parsing.
- [ ] `src/codegenie/tools/grype.py` exports `GrypeResult(ToolResult)` (with `matches: list[GrypeMatch]`), `TOOL_NAME = "grype"`, `async def run(sbom_path: Path, raw_output_path: Path, timeout_s: float = 120.0) -> GrypeResult`, and a separate `async def db_check() -> GrypeDbStatus` + `async def db_update(allowed_hosts: Sequence[str], timeout_s: float = 300.0) -> None` lifecycle. `db_update` calls `run_in_sandbox(..., network="scoped", scoped_egress_hosts=allowed_hosts)`; all other entry points use `network="none"`.
- [ ] Each wrapper routes through `exec.run_in_sandbox`; the `scripts/check_tools_no_subprocess.py` lint from S1-04 passes against all three modules.
- [ ] Each wrapper writes raw stdout (or the documented output flag's target file) to `raw_output_path` **before** Pydantic parsing; parse failure raises `ToolOutputMalformed(tool_name=..., detail=...)` and the raw file remains on disk for triage.
- [ ] Each wrapper emits a single `probe.tool.invoked` structlog event per call carrying `tool_name`, `sandbox_network`, `wall_clock_ms`, `exit_code`.
- [ ] Typed exception coverage: `ToolNotFound` when `argv[0]` is not on `$PATH`; `ToolTimeout` when the sandbox kills the child on timeout; `ToolNonZeroExit` carrying the first 4 KiB of stderr; `ToolOutputMalformed` on parse failure; `ToolInvariantViolation` for the semgrep flag invariant.
- [ ] Per-wrapper unit-test file under `tests/unit/tools/` ships ≥ 4 tests: happy path (recorded fixture), `ToolNonZeroExit`, `ToolTimeout`, `ToolOutputMalformed`, `ToolNotFound`. The semgrep file ships an additional fifth test for `ToolInvariantViolation`.
- [ ] Recorded fixture stdouts under `tests/fixtures/tool_outputs/{semgrep,syft,grype}/` with at least one happy-path and one malformed-output sample per tool.
- [ ] No `httpx` / `requests` / `urllib` import anywhere in the three modules (verified by `scripts/check_tools_no_subprocess.py`).
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Land `tests/unit/tools/test_semgrep.py`, `test_syft.py`, `test_grype.py` first (red). Each test patches `codegenie.exec._spawn` (or `run_in_sandbox`) to return a recorded fixture stdout / stderr / exit code; the wrapper under test parses it.
2. Implement `src/codegenie/tools/semgrep.py`:
   - `class SemgrepFinding(BaseModel)` with `model_config = ConfigDict(extra="forbid", frozen=True)`; fields `check_id`, `path`, `start_line`, `end_line`, `message`, `severity`.
   - `class SemgrepResult(ToolResult)` adding `findings: list[SemgrepFinding]`.
   - `async def run(...)` constructs argv with `["semgrep", "scan", "--json", "--disable-version-check", "--disable-metrics", "--config", ..., str(target)]`. Validates `--disable-version-check` and `--disable-metrics` present in argv before calling `run_in_sandbox`; missing → raise `ToolInvariantViolation`.
   - Catches `ProcessTimeout` from `run_in_sandbox` → re-raises `ToolTimeout`; catches non-zero exit → re-raises `ToolNonZeroExit`; catches `FileNotFoundError` from spawn → re-raises `ToolNotFound`; catches `pydantic.ValidationError` on parse → re-raises `ToolOutputMalformed`.
3. Implement `src/codegenie/tools/syft.py`:
   - `class SyftPackage(BaseModel)` (`name`, `version`, `type`, `purl`).
   - `class SyftResult(ToolResult)` adding `packages: list[SyftPackage]`.
   - `async def run(...)` constructs argv with `["syft", image_ref, "-o", "json"]`. Pipes stdout to `raw_output_path` (via the wrapper, not the tool — write `result.stdout` to file before parsing).
4. Implement `src/codegenie/tools/grype.py`:
   - `class GrypeMatch(BaseModel)` (`vulnerability_id`, `severity`, `package_name`, `package_version`, `fix_state`).
   - `class GrypeResult(ToolResult)` adding `matches: list[GrypeMatch]`.
   - `class GrypeDbStatus(BaseModel)` (`built_at: datetime`, `age_hours: float`, `digest: str`).
   - `async def run(...)` argv: `["grype", "sbom:" + str(sbom_path), "-o", "json"]`, `network="none"`.
   - `async def db_check()` argv: `["grype", "db", "check", "--output", "json"]`, `network="none"`.
   - `async def db_update(...)` argv: `["grype", "db", "update"]`, `network="scoped"`, `scoped_egress_hosts=allowed_hosts`.
5. Each wrapper emits `probe.tool.invoked` once per call after the subprocess completes, with `tool_name=TOOL_NAME`, `sandbox_network`, `wall_clock_ms` (time.monotonic delta), `exit_code`.
6. Run the test suite, the no-subprocess lint, `ruff check`, `mypy --strict src/codegenie/tools/{semgrep,syft,grype}.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/tools/test_semgrep.py`.

```python
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import codegenie.errors as e
from codegenie.tools import semgrep


HAPPY_FIXTURE = Path("tests/fixtures/tool_outputs/semgrep/happy.json")


@pytest.mark.asyncio
async def test_semgrep_happy_path_parses_findings(tmp_path: Path):
    raw_out = tmp_path / "raw.json"
    fake_stdout = HAPPY_FIXTURE.read_text()
    with patch("codegenie.tools.semgrep._spawn_sandboxed") as spawn:
        spawn.return_value = (fake_stdout, "", 0, 25)  # stdout, stderr, exit, ms
        result = await semgrep.run(
            target=tmp_path, rule_packs=[Path("p/rules")], raw_output_path=raw_out,
        )
    assert isinstance(result, semgrep.SemgrepResult)
    assert raw_out.read_text() == fake_stdout
    assert len(result.findings) >= 1


@pytest.mark.asyncio
async def test_semgrep_invariant_violation_when_flag_missing():
    # Build wrapper that bypasses the flag (simulated via monkeypatched argv builder)
    with pytest.raises(e.ToolInvariantViolation):
        # Call the internal argv builder directly with a poisoned flag set
        semgrep._build_argv(
            target=Path("/tmp"), rule_packs=[Path("p")],
            flags_override=("--no-disable-version-check",),
        )


@pytest.mark.asyncio
async def test_semgrep_non_zero_exit_raises_typed(tmp_path: Path):
    with patch("codegenie.tools.semgrep._spawn_sandboxed") as spawn:
        spawn.return_value = ("", "rule parse error at line 1", 2, 10)
        with pytest.raises(e.ToolNonZeroExit) as exc:
            await semgrep.run(target=tmp_path, rule_packs=[], raw_output_path=tmp_path / "r.json")
    assert exc.value.exit_code == 2
    assert "rule parse error" in exc.value.stderr_excerpt


@pytest.mark.asyncio
async def test_semgrep_malformed_output_raises_typed(tmp_path: Path):
    with patch("codegenie.tools.semgrep._spawn_sandboxed") as spawn:
        spawn.return_value = ("not json", "", 0, 10)
        with pytest.raises(e.ToolOutputMalformed):
            await semgrep.run(target=tmp_path, rule_packs=[], raw_output_path=tmp_path / "r.json")


@pytest.mark.asyncio
async def test_semgrep_missing_binary_raises_tool_not_found(tmp_path: Path):
    with patch("codegenie.tools.semgrep._spawn_sandboxed", side_effect=FileNotFoundError):
        with pytest.raises(e.ToolNotFound):
            await semgrep.run(target=tmp_path, rule_packs=[], raw_output_path=tmp_path / "r.json")
```

Mirror the shape for `test_syft.py` (without the invariant test) and `test_grype.py` (adding a `test_grype_db_update_uses_scoped_network` test that asserts `network="scoped"` is passed to `run_in_sandbox`).

Run; confirm `ImportError` on the modules. Commit as red marker.

### Green — make it pass

Land the three wrapper modules per the implementation outline. Keep each wrapper module under ~120 LOC; if it grows past that, the wrapper is doing too much.

### Refactor — clean up

- Each wrapper has the same try/except shape — extract a `_invoke(tool_name: str, argv: Sequence[str], ...)` helper *only if* the duplication is bothersome and the helper preserves the typed-exception mapping (otherwise the boilerplate is cheap and the helper invites coupling). Don't pre-extract.
- Recorded-fixture file paths live next to the tests under `tests/fixtures/tool_outputs/{semgrep,syft,grype}/`. Each fixture is committed JSON; document its provenance in a sibling `README.md` (which version of the tool produced it, what target was scanned).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/tools/semgrep.py` | New — wrapper |
| `src/codegenie/tools/syft.py` | New — wrapper |
| `src/codegenie/tools/grype.py` | New — wrapper |
| `tests/unit/tools/test_semgrep.py` | New — ≥ 5 tests |
| `tests/unit/tools/test_syft.py` | New — ≥ 4 tests |
| `tests/unit/tools/test_grype.py` | New — ≥ 5 tests (incl. scoped-network) |
| `tests/fixtures/tool_outputs/semgrep/{happy.json,malformed.txt}` | New — fixtures |
| `tests/fixtures/tool_outputs/syft/{happy.json,malformed.txt}` | New — fixtures |
| `tests/fixtures/tool_outputs/grype/{happy.json,db_check_happy.json,malformed.txt}` | New — fixtures |

## Out of scope

- **`gitleaks`, `scip_typescript`, `docker` wrappers** — handled by S1-06.
- **`treesitter` in-process wrapper** — handled by S1-07.
- **Tool digest pin manifest + `--version` cross-check** — handled by S1-08. This story's wrappers do **not** verify digests; S1-08's loader plus the per-wrapper `tool_digest` field in `ToolResult` link the two later.
- **Signed grype DB listing** (`grype-db-listing.signed.json`) — handled by S6-02.
- **`SemgrepProbe` / `SyftSBOMProbe` / `GrypeCVEProbe` themselves** — handled by S7-02, S6-01, S6-02. This story is wrapper-only.
- **The `--ignore-scripts` invariant for `pnpm`/`npm`** — handled by S3-02 (wrapper invariant lives in the build-graph path, not here). This story's semgrep invariant is the only invariant pinned here.

## Notes for the implementer

- The semgrep `--disable-version-check --disable-metrics` invariant is the load-bearing piece: without it, the binary reaches out to semgrep.dev on every run, which violates the `network="none"` posture silently (the network call would fail under bwrap but the wrapper would issue confusing errors). Enforce at the argv-builder level; surface the missing-flag case in a unit test.
- `grype.db_update` is the **only** default outbound-network path in Phase 2 (per Goals #12). Do not add a generic `grype.run(network="scoped")` overload that lets a future probe author bypass this. The `db_update` entry point is the single sanctioned scoped path.
- `raw_output_path` is written **before** parsing — this is the wrapper-contract checklist item #3 from S1-04. The pattern: write bytes to disk, then call `pydantic.TypeAdapter(...).validate_json(...)`. If parsing fails, the raw bytes are on disk for triage. Critical for debugging hostile-input adversarial tests.
- Pydantic `extra="forbid"` on every `SemgrepFinding` / `SyftPackage` / `GrypeMatch` is load-bearing for the "fail loud" stance: if a tool version introduces a new field, parsing fails (ToolOutputMalformed), which is correct behavior — the digest pin (S1-08) must be bumped, the new field reviewed, the schema extended.
- The `_spawn_sandboxed` indirection in each wrapper is the seam tests patch. Name it consistently across all three wrappers (and the four in S1-06) so the test patterns are uniform.
- `time.monotonic_ns() // 1_000_000` is the cheap way to populate `wall_clock_ms`. Don't use `time.time()` (subject to clock drift).
- Per Rule 12 (Fail loud), the 4 KiB stderr-excerpt cap is on the *raise site* — truncate at the wrapper, store on `ToolNonZeroExit`. If the cap is bigger than 4 KiB, audit log noise dominates triage data; if smaller, useful debugging context is lost. 4 KiB is the documented default.
- Do **not** import anything from `codegenie.probes.*` here. The dependency direction is probes → tools, never the reverse. If a wrapper needs probe-side context (e.g., to know which probe called it), receive it as a parameter, not via an import.
- The recorded fixture stdouts must be committed JSON (not generated at test time). Per "Implementation-level risks" in `High-level-impl.md`, regenerating fixtures from live tools makes the test suite non-deterministic. Pin the version that produced each fixture in a sibling `README.md` so future drift is visible.
