"""``codegenie.transforms.sandbox`` — Hexagonal Adapters for the
:class:`SubprocessJail` Port (S4-01).

This package holds the substrate-specific Adapters that implement the
Phase-3 jail surface:

* :class:`BwrapAdapter` (S4-02) — Linux ``bwrap --unshare-all`` + seccomp +
  network namespace.
* ``SandboxExecAdapter`` (S4-03) — macOS ``sandbox-exec`` with a hardened
  profile. Lands in a follow-up story.

The shared, pure helpers — :mod:`._classify` (outcome classifier) and
:mod:`._seccomp` (hand-written BPF filter) — are consumed by both Adapters
so the SIGKILL discriminator, NetworkDenied false-positive prevention,
and blocked-syscall list live in exactly one place.

ADRs honoured: phase-3 ADR-0006 (this Port + Adapters), production ADR-0012
(microVM substitution at Phase 5 substitutes via the same Port — no edits
to this module).
"""

from codegenie.transforms.sandbox.bwrap import BwrapAdapter

__all__ = ["BwrapAdapter"]
