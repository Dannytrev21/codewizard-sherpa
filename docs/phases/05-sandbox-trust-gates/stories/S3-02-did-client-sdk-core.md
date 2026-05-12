# Story S3-02 — `DockerInDockerClient` SDK core — create/start/exec/inspect/remove

**Step:** Step 3 — Implement DinD backend + SandboxSpecBuilder + SandboxHealthProbe
**Status:** Ready
**Effort:** M
**Depends on:** S1-05 (registries + `env_allowlist`)
**ADRs honored:** ADR-0001 (two chokepoints — SDK lives here; subprocess does not), ADR-0004 (DinD macOS default + `gate_isolation_class: shared_kernel`), ADR-0006 (Protocol vs ABC convention)

## Context

`DockerInDockerClient` is the macOS/Linux-default `SandboxClient` implementation. This story lands the SDK-driven happy path only — create + start + exec + capture stdout/stderr + inspect + remove, returning a populated `SandboxRun`. The build subprocess chokepoint (`docker buildx`) and the iptables network policy chokepoint are intentionally split into S3-03 because they are the only `subprocess` callers in the entire `sandbox/` tree and the AST fence test (`tests/schema/test_no_subprocess_outside_build_chokepoint.py`) only tolerates them in their dedicated files. Copy-out, OOM, and timeout handling are S3-04. Keep this story narrow.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — DockerInDockerClient` — public surface, internal structure, dependencies, performance envelope, failure-mode mapping (`APIError` → `SandboxBackendError`).
  - `../phase-arch-design.md §Logical view` — class diagram for `DockerInDockerClient` implementing `SandboxClient`.
  - `../phase-arch-design.md §Process view` — sequence of `docker create + cp + start + exec`.
  - `../phase-arch-design.md §Physical view` — workload container annotated `shared_kernel`.
  - `../phase-arch-design.md §Edge case 1` — Docker daemon dies mid-build → `SandboxBackendError`.
- **Phase ADRs:**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — ADR-0001 — `client.py` MUST NOT `import subprocess`; SDK only.
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — ADR-0004 — every `SandboxRun` from this backend carries `gate_isolation_class="shared_kernel"`, `backend="docker_in_docker"`.
  - `../ADRs/0006-protocol-vs-abc-convention.md` — ADR-0006 — `DockerInDockerClient` satisfies `SandboxClient` Protocol structurally, no inheritance.
- **Source design:**
  - `../final-design.md §Synthesis ledger — Sandbox stack default macOS row` — DinD on macOS is the explicit pick.
- **Existing code:**
  - `src/codegenie/sandbox/contract.py` (from S1-02) — `SandboxClient` Protocol, `SandboxSpec`, `SandboxRun`, `SandboxHealth`, `CopyInEntry`.
  - `src/codegenie/sandbox/registry.py` (from S1-05) — `@register_sandbox_backend("docker_in_docker")` decorator.
- **External docs:**
  - https://docker-py.readthedocs.io/en/stable/containers.html — `client.containers.create`, `.start`, `.exec_run`, `.wait`, `.remove`.
  - https://docker-py.readthedocs.io/en/stable/api.html — low-level `APIClient` for streaming logs.

## Goal

Ship a Docker-SDK-only `execute()` path that creates an ephemeral container from a `SandboxSpec`, runs `cmd`, captures stdout/stderr to `logs_dir`, and returns a `SandboxRun` populated with `backend`, `gate_isolation_class`, timings, and `exit_code`.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/did/client.py` defines `DockerInDockerClient` with `__init__(self, *, docker_url: str | None = None, allowlist: EnvAllowlist)` and `execute(self, spec: SandboxSpec) -> SandboxRun`, `health(self) -> SandboxHealth`.
- [ ] Registered via `@register_sandbox_backend("docker_in_docker")` from S1-05.
- [ ] `execute()` calls `docker.from_env(...)` (or `docker.DockerClient(base_url=docker_url)` when provided) and uses **only** the Python SDK — `import subprocess` is absent from this file (verified by the existing AST fence test).
- [ ] On success, `SandboxRun` carries: `backend="docker_in_docker"`, `gate_isolation_class="shared_kernel"`, `run_id` (uuid7), populated `started_at`/`ended_at`/`duration_ms`, `exit_code` from `container.wait()`, `logs_dir` containing `stdout.log` and `stderr.log` byte-for-byte from the container, `copy_out_root` as a Path even when empty (Step 3-04 populates it).
- [ ] `docker.errors.APIError` raised during create/start/exec is caught and re-raised as `SandboxBackendError` with a structured `reason` field (kept short — no log bytes).
- [ ] `health()` returns `SandboxHealth(backend="docker_in_docker", reachable=<bool>, confidence=<level>, reasons=[...], warnings=[...])`; `client.ping()` failure → `reachable=False, reasons=["daemon_unreachable"]`; missing `buildx` plugin → `warnings=["buildx_missing"]` (does not flip `reachable`); strace `SYS_PTRACE` denial → `warnings=["strace_ptrace_missing"]` (macOS soft-signal per arch §Risk-3).
- [ ] Cleanup: the ephemeral container is always removed (`force=True`) in a `try/finally`; cleanup failure logs at WARNING but does not raise.
- [ ] Unit tests use `pytest-mock` to stub the Docker SDK — no real daemon needed for this story; integration is S3-07.
- [ ] `tests/schema/test_no_subprocess_outside_build_chokepoint.py` and `tests/schema/test_no_llm_imports_in_sandbox.py` both green.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/sandbox/did/client.py`, `pytest` pass.

## Implementation outline

1. Create `src/codegenie/sandbox/did/__init__.py` and `client.py`. Import `docker`, `uuid_extensions` (or stdlib UUID7 helper if vendored), `datetime`, `pathlib.Path`, `structlog`, `codegenie.sandbox.contract.*`, `codegenie.sandbox.errors.*`, `codegenie.sandbox.registry.register_sandbox_backend`. **Do not** import `subprocess`.
2. `__init__`: store `self._client = docker.from_env()` (or `DockerClient(base_url=docker_url)`); store `self._allowlist`.
3. `execute(spec)`:
   - Generate `run_id` (uuid7).
   - Build `logs_dir = Path(".codegenie/sandbox/runs") / run_id`; `mkdir(parents=True)`.
   - Build container kwargs from `spec`: `image=spec.base_image`, `command=spec.cmd`, `environment=dict(spec.env)`, `network_mode="none"` (S3-03 will widen to `bridge` + iptables for `scoped`), `mem_limit=f"{spec.memory_limit_mib}m"`, `pids_limit=spec.pids_limit`.
   - `container = self._client.containers.create(**kwargs)`; `container.start()`.
   - Stream stdout/stderr via `container.logs(stream=True, stdout=True, stderr=True, demux=True)` into the two log files byte-faithfully.
   - `result = container.wait()`; collect `exit_code = result["StatusCode"]`.
   - Build `SandboxRun` (timed_out=False, killed_by_oom=False — S3-04 wires those).
4. `health()`:
   - Try `self._client.ping()`. On failure → `reachable=False, confidence="high", reasons=["daemon_unreachable"]`.
   - On success, check `self._client.api.version()["Components"]` for buildx; absent → `warnings=["buildx_missing"]`.
   - On macOS (detect via `platform.system() == "Darwin"`), attempt a one-off `--cap-add SYS_PTRACE` strace probe (still via SDK only); on refusal → `warnings=["strace_ptrace_missing"]`.
5. structlog events: `sandbox.did.execute.start`, `sandbox.did.execute.done`, `sandbox.did.execute.error`, `sandbox.did.health` — all with `run_id`, `spec.label`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/sandbox/did/test_client_core.py`

```python
# tests/sandbox/did/test_client_core.py
from unittest.mock import MagicMock
from pathlib import Path
import pytest
from codegenie.sandbox.did.client import DockerInDockerClient
from codegenie.sandbox.errors import SandboxBackendError
from codegenie.sandbox.contract import SandboxSpec, SandboxRun

def _spec(**overrides):
    base = dict(base_image="cgr.dev/chainguard/node@sha256:deadbeef", copy_in=[], env={},
                cmd=["true"], network="none", egress_allowlist=[], enable_trace=False,
                time_budget_seconds=10, memory_limit_mib=256, pids_limit=64, copy_out=[],
                label="t", sandbox_spec_hash="0" * 32)
    base.update(overrides)
    return SandboxSpec(**base)

def test_execute_returns_sandbox_run_with_shared_kernel_class(monkeypatch, tmp_path, allowlist):
    """Happy path: SandboxRun carries backend + gate_isolation_class + duration_ms.
    Catches a refactor that forgets to stamp gate_isolation_class — load-bearing per ADR-0004."""
    fake_container = MagicMock()
    fake_container.wait.return_value = {"StatusCode": 0}
    fake_container.logs.return_value = iter([(b"hello\n", b"")])
    fake_docker = MagicMock()
    fake_docker.containers.create.return_value = fake_container
    monkeypatch.setattr("docker.from_env", lambda: fake_docker)
    monkeypatch.chdir(tmp_path)

    client = DockerInDockerClient(allowlist=allowlist)
    run = client.execute(_spec())

    assert isinstance(run, SandboxRun)
    assert run.backend == "docker_in_docker"
    assert run.gate_isolation_class == "shared_kernel"
    assert run.exit_code == 0
    assert (run.logs_dir / "stdout.log").read_bytes() == b"hello\n"
    fake_container.remove.assert_called_once_with(force=True)

def test_api_error_during_create_raises_sandbox_backend_error(monkeypatch, allowlist):
    """Docker APIError must be wrapped — orchestrator never sees raw docker exceptions."""
    import docker.errors
    fake_docker = MagicMock()
    fake_docker.containers.create.side_effect = docker.errors.APIError("daemon down")
    monkeypatch.setattr("docker.from_env", lambda: fake_docker)
    client = DockerInDockerClient(allowlist=allowlist)
    with pytest.raises(SandboxBackendError) as exc:
        client.execute(_spec())
    assert "daemon" in str(exc.value).lower()

def test_container_removed_even_when_exec_raises(monkeypatch, tmp_path, allowlist):
    """Cleanup discipline: container.remove must run even on exec exception."""
    fake_container = MagicMock()
    fake_container.start.side_effect = RuntimeError("boom")
    fake_docker = MagicMock()
    fake_docker.containers.create.return_value = fake_container
    monkeypatch.setattr("docker.from_env", lambda: fake_docker)
    monkeypatch.chdir(tmp_path)
    client = DockerInDockerClient(allowlist=allowlist)
    with pytest.raises(SandboxBackendError):
        client.execute(_spec())
    fake_container.remove.assert_called_once_with(force=True)

def test_health_reports_daemon_unreachable(monkeypatch, allowlist):
    fake_docker = MagicMock()
    fake_docker.ping.side_effect = Exception("connection refused")
    monkeypatch.setattr("docker.from_env", lambda: fake_docker)
    client = DockerInDockerClient(allowlist=allowlist)
    health = client.health()
    assert health.reachable is False
    assert "daemon_unreachable" in health.reasons
```

### Green — make it pass

Implement the SDK calls in the order above; wrap `docker.errors.APIError` in try/except; use `try/finally` for `container.remove(force=True)`; write logs to disk.

### Refactor — clean up

- Extract `_build_container_kwargs(spec) -> dict` for clarity.
- Type hints, docstrings citing ADR-0001 + ADR-0004 at top of file.
- structlog `bind` of `run_id` for the whole execute scope.
- Verify `mypy --strict` clean — the Docker SDK is typed via `docker-stubs`; vendor a `py.typed` shim if missing.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/did/__init__.py` | New subpackage marker. |
| `src/codegenie/sandbox/did/client.py` | The SDK-driven `execute` + `health`. |
| `src/codegenie/sandbox/errors.py` | Add `SandboxBackendError` (if not from S1-01). |
| `tests/sandbox/did/test_client_core.py` | Unit tests for happy/error/cleanup/health. |
| `tests/sandbox/did/__init__.py` | New test subpackage marker. |

## Out of scope

- `docker buildx build` — S3-03 owns the build chokepoint.
- iptables / `network=scoped` — S3-03.
- `docker cp` copy-out, OOM detection, SIGKILL/timeout — S3-04.
- Real Docker daemon integration — S3-07 wires the live test.
- `SandboxHealthProbe` Phase 1 probe wrapper — S3-06.

## Notes for the implementer

- **No `subprocess` import.** The AST fence test will fail PR immediately if you add one. If you find yourself wanting `subprocess.run("docker", ...)`, you're in the wrong file — that belongs in `did/build.py` (S3-03).
- `network_mode="none"` is the correct stub for this story; S3-03 will override per `spec.network`.
- `gate_isolation_class="shared_kernel"` is a *string literal* on this backend, always — no conditional. Firecracker's client (S6-01) sets `"microvm"`.
- Don't try to detect `strace_ptrace_missing` on Linux; only emit the warning on Darwin. CI on Linux must not flake on this.
- Cleanup in `finally` must catch its own exceptions and log; never let a `remove` failure overwrite the real error.
- `container.logs(stream=True, demux=True)` is the only way to separate stdout/stderr cleanly from the SDK; the alternative `attach()` is unreliable on Docker Desktop.
