"""The one-and-only path from ``codegenie`` source to an external binary.

ADR-0012 makes this module a load-bearing chokepoint: every subprocess invocation
across the lifetime of the project routes through :func:`run_allowlisted`. The
wrapper enforces six invariants in one place so Phase 7's ~30 subprocess callsites
inherit the discipline without per-callsite audits:

1. ``argv[0]`` must be in :data:`ALLOWED_BINARIES` — checked *before* any spawn.
2. The shell flag is implicitly off — :func:`asyncio.create_subprocess_exec`
   has no ``shell`` parameter at all. The ``forbidden-patterns`` pre-commit
   hook blocks any reintroduction of a shell-enabled subprocess call
   anywhere in ``src/codegenie/``.
3. ``stdin`` is explicitly :data:`asyncio.subprocess.DEVNULL`.
4. The child environment is built by *omission*: a four-key safe baseline
   (``PATH``/``HOME``/``LANG``/``LC_ALL``) plus a sanitized ``env_extra``. The
   parent process's ``os.environ`` is never copied — so ``OPENAI_API_KEY``,
   ``AWS_*``, ``SSH_AUTH_SOCK``, ``GITHUB_TOKEN``, ``ANTHROPIC_API_KEY`` are
   structurally absent rather than explicitly deleted.
5. ``cwd`` is mandatory; the wrapper resolves it and asserts it is an existing
   directory. Under-repo-root enforcement is the caller's responsibility
   (the CLI resolves the repo root with ``Path.resolve(strict=True)`` at its
   single Phase 0 callsite).
6. Timeout is mandatory; on expiry the wrapper escalates SIGTERM → 100 ms grace
   → SIGKILL and raises :class:`~codegenie.errors.ProbeTimeoutError` with an
   ``elapsed_ms=`` substring for log forensics.

A module-level :data:`_RUNNING_PROCS` weakref table registers the in-flight child
process by pid. Phase 7's coordinator-cancel path iterates this table to SIGKILL
stragglers; the wrapper pops on every exit (success / timeout / tool-missing /
other) inside a ``finally:`` block so the table stays accurate during a run.

The structural defense around this module is ``tests/adv/test_no_shell_true.py``
(Phase 0 adversarial suite, S4-05): an AST scan that fails CI if any file under
``src/codegenie/`` other than this one imports ``asyncio.create_subprocess_exec``
or ``subprocess.run``.

Sources:

- ``docs/phases/00-bullet-tracer-foundations/ADRs/0012-subprocess-allowlist-chokepoint.md``
- ``docs/phases/01-context-gather-layer-a-node/ADRs/0001-add-node-to-allowed-binaries.md``
- ``docs/phases/00-bullet-tracer-foundations/phase-arch-design.md``
  §Component design — Subprocess allowlist
- ``docs/phases/00-bullet-tracer-foundations/stories/S2-04-exec-allowlist.md``
"""

from __future__ import annotations

import asyncio
import os
import weakref
from dataclasses import dataclass
from pathlib import Path

import structlog

from codegenie.errors import (
    DisallowedSubprocessError,
    ProbeTimeoutError,
    ToolMissingError,
)

__all__ = [
    "ALLOWED_BINARIES",
    "ProcessResult",
    "run_allowlisted",
]

# Phase 0 allowlist was exactly ``{"git"}``; Phase 1 ADR-0001 extends to
# ``{"git", "node"}`` so ``NodeBuildSystemProbe`` can record the locally-resolved
# Node version via ``node --version``. Every addition is a deliberate-PR change
# with mandatory review (ADR-0012 §Decision).
ALLOWED_BINARIES: frozenset[str] = frozenset({"git", "node"})

# Keys that must never reach a child process via ``env_extra``. ``AWS_*`` is
# matched by prefix. Comparison is on the uppercased key so callers can't
# bypass with ``"openai_api_key"``.
_SENSITIVE_EXACT: frozenset[str] = frozenset(
    {"SSH_AUTH_SOCK", "GITHUB_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
)
_SENSITIVE_PREFIX: tuple[str, ...] = ("AWS_",)

# Grace window between SIGTERM and SIGKILL on timeout escalation. ADR-0012 calls
# for SIGKILL at ``1.5 × timeout_s`` cumulative; 100 ms after SIGTERM matches
# that envelope for the Phase 0 ``git`` use case and is verified by the test
# suite via a fake ``Process`` whose ``communicate()`` awaits an Event the test
# never sets.
_SIGTERM_GRACE_S: float = 0.1

# Weakref table of in-flight children, keyed by pid. Phase 7's coordinator-cancel
# path will iterate this on shutdown to SIGKILL stragglers; the wrapper itself
# pops on every exit path inside a ``finally:`` block so the table is accurate
# during a run as well.
_RUNNING_PROCS: weakref.WeakValueDictionary[int, asyncio.subprocess.Process] = (
    weakref.WeakValueDictionary()
)

_log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ProcessResult:
    """Immutable record of a completed allowlisted subprocess.

    ``frozen=True`` is load-bearing — callers index this into the
    ``RepoSnapshot`` and downstream probes hash it; mutability would defeat
    the cache-key story (S3-01).
    """

    returncode: int
    stdout: bytes
    stderr: bytes


def _is_sensitive(key: str) -> bool:
    """Return ``True`` if *key* must be dropped from ``env_extra``.

    Comparison is on ``upper()`` so ``"openai_api_key"`` and ``"OPENAI_API_KEY"``
    are treated identically.
    """
    upper = key.upper()
    if upper in _SENSITIVE_EXACT:
        return True
    return any(upper.startswith(p) for p in _SENSITIVE_PREFIX)


def _filter_env(env_extra: dict[str, str] | None) -> dict[str, str]:
    """Build the child environment by omission.

    The baseline is four keys read from the parent — ``PATH`` is required
    (the OS needs it to resolve the binary); the other three default to
    safe values when absent. ``env_extra`` overlays the baseline so callers
    can supply legitimate extras (e.g. ``GIT_SSH_COMMAND``) and even override
    ``PATH`` for test fixtures. Sensitive keys in ``env_extra`` are silently
    dropped and logged at WARNING — the wrapper is a chokepoint, not a
    backdoor.
    """
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C"),
        "LC_ALL": os.environ.get("LC_ALL", "C"),
    }
    if env_extra:
        for key, value in env_extra.items():
            if _is_sensitive(key):
                _log.warning(
                    "subproc.env_extra.sensitive_key_dropped",
                    key=key,
                )
                continue
            env[key] = value
    return env


async def _escalate_and_kill(proc: asyncio.subprocess.Process) -> None:
    """SIGTERM the child, sleep ``_SIGTERM_GRACE_S``, then SIGKILL and reap.

    The escalation is unconditional: even if the child exits during the grace
    window, we still call ``kill()`` — the call is harmless on a finished
    process and gives the test suite a deterministic spy assertion. The
    final ``await proc.wait()`` reaps the zombie so callers never see one;
    if the kernel never delivers the exit (pathological case), we cap the
    wait at the remaining 0.5 × timeout budget that ADR-0012 carves out for
    SIGKILL beyond the original ``timeout_s``.
    """
    proc.terminate()
    await asyncio.sleep(_SIGTERM_GRACE_S)
    proc.kill()
    try:
        await asyncio.wait_for(proc.wait(), timeout=_SIGTERM_GRACE_S)
    except TimeoutError:
        # The kernel will reap eventually; we have done everything the wrapper
        # is allowed to do.
        pass


async def run_allowlisted(
    argv: list[str],
    *,
    cwd: Path,
    timeout_s: float,
    env_extra: dict[str, str] | None = None,
) -> ProcessResult:
    """Run an allowlisted external binary with the six chokepoint invariants.

    Args:
        argv: Tokenized command. ``argv[0]`` must be a bare binary name (no
            ``/usr/bin/git``, no ``./git``) and must appear in
            :data:`ALLOWED_BINARIES`. Empty ``argv`` is rejected.
        cwd: Working directory for the child. Must exist and be a directory.
            Resolved via :meth:`pathlib.Path.resolve` (strict). Under-repo-root
            enforcement is the caller's responsibility in Phase 0.
        timeout_s: Wall-clock budget. On expiry, the wrapper escalates
            SIGTERM → SIGKILL and raises :class:`ProbeTimeoutError`.
        env_extra: Optional narrow passthrough of additional env vars. Keys
            in the sensitive set (``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``,
            ``GITHUB_TOKEN``, ``SSH_AUTH_SOCK``, ``AWS_*``) are silently
            dropped and logged at WARNING.

    Returns:
        A frozen :class:`ProcessResult` carrying the return code and stdio.

    Raises:
        DisallowedSubprocessError: ``argv`` is empty or ``argv[0]`` is not in
            :data:`ALLOWED_BINARIES`. Raised *before* any process is spawned.
        FileNotFoundError: ``cwd`` does not exist.
        NotADirectoryError: ``cwd`` exists but is not a directory.
        ToolMissingError: The binary is not resolvable on ``PATH``.
        ProbeTimeoutError: The child did not exit within ``timeout_s``. The
            error's ``str()`` contains ``elapsed_ms=<int>`` for forensics.
    """
    # (1) Allowlist check — must happen before any spawn.
    if not argv:
        raise DisallowedSubprocessError("empty argv is not allowlisted")
    binary = argv[0]
    if binary not in ALLOWED_BINARIES:
        raise DisallowedSubprocessError(
            f"binary {binary!r} is not in ALLOWED_BINARIES (allowed: {sorted(ALLOWED_BINARIES)})"
        )

    # (2) cwd hygiene — Path.resolve(strict=True) raises FileNotFoundError for
    # missing paths; is_dir() distinguishes regular files.
    resolved_cwd = cwd.resolve(strict=True)
    if not resolved_cwd.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {resolved_cwd}")

    env = _filter_env(env_extra)
    loop = asyncio.get_event_loop()
    start = loop.time()

    _log.debug(
        "subproc.spawn",
        argv0=binary,
        cwd=str(resolved_cwd),
        timeout_s=timeout_s,
    )

    # (3) Spawn. ``create_subprocess_exec`` is implicitly shell=False.
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=resolved_cwd,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ToolMissingError(
            f"{binary!r} not found on PATH — install it or fix your PATH ({exc})"
        ) from exc

    pid = proc.pid
    _RUNNING_PROCS[pid] = proc

    try:
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError:
            await _escalate_and_kill(proc)
            elapsed_ms = int((loop.time() - start) * 1000)
            _log.warning(
                "subproc.timeout",
                argv0=binary,
                elapsed_ms=elapsed_ms,
            )
            raise ProbeTimeoutError(
                f"{binary!r} exceeded timeout_s={timeout_s} (elapsed_ms={elapsed_ms})"
            ) from None

        elapsed_ms = int((loop.time() - start) * 1000)
        _log.debug(
            "subproc.exit",
            argv0=binary,
            returncode=proc.returncode,
            elapsed_ms=elapsed_ms,
        )
        # proc.returncode is set once communicate() returns.
        assert proc.returncode is not None  # noqa: S101 — invariant of communicate()
        return ProcessResult(
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    finally:
        _RUNNING_PROCS.pop(pid, None)
