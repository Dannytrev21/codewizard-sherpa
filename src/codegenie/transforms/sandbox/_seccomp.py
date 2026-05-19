"""Hand-written seccomp BPF filter builder — S4-02 AC-3 + AC-24.

The Phase-3 jail blocks six syscalls (``mount``, ``pivot_root``, ``ptrace``,
``bpf``, ``unshare``, ``keyctl``) per ADR-0006 §Decision. Rather than pull
in a new runtime dependency (``pyseccomp`` / ``libseccomp``), this module
emits the BPF program by hand: it is roughly thirty ``struct.pack`` calls
producing the canonical Linux seccomp BPF program shape, which the kernel
parses via the ``SECCOMP_SET_MODE_FILTER`` ``prctl``.

The output is **pure bytes**. The caller (:mod:`codegenie.transforms.sandbox.bwrap`)
writes the bytes into a temp file and hands the file descriptor to
``bwrap --seccomp <fd>``. ``bwrap`` ``read(2)``-s the filter and installs
it on the child via ``seccomp(SECCOMP_SET_MODE_FILTER, ...)``.

Architecture choices pinned by the story validator (S4-02 §Validation note):

* **No new runtime dep.** A 30-line hand-written BPF program is more
  auditable than a 5,000-line C-extension import; the six syscalls are a
  fixed list.
* **Closed enum of syscalls** (:class:`Syscall`). No primitive obsession on
  raw syscall names; adding/removing a syscall is one row in the enum +
  one row in the ``_BLOCKED_SYSCALLS`` constant in
  :mod:`codegenie.transforms.sandbox.bwrap`.
* **Pure function.** No I/O, no side-effects, no globals. Same input →
  same output (AC-17 determinism property hinges on this).
* **Architecture-narrowed.** Only ``AUDIT_ARCH_X86_64`` is emitted today
  (the Phase-3 CI matrix and the operator-laptop threat model both pin
  x86_64 Linux). Multi-arch support is a follow-up; the function header
  documents the constraint.
"""

from __future__ import annotations

import struct
from enum import StrEnum
from typing import Final

__all__ = ["Syscall", "build_filter"]


class Syscall(StrEnum):
    """The six syscalls the Phase-3 jail blocks (ADR-0006 §Decision).

    The string value is the canonical Linux syscall name. The numeric x86_64
    syscall number lives in :data:`_SYSCALL_NR_X86_64` — keeping the mapping
    in one place means adding a new blocked syscall is two rows: one in
    this enum + one in the dispatch table.
    """

    MOUNT = "mount"
    PIVOT_ROOT = "pivot_root"
    PTRACE = "ptrace"
    BPF = "bpf"
    UNSHARE = "unshare"
    KEYCTL = "keyctl"


# x86_64 syscall numbers per ``/usr/include/asm/unistd_64.h``. Pinned at the
# module level so the BPF builder is pure (no ``ctypes`` import, no kernel
# header parsing at import time).
_SYSCALL_NR_X86_64: Final[dict[Syscall, int]] = {
    Syscall.MOUNT: 165,
    Syscall.PIVOT_ROOT: 155,
    Syscall.PTRACE: 101,
    Syscall.BPF: 321,
    Syscall.UNSHARE: 272,
    Syscall.KEYCTL: 250,
}

# Linux audit-arch constant for x86_64 (``linux/audit.h``):
# ``AUDIT_ARCH_X86_64 = EM_X86_64 | __AUDIT_ARCH_64BIT | __AUDIT_ARCH_LE``
# (62 | 0x80000000 | 0x40000000 = 0xC000003E).
_AUDIT_ARCH_X86_64: Final[int] = 0xC000003E

# BPF instruction opcodes (``linux/bpf_common.h``).
_BPF_LD: Final[int] = 0x00
_BPF_JMP: Final[int] = 0x05
_BPF_RET: Final[int] = 0x06
_BPF_W: Final[int] = 0x00  # word-size load
_BPF_ABS: Final[int] = 0x20  # absolute-offset addressing
_BPF_JEQ: Final[int] = 0x10  # jump-if-equal
_BPF_K: Final[int] = 0x00  # immediate operand

# seccomp_data layout (``linux/seccomp.h``):
#   struct seccomp_data { int nr; __u32 arch; __u64 instruction_pointer; ... }
# Offsets in 32-bit words: nr=0, arch=4.
_OFFSET_NR: Final[int] = 0
_OFFSET_ARCH: Final[int] = 4

# seccomp return values (``linux/seccomp.h``).
_SECCOMP_RET_ALLOW: Final[int] = 0x7FFF0000
_SECCOMP_RET_KILL_PROCESS: Final[int] = 0x80000000

# One BPF instruction is 8 bytes: ``struct sock_filter { __u16 code;
# __u8 jt; __u8 jf; __u32 k; }``.
_BPF_INSN_FMT: Final[str] = "HBBI"


def _insn(code: int, jt: int, jf: int, k: int) -> bytes:
    """Pack one ``sock_filter`` instruction (8 bytes, little-endian)."""
    return struct.pack(_BPF_INSN_FMT, code, jt, jf, k)


def build_filter(blocked: frozenset[Syscall]) -> bytes:
    """Build the seccomp BPF program blocking *blocked* syscalls on x86_64.

    Program shape::

        # Load arch from seccomp_data.
        LD W ABS [arch]
        # If arch != AUDIT_ARCH_X86_64, kill the process (defence against
        # 32-bit-syscall-on-64-bit-kernel attacks).
        JEQ AUDIT_ARCH_X86_64, jt=0, jf=KILL
        # Load syscall number.
        LD W ABS [nr]
        # For each blocked syscall: JEQ nr, jump to KILL on match.
        JEQ <nr_1>, jt=KILL_REL, jf=0
        JEQ <nr_2>, jt=KILL_REL, jf=0
        ...
        # Fall-through: allow.
        RET ALLOW
        # KILL label:
        RET KILL_PROCESS

    Args:
        blocked: Closed set of :class:`Syscall` values the filter blocks.
            Must be non-empty (an empty filter is a programming error —
            the caller should not be invoking a seccomp filter at all).

    Returns:
        Bytes of the BPF program ready to hand to ``bwrap --seccomp <fd>``.

    Raises:
        ValueError: ``blocked`` is empty.
    """
    if not blocked:
        raise ValueError(
            "sandbox._seccomp.empty_filter: build_filter requires at least one "
            "blocked syscall; empty filter is a programming error."
        )

    # Deterministic ordering — the BPF program shape depends on iteration
    # order. Sort by syscall NAME (not number) so the bytes are stable
    # across CPython hash-randomization seeds (AC-17 determinism).
    blocked_sorted = sorted(blocked, key=lambda s: s.value)

    instructions: list[bytes] = []

    # 1. Architecture check.
    instructions.append(_insn(_BPF_LD | _BPF_W | _BPF_ABS, 0, 0, _OFFSET_ARCH))
    # JEQ AUDIT_ARCH_X86_64: jt=0 (continue if match), jf=<jump-to-kill>.
    # We compute the jump-to-kill offset after all instructions are laid out,
    # so we patch it in at the end. For now use a placeholder.
    arch_check_idx = len(instructions)
    instructions.append(_insn(_BPF_JMP | _BPF_JEQ | _BPF_K, 0, 0, _AUDIT_ARCH_X86_64))

    # 2. Load syscall number.
    instructions.append(_insn(_BPF_LD | _BPF_W | _BPF_ABS, 0, 0, _OFFSET_NR))

    # 3. For each blocked syscall: JEQ nr, jt=<jump-to-kill>, jf=0 (continue).
    syscall_check_indices: list[int] = []
    for syscall in blocked_sorted:
        nr = _SYSCALL_NR_X86_64[syscall]
        syscall_check_indices.append(len(instructions))
        instructions.append(_insn(_BPF_JMP | _BPF_JEQ | _BPF_K, 0, 0, nr))

    # 4. Fall-through: RET ALLOW.
    allow_idx = len(instructions)
    instructions.append(_insn(_BPF_RET | _BPF_K, 0, 0, _SECCOMP_RET_ALLOW))

    # 5. KILL label: RET KILL_PROCESS.
    kill_idx = len(instructions)
    instructions.append(_insn(_BPF_RET | _BPF_K, 0, 0, _SECCOMP_RET_KILL_PROCESS))

    # Patch the arch-check JEQ:
    #   jt=0 (arch matches → fall through to next insn)
    #   jf=<offset to kill_idx>
    arch_jt = 0
    arch_jf = kill_idx - arch_check_idx - 1
    instructions[arch_check_idx] = _insn(
        _BPF_JMP | _BPF_JEQ | _BPF_K, arch_jt, arch_jf, _AUDIT_ARCH_X86_64
    )

    # Patch each syscall-check JEQ:
    #   jt=<offset to kill_idx>  (match → kill)
    #   jf=0                     (no match → continue to next check)
    for idx in syscall_check_indices:
        # The k (syscall nr) was already correct.
        existing = struct.unpack(_BPF_INSN_FMT, instructions[idx])
        code = existing[0]
        k = existing[3]
        jt = kill_idx - idx - 1
        instructions[idx] = _insn(code, jt, 0, k)
    # Tracker for the no-op patch on the allow-fallthrough (kept so future
    # readers can see the slot exists; the value isn't patched).
    _ = allow_idx

    return b"".join(instructions)
