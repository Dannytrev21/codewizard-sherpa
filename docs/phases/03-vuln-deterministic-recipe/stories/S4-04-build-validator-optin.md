# Story S4-04 — `build_validator` — opt-in `npm run build` under `scripts.build` presence

**Step:** Step 4 — Ship `LockfilePolicyScanner` (graded escape) and the single-profile `ValidationGate` (install/test/build + signal-escalate)
**Status:** Ready
**Effort:** S
**Depends on:** S4-02 (`install_validator` pattern + `tools/npm` wrapper shape), S1-06 (sandbox overlay), S1-07 (audit event types)
**ADRs honored:** ADR-0005 (single sandbox profile, `test_execution=False` for build), ADR-0010 (audit chain extension), ADR-0013 (strict-AND signals — build is a non-required signal in v0.3.0 but emitted for Phase 4 RAG)

## Context

`build_validator` is the third gate sub-validator, opt-in by presence of `package.json#scripts.build`. Most Node libraries have it (`tsc`, `vite`, `webpack`); most Node services do not. Running it when absent would noise the gate; running it when present catches type errors and bundling regressions that `npm test` can miss (`final-design.md §"Components" #7`). The validator mirrors the install validator's sandbox shape (`network="scoped"`, `test_execution=False`) — most builds don't need network beyond what `npm ci` already did, but a few (e.g., `webpack-bundle-analyzer` posting telemetry) reach out.

This is the lightest validator in Step 4: same `tools/npm` wrapper, same `run_in_sandbox` overlay, no signal-escalate path (no honest-failure escape; a non-zero build = exit 6, full stop). The cross-cutting concern is the opt-in shape — when `scripts.build` is absent, the validator returns a `"skipped"`-flavored `ValidatorOutput` cleanly so the `TrustScorer` (S4-05) does not penalize the run.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #11 ValidationGate — Install / Test / Build validators` — `build_validator` row (opt-in via `scripts.build`; same sandbox as install; `network="scoped"`).
  - `../phase-arch-design.md §"Edge cases"` row #5 — build failure → exit 6.
- **Phase ADRs:**
  - `../ADRs/0005-single-sandbox-profile-test-execution-overlay-signal-escalate.md` — ADR-0005 — build validator runs `test_execution=False`, `network="scoped"`; same chokepoint.
  - `../ADRs/0010-audit-chain-extension-cache-replay-event.md` — ADR-0010 — audit event for build invocations: `npm.install.run` event can be reused with `mode: "run_build"` *or* a dedicated `npm.build.run` event; this story ships **`npm.install.run` with `mode: "run_build"`** to avoid expanding the event vocabulary mid-step (mechanical decision; the ADR-0010 closed-enum is the source of truth).
  - `../ADRs/0013-confidence-strict-and-of-binary-signals-no-llm.md` — ADR-0013 — build is *not* in the strict-AND-required-signal set (the nine signals are install + test focused). However, on build failure, `TrustScorer` reads `signals["npm.build.exit_status"] != 0` via `recipe.engine.exit_status == 0` upstream propagation — see S4-05 for the wiring choice.
- **Production ADRs:**
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — objective-signal-only confidence; build is one such signal once present.
- **Source design:**
  - `../final-design.md §"Components" #7 ValidationGate` — build validator opt-in semantics.
- **Existing code:**
  - `src/codegenie/transforms/validation/install.py` (S4-02) — mirror this shape.
  - `src/codegenie/tools/npm.py` (S3-01) — add `run_npm_run(script_name, ...)` wrapper invocation if not already shipped; otherwise reuse the existing generic-script entry point.
  - `src/codegenie/transforms/contract.py` (S1-02) — `ValidatorOutput`.

## Goal

Implement `src/codegenie/transforms/validation/build.py` exposing `build_validator(transform_output) -> ValidatorOutput` that detects `package.json#scripts.build`, runs `npm run build` through the Phase-2 `run_in_sandbox` chokepoint (`network="scoped"`, `test_execution=False`) when present, and returns a `"skipped"`-flavored `ValidatorOutput(passed=True, confidence="high", signals={"build.skipped": True})` when absent — cleanly, without penalizing the gate.

## Acceptance criteria

- [ ] `build_validator(transform_output: TransformOutput, *, wall_timeout_s: int = 300) -> ValidatorOutput` is defined and importable from `codegenie.transforms.validation.build`.
- [ ] The function reads `package.json` from `transform_output.worktree_root`; if the file is missing, raise `FileNotFoundError` (loud — every Node repo has `package.json`; absence is a Phase-2 gather-level bug, not a build-validator concern).
- [ ] If `package.json#scripts.build` is absent or empty-string: return `ValidatorOutput(name="build", passed=True, stdout_path=Path("/dev/null"), stderr_path=Path("/dev/null"), duration_ms=0, confidence="high", signals={"build.skipped": True, "npm.build.exit_status": 0}, warnings=["scripts.build absent; build validator skipped cleanly"], errors=[])`. **No audit event emitted** in the skipped branch (no subprocess ran).
- [ ] If `scripts.build` is present: route through `codegenie.tools.npm.run_npm_run("build", cwd=transform_output.worktree_root, timeout_s=wall_timeout_s, network="scoped", scoped_egress_hosts=("registry.npmjs.org",), test_execution=False, stdout_to=..., stderr_to=...)`.
- [ ] On `scripts.build` present, the validator emits one audit event: `npm.install.run` with payload `{mode: "run_build", exit_code, wall_ms, egress_bytes}` (mode `"run_build"` is added to the closed enum on `NpmInstallRunPayload.mode` Pydantic model — closed-enum update lands in S1-07; if not, this story includes a one-line additive PR to the audit schema).
- [ ] `ValidatorOutput.name == "build"`, `passed = exit_code == 0`, `stdout_path` / `stderr_path` point at `.codegenie/remediation/<run-id>/raw/build.{stdout,stderr}.log`, `confidence = "high" if passed else "low"`, `signals = {"npm.build.exit_status": exit_code, "npm.build.wall_ms": wall_ms, "build.skipped": False}`.
- [ ] No signal-escalate path — `requires_network` is always `False` for build. A non-zero build = exit 6 territory (orchestrator-side); this validator just signals.
- [ ] Wall-clock default = 300 s (5 min) — most builds are 5–60 s; outliers exist; `webpack` cold-cache can spike. Operator can raise via per-repo config (defer to Phase 5).
- [ ] `tests/unit/transforms/validation/test_build.py` ships ≥ 4 tests: (a) `scripts.build` absent → `passed=True`, `confidence="high"`, `signals["build.skipped"]==True`, no audit event; (b) `scripts.build` present + happy build → `passed=True`, `confidence="high"`, audit event emitted with `mode="run_build"`; (c) `scripts.build` present + failure → `passed=False`, `confidence="low"`; (d) sandbox shape: assert mock-captured `run_npm_run` kwargs include `network="scoped"` + `test_execution=False`.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write the failing tests under `tests/unit/transforms/validation/test_build.py`. Mock `codegenie.tools.npm.run_npm_run`. Use `tmp_path` to write `package.json` fixtures inline.
2. Create `src/codegenie/transforms/validation/build.py`. Import `TransformOutput`, `ValidatorOutput` from `transforms.contract`.
3. Define `build_validator(transform_output, *, wall_timeout_s=300)`:
   - Read `package.json` from `transform_output.worktree_root / "package.json"`; `json.loads`.
   - Branch on `scripts.build` presence + truthiness. Absent or `""` → skipped path.
   - Skipped path: return the `passed=True`, `build.skipped=True` `ValidatorOutput`. No audit emit.
   - Present path: resolve log paths under `.codegenie/remediation/<run-id>/raw/build.{stdout,stderr}.log`. Call `run_npm_run("build", ...)` with the sandbox shape above.
   - Compute `signals`, `confidence`, emit `npm.install.run` audit event with `mode="run_build"`.
   - Return `ValidatorOutput`.
4. If `NpmInstallRunPayload.mode` doesn't yet include `"run_build"` in its `Literal[...]` enum, extend it in `src/codegenie/audit/events.py` (the cross-cutting `additionalProperties: false` + `schema_version: "v1"` discipline applies — closed enum, all consumers must compile against the same set).
5. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/transforms/validation/build.py tests/unit/transforms/validation/test_build.py`, `pytest tests/unit/transforms/validation/test_build.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Path: `tests/unit/transforms/validation/test_build.py`

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from codegenie.transforms.contract import TransformOutput
from codegenie.transforms.validation.build import build_validator


def _output_with_package(tmp: Path, scripts: dict[str, str] | None) -> TransformOutput:
    pkg = {"name": "fixture", "version": "1.0.0"}
    if scripts is not None:
        pkg["scripts"] = scripts
    (tmp / "package.json").write_text(json.dumps(pkg))
    return TransformOutput(
        name="npm_package_upgrade", diff_path=tmp / "p.patch",
        branch_name="codegenie/vuln-fix/CVE-2024-0001-abc1234",
        files_changed=[], confidence="high",
        worktree_root=tmp, run_id="run-1",
    )


def test_build_skipped_when_scripts_build_absent(tmp_path: Path) -> None:
    with patch("codegenie.audit.writer.append") as audit:
        out = build_validator(_output_with_package(tmp_path, scripts={"test": "jest"}))
    assert out.passed is True
    assert out.confidence == "high"
    assert out.signals["build.skipped"] is True
    # No audit event emitted on the skipped path
    assert audit.call_count == 0


def test_build_runs_when_scripts_build_present(tmp_path: Path) -> None:
    with patch("codegenie.tools.npm.run_npm_run") as run, \
         patch("codegenie.audit.writer.append") as audit:
        run.return_value = MagicMock(exit_code=0, wall_ms=4567, egress_bytes=0)
        out = build_validator(_output_with_package(tmp_path, scripts={"build": "tsc"}))
    assert out.passed is True
    assert out.confidence == "high"
    assert out.signals["build.skipped"] is False
    # Audit event emitted with mode="run_build"
    payload = next(c.kwargs["payload"] for c in audit.call_args_list
                   if c.args[0] == "npm.install.run")
    assert payload.mode == "run_build"


def test_build_failure_low_confidence(tmp_path: Path) -> None:
    with patch("codegenie.tools.npm.run_npm_run") as run:
        run.return_value = MagicMock(exit_code=2, wall_ms=1500, egress_bytes=0)
        out = build_validator(_output_with_package(tmp_path, scripts={"build": "tsc"}))
    assert out.passed is False
    assert out.confidence == "low"


def test_build_uses_scoped_network_test_execution_false(tmp_path: Path) -> None:
    with patch("codegenie.tools.npm.run_npm_run") as run:
        run.return_value = MagicMock(exit_code=0, wall_ms=1, egress_bytes=0)
        build_validator(_output_with_package(tmp_path, scripts={"build": "tsc"}))
    kwargs = run.call_args.kwargs
    assert kwargs["network"] == "scoped"
    assert kwargs["test_execution"] is False
    assert kwargs["scoped_egress_hosts"] == ("registry.npmjs.org",)
```

Run; confirm `ImportError`. Commit red marker.

### Green — smallest impl shape

- Body is ~25 lines. The skipped branch is the first early return.
- Use `json.loads((worktree_root / "package.json").read_text())` — no `package.json` parser library needed.
- `scripts = pkg.get("scripts") or {}`; `build_cmd = scripts.get("build") or ""`; `if not build_cmd: <skipped>`.

### Refactor — bounded

- Module-level `_DEFAULT_BUILD_WALL_S: Final[int] = 300`.
- Reuse the `_log_paths(transform_output, name)` helper extracted in S4-02 (if S4-02 didn't extract it, this story may add the helper under `transforms/validation/_paths.py`).
- The `mode="run_build"` audit-event literal stays a single source of truth in `audit/events.py` enum; this validator imports it.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/validation/build.py` | New — `build_validator` function |
| `src/codegenie/audit/events.py` | One-line additive — extend `NpmInstallRunPayload.mode` `Literal[...]` to include `"run_build"` (if not already in S1-07) |
| `tests/unit/transforms/validation/test_build.py` | New — 4 tests (skipped + happy + fail + sandbox shape) |
| `src/codegenie/transforms/validation/_paths.py` | Optional — extract shared log-path resolution if S4-02 didn't |

## Out of scope

- **Trust scoring integration** — S4-05 reads `signals["npm.build.exit_status"]` if non-skipped; build failure feeds the `low` confidence path via the broader gate orchestration logic.
- **Build-failure exit-code mapping (exit 6)** — orchestrator-side; S5-03 + S5-05.
- **Build-specific cache (e.g., webpack persistent cache)** — out of Phase 3 scope; Phase 5+ optimization territory.
- **Build that requires unscoped network** — explicitly defer; if a real fixture needs broader network, ADR-0005 amendment + new validator config, not a silent widening here.
- **CLI flag to force-skip the build validator** — not needed in v0.3.0; the `scripts.build` presence check is the operator's contract.
- **Audit event renaming to `npm.build.run`** — mechanical decision deferred; reusing `npm.install.run` with `mode="run_build"` keeps ADR-0010's closed-enum vocabulary tight. A dedicated event can ship in Phase 4 if RAG retrieval finds the conflated mode confusing.

## Notes for the implementer

- **The skipped path is the most common one.** Most service repos don't have `scripts.build`. Make sure the skipped path is the cheap, audit-event-free, early-return path. Do not emit a `tests.skipped`-style audit event — the cross-cutting "facts not judgments" stance is that *absence* of build is not a fact worth recording; it's a non-event.
- **No signal-escalate path.** Build failures never escalate. A non-zero build = exit 6 (full stop), no `--allow-test-network`-style retry surface. The test validator's network-required signal is unique to that validator; do not generalize it here even if you spot a `getaddrinfo` pattern in build stderr. If a build legitimately needs unscoped network, that's an ADR-0005 amendment, not a per-validator hack.
- **`mode="run_build"` is the audit-event vocabulary choice.** Reusing `npm.install.run` with a discriminator field is mechanically cleaner than a new event type — the audit chain (ADR-0010) closes the event vocabulary tightly; every new event adds an ADR amendment. If the discriminator confuses Phase 4 RAG retrieval later, a dedicated `npm.build.run` event can ship then; not now.
- **`egress_bytes` on build is usually 0** — `npm run build` after `npm ci` should not hit `registry.npmjs.org`. If the audit log shows non-zero egress, that's an interesting signal — surface it to the runbook (S7-07). The strict-AND `TrustScorer` (S4-05) does NOT have a `npm.build.disallowed_egress_bytes == 0` signal in the closed-nine set; that's an intentional Phase-3 scope decision. Phase 4 may add it; ADR-0013 amendment.
- **`package.json` must exist.** Raise `FileNotFoundError` loud — every Node repo has one. If Phase 2's `NodeManifest` probe somehow let through a repo without `package.json`, that's a Phase 2 bug; we surface it here, not paper over it (Rule 12 — fail loud).
- **Wall budget 300 s.** Builds outside this budget exist (e.g., monorepo webpack cold); they fail and the operator re-runs with a longer budget. Do not auto-extend. The S7-04 perf canary asserts hot-path p95 ≤ 30 s *excluding the test suite* — build is on the hot path; if it dominates wall time on the fixture portfolio, the canary will flag it.
- **`run_npm_run("build", ...)` is the wrapper entry point.** S3-01 ships `run_npm_ci` and `run_npm_test`; if `run_npm_run(script_name, ...)` isn't already there, this story adds the wrapper signature — one short function that mirrors the others. The wrapper-level `--ignore-scripts` invariant is preserved (build scripts are *not* lifecycle scripts; `--ignore-scripts` only affects `pre/install/post`-install hooks, which `npm run build` doesn't trigger). Cross-check the wrapper docstring.
