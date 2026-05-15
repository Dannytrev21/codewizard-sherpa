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

Phase 2 (02-ADR-0001) extends :data:`ALLOWED_BINARIES` with the ten Layer B/C/G
tools listed in
``docs/phases/02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md``.
Future additions are ADR-amend or new-phase-ADR; no silent expansion.

Sources:

- ``docs/phases/00-bullet-tracer-foundations/ADRs/0012-subprocess-allowlist-chokepoint.md``
- ``docs/phases/01-context-gather-layer-a-node/ADRs/0001-add-node-to-allowed-binaries.md``
- ``docs/phases/02-context-gather-layers-b-g/ADRs/``
  ``0001-add-docker-and-security-cli-tools-to-allowed-binaries.md``
- ``docs/phases/00-bullet-tracer-foundations/phase-arch-design.md``
  §Component design — Subprocess allowlist
- ``docs/phases/00-bullet-tracer-foundations/stories/S2-04-exec-allowlist.md``
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
import tempfile
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import structlog

from codegenie.errors import (
    DisallowedSubprocessError,
    ProbeTimeoutError,
    ToolMissingError,
)

if TYPE_CHECKING:
    # Lazy import to avoid the circular dependency between this module and
    # ``codegenie.types.identifiers`` (which re-exports ``PackageManager``
    # from ``codegenie.probes.node_build_system``, which itself imports
    # ``codegenie.exec``). The type is used only in the
    # :func:`run_external_cli` signature; we never call ``ProbeId(...)`` in
    # this module.
    from codegenie.types.identifiers import ProbeId

__all__ = [
    "ALLOWED_BINARIES",
    "ProcessResult",
    "run_allowlisted",
    "run_external_cli",
]

# Phase 0 allowlist was ``{"git"}``; Phase 1 ADR-0001 added ``node``; Phase 2
# 02-ADR-0001 (and its AC-10 amendment) extends with ten Layer B/C/G tools
# listed in ``docs/phases/02-context-gather-layers-b-g/ADRs/0001-add-docker-
# and-security-cli-tools-to-allowed-binaries.md``. Every addition is a
# deliberate-PR change with mandatory review (ADR-0012 §Decision); future
# additions are ADR-amend or new-phase-ADR — no silent expansion.
ALLOWED_BINARIES: frozenset[str] = frozenset(
    {
        "git",
        "node",
        "semgrep",
        "syft",
        "grype",
        "gitleaks",
        "scip-typescript",
        "ast-grep",
        "ripgrep",
        "tree-sitter",
        "docker",
        "strace",
    }
)

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
    return await _spawn_with_invariants(
        argv,
        cwd=resolved_cwd,
        timeout_s=timeout_s,
        env=env,
    )


async def _spawn_with_invariants(
    argv: list[str],
    *,
    cwd: Path,
    timeout_s: float,
    env: dict[str, str],
) -> ProcessResult:
    """Shared private spawn used by ``run_allowlisted`` and the bwrap path.

    Owns five of the six Phase 0 invariants: no shell, ``stdin=DEVNULL``, env
    supplied by the caller (pre-built via :func:`_filter_env`), mandatory
    ``cwd`` (caller resolves and validates), mandatory ``timeout_s`` with
    SIGTERM → 100 ms grace → SIGKILL escalation, and ``_RUNNING_PROCS``
    registration. The **allowlist check is the caller's responsibility**:

    - :func:`run_allowlisted` checks ``argv[0] in ALLOWED_BINARIES`` before
      calling this helper.
    - :func:`run_external_cli` allowlist-checks the **inner** ``argv[0]`` at
      its boundary, then calls this helper on the bwrap path with a
      ``bwrap``-prefixed argv (``bwrap`` itself is intentionally NOT in
      ``ALLOWED_BINARIES`` per 02-ADR-0001 §Consequences last bullet; the
      wrapper-pattern exception is structural — the spawn lives inside this
      module, same trust tier as the chokepoint itself).
    """
    binary = argv[0]
    loop = asyncio.get_event_loop()
    start = loop.time()

    _log.debug(
        "subproc.spawn",
        argv0=binary,
        cwd=str(cwd),
        timeout_s=timeout_s,
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
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
        assert proc.returncode is not None  # noqa: S101 — invariant of communicate()
        return ProcessResult(
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    finally:
        _RUNNING_PROCS.pop(pid, None)


# ---------------------------------------------------------------------------
# Phase 2 / S1-07 — ``run_external_cli`` Layer B/G subprocess port.
#
# Adds optional ``bubblewrap`` egress containment, a 64 MB stdout/stderr cap
# with tail preservation, env-strip to the Phase 0 baseline, and warn-once
# behavior. ``bwrap``/``bubblewrap`` are *intentionally* NOT in
# ``ALLOWED_BINARIES`` (02-ADR-0001 §Consequences last bullet; pinned by the
# closed-set regression test
# ``tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression``):
# the bwrap spawn lives **inside this module** via :func:`_spawn_bwrap_wrapped`
# / :func:`_spawn_with_invariants` (same file, same trust tier as
# :func:`run_allowlisted`). The wrapper-pattern exception is the recorded
# decision; the inner probe binary (``argv[0]`` of the caller's argv) is what
# gets allowlist-checked at the boundary of :func:`run_external_cli`.
#
# See:
# - ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
#   §"Component design" #3 (public interface, internal structure).
# - ``docs/phases/02-context-gather-layers-b-g/ADRs/0001-...md``
#   §Consequences last bullet (bwrap-not-in-allowlist wrapper-pattern exception).
# ---------------------------------------------------------------------------

_BWRAP_WARNED: bool = False
_TRUNC_MARKER: bytes = b"...[TRUNCATED]..."
_PROBE_NAME_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _platform_is_linux() -> bool:
    """Runtime platform check that mypy cannot narrow via ``sys.platform`` Literal.

    Without this indirection mypy on macOS narrows ``sys.platform`` to
    ``"darwin"`` and reports the post-check ``shutil.which("bwrap")`` branch as
    unreachable. The function is also a single seam for tests that need to
    flip platform behavior — and on Linux CI the real branch executes.
    """
    return sys.platform.startswith("linux")


def _validate_probe_name(probe_name: str) -> None:
    """Reject probe names that would be unsafe as a ``tempfile.mkdtemp`` prefix.

    ``ProbeId = NewType("ProbeId", str)`` is nominal under mypy but has no
    runtime character-class constraint. Passing ``ProbeId("../bad")`` would
    flow into ``tempfile.mkdtemp(prefix=...)`` and either fail noisily (path
    separators) or accept surprising input (whitespace). The
    ``^[a-z][a-z0-9_]{0,63}$`` shape matches the codebase convention for
    probe identifiers and is conservative.
    """
    if _PROBE_NAME_RE.match(probe_name) is None:
        raise ValueError(f"invalid probe_name: {probe_name!r}")


def _truncate_tail(buf: bytes, cap: int) -> bytes:
    """Return ``buf`` (identity) if under cap, else marker + tail.

    Invariants pinned by ``tests/property/test_truncate_tail.py``:

    1. ``len(result) <= max(cap, len(_TRUNC_MARKER))``.
    2. ``len(buf) <= cap`` ⇒ ``result is buf`` (the same object, not equal).
    3. ``len(buf) > cap`` ⇒ ``result.startswith(_TRUNC_MARKER)`` AND
       ``result.endswith(buf[-(cap - len(_TRUNC_MARKER)):])`` AND
       ``len(result) == cap`` exactly.
    """
    if len(buf) <= cap:
        return buf
    keep = cap - len(_TRUNC_MARKER)
    return _TRUNC_MARKER + buf[-keep:]


def _maybe_wrap_with_bwrap(
    probe_name: str,
    argv: list[str],
    cwd: Path,
    allowlisted_egress: frozenset[str],
) -> tuple[
    list[str],
    list[Path],
    Literal["wrapped", "skipped_not_linux", "skipped_not_installed"],
]:
    """Build the bwrap-wrapped argv, or return ``argv`` unchanged with a status.

    On non-Linux or when ``bwrap`` is missing: emit
    ``subproc.bwrap.skipped`` at WARNING **exactly once per process** (the
    module-level ``_BWRAP_WARNED`` flag is the gate), then return
    ``(argv, [], "skipped_*")``. On Linux + ``bwrap`` present: allocate a
    per-call tmpdir, build the wrap prefix (``--unshare-net`` omitted when
    ``allowlisted_egress`` is non-empty), emit ``subproc.bwrap.wrapped`` at
    DEBUG, and return ``(wrap + argv, [tmpdir], "wrapped")``.
    """
    global _BWRAP_WARNED
    _validate_probe_name(probe_name)
    if not _platform_is_linux():
        if not _BWRAP_WARNED:
            _log.warning(
                "subproc.bwrap.skipped",
                reason="not_linux",
                platform=sys.platform,
            )
            _BWRAP_WARNED = True
        return argv, [], "skipped_not_linux"
    if shutil.which("bwrap") is None:
        if not _BWRAP_WARNED:
            _log.warning("subproc.bwrap.skipped", reason="not_installed")
            _BWRAP_WARNED = True
        return argv, [], "skipped_not_installed"
    tmpdir = Path(tempfile.mkdtemp(prefix=f"{probe_name}-"))
    wrap: list[str] = ["bwrap"]
    if not allowlisted_egress:
        wrap.append("--unshare-net")
    wrap += [
        "--ro-bind",
        str(cwd),
        "/work",
        "--bind",
        str(tmpdir),
        "/tmp/probe",
        "--",
    ]
    _log.debug(
        "subproc.bwrap.wrapped",
        probe_name=probe_name,
        egress=bool(allowlisted_egress),
    )
    return wrap + argv, [tmpdir], "wrapped"


async def run_external_cli(
    probe_name: ProbeId,
    argv: list[str],
    *,
    cwd: Path,
    timeout_s: float,
    allowlisted_egress: frozenset[str] = frozenset(),
    max_stdout_bytes: int = 64 * 1024 * 1024,
) -> ProcessResult:
    """Layer-B/G subprocess port — env-strip, optional bwrap, 64 MB tail-cap.

    On Linux with ``bwrap`` on PATH the argv is wrapped with
    ``bubblewrap --unshare-net --ro-bind <cwd> /work --bind <tmpdir> /tmp/probe --``
    and invoked via the private :func:`_spawn_with_invariants` helper (the
    wrapper-pattern exception — ``bwrap`` is intentionally NOT in
    ``ALLOWED_BINARIES``; see 02-ADR-0001 §Consequences last bullet). On
    macOS or when ``bwrap`` is missing, the unwrapped argv is delegated to
    :func:`run_allowlisted` (full Phase 0 chokepoint). Non-zero exits return
    a :class:`ProcessResult`; timeouts and tool-missing continue to raise per
    Phase 0. Output is capped at ``max_stdout_bytes`` on every call (success
    or failure) with tail preservation; truncation emits
    ``subproc.stdout.truncated`` per affected stream.

    Args:
        probe_name: Identifier of the calling probe. Validated against
            ``^[a-z][a-z0-9_]{0,63}$`` before any spawn or tmpdir creation.
            Flows into ``tempfile.mkdtemp(prefix=...)`` on the bwrap path.
        argv: Tokenized command. ``argv[0]`` must be in
            :data:`ALLOWED_BINARIES` (allowlist applies to the **inner**
            probe binary, never to ``bwrap``).
        cwd: Working directory for the child. Resolved with
            ``Path.resolve(strict=True)``.
        timeout_s: Wall-clock budget.
        allowlisted_egress: Hostnames the caller declares it needs egress to.
            When non-empty, the bwrap prefix omits ``--unshare-net``
            (egress allowed); the ``--ro-bind`` / ``--bind`` separators are
            unaffected. Advisory metadata for logs — this function neither
            validates nor enforces the hostnames.
        max_stdout_bytes: Per-stream cap. Default 64 MB. When exceeded,
            :func:`_truncate_tail` returns the last ``cap - len(_TRUNC_MARKER)``
            bytes prefixed with the marker.

    Returns:
        :class:`ProcessResult` with stdout/stderr possibly truncated.

    Raises:
        DisallowedSubprocessError: ``argv`` is empty, or ``argv[0]`` is not
            in :data:`ALLOWED_BINARIES`. Raised before any spawn or tmpdir.
        ValueError: ``probe_name`` does not match the validator pattern.
        ProbeTimeoutError: The child exceeded ``timeout_s``.
        ToolMissingError: The inner binary is not on PATH.
    """
    _validate_probe_name(probe_name)
    if not argv:
        raise DisallowedSubprocessError("empty argv is not allowlisted")
    inner_binary = argv[0]
    if inner_binary not in ALLOWED_BINARIES:
        raise DisallowedSubprocessError(
            f"binary {inner_binary!r} is not in ALLOWED_BINARIES "
            f"(allowed: {sorted(ALLOWED_BINARIES)})"
        )

    resolved_cwd = cwd.resolve(strict=True)
    if not resolved_cwd.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {resolved_cwd}")

    wrapped_argv, tmpdirs, status = _maybe_wrap_with_bwrap(
        probe_name,
        argv,
        resolved_cwd,
        allowlisted_egress,
    )
    try:
        if status == "wrapped":
            # bwrap path: spawn directly inside this module (bwrap NOT in
            # ALLOWED_BINARIES; wrapper-pattern exception per 02-ADR-0001).
            result = await _spawn_with_invariants(
                wrapped_argv,
                cwd=resolved_cwd,
                timeout_s=timeout_s,
                env=_filter_env(env_extra=None),
            )
        else:
            # macOS / no-bwrap path: full Phase 0 chokepoint (includes the
            # inner-argv allowlist re-check — defense in depth).
            result = await run_allowlisted(
                argv,
                cwd=resolved_cwd,
                timeout_s=timeout_s,
            )
    finally:
        for d in tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    truncated_out = _truncate_tail(result.stdout, max_stdout_bytes)
    truncated_err = _truncate_tail(result.stderr, max_stdout_bytes)
    if truncated_out is not result.stdout:
        _log.warning(
            "subproc.stdout.truncated",
            probe_name=probe_name,
            stream="stdout",
        )
    if truncated_err is not result.stderr:
        _log.warning(
            "subproc.stdout.truncated",
            probe_name=probe_name,
            stream="stderr",
        )
    if truncated_out is not result.stdout or truncated_err is not result.stderr:
        return ProcessResult(
            returncode=result.returncode,
            stdout=truncated_out,
            stderr=truncated_err,
        )
    return result
