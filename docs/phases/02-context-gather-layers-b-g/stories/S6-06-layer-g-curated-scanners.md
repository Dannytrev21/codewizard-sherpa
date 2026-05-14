# Story S6-06 — `Semgrep` + `AstGrep` + `RipgrepCurated` Layer G scanners

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** Ready
**Effort:** M
**Depends on:** S1-07 (`run_external_cli` wrapper with bubblewrap + 64 MB cap + env strip), S3-03 (writer signature + sanitizer composition — scanner findings flow through `SecretRedactor` at the writer chokepoint)
**ADRs honored:** 02-ADR-0001 (`semgrep`, `ast-grep`, `ripgrep` added to `ALLOWED_BINARIES`), 02-ADR-0005 (no plaintext persistence — findings flow through `SecretRedactor`), 02-ADR-0010 (`RedactedSlice` smart constructor at writer boundary — the four scanners' outputs reach the writer via that single typed door)
**Phase-2 load-bearing design discipline:** [`../phase-arch-design.md` §"Design patterns applied"](../phase-arch-design.md) **row 7** — *"One file per Layer G scanner; no shared `ScannerRunner` abstraction"* — SRP + Rule of Three. Four scanners have four genuinely different I/O shapes; ~60 LOC saved by sharing is not worth the speculative coupling. **This story is the test of that discipline.**

## Context

The Layer G scanners are where the temptation to abstract is highest and the cost is most visible. All four (`semgrep`, `ast-grep`, `ripgrep`, `gitleaks`) follow the same five-step shape:

1. Check the tool is available via Phase 0's `tool_cache`.
2. Invoke via `run_external_cli` with explicit argv (no shell, scanner-specific flags).
3. Parse stdout JSON via a Pydantic smart constructor.
4. Map findings into `ScannerOutcome = ScannerRan | ScannerSkipped | ScannerFailed`.
5. Return `ProbeOutput` whose `schema_slice` round-trips through the writer's redactor.

A naive reading says "abstract steps 1-5 into a `ScannerRunner` base class." The design table says no: each scanner's flags are different (`semgrep --metrics=off --json`, `ast-grep run --json=stream`, `rg --json`, `gitleaks detect --no-banner`), each scanner's JSON shape is different (Semgrep's `results: [{check_id, path, start: {line}, extra: {message}}]`, ast-grep's `[{file, range, message}]`, ripgrep's NDJSON stream, gitleaks' `[{Description, RuleID, File, StartLine, Match}]`), and each scanner's error model is different (semgrep's `errors:` array, gitleaks' exit-code-1-on-findings vs. exit-code-2-on-error). Abstracting them produces a base class with five `abstractmethod`s — at which point you've made each scanner harder to read in isolation in exchange for saving ~60 LOC.

This story ships **three** of the four (semgrep, ast-grep, ripgrep-curated). The fourth (gitleaks) ships in S6-07 *because* it's the load-bearing security scanner — the `test_secret_in_source.py` adversarial test pins the writer-chokepoint guarantee, and isolating it as a separate story prevents review pressure from collapsing the four scanners into a shared abstraction (which would invalidate the test's coverage).

`ScannerOutcome` is the typed sum across all four scanners — that's the **shared discriminated union**, the level the discipline allows sharing at. It lands in S5-01 (`src/codegenie/probes/_shared/scanner_outcome.py`); this story imports it.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Design patterns applied"](../phase-arch-design.md) **row 7** — the load-bearing "no shared `ScannerRunner`" decision; this story is the test of it.
  - [`../phase-arch-design.md` §"Component design" #5 Layer G scanners](../phase-arch-design.md) — one file per scanner, ≤ 200 LOC each.
  - [`../phase-arch-design.md` §"Component design" #3 `run_external_cli`](../phase-arch-design.md) — env strip, 64 MB stdout/stderr cap, `asyncio.wait_for` timeout, optional bubblewrap.
  - [`../phase-arch-design.md` §"Edge cases"](../phase-arch-design.md) rows 1–3 + 13 — tool missing, non-zero exit, bad JSON, hostile JSON (truncated/oversized/deeply nested).
  - [`../phase-arch-design.md` §"Anti-patterns avoided"](../phase-arch-design.md) "Inheritance for code reuse" — every Phase 2 class inherits only `Probe` or `BaseModel`.
- **Phase ADRs:**
  - [`../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md`](../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) — `semgrep`, `ast-grep`, `ripgrep` in the allowlist; the only auditable list.
  - [`../ADRs/0005-secret-findings-no-plaintext-persistence.md`](../ADRs/0005-secret-findings-no-plaintext-persistence.md) — findings flow through `SecretRedactor` at the writer.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) — per-probe timeouts (semgrep 60s, ast-grep 30s, ripgrep-curated 30s); `--metrics=off` for semgrep; `@register_probe(heaviness="medium")`.
  - [`../../localv2.md` §5.6 G1 / G2 / G5](../../../localv2.md) — slice shapes.
- **Existing kernel:**
  - `src/codegenie/exec.py` (S1-07) — `run_external_cli(binary, argv, *, timeout_seconds, ...) -> ProcessResult`.
  - `src/codegenie/probes/_shared/scanner_outcome.py` (S5-01) — `ScannerRan | ScannerSkipped | ScannerFailed`.
  - `src/codegenie/output/sanitizer.py` (S3-01..03) — `SecretRedactor`; this probe doesn't call it (writer does).

## Goal

Ship three files under `src/codegenie/probes/layer_g/`: `semgrep.py`, `ast_grep.py`, `ripgrep_curated.py`. Each:

- Is `@register_probe(heaviness="medium")`.
- Is **≤ 200 LOC** (including Pydantic models, imports, docstring).
- Imports **no** code from another scanner in this set.
- Follows the five-step shape — but the five steps are inline, not behind a base class.
- Routes invocation through `run_external_cli`; parses stdout JSON via a per-scanner Pydantic smart constructor; returns `ScannerOutcome` as the slice payload.

The fourth scanner (`gitleaks.py`) is S6-07; same shape, different story.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

- [ ] **AC-1.** Three new files exist plus a `layer_g/__init__.py` package marker. Each file's `__all__` declares exactly the slice model + probe class.
- [ ] **AC-2.** Each probe file is **≤ 200 LOC** including Pydantic models, imports, docstring. Verified by `tests/unit/probes/layer_g/test_scanner_loc_ceiling.py`.
- [ ] **AC-3.** Each probe is `@register_probe(heaviness="medium")`; `probe_id` matches filename (`semgrep`, `ast_grep`, `ripgrep_curated`); `applies_to_tasks=("*",)`; `applies_to_languages=("*",)`.
- [ ] **AC-4.** Per-probe timeouts: `semgrep.timeout_seconds = 60`, `ast_grep.timeout_seconds = 30`, `ripgrep_curated.timeout_seconds = 30`.
- [ ] **AC-5.** **`SemgrepProbe`** invokes `run_external_cli("semgrep", ["--config", config_path, "--json", "--metrics=off", "--quiet", str(repo_root)], timeout_seconds=60)`. The `--metrics=off` flag is mandatory (verified by argv-introspection test); `--quiet` keeps stderr minimal for the 64 MB cap.
- [ ] **AC-6.** **`AstGrepProbe`** invokes `run_external_cli("ast-grep", ["scan", "--config", config_path, "--json=stream", str(repo_root)], timeout_seconds=30)`. `--json=stream` is the documented NDJSON-per-line emission mode (chosen over `--json=compact` because it bounds peak memory under the 64 MB cap).
- [ ] **AC-7.** **`RipgrepCuratedProbe`** invokes `run_external_cli("rg", ["--json", "--max-count", "100", "--type-not", "lock"] + curated_patterns + [str(repo_root)], timeout_seconds=30)`. `--max-count 100` caps per-pattern matches; `--type-not lock` skips lockfiles (huge, low signal). The curated pattern set is the closed set from `localv2.md` §5.6 G5: `/bin/`, `/usr/bin/`, `/sbin/`, `exec\\(`, `spawn\\(`, `execSync\\(`, `process\\.platform`, `os\\.platform\\(`, `LD_PRELOAD`, `LD_LIBRARY_PATH`.
- [ ] **AC-8.** **No shared `ScannerRunner` base class.** Architectural test: each of the three files imports `Probe` from `codegenie.probes.base`; none imports from one of the other two scanner files; none imports a `ScannerRunner` / `BaseScanner` symbol. If a future contributor extracts a base, the test fails immediately. The shared types are `ScannerOutcome` (S5-01) and `run_external_cli` (S1-07) — both at the *kernel* level, not the scanner-family level.
- [ ] **AC-9.** **Pydantic smart constructor per scanner.** Each scanner has its own `parse_*_stdout(raw: bytes) -> Result[list[Finding], ParseError]` private function. `Finding` is a per-scanner Pydantic model (`SemgrepFinding`, `AstGrepFinding`, `RipgrepFinding`) with `model_config = ConfigDict(frozen=True, extra="forbid")` — the three Finding types are NOT a discriminated union (different field shapes; each consumer uses its own type).
- [ ] **AC-10.** **Tool missing → `ScannerSkipped`.** When `run_external_cli` raises `ToolMissingError` (Phase 0 typed exception from the tool-cache check), the probe returns `ScannerOutcome.ScannerSkipped(reason="tool_missing")` with `confidence="low"`. Mutation caught: raising past the probe boundary would break Phase 0 isolation.
- [ ] **AC-11.** **Non-zero exit → `ScannerFailed`.** When `run_external_cli` returns `ProcessResult(exit_code != 0)` AND the scanner's own convention says non-zero means error (NOT semgrep's "findings present" which uses exit code 1 — see AC-15), the probe returns `ScannerFailed(exit_code, stderr_tail)`.
- [ ] **AC-12.** **Invalid JSON → `ScannerFailed`.** When stdout fails the Pydantic smart constructor, the probe returns `ScannerFailed(exit_code=0, stderr_tail="invalid_json: <tail>")`. Mutation caught: any silent swallow of `ValidationError`.
- [ ] **AC-13.** **64 MB stdout/stderr cap honored.** Test parametrized across three probes: a fixture whose mocked subprocess emits >64 MB of stdout triggers `run_external_cli`'s cap (Phase 1 contract); the probe sees the typed `OutputTooLarge` error and returns `ScannerFailed(reason="output_too_large")`. Mutation caught: any probe that bypasses the wrapper.
- [ ] **AC-14.** **`bubblewrap` no-op on macOS.** On macOS, `run_external_cli` skips the `bwrap` wrap with a single startup warning; the probe's behavior is unchanged. Test mocks `sys.platform = "darwin"` and verifies the scanner still runs.
- [ ] **AC-15.** **Semgrep exit code 1 = findings present.** Semgrep documents exit code 1 as "rule findings present, no error"; the probe MUST treat exit code 1 as success (parse stdout normally) and emit `ScannerRan(findings)`. Exit code 2+ is an actual error. The other two scanners use the default "non-zero = error" convention. **This is the textbook example of why a shared `ScannerRunner` is wrong.**
- [ ] **AC-16.** **All scanner invocations route through `run_external_cli`.** Architectural test parametrized across the three files: no direct `subprocess.run` / `subprocess.Popen` / `asyncio.create_subprocess_exec` calls. The single chokepoint is `run_external_cli` — the auditable list of "every external CLI invocation" is `grep -rn run_external_cli src/codegenie/`.
- [ ] **AC-17.** **`mypy --strict`** passes on all three files. No `Any` escapes the scanner-specific `Finding` types.
- [ ] **AC-18.** **Sub-schemas validate.** Each scanner's slice round-trips through `src/codegenie/schema/probes/layer_g/{semgrep,ast_grep,ripgrep_curated}.schema.json` (sub-schemas land in S6-08); `additionalProperties: false` at every level; `ScannerOutcome` discriminator is `kind` ∈ {`"ran"`, `"skipped"`, `"failed"`}.
- [ ] **AC-19.** **Mocked via `pytest-subprocess`.** All scanner unit tests mock `run_external_cli`'s underlying subprocess via `pytest-subprocess` — no real `semgrep`/`ast-grep`/`rg` invocations in the unit lane. Integration lane (in S7-05) runs the real binaries.

## Implementation outline

For each scanner file, structure mirrors:

```python
# 1. Module docstring (deferral discipline + arch references)
# 2. Per-scanner Pydantic Finding model (frozen, extra="forbid")
# 3. Per-scanner slice model (carrying ScannerOutcome + scanner-specific metadata)
# 4. Per-scanner smart constructor (parse_X_stdout(raw) -> Result[list[Finding], ParseError])
# 5. Probe class with _run that does the five-step shape inline
```

Concretely:

1. `semgrep.py` (~150 LOC):
   - `SemgrepFinding` with `check_id: str, path: str, line: int, severity: Literal["info","warning","error"], message: str`.
   - `SemgrepSlice` with `outcome: ScannerOutcome, rules_run: int | None, files_scanned: int | None`.
   - `parse_semgrep_stdout(raw) -> Result[tuple[list[SemgrepFinding], int, int], ParseError]` — also extracts `rules_run` + `files_scanned` from semgrep's `paths.scanned` + `paths.skipped`.
   - `SemgrepProbe._run`: call `run_external_cli`; treat exit 0 + exit 1 as parse-stdout; exit ≥ 2 as failure; map to `ScannerOutcome`.

2. `ast_grep.py` (~120 LOC):
   - `AstGrepFinding` with `file: str, line: int, message: str, rule_id: str`.
   - NDJSON parser (one finding per line).
   - Default error convention (non-zero = failure).

3. `ripgrep_curated.py` (~150 LOC):
   - `_CURATED_PATTERNS: Final[tuple[str, ...]] = ("/bin/", "/usr/bin/", "/sbin/", r"exec\(", r"spawn\(", r"execSync\(", r"process\.platform", r"os\.platform\(", "LD_PRELOAD", "LD_LIBRARY_PATH")` — closed set.
   - `RipgrepFinding` with `pattern: str, file: str, line: int, snippet: str`.
   - NDJSON parser; ripgrep emits `{"type": "match", "data": {...}}` per line.

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/probes/layer_g/test_semgrep.py
"""Unit tests for SemgrepProbe (S6-06)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from codegenie.probes.base import ProbeContext, _PROBE_REGISTRY
from codegenie.probes.layer_g import semgrep as sg
from codegenie.probes._shared.scanner_outcome import ScannerRan, ScannerSkipped, ScannerFailed


def test_semgrep_metrics_off_is_mandatory_in_argv(fp) -> None:
    """AC-5. Mutation caught: dropping `--metrics=off` would let
    semgrep phone home — the test pins the argv via `pytest-subprocess`
    capture."""
    fp.register(
        ["semgrep", "--config", fp.any(), "--json", "--metrics=off", "--quiet", fp.any()],
        stdout=json.dumps({"results": [], "paths": {"scanned": [], "skipped": []}}).encode(),
        returncode=0,
    )
    ctx = ProbeContext.for_test(repo_root=Path("/tmp/repo"))
    output = sg.SemgrepProbe()._run(ctx)
    # The fp recorder rejects if argv doesn't match exactly.
    assert output.confidence in ("high", "medium")


def test_semgrep_exit_code_1_is_findings_not_failure(fp) -> None:
    """AC-15. Mutation caught: a shared ScannerRunner that defaults
    "non-zero exit = ScannerFailed" would mis-classify semgrep
    findings-present runs."""
    fp.register(
        ["semgrep", fp.any(), fp.any(), fp.any(), fp.any(), fp.any(), fp.any()],
        stdout=json.dumps({
            "results": [{
                "check_id": "p/nodejs.eval-detected",
                "path": "src/loader.ts",
                "start": {"line": 42},
                "extra": {"severity": "ERROR", "message": "eval call"},
            }],
            "paths": {"scanned": ["src/loader.ts"], "skipped": []},
        }).encode(),
        returncode=1,  # findings present
    )
    ctx = ProbeContext.for_test(repo_root=Path("/tmp/repo"))
    output = sg.SemgrepProbe()._run(ctx)
    slice_ = sg.SemgrepSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerRan)
    assert len(slice_.outcome.findings) == 1
    assert slice_.outcome.findings[0].check_id == "p/nodejs.eval-detected"


def test_semgrep_exit_code_2_is_failure(fp) -> None:
    """AC-15. Mutation caught: treating exit code 2 as findings
    (parse-then-emit-empty) would mask real configuration errors."""
    fp.register(
        ["semgrep", fp.any(), fp.any(), fp.any(), fp.any(), fp.any(), fp.any()],
        stdout=b"",
        stderr=b"Error: invalid rule config",
        returncode=2,
    )
    ctx = ProbeContext.for_test(repo_root=Path("/tmp/repo"))
    output = sg.SemgrepProbe()._run(ctx)
    slice_ = sg.SemgrepSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 2


def test_semgrep_invalid_json_yields_scanner_failed(fp) -> None:
    """AC-12. Mutation caught: silent ValidationError swallow."""
    fp.register(
        ["semgrep", fp.any(), fp.any(), fp.any(), fp.any(), fp.any(), fp.any()],
        stdout=b"not json at all",
        returncode=0,
    )
    output = sg.SemgrepProbe()._run(ProbeContext.for_test(repo_root=Path("/tmp/repo")))
    slice_ = sg.SemgrepSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerFailed)
    assert "invalid_json" in slice_.outcome.stderr_tail


def test_semgrep_tool_missing_yields_scanner_skipped(monkeypatch) -> None:
    """AC-10. Mutation caught: raising past the probe boundary."""
    from codegenie.exec import ToolMissingError

    def raise_missing(*args, **kwargs):
        raise ToolMissingError("semgrep")

    monkeypatch.setattr("codegenie.probes.layer_g.semgrep.run_external_cli", raise_missing)
    output = sg.SemgrepProbe()._run(ProbeContext.for_test(repo_root=Path("/tmp/repo")))
    slice_ = sg.SemgrepSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerSkipped)
    assert slice_.outcome.reason == "tool_missing"
    assert output.confidence == "low"


def test_semgrep_timeout_seconds_is_60() -> None:
    """AC-4. Mutation caught: any timeout change would be visible here."""
    assert sg.SemgrepProbe.timeout_seconds == 60


def test_registry_heaviness_is_medium() -> None:
    """AC-3. Mutation caught: bumping to "heavy" would cost the
    coordinator the runs_last slot."""
    assert _PROBE_REGISTRY["semgrep"].heaviness == "medium"
```

```python
# tests/unit/probes/layer_g/test_scanner_loc_ceiling.py
"""Architectural tests for Layer G scanners (S6-06)."""
from __future__ import annotations

import ast
import importlib
import inspect

import pytest

SCANNER_MODULES = [
    "codegenie.probes.layer_g.semgrep",
    "codegenie.probes.layer_g.ast_grep",
    "codegenie.probes.layer_g.ripgrep_curated",
]


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_each_scanner_under_200_loc(module_path: str) -> None:
    """AC-2. Mutation caught: a scanner creeping past 200 LOC is the
    signal that either the scanner's contract is complex enough to
    warrant a split, OR a shared kernel is overdue. The ceiling forces
    the conversation."""
    mod = importlib.import_module(module_path)
    src_path = inspect.getsourcefile(mod)
    assert src_path is not None
    line_count = sum(1 for _ in open(src_path))
    assert line_count <= 200, f"{module_path} has {line_count} LOC"


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_shared_scanner_base_class_import(module_path: str) -> None:
    """AC-8. Mutation caught: a future contributor extracting a
    `ScannerRunner` / `BaseScanner` base class — final-design
    Design-patterns row 7 forbids it."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    for forbidden in ("ScannerRunner", "BaseScanner", "AbstractScanner"):
        assert forbidden not in src, (
            f"{module_path} references {forbidden!r}; the final-design table "
            "row 7 forbids this abstraction (SRP + Rule of Three)."
        )


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_cross_scanner_imports(module_path: str) -> None:
    """AC-8. Mutation caught: importing one scanner from another."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    for sibling in SCANNER_MODULES:
        if sibling == module_path:
            continue
        assert sibling not in src


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_direct_subprocess_calls(module_path: str) -> None:
    """AC-16. Mutation caught: bypassing run_external_cli would skip
    env-strip, the 64 MB cap, and the asyncio timeout."""
    mod = importlib.import_module(module_path)
    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr in {"run", "Popen", "create_subprocess_exec", "create_subprocess_shell"}:
                # Check if the value is `subprocess` or `asyncio`.
                if isinstance(node.value, ast.Name) and node.value.id in {"subprocess", "asyncio"}:
                    pytest.fail(f"{module_path} calls {node.value.id}.{node.attr} directly")


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_each_scanner_routes_through_run_external_cli(module_path: str) -> None:
    """AC-16. Mutation caught: any future direct invocation that
    bypasses the chokepoint."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    assert "run_external_cli" in src
```

Equivalent test files `test_ast_grep.py` and `test_ripgrep_curated.py` mirror the semgrep file but with their per-scanner argv, stdout shapes, and the default-error convention (non-zero = failure, no exit-code-1-is-findings carve-out).

### Green — make it pass

Skeleton for `semgrep.py` (~150 LOC):

```python
# src/codegenie/probes/layer_g/semgrep.py
"""SemgrepProbe — Layer G, medium heaviness.

Invokes semgrep via run_external_cli (S1-07). Treats exit code 1 as
"findings present" (semgrep's documented convention) and exit code
>= 2 as actual failure — the carve-out the shared-ScannerRunner
abstraction WOULD obscure. Final-design Design-patterns row 7.

Sources:
- ../phase-arch-design.md §"Component design" #5.
- ../../localv2.md §5.6 G1.
- ../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from codegenie.exec import ProcessResult, ToolMissingError, run_external_cli
from codegenie.ids import ProbeId
from codegenie.probes._shared.scanner_outcome import (
    ScannerFailed,
    ScannerOutcome,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, register_probe

__all__ = ["SemgrepProbe", "SemgrepFinding", "SemgrepSlice"]


class SemgrepFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    check_id: str
    path: str
    line: int
    severity: Literal["info", "warning", "error"]
    message: str


class SemgrepSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: ScannerOutcome
    rules_run: int | None
    files_scanned: int | None


def _parse(raw: bytes) -> tuple[tuple[SemgrepFinding, ...], int, int] | str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return f"invalid_json: {str(e)[:200]}"
    try:
        findings = tuple(
            SemgrepFinding(
                check_id=r["check_id"],
                path=r["path"],
                line=r["start"]["line"],
                severity=r["extra"]["severity"].lower(),
                message=r["extra"]["message"],
            )
            for r in data.get("results", [])
        )
    except (KeyError, ValidationError) as e:
        return f"invalid_json: {str(e)[:200]}"
    paths = data.get("paths", {})
    return findings, len(paths.get("scanned", [])), len(set(f.check_id for f in findings))


@register_probe(heaviness="medium")
class SemgrepProbe(Probe):
    probe_id = ProbeId("semgrep")
    applies_to_tasks: tuple[str, ...] = ("*",)
    applies_to_languages: tuple[str, ...] = ("*",)
    timeout_seconds = 60

    def _run(self, ctx: ProbeContext) -> ProbeOutput:
        config_path = self._config_path(ctx)
        try:
            result: ProcessResult = run_external_cli(
                "semgrep",
                ["--config", str(config_path), "--json", "--metrics=off", "--quiet",
                 str(ctx.repo_root)],
                timeout_seconds=self.timeout_seconds,
            )
        except ToolMissingError:
            return self._wrap(
                ScannerSkipped(reason="tool_missing"), rules_run=None, files_scanned=None,
                confidence="low",
            )
        # Semgrep: exit 0 or 1 = success (findings or no findings); >= 2 = error.
        if result.exit_code >= 2:
            return self._wrap(
                ScannerFailed(exit_code=result.exit_code, stderr_tail=result.stderr_tail),
                rules_run=None, files_scanned=None, confidence="low",
            )
        parsed = _parse(result.stdout)
        if isinstance(parsed, str):
            return self._wrap(
                ScannerFailed(exit_code=result.exit_code, stderr_tail=parsed),
                rules_run=None, files_scanned=None, confidence="low",
            )
        findings, files_scanned, rules_run = parsed
        return self._wrap(
            ScannerRan(findings=list(findings)),
            rules_run=rules_run, files_scanned=files_scanned, confidence="high",
        )

    def _wrap(self, outcome: ScannerOutcome, *, rules_run: int | None,
              files_scanned: int | None, confidence: str) -> ProbeOutput:
        slice_ = SemgrepSlice(outcome=outcome, rules_run=rules_run, files_scanned=files_scanned)
        return ProbeOutput(
            probe_id=self.probe_id, confidence=confidence,
            schema_slice=slice_.model_dump(mode="json"), errors=[],
        )

    def _config_path(self, ctx: ProbeContext) -> Path:
        # Default to the curated rule packs; operator override via ctx.config.
        return Path(ctx.config.get("semgrep_config", "p/nodejs"))
```

`ast_grep.py` and `ripgrep_curated.py` mirror this shape — distinct Pydantic models, distinct argv, distinct stdout parsers, distinct error conventions (both default "non-zero = failure"). **None imports the other.**

### Refactor

- **Do not extract a `_call_scanner(name, argv, timeout) -> ScannerOutcome` helper** — even though it would deduplicate the `try: run_external_cli except ToolMissingError` block. The carve-out for semgrep's exit code 1 makes a generic wrapper either incorrect (treating exit 1 as failure for everyone) or parameterized to the point of being unreadable. Inline is the right shape.
- The `SemgrepSlice` / `AstGrepSlice` / `RipgrepCuratedSlice` models share the `outcome: ScannerOutcome` field — that's the discriminated union from S5-01 (the shared kernel). They do not share other fields; `rules_run` and `files_scanned` are semgrep-specific.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_g/__init__.py` | New file — package marker. |
| `src/codegenie/probes/layer_g/semgrep.py` | New file ≤ 200 LOC. |
| `src/codegenie/probes/layer_g/ast_grep.py` | New file ≤ 200 LOC. |
| `src/codegenie/probes/layer_g/ripgrep_curated.py` | New file ≤ 200 LOC. |
| `tests/unit/probes/layer_g/__init__.py` | New file — empty marker. |
| `tests/unit/probes/layer_g/test_semgrep.py` | New file — 7 tests. |
| `tests/unit/probes/layer_g/test_ast_grep.py` | New file — 5 tests (default error convention). |
| `tests/unit/probes/layer_g/test_ripgrep_curated.py` | New file — 5 tests (NDJSON parser + curated-pattern set). |
| `tests/unit/probes/layer_g/test_scanner_loc_ceiling.py` | New file — 5 parametrized architectural tests across all three modules. |

## Out of scope

- **`GitleaksProbe`.** S6-07 (load-bearing security scanner; isolated so review pressure doesn't collapse the four into a shared abstraction).
- **`TestCoverageMappingProbe`.** S6-08 (Layer G but a different shape — reads coverage data, not a CLI tool with a scanning convention).
- **Custom rule pack authoring.** This story uses the curated packs (`p/nodejs`, `p/dockerfile`, etc.); the `semgrep_config` is overridable via `ctx.config["semgrep_config"]`.
- **Cross-validation between semgrep + ast-grep findings.** Each scanner emits independently; the Planner correlates if it wants.
- **`SecretRedactor` invocation.** That's the writer chokepoint's job (S3-03). The probes return raw findings; the writer redacts before disk.

## Notes for the implementer

1. **The "no shared ScannerRunner" discipline is the story's whole point.** A reviewer who asks "why is this duplicated" gets the same answer the design table gives: Rule of Three + four genuinely different I/O shapes + semgrep's exit-code-1-is-findings carve-out. If you find yourself writing the third copy and reaching for a base class, **the right move is to write the third copy** and move on. The fourth copy (gitleaks, S6-07) lives in its own story to make the discipline visible in the PR queue.
2. **`run_external_cli` is the *only* subprocess door.** Direct `subprocess.run` calls bypass env strip + the 64 MB cap + the bubblewrap wrap. AC-16 enforces this; the architectural test fires immediately on any future violation.
3. **`--metrics=off` for semgrep is non-negotiable.** Without it, semgrep phones home to `metrics.semgrep.dev`. The argv-introspection test (AC-5) is what makes this mutation-resistant: any future `argv.remove("--metrics=off")` fires immediately.
4. **`pytest-subprocess` mocks at the subprocess layer, not at `run_external_cli`.** This is deliberate: it exercises the wrapper as well as the probe. A future contributor who refactors `run_external_cli` will have the scanner tests catch any subprocess-argv drift.
5. **Semgrep's exit-code convention is the load-bearing example.** Exit 0 = no findings, parsed normally. Exit 1 = findings present, parsed normally. Exit 2+ = error, no parse. The shared-`ScannerRunner` abstraction would either (a) lose this nuance and treat exit 1 as failure (silent bug), or (b) parameterize the success-codes per scanner (which is the inline-conditional in different syntax). Inline is honest.
6. **Ripgrep's curated pattern set is closed.** Adding a new pattern is a code change with a test fixture, not a config option. The pattern list lives in `_CURATED_PATTERNS` as a `Final[tuple[...]]` — a future contributor adding patterns must update both the constant and the test.
7. **`--max-count 100` on ripgrep is per-pattern, per-file.** Without it, a `LD_LIBRARY_PATH` hit in 5,000 files would emit 5,000 JSON lines and breach the 64 MB cap. The cap is policy ("scanner is meant to be a flag, not exhaustive"); operators wanting exhaustive results run `rg` themselves.
8. **`ast-grep --json=stream` over `--json=compact`.** Stream emits one JSON object per line (NDJSON); compact emits a single buffered array. NDJSON peak memory is O(one finding); compact is O(all findings). The 64 MB cap is on the *wire*, but stream lets the probe parse incrementally — a future enhancement, not a Phase-2 requirement, but the flag choice keeps the door open.
9. **`ScannerOutcome` is the shared sum type (S5-01); each scanner's `Finding` model is NOT.** The discipline is: share the **outcome** (typed sum across all scanners), don't share the **inputs** (different field shapes per scanner). That's the right level of abstraction; a `BaseFinding` class with `file: str, line: int` would force every scanner's quirks into a lowest common denominator.
10. **`mypy --strict` + `--warn-unreachable`** is what makes the `match outcome:` blocks in the consumer (`confidence_section.py`) exhaustive. The three slice models keep `ScannerOutcome` as the typed field; consumers `match` against the discriminator; the `assert_never` path catches a missed variant statically.
