# Story S6-01 — `FirecrackerClient` boot + exec + copy-out

**Step:** Step 6 — FirecrackerClient backend + KVM-gated CI smoke test
**Status:** Ready (HARDENED 2026-05-25)
**Effort:** L
**Depends on:**
- S1-01 (errors + structlog + warning-ID `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` regex + canonical-events table append-only)
- S1-02 (`SandboxClient` Protocol + the four frozen `extra="forbid"` models + `RunId` / `SandboxSpecHash` NewTypes + cross-field validator `(firecracker, microvm)`)
- S1-05 (`@register_sandbox_backend` decorator)
- S3-02 HARDENED (FCS + Hexagonal DI port + closed-Literal `reason` + canonical-Literal AST walker + module-purity AST walker patterns this story inherits as third concrete consumer)
**ADRs honored:**
- ADR-0001 — `sandbox/firecracker/client.py` is one of the (now-three) allowlisted subprocess chokepoints; S6-02 will additively widen to `network_policy.py`.
- ADR-0004 — every Firecracker `SandboxRun` carries `gate_isolation_class="microvm"` + `backend="firecracker"` (closed Literal pair enforced by the S1-02 `_check_run_invariants` model_validator).
- ADR-0006 — `FirecrackerClient` implements `SandboxClient` Protocol structurally (no inheritance from `DockerInDockerClient`).

## Validation notes (2026-05-25 HARDENED)

This draft had thirteen block-tier weaknesses (see [`_validation/S6-01-firecracker-client-kvm-boot.md`](_validation/S6-01-firecracker-client-kvm-boot.md)). Headlines:

- **`SandboxSpec.logs_dir` / `SandboxSpec.copy_out_root` are phantom fields** — S1-02 places both on `SandboxRun` (the client outputs them, never accepts them as input). The draft's TDD fixtures constructed `SandboxSpec(logs_dir=..., copy_out_root=...)` and would have failed at `extra="forbid"` validation on the first import. Family-bug identical to `EnvAllowlist` that S3-02 caught.
- **Six required `SandboxSpec` fields were missing** from every TDD fixture (`pids_limit`, `base_image`, `enable_trace`, `copy_out`, `label`, `sandbox_spec_hash`).
- **Warning-ID regex violation** — `"kvm_missing"` etc. lack the mandatory `<namespace>.<symbol>` form. S3-02 paid this rent (`buildx_missing` → `sandbox.buildx_missing`); S6-01 inherits.
- **`SendCtrlAltDel` ≠ `SIGKILL`** — ACPI graceful shutdown is not a hard kill. AC-8 was semantically wrong.
- **`requests` doesn't speak UDS** — impl outline and Notes contradicted each other; pyproject change would have been wrong. Picked `httpx` (S3-02 ecosystem precedent).
- **Third concrete consumer of S3-02-HARDENED patterns** completes the rule-of-three on Hexagonal DI port + functional-core/imperative-shell + `_BACKEND_NAME` / `_GATE_ISOLATION_CLASS` `Final` constants + closed-Literal `SandboxBackendError.reason` discriminator + module-purity AST walker. These were elevated from Notes to AC-tier.

Resolution: ~75 numbered ACs across 18 sections, a five-test-file TDD plan mirroring S3-02, and an expanded Files-to-touch table.

## Context

Phase 5's second `SandboxClient` backend is real Firecracker (not a stub) so we generate ADR-0019-grade evidence of microVM cold-start latency, kernel feature requirements, and per-evaluation cost. This story ships the API-socket-driven `FirecrackerClient` that boots a pinned `vmlinux`+`rootfs.ext4`, mounts a copy-in tar, execs the gate `cmd`, and tars the workdir back out — without network policy (deferred to S6-02), without digests-yaml enforcement (deferred to S6-03), without auto-detect wiring (deferred to S6-04), but with the three structured-failure errors the auto-detect path (S6-04) needs to fall back cleanly.

**Pattern lineage:** S6-01 is the **third concrete consumer** of the `SandboxClient` Protocol + the S3-02-HARDENED Hexagonal DI / functional-core/imperative-shell / closed-Literal `reason` / canonical-`Final`-constants / module-purity AST-walker stack. The rule of three is reached; what S3-02 surfaced as Notes for S6-01 forward is now mandatory inheritance. See `_validation/S3-02-did-client-sdk-core.md §"Forward-compat anchor"` for the literal mandates.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — FirecrackerClient` (lines ~495-502) — public interface, internal structure, performance envelope, failure behavior.
  - `../phase-arch-design.md §Logical view` (line ~83) — `FirecrackerClient` class diagram (`firecracker_path`, `vmlinux_digest`, `rootfs_digest`).
  - `../phase-arch-design.md §Physical view` (line ~329) — KVM runner box: `firecracker bin → KVM → microVM (vmlinux+rootfs, microvm class)`.
  - `../phase-arch-design.md §Process view` — `SandboxClient.execute` sequence (copy-in → start → exec → copy-out).
  - `../phase-arch-design.md §Data model` (lines ~655-684) — the canonical 13+4 `SandboxRun` fields, `SandboxSpec` 13-field set, `SandboxHealth` shape. **Note the arch literal `"kvm_missing"` at §Edge case 15 (line 867) is an erratum** — CLAUDE.md's namespace regex requires `sandbox.kvm_missing`. This story follows CLAUDE.md.
- **Phase ADRs:**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — `subprocess` here is one of three allowlisted chokepoint files (`sandbox/firecracker/client.py`); S6-02 additively widens to `network_policy.py`.
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — every Firecracker `SandboxRun` carries `gate_isolation_class="microvm"` and `backend="firecracker"`.
  - `../ADRs/0006-protocol-vs-abc-convention.md` — backend implements `SandboxClient` Protocol structurally; no inheritance.
- **Production ADRs:**
  - `../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md` — microVM-for-gates production target this evidences.
  - `../../../production/adrs/0019-sandbox-stack.md` — phase 5 generates real Firecracker numbers for the eventual resolution.
- **Source design:** `../final-design.md §Synthesis ledger row "Real Firecracker (not stub)"`.
- **Prior validation (mandatory read):**
  - `_validation/S3-02-did-client-sdk-core.md` — sibling backend's HARDENED report. The "Forward-compat anchor" section names S6-01 explicitly with the patterns to inherit.
  - `_validation/S1-02-sandbox-contract-protocol-models.md` — the 13+4-field `SandboxRun` + `RunId` NewType + cross-field validator that this story consumes.
- **Existing code:**
  - `src/codegenie/sandbox/contract.py` (from S1-02) — `SandboxClient` Protocol, `SandboxSpec`, `SandboxRun`, `SandboxHealth`, `RunId`, `SandboxSpecHash`.
  - `src/codegenie/sandbox/did/client.py` (from S3-02) — sibling backend; mirror its module-level `Final` discipline, `_construct_sandbox_run`-style pure helpers, and event-naming convention.
  - `src/codegenie/sandbox/did/_uuid7.py` (from S3-02) — re-use `generate_run_id() -> RunId`. Do NOT re-vendor; future cleanup may hoist to `sandbox/_uuid7.py`, but Rule 2 says note the opportunity and defer.
  - `src/codegenie/sandbox/did/_docker_types.py` (from S3-02) — TypedDict-shim precedent for `_firecracker_api_types.py` to follow.
  - `src/codegenie/sandbox/errors.py` (from S1-01) — extend with the three new structured failures; the new errors carry a closed-Literal `reason` field per the inherited pattern.
  - `src/codegenie/sandbox/registry.py` (from S1-05) — register via `@register_sandbox_backend("firecracker")`.
  - `src/codegenie/sandbox/_events.py` (or wherever S1-01 placed the canonical-events table) — append-only the new STARTED/COMPLETED/FAILED triples.
- **External docs:**
  - Firecracker API socket reference: <https://github.com/firecracker-microvm/firecracker/blob/main/docs/api_requests/actions.md> — `PUT /actions {action_type:"InstanceStart"}` and the `/boot-source`, `/drives/rootfs`, `/machine-config` shapes. (Note: `SendCtrlAltDel` is ACPI graceful shutdown, NOT a SIGKILL — see AC-TIMEOUT-* for the correct termination contract.)
  - Firecracker vsock guest exec pattern: <https://github.com/firecracker-microvm/firecracker/blob/main/docs/vsock.md> — needed by the deferred `_VsockExecPort` real implementation in S6-03.
  - RFC 9562 §5.7 — UUIDv7 spec (the `generate_run_id` helper inherits from S3-02).
- **CLAUDE.md anchors:**
  - "Warning + error IDs match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`" — story uses `sandbox.kvm_missing`, `sandbox.firecracker.binary_digest_mismatch`, etc.
  - "Newtype identifiers" — `RunId` consumed at generation site.
  - "Extension by addition" — additive registry decoration; new event names append to S1-01 canonical-table.
  - "Functional core / imperative shell" — five pure helpers + thin shell.

## Goal

Ship `src/codegenie/sandbox/firecracker/client.py` exposing `FirecrackerClient` such that `execute(spec: SandboxSpec) -> SandboxRun` boots a microVM via the API socket against pinned `vmlinux`+`rootfs.ext4`, runs `spec.cmd` through a `_VsockExecPort` injection, copy-ins from `spec.copy_in`, copy-outs to a client-generated `copy_out_root` under `runs_root / run_id /`, and returns a fully-populated `SandboxRun` with all 13+4 contract fields valid against the S1-02 `_check_run_invariants` validator. `health()` runs four precondition checks (kvm + binary digest + vmlinux digest + rootfs digest), populates `SandboxHealth` with namespaced canonical reason IDs and a deterministic confidence value, and never raises. `FirecrackerKvmMissing`, `FirecrackerBinaryMissing`, `FirecrackerRootfsMissing` (each carrying a closed-Literal `reason`) are raised on first `execute()` (not at `__init__`) when their respective precondition fails, with a message matching the S6-04 auto-detect contract for `FirecrackerKvmMissing`.

## Acceptance criteria

### A. Public surface + module discipline

- [ ] **AC-A1 — Imports:** `from codegenie.sandbox.firecracker.client import FirecrackerClient` and `from codegenie.sandbox.errors import FirecrackerKvmMissing, FirecrackerBinaryMissing, FirecrackerRootfsMissing` both succeed with no side effects.
- [ ] **AC-A2 — Constructor signature:** `FirecrackerClient(*, firecracker_path: Path, vmlinux_path: Path, rootfs_path: Path, firecracker_digest: str, vmlinux_digest: str, rootfs_digest: str, runs_root: Path = Path(".codegenie/sandbox/runs"), api_socket_factory: ApiSocketFactory = _default_api_socket_factory, process_handle_factory: ProcessHandleFactory = _default_process_handle_factory, vsock_exec_port: VsockExecPort = _default_vsock_exec_port, clock: Callable[[], datetime] = _default_clock)`. The factory + port parameters are Hexagonal DI seams (S3-02 `docker_factory` precedent); the `runs_root` parameter replaces the phantom `spec.logs_dir` / `spec.copy_out_root` — the client *generates* `logs_dir` and `copy_out_root` from `runs_root / run_id /`.
- [ ] **AC-A3 — `RunId` generation at the source:** `run_id` is minted via `from codegenie.sandbox.did._uuid7 import generate_run_id` (re-use; do NOT re-vendor) and is typed `RunId`. `typing.get_type_hints(...)["run_id"] is RunId`.
- [ ] **AC-A4 — `from __future__ import annotations`** appears as the first non-docstring statement of `client.py`.
- [ ] **AC-A5 — `__all__`:** `set(codegenie.sandbox.firecracker.client.__all__) == {"FirecrackerClient"}`. The factory / port types and the three error subclasses re-export from `sandbox.firecracker.__init__` and `sandbox.errors` respectively.
- [ ] **AC-A6 — Module-level `Final` constants:** `_BACKEND_NAME: Final[str] = "firecracker"`, `_GATE_ISOLATION_CLASS: Final[str] = "microvm"`. Inline string literals of either value anywhere else in `client.py` are forbidden (enforced by AC-CANONICAL-*).
- [ ] **AC-A7 — ADR docstring:** module docstring cites ADR-0001, ADR-0004, ADR-0006 by ID.

### B. Hexagonal DI ports

- [ ] **AC-B1 — `ApiSocketFactory` Protocol** defined as `Callable[[Path], _ApiSocket]` where `_ApiSocket` exposes `put(path: str, body: Mapping[str, Any]) -> _ApiSocketResponse`. Default impl uses `httpx` UDS transport.
- [ ] **AC-B2 — `ProcessHandleFactory` Protocol** defined as `Callable[[Path, Path], _ProcessHandle]` where `_ProcessHandle` exposes `wait(timeout: float | None) -> int`, `terminate() -> None`, `kill() -> None`. Default impl uses `subprocess.Popen` (the chokepoint call).
- [ ] **AC-B3 — `VsockExecPort` Protocol** exposes `exec(cmd: Sequence[str], copy_in_tar: bytes, timeout_seconds: int) -> VsockExecResult`. **Default impl raises `NotImplementedError("S6-03 ships the real in-guest exec helper; S6-01 ports the seam only")`** — S6-01 ships the seam; S6-03 wires the real helper. Unit tests inject a fake.
- [ ] **AC-B4 — Tests inject through ports, never patch `subprocess.Popen` or `httpx`** — the mock boundary is the constructor parameter, not the transport.

### C. `execute()` happy-path + precondition ordering

- [ ] **AC-C1 — Precondition order is strict:** `execute(spec)` runs `_assert_kvm() → _assert_binary_digest() → _assert_rootfs_artifacts()` in that order. Each `_assert_*` is a pure-ish method (no I/O beyond the precondition check); a positive parametrized test (AC-PRECOND-3) asserts via mock `call_count` that when precondition N fails, preconditions N+1..k are NEVER consulted.
- [ ] **AC-C2 — Preconditions run at `execute()` time, not at `__init__`** — the host may sleep+wake or the runner may rotate hosts mid-process. Constructor performs zero filesystem reads; `_assert_*` reads happen per-call.
- [ ] **AC-C3 — `spec.network == "scoped"` raises `NotImplementedError("network='scoped' deferred to S6-02; see ADR-0009")`** as the explicit wiring point for S6-02. Verified by `tests/sandbox/firecracker/test_client_core.py::test_scoped_network_not_implemented`.
- [ ] **AC-C4 — Happy path (`spec.network == "none"`):** `execute()` (a) mints `run_id`, (b) creates `runs_root / run_id /` jail dir, (c) builds copy-in tar from `spec.copy_in`, (d) starts the firecracker process via `process_handle_factory`, (e) configures the VM via `api_socket_factory` PUTs (`/machine-config`, `/boot-source`, `/drives/rootfs`, `/drives/work`, `/actions InstanceStart`), (f) waits for socket readiness up to 5 s (`AC-BOOT-WAIT-1`), (g) calls `vsock_exec_port.exec(spec.cmd, copy_in_tar, spec.time_budget_seconds)`, (h) streams stdout/stderr to `<jail_dir>/stdout.log` + `<jail_dir>/stderr.log`, (i) copy-outs workdir tar to `<jail_dir>/copy_out/`, (j) constructs `SandboxRun` via `_construct_sandbox_run(...)` pure helper, (k) tears down unconditionally (`AC-CLEANUP-*`), (l) returns the run.

### D. Full `SandboxRun` 13+4-field coverage

For every field on `SandboxRun`, a parametrized happy-path test asserts the populated value matches a known rule. Rules:

- [ ] **AC-D1 — `run_id`:** RFC 9562 UUIDv7 hex (32 hex chars after `-` removal), `version_nibble == 7`, monotonically increasing across two successive `generate_run_id()` calls; typed `RunId`.
- [ ] **AC-D2 — `spec`:** identical (`is`) to the input `SandboxSpec` (no copy).
- [ ] **AC-D3 — `backend`:** byte-exactly `_BACKEND_NAME` (`"firecracker"`). AST walker asserts the literal occurs exactly once in `client.py`.
- [ ] **AC-D4 — `gate_isolation_class`:** byte-exactly `_GATE_ISOLATION_CLASS` (`"microvm"`). AST walker asserts the literal occurs exactly once.
- [ ] **AC-D5 — `started_at`:** captured immediately before `_handle.wait()` (boot-complete moment); `tzinfo=timezone.utc`.
- [ ] **AC-D6 — `ended_at`:** captured immediately after `vsock_exec_port.exec` returns OR after termination signal completes (whichever fires); `tzinfo=timezone.utc`; `>= started_at` (S1-02 validator enforces).
- [ ] **AC-D7 — `exit_code`:** from `VsockExecResult.exit_code`. On timeout: `124` (POSIX `timeout(1)` convention). On OOM: `137` (POSIX `128 + SIGKILL`).
- [ ] **AC-D8 — `duration_ms`:** `int((ended_at - started_at).total_seconds() * 1000)`; `>= 0`.
- [ ] **AC-D9 — `microvm_seconds`:** `(ended_at - started_at).total_seconds()` as `float >= 0.0`.
- [ ] **AC-D10 — `image_pull_bytes`:** `0` (Firecracker does not pull container images; pinned rootfs is on-disk). Forever-stub for `backend == "firecracker"`.
- [ ] **AC-D11 — `build_cache_hit`:** `False` (no buildx). Forever-stub.
- [ ] **AC-D12 — `logs_dir`:** `runs_root / run_id /` (resolved absolute); `Path.is_absolute() is True`; idempotent `mkdir(parents=True, exist_ok=True)`.
- [ ] **AC-D13 — `trace_path`:** `None` for this story; S4-03 will populate when `spec.enable_trace=True` lands strace-in-VM.
- [ ] **AC-D14 — `copy_out_root`:** `logs_dir / "copy_out"` (resolved absolute); exists after `execute()`.
- [ ] **AC-D15 — `timed_out`:** `True` iff the timeout grace window expired (`AC-TIMEOUT-*`); else `False`.
- [ ] **AC-D16 — `killed_by_oom`:** `True` iff OOM evidence detected (`AC-OOM-*`); else `False`.
- [ ] **AC-D17 — Cross-field invariants from S1-02 hold:** `(backend, gate_isolation_class) == ("firecracker", "microvm")`; `not (timed_out and killed_by_oom)`; `ended_at >= started_at`. (S1-02's `_check_run_invariants` catches violations at construction; these ACs are positive assertions on the happy-path test fixture.)

### E. Canonical Literal — AST walker

- [ ] **AC-E1 — AST single-occurrence:** `tests/sandbox/firecracker/test_client_purity.py` walks the AST of `src/codegenie/sandbox/firecracker/client.py` and asserts the strings `"firecracker"` and `"microvm"` each appear exactly once (in the `_BACKEND_NAME` / `_GATE_ISOLATION_CLASS` `Final` constant assignments). Any third occurrence — even in a docstring — fails the test, forcing constant re-use.
- [ ] **AC-E2 — Positive Literal pinning:** the test imports the constants and asserts equality (`_BACKEND_NAME == "firecracker"`, `_GATE_ISOLATION_CLASS == "microvm"`).

### F. Closed-`Literal` `SandboxBackendError.reason` discriminator

- [ ] **AC-F1 — `SandboxBackendError` (or its `FirecrackerSandboxError` subclass) declares a closed `reason: Literal[...]` field.** The closed set for S6-01 is:
  ```python
  FirecrackerReason = Literal[
      "sandbox.kvm_missing",
      "sandbox.firecracker.binary_missing",
      "sandbox.firecracker.binary_digest_mismatch",
      "sandbox.firecracker.vmlinux_digest_mismatch",
      "sandbox.firecracker.rootfs_digest_mismatch",
      "sandbox.firecracker.api_socket_unreachable",
      "sandbox.firecracker.instance_start_failed",
      "sandbox.firecracker.vsock_exec_failed",
      "sandbox.firecracker.copy_out_failed",
      "sandbox.firecracker.teardown_failed",
  ]
  ```
  Extending this set requires an ADR amendment (per S3-02 sealed-Literal precedent). Phase 11 / 13 key on the values.
- [ ] **AC-F2 — Each of the three precondition errors carries its `reason`:**
  - `FirecrackerKvmMissing` → `reason="sandbox.kvm_missing"`, message contains both `/dev/kvm` and the literal `"docker_in_docker"` (S6-04 fallback contract).
  - `FirecrackerBinaryMissing` → `reason="sandbox.firecracker.binary_missing"` if path absent / not executable; `reason="sandbox.firecracker.binary_digest_mismatch"` if BLAKE3 mismatched. Message includes expected and observed 8-char hex prefixes (e.g., `"expected=ab12cd34 actual=ab12dead"`).
  - `FirecrackerRootfsMissing` → `reason="sandbox.firecracker.vmlinux_digest_mismatch"` or `"sandbox.firecracker.rootfs_digest_mismatch"`; message names which artifact (`vmlinux` vs `rootfs.ext4`) failed.
- [ ] **AC-F3 — `_wrap_api_error(exc: Exception) -> SandboxBackendError`** is a pure Adapter mapping `httpx.HTTPError` / `httpx.RemoteProtocolError` / `subprocess.SubprocessError` / `OSError` → `SandboxBackendError(reason=<phase-specific Literal>, ...)`. Per-phase mapping table is documented in `Notes for the implementer`.

### G. Spec-feature fail-loud + deferred-warning policy

- [ ] **AC-G1 — `spec.network == "scoped"` →** `NotImplementedError` (covered by AC-C3).
- [ ] **AC-G2 — `spec.enable_trace == True` → WARNING event** `sandbox.firecracker.enable_trace_unsupported` emitted; `SandboxRun.trace_path=None`. S4-03 will wire strace-in-VM later (mirrors S3-02 AC-SPEC-DEFER-5).
- [ ] **AC-G3 — `spec.copy_out` non-empty selectors:** for S6-01, the entire workdir is copy-out by default; specific selectors deferred to S6-03. WARNING event if `spec.copy_out` contains paths the impl will not filter against.
- [ ] **AC-G4 — `spec.copy_in` non-empty:** tarred into the guest workdir (`AC-COPYIN-*`).
- [ ] **AC-G5 — `spec.time_budget_seconds`:** enforced (`AC-TIMEOUT-*`).
- [ ] **AC-G6 — `spec.memory_limit_mib`:** translated to `/machine-config` `mem_size_mib`; positive integer enforced by S1-02 contract.
- [ ] **AC-G7 — `spec.pids_limit`:** Firecracker does not natively pid-limit microVMs; emit WARNING `sandbox.firecracker.pids_limit_unsupported` and proceed (the microVM's own kernel cgroup configuration is set in the rootfs by S6-03).
- [ ] **AC-G8 — `spec.egress_allowlist`:** ignored when `spec.network == "none"` (S1-02 model_validator already rejects non-empty allowlist with `network="none"`); for `"scoped"` paths, raises `NotImplementedError` per AC-C3.

### H. `health()` confidence mapping

- [ ] **AC-H1 — Five-row confidence table:**
  | kvm | fc digest | vmlinux digest | rootfs digest | `reachable` | `confidence` | `reasons` |
  |---|---|---|---|---|---|---|
  | ✓ | ✓ | ✓ | ✓ | True | `"high"` | `[]` |
  | ✗ | * | * | * | False | `"low"` | `["sandbox.kvm_missing"]` |
  | ✓ | ✗ | * | * | False | `"low"` | `["sandbox.firecracker.binary_digest_mismatch"]` |
  | ✓ | ✓ | ✗ | * | False | `"low"` | `["sandbox.firecracker.vmlinux_digest_mismatch"]` |
  | ✓ | ✓ | ✓ | ✗ | False | `"low"` | `["sandbox.firecracker.rootfs_digest_mismatch"]` |
  Multiple-failure case: all matching `reasons` reported (alphabetized).
- [ ] **AC-H2 — `reasons` and `warnings` are alphabetized** at `SandboxHealth` construction; parametrized test asserts ordering.
- [ ] **AC-H3 — `detected_at`** is `tzinfo=timezone.utc`; `backend == "firecracker"`.
- [ ] **AC-H4 — `health()` never raises.** Any exception inside is captured and surfaced as `reasons=["sandbox.firecracker.health_probe_error"]` + a WARNING event.
- [ ] **AC-H5 — Every reason ID matches the CLAUDE.md regex** `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Module-level `_WARNING_IDS: Final[frozenset[str]]` enumerates them; `client.py` raises `AssertionError` at import time if any value violates the regex (mirrors Phase-1 ADR-0007 convention).

### I. Cleanup discipline (8-cell parametrized grid)

- [ ] **AC-I1 — `execute()` body is wrapped in `try/finally`;** `_teardown(run_id)` runs unconditionally on success or any exception.
- [ ] **AC-I2 — `_teardown(run_id)` is idempotent:** double-call does not raise; ATL retries (`codegenie sandbox gc`) rely on this.
- [ ] **AC-I3 — Teardown removes:** (a) API socket file, (b) firecracker process (SIGTERM → grace → SIGKILL), (c) jail dir overlays (vmlinux/rootfs symlinks), (d) `<jail_dir>` *except* `<jail_dir>/stdout.log`, `<jail_dir>/stderr.log`, `<jail_dir>/copy_out/` (these are part of `SandboxRun.logs_dir` / `copy_out_root` and must survive for downstream consumers).
- [ ] **AC-I4 — Cleanup-failure path:** `_teardown` failures are logged as WARNING `sandbox.firecracker.teardown_failed` events but do NOT mask the original exception. If `execute()` would have succeeded, teardown failure raises `SandboxBackendError(reason="sandbox.firecracker.teardown_failed")`.
- [ ] **AC-I5 — Parametrized cleanup grid:** `tests/sandbox/firecracker/test_client_core.py::test_cleanup_on_each_failure_phase` parametrized over `["kvm", "binary_digest", "rootfs_digest", "boot", "exec", "copy_out", "timeout", "oom"]`. Each case: trigger the failure, assert the jail dir is torn down (via `monkeypatch.chdir(tmp_path)` so paths are tmp-scoped), assert teardown event was emitted, assert API socket file no longer exists.

### J. OOM detection

- [ ] **AC-J1 — Primary OOM signal:** `VsockExecResult.exit_code == 137`. If observed, `killed_by_oom=True`.
- [ ] **AC-J2 — Secondary OOM signal (dmesg fallback):** when the in-guest process is killed by the kernel's OOM-killer but the vsock channel returns no exit code (process died too fast), the impl reads dmesg buffer over the API socket / serial console for the pattern `r"Out of memory: Killed process \d+"` referencing the cgroup. If matched, `killed_by_oom=True`.
- [ ] **AC-J3 — Signal-absence WARNING:** if `exit_code != 137` AND no dmesg evidence AND the process did not exit normally, emit WARNING `sandbox.firecracker.oom_signal_absent` and set `killed_by_oom=False` (do not guess). This is the silent-miss surface — making it loud per Rule 12.

### K. Timeout (replaces the draft's CtrlAltDel ≠ SIGKILL bug)

- [ ] **AC-K1 — Grace window:** when `vsock_exec_port.exec(...)` does not return within `spec.time_budget_seconds`, send `SIGTERM` to the firecracker host process (via `_handle.terminate()`), wait `_TIMEOUT_GRACE_SECONDS = 3` for clean shutdown.
- [ ] **AC-K2 — Hard kill:** if the process is still alive after the grace window, send `SIGKILL` (`_handle.kill()`).
- [ ] **AC-K3 — `timed_out=True`** in the resulting `SandboxRun`. `exit_code = 124` (POSIX timeout convention).
- [ ] **AC-K4 — `SendCtrlAltDel` is NOT used** for timeout — it is ACPI graceful shutdown, not a kill signal. AST walker asserts no `"SendCtrlAltDel"` string occurs in `client.py`.

### L. Registry round-trip + Protocol structural conformance

- [ ] **AC-L1 — `@register_sandbox_backend("firecracker")`** decorates `FirecrackerClient` in `src/codegenie/sandbox/firecracker/__init__.py`.
- [ ] **AC-L2 — Registry round-trip:** `from codegenie.sandbox import registry; registry.get_backend("firecracker") is FirecrackerClient`.
- [ ] **AC-L3 — Protocol conformance:** `isinstance(<FirecrackerClient instance>, SandboxClient) is True` (the `@runtime_checkable Protocol` from S1-02).
- [ ] **AC-L4 — Conflict-free coexistence with DinD:** `registry.get_backend("docker_in_docker")` still returns `DockerInDockerClient`; both backends co-registered.

### M. RunId / uuid7 helper re-use

- [ ] **AC-M1 — Import path:** `from codegenie.sandbox.did._uuid7 import generate_run_id`. No new uuid7 helper vendored. Notes-for-implementer records the future hoist opportunity to `sandbox/_uuid7.py` (rule-of-three on the helper not yet reached).
- [ ] **AC-M2 — Single call site in `client.py`:** AST walker asserts `generate_run_id` appears exactly once.

### N. Dependencies

- [ ] **AC-N1 — `httpx>=0.27`** added to `pyproject.toml` runtime deps (replaces the draft's `requests`; `requests` does not speak UDS natively). UDS transport via `httpx.HTTPTransport(uds=<path>)`.
- [ ] **AC-N2 — `blake3>=0.4`** already present from S2-01; verify import succeeds.
- [ ] **AC-N3 — `make fence`** stays green: `httpx` is added to the closure-wide *admitted* set (it is not an LLM SDK); no `FORBIDDEN_LLM_SDKS` update needed. Confirmed by running `pytest tests/unit/test_pyproject_fence.py` after dep add.

### O. Module purity (AST walker)

- [ ] **AC-O1 — `tests/sandbox/firecracker/test_client_purity.py`** walks the AST of `src/codegenie/sandbox/firecracker/client.py` and asserts:
  - (a) imports allowlist: `__future__`, `dataclasses`, `datetime`, `os`, `pathlib`, `signal`, `subprocess`, `tarfile`, `time`, `typing`, `httpx`, `blake3`, `structlog`, `codegenie.sandbox.*`, `codegenie.types.*`. Anything else fails.
  - (b) banned imports outside the chokepoint test file: `langgraph`, `openai`, `anthropic`, `transformers`, `sentence_transformers`, `torch`, `chromadb`.
  - (c) `_BACKEND_NAME` / `_GATE_ISOLATION_CLASS` canonical-Literal single-occurrence (AC-E1).
  - (d) `_WARNING_IDS: Final[frozenset[str]]` declared at module level; every member matches the CLAUDE.md regex.
  - (e) No bare structlog event strings — every `logger.info(...)` / `logger.warning(...)` first positional argument must be a name from the canonical events table (re-exported as constants from `sandbox._events`).
  - (f) No `"SendCtrlAltDel"` string anywhere in `client.py` (AC-K4).

### P. structlog event discipline

- [ ] **AC-P1 — Event-name verbs follow STARTED / COMPLETED / FAILED convention** (S3-02 + S1-01 inheritance):
  - `sandbox.firecracker.boot_started`, `sandbox.firecracker.boot_completed`, `sandbox.firecracker.boot_failed`
  - `sandbox.firecracker.exec_started`, `sandbox.firecracker.exec_completed`, `sandbox.firecracker.exec_failed`
  - `sandbox.firecracker.copy_out_started`, `sandbox.firecracker.copy_out_completed`, `sandbox.firecracker.copy_out_failed`
  - `sandbox.firecracker.teardown_started`, `sandbox.firecracker.teardown_completed`, `sandbox.firecracker.teardown_failed`
  - WARNING-only: `sandbox.firecracker.enable_trace_unsupported`, `sandbox.firecracker.pids_limit_unsupported`, `sandbox.firecracker.oom_signal_absent`, `sandbox.firecracker.health_probe_error`.
- [ ] **AC-P2 — Each event appended (not modified) into the S1-01 canonical-events table file** (`sandbox/_events.py` or whichever path S1-01 ships); append-only is asserted by `tests/sandbox/test_events_table_append_only.py` (existing from S1-01) staying green.
- [ ] **AC-P3 — `structlog.testing.capture_logs()`** is used in `test_client_core.py` to assert each event fires with structured fields (`run_id`, `microvm_seconds`, `exit_code`, `reason`).

### Q. Functional core / imperative shell (third consumer; mandate per S3-02)

- [ ] **AC-Q1 — Five pure helpers** (no I/O, no clock, no logging) extracted from `execute()` and unit-tested in `test_client_helpers.py`:
  - `_build_api_socket_requests(spec, vmlinux_path, rootfs_path, run_id) -> list[ApiRequest]` — table-testable list of `(verb, path, body)` tuples for `/machine-config`, `/boot-source`, `/drives/rootfs`, `/drives/work`, `/actions InstanceStart`.
  - `_construct_sandbox_run(*, spec, run_id, started_at, ended_at, exit_code, logs_dir, copy_out_root, timed_out, killed_by_oom) -> SandboxRun` — single source of truth for the 13+4 fields with the stub values from AC-D*.
  - `_wrap_api_error(exc, phase) -> SandboxBackendError` — Adapter mapping per-phase exceptions to closed-Literal `reason`.
  - `_parse_oom_evidence(exit_code: int, dmesg_tail: bytes) -> bool` — pure decision over the two OOM signals.
  - `_parse_vsock_exit_code(payload: bytes) -> int` — pure parser over the vsock wire format.
- [ ] **AC-Q2 — Impure shell methods:** `_ensure_logs_dir`, `_apply_vm_config`, `_wait_for_socket_ready`, `_stream_logs`, `_teardown`. Each is short (≤30 LOC) and calls into the pure helpers.
- [ ] **AC-Q3 — TypedDict shim:** `src/codegenie/sandbox/firecracker/_firecracker_api_types.py` declares `MachineConfig`, `BootSource`, `Drive`, `Action` TypedDicts (mirrors S3-02 `_docker_types.py` precedent). `_build_api_socket_requests` consumes/produces these; `mypy --strict` passes against the shim, not against raw `dict[str, Any]`.
- [ ] **AC-Q4 — Pure-helper coverage:** `tests/sandbox/firecracker/test_client_helpers.py` ≥ 95% line / 90% branch on each pure helper.
- [ ] **AC-Q5 — Hypothesis property (digest-mismatch):** for any two distinct 32-byte BLAKE3 digests `expected ≠ actual`, `_assert_binary_digest(...)` (or the pure-helper underlying it) raises `FirecrackerBinaryMissing` with `reason="sandbox.firecracker.binary_digest_mismatch"` and the message contains both 8-char prefixes. Run ≥ 30 examples.

### R. Coverage + tooling gates

- [ ] **AC-R1 — Branch coverage on `src/codegenie/sandbox/firecracker/` ≥ 90%; line coverage ≥ 95%.** Asserted by `pytest --cov=codegenie.sandbox.firecracker --cov-branch --cov-fail-under=95`.
- [ ] **AC-R2 — `ruff check src/codegenie/sandbox/firecracker tests/sandbox/firecracker`** passes.
- [ ] **AC-R3 — `ruff format --check src/codegenie/sandbox/firecracker tests/sandbox/firecracker`** passes.
- [ ] **AC-R4 — `mypy --strict src/codegenie/sandbox/firecracker`** passes; no `# type: ignore` except where named and adjacent to an upstream-stub gap.
- [ ] **AC-R5 — `pytest tests/sandbox/firecracker/`** passes locally; KVM-only tests appropriately skipped via `pytest.mark.skip_if_no_kvm`.
- [ ] **AC-R6 — `tests/schema/test_no_subprocess_outside_build_chokepoint.py`** stays green (no regression of the chokepoint discipline).
- [ ] **AC-R7 — Pre-commit + `make check` green** end-to-end.

## Implementation outline

1. **Deps + canonical constants first.** Add `httpx>=0.27` to `pyproject.toml`. Verify `blake3` already present. Run `make fence` to confirm closure-fence stays green.
2. **TypedDict shim.** Create `src/codegenie/sandbox/firecracker/_firecracker_api_types.py` with `MachineConfig`, `BootSource`, `Drive`, `Action`. Mirror S3-02 `_docker_types.py` structure.
3. **Errors extension.** In `src/codegenie/sandbox/errors.py`, add `FirecrackerKvmMissing`, `FirecrackerBinaryMissing`, `FirecrackerRootfsMissing` as subclasses of `SandboxBackendError`. Each carries the closed-Literal `reason` field per AC-F1. Add (or extend) the `FirecrackerReason` Literal alias.
4. **Events append.** Append the STARTED/COMPLETED/FAILED triples to `src/codegenie/sandbox/_events.py` (the canonical-events table). Do NOT edit existing entries.
5. **Module skeleton.** Create `src/codegenie/sandbox/firecracker/__init__.py` and `src/codegenie/sandbox/firecracker/client.py`:
   - `from __future__ import annotations` (AC-A4).
   - Module docstring citing ADR-0001 / ADR-0004 / ADR-0006 (AC-A7).
   - Module-level `Final` constants: `_BACKEND_NAME`, `_GATE_ISOLATION_CLASS`, `_TIMEOUT_GRACE_SECONDS`, `_BOOT_WAIT_SECONDS = 5`, `_WARNING_IDS: Final[frozenset[str]]` enumerating every event/reason ID this module emits (AC-A6, AC-H5).
   - `_WARNING_IDS` regex-validates at import time (`raise AssertionError(...)` if any member violates `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`).
   - Protocol definitions: `ApiSocketFactory`, `ProcessHandleFactory`, `VsockExecPort` (AC-B1..-B3).
   - Default impls: `_default_api_socket_factory` (httpx UDS), `_default_process_handle_factory` (subprocess.Popen — the chokepoint), `_default_vsock_exec_port` (raises `NotImplementedError` per AC-B3).
6. **Pure helpers (AC-Q1).** Implement `_build_api_socket_requests`, `_construct_sandbox_run`, `_wrap_api_error`, `_parse_oom_evidence`, `_parse_vsock_exit_code` as module-level pure functions above `class FirecrackerClient`.
7. **Class `FirecrackerClient`:**
   - `__init__` accepts the parameters from AC-A2; stores them on `self`; no I/O.
   - `health(self) -> SandboxHealth` runs four preconditions, returns structured reasons + confidence per AC-H1; never raises (AC-H4).
   - `execute(self, spec) -> SandboxRun`:
     1. `_assert_kvm()` → raise `FirecrackerKvmMissing(reason="sandbox.kvm_missing", ...)`.
     2. `_assert_binary_digest()` → raise `FirecrackerBinaryMissing` with appropriate `reason`.
     3. `_assert_rootfs_artifacts()` → raise `FirecrackerRootfsMissing` with appropriate `reason`.
     4. `if spec.network == "scoped": raise NotImplementedError("network='scoped' deferred to S6-02; see ADR-0009")`.
     5. Mint `run_id = generate_run_id()`; build `jail_dir = self.runs_root / run_id /`; mkdir.
     6. `try:` build copy-in tar; start process via `self.process_handle_factory(self.firecracker_path, jail_dir / "api.sock")`; wait socket ready (≤ 5 s); apply VM config via `_build_api_socket_requests` + `self.api_socket_factory(socket)`; `PUT /actions InstanceStart`; capture `started_at`; call `self.vsock_exec_port.exec(spec.cmd, copy_in_tar, spec.time_budget_seconds)`; stream stdout/stderr to disk; copy-out tar; capture `ended_at`; build `SandboxRun` via `_construct_sandbox_run(...)`.
     7. Catch `TimeoutError` → SIGTERM → grace → SIGKILL → `timed_out=True`, `exit_code=124` (AC-K*).
     8. Catch other exceptions → wrap via `_wrap_api_error(exc, phase)`.
     9. `finally:` `_teardown(run_id)` unconditionally (AC-I*).
     10. Return the `SandboxRun`.
8. **Registry.** `@register_sandbox_backend("firecracker")` in `src/codegenie/sandbox/firecracker/__init__.py`; re-export at `src/codegenie/sandbox/__init__.py`.
9. **Tests (red-first):**
   1. `tests/sandbox/firecracker/test_client_purity.py` — AST walker (failing initially because `client.py` doesn't exist).
   2. `tests/sandbox/firecracker/test_client_helpers.py` — pure-helper red tests + hypothesis property.
   3. `tests/sandbox/firecracker/test_client_core.py` — core integration red tests (precondition order, cleanup grid, registry, Protocol, structlog).
   4. `tests/sandbox/firecracker/test_client_health.py` — confidence table red tests.
   5. `tests/sandbox/firecracker/test_client_timeout_and_oom.py` — timeout / OOM red tests.
   6. Optional `tests/integration/sandbox/test_firecracker_boot.py` — `pytest.mark.skip_if_no_kvm` real-Firecracker positive boot (placeholder for S6-05).
10. **Refactor:** confirm AC-Q2 shell methods stay ≤30 LOC; run `mypy --strict`; ensure no `# type: ignore` is unnamed; finalize `__all__`.

## TDD plan — red / green / refactor

### Red — five test files, written failing-first

**Shared helper** `tests/sandbox/firecracker/conftest.py`:

```python
# tests/sandbox/firecracker/conftest.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from codegenie.sandbox.contract import CopyInEntry, SandboxSpec, SandboxSpecHash


def _valid_spec_kwargs(**overrides: Any) -> dict[str, Any]:
    """Build a kwargs dict with EVERY required SandboxSpec field populated.
    Mirrors tests/sandbox/test_contract_models.py::_valid_spec_kwargs from S1-02.
    """
    base: dict[str, Any] = dict(
        base_image="docker.io/library/alpine:3.19",
        copy_in=[],
        env={},
        cmd=["/bin/true"],
        network="none",
        egress_allowlist=[],
        enable_trace=False,
        time_budget_seconds=60,
        memory_limit_mib=512,
        pids_limit=256,
        copy_out=[],
        label="s6-01-test",
        sandbox_spec_hash=SandboxSpecHash("a" * 32),
    )
    base.update(overrides)
    return base


@pytest.fixture
def valid_spec() -> SandboxSpec:
    return SandboxSpec(**_valid_spec_kwargs())


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "skip_if_no_kvm: skip on hosts without /dev/kvm r+w access",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    kvm_ok = Path("/dev/kvm").exists() and os.access("/dev/kvm", os.R_OK | os.W_OK)
    if kvm_ok:
        return
    skipper = pytest.mark.skip(reason="no /dev/kvm; KVM-only test")
    for item in items:
        if "skip_if_no_kvm" in item.keywords:
            item.add_marker(skipper)
```

**File 1: `tests/sandbox/firecracker/test_client_purity.py`** — AST walker (Phase-5 convention):

```python
# tests/sandbox/firecracker/test_client_purity.py
"""AST module-purity walker. Enforces AC-O1: imports allowlist, banned LLM SDKs,
canonical-Literal single-occurrence, _WARNING_IDS regex membership, no
'SendCtrlAltDel' string, no bare structlog event strings."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

CLIENT_PATH = Path(__file__).resolve().parents[3] / "src/codegenie/sandbox/firecracker/client.py"
ID_REGEX = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
ALLOWED_IMPORTS = frozenset({
    "__future__", "dataclasses", "datetime", "os", "pathlib", "signal",
    "subprocess", "tarfile", "time", "typing", "httpx", "blake3", "structlog",
    "codegenie.sandbox", "codegenie.sandbox.contract", "codegenie.sandbox.errors",
    "codegenie.sandbox.registry", "codegenie.sandbox._events",
    "codegenie.sandbox.did._uuid7", "codegenie.sandbox.firecracker._firecracker_api_types",
    "codegenie.types.identifiers",
})
BANNED_IMPORTS = frozenset({
    "langgraph", "openai", "anthropic", "transformers",
    "sentence_transformers", "torch", "chromadb",
})


@pytest.fixture(scope="module")
def tree() -> ast.AST:
    return ast.parse(CLIENT_PATH.read_text())


def test_imports_allowlisted(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in ALLOWED_IMPORTS or alias.name in ALLOWED_IMPORTS, alias.name
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None
            root = node.module.split(".")[0]
            assert node.module in ALLOWED_IMPORTS or root in ALLOWED_IMPORTS, node.module
            assert root not in BANNED_IMPORTS, f"banned import: {node.module}"


def test_canonical_literal_single_occurrence(tree: ast.AST) -> None:
    """AC-E1: 'firecracker' and 'microvm' each appear exactly once."""
    fc_count = sum(
        1 for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and n.value == "firecracker"
    )
    mv_count = sum(
        1 for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and n.value == "microvm"
    )
    assert fc_count == 1, f"'firecracker' literal appears {fc_count} times; expected 1"
    assert mv_count == 1, f"'microvm' literal appears {mv_count} times; expected 1"


def test_no_send_ctrl_alt_del(tree: ast.AST) -> None:
    """AC-K4: SendCtrlAltDel is ACPI graceful shutdown, not SIGKILL — must not be used."""
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            assert "SendCtrlAltDel" not in n.value


def test_warning_ids_module_level_and_regex_compliant() -> None:
    """AC-H5 + AC-A6: _WARNING_IDS is a module-level Final[frozenset[str]] and every member is namespaced."""
    from codegenie.sandbox.firecracker import client as mod

    assert hasattr(mod, "_WARNING_IDS"), "module must declare _WARNING_IDS"
    ids = getattr(mod, "_WARNING_IDS")
    assert isinstance(ids, frozenset)
    assert len(ids) > 0
    for wid in ids:
        assert ID_REGEX.match(wid), f"{wid!r} violates ^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"


def test_backend_constants_value() -> None:
    """AC-A6, AC-D3, AC-D4: positive Literal pinning."""
    from codegenie.sandbox.firecracker import client as mod

    assert mod._BACKEND_NAME == "firecracker"
    assert mod._GATE_ISOLATION_CLASS == "microvm"
```

**File 2: `tests/sandbox/firecracker/test_client_helpers.py`** — pure-helper unit tests + hypothesis property:

```python
# tests/sandbox/firecracker/test_client_helpers.py
"""Pure-helper unit tests (AC-Q1, AC-Q4, AC-Q5)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from codegenie.sandbox.contract import SandboxRun
from codegenie.sandbox.errors import FirecrackerBinaryMissing
from codegenie.sandbox.firecracker.client import (
    _construct_sandbox_run,
    _parse_oom_evidence,
    _parse_vsock_exit_code,
)
from codegenie.types.identifiers import RunId


def test_construct_sandbox_run_pins_every_field(valid_spec) -> None:
    started = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 5, 25, 12, 0, 1, tzinfo=timezone.utc)
    run = _construct_sandbox_run(
        spec=valid_spec, run_id=RunId("0190" + "a" * 28),
        started_at=started, ended_at=ended, exit_code=0,
        logs_dir=Path("/tmp/runs/0190x/logs"),
        copy_out_root=Path("/tmp/runs/0190x/copy_out"),
        timed_out=False, killed_by_oom=False,
    )
    assert isinstance(run, SandboxRun)
    assert run.backend == "firecracker"
    assert run.gate_isolation_class == "microvm"
    assert run.spec is valid_spec
    assert run.started_at == started
    assert run.ended_at == ended
    assert run.exit_code == 0
    assert run.duration_ms == 1000
    assert run.microvm_seconds == pytest.approx(1.0)
    assert run.image_pull_bytes == 0
    assert run.build_cache_hit is False
    assert run.trace_path is None
    assert run.timed_out is False
    assert run.killed_by_oom is False


def test_construct_sandbox_run_rejects_timed_out_and_oom_simultaneously(valid_spec) -> None:
    started = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 5, 25, 12, 0, 1, tzinfo=timezone.utc)
    with pytest.raises(Exception):  # pydantic ValidationError per S1-02 AC-7d
        _construct_sandbox_run(
            spec=valid_spec, run_id=RunId("0190" + "a" * 28),
            started_at=started, ended_at=ended, exit_code=137,
            logs_dir=Path("/tmp/x"), copy_out_root=Path("/tmp/y"),
            timed_out=True, killed_by_oom=True,
        )


@pytest.mark.parametrize(
    ("exit_code", "dmesg", "expected"),
    [
        (137, b"", True),
        (0, b"Out of memory: Killed process 42", True),
        (1, b"normal stderr", False),
        (124, b"", False),  # timeout-without-OOM
    ],
)
def test_parse_oom_evidence(exit_code: int, dmesg: bytes, expected: bool) -> None:
    assert _parse_oom_evidence(exit_code, dmesg) is expected


@given(
    expected=st.binary(min_size=32, max_size=32),
    actual=st.binary(min_size=32, max_size=32),
)
@settings(max_examples=30, deadline=None)
def test_digest_mismatch_property(expected: bytes, actual: bytes) -> None:
    """AC-Q5: any digest mismatch raises with both 8-char prefixes in the message."""
    if expected == actual:
        return  # vacuously true; equal digests don't raise
    from codegenie.sandbox.firecracker.client import _check_digest

    with pytest.raises(FirecrackerBinaryMissing) as exc:
        _check_digest(label="firecracker", expected_hex=expected.hex(), actual_hex=actual.hex())
    msg = str(exc.value)
    assert expected.hex()[:8] in msg
    assert actual.hex()[:8] in msg
    assert exc.value.reason == "sandbox.firecracker.binary_digest_mismatch"
```

**File 3: `tests/sandbox/firecracker/test_client_core.py`** — core integration via injected ports:

```python
# tests/sandbox/firecracker/test_client_core.py
"""Core integration tests via Hexagonal DI ports (AC-B*, AC-C*, AC-D*, AC-G*,
AC-I*, AC-L*, AC-P*). Mocks at the constructor-port boundary; no patching of
subprocess.Popen or httpx."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import structlog

from codegenie.sandbox import registry
from codegenie.sandbox.contract import SandboxClient, SandboxRun
from codegenie.sandbox.errors import (
    FirecrackerBinaryMissing,
    FirecrackerKvmMissing,
    FirecrackerRootfsMissing,
)
from codegenie.sandbox.firecracker.client import FirecrackerClient


def _make_client(tmp_path: Path, **overrides) -> FirecrackerClient:
    fc = tmp_path / "firecracker"
    fc.write_bytes(b"\x7fELF stub")
    fc.chmod(0o755)
    kwargs = dict(
        firecracker_path=fc,
        vmlinux_path=tmp_path / "vmlinux",
        rootfs_path=tmp_path / "rootfs.ext4",
        firecracker_digest="a" * 64,
        vmlinux_digest="b" * 64,
        rootfs_digest="c" * 64,
        runs_root=tmp_path / "runs",
        # Inject fakes — no subprocess, no httpx, no /dev/kvm contact
        api_socket_factory=MagicMock(),
        process_handle_factory=MagicMock(),
        vsock_exec_port=MagicMock(),
        clock=lambda: datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc),
    )
    kwargs.update(overrides)
    return FirecrackerClient(**kwargs)


def test_registry_round_trip() -> None:
    """AC-L2."""
    cls = registry.get_backend("firecracker")
    assert cls is FirecrackerClient


def test_protocol_structural_conformance(tmp_path: Path) -> None:
    """AC-L3."""
    client = _make_client(tmp_path)
    assert isinstance(client, SandboxClient)


@pytest.mark.parametrize(
    "fail_phase, expected_exc, expected_reason",
    [
        ("kvm", FirecrackerKvmMissing, "sandbox.kvm_missing"),
        ("binary_digest", FirecrackerBinaryMissing, "sandbox.firecracker.binary_digest_mismatch"),
        ("vmlinux_digest", FirecrackerRootfsMissing, "sandbox.firecracker.vmlinux_digest_mismatch"),
        ("rootfs_digest", FirecrackerRootfsMissing, "sandbox.firecracker.rootfs_digest_mismatch"),
    ],
)
def test_precondition_order_failure_short_circuits(
    tmp_path: Path, monkeypatch, fail_phase, expected_exc, expected_reason, valid_spec,
) -> None:
    """AC-C1, AC-PRECOND-3: each precondition failure short-circuits later checks.
    Verified via mock call_count == 0 on downstream asserts."""
    monkeypatch.chdir(tmp_path)
    client = _make_client(tmp_path)
    # Patch the four _assert_* methods with mocks; configure fail_phase to raise.
    asserts = {
        "kvm": MagicMock(side_effect=FirecrackerKvmMissing(
            reason="sandbox.kvm_missing", message="/dev/kvm absent; docker_in_docker fallback")),
        "binary_digest": MagicMock(side_effect=FirecrackerBinaryMissing(
            reason="sandbox.firecracker.binary_digest_mismatch", message="prefix mismatch")),
        "vmlinux_digest": MagicMock(side_effect=FirecrackerRootfsMissing(
            reason="sandbox.firecracker.vmlinux_digest_mismatch", message="vmlinux mismatch")),
        "rootfs_digest": MagicMock(side_effect=FirecrackerRootfsMissing(
            reason="sandbox.firecracker.rootfs_digest_mismatch", message="rootfs mismatch")),
    }
    ordered = ["kvm", "binary_digest", "vmlinux_digest", "rootfs_digest"]
    for phase in ordered:
        if phase != fail_phase:
            asserts[phase].side_effect = None  # passes
        monkeypatch.setattr(client, f"_assert_{phase}", asserts[phase])

    with pytest.raises(expected_exc) as exc:
        client.execute(valid_spec)
    assert exc.value.reason == expected_reason

    # Downstream asserts must not have been called
    idx = ordered.index(fail_phase)
    for phase in ordered[idx + 1:]:
        assert asserts[phase].call_count == 0, f"{phase} should not have been called"


def test_kvm_missing_message_contains_remediation(tmp_path, monkeypatch, valid_spec) -> None:
    """AC-F2: message contains '/dev/kvm' and the literal 'docker_in_docker'."""
    monkeypatch.chdir(tmp_path)
    client = _make_client(tmp_path)
    monkeypatch.setattr(client, "_assert_kvm",
                        MagicMock(side_effect=FirecrackerKvmMissing(
                            reason="sandbox.kvm_missing",
                            message="/dev/kvm not accessible; run on a KVM-capable Linux host or use the docker_in_docker backend")))
    with pytest.raises(FirecrackerKvmMissing) as exc:
        client.execute(valid_spec)
    assert "/dev/kvm" in str(exc.value)
    assert "docker_in_docker" in str(exc.value)


def test_scoped_network_not_implemented(tmp_path, monkeypatch, valid_spec) -> None:
    """AC-C3, AC-G1."""
    monkeypatch.chdir(tmp_path)
    spec_scoped = valid_spec.model_copy(update={"network": "scoped"})
    client = _make_client(tmp_path)
    monkeypatch.setattr(client, "_assert_kvm", MagicMock())
    monkeypatch.setattr(client, "_assert_binary_digest", MagicMock())
    monkeypatch.setattr(client, "_assert_rootfs_artifacts", MagicMock())
    with pytest.raises(NotImplementedError, match="S6-02"):
        client.execute(spec_scoped)


@pytest.mark.parametrize(
    "fail_phase",
    ["kvm", "binary_digest", "rootfs_digest", "boot", "exec", "copy_out", "timeout", "oom"],
)
def test_cleanup_on_each_failure_phase(tmp_path, monkeypatch, fail_phase, valid_spec) -> None:
    """AC-I5: 8-cell parametrized cleanup grid. Asserts the jail dir is torn down
    (logs survive, transient artifacts removed) and the teardown event fires."""
    monkeypatch.chdir(tmp_path)
    # Implementation: inject fakes that raise at the named phase, then assert:
    #   - <runs_root>/<run_id>/api.sock does not exist after execute()
    #   - <runs_root>/<run_id>/stdout.log + stderr.log DO exist if past 'exec' phase
    #   - teardown event was emitted
    # See AC-I3 for the survives/removes split.
    pytest.skip("RED: implementation pending; placeholder asserts the grid is wired")


def test_structlog_events_emit_with_canonical_names(tmp_path, monkeypatch, valid_spec) -> None:
    """AC-P3: structlog.testing.capture_logs() asserts STARTED/COMPLETED/FAILED triples."""
    pytest.skip("RED: implementation pending")


def test_happy_path_populates_every_sandbox_run_field(tmp_path, monkeypatch, valid_spec) -> None:
    """AC-D1..-D17: every field on SandboxRun is asserted on the populated result."""
    pytest.skip("RED: implementation pending")
```

**File 4: `tests/sandbox/firecracker/test_client_health.py`** — confidence table:

```python
# tests/sandbox/firecracker/test_client_health.py
"""AC-H1..-H5: parametrized confidence mapping table."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "kvm_ok, fc_ok, vmlinux_ok, rootfs_ok, exp_reachable, exp_confidence, exp_reasons",
    [
        (True, True, True, True, True, "high", []),
        (False, True, True, True, False, "low", ["sandbox.kvm_missing"]),
        (True, False, True, True, False, "low", ["sandbox.firecracker.binary_digest_mismatch"]),
        (True, True, False, True, False, "low", ["sandbox.firecracker.vmlinux_digest_mismatch"]),
        (True, True, True, False, False, "low", ["sandbox.firecracker.rootfs_digest_mismatch"]),
        (False, False, True, True, False, "low",
         ["sandbox.firecracker.binary_digest_mismatch", "sandbox.kvm_missing"]),  # alphabetized
    ],
)
def test_health_confidence_table(
    kvm_ok, fc_ok, vmlinux_ok, rootfs_ok, exp_reachable, exp_confidence, exp_reasons,
) -> None:
    pytest.skip("RED: implementation pending")


def test_health_never_raises_wraps_unexpected_errors() -> None:
    """AC-H4: any internal exception → reasons=['sandbox.firecracker.health_probe_error'] + WARNING."""
    pytest.skip("RED: implementation pending")
```

**File 5: `tests/sandbox/firecracker/test_client_timeout_and_oom.py`**:

```python
# tests/sandbox/firecracker/test_client_timeout_and_oom.py
"""AC-J*, AC-K*: OOM detection + timeout grace + signal-absence warning."""
from __future__ import annotations

import pytest


def test_oom_via_exit_code_137_sets_killed_by_oom() -> None:
    """AC-J1."""
    pytest.skip("RED: implementation pending")


def test_oom_via_dmesg_fallback_sets_killed_by_oom() -> None:
    """AC-J2."""
    pytest.skip("RED: implementation pending")


def test_oom_signal_absent_emits_warning_and_returns_false() -> None:
    """AC-J3."""
    pytest.skip("RED: implementation pending")


def test_timeout_sigterm_then_sigkill_grace_window() -> None:
    """AC-K1, AC-K2: SIGTERM, wait 3 s, then SIGKILL."""
    pytest.skip("RED: implementation pending")


def test_timeout_sets_timed_out_true_exit_code_124() -> None:
    """AC-K3."""
    pytest.skip("RED: implementation pending")
```

### Green — make it pass

Smallest implementation per the outline. The pure helpers are the bulk; the impure shell methods are short orchestrators around them. Key gotchas the executor must NOT regress:

- `_assert_kvm` reads `Path("/dev/kvm").exists()` AND `os.access("/dev/kvm", os.R_OK | os.W_OK)` (both, not either).
- Each `_assert_*` raises the appropriate error with the right `reason` from the closed Literal set.
- The constructor performs zero filesystem reads — preconditions are checked at `execute()` time per AC-C2.
- `_default_vsock_exec_port` raises `NotImplementedError`; unit tests inject a fake; the KVM-only integration test (placeholder for S6-05) will inject the real S6-03 helper once it lands.
- `try/finally` wraps the entire `execute()` body; `_teardown` is idempotent.
- Module-level `_WARNING_IDS: Final[frozenset[str]]` lists every event + reason ID this module emits; the import-time `assert` catches typos.

### Refactor — clean up

- Confirm each shell method ≤ 30 LOC (AC-Q2).
- Confirm `mypy --strict` passes; eliminate or name any `# type: ignore`.
- Confirm AST walker (file 1) catches mutation: temporarily inline `"firecracker"` in a second location and verify the test fails; revert.
- Confirm structlog event capture asserts canonical names (no bare strings).
- Confirm `__all__` is sorted and minimal.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/firecracker/__init__.py` | New — `@register_sandbox_backend("firecracker")` + re-export `FirecrackerClient`. |
| `src/codegenie/sandbox/firecracker/client.py` | New — class + pure helpers + module-level `Final`s + `_WARNING_IDS`. |
| `src/codegenie/sandbox/firecracker/_firecracker_api_types.py` | New — TypedDict shim for API payloads (AC-Q3). |
| `src/codegenie/sandbox/firecracker/copy_in.py` | New (lightweight) — copy-in tar builder, table-testable (AC-G4). |
| `src/codegenie/sandbox/errors.py` | Modify (additive) — add the three error subclasses + `FirecrackerReason` Literal alias. |
| `src/codegenie/sandbox/__init__.py` | Modify (additive) — re-export the three errors + `FirecrackerClient`. |
| `src/codegenie/sandbox/_events.py` | Modify (additive, append-only) — append STARTED/COMPLETED/FAILED triples. |
| `pyproject.toml` | Modify — add `httpx>=0.27` to runtime deps. |
| `tests/sandbox/firecracker/__init__.py` | New — make the test package importable. |
| `tests/sandbox/firecracker/conftest.py` | New — `_valid_spec_kwargs` helper + `skip_if_no_kvm` marker. |
| `tests/sandbox/firecracker/test_client_purity.py` | New — AST module-purity walker. |
| `tests/sandbox/firecracker/test_client_helpers.py` | New — pure-helper unit tests + hypothesis property. |
| `tests/sandbox/firecracker/test_client_core.py` | New — Hexagonal-port integration: precondition order, cleanup grid, registry, Protocol, structlog. |
| `tests/sandbox/firecracker/test_client_health.py` | New — confidence-mapping parametrized table. |
| `tests/sandbox/firecracker/test_client_timeout_and_oom.py` | New — OOM + timeout positive coverage. |

## Out of scope

- Host-side TAP + nftables network policy (`network="scoped"`) — **S6-02**. This story raises `NotImplementedError("network='scoped' deferred to S6-02; see ADR-0009")` as the explicit wiring point.
- Rootfs digest enforcement against `tools/digests.yaml` and the `from_digests_yaml(path)` factory — **S6-03**. This story compares against constructor-passed digests only.
- The real in-guest vsock exec helper (`/sbin/sandbox-exec` and the `/etc/sandbox-cmd` wire format) — **S6-03 / S6-05**. This story ports the `_VsockExecPort` Protocol seam; the default impl raises `NotImplementedError` and unit tests inject a fake. S6-03 ships the rootfs + the real helper; S6-05's KVM smoke test exercises it end-to-end.
- `auto_detect()` returning `FirecrackerClient` on KVM hosts — **S6-04**. S6-04 consumes the `FirecrackerKvmMissing.reason == "sandbox.kvm_missing"` discriminator and the `"docker_in_docker"` literal in the error message.
- KVM-gated CI smoke test and weekly cron — **S6-05**.
- Warm pool / cold-start optimization — Phase 9 territory per `phase-arch-design.md §Non-goal 3`.
- Hoisting `_uuid7.py` from `sandbox/did/` to `sandbox/` — future cleanup. Rule-of-three on the helper not yet reached.
- A `BaseSandboxClient` mixin extracting the `health()` shape — Phase 7 territory (rule-of-three on backends fires there).

## Notes for the implementer

### Pattern lineage — third consumer mandates

S6-01 is the third concrete consumer of:
1. **`SandboxClient` Protocol** (DinD S3-02 + Firecracker S6-01 + Phase 7 distroless later) — Open/Closed by registry decoration. Do not edit `sandbox/contract.py`.
2. **Hexagonal DI port pattern** — S3-02 shipped `docker_factory`; S6-01 ships `api_socket_factory` + `process_handle_factory` + `vsock_exec_port`. Tests inject; production uses defaults.
3. **Functional core / imperative shell** — S3-02 shipped 4 pure helpers + 1 impure shell pattern; S6-01 ships 5 pure helpers + 5 short shell methods.
4. **Closed-`Literal` `SandboxBackendError.reason`** — S3-02 set the precedent; S6-01 adds the Firecracker subset (AC-F1). Phase 11 / 13 key on this.
5. **Module-level `Final` constants + AST single-occurrence walker** — `_BACKEND_NAME` / `_GATE_ISOLATION_CLASS` discipline.
6. **Module-purity AST walker** — `test_client_purity.py` is non-negotiable for any new module under `sandbox/<backend>/`.

If you find yourself diverging from S3-02's shape, stop and ask why. The convention is the win.

### `httpx` over `requests` for UDS

`requests` does not natively support Unix-domain sockets. `httpx.HTTPTransport(uds=str(socket_path))` is the idiomatic way; `httpx.Client(transport=transport)` mints the session. The default factory should look roughly like:

```python
def _default_api_socket_factory(socket_path: Path) -> _ApiSocket:
    transport = httpx.HTTPTransport(uds=str(socket_path))
    client = httpx.Client(transport=transport, base_url="http://localhost", timeout=5.0)
    return _ApiSocket(client)
```

Wrap PUT calls behind the `_ApiSocket` Protocol — tests should never need to know about httpx.

### Warning-ID regex + arch erratum

CLAUDE.md mandates `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. The arch's `phase-arch-design.md §Edge case 15` writes `reasons=["kvm_missing"]` — this is an arch erratum. The story uses `sandbox.kvm_missing`. If you encounter resistance, point at S3-02's `_validation` report (which renamed `buildx_missing` → `sandbox.buildx_missing` for the same reason).

The `_WARNING_IDS: Final[frozenset[str]]` module-level constant enumerates every event/reason ID this module emits. The import-time `raise AssertionError(...)` catches typos before any consumer sees them.

### `SendCtrlAltDel` is not SIGKILL — do not use it for timeouts

The Firecracker API's `PUT /actions {action_type:"SendCtrlAltDel"}` sends an ACPI graceful-shutdown signal to the guest. A guest that ignores ACPI (or hangs on shutdown) will satisfy the call and leak past `time_budget_seconds`. Use `_handle.terminate()` (SIGTERM) → 3 s grace → `_handle.kill()` (SIGKILL) on the host firecracker process. The AST walker (AC-K4) bans the string `"SendCtrlAltDel"` to catch reverts.

### Extending the closed `reason` Literal

When a future story (S6-02 / S6-03 / Phase 7) needs to raise a `FirecrackerSandboxError` with a new reason, the procedure is:
1. Open an ADR amendment under `docs/phases/05-sandbox-trust-gates/ADRs/` extending the `FirecrackerReason` Literal alias.
2. Add the new value to `_WARNING_IDS` in `client.py`.
3. Add the value to the per-phase mapping table in `_wrap_api_error`.

Inline string literals as `reason=` values are not allowed — `mypy --strict` rejects them against the closed Literal.

### vsock exec contract is deferred — but the seam is mandatory

`_VsockExecPort` ports the in-guest exec protocol so unit tests can use a fake `VsockExecResult(exit_code=0, stdout=b"", stderr=b"", copy_out_tar=b"")`. The real implementation (in-guest helper script + serial-console or vsock byte protocol) lands in S6-03 (rootfs bake) or S6-05 (KVM smoke). When S6-03 lands, the default factory will be swapped to a real impl; this story ships the Protocol seam and the `NotImplementedError` default.

### Forward compatibility with S6-02 chokepoint widening

AC-9 (from the draft) said "every subprocess invocation lives inside `client.py`". This is correct **for S6-01** but is forward-incompatible with S6-02, which will additively introduce `sandbox/firecracker/network_policy.py` as a second chokepoint (per ADR-0001's "two-chokepoint" doctrine widening to three with S6-02). The story's tests assert "no NEW subprocess sites in S6-01 beyond `client.py`" rather than "no other subprocess sites in `sandbox/firecracker/` forever."

### uuid7 helper re-use

Import `generate_run_id` from `codegenie.sandbox.did._uuid7`. Do NOT re-vendor. The current location is suboptimal (a Firecracker-side import from `did/`); the future hoist to `sandbox/_uuid7.py` is a noted cleanup task. Do not perform the hoist in this story — Rule 3 (surgical changes).

### `_assert_*` precondition iteration — note the pattern, do not abstract yet

A future story may want a `Precondition` dataclass + `_PRECONDITIONS: Final[tuple[Precondition, ...]]` iterated in `_assert_all()` so adding a precondition is a tuple-entry append (Open/Closed). This is the first consumer of the pattern; Rule 2 says note the opportunity and defer. The inline `_assert_kvm() → _assert_binary_digest() → _assert_rootfs_artifacts()` ordering in `execute()` is acceptable for this story.

### Resist "ready" wait-loops longer than 5 s

If the API socket isn't responsive within 5 s of `InstanceStart`, surface the failure fast — operators run `codegenie sandbox health` for diagnostics. AC-BOOT-WAIT-1 pins this. A 30 s wait-loop hides the failure mode the operator most needs to see.

### Teardown is idempotent

`codegenie sandbox gc` (S8-01) will retry teardown on orphaned jail dirs. `_teardown(run_id)` must accept a partially-cleaned state without raising. "Already cleaned" is success, not failure.

### macOS-laptop test hygiene

Every test in `tests/sandbox/firecracker/` except those marked `skip_if_no_kvm` must run cleanly on macOS without `/dev/kvm`. Inject fakes through the constructor ports; do NOT `patch("codegenie.sandbox.firecracker.client.Path.exists")` globally — that patches every `Path.exists` call in the module and tightly couples the test to the order of internal `Path.exists` invocations.
