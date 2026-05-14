# Story S1-07 — `run_external_cli` wrapper with optional bubblewrap + 64 MB cap + env strip

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready
**Effort:** M
**Depends on:** S1-06
**ADRs honored:** 02-ADR-0001 (allowlist), 02-ADR-0003 (registry annotations) — composes; this story does not itself author an ADR.

## Context

Layer B/G probes (`SemgrepProbe`, `SyftProbe`, `GrypeProbe`, `GitleaksProbe`, `ScipIndexProbe`, `AstGrepProbe`, `RipgrepCuratedProbe`, `TestCoverageMapping`) all need the same shape of subprocess invocation: a name-bound `ProbeId`, env stripped to the Phase 0 baseline, optional `bubblewrap` egress containment on Linux, a 64 MB stdout/stderr cap with tail-included on failure. `run_external_cli` is the one place that shape lives. Layer C (`docker`, `strace`) uses `run_allowlisted` directly — those probes need to construct hardening argv at the call site and the wrapper would obscure that.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #3 — run_external_cli` — public interface, internal structure, env strip, optional `bubblewrap` wrap, 64 MB stdout cap.
  - `../phase-arch-design.md §"Tradeoffs (consolidated)"` row "`bubblewrap` opt-in-on-availability" — Linux best-effort, macOS no-op.
  - `../phase-arch-design.md §"Anti-patterns avoided"` row "Hexagonal sandbox that smuggles subprocess into the core" — `run_external_cli` is honestly a Command-pattern wrapper; do not invent a `Port` abstraction.
  - `../phase-arch-design.md §"Goals"` G6 — "One subprocess port for Layer B/G external CLIs; Layer C keeps using `run_allowlisted` directly."
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md` — 02-ADR-0001 §Consequences — `run_external_cli` wraps for seven Layer B/G binaries; `RuntimeTraceProbe` calls `run_allowlisted("docker", …)` directly.
- **Source design:**
  - `../final-design.md §"Components" §3 _run_external_cli` — composition rationale.
- **Existing code:**
  - `src/codegenie/exec.py` — Phase 0 `run_allowlisted` is the delegate; reuse `_filter_env`, `_RUNNING_PROCS`, the SIGTERM→SIGKILL escalation. **Extend the same module — do not create a new file** (`run_external_cli` is the second function in `exec.py`).
  - S1-06's extension to `ALLOWED_BINARIES` — already present when this story lands (depends-on).
- **External docs (only if directly relevant):**
  - https://man7.org/linux/man-pages/man1/bwrap.1.html — `bubblewrap` flags (`--unshare-net`, `--ro-bind`, `--bind`).

## Goal

Extend `src/codegenie/exec.py` with `async def run_external_cli(probe_name: ProbeId, argv: list[str], *, cwd: Path, timeout_s: float, allowlisted_egress: frozenset[str] = frozenset(), max_stdout_bytes: int = 64 * 1024 * 1024) -> ProcessResult` — a wrapper over `run_allowlisted` that strips env to the Phase 0 baseline, optionally wraps `argv` in `bubblewrap --unshare-net --ro-bind <cwd> /work --bind <tmp> /tmp/probe` when `bwrap` is on `$PATH` on Linux (graceful no-op on macOS or when missing), caps stdout/stderr at 64 MB tail-included, and `asyncio.wait_for(timeout_s)`-times the whole call.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/exec.py` exports `run_external_cli` via `__all__`. Signature exactly matches the architecture: `probe_name: ProbeId`, `argv: list[str]`, `*`, `cwd: Path`, `timeout_s: float`, `allowlisted_egress: frozenset[str] = frozenset()`, `max_stdout_bytes: int = 64 * 1024 * 1024`.
- [ ] **AC-2.** `run_external_cli` delegates to `run_allowlisted` (Phase 0) — does **not** duplicate the six Phase 0 invariants (allowlist check, shell off, stdin DEVNULL, env strip, cwd hygiene, timeout escalation).
- [ ] **AC-3.** When `sys.platform.startswith("linux")` AND `shutil.which("bwrap") is not None`: the actual argv passed to `run_allowlisted` is `["bwrap", "--unshare-net", "--ro-bind", str(cwd), "/work", "--bind", "/tmp/<probe>-<pid>", "/tmp/probe", "--"] + argv` (one tmpdir per call; cleaned up in `finally`). When `allowlisted_egress` is non-empty, omit `--unshare-net` (egress needed for that call). **`bwrap` is NOT added to `ALLOWED_BINARIES`** (it's a wrapper, invoked from `exec.py` only, same trust tier as `run_allowlisted` itself); the call site is documented in the module docstring.
- [ ] **AC-4.** When `sys.platform == "darwin"` OR `shutil.which("bwrap") is None`: `bwrap` wrap is skipped; a single startup-warning is emitted **once per process** via a module-level flag (`_BWRAP_WARNED`) so subsequent calls don't spam the log. The probe-side argv is passed directly to `run_allowlisted`.
- [ ] **AC-5.** Stdout/stderr are capped at `max_stdout_bytes` (default 64 MB). On exceed, the wrapper truncates to the **tail** — i.e., the last `max_stdout_bytes // 2` bytes of stdout and stderr each — and the returned `ProcessResult.stdout` / `.stderr` carry the truncated tail prefixed with `b"...[TRUNCATED]..."`. The behavior matches `../phase-arch-design.md §"Component design" #3 — Failure behavior` ("stdout/stderr capped, tail-included in failures").
- [ ] **AC-6.** Non-zero exit codes from the child are **not** raised — `run_external_cli` returns `ProcessResult(returncode=N, stdout=tail, stderr=tail)` and the *caller* (a scanner probe) wraps it into `ScannerOutcome.ScannerFailed`. Timeouts and tool-missing continue to raise `ProbeTimeoutError` / `ToolMissingError` per Phase 0.
- [ ] **AC-7.** Env-strip: the env passed to the child is exactly `_filter_env(env_extra=None)` from Phase 0 (no additional `env_extra` parameter on `run_external_cli` — every caller wants the bare baseline; if a future tool needs `GIT_SSH_COMMAND`, that's a per-binary ADR amendment). Sensitive keys cannot reach the child by construction.
- [ ] **AC-8.** A test exercises:
  - happy path (mock `run_allowlisted` to return `ProcessResult(0, b"ok", b"")`) — `run_external_cli` returns the same;
  - 64 MB cap (mock returns 100 MB) — result stdout is `len <= 64 * 1024 * 1024` and contains `b"...[TRUNCATED]..."`;
  - macOS path (`sys.platform == "darwin"`) — `bwrap` wrap is skipped; warning emitted once per process; argv reaches `run_allowlisted` unwrapped;
  - Linux + `bwrap` present (mock `shutil.which("bwrap") -> "/usr/bin/bwrap"`) — `bwrap --unshare-net …` is prepended;
  - Linux + `allowlisted_egress={"github.com"}` — `--unshare-net` is omitted;
  - Linux + `bwrap` missing — graceful no-op, warning once per process;
  - Timeout via `asyncio.wait_for(timeout_s)` — `ProbeTimeoutError` propagates;
  - Non-zero exit — `ProcessResult(returncode=N, stdout=..., stderr=...)` is returned (no raise).
- [ ] **AC-9.** `tests/adv/test_no_shell_true.py` (Phase 0 S4-05) stays green — no new direct `subprocess.run`/`asyncio.create_subprocess_exec` callsite outside `exec.py`.
- [ ] **AC-10.** Structured log emission: `subproc.bwrap.wrapped` (Linux + bwrap present), `subproc.bwrap.skipped` (macOS or missing, once per process), `subproc.stdout.truncated` (cap hit) — verified by structlog test capture.
- [ ] **AC-11.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-12.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/exec/` all pass on the touched files.

## Implementation outline

1. In `src/codegenie/exec.py`, add a module-level `_BWRAP_WARNED: bool = False` (used as a "warn once" gate).
2. Add `_maybe_wrap_with_bwrap(argv, cwd, allowlisted_egress) -> tuple[list[str], list[Path]]` — returns `(wrapped_argv, tmp_dirs_to_clean)`. On non-Linux or missing `bwrap`, sets `_BWRAP_WARNED` and returns `(argv, [])`. On Linux + `bwrap`: build the `bwrap` argv (omit `--unshare-net` if `allowlisted_egress` is non-empty), create a per-call tmpdir under `tempfile.mkdtemp(prefix=f"{probe_name}-")`, append it to the return list.
3. Add `_truncate_tail(buf: bytes, cap: int) -> bytes` — if `len(buf) <= cap`, return as-is; else return `b"...[TRUNCATED]..." + buf[-(cap - len(b"...[TRUNCATED]...")):]`.
4. Add `async def run_external_cli(...)`. The body: build wrapped argv → call `run_allowlisted(wrapped_argv, cwd=cwd, timeout_s=timeout_s)` → on `ProcessResult`, truncate stdout/stderr if needed → return; in `finally`, `shutil.rmtree` any tmpdirs.
5. Append `"run_external_cli"` to `__all__`.
6. Red tests → impl → refactor.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/exec/test_run_external_cli.py`

```python
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from codegenie.errors import ProbeTimeoutError
from codegenie.exec import ProcessResult, run_external_cli


@pytest.fixture
def fake_cwd(tmp_path: Path) -> Path:
    return tmp_path


async def test_happy_path_delegates_to_run_allowlisted(fake_cwd: Path) -> None:
    expected = ProcessResult(returncode=0, stdout=b"ok", stderr=b"")
    fake = AsyncMock(return_value=expected)
    with patch("codegenie.exec.run_allowlisted", fake):
        result = await run_external_cli(
            "semgrep_probe", ["semgrep", "--version"], cwd=fake_cwd, timeout_s=5.0,
        )
    assert result == expected
    fake.assert_awaited_once()


async def test_64mb_stdout_cap_truncates_tail(fake_cwd: Path) -> None:
    huge = b"A" * (100 * 1024 * 1024)
    fake = AsyncMock(return_value=ProcessResult(returncode=0, stdout=huge, stderr=b""))
    with patch("codegenie.exec.run_allowlisted", fake):
        result = await run_external_cli(
            "semgrep_probe", ["semgrep", "scan"], cwd=fake_cwd, timeout_s=5.0,
        )
    assert len(result.stdout) <= 64 * 1024 * 1024
    assert b"...[TRUNCATED]..." in result.stdout
    # tail preservation — last bytes of original survive
    assert result.stdout.endswith(b"A" * 1024)


async def test_macos_skips_bwrap_warns_once(monkeypatch: pytest.MonkeyPatch, fake_cwd: Path) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    # reset the module-level warn-once flag
    import codegenie.exec as ex
    monkeypatch.setattr(ex, "_BWRAP_WARNED", False, raising=False)
    seen: list[list[str]] = []
    async def fake_run_allowlisted(argv: list[str], **kwargs: object) -> ProcessResult:
        seen.append(argv)
        return ProcessResult(returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr(ex, "run_allowlisted", fake_run_allowlisted)
    await run_external_cli("p1", ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0)
    await run_external_cli("p2", ["semgrep", "y"], cwd=fake_cwd, timeout_s=5.0)
    # bwrap NEVER prepended on macOS
    assert all(a[0] == "semgrep" for a in seen)


async def test_linux_with_bwrap_wraps_argv(monkeypatch: pytest.MonkeyPatch, fake_cwd: Path) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("codegenie.exec.shutil.which", lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    seen: list[list[str]] = []
    async def fake_run_allowlisted(argv: list[str], **kwargs: object) -> ProcessResult:
        seen.append(argv)
        return ProcessResult(returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr("codegenie.exec.run_allowlisted", fake_run_allowlisted)
    await run_external_cli("p1", ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0)
    assert seen[0][0] == "bwrap"
    assert "--unshare-net" in seen[0]
    assert "--ro-bind" in seen[0]
    assert "--" in seen[0]
    # Probe argv preserved after the `--` separator
    sep = seen[0].index("--")
    assert seen[0][sep + 1 :] == ["semgrep", "x"]


async def test_linux_with_bwrap_egress_omits_unshare_net(monkeypatch: pytest.MonkeyPatch, fake_cwd: Path) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("codegenie.exec.shutil.which", lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    seen: list[list[str]] = []
    async def fake_run_allowlisted(argv: list[str], **kwargs: object) -> ProcessResult:
        seen.append(argv)
        return ProcessResult(returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr("codegenie.exec.run_allowlisted", fake_run_allowlisted)
    await run_external_cli(
        "p1", ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0,
        allowlisted_egress=frozenset({"github.com"}),
    )
    assert "--unshare-net" not in seen[0]


async def test_linux_without_bwrap_warns_once(monkeypatch: pytest.MonkeyPatch, fake_cwd: Path) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("codegenie.exec.shutil.which", lambda name: None)
    import codegenie.exec as ex
    monkeypatch.setattr(ex, "_BWRAP_WARNED", False, raising=False)
    seen: list[list[str]] = []
    async def fake_run_allowlisted(argv: list[str], **kwargs: object) -> ProcessResult:
        seen.append(argv)
        return ProcessResult(returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr(ex, "run_allowlisted", fake_run_allowlisted)
    await run_external_cli("p1", ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0)
    assert seen[0][0] == "semgrep"  # no wrap


async def test_timeout_propagates(monkeypatch: pytest.MonkeyPatch, fake_cwd: Path) -> None:
    async def fake_run_allowlisted(argv: list[str], **kwargs: object) -> ProcessResult:
        raise ProbeTimeoutError("semgrep exceeded timeout_s=5 (elapsed_ms=5001)")
    monkeypatch.setattr("codegenie.exec.run_allowlisted", fake_run_allowlisted)
    with pytest.raises(ProbeTimeoutError):
        await run_external_cli("p1", ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0)


async def test_nonzero_exit_returned_not_raised(monkeypatch: pytest.MonkeyPatch, fake_cwd: Path) -> None:
    async def fake_run_allowlisted(argv: list[str], **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=2, stdout=b"out", stderr=b"err")
    monkeypatch.setattr("codegenie.exec.run_allowlisted", fake_run_allowlisted)
    result = await run_external_cli("p1", ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0)
    assert result.returncode == 2
    assert result.stdout == b"out"
    assert result.stderr == b"err"
```

Run — confirm `ImportError: cannot import name 'run_external_cli' from 'codegenie.exec'`. Commit.

### Green — make it pass

Sketch (extension of `exec.py`):

```python
# in src/codegenie/exec.py — append
import shutil
import sys
import tempfile

_BWRAP_WARNED: bool = False
_TRUNC_MARKER: bytes = b"...[TRUNCATED]..."


def _maybe_wrap_with_bwrap(
    probe_name: str,
    argv: list[str],
    cwd: Path,
    allowlisted_egress: frozenset[str],
) -> tuple[list[str], list[Path]]:
    global _BWRAP_WARNED
    if not sys.platform.startswith("linux"):
        if not _BWRAP_WARNED:
            _log.warning("subproc.bwrap.skipped", reason="not_linux", platform=sys.platform)
            _BWRAP_WARNED = True
        return argv, []
    if shutil.which("bwrap") is None:
        if not _BWRAP_WARNED:
            _log.warning("subproc.bwrap.skipped", reason="not_installed")
            _BWRAP_WARNED = True
        return argv, []
    tmpdir = Path(tempfile.mkdtemp(prefix=f"{probe_name}-"))
    wrap = ["bwrap"]
    if not allowlisted_egress:
        wrap.append("--unshare-net")
    wrap += ["--ro-bind", str(cwd), "/work", "--bind", str(tmpdir), "/tmp/probe", "--"]
    _log.debug("subproc.bwrap.wrapped", probe_name=probe_name, egress=bool(allowlisted_egress))
    return wrap + argv, [tmpdir]


def _truncate_tail(buf: bytes, cap: int) -> bytes:
    if len(buf) <= cap:
        return buf
    keep = cap - len(_TRUNC_MARKER)
    return _TRUNC_MARKER + buf[-keep:]


async def run_external_cli(
    probe_name: str,
    argv: list[str],
    *,
    cwd: Path,
    timeout_s: float,
    allowlisted_egress: frozenset[str] = frozenset(),
    max_stdout_bytes: int = 64 * 1024 * 1024,
) -> ProcessResult:
    wrapped, tmpdirs = _maybe_wrap_with_bwrap(probe_name, argv, cwd, allowlisted_egress)
    try:
        result = await run_allowlisted(wrapped, cwd=cwd, timeout_s=timeout_s)
    finally:
        for d in tmpdirs:
            shutil.rmtree(d, ignore_errors=True)
    truncated_out = _truncate_tail(result.stdout, max_stdout_bytes)
    truncated_err = _truncate_tail(result.stderr, max_stdout_bytes)
    if truncated_out is not result.stdout or truncated_err is not result.stderr:
        _log.warning("subproc.stdout.truncated", probe_name=probe_name)
        return ProcessResult(returncode=result.returncode, stdout=truncated_out, stderr=truncated_err)
    return result
```

Extend `__all__` to include `"run_external_cli"`.

### Refactor — clean up

- Update the module docstring of `exec.py`: a new paragraph naming `run_external_cli` as the Layer-B/G wrapper and pointing at 02-ADR-0001 §Consequences and `../phase-arch-design.md §"Component design" #3`.
- Confirm: no second `asyncio.create_subprocess_exec` callsite — `bwrap` reaches the kernel only via `run_allowlisted` (which `bwrap`'s argv goes through; but `bwrap` itself is **not in `ALLOWED_BINARIES`**, so `run_allowlisted` would reject it). **Reconcile:** `bwrap` must be added to `ALLOWED_BINARIES` after all, OR `run_external_cli` invokes `asyncio.create_subprocess_exec` directly for the `bwrap` case. The architecture says `run_external_cli` "wraps `run_allowlisted`" — so the simplest correct shape is: add `bwrap` to `ALLOWED_BINARIES` (a one-line amendment to S1-06's frozenset; document in 02-ADR-0001 §Consequences or open a separate amendment). Pick this path at implementation time and update both S1-06 and 02-ADR-0001 accordingly. **This story names the reconciliation as a known issue and resolves it before merge.**
- Verify: `tests/adv/test_no_shell_true.py` continues to pass.
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/exec.py tests/unit/exec/test_run_external_cli.py`, `pytest tests/unit/exec/ -v`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/exec.py` | Add `run_external_cli` + `_maybe_wrap_with_bwrap` + `_truncate_tail` + `_BWRAP_WARNED`. |
| `tests/unit/exec/test_run_external_cli.py` | Coverage for happy path, 64 MB cap, macOS/Linux paths, bwrap egress, timeout, non-zero exit. |
| `src/codegenie/exec.py` `ALLOWED_BINARIES` | Reconciliation: add `bwrap` to the allowlist OR document the direct-invocation exception. See refactor §reconcile. |

## Out of scope

- **`docker` / `strace` wrapping** — explicitly NOT routed through `run_external_cli` (per 02-ADR-0001 §Tradeoffs and `../phase-arch-design.md §"Component design" #3`); Layer C probes (S5-02 onward) call `run_allowlisted` directly with hardening flags.
- **Per-probe egress policy enforcement** — `allowlisted_egress` is the **caller**'s declaration; this story neither validates nor enforces it. The `--unshare-net` flag is the structural defense; the egress hostnames are advisory metadata for logs.
- **Network namespaces beyond `bwrap`** — Linux network namespaces / nftables rules are Phase 5 (microVM) work.
- **Per-tool retry policy** — bare-metal "is the tool flaking" is the caller's concern; `run_external_cli` runs once.
- **Streaming output processing** — buffered, then capped. If a future tool needs streaming (>>64 MB stdout for SBOM JSON?), that's a separate ADR.

## Notes for the implementer

- **`bwrap` allowlist reconciliation.** The architecture says `run_external_cli` *wraps* `run_allowlisted`. The cleanest implementation prepends `bwrap` to `argv` and calls `run_allowlisted(bwrap-wrapped-argv, …)` — which means `bwrap` must be in `ALLOWED_BINARIES`. Add it to S1-06's frozenset and update 02-ADR-0001's table to mention it as the wrapper exception (single-paragraph amendment). The alternative — `asyncio.create_subprocess_exec` directly in `run_external_cli` — creates a second chokepoint and violates `tests/adv/test_no_shell_true.py`. Pick the allowlist amendment; it's the structural fit.
- **Warn-once flag is module-level.** A `_BWRAP_WARNED: bool` global is the simplest correct shape; a `threading.Lock` is unnecessary (warnings are idempotent and the race is benign). Tests reset it via `monkeypatch.setattr(ex, "_BWRAP_WARNED", False)`.
- **Tail truncation, not head.** When stdout is huge, the tail is what matters (final error message, last finding). `_truncate_tail` is the right shape; do not invent `head_and_tail` interleaving.
- **`run_external_cli` is the per-call-site decoration, not a sandbox.** The architecture is explicit: `bubblewrap` is opt-in-on-availability hardening, NOT a substitute for the Phase 5 microVM. Do not market it as one in docstrings.
- **Layer C does not call this function.** S5-02's `RuntimeTraceProbe` calls `run_allowlisted("docker", […", "run", "--network=none", "--cap-drop=ALL", "--security-opt=no-new-privileges", …])` directly — those flags are hardening, not generic. The wrapper's `--unshare-net` is not equivalent to `docker run --network=none`; that's why Layer C bypasses.
- **No `env_extra` on `run_external_cli`.** Phase 2 scanners do not need supplemental env. If a future probe does (e.g., `GIT_SSH_COMMAND` for a hypothetical signed-fetch use case), that's a per-probe-ADR amendment; do not preemptively widen the signature.
- **Cleanup discipline.** Per-call `mkdtemp` MUST be `rmtree`-cleaned in `finally`. The Phase 0 audit anchor and cache hygiene depend on this — leaking tmpdirs is a slow-burning resource leak that surfaces only in CI long after.
