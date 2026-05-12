# Story S4-02 — `install_validator` — `npm ci --ignore-scripts` in single-profile sandbox with `egress_bytes` audit

**Step:** Step 4 — Ship `LockfilePolicyScanner` (graded escape) and the single-profile `ValidationGate` (install/test/build + signal-escalate)
**Status:** Ready
**Effort:** M
**Depends on:** S3-08 (`LockfileResolver` + `cache.replay`), S1-06 (`run_in_sandbox(test_execution=True)` overlay), S3-01 (`tools/npm` wrapper + `NpmScriptsEnabled` guard), S1-07 (audit event types)
**ADRs honored:** ADR-0005 (single sandbox profile), ADR-0010 (audit chain extension), ADR-0014 (`ALLOWED_BINARIES += npm`)

## Context

Stage 6 of the orchestrator verifies a candidate diff installs cleanly inside the same Phase-2 `run_in_sandbox` chokepoint that gathers facts in Phases 0–2 (`final-design.md §"Components" #7`). The install validator is the *first* of the three gate sub-validators (install → test → build); it is the simplest because the install command itself is deterministic and the sandbox profile is the same as Phase 2's scoped-network shape (registry allowlist, `--ignore-scripts` ON).

The single load-bearing wrinkle is `egress_bytes` — the audit chain (ADR-0010) records bytes-over-registry-network for every install, so the `TrustScorer` (S4-05) can read `npm.install.disallowed_egress_bytes == 0` as one of the nine strict-AND signals. Performance-first proposed eliding the install validation behind a fast-path subset; the critic dismantled it; this story is the safety-first stance.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #11 ValidationGate — Install / Test / Build validators` — `install_validator` row.
  - `../phase-arch-design.md §"Goals" #12` — single sandbox profile + `test_execution=False` for install.
  - `../phase-arch-design.md §"Edge cases"` row #3 — non-zero install exit closes the gate without signal-escalate.
- **Phase ADRs:**
  - `../ADRs/0005-single-sandbox-profile-test-execution-overlay-signal-escalate.md` — ADR-0005 — `install_validator` runs with `network="scoped"`, `allowlist=["registry.npmjs.org"]`, `--ignore-scripts` ON.
  - `../ADRs/0010-audit-chain-extension-cache-replay-event.md` — ADR-0010 — `npm.install.run` event payload `{mode, exit_code, wall_ms, egress_bytes}`.
  - `../ADRs/0014-allowed-binaries-additions-npm-ncu-java.md` — ADR-0014 — `npm` is in `ALLOWED_BINARIES` since S1-05.
- **Production ADRs:**
  - `../../../production/adrs/0019-sandbox-stack.md` — chokepoint preservation; Phase 5 microVM swap at the same seam.
- **Source design:**
  - `../final-design.md §"Components" #7 ValidationGate` — install validator semantics.
  - `../final-design.md §"Components" §7 stage 6` — Stage 6 sequencing.
- **Existing code:**
  - `src/codegenie/exec.py` (Phases 0/1/2 + S1-06 overlay) — `run_in_sandbox(network="scoped", test_execution=False, allowlist=[...])`.
  - `src/codegenie/tools/npm.py` (S3-01) — typed `npm` wrapper enforcing wrapper-level `--ignore-scripts`; raises `NpmScriptsEnabled` if the flag is omitted (except inside `test_execution=True`).
  - `src/codegenie/transforms/contract.py` (S1-02) — `TransformOutput`.
  - `src/codegenie/audit/events.py` (S1-07) — `npm.install.run` Pydantic payload.
  - `src/codegenie/transforms/validation/__init__.py` (created in S4-01).

## Goal

Implement `src/codegenie/transforms/validation/install.py` exposing `install_validator(transform_output: TransformOutput) -> ValidatorOutput` that runs `npm ci --ignore-scripts --no-audit --no-fund` through the Phase-2 `run_in_sandbox` chokepoint with `network="scoped"`, `allowlist=["registry.npmjs.org"]`, `test_execution=False`, captures stdout/stderr to disk, measures `egress_bytes`, and emits the `npm.install.run` audit event.

## Acceptance criteria

- [ ] `install_validator(transform_output: TransformOutput, *, wall_timeout_s: int = 180) -> ValidatorOutput` is defined and importable from `codegenie.transforms.validation.install`.
- [ ] The function reads `transform_output.worktree_root` (or equivalent — the path containing the newly-written `package.json` + `package-lock.json`) and runs `npm ci --ignore-scripts --no-audit --no-fund` from that cwd.
- [ ] The invocation routes through `codegenie.tools.npm.run_npm_ci(...)` (S3-01 wrapper), which itself routes through `run_in_sandbox(..., network="scoped", scoped_egress_hosts=("registry.npmjs.org",), test_execution=False, timeout_s=wall_timeout_s)`. The wrapper's `--ignore-scripts` invariant is preserved.
- [ ] `ValidatorOutput.name == "install"`, `passed` mirrors `exit_code == 0`, `stdout_path` and `stderr_path` point at files under `.codegenie/remediation/<run-id>/raw/install.{stdout,stderr}.log`, `duration_ms` is wall-clock from the wrapper's `ProcessResult`, `confidence` is `"high"` on pass and `"low"` on fail (per ADR-0013 binary-signal posture), `requires_network=False` always (install never escalates — that's exit 6 territory).
- [ ] `signals` dict on `ValidatorOutput` includes at minimum: `npm.install.exit_status: int`, `npm.install.disallowed_egress_bytes: int`, `npm.install.wall_ms: int`. The first two are the strict-AND signals consumed by S4-05's `TrustScorer`.
- [ ] On every invocation, the validator emits exactly one `npm.install.run` audit event with payload `{mode: "ci", exit_code, wall_ms, egress_bytes}` (per ADR-0010 payload).
- [ ] `egress_bytes` is sourced from the sandbox's per-call accounting (Phase 2 ADR-0003 made this a `ProcessResult.egress_bytes` field; if the field isn't present on macOS best-effort mode, record `egress_bytes=-1` and warn — do not lie with `0`).
- [ ] Wall-clock timeout default = 180 s; if `run_in_sandbox` raises `SandboxTimeout`, the validator returns `ValidatorOutput(passed=False, confidence="low", errors=["install timed out"])` and emits the audit event with `exit_code=-1, wall_ms=wall_timeout_s*1000`.
- [ ] The validator never catches generic `Exception`. Sandbox launch failures (`SandboxLaunchError`) propagate to the orchestrator (S5-03 handles non-green exits).
- [ ] `tests/unit/transforms/validation/test_install.py` ships ≥ 4 tests: (a) happy path; (b) non-zero install → `passed=False`, `confidence="low"`, exit 6 hint via `errors`; (c) `network="scoped"` + `allowlist=("registry.npmjs.org",)` argv enforced (mock-asserted on the `run_in_sandbox` call); (d) `npm.install.run` audit event emitted with `egress_bytes` field present.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write the failing test under `tests/unit/transforms/validation/test_install.py`. Mock `codegenie.tools.npm.run_npm_ci` to return canned `ProcessResult` values; capture audit-event emissions via the S1-07 audit-writer mock seam.
2. Create `src/codegenie/transforms/validation/install.py`. Import `TransformOutput`, `ValidatorOutput`, `Confidence` from `transforms.contract`.
3. Define `install_validator(transform_output, *, wall_timeout_s=180)`:
   - Resolve `cwd = transform_output.worktree_root`.
   - Resolve stdout/stderr destination paths under `.codegenie/remediation/<run-id>/raw/install.{stdout,stderr}.log` (mkdir parents).
   - Call `codegenie.tools.npm.run_npm_ci(cwd=cwd, timeout_s=wall_timeout_s, stdout_to=stdout_path, stderr_to=stderr_path)` — the wrapper handles the sandbox wiring + `--ignore-scripts --no-audit --no-fund`.
   - Catch `SandboxTimeout` → fabricate timeout `ProcessResult` shape; emit audit event with `exit_code=-1`.
   - Compute `signals = {"npm.install.exit_status": result.exit_code, "npm.install.disallowed_egress_bytes": max(0, result.egress_bytes), "npm.install.wall_ms": result.wall_ms}`.
   - Determine `confidence`: `"high"` if `exit_code == 0`, else `"low"`.
   - Emit `audit.append(EventName.NPM_INSTALL_RUN, payload=NpmInstallRunPayload(mode="ci", exit_code=..., wall_ms=..., egress_bytes=...))`.
   - Return `ValidatorOutput(name="install", passed=..., stdout_path=..., stderr_path=..., duration_ms=..., confidence=..., signals=signals, warnings=[], errors=[...] if not passed else [])`.
4. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/transforms/validation/install.py tests/unit/transforms/validation/test_install.py`, `pytest tests/unit/transforms/validation/test_install.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Path: `tests/unit/transforms/validation/test_install.py`

```python
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from codegenie.transforms.contract import TransformOutput
from codegenie.transforms.validation.install import install_validator


def _fake_transform_output(worktree: Path) -> TransformOutput:
    return TransformOutput(
        name="npm_package_upgrade",
        diff_path=worktree / "diff.patch",
        branch_name="codegenie/vuln-fix/CVE-2024-0001-abc1234",
        files_changed=["package.json", "package-lock.json"],
        confidence="high",
        worktree_root=worktree,
        run_id="run-1",
    )


def test_install_validator_happy_path(tmp_path: Path) -> None:
    with patch("codegenie.tools.npm.run_npm_ci") as run:
        run.return_value = MagicMock(
            exit_code=0, wall_ms=12345, egress_bytes=4096,
        )
        out = install_validator(_fake_transform_output(tmp_path))
    assert out.passed is True
    assert out.confidence == "high"
    assert out.signals["npm.install.exit_status"] == 0
    assert out.signals["npm.install.disallowed_egress_bytes"] == 4096


def test_install_failure_closes_gate(tmp_path: Path) -> None:
    with patch("codegenie.tools.npm.run_npm_ci") as run:
        run.return_value = MagicMock(exit_code=1, wall_ms=2000, egress_bytes=0)
        out = install_validator(_fake_transform_output(tmp_path))
    assert out.passed is False
    assert out.confidence == "low"
    assert out.errors  # non-empty


def test_install_uses_scoped_network_and_registry_allowlist(tmp_path: Path) -> None:
    with patch("codegenie.tools.npm.run_npm_ci") as run:
        run.return_value = MagicMock(exit_code=0, wall_ms=1, egress_bytes=0)
        install_validator(_fake_transform_output(tmp_path))
    # The wrapper is the seam; assert it was called with the right cwd + timeout.
    kwargs = run.call_args.kwargs
    assert kwargs["cwd"] == tmp_path
    assert kwargs["timeout_s"] == 180


def test_install_emits_audit_event_with_egress_bytes(tmp_path: Path) -> None:
    with patch("codegenie.tools.npm.run_npm_ci") as run, \
         patch("codegenie.audit.writer.append") as audit:
        run.return_value = MagicMock(exit_code=0, wall_ms=42, egress_bytes=2048)
        install_validator(_fake_transform_output(tmp_path))
    events = [c.args[0] for c in audit.call_args_list]
    assert "npm.install.run" in events
    payload = next(c.kwargs["payload"] for c in audit.call_args_list
                   if c.args[0] == "npm.install.run")
    assert payload.egress_bytes == 2048
    assert payload.mode == "ci"
```

Run; confirm `ImportError`. Commit red marker.

### Green — smallest impl shape

- Body is ~30 lines of straight-line code. No abstraction layers.
- Use the S3-01 `run_npm_ci` wrapper directly — do not call `run_in_sandbox` from this module (preserves the chokepoint discipline; the wrapper owns the sandbox shape).
- Audit emission via the S1-07 `audit.writer.append(event_name, payload=...)` API.

### Refactor — bounded

- Lift the stdout/stderr path resolution into a tiny `_log_paths(transform_output) -> tuple[Path, Path]` helper; S4-04 (`build_validator`) will reuse the shape.
- Constant `_DEFAULT_INSTALL_WALL_S: Final[int] = 180` at module top.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/validation/install.py` | New — `install_validator` function |
| `tests/unit/transforms/validation/test_install.py` | New — 4 tests (happy + fail-closed + sandbox shape + audit event) |

## Out of scope

- **Sandbox profile assembly (`bwrap --unshare-net` argv construction)** — owned by S1-02 + S1-06; this story uses the chokepoint.
- **`--ignore-scripts` wrapper-level guard** — owned by S3-01; we consume the wrapper as a black box.
- **Test validator network-required signature scan** — S4-03.
- **Build validator opt-in** — S4-04.
- **Trust scoring + gate orchestration** — S4-05.
- **Exit-code mapping (exit 6 on install failure)** — orchestrator-side; S5-03 + S5-05.
- **`cache.replay` audit event on warm-resolver path** — emitted by S3-08, not by this validator.

## Notes for the implementer

- **The wrapper is the seam, not `run_in_sandbox`.** The cross-cutting "wrapper-enforced `--ignore-scripts`" invariant means every consumer routes through `tools/npm.py`. If you reach for `run_in_sandbox` directly from this module to "save a hop," you break the invariant — and the `test_npm_wrapper_rejects_scripts_enabled.py` adversarial pin (Phase 7) will catch you, but only after merge. Do it right here.
- **`egress_bytes=-1` on macOS best-effort.** Phase 2 ADR-0003 made macOS sandbox-exec network accounting best-effort. Reporting `0` would lie to the `TrustScorer` (S4-05 reads `npm.install.disallowed_egress_bytes == 0` as a green signal). Use `-1` as the "unknown" sentinel and let S4-05's strict-AND fail closed. The cross-platform `signals` dict shape stays the same; the value is the honest signal.
- **`confidence="low"` on any non-zero exit** — even a transient `EAI_AGAIN` install hiccup. Phase 3 has no retry layer (ADR-0006). Phase 5's three-retry wrap will re-run; do not soften here.
- **Wall budget 180 s default.** The cross-cutting fixture portfolio (S7-01) uses tiny `.bundle` repos — install should be 10–30 s warm. If a real repo blows the budget, the operator sees a timeout error and re-runs with a longer budget; do not auto-extend.
- **Don't catch `SandboxLaunchError`.** A sandbox launch failure is a Phase 0/1/2 infrastructure bug, not a validator-level failure. Letting it propagate surfaces the right diagnostic — Rule 12 (Fail loud).
- **`raw/install.{stdout,stderr}.log` paths** are part of the `RemediationReport` schema Phase 4 consumes (S7-06 contract test). If you rename them, S7-06 breaks. The names are load-bearing.
- **`worktree_root` field on `TransformOutput`.** S5-01 (`NpmPackageUpgradeTransform`) populates it. This story consumes it. Cross-check the contract surface in `transforms/contract.py` before writing the test — if the field is named differently, surface the mismatch in your story PR rather than fork it (Rule 11).
