# Story S8-02 — `codegenie remediate` flags `--sandbox-backend`, `--max-attempts-override`, `--allow-test-network` + `--operator-ack`

**Step:** Step 8 — Operator CLI surface + end-to-end smoke
**Status:** Ready
**Effort:** S
**Depends on:** S8-01
**ADRs honored:** ADR-0004, ADR-0009, ADR-0012

## Context

`codegenie remediate` is the operator-facing entry point that drives Phase 3 → 4 → 5 end-to-end. Phase 5 introduces three new flags that must compose with existing flags without breaking them and must enforce one explicit safety interlock: `--max-attempts-override` is acknowledged operator override of the production-ADR-0014 three-retry default and may only proceed with `--operator-ack`. This story wires those flags, the Click validator that rejects missing acknowledgement with exit code 2, and the `gate.attempts_override` audit event that the override path emits exactly once.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — CLI surface (codegenie sandbox)` — the three flags' exact spelling and semantics.
  - `../phase-arch-design.md §Cross-cutting concerns — Decision points and defaults` — override raises (never lowers) the cap; one audit event per invocation.
  - `../phase-arch-design.md §Edge cases §14` — `--max-attempts-override 5` without `--operator-ack` is Click exit 2; precise error message.
  - `../phase-arch-design.md §Open questions §3` — `--allow-test-network` widens `egress_allowlist` and leaves `trace.new_endpoints` informational (do NOT promote to failed); `test_allow_test_network.py` exercises both paths.
- **Phase ADRs:**
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — `--sandbox-backend auto` is the default; `auto_detect()` chooses; explicit `did` or `firecracker` overrides.
  - `../ADRs/0009-firecracker-network-policy-host-side-nftables.md` — `--allow-test-network` interacts with the Firecracker nftables policy by extending the host-side allowlist; the policy module must accept the widened spec without code changes.
  - `../ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md` — even with `--allow-test-network`, env-allowlist filtering is unchanged.
- **Production ADRs:**
  - `../../../production/adrs/0014-three-retry-default-per-gate.md` — three retries is the default; `--max-attempts-override` is the documented exception path requiring acknowledgement.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Operator ack on attempt override"`.
- **Existing code:**
  - `src/codegenie/cli/remediate.py` — existing remediate command; this story extends, does not rewrite.
  - `src/codegenie/cli/sandbox.py` (S8-01) — for shared `--sandbox-backend` option definition (move to a shared helper if needed).
  - `src/codegenie/audit/events.py` — emit `gate.attempts_override` here, mirroring existing audit-event constants.

## Goal

Wire `--sandbox-backend {did,firecracker,auto}`, `--max-attempts-override <int>` (gated by `--operator-ack`), and `--allow-test-network` onto `codegenie remediate`, with a Click validator that exits 2 on missing acknowledgement and a single `gate.attempts_override` audit event emitted exactly once per override invocation.

## Acceptance criteria

- [ ] `codegenie remediate --sandbox-backend {did,firecracker,auto}` accepts the three values; default is `auto`; the resolved backend is threaded into the orchestrator → `GateRunner` → `SandboxClient` construction site via the existing settings stack (CLI flag wins per `phase-arch-design.md §Configuration`).
- [ ] `codegenie remediate --max-attempts-override 5` without `--operator-ack` exits with Click code 2 and prints a clear stderr message naming both flags (`"--max-attempts-override requires --operator-ack"`); no audit event is emitted on this failure path.
- [ ] `codegenie remediate --max-attempts-override 5 --operator-ack` proceeds, raises the per-gate `max_attempts` from its YAML-catalog default of 3 to 5, and emits exactly one `gate.attempts_override` audit event with fields `{gate_id, default_max_attempts: 3, override_max_attempts: 5, operator_ack: true, invocation_id}`.
- [ ] `--max-attempts-override` rejects values `< 3` with Click exit 2 (override may only raise, never lower, per arch §Decision points and defaults); rejects non-integers (handled by `click.IntRange`).
- [ ] `codegenie remediate --allow-test-network` widens every `SandboxSpec.egress_allowlist` for gates with `network=scoped` by appending the values in `tools/policy/sandbox-policy.yaml#test_network_extra_hosts` (or an empty list if the key is absent) — never disables the allowlist; leaves `trace.new_endpoints` informational regardless of any new endpoint observed.
- [ ] `--allow-test-network` does NOT relax env-allowlist filtering (ADR-0012) — env keys still pass through `env_allowlist.filter()`; covered by an explicit assertion.
- [ ] The three flags' `--help` text states the safety interlocks (`--operator-ack` required, override raises only, allow-test-network keeps `trace.new_endpoints` informational); `--help` exit code 0.
- [ ] `tests/cli/test_remediate_flags.py` ≥ 90% line coverage on the new validator + flag-handler functions; exercises every failure-mode message string verbatim.
- [ ] Audit event constant `gate.attempts_override` is defined in `src/codegenie/audit/events.py` (or the equivalent existing constants module) and used through that constant — no string literal at the emit site.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/cli`, `pytest tests/cli/test_remediate_flags.py` all pass.

## Implementation outline

1. Add the three `click.option` decorators to `codegenie remediate`:
   - `--sandbox-backend` with `click.Choice(["did","firecracker","auto"])`, default `auto`.
   - `--max-attempts-override` with `click.IntRange(min=3)`, default `None`.
   - `--operator-ack` boolean flag (default `False`).
   - `--allow-test-network` boolean flag (default `False`).
2. Add a `callback=` validator on `--max-attempts-override` that raises `click.UsageError` (→ exit 2) if `value is not None and not ctx.params.get("operator_ack")` — relies on Click's `ctx.params` population order, so declare `--operator-ack` before `--max-attempts-override` in the decorator order, OR use a `@remediate.result_callback`-style post-parse hook. Pick the simpler approach (declaration order) and document it.
3. Thread the resolved values into the existing settings/orchestrator construction site. If a `RemediationSettings` Pydantic model exists, extend it with three fields; otherwise pass them as kwargs to the orchestrator factory.
4. In the orchestrator's `GateRunner` factory:
   - If `--max-attempts-override` was set, replace the catalog's `max_attempts` for *every* gate (this is the documented override semantics — single dial, raises only) and emit one `gate.attempts_override` audit event before the first gate runs.
   - If `--allow-test-network` was set, extend each `SandboxSpec.egress_allowlist` with the policy-YAML extras; set a flag on `GateContext` so `collect_trace_signal` knows to keep `new_endpoints` informational.
5. Define `AuditEvent.GATE_ATTEMPTS_OVERRIDE = "gate.attempts_override"` in the existing event constants module; emit via the existing audit-emit function with structured fields per AC.
6. Update `--help` epilog with one example for each flag combination.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/cli/test_remediate_flags.py`

```python
from __future__ import annotations

import pytest
from click.testing import CliRunner

from codegenie.cli import cli


def test_max_attempts_override_without_ack_exits_2() -> None:
    result = CliRunner().invoke(
        cli, ["remediate", "--cve", "CVE-2026-0001", "--max-attempts-override", "5"]
    )
    assert result.exit_code == 2, result.output
    assert "--max-attempts-override requires --operator-ack" in (result.stderr or result.output)


def test_max_attempts_override_with_ack_emits_one_audit_event(monkeypatch, tmp_path) -> None:
    emitted: list[dict] = []
    monkeypatch.setattr(
        "codegenie.audit.emit",
        lambda event, **fields: emitted.append({"event": event, **fields}),
    )
    # stub the actual remediate pipeline so the test stays a unit test
    monkeypatch.setattr("codegenie.orchestrator.run", lambda **kw: 0)

    result = CliRunner().invoke(
        cli,
        [
            "remediate", "--cve", "CVE-2026-0001",
            "--max-attempts-override", "5", "--operator-ack",
        ],
    )

    assert result.exit_code == 0, result.output
    override_events = [e for e in emitted if e["event"] == "gate.attempts_override"]
    assert len(override_events) == 1
    assert override_events[0]["default_max_attempts"] == 3
    assert override_events[0]["override_max_attempts"] == 5
    assert override_events[0]["operator_ack"] is True


def test_max_attempts_override_below_3_rejected() -> None:
    result = CliRunner().invoke(
        cli,
        ["remediate", "--cve", "CVE-2026-0001",
         "--max-attempts-override", "2", "--operator-ack"],
    )
    assert result.exit_code == 2


def test_sandbox_backend_default_is_auto(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(
        "codegenie.orchestrator.run",
        lambda **kw: captured.update(kw) or 0,
    )
    CliRunner().invoke(cli, ["remediate", "--cve", "CVE-2026-0001"])
    assert captured["sandbox_backend"] == "auto"


def test_allow_test_network_widens_egress_but_does_not_disable_env_filter(monkeypatch) -> None:
    # Stub orchestrator; assert it received allow_test_network=True
    # and that env_allowlist.filter is invoked on the spec build (call-count >= 1).
    ...
```

### Green

The validator is one `callback=` on `--max-attempts-override` (or a `--operator-ack`-aware Click parameter group). The orchestrator factory grows three kwargs (`sandbox_backend`, `max_attempts_override`, `allow_test_network`). The audit emit is one line guarded by `if max_attempts_override is not None:`.

### Refactor

- If `--sandbox-backend` is already used by `codegenie sandbox health` (S8-01), promote the choice constant to `src/codegenie/cli/_options.py` so both commands share it.
- Replace any `click.echo(..., err=True)` ad-hoc error with `raise click.UsageError(...)` so Click's `--help` and exit-code conventions stay consistent.
- Push the override semantics ("raises only, single dial across gates") into a docstring on the orchestrator entry point so future flags don't accidentally allow per-gate overrides without a contract change.
- Extract `_audit_override(default: int, override: int)` so the emit-site is one line in the orchestrator.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli/remediate.py` | Add the three flags + validator. |
| `src/codegenie/cli/_options.py` (new or existing) | Shared `--sandbox-backend` choice constant. |
| `src/codegenie/orchestrator/__init__.py` (or wherever the factory lives) | Accept `sandbox_backend`, `max_attempts_override`, `allow_test_network` kwargs. |
| `src/codegenie/audit/events.py` | Add `GATE_ATTEMPTS_OVERRIDE` constant. |
| `tests/cli/test_remediate_flags.py` | Red + green tests. |

## Out of scope

- The full E2E run that exercises retry-2-recover with these flags — S8-03.
- ADR audit and coverage closure — S8-04.
- New sandbox backends added by Phase 7 — they slot into `auto_detect()` by `@register_sandbox_backend` decoration; no CLI edit required.
- A `--max-attempts-override` that *lowers* the cap — explicitly out per arch (could be revisited in a future ADR, but not here).
- Persisting `--operator-ack` across invocations or to disk — single-invocation only.

## Notes for the implementer

- Click's `IntRange(min=3)` already covers the "raise only" rule, but add a separate test asserting the *error message* mentions "must be at least 3" so contributors don't have to guess.
- `--operator-ack` is intentionally a boolean flag, not a value; `--operator-ack=anything` should fail. Verify with `click.testing`.
- Do NOT emit `gate.attempts_override` on the failure path (missing ack). The audit event records a *successful operator decision*, not a rejected one. The rejection is already captured in the structured error message.
- Avoid passing `--max-attempts-override` and `--operator-ack` through to the gate-catalog YAML; the catalog is digest-stable. The override mutates the in-memory `RetryPolicy.max_attempts` at runtime only.
- `--allow-test-network` adds entries to `egress_allowlist`; it must NOT change `SandboxSpec.network` from `scoped` to `none` or vice versa. Verify by asserting the resolved spec's `network` field is whatever the gate catalog said.
- `trace.new_endpoints` informational behavior is a property of the *trace collector* reading a `GateContext.allow_test_network` flag — wire it through `GateContext`, not via a global.
- One audit event per invocation, not per gate. If the operator runs `remediate` against a CVE that triggers four gates, there is still exactly one `gate.attempts_override` event.
