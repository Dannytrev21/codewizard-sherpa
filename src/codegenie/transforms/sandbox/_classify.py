"""Pure outcome classifier — S4-02 AC-23.

Both :class:`~codegenie.transforms.sandbox.bwrap.BwrapAdapter` and the
forthcoming ``SandboxExecAdapter`` (S4-03) delegate variant translation
to :func:`classify_outcome`. Centralising the logic here makes the
SIGKILL discriminator (timeout-vs-OOM tie-break) and the NetworkDenied
false-positive prevention rule (AC-5 / Coverage H2) single-sourced —
the second Adapter cannot drift from the first.

The module is **pure**: no subprocess calls, no filesystem reads, no
clock. The caller (the Adapter) collects all signals it needs from the
substrate (cgroups ``oom_kill`` count, ``memory.peak``, monotonic
elapsed time) and passes them in via :class:`ClassifierSignals`. This
makes the classifier trivially testable with parametric mocks (AC-5).

ADRs honoured: phase-3 ADR-0006 (typed variants only — every failure
mode must round-trip through :data:`JailedSubprocessResult`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from codegenie.errors import (
    DisallowedSubprocessError,
    ProbeTimeoutError,
    ToolMissingError,
)
from codegenie.exec import ProcessResult
from codegenie.transforms.sandbox_jail import (
    Completed,
    DiskQuotaExceeded,
    JailedSubprocessResult,
    JailSetupFailed,
    NetworkDenied,
    OomKilled,
    RegistryAllowlist,
    TimedOut,
)

__all__ = ["ClassifierSignals", "classify_outcome"]


# 100 ms slack on the timeout-deadline check — the subprocess wrapper's
# SIGTERM/SIGKILL escalation can stretch the wall-clock by up to
# ``_SIGTERM_GRACE_S`` (codegenie.exec); we treat anything within that
# window as "the budget was hit."
_TIMEOUT_SLACK_S: Final[float] = 0.1

# Stderr signatures the classifier treats as evidence of a network-policy
# block. Order is irrelevant — any single match qualifies. Keep this list
# tight; loose patterns produce false-positive ``NetworkDenied`` outcomes
# that the orchestrator surfaces as operator-blocking events.
_NETWORK_DENIED_PATTERNS: Final[tuple[re.Pattern[bytes], ...]] = (
    re.compile(rb"connect:\s+Network is unreachable"),
    re.compile(rb"connect:\s+Permission denied"),
    re.compile(rb"getaddrinfo.*Temporary failure"),
    re.compile(rb"getaddrinfo.*Name or service not known"),
    re.compile(rb"ENETUNREACH"),
    re.compile(rb"ECONNREFUSED.*blocked"),
)

# Stderr signatures the classifier treats as evidence of a disk-quota /
# tmpfs-full failure. Best-effort — the orchestrator surfaces a
# ``DiskQuotaExceeded`` variant only when the signature matches AND the
# caller supplied a quota signal.
_DISK_QUOTA_PATTERNS: Final[tuple[re.Pattern[bytes], ...]] = (
    re.compile(rb"No space left on device"),
    re.compile(rb"ENOSPC"),
    re.compile(rb"Disk quota exceeded"),
)

# Hostnames are conservatively parsed out of the spec's argv as the
# substring after ``https://`` or ``http://`` up to the next ``/`` or
# port separator. Mirrors the simplest sufficient parse for the AC-9
# fixture (``node -e "fetch('https://github.com/')"``).
_HOST_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"https?://([^/:'\"\s]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClassifierSignals:
    """Substrate-collected post-mortem signals fed to :func:`classify_outcome`.

    All fields are observations; the classifier owns the policy that maps
    them to a :data:`JailedSubprocessResult` variant. Keeping the signal
    bag separate from the policy makes adding a new substrate
    (``FirecrackerAdapter``, ``SandboxExecAdapter``) a matter of populating
    this dataclass — the policy is reused unchanged.
    """

    elapsed_s: float
    peak_rss_mib: int
    oom_kill_count: int = 0
    tmpfs_quota_bytes: int | None = None
    tmpfs_bytes_written: int | None = None


def _extract_hosts(cmd: tuple[str, ...]) -> list[str]:
    """Return the lowercased hostnames mentioned in *cmd* — used for the
    NetworkDenied false-positive prevention rule (AC-5).
    """
    hosts: list[str] = []
    for token in cmd:
        for match in _HOST_PATTERN.finditer(token):
            hosts.append(match.group(1).lower())
    return hosts


def _is_sigkill(returncode: int) -> bool:
    """SIGKILL on POSIX surfaces as ``-9`` (``-signal.SIGKILL``)."""
    return returncode == -9


def classify_outcome(
    process_result: ProcessResult | None,
    raised_exception: BaseException | None,
    spec_cmd: tuple[str, ...],
    spec_time_budget_s: float,
    spec_memory_mib: int,
    spec_network_hosts: frozenset[str] | None,
    signals: ClassifierSignals,
) -> JailedSubprocessResult:
    """Map a chokepoint outcome to a typed :data:`JailedSubprocessResult`.

    Exactly one of *process_result* / *raised_exception* must be non-None.
    The classifier never raises — every failure mode rides home as a
    typed variant.

    Dispatch order (AC-5 SIGKILL discriminator):

    1. Typed exceptions from the chokepoint → :class:`JailSetupFailed` /
       :class:`TimedOut`.
    2. SIGKILL + elapsed at deadline → :class:`TimedOut`.
    3. SIGKILL + OOM evidence → :class:`OomKilled`.
    4. Non-zero exit + NetworkDenied stderr signature + host-not-in-allowlist
       → :class:`NetworkDenied`.
    5. Non-zero exit + DiskQuota stderr signature + quota signal
       → :class:`DiskQuotaExceeded`.
    6. Else → :class:`Completed`.

    Args:
        process_result: Chokepoint return value (``None`` if it raised).
        raised_exception: Exception raised by the chokepoint (``None`` on
            clean return).
        spec_cmd: Verbatim ``spec.cmd`` (used for host extraction in the
            NetworkDenied check).
        spec_time_budget_s: ``spec.time_budget_s`` — deadline tie-break
            input.
        spec_memory_mib: ``spec.memory_mib`` — OOM tie-break input.
        spec_network_hosts: For :class:`RegistryAllowlist` networks, the
            ``hosts`` frozen-set (string form). ``None`` for ``DenyAll``
            (any external host is by definition outside the allowlist).
        signals: Substrate-collected post-mortem observations.

    Returns:
        The :data:`JailedSubprocessResult` variant that best describes the
        outcome.
    """
    # ── (1) Typed-exception fence ─────────────────────────────────────────
    if raised_exception is not None:
        if isinstance(raised_exception, ProbeTimeoutError):
            return TimedOut(
                kind="timed_out",
                budget_s=spec_time_budget_s,
                elapsed_s=max(spec_time_budget_s, signals.elapsed_s),
            )
        if isinstance(raised_exception, DisallowedSubprocessError):
            return JailSetupFailed(
                kind="jail_setup_failed",
                reason="binary-not-allowlisted",
                detail=str(raised_exception),
            )
        if isinstance(raised_exception, ToolMissingError):
            return JailSetupFailed(
                kind="jail_setup_failed",
                reason="bwrap-not-on-path",
                detail=str(raised_exception),
            )
        if isinstance(raised_exception, FileNotFoundError | NotADirectoryError):
            return JailSetupFailed(
                kind="jail_setup_failed",
                reason="cwd-missing",
                detail=str(raised_exception),
            )
        if isinstance(raised_exception, PermissionError):
            return JailSetupFailed(
                kind="jail_setup_failed",
                reason="cap-net-admin-missing",
                detail=str(raised_exception),
            )
        # Any other OSError or runtime failure during jail setup.
        return JailSetupFailed(
            kind="jail_setup_failed",
            reason="kernel-setup-failed",
            detail=str(raised_exception) or type(raised_exception).__name__,
        )

    # If we got here, the chokepoint returned cleanly.
    if process_result is None:
        # Programming error — caller violated the precondition.
        return JailSetupFailed(
            kind="jail_setup_failed",
            reason="kernel-setup-failed",
            detail="classifier invoked with both process_result=None and raised_exception=None",
        )

    rc = process_result.returncode
    stderr = process_result.stderr or b""
    stdout_bytes = len(process_result.stdout or b"")
    stderr_bytes = len(stderr)

    # ── (2) SIGKILL discriminator ─────────────────────────────────────────
    if _is_sigkill(rc):
        # (2a) Timeout wins the tie-break — elapsed at/above deadline ⇒ timeout.
        if signals.elapsed_s >= (spec_time_budget_s - _TIMEOUT_SLACK_S):
            return TimedOut(
                kind="timed_out",
                budget_s=spec_time_budget_s,
                elapsed_s=signals.elapsed_s,
            )
        # (2b) OOM — cgroup kill counter or peak_rss above limit.
        if signals.oom_kill_count > 0 or signals.peak_rss_mib >= spec_memory_mib:
            return OomKilled(
                kind="oom_killed",
                peak_rss_mib=signals.peak_rss_mib,
            )
        # (2c) Third-party SIGKILL — preserve the exit code as Completed.
        return Completed(
            kind="completed",
            exit_code=rc,
            stdout_bytes=stdout_bytes,
            stderr_bytes=stderr_bytes,
            wall_time_s=signals.elapsed_s,
        )

    # ── (3) NetworkDenied — non-zero exit + stderr signature + host check ─
    if rc != 0 and any(p.search(stderr) for p in _NETWORK_DENIED_PATTERNS):
        cmd_hosts = _extract_hosts(spec_cmd)
        if cmd_hosts:
            denied = _first_denied_host(cmd_hosts, spec_network_hosts)
            if denied is not None:
                return NetworkDenied(kind="network_denied", host=denied)
        # Stderr matched but no host literal found in cmd. False-positive
        # prevention: fall through to Completed rather than guess.

    # ── (4) DiskQuotaExceeded — best-effort ────────────────────────────────
    if rc != 0 and any(p.search(stderr) for p in _DISK_QUOTA_PATTERNS):
        if signals.tmpfs_quota_bytes is not None and signals.tmpfs_bytes_written is not None:
            return DiskQuotaExceeded(
                kind="disk_quota_exceeded",
                quota_bytes=signals.tmpfs_quota_bytes,
                bytes_written=signals.tmpfs_bytes_written,
            )
        # Signature matched but no quota signals — fall through (AC-5: best-effort).

    # ── (5) Clean exit (zero or non-zero with no matched signature) ───────
    return Completed(
        kind="completed",
        exit_code=rc,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        wall_time_s=signals.elapsed_s,
    )


def _first_denied_host(
    cmd_hosts: list[str],
    allowlist: frozenset[str] | None,
) -> str | None:
    """Return the first host in *cmd_hosts* that is not in *allowlist*.

    ``allowlist=None`` (a :class:`~codegenie.transforms.sandbox_jail.DenyAll`
    policy) treats every host as denied — the first host wins. Allowlist
    membership is checked against the bare host (no scheme) — the
    constants in ``allowlist`` are full ``https://`` URLs per
    :class:`RegistryAllowlist`, so we normalise both sides.
    """
    if allowlist is None:
        return cmd_hosts[0]
    bare_allowed = {_bare_host(h) for h in allowlist}
    for host in cmd_hosts:
        if host not in bare_allowed:
            return host
    return None


def _bare_host(url_or_host: str) -> str:
    """Strip the ``https://`` (or ``http://``) prefix from a URL; return
    the host (lowercased) for set comparison."""
    lowered = url_or_host.lower()
    for prefix in ("https://", "http://"):
        if lowered.startswith(prefix):
            return lowered[len(prefix) :].split("/", 1)[0].split(":", 1)[0]
    return lowered


# Re-export for downstream Adapters that want a direct reference to
# ``RegistryAllowlist`` for the hosts extraction (kept here so adapter
# code only imports from this module + sandbox_jail, no transitive needs).
_ = RegistryAllowlist
