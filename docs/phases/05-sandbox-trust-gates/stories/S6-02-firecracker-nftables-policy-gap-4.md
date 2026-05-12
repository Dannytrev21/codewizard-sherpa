# Story S6-02 — Firecracker host-side TAP + nftables network policy

**Step:** Step 6 — FirecrackerClient backend + KVM-gated CI smoke test
**Status:** Ready
**Effort:** M
**Depends on:** S6-01
**ADRs honored:** ADR-0009, ADR-0001, ADR-0004

## Context

`SandboxSpec.network: Literal["none","scoped"]` plus `egress_allowlist: list[str]` is the contract every backend must enforce. DinD enforces via iptables in `sandbox/did/network_policy.py`; Firecracker has no iptables analog inside the guest, and the synthesis was silent on the mechanism — Gap 4 in `phase-arch-design.md`. ADR-0009 commits us to a host-side TAP device + nftables ruleset so the trusted boundary is the host kernel, not the (untrusted) guest. This story closes Gap 4: ship `sandbox/firecracker/network_policy.py::apply_policy(spec)` and wire it into `FirecrackerClient.execute` so `network="scoped"` no longer raises `NotImplementedError` (left there by S6-01).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap 4` — verbatim statement of the problem and the host-side-TAP + nftables fix.
  - `../phase-arch-design.md §Component design — FirecrackerClient` — `network_policy.py` is the second of two subprocess sites in the Firecracker subpackage.
  - `../phase-arch-design.md §Physical view` — host kernel as enforcement boundary; guest is untrusted.
  - `../phase-arch-design.md §Tool-use safety` — subprocess allowlist now includes `sandbox/firecracker/network_policy.py`.
- **Phase ADRs:**
  - `../ADRs/0009-firecracker-network-policy-host-side-nftables.md` — decision, options considered (inside-guest filtering, MMDS DNS allowlist, slirp4netns), consequences (`apply_policy` signature, `tests/golden/nftables_rules_<network-policy>.txt`, KVM-only integration test, ~50–100 ms per-execute overhead).
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — subprocess chokepoint discipline; this module is allowlisted.
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — Firecracker is Linux-only; nftables-on-Linux is acceptable.
- **Production ADRs:**
  - `../../../production/adrs/0019-sandbox-stack.md` — sandbox stack target this composes with.
- **Source design:**
  - `../final-design.md §Risk surface` — egress as defense-in-depth.
- **Existing code:**
  - `src/codegenie/sandbox/did/network_policy.py` (from S3-03) — iptables-based reference shape; same per-backend pattern.
  - `src/codegenie/sandbox/firecracker/client.py` (from S6-01) — `execute()` currently raises `NotImplementedError` on `network="scoped"`; replace with `apply_policy(spec)` call wrapped in try/finally for teardown.
  - `src/codegenie/sandbox/contract.py` (from S1-02) — `SandboxSpec.network`, `egress_allowlist`.
- **External docs:**
  - nftables tutorial — atomic ruleset updates: <https://wiki.nftables.org/wiki-nftables/index.php/Atomic_rule_replacement> — needed so partial-apply on failure leaves no leak.
  - Firecracker TAP networking guide: <https://github.com/firecracker-microvm/firecracker/blob/main/docs/network-setup.md> — `ip tuntap add`, `ip link set` and the boot-arg shape (`ip=<guest>::<gw>::eth0:off`).

## Goal

Ship `sandbox/firecracker/network_policy.py` so `FirecrackerClient.execute(spec)` enforces `network="none"` (no NIC at all) and `network="scoped"` (host-side TAP + nftables egress allowlist) using the host kernel as the trusted boundary.

## Acceptance criteria

- [ ] `apply_policy(spec: SandboxSpec) -> NetNamespaceConfig` lives at `src/codegenie/sandbox/firecracker/network_policy.py` and returns a context-manager-like `NetNamespaceConfig` with `tap_name: str`, `guest_ip: str`, `host_ip: str`, `nftables_table: str`, and a `teardown()` method that removes the TAP + the nftables table atomically.
- [ ] `spec.network == "none"` → `apply_policy` returns a `NetNamespaceConfig(tap_name=None, ...)` and `FirecrackerClient` boots the microVM with no `--config-file network-interfaces`; `tests/sandbox/firecracker/test_network_policy.py::test_none_creates_no_tap` asserts `subprocess` is never called when `network="none"`.
- [ ] `spec.network == "scoped"` with `egress_allowlist=["registry.npmjs.org"]` produces an nftables ruleset that (a) drops all egress by default, (b) resolves the allowlisted hostnames *on the host* to IPv4+IPv6 addresses and permits only those, (c) permits the established/related connection track, (d) is loaded atomically via `nft -f -` from stdin.
- [ ] The rendered ruleset is byte-equal to `tests/golden/nftables_rules_scoped_npmjs.txt` for the canonical input `egress_allowlist=["registry.npmjs.org"]` (DNS resolution mocked to a fixed address set so the golden is stable).
- [ ] `teardown()` is **idempotent**: calling it twice is a no-op the second time; calling it on a `NetNamespaceConfig` whose `apply` raised partway is also safe. Verified by a unit test that calls `teardown()` twice and asserts the second call does not invoke `subprocess`.
- [ ] On apply failure (e.g., `nft` exits non-zero), `apply_policy` removes any partially created TAP device before re-raising as `FirecrackerNetworkPolicyError(SandboxBackendError)` with the `nft` stderr embedded in `details`.
- [ ] DNS-resolution failure on the host (a hostname in `egress_allowlist` does not resolve) raises `FirecrackerNetworkPolicyError` with a message that clearly distinguishes resolution failure from rule-load failure (matches ADR-0009 tradeoff row 5).
- [ ] `FirecrackerClient.execute(spec)` calls `apply_policy(spec)` *before* `InstanceStart` and `cfg.teardown()` in a `finally` block — never leak a TAP/ruleset across runs (verified by a test that raises mid-execute and asserts `teardown` was called once).
- [ ] `tests/integration/sandbox/test_firecracker_network_policy.py` is created with `pytest.mark.skip_if_no_kvm` and asserts: `curl https://registry.npmjs.org` succeeds inside the guest; `curl https://github.com` fails (S6-05 wires it into CI; the test file lands here).
- [ ] `subprocess` invocations live exclusively in `sandbox/firecracker/network_policy.py` and `sandbox/firecracker/client.py`; `tests/schema/test_no_subprocess_outside_build_chokepoint.py` remains green.
- [ ] `codegenie sandbox health` (post-S8-01) and `codegenie sandbox gc` detect orphan TAP devices matching the `cgsbx-<run_id>` naming pattern; this story emits the naming convention and structlog event `sandbox.firecracker.tap_orphan` on cleanup detection.
- [ ] Branch coverage on `src/codegenie/sandbox/firecracker/network_policy.py` ≥ 90%; line coverage ≥ 95%.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/sandbox/firecracker`, `pytest tests/sandbox/firecracker/test_network_policy.py` pass.

## Implementation outline

1. Extend `src/codegenie/sandbox/errors.py` with `FirecrackerNetworkPolicyError(SandboxBackendError)`.
2. Create `src/codegenie/sandbox/firecracker/network_policy.py`:
   - `@dataclass class NetNamespaceConfig`: `tap_name: str | None`, `guest_ip: str | None`, `host_ip: str | None`, `nftables_table: str | None`, `_torn_down: bool = False`, `teardown(self)` method.
   - `def apply_policy(spec: SandboxSpec) -> NetNamespaceConfig:` branches on `spec.network`.
   - Private `_render_ruleset(allowlist: list[str], resolved_ips: dict[str, list[str]]) -> str` — pure function, returns nftables script as text; this is what the golden file tests.
   - Private `_resolve_hostnames(allowlist: list[str]) -> dict[str, list[str]]` — uses `socket.getaddrinfo`; raises `FirecrackerNetworkPolicyError` on resolution failure.
   - Private `_apply_nft(script: str) -> None` — subprocess `["nft","-f","-"]` with stdin; raises on non-zero exit.
   - Private `_create_tap(run_id: str) -> tuple[str, str, str]` — subprocess `["ip","tuntap","add","dev","cgsbx-<run_id>","mode","tap"]` plus `ip addr add` for `host_ip/30`; returns `(tap_name, host_ip, guest_ip)`.
3. Wire `FirecrackerClient.execute(spec)` to call `apply_policy(spec)` immediately after `_assert_rootfs_artifacts()` and put `cfg.teardown()` in the `finally` of the outer try.
4. Pass `host_ip`/`guest_ip` into the Firecracker `/network-interfaces` API call when `cfg.tap_name` is non-None; pass `boot_args="... ip=<guest_ip>::<host_ip>::eth0:off"`.
5. Generate `tests/golden/nftables_rules_scoped_npmjs.txt` from `_render_ruleset(["registry.npmjs.org"], {"registry.npmjs.org": ["104.16.16.35","2606:4700::6810:1023"]})`.
6. Emit structlog events `sandbox.firecracker.network.apply` (with `tap_name`, allowlist size) and `sandbox.firecracker.network.teardown` (with `tap_name`).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/sandbox/firecracker/test_network_policy.py`

```python
# tests/sandbox/firecracker/test_network_policy.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from codegenie.sandbox.contract import SandboxSpec
from codegenie.sandbox.errors import FirecrackerNetworkPolicyError
from codegenie.sandbox.firecracker import network_policy as np


def _spec(network: str, allowlist: list[str], tmp_path: Path) -> SandboxSpec:
    return SandboxSpec(
        cmd=["true"], copy_in=[], logs_dir=tmp_path / "logs",
        copy_out_root=tmp_path / "out", time_budget_seconds=60,
        memory_limit_mib=512, network=network, egress_allowlist=allowlist,
        env={},
    )


def test_none_creates_no_tap_and_no_subprocess(tmp_path: Path) -> None:
    spec = _spec("none", [], tmp_path)
    with patch("subprocess.run") as mocked:
        cfg = np.apply_policy(spec)
    assert cfg.tap_name is None
    assert mocked.call_count == 0, "network=none must not invoke any subprocess"
    cfg.teardown()  # must not blow up


def test_scoped_renders_golden_ruleset(tmp_path: Path) -> None:
    spec = _spec("scoped", ["registry.npmjs.org"], tmp_path)
    fake_dns = {"registry.npmjs.org": ["104.16.16.35", "2606:4700::6810:1023"]}
    rendered = np._render_ruleset(spec.egress_allowlist, fake_dns)

    golden = (Path("tests/golden/nftables_rules_scoped_npmjs.txt")).read_text()
    assert rendered == golden, "ruleset must be byte-equal to the golden file"


def test_scoped_raises_on_dns_failure(tmp_path: Path) -> None:
    spec = _spec("scoped", ["nonexistent.invalid"], tmp_path)
    with patch("codegenie.sandbox.firecracker.network_policy.socket.getaddrinfo",
               side_effect=OSError("Name does not resolve")):
        with pytest.raises(FirecrackerNetworkPolicyError) as exc:
            np.apply_policy(spec)
        assert "resolve" in str(exc.value).lower(), \
            "DNS failure must be distinct from rule-load failure"


def test_teardown_is_idempotent(tmp_path: Path) -> None:
    spec = _spec("scoped", ["registry.npmjs.org"], tmp_path)
    with patch.object(np, "_apply_nft"), \
         patch.object(np, "_create_tap", return_value=("cgsbx-test", "10.0.0.1", "10.0.0.2")), \
         patch.object(np, "_resolve_hostnames", return_value={"registry.npmjs.org": ["1.2.3.4"]}):
        cfg = np.apply_policy(spec)
    with patch("subprocess.run") as mocked:
        cfg.teardown()
        cfg.teardown()
    # Exactly one cleanup-side subprocess batch should have run.
    first_calls = mocked.call_count
    cfg.teardown()
    assert mocked.call_count == first_calls, "second/third teardown must be no-ops"


def test_apply_failure_cleans_up_partial_tap(tmp_path: Path) -> None:
    spec = _spec("scoped", ["registry.npmjs.org"], tmp_path)
    with patch.object(np, "_create_tap", return_value=("cgsbx-x", "10.0.0.1", "10.0.0.2")), \
         patch.object(np, "_resolve_hostnames", return_value={"registry.npmjs.org": ["1.2.3.4"]}), \
         patch.object(np, "_apply_nft", side_effect=FirecrackerNetworkPolicyError("nft load failed")):
        with patch.object(np, "_destroy_tap") as destroy:
            with pytest.raises(FirecrackerNetworkPolicyError):
                np.apply_policy(spec)
            destroy.assert_called_once_with("cgsbx-x"), \
                "partial TAP must be destroyed before re-raising"


@pytest.mark.skip_if_no_kvm
def test_scoped_blocks_non_allowlisted_egress_in_real_guest(
    tmp_path: Path,
) -> None:
    # KVM-only — wired into S6-05 CI. Lands here as a placeholder per ADR-0009.
    pytest.skip("Real-guest assertion deferred to S6-05 KVM-gated suite")
```

Use `pytest.mark.skip_if_no_kvm` for KVM-required tests. The integration assertion (`curl npmjs ok / curl github fails`) is placeholder-stubbed here and fully exercised in S6-05.

### Green — make it pass

Minimal: `apply_policy` branches on `spec.network`; `none` short-circuits with a no-op `NetNamespaceConfig`. `scoped` calls `_resolve_hostnames` → `_create_tap` → `_render_ruleset` → `_apply_nft`; on any raise after `_create_tap`, call `_destroy_tap` then re-raise. `teardown()` checks `self._torn_down`, calls `_destroy_tap` + `nft delete table` if set, then sets `_torn_down=True`.

### Refactor — clean up

- Move the nftables script template to a module-level `_RULESET_TEMPLATE` triple-quoted constant; rendering becomes pure string interpolation.
- Pull TAP-name derivation into `_tap_name_for(run_id: str) -> str` returning `f"cgsbx-{run_id[:8]}"` — keep names ≤ IFNAMSIZ (16).
- Promote `subprocess` chokepoint helpers (`_run_or_raise`) into a single private function so audit is local.
- Add docstrings citing ADR-0009 on `apply_policy` and `NetNamespaceConfig`.
- Ensure all error messages include both the failing command (without secrets) and stderr first 200 chars.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/firecracker/network_policy.py` | New module — `apply_policy`, `NetNamespaceConfig`, render+resolve+apply helpers. |
| `src/codegenie/sandbox/firecracker/client.py` | Replace `NotImplementedError` on `network="scoped"` with `apply_policy` call + finally-teardown. |
| `src/codegenie/sandbox/errors.py` | Add `FirecrackerNetworkPolicyError`. |
| `tests/sandbox/firecracker/test_network_policy.py` | Red test + golden + idempotent-teardown + DNS-failure tests. |
| `tests/golden/nftables_rules_scoped_npmjs.txt` | Byte-stable golden ruleset (committed). |
| `tests/integration/sandbox/test_firecracker_network_policy.py` | Placeholder KVM-only test file (assertions land in S6-05). |

## Out of scope

- Real KVM-gated integration assertions on `curl npmjs ok / curl github fails` — S6-05.
- Auto-detect path that picks Firecracker on Linux/KVM — S6-04.
- Rootfs digest enforcement — S6-03.
- Operator CLI surface (`sandbox health` orphan-TAP detection) — S8-01.
- IPv6-only allowlist edge cases — explicit non-goal for Phase 5; both v4 and v6 are emitted but no v6-only mode is exposed in `SandboxSpec`.

## Notes for the implementer

- nftables atomic ruleset replacement is a load-bearing detail — partial application leaks egress. Pipe the *entire* ruleset to `nft -f -` once; do not split into multiple `nft add rule` calls.
- DNS resolution on the host is part of the security boundary. Do **not** resolve hostnames inside the guest; that re-trusts the guest's resolver. Resolve on the host, emit literal IPs in the ruleset.
- TAP names must be ≤ 15 chars (Linux IFNAMSIZ minus the trailing NUL). The `cgsbx-` prefix plus 8 hex chars of `run_id` is 14 — safe.
- The structlog event `sandbox.firecracker.tap_orphan` is a hook for S8-01's `gc` subcommand; emit it with the orphan name(s) so the CLI can act on it.
- Re-resolving allowlisted hostnames on every `execute()` is the right default — DNS rotates, and per ADR-0009 the ~50–100 ms cost is acceptable. Do **not** cache resolution across runs.
- Be defensive against `egress_allowlist` containing IP literals (skip resolution, emit directly); the test suite should include one IP-literal case.
- `iptables-nft` compatibility is *not* equivalent to native `nft` — require the binary to be `nft` (not `iptables`) on the runner; surface mismatch in `FirecrackerClient.health()` as `nftables_missing` (this also coordinates with S8-01 health output).
- On nftables teardown, prefer `nft delete table inet cgsbx_<run_id>` (atomic) over rule-by-rule deletion; idempotency falls out for free since deleting a missing table is `EEXIST=0` in `nft`'s exit when `-c` (check mode) is not used — but you must still handle the absent-table exit cleanly.
