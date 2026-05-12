# Story S4-03 — `test_validator` + `network_signatures.yaml` + `gate.signal_escalate` honest-failure surface

**Step:** Step 4 — Ship `LockfilePolicyScanner` (graded escape) and the single-profile `ValidationGate` (install/test/build + signal-escalate)
**Status:** Ready
**Effort:** L
**Depends on:** S4-02 (`install_validator` pattern), S1-06 (`run_in_sandbox(test_execution=True)` overlay), S1-07 (audit event types), S1-10 (`--allow-test-network` click flag)
**ADRs honored:** ADR-0005 (single sandbox profile + `test_execution=True` overlay + `gate.signal_escalate`), ADR-0010 (audit chain — `tests.executed`, `gate.signal_escalate`), ADR-0013 (no LLM in this loop)

## Context

The `test_validator` is the single most architecturally load-bearing component in Phase 3 — it's where the honest-failure invariant lives. Security-first proposed a HARD `--network=none` wall on `npm test`; the critic dismantled it: a meaningful fraction of real Node test suites need a DB sidecar or DNS, and routing them to a nonexistent human reviewer fails closed at scale (`critique.md §security.4`). Best-practices proposed no sandbox at all; performance-first proposed a fast-path subset that can't survive dynamic `require`. The synth ships **one profile, one overlay flag, network-none default with explicit `gate.signal_escalate`** — per critic recommendation verbatim (ADR-0005).

The architecture explicitly does **NOT** auto-allow egress on signature match. A test failing with `ENOTFOUND` must surface `requires_network=true`, emit `gate.signal_escalate`, and exit 8 — *not* silently widen the sandbox to scoped. The operator re-runs with `--allow-test-network` after review. The cross-cutting "honest-failure invariant" called out in `stories/README.md §Cross-cutting concerns` is exactly this story's contract.

The network-required signature catalog is empirical (Open Question #3); we ship the initial closed set in `src/codegenie/recipes/network_signatures.yaml` so the catalog is version-pinned and operator-auditable. New signatures require code + schema PR in the same change (cross-cutting "pin-manifest discipline" + cross-cutting "schema_version v1" + closed-enum).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #11 ValidationGate — Install / Test / Build validators` — `test_validator` row, network-required signatures list.
  - `../phase-arch-design.md §"Goals" #12` — `test_execution=True` overlay flag.
  - `../phase-arch-design.md §"Edge cases"` row #4 — `requires_network=true` → exit 8, worktree preserved, operator re-runs.
  - `../phase-arch-design.md §"Gap 3"` — `gate.signal_escalate` has no human in the local POC; operator-surface is JSON file + report section + CLI stderr banner.
- **Phase ADRs:**
  - `../ADRs/0005-single-sandbox-profile-test-execution-overlay-signal-escalate.md` — ADR-0005 — `test_validator` runs with `test_execution=True`, `network="none"` default | `"scoped"` if `allow_test_network=True`; signature scan; `--allow-test-network` opt-in; explicit non-auto-allow posture.
  - `../ADRs/0010-audit-chain-extension-cache-replay-event.md` — ADR-0010 — `tests.executed` payload `{exit_code, wall_ms, duration_vs_baseline_pct, requires_network}` + `gate.signal_escalate` payload `{signature_matched, suggested_flag, validator_name}`.
  - `../ADRs/0013-confidence-strict-and-of-binary-signals-no-llm.md` — ADR-0013 — `medium` confidence tier exists *only* for `gate.signal_escalate`; otherwise binary.
- **Production ADRs:**
  - `../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md` — Phase 5 microVM at same chokepoint; `test_execution` overlay translates to microVM resource caps.
- **Source design:**
  - `../final-design.md §"Components" #7 ValidationGate` — `test_validator` semantics + network-signature list.
  - `../final-design.md §"Departures from all three inputs" #3` — synth choice rationale.
  - `../final-design.md §"Open questions"` #3 — network-required signature catalog evolution.
- **Existing code:**
  - `src/codegenie/exec.py` (S1-06 overlay) — `run_in_sandbox(..., test_execution=True, network="none" | "scoped")` overlay shape.
  - `src/codegenie/tools/npm.py` (S3-01) — wrapper-level guard; under `test_execution=True`, `--ignore-scripts` is **OFF** (the test command runs scripts by definition).
  - `src/codegenie/transforms/contract.py` (S1-02) — `ValidatorOutput`, `Confidence`.
  - `src/codegenie/audit/events.py` (S1-07) — `tests.executed`, `gate.signal_escalate` Pydantic payloads.
  - `src/codegenie/cli/__init__.py` (S1-10) — `--allow-test-network` click flag.

## Goal

Implement `src/codegenie/transforms/validation/test.py` exposing `test_validator(transform_output, *, allow_test_network)` that runs `npm test` through the Phase-2 `run_in_sandbox` chokepoint with `test_execution=True` overlay (network `"none"` default | `"scoped"` allowlist if opt-in), scans stderr against the closed-enum `network_signatures.yaml` catalog on non-zero exit, emits `tests.executed` + (on match) `gate.signal_escalate` audit events, and sets `ValidatorOutput.requires_network=true` + `confidence="medium"` without ever auto-widening egress.

## Acceptance criteria

- [ ] `test_validator(transform_output: TransformOutput, *, allow_test_network: bool, wall_timeout_s: int = 600, pid_budget: int = 1024) -> ValidatorOutput` is defined and importable from `codegenie.transforms.validation.test`.
- [ ] Sandbox shape: when `allow_test_network=False`, `run_in_sandbox(..., test_execution=True, network="none")`. When `allow_test_network=True`, `run_in_sandbox(..., test_execution=True, network="scoped", scoped_egress_hosts=<per-repo list>)`. The scoped allowlist initial value is empty (documented as per-run operator decision); if the operator passes `--allow-test-network` without configuring an allowlist, the validator emits a warning and proceeds with an empty allowlist (Phase 5 will harden this; ADR-0005 explicitly defers).
- [ ] `src/codegenie/recipes/network_signatures.yaml` exists, ships the closed initial catalog: `["ENOTFOUND", "ECONNREFUSED", "getaddrinfo", "getaddrinfo EAI_AGAIN", "DNS lookup", "Connection refused 127.0.0.1", "connect ECONNREFUSED", "KafkaTimeout"]` plus three ORM connect strings (`"connection refused"` for postgres, `"NoNodeAvailable"` for cassandra, `"Could not connect to redis"` — explicit, not regex), and ships a top-level `schema_version: "v1"`, `additionalProperties: false` at every nesting level. Each entry is `{name: str, pattern: str, kind: "literal"|"regex", source: str}`.
- [ ] A loader `load_network_signatures(path: Path = DEFAULT_PATH) -> tuple[NetworkSignature, ...]` is defined and Pydantic-validated. Unknown top-level keys raise `ConfigError`.
- [ ] On non-zero `npm test` exit AND `allow_test_network=False`, the validator: (a) reads `stderr` (capped at 1 MiB tail to bound memory), (b) iterates the signature catalog in declaration order, (c) on first match → sets `requires_network=true`, `confidence="medium"`, populates `signals["tests.requires_network"]=True`, `signals["tests.signature_matched"]=<entry.name>`, and emits one `gate.signal_escalate` audit event with payload `{signature_matched, suggested_flag: "--allow-test-network", validator_name: "test"}`.
- [ ] **Does not auto-allow egress.** On signature match, the validator does NOT re-invoke `run_in_sandbox(network="scoped")`. The escalation surface is the audit event + on-disk JSON + report section + CLI banner — all written by S4-05 (`gate.py`) and S5-04 (`PatchBranchWriter`); this story only signals.
- [ ] Validator emits exactly one `tests.executed` audit event per invocation with payload `{exit_code, wall_ms, duration_vs_baseline_pct, requires_network}`. `duration_vs_baseline_pct` is `100` for the first run on a worktree (no baseline yet); subsequent calls in the same `run_id` may read a baseline from `transform_output.test_baseline_ms` if populated (S5-01 populates it; if absent, `100`).
- [ ] `ValidatorOutput.name == "test"`, `passed = exit_code == 0`, `stdout_path` / `stderr_path` point at `.codegenie/remediation/<run-id>/raw/test.{stdout,stderr}.log`, `confidence` is `"high"` on pass, `"medium"` on `requires_network=true`, `"low"` on non-zero exit without signature match.
- [ ] `signals` dict includes: `tests.exit_status: int`, `tests.wall_ms: int`, `tests.duration_vs_baseline_pct: float`, `tests.requires_network: bool`. These are the strict-AND inputs S4-05's `TrustScorer` reads.
- [ ] `tests/unit/transforms/validation/test_test_gate.py` ships ≥ 4 tests: (a) happy pass; (b) non-zero exit, no network signature → `passed=False`, `confidence="low"`, no `gate.signal_escalate` event; (c) non-zero exit, stderr contains `ENOTFOUND` → `requires_network=true`, `confidence="medium"`, `gate.signal_escalate` event emitted; (d) `--allow-test-network=True` widens the sandbox to `network="scoped"` (assert via mock on `run_in_sandbox` call argv).
- [ ] **Adversarial test** `tests/adv/test_test_profile_refuses_scoped_network_without_flag.py` pins the honest-failure invariant: invoke the validator with `allow_test_network=False` and a stderr containing `ENOTFOUND`; assert that **at no point** does any `run_in_sandbox` call mention `network="scoped"`. Capture every `run_in_sandbox` argv via mock; assert all of them have `network="none"`.
- [ ] `tests/unit/recipes/test_network_signatures_yaml.py` validates the catalog YAML parses, has the expected closed-enum entries, and rejects unknown top-level keys.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write the failing tests under `tests/unit/transforms/validation/test_test_gate.py` and `tests/adv/test_test_profile_refuses_scoped_network_without_flag.py` first. Mock the `tools/npm` wrapper for the test command path; assert on call kwargs.
2. Create `src/codegenie/recipes/network_signatures.yaml` with the initial closed catalog.
3. Create `src/codegenie/recipes/network_signatures.py` ship `NetworkSignature` Pydantic model + `load_network_signatures()` loader + `match_signature(stderr_tail: str, signatures: Sequence[NetworkSignature]) -> NetworkSignature | None` pure function.
4. Create `src/codegenie/transforms/validation/test.py`:
   - `test_validator(transform_output, *, allow_test_network, wall_timeout_s=600, pid_budget=1024)`.
   - Resolve log paths under `.codegenie/remediation/<run-id>/raw/test.{stdout,stderr}.log`.
   - Call `codegenie.tools.npm.run_npm_test(cwd=transform_output.worktree_root, timeout_s=wall_timeout_s, pid_budget=pid_budget, network=("scoped" if allow_test_network else "none"), stdout_to=..., stderr_to=..., test_execution=True)`.
   - On non-zero exit AND `not allow_test_network`: read `stderr_tail` (last 1 MiB); `match_signature(...)`; on match → set `requires_network=True`, emit `gate.signal_escalate`.
   - Compute `duration_vs_baseline_pct`: if `transform_output.test_baseline_ms` is set, `(result.wall_ms / transform_output.test_baseline_ms) * 100`; else `100.0`.
   - Emit `tests.executed` audit event.
   - Compute `confidence`: `"high"` on pass; `"medium"` on `requires_network`; `"low"` otherwise.
   - Return `ValidatorOutput(name="test", passed=..., stdout_path=..., stderr_path=..., duration_ms=..., confidence=..., requires_network=..., signals=..., warnings=[...], errors=[...])`.
5. Audit-event payload construction uses the S1-07 Pydantic models. Use the `audit.writer.append(event_name, payload=...)` API; never write raw dicts.
6. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/transforms/validation/test.py src/codegenie/recipes/network_signatures.py tests/unit/transforms/validation/test_test_gate.py tests/adv/`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Path: `tests/unit/transforms/validation/test_test_gate.py`

```python
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from codegenie.transforms.contract import TransformOutput
from codegenie.transforms.validation.test import test_validator


def _fake_output(tmp: Path) -> TransformOutput:
    return TransformOutput(
        name="npm_package_upgrade",
        diff_path=tmp / "p.patch",
        branch_name="codegenie/vuln-fix/CVE-2024-0001-deadbee",
        files_changed=["package.json", "package-lock.json"],
        confidence="high",
        worktree_root=tmp,
        run_id="run-1",
    )


def test_test_validator_happy_pass(tmp_path: Path) -> None:
    with patch("codegenie.tools.npm.run_npm_test") as run:
        run.return_value = MagicMock(
            exit_code=0, wall_ms=1234, stderr=b"", stderr_tail=b"",
        )
        out = test_validator(_fake_output(tmp_path), allow_test_network=False)
    assert out.passed is True
    assert out.confidence == "high"
    assert out.requires_network is False


def test_test_failure_without_network_signature_is_low_confidence(tmp_path: Path) -> None:
    with patch("codegenie.tools.npm.run_npm_test") as run, \
         patch("codegenie.audit.writer.append") as audit:
        run.return_value = MagicMock(
            exit_code=1, wall_ms=1000, stderr_tail=b"AssertionError: 1 != 2",
        )
        out = test_validator(_fake_output(tmp_path), allow_test_network=False)
    assert out.passed is False
    assert out.confidence == "low"
    assert out.requires_network is False
    events = [c.args[0] for c in audit.call_args_list]
    assert "gate.signal_escalate" not in events


def test_test_failure_with_network_signature_escalates(tmp_path: Path) -> None:
    with patch("codegenie.tools.npm.run_npm_test") as run, \
         patch("codegenie.audit.writer.append") as audit:
        run.return_value = MagicMock(
            exit_code=1, wall_ms=900,
            stderr_tail=b"Error: getaddrinfo ENOTFOUND db.local",
        )
        out = test_validator(_fake_output(tmp_path), allow_test_network=False)
    assert out.requires_network is True
    assert out.confidence == "medium"
    events = [c.args[0] for c in audit.call_args_list]
    assert "gate.signal_escalate" in events


def test_allow_test_network_widens_sandbox_to_scoped(tmp_path: Path) -> None:
    with patch("codegenie.tools.npm.run_npm_test") as run:
        run.return_value = MagicMock(exit_code=0, wall_ms=1, stderr_tail=b"")
        test_validator(_fake_output(tmp_path), allow_test_network=True)
    kwargs = run.call_args.kwargs
    assert kwargs["network"] == "scoped"
    assert kwargs["test_execution"] is True
```

Path: `tests/adv/test_test_profile_refuses_scoped_network_without_flag.py`

```python
from pathlib import Path
from unittest.mock import patch, MagicMock

from codegenie.transforms.contract import TransformOutput
from codegenie.transforms.validation.test import test_validator


def test_signature_match_never_auto_widens_to_scoped(tmp_path: Path) -> None:
    """Honest-failure invariant (ADR-0005, cross-cutting concern).

    A test failing with `ENOTFOUND` MUST NOT result in the sandbox being
    silently widened to scoped. It must surface `requires_network=true`,
    emit `gate.signal_escalate`, and exit 8 via the orchestrator. The
    operator re-runs with `--allow-test-network` after review.
    """
    output = TransformOutput(
        name="npm_package_upgrade", diff_path=tmp_path / "p.patch",
        branch_name="codegenie/vuln-fix/CVE-2024-0001-abc1234",
        files_changed=[], confidence="high",
        worktree_root=tmp_path, run_id="run-1",
    )
    with patch("codegenie.tools.npm.run_npm_test") as run:
        run.return_value = MagicMock(
            exit_code=1, wall_ms=100,
            stderr_tail=b"ECONNREFUSED 127.0.0.1:5432",
        )
        test_validator(output, allow_test_network=False)
    # Assert: every run_in_sandbox call (here, just one) used network="none"
    for call in run.call_args_list:
        assert call.kwargs["network"] == "none"
    # And no second invocation happened
    assert run.call_count == 1
```

Run; confirm `ImportError`. Commit red marker.

### Green — smallest impl shape

- `network_signatures.yaml` is a literal YAML list of `{name, pattern, kind, source}` entries.
- `match_signature(stderr_tail, signatures)` walks in order; literal entries → `pattern in stderr_tail`; regex entries → `re.search(pattern, stderr_tail)`. First match wins.
- The validator body is ~50 lines. Branch only on `allow_test_network` for the `network=` keyword; signature scan is post-hoc on stderr_tail.

### Refactor — bounded

- Pull the stderr-tail read (last 1 MiB) into a `_tail_bytes(path, n)` helper; reused by S4-04 if build stderr scanning ever lands (Phase 5 territory).
- Module-level `_DEFAULT_TEST_WALL_S: Final[int] = 600`, `_DEFAULT_PID_BUDGET: Final[int] = 1024`.
- `network_signatures.yaml` location: `src/codegenie/recipes/network_signatures.yaml`. The recipes/ namespace owns it because it's a pinned data catalog (cross-cutting "pin-manifest discipline").

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/validation/test.py` | New — `test_validator` function |
| `src/codegenie/recipes/network_signatures.yaml` | New — closed initial signature catalog |
| `src/codegenie/recipes/network_signatures.py` | New — Pydantic `NetworkSignature` + loader + matcher |
| `tests/unit/transforms/validation/test_test_gate.py` | New — 4 tests (happy + low + medium-escalate + scoped-widening) |
| `tests/unit/recipes/test_network_signatures_yaml.py` | New — catalog loader + extra-field rejection |
| `tests/adv/test_test_profile_refuses_scoped_network_without_flag.py` | New — honest-failure invariant pin |

## Out of scope

- **On-disk escalation JSON (`escalations/<utc>.json`)** — S4-05 owns the operator surface composition.
- **CLI stderr banner on exit 8** — wired in S5-05.
- **`remediation-report.yaml#escalations[]` section** — wired in S5-04.
- **Trust scoring + gate orchestration** — S4-05.
- **Build validator** — S4-04.
- **CLI `--allow-test-network` flag definition** — S1-10 ships the click flag; this story consumes it via the function param.
- **Network-scope allowlist sourcing for `--allow-test-network`** — ADR-0005 explicitly defers to Phase 5; empty allowlist + warning is the v0.3.0 stance.
- **Signature catalog evolution (adding new patterns)** — every addition is a separate code+yaml+test PR; this story ships the initial set only.

## Notes for the implementer

- **The honest-failure invariant is the story's single most important property.** The adversarial test pins it; the integration test in S5-05 (`test_remediate_test_needs_network_escalates.py`) pins it end-to-end. If your refactor introduces a second `run_in_sandbox` call on signature match (even "just to retry with scoped"), you've broken the invariant. ADR-0005 explicitly forbids this. The flow is: signature match → audit event + signal → exit 8 → operator re-runs with `--allow-test-network`. No automation across that boundary.
- **`--ignore-scripts` is OFF under `test_execution=True`.** The wrapper (S3-01) knows this. The test command itself is allowed to run scripts by definition — `npm test` invokes `package.json#scripts.test`, which is the whole point. Do not pass `--ignore-scripts` through this validator. The wrapper-level guard in S3-01 is `NpmScriptsEnabled` raised iff `--ignore-scripts` is missing AND `test_execution=False`. Cross-check the wrapper's contract before writing test mocks.
- **`stderr_tail`, not `stderr`.** Test suites that emit hundreds of MB of stderr exist. Cap at 1 MiB tail. The match patterns are all short literals or short regexes — a tail is sufficient. If a real signature lands beyond the 1 MiB window in the wild, surface it via runbook + signature catalog update, not by removing the cap.
- **`duration_vs_baseline_pct` baseline** is populated by S5-01 (`NpmPackageUpgradeTransform`); first-run defaults to `100.0`. The `TrustScorer` (S4-05) reads it through `signals["tests.duration_vs_baseline_pct"] <= 200` — a flat 100 means the strict-AND passes; the only risk is a regression test that doubles in wall time, which the property is designed to catch. Phase 4 calibration improves this.
- **YAML catalog has `schema_version: "v1"` at top level** and `additionalProperties: false` on each entry (cross-cutting "schema discipline"). The catalog grows by code+yaml PR; never by inline string addition in Python code.
- **No regex catastrophic-backtracking risk on the signature patterns.** They're all short literals or short anchored patterns. If you add a pattern that uses `.*.*` or unbounded repetition, surface it in code review; the adversarial corpus (S7-02) will eventually grow a regex-bomb fixture if Phase 4/5 expands the catalog.
- **`gate.signal_escalate` is emitted from the validator**, not from `gate.py` (S4-05). The reason: the signal-escalate determination is signal-local — only this validator knows whether stderr matched. S4-05 reads the `requires_network` flag back and orchestrates the operator surface (JSON file + report section + banner). Split the responsibilities cleanly.
- **No LLM in this loop.** Cross-cutting fence (S1-09 + S7-07 CI gate) forbids LLM imports under `transforms/`. If you find yourself reaching for "let me just ask the LLM to classify this error string," stop — the signature catalog is the contract; new patterns ship as code, not as prompts. ADR-0013 makes this load-bearing.
