"""Phase 6 S1-02 — pure chain-head helper substrate (ADR-0003 replay gate).

The function :func:`_compute_chain_head` is the single canonical-declaration
site for the BLAKE3 chain-head computation Phase-6 S2-02's replay verifier
will dispatch on. Discipline (Rule 5 + CLAUDE.md "functional core /
imperative shell"):

* No I/O — no filesystem, no env, no clock, no network, no randomness.
* No hidden state — same inputs ⇒ same output across processes / Python
  versions / Local-vs-Temporal SUT substrates.
* Routes hashing through :mod:`codegenie.hashing` (ADR-0001 chokepoint —
  the BLAKE3 import lives there, not here).

The AST no-side-effects fence at
``tests/fence/test_chain_head_purity.py`` walks this module and refuses
names like ``open``, ``socket``, ``time.time``, ``datetime.now``,
``random``, ``uuid``, ``os.environ`` — the moment any later story tries
to widen the chain-head path with impurity, CI fails loud. This guard
exists because the Phase-9 S4-05 G5 byte-equality story depends on the
*same* event sequence producing the *same* chain head across both
``LocalVulnRemediationSut`` and ``TemporalVulnRemediationSut`` — any
clock/env dependency would spuriously trip
``FailedUnrecoverable(reason="checkpoint_integrity")`` on resume.

Wire shape: :data:`~codegenie.types.identifiers.ChainHead` is a bare
64-char lowercase hex string (no ``"blake3:"`` prefix — convention pinned
by the existing Phase-4 ``parse_chain_head`` + every existing call site
in :mod:`codegenie.rag.store` and :mod:`codegenie.plugins.events`). The
``content_hash_bytes`` chokepoint returns ``"blake3:<64hex>"``; we strip
the prefix here to keep the newtype shape stable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codegenie.hashing import content_hash_bytes
from codegenie.types.identifiers import ChainHead

if TYPE_CHECKING:  # pragma: no cover — type-checker-only
    from codegenie.workflows.vuln_ledger import TransitionEvent

__all__ = ["_compute_chain_head"]

_BLAKE3_PREFIX = "blake3:"


def _compute_chain_head(prior_head: ChainHead, event: TransitionEvent) -> ChainHead:
    """Return ``ChainHead`` for ``(prior_head, event)`` — pure functional core.

    Computation:

    1. Encode ``prior_head`` UTF-8 → bytes.
    2. Encode ``event.model_dump_json()`` UTF-8 → bytes. Pydantic v2's
       JSON dumper is deterministic on a frozen / ``extra="forbid"``
       model (no insertion-order drift).
    3. Concatenate (a separator byte ``\\x1e`` — ASCII Record Separator,
       cannot appear in either UTF-8 hex or JSON output — defuses the
       boundary-shift attack a printable separator would open, mirroring
       :mod:`codegenie.hashing`'s ``_RECORD_SEP`` discipline).
    4. Hash with ``content_hash_bytes`` (BLAKE3 chokepoint).
    5. Strip the canonical ``"blake3:"`` prefix to return a bare 64-hex
       ``ChainHead`` — matches the existing newtype shape.

    Mutation-resistance properties exercised by
    ``tests/unit/workflows/test_chain_head_properties.py``:

    * **Stability** — same ``(prior, event)`` ⇒ byte-equal ``ChainHead``
      across two computations.
    * **Sensitivity** — any field change in ``event`` (or in
      ``prior_head``) changes the output. Mutants that omit a field from
      the canonical bytes die here.
    * **Chain-forward extension** — folding a sequence of events through
      this helper is a pure function of the sequence; no hidden state.
    """
    payload = prior_head.encode("utf-8") + b"\x1e" + event.model_dump_json().encode("utf-8")
    prefixed = content_hash_bytes(payload)
    return ChainHead(prefixed.removeprefix(_BLAKE3_PREFIX))
