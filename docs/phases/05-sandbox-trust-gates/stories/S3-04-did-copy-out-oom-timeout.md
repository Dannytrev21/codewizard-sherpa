# Story S3-04 — DinD `copy_out.py` + OOM detection + `time_budget_seconds` SIGKILL

**Step:** Step 3 — Implement DinD backend + SandboxSpecBuilder + SandboxHealthProbe
**Status:** Ready
**Effort:** M
**Depends on:** S3-02 (`DockerInDockerClient` SDK core)
**ADRs honored:** ADR-0001 (no `subprocess` in `copy_out.py` — pure SDK via `get_archive` or fall back to a chokepoint), ADR-0004 (DinD `shared_kernel`)

## Context

A `SandboxRun` is only useful to downstream collectors if its artifacts arrive — `logs_dir` plus `copy_out_root` carry `stdout.log`, `stderr.log`, `trace.jsonl`, `policy.json`, `sbom.json`, and any glob-matched files from `spec.copy_out`. This story wires that copy-out path. It also closes the two non-success exit paths every collector depends on: `SandboxRun.timed_out` (SIGKILL after `spec.time_budget_seconds`) and `SandboxRun.killed_by_oom` (detected via `docker inspect`'s `State.OOMKilled` flag). Both are required by `phase-arch-design.md §Edge cases #3 and #4`.

Copy-out uses the Docker SDK's `container.get_archive()` — tar-stream extraction — staying out of the subprocess chokepoint. The golden-file test `tests/golden/docker_cp_args_<scenario>.json` from §Testing strategy captures the argv list when subprocess is needed (only if the SDK path is unworkable; default is SDK-only).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — DockerInDockerClient` — "wraps timeout into `SandboxRun(timed_out=True)`; wraps OOM (detected via `docker inspect` State.OOMKilled) into `SandboxRun(killed_by_oom=True)`".
  - `../phase-arch-design.md §Edge case 3` — `time_budget_seconds` → SIGKILL → `timed_out=True`; non-retryable by default.
  - `../phase-arch-design.md §Edge case 4` — `docker inspect State.OOMKilled` → `killed_by_oom=True`; non-retryable.
  - `../phase-arch-design.md §Testing strategy — Golden files` — `tests/golden/docker_cp_args_<scenario>.json`.
  - `../phase-arch-design.md §Data model — SandboxRun` — every field this story populates (`timed_out`, `killed_by_oom`, `copy_out_root`).
- **Phase ADRs:**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — ADR-0001 — `copy_out.py` is **not** in the subprocess allowlist; must use SDK (`container.get_archive`) only.
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — ADR-0004 — `shared_kernel` annotation persists across all `SandboxRun` exit paths.
- **Source design:**
  - `../final-design.md §Synthesis ledger — Trace soft signal row` — informs why `timed_out` is non-retryable but configurable per `retry_policy.timeout_retryable`.
- **Existing code:**
  - `src/codegenie/sandbox/did/client.py` (from S3-02) — `execute()` returns `SandboxRun` with `timed_out=False`, `killed_by_oom=False`; this story wires the real values.
  - `src/codegenie/sandbox/contract.py` (from S1-02) — `SandboxRun.copy_out_root: Path`.
- **External docs:**
  - https://docker-py.readthedocs.io/en/stable/containers.html#docker.models.containers.Container.get_archive — tar-stream API.
  - https://docker-py.readthedocs.io/en/stable/containers.html#docker.models.containers.Container.kill — SIGKILL via SDK.

## Goal

Wire copy-out (SDK tar-stream → `copy_out_root` glob materialization), OOM detection (`State.OOMKilled` → `killed_by_oom=True`), and the timeout SIGKILL path (`time_budget_seconds` → `container.kill(signal="SIGKILL")` → `timed_out=True`) into `DockerInDockerClient.execute`.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/did/copy_out.py` defines `copy_out(container, *, globs: list[str], dest_root: Path) -> Path` using `container.get_archive(path)` (SDK only — no `subprocess` import).
- [ ] `copy_out` materializes each glob match under `dest_root` preserving relative paths; missing globs are logged at WARNING but do not raise.
- [ ] `DockerInDockerClient.execute` waits with `container.wait(timeout=spec.time_budget_seconds + grace_seconds)`; on `requests.exceptions.ReadTimeout` (or docker SDK equivalent), calls `container.kill(signal="SIGKILL")`, then re-reads `wait()` (no timeout), then sets `SandboxRun.timed_out=True`, `exit_code=137` (SIGKILL convention).
- [ ] After `wait()` returns normally, `execute` calls `container.reload(); container.attrs["State"]["OOMKilled"]` — if `True`, sets `SandboxRun.killed_by_oom=True`. (Mutually exclusive with `timed_out` — OOM also gets exit 137 from the kernel; the inspect flag disambiguates.)
- [ ] `copy_out_root` is `logs_dir / "copy_out"`; created (empty dir if no globs match) so collectors don't `FileNotFoundError`.
- [ ] Golden-file test `tests/golden/docker_cp_args_stage6_validate.json` snapshots the **argument tuples** passed to `container.get_archive` for the stage6 spec (paths only, no contents).
- [ ] Unit test: `wait` raising `ReadTimeout` → `SandboxRun.timed_out is True`, `killed_by_oom is False`, `exit_code == 137`; `container.kill` called exactly once.
- [ ] Unit test: `OOMKilled=True` in inspect → `SandboxRun.killed_by_oom is True`, `timed_out is False`.
- [ ] Unit test: `copy_out` with two globs, one matching one not → matching files materialized under `dest_root`, no exception on the miss.
- [ ] No `subprocess` import added to `copy_out.py` or `client.py`; fence test green.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass.

## Implementation outline

1. `src/codegenie/sandbox/did/copy_out.py`:
   - `copy_out(container, *, globs, dest_root)`:
     - `dest_root.mkdir(parents=True, exist_ok=True)`.
     - For each glob, resolve to concrete paths via `container.exec_run(["sh", "-c", f"ls -1 {glob}"])` — **the SDK's exec, not subprocess** — collect matching paths.
     - For each match path: `bits, stat = container.get_archive(match)`; stream `bits` (iterator of bytes) into a tempfile; use `tarfile.open(temp, mode="r:")` to extract into `dest_root / Path(match).name`.
     - Log misses at WARNING.
   - Return `dest_root`.
2. Edit `DockerInDockerClient.execute`:
   - Wrap `container.wait()` in try/except for the SDK's timeout error (`docker.errors.ContainerError`? `requests.ReadTimeout`? — check SDK version; encapsulate in helper `_wait_with_timeout`).
   - On timeout: `container.kill(signal="SIGKILL")`; call `container.wait()` again (no timeout) to drain; set local flags.
   - On normal return: `container.reload()`; `oom = container.attrs.get("State", {}).get("OOMKilled", False)`.
   - Call `copy_out(container, globs=spec.copy_out, dest_root=logs_dir / "copy_out")` before container removal.
   - Populate `SandboxRun(timed_out=..., killed_by_oom=..., exit_code=..., copy_out_root=...)`.
3. structlog events: `sandbox.did.copy_out`, `sandbox.did.timeout`, `sandbox.did.oom_killed` (each with `run_id`).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths:
- `tests/sandbox/did/test_copy_out.py`
- `tests/sandbox/did/test_timeout.py`
- `tests/sandbox/did/test_oom.py`

```python
# tests/sandbox/did/test_copy_out.py
import io, tarfile
from pathlib import Path
from unittest.mock import MagicMock
from codegenie.sandbox.did.copy_out import copy_out

def _make_tar(name: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        info = tarfile.TarInfo(name=name); info.size = len(content)
        tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()

def test_copy_out_materializes_matching_glob_logs_misses(tmp_path):
    """Verifies that a present glob lands on disk and a missing glob does NOT raise.
    Catches collectors choking on FileNotFoundError from an over-strict copy_out."""
    container = MagicMock()
    container.exec_run.side_effect = [
        MagicMock(output=b"/work/trace.jsonl\n", exit_code=0),
        MagicMock(output=b"", exit_code=1),  # miss
    ]
    container.get_archive.return_value = (iter([_make_tar("trace.jsonl", b"{}\n")]), {})
    dest = tmp_path / "copy_out"
    copy_out(container, globs=["/work/trace.jsonl", "/work/missing.txt"], dest_root=dest)
    assert (dest / "trace.jsonl").read_bytes() == b"{}\n"
    assert not (dest / "missing.txt").exists()
```

```python
# tests/sandbox/did/test_timeout.py
from unittest.mock import MagicMock
import pytest
from codegenie.sandbox.did.client import DockerInDockerClient

def test_wait_timeout_triggers_sigkill_and_sets_timed_out(monkeypatch, tmp_path, allowlist, spec_short_budget):
    """time_budget_seconds=1 → wait() raises → kill() once → SandboxRun.timed_out=True, exit=137.
    Catches regression of the SIGKILL-then-second-wait sequence."""
    fake = MagicMock(); fake.id = "x"
    # First wait raises; second wait (after kill) returns 137.
    fake.wait.side_effect = [TimeoutError("budget"), {"StatusCode": 137}]
    fake.logs.return_value = iter([])
    fake.attrs = {"State": {"OOMKilled": False}}
    fake_docker = MagicMock(); fake_docker.containers.create.return_value = fake
    monkeypatch.setattr("docker.from_env", lambda: fake_docker)
    monkeypatch.chdir(tmp_path)
    client = DockerInDockerClient(allowlist=allowlist)
    run = client.execute(spec_short_budget)
    assert run.timed_out is True
    assert run.killed_by_oom is False
    assert run.exit_code == 137
    fake.kill.assert_called_once_with(signal="SIGKILL")
```

```python
# tests/sandbox/did/test_oom.py
from unittest.mock import MagicMock
from codegenie.sandbox.did.client import DockerInDockerClient

def test_oom_killed_inspect_flag_sets_sandbox_run(monkeypatch, tmp_path, allowlist, tiny_spec):
    """OOMKilled=True in container.attrs MUST flip the SandboxRun field.
    A passing test here is the only thing keeping Edge case #4 working."""
    fake = MagicMock()
    fake.wait.return_value = {"StatusCode": 137}
    fake.logs.return_value = iter([])
    fake.attrs = {"State": {"OOMKilled": True}}
    fake_docker = MagicMock(); fake_docker.containers.create.return_value = fake
    monkeypatch.setattr("docker.from_env", lambda: fake_docker)
    monkeypatch.chdir(tmp_path)
    run = DockerInDockerClient(allowlist=allowlist).execute(tiny_spec)
    assert run.killed_by_oom is True
    assert run.timed_out is False
```

### Green — make it pass

- Implement `copy_out.py` with `get_archive`-based extraction and miss-tolerance.
- Add `_wait_with_timeout(container, timeout) -> dict` helper; on timeout `kill + wait again`.
- Wire `container.reload()` and `attrs.State.OOMKilled` check.
- Generate `tests/golden/docker_cp_args_stage6_validate.json` from a captured `container.get_archive` argument list.

### Refactor — clean up

- Extract `_safe_extract(tar_bytes, dest) -> None` with path-traversal guard (tar entries beginning with `/` or `..`).
- Docstrings citing edge cases #3 and #4.
- structlog events with `duration_ms` measured between `start` and final `wait`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/did/copy_out.py` | New — SDK tar-stream extractor + glob resolver. |
| `src/codegenie/sandbox/did/client.py` | Edit — `_wait_with_timeout`, SIGKILL on timeout, OOM detect, call `copy_out`. |
| `tests/sandbox/did/test_copy_out.py` | New — glob match/miss. |
| `tests/sandbox/did/test_timeout.py` | New — timeout → SIGKILL → `timed_out=True`. |
| `tests/sandbox/did/test_oom.py` | New — `OOMKilled` flag → `killed_by_oom=True`. |
| `tests/golden/docker_cp_args_stage6_validate.json` | New — argv golden for `get_archive` calls. |

## Out of scope

- iptables / build chokepoint — S3-03.
- `SandboxHealthProbe` — S3-06.
- Live integration against real Docker — S3-07.
- `retry_policy.timeout_retryable` semantics — wired in `GateRunner` Step 5, not here.

## Notes for the implementer

- **OOM and timeout are mutually exclusive in the `SandboxRun` model** — set one or the other, never both. The kernel returns exit 137 for either; `State.OOMKilled` is the only reliable disambiguator.
- The SDK's `container.wait()` accepts `timeout=` in some versions and raises `requests.ReadTimeout` (the underlying HTTP client) — wrap in a try/except for the appropriate exception class on your pinned docker-py version.
- `container.get_archive` returns a tar **stream** (iterator of bytes chunks); buffer to a tempfile before opening with `tarfile` — naive `BytesIO(b"".join(stream))` is fine for our log-sized payloads but flag if `npm ci`'s node_modules ends up here.
- `copy_out_root` directory must exist after `execute` returns even when `globs` is empty or every glob misses — collectors will iterate it.
- Use `container.exec_run(["sh", "-c", f"ls -1 -- {shlex.quote(glob)}"])` for glob resolution to avoid shell-injection when `egress_allowlist` entries reach here. Better: pass globs through `shlex.quote`.
- Path traversal: a malicious tar entry with `../../../etc/passwd` must extract to `dest_root/etc/passwd` (relative), never escape. Use `tarfile`'s `filter="data"` (Python 3.12+) or implement a manual prefix check.
- Don't import `subprocess` in `copy_out.py`. The SDK does the work. If you genuinely need a `docker cp` argv (e.g. for a Docker Desktop version where `get_archive` is broken), escalate to ADR amendment — do not silently add a chokepoint.
