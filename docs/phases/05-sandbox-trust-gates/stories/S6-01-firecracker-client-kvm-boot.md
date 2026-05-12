# Story S6-01 — `FirecrackerClient` boot + exec + copy-out

**Step:** Step 6 — FirecrackerClient backend + KVM-gated CI smoke test
**Status:** Ready
**Effort:** L
**Depends on:** S3-02
**ADRs honored:** ADR-0001, ADR-0004, ADR-0006

## Context

Phase 5's second `SandboxClient` backend is real Firecracker (not a stub) so we generate ADR-0019-grade evidence of microVM cold-start latency, kernel feature requirements, and per-evaluation cost. This story ships the API-socket-driven `FirecrackerClient` that boots a pinned `vmlinux`+`rootfs.ext4`, mounts a copy-in tar, execs the gate `cmd`, and tars the workdir back out — without network policy (S6-02) or rootfs digest pinning (S6-03), but with all three structured-failure errors the auto-detect path (S6-04) needs to fall back cleanly.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — FirecrackerClient` — public interface, internal structure, performance envelope, failure behavior.
  - `../phase-arch-design.md §Logical view` — `FirecrackerClient` class diagram (`firecracker_path`, `vmlinux_digest`, `rootfs_digest`).
  - `../phase-arch-design.md §Physical view` — KVM runner box: `firecracker bin → KVM → microVM (vmlinux+rootfs, microvm class)`.
  - `../phase-arch-design.md §Process view` — `SandboxClient.execute` sequence (copy-in → start → exec → copy-out).
  - `../phase-arch-design.md §Edge cases §15` — `/dev/kvm` absent → `FirecrackerClient.health()` returns `reachable=False, reasons=["kvm_missing"]`.
- **Phase ADRs:**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — `subprocess` here is one of the three allowlisted chokepoint files (`sandbox/firecracker/client.py`).
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — every Firecracker `SandboxRun` carries `gate_isolation_class="microvm"` and `backend="firecracker"`.
  - `../ADRs/0006-protocol-vs-abc-convention.md` — backend implements `SandboxClient` Protocol structurally; no inheritance.
- **Production ADRs:**
  - `../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md` — microVM-for-gates production target this evidences.
  - `../../../production/adrs/0019-sandbox-stack.md` — phase 5 generates real Firecracker numbers for the eventual resolution.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Real Firecracker (not stub)"`.
- **Existing code:**
  - `src/codegenie/sandbox/contract.py` (from S1-02) — `SandboxClient` Protocol, `SandboxSpec`, `SandboxRun`, `SandboxHealth`.
  - `src/codegenie/sandbox/did/client.py` (from S3-02) — reference shape for `execute()`, `health()` return value, and structured-failure wrapping.
  - `src/codegenie/sandbox/errors.py` (from S1-01) — extend with the three new structured failures.
  - `src/codegenie/sandbox/registry.py` (from S1-05) — register the backend via `@register_sandbox_backend("firecracker")`.
- **External docs:**
  - Firecracker API socket reference: <https://github.com/firecracker-microvm/firecracker/blob/main/docs/api_requests/actions.md> — `PUT /actions {action_type:"InstanceStart"}` and the `/boot-source`, `/drives/rootfs`, `/machine-config` shapes.
  - Firecracker vsock guest exec pattern: <https://github.com/firecracker-microvm/firecracker/blob/main/docs/vsock.md> — needed to send `cmd` into the guest without spawning an in-guest SSH daemon.

## Goal

Implement `FirecrackerClient` so a `SandboxSpec` against the pinned `vmlinux`+`rootfs.ext4` boots a microVM via the API socket, runs `cmd`, and returns a populated `SandboxRun` — with `FirecrackerKvmMissing`, `FirecrackerBinaryMissing`, and `FirecrackerRootfsMissing` raised on each precondition failure.

## Acceptance criteria

- [ ] `FirecrackerClient(firecracker_path: Path, vmlinux_digest: str, rootfs_digest: str)` is registered via `@register_sandbox_backend("firecracker")` and discoverable through `sandbox.registry.get_backend("firecracker")`.
- [ ] `execute(spec: SandboxSpec) -> SandboxRun` boots a microVM (cold boot every time — no warm pool), mounts copy-in tar at `/work` inside the guest, execs `spec.cmd` with `cwd=/work`, captures stdout/stderr to `spec.logs_dir`, copy-outs the workdir back to `spec.copy_out_root`, and returns a `SandboxRun` with `backend="firecracker"` and `gate_isolation_class="microvm"`.
- [ ] `health() -> SandboxHealth` returns `reachable=True` only when (a) `/dev/kvm` is readable+writable, (b) the `firecracker` binary BLAKE3 matches `tools/digests.yaml#sandbox.firecracker`, (c) the `vmlinux` BLAKE3 matches `tools/digests.yaml#sandbox.vmlinux`, (d) the `rootfs.ext4` BLAKE3 matches `tools/digests.yaml#sandbox.rootfs`. Each failed precondition produces a structured `reasons` entry (`"kvm_missing"`, `"firecracker_binary_digest_mismatch"`, `"vmlinux_digest_mismatch"`, `"rootfs_digest_mismatch"`); confidence is `low` on any failure.
- [ ] `FirecrackerKvmMissing` is raised on first `execute()` call (not at `__init__`) when `/dev/kvm` is unreadable; message includes the absolute path checked and a remediation pointer (`run on a KVM-capable Linux host or use the docker_in_docker backend`).
- [ ] `FirecrackerBinaryMissing` is raised when the configured `firecracker_path` does not exist, is not executable, or its BLAKE3 digest does not match the pinned value in `tools/digests.yaml`; message includes the expected vs observed hex prefix (first 8 chars only).
- [ ] `FirecrackerRootfsMissing` is raised when either `vmlinux` or `rootfs.ext4` is absent under `tools/firecracker/<rootfs_digest>/`, or their BLAKE3 digests do not match; message identifies *which* artifact failed.
- [ ] OOM detection: when the in-guest process is killed by the OOM-killer (signal observed via vsock exit code or `SIGKILL` with `dmesg` evidence), `SandboxRun.killed_by_oom=True`.
- [ ] Timeout: `spec.time_budget_seconds` exceeded → guest `SIGKILL` via `PUT /actions {action_type:"SendCtrlAltDel"}` followed by VM teardown; `SandboxRun.timed_out=True`.
- [ ] Every `subprocess` invocation lives inside `src/codegenie/sandbox/firecracker/client.py`; `tests/schema/test_no_subprocess_outside_build_chokepoint.py` remains green.
- [ ] On `execute()` exit (success *or* failure), the API-socket file, the temp `vmlinux`/`rootfs` overlay, and the VM jail dir are removed; orphan dirs are detected by `codegenie sandbox health` (verified by a unit test that asserts cleanup on raised exception).
- [ ] Unit tests cover `health()` with each failure mode mocked (4 cases); the boot path is fully mocked at the `subprocess.Popen` + `requests.Session` boundary so unit tests run on macOS (no KVM).
- [ ] Branch coverage on `src/codegenie/sandbox/firecracker/client.py` ≥ 90%; line coverage ≥ 95%.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/sandbox/firecracker`, `pytest tests/sandbox/firecracker/` all pass.

## Implementation outline

1. Extend `src/codegenie/sandbox/errors.py` with `FirecrackerKvmMissing(SandboxBackendError)`, `FirecrackerBinaryMissing(SandboxBackendError)`, `FirecrackerRootfsMissing(SandboxBackendError)`.
2. Create `src/codegenie/sandbox/firecracker/__init__.py` and `src/codegenie/sandbox/firecracker/client.py`:
   - `class FirecrackerClient:` constructor accepts `firecracker_path: Path`, `vmlinux_digest: str`, `rootfs_digest: str`.
   - `health(self) -> SandboxHealth` runs four preconditions, returns structured reasons; never raises.
   - `execute(self, spec: SandboxSpec) -> SandboxRun`:
     1. `_assert_kvm()` → raise `FirecrackerKvmMissing`.
     2. `_assert_binary_digest()` → raise `FirecrackerBinaryMissing`.
     3. `_assert_rootfs_artifacts()` → raise `FirecrackerRootfsMissing`.
     4. Build copy-in tar from `spec.copy_in` (reuse the DinD copy-in helper if it exists; otherwise local `tarfile`).
     5. Allocate a unique jail dir under `.codegenie/sandbox/runs/<run_id>/`.
     6. Spawn `firecracker --api-sock <socket>` via the chokepoint `subprocess.Popen`.
     7. Configure machine: `PUT /machine-config`, `PUT /boot-source` (kernel), `PUT /drives/rootfs`, `PUT /drives/work` (copy-in overlay).
     8. `PUT /actions {action_type:"InstanceStart"}`.
     9. Exec `spec.cmd` via vsock; tee stdout/stderr to `spec.logs_dir/{stdout.log,stderr.log}`.
     10. Wait up to `spec.time_budget_seconds`; on expiry, teardown + `timed_out=True`.
     11. Copy out workdir via `tar` over vsock to `spec.copy_out_root`.
     12. Teardown: SIGTERM the firecracker process, remove jail dir, unlink socket.
     13. Return `SandboxRun(backend="firecracker", gate_isolation_class="microvm", ...)`.
3. Add `requests>=2.31` and `blake3>=0.4` to `pyproject.toml` if not already declared (S2-01 already added `blake3`).
4. Register via `@register_sandbox_backend("firecracker")` in `firecracker/__init__.py` and re-export at `sandbox/__init__.py`.
5. Wire a structlog event constant `sandbox.firecracker.boot` (logged on InstanceStart) and `sandbox.firecracker.teardown` (logged on cleanup, even on exception).
6. Defer network policy and digest enforcement plumbing to S6-02 and S6-03 respectively — but emit a `network=scoped` placeholder `NotImplementedError` raise so S6-02 has an obvious wiring point.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/sandbox/firecracker/test_client.py`

```python
# tests/sandbox/firecracker/test_client.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codegenie.sandbox.contract import SandboxSpec
from codegenie.sandbox.errors import (
    FirecrackerBinaryMissing,
    FirecrackerKvmMissing,
    FirecrackerRootfsMissing,
)
from codegenie.sandbox.firecracker.client import FirecrackerClient


@pytest.fixture
def client(tmp_path: Path) -> FirecrackerClient:
    fc = tmp_path / "firecracker"
    fc.write_bytes(b"\x7fELF stub")
    fc.chmod(0o755)
    return FirecrackerClient(
        firecracker_path=fc,
        vmlinux_digest="aa" * 32,
        rootfs_digest="bb" * 32,
    )


def test_execute_raises_kvm_missing_when_dev_kvm_absent(
    client: FirecrackerClient, tmp_path: Path
) -> None:
    spec = SandboxSpec(
        cmd=["true"],
        copy_in=[],
        logs_dir=tmp_path / "logs",
        copy_out_root=tmp_path / "out",
        time_budget_seconds=60,
        memory_limit_mib=512,
        network="none",
        egress_allowlist=[],
        env={},
    )
    with patch("codegenie.sandbox.firecracker.client.Path.exists", return_value=False):
        with pytest.raises(FirecrackerKvmMissing) as exc:
            client.execute(spec)
        assert "/dev/kvm" in str(exc.value)
        assert "docker_in_docker" in str(exc.value), "error must suggest fallback"


@pytest.mark.skip_if_no_kvm
def test_execute_boots_microvm_and_returns_microvm_class(
    client: FirecrackerClient, tmp_path: Path
) -> None:
    spec = SandboxSpec(
        cmd=["echo", "hello"],
        copy_in=[],
        logs_dir=tmp_path / "logs",
        copy_out_root=tmp_path / "out",
        time_budget_seconds=60,
        memory_limit_mib=512,
        network="none",
        egress_allowlist=[],
        env={"PATH": "/usr/bin"},
    )
    run = client.execute(spec)
    assert run.backend == "firecracker"
    assert run.gate_isolation_class == "microvm"
    assert run.exit_code == 0
    assert (tmp_path / "logs" / "stdout.log").read_text().strip() == "hello"


def test_health_reports_all_four_preconditions(
    client: FirecrackerClient, tmp_path: Path
) -> None:
    # All four bad in this fixture (no /dev/kvm in unit env, fake binary digest, missing rootfs).
    health = client.health()
    assert health.reachable is False
    assert "kvm_missing" in health.reasons
    assert health.confidence == "low"


def test_execute_cleans_up_jail_dir_on_exception(
    client: FirecrackerClient, tmp_path: Path
) -> None:
    spec = SandboxSpec(
        cmd=["false"], copy_in=[], logs_dir=tmp_path / "logs",
        copy_out_root=tmp_path / "out", time_budget_seconds=1,
        memory_limit_mib=512, network="none", egress_allowlist=[], env={},
    )
    with patch.object(client, "_assert_kvm"), \
         patch.object(client, "_assert_binary_digest", side_effect=FirecrackerBinaryMissing("digest mismatch: aa12..")):
        with pytest.raises(FirecrackerBinaryMissing):
            client.execute(spec)
    # No jail dir survives the failed call.
    assert not any((tmp_path / ".codegenie" / "sandbox" / "runs").glob("*")) \
        if (tmp_path / ".codegenie").exists() else True
```

Use `pytest.mark.skip_if_no_kvm` for KVM-required tests. The S6-05 conftest will define the marker; for this story, register it in `tests/sandbox/firecracker/conftest.py` (an `os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)` predicate).

### Green — make it pass

Smallest implementation: `_assert_kvm` checks `Path("/dev/kvm").exists()` and `os.access(..., os.R_OK | os.W_OK)`; raises `FirecrackerKvmMissing(f"/dev/kvm not accessible; run on a KVM-capable Linux host or use the docker_in_docker backend")`. `_assert_binary_digest` BLAKE3-hashes the binary, compares to `vmlinux_digest`/`rootfs_digest`/loader-pinned `firecracker` digest. `execute()` runs the preconditions in order, then the boot+exec+copy-out flow. `health()` mirrors but never raises.

### Refactor — clean up

- Split the API-socket client into a `_FirecrackerApiSocket` helper (so the test can mock it cleanly).
- Pull `_compute_blake3` into a module-level helper reused by `health()` and the assertion methods.
- Replace any inline `print` with structlog `sandbox.firecracker.*` events.
- Ensure `_teardown` runs in a `try/finally` around the entire `execute()` body — cleanup is unconditional.
- Add typed return annotation on every private method; `from __future__ import annotations` at top.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/firecracker/__init__.py` | New module — register backend, re-export client. |
| `src/codegenie/sandbox/firecracker/client.py` | New module — `FirecrackerClient` boot/exec/copy-out. |
| `src/codegenie/sandbox/errors.py` | Add `FirecrackerKvmMissing`, `FirecrackerBinaryMissing`, `FirecrackerRootfsMissing`. |
| `src/codegenie/sandbox/__init__.py` | Re-export the three new errors. |
| `tests/sandbox/firecracker/__init__.py` | Make the test package importable. |
| `tests/sandbox/firecracker/conftest.py` | Define `pytest.mark.skip_if_no_kvm` marker. |
| `tests/sandbox/firecracker/test_client.py` | Red test + unit-level coverage. |
| `pyproject.toml` | Add `requests` dep if not present. |

## Out of scope

- Host-side TAP + nftables network policy — S6-02 (this story raises `NotImplementedError` on `network="scoped"`).
- Rootfs digest enforcement against `tools/digests.yaml` — S6-03 (this story compares against the constructor-passed digest only).
- `auto_detect()` selecting Firecracker on KVM hosts — S6-04.
- The KVM-gated CI smoke test and weekly cron — S6-05.
- Warm pool / cold-start optimization — Phase 9 territory per `phase-arch-design.md §Non-goal 3`.

## Notes for the implementer

- Firecracker's API socket pattern is one-shot: spawn the binary with `--api-sock <path>`, then `PUT` JSON to `<path>` over a Unix-domain HTTP session (`requests` does not natively support UDS — use `requests-unixsocket` or hand-roll an `httpx` client over `httpx.HTTPTransport`).
- `_assert_kvm` runs at *every* `execute()` call, not at `__init__` — the laptop may sleep+wake or the runner may rotate hosts mid-process; check fresh.
- vsock exec is the one rough edge — keep the in-guest exec helper to a single `/sbin/init` busybox script that reads `cmd` from `/etc/sandbox-cmd`; do not build a full guest agent. Phase 6 will lift this if it proves load-bearing.
- The error message for `FirecrackerKvmMissing` must include the literal string `docker_in_docker` so S6-04's auto-detect fallback log can match on it.
- On macOS contributor laptops, every test in this file must be either pure mock or `skip_if_no_kvm`; do not let a real `/dev/kvm` check leak (mock with `patch("codegenie.sandbox.firecracker.client.Path.exists")`).
- Teardown must be idempotent — `codegenie sandbox gc` will retry it; raising on "already cleaned" is wrong.
- Resist building a "Firecracker is ready" wait-loop longer than 5 s; if boot fails fast, surface the failure fast — operator runs `codegenie sandbox health` for diagnostics.
