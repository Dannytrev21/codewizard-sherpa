"""AC-5 + AC-23 — pure classifier tests covering every variant and every
SIGKILL discriminator branch.
"""

from __future__ import annotations

import pytest

from codegenie.errors import (
    DisallowedSubprocessError,
    ProbeTimeoutError,
    ToolMissingError,
)
from codegenie.exec import ProcessResult
from codegenie.transforms.sandbox._classify import (
    ClassifierSignals,
    classify_outcome,
)
from codegenie.transforms.sandbox_jail import (
    Completed,
    DiskQuotaExceeded,
    JailSetupFailed,
    NetworkDenied,
    OomKilled,
    TimedOut,
)


def _signals(**over: object) -> ClassifierSignals:
    base: dict[str, object] = dict(elapsed_s=0.05, peak_rss_mib=10, oom_kill_count=0)
    base.update(over)
    return ClassifierSignals(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Clean exit → Completed.
# ---------------------------------------------------------------------------


def test_clean_zero_exit_is_completed() -> None:
    result = classify_outcome(
        process_result=ProcessResult(returncode=0, stdout=b"hi", stderr=b""),
        raised_exception=None,
        spec_cmd=("/bin/echo", "hi"),
        spec_time_budget_s=5.0,
        spec_memory_mib=128,
        spec_network_hosts=None,
        signals=_signals(),
    )
    assert isinstance(result, Completed)
    assert result.exit_code == 0
    assert result.stdout_bytes == 2


def test_non_zero_exit_with_no_signature_is_completed() -> None:
    """Ambiguous failure → fall through to Completed, NOT NetworkDenied."""
    result = classify_outcome(
        process_result=ProcessResult(returncode=1, stdout=b"", stderr=b"some random failure"),
        raised_exception=None,
        spec_cmd=("node", "-e", "process.exit(1)"),
        spec_time_budget_s=5.0,
        spec_memory_mib=128,
        spec_network_hosts=None,
        signals=_signals(),
    )
    assert isinstance(result, Completed)
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# SIGKILL discriminator — deadline wins (tie-break #1).
# ---------------------------------------------------------------------------


def test_sigkill_at_deadline_is_timedout() -> None:
    result = classify_outcome(
        process_result=ProcessResult(returncode=-9, stdout=b"", stderr=b""),
        raised_exception=None,
        spec_cmd=("/bin/sleep", "100"),
        spec_time_budget_s=5.0,
        spec_memory_mib=128,
        spec_network_hosts=None,
        signals=_signals(elapsed_s=5.05, peak_rss_mib=10, oom_kill_count=0),
    )
    assert isinstance(result, TimedOut)
    assert result.budget_s == 5.0


def test_sigkill_with_oom_evidence_is_oomkilled() -> None:
    result = classify_outcome(
        process_result=ProcessResult(returncode=-9, stdout=b"", stderr=b""),
        raised_exception=None,
        spec_cmd=("/bin/echo", "x"),
        spec_time_budget_s=5.0,
        spec_memory_mib=128,
        spec_network_hosts=None,
        signals=_signals(elapsed_s=0.5, peak_rss_mib=200, oom_kill_count=1),
    )
    assert isinstance(result, OomKilled)
    assert result.peak_rss_mib == 200


def test_sigkill_with_peak_rss_at_limit_is_oomkilled() -> None:
    """OOM kill counter is 0 but peak_rss >= memory_mib — still OOM."""
    result = classify_outcome(
        process_result=ProcessResult(returncode=-9, stdout=b"", stderr=b""),
        raised_exception=None,
        spec_cmd=("/bin/echo", "x"),
        spec_time_budget_s=5.0,
        spec_memory_mib=128,
        spec_network_hosts=None,
        signals=_signals(elapsed_s=0.5, peak_rss_mib=128, oom_kill_count=0),
    )
    assert isinstance(result, OomKilled)


def test_sigkill_no_deadline_no_oom_falls_through_to_completed() -> None:
    """Third-party SIGKILL — neither deadline nor OOM — preserve exit code."""
    result = classify_outcome(
        process_result=ProcessResult(returncode=-9, stdout=b"", stderr=b""),
        raised_exception=None,
        spec_cmd=("/bin/echo", "x"),
        spec_time_budget_s=5.0,
        spec_memory_mib=128,
        spec_network_hosts=None,
        signals=_signals(elapsed_s=0.5, peak_rss_mib=10, oom_kill_count=0),
    )
    assert isinstance(result, Completed)
    assert result.exit_code == -9


# ---------------------------------------------------------------------------
# NetworkDenied — false-positive prevention.
# ---------------------------------------------------------------------------


def test_network_denied_with_signature_and_disallowed_host() -> None:
    result = classify_outcome(
        process_result=ProcessResult(
            returncode=6,
            stdout=b"",
            stderr=b"connect: Network is unreachable\n",
        ),
        raised_exception=None,
        spec_cmd=("node", "-e", "fetch('https://github.com/')"),
        spec_time_budget_s=5.0,
        spec_memory_mib=128,
        spec_network_hosts=frozenset({"https://registry.npmjs.org"}),
        signals=_signals(),
    )
    assert isinstance(result, NetworkDenied)
    assert result.host == "github.com"


def test_signature_matches_but_host_in_allowlist_falls_through() -> None:
    """The exact denial signature is ambiguous when the cmd host IS in the
    allowlist — fall through to Completed rather than misclassify."""
    result = classify_outcome(
        process_result=ProcessResult(
            returncode=6,
            stdout=b"",
            stderr=b"connect: Network is unreachable\n",
        ),
        raised_exception=None,
        spec_cmd=("node", "-e", "fetch('https://registry.npmjs.org/foo')"),
        spec_time_budget_s=5.0,
        spec_memory_mib=128,
        spec_network_hosts=frozenset({"https://registry.npmjs.org"}),
        signals=_signals(),
    )
    assert isinstance(result, Completed)


def test_signature_matches_but_no_host_in_cmd_falls_through() -> None:
    result = classify_outcome(
        process_result=ProcessResult(
            returncode=6,
            stdout=b"",
            stderr=b"connect: Network is unreachable\n",
        ),
        raised_exception=None,
        spec_cmd=("/bin/false",),
        spec_time_budget_s=5.0,
        spec_memory_mib=128,
        spec_network_hosts=None,
        signals=_signals(),
    )
    assert isinstance(result, Completed)


# ---------------------------------------------------------------------------
# DiskQuotaExceeded — best-effort, requires signal + signature.
# ---------------------------------------------------------------------------


def test_disk_quota_with_signature_and_signals_returns_typed_variant() -> None:
    result = classify_outcome(
        process_result=ProcessResult(
            returncode=28,
            stdout=b"",
            stderr=b"write: No space left on device\n",
        ),
        raised_exception=None,
        spec_cmd=("/bin/dd", "if=/dev/zero", "of=/tmp/x"),
        spec_time_budget_s=5.0,
        spec_memory_mib=128,
        spec_network_hosts=None,
        signals=_signals(tmpfs_quota_bytes=1024, tmpfs_bytes_written=2048),
    )
    assert isinstance(result, DiskQuotaExceeded)
    assert result.quota_bytes == 1024
    assert result.bytes_written == 2048


def test_disk_quota_signature_without_signal_falls_through_to_completed() -> None:
    result = classify_outcome(
        process_result=ProcessResult(
            returncode=28,
            stdout=b"",
            stderr=b"No space left on device\n",
        ),
        raised_exception=None,
        spec_cmd=("/bin/dd",),
        spec_time_budget_s=5.0,
        spec_memory_mib=128,
        spec_network_hosts=None,
        signals=_signals(),
    )
    assert isinstance(result, Completed)
    assert result.exit_code == 28


# ---------------------------------------------------------------------------
# Typed exceptions → JailSetupFailed / TimedOut.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc, expected_reason",
    [
        (DisallowedSubprocessError("bwrap blocked"), "binary-not-allowlisted"),
        (ToolMissingError("bwrap missing"), "bwrap-not-on-path"),
        (FileNotFoundError("/no/such"), "cwd-missing"),
        (NotADirectoryError("/etc/passwd"), "cwd-missing"),
        (PermissionError("EPERM"), "cap-net-admin-missing"),
        (OSError("kernel said no"), "kernel-setup-failed"),
    ],
)
def test_typed_exceptions_map_to_jail_setup_failed(
    exc: BaseException, expected_reason: str
) -> None:
    result = classify_outcome(
        process_result=None,
        raised_exception=exc,
        spec_cmd=("/bin/echo",),
        spec_time_budget_s=5.0,
        spec_memory_mib=128,
        spec_network_hosts=None,
        signals=_signals(),
    )
    assert isinstance(result, JailSetupFailed)
    assert result.reason == expected_reason


def test_probe_timeout_exception_maps_to_timed_out() -> None:
    result = classify_outcome(
        process_result=None,
        raised_exception=ProbeTimeoutError("bwrap exceeded timeout_s=5.0 (elapsed_ms=5050)"),
        spec_cmd=("/bin/sleep", "100"),
        spec_time_budget_s=5.0,
        spec_memory_mib=128,
        spec_network_hosts=None,
        signals=_signals(elapsed_s=5.05),
    )
    assert isinstance(result, TimedOut)
    assert result.budget_s == 5.0


def test_neither_result_nor_exception_is_a_jail_setup_failure() -> None:
    """Defence in depth: programming-error caller path → typed variant,
    not a raise (AC-16)."""
    result = classify_outcome(
        process_result=None,
        raised_exception=None,
        spec_cmd=("/bin/echo",),
        spec_time_budget_s=5.0,
        spec_memory_mib=128,
        spec_network_hosts=None,
        signals=_signals(),
    )
    assert isinstance(result, JailSetupFailed)
