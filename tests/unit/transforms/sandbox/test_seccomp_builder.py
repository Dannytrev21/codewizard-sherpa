"""S4-02 AC-3 (helper-input + helper-output) + AC-24 seccomp builder.

The integration / kernel-boundary test (AC-3 tier 3) is in
``tests/integration/transforms/test_bwrap_seccomp_live.py`` —
Linux-only and gated on ``shutil.which("bwrap")``.
"""

from __future__ import annotations

import pytest

from codegenie.transforms.sandbox._seccomp import Syscall, build_filter
from codegenie.transforms.sandbox.bwrap import _BLOCKED_SYSCALLS


def test_blocked_syscalls_constant_matches_adr_0006() -> None:
    """AC-24 + AC-3: the closed-set blocked syscalls.

    ADR-0006 §Decision pins exactly six syscalls: mount, pivot_root,
    ptrace, bpf, unshare, keyctl.
    """
    assert _BLOCKED_SYSCALLS == frozenset(
        {
            Syscall.MOUNT,
            Syscall.PIVOT_ROOT,
            Syscall.PTRACE,
            Syscall.BPF,
            Syscall.UNSHARE,
            Syscall.KEYCTL,
        }
    )
    assert len(_BLOCKED_SYSCALLS) == 6


def test_build_filter_returns_non_empty_bytes() -> None:
    blob = build_filter(_BLOCKED_SYSCALLS)
    assert isinstance(blob, bytes)
    assert len(blob) > 0
    # 11 BPF instructions × 8 bytes/instruction = 88 bytes for six syscalls.
    assert len(blob) == 88


def test_build_filter_rejects_empty_blocked_set() -> None:
    with pytest.raises(ValueError, match="empty_filter"):
        build_filter(frozenset())


def test_build_filter_input_changes_change_output() -> None:
    """AC-24 mutation-resistance: dropping a syscall changes the bytes."""
    full = build_filter(_BLOCKED_SYSCALLS)
    dropped = build_filter(_BLOCKED_SYSCALLS - {Syscall.PTRACE})
    assert full != dropped, "build_filter is not sensitive to input — likely returns a constant"


def test_build_filter_is_deterministic() -> None:
    """AC-17 helper-side determinism: two calls with the same input
    return identical bytes."""
    a = build_filter(_BLOCKED_SYSCALLS)
    b = build_filter(_BLOCKED_SYSCALLS)
    assert a == b


def test_each_single_syscall_filter_is_distinct() -> None:
    """AC-24: ``build_filter(frozenset({s_a}))`` != ``build_filter(frozenset({s_b}))``."""
    blobs = {s: build_filter(frozenset({s})) for s in Syscall}
    assert len(set(blobs.values())) == len(blobs), (
        "different single-syscall filters collapsed to the same bytes"
    )


def test_syscall_strenum_has_six_members() -> None:
    members = set(Syscall)
    assert len(members) == 6
    assert {m.value for m in members} == {
        "mount",
        "pivot_root",
        "ptrace",
        "bpf",
        "unshare",
        "keyctl",
    }
