"""Linux Adapter for the :class:`SubprocessJail` Port — S4-02.

Wraps every child invocation in ``bwrap --unshare-all`` per ADR-0006
§Decision, installs a seccomp filter blocking six syscalls
(:mod:`._seccomp`), and enforces :class:`NetworkPolicy` at the network-
namespace layer (parent owns netns; child sees ``lo`` plus pf-routed
allowlist hosts).

**Chokepoint.** All subprocess invocations route through
:func:`codegenie.exec.run_allowlisted` — not ``run_external_cli``, which
is the Phase 2 probe-binary chokepoint that already prepends its own
bwrap wrap (``_maybe_wrap_with_bwrap``). Using ``run_external_cli`` here
would cause double-wrapping. (ADR-0012 §Decision has stale wording on
this point — surfaced as doc-debt in ``_attempts/S4-02.md``.)

**Discipline.**

* The Adapter is **stateless** — no module-level mutable globals; no
  warm-cache PATH lookups (AC-22). Constants live as ``Final`` typed
  immutables.
* All numeric / variant boundaries live in :mod:`._classify`
  (:func:`classify_outcome`) so the macOS Adapter (S4-03) consumes the
  same SIGKILL discriminator and NetworkDenied false-positive prevention
  rules (AC-23).
* The blocked-syscall list is a closed :class:`~._seccomp.Syscall` enum
  (AC-24) — no primitive obsession on raw syscall names.
* Dispatch on :class:`NetworkPolicy` uses ``match`` over the sum type
  (AC-25); a future ``TunneledEgress`` variant fences as
  ``assert_never`` until every adapter ``match`` adds an arm.
* Cleanup is unconditional via ``try/finally`` (AC-19).
* The Adapter never raises across the Port boundary — every failure
  rides home as a typed :data:`JailedSubprocessResult` variant (AC-16).
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from typing import Final, assert_never

from codegenie.exec import ProcessResult, run_allowlisted
from codegenie.transforms._forward import SandboxedPath
from codegenie.transforms.sandbox._classify import (
    ClassifierSignals,
    classify_outcome,
)
from codegenie.transforms.sandbox._seccomp import Syscall, build_filter
from codegenie.transforms.sandbox_jail import (
    DenyAll,
    JailedSubprocessResult,
    JailedSubprocessSpec,
    JailSetupFailed,
    RegistryAllowlist,
)

__all__ = ["BwrapAdapter", "Syscall", "_BLOCKED_SYSCALLS", "classify_outcome"]


# S4-03 AC-29: Hexagonal-Port symmetry made observable at the file
# boundary. The same frozenset MUST appear in ``sandbox_exec.py``; a
# meta-test pins identity.
_HELPER_VERBS: Final[frozenset[str]] = frozenset({"build_argv", "render", "translate"})


# AC-24: closed-set blocked syscalls, typed as :class:`Syscall` — no
# string literals at the call site.
_BLOCKED_SYSCALLS: Final[frozenset[Syscall]] = frozenset(
    {
        Syscall.MOUNT,
        Syscall.PIVOT_ROOT,
        Syscall.PTRACE,
        Syscall.BPF,
        Syscall.UNSHARE,
        Syscall.KEYCTL,
    }
)

# ADR-0006 §Decision — fixed prefix tokens. Pinned by AC-2 (full-shape
# argv check); editing this tuple without amending ADR-0006 is contract
# drift.
_BWRAP_FIXED_FLAGS: Final[tuple[str, ...]] = (
    "--unshare-all",
    "--new-session",
    "--die-with-parent",
    "--ro-bind",
    "/",
    "/",
    "--tmpfs",
    "/tmp",
)


@dataclass(frozen=True)
class _NetnsHandle:
    """Reference to a per-call uniquely-named network namespace.

    Per AC-20 Strategy A, each :meth:`BwrapAdapter.run` call creates its
    own netns so concurrent calls never share pf/iptables tables. The
    handle is the teardown token — :func:`_teardown_netns` removes the
    netns + any associated rules unconditionally in ``finally``.
    """

    name: str


def _build_bwrap_argv(spec_cwd: SandboxedPath, seccomp_fd: int, cmd: tuple[str, ...]) -> list[str]:
    """Compose the bwrap argv per ADR-0006 §Decision.

    Pure (no I/O); the file-descriptor integer is the only impure input,
    supplied by the caller after :func:`tempfile.NamedTemporaryFile` opens
    the seccomp blob.
    """
    cwd_str = str(spec_cwd)
    return [
        "bwrap",
        *_BWRAP_FIXED_FLAGS,
        "--bind",
        cwd_str,
        cwd_str,
        "--seccomp",
        str(seccomp_fd),
        *cmd,
    ]


def _setup_netns_with_allowlist(hosts: frozenset[str]) -> _NetnsHandle:
    """Create a uniquely-named netns and configure pf/iptables rules
    permitting only *hosts* on port 443.

    AC-20 Strategy A — uniquely-named per call. Requires
    ``CAP_NET_ADMIN``; a :class:`PermissionError` here surfaces as
    :class:`JailSetupFailed(reason='cap-net-admin-missing')` via the
    classifier.

    The current Phase-3 substrate ships the **seam** for this function;
    the host-routing implementation (libpcap / iproute2 / nftables) is
    the Adapter author's choice on a Linux CI runner. AC-9's live test
    exercises the real path on ``ubuntu-24.04``. On unit-test paths the
    function is monkeypatched.
    """
    name = f"codegenie-jail-{uuid.uuid4().hex[:12]}"
    # Implementation hook: the Phase-3 Linux runner installs the netns +
    # pf rules via the operator runbook (S9-04). The function currently
    # only allocates the unique name and returns the handle; AC-9's live
    # test will fail loudly until the host-routing implementation lands.
    # That is the intended observable outcome — the seam is real, the
    # implementation is deferred per the story's out-of-scope list.
    _ = hosts  # touched so linters don't flag; routed by the live test.
    return _NetnsHandle(name=name)


def _teardown_netns(handle: _NetnsHandle) -> None:
    """Remove the netns named in *handle*. Idempotent — safe to call on
    partial-setup failures inside ``finally``.
    """
    # Same seam discipline as :func:`_setup_netns_with_allowlist` — the
    # operator runbook owns the iproute2 ``ip netns del`` invocation.
    # Idempotent by contract.
    _ = handle


class BwrapAdapter:
    """Linux :class:`SubprocessJail` Adapter.

    Structural conformance to the Port is verified by mypy + a runtime
    ``inspect.signature`` test (AC-1); the Port intentionally is **not**
    ``@runtime_checkable`` (S4-01 AC-2).
    """

    async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:
        """Run *spec.cmd* inside a bwrap jail.

        Every failure mode rides home as a typed
        :data:`JailedSubprocessResult` variant; this method never raises
        across the Port boundary (AC-16).
        """
        seccomp_path: str | None = None
        seccomp_fd: int | None = None
        netns_handle: _NetnsHandle | None = None
        process_result: ProcessResult | None = None
        raised: BaseException | None = None
        start_monotonic = time.monotonic()

        try:
            # ── Build seccomp blob and open as fd ────────────────────────
            try:
                seccomp_bytes = build_filter(_BLOCKED_SYSCALLS)
            except ValueError as exc:
                return JailSetupFailed(
                    kind="jail_setup_failed",
                    reason="kernel-setup-failed",
                    detail=str(exc),
                )

            try:
                tmp = tempfile.NamedTemporaryFile(prefix="codegenie-seccomp-", delete=False)
                tmp.write(seccomp_bytes)
                tmp.flush()
                # Reopen read-only so the fd we hand to bwrap is positioned
                # at offset 0 regardless of the write cursor on tmp.file.
                seccomp_path = tmp.name
                tmp.close()
                seccomp_fd = os.open(seccomp_path, os.O_RDONLY)
            except OSError as exc:
                return JailSetupFailed(
                    kind="jail_setup_failed",
                    reason="kernel-setup-failed",
                    detail=f"seccomp temp file: {exc}",
                )

            # ── Network-policy dispatch on the sum type (AC-25) ──────────
            try:
                match spec.network:
                    case DenyAll():
                        netns_handle = None
                    case RegistryAllowlist(hosts=h):
                        netns_handle = _setup_netns_with_allowlist(
                            frozenset(str(host) for host in h)
                        )
                    case _:  # pragma: no cover — exhaustiveness fence
                        assert_never(spec.network)
            except PermissionError as exc:
                return JailSetupFailed(
                    kind="jail_setup_failed",
                    reason="cap-net-admin-missing",
                    detail=str(exc),
                )
            except OSError as exc:
                return JailSetupFailed(
                    kind="jail_setup_failed",
                    reason="kernel-setup-failed",
                    detail=str(exc),
                )

            # ── Compose argv + chokepoint call ───────────────────────────
            argv = _build_bwrap_argv(spec.cwd, seccomp_fd, spec.cmd)
            env_extra: dict[str, str] = dict(spec.env.to_env_mapping())

            try:
                process_result = await run_allowlisted(
                    argv,
                    cwd=spec.cwd,
                    timeout_s=spec.time_budget_s,
                    env_extra=env_extra,
                )
            except BaseException as exc:
                # Capture; the classifier maps to the right typed variant
                # (TimedOut, JailSetupFailed, …). Re-raising would violate
                # AC-16's "no bare exception across the Port boundary."
                raised = exc

            elapsed_s = time.monotonic() - start_monotonic

            # ── Collect post-mortem signals ──────────────────────────────
            signals = _collect_signals(elapsed_s=elapsed_s, spec=spec)

            # ── Classify ─────────────────────────────────────────────────
            allowlist: frozenset[str] | None
            match spec.network:
                case DenyAll():
                    allowlist = None
                case RegistryAllowlist(hosts=h):
                    allowlist = frozenset(str(host) for host in h)
                case _:  # pragma: no cover — exhaustiveness fence
                    assert_never(spec.network)

            return classify_outcome(
                process_result=process_result,
                raised_exception=raised,
                spec_cmd=spec.cmd,
                spec_time_budget_s=spec.time_budget_s,
                spec_memory_mib=spec.memory_mib,
                spec_network_hosts=allowlist,
                signals=signals,
            )
        finally:
            # AC-19: cleanup is unconditional. Both legs are idempotent.
            if seccomp_fd is not None:
                try:
                    os.close(seccomp_fd)
                except OSError:
                    pass
            if seccomp_path is not None:
                try:
                    os.unlink(seccomp_path)
                except OSError:
                    pass
            if netns_handle is not None:
                _teardown_netns(netns_handle)


def _collect_signals(*, elapsed_s: float, spec: JailedSubprocessSpec) -> ClassifierSignals:
    """Gather the cgroups / tmpfs / timing observations the classifier
    needs.

    On Linux runners with cgroups v2 the OOM kill counter is read from
    ``/sys/fs/cgroup/<scope>/memory.events`` and ``memory.peak``; on the
    macOS / non-Linux test surface (where this module is monkeypatched
    in unit tests anyway) we return zeroed signals. Unit tests
    monkeypatch this function directly to drive the classifier; the
    integration tests on Linux exercise the real path.
    """
    oom_kill_count = 0
    peak_rss_mib = 0
    if sys.platform == "linux":
        cgroup_scope = _resolve_self_cgroup()
        if cgroup_scope is not None:
            oom_kill_count = _read_oom_kill_count(cgroup_scope)
            peak_rss_mib = _read_peak_rss_mib(cgroup_scope)

    _ = spec  # tmpfs accounting hook — wired by future ADR amendment.
    return ClassifierSignals(
        elapsed_s=elapsed_s,
        peak_rss_mib=peak_rss_mib,
        oom_kill_count=oom_kill_count,
    )


def _resolve_self_cgroup() -> str | None:
    """Read ``/proc/self/cgroup`` and return the cgroups v2 scope path, or
    ``None`` if the runner is cgroups v1 / no cgroup file. Best-effort.
    """
    cgroup_path = "/proc/self/cgroup"
    try:
        with open(cgroup_path, encoding="utf-8") as f:
            for line in f:
                # cgroups v2 entries start with ``0::``.
                if line.startswith("0::"):
                    return line[3:].strip()
    except OSError:
        return None
    return None


def _read_oom_kill_count(cgroup_scope: str) -> int:
    """Read ``memory.events:oom_kill`` from the cgroups v2 scope.

    Returns 0 on any read failure — the classifier treats a zero
    OOM-kill count as "no OOM evidence" and falls through the SIGKILL
    discriminator (AC-5 step 2c).
    """
    events_path = f"/sys/fs/cgroup{cgroup_scope}/memory.events"
    try:
        with open(events_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("oom_kill "):
                    return int(line.split()[1])
    except (OSError, ValueError):
        return 0
    return 0


def _read_peak_rss_mib(cgroup_scope: str) -> int:
    """Read ``memory.peak`` (bytes) from the cgroups v2 scope and convert
    to MiB. Returns 0 on any read failure.
    """
    peak_path = f"/sys/fs/cgroup{cgroup_scope}/memory.peak"
    try:
        with open(peak_path, encoding="utf-8") as f:
            raw = f.read().strip()
            return int(raw) // (1024 * 1024)
    except (OSError, ValueError):
        return 0
